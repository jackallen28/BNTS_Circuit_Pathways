// Circuit Pathways on Cloudflare. Static files (the whole site) are served straight from Workers
// static assets with the headers in _headers. This Worker answers the API: teacher sign-in, saved
// classes (D1), students' synced work, the Raspberry Pi relay (a Durable Object per Pi), and sends
// compiles on to a separate compiler (the Docker image) when COMPILE_URL is set.
import { json, error, noContent, readJSON, secure, HttpError } from "./util.js";
import { classRoutes, studentOf, cleanUp } from "./classes.js";
import { teacherFrom, bearer } from "./auth.js";
import { verifyPiKey, normaliseId } from "./pikeys.js";
import { checkCommand } from "./command.js";

export { PiHub } from "./relay.js";

const PLACEHOLDER_SERVER = "https://circuit-pathways.onrender.com";
const BETA_HIDDEN = [/^\/teacher(\/|$)/, /^\/api\/teacher\//, /^\/api\/class\//, /^\/api\/student\//, /^\/api\/pi\//, /^\/pipath\/remote\/?(index\.html|circuitpathways_pi\.py|install\.sh)?$/];

const isBeta = (env) => env.BETA === "1" || env.BETA === "true";
// The Pi beta: students use the site on a Raspberry Pi. A class code is optional. Without one, work is
// saved on that device only and the apps use the access word "local"; with one, work also syncs to the class.
const isPiBeta = (env) => !isBeta(env) && (env.PI_BETA === "1" || env.PI_BETA === "true");

/** Who may use the compiler and the Pi relay: a student in a class that's running, or a teacher. */
async function accessOK(env, token, now) {
  if (isBeta(env) && token === "beta") return true;
  if (isPiBeta(env) && token === "local") return true; // no class: saved on the device, still rate limited
  if (await teacherFrom(env, token, now)) return true;
  return Boolean(await studentOf(env, token, now));
}

function limiter(req, env) {
  const ip = req.headers.get("CF-Connecting-IP") ?? "local";
  return async (what) => {
    const rl = env[`LIMIT_${what.toUpperCase()}`];
    if (!rl) return;
    const { success } = await rl.limit({ key: `${what}:${ip}` });
    if (!success) throw new HttpError(429, "slow_down", "That's a lot of tries. Wait a minute and try again.");
  };
}

async function piApp(req, env, url, file) {
  const res = await env.ASSETS.fetch(new Request(new URL(`/pipath/remote/${file}`, url), req));
  if (!res.ok) return res;
  const text = (await res.text()).replaceAll(PLACEHOLDER_SERVER, url.origin);
  const h = secure(new Headers({ "Content-Type": file.endsWith(".py") ? "text/x-python; charset=utf-8" : "text/x-shellscript; charset=utf-8", "Cache-Control": "no-cache" }));
  if (file.endsWith(".py")) h.set("Content-Disposition", 'attachment; filename="circuitpathways_pi.py"');
  return new Response(text, { headers: h });
}

async function compile(req, env, now) {
  if (!(await accessOK(env, req.headers.get("X-Access"), now))) return error(401, "no_class", "Join a class with your class code to upload to a board.");
  if (!env.COMPILE_URL) return error(503, "no_tools", "Compiling for real boards is switched off on this site. The simulator still works.");
  const body = await req.text();
  if (body.length > 128 << 10) return error(413, "too_big", "That sketch is too big to send.");
  const res = await fetch(new URL("/api/compile", env.COMPILE_URL), {
    method: "POST", body,
    headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", "X-Compile-Key": env.COMPILE_KEY ?? "" },
  }).catch(() => null);
  if (!res) return error(503, "no_tools", "The compiler can't be reached right now. The simulator still works.");
  return new Response(res.body, { status: res.status, headers: secure(new Headers({ "Content-Type": res.headers.get("Content-Type") ?? "application/json" })) });
}

async function piRoutes(req, env, url, now, limit) {
  const p = url.pathname;
  const hub = (id) => env.PIHUB.get(env.PIHUB.idFromName(normaliseId(id)));

  if (p === "/api/pi/pi/ws") {
    const id = await verifyPiKey(env, req.headers.get("X-Pi-Key"));
    if (!env.PI_KEY_SECRET) return error(503, "no_pi", "Pi Link is switched off on this site.");
    if (!id) return error(403, "pi_key", "That Pi key isn't valid.");
    const fwd = new Request(req);
    fwd.headers.set("X-Role", "pi");
    return hub(id).fetch(fwd);
  }
  if (p === "/api/pi/ws") {
    // a browser can't set headers on a WebSocket, so it sends its access in the protocol list: ["cp-access", token]
    const protos = (req.headers.get("Sec-WebSocket-Protocol") ?? "").split(",").map((s) => s.trim());
    const token = protos[0] === "cp-access" ? protos[1] : "";
    if (!(await accessOK(env, token, now))) return error(401, "no_class", "Join a class with your class code to connect to a Pi.");
    await limit("join");
    const fwd = new Request(new URL("/browser", url), req);
    fwd.headers.set("X-Role", "browser");
    return hub(url.searchParams.get("code") ?? "").fetch(fwd);
  }
  if (p === "/api/pi/command" && req.method === "POST") {
    if (!(await accessOK(env, req.headers.get("X-Access"), now))) return error(401, "no_class", "Join a class with your class code to connect to a Pi.");
    const body = await readJSON(req);
    const cmd = checkCommand(body.cmd);
    if (!cmd) return error(400, "bad_command", "That isn't something a Pi can do.");
    const res = await hub(body.code ?? "").fetch(new Request(new URL("/command", url), { method: "POST", body: JSON.stringify(cmd) }));
    return res.status === 204 ? noContent() : new Response(res.body, { status: res.status, headers: secure(new Headers({ "Content-Type": "application/json" })) });
  }
  return error(404, "use_websocket", "This site links Pis with WebSockets. Update the Pi app (run its installer again).");
}

async function handle(req, env) {
  const url = new URL(req.url);
  const p = url.pathname;
  const now = Date.now();
  const beta = isBeta(env);
  if (beta && BETA_HIDDEN.some((re) => re.test(p))) return error(404, "not_found", "There's nothing here.");
  if (p === "/pipath/remote/circuitpathways_pi.py" || p === "/pipath/remote/install.sh") return piApp(req, env, url, p.split("/").pop());
  if (!p.startsWith("/api/")) return env.ASSETS.fetch(req);

  // writes must come from our own pages
  if (req.method !== "GET" && req.method !== "HEAD" && req.headers.get("X-Circuit-Pathways") !== "1" && !(p.startsWith("/api/pi/") && req.headers.get("Upgrade") === "websocket")) {
    return error(403, "bad_request", "That request didn't come from the Circuit Pathways page.");
  }
  const limit = limiter(req, env);
  if (p === "/healthz" || p === "/api/healthz") return new Response("ok\n");
  if (p === "/api/info") {
    return json(200, {
      app: "Circuit Pathways", version: env.VERSION ?? "cloudflare", compile: Boolean(env.COMPILE_URL), beta,
      edition: beta ? "test" : isPiBeta(env) ? "pi-beta" : "", class_optional: isPiBeta(env),
      classes: !beta, relay: env.PI_KEY_SECRET ? "ws" : "off", commit: String(env.CF_VERSION_METADATA?.id ?? "").slice(0, 8),
    });
  }
  if (p === "/api/compile" && req.method === "POST") {
    await limit("compile");
    return compile(req, env, now);
  }
  if (p.startsWith("/api/pi/")) return piRoutes(req, env, url, now, limit);
  const res = await classRoutes(req, env, url, now, limit);
  return res ?? error(404, "not_found", "There's nothing here.");
}

export default {
  async fetch(req, env) {
    try {
      return await handle(req, env);
    } catch (e) {
      if (e instanceof HttpError) return error(e.status, e.code, e.message);
      console.error("unexpected error", e?.message); // never the request body: it can hold names
      return error(500, "oops", "Something went wrong. Try again.");
    }
  },

  // every day: delete classes that have ended, with their students and work
  async scheduled(_event, env) {
    await cleanUp(env, Date.now());
  },
};
