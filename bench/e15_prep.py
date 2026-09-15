#!/usr/bin/env python3
"""E15 stage C (spec section 3): delivery, rule compliance and freeze. Zero sessions.

docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md

Installs each counted variant draft (bench/distilled/C/learn-e15-nogate) and
each of E13's three skill drafts ALONE through the real save_skill.py into a
sandboxed HOME, runs HEAD's prompt hook on trap C's author prompt, records
delivery and the three descriptive rule-compliance flags, and freezes the
drafts' sha256 in bench/distilled/C/e15-probe.json. The probe is allowed only
if at least 3 variant drafts and all 3 baseline drafts are delivered; the
record is written either way (plan ruling 3). Run from the repo root:

    python3 bench/e15_prep.py --write          # check and record
    python3 bench/e15_prep.py --check-frozen   # probe guard
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import libguard                                                   # noqa: E402
import save_skill                                                 # noqa: E402
from e13_qualify import _install, _sandbox                         # noqa: E402
from e14_deliver import drifted, sha256                            # noqa: E402
from e15_read import RECORD, TASK                                  # noqa: E402
from real_path_check import delivered, export_scripts              # noqa: E402

VARIANT_SEG = ROOT / "bench" / "distilled" / "C" / "learn-e15-nogate"
BASELINE = tuple("bench/distilled/C/learn-nogate/%d/SKILL.md" % d for d in (1, 2, 3))
MIN_VARIANT = 3


def counted_variant_drafts(seg):
    """Spec section 3 stage B: saved, draft present, not tainted -- in draw order."""
    out = []
    for meta in sorted(pathlib.Path(seg).glob("*/meta.json"), key=lambda p: int(p.parent.name)):
        m = json.loads(meta.read_text(encoding="utf-8"))
        draft = meta.parent / "SKILL.md"
        if m.get("outcome") == "saved" and draft.is_file() and not m.get("tainted"):
            out.append(draft)
    return out


def compliance(text):
    """Spec section 3 stage C: descriptive only, never a gate."""
    fm, body = save_skill.parse_frontmatter(text)
    desc = " ".join(str((fm or {}).get("description") or "").split())
    first = desc.split(". ", 1)[0]
    return {"names_test": bool(re.search(r"\btest_\w+|\btests/", text)),
            "find_step": bool(re.search(r"^\s*\d+\.\s+(\*\*)?Find\b", body or "", re.M)),
            "fn_first": "verdict_from" in first}


def allowed(rows):
    variants = [r for r in rows if r["group"] == "variant" and r["delivered"]]
    baseline = [r for r in rows if r["group"] == "baseline"]
    return (len(variants) >= MIN_VARIANT and len(baseline) == len(BASELINE)
            and all(r["delivered"] for r in baseline))


def stale(record, root):
    """Paths whose draft is missing or changed since `record` was written."""
    return [r["path"] for r in record["drafts"]
            if not (pathlib.Path(root) / r["path"]).is_file()
            or sha256(pathlib.Path(root) / r["path"]) != r["sha256"]]


def check_frozen():
    if not RECORD.is_file():
        print("FATAL: %s missing -- run bench/e15_prep.py --write" % RECORD.relative_to(ROOT))
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if not record.get("probe_allowed"):
        print("FATAL: e15-probe.json does not allow the probe (emission, or a baseline draft undelivered)")
        return 1
    changed = stale(record, ROOT)
    if changed:
        print("FATAL: draft(s) changed since e15-probe.json: %s" % ", ".join(changed))
        return 1
    if drifted(record["commit"], ROOT):
        print("FATAL: scripts/ or hooks/ changed since the delivery check ran at %s" % record["commit"][:7])
        return 1
    print("drafts frozen: %d probe drafts, none changed"
          % sum(1 for r in record["drafts"] if r["delivered"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write bench/distilled/C/e15-probe.json")
    ap.add_argument("--check-frozen", action="store_true", help="exit 1 unless the probe may run")
    args = ap.parse_args(argv)
    if args.check_frozen:
        return check_frozen()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "hooks"],
                           cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if dirty:
        print("FATAL: uncommitted changes under scripts/ or hooks/")
        return 1
    cfg = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))
    prompt = next(t for t in cfg["tasks"] if t["id"] == TASK)["prompt"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()
    drafts = ([("variant", p) for p in counted_variant_drafts(VARIANT_SEG)]
              + [("baseline", ROOT / p) for p in BASELINE])

    before = libguard.snapshot()
    work = os.path.realpath(tempfile.mkdtemp(prefix="e15-prep-"))
    rows, problems = [], []
    try:
        scripts = export_scripts("HEAD", os.path.join(work, "head"))
        for i, (group, path) in enumerate(drafts):
            text = path.read_text(encoding="utf-8")
            name = (save_skill.parse_frontmatter(text)[0] or {}).get("name")
            home, project = _sandbox(work, "d%d" % i)
            problems += _install([path], home, project)
            got, err = delivered(scripts, prompt, "e15-prep-%d" % i, project, home)
            if err:
                problems.append("%s hook stderr: %s" % (path.name, err[-200:]))
            rows.append({"group": group, "path": str(path.relative_to(ROOT)), "name": name,
                         "sha256": sha256(path), "delivered": name in got,
                         "compliance": compliance(text)})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    for r in rows:
        c = r["compliance"]
        print("%-8s %-44s delivered %-5s names_test %-5s find_step %-5s fn_first %s"
              % (r["group"], r["path"].replace("bench/distilled/C/", ""), r["delivered"],
                 c["names_test"], c["find_step"], c["fn_first"]))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    probe_ok = allowed(rows)
    print("probe allowed: %s" % probe_ok)
    if untouched and not problems:
        if args.write:
            RECORD.write_text(json.dumps({"task": TASK, "commit": commit, "drafts": rows,
                                          "probe_allowed": probe_ok, "library_untouched": untouched},
                                         indent=2) + "\n", encoding="utf-8")
            print("wrote %s" % RECORD.relative_to(ROOT))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
