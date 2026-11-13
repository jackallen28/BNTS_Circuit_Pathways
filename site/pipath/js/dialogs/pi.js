// The "Link to my Pi" window: type the ID that's on the Pi.
import { h } from "../dom.js";
import { dialog } from "../widgets/window.js";
import { getPi, savedPiId, rememberPiId, hasClass } from "../runtime/pi.js";

/** @returns {Promise<boolean>} true when the Pi is linked and ready to run programs */
export function linkPiDialog() {
  const pi = getPi();
  const input = h("input", { class: "input", id: "pi-id", type: "text", autocomplete: "off", spellcheck: "false", maxlength: "12", placeholder: "K7M2-QX9P", "aria-label": "Your Pi's ID", autofocus: true, value: pi.code || savedPiId(), style: { width: "10em", textTransform: "uppercase" } });
  const msg = h("p", { id: "pi-msg", class: "small", role: "status" });
  const say = (text, bad = false) => { msg.textContent = text; msg.classList.toggle("bad", bad); };
  let ok = false;

  async function link() {
    const id = input.value.trim();
    if (!id) return say("Type the ID that's on your Pi first.", true);
    if (!hasClass()) return say("Join your class from the home page first (you need your class code), then come back.", true);
    say("Linking...");
    try {
      await pi.connect(id);
    } catch (e) {
      return say(e.message, true);
    }
    if (pi.state === "pi-offline") return say("That Pi isn't switched on or isn't online right now. Check its power and WiFi.", true);
    if (!pi.canRun) {
      // the Pi's app says hello a moment after the link starts
      await new Promise((r) => setTimeout(r, 600));
    }
    if (!pi.canRun) return say("This Pi is linked, but it isn't set to run programs from the website. Ask your teacher.", true);
    rememberPiId(id.toUpperCase());
    ok = true;
    say("Linked! ✓");
    d.close(true);
  }
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); link(); } });

  const body = h("div", {},
    h("p", {}, "Your Raspberry Pi has an ID. It's on the label, on the Pi's screen when it starts, or in the file ", h("b", { text: "PI-LINK-ID.txt" }), " on the Pi."),
    h("p", {}, h("label", {}, "Pi ID: ", input)),
    msg,
    h("p", { class: "small muted" }, "When you press Run, your program is sent to your Pi and runs there for real. You'll see what it prints here. The website doesn't keep your program."));
  const d = dialog({ title: "Link to my Raspberry Pi", body, buttons: [{ label: "Not now", value: false }, { label: "Link", default: true, keepOpen: true, onclick: link }] });
  return d.result.then((v) => v === true || ok);
}
