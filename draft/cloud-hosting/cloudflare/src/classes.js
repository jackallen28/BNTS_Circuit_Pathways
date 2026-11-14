// Classes, the students in them, and their work, in D1. Only a student's first name(s) and school
// are kept about them. A class ends on the date the teacher picks (at most about a year away), and
// the daily clean-up deletes it with everyone and everything in it. Teachers can delete sooner.
import { cleanNames, cleanSchool, ValidationError } from "../../site/shared/local/validate.js";
import { json, error, noContent, readJSON, randomCode, randomId, normaliseCode, showCode, HttpError, isBetaEdition } from "./util.js";
import { signIn, teacherFrom, studentFrom, studentToken, bearer } from "./auth.js";

export const MAX_DAYS = 400;
const DAY = 24 * 3600 * 1000;
const APPS = new Set(["arduinopath", "pipath"]);
const KINDS = { sketch: 100 << 10, progress: 64 << 10, settings: 8 << 10 };
const ITEM = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const MAX_ITEMS_PER_STUDENT = 300;
const MAX_STUDENTS_PER_CLASS = 200;
const MAX_CLASSES_PER_TEACHER = 60;
const enc = new TextEncoder();

function clean(fn) {
  try {
    return fn();
  } catch (e) {
    if (e instanceof ValidationError) throw new HttpError(400, e.code, e.message);
    throw e;
  }
}

/** A class label: letters, numbers and simple punctuation, up to 40 characters. Not for names. */
function cleanLabel(s) {
  s = String(s ?? "").trim().replace(/\s+/g, " ");
  if (!s) return "My class";
  if ([...s].length > 40 || !/^[\p{L}\p{Nd} .,'’&()/#:-]+$/u.test(s)) throw new HttpError(400, "bad_name", "A class name can have letters, numbers and simple punctuation (up to 40). Don't put students' names in it.");
  return s;
}

const classOut = (c, students) => ({
  code: showCode(c.code), name: c.name, school: c.school, created_at: c.created_at, ends_at: c.ends_at, expires_at: c.ends_at,
  ...(students === undefined ? {} : { students }),
});

async function needTeacher(req, env, now) {
  const t = await teacherFrom(env, bearer(req), now);
  if (!t) throw new HttpError(401, "no_teacher", "Please sign in as a teacher again.");
  return t;
}

async function teachersClass(env, teacher, code) {
  const c = await env.DB.prepare("SELECT * FROM classes WHERE code = ? AND teacher = ?").bind(normaliseCode(code), teacher).first();
  if (!c) throw new HttpError(404, "no_class", "That class isn't one of yours (or it has ended).");
  return c;
}

/** The student (and their class) for a student token, if the class is still running. */
export async function studentOf(env, token, now) {
  const id = await studentFrom(env, token);
  if (!id) return null;
  const row = await env.DB.prepare(
    "SELECT s.id, s.names, s.school, s.class_code, c.name AS class_name, c.school AS class_school, c.ends_at FROM students s JOIN classes c ON c.code = s.class_code WHERE s.id = ? AND c.ends_at > ?",
  ).bind(id, now).first();
  return row ? { ...row, names: JSON.parse(row.names) } : null;
}

/** Deletes classes that have ended, with their students and work. Run by the daily cron. */
export async function cleanUp(env, now) {
  const ended = (await env.DB.prepare("SELECT code FROM classes WHERE ends_at <= ?").bind(now).all()).results.map((r) => r.code);
  for (const code of ended) await deleteClass(env, code);
  return ended.length;
}

async function deleteClass(env, code) {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM work WHERE student_id IN (SELECT id FROM students WHERE class_code = ?)").bind(code),
    env.DB.prepare("DELETE FROM students WHERE class_code = ?").bind(code),
    env.DB.prepare("DELETE FROM classes WHERE code = ?").bind(code),
  ]);
}

async function deleteStudent(env, id) {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM work WHERE student_id = ?").bind(id),
    env.DB.prepare("DELETE FROM students WHERE id = ?").bind(id),
  ]);
}

function endsAt(body, now) {
  let ends;
  if (body.ends_at !== undefined) ends = Number(body.ends_at);
  else {
    const days = Number(body.days ?? 30);
    if (!Number.isInteger(days) || days < 1 || days > MAX_DAYS) throw new HttpError(400, "bad_days", `A class can last 1 to ${MAX_DAYS} days.`);
    ends = now + days * DAY;
  }
  if (!Number.isFinite(ends) || ends <= now || ends > now + MAX_DAYS * DAY) throw new HttpError(400, "bad_days", `Pick an end date within ${MAX_DAYS} days.`);
  return Math.round(ends);
}

/** Routes under /api/teacher, /api/class and /api/student. Returns null if the path isn't one of them. */
export async function classRoutes(req, env, url, now, limit) {
  const p = url.pathname;
  const m = req.method;

  if (p === "/api/teacher/signin" && m === "POST") {
    await limit("signin");
    const body = await readJSON(req);
    const res = await signIn(env, body.code, now, isBetaEdition(env));
    if (!res) {
      await new Promise((r) => setTimeout(r, 400));
      return error(401, "bad_code", "That teacher code isn't right.");
    }
    return json(200, res);
  }

  if (p === "/api/teacher/classes" && m === "GET") {
    const t = await needTeacher(req, env, now);
    const rows = (await env.DB.prepare(
      "SELECT c.*, (SELECT count(*) FROM students s WHERE s.class_code = c.code) AS n FROM classes c WHERE c.teacher = ? AND c.ends_at > ? ORDER BY c.created_at DESC",
    ).bind(t, now).all()).results;
    return json(200, { classes: rows.map((c) => classOut(c, c.n)) });
  }

  if (p === "/api/teacher/class" && m === "POST") {
    const t = await needTeacher(req, env, now);
    await limit("class");
    const body = await readJSON(req);
    const name = cleanLabel(body.name);
    const school = clean(() => cleanSchool(body.school ?? env.DEFAULT_SCHOOL ?? "Banyule Nillumbik Tech School"));
    const ends = endsAt(body, now);
    const count = (await env.DB.prepare("SELECT count(*) AS n FROM classes WHERE teacher = ? AND ends_at > ?").bind(t, now).first()).n;
    if (count >= MAX_CLASSES_PER_TEACHER) throw new HttpError(429, "too_many", "You have a lot of classes running. Delete one you don't need first.");
    let code;
    for (let i = 0; i < 5; i++) {
      code = randomCode(10);
      const r = await env.DB.prepare("INSERT OR IGNORE INTO classes (code, teacher, name, school, created_at, ends_at) VALUES (?, ?, ?, ?, ?, ?)").bind(code, t, name, school, now, ends).run();
      if (r.meta.changes === 1) break;
      code = null;
    }
    if (!code) throw new HttpError(503, "busy", "Try again.");
    return json(200, classOut({ code, name, school, created_at: now, ends_at: ends }, 0));
  }

  const cm = /^\/api\/teacher\/class\/([0-9A-Za-z-]{10,12})(\/.*)?$/.exec(p);
  if (cm) {
    const t = await needTeacher(req, env, now);
    const c = await teachersClass(env, t, cm[1]);
    const rest = cm[2] ?? "";
    if (rest === "" && m === "GET") {
      const rows = (await env.DB.prepare(
        "SELECT s.id, s.names, s.school, s.joined_at, s.seen_at, (SELECT count(*) FROM work w WHERE w.student_id = s.id) AS items, (SELECT max(updated_at) FROM work w WHERE w.student_id = s.id) AS last_work FROM students s WHERE s.class_code = ? ORDER BY s.joined_at",
      ).bind(c.code).all()).results;
      return json(200, { class: classOut(c), students: rows.map((r) => ({ ...r, names: JSON.parse(r.names) })) });
    }
    if (rest === "/work" && m === "GET") {
      const rows = (await env.DB.prepare(
        "SELECT s.id, s.names, s.school, w.app, w.item, w.kind, w.body, w.updated_at FROM students s LEFT JOIN work w ON w.student_id = s.id WHERE s.class_code = ? ORDER BY s.joined_at",
      ).bind(c.code).all()).results;
      const by = new Map();
      for (const r of rows) {
        if (!by.has(r.id)) by.set(r.id, { id: r.id, names: JSON.parse(r.names), school: r.school, work: [] });
        if (r.app) by.get(r.id).work.push({ app: r.app, item: r.item, kind: r.kind, body: r.body, updated_at: r.updated_at });
      }
      return json(200, { class: classOut(c), students: [...by.values()] });
    }
    if (rest === "/end" && m === "POST") {
      const ends = endsAt(await readJSON(req), now);
      await env.DB.prepare("UPDATE classes SET ends_at = ? WHERE code = ?").bind(ends, c.code).run();
      return json(200, classOut({ ...c, ends_at: ends }));
    }
    if (rest === "" && m === "DELETE") {
      await deleteClass(env, c.code);
      return noContent();
    }
    const sm = /^\/students\/([0-9a-f]{32})$/.exec(rest);
    if (sm && m === "DELETE") {
      await env.DB.prepare("DELETE FROM work WHERE student_id = (SELECT id FROM students WHERE id = ? AND class_code = ?)").bind(sm[1], c.code).run();
      await env.DB.prepare("DELETE FROM students WHERE id = ? AND class_code = ?").bind(sm[1], c.code).run();
      return noContent();
    }
    return error(404, "not_found", "There's nothing here.");
  }

  if (p === "/api/class/join" && m === "POST") {
    await limit("join");
    const body = await readJSON(req);
    const code = normaliseCode(body.code);
    const c = code.length === 10 ? await env.DB.prepare("SELECT * FROM classes WHERE code = ? AND ends_at > ?").bind(code, now).first() : null;
    if (!c) {
      await new Promise((r) => setTimeout(r, 300));
      return error(404, "no_class", "That class code isn't right, or the class has ended. Check it with your teacher.");
    }
    if (body.names === undefined) return json(200, { needs_names: true, class: classOut(c), expires_at: c.ends_at });
    const names = clean(() => cleanNames(body.names));
    const school = clean(() => cleanSchool(body.school || c.school));
    const n = (await env.DB.prepare("SELECT count(*) AS n FROM students WHERE class_code = ?").bind(c.code).first()).n;
    if (n >= MAX_STUDENTS_PER_CLASS) throw new HttpError(409, "class_full", "This class is full. Ask your teacher.");
    const id = randomId();
    await env.DB.prepare("INSERT INTO students (id, class_code, names, school, joined_at, seen_at) VALUES (?, ?, ?, ?, ?, ?)").bind(id, c.code, JSON.stringify(names), school, now, now).run();
    return json(200, { token: await studentToken(env, id), expires_at: c.ends_at, class: classOut(c), student: { names, school } });
  }

  if (p.startsWith("/api/student/")) {
    const st = await studentOf(env, bearer(req), now);
    if (!st) return error(401, "no_class", "Your class has ended, or you've been taken off it. Join again with a class code.");
    const me = () => ({ class: { code: showCode(st.class_code), name: st.class_name, school: st.class_school, ends_at: st.ends_at }, student: { names: st.names, school: st.school } });

    if (p === "/api/student/me" && m === "GET") {
      await env.DB.prepare("UPDATE students SET seen_at = ? WHERE id = ?").bind(now, st.id).run();
      return json(200, me());
    }
    if (p === "/api/student/me" && m === "DELETE") {
      await deleteStudent(env, st.id);
      return noContent();
    }
    if (p === "/api/student/work" && m === "GET") {
      const rows = (await env.DB.prepare("SELECT app, item, kind, body, updated_at FROM work WHERE student_id = ?").bind(st.id).all()).results;
      return json(200, { ...me(), work: rows });
    }
    if (p === "/api/student/work" && m === "POST") {
      await limit("work");
      const body = await readJSON(req, 512 << 10);
      const items = body.items;
      if (!Array.isArray(items) || items.length === 0 || items.length > 25) throw new HttpError(400, "bad_items", "Send 1 to 25 pieces of work at a time.");
      const stmts = [];
      for (const it of items) {
        if (!it || !APPS.has(it.app) || !ITEM.test(it.item ?? "") || !(it.kind in KINDS) || typeof it.body !== "string") throw new HttpError(400, "bad_item", "That work couldn't be saved.");
        if (enc.encode(it.body).length > KINDS[it.kind]) throw new HttpError(413, "too_big", "That work is too big to save.");
        const at = Number.isFinite(it.updated_at) ? Math.min(Math.round(it.updated_at), now) : now;
        // newer work wins: an old copy from another device never replaces newer work
        stmts.push(env.DB.prepare(
          "INSERT INTO work (student_id, app, item, kind, body, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (student_id, app, item, kind) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at WHERE excluded.updated_at >= work.updated_at",
        ).bind(st.id, it.app, it.item, it.kind, it.body, at));
      }
      const count = (await env.DB.prepare("SELECT count(*) AS n FROM work WHERE student_id = ?").bind(st.id).first()).n;
      if (count + items.length > MAX_ITEMS_PER_STUDENT) throw new HttpError(409, "too_much", "You've saved a lot of work in this class. Ask your teacher to tidy it up.");
      stmts.push(env.DB.prepare("UPDATE students SET seen_at = ? WHERE id = ?").bind(now, st.id));
      await env.DB.batch(stmts);
      return json(200, { saved: items.length, at: now });
    }
    return error(404, "not_found", "There's nothing here.");
  }

  return null;
}
