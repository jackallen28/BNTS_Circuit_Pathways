# Circuit Pathways

A free, no-AI coding tutor for secondary students, made by the **Banyule Nillumbik Tech School (BNTS)**.
It has two apps that run in the student's browser (Chrome or Edge):

- **PiPath**: Python for the Raspberry Pi (a Windows 95 look).
- **ArduinoPath**: Arduino and ESP boards, in blocks or C++ (a Windows Vista look).

**This repository is the one home for Circuit Pathways.** The `main` branch holds only the current product. Older and
experimental work is kept, organised, on the `drafts` branch.

## Which version is which

The same code runs as three "editions". Pick by who is using it:

| Edition | For | Class code | Where a student's work is saved | Teachers |
|---|---|---|---|---|
| **Real site** | Classes | Required | In their class (Cloudflare) or only on their device (Render) | The school's own `TEACHER_CODES` |
| **Pi beta** | Students on Raspberry Pis | **Optional** | On the Pi; **or in their class** if they join one | School codes, or a code they make up |
| **TEST** | Colleagues trying it out | Optional | Nothing kept on the computer; **or in their class** if they join one (Cloudflare) | A code they make up |

All three can be hosted on **Cloudflare** (classes saved in a database, deleted when the class ends) or **Render** (the Go
server, nothing stored). See [`docs/`](docs/README.md) for setting them up.

## Where things are

```
site/          What the browser loads. The folders match the web addresses: pipath/, arduinopath/, teacher/,
               shared/ (code both apps use), and the home page.
content/       What a teacher can edit, as data: arduinopath/ (boards, parts, projects, errors) and pipath/ (lessons).
cmd/, internal/, embed.go   The Go server (Render) and the Go tools (Pi keys, the Cloudflare export).
cloudflare/    The same site as a Cloudflare Worker: classes, the Pi relay, the compile proxy.
raspberry-pi/  Tests and README for the Pi app. (The app is site/pipath/remote/circuitpathways_pi.py.)
tests/         js/ (Node tests) and e2e/ (Playwright, in a real browser).
tools/         build_pipath_data.py (lessons to JSON) and grove_art.mjs (Grove part drawings).
docs/          The documentation: start at docs/README.md.
Dockerfile*, render*.yaml   Building and hosting on Render.
.github/workflows/          ci.yml (every test) and cloudflare-deploy.yml (the deploy button).
AGENTS.md      The rules for anyone (or any AI tool) changing the code. Read it first.
```

## The other repositories

| Repository | What it is |
|---|---|
| **BNTS_Circuit_Pathways** (this one) | The product. Everything new goes here. |
| **BNTS_PIPath** and **BNTS_ArduinoPath** | The older stand-alone apps (installed on each Pi or laptop). Copied into this repository's `drafts` branch; the original repositories can stay as they are. |
| **jackallen** | A personal catch-all (many unrelated projects). Not part of Circuit Pathways. |
| **BNTS_FidgetCAD** | A different project. |

## Branches

- **`main`**: the current work. Everything is built from here. (Set it as the default branch in Settings > Branches.)
- **`drafts`**: older and experimental work in a `draft/` folder: the first laptop app and showcase website, the offline
  PiPath and ArduinoPath, WastePath and the bin monitor. Not deployed, not tested. `draft/README.md` explains each.
- **`claude/inspiring-hamilton-mfxok0`**: a frozen copy of `main` as it was before the folders were reorganised. Anything
  still deploying from it keeps working until it is pointed at `main`. It can be deleted afterwards.
- **`BNTS_CircuitPath`**, **`BNTS_PiPath`**: the two original branches, kept as they were (they share no history with
  `main`; the same work is now on `drafts`).

## Try it

```bash
go run ./cmd/launch -dev                 # http://localhost:8080  (teacher code: teacher-code-dev)
go run ./cmd/launch -dev -beta           # the TEST edition (make up your own teacher code)
npm ci && npm test                       # the JavaScript tests
go test ./...                            # the Go tests
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # the browser tests
```

The full list of commands, and what must pass before a change is committed, is in [`AGENTS.md`](AGENTS.md).

## The rules that never change

No AI anywhere. No accounts, cookies, analytics or CDN files. Only a first name (or names) and a school are ever asked
for. Student-facing text is plain English at about a Year 7 reading level, in Australian spelling. See
[`AGENTS.md`](AGENTS.md) for the full list.
