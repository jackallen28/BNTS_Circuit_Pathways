// Raspberry Pi keys, checked exactly as the Go server checks them (internal/pilink), so the same
// installers and keys work on either. A key looks like CPK1-K7M2QX9P-AB12CD34EF.
import { ALPHABET, hmac, same } from "./util.js";

export function normaliseId(s) {
  return String(s ?? "").toUpperCase().replace(/[\s\-_\t]/g, "").replace(/[IL]/g, "1").replace(/O/g, "0");
}

async function mac(secret, id) {
  const sum = await hmac(secret, `pikey1:${id}`);
  let out = "";
  for (let i = 0; i < 10; i++) {
    const bit = i * 5;
    const v = (sum[bit >> 3] << 8) | sum[(bit >> 3) + 1];
    out += ALPHABET[(v >> (11 - (bit % 8))) & 31];
  }
  return out;
}

/** The Pi's ID if the key is real and not revoked, else null. */
export async function verifyPiKey(env, key) {
  const secret = env.PI_KEY_SECRET ?? "";
  if (secret.length < 16) return null;
  const parts = String(key ?? "").trim().toUpperCase().split("-");
  if (parts.length !== 3 || parts[0] !== "CPK1" || parts[1].length !== 8 || parts[2].length !== 10) return null;
  const id = parts[1];
  if (![...id].every((c) => ALPHABET.includes(c))) return null;
  const revoked = new Set(String(env.REVOKED_PI_IDS ?? "").split(/[,\s]+/).map(normaliseId).filter(Boolean));
  if (revoked.has(id)) return null;
  return same(await mac(secret, id), parts[2]) ? id : null;
}

export const keyFor = async (secret, id) => `CPK1-${id}-${await mac(secret, id)}`;
