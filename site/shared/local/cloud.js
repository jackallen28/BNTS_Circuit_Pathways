// Class sync: on the Cloudflare site, a student who joined a class with a class code has their work
// (code, progress and settings) copied to their class, so the teacher sees it all in one place and the
// student can carry on on another device (a Raspberry Pi, say). Only work goes up: the student's first
// names and school were given when they joined. Work still saves in this browser first; syncing is extra.

import { getAccess } from "../access.js";

const BATCH = 25;

/** The class link in this browser (from joining a class), or null. */
export function classLink() {
  const a = getAccess();
  return a?.kind === "student" ? { token: a.value, names: a.names ?? [], school: a.school ?? "", class: a.class ?? null } : null;
}

export const validLink = (t) => typeof t === "string" && /^s2\.[0-9a-f]{32}\.[0-9a-f]{32}$/.test(t);

/**
 * @param {{ link?: () => object|null, fetchImpl?: typeof fetch, delay?: number }} [o]
 */
export function createCloud({ link = classLink, fetchImpl = (...a) => fetch(...a), delay = 1500 } = {}) {
  const pending = new Map(); // token -> Map(key -> item)
  const listeners = new Set();
  let timer = 0;
  let state = "idle"; // idle | saving | saved | offline | ended

  const say = (s) => { state = s; for (const f of listeners) f(s); };

  async function send(token, items) {
    const res = await fetchImpl("/api/student/work", {
      method: "POST", credentials: "omit",
      headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ items }),
    });
    if (res.status === 401) return "ended";
    if (!res.ok) throw new Error(`status ${res.status}`);
    return "saved";
  }

  async function flush() {
    clearTimeout(timer);
    timer = 0;
    if (!pending.size) return state;
    say("saving");
    for (const [token, items] of [...pending]) {
      pending.delete(token);
      const list = [...items.values()];
      try {
        for (let i = 0; i < list.length; i += BATCH) {
          if ((await send(token, list.slice(i, i + BATCH))) === "ended") { say("ended"); cloud.onEnded?.(token); return state; }
        }
      } catch {
        // offline: keep it for the next try
        const again = pending.get(token) ?? new Map();
        for (const it of list) if (!again.has(key(it))) again.set(key(it), it);
        pending.set(token, again);
        say("offline");
        timer = setTimeout(flush, 15000);
        return state;
      }
    }
    say("saved");
    return state;
  }

  const key = (it) => `${it.app}/${it.item}/${it.kind}`;

  const cloud = {
    link,
    get state() { return state; },
    onStatus(f) { listeners.add(f); return () => listeners.delete(f); },
    onEnded: null,
    /** Queues a piece of work for the class; it goes up a moment later (newest copy wins). */
    queue(token, item) {
      if (!validLink(token)) return;
      if (!pending.has(token)) pending.set(token, new Map());
      pending.get(token).set(key(item), item);
      clearTimeout(timer);
      timer = setTimeout(flush, delay);
    },
    flush,
    /** The work saved in the class for this student, or null if the class has ended. */
    async pull(token) {
      if (!validLink(token)) return null;
      const res = await fetchImpl("/api/student/work", { credentials: "omit", headers: { Authorization: `Bearer ${token}` } });
      if (res.status === 401) return null;
      if (!res.ok) throw new Error(`status ${res.status}`);
      return (await res.json()).work ?? [];
    },
  };
  if (typeof addEventListener === "function") {
    addEventListener("pagehide", () => { flush(); });
  }
  return cloud;
}
