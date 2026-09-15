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
from e15_read import MIN_VARIANT, RECORD, TASK                     # noqa: E402
from real_path_check import delivered, export_scripts              # noqa: E402

VARIANT_SEG = ROOT / "bench" / "distilled" / "C" / "learn-e15-nogate"
VARIANT_FILE = ROOT / "bench" / "variants" / "E15" / "distilling-skills.md"
BASELINE = tuple("bench/distilled/C/learn-nogate/%d/SKILL.md" % d for d in (1, 2, 3))
# Spec amendment 1: repair_unresolved means the source session never fixed the
# bug, before the distiller's rules were read -- not an emission outcome.
HARNESS_OUTCOMES = ("session_failed", "errored", "missing", "repair_unresolved")
# Spec amendment 3: a path in the variant snapshot's scripts/. Its hooks import
# them, so the sandbox leaves them readable (sandbox spec section 3.4).
SNAPSHOT_SCRIPTS = re.compile(r"/skillforge-bench/plugin-[^/]+-e15/scripts(/|$)")


def _ran_under_variant(m, variant_file):
    """True if meta's plugin_commit marks the pinned variant file (finding 2)."""
    return str(m.get("plugin_commit") or "").endswith("+e15-" + sha256(variant_file)[:12])


def _isolated(m):
    """Spec amendments 1 and 3: sandboxed, not tainted, and an audit that is clean
    or whose every leak is in the variant snapshot's scripts/ (a read of the fixed
    file itself is `tainted`). A missing key fails closed."""
    aud = m.get("audit") or {}
    leaked = aud.get("leaked")
    confined = (aud.get("verdict") == "leak" and isinstance(leaked, list) and bool(leaked)
                and all(SNAPSHOT_SCRIPTS.search(str(p)) for p in leaked))
    return (m.get("sandbox") is True and m.get("tainted") is False
            and (aud.get("verdict") == "clean" or confined))


def _counted(m, draft, variant_file):
    """Spec section 3 stage B and amendment 1: the one counting predicate."""
    return (m.get("outcome") == "saved" and draft.is_file() and _isolated(m)
            and _ran_under_variant(m, variant_file))


def counted_variant_drafts(seg, variant_file=VARIANT_FILE):
    """Counted drafts (`_counted`), in draw order."""
    out = []
    for meta in sorted(pathlib.Path(seg).glob("*/meta.json"), key=lambda p: int(p.parent.name)):
        if _counted(json.loads(meta.read_text(encoding="utf-8")), meta.parent / "SKILL.md", variant_file):
            out.append(meta.parent / "SKILL.md")
    return out


def draw_outcomes(seg, expected=6, variant_file=VARIANT_FILE):
    """Finding 1: one row per draw number 1..expected, so a harness failure
    (session_failed/errored/missing) cannot read as a silent non-emission."""
    out = []
    for n in range(1, expected + 1):
        meta = pathlib.Path(seg) / str(n) / "meta.json"
        draft = pathlib.Path(seg) / str(n) / "SKILL.md"
        if not meta.is_file():
            out.append({"draw": n, "outcome": "missing", "sandbox": None, "audit": None,
                        "leaked": None, "tainted": None, "counted": False})
            continue
        m = json.loads(meta.read_text(encoding="utf-8"))
        aud = m.get("audit") or {}
        out.append({"draw": n, "outcome": m.get("outcome") or "missing",
                    "sandbox": m.get("sandbox"), "audit": aud.get("verdict"),
                    "leaked": aud.get("leaked"), "tainted": m.get("tainted"),
                    "counted": _counted(m, draft, variant_file)})
    return out


def harness_failed(outcomes):
    """Finding 1 and spec amendments 1 and 3: a draw the harness failed on, whose
    source repair did not resolve, or whose isolation cannot be trusted. None of
    these is an emission outcome: it blocks the probe and stage B is re-run."""
    return any(o["outcome"] in HARNESS_OUTCOMES
               or not _isolated({"sandbox": o["sandbox"], "tainted": o["tainted"],
                                 "audit": {"verdict": o["audit"], "leaked": o.get("leaked")}})
               for o in outcomes)


def _procedure_section(body):
    """The `## Procedure` section body: from its heading to the next `## ` or end."""
    m = re.search(r"^## Procedure\s*$(.*?)(?=^## |\Z)", body or "", re.M | re.S)
    return m.group(1) if m else ""


def compliance(text):
    """Spec section 3 stage C: descriptive only, never a gate."""
    fm, body = save_skill.parse_frontmatter(text)
    desc = " ".join(str((fm or {}).get("description") or "").split())
    first = desc.split(". ", 1)[0]
    return {"names_test": bool(re.search(r"\btest_\w+|\btests/", text)),
            "find_step": bool(re.search(r"^\s*\d+\.\s+(\*\*)?Find\b",
                                        _procedure_section(body), re.M)),
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
    committed = subprocess.run(["git", "status", "--porcelain", "--", str(RECORD.relative_to(ROOT))],
                               cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if committed:
        print("FATAL: e15-probe.json is not committed")
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if record.get("harness_failure"):
        print("FATAL: a variant draw is a harness failure (session_failed, errored, missing, "
              "repair_unresolved, unsandboxed, audit not clean or tainted) "
              "-- re-run stage B, do not record emission")
        return 1
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

    outcomes = draw_outcomes(VARIANT_SEG)
    for o in outcomes:
        print("draw %-3d outcome %-17s sandbox %-5s audit %-8s tainted %-5s counted %s"
              % (o["draw"], o["outcome"], o["sandbox"], o["audit"], o["tainted"], o["counted"]))
    failed = harness_failed(outcomes)
    print("harness failure: %s" % failed)

    probe_ok = allowed(rows) and not failed
    print("probe allowed: %s" % probe_ok)
    if untouched and not problems:
        if args.write:
            RECORD.write_text(json.dumps({"task": TASK, "commit": commit, "drafts": rows,
                                          "draws": outcomes, "harness_failure": failed,
                                          "probe_allowed": probe_ok, "library_untouched": untouched},
                                         indent=2) + "\n", encoding="utf-8")
            print("wrote %s" % RECORD.relative_to(ROOT))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
