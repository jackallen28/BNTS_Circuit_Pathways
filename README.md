# Circuit Pathways

A free, no-AI coding tutor for secondary students, made by the **Banyule Nillumbik Tech School (BNTS)**.
It has two apps that run in the student's browser (Chrome or Edge):

- **PiPath**: Python for the Raspberry Pi (a Windows 95 look).
- **ArduinoPath**: Arduino and ESP boards, in blocks or C++ (a Windows Vista look).

**This repository is the one home for the website and everything around it.** If you have lost track of the
other repositories and branches, the map is below.

## Which version is which

The same code runs as three "editions". Pick by who is using it:

| Edition | For | Class code | Where a student's work is saved | Teachers |
|---|---|---|---|---|
| **Real site** | Classes | Required | In their class (Cloudflare) or only on their device (Render) | The school's own `TEACHER_CODES` |
| **Pi beta** | Students on Raspberry Pis | **Optional** | On the Pi; **or in their class** if they join one | School codes, or a code they make up |
| **TEST** | Colleagues trying it out | Optional | Nothing kept on the computer; **or in their class** if they join one (Cloudflare) | A code they make up |

All three can be hosted on **Cloudflare** (classes saved in a database, deleted when the class ends) or
**Render** (the Go server, nothing stored). Setting them up: [`launch/cloudflare/README.md`](launch/cloudflare/README.md)
(Cloudflare, with `npm run deploy`, `deploy:pi`, `deploy:test`) and [`launch/LAUNCH.md`](launch/LAUNCH.md) (Render, the
Raspberry Pis, the privacy notice).

## Where things are in this repository

```
launch/               THE PRODUCT. The website: the home page, PiPath, ArduinoPath, the teacher page, the Go server,
                      the Cloudflare Worker (launch/cloudflare/), the Raspberry Pi app and installer. Work here.
development/          The earlier "install an app on each laptop" version of ArduinoPath, and the showcase site. Parked.
AGENTS.md             The rules for anyone (or any AI tool) changing the code. Read it first.
render*.yaml          Render settings (real, paid, TEST).
.github/workflows/    CI (launch.yml), and the Cloudflare deploy button (cloudflare-deploy.yml).
```

Start with [`launch/docs/PROJECT-OVERVIEW.md`](launch/docs/PROJECT-OVERVIEW.md): what it is, how it is built, how to test it.

## The other repositories (and what they are)

| Repository | What it is | Use it for |
|---|---|---|
| **BNTS_Circuit_Pathways** (this one) | The website and the Pi beta, and the Cloudflare version | **Everything new** |
| **BNTS_PIPath** | The older stand-alone PiPath for the Raspberry Pi (Python, installed on each Pi), with the WastePath work | Offline Pi use; WastePath |
| **BNTS_ArduinoPath** | The older stand-alone ArduinoPath (Windows, Mac and Pi app), with the bin-monitor work | Offline laptop use; bin monitor |
| **jackallen** | A personal catch-all (many unrelated projects). Its `BNTS_CircuitPath` and `BNTS_PiPath` branches are old copies of this work | Nothing here: it is kept for history |
| **BNTS_FidgetCAD** | A different project | Not part of Circuit Pathways |

## Branches and tags in this repository

- **`main`**: the current work. Everything is built from here. (Set it as the default branch in the repository's
  Settings > Branches, so new visitors land on it.)
- **`claude/inspiring-hamilton-mfxok0`**: the working branch of the AI-assisted sessions; `main` is brought up to
  date from it when the tests pass. It can be deleted once you no longer need it.
- **`BNTS_CircuitPath`** and **`BNTS_PiPath`**: the two older versions that used to be the only branches (the
  Windows/Mac laptop app with its showcase website, and the original PiPath). They share no history with `main`.
  Keep them as they are, or copy them somewhere before deleting: nothing else holds them.

## Try it

```bash
cd launch
go run ./cmd/launch -dev                 # http://localhost:8080  (teacher code: teacher-code-dev)
go run ./cmd/launch -dev -beta           # the TEST edition (make up your own teacher code)
npm ci && npm test                       # the JavaScript tests
go test ./...                            # the Go tests
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # the browser tests (65 of them)
```

The full list of commands, and what must pass before a change is committed, is in [`AGENTS.md`](AGENTS.md).

## The rules that never change

No AI anywhere. No accounts, cookies, analytics or CDN files. Only a first name (or names) and a school are ever
asked for. Student-facing text is plain English at about a Year 7 reading level, in Australian spelling. See
[`AGENTS.md`](AGENTS.md) for the full list.
