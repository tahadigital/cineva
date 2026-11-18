import type { Config, Context } from "@netlify/edge-functions";

const COOKIE_NAME = "cineva_admin_gate";
const enc = new TextEncoder();

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function constantTimeEqual(secret: string, a: string, b: string): Promise<boolean> {
  if (!a || !b) return false;
  const [ha, hb] = await Promise.all([hmacHex(secret, "cmp:" + a), hmacHex(secret, "cmp:" + b)]);
  let diff = ha.length ^ hb.length;
  for (let i = 0; i < Math.min(ha.length, hb.length); i++) {
    diff |= ha.charCodeAt(i) ^ hb.charCodeAt(i);
  }
  return diff === 0;
}

function getCookie(req: Request, name: string): string {
  const raw = req.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) return decodeURIComponent(part.slice(idx + 1).trim());
  }
  return "";
}

async function verifyGateCookie(secret: string, token: string): Promise<boolean> {
  const dot = token.indexOf(".");
  if (dot <= 0) return false;
  const expStr = token.slice(0, dot);
  const sigHex = token.slice(dot + 1);
  const exp = Number(expStr);
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) return false;
  const expected = await hmacHex(secret, "gate:" + expStr);
  return constantTimeEqual(secret, sigHex, expected);
}

function hidden404(isApi: boolean): Response {
  const headers = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Type": isApi ? "application/json; charset=utf-8" : "text/plain; charset=utf-8",
  };
  return new Response(isApi ? JSON.stringify({ error: "Sayfa bulunamadı." }) : "Not Found", {
    status: 404,
    headers,
  });
}

export default async (req: Request, context: Context) => {
  const gateKey = (Netlify.env.get("CINEVA_ADMIN_GATE_KEY") ?? "").trim();
  const url = new URL(req.url);
  const isApi = url.pathname.startsWith("/api/");

  // Fail closed until CINEVA_ADMIN_GATE_KEY is configured in Netlify Env Vars.
  if (!gateKey) return hidden404(isApi);

  const signingSecret = (Netlify.env.get("CINEVA_CLOUD_SECRET") ?? "").trim() || gateKey;
  const headerGate = (req.headers.get("x-admin-gate") ?? "").trim();
  const cookieValid = await verifyGateCookie(signingSecret, getCookie(req, COOKIE_NAME));
  const headerValid = headerGate ? await constantTimeEqual(signingSecret, headerGate, gateKey) : false;

  if (!isApi) {
    const accessParam = (url.searchParams.get("access") ?? "").trim();
    if (accessParam && (await constantTimeEqual(signingSecret, accessParam, gateKey))) {
      const exp = String(Math.floor(Date.now() / 1000) + 12 * 3600);
      const sig = await hmacHex(signingSecret, "gate:" + exp);
      const secureFlag = url.protocol === "https:" ? "; Secure" : "";
      return new Response(null, {
        status: 302,
        headers: {
          Location: "/admin",
          "Set-Cookie": `${COOKIE_NAME}=${exp}.${sig}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200${secureFlag}`,
          "Cache-Control": "no-store",
          "X-Robots-Tag": "noindex, nofollow",
        },
      });
    }
    if (!cookieValid && !headerValid) return hidden404(false);

    const res = await context.next();
    const headers = new Headers(res.headers);
    headers.set("X-Robots-Tag", "noindex, nofollow");
    headers.set("Cache-Control", "no-store");
    return new Response(res.body, { status: res.status, headers });
  }

  if (!cookieValid && !headerValid) return hidden404(true);
  return context.next();
};

export const config: Config = {
  path: ["/admin", "/admin/", "/admin.html", "/api/v1/admin/*"],
};
