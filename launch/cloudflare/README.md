# Circuit Pathways on Cloudflare

The whole site runs on Cloudflare Workers. Everything a student loads (both apps, Python, the
simulators) is served from Workers static assets, which are free and unlimited. A small Worker
answers the rest. Its parts are:

| Part | What it does | Where |
|---|---|---|
| Saved classes | Teachers make classes. Students join with the class code, their **first name(s)** and **school**. Their **work** (code, progress, settings) syncs to the class. | D1 database (`migrations/`) |
| Clean-up | Every day, classes that have ended are deleted with their students and work. | Cron trigger in `wrangler.jsonc` |
| Pi relay | Links a student's browser to their Raspberry Pi, for Run on my Pi and Pi Link. | A Durable Object per Pi, with hibernating WebSockets |
| Compiling | Upload to a real Arduino/ESP board needs a compiler. The Worker passes compiles on to a separate compiler (`COMPILE_URL`). | The Docker image (`launch/Dockerfile`) on Render, a school PC or a Pi 5 |

Everything fits Cloudflare's **free plan**, except the compiler, which runs elsewhere.

## What is kept, and for how long

- About a student: only their first name(s) and school, as they type them when they join. Their
  work is kept with them. Nothing else: no email, password, address, IP address or analytics. The
  Worker never logs request bodies.
- About a teacher: nothing. Their classes are kept under a fingerprint of their teacher code, never
  the code itself.
- **Removal:**
  - A class, its students and their work are deleted by the daily clean-up after the class's end
    date. The teacher picks the date, at most about 13 months ahead.
  - A teacher can delete a class, or one student, at any time.
  - A student can take their own name and work off a class (home page > Take my name off the class).
- D1 keeps an automatic backup history ("Time Travel") for 7 days on the free plan and 30 days on
  paid plans. Deleted rows can be restored by the account owner during that window, and are gone
  after it. Say so in your privacy notice.
- Students still keep their own save files (`.circuit` / `.pipath`). A file from a class member
  carries the class link, so opening it on another device (such as a Raspberry Pi) joins that
  device's profile to the class.

## Set it up (once)

You need a Cloudflare account (free), Node 22 and Go 1.24.

```bash
cd launch/cloudflare
npm ci
npx wrangler login
npx wrangler d1 create circuit-pathways        # copy the database_id it prints into wrangler.jsonc
npx wrangler secret put CLASS_SECRET            # a long random text; never change it once classes exist
npx wrangler secret put TEACHER_CODES           # each teacher's own code (8+ characters), separated by commas
npx wrangler secret put PI_KEY_SECRET           # the same value as the Render site, so your Pi keys keep working
npm run deploy                                  # builds dist/, updates the database, deploys
```

Optional, for uploading to real boards:

```bash
npx wrangler secret put COMPILE_URL             # e.g. https://circuit-pathways.onrender.com (the Docker server)
npx wrangler secret put COMPILE_KEY             # a long random text; set the same COMPILE_KEY on that server
```

To deploy from GitHub instead, add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as repository
secrets. Then run **Actions > Deploy to Cloudflare**.

**The TEST site** (`npm run deploy:test`, or the same Action with "test") is the BETA version: anyone can use the
apps with no code, and nothing is saved on the computer. It has **beta teacher mode**: a teacher types **a teacher
code they make up** (8+ characters) on the home page and makes a class, and students join it with the class code.
A student in a class has their work saved to the class (in the TEST database), so it comes back after a reload.
Create its own database first (`npx wrangler d1 create circuit-pathways-test`), put that id in the `test` section
of `wrangler.jsonc`, and set its `CLASS_SECRET` (`npx wrangler secret put CLASS_SECRET --env test`).

**The Pi beta site** (`npm run deploy:pi`, or the same Action with "pi") is for students using Raspberry Pis.
It is the real site, marked BETA, where **a class code is optional**, and where teachers can also make up their
own teacher code (beta teacher mode, as on the TEST site) as well as using the school's `TEACHER_CODES`:

- With no code, a student starts straight away and their work is saved **on that Pi only** (in its browser).
- With a class code (and their first name(s) and school), their work **also syncs to the class database**, so
  the teacher sees it and it follows them to any device. Work they did before joining is sent up the next
  time they open the app.
- The Pi relay, Run on my Pi, the installers and the teacher page are all on. Uploading to a board and
  linking a Pi work without a class code too (still rate limited).

It uses the **same D1 database as the real site** (put the same `database_id` in the `pi` section of
`wrangler.jsonc`), so a class a teacher makes on one site is the class students join on the other. Give it
the same secrets, once, with `--env pi`:

```bash
for s in CLASS_SECRET TEACHER_CODES PI_KEY_SECRET COMPILE_URL COMPILE_KEY; do npx wrangler secret put $s --env pi; done
```

Then point the Pis at it: `sudo pilink server https://circuit-pathways-pi.YOUR-NAME.workers.dev` on each Pi, or
make fresh installers with `launch -pi-refresh ... -server <that address>` (see LAUNCH.md).

**Each teacher has their own code.** Their classes belong to that code. If a teacher's code is
removed from `TEACHER_CODES`, they can't sign in any more, and their classes are deleted when they end.

## Raspberry Pis

Pis link over WebSockets here. Pi app 0.2.0+ does this by itself, and still works with the Go site.
Re-run each Pi's installer (made with `launch -pi-refresh`) to update older Pis. Set it to this
site's address: `sudo pilink server https://your-site`.

**The Raspberry Pi version** (students using a Pi as their computer): the installer also puts
**Circuit Pathways**, **PiPath** and **ArduinoPath** in the Pi menu (Education) and on the desktop.
They open this site in Chromium as an app window with `?pi=<this Pi's ID>`, so:

- PiPath runs students' programs on that Pi straight away (Run on: My Raspberry Pi), with no ID to type.
- Work is saved in Chromium on the Pi, like on a laptop. Once the student joins a class (class code,
  first name(s), school) it also syncs to the class in D1, so it's the same work on the Pi, a laptop
  or at home. Save files (`.pipath`, `.circuit`) remember the class, so opening one on another
  device links that device too.
- ArduinoPath uploads to boards from the Pi with Web Serial (Linux has the USB drivers built in).

`CP_DESKTOP=no` skips the shortcuts. `circuitpathways pipath` opens PiPath from a terminal.

## Develop and test

```bash
cp .dev.vars.example .dev.vars
npm run dev          # http://localhost:8787, teacher code teacher-code-dev
npm test             # the Worker's API, classes and Pi relay against a local Worker, D1 and the real Pi app
```

`npm test` and the browser test (`launch/tests/e2e/cloudflare.spec.js`) run Cloudflare's own runtime
(workerd) on this computer. They have not been run against a real Cloudflare account: try the
first deploy on the TEST site.
