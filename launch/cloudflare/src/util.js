// Small helpers shared by the Worker's routes.

export const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"; // Crockford's base 32: no I, L, O or U

const enc = new TextEncoder();

/** Security headers for everything the Worker answers itself (static files get theirs from _headers). */
export function secure(headers = new Headers()) {
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("Cross-Origin-Resource-Policy", "same-origin");
  headers.set("Cross-Origin-Opener-Policy", "same-origin");
  if (!headers.has("Cache-Control")) headers.set("Cache-Control", "no-store");
  return headers;
}

export function json(status, body, extra = {}) {
  const h = secure(new Headers({ "Content-Type": "application/json; charset=utf-8", ...extra }));
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: h });
}

export const error = (status, code, message) => json(status, { error: code, message });
export const noContent = () => new Response(null, { status: 204, headers: secure() });

export class HttpError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** Reads a JSON body of at most `max` bytes. */
export async function readJSON(req, max = 128 << 10) {
  const len = Number(req.headers.get("Content-Length") ?? 0);
  if (len > max) throw new HttpError(413, "too_big", "That is too big to send.");
  const text = await req.text();
  if (enc.encode(text).length > max) throw new HttpError(413, "too_big", "That is too big to send.");
  try {
    const v = JSON.parse(text);
    if (v === null || typeof v !== "object" || Array.isArray(v)) throw new Error("not an object");
    return v;
  } catch {
    throw new HttpError(400, "bad_json", "That request wasn't understood.");
  }
}

export function randomCode(n) {
  const b = crypto.getRandomValues(new Uint8Array(n));
  return [...b].map((v) => ALPHABET[v & 31]).join("");
}

export function randomId() {
  return [...crypto.getRandomValues(new Uint8Array(16))].map((v) => v.toString(16).padStart(2, "0")).join("");
}

/** Tidies a typed code: upper case, no spaces or dashes, look-alikes fixed. */
export function normaliseCode(s) {
  return String(s ?? "").toUpperCase().replace(/[\s\-_]/g, "").replace(/[IL]/g, "1").replace(/O/g, "0");
}

export const showCode = (c) => (c.length === 10 ? `${c.slice(0, 5)}-${c.slice(5)}` : c);

const keyCache = new Map();
async function hmacKey(secret) {
  if (!keyCache.has(secret)) {
    keyCache.set(secret, crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]));
  }
  return keyCache.get(secret);
}

export async function hmac(secret, msg) {
  return new Uint8Array(await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(msg)));
}

export const hex = (bytes) => [...bytes].map((v) => v.toString(16).padStart(2, "0")).join("");

/** A short signature as text (url-safe). */
export async function sign(secret, msg, len = 16) {
  return hex(await hmac(secret, msg)).slice(0, len * 2);
}

export function same(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
