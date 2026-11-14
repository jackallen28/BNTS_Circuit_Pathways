# The school server: Circuit Pathways on your own Raspberry Pi

Circuit Pathways runs on **one main Raspberry Pi at school** (the *school server*). Every computer on the school
network opens it in Chrome or Edge. Nothing goes to the internet, and you control it all.

```
                        ┌──────────────────────────── school network ────────────────────────────┐
  laptops (Chrome/Edge) │  https://pathways.local ──▶  SCHOOL SERVER (main Pi)                     │
   - PiPath (Python,    │                              - the site (PiPath, ArduinoPath, home page)  │
     on-screen Pi)      │                              - classes, set work, students' work (SQLite) │
   - ArduinoPath +      │                              - the compiler for uploading to boards       │
     upload over USB    │                              - the teacher portal                         │
   - teacher portal     │                              ▲                                            │
                        │                              │ classes, work, compiling (https)           │
  student Pis           │  each runs Circuit Pathways itself (http://localhost:8080):              │
   - PiPath on real pins│   - works with no network (work saved on the Pi)                         │
   - ArduinoPath + USB  │   - Pi Link: PiPath runs programs on this Pi's own pins                  │
                        └──────────────────────────────────────────────────────────────────────────┘
```

| Who | Opens | What they get |
|---|---|---|
| **Students on laptops** | `https://pathways.local` | PiPath (Python in the browser, on the on-screen Pi) and ArduinoPath (simulator, and Upload to a board on USB). No GPIO: that is for student Pis. |
| **Students on student Pis** | The Pi menu or desktop: **Circuit Pathways**, **PiPath**, **ArduinoPath** | The same apps, served by the Pi itself, so they work even when the network is down. PiPath runs programs on the Pi's real pins. Work goes to their class whenever the school server can be reached. |
| **Teachers** | `https://pathways.local`, then **Teacher sign in** | The teacher portal: make classes, set work, see each student's progress and code, download everyone's work, end or delete a class. |

## What you need

- **The school server:** a Raspberry Pi 4 or 5 with **4 GB or more** (8 GB is comfortable for 30 students uploading),
  a good microSD card or (better) a USB SSD, **64-bit Raspberry Pi OS** (Lite is fine), a wired network connection if
  you can, and **the internet once**, to download the board tools (about 1.5 GB).
- **Student Pis:** any Pi 3, 4, 5 or Zero 2 W with **64-bit Raspberry Pi OS with the desktop**, on the same network.
- **Laptops:** Chrome or Edge, on the same network.
- **The download:** `circuitpathways-pi-VERSION.tar.gz` (from the repository's **Releases**, or make it yourself with
  `bash tools/build-pi.sh` on any computer with Go 1.24).

## 1. Set up the school server (once, about 30 minutes)

Copy the download to the Pi (a USB stick is fine), then in a Terminal on the Pi:

```bash
tar xzf circuitpathways-pi-*.tar.gz
```

```bash
cd circuitpathways-pi && sudo bash install-server.sh
```

It:

1. names the Pi **pathways**, so every computer can find it as **pathways.local** (`CP_HOSTNAME=keep` leaves the name);
2. installs Circuit Pathways as a service that starts with the Pi (it runs as its own user, `circuitpathways`);
3. downloads the board tools for uploading to Arduino and ESP boards (`CP_TOOLS=no` skips this);
4. makes the server's own https certificate and the **first teacher code**, and prints them.

Write down the teacher code. Settings go after `sudo`, for example
`sudo CP_SCHOOL="Eltham High School" CP_TEACHER="Ms Lee" bash install-server.sh`.

**Give the server a fixed address.** Ask IT for a DHCP reservation for the Pi (or a DNS name). `pathways.local` works on
most networks (Windows 10/11, Macs, Chromebooks and Pis all look up `.local` names), but some school networks block it:
then use the Pi's address, such as `https://10.20.1.5`. The certificate covers the Pi's name and all its addresses, and
is made again by itself if the address changes.

## 2. Set up each laptop (once, about a minute)

Uploading to a board (Web Serial) and Python programs that wait for input (shared memory) only work on a **secure**
address, and the school server's certificate is its own. So each laptop trusts it once:

- **A student or teacher:** open **`http://pathways.local/trust`** and follow the steps there (Windows: install the
  certificate for the **Current User**, no administrator needed; Mac; Chromebook). Then use `https://pathways.local`.
- **IT, for every laptop at once:** deploy `http://pathways.local/ca.crt` to the **Trusted Root Certification Authorities**
  store (Intune or Group Policy; the Google Admin console for Chromebooks). The certificate can only vouch for `.local`
  names and private network addresses (name constraints), so it can't be used to pretend to be a real website.
  *Or* set the Chrome/Edge policy `OverrideSecurityRestrictionsOnInsecureOrigin` to `http://pathways.local`.

Without this, everything else still works on `http://pathways.local`, and the home page says what to do.

USB drivers for clone boards (CH340, CP2102) on Windows are still IT's job; boards with built-in USB need none.

## 3. Set up each student Pi (once, about 2 minutes)

With the school server on, in a Terminal on the student Pi:

```bash
curl -fsSL http://pathways.local/install/student-pi.sh | sudo bash
```

It downloads Circuit Pathways from the school server, installs it as a service on `http://localhost:8080` (only this
Pi can open it), installs **Pi Link** (PiPath's programs on this Pi's pins, run as an unprivileged user with limits),
and adds **Circuit Pathways**, **PiPath** and **ArduinoPath** to the Pi menu and desktop.
Options go after `sudo`: `CP_NAME="Pi 7"` (a label, no student names), `CP_RUN=no` (pins only, no students' programs),
`CP_TOOLS=yes` (the board tools on this Pi too, so uploading works even offline; 1.5 GB).

**Double-click to open:** the **Circuit Pathways** icon on the student Pi's desktop opens straight into the app (no
"Execute?" question: the installer sets the Pi's file manager to run shortcuts on a double-click). Just after the Pi
starts, it waits a moment for Circuit Pathways to be ready.

**Offline:** if the school server can't be reached, students carry on. Their work is saved on the Pi, the home page says
the server can't be reached, and everything goes to their class when it can. Joining a class and uploading (without
`CP_TOOLS=yes`) need the server.

On a Pi, ArduinoPath uploads through Chromium. If it can't open the USB port:
`sudo usermod -aG dialout <username>`, then log out and in.

## The school's ESP boards (unique WiFi for each board)

ESP boards (NodeMCU, D1 mini, ESP32...) make their own WiFi in the WiFi projects. So that one student's phone can't
join (or control) another student's board, each of the school's boards gets **its own WiFi name and password**, and
ArduinoPath only uploads to a student's **own** board.

1. In the **teacher portal**, under **3. ESP boards**, pick the board type and a label (the next free one, such as
   `ESP-01`, is filled in), plug the board into your laptop, and press **Plug it in, then set it up**. (Use the secure
   address, `https://pathways.local`, in Chrome or Edge.) The portal asks the server for the board's WiFi name (such as
   `CP-ESP01-K3QX`), a random password and a sticker code, compiles a small set-up sketch, uploads it, and records the
   board's chip (its MAC address). The board then makes its WiFi straight away, so you can check it with a phone.
2. Write the label on the board, and **Print stickers** (the label, the code and the WiFi name; no password).
3. A student (in one of your classes) opens **ArduinoPath > Settings > My ESP board** and types the code on the
   sticker. That board is theirs: Settings shows its WiFi name and password, which ArduinoPath puts in their code (the
   `#define MY_WIFI_NAME` and `MY_WIFI_PASSWORD` lines; a hotspot with any other name is changed to the board's), and
   **Upload** reads the chip of the board that's plugged in and stops if it isn't theirs ("This isn't your board").
4. When a student leaves the class (or the class ends), their board is free for someone else. **Free it** gives a board
   back by hand; **Flash again** sets it up again (its WiFi doesn't change).

Students without a class (or a school board) get a WiFi name and password made just for their browser, so two boards
still never share one. Boards belong to the teacher who set them up, and only that teacher's students can claim them.
The check is in ArduinoPath, so it stops mistakes and casual borrowing; a student who flashed a board with other
software (the Arduino IDE) could still change it.

## Teachers and classes

- **Teacher codes** are kept on the server. Add one per teacher:

  ```bash
  sudo circuitpathways teacher add "Ms Lee"
  ```

  It prints a new code such as `comet-maple-reef-42`. `sudo circuitpathways teacher list` shows them;
  `sudo circuitpathways teacher remove CODE` takes one away (that teacher's classes can no longer be opened). Changes
  work at once.
- In the **teacher portal**: make a class (a name, the school, an end date), give students the class code, **set work**
  (projects and activities in order, with a note), and watch **progress** (✓ finished, *n/N* steps, · opened).
  **See work** shows a student's code; **Download everyone's work** saves it all as files.
- **Students** join on the home page with the class code, then their **first name(s)** and **school**. A class code is
  optional: without one, work is saved in the browser only.

## What is kept, where, and for how long

- On the school server, in `/var/lib/circuitpathways/pathways.db` (SQLite): classes, the work set for them, and for each
  student who joins, their **first name(s)**, **school**, and **work** (code, progress, settings). Nothing else about
  students, ever: no accounts, no passwords, no addresses in the logs.
- **Everything in a class is deleted** after its end date (checked every few hours), or sooner when the teacher deletes
  the class or a student takes their name off it. Deleted work is wiped from the file (`secure_delete`, and the file is
  compacted).
- In each browser (and on each student Pi): the student's own work, as before. **Save my work** makes a file to keep.
- **Backups:** `sudo circuitpathways backup /home/pi/pathways-backup.db` copies everything (it holds names: keep it
  private). Copy it off the Pi if you need a backup.
- **End of a program:** `sudo circuitpathways wipe` deletes every class, student and piece of work (teacher codes stay).

## Looking after it

| To | Run (on the school server) |
|---|---|
| See how it's going | `sudo circuitpathways status` and `systemctl status circuitpathways` |
| See its log | `journalctl -u circuitpathways -n 50` (requests show method, path, status and time only) |
| Restart it | `sudo systemctl restart circuitpathways` |
| Check it's ready (from any computer with Node 18+) | `node tools/preflight.mjs http://pathways.local --teacher-code CODE` |
| Update it | It updates itself each time it starts (see **Updates** below). By hand: copy the new download over and run `sudo bash install-server.sh` again (classes and codes are kept) |
| Install or repair the board tools | `sudo -u circuitpathways circuitpathways -setup -warm -tools /opt/circuitpathways`, then restart |
| The certificate's fingerprint | `sudo circuitpathways certificate` |

## Updates (every time a Pi starts)

- **The school server** updates itself from the newest **GitHub release** each time it starts (the
  `circuitpathways-update` service, before Circuit Pathways starts). A release is made by **Actions > Release**, or by
  itself when `VERSION` changes on `main`. While the repository is **private**, the server needs a read-only token:
  make a *fine-grained personal access token* on GitHub with **Contents: Read-only** for this repository only, then on the
  server:

  ```bash
  echo "github_pat_..." | sudo tee /etc/circuitpathways/update-token > /dev/null && sudo chmod 600 /etc/circuitpathways/update-token
  ```

  (or give it at install: `sudo CP_UPDATE_TOKEN=github_pat_... bash install-server.sh`). No internet, or no token: it
  starts the version it has, and says why in `journalctl -u circuitpathways-update`. `CP_UPDATES=no` switches it off.
- **Each student Pi** updates itself from the school server each time it starts (over https, checked against the
  program's SHA-256), and refreshes its Pi Link app. So after the school server updates, every student Pi has the same
  version the next time it starts. With no network it starts the version it has.
- A new program is only used when its checksum matches, and it replaces the old one in one step. Classes, work and
  settings are never touched by an update.

The server listens on ports 80 (the plain address: the trust page, the student Pi installer, and the site) and 443 (the
secure address). It needs no inbound access from the internet, and makes no outbound requests except when you install
the board tools.

## Try it on a computer first (no Pi)

```bash
go run ./cmd/circuitpathways -dev
```

That's the school server on http://localhost:8080 (teacher code `teacher-code-dev`, a fresh data folder each time).
`localhost` counts as a secure address, so uploading and Python work. With https too:

```bash
go run ./cmd/circuitpathways -dev -http :8080 -https :8443
```

A student Pi beside it (on the same computer):

```bash
go run ./cmd/circuitpathways -dev -mode student-pi -addr :8090 -school http://localhost:8080
```

`bash tests/pi-server/smoke.sh` does all of this for real (a school server with https, a student Pi installed from
it with its Pi Link, the preflight, and the server going away) and checks every step.

## How it works (for whoever changes the code)

- `cmd/circuitpathways`: the program. `-mode school` (the default) or `-mode student-pi`; the `teacher`, `status`,
  `backup`, `wipe`, `certificate`, `pi-key`, `pi-installer`, `pi-app` and `self-update` commands; `-setup` for the board tools.
- ESP boards: `internal/store/boards.go`, `internal/server/boards.go`, `internal/setup/board.go` (the set-up sketch),
  `site/teacher/boards.js` (flashing from the portal), `site/arduinopath/js/myboard.js` (the student's board, its WiFi
  in their code, and the chip check on Upload, in `js/flash/esp.js`).
- `internal/server`: the site and API. `classes.go` (teachers, classes, set work, students' work), `upstream.go` (a
  student Pi passing classes and compiles to the school server, and noticing when it's gone), `install.go` (the student Pi
  installer, the program and the certificate), `compile.go`, `pi.go` (the Pi Link relay).
- `internal/store`: SQLite (pure Go, no cgo), with a schema version (3: classes, set work, boards). `internal/auth`: teacher and student tokens
  (HMAC-signed with the server's own secret in its data folder) and the teacher codes file. `internal/tlsca`: the
  server's own certificate authority and certificate. `internal/setup`: the installers.
- The pages are unchanged from the hosted versions: the classes API is the same (see the `drafts` branch,
  `draft/cloud-hosting/`, for the Cloudflare and Render versions it replaced).
- Security: writes need the `X-Circuit-Pathways` header (no cross-site requests); strict CSP; every input validated; a
  student's token only reaches their own work, a teacher's only their own classes; sign-in, joining and compiling are
  rate limited by address; no proxy headers are trusted.
