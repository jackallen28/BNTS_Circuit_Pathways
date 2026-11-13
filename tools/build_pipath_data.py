#!/usr/bin/env python3
"""Turns PiPath's teacher-editable TOML (content/pipath/) into the JSON the website loads
(site/pipath/data/). Run it after editing a lesson:

    python3 tools/build_pipath_data.py          # write the JSON
    python3 tools/build_pipath_data.py --check  # fail if the JSON is out of date (CI)

Each lesson step gets the same defaults PiPath's own loader gives it, so the browser and
the Pi version read lessons the same way.
"""
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "pipath"
OUT = ROOT / "site" / "pipath" / "data"


def load(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def lesson(pid):
    les = load(SRC / "lessons" / f"{pid}.toml")
    for i, step in enumerate(les.get("steps", [])):
        step.setdefault("id", f"step{i + 1}")
        step.setdefault("support", "scaffolded")
        step.setdefault("starter_mode", "keep")
        step.setdefault("checks", [{"type": "runs_ok", "label": "Your program runs"}])
        step.setdefault("hints", [])
        step.setdefault("error_hints", {})
    return les


def build():
    out = {}
    cat = load(SRC / "catalog.toml")
    out["catalog.json"] = {"tiers": cat.get("tier", []), "projects": cat.get("project", [])}
    out["config.json"] = load(SRC / "config.toml")
    out["errors.json"] = load(SRC / "errors.toml").get("error", [])
    out["freeplay.json"] = load(SRC / "freeplay.toml")
    for p in cat.get("project", []):
        if (SRC / "lessons" / f"{p['id']}.toml").exists():
            out[f"lessons/{p['id']}.json"] = lesson(p["id"])
    return {k: json.dumps(v, indent=1, ensure_ascii=False, sort_keys=True) + "\n" for k, v in out.items()}


def demo_manifest():
    """The files lessons copy next to the student's program (site/pipath/data/demo_files)."""
    base = OUT / "demo_files"
    files = sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file() and p.name != "manifest.json")
    return json.dumps({"files": files}, indent=1) + "\n"


def py_manifest():
    """The Python files the browser loads into Pyodide (site/pipath/py)."""
    base = ROOT / "site" / "pipath" / "py"
    files = sorted(str(p.relative_to(base)) for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return json.dumps({"files": files}, indent=1) + "\n"


def main():
    files = build()
    files["../py/manifest.json"] = py_manifest()
    files["demo_files/manifest.json"] = demo_manifest()
    if "--check" in sys.argv:
        stale = [k for k, v in files.items() if not (OUT / k).exists() or (OUT / k).read_text() != v]
        if stale:
            sys.exit("out of date (run tools/build_pipath_data.py): " + ", ".join(stale))
        print(f"{len(files)} files up to date")
        return
    for k, v in files.items():
        p = OUT / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    print(f"wrote {len(files)} files to {OUT}")


if __name__ == "__main__":
    main()
