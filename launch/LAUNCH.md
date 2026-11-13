# Launching Circuit Pathways v1.0 on Render

This is the checklist for putting the site live and trying it yourself. It assumes the branch
has been merged (or Render is pointed at this branch).

> **Cloudflare instead?** The site can also run on Cloudflare Workers, with **classes saved in a database** (students'
> first names, school and work, deleted when the class ends) and the **Pi beta** and **TEST** editions. That is set up
> from [cloudflare/README.md](cloudflare/README.md). Most of this page (Pis, the compiler, hardware checks) applies to
> both; the "nothing is stored" statements below are about the **Render** site.

## 1. What you are launching

| Part | Where | What it does |
|---|---|---|
| Home page | `/` | The Circuit Pathways page. Students join a class with a class code; teachers sign in. |
| ArduinoPath | `/arduinopath/` | The whole app in the browser: simulator, Wiring Wizard, Coach, Blocks. **Upload to a real board** from Chrome / Edge. |
| PiPath | `/pipath/` | 27 of the 28 Python activities. **Run on:** the on-screen Simulator (Python runs in the browser) **or My Raspberry Pi** (the program runs on a real Pi that the student links to by its ID). |
| Pi Link | `/pipath/remote/` | Switch a real Raspberry Pi's pins on and off by hand from the browser. Same Pi IDs. |
| Teacher page | `/teacher/` | Make class codes. Save and open class files with students' work. |

On Render, students' names and schools stay in their own browser and in the files they save. The server
stores nothing: no database, no logs of code, no student data. (On Cloudflare, a student who joins a class has their
first name(s), school and work kept with that class until it ends: see the privacy notice in section 6.)

## 2. Put it on Render

1. In Render: **New > Blueprint**, pick the `BNTS_Circuit_Pathways` repository and the branch you want
   live. Render reads `render.yaml` and creates the `circuit-pathways` web service (Docker, **Standard** plan: the
   ESP32 compiler needs about 1.5 GB of memory).
2. When it asks for the secrets, paste the three values from `launch/private/RENDER-ENV.txt`
   (that file is git-ignored; it was made for you with this release):
   - `TEACHER_CODES`: the teacher code(s) you type on the home page.
   - `CLASS_SECRET`: signs class codes. **Never change it** once classes are using codes.
   - `PI_KEY_SECRET`: signs the Pi keys. The 5 test keys only work with this value.
3. The first build takes a long while (about 20 to 40 minutes): it downloads the Arduino compilers
   (~1.5 GB) and compiles once for every board so the first student isn't slow. Later builds reuse a cache.
4. Open `https://<your service>.onrender.com/`. If Render gave the service a different name than
   `circuit-pathways`, tell the Pis (see step 5): `sudo pilink server https://<your-address>`.
5. Optional: add your own domain in Render (for example one under your school's website).

If your Render address isn't `circuit-pathways.onrender.com`, regenerate the Pi installers with the real address:

```
cd launch
PI_KEY_SECRET=<the same value> go run ./cmd/launch -pi-keys 5 -pi-out private/pi -server https://<your-address>
```
(That makes new IDs. To keep the IDs you already have, use `sudo pilink server ...` on each Pi instead.)

## 3. Your first test (about 15 minutes)

1. **Home page** loads. Choose **Teacher: sign in** with your `TEACHER_CODES` value.
2. **Teacher page** opens. Press **Make a class code** (1 term). Copy it.
3. Open a **private window** (so you are a student), go to the home page, type the class code, press **Join class**.
4. **PiPath**: make a profile (first name, school). Pick Beginner. Open **Hello, Pi!**, press **Run**:
   the Output shows `Hello, Pi!` and the checklist ticks. Try **Traffic Lights > Watch the goal**: the LEDs glow.
5. **ArduinoPath**: make a profile. Open **Blink & Traffic Lights**. Run it in the Simulator.
6. **Upload to a real board**: plug in an Uno (or Nano / NodeMCU / ESP32) with a USB data cable, press
   **Upload**, choose the board in the browser's box. First upload of the day can take a minute.
   (Chrome or Edge only. This is the one part not yet tried on real hardware: see "Known limits".)
7. **Settings > My work > Save my work**, close the window, open it again, **Open my work**.
8. On the **Teacher page** add that `.pipath` / `.circuit` file, then **Save class file**.

## 3b. If something looks wrong

- Home page won't load a class code: check `CLASS_SECRET` and `TEACHER_CODES` are set (Render > Environment).
- **PiPath says "Your browser can't run Python here"**: use a recent Chrome or Edge, and open it from the
  site's own address (not an embedded frame). Python needs a page the browser treats as isolated; the server sends the
  headers for that on `/pipath/`.
- **Upload says the compiler is switched off**: the image has no compilers (the build step `launch -setup -warm` failed). Check the Render build log.
- Logs show the method, path, status and time of each API call, and nothing else.

## Free hosting (no payment)

`render.yaml` is the **free** version: Render's free plan and `Dockerfile.free` (no Arduino compilers). Everything works
except **Upload to a real board** (the site says "Compiling is switched off"; the ArduinoPath simulator, PiPath, class
codes, the teacher page and Run on my Pi all work). Limits of a free Render service:

- It **sleeps after 15 minutes** with no visitors and takes about a minute to wake: open the site a few minutes before a class.
- Pis reconnect by themselves after a sleep (the relay keeps nothing). 750 free hours a month; 512 MB memory.
- If Render still asks for a card on **New > Blueprint**, use **New > Web Service** instead (pick the repo and branch,
  Runtime **Docker**, Root Directory `launch`, Dockerfile Path `./Dockerfile.free`, Instance Type **Free**) and add the
  environment variables `CLASS_SECRET`, `TEACHER_CODES`, `PI_KEY_SECRET` by hand (values in `private/RENDER-ENV.txt`).
- When you want uploading to real boards, switch to `render.paid.yaml` (Standard plan, about US$25 a month, the ESP32
  compiler needs 1.5 GB), or run the full `Dockerfile` on a computer you already have.

## A TEST version to share with colleagues

The same site run with `BETA=1`: the **same home page** (PiPath and ArduinoPath) with a **TEST** label, **no Raspberry Pi
linking and nothing saved**. Colleagues open the link, make a pretend profile and try everything a student sees. Closing
or reloading the tab clears it (there are no save files, no "Save my work" or "Download .ino", no autosave to the
browser). Search engines are asked to stay away (`noindex`).

**Beta teacher mode:** a colleague who wants to try classes scrolls down, types **a teacher code they make up** (8 or more
characters, and remembers it) and makes a class code; students join with it. No secret teacher codes are needed.
On Render set a `CLASS_SECRET` (any long random text) too, or class codes stop working whenever the free site sleeps and
restarts. (On the Cloudflare TEST site a student who joins a class also has their work saved to it.)

On Render: **New > Blueprint**, pick this repo and branch, and set **Blueprint file path** to `render.test.yaml` (a second
free service named `circuit-pathways-test`, with its own address; it can run beside the real site). Or by hand:
**New > Web Service**, Runtime Docker, Root Directory `launch`, Dockerfile Path `./Dockerfile.free`, Free, and the
environment variable `BETA` = `1`. That is all that is needed to open it: no teacher codes or other settings (add `CLASS_SECRET` if testers will try classes).
There is no password in the site itself, so anyone with the link can open it (fine for a test; a gateway in front of it is optional).

Upload to a real board is off on the free plan, so colleagues can try everything except real hardware. To let them
upload too, deploy the full `Dockerfile` on a paid instance with `BETA=1`. The test link is open to anyone who has it, so
only share it with people you trust. Try it locally: `go run ./cmd/launch -dev -beta`.

## 4. Set up the Raspberry Pis

The 5 test Pis are in `launch/private/pi/` (git-ignored). `PI-KEYS.md` lists each Pi's **ID**; there is one
installer file per Pi.

For each Pi (Raspberry Pi OS, on the internet):

1. Copy that Pi's `install-pi-XXXX-XXXX.sh` to it (USB stick is fine).
2. In a Terminal on the Pi: `sudo bash install-pi-XXXX-XXXX.sh`.
3. It prints the Pi's ID and starts Pi Link, with **students' programs switched on** (see "Running students' programs on a Pi" below). **It starts by itself every time the Pi turns on.** (With a desktop,
   a small window also shows the ID at start-up. The ID is also in `PI-LINK-ID.txt` on the SD card's boot folder.)
4. Stick the ID on the Pi.
5. In PiPath, open any activity (or Free Play), set **Run on: My Raspberry Pi**, type the ID and press **Link**. Press
   **Run**: the program runs on the Pi and its output appears in the Output box. To try the pins, wire an LED on GPIO 17
   with a 330 ohm resistor and run `from gpiozero import LED` / `LED(17).blink()`; or use the Pi Link page
   (`/pipath/remote/`) and press **Blink an LED**.

**Students using the Pi as their computer** (the Raspberry Pi version): the installer also adds **Circuit
Pathways**, **PiPath** and **ArduinoPath** to the Pi menu (Education) and the desktop. They open the site in Chromium
already linked to that Pi, so PiPath runs programs on it with no ID to type. Work is saved on the Pi, and with the
student's class once they join it (Cloudflare site), so they can carry on on a laptop or at home.

**The Pi beta:** to have students on Pis use the BETA site where a class code is optional (work saved on the Pi,
or synced to their class if they join one), deploy it with `npm run deploy:pi` in `cloudflare/` (see its README), then
make the Pis' installers with `-server https://<the Pi beta address>`. Updating a Pi that's already set up:
`sudo pilink server https://<the Pi beta address>`. Teachers still make classes on either site (same database).
On a small Pi (Zero 2, 3) the first open of PiPath downloads about 12 MB of Python; after that it is cached for a week.

Handy commands on a Pi: `pilink show` (the ID), `pilink status`, `pilink log`, `sudo pilink restart`,
`sudo pilink run on|off`, `sudo pilink server https://new-address`, `sudo pilink uninstall`.

More keys: `PI_KEY_SECRET=... go run ./cmd/launch -pi-keys 20 -pi-out private/pi2 -server https://your-address`.
A lost or stolen Pi: add its ID to `REVOKED_PI_IDS` in Render (comma-separated), and its key stops working.

**If you updated the site after installing a Pi,** write fresh installers for the same keys and run them on the Pis
(running the installer again just updates the Pi; keys and IDs don't change):
`go run ./cmd/launch -pi-refresh private/pi/pi-keys.csv -pi-out private/pi -server https://your-address`.

### Running students' programs on a Pi (what it means, and the limits)

When a student chooses **Run on: My Raspberry Pi**, their Python program travels browser → this site (held in memory
for that one message, never stored or logged) → the Pi, which runs it and sends back what it prints. What the Pi does:

- Runs **one program at a time**, in its own temporary folder (deleted afterwards), as the unprivileged user `cprun`
  (no password, no login, no sudo; it can use the GPIO pins, camera and I²C/SPI). It can't read the Pi's key file, and
  the Pi Link service can only write to its own folder.
- Limits: 10 minutes, 2 GB memory, 10 MB per file, 64 processes, 200 000 characters of output. A program that goes
  over, or whose browser page goes quiet for 25 seconds, or whose Pi loses the site for 10 seconds, is stopped. Stop
  sends Ctrl+C, then a firmer stop, then a kill. Pins the program used are released when it ends.
- While a program runs it owns the pins, so the pin buttons on the Pi Link page are paused.
- A teacher can switch it off for a Pi: `sudo pilink run off` (pins still work), or install with `CP_RUN=no`.

**What this does not do:** the program is real Python on a real computer on your school network. The `cprun` user can
make network connections like any user on that Pi (and so could try to reach other devices). Treat Pis that run
students' programs like any lab computer: put them on the student or guest network, not the staff network. A class
code **and** a Pi's ID are both needed to reach a Pi, and Pi IDs are not secret on the Pi's label, so keep the Pi's
key (in `/etc/circuitpathways-pi.conf`, root only) private and use `REVOKED_PI_IDS` if a Pi goes missing.

## 5. Known limits in v1.0 (honest list)

- **Not yet tried on real hardware:** uploading to real Arduino / ESP boards from the browser, and Pi Link on a real
  Raspberry Pi. Both are covered by automated tests with pretend boards, but a real test with your kit is the first
  thing to do. The ESP8266 / ESP32 upload (esptool) is the least tested.
- **Real compiles** are checked in CI (`launch.yml`), not before the first deploy, because the build machine used to write this has no access to the
  Arduino download site.
- **PiPath:** the Turtle Art activity needs a drawing window, so it is listed but not opened in the browser.
  On **Run on: My Raspberry Pi** the Output, typing answers (`input()`), Stop, the Coach and the lesson checks all
  work, but the on-screen board is replaced by a Pi status panel (the real LEDs and buttons are the board), and
  "Watch the goal" still plays in the Simulator. **Not yet tried on a real Pi** (tested here against the real Pi app
  with pretend pins). A momentary wifi blip can lose a few lines of output (the page says so).
- **Browsers:** Chrome or Edge on a laptop for everything. Safari / Firefox run the simulators but can't upload to boards.
- **Class codes can't be switched off early** (they expire). Use short codes for short programs.
- **Pi Link and Run on my Pi** delay is the round trip to the site (tens to a couple of hundred milliseconds): fine for LEDs, buttons and
  PWM, not for timing-critical parts.
- Render logs visitors' IP addresses, as any host does. Say so in your privacy notice.

## 6. A short privacy notice you can adapt

> Circuit Pathways asks students for a first name and a school name. These stay in the student's own browser and in the
> files the student chooses to save. They are not sent to or kept on our server. When a student uploads code to a
> board, the code is sent to our server to be compiled and is not stored. Our hosting provider records visitors'
> addresses in its normal logs. If a student chooses to run a program on their own Raspberry Pi, the program is sent
> through our server to that Pi and what it prints comes back the same way; it is held in memory for that moment only
> and is not stored. There are no accounts, cookies, advertising or analytics, and no generative AI.

**On the Cloudflare site** (students can join a saved class), adapt this instead:

> Circuit Pathways asks students for a first name and a school name. A student who does not join a class keeps these
> only in their own browser and in the files they choose to save. A student who joins a class (with a class code from
> their teacher) has their first name(s), school and the work they do in Circuit Pathways kept with that class, so
> their teacher can see it and they can carry on on another device. Nothing else about them is kept, and all of it is
> deleted after the class's end date, or sooner if the teacher or the student removes it. Backups kept by our database
> provider may hold deleted information for up to 30 days. When a student uploads code to a board, the code is sent
> to our server to be compiled and is not stored. Our hosting provider records visitors' addresses in its normal logs.
> There are no accounts, cookies, advertising or analytics, and no generative AI.

## 7. Changing things later

- **Edit a PiPath lesson:** change the TOML in `launch/content-pipath/`, run `python3 tools/build_pipath_data.py`, commit.
  (CI checks they match.)
- **Edit ArduinoPath content:** `launch/content/` (projects, boards, errors) and `launch/site/arduinopath/`.
- **Update a deploy:** push to the branch Render watches; it rebuilds. Browsers fetch new files straight away.
