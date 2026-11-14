// Tek kullanıcılı panel girişi: ADMIN_PASSWORD + HMAC imzalı çerez.
// Web Crypto kullanır; proxy.ts ve sunucu kodunda aynı şekilde çalışır.
export const SESSION_COOKIE = "fds_session";
const MAX_AGE_SEC = 60 * 60 * 24 * 14;

const enc = new TextEncoder();

function b64url(buf: ArrayBuffer) {
  return Buffer.from(buf).toString("base64url");
}

async function hmac(secret: string, data: string) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

function secret() {
  return process.env.SESSION_SECRET || process.env.ADMIN_PASSWORD || "";
}

/** Şifre tanımlı değilse ve üretim ortamı değilse giriş devre dışıdır (yalnızca yerel geliştirme). */
export function authDisabled() {
  return !process.env.ADMIN_PASSWORD && process.env.NODE_ENV !== "production";
}

export async function createSessionToken() {
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_SEC;
  const payload = `admin.${exp}`;
  return { token: `${payload}.${await hmac(secret(), payload)}`, maxAge: MAX_AGE_SEC };
}

export async function verifySessionToken(token: string | undefined) {
  if (!token || !secret()) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [who, exp, sig] = parts;
  if (who !== "admin" || Number(exp) < Date.now() / 1000) return false;
  const expected = await hmac(secret(), `${who}.${exp}`);
  if (expected.length !== sig.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export function checkPassword(input: string) {
  const pw = process.env.ADMIN_PASSWORD ?? "";
  if (!pw || input.length !== pw.length) return false;
  let diff = 0;
  for (let i = 0; i < pw.length; i++) diff |= pw.charCodeAt(i) ^ input.charCodeAt(i);
  return diff === 0;
}
