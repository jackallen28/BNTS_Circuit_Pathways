// Makes Pi keys the way the server does, using the dev Pi key secret, so the
// tests can start the real Pi app with a real key.
import { createHmac, randomBytes } from "node:crypto";

export const DEV_PI_KEY_SECRET = "dev-pi-key-secret-do-not-use-in-production";
const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function mac(id) {
  const sum = createHmac("sha256", DEV_PI_KEY_SECRET).update(`pikey1:${id}`).digest();
  let out = "";
  for (let i = 0; i < 10; i++) {
    const bit = i * 5;
    const v = (sum[bit >> 3] << 8) | sum[(bit >> 3) + 1];
    out += ALPHABET[(v >> (11 - (bit % 8))) & 31];
  }
  return out;
}

/** @returns {{ id: string, display: string, key: string }} */
export function newPiKey() {
  const id = [...randomBytes(8)].map((b) => ALPHABET[b & 31]).join("");
  return { id, display: `${id.slice(0, 4)}-${id.slice(4)}`, key: `CPK1-${id}-${mac(id)}` };
}
