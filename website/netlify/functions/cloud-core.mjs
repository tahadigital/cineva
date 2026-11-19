import crypto from "node:crypto";
import net from "node:net";
import tls from "node:tls";

export const PLANS = new Set(["normal", "pro"]);
export const LEGACY_PLAN_MAP = {
  free: "normal",
  normal: "normal",
  pro: "pro",
  family: "pro",
  lifetime: "pro",
};
export const STATUSES = new Set(["active", "suspended"]);
export const ROLES = new Set(["user", "admin"]);
export const DOWNLOAD_TARGETS = new Set([
  "windows-installer",
  "windows-portable",
  "android-apk",
  "macos",
  "ios",
]);
export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$/;
export const TRIAL_DURATION_MS = 72 * 3600 * 1000;
export const VERIFY_TTL_MS = 24 * 3600 * 1000;
export const RESET_TTL_MS = 30 * 60 * 1000;
export const MAX_CODE_ATTEMPTS = 5;

export const SAFE_SYNC_KEYS = [
  "version",
  "exportedAt",
  "items",
  "favorites",
  "progress",
  "playlists",
  "playlistItems",
  "trackPreferences",
  "nativeTrackPreferences",
];

export const DEFAULT_VERSIONS = {
  latestVersion: "2.1.0",
  windowsLatest: "2.1.0",
  windowsMin: "2.0.0",
  androidLatest: "2.1.0",
  androidMin: "2.0.0",
  macosLatest: "2.1.0",
  macosMin: "2.0.0",
  iosLatest: "2.1.0",
  iosMin: "2.0.0",
  windowsInstallerUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Vrelio-Setup.exe",
  windowsPortableUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Vrelio.exe",
  androidApkUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Vrelio-Android.apk",
  macosUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Vrelio-macOS.dmg",
  iosUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Vrelio-iOS.ipa",
  releaseNotes: "Vrelio 2.1.0: 4 platform desteği, e-posta doğrulama ve 3 günlük Pro deneme.",
};

export const PLAN_CATALOG = {
  normal: {
    maxDevices: 1,
    features: ["demo_m3u_local", "single_profile", "single_device"],
  },
  pro: {
    maxDevices: 5,
    trialDays: 3,
    features: [
      "cloud_sync",
      "multi_view",
      "unlimited_profiles_pin",
      "epg_match",
      "advanced_tracks",
      "five_devices",
    ],
  },
};

class HttpError extends Error {
  constructor(status, message, code = "", extra = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra || {};
  }
}

export function isoNow() {
  return new Date().toISOString();
}

export function normalizePlan(plan) {
  const clean = String(plan || "").trim().toLowerCase();
  return Object.hasOwn(LEGACY_PLAN_MAP, clean) ? LEGACY_PLAN_MAP[clean] : "normal";
}

function envAny(env, ...names) {
  for (const name of names) {
    const val = String(env(name) || "").trim();
    if (val) return val;
  }
  return "";
}

function stripHeaderCrlf(value) {
  return String(value ?? "").replace(/[\r\n\x00]+/g, " ").trim();
}

function hashCode(purpose, userId, code) {
  const clean = String(code ?? "").trim();
  return crypto.createHash("sha256").update(`${purpose}:${userId}:${clean}`, "utf8").digest("hex");
}

function hashToken(purpose, rawToken) {
  const clean = String(rawToken ?? "").trim();
  return crypto.createHash("sha256").update(`${purpose}_token:${clean}`, "utf8").digest("hex");
}

function legacyHashToken(rawToken) {
  const clean = String(rawToken ?? "").trim();
  return crypto.createHash("sha256").update(clean, "utf8").digest("hex");
}

function timingSafeHexEqual(a, b) {
  try {
    if (!a || !b || a.length !== b.length) return false;
    return crypto.timingSafeEqual(Buffer.from(a, "hex"), Buffer.from(b, "hex"));
  } catch {
    return false;
  }
}

export function sanitizeSyncState(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new HttpError(400, "Eşitleme verisi geçerli bir JSON nesnesi olmalıdır.");
  }
  const source =
    raw.state && typeof raw.state === "object" && !Array.isArray(raw.state)
      ? raw.state
      : raw;
  return {
    version: Number(source.version) || 1,
    exportedAt: String(source.exportedAt || isoNow()).slice(0, 64),
    items: Array.isArray(source.items) ? source.items.slice(0, 2000) : [],
    favorites: Array.isArray(source.favorites) ? source.favorites.slice(0, 2000) : [],
    progress: Array.isArray(source.progress) ? source.progress.slice(0, 2000) : [],
    playlists: Array.isArray(source.playlists) ? source.playlists.slice(0, 200) : [],
    playlistItems: Array.isArray(source.playlistItems) ? source.playlistItems.slice(0, 5000) : [],
    trackPreferences: Array.isArray(source.trackPreferences) ? source.trackPreferences.slice(0, 2000) : [],
    nativeTrackPreferences: Array.isArray(source.nativeTrackPreferences)
      ? source.nativeTrackPreferences.slice(0, 2000)
      : [],
  };
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

export function issueToken(secret, userId, role, tokenVersion = 1, ttlSeconds = 7 * 24 * 3600) {
  const claims = {
    sub: userId,
    role,
    tv: Number(tokenVersion || 1),
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
  const norm = normalizePlan(plan);
  if (norm !== "pro") return "normal";
  if (!expiresAt) return "pro";
  const ts = Date.parse(expiresAt);
  if (!Number.isNaN(ts) && ts < Date.now()) return "normal";
  return "pro";
}

export function publicUser(row, devices = null) {
  const expiresAt = row.expires_at || "";
  const rawPlan = normalizePlan(row.plan);
  const effPlan = effectivePlan(rawPlan, expiresAt);
  const isPro = effPlan === "pro";
  const emailVerified = Boolean(row.email_verified);
  const trialUsed = Boolean(row.trial_used);
  const trialStartedAt = row.trial_started_at || "";
  const trialEndsAt = row.trial_ends_at || "";
  const trialEndsMs = trialEndsAt ? Date.parse(trialEndsAt) : Number.NaN;
  const trialActive = Boolean(
    isPro &&
      trialEndsAt &&
      expiresAt === trialEndsAt &&
      !Number.isNaN(trialEndsMs) &&
      trialEndsMs > Date.now(),
  );
  const maxDevices =
    row.role === "admin"
      ? Math.max(1, Number(row.max_devices || 10))
      : !isPro
        ? 1
        : Math.max(1, Number(row.max_devices || 5));

  const out = {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    role: row.role,
    emailVerified,
    verifiedAt: row.verified_at || "",
    plan: rawPlan,
    effectivePlan: effPlan,
    isPro,
    trialActive,
    trialUsed,
    trialStartedAt,
    trialEndsAt,
    status: row.status,
    maxDevices,
    expiresAt,
    adminNote: row.admin_note || "",
    createdAt: row.created_at,
    lastSeenAt: row.last_seen_at,
    features: {
      cloudSync: isPro,
      multiView: isPro,
      unlimitedProfiles: isPro,
      epgMatch: isPro,
      advancedTracks: isPro,
      maxDevices,
    },
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

async function readJsonBody(req, maxBytes = 1536 * 1024) {
  const text = await req.text();
  if (Buffer.byteLength(text, "utf8") > maxBytes) throw new HttpError(400, "İstek boyutu çok büyük.");
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
  const email = envAny(env, "VRELIO_ADMIN_EMAIL", "CINEVA_ADMIN_EMAIL").toLowerCase();
  const password = envAny(env, "VRELIO_ADMIN_PASSWORD", "CINEVA_ADMIN_PASSWORD");
  if (!email || !password || !EMAIL_RE.test(email)) return;
  const { rows } = await pool.query("SELECT id FROM users WHERE role = 'admin' LIMIT 1");
  if (rows.length > 0) return;
  const now = isoNow();
  const uid = "usr_admin_" + crypto.randomBytes(6).toString("hex");
  const pwHash = hashPassword(password);
  await pool.query(
    `INSERT INTO users (id, email, display_name, password_hash, role, plan, status, max_devices, expires_at, admin_note, created_at, last_seen_at, email_verified, verified_at, trial_used, trial_started_at, trial_ends_at, token_version)
     VALUES ($1,$2,$3,$4,'admin','pro','active',10,'','Sistem yöneticisi',$5,$6,TRUE,$7,TRUE,'','',1)
     ON CONFLICT (email) DO NOTHING`,
    [uid, email, "Yönetici", pwHash, now, now, now],
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

function extractEmailAddress(headerVal) {
  const m = String(headerVal || "").match(/<([^>\s]+)>/);
  return (m ? m[1] : String(headerVal || "")).replace(/[\r\n\x00<>]/g, "").trim();
}

async function sendRawSmtp({ host, port, user, pass, from, to, subject, bodyText, tlsMode }) {
  const fromAddr = extractEmailAddress(from);
  const toAddr = extractEmailAddress(to);
  const useImplicitTls = tlsMode === "ssl" || (!tlsMode && port === 465);
  const useStartTls = !useImplicitTls && tlsMode !== "none";

  const createLineReader = (sock) => {
    let buffer = "";
    const waiters = [];
    const onData = (chunk) => {
      buffer += chunk.toString("utf8");
      while (waiters.length) {
        const lines = buffer.split("\r\n");
        let endIdx = -1;
        for (let i = 0; i < lines.length - 1; i++) {
          if (/^\d{3} /.test(lines[i])) {
            endIdx = i;
            break;
          }
        }
        if (endIdx === -1) break;
        const msgLines = lines.slice(0, endIdx + 1);
        buffer = lines.slice(endIdx + 1).join("\r\n");
        const w = waiters.shift();
        w.resolve(msgLines.join("\r\n"));
      }
    };
    const onError = (err) => {
      while (waiters.length) waiters.shift().reject(err);
    };
    const onClose = () => {
      while (waiters.length) waiters.shift().reject(new Error("SMTP connection closed unexpectedly"));
    };
    sock.on("data", onData);
    sock.on("error", onError);
    sock.on("close", onClose);
    const readResp = () =>
      new Promise((resolve, reject) => {
        waiters.push({ resolve, reject });
        const lines = buffer.split("\r\n");
        for (let i = 0; i < lines.length - 1; i++) {
          if (/^\d{3} /.test(lines[i])) {
            const msgLines = lines.slice(0, i + 1);
            buffer = lines.slice(i + 1).join("\r\n");
            waiters.shift();
            resolve(msgLines.join("\r\n"));
            return;
          }
        }
      });
    readResp.detach = () => {
      sock.off("data", onData);
      sock.off("error", onError);
      sock.off("close", onClose);
    };
    return readResp;
  };

  let sock = useImplicitTls
    ? tls.connect({ host, port, servername: host })
    : net.connect({ host, port });
  sock.setTimeout(15_000, () => sock.destroy(new Error("SMTP timeout")));

  await new Promise((resolve, reject) => {
    sock.once("error", reject);
    sock.once(useImplicitTls ? "secureConnect" : "connect", resolve);
  });

  let readResp = createLineReader(sock);
  const expect = async (cmd, allowedCodes) => {
    if (cmd !== null) sock.write(cmd + "\r\n");
    const resp = await readResp();
    const code = Number(resp.slice(0, 3));
    if (!allowedCodes.includes(code)) {
      throw new Error(`SMTP error (${code}): ${resp}`);
    }
    return resp;
  };

  try {
    await expect(null, [220]);
    await expect("EHLO vrelio.app", [250]);
    if (useStartTls) {
      await expect("STARTTLS", [220]);
      readResp.detach();
      sock = tls.connect({ socket: sock, servername: host });
      sock.setTimeout(15_000, () => sock.destroy(new Error("SMTP TLS timeout")));
      await new Promise((resolve, reject) => {
        sock.once("error", reject);
        sock.once("secureConnect", resolve);
      });
      readResp = createLineReader(sock);
      await expect("EHLO vrelio.app", [250]);
    }
    if (user && pass) {
      const authToken = Buffer.from(`\0${user}\0${pass}`, "utf8").toString("base64");
      await expect(`AUTH PLAIN ${authToken}`, [235]);
    }
    await expect(`MAIL FROM:<${fromAddr}>`, [250]);
    await expect(`RCPT TO:<${toAddr}>`, [250, 251]);
    await expect("DATA", [354]);
    const safeBody = String(bodyText || "").replace(/\r?\n/g, "\r\n").replace(/^\./gm, "..");
    const mime =
      `From: ${from}\r\n` +
      `To: ${toAddr}\r\n` +
      `Subject: ${subject}\r\n` +
      `MIME-Version: 1.0\r\n` +
      `Content-Type: text/plain; charset=utf-8\r\n\r\n` +
      `${safeBody}\r\n.`;
    await expect(mime, [250]);
    await expect("QUIT", [221, 250]).catch(() => {});
  } finally {
    sock.destroy();
  }
}

function resolveEmailTransport(env, mailer) {
  if (typeof mailer === "function") return "custom";
  const mode = (envAny(env, "VRELIO_EMAIL_MODE", "CINEVA_EMAIL_MODE", "EMAIL_MODE") || "auto").toLowerCase();
  if (mode === "outbox") return "outbox";
  const resendKey = envAny(env, "VRELIO_RESEND_API_KEY", "RESEND_API_KEY");
  const webhookUrl = envAny(env, "VRELIO_EMAIL_WEBHOOK_URL", "EMAIL_WEBHOOK_URL");
  const smtpHost = envAny(env, "VRELIO_SMTP_HOST", "CINEVA_SMTP_HOST", "SMTP_HOST");

  if (mode === "resend") return "resend";
  if (mode === "webhook") return "webhook";
  if (mode === "smtp") return "smtp";
  if (resendKey) return "resend";
  if (webhookUrl) return "webhook";
  if (smtpHost) return "smtp";
  return "outbox";
}

async function deliverEmail(pool, env, mailer, { kind, recipient, displayName, code, token }) {
  const cleanRecipient = stripHeaderCrlf(recipient).toLowerCase();
  const cleanName = stripHeaderCrlf(displayName) || "Kullanıcı";
  const subject =
    kind === "verify_email"
      ? stripHeaderCrlf("Vrelio — E-posta Adresinizi Doğrulayın")
      : stripHeaderCrlf("Vrelio — Parola Sıfırlama Kodu");
  const bodyText =
    kind === "verify_email"
      ? `Merhaba ${cleanName},\n\nVrelio hesabınızı doğrulamak için 6 haneli kodunuz: ${code}\nDoğrulama belirteci: ${token}\n\nBu kod 24 saat geçerlidir. Doğrulama tamamlandığında 3 günlük ücretsiz Pro denemeniz otomatik başlar.\n`
      : `Merhaba ${cleanName},\n\nVrelio hesabınız için parola sıfırlama kodunuz: ${code}\nSıfırlama belirteci: ${token}\n\nBu kod 30 dakika geçerlidir. Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz.\n`;

  const mode = resolveEmailTransport(env, mailer);
  const fromAddr = stripHeaderCrlf(
    envAny(env, "VRELIO_SMTP_FROM", "CINEVA_SMTP_FROM", "SMTP_FROM") || "Vrelio <noreply@vrelio.app>",
  );
  const msgId = "mail_" + crypto.randomBytes(8).toString("hex");
  const now = isoNow();

  const recordOutbox = async (deliveryMode, status, metadata = {}, errorMessage = "") => {
    await pool.query(
      `INSERT INTO email_outbox (id, recipient, subject, body_text, body_html, kind, delivery_mode, status, metadata_json, error_message, created_at)
       VALUES ($1,$2,$3,$4,'',$5,$6,$7,$8,$9,$10)`,
      [msgId, cleanRecipient, subject, bodyText, kind, deliveryMode, status, JSON.stringify(metadata), errorMessage, now],
    );
  };

  if (mode === "custom") {
    await mailer({ kind, recipient: cleanRecipient, displayName: cleanName, subject, bodyText, code, token });
    await recordOutbox("custom", "sent", {});
    return "custom";
  }

  if (mode === "outbox") {
    await recordOutbox("outbox", "stored", { code, token });
    return "outbox";
  }

  try {
    if (mode === "resend") {
      const apiKey = envAny(env, "VRELIO_RESEND_API_KEY", "RESEND_API_KEY");
      if (!apiKey) throw new Error("RESEND_API_KEY missing");
      const resp = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: fromAddr,
          to: [cleanRecipient],
          subject,
          text: bodyText,
        }),
      });
      if (!resp.ok) {
        const errBody = await resp.text().catch(() => "");
        throw new Error(`Resend HTTP ${resp.status}: ${errBody.slice(0, 160)}`);
      }
      await recordOutbox("resend", "sent", {});
      return "resend";
    }

    if (mode === "webhook") {
      const webhookUrl = envAny(env, "VRELIO_EMAIL_WEBHOOK_URL", "EMAIL_WEBHOOK_URL");
      if (!webhookUrl) throw new Error("EMAIL_WEBHOOK_URL missing");
      const webhookSecret = envAny(env, "VRELIO_EMAIL_WEBHOOK_SECRET", "EMAIL_WEBHOOK_SECRET");
      const resp = await fetch(webhookUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(webhookSecret ? { Authorization: `Bearer ${webhookSecret}` } : {}),
        },
        body: JSON.stringify({ from: fromAddr, to: cleanRecipient, kind, subject, text: bodyText, code, token }),
      });
      if (!resp.ok) throw new Error(`Webhook HTTP ${resp.status}`);
      await recordOutbox("webhook", "sent", {});
      return "webhook";
    }

    if (mode === "smtp") {
      const host = envAny(env, "VRELIO_SMTP_HOST", "CINEVA_SMTP_HOST", "SMTP_HOST");
      if (!host) throw new Error("SMTP_HOST missing");
      const port = Number.parseInt(envAny(env, "VRELIO_SMTP_PORT", "CINEVA_SMTP_PORT", "SMTP_PORT") || "587", 10) || 587;
      const user = envAny(env, "VRELIO_SMTP_USER", "CINEVA_SMTP_USER", "SMTP_USER");
      const pass = envAny(env, "VRELIO_SMTP_PASS", "CINEVA_SMTP_PASS", "SMTP_PASS");
      const tlsMode = (envAny(env, "VRELIO_SMTP_TLS", "SMTP_TLS") || (port === 465 ? "ssl" : "starttls")).toLowerCase();
      await sendRawSmtp({ host, port, user, pass, from: fromAddr, to: cleanRecipient, subject, bodyText, tlsMode });
      await recordOutbox("smtp", "sent", {});
      return "smtp";
    }
  } catch (err) {
    await recordOutbox(mode, "failed", {}, String(err?.message || err).slice(0, 300)).catch(() => {});
    throw new HttpError(502, "E-posta gönderilemedi. Lütfen daha sonra tekrar deneyin.", "EMAIL_DELIVERY_FAILED");
  }

  await recordOutbox("outbox", "stored", { code, token });
  return "outbox";
}

async function getPublicConfig(pool) {
  const defaultAnn = { enabled: false, title: "", message: "", severity: "info" };
  const cfgRes = await pool.query("SELECT key, value FROM app_config");
  const map = Object.fromEntries(cfgRes.rows.map((r) => [r.key, r.value]));
  const dlRes = await pool.query("SELECT target, count FROM download_stats");
  const downloads = Object.fromEntries(dlRes.rows.map((r) => [r.target, Number(r.count)]));
  const parsedVers = map.versions ? JSON.parse(map.versions) : {};
  return {
    announcement: map.announcement ? JSON.parse(map.announcement) : defaultAnn,
    versions: { ...DEFAULT_VERSIONS, ...parsedVers },
    downloads,
    plans: PLAN_CATALOG,
  };
}

export async function handleApiRequest(req, { ip = "0.0.0.0", db, env, mailer = null }) {
  const url = new URL(req.url);
  const path = url.pathname;
  const method = req.method.toUpperCase();
  const pool = db.pool;
  const secret = envAny(env, "VRELIO_CLOUD_SECRET", "CINEVA_CLOUD_SECRET");

  try {
    if (path === "/api/v1/health" && method === "GET") {
      return jsonResp({ ok: true, service: "vrelio-cloud" });
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
      const res = await pool.query("SELECT * FROM users WHERE id = $1", [claims.sub]);
      const row = res.rows[0];
      if (!row) throw new HttpError(401, "Oturum açmanız gerekiyor.");
      if (Number(claims.tv ?? claims.ver ?? 1) !== Number(row.token_version ?? 1)) {
        throw new HttpError(401, "Oturumunuz sonlandırıldı. Lütfen tekrar giriş yapın.");
      }
      if (row.status !== "active") {
        throw new HttpError(403, "Hesabınız askıya alınmış.", "ACCOUNT_SUSPENDED");
      }
      if (!row.email_verified) {
        throw new HttpError(403, "E-posta doğrulaması gerekli.", "EMAIL_NOT_VERIFIED", {
          verificationRequired: true,
          email: row.email,
        });
      }
      return publicUser(row);
    };

    const requireAdmin = async () => {
      const user = await requireUser();
      if (user.role !== "admin") throw new HttpError(403, "Bu işlem için yönetici yetkisi gerekli.");
      return user;
    };

    if (path === "/api/v1/downloads/track" && method === "POST") {
      const body = await readJsonBody(req);
      const clean = String(body.target || body.platform || "").trim().toLowerCase();
      if (!DOWNLOAD_TARGETS.has(clean)) {
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
      const name = (stripHeaderCrlf(body.displayName || "") || cleanEmail.split("@", 1)[0]).slice(0, 80);
      const pwHash = hashPassword(body.password || "");
      const nowMs = Date.now();
      const now = new Date(nowMs).toISOString();
      const expiresAt = new Date(nowMs + VERIFY_TTL_MS).toISOString();
      const code = String(crypto.randomInt(0, 1_000_000)).padStart(6, "0");
      const rawToken = crypto.randomBytes(24).toString("base64url");

      const client = await pool.connect();
      let userRow;
      try {
        await client.query("BEGIN");
        const existingRes = await client.query("SELECT * FROM users WHERE email = $1 FOR UPDATE", [cleanEmail]);
        const existing = existingRes.rows[0];
        let uid;
        if (existing) {
          if (existing.email_verified) {
            throw new HttpError(400, "Bu e-posta adresi zaten kayıtlı.", "EMAIL_ALREADY_EXISTS");
          }
          uid = existing.id;
          const upd = await client.query(
            "UPDATE users SET display_name = $1, password_hash = $2, last_seen_at = $3 WHERE id = $4 RETURNING *",
            [name, pwHash, now, uid],
          );
          userRow = upd.rows[0];
          await client.query("UPDATE email_verifications SET used_at = $1 WHERE user_id = $2 AND used_at = ''", [now, uid]);
        } else {
          uid = "usr_" + crypto.randomBytes(8).toString("hex");
          const ins = await client.query(
            `INSERT INTO users (id, email, display_name, password_hash, role, plan, status, max_devices, expires_at, admin_note, created_at, last_seen_at, email_verified, verified_at, trial_used, trial_started_at, trial_ends_at, token_version)
             VALUES ($1,$2,$3,$4,'user','normal','active',1,'','',$5,$6,FALSE,'',FALSE,'','',1) RETURNING *`,
            [uid, cleanEmail, name, pwHash, now, now],
          );
          userRow = ins.rows[0];
        }
        const verId = "ver_" + crypto.randomBytes(8).toString("hex");
        await client.query(
          `INSERT INTO email_verifications (id, user_id, email, code_hash, token_hash, expires_at, used_at, attempts, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,'',0,$7)`,
          [
            verId,
            uid,
            cleanEmail,
            hashCode("verify_email", uid, code),
            hashToken("verify_email", rawToken),
            expiresAt,
            now,
          ],
        );
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        if (err?.code === "23505" || String(err?.message || "").includes("unique")) {
          throw new HttpError(400, "Bu e-posta adresi zaten kayıtlı.", "EMAIL_ALREADY_EXISTS");
        }
        throw err;
      } finally {
        client.release();
      }

      const deliveryMode = await deliverEmail(pool, env, mailer, {
        kind: "verify_email",
        recipient: cleanEmail,
        displayName: userRow.display_name,
        code,
        token: rawToken,
      });

      return jsonResp(
        {
          ok: true,
          verificationRequired: true,
          emailVerified: false,
          deliveryMode,
          user: publicUser(userRow),
        },
        201,
      );
    }

    if (path === "/api/v1/auth/verify-email" && method === "POST") {
      if (!(await checkRateLimit(pool, "verify:" + ip, 15))) {
        throw new HttpError(429, "Çok fazla doğrulama denemesi. Lütfen bekleyin.");
      }
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      const cleanCode = String(body.code || "").trim();
      const cleanToken = String(body.token || "").trim();
      if (!cleanToken && (!EMAIL_RE.test(cleanEmail) || !cleanCode)) {
        throw new HttpError(400, "Doğrulama kodu veya belirteci gerekli.", "INVALID_VERIFICATION_INPUT");
      }

      const client = await pool.connect();
      let errToThrow = null;
      let trialActivated = false;
      let updatedUser = null;

      try {
        await client.query("BEGIN");
        let rec = null;
        let matched = false;
        if (cleanToken) {
          const thash = hashToken("verify_email", cleanToken);
          const q = await client.query(
            "SELECT * FROM email_verifications WHERE token_hash = $1 AND used_at = '' FOR UPDATE",
            [thash],
          );
          rec = q.rows[0] || null;
          matched = Boolean(rec && timingSafeHexEqual(rec.token_hash, thash));
        } else {
          const q = await client.query(
            "SELECT * FROM email_verifications WHERE email = $1 AND used_at = '' ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
            [cleanEmail],
          );
          rec = q.rows[0] || null;
          if (rec) {
            const chash = hashCode("verify_email", rec.user_id, cleanCode);
            matched = timingSafeHexEqual(rec.code_hash, chash);
          }
        }

        const nowMs = Date.now();
        const now = new Date(nowMs).toISOString();

        if (!rec) {
          errToThrow = new HttpError(400, "Doğrulama kodu geçersiz veya kullanılmış.", "INVALID_VERIFICATION_CODE");
        } else if (rec.expires_at && Date.parse(rec.expires_at) < nowMs) {
          await client.query("UPDATE email_verifications SET used_at = $1 WHERE id = $2", [now, rec.id]);
          errToThrow = new HttpError(400, "Doğrulama kodunun süresi dolmuş.", "VERIFICATION_EXPIRED");
        } else if (Number(rec.attempts) >= MAX_CODE_ATTEMPTS) {
          await client.query("UPDATE email_verifications SET used_at = $1 WHERE id = $2", [now, rec.id]);
          errToThrow = new HttpError(
            400,
            "Çok fazla hatalı deneme. Yeni doğrulama kodu isteyin.",
            "VERIFICATION_LOCKED",
          );
        } else if (!matched) {
          const nextAttempts = Number(rec.attempts) + 1;
          const burn = nextAttempts >= MAX_CODE_ATTEMPTS;
          await client.query(
            "UPDATE email_verifications SET attempts = $1, used_at = $2 WHERE id = $3",
            [nextAttempts, burn ? now : rec.used_at || "", rec.id],
          );
          errToThrow = new HttpError(
            400,
            burn ? "Çok fazla hatalı deneme. Yeni doğrulama kodu isteyin." : "Doğrulama kodu hatalı.",
            burn ? "VERIFICATION_LOCKED" : "INVALID_VERIFICATION_CODE",
          );
        } else {
          const consume = await client.query(
            "UPDATE email_verifications SET used_at = $1 WHERE id = $2 AND used_at = ''",
            [now, rec.id],
          );
          if (consume.rowCount === 0) {
            errToThrow = new HttpError(400, "Doğrulama kodu geçersiz veya kullanılmış.", "INVALID_VERIFICATION_CODE");
          } else {
            await client.query("UPDATE email_verifications SET used_at = $1 WHERE user_id = $2 AND used_at = ''", [
              now,
              rec.user_id,
            ]);
            const uRes = await client.query("SELECT * FROM users WHERE id = $1 FOR UPDATE", [rec.user_id]);
            const u = uRes.rows[0];
            if (!u) {
              errToThrow = new HttpError(400, "Kullanıcı bulunamadı.", "USER_NOT_FOUND");
            } else if (u.status !== "active") {
              errToThrow = new HttpError(403, "Hesabınız askıya alınmış. Destek ile iletişime geçin.", "ACCOUNT_SUSPENDED");
            } else {
              const verifiedAt = u.verified_at || now;
              if (!u.trial_used && normalizePlan(u.plan) === "normal") {
                const trialEnds = new Date(nowMs + TRIAL_DURATION_MS).toISOString();
                const upd = await client.query(
                  `UPDATE users
                   SET email_verified = TRUE, verified_at = $1, plan = 'pro', max_devices = 5,
                       trial_used = TRUE, trial_started_at = $2, trial_ends_at = $3, expires_at = $4, last_seen_at = $5
                   WHERE id = $6 RETURNING *`,
                  [verifiedAt, now, trialEnds, trialEnds, now, u.id],
                );
                updatedUser = upd.rows[0];
                trialActivated = true;
              } else {
                const upd = await client.query(
                  "UPDATE users SET email_verified = TRUE, verified_at = $1, last_seen_at = $2 WHERE id = $3 RETURNING *",
                  [verifiedAt, now, u.id],
                );
                updatedUser = upd.rows[0];
              }
            }
          }
        }
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      } finally {
        client.release();
      }

      if (errToThrow) throw errToThrow;

      return jsonResp({
        ok: true,
        token: issueToken(secret, updatedUser.id, updatedUser.role, Number(updatedUser.token_version ?? 1)),
        trialActivated,
        user: publicUser(updatedUser),
      });
    }

    if (path === "/api/v1/auth/resend-verification" && method === "POST") {
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      if (!EMAIL_RE.test(cleanEmail)) throw new HttpError(400, "Geçerli bir e-posta adresi girin.");
      if (
        !(await checkRateLimit(pool, "resend:" + ip, 6)) ||
        !(await checkRateLimit(pool, "resend_email:" + cleanEmail, 3))
      ) {
        throw new HttpError(429, "Çok fazla kod isteği. Lütfen daha sonra tekrar deneyin.");
      }

      const uRes = await pool.query("SELECT * FROM users WHERE email = $1", [cleanEmail]);
      const row = uRes.rows[0];
      if (row) {
        if (row.email_verified) {
          throw new HttpError(400, "E-posta adresi zaten doğrulanmış.", "ALREADY_VERIFIED");
        }
        if (row.status === "active") {
          const nowMs = Date.now();
          const now = new Date(nowMs).toISOString();
          const expiresAt = new Date(nowMs + VERIFY_TTL_MS).toISOString();
          const code = String(crypto.randomInt(0, 1_000_000)).padStart(6, "0");
          const rawToken = crypto.randomBytes(24).toString("base64url");
          await pool.query("UPDATE email_verifications SET used_at = $1 WHERE user_id = $2 AND used_at = ''", [
            now,
            row.id,
          ]);
          await pool.query(
            `INSERT INTO email_verifications (id, user_id, email, code_hash, token_hash, expires_at, used_at, attempts, created_at)
             VALUES ($1,$2,$3,$4,$5,$6,'',0,$7)`,
            [
              "ver_" + crypto.randomBytes(8).toString("hex"),
              row.id,
              cleanEmail,
              hashCode("verify_email", row.id, code),
              hashToken("verify_email", rawToken),
              expiresAt,
              now,
            ],
          );
          const deliveryMode = await deliverEmail(pool, env, mailer, {
            kind: "verify_email",
            recipient: cleanEmail,
            displayName: row.display_name,
            code,
            token: rawToken,
          });
          return jsonResp({ ok: true, deliveryMode });
        }
      }
      return jsonResp({ ok: true, deliveryMode: resolveEmailTransport(env, mailer) });
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
        throw new HttpError(401, "E-posta veya parola hatalı.", "INVALID_CREDENTIALS");
      }
      if (row.status !== "active") {
        throw new HttpError(403, "Hesabınız askıya alınmış. Destek ile iletişime geçin.", "ACCOUNT_SUSPENDED");
      }
      if (!row.email_verified) {
        throw new HttpError(403, "E-posta doğrulaması gerekli.", "EMAIL_NOT_VERIFIED", {
          verificationRequired: true,
          email: row.email,
        });
      }
      await clearRateLimit(pool, bucket);
      const now = isoNow();
      await pool.query("UPDATE users SET last_seen_at = $1 WHERE id = $2", [now, row.id]);
      const user = await getUserById(pool, row.id, true);
      return jsonResp({
        ok: true,
        token: issueToken(secret, row.id, row.role, Number(row.token_version ?? 1)),
        user,
      });
    }

    if (path === "/api/v1/auth/forgot-password" && method === "POST") {
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      if (!EMAIL_RE.test(cleanEmail)) throw new HttpError(400, "Geçerli bir e-posta adresi girin.");
      if (
        !(await checkRateLimit(pool, "forgot:" + ip, 6)) ||
        !(await checkRateLimit(pool, "forgot_email:" + cleanEmail, 3))
      ) {
        throw new HttpError(429, "Çok fazla sıfırlama isteği. Lütfen bekleyin.");
      }

      const uRes = await pool.query("SELECT * FROM users WHERE email = $1", [cleanEmail]);
      const row = uRes.rows[0];
      let deliveryMode = resolveEmailTransport(env, mailer);
      if (row && row.status === "active" && row.email_verified) {
        const nowMs = Date.now();
        const now = new Date(nowMs).toISOString();
        const expiresAt = new Date(nowMs + RESET_TTL_MS).toISOString();
        const code = String(crypto.randomInt(0, 1_000_000)).padStart(6, "0");
        const rawToken = crypto.randomBytes(24).toString("base64url");
        await pool.query("UPDATE password_resets SET used = 1 WHERE user_id = $1 AND used = 0", [row.id]);
        await pool.query(
          `INSERT INTO password_resets (token_hash, user_id, email, code_hash, expires_at, attempts, used, created_at)
           VALUES ($1,$2,$3,$4,$5,0,0,$6)`,
          [
            hashToken("password_reset", rawToken),
            row.id,
            cleanEmail,
            hashCode("password_reset", row.id, code),
            expiresAt,
            now,
          ],
        );
        deliveryMode = await deliverEmail(pool, env, mailer, {
          kind: "password_reset",
          recipient: cleanEmail,
          displayName: row.display_name,
          code,
          token: rawToken,
        });
      }
      return jsonResp({
        ok: true,
        deliveryMode,
        message: "Eğer hesap kayıtlıysa şifre sıfırlama kodu gönderildi.",
      });
    }

    const findResetRecord = async (queryable, { cleanEmail, cleanCode, cleanToken }) => {
      if (cleanToken) {
        const thash = hashToken("password_reset", cleanToken);
        const legHash = legacyHashToken(cleanToken);
        const q = await queryable.query(
          "SELECT * FROM password_resets WHERE (token_hash = $1 OR token_hash = $2) AND used = 0 FOR UPDATE",
          [thash, legHash],
        );
        const rec = q.rows[0] || null;
        const matched = Boolean(
          rec && (timingSafeHexEqual(rec.token_hash, thash) || timingSafeHexEqual(rec.token_hash, legHash)),
        );
        return { rec, matched };
      }
      let q = await queryable.query(
        "SELECT * FROM password_resets WHERE email = $1 AND used = 0 ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
        [cleanEmail],
      );
      let rec = q.rows[0] || null;
      if (!rec) {
        q = await queryable.query(
          `SELECT pr.* FROM password_resets pr
           JOIN users u ON u.id = pr.user_id
           WHERE u.email = $1 AND pr.used = 0
           ORDER BY pr.created_at DESC LIMIT 1 FOR UPDATE`,
          [cleanEmail],
        );
        rec = q.rows[0] || null;
      }
      if (!rec || !rec.code_hash) return { rec, matched: false };
      const expected = hashCode("password_reset", rec.user_id, cleanCode);
      return { rec, matched: timingSafeHexEqual(rec.code_hash, expected) };
    };

    if (path === "/api/v1/auth/verify-reset-code" && method === "POST") {
      if (!(await checkRateLimit(pool, "reset:" + ip, 12))) {
        throw new HttpError(429, "Çok fazla deneme. Lütfen bekleyin.");
      }
      const body = await readJsonBody(req);
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      const cleanCode = String(body.code || "").trim();
      const cleanToken = String(body.token || "").trim();
      if (!cleanToken && (!EMAIL_RE.test(cleanEmail) || !cleanCode)) {
        throw new HttpError(400, "Sıfırlama kodu veya belirteci gerekli.", "INVALID_RESET_INPUT");
      }

      const client = await pool.connect();
      let errToThrow = null;
      try {
        await client.query("BEGIN");
        const { rec, matched } = await findResetRecord(client, { cleanEmail, cleanCode, cleanToken });
        if (!rec) {
          errToThrow = new HttpError(400, "Sıfırlama kodu geçersiz veya kullanılmış.", "INVALID_RESET_CODE");
        } else if (rec.expires_at && Date.parse(rec.expires_at) < Date.now()) {
          await client.query("UPDATE password_resets SET used = 1 WHERE token_hash = $1", [rec.token_hash]);
          errToThrow = new HttpError(400, "Sıfırlama kodunun süresi dolmuş.", "RESET_EXPIRED");
        } else if (Number(rec.attempts) >= MAX_CODE_ATTEMPTS) {
          await client.query("UPDATE password_resets SET used = 1 WHERE token_hash = $1", [rec.token_hash]);
          errToThrow = new HttpError(400, "Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.", "RESET_LOCKED");
        } else if (!matched) {
          const nextAttempts = Number(rec.attempts) + 1;
          const burn = nextAttempts >= MAX_CODE_ATTEMPTS;
          await client.query(
            "UPDATE password_resets SET attempts = $1, used = CASE WHEN $2 THEN 1 ELSE used END WHERE token_hash = $3",
            [nextAttempts, burn, rec.token_hash],
          );
          errToThrow = new HttpError(
            400,
            burn ? "Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin." : "Sıfırlama kodu hatalı.",
            burn ? "RESET_LOCKED" : "INVALID_RESET_CODE",
          );
        }
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      } finally {
        client.release();
      }
      if (errToThrow) throw errToThrow;
      return jsonResp({ ok: true, valid: true });
    }

    if (path === "/api/v1/auth/reset-password" && method === "POST") {
      if (!(await checkRateLimit(pool, "reset:" + ip, 12))) {
        throw new HttpError(429, "Çok fazla deneme. Lütfen bekleyin.");
      }
      const body = await readJsonBody(req);
      const pwHash = hashPassword(body.newPassword || "");
      const cleanToken = String(body.token || "").trim();
      const cleanEmail = String(body.email || "").trim().toLowerCase();
      const cleanCode = String(body.code || "").trim();
      if (!cleanToken && (!EMAIL_RE.test(cleanEmail) || !cleanCode)) {
        throw new HttpError(400, "Sıfırlama bağlantısı veya kodu gerekli.", "INVALID_RESET_INPUT");
      }

      const client = await pool.connect();
      let errToThrow = null;
      try {
        await client.query("BEGIN");
        const { rec, matched } = await findResetRecord(client, { cleanEmail, cleanCode, cleanToken });
        if (!rec) {
          errToThrow = new HttpError(400, "Sıfırlama bağlantısı geçersiz veya kullanılmış.", "INVALID_RESET_CODE");
        } else if (rec.expires_at && Date.parse(rec.expires_at) < Date.now()) {
          await client.query("UPDATE password_resets SET used = 1 WHERE token_hash = $1", [rec.token_hash]);
          errToThrow = new HttpError(400, "Sıfırlama bağlantısının süresi dolmuş.", "RESET_EXPIRED");
        } else if (Number(rec.attempts) >= MAX_CODE_ATTEMPTS) {
          await client.query("UPDATE password_resets SET used = 1 WHERE token_hash = $1", [rec.token_hash]);
          errToThrow = new HttpError(400, "Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.", "RESET_LOCKED");
        } else if (!matched) {
          const nextAttempts = Number(rec.attempts) + 1;
          const burn = nextAttempts >= MAX_CODE_ATTEMPTS;
          await client.query(
            "UPDATE password_resets SET attempts = $1, used = CASE WHEN $2 THEN 1 ELSE used END WHERE token_hash = $3",
            [nextAttempts, burn, rec.token_hash],
          );
          errToThrow = new HttpError(
            400,
            burn ? "Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin." : "Sıfırlama kodu hatalı.",
            burn ? "RESET_LOCKED" : "INVALID_RESET_CODE",
          );
        } else {
          const consume = await client.query(
            "UPDATE password_resets SET used = 1 WHERE token_hash = $1 AND used = 0",
            [rec.token_hash],
          );
          if (consume.rowCount === 0) {
            errToThrow = new HttpError(400, "Sıfırlama bağlantısı geçersiz veya kullanılmış.", "INVALID_RESET_CODE");
          } else {
            await client.query("UPDATE password_resets SET used = 1 WHERE user_id = $1 AND used = 0", [rec.user_id]);
            const uRes = await client.query(
              "UPDATE users SET password_hash = $1, token_version = token_version + 1, last_seen_at = $2 WHERE id = $3 RETURNING id, email",
              [pwHash, isoNow(), rec.user_id],
            );
            if (uRes.rows[0]) {
              await addAudit(client, uRes.rows[0], "user.password_reset", "user", uRes.rows[0].id, {});
            }
          }
        }
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      } finally {
        client.release();
      }
      if (errToThrow) throw errToThrow;
      return jsonResp({ ok: true });
    }

    if (path === "/api/v1/me" && method === "GET") {
      const user = await requireUser();
      return jsonResp({ user: await getUserById(pool, user.id, true) });
    }

    if (path === "/api/v1/sync" && method === "GET") {
      const user = await requireUser();
      if (user.effectivePlan !== "pro") {
        throw new HttpError(403, "Bu özellik Pro plan gerektirir.", "PRO_REQUIRED", { upgradeRequired: true });
      }
      const res = await pool.query("SELECT state_json, updated_at FROM user_sync WHERE user_id = $1", [user.id]);
      const row = res.rows[0];
      if (!row) return jsonResp({ state: null, updatedAt: "" });
      let state = null;
      try {
        state = JSON.parse(row.state_json);
      } catch {
        state = null;
      }
      return jsonResp({ state, updatedAt: row.updated_at });
    }

    if (path === "/api/v1/sync" && (method === "PUT" || method === "POST")) {
      const user = await requireUser();
      if (user.effectivePlan !== "pro") {
        throw new HttpError(403, "Bu özellik Pro plan gerektirir.", "PRO_REQUIRED", { upgradeRequired: true });
      }
      const body = await readJsonBody(req);
      const cleanState = sanitizeSyncState(body);
      const now = isoNow();
      await pool.query(
        `INSERT INTO user_sync (user_id, state_json, updated_at) VALUES ($1, $2, $3)
         ON CONFLICT (user_id) DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = EXCLUDED.updated_at`,
        [user.id, JSON.stringify(cleanState), now],
      );
      await pool.query("UPDATE users SET last_seen_at = $1 WHERE id = $2", [now, user.id]);
      return jsonResp({ ok: true, state: cleanState, updatedAt: now });
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
      const cntRes = await pool.query("SELECT COUNT(*)::int AS cnt FROM devices WHERE user_id = $1", [user.id]);
      const count = Number(cntRes.rows[0].cnt);
      if ((!ex.rows.length && count >= user.maxDevices) || (ex.rows.length && count > user.maxDevices)) {
        throw new HttpError(
          403,
          `Maksimum cihaz sınırına (${user.maxDevices}) ulaşıldı. Plan yükseltin veya eski bir cihazı kaldırın.`,
          "DEVICE_LIMIT_REACHED",
          { maxDevices: user.maxDevices, upgradeRequired: !user.isPro },
        );
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

    if (path.startsWith("/api/v1/devices/") && method === "DELETE") {
      const user = await requireUser();
      const did = decodeURIComponent(path.slice("/api/v1/devices/".length)).trim();
      if (!did) throw new HttpError(400, "Cihaz kimliği gerekli.");
      const delRes = await pool.query("DELETE FROM devices WHERE user_id = $1 AND device_id = $2", [user.id, did]);
      if (delRes.rowCount === 0) {
        throw new HttpError(404, "Cihaz bulunamadı.", "DEVICE_NOT_FOUND");
      }
      const full = await getUserById(pool, user.id, true);
      return jsonResp({ ok: true, devices: full.devices });
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
        const licPlan = normalizePlan(lic.plan);
        const expires = lic.plan === "lifetime" || Number(lic.duration_days) <= 0
          ? ""
          : new Date(now.getTime() + Number(lic.duration_days) * 86400_000).toISOString();
        const newMaxDevices =
          user.effectivePlan === "normal" || user.trialActive
            ? Math.max(1, Number(lic.max_devices))
            : Math.max(user.maxDevices, Number(lic.max_devices));

        await client.query("UPDATE licenses SET uses_count = uses_count + 1 WHERE code = $1", [code]);
        await client.query("INSERT INTO license_redemptions (code, user_id, redeemed_at) VALUES ($1,$2,$3)", [code, user.id, now.toISOString()]);
        await client.query(
          "UPDATE users SET plan = $1, max_devices = $2, expires_at = $3, last_seen_at = $4 WHERE id = $5",
          [licPlan, newMaxDevices, expires, now.toISOString(), user.id],
        );
        await addAudit(client, user, "license.redeem", "license", code, { plan: licPlan, expiresAt: expires });
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
        const now = isoNow();
        const [uTot, uPro, uTrial, uVer, uSusp, devs, lics, dls] = await Promise.all([
          pool.query("SELECT COUNT(*)::int AS c FROM users"),
          pool.query(
            "SELECT COUNT(*)::int AS c FROM users WHERE plan IN ('pro','family','lifetime') AND role = 'user' AND (expires_at = '' OR expires_at > $1)",
            [now],
          ),
          pool.query(
            "SELECT COUNT(*)::int AS c FROM users WHERE plan = 'pro' AND role = 'user' AND trial_ends_at != '' AND expires_at = trial_ends_at AND trial_ends_at > $1",
            [now],
          ),
          pool.query("SELECT COUNT(*)::int AS c FROM users WHERE email_verified = TRUE"),
          pool.query("SELECT COUNT(*)::int AS c FROM users WHERE status = 'suspended'"),
          pool.query("SELECT COUNT(*)::int AS c FROM devices"),
          pool.query("SELECT COUNT(*)::int AS c, COALESCE(SUM(uses_count),0)::int AS r FROM licenses"),
          pool.query("SELECT target, count FROM download_stats"),
        ]);
        return jsonResp({
          totalUsers: uTot.rows[0].c,
          paidUsers: uPro.rows[0].c,
          trialUsers: uTrial.rows[0].c,
          verifiedUsers: uVer.rows[0].c,
          suspendedUsers: uSusp.rows[0].c,
          activeDevices: devs.rows[0].c,
          licensesCreated: lics.rows[0].c,
          licensesRedeemed: lics.rows[0].r,
          downloads: Object.fromEntries(dls.rows.map((r) => [r.target, Number(r.count)])),
        });
      }

      if (path === "/api/v1/admin/users" && method === "GET") {
        const q = (url.searchParams.get("q") || "").trim().toLowerCase();
        const rawPlan = (url.searchParams.get("plan") || "").trim().toLowerCase();
        const status = (url.searchParams.get("status") || "").trim().toLowerCase();
        const where = ["1=1"];
        const args = [];
        if (q) {
          args.push(`%${q}%`, `%${q}%`, q);
          where.push(`(LOWER(email) LIKE $${args.length - 2} OR LOWER(display_name) LIKE $${args.length - 1} OR id = $${args.length})`);
        }
        if (Object.hasOwn(LEGACY_PLAN_MAP, rawPlan)) {
          args.push(normalizePlan(rawPlan));
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
        const tokenHash = hashToken("password_reset", rawToken);
        const now = isoNow();
        const expires = new Date(Date.now() + 3600_000).toISOString();
        await pool.query(
          "INSERT INTO password_resets (token_hash, user_id, email, code_hash, expires_at, attempts, used, created_at) VALUES ($1,$2,$3,'',$4,0,0,$5)",
          [tokenHash, uid, uRes.rows[0].email, expires, now],
        );
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
        const rawPlan = String(body.plan ?? old.plan).trim().toLowerCase();
        if (!Object.hasOwn(LEGACY_PLAN_MAP, rawPlan)) throw new HttpError(400, "Geçersiz plan.");
        const plan = normalizePlan(rawPlan);
        const status = String(body.status ?? old.status).trim().toLowerCase();
        if (!STATUSES.has(status)) throw new HttpError(400, "Geçersiz hesap durumu.");
        const role = String(body.role ?? old.role).trim().toLowerCase();
        if (!ROLES.has(role)) throw new HttpError(400, "Geçersiz rol.");
        if (old.id === admin.id && role !== "admin") {
          throw new HttpError(400, "Kendi yönetici rolünüzü kaldıramazsınız.");
        }

        let maxDevices;
        if ("maxDevices" in body) {
          maxDevices = Math.max(1, Math.min(50, Number.parseInt(body.maxDevices, 10) || Number(old.max_devices)));
        } else if (plan === "normal" && normalizePlan(old.plan) !== "normal") {
          maxDevices = 1;
        } else if (plan === "pro" && normalizePlan(old.plan) !== "pro") {
          maxDevices = Math.max(5, Number(old.max_devices || 5));
        } else {
          maxDevices = Math.max(1, Math.min(50, Number(old.max_devices || 1)));
        }

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
        if (rawPlan === "lifetime") expiresAt = "";

        const emailVerified = "emailVerified" in body ? Boolean(body.emailVerified) : Boolean(old.email_verified);
        const verifiedAt = old.verified_at || (emailVerified ? isoNow() : "");
        const bumpTv = (status === "suspended" && old.status !== "suspended") || role !== old.role ? 1 : 0;

        await pool.query(
          `UPDATE users
           SET plan = $1, status = $2, role = $3, max_devices = $4, display_name = $5, admin_note = $6, expires_at = $7,
               email_verified = $8, verified_at = $9, token_version = token_version + $10
           WHERE id = $11`,
          [plan, status, role, maxDevices, displayName, adminNote, expiresAt, emailVerified, verifiedAt, bumpTv, uid],
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
            plan: normalizePlan(r.plan),
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
        const rawPlan = String(body.plan || "pro").trim().toLowerCase();
        if (!Object.hasOwn(LEGACY_PLAN_MAP, rawPlan) || normalizePlan(rawPlan) === "normal") {
          throw new HttpError(400, "Lisans planı pro olmalıdır.");
        }
        const cleanPlan = "pro";
        const parsedDays = Number.parseInt(body.durationDays ?? 365, 10);
        const days = rawPlan === "lifetime" || parsedDays <= 0 ? 0 : Math.max(1, Math.min(3650, parsedDays || 365));
        const devs = Math.max(1, Math.min(50, Number.parseInt(body.maxDevices ?? 5, 10) || 5));
        const uses = Math.max(1, Math.min(10000, Number.parseInt(body.maxUses ?? 1, 10) || 1));
        const raw = crypto.randomBytes(6).toString("hex").toUpperCase();
        const code = `VRELIO-${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
        const note = String(body.note || "").slice(0, 200);
        const now = isoNow();
        await pool.query(
          "INSERT INTO licenses (code, plan, duration_days, max_devices, max_uses, uses_count, note, created_by, created_at) VALUES ($1,$2,$3,$4,$5,0,$6,$7,$8)",
          [code, cleanPlan, days, devs, uses, note, admin.email, now],
        );
        await addAudit(pool, admin, "license.create", "license", code, { plan: cleanPlan, durationDays: days, maxUses: uses });
        return jsonResp(
          { license: { code, plan: cleanPlan, durationDays: days, maxDevices: devs, maxUses: uses, usesCount: 0, note, createdAt: now } },
          201,
        );
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
          const allowedKeys = [
            "latestVersion",
            "windowsLatest",
            "windowsMin",
            "androidLatest",
            "androidMin",
            "macosLatest",
            "macosMin",
            "iosLatest",
            "iosMin",
            "windowsInstallerUrl",
            "windowsPortableUrl",
            "androidApkUrl",
            "macosUrl",
            "iosUrl",
            "releaseNotes",
          ];
          for (const k of allowedKeys) {
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
    if (err instanceof HttpError) {
      return jsonResp(
        {
          error: err.message,
          ...(err.code ? { code: err.code } : {}),
          ...err.extra,
        },
        err.status,
      );
    }
    console.error("Vrelio cloud function error:", err);
    return jsonResp({ error: "Sunucu hatası oluştu." }, 500);
  }
}
