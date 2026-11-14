# AGENTS.md: instructions for AI coding agents (Codex, Claude Code, etc.)

Project: **Circuit Pathways** (PiPath + ArduinoPath), a no-AI coding tutor for secondary students, served by the school's
own Raspberry Pi (the school server) to the school network, and run by each student Pi itself (`docs/server.md`).
**Read `docs/overview.md` first.** Work at the repository root. Older and experimental work (the cloud hosting, the first
laptop app, the offline apps, WastePath, the bin monitor) is on the `drafts` branch, not here.

## Non-negotiable rules
1. **Keep student data to the minimum.** Only first name(s) + school are ever asked. With no class they stay in the
   browser and the student's own save files. A student who joins a class has their first name(s), school and work kept
   with that class on the school server (SQLite, `internal/store`), and all of it is deleted after the class's end date,
   or sooner by the teacher or the student. Nothing else about students, ever, and nothing goes to the internet.
2. **No AI** features, model calls, telemetry, analytics, cookies, accounts, CDN scripts/fonts. Vendor third-party code with its licence.
3. **Strict CSP:** under `site/arduinopath/` and `site/pipath/` there are no inline styles (`style=""`) and no inline scripts. Use CSS files, and
   CSSOM (`el.style.x = ...`) for dynamic values. Plain ES modules, **no build step**.
4. **Secrets never go in git.** The server makes its own (in its data folder). `private/` and `dist/` are git-ignored. Don't print or commit secrets or teacher codes.
5. Student-facing text: plain English, short sentences, ~Year 7 reading level, **Australian spelling**, encouraging ("clues", not "failures").
6. Content is data (JSON/TOML) editable without code. Every lesson step / project step needs a `demo` that passes its own checks.
7. Never break the save-file formats (`.circuit`, `.pipath`, `.circuitclass`) or the database: version and migrate
   (`internal/store` has a schema version).
8. Keep the look: PiPath = Windows 95, ArduinoPath = Windows Vista (BNTS teal `#19C1CA`/`#04BBC1`, purple `#704988`, light purple `#CFC2E0`).
9. Pi app runs students' code: never as root, keep limits, keep the relay whitelist (`internal/pirelay/command.go`) and the Pi app's own checks in step.
10. FidgetCAD is out of scope.

## Commands (run at the repository root)
```
go run ./cmd/circuitpathways -dev                 # the school server on http://localhost:8080, teacher code teacher-code-dev, no compilers
gofmt -l . ; go vet ./... ; go test -race ./...
python3 tools/build_pipath_data.py --check          # run without --check to regenerate after editing content/pipath/
node tools/make_compile_fixtures.mjs --check        # run without --check after changing site/arduinopath/js/webpage.js
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover raspberry-pi
npm ci && npm test
bash tests/pi-server/smoke.sh                       # the school server (https) + a student Pi installed from it, for real
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # starts a dev school server (8543) and a student Pi (8546)
node tools/preflight.mjs http://localhost:8080 --teacher-code teacher-code-dev --no-compile   # is a running server ready for a test day?
```
All must pass before you commit. CI is `.github/workflows/ci.yml`.

## Working agreements
- Branches: **`main`** is the current work (the top-level `README.md` maps the repositories and branches). Work on a branch
  off `main` (a session's `claude/...` branch is fine) and bring `main` up to date when the tests pass. Older work is on
  the `drafts` branch; don't add it back to `main`. Pull before you start; commit small, pushed often, so two agents
  don't collide. Say which files you are touching if you coordinate through the user.
- Don't force-push, rewrite history, or open a PR unless asked.
- Don't run `pkill -f` (it can kill your own shell); use `kill <pid>` or `fuser -k PORT/tcp`.
- Generated files: `site/pipath/data/*.json`, `site/pipath/py/manifest.json` come from `tools/build_pipath_data.py`. Don't hand-edit.
- The installer templates use `<% %>` delimiters (bash `[[ ]]` clashes with Go `{{ }}`). After changing an installer,
  run `bash tests/pi-server/smoke.sh`.
- In shell commands, never nest a heredoc ending in `EOF` inside another `EOF` heredoc: write the file with a tool instead.
- `test-results/`, `node_modules/`, `__pycache__`, `dist/` are not committed.
- Be honest in docs: say what is untested (real boards, a real Pi, the installers under systemd, CI-only jobs).
