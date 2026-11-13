# AGENTS.md: instructions for AI coding agents (Codex, Claude Code, etc.)

Project: **Circuit Pathways** (PiPath + ArduinoPath), a no-AI coding tutor for secondary students, hosted on Render or
Cloudflare (`launch/cloudflare/README.md`).
**Read `launch/docs/PROJECT-OVERVIEW.md` first.** Work in `launch/`. `development/` is the parked earlier version.

## Non-negotiable rules
1. **Keep student data to the minimum.** Only first name(s) + school are ever asked. On the Go/Render site they stay in the
   browser and the student's own save files. On the Cloudflare site (`launch/cloudflare/`), a student who joins a class
   has their first name(s), school and work kept with that class in D1, and all of it is deleted after the class's end
   date (daily clean-up), or sooner by the teacher or the student. Nothing else about students, ever.
2. **No AI** features, model calls, telemetry, analytics, cookies, accounts, CDN scripts/fonts. Vendor third-party code with its licence.
3. **Strict CSP:** under `site/arduinopath/` and `site/pipath/` there are no inline styles (`style=""`) and no inline scripts. Use CSS files, and
   CSSOM (`el.style.x = ...`) for dynamic values. Plain ES modules, **no build step**.
4. **Secrets never go in git.** `launch/private/` is git-ignored (Render env values, Pi keys, installers). Don't print or commit secrets.
5. Student-facing text: plain English, short sentences, ~Year 7 reading level, **Australian spelling**, encouraging ("clues", not "failures").
6. Content is data (JSON/TOML) editable without code. Every lesson step / project step needs a `demo` that passes its own checks.
7. Never break the save-file formats (`.circuit`, `.pipath`, `.circuitclass`): version and migrate.
8. Keep the look: PiPath = Windows 95, ArduinoPath = Windows Vista (BNTS teal `#19C1CA`/`#04BBC1`, purple `#704988`, light purple `#CFC2E0`).
9. Pi app runs students' code: never as root, keep limits, keep the relay whitelist (`internal/pirelay/command.go`) and the Pi app's own checks in step.
10. FidgetCAD is out of scope.

## Commands (run in `launch/`)
```
go run ./cmd/launch -dev                 # http://localhost:8080, teacher code teacher-code-dev, no compilers
gofmt -l . ; go vet ./... ; go test -race ./...
python3 tools/build_pipath_data.py --check          # run without --check to regenerate after editing content-pipath/
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover pi-bridge
npm ci && npm test
CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test   # the app server is started by the config; port E2E_PORT or 8543
```
All must pass before you commit. CI is `.github/workflows/launch.yml`.

## Working agreements
- Branches: **`main`** is the current work (see the top-level `README.md` for the map of repositories and branches). Day-to-day work happens on a `claude/...` branch (this session: `claude/inspiring-hamilton-mfxok0`); when the tests pass, `main` is brought up to date from it. Pull before you start; commit small, pushed often, so two agents don't collide. Say which files you are touching if you coordinate through the user.
- Don't force-push, rewrite history, or open a PR unless asked.
- Don't run `pkill -f` (it can kill your own shell); use `kill <pid>` or `fuser -k PORT/tcp`.
- Generated files: `site/pipath/data/*.json`, `site/pipath/py/manifest.json` come from `tools/build_pipath_data.py`. Don't hand-edit.
- The Pi installer template uses `<% %>` delimiters (bash `[[ ]]` clashes with Go `{{ }}`).
- `test-results/`, `node_modules/`, `__pycache__` are not committed.
- Be honest in docs: say what is untested (real boards, a real Pi, CI-only jobs).
