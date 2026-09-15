#!/usr/bin/env python3
"""E14 delivery check (spec section 3). Zero sessions.

docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md

Installs each E14 draft ALONE through the real save_skill.py into a sandboxed
HOME and project, runs the plugin's prompt hook (from `git archive HEAD`) on
the task's author prompt, and records whether that draft was delivered. All
four must be. delivery.json freezes each draft's sha256, and the batch script
refuses to start if a draft changed since. Run from the repo root:

    python3 bench/e14_deliver.py --write          # check and record
    python3 bench/e14_deliver.py --check-frozen   # batch guard
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import libguard                                                   # noqa: E402
from e13_qualify import _install, _sandbox                         # noqa: E402
from e14_read import CELLS, TASK, draft_name                       # noqa: E402
from real_path_check import delivered, export_scripts              # noqa: E402

DRAFTS = ROOT / "bench" / "drafts" / "E14"
RECORD = DRAFTS / "delivery.json"


def draft_path(cell):
    return DRAFTS / (draft_name(cell) + ".md")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def gate(rows):
    return len(rows) == len(CELLS) and all(r["delivered"] for r in rows)


def stale(record, root):
    """Cells whose draft is missing or changed since `record` was written."""
    out = []
    for r in record["drafts"]:
        p = pathlib.Path(root) / r["path"]
        if not p.is_file() or sha256(p) != r["sha256"]:
            out.append(r["cell"])
    return out


def check_frozen():
    if not RECORD.is_file():
        print("FATAL: %s missing -- run bench/e14_deliver.py --write" % RECORD.relative_to(ROOT))
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if not gate(record["drafts"]):
        print("FATAL: delivery.json records a draft that was not delivered")
        return 1
    changed = stale(record, ROOT)
    if changed:
        print("FATAL: draft(s) changed since delivery.json: %s" % ", ".join(changed))
        return 1
    print("drafts frozen: all %d delivered, none changed" % len(record["drafts"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write bench/drafts/E14/delivery.json")
    ap.add_argument("--check-frozen", action="store_true",
                    help="exit 1 unless delivery.json passes and no draft changed")
    args = ap.parse_args(argv)
    if args.check_frozen:
        return check_frozen()
    # The hook runs from `git archive HEAD`, so uncommitted plugin code would
    # make this check a different plugin from the one on disk.
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "hooks"],
                           cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if dirty:
        print("FATAL: uncommitted changes under scripts/ or hooks/")
        return 1
    cfg = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))
    prompt = next(t for t in cfg["tasks"] if t["id"] == TASK)["prompt"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()

    before = libguard.snapshot()
    # Resolved: save_skill records project roots with symlinks resolved and
    # macOS's temp dir is a symlink (same reason as e13_qualify).
    work = os.path.realpath(tempfile.mkdtemp(prefix="e14-deliver-"))
    rows, problems = [], []
    try:
        scripts = export_scripts("HEAD", os.path.join(work, "head"))
        for i, cell in enumerate(CELLS):
            home, project = _sandbox(work, cell)
            problems += _install([draft_path(cell)], home, project)
            got, err = delivered(scripts, prompt, "e14-deliver-%d" % i, project, home)
            if err:
                problems.append("%s hook stderr: %s" % (cell, err[-200:]))
            rows.append({"cell": cell, "name": draft_name(cell),
                         "path": str(draft_path(cell).relative_to(ROOT)),
                         "sha256": sha256(draft_path(cell)),
                         "delivered": draft_name(cell) in got})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    for r in rows:
        print("%-3s %-28s delivered %s" % (r["cell"], r["name"], r["delivered"]))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    ok = gate(rows) and untouched and not problems
    print("gate: %s" % ("pass" if ok else "FAIL"))
    if args.write and ok:
        RECORD.write_text(json.dumps({"task": TASK, "ref": "HEAD", "commit": commit,
                                      "drafts": rows, "library_untouched": untouched},
                                     indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % RECORD.relative_to(ROOT))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
