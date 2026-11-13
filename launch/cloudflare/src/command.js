// What a browser may ask a Pi to do: the same whitelist as the Go relay (internal/pirelay/command.go).
// The Pi app checks every command again.
const MODES = new Set(["out", "in", "in_up", "in_down", "pwm"]);
const PROGRAM = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}\.py$/;
const SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}$/;
const CAMERA = /^[a-z ]{0,30}$/;
const SUPPORT = new Set(["pipath_camera", "pipath_computer"]);
export const MAX_CODE = 40 << 10;
export const MAX_FILES_B64 = 40 << 10;
const enc = new TextEncoder();

const isInt = (v) => Number.isInteger(v);
const pinOK = (p) => isInt(p) && p >= 2 && p <= 27;
const textOK = (s, max) => typeof s === "string" && enc.encode(s).length <= max && !s.includes("\u0000");

/** A tidy copy of the command (only the fields its operation uses), or null if it isn't allowed. */
export function checkCommand(c) {
  if (!c || typeof c !== "object") return null;
  const out = { op: c.op };
  if (isInt(c.id) && c.id !== 0) out.id = c.id;
  switch (c.op) {
    case "all_off": case "ping": case "read":
      return out;
    case "release":
      return pinOK(c.pin) ? { ...out, pin: c.pin } : null;
    case "mode":
      return pinOK(c.pin) && MODES.has(c.mode) ? { ...out, pin: c.pin, mode: c.mode } : null;
    case "write":
      return pinOK(c.pin) && (c.value === 0 || c.value === 1) ? { ...out, pin: c.pin, value: c.value } : null;
    case "pwm": {
      const duty = c.duty ?? 0;
      const freq = c.freq ?? 0;
      if (!pinOK(c.pin) || typeof duty !== "number" || duty < 0 || duty > 1 || !isInt(freq) || freq < 0 || freq > 10000) return null;
      return { ...out, pin: c.pin, duty, ...(freq ? { freq } : {}) };
    }
    case "run": {
      if (!isInt(c.rid) || c.rid <= 0 || !PROGRAM.test(c.name ?? "")) return null;
      if (!textOK(c.code, MAX_CODE) || !c.code) return null;
      const files = c.files ?? {};
      if (typeof files !== "object" || Array.isArray(files) || Object.keys(files).length > 8) return null;
      let total = 0;
      for (const [name, data] of Object.entries(files)) {
        const segs = name.split("/");
        if (segs.length > 3 || !segs.every((s) => SEGMENT.test(s) && s !== "..") || typeof data !== "string") return null;
        total += data.length;
      }
      if (total > MAX_FILES_B64) return null;
      const support = c.support ?? [];
      if (!Array.isArray(support) || !support.every((s) => SUPPORT.has(s))) return null;
      if (!CAMERA.test(c.camera_object ?? "")) return null;
      return { ...out, rid: c.rid, name: c.name, code: c.code, ...(Object.keys(files).length ? { files } : {}), ...(support.length ? { support } : {}), ...(c.camera_object ? { camera_object: c.camera_object } : {}) };
    }
    case "stdin":
      return isInt(c.rid) && c.rid > 0 && textOK(c.text ?? "", 1000) ? { ...out, rid: c.rid, text: c.text ?? "" } : null;
    case "stop":
      return isInt(c.rid ?? 0) && (c.rid ?? 0) >= 0 ? { ...out, rid: c.rid ?? 0 } : null;
  }
  return null;
}

/** Events a Pi may send to the browser. */
export const PI_EVENTS = new Set(["hello", "state", "error", "pong", "run", "out", "exit"]);
