# Circuit Pathways: the website (`launch/`)

PiPath and ArduinoPath in the browser, for the Banyule Nillumbik Tech School. This folder is
what is deployed. The earlier app and its docs are in `../development/`.

- **Home** (`site/index.html`): the Circuit Pathways page, where students join a class with a
  class code and teachers sign in.
- **ArduinoPath** (`site/arduinopath/`): the whole app in the browser. Profiles, progress and code
  are saved **in the student's own browser** (IndexedDB) and in `.circuit` files they download.
  Upload to a real board uses **Web Serial** (Chrome or Edge): the server compiles, the browser
  flashes (STK500v1 for Uno/Nano, esptool-js for ESP boards).
- **Teacher page** (`site/teacher/`): make a class code; save and open `.circuitclass` class files
  with students' work, all on the teacher's computer.
- **PiPath** (`site/pipath/`): Python in the browser (Pyodide) with an on-screen Raspberry Pi: 24 of the 25
  activities, PiPath's own Coach, hints, adaptive nudges and code review (its Python engine runs unchanged).
  `content-pipath/` holds the lessons as TOML; `tools/build_pipath_data.py` makes the JSON the site loads.
- **Run on my Raspberry Pi** and **Pi Link** (`site/pipath/remote/`, `pi-bridge/`): a student links to their own Pi by its
  ID, then PiPath's Run button runs the program on the real Pi (output, `input()`, Stop, Coach and checks all work), or
  the Pi Link page switches pins by hand. Each Pi has its own signed key and an installer that starts at boot.

**To launch: read [LAUNCH.md](LAUNCH.md).**

## What the server does and doesn't do

It serves the pages, checks class codes and teacher sign-ins, **compiles** Arduino code, and
**relays Pi Link** messages (pin commands, and for "Run on my Pi", the program and its output, held in memory for that moment). It has **no database and writes nothing to disk** except the
compiler's temporary folder, deleted after each compile. It never receives a student's name or
school: those stay in the browser and the student's save file. Compiled code is held for one
request and never logged. Logs hold the method, path, status code and time, and nothing else.
(Render itself logs visitors' IP addresses, as any host does: say so in your privacy notice.)

## Deploy on Render

1. In Render choose **New > Blueprint** and pick this repository and branch (`render.yaml` is at
   the top of the repository). It builds `launch/Dockerfile`; the first build takes a while because
   it downloads the Arduino compilers (about 1.5 GB) and warms them up.
2. Set **`TEACHER_CODES`**: one or more teacher codes (each at least 8 characters), separated by
   commas. Teachers type one of these on the home page. `CLASS_SECRET` is made for you.
   **Never change `CLASS_SECRET`**: every class code already handed out would stop working.
3. Use the **Standard** plan (2 GB) or bigger. The ESP32 compiler needs about 1.5 GB of memory.
4. Optional: add a custom domain (for example one under your school's website) so school filters
   and students trust it. Ask IT to allow the domain, and to allow **USB serial** in Chrome / Edge
   if they restrict it (the `SerialAllowForUrls` policy).

## Class codes and teacher sign-in

- A teacher signs in with a teacher code and makes a class code (`ABCDE-FGHJK`) that works for 1
  day to a year. The code carries its own expiry and a signature, so the server stores nothing.
  A class code can't be switched off early: choose a length that suits the program.
- Students type the class code on the home page. It is kept in their browser until it expires.
  The apps and compiling need it. A teacher's sign-in also works in the apps, for 12 hours.
- Sign-in and code checks are rate limited by address, in memory.

## Develop

```
go run ./cmd/launch -dev                 # http://localhost:8080  (teacher code: teacher-code-dev; no compilers)
go test -race ./...                      # server, class codes, Pi relay, content
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover pi-bridge   # the Pi Link app (no Pi needed)
npm ci && npm test                       # ArduinoPath simulator and wizard, save files, upload to a pretend board,
                                         # and PiPath: every activity's model answer in real Pyodide
npm run e2e                              # the whole site in Chromium (set CHROMIUM_PATH if needed)
go run ./cmd/launch -setup -warm -tools ~/tools    # install the real compilers (needs the internet)
CIRCUITPATHWAYS_TOOLS=~/tools go test -run TestCompileEveryBoardForReal ./internal/arduino
```

Part pictures come from the Fritzing parts library (CC BY-SA 3.0); `esptool-js` (Apache-2.0) and
Blockly (Apache-2.0) are vendored with their licences in `site/arduinopath/vendor/`.
