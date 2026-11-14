# Cloud hosting (Cloudflare and Render): parked

Circuit Pathways was hosted on the internet before it moved onto the school's own Raspberry Pi (November 2026).
This folder keeps everything that was only for hosting it publicly, exactly as it was on `main` at commit
**`bd484de`** ("Pi relay: always send to the Pi's newest open connection"), where it all passed CI.

| What | Where it was |
|---|---|
| The Cloudflare Worker: static site, classes in D1, Pi relay over WebSockets (Durable Objects), compile proxy, tests | `cloudflare/` |
| Render and Docker: the Go server with the compilers in an image | `Dockerfile`, `Dockerfile.free`, `.dockerignore`, `render*.yaml`, `docs/deploy-render.md` |
| The deploy button | `.github/workflows/cloudflare-deploy.yml` (and the old `ci.yml`, with the Worker tests and the image job) |
| The three "editions": the real site, the Pi beta, the TEST version (beta teacher mode, made-up teacher codes) | `site/shared/beta.js`, `site/shared/access.js`, `cmd/circuitpathways/main.go` (`-beta`), `tests/e2e/*` |
| Stateless class codes (signed, no database) and Pi keys made for a public site (`-pi-keys`, `-pi-refresh`) | `internal/classes/`, `cmd/circuitpathways/pikeys.go`, `export.go` (the `-export` for Cloudflare) |
| The docs and the preflight for those sites | `docs/`, `tools/preflight.mjs`, the old `README.md` and `AGENTS.md` |

## Why it was parked

The teacher chose a school server they control: one main Raspberry Pi serves the site, the classes (SQLite) and the
compiler to every computer on the school network, and each student Pi runs the site itself so it works offline.
That is `main` now (see its `docs/server.md`). The classes API on `main` is the same as the Worker's (the same
requests, answers and limits), so the pages didn't change.

## Bringing it back

Check out `bd484de` (or copy these files back), then follow `cloudflare/README.md` or `docs/deploy-render.md`. The
newer work on `main` (set work, the school server, student Pis) isn't in this copy.
