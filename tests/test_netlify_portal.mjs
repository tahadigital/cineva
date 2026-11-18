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
  handleApiRequest,
} from "../website/netlify/functions/cloud-core.mjs";

function makeMemoryPool() {
  const users = new Map();
  const userSync = new Map();
  const devices = [];
  const licenses = new Map();
  const redemptions = new Set();
  const resets = new Map();
  const auditLogs = [];
  const rateLimits = [];
  const appConfig = new Map([
    ["announcement", JSON.stringify({ enabled: false, title: "", message: "", severity: "info" })],
    ["versions", JSON.stringify({ windowsLatest: "2.0.1", androidLatest: "2.0.1" })],
  ]);
  const downloads = new Map([
    ["windows-installer", 0],
    ["windows-portable", 0],
    ["android-apk", 0],
    ["macos", 0],
  ]);

  const query = async (sql, params = []) => {
    const q = sql.replace(/\s+/g, " ").trim();
    if (q.startsWith("SELECT key, value FROM app_config")) {
      return { rows: Array.from(appConfig, ([key, value]) => ({ key, value })) };
    }
    if (q.startsWith("SELECT target, count FROM download_stats")) {
      return { rows: Array.from(downloads, ([target, count]) => ({ target, count })) };
    }
    if (q.startsWith("SELECT id FROM users WHERE role = 'admin'")) {
      const adm = Array.from(users.values()).find((u) => u.role === "admin");
      return { rows: adm ? [{ id: adm.id }] : [] };
    }
    if (q.includes("INSERT INTO users")) {
      const [id, email, display_name, password_hash] = params;
      if (q.includes("'admin'")) {
        users.set(id, { id, email, display_name, password_hash, role: "admin", plan: "lifetime", status: "active", max_devices: 10, expires_at: "", admin_note: "", created_at: params[4], last_seen_at: params[5] });
        return { rows: [users.get(id)] };
      }
      if (Array.from(users.values()).some((u) => u.email === email)) {
        const e = new Error("duplicate key value violates unique constraint");
        e.code = "23505";
        throw e;
      }
      const row = { id, email, display_name, password_hash, role: "user", plan: "free", status: "active", max_devices: 2, expires_at: "", admin_note: "", created_at: params[4], last_seen_at: params[5] };
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
    if (q.startsWith("SELECT device_id AS id")) {
      return { rows: devices.filter((d) => d.user_id === params[0]).map((d) => ({ id: d.device_id, name: d.device_name, platform: d.platform, lastSeenAt: d.last_seen_at })) };
    }
    if (q.startsWith("DELETE FROM rate_limits")) return { rows: [] };
    if (q.startsWith("SELECT COUNT(*)::int AS cnt FROM rate_limits")) {
      return { rows: [{ cnt: rateLimits.filter((r) => r === params[0]).length }] };
    }
    if (q.startsWith("INSERT INTO rate_limits")) {
      rateLimits.push(params[0]);
      return { rows: [] };
    }
    if (q.startsWith("UPDATE users SET last_seen_at")) {
      const u = users.get(params[1]);
      if (u) u.last_seen_at = params[0];
      return { rows: [] };
    }
    if (q.startsWith("UPDATE users SET plan = $1, status = $2")) {
      const u = users.get(params[7]);
      if (u) Object.assign(u, { plan: params[0], status: params[1], role: params[2], max_devices: params[3], display_name: params[4], admin_note: params[5], expires_at: params[6] });
      return { rows: [] };
    }
    if (q.startsWith("UPDATE users SET plan = $1, max_devices = $2")) {
      const u = users.get(params[4]);
      if (u) Object.assign(u, { plan: params[0], max_devices: params[1], expires_at: params[2], last_seen_at: params[3] });
      return { rows: [] };
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
    if (q.startsWith("INSERT INTO audit_logs")) {
      auditLogs.push({ id: auditLogs.length + 1, actor_email: params[1], action: params[2], target_id: params[4], details: params[5], created_at: params[6] });
      return { rows: [] };
    }
    if (q.startsWith("INSERT INTO download_stats")) {
      const next = (downloads.get(params[0]) ?? 0) + 1;
      downloads.set(params[0], next);
      return { rows: [{ count: next }] };
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
  };
}

test("public index.html hides /admin links and robots.txt disallows admin", () => {
  const indexHtml = fs.readFileSync(path.resolve("website/index.html"), "utf8");
  const robots = fs.readFileSync(path.resolve("website/robots.txt"), "utf8");
  assert.equal(indexHtml.includes('href="/admin"'), false);
  assert.match(robots, /Disallow: \/admin/);
});

test("Netlify cloud core handles PBKDF2 passwords, HMAC tokens, role gating, and license redemption", async () => {
  const hash = hashPassword("StrongPass!99");
  assert.ok(hash.startsWith("pbkdf2_sha256:200000:"));
  assert.equal(verifyPassword("StrongPass!99", hash), true);
  assert.equal(verifyPassword("wrong", hash), false);

  const tok = issueToken("super-secret-key", "usr_1", "user");
  const claims = verifyTokenClaims("super-secret-key", tok);
  assert.equal(claims.sub, "usr_1");

  const db = makeMemoryPool();
  const envMap = {
    CINEVA_CLOUD_SECRET: "super-secret-key",
    CINEVA_ADMIN_EMAIL: "boss@cineva.app",
    CINEVA_ADMIN_PASSWORD: "BossPassword!2026",
  };
  const call = (method, p, body = null, token = "") =>
    handleApiRequest(
      new Request("https://cineva-app.netlify.app" + p, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: "Bearer " + token } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      }),
      { ip: "1.2.3.4", db, env: (k) => envMap[k] || "" },
    );

  // Regular registration + 403 block on admin routes
  const regRes = await call("POST", "/api/v1/auth/register", { email: "user@example.com", password: "UserPass123!" });
  assert.equal(regRes.status, 201);
  const regJson = await regRes.json();
  assert.equal(regJson.user.role, "user");

  const forbidden = await call("GET", "/api/v1/admin/overview", null, regJson.token);
  assert.equal(forbidden.status, 403);

  // Bootstrap admin login + mint license + user redeem
  const admLogin = await call("POST", "/api/v1/auth/login", { email: "boss@cineva.app", password: "BossPassword!2026" });
  assert.equal(admLogin.status, 200);
  const admJson = await admLogin.json();
  assert.equal(admJson.user.role, "admin");

  const licRes = await call("POST", "/api/v1/admin/licenses", { plan: "pro", durationDays: 90, maxUses: 1 }, admJson.token);
  assert.equal(licRes.status, 201);
  const { license } = await licRes.json();

  const redRes = await call("POST", "/api/v1/licenses/redeem", { code: license.code }, regJson.token);
  assert.equal(redRes.status, 200);
  const redJson = await redRes.json();
  assert.equal(redJson.user.plan, "pro");

  // Admin promotes user to co-admin; self-demote prevented
  const promoteRes = await call("PATCH", `/api/v1/admin/users/${regJson.user.id}`, { role: "admin" }, admJson.token);
  assert.equal(promoteRes.status, 200);
  assert.equal((await promoteRes.json()).user.role, "admin");

  const selfDemote = await call("PATCH", `/api/v1/admin/users/${admJson.user.id}`, { role: "user" }, admJson.token);
  assert.equal(selfDemote.status, 400);

  // Zero-Knowledge Cross-Device Sync (/api/v1/sync)
  const initialSync = await call("GET", "/api/v1/sync", null, regJson.token);
  assert.equal(initialSync.status, 200);
  assert.equal((await initialSync.json()).state, null);

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
    regJson.token,
  );
  assert.equal(putSync.status, 200);
  const putSyncJson = await putSync.json();
  assert.equal(putSyncJson.ok, true);
  assert.equal(putSyncJson.state.favorites.length, 1);
  assert.equal("connection" in putSyncJson.state, false);

  const getSync = await call("GET", "/api/v1/sync", null, regJson.token);
  assert.equal(getSync.status, 200);
  const getSyncJson = await getSync.json();
  assert.equal(getSyncJson.state.favorites[0].itemId, "vod:101");
  assert.equal(getSyncJson.state.progress[0].positionSeconds, 120);
  assert.equal("connection" in getSyncJson.state, false);
});
