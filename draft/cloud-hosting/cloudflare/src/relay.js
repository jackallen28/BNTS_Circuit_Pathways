// The Pi relay on Cloudflare: one Durable Object per Raspberry Pi, holding a WebSocket to the Pi and
// one to the browser that is controlling it. Hibernating WebSockets keep it free while nothing is
// happening. It keeps nothing about students and stores nothing permanently except the Pi's label.
import { DurableObject } from "cloudflare:workers";
import { checkCommand, PI_EVENTS } from "./command.js";

const MAX_EVENT = 16 << 10;
const CLEAN_NAME = (s) => (String(s ?? "").replace(/[^a-zA-Z0-9 -]/g, "").slice(0, 24).trim() || "Raspberry Pi");

export class PiHub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    // keep-alives are answered without waking the object
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
    this.recent = [];
  }

  sockets(tag) {
    return this.ctx.getWebSockets(tag);
  }

  /**
   * The Pi's live connection: the newest one that is open. After a Pi reconnects, its old connection can still be
   * listed while it closes; a command sent to that one is lost, so never use "the first one".
   */
  livePi() {
    const open = this.sockets("pi").filter((s) => (s.readyState ?? 1) === 1);
    return open[open.length - 1] ?? null;
  }

  toBrowsers(ev) {
    const text = typeof ev === "string" ? ev : JSON.stringify(ev);
    for (const ws of this.sockets("browser")) {
      try { ws.send(text); } catch { /* it has gone */ }
    }
  }

  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/command") {
      const pi = this.livePi();
      if (!pi) return Response.json({ error: "pi_not_found", message: "That Pi isn't connected. Check the ID on your Pi, and that it is switched on." }, { status: 404 });
      const now = Date.now();
      this.recent = this.recent.filter((t) => now - t < 1000);
      if (this.recent.length >= 30) return Response.json({ error: "pi_busy", message: "The Pi can't keep up. Slow down a little." }, { status: 429 });
      this.recent.push(now);
      const cmd = checkCommand(await req.json());
      if (!cmd) return Response.json({ error: "bad_command", message: "That isn't something a Pi can do." }, { status: 400 });
      pi.send(JSON.stringify(cmd));
      return new Response(null, { status: 204 });
    }
    if (req.headers.get("Upgrade") !== "websocket") return new Response("expected a WebSocket", { status: 426 });
    const role = req.headers.get("X-Role");
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    if (role === "pi") {
      for (const old of this.sockets("pi")) old.close(4000, "replaced by a newer connection");
      this.ctx.acceptWebSocket(server, ["pi"]);
      this.toBrowsers({ type: "pi-online" });
      return new Response(null, { status: 101, webSocket: client });
    }
    // a browser: the newest one takes over
    for (const old of this.sockets("browser")) {
      try { old.send(JSON.stringify({ type: "closed", data: { reason: "Someone else connected to this Pi." } })); } catch { /* gone */ }
      old.close(4001, "replaced");
    }
    this.ctx.acceptWebSocket(server, ["browser"]);
    const saved = (await this.ctx.storage.get(["name", "hello"])) ?? new Map();
    const live = this.livePi();
    const online = Boolean(live);
    server.send(JSON.stringify({ type: "connected", data: { name: saved.get("name") ?? "Raspberry Pi", pi_online: online } }));
    if (online && saved.get("hello")) server.send(saved.get("hello"));
    const state = live?.deserializeAttachment()?.state;
    if (online && state) server.send(state);
    return new Response(null, { status: 101, webSocket: client, headers: { "Sec-WebSocket-Protocol": "cp-access" } });
  }

  async webSocketMessage(ws, msg) {
    const [tag] = this.ctx.getTags(ws);
    if (tag !== "pi" || typeof msg !== "string" || msg.length > MAX_EVENT) return;
    let ev;
    try { ev = JSON.parse(msg); } catch { return; }
    if (!ev || !PI_EVENTS.has(ev.type) || ev.data === undefined) return;
    const text = JSON.stringify({ type: ev.type, data: ev.data });
    if (ev.type === "hello") {
      await this.ctx.storage.put({ hello: text, name: CLEAN_NAME(ev.data?.name) });
    } else if (ev.type === "state") {
      ws.serializeAttachment({ state: text }); // the latest pins, for a browser that connects later (no storage write)
    }
    this.toBrowsers(text);
  }

  async webSocketClose(ws) {
    const [tag] = this.ctx.getTags(ws);
    if (tag === "pi" && !this.sockets("pi").some((s) => s !== ws && (s.readyState ?? 1) === 1)) this.toBrowsers({ type: "pi-offline" });
  }

  async webSocketError(ws) {
    await this.webSocketClose(ws);
  }
}
