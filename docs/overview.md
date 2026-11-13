# Circuit Pathways: project overview (for anyone, human or AI, joining the work)

Read this first, then `AGENTS.md` (the rules) and `docs/deploy-render.md` (deploying).

## 1. What this is

**Circuit Pathways** is a free, no-AI coding tutor for secondary students (Years 7-10, some VCE), made by the
**Banyule Nillumbik Tech School (BNTS)** and reviewed by teachers. It has two learning apps that run **in the
student's browser** (Chrome or Edge on a laptop) from one website:

| App | Language | Real hardware | In the browser |
|---|---|---|---|
| **PiPath** | Python | Raspberry Pi (GPIO, camera) | 27 of 28 activities run with Python in the browser (Pyodide) and an on-screen Pi. A student can instead choose **Run on: My Raspberry Pi** so the program runs on their own Pi. |
| **ArduinoPath** | Blocks or Arduino C++ | Uno, Nano, NodeMCU, ESP32 and others | A full simulator, Wiring Wizard, Coach, and **Upload to a real board** over USB (Web Serial). |

The teacher's priorities, which everything must respect:

1. **Keep student data to the minimum.** A student gives a *first name (or up to 4 first names) and a school*, nothing
   else. On the **Go / Render** site these stay in the student's browser and in save files the student downloads; the
   server never receives them. On the **Cloudflare** site, a student who *chooses to join a class* has their first
   name(s), school and work kept with that class (so the teacher can see it), and all of it is deleted after the
   class's end date. A student with no class (the Pi beta, the TEST version) keeps everything on their own device.
2. **No AI** anywhere (no generative features, no model calls). All help is a hand-written database of errors, hints
   and tiered explanations.
3. **No accounts, cookies, analytics, CDN scripts or fonts.** Third-party code is vendored with its licence.
4. **Students run their own learning.** Every activity is open from day one; the student picks their help level.
5. **Student-facing text:** plain English, short sentences, about a Year 7 reading level, **Australian spelling**
   (colour, organise, favourite), encouraging, errors are "clues" not "failures".
6. **Safety text** on every wiring screen (unplug before changing wires, never 5V on an ESP/Pi pin, resistor with LEDs).
7. FidgetCAD is **out of scope**. Ignore anything about it.

### Added in 2026 (Cloudflare and kits)
- **Cloudflare** (`cloudflare/`, its README): the site as a Worker with static assets, saved classes in D1, the Pi relay
  as a Durable Object, and compiles passed to `COMPILE_URL`. The Go server still runs the same site on Render.
- **Grove kits** (`site/shared/grove/grove.json`, `grove.js`): Base Shield / Base Hat ports and modules, Grove
  projects in both apps (a `grove` tier) with plug-in steps instead of breadboard wiring, and Grove in Free Play.
- **Web Page Designer** (ArduinoPath, ESP boards: `js/webpage.js`, `js/dialogs/webpage.js`): students design a
  phone web page and get a working WebServer sketch; the simulator's phone panel shows it.
- **USB the browser way** (`js/usbserial.js`, `js/dialogs/boardhelp.js`): a website can't install drivers, so when
  Web Serial's box doesn't list the board, "Can't see your board?" gives tips for that kind of computer and offers
  the USB way: WebUSB drivers for CH340, CP210x, FTDI and CDC-ACM chips, shaped like Web Serial's SerialPort.
  Chrome on Android (WebUSB, no Web Serial) uses it straight away. On Windows the normal way is the one to use:
  Windows Update adds the CH340 / CP210x drivers, and WebUSB can't claim a chip that has a driver.
- **The Pi beta edition** (`PI_BETA=1`, wrangler env `pi`, `site/shared/beta.js` `piBeta`, `access.js` kind `local`): the
  real site marked BETA where a class code is optional. No code: the apps get the access word `local` (the Worker lets
  it compile and link a Pi, rate limited) and everything is saved in the browser on that device. A class code: the
  same sync to the class database as the real site (which it shares). A profile made before joining is linked and
  uploaded the next time the app opens (`localapi.me()`). The TEST version (`BETA=1`) is unchanged: nothing saved.
- **Faster on a Pi**: vendored files (Python, Blockly, esptool, logos) are cached a week (`cacheControlFor`, `_headers`);
  the Pi launcher passes Chromium flags for classrooms (no keyring prompt, big disk cache, low-memory mode on <=2 GB).
- **The Raspberry Pi version** (`internal/pilink/install.sh.tmpl`, `site/shared/thispi.js`): the Pi installer adds
  Pi menu and desktop shortcuts that open the site with `?pi=<ID>`, so PiPath on that Pi runs programs on it. Work is
  saved on the Pi and synced to the student's class.

## 2. Repository layout

```
README.md               start here: which edition and which repository is which
AGENTS.md               the rules for anyone (or any AI tool) changing the code
site/                   everything the browser loads (plain HTML, CSS and ES modules, no build step).
                        The folders match the web addresses:
  index.html, css/, js/, img/   the home page (/)
  pipath/                       PiPath (/pipath/), with the Pi app in pipath/remote/
  arduinopath/                  ArduinoPath (/arduinopath/)
  teacher/                      the teacher page (/teacher/)
  shared/                       code both apps use: access, beta editions, class sync, Grove, the local database
content/                what a teacher can edit, as data
  arduinopath/                  boards, parts, projects, errors, kit, curriculum (JSON)
  pipath/                       lessons, catalogue, errors, free play (TOML)
cmd/circuitpathways/             the Go program: flags, environment, Pi keys, the export for Cloudflare
internal/               the Go server's packages (listed below)
embed.go                builds site/ and content/arduinopath/ into the Go program
cloudflare/             the same site as a Cloudflare Worker: classes in D1, the Pi relay, the compile proxy
raspberry-pi/           tests and README for the Pi app (the app is site/pipath/remote/circuitpathways_pi.py,
                        its installer is internal/pilink/install.sh.tmpl)
tests/                  js/ (Node tests), e2e/ (Playwright, in a real browser)
tools/                  build_pipath_data.py (PiPath TOML to JSON), grove_art.mjs (Grove part drawings)
docs/                   overview.md (this), deploy-render.md, server.md, hardware-checklist.md
Dockerfile*, render*.yaml   building and hosting on Render
.github/workflows/      ci.yml (every test, a real compile, the Docker image), cloudflare-deploy.yml
```

Older and experimental work is **not** here: it is on the `drafts` branch (section 9).

The Go packages in `internal/`:
```
internal/classes/       class codes and teacher tokens (signed, stateless)
internal/server/        HTTP server: routes, security headers/CSP, rate limits, compile, Pi relay endpoints
internal/arduino/       arduino-cli pinned in requirements.json; Setup/Compile; returns base64 artifacts
internal/content/       loads and validates ArduinoPath content (boards, projects, errors)
internal/pirelay/       the Pi relay: Command (whitelist), in-memory hubs, SSE streams
internal/pilink/        Pi keys (HMAC) and the Pi installer template (install.sh.tmpl)
```

## 3. The website (what students and teachers see)

### Home page (`site/index.html`, `css/`, `js/home.js`)
Dark gradient with the 3D BNTS logo, a Win95-styled PiPath card and a Vista-styled ArduinoPath card, a
compare table, and two forms:
- **Student:** type a **class code** (`ABCDE-FGHJK`) -> stored in `localStorage` (`circuitpathways.access`) until it
  expires -> open PiPath or ArduinoPath. Then the app asks for first name(s) + school (kept in the browser).
- **Teacher:** type a **teacher code** -> a 12-hour teacher token -> the teacher page.

### Teacher page (`site/teacher/`)
Signed-in teachers can: make a **class code** (1 day to a year); name the class; **save/open a class file**
(`.circuitclass`, a zip holding the class setup plus students' handed-in `.circuit` / `.pipath` files); add student
files and see who has done what. The class name, the class file and all student work stay on the **teacher's
computer**, handled only in the browser. The Go server stores nothing about classes. **On Cloudflare** (`cloudflare/`),
classes are saved in D1 instead: students join with the class code + first name(s) + school, their work syncs to the
class, and the teacher page shows the roster and work. Everything is deleted after the class's end date.

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
`access.js` (class/teacher access in localStorage, `postJSON` adds the required headers), and `local/` (the
browser-local save system used by both apps: `.circuit` for ArduinoPath, `.pipath` for PiPath).

## 4. The server (Go, `internal/server`)

One binary, one port (`$PORT`, default 8080). Only these jobs: serve the site, check class/teacher access,
compile Arduino code, relay Pi messages.

| Route | Purpose |
|---|---|
| `POST /api/teacher/signin` | teacher code -> 12 h token `t1.<exp>.<sig>` |
| `POST /api/teacher/class` | teacher token -> new class code |
| `POST /api/class/join` | check a class code (rate limited) |
| `POST /api/compile` | class code or teacher token in `X-Access`; compiles for a board with arduino-cli |
| `GET /arduinopath/data/catalogue.json`, `/projects/{id}` | ArduinoPath content |
| `GET /api/pi/events?code=` (SSE), `POST /api/pi/command` | browser side of the Pi relay (needs class access) |
| `GET /api/pi/pi/events` (SSE), `POST /api/pi/pi/send` | Pi side (needs the Pi's key in `X-Pi-Key`) |
| `GET /pipath/remote/circuitpathways_pi.py`, `install.sh` | the Pi app / generic installer with this site's address filled in |
| `GET /healthz`, `GET /api/info` | health, version |

Rules the server enforces: security headers on everything; **strict CSP** (`/arduinopath/` and `/pipath/` use
`style-src 'self'`, so no inline styles; the home and teacher pages allow inline styles); every write needs the
`X-Circuit-Pathways: 1` header; strict request validation and size limits (`maxBody` 128 KB); per-IP in-memory
rate limits; logs hold method, path, status, time only. **No database. Nothing is written to disk** except the
compiler's temporary folder.

### Stateless auth (`internal/classes`)
- **Class code** `ABCDE-FGHJK`: 12 bits expiry day (days after 1 Jan 2026) + 13 random bits + 25-bit
  HMAC-SHA256 tag, Crockford base32, valid to the end of that day in Melbourne time. Cannot be revoked early.
- **Teacher token** `t1.<exp>.<sig>`, 12 hours. Teacher codes come from env `TEACHER_CODES` (comma separated, >= 8 chars).
- Secrets: `CLASS_SECRET` (never change it once classes are out), `TEACHER_CODES`, `PI_KEY_SECRET`,
  optional `REVOKED_PI_IDS`. `-dev` mode uses fixed dev values (teacher code `teacher-code-dev`).

## 5. Raspberry Pi: Pi Link and "Run on my Raspberry Pi"

```
student's browser  <--SSE / POST-->  Circuit Pathways server (relay, in memory)  <--SSE / POST-->  Pi app
```
Both sides only make **outgoing** connections, so it works on school networks and from an https page.

- Each Pi has its own key `CPK1-<8 id>-<10 mac>` (HMAC, `PI_KEY_SECRET`); the student types the Pi's ID `XXXX-XXXX`.
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
- **Installer** (`internal/pilink/install.sh.tmpl`, per-Pi via `go run ./cmd/circuitpathways -pi-keys N`; refresh with
  `-pi-refresh pi-keys.csv`): installs the app, `cprun`, a locked-down systemd service that starts at boot, the
  `pilink` helper (`show|status|log|restart|run on|off|server|uninstall`), `PI-LINK-ID.txt`, a desktop ID popup.
  The template uses `<% %>` delimiters because bash `[[ ]]` clashes with Go's `{{ }}`.
- **Browser side:** `site/pipath/remote/pi-remote.js` (`PiRemote`: connect, pins, `run/stdin/stop`),
  `site/pipath/js/runtime/pi.js` (singleton), `js/dialogs/pi.js` (link window), `js/screens/workspace.js`
  (`where`, `ensurePi`, `runOnPi`), and `/pipath/remote/` (the older pin-switching page).
- Security posture is documented in `docs/deploy-render.md` ("Running students' programs on a Pi"). Be honest in docs:
  student code is real Python on the school network.

## 6. Data and saving

- Students' work lives in the browser (IndexedDB / localStorage) and in downloadable save files
  (`.circuit`, `.pipath`; zips with a version number). Never break the save format: it has a schema version and
  migrations. Teachers' class files `.circuitclass` bundle a class setup plus student files.
- Content is **data a teacher can edit without touching code** (JSON/TOML). Add a project/lesson by editing data.

## 7. Testing (keep all of it green)

```
gofmt -l .                                   # must print nothing
go vet ./... && go test -race ./...          # server, classes, relay, pilink, content, cmd
python3 tools/build_pipath_data.py --check   # PiPath JSON up to date with the TOML
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover raspberry-pi   # Pi app, runs real programs (36 tests)
npm ci && npm test                           # about 400 Node tests (simulator, wizard, saves, flashing, every PiPath demo in real Pyodide)
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test        # 65 end-to-end tests (spawns the real Go server in -dev; some spawn the real Pi app)
```
CI (`.github/workflows/ci.yml`) runs all of that plus `compile` (real arduino-cli compile of every board via
`TestCompileEveryBoardForReal`) and `image` (docker build + smoke). Not verifiable offline: the real compile and
Docker build (CI covers them), real board upload, and a real Pi.

## 8. Deploy

`render.yaml` (repository root): Docker web service `circuit-pathways`, Standard plan (ESP32
compiler needs ~1.5 GB). Env: `CLASS_SECRET` (generated), `TEACHER_CODES`, `PI_KEY_SECRET`, `REVOKED_PI_IDS`
(secrets set in Render, never in git). The first build downloads the Arduino toolchain. See `docs/deploy-render.md`.

## 8b. The TEST version (BETA=1)

`BETA=1` (or `-beta`) turns the same build into a shareable test for colleagues: the home page shows a TEST label;
`site/shared/beta.js` asks `/api/info`, and when it is the test version `getAccess()` returns an open "beta" access (a
joined class or teacher sign-in wins over it), `openStore()` returns the in-memory store, Save/Open my work, Download
.ino, Wipe and the PiPath "Run on" choice are hidden, and a TEST tag is shown. The server returns 404 for `/api/pi/` and
the Pi Link page, sends `X-Robots-Tag: noindex`, and accepts the open access only for `/api/compile`.

**Beta teacher mode** (both beta editions, `info.teacher_mode`): classes and the teacher page are there, and a teacher
signs in with **a code they make up** (8 to 64 characters; their classes are kept under it, nobody else sees them
without it). The real site still only takes the school's `TEACHER_CODES`. Students join with the class code. On the Go
site that is a stateless class code (nothing saved). On the Cloudflare TEST version, a student who joins has their first
name(s), school and work saved to the class in the TEST database (the device itself still keeps nothing, so after a
reload they join back in and their work returns); the Go site's class codes keep nothing. On Go set `CLASS_SECRET`, or
class codes stop working when the TEST version restarts. Blueprint: `render.test.yaml`. Tests: `tests/e2e/test-version.spec.js`
(second server, port 8544), `tests/e2e/cloudflare-test.spec.js` (the Worker's `test` env, port 8547), `cloudflare/test/pibeta.test.mjs`.

## 9. Older and experimental work (the `drafts` branch)

The first CircuitPath was a **local app** (`CircuitPath.exe` / `.app`, Go + SQLite, served on localhost, Edge app
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
| Change the home or teacher page | `site/index.html`, `css/`, `js/home.js`, `site/teacher/` |
| Change how PiPath runs code | `site/pipath/js/runtime/`, `py/cpsim/` |
| Change the Pi app or installer | `site/pipath/remote/circuitpathways_pi.py`, `internal/pilink/install.sh.tmpl`, `raspberry-pi/` tests |
| Change auth / rate limits / headers | `internal/classes/`, `internal/server/` |
| Add a board or part | `content/arduinopath/boards/`, `content/arduinopath/parts/`, `site/arduinopath/parts/` |

## 11. Known limits and open ideas

- Not yet tried on real hardware: Arduino/ESP upload (esptool path least tested), Run on my Pi on a real Pi.
- PiPath Turtle Art not in the browser. A wifi blip can lose a few lines of output on the Pi run.
- Ideas: pin events from a Pi program into a pins panel, an SD-card image with Pi Link installed, a teacher view of
  online Pis, a direct (no-internet) mode where the Pi serves the page itself, native remote GPIO over SSH.
