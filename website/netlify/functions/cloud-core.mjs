import crypto from "node:crypto";

export const PLANS = new Set(["free", "pro", "family", "lifetime"]);
export const STATUSES = new Set(["active", "suspended"]);
export const ROLES = new Set(["user", "admin"]);
export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$/;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function isoNow() {
  return new Date().toISOString();
}

export function hashPassword(password) {
  const raw = String(password ?? "");
  if (raw.length < 8 || raw.length > 200) {
    throw new HttpError(400, "Parola 8 ile 200 karakter arasında olmalıdır.");
  }
  const salt = crypto.randomBytes(16);
  const digest = crypto.pbkdf2Sync(Buffer.from(raw, "utf8"), salt, 200_000, 32, "sha256");
  return `pbkdf2_sha256:200000:${salt.toString("hex")}:${digest.toString("hex")}`;
}

export function verifyPassword(password, stored) {
  try {
    const parts = String(stored || "").split(":", 4);
    if (parts.length !== 4 || parts[0] !== "pbkdf2_sha256") return false;
    const iters = Number(parts[1]);
    if (!Number.isInteger(iters) || iters < 10_000) return false;
    const salt = Buffer.from(parts[2], "hex");
    const expected = Buffer.from(parts[3], "hex");
    const actual = crypto.pbkdf2Sync(Buffer.from(String(password ?? ""), "utf8"), salt, iters, expected.length, "sha256");
    return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

export function issueToken(secret, userId, role, ttlSeconds = 7 * 24 * 3600) {
  const claims = {
    sub: userId,
    role,
    exp: Math.floor(Date.now() / 1000) + ttlSeconds,
    jti: crypto.randomBytes(8).toString("hex"),
  };
  const body = Buffer.from(JSON.stringify(claims), "utf8").toString("base64url");
  const sig = crypto.createHmac("sha256", secret).update(body, "ascii").digest("base64url");
  return `${body}.${sig}`;
}

export function verifyTokenClaims(secret, token) {
  if (!token || !token.includes(".")) return null;
  try {
    const [body, sigB64] = token.trim().split(".", 2);
    const expected = crypto.createHmac("sha256", secret).update(body, "ascii").digest();
    const actual = Buffer.from(sigB64, "base64url");
    if (actual.length !== expected.length || !crypto.timingSafeEqual(actual, expected)) return null;
    const claims = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
    if (Number(claims.exp || 0) < Math.floor(Date.now() / 1000)) return null;
    return claims;
  } catch {
    return null;
  }
}

export function effectivePlan(plan, expiresAt) {
  if (plan === "free" || plan === "lifetime" || !expiresAt) return plan;
  const ts = Date.parse(expiresAt);
  if (!Number.isNaN(ts) && ts < Date.now()) return "free";
  return plan;
}

export function publicUser(row, devices = null) {
  const expiresAt = row.expires_at || "";
  const out = {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    role: row.role,
    plan: row.plan,
    effectivePlan: effectivePlan(row.plan, expiresAt),
    status: row.status,
    maxDevices: Number(row.max_devices),
    expiresAt,
    adminNote: row.admin_note || "",
    createdAt: row.created_at,
    lastSeenAt: row.last_seen_at,
  };
  if (devices !== null) out.devices = devices;
  return out;
}

function jsonResp(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function readJsonBody(req) {
  const text = await req.text();
  if (Buffer.byteLength(text, "utf8") > 512 * 1024) throw new HttpError(400, "İstek boyutu çok büyük.");
  if (!text.trim()) return {};
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new HttpError(400, "JSON gövdesi okunamadı.");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new HttpError(400, "JSON nesnesi bekleniyor.");
  }
  return data;
}

async function checkRateLimit(pool, bucket, limit = 12, windowMs = 300_000) {
  const now = Date.now();
  const cutoff = now - windowMs;
  await pool.query("DELETE FROM rate_limits WHERE bucket = $1 AND ts < $2", [bucket, cutoff]);
  const res = await pool.query("SELECT COUNT(*)::int AS cnt FROM rate_limits WHERE bucket = $1", [bucket]);
  const count = Number(res.rows[0]?.cnt ?? 0);
  if (count >= limit) return false;
  await pool.query("INSERT INTO rate_limits (bucket, ts) VALUES ($1, $2)", [bucket, now]);
  return true;
}

async function clearRateLimit(pool, bucket) {
  await pool.query("DELETE FROM rate_limits WHERE bucket = $1", [bucket]);
}

async function ensureBootstrapAdmin(pool, env) {
  const email = env("CINEVA_ADMIN_EMAIL").trim().toLowerCase();
  const password = env("CINEVA_ADMIN_PASSWORD").trim();
  if (!email || !password || !EMAIL_RE.test(email)) return;
  const { rows } = await pool.query("SELECT id FROM users WHERE role = 'admin' LIMIT 1");
  if (rows.length > 0) return;
  const now = isoNow();
  const uid = "usr_admin_" + crypto.randomBytes(6).toString("hex");
  const pwHash = hashPassword(password);
  await pool.query(
    `INSERT INTO users (id, email, display_name, password_hash, role, plan, status, max_devices, expires_at, admin_note, created_at, last_seen_at)
     VALUES ($1,$2,$3,$4,'admin','lifetime','active',10,'','Sistem yöneticisi',$5,$6)
     ON CONFLICT (email) DO NOTHING`,
    [uid, email, "Yönetici", pwHash, now, now],
  );
}

async function getUserById(pool, uid, includeDevices = false) {
  const res = await pool.query("SELECT * FROM users WHERE id = $1", [uid]);
  if (!res.rows.length) return null;
  let devices = null;
  if (includeDevices) {
    const devRes = await pool.query(
      "SELECT device_id AS id, device_name AS name, platform, last_seen_at AS \"lastSeenAt\" FROM devices WHERE user_id = $1 ORDER BY last_seen_at DESC",
      [uid],
    );
    devices = devRes.rows;
  }
  return publicUser(res.rows[0], devices);
}

async function addAudit(queryable, actor, action, targetType, targetId, details) {
  await queryable.query(
    "INSERT INTO audit_logs (actor_id, actor_email, action, target_type, target_id, details, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7)",
    [actor.id, actor.email, action, targetType, targetId, JSON.stringify(details), isoNow()],
  );
}

async function getPublicConfig(pool) {
  const defaultAnn = { enabled: false, title: "", message: "", severity: "info" };
  const defaultVers = {
    windowsLatest: "2.0.1",
    windowsMin: "2.0.0",
    androidLatest: "2.0.1",
    androidMin: "2.0.0",
    windowsInstallerUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Setup.exe",
    windowsPortableUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Cineva.exe",
    androidApkUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Android.apk",
  };
  const cfgRes = await pool.query("SELECT key, value FROM app_config");
  const map = Object.fromEntries(cfgRes.rows.map((r) => [r.key, r.value]));
  const dlRes = await pool.query("SELECT target, count FROM download_stats");
  const downloads = Object.fromEntries(dlRes.rows.map((r) => [r.target, Number(r.count)]));
  return {
    announcement: map.announcement ? JSON.parse(map.announcement) : defaultAnn,
    versions: map.versions ? JSON.parse(map.versions) : defaultVers,
    downloads,
  };
}

export async function handleApiRequest(req, { ip = "0.0.0.0", db, env }) {
  const url = new URL(req.url);
  const path = url.pathname;
  const method = req.method.toUpperCase();
  const pool = db.pool;
  const secret = env("CINEVA_CLOUD_SECRET").trim();

  try {
    if (path === "/api/v1/health" && method === "GET") {
      return jsonResp({ ok: true, service: "cineva-cloud" });
    }
    if ((path === "/api/v1/app-config" || path === "/api/v1/downloads") && method === "GET") {
      return jsonResp(await getPublicConfig(pool));
    }

    if (!secret) {
      return jsonResp({ error: "Sunucu gizli anahtarı yapılandırılmamış." }, 500);
    }
    await ensureBootstrapAdmin(pool, env);

    const requireUser = async () => {
      const auth = req.headers.get("authorization") || "";
      if (!auth.startsWith("Bearer ")) throw new HttpError(401, "Oturum açmanız gerekiyor.");
      const claims = verifyTokenClaims(secret, auth.slice(7));
      if (!claims?.sub) throw new HttpError(401, "Oturum açmanız gerekiyor.");
      const user = await getUserById(pool, claims.sub, false);
      if (!user) throw new HttpError(401, "Oturum açmanız gerekiyor.");
      if (user.status !== "active") throw new HttpError(403, "Hesabınız askıya alınmış.");
      return user;
    };

    const requireAdmin = async () => {
      const user = await requireUser();
      if (user.role !== "admin") throw new HttpError(403, "Bu işlem için yönetici yetkisi gerekli.");
      return user;
    };

    if (path === "/api/v1/downloads/track" && method === "POST") {
      const body = await readJsonBody(req);
      const clean = String(body.target || "").trim().toLowerCase();
      if (!["windows-installer", "windows-portable", "android-apk", "macos"].includes(clean)) {
        throw new HttpError(400, "Geçersiz indirme hedefi.");
      }
      const now = isoNow();
      const res = await pool.query(
        `INSERT INTO download_stats (target, count, updated_at) VALUES ($1, 1, $2)
         ON CONFLICT (target) DO UPDATE SET count = download_stats.count + 1, updated_at = EXCLUDED.updated_at
         RETURNING count`,
        [clean, now],
      );
      return jsonResp({ target: clean, count: Number(res.rows[0].count) });
    }

    if (path === "/api/v1/auth/register" && method === "POST") {
      if (!(await checkRateLimit(pool, "reg:" + ip, 10))) {
        throw new HttpError(429, "Çok fazla kayıt denemesi. Lütfen bekleyin.");
      }
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      if (!EMAIL_RE.test(cleanEmail)) throw new HttpError(400, "Geçerli bir e-posta adresi girin.");
      const name = (String(body.displayName || "").trim() || cleanEmail.split("@", 1)[0]).slice(0, 80);
      const pwHash = hashPassword(body.password || "");
      const uid = "usr_" + crypto.randomBytes(8).toString("hex");
      const now = isoNow();
      try {
        const res = await pool.query(
          `INSERT INTO users (id, email, display_name, password_hash, role, plan, status, max_devices, expires_at, admin_note, created_at, last_seen_at)
           VALUES ($1,$2,$3,$4,'user','free','active',2,'','',$5,$6) RETURNING *`,
          [uid, cleanEmail, name, pwHash, now, now],
        );
        const user = publicUser(res.rows[0]);
        return jsonResp({ token: issueToken(secret, uid, "user"), user }, 201);
      } catch (err) {
        if (err?.code === "23505" || String(err?.message || "").includes("unique")) {
          throw new HttpError(400, "Bu e-posta adresi zaten kayıtlı.");
        }
        throw err;
      }
    }

    if (path === "/api/v1/auth/login" && method === "POST") {
      const bucket = "login:" + ip;
      if (!(await checkRateLimit(pool, bucket, 12))) {
        throw new HttpError(429, "Çok fazla hatalı giriş denemesi. 5 dakika bekleyin.");
      }
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      const res = await pool.query("SELECT * FROM users WHERE email = $1", [cleanEmail]);
      const row = res.rows[0];
      if (!row || !verifyPassword(body.password || "", row.password_hash)) {
        throw new HttpError(403, "E-posta veya parola hatalı.");
      }
      if (row.status !== "active") {
        throw new HttpError(403, "Hesabınız askıya alınmış. Destek ile iletişime geçin.");
      }
      await clearRateLimit(pool, bucket);
      const now = isoNow();
      await pool.query("UPDATE users SET last_seen_at = $1 WHERE id = $2", [now, row.id]);
      const user = await getUserById(pool, row.id, true);
      return jsonResp({ token: issueToken(secret, row.id, row.role), user });
    }

    if (path === "/api/v1/auth/reset-password" && method === "POST") {
      const body = await readJsonBody(req);
      const rawToken = String(body.token || "").trim();
      const tokenHash = crypto.createHash("sha256").update(rawToken, "utf8").digest("hex");
      const pwHash = hashPassword(body.newPassword || "");
      const res = await pool.query("SELECT * FROM password_resets WHERE token_hash = $1 AND used = 0", [tokenHash]);
      const row = res.rows[0];
      if (!row) throw new HttpError(400, "Sıfırlama bağlantısı geçersiz veya kullanılmış.");
      if (Date.parse(row.expires_at) < Date.now()) throw new HttpError(400, "Sıfırlama bağlantısının süresi dolmuş.");
      await pool.query("UPDATE users SET password_hash = $1 WHERE id = $2", [pwHash, row.user_id]);
      await pool.query("UPDATE password_resets SET used = 1 WHERE token_hash = $1", [tokenHash]);
      return jsonResp({ ok: true });
    }

    if (path === "/api/v1/me" && method === "GET") {
      const user = await requireUser();
      return jsonResp({ user: await getUserById(pool, user.id, true) });
    }

    if (path === "/api/v1/devices/register" && method === "POST") {
      const user = await requireUser();
      const body = await readJsonBody(req);
      const did = String(body.deviceId || "").trim().slice(0, 80);
      if (!did) throw new HttpError(400, "Cihaz kimliği gerekli.");
      const dname = (String(body.deviceName || "Cihaz").trim() || "Cihaz").slice(0, 80);
      const plat = (String(body.platform || "web").trim().toLowerCase() || "web").slice(0, 24);
      const now = isoNow();
      const ex = await pool.query("SELECT device_id FROM devices WHERE user_id = $1 AND device_id = $2", [user.id, did]);
      if (!ex.rows.length) {
        const cntRes = await pool.query("SELECT COUNT(*)::int AS cnt FROM devices WHERE user_id = $1", [user.id]);
        if (Number(cntRes.rows[0].cnt) >= user.maxDevices) {
          throw new HttpError(400, `Maksimum cihaz sınırına (${user.maxDevices}) ulaşıldı. Plan yükseltin veya eski bir cihazı kaldırın.`);
        }
      }
      await pool.query(
        `INSERT INTO devices (user_id, device_id, device_name, platform, last_seen_at) VALUES ($1,$2,$3,$4,$5)
         ON CONFLICT (user_id, device_id) DO UPDATE SET device_name = EXCLUDED.device_name, platform = EXCLUDED.platform, last_seen_at = EXCLUDED.last_seen_at`,
        [user.id, did, dname, plat, now],
      );
      await pool.query("UPDATE users SET last_seen_at = $1 WHERE id = $2", [now, user.id]);
      const full = await getUserById(pool, user.id, true);
      return jsonResp({ devices: full.devices });
    }

    if (path === "/api/v1/licenses/redeem" && method === "POST") {
      const user = await requireUser();
      const body = await readJsonBody(req);
      const code = String(body.code || "").trim().toUpperCase();
      if (!code) throw new HttpError(400, "Lisans anahtarı boş olamaz.");

      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        const licRes = await client.query("SELECT * FROM licenses WHERE code = $1 FOR UPDATE", [code]);
        const lic = licRes.rows[0];
        if (!lic) throw new HttpError(400, "Lisans anahtarı bulunamadı.");
        if (Number(lic.uses_count) >= Number(lic.max_uses)) throw new HttpError(400, "Bu lisans anahtarının kullanım limiti dolmuş.");
        const dup = await client.query("SELECT 1 FROM license_redemptions WHERE code = $1 AND user_id = $2", [code, user.id]);
        if (dup.rows.length) throw new HttpError(400, "Bu lisans anahtarı bu hesapta zaten kullanıldı.");
        const now = new Date();
        const expires = lic.plan === "lifetime" || Number(lic.duration_days) <= 0
          ? ""
          : new Date(now.getTime() + Number(lic.duration_days) * 86400_000).toISOString();
        await client.query("UPDATE licenses SET uses_count = uses_count + 1 WHERE code = $1", [code]);
        await client.query("INSERT INTO license_redemptions (code, user_id, redeemed_at) VALUES ($1,$2,$3)", [code, user.id, now.toISOString()]);
        await client.query(
          "UPDATE users SET plan = $1, max_devices = $2, expires_at = $3, last_seen_at = $4 WHERE id = $5",
          [lic.plan, Math.max(user.maxDevices, Number(lic.max_devices)), expires, now.toISOString(), user.id],
        );
        await addAudit(client, user, "license.redeem", "license", code, { plan: lic.plan, expiresAt: expires });
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      } finally {
        client.release();
      }
      return jsonResp({ ok: true, user: await getUserById(pool, user.id, false) });
    }

    // ---------------- Admin Routes ----------------
    if (path.startsWith("/api/v1/admin/")) {
      const admin = await requireAdmin();

      if (path === "/api/v1/admin/overview" && method === "GET") {
        const [uTot, uPro, uSusp, devs, lics, dls] = await Promise.all([
          pool.query("SELECT COUNT(*)::int AS c FROM users"),
          pool.query("SELECT COUNT(*)::int AS c FROM users WHERE plan IN ('pro','family','lifetime') AND role = 'user'"),
          pool.query("SELECT COUNT(*)::int AS c FROM users WHERE status = 'suspended'"),
          pool.query("SELECT COUNT(*)::int AS c FROM devices"),
          pool.query("SELECT COUNT(*)::int AS c, COALESCE(SUM(uses_count),0)::int AS r FROM licenses"),
          pool.query("SELECT target, count FROM download_stats"),
        ]);
        return jsonResp({
          totalUsers: uTot.rows[0].c,
          paidUsers: uPro.rows[0].c,
          suspendedUsers: uSusp.rows[0].c,
          activeDevices: devs.rows[0].c,
          licensesCreated: lics.rows[0].c,
          licensesRedeemed: lics.rows[0].r,
          downloads: Object.fromEntries(dls.rows.map((r) => [r.target, Number(r.count)])),
        });
      }

      if (path === "/api/v1/admin/users" && method === "GET") {
        const q = (url.searchParams.get("q") || "").trim().toLowerCase();
        const plan = (url.searchParams.get("plan") || "").trim().toLowerCase();
        const status = (url.searchParams.get("status") || "").trim().toLowerCase();
        const where = ["1=1"];
        const args = [];
        if (q) {
          args.push(`%${q}%`, `%${q}%`, q);
          where.push(`(LOWER(email) LIKE $${args.length - 2} OR LOWER(display_name) LIKE $${args.length - 1} OR id = $${args.length})`);
        }
        if (PLANS.has(plan)) {
          args.push(plan);
          where.push(`plan = $${args.length}`);
        }
        if (STATUSES.has(status)) {
          args.push(status);
          where.push(`status = $${args.length}`);
        }
        const res = await pool.query(
          `SELECT u.*, COALESCE(dc.cnt, 0)::int AS device_count
           FROM users u
           LEFT JOIN (SELECT user_id, COUNT(*)::int AS cnt FROM devices GROUP BY user_id) dc ON dc.user_id = u.id
           WHERE ${where.join(" AND ")}
           ORDER BY CASE WHEN u.role = 'admin' THEN 0 ELSE 1 END, u.created_at DESC
           LIMIT 200`,
          args,
        );
        return jsonResp({
          users: res.rows.map((r) => ({ ...publicUser(r), deviceCount: Number(r.device_count) })),
        });
      }

      if (path.startsWith("/api/v1/admin/users/") && method === "GET") {
        const uid = decodeURIComponent(path.slice("/api/v1/admin/users/".length));
        const found = await getUserById(pool, uid, true);
        if (!found) return jsonResp({ error: "Kullanıcı bulunamadı." }, 404);
        return jsonResp({ user: found });
      }

      if (path.startsWith("/api/v1/admin/users/") && path.endsWith("/reset-password-token") && method === "POST") {
        const uid = decodeURIComponent(path.slice("/api/v1/admin/users/".length, -"/reset-password-token".length));
        const uRes = await pool.query("SELECT id, email FROM users WHERE id = $1", [uid]);
        if (!uRes.rows.length) throw new HttpError(400, "Kullanıcı bulunamadı.");
        const rawToken = crypto.randomBytes(24).toString("base64url");
        const tokenHash = crypto.createHash("sha256").update(rawToken, "utf8").digest("hex");
        const expires = new Date(Date.now() + 3600_000).toISOString();
        await pool.query("INSERT INTO password_resets (token_hash, user_id, expires_at, used) VALUES ($1,$2,$3,0)", [tokenHash, uid, expires]);
        await addAudit(pool, admin, "user.reset_token", "user", uid, { email: uRes.rows[0].email });
        return jsonResp({ resetToken: rawToken });
      }

      if (path.startsWith("/api/v1/admin/users/") && path.includes("/devices/") && method === "DELETE") {
        const tail = path.slice("/api/v1/admin/users/".length);
        const [uidRaw, didRaw] = tail.split("/devices/", 2);
        const uid = decodeURIComponent(uidRaw);
        const did = decodeURIComponent(didRaw);
        await pool.query("DELETE FROM devices WHERE user_id = $1 AND device_id = $2", [uid, did]);
        await addAudit(pool, admin, "device.remove", "device", `${uid}:${did}`, {});
        return jsonResp({ ok: true });
      }

      if (path.startsWith("/api/v1/admin/users/") && method === "PATCH") {
        const uid = decodeURIComponent(path.slice("/api/v1/admin/users/".length));
        const body = await readJsonBody(req);
        const oldRes = await pool.query("SELECT * FROM users WHERE id = $1", [uid]);
        const old = oldRes.rows[0];
        if (!old) throw new HttpError(400, "Kullanıcı bulunamadı.");
        if (old.id === admin.id && body.status === "suspended") {
          throw new HttpError(400, "Kendi yönetici hesabınızı askıya alamazsınız.");
        }
        const plan = String(body.plan ?? old.plan).trim().toLowerCase();
        if (!PLANS.has(plan)) throw new HttpError(400, "Geçersiz plan.");
        const status = String(body.status ?? old.status).trim().toLowerCase();
        if (!STATUSES.has(status)) throw new HttpError(400, "Geçersiz hesap durumu.");
        const role = String(body.role ?? old.role).trim().toLowerCase();
        if (!ROLES.has(role)) throw new HttpError(400, "Geçersiz rol.");
        if (old.id === admin.id && role !== "admin") {
          throw new HttpError(400, "Kendi yönetici rolünüzü kaldıramazsınız.");
        }
        const maxDevices = Math.max(1, Math.min(50, Number.parseInt(body.maxDevices ?? old.max_devices, 10) || old.max_devices));
        const displayName = (String(body.displayName ?? old.display_name).trim() || old.display_name).slice(0, 80);
        const adminNote = String(body.adminNote ?? old.admin_note ?? "").slice(0, 500);
        let expiresAt = old.expires_at || "";
        if ("expiresAt" in body) {
          expiresAt = String(body.expiresAt || "").trim().slice(0, 64);
        } else if (Number(body.addDays) > 0) {
          const days = Number.parseInt(body.addDays, 10);
          let base = old.expires_at ? Date.parse(old.expires_at) : Date.now();
          if (Number.isNaN(base) || base < Date.now()) base = Date.now();
          expiresAt = new Date(base + days * 86400_000).toISOString();
        }
        if (plan === "lifetime") expiresAt = "";
        await pool.query(
          "UPDATE users SET plan = $1, status = $2, role = $3, max_devices = $4, display_name = $5, admin_note = $6, expires_at = $7 WHERE id = $8",
          [plan, status, role, maxDevices, displayName, adminNote, expiresAt, uid],
        );
        await addAudit(pool, admin, "user.update", "user", uid, {
          old: { plan: old.plan, status: old.status, role: old.role, maxDevices: old.max_devices },
          new: { plan, status, role, maxDevices, expiresAt },
        });
        return jsonResp({ user: await getUserById(pool, uid, true) });
      }

      if (path === "/api/v1/admin/licenses" && method === "GET") {
        const res = await pool.query("SELECT * FROM licenses ORDER BY created_at DESC LIMIT 200");
        return jsonResp({
          licenses: res.rows.map((r) => ({
            code: r.code,
            plan: r.plan,
            durationDays: Number(r.duration_days),
            maxDevices: Number(r.max_devices),
            maxUses: Number(r.max_uses),
            usesCount: Number(r.uses_count),
            note: r.note,
            createdBy: r.created_by,
            createdAt: r.created_at,
          })),
        });
      }

      if (path === "/api/v1/admin/licenses" && method === "POST") {
        const body = await readJsonBody(req);
        const cleanPlan = String(body.plan || "pro").trim().toLowerCase();
        if (!PLANS.has(cleanPlan) || cleanPlan === "free") {
          throw new HttpError(400, "Lisans planı pro, family veya lifetime olmalıdır.");
        }
        const days = cleanPlan === "lifetime" ? 0 : Math.max(1, Math.min(3650, Number.parseInt(body.durationDays ?? 365, 10) || 365));
        const devs = Math.max(1, Math.min(50, Number.parseInt(body.maxDevices ?? 5, 10) || 5));
        const uses = Math.max(1, Math.min(10000, Number.parseInt(body.maxUses ?? 1, 10) || 1));
        const raw = crypto.randomBytes(6).toString("hex").toUpperCase();
        const code = `CINEVA-${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
        const note = String(body.note || "").slice(0, 200);
        const now = isoNow();
        await pool.query(
          "INSERT INTO licenses (code, plan, duration_days, max_devices, max_uses, uses_count, note, created_by, created_at) VALUES ($1,$2,$3,$4,$5,0,$6,$7,$8)",
          [code, cleanPlan, days, devs, uses, note, admin.email, now],
        );
        await addAudit(pool, admin, "license.create", "license", code, { plan: cleanPlan, durationDays: days, maxUses: uses });
        return jsonResp({ license: { code, plan: cleanPlan, durationDays: days, maxDevices: devs, maxUses: uses, usesCount: 0, note, createdAt: now } }, 201);
      }

      if (path.startsWith("/api/v1/admin/licenses/") && method === "DELETE") {
        const code = decodeURIComponent(path.slice("/api/v1/admin/licenses/".length)).trim().toUpperCase();
        await pool.query("DELETE FROM licenses WHERE code = $1", [code]);
        await addAudit(pool, admin, "license.delete", "license", code, {});
        return jsonResp({ ok: true });
      }

      if (path === "/api/v1/admin/config" && method === "GET") {
        return jsonResp(await getPublicConfig(pool));
      }

      if (path === "/api/v1/admin/config" && (method === "PUT" || method === "PATCH")) {
        const body = await readJsonBody(req);
        const current = await getPublicConfig(pool);
        let ann = current.announcement;
        const vers = { ...current.versions };
        if (body.announcement && typeof body.announcement === "object") {
          const a = body.announcement;
          ann = {
            enabled: Boolean(a.enabled ?? ann.enabled),
            title: String(a.title ?? ann.title).slice(0, 120),
            message: String(a.message ?? ann.message).slice(0, 500),
            severity: ["info", "warning", "critical"].includes(a.severity) ? a.severity : "info",
          };
        }
        if (body.versions && typeof body.versions === "object") {
          const v = body.versions;
          for (const k of ["windowsLatest", "windowsMin", "androidLatest", "androidMin", "windowsInstallerUrl", "windowsPortableUrl", "androidApkUrl"]) {
            if (typeof v[k] === "string") {
              const val = v[k].trim().slice(0, 500);
              if (k.includes("Url") && val && !/^(https?:\/\/|\/)/.test(val)) {
                throw new HttpError(400, "İndirme bağlantısı geçerli bir adres olmalıdır.");
              }
              vers[k] = val;
            }
          }
        }
        await pool.query(
          "INSERT INTO app_config (key, value) VALUES ('announcement', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
          [JSON.stringify(ann)],
        );
        await pool.query(
          "INSERT INTO app_config (key, value) VALUES ('versions', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
          [JSON.stringify(vers)],
        );
        await addAudit(pool, admin, "config.update", "app_config", "global", { announcementEnabled: ann.enabled });
        return jsonResp(await getPublicConfig(pool));
      }

      if (path === "/api/v1/admin/audit" && method === "GET") {
        const res = await pool.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 80");
        return jsonResp({
          logs: res.rows.map((r) => ({
            id: r.id,
            actorEmail: r.actor_email,
            action: r.action,
            targetType: r.target_type,
            targetId: r.target_id,
            details: JSON.parse(r.details),
            createdAt: r.created_at,
          })),
        });
      }

      return jsonResp({ error: "Bilinmeyen yönetim uç noktası." }, 404);
    }

    return jsonResp({ error: "Uç nokta bulunamadı." }, 404);
  } catch (err) {
    if (err instanceof HttpError) return jsonResp({ error: err.message }, err.status);
    console.error("Cineva cloud function error:", err);
    return jsonResp({ error: "Sunucu hatası oluştu." }, 500);
  }
}
