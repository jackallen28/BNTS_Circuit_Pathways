# Circuit Pathways: project overview (for anyone, human or AI, joining the work)

Read this first, then `AGENTS.md` (the rules) and `docs/server.md` (setting up the school server).

## 1. What this is

**Circuit Pathways** is a free, no-AI coding tutor for secondary students (Years 7-10, some VCE), made by the
**Banyule Nillumbik Tech School (BNTS)** and reviewed by teachers. It runs on **the school's own Raspberry Pi** (the
*school server*), which every computer on the school network opens in Chrome or Edge, and on each **student Pi**, which
runs it itself so it works offline. Nothing is on the internet. It has two learning apps:

| App | Language | Real hardware | In the browser |
|---|---|---|---|
| **PiPath** | Python | Raspberry Pi (GPIO, camera) | 27 of 28 activities run with Python in the browser (Pyodide) and an on-screen Pi. On a **student Pi**, programs run on its real pins (Pi Link). Laptops are simulation only. |
| **ArduinoPath** | Blocks or Arduino C++ | Uno, Nano, NodeMCU, ESP32 and others | A full simulator, Wiring Wizard, Coach, and **Upload to a real board** over USB (Web Serial), compiled on the school server. |

```
laptops ──https──▶ SCHOOL SERVER (main Pi): the site, classes + set work + students' work (SQLite), the compiler,
                   the teacher portal, the student Pi installer, its own https certificate
student Pis: the same program on http://localhost:8080 (the site, Pi Link), classes and compiles passed on to the
             school server when it can be reached (offline: work waits in the browser and goes up later)
```

The teacher's priorities, which everything must respect:

1. **Keep student data to the minimum.** A student gives a *first name (or up to 4 first names) and a school*, nothing
   else. With no class, these stay in the student's browser and in save files the student downloads. A student who
   *chooses to join a class* has their first name(s), school and work kept with that class **on the school server**
   (so the teacher can see it), and all of it is deleted after the class's end date.
2. **No AI** anywhere (no generative features, no model calls). All help is a hand-written database of errors, hints
   and tiered explanations.
3. **No accounts, cookies, analytics, CDN scripts or fonts, and nothing on the internet.** Third-party code is vendored
   with its licence.
4. **Students run their own learning.** Every activity is open from day one; the student picks their help level.
   Teachers can **set work** (a suggested list), never lock it.
5. **Student-facing text:** plain English, short sentences, about a Year 7 reading level, **Australian spelling**
   (colour, organise, favourite), encouraging, errors are "clues" not "failures".
6. **Safety text** on every wiring screen (unplug before changing wires, never 5V on an ESP/Pi pin, resistor with LEDs).
7. FidgetCAD is **out of scope**. Ignore anything about it.

### Added in 2026
- **The school server** (November 2026; `docs/server.md`): the Go program keeps classes in SQLite (`internal/store`),
  makes its own https certificate (`internal/tlsca`), hands student Pis their installer (`internal/setup`), and runs as
  a student Pi (`-mode student-pi`, `internal/server/upstream.go`). Teachers **set work** for a class and see
  **progress** on it. The Cloudflare and Render hosting it replaced is on the `drafts` branch (`draft/cloud-hosting/`).
- **Grove kits** (`site/shared/grove/grove.json`, `grove.js`): Base Shield / Base Hat ports and modules, Grove
  projects in both apps (a `grove` tier) with plug-in steps instead of breadboard wiring, and Grove in Free Play.
- **Web Page Designer** (ArduinoPath, ESP boards: `js/webpage.js` is the model and code maker, `js/dialogs/webpage.js`
  the screen): students **drag** elements (heading, text, button, switch, slider, colour picker, reading as a number or a
  bar, status light) from a palette onto a phone, drag them to reorder or onto a bin to remove (pointer events: mouse,
  touch or pen; every action has a keyboard way too, and Undo/Redo). Each element shows what it's wired to
  (`→ LED_PIN (pin 25)`, `← Knob (pin 34)`), clashing pins are flagged (a NodeMCU has one analog pin), and the inspector
  says in one sentence what it does. **Try it** makes the page work against a pretend board (LEDs glow, the RGB LED
  mixes, the buzzer beeps, knob and sensor sliders move the readings) using `tryIt()`, which follows the real sketch.
  "See the code it makes" shows the sketch live. The generated page has no scripts, so it works in any phone browser and
  in the simulator's phone. Every idea and an every-element page are compiled for real in CI for every ESP board
  (`tools/make_compile_fixtures.mjs` writes them to `internal/arduino/testdata/webpage/`; a JS test keeps them in step).
- **USB the browser way** (`js/usbserial.js`, `js/dialogs/boardhelp.js`): a website can't install drivers, so when
  Web Serial's box doesn't list the board, "Can't see your board?" gives tips for that kind of computer and offers
  the USB way: WebUSB drivers for CH340, CP210x, FTDI and CDC-ACM chips, shaped like Web Serial's SerialPort.
  Chrome on Android (WebUSB, no Web Serial) uses it straight away. On Windows the normal way is the one to use:
  Windows Update adds the CH340 / CP210x drivers, and WebUSB can't claim a chip that has a driver.
- **Faster on a Pi**: vendored files (Python, Blockly, esptool, logos) are cached a week (`cacheControlFor`);
  the Pi launcher passes Chromium flags for classrooms (no keyring prompt, big disk cache, low-memory mode on <=2 GB).
- **ESP boards with their own WiFi** (`internal/store/boards.go`, `site/teacher/boards.js`, `site/arduinopath/js/myboard.js`):
  the teacher portal flashes each school ESP board with its own WiFi name and password and records its chip; a student
  claims one with its sticker code; ArduinoPath fills in `MY_WIFI_NAME` / `MY_WIFI_PASSWORD` and only uploads to that
  board (`flash/esp.js` reads the MAC first).
- **Updates at start-up** (`cmd/circuitpathways/update.go`): the school server from the newest GitHub release, each
  student Pi from the school server, checked by SHA-256.
- **Student Pis** (`internal/setup/student-pi.sh.tmpl`, `internal/pilink/install.sh.tmpl`, `site/shared/thispi.js`):
  the installer adds Pi menu and desktop shortcuts that open `http://localhost:8080` with `?pi=<ID>`, so PiPath on that
  Pi runs programs on it. Work is saved on the Pi and synced to the student's class.

## 2. Repository layout

```
README.md               start here: how it fits together, and which repository is which
AGENTS.md               the rules for anyone (or any AI tool) changing the code
site/                   everything the browser loads (plain HTML, CSS and ES modules, no build step).
                        The folders match the web addresses:
  index.html, css/, js/, img/   the home page (/)
  pipath/                       PiPath (/pipath/), with the Pi app in pipath/remote/
  arduinopath/                  ArduinoPath (/arduinopath/)
  teacher/                      the teacher portal (/teacher/)
  trust/                        setting a laptop up to trust the school server's https certificate (/trust/)
  shared/                       code both apps use: access, the server's edition, class sync, Grove, the local database
content/                what a teacher can edit, as data
  arduinopath/                  boards, parts, projects, errors, kit, curriculum (JSON)
  pipath/                       lessons, catalogue, errors, free play (TOML)
cmd/circuitpathways/    the Go program: the school server / student Pi, and its commands (teacher, status, backup...)
internal/               the Go server's packages (listed below)
embed.go                builds site/ and content/arduinopath/ into the Go program
raspberry-pi/           tests and README for the Pi app (the app is site/pipath/remote/circuitpathways_pi.py,
                        its installer is internal/pilink/install.sh.tmpl)
tests/                  js/ (Node tests), e2e/ (Playwright, in a real browser), pi-server/smoke.sh (the servers for real)
tools/                  build-pi.sh (the Raspberry Pi download), preflight.mjs, build_pipath_data.py, grove_art.mjs
docs/                   overview.md (this), server.md, test-day.md, teacher-guide.md, hardware-checklist.md
VERSION                 the version the download and releases carry
.github/workflows/      ci.yml (every test, a real compile, the Pi download), release.yml (publish the download)
```

Older and experimental work is **not** here: it is on the `drafts` branch (section 9).

The Go packages in `internal/`:
```
internal/store/         SQLite: classes, students (first names + school), work, set work; clean-up, backup, wipe
internal/auth/          teacher and student tokens (HMAC), the teacher codes file
internal/tlsca/         the school server's own certificate authority and https certificate
internal/setup/         the installers: the school server's (in the download) and each student Pi's (served)
internal/server/        HTTP server: routes, classes, security headers/CSP, rate limits, compile, Pi relay, student Pi upstream
internal/arduino/       arduino-cli pinned in requirements.json; Setup/Compile; returns base64 artifacts
internal/content/       loads and validates ArduinoPath content (boards, projects, errors)
internal/pirelay/       the Pi relay: Command (whitelist), in-memory hubs, SSE streams
internal/pilink/        Pi keys (HMAC) and the Pi installer template (install.sh.tmpl)
```

## 3. The website (what students and teachers see)

### Home page (`site/index.html`, `css/`, `js/home.js`)
Dark gradient with the 3D BNTS logo, a Win95-styled PiPath card and a Vista-styled ArduinoPath card, a compare table,
and two forms:
- **Student:** start straight away (no class: work saved in this browser), or type a **class code** (`ABCDE-FGHJK`),
  then first name(s) + school -> a student token in `localStorage` (`circuitpathways.access`) until the class ends.
  A student in a class sees the **work their teacher set**, with links that open each project or activity.
- **Teacher:** type a **teacher code** -> a 12-hour teacher token -> the teacher portal.
- On a laptop over plain http, a note links to the secure address and `/trust/`. On a student Pi, a note says when the
  school server can't be reached.

### Teacher portal (`site/teacher/`)
Make classes (name, school, end date), see each class's roster and work (**See work**, download everyone's work as
save files), **set work** (ArduinoPath projects and PiPath activities in order, with a note:
`PUT /api/teacher/class/<code>/tasks`), and a **progress** table for the set work (✓ finished, n/N steps, · opened,
worked out from each student's synced progress). Change a class's end date, remove a student, delete a class.
Class files (`.circuitclass`) are an optional copy on the teacher's computer.

### PiPath (`site/pipath/`) - Windows 95 look
- Vanilla ES modules and DOM helpers only (`js/dom.js` `h()`), CSSOM for dynamic styles (CSP forbids `style=""`).
- Screens: login (profiles in this browser), setup (help level), picker (Free Play + 28 activities in tiers),
  workspace (instructions, editor, board, Output console), Settings dialog.
- **Python runs in the browser:** Pyodide 0.29.3 (vendored in `vendor/pyodide`) in a module worker
  (`js/runtime/worker.js`, `runner.js`, `ipc.js`). A SharedArrayBuffer ring carries button presses and `input()`
  lines; `Atomics.wait` implements `sleep`. This needs the `/pipath/` pages to be cross-origin isolated
  (COOP same-origin + COEP require-corp, set by the server).
- `py/cpsim/` is a gpiozero look-alike (no threads; a cooperative scheduler) driving the on-screen board
  (`js/widgets/board.js`). `py/pipath/` is PiPath's own Coach (`hints.py`, `levels.py`, `review.py`, `adapt.py`),
  run unchanged through `cpsim/bridge.py`. `pipath_camera.py` / `pipath_computer.py` are the helper modules lessons import.
- **Help levels** (student's choice): Beginner / Moderate / Advanced. **Adaptive nudges**, hint tiers, "Watch the
  goal" (plays the model answer in the simulator), independence stars, code review, curriculum links in Settings.
- **Run on: Simulator | My Raspberry Pi** (new). See section 5.
- Lessons are TOML in `content/pipath/`; `tools/build_pipath_data.py` writes the JSON under `site/pipath/data/`.
  Lesson step checks: `runs_ok`, `code_regex/uses/count/contains`, `output_contains/regex/lines_min`, `confirm`,
  `file_exists/contains`, `run_count_min`. Every step has a `demo` (model answer) that must pass its own checks
  (tested for real in Pyodide).
- Known gap: the Turtle Art activity needs a drawing window and is listed but not opened in the browser.

### ArduinoPath (`site/arduinopath/`) - Windows Vista look
- Plain ES modules. A Fritzing-style renderer draws breadboard + schematic from the part SVGs (CC BY-SA 3.0,
  `parts/`); the same renderer serves the Wiring Wizard, simulator and Free Play.
- **Simulator:** its own Arduino C++ interpreter in JS (`js/sim/`) running in a Web Worker with an instruction
  budget; a simulated Arduino API (pins, Serial, Servo, NeoPixel, DHT, OLED, LCD, WiFi/web server with a "phone"
  panel...). Blocks editor (Blockly, vendored) alongside C++.
- **Wiring Wizard** before every project: meet the parts -> wire step by step -> a forced **Test** sketch generated
  from the project's parts -> confirm each part -> then programming opens.
- **Coach** explains compiler/runtime errors from `content/arduinopath/errors.json`; help levels; code review.
- **Real boards:** `POST /api/compile` -> artifacts -> flashed in the browser over **Web Serial**: own STK500v1
  (Optiboot) for Uno/Nano, vendored esptool-js 0.7.0 for ESP8266/ESP32 (`js/flash/`, `webserial.js`, `realboard.js`).
- Storage: `js/api.js` is replaced by a **browser-local API** (`site/shared/local/`: IndexedDB or memory store,
  zip, save-file format, validation). The server serves only the catalogue and project JSON
  (`/arduinopath/data/...`).
- Projects/boards/errors are data in `content/` (JSON, schema in `content/arduinopath/schema/`).

### Shared (`site/shared/`)
`access.js` (a student's class token or a teacher's sign-in in localStorage, else `local`; `postJSON` adds the required
headers), `edition.js` (school server or student Pi, Pi Link on or off, the build line), and `local/` (the browser-local
save system used by both apps: `.circuit` for ArduinoPath, `.pipath` for PiPath; `cloud.js` and `localapi.js` sync a
class member's work to the school server, and send up anything newer that waited while offline).

## 4. The server (Go, `internal/server`)

One program, two modes (`-mode school`, the default, and `-mode student-pi`). See `docs/server.md` for running it.

| Route | Purpose |
|---|---|
| `POST /api/teacher/signin` | a teacher code (from `teacher-codes.txt` in the data folder) -> 12 h token `t2.<teacher>.<exp>.<sig>` |
| `GET /api/teacher/classes`, `POST /api/teacher/class` | the teacher's classes; make one (name, school, `days` or `ends_at`) |
| `/api/teacher/class/<code>` (`GET`, `DELETE`, `/work`, `/end`, `/tasks` `GET`/`PUT`, `/students/<id>` `DELETE`) | a class: roster + tasks, everyone's work, end date, set work, remove a student |
| `POST /api/class/join` | a class code alone -> `needs_names`; with first names + school -> a student token `s2.<id>.<sig>` |
| `/api/student/me` (`GET` with tasks, `DELETE`), `/api/student/work` (`GET`, `POST` up to 25 items, newer wins) | a student's own class |
| `POST /api/compile` | compiles for a board with arduino-cli. Anyone on the network; a token that is sent must be real |
| `GET /api/pi/events?code=` (SSE), `POST /api/pi/command` | browser side of the Pi relay (a student Pi) |
| `GET /api/pi/pi/events` (SSE), `POST /api/pi/pi/send` | Pi side (needs the Pi's key in `X-Pi-Key`) |
| `GET /install/student-pi.sh`, `/install/circuitpathways-linux-<arch>`, `/install/version`, `/ca.crt` | the school server sets up (and updates) student Pis, and laptops |
| `/api/teacher/boards` (`GET`, `POST`), `/api/teacher/boards/<id>` (`DELETE`, `/sketch`, `/flashed`, `/release`) | the school's ESP boards: own WiFi, sticker code, chip (MAC) |
| `/api/student/board` (`GET`, `POST` a sticker code, `DELETE`) | a student's own ESP board |
| `GET /healthz`, `GET /api/info` | health; edition (`school`/`student-pi`), name, build, compile, relay, online, tls, fingerprint |

Rules the server enforces: security headers on everything; **strict CSP** (`/arduinopath/` and `/pipath/` use
`style-src 'self'`, so no inline styles; the home, teacher and trust pages allow inline styles); every write needs the
`X-Circuit-Pathways: 1` header and JSON; strict validation (the same name/school rules as `validate.js`) and size
limits; per-address in-memory rate limits (no proxy headers trusted); logs hold method, path, status and time only.

**Data** (`/var/lib/circuitpathways`): `pathways.db` (SQLite, WAL, `secure_delete`, schema version), `secret` (signs
tokens), `teacher-codes.txt`, `tls/` (the certificate authority and certificate), and on a student Pi `pi-key-secret`
and `this-pi-id`. Classes that have ended are deleted every few hours (then the file is compacted).

**A student Pi** (`upstream.go`): serves the site and Pi Link itself on `127.0.0.1:8080`; `/api/teacher/`, `/api/class/`,
`/api/student/` (and `/api/compile` without local tools) go to the school server over https, trusting only its
certificate authority; if it can't be reached, those answer 503 `offline` and `/api/info` says `online: false`.

## 5. Raspberry Pi: Pi Link and "Run on my Raspberry Pi"

```
the Pi's browser  <--SSE / POST-->  Circuit Pathways on the same Pi (localhost:8080, relay in memory)  <--SSE / POST-->  Pi app
```
Everything stays on the student Pi, so it works with no network.

- Each Pi has its own key `CPK1-<8 id>-<10 mac>` (HMAC with the Pi's own `pi-key-secret`, made by
  `circuitpathways pi-key`); the shortcuts pass the Pi's ID `XXXX-XXXX` (`?pi=`), so nobody types it.
- **Pi app** `site/pipath/remote/circuitpathways_pi.py` (stdlib + gpiozero; `--mock` for pretend pins):
  - **Bridge:** whitelisted pin commands (GPIO 2-27: mode/write/pwm/release/all_off/read/ping); fail-safe turns
    outputs off after 10 s offline.
  - **Runner (v0.2.0):** `run` / `stdin` / `stop`. One program at a time in a temp folder, as the unprivileged user
    `cprun` (never root), RLIMITs (10 min, 2 GB, 10 MB files, 64 procs), 200k chars output, stopped when the page
    goes quiet (25 s) or the Pi loses the site (10 s); the program owns the pins while it runs; PiPath helper
    modules fetched from the site; new small files reported back so lesson file-checks work; tracebacks show
    `File "program.py"`. Off switch: `RUN=no` / `sudo pilink run off`.
- **Relay** (`internal/pirelay`): `Command.Check()` is the whitelist (file names, sizes, helper list, camera
  object); events `hello/state/error/pong/run/out/exit`; browser queue 512 so output is never dropped.
- **Installer** (`internal/pilink/install.sh.tmpl`, run by the student Pi installer via `circuitpathways pi-installer`):
  installs the app, `cprun`, a locked-down systemd service that starts at boot, the
  `pilink` helper (`show|status|log|restart|run on|off|server|uninstall`), `PI-LINK-ID.txt`, a desktop ID popup.
  The template uses `<% %>` delimiters because bash `[[ ]]` clashes with Go's `{{ }}`.
- **Browser side:** `site/pipath/remote/pi-remote.js` (`PiRemote`: connect, pins, `run/stdin/stop`),
  `site/pipath/js/runtime/pi.js` (singleton), `js/dialogs/pi.js` (link window), `js/screens/workspace.js`
  (`where`, `ensurePi`, `runOnPi`), and `/pipath/remote/` (the older pin-switching page).
- Be honest in docs: student code is real Python on the student's Pi (as `cprun`, with limits).

## 6. Data and saving

- Students' work lives in the browser (IndexedDB / localStorage) and in downloadable save files
  (`.circuit`, `.pipath`; zips with a version number). Never break the save format: it has a schema version and
  migrations. Teachers' class files `.circuitclass` bundle a class setup plus student files.
- Content is **data a teacher can edit without touching code** (JSON/TOML). Add a project/lesson by editing data.

## 7. Testing (keep all of it green)

```
gofmt -l .                                   # must print nothing
go vet ./... && go test -race ./...          # server, classes, set work, student Pi, certificates, relay, pilink, content
python3 tools/build_pipath_data.py --check   # PiPath JSON up to date with the TOML
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover raspberry-pi   # Pi app, runs real programs
npm ci && npm test                           # about 400 Node tests (simulator, wizard, saves, flashing, every PiPath demo in real Pyodide)
bash tests/pi-server/smoke.sh                # the school server with https + a student Pi installed from it, Pi Link, offline
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # end-to-end: a dev school server (8543) and a student Pi (8546)
```
CI (`.github/workflows/ci.yml`) runs all of that plus `compile` (the real arduino-cli for every board, and the smoke test
with a real compile through the school server and a student Pi) and `pi-bundle` (builds the Raspberry Pi download and
runs the smoke test with it). Not verifiable here: real board uploads, a real Pi's pins, the installers under systemd
on a real Pi, and laptops trusting the certificate.

## 8. Deploy

`bash tools/build-pi.sh` (or **Actions > Release**) makes `circuitpathways-pi-VERSION.tar.gz`: the program for 64-bit
Raspberry Pi OS and `install-server.sh`. On the school server Pi: `sudo bash install-server.sh`. On each student Pi:
`curl -fsSL http://pathways.local/install/student-pi.sh | sudo bash`. Laptops: `http://pathways.local/trust` once.
See `docs/server.md`.

## 9. Older and experimental work (the `drafts` branch)

The hosted versions (Cloudflare with classes in D1, Render, the TEST and Pi beta editions) are in
`draft/cloud-hosting/`, as they were at commit `bd484de`. The first CircuitPath was a **local app** (`CircuitPath.exe` / `.app`, Go + SQLite, served on localhost, Edge app
window) and, before that, a Pi/cloud server. The offline PiPath and ArduinoPath apps, WastePath (a Pi waste-sorting
camera bin) and the bin monitor (an Arduino bin with a dashboard) were built beside it. All of that is kept, organised,
in the **`draft/`** folder on the **`drafts`** branch (`draft/README.md` says what each folder is and where it came from).
Nothing there is deployed or tested. The original brief for the Wiring Wizard, simulator and boards is in
`draft/laptop-app-circuitpath/CLAUDE.md`.

## 10. Where to start for common jobs

| Job | Look at |
|---|---|
| Add/edit a PiPath lesson | `content/pipath/lessons/*.toml` -> `python3 tools/build_pipath_data.py` -> tests |
| Add/edit an ArduinoPath project or error hint | `content/arduinopath/projects/*.json`, `content/arduinopath/errors.json` (+ its test) |
| Change the home page or teacher portal | `site/index.html`, `css/`, `js/home.js`, `site/teacher/` |
| Change classes, set work or the database | `internal/server/classes.go`, `internal/store/` (bump `schemaVersion` and migrate) |
| Change the installers | `internal/setup/`, `internal/pilink/install.sh.tmpl`, then `bash tests/pi-server/smoke.sh` |
| Change how PiPath runs code | `site/pipath/js/runtime/`, `py/cpsim/` |
| Change the Pi app or installer | `site/pipath/remote/circuitpathways_pi.py`, `internal/pilink/install.sh.tmpl`, `raspberry-pi/` tests |
| Change auth / rate limits / headers | `internal/auth/`, `internal/server/` |
| Add a board or part | `content/arduinopath/boards/`, `content/arduinopath/parts/`, `site/arduinopath/parts/` |

## 11. Known limits and open ideas

- Not yet tried on real hardware: the school server and student Pi installers on real Pis (they are tested in a
  folder, with systemd left out), laptops trusting the certificate, Arduino/ESP upload (the esptool path least tested),
  and Run on my Pi on a real Pi's pins.
- PiPath Turtle Art not in the browser.
- Ideas: a teacher view of which student Pis are online, an SD-card image of a ready student Pi, updating student Pis
  from the school server by themselves, the server's status (disk, backups) in the teacher portal.
