// The welcome screen: pick your name, or make a profile (first names and school, nothing else).
import { h, fill, joinNames, download } from "../dom.js";
import { api } from "../api.js";
import { dialog, messageBox } from "../widgets/window.js";

export function loginScreen(root, { onLoggedIn, onCreated }) {
  const stage = h("div", { class: "win dialog" });
  fill(root, h("main", { class: "desktop", id: "main" },
    h("div", { class: "brand" }, h("img", { src: "../img/bnts-mark.svg", alt: "" }), h("div", {}, h("h1", { text: "PiPath" }), h("small", { text: "Banyule Nillumbik Tech School" }))),
    stage,
    h("div", { class: "desk-foot" },
      h("button", { class: "link", type: "button", onclick: wipeDialog, text: "Wipe this browser" }),
      h("a", { class: "link", href: "/", style: { color: "#fff" }, text: "Circuit Pathways home" }))));

  const frame = (title, ...body) => fill(stage,
    h("div", { class: "titlebar" }, h("span", { class: "logo" }), h("span", { class: "title", text: title })), h("div", { class: "win-body" }, ...body));

  async function pickName() {
    let students = [];
    try { students = await api.students(); } catch { /* an empty list is fine */ }
    if (!students.length) return newProfile();
    frame("Welcome to PiPath",
      h("p", { text: "Who's working today?" }),
      h("div", { class: "profile-list bevel-in" }, students.map((s) => h("button", { class: "btn profile-btn", type: "button", onclick: async () => onLoggedIn(await api.login(s.id)) }, h("b", { text: joinNames(s.names) }), h("span", { class: "muted", text: s.school })))),
      h("div", { class: "dlg-buttons" }, h("button", { class: "btn default", type: "button", id: "new", text: "I'm new here", onclick: () => newProfile() })));
  }

  function newProfile(error = "") {
    const names = [h("input", { class: "input", id: "name1", autocomplete: "off", maxlength: 30, autofocus: true })];
    const list = h("div", {}, names);
    const school = h("input", { class: "input", id: "school", autocomplete: "off", maxlength: 60 });
    const msg = h("div", { class: ["note", "error"], role: "alert", hidden: !error, text: error });
    const submit = async () => {
      try {
        const me = await api.createStudent({ names: names.map((n) => n.value).filter((v) => v.trim()), school: school.value });
        onCreated(me);
      } catch (e) { msg.hidden = false; msg.textContent = e.message; }
    };
    frame("Make your profile",
      h("p", { text: "Just first names. No last names. Sharing a Pi? Add everyone's first name (up to 4)." }),
      h("div", { class: "field" }, h("label", { for: "name1", text: "Your first name" }), list),
      h("p", {}, h("button", { class: "btn small", type: "button", text: "+ Add another name", onclick: () => {
        if (names.length >= 4) return;
        const n = h("input", { class: "input", "aria-label": `First name ${names.length + 1}`, autocomplete: "off", maxlength: 30 });
        names.push(n); list.append(n); n.focus();
      } })),
      h("div", { class: "field" }, h("label", { for: "school", text: "Your school" }), school),
      msg,
      h("div", { class: "dlg-buttons" },
        h("button", { class: "btn", type: "button", text: "Back", onclick: () => pickName() }),
        h("button", { class: "btn default", type: "button", id: "next", text: "Next", onclick: submit })));
    [...names, school].forEach((i) => i.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); }));
  }

  async function wipeDialog() {
    const students = await api.students().catch(() => []);
    const confirmBox = h("input", { class: "input", id: "wipe-confirm", autocomplete: "off", "aria-label": "Type WIPE in capital letters" });
    const body = h("div", {},
      h("p", { text: students.length ? `This deletes every profile in this browser (${students.length}), with all their code and progress. Use it at the end of a program, before the next group.` : "There are no profiles in this browser. It's already clear." }),
      students.length ? h("ul", {}, students.map((s) => h("li", { text: `${joinNames(s.names)}, ${s.school}` }))) : null,
      students.length ? h("p", {}, h("button", { class: "btn", type: "button", text: "1. Save everyone's work first", onclick: async () => { const { bytes, name } = await api.exportEveryone(); download(bytes, name); } })) : null,
      students.length ? h("div", { class: "field" }, h("label", { text: "2. Type WIPE in capital letters" }), confirmBox) : null);
    const d = dialog({ title: "Wipe this browser", body, buttons: [{ label: "Cancel", value: "no" }, ...(students.length ? [{ label: "Wipe this browser", value: "wipe", keepOpen: true, onclick: async () => {
      if (confirmBox.value !== "WIPE") { confirmBox.focus(); return; }
      await api.wipe();
      d.close("wiped");
    } }] : [])] });
    if ((await d.result) === "wiped") { await messageBox({ instruction: "This browser is wiped.", text: "Every profile is gone. It's ready for the next group." }); pickName(); }
  }

  pickName();
}
