// Who is asking: a teacher (signed in with one of the TEACHER_CODES), or a student in a class.
// Tokens are signed with CLASS_SECRET, so the Worker can check them without a lookup.
import { sign, same, HttpError } from "./util.js";

export const TEACHER_HOURS = 12;

/** TEACHER_CODES: codes of at least 8 characters, separated by commas. Each teacher has their own. */
export function teacherCodes(env) {
  return String(env.TEACHER_CODES ?? "").split(/[,\n]/).map((s) => s.trim()).filter((s) => s.length >= 8);
}

export function secret(env) {
  const s = env.CLASS_SECRET ?? "";
  if (s.length < 16) throw new HttpError(503, "not_set_up", "This site isn't set up yet (CLASS_SECRET is missing).");
  return s;
}

/** A teacher's identity: a fingerprint of their code (the code itself is never stored). */
export const teacherId = async (env, code) => sign(secret(env), `teacher:${code}`, 12);

export async function signIn(env, code, now) {
  const typed = String(code ?? "").trim();
  for (const c of teacherCodes(env)) {
    if (same(c, typed)) {
      const id = await teacherId(env, c);
      const exp = now + TEACHER_HOURS * 3600 * 1000;
      const body = `t2.${id}.${exp}`;
      return { token: `${body}.${await sign(secret(env), body)}`, expires_at: exp };
    }
  }
  return null;
}

/** The teacher's id from a token, or null. */
export async function teacherFrom(env, token, now) {
  const m = /^t2\.([0-9a-f]{24})\.(\d{10,15})\.([0-9a-f]{32})$/.exec(String(token ?? ""));
  if (!m || Number(m[2]) < now) return null;
  return same(await sign(secret(env), `t2.${m[1]}.${m[2]}`), m[3]) ? m[1] : null;
}

export async function studentToken(env, id) {
  return `s2.${id}.${await sign(secret(env), `s2.${id}`)}`;
}

/** The student id from a token (still to be looked up in the class list), or null. */
export async function studentFrom(env, token) {
  const m = /^s2\.([0-9a-f]{32})\.([0-9a-f]{32})$/.exec(String(token ?? ""));
  if (!m) return null;
  return same(await sign(secret(env), `s2.${m[1]}`), m[2]) ? m[1] : null;
}

export const bearer = (req) => (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "") || req.headers.get("X-Access") || "";
