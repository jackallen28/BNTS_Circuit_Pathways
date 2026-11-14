# Circuit Pathways

A free, no-AI coding tutor for secondary students, made by the **Banyule Nillumbik Tech School (BNTS)**.
It has two apps that run in the student's browser (Chrome or Edge):

- **PiPath**: Python for the Raspberry Pi (a Windows 95 look).
- **ArduinoPath**: Arduino and ESP boards, in blocks or C++ (a Windows Vista look).

**It runs on the school's own Raspberry Pi.** One main Pi (the *school server*) serves the site, the classes and the
compiler to every computer on the school network. Nothing is on the internet.

| Who | How they use it |
|---|---|
| **Students on laptops** | Open `https://pathways.local` in Chrome or Edge: PiPath (Python on the on-screen Pi) and ArduinoPath (the simulator, and Upload to a board on USB). |
| **Students on student Pis** | Open PiPath or ArduinoPath from the Pi menu. Each student Pi runs Circuit Pathways itself, so it works offline, and PiPath runs programs on the Pi's real pins. Work goes to the class on the school server whenever it can. |
| **Teachers** | Sign in on the home page: the teacher portal makes classes, sets work, and shows each student's progress and code. |

Setting it up: [`docs/server.md`](docs/server.md). About to test with real Pis and boards: [`docs/test-day.md`](docs/test-day.md).

## Where things are

```
site/          What the browser loads. The folders match the web addresses: pipath/, arduinopath/, teacher/
               (the teacher portal), trust/ (setting up a laptop for https), shared/ (code both apps use), the home page.
content/       What a teacher can edit, as data: arduinopath/ (boards, parts, projects, errors) and pipath/ (lessons).
cmd/, internal/, embed.go   The Go program: the school server and student Pis (classes in SQLite, its own https
               certificate, the compiler, Pi Link, the installers).
raspberry-pi/  Tests and README for Pi Link, the app on each student Pi (site/pipath/remote/circuitpathways_pi.py).
tests/         js/ (Node tests), e2e/ (Playwright, in a real browser), pi-server/ (the school server and a student Pi, for real).
tools/         build-pi.sh (the Raspberry Pi download), preflight.mjs (is a server ready?), build_pipath_data.py, grove_art.mjs.
docs/          The documentation: start at docs/README.md.
.github/workflows/          ci.yml (every test) and release.yml (publish the Raspberry Pi download).
AGENTS.md      The rules for anyone (or any AI tool) changing the code. Read it first.
```

## The other repositories and branches

| Where | What it is |
|---|---|
| **BNTS_Circuit_Pathways**, branch **`main`** (this) | The product. Everything new goes here. |
| branch **`drafts`** | Older and experimental work in `draft/`: the cloud hosting this replaced (Cloudflare, Render, the TEST and Pi beta editions), the first laptop app, the offline PiPath and ArduinoPath, WastePath and the bin monitor. Not deployed, not tested. `draft/README.md` explains each. |
| **BNTS_PIPath**, **BNTS_ArduinoPath** | The older stand-alone apps (copied into `drafts`). |
| **jackallen** | A personal catch-all, not part of Circuit Pathways. **BNTS_FidgetCAD** is a different project. |

## Try it on a computer

```bash
go run ./cmd/circuitpathways -dev                 # the school server on http://localhost:8080 (teacher code: teacher-code-dev)
go run ./cmd/circuitpathways -dev -mode student-pi -addr :8090 -school http://localhost:8080   # a student Pi beside it
npm ci && npm test                                # the JavaScript tests
go test ./...                                     # the Go tests
bash tests/pi-server/smoke.sh                     # the school server (https) and a student Pi installed from it, for real
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # the browser tests
bash tools/build-pi.sh                            # the Raspberry Pi download, in dist/
```

The full list of commands, and what must pass before a change is committed, is in [`AGENTS.md`](AGENTS.md).

## The rules that never change

No AI anywhere. No accounts, cookies, analytics or CDN files, and nothing on the internet. Only a first name (or names)
and a school are ever asked for, and they are deleted when the class ends. Student-facing text is plain English at about
a Year 7 reading level, in Australian spelling. See [`AGENTS.md`](AGENTS.md) for the full list.
