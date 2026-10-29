# Launching Circuit Pathways v1.0 on Render

This is the checklist for putting the site live and trying it yourself. It assumes the branch
has been merged (or Render is pointed at this branch).

## 1. What you are launching

| Part | Where | What it does |
|---|---|---|
| Home page | `/` | The Circuit Pathways page. Students join a class with a class code; teachers sign in. |
| ArduinoPath | `/arduinopath/` | The whole app in the browser: simulator, Wiring Wizard, Coach, Blocks. **Upload to a real board** from Chrome / Edge. |
| PiPath | `/pipath/` | 24 of the 25 Python activities, with an on-screen Raspberry Pi. Python runs in the browser. |
| Pi Link (beta) | `/pipath/remote/` | Control a real Raspberry Pi's pins from the browser. Each Pi has its own key. |
| Teacher page | `/teacher/` | Make class codes. Save and open class files with students' work. |

Students' names and schools stay in their own browser and in the files they save. The server
stores nothing: no database, no logs of code, no student data.

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

## 4. Set up the Raspberry Pis

The 5 test Pis are in `launch/private/pi/` (git-ignored). `PI-KEYS.md` lists each Pi's **ID**; there is one
installer file per Pi.

For each Pi (Raspberry Pi OS, on the internet):

1. Copy that Pi's `install-pi-XXXX-XXXX.sh` to it (USB stick is fine).
2. In a Terminal on the Pi: `sudo bash install-pi-XXXX-XXXX.sh`.
3. It prints the Pi's ID and starts Pi Link. **It starts by itself every time the Pi turns on.** (With a desktop,
   a small window also shows the ID at start-up. The ID is also in `PI-LINK-ID.txt` on the SD card's boot folder.)
4. Stick the ID on the Pi.
5. In PiPath, open **Link to a Raspberry Pi (beta)** (or `/pipath/remote/`), type the ID, press **Link to my Pi**,
   and switch a pin. Wire an LED on GPIO 17 with a 330 ohm resistor, press **Blink an LED**.

Handy commands on a Pi: `pilink show` (the ID), `pilink status`, `pilink log`, `sudo pilink restart`,
`sudo pilink server https://new-address`, `sudo pilink uninstall`.

More keys: `PI_KEY_SECRET=... go run ./cmd/launch -pi-keys 20 -pi-out private/pi2 -server https://your-address`.
A lost or stolen Pi: add its ID to `REVOKED_PI_IDS` in Render (comma-separated), and its key stops working.

## 5. Known limits in v1.0 (honest list)

- **Not yet tried on real hardware:** uploading to real Arduino / ESP boards from the browser, and Pi Link on a real
  Raspberry Pi. Both are covered by automated tests with pretend boards, but a real test with your kit is the first
  thing to do. The ESP8266 / ESP32 upload (esptool) is the least tested.
- **Real compiles** are checked in CI (`launch.yml`), not before the first deploy, because the build machine used to write this has no access to the
  Arduino download site.
- **PiPath:** the Turtle Art activity needs a drawing window, so it is listed but not opened in the browser.
  "Real Pi" mode in PiPath's workspace is the separate Pi Link page for now; it doesn't yet run a student's
  program on a real Pi.
- **Browsers:** Chrome or Edge on a laptop for everything. Safari / Firefox run the simulators but can't upload to boards.
- **Class codes can't be switched off early** (they expire). Use short codes for short programs.
- **Pi Link** delay is the round trip to the site (tens to a couple of hundred milliseconds): fine for LEDs, buttons and
  PWM, not for timing-critical parts.
- Render logs visitors' IP addresses, as any host does. Say so in your privacy notice.

## 6. A short privacy notice you can adapt

> Circuit Pathways asks students for a first name and a school name. These stay in the student's own browser and in the
> files the student chooses to save. They are not sent to or kept on our server. When a student uploads code to a
> board, the code is sent to our server to be compiled and is not stored. Our hosting provider records visitors'
> addresses in its normal logs. There are no accounts, cookies, advertising or analytics, and no generative AI.

## 7. Changing things later

- **Edit a PiPath lesson:** change the TOML in `launch/content-pipath/`, run `python3 tools/build_pipath_data.py`, commit.
  (CI checks they match.)
- **Edit ArduinoPath content:** `launch/content/` (projects, boards, errors) and `launch/site/arduinopath/`.
- **Update a deploy:** push to the branch Render watches; it rebuilds. Browsers fetch new files straight away.
