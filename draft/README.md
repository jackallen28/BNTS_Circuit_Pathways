# Drafts

Older and experimental work, kept for reference or to pick up again later. Each folder is a copy of a working tree
(source and docs, no build output or zip files) taken on **13 November 2026**. The full history of each stays in the
GitHub repository it came from, named below.

| Folder | What it is | Came from | State |
|---|---|---|---|
| [`laptop-app-circuitpath/`](laptop-app-circuitpath/) | The first Circuit Pathways: **CircuitPath.exe / .app**, an app installed on each student laptop (Go + SQLite, served on localhost), plus the showcase website with its walkthrough videos. The website replaced it. | `BNTS_Circuit_Pathways`, folder `development/` on the old working branch | Parked. Its ideas (Wiring Wizard, simulator, Coach, WIPE page) are all in the website now. |
| [`offline-pipath/`](offline-pipath/) | **PiPath** installed on a Raspberry Pi (Python and Tk, no internet needed), with a Windows 95 look | `BNTS_PIPath`, branch `main` (commit `bc7b3b2`) | Worked. The website's PiPath runs the same lessons and the same Coach in the browser, so use that unless a Pi has no internet. |
| [`offline-arduinopath/`](offline-arduinopath/) | **ArduinoPath** installed on a Windows laptop, Mac or Raspberry Pi (Go, no internet needed), version 1.0.1 | `BNTS_ArduinoPath`, branch `main` (commit `d480189`) | Worked. Ready for its first real hardware test. The website's ArduinoPath replaces it. Its teacher guide and hardware checklist are good starting points for the website's. |
| [`wastepath/`](wastepath/) | **WastePath**: a Raspberry Pi waste-sorting bin with a camera that learns (ML Camera), GPIO and a servo lid. Two lines of work, both kept. | `BNTS_PIPath`, branches `claude/funny-carson-uahysa` (0.4.1, commit `f56750c`) and `test-wastepath-gpio` (0.3.0) | Experimental. 0.4.1 (27 Oct) adds automatic bin set-up. 0.3.0 (28 Oct) goes back to the original ML Camera workflow. Needs a real Pi and bin to finish testing. |
| [`bin-monitor/`](bin-monitor/) | The **bin monitor**: an Uno bin controller, a C3 Wi-Fi bridge, a live dashboard and wiring drawings | `BNTS_ArduinoPath`, branch `bin-monitor` (commit `b11df98`) | Experimental. A runnable prototype with browser captures. Hardware checks listed in its README are still open. |
| [`cloud-hosting/`](cloud-hosting/) | **Circuit Pathways on the internet**: the Cloudflare Worker (classes in D1, Pi relay), Render and Docker, the TEST and Pi beta editions, and their docs | `BNTS_Circuit_Pathways`, branch `main` (commit `bd484de`, 14 Nov 2026) | Parked when Circuit Pathways moved onto the school's own Raspberry Pi server. Passed CI as it was. |

## Not copied

These branches still exist in the old repositories and were left there: in `BNTS_ArduinoPath`, `arduinopath`,
`hardware-ready`, `showcase`, `wip/circuit-renderer`, `wip/simulator`, `wip/workspace` and
`sandbox/bin-monitor-preview-20261027` (an earlier copy of the bin monitor); in `BNTS_PIPath`, `pipath-waste-sorting`.
They are older stages of the same work. The `jackallen` repository also holds old copies (branches `BNTS_CircuitPath`
and `BNTS_PiPath`) and unrelated projects.

## Bringing something back to the product

Copy it into `main` in the right place (see the README on `main`), make it pass `AGENTS.md`'s rules (no AI, no
CDN files, strict CSP, Australian spelling), and add tests. WastePath and the bin monitor would most naturally
become PiPath and ArduinoPath projects, with a Wiring Wizard and a `demo` for every step.
