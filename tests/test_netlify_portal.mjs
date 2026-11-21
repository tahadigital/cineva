import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {
  hashPassword,
  verifyPassword,
  issueToken,
  verifyTokenClaims,
  sanitizeSyncState,
  normalizePlan,
  handleApiRequest,
} from "../website/netlify/functions/cloud-core.mjs";

function makeMemoryPool() {
  const users = new Map();
  const userSync = new Map();
  const devices = [];
  const licenses = new Map();
  const redemptions = new Set();
  const emailVerifications = [];
  const resets = [];
  const emailOutbox = [];
  const auditLogs = [];
  const rateLimits = [];
  const appConfig = new Map([
    ["announcement", JSON.stringify({ enabled: false, title: "", message: "", severity: "info" })],
    ["versions", JSON.stringify({ windowsLatest: "2.1.0", androidLatest: "2.1.0" })],
  ]);
  const downloads = new Map([
    ["windows-installer", 0],
    ["windows-portable", 0],
    ["android-apk", 0],
    ["macos", 0],
    ["ios", 0],
  ]);

  const query = async (sql, params = []) => {
    const q = sql.replace(/\s+/g, " ").trim();

    if (q.startsWith("SELECT key, value FROM app_config")) {
      return { rows: Array.from(appConfig, ([key, value]) => ({ key, value })) };
    }
    if (q.startsWith("INSERT INTO app_config")) {
      const keyMatch = q.match(/VALUES \('([^']+)'/);
      if (keyMatch) appConfig.set(keyMatch[1], params[0]);
      return { rows: [] };
    }
    if (q.startsWith("SELECT target, count FROM download_stats")) {
      return { rows: Array.from(downloads, ([target, count]) => ({ target, count })) };
    }
    if (q.startsWith("INSERT INTO download_stats")) {
      const next = (downloads.get(params[0]) ?? 0) + 1;
      downloads.set(params[0], next);
      return { rows: [{ count: next }] };
    }

    // Users queries
    if (q.startsWith("SELECT id FROM users WHERE role = 'admin'")) {
      const adm = Array.from(users.values()).find((u) => u.role === "admin");
      return { rows: adm ? [{ id: adm.id }] : [] };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS c FROM users WHERE plan IN ('pro','family','lifetime')")) {
      const now = params[0];
      const cnt = Array.from(users.values()).filter(
        (u) => ["pro", "family", "lifetime"].includes(u.plan) && u.role === "user" && (!u.expires_at || u.expires_at > now),
      ).length;
      return { rows: [{ c: cnt }] };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS c FROM users WHERE plan = 'pro' AND role = 'user' AND trial_ends_at != ''")) {
      const now = params[0];
      const cnt = Array.from(users.values()).filter(
        (u) => u.plan === "pro" && u.role === "user" && u.trial_ends_at && u.expires_at === u.trial_ends_at && u.trial_ends_at > now,
      ).length;
      return { rows: [{ c: cnt }] };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS c FROM users WHERE email_verified = TRUE")) {
      return { rows: [{ c: Array.from(users.values()).filter((u) => u.email_verified).length }] };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS c FROM users WHERE status = 'suspended'")) {
      return { rows: [{ c: Array.from(users.values()).filter((u) => u.status === "suspended").length }] };
    }
    if (q === "SELECT COUNT(*)::int AS c FROM users") {
      return { rows: [{ c: users.size }] };
    }
    if (q.startsWith("SELECT u.*, COALESCE(dc.cnt, 0)::int AS device_count FROM users u")) {
      const list = Array.from(users.values()).map((u) => ({
        ...u,
        device_count: devices.filter((d) => d.user_id === u.id).length,
      }));
      return { rows: list };
    }
    if (q.startsWith("INSERT INTO users")) {
      const [id, email, display_name, password_hash] = params;
      if (q.includes("'admin'")) {
        if (Array.from(users.values()).some((u) => u.email === email)) return { rows: [] };
        const row = {
          id,
          email,
          display_name,
          password_hash,
          role: "admin",
          plan: "pro",
          status: "active",
          max_devices: 10,
          expires_at: "",
          admin_note: "Sistem yöneticisi",
          created_at: params[4],
          last_seen_at: params[5],
          email_verified: true,
          verified_at: params[6],
          trial_used: true,
          trial_started_at: "",
          trial_ends_at: "",
          token_version: 1,
        };
        users.set(id, row);
        return { rows: [row] };
      }
      if (Array.from(users.values()).some((u) => u.email === email)) {
        const e = new Error("duplicate key value violates unique constraint");
        e.code = "23505";
        throw e;
      }
      const row = {
        id,
        email,
        display_name,
        password_hash,
        role: "user",
        plan: "normal",
        status: "active",
        max_devices: 1,
        expires_at: "",
        admin_note: "",
        created_at: params[4],
        last_seen_at: params[5],
        email_verified: false,
        verified_at: "",
        trial_used: false,
        trial_started_at: "",
        trial_ends_at: "",
        token_version: 1,
      };
      users.set(id, row);
      return { rows: [row] };
    }
    if (q.startsWith("SELECT * FROM users WHERE id = $1")) {
      const u = users.get(params[0]);
      return { rows: u ? [u] : [] };
    }
    if (q.startsWith("SELECT * FROM users WHERE email = $1")) {
      const u = Array.from(users.values()).find((x) => x.email === params[0]);
      return { rows: u ? [u] : [] };
    }
    if (q.startsWith("SELECT id, email FROM users WHERE id = $1")) {
      const u = users.get(params[0]);
      return { rows: u ? [{ id: u.id, email: u.email }] : [] };
    }
    if (q.startsWith("UPDATE users SET display_name = $1, password_hash = $2, last_seen_at = $3 WHERE id = $4")) {
      const u = users.get(params[3]);
      if (u) Object.assign(u, { display_name: params[0], password_hash: params[1], last_seen_at: params[2] });
      return { rows: u ? [u] : [] };
    }
    if (q.startsWith("UPDATE users SET email_verified = TRUE, verified_at = $1, plan = 'pro'")) {
      const u = users.get(params[5]);
      if (u) {
        Object.assign(u, {
          email_verified: true,
          verified_at: params[0],
          plan: "pro",
          max_devices: 5,
          trial_used: true,
          trial_started_at: params[1],
          trial_ends_at: params[2],
          expires_at: params[3],
          last_seen_at: params[4],
        });
      }
      return { rows: u ? [u] : [] };
    }
    if (q.startsWith("UPDATE users SET email_verified = TRUE, verified_at = $1, last_seen_at = $2 WHERE id = $3")) {
      const u = users.get(params[2]);
      if (u) Object.assign(u, { email_verified: true, verified_at: params[0], last_seen_at: params[1] });
      return { rows: u ? [u] : [] };
    }
    if (q.startsWith("UPDATE users SET password_hash = $1, token_version = token_version + 1, last_seen_at = $2 WHERE id = $3")) {
      const u = users.get(params[2]);
      if (u) {
        u.password_hash = params[0];
        u.token_version += 1;
        u.last_seen_at = params[1];
      }
      return { rows: u ? [{ id: u.id, email: u.email }] : [] };
    }
    if (q.startsWith("UPDATE users SET last_seen_at = $1 WHERE id = $2")) {
      const u = users.get(params[1]);
      if (u) u.last_seen_at = params[0];
      return { rows: [] };
    }
    if (q.startsWith("UPDATE users SET plan = $1, status = $2")) {
      const u = users.get(params[10]);
      if (u) {
        Object.assign(u, {
          plan: params[0],
          status: params[1],
          role: params[2],
          max_devices: params[3],
          display_name: params[4],
          admin_note: params[5],
          expires_at: params[6],
          email_verified: params[7],
          verified_at: params[8],
          token_version: u.token_version + Number(params[9] || 0),
        });
      }
      return { rows: [] };
    }
    if (q.startsWith("UPDATE users SET plan = $1, max_devices = $2")) {
      const u = users.get(params[4]);
      if (u) Object.assign(u, { plan: params[0], max_devices: params[1], expires_at: params[2], last_seen_at: params[3] });
      return { rows: [] };
    }

    // Email verifications
    if (q.startsWith("INSERT INTO email_verifications")) {
      emailVerifications.push({
        id: params[0],
        user_id: params[1],
        email: params[2],
        code_hash: params[3],
        token_hash: params[4],
        expires_at: params[5],
        used_at: "",
        attempts: 0,
        created_at: params[6],
      });
      return { rows: [] };
    }
    if (q.startsWith("UPDATE email_verifications SET used_at = $1 WHERE user_id = $2")) {
      for (const r of emailVerifications) {
        if (r.user_id === params[1] && r.used_at === "") r.used_at = params[0];
      }
      return { rows: [] };
    }
    if (q.startsWith("SELECT * FROM email_verifications WHERE token_hash = $1 AND used_at = ''")) {
      const r = emailVerifications.find((x) => x.token_hash === params[0] && x.used_at === "");
      return { rows: r ? [r] : [] };
    }
    if (q.startsWith("SELECT * FROM email_verifications WHERE email = $1 AND used_at = ''")) {
      const list = emailVerifications
        .filter((x) => x.email === params[0] && x.used_at === "")
        .sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { rows: list.length ? [list[0]] : [] };
    }
    if (q.startsWith("UPDATE email_verifications SET used_at = $1 WHERE id = $2 AND used_at = ''")) {
      const r = emailVerifications.find((x) => x.id === params[1] && x.used_at === "");
      if (r) {
        r.used_at = params[0];
        return { rows: [], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    }
    if (q.startsWith("UPDATE email_verifications SET used_at = $1 WHERE id = $2")) {
      const r = emailVerifications.find((x) => x.id === params[1]);
      if (r) r.used_at = params[0];
      return { rows: [] };
    }
    if (q.startsWith("UPDATE email_verifications SET attempts = $1, used_at = $2 WHERE id = $3")) {
      const r = emailVerifications.find((x) => x.id === params[2]);
      if (r) {
        r.attempts = params[0];
        r.used_at = params[1];
      }
      return { rows: [] };
    }

    // Password resets
    if (q.startsWith("INSERT INTO password_resets")) {
      resets.push({
        token_hash: params[0],
        user_id: params[1],
        email: params[2],
        code_hash: params[3],
        expires_at: params[4],
        attempts: 0,
        used: 0,
        created_at: params[5],
      });
      return { rows: [] };
    }
    if (q.startsWith("UPDATE password_resets SET used = 1 WHERE user_id = $1 AND used = 0")) {
      for (const r of resets) {
        if (r.user_id === params[0] && r.used === 0) r.used = 1;
      }
      return { rows: [] };
    }
    if (q.startsWith("SELECT * FROM password_resets WHERE (token_hash = $1 OR token_hash = $2) AND used = 0")) {
      const r = resets.find((x) => (x.token_hash === params[0] || x.token_hash === params[1]) && x.used === 0);
      return { rows: r ? [r] : [] };
    }
    if (q.startsWith("SELECT * FROM password_resets WHERE email = $1 AND used = 0")) {
      const list = resets
        .filter((x) => x.email === params[0] && x.used === 0)
        .sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { rows: list.length ? [list[0]] : [] };
    }
    if (q.startsWith("SELECT pr.* FROM password_resets pr JOIN users u")) {
      const u = Array.from(users.values()).find((x) => x.email === params[0]);
      if (!u) return { rows: [] };
      const list = resets
        .filter((x) => x.user_id === u.id && x.used === 0)
        .sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { rows: list.length ? [list[0]] : [] };
    }
    if (q.startsWith("UPDATE password_resets SET used = 1 WHERE token_hash = $1 AND used = 0")) {
      const r = resets.find((x) => x.token_hash === params[0] && x.used === 0);
      if (r) {
        r.used = 1;
        return { rows: [], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    }
    if (q.startsWith("UPDATE password_resets SET used = 1 WHERE token_hash = $1")) {
      const r = resets.find((x) => x.token_hash === params[0]);
      if (r) r.used = 1;
      return { rows: [] };
    }
    if (q.startsWith("UPDATE password_resets SET attempts = $1, used = CASE WHEN $2 THEN 1 ELSE used END WHERE token_hash = $3")) {
      const r = resets.find((x) => x.token_hash === params[2]);
      if (r) {
        r.attempts = params[0];
        if (params[1]) r.used = 1;
      }
      return { rows: [] };
    }

    // Email outbox
    if (q.startsWith("INSERT INTO email_outbox")) {
      emailOutbox.push({
        id: params[0],
        recipient: params[1],
        subject: params[2],
        body_text: params[3],
        kind: params[4],
        delivery_mode: params[5],
        status: params[6],
        metadata_json: params[7],
        error_message: params[8],
        created_at: params[9],
      });
      return { rows: [] };
    }

    // Devices
    if (q.startsWith("SELECT device_id AS id")) {
      return {
        rows: devices
          .filter((d) => d.user_id === params[0])
          .map((d) => ({ id: d.device_id, name: d.device_name, platform: d.platform, lastSeenAt: d.last_seen_at })),
      };
    }
    if (q.startsWith("SELECT device_id FROM devices WHERE user_id = $1 AND device_id = $2")) {
      return { rows: devices.filter((d) => d.user_id === params[0] && d.device_id === params[1]) };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS cnt FROM devices WHERE user_id = $1")) {
      return { rows: [{ cnt: devices.filter((d) => d.user_id === params[0]).length }] };
    }
    if (q === "SELECT COUNT(*)::int AS c FROM devices") {
      return { rows: [{ c: devices.length }] };
    }
    if (q.startsWith("INSERT INTO devices")) {
      const idx = devices.findIndex((d) => d.user_id === params[0] && d.device_id === params[1]);
      const rec = { user_id: params[0], device_id: params[1], device_name: params[2], platform: params[3], last_seen_at: params[4] };
      if (idx >= 0) devices[idx] = rec;
      else devices.push(rec);
      return { rows: [] };
    }
    if (q.startsWith("DELETE FROM devices WHERE user_id = $1 AND device_id = $2")) {
      let deleted = 0;
      for (let i = devices.length - 1; i >= 0; i--) {
        if (devices[i].user_id === params[0] && devices[i].device_id === params[1]) {
          devices.splice(i, 1);
          deleted += 1;
        }
      }
      return { rows: [], rowCount: deleted };
    }

    // Rate limits
    if (q.startsWith("DELETE FROM rate_limits WHERE bucket = $1 AND ts < $2")) {
      for (let i = rateLimits.length - 1; i >= 0; i--) {
        if (rateLimits[i].bucket === params[0] && rateLimits[i].ts < params[1]) rateLimits.splice(i, 1);
      }
      return { rows: [] };
    }
    if (q.startsWith("DELETE FROM rate_limits WHERE bucket = $1")) {
      for (let i = rateLimits.length - 1; i >= 0; i--) {
        if (rateLimits[i].bucket === params[0]) rateLimits.splice(i, 1);
      }
      return { rows: [] };
    }
    if (q.startsWith("SELECT COUNT(*)::int AS cnt FROM rate_limits")) {
      return { rows: [{ cnt: rateLimits.filter((r) => r.bucket === params[0]).length }] };
    }
    if (q.startsWith("INSERT INTO rate_limits")) {
      rateLimits.push({ bucket: params[0], ts: params[1] });
      return { rows: [] };
    }

    // Licenses & redemptions
    if (q.startsWith("SELECT COUNT(*)::int AS c, COALESCE(SUM(uses_count),0)::int AS r FROM licenses")) {
      const rSum = Array.from(licenses.values()).reduce((acc, l) => acc + l.uses_count, 0);
      return { rows: [{ c: licenses.size, r: rSum }] };
    }
    if (q.startsWith("INSERT INTO licenses")) {
      const [code, plan, duration_days, max_devices, max_uses, note, created_by, created_at] = params;
      licenses.set(code, { code, plan, duration_days, max_devices, max_uses, uses_count: 0, note, created_by, created_at });
      return { rows: [] };
    }
    if (q.startsWith("SELECT * FROM licenses WHERE code = $1")) {
      const l = licenses.get(params[0]);
      return { rows: l ? [l] : [] };
    }
    if (q.startsWith("SELECT * FROM licenses ORDER BY")) {
      return { rows: Array.from(licenses.values()) };
    }
    if (q.startsWith("DELETE FROM licenses WHERE code = $1")) {
      licenses.delete(params[0]);
      return { rows: [] };
    }
    if (q.startsWith("SELECT 1 FROM license_redemptions")) {
      return { rows: redemptions.has(`${params[0]}:${params[1]}`) ? [{ ok: 1 }] : [] };
    }
    if (q.startsWith("UPDATE licenses SET uses_count")) {
      licenses.get(params[0]).uses_count += 1;
      return { rows: [] };
    }
    if (q.startsWith("INSERT INTO license_redemptions")) {
      redemptions.add(`${params[0]}:${params[1]}`);
      return { rows: [] };
    }

    // Audit & sync
    if (q.startsWith("INSERT INTO audit_logs")) {
      auditLogs.push({ id: auditLogs.length + 1, actor_email: params[1], action: params[2], target_type: params[3], target_id: params[4], details: params[5], created_at: params[6] });
      return { rows: [] };
    }
    if (q.startsWith("SELECT * FROM audit_logs")) {
      return { rows: [...auditLogs].reverse() };
    }
    if (q.startsWith("SELECT state_json, updated_at FROM user_sync")) {
      const row = userSync.get(params[0]);
      return { rows: row ? [row] : [] };
    }
    if (q.startsWith("INSERT INTO user_sync")) {
      userSync.set(params[0], { state_json: params[1], updated_at: params[2] });
      return { rows: [] };
    }
    if (q.startsWith("BEGIN") || q.startsWith("COMMIT") || q.startsWith("ROLLBACK")) return { rows: [] };
    throw new Error("Unhandled mock SQL: " + q);
  };

  return {
    pool: {
      query,
      connect: async () => ({ query, release: () => {} }),
    },
    _users: users,
    _emailOutbox: emailOutbox,
    _devices: devices,
  };
}

function makeCaller(db, envMap, ip = "1.2.3.4", mailer = null) {
  return (method, p, body = null, token = "") =>
    handleApiRequest(
      new Request("https://mavie.netlify.app" + p, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: "Bearer " + token } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      }),
      { ip, db, env: (k) => envMap[k] || "", mailer },
    );
}

test("public index.html hides /admin links and robots.txt disallows admin", () => {
  const indexHtml = fs.readFileSync(path.resolve("website/index.html"), "utf8");
  const robots = fs.readFileSync(path.resolve("website/robots.txt"), "utf8");
  assert.equal(indexHtml.includes('href="/admin"'), false);
  assert.match(robots, /Disallow: \/admin/);
});

test("admin-gate.ts and website/package.json reflect Mavie branding with legacy fallback", () => {
  const pkg = JSON.parse(fs.readFileSync(path.resolve("website/package.json"), "utf8"));
  assert.equal(pkg.name, "mavie-portal");
  const gateSrc = fs.readFileSync(path.resolve("website/netlify/edge-functions/admin-gate.ts"), "utf8");
  assert.match(gateSrc, /mavie_admin_gate/);
  assert.match(gateSrc, /MAVIE_ADMIN_GATE_KEY/);
  assert.match(gateSrc, /CINEVA_ADMIN_GATE_KEY/);
});

test("Netlify cloud core health, 4-platform app-config, and iOS download tracking", async () => {
  const db = makeMemoryPool();
  const call = makeCaller(db, { MAVIE_CLOUD_SECRET: "super-secret-key" });

  const hRes = await call("GET", "/api/v1/health");
  assert.equal(hRes.status, 200);
  assert.deepEqual(await hRes.json(), { ok: true, service: "mavie-cloud" });

  const cfgRes = await call("GET", "/api/v1/app-config");
  assert.equal(cfgRes.status, 200);
  const cfg = await cfgRes.json();
  assert.match(cfg.versions.windowsInstallerUrl, /Mavie-Setup\.exe/);
  assert.match(cfg.versions.macosUrl, /Mavie-macOS\.dmg/);
  assert.match(cfg.versions.iosUrl, /Mavie-iOS\.ipa/);
  assert.equal(cfg.plans.normal.maxDevices, 1);
  assert.equal(cfg.plans.pro.maxDevices, 5);
  assert.equal(cfg.plans.pro.trialDays, 3);

  const trackIos = await call("POST", "/api/v1/downloads/track", { target: "ios" });
  assert.equal(trackIos.status, 200);
  assert.deepEqual(await trackIos.json(), { target: "ios", count: 1 });
});

test("Netlify cloud core handles email verification, 3-day Pro trial, trial expiry, device removal, and Normal/Pro gating", async () => {
  const hash = hashPassword("StrongPass!99");
  assert.ok(hash.startsWith("pbkdf2_sha256:200000:"));
  assert.equal(verifyPassword("StrongPass!99", hash), true);
  assert.equal(verifyPassword("wrong", hash), false);

  const tok = issueToken("super-secret-key", "usr_1", "user");
  const claims = verifyTokenClaims("super-secret-key", tok);
  assert.equal(claims.sub, "usr_1");

  const db = makeMemoryPool();
  const envMap = {
    MAVIE_CLOUD_SECRET: "super-secret-key",
    MAVIE_ADMIN_EMAIL: "boss@mavie.app",
    MAVIE_ADMIN_PASSWORD: "BossPassword!2026",
  };
  const call = makeCaller(db, envMap);

  // 1. Register creates unverified Normal account without returning token
  const regRes = await call("POST", "/api/v1/auth/register", {
    email: "user@example.com",
    password: "UserPass123!",
    displayName: "Kullanıcı",
  });
  assert.equal(regRes.status, 201);
  const regJson = await regRes.json();
  assert.equal(regJson.verificationRequired, true);
  assert.equal(regJson.emailVerified, false);
  assert.equal("token" in regJson, false);
  assert.equal(regJson.user.plan, "normal");
  assert.equal(regJson.user.maxDevices, 1);

  // Unverified login blocked with 403 EMAIL_NOT_VERIFIED
  const unverifiedLogin = await call("POST", "/api/v1/auth/login", {
    email: "user@example.com",
    password: "UserPass123!",
  });
  assert.equal(unverifiedLogin.status, 403);
  assert.equal((await unverifiedLogin.json()).code, "EMAIL_NOT_VERIFIED");

  // Unverified re-registration updates password & sends new code without trial
  const reregRes = await call("POST", "/api/v1/auth/register", {
    email: "user@example.com",
    password: "UpdatedUserPass123!",
    displayName: "Yeni Ad",
  });
  assert.equal(reregRes.status, 201);

  // Resend verification & verify via outbox code -> activates 3-day Pro trial
  const resendRes = await call("POST", "/api/v1/auth/resend-verification", { email: "user@example.com" });
  assert.equal(resendRes.status, 200);
  const latestMail = db._emailOutbox.filter((m) => m.recipient === "user@example.com" && m.kind === "verify_email").pop();
  const { code } = JSON.parse(latestMail.metadata_json);

  const verRes = await call("POST", "/api/v1/auth/verify-email", { email: "user@example.com", code });
  assert.equal(verRes.status, 200);
  const verJson = await verRes.json();
  assert.equal(verJson.trialActivated, true);
  assert.equal(verJson.user.effectivePlan, "pro");
  assert.equal(verJson.user.trialActive, true);
  assert.equal(verJson.user.maxDevices, 5);
  const userToken = verJson.token;

  // Ordinary user CANNOT touch admin APIs
  const forbidden = await call("GET", "/api/v1/admin/overview", null, userToken);
  assert.equal(forbidden.status, 403);

  // Active trial allows sync & multiple devices
  const putSync = await call(
    "PUT",
    "/api/v1/sync",
    {
      state: {
        version: 1,
        favorites: [{ itemId: "vod:101", addedAt: 1700000000 }],
        progress: [{ itemId: "vod:101", positionSeconds: 120, durationSeconds: 3600, completed: false, updatedAt: 1700000050 }],
        connection: { host: "http://secret-iptv.example.com", password: "secret" },
      },
    },
    userToken,
  );
  assert.equal(putSync.status, 200);
  const putSyncJson = await putSync.json();
  assert.equal("connection" in putSyncJson.state, false);

  await call("POST", "/api/v1/devices/register", { deviceId: "d1", deviceName: "Mac", platform: "macos" }, userToken);
  await call("POST", "/api/v1/devices/register", { deviceId: "d2", deviceName: "iPhone", platform: "ios" }, userToken);

  // Expire trial -> auto-downgrade to normal, sync returns 403 PRO_REQUIRED, 3rd device returns 403 DEVICE_LIMIT_REACHED
  const userRow = db._users.get(verJson.user.id);
  const past = new Date(Date.now() - 60_000).toISOString();
  userRow.trial_ends_at = past;
  userRow.expires_at = past;

  const blockedSync = await call("GET", "/api/v1/sync", null, userToken);
  assert.equal(blockedSync.status, 403);
  assert.equal((await blockedSync.json()).code, "PRO_REQUIRED");

  const blockedDev = await call(
    "POST",
    "/api/v1/devices/register",
    { deviceId: "d3", deviceName: "TV", platform: "android" },
    userToken,
  );
  assert.equal(blockedDev.status, 403);
  assert.equal((await blockedDev.json()).code, "DEVICE_LIMIT_REACHED");

  // User trims device d2 -> 1 device remains; deleting non-owned device returns 404
  const delOther = await call("DELETE", "/api/v1/devices/not-mine", null, userToken);
  assert.equal(delOther.status, 404);
  const delDev = await call("DELETE", "/api/v1/devices/d2", null, userToken);
  assert.equal(delDev.status, 200);
  assert.equal((await delDev.json()).devices.length, 1);

  // Admin login + mint MAVIE-* license + user redeem restores Pro & sync
  const admLogin = await call("POST", "/api/v1/auth/login", { email: "boss@mavie.app", password: "BossPassword!2026" });
  assert.equal(admLogin.status, 200);
  const admJson = await admLogin.json();
  assert.equal(admJson.user.role, "admin");

  const licRes = await call("POST", "/api/v1/admin/licenses", { plan: "pro", durationDays: 90, maxUses: 1 }, admJson.token);
  assert.equal(licRes.status, 201);
  const { license } = await licRes.json();
  assert.ok(license.code.startsWith("MAVIE-"));

  const redRes = await call("POST", "/api/v1/licenses/redeem", { code: license.code }, userToken);
  assert.equal(redRes.status, 200);
  const redJson = await redRes.json();
  assert.equal(redJson.user.effectivePlan, "pro");

  const getSync = await call("GET", "/api/v1/sync", null, userToken);
  assert.equal(getSync.status, 200);
  assert.equal((await getSync.json()).state.favorites[0].itemId, "vod:101");

  // Admin promotes user to co-admin; self-demote prevented
  const promoteRes = await call("PATCH", `/api/v1/admin/users/${verJson.user.id}`, { role: "admin" }, admJson.token);
  assert.equal(promoteRes.status, 200);
  assert.equal((await promoteRes.json()).user.role, "admin");

  const selfDemote = await call("PATCH", `/api/v1/admin/users/${admJson.user.id}`, { role: "user" }, admJson.token);
  assert.equal(selfDemote.status, 400);
});

test("Netlify cloud core handles password reset, 5-attempt lockout, token_version revocation, and CINEVA_* fallback", async () => {
  const db = makeMemoryPool();
  const sentHooks = [];
  const call = makeCaller(
    db,
    {
      CINEVA_CLOUD_SECRET: "legacy-secret-fallback",
      CINEVA_ADMIN_EMAIL: "boss@cineva.app",
      CINEVA_ADMIN_PASSWORD: "BossPassword!2026",
    },
    "5.6.7.8",
    async (mail) => {
      sentHooks.push(mail);
    },
  );

  await call("POST", "/api/v1/auth/register", { email: "rst@example.com", password: "InitialPass123!" });
  const verifyMail = sentHooks.find((m) => m.recipient === "rst@example.com" && m.kind === "verify_email");
  assert.ok(verifyMail);
  const verRes = await call("POST", "/api/v1/auth/verify-email", { token: verifyMail.token });
  assert.equal(verRes.status, 200);
  const oldToken = (await verRes.json()).token;

  // Forgot password -> non-enumerating 200 for unknown email, sends reset code for verified email
  const fgUnk = await call("POST", "/api/v1/auth/forgot-password", { email: "missing@example.com" });
  assert.equal(fgUnk.status, 200);
  const fgKnown = await call("POST", "/api/v1/auth/forgot-password", { email: "rst@example.com" });
  assert.equal(fgKnown.status, 200);
  const resetMail = sentHooks.filter((m) => m.recipient === "rst@example.com" && m.kind === "password_reset").pop();

  // 5 bad attempts burn the reset code
  for (let i = 0; i < 5; i++) {
    const bad = await call("POST", "/api/v1/auth/verify-reset-code", { email: "rst@example.com", code: `00000${i}` });
    assert.equal(bad.status, 400);
  }
  const burned = await call("POST", "/api/v1/auth/verify-reset-code", { email: "rst@example.com", code: resetMail.code });
  assert.equal(burned.status, 400);

  // Request new reset code, verify without consuming, then reset password
  await call("POST", "/api/v1/auth/forgot-password", { email: "rst@example.com" });
  const resetMail2 = sentHooks.filter((m) => m.recipient === "rst@example.com" && m.kind === "password_reset").pop();

  const vrc = await call("POST", "/api/v1/auth/verify-reset-code", { email: "rst@example.com", code: resetMail2.code });
  assert.equal(vrc.status, 200);
  assert.equal((await vrc.json()).valid, true);

  const rstDone = await call("POST", "/api/v1/auth/reset-password", {
    email: "rst@example.com",
    code: resetMail2.code,
    newPassword: "BrandNewPass!2026",
  });
  assert.equal(rstDone.status, 200);

  // Old token is revoked immediately via token_version
  const oldMe = await call("GET", "/api/v1/me", null, oldToken);
  assert.equal(oldMe.status, 401);

  // Old password returns 401; new password returns 200
  const oldLogin = await call("POST", "/api/v1/auth/login", { email: "rst@example.com", password: "InitialPass123!" });
  assert.equal(oldLogin.status, 401);
  const newLogin = await call("POST", "/api/v1/auth/login", { email: "rst@example.com", password: "BrandNewPass!2026" });
  assert.equal(newLogin.status, 200);
});

test("Netlify cloud core rejects Object.prototype keys like toString and constructor as invalid plans", async () => {
  const db = makeMemoryPool();
  const call = makeCaller(db, {
    MAVIE_CLOUD_SECRET: "test-secret",
    MAVIE_ADMIN_EMAIL: "boss@mavie.app",
    MAVIE_ADMIN_PASSWORD: "BossPassword!2026",
  });
  const admLogin = await call("POST", "/api/v1/auth/login", {
    email: "boss@mavie.app",
    password: "BossPassword!2026",
  });
  assert.equal(admLogin.status, 200);
  const admJson = await admLogin.json();
  const adminToken = admJson.token;

  for (const protoKey of ["toString", "constructor", "valueOf"]) {
    assert.equal(normalizePlan(protoKey), "normal");

    const patchUser = await call(
      "PATCH",
      `/api/v1/admin/users/${admJson.user.id}`,
      { plan: protoKey },
      adminToken,
    );
    assert.equal(patchUser.status, 400);

    const createLic = await call(
      "POST",
      "/api/v1/admin/licenses",
      { plan: protoKey, durationDays: 30 },
      adminToken,
    );
    assert.equal(createLic.status, 400);

    const listUsers = await call("GET", `/api/v1/admin/users?plan=${encodeURIComponent(protoKey)}`, null, adminToken);
    assert.equal(listUsers.status, 200);
    assert.ok((await listUsers.json()).users.length >= 1);
  }
});
