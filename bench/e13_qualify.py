#!/usr/bin/env python3
"""E13 trap-2 qualification (spec section 6.1) and delivery check (section 7).

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

For every counted draft of a trap, in section 6.1's order (learn before
learn-failure, lower draw first; gate-off draws only; outcome `saved` only):

  qualification  install the consolidated seven plus the draft through the real
                 save_skill.py into a sandboxed HOME and project, then run the
                 real hook on the trap's author prompt from `git archive` of
                 06885c0 (before the tokenizer fix) and of 9cbb472 (after it).
                 The draft qualifies if the old hook does not deliver it and
                 the new one does.
  delivery       install the draft ALONE and run the new hook on the same
                 prompt. A draft it does not deliver cannot act as a treatment
                 and is not probed.

Zero sessions: no `claude` runs, which is what makes the sandboxed HOME safe.
Installs use the current save_skill.py, so only the hook differs between old
and new (bench/real_path_check.py's method, whose helpers this reuses). The
operator's library must come out unchanged. Run from the repo root:

    python3 bench/e13_qualify.py --trap C --write
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bench"))
import budget_sweep as bs                                         # noqa: E402
import libguard                                                   # noqa: E402
from dryrun import PROBES                                         # noqa: E402
from real_path_check import delivered, export_scripts, sandbox_env  # noqa: E402

ARCHIVE = ROOT / "bench" / "distilled"
OLD_REF, NEW_REF = "06885c0", "9cbb472"
DISTILLERS = ("learn", "learn-failure")      # section 6.1: learn first


def counted_drafts(archive, letter):
    """Every draft section 5 counts, in section 6.1's order."""
    out = []
    for distiller in DISTILLERS:
        seg = archive / letter / (distiller + "-nogate")
        metas = sorted(seg.glob("*/meta.json"), key=lambda p: int(p.parent.name))
        for meta in metas:
            m = json.loads(meta.read_text(encoding="utf-8"))
            draft = meta.parent / "SKILL.md"
            if m.get("outcome") == "saved" and draft.is_file():
                out.append({"segment": seg.name, "draw": int(meta.parent.name),
                            "path": draft, "name": m.get("skill_name")})
    return out


def plugin_drift(ref):
    """True if the working tree differs from `ref` under scripts/ or hooks/.

    Qualification only equals "the real hook as qualified" while the plugin
    under test is unchanged since NEW_REF -- e13_qualify runs NEW_REF's hook
    for the delivery-alone check but installs with the CURRENT save_skill.py,
    and a parallel branch can edit scripts/retrieve.py underneath this run.
    """
    r = subprocess.run(["git", "diff", "--quiet", ref, "--", "scripts", "hooks"],
                       cwd=str(ROOT))
    return r.returncode != 0


def qualifies(name, old, new):
    return name not in old and name in new


def first_qualifying(rows):
    return next((r for r in rows if r["qualifies"]), None)


def _sandbox(work, tag):
    home = tempfile.mkdtemp(prefix="home-%s-" % tag, dir=work)
    project = pathlib.Path(tempfile.mkdtemp(prefix="proj-%s-" % tag, dir=work))
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    return home, project


def _install(paths, home, project):
    problems = []
    for p in paths:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_skill.py"),
                            str(pathlib.Path(p).resolve()), "--scope", "project",
                            "--project-root", str(project)],
                           capture_output=True, text=True, cwd=str(project),
                           env=sandbox_env(home), timeout=120)
        if r.returncode:
            problems.append("%s did not save: %s" % (p, (r.stdout + r.stderr)[-200:]))
    return problems


def _rel(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True, choices=sorted(PROBES))
    ap.add_argument("--write", action="store_true",
                    help="write bench/distilled/<trap>/qualification.json")
    args = ap.parse_args(argv)
    if plugin_drift(NEW_REF):
        print("FATAL: scripts/ or hooks/ have drifted from %s -- qualification no"
              " longer matches the plugin under test" % NEW_REF)
        return 1
    task = PROBES[args.trap]
    prompt = bs.P[task]
    drafts = counted_drafts(ARCHIVE, args.trap)
    if not drafts:
        print("no counted draft for trap %s" % args.trap)
        return 1

    before = libguard.snapshot()
    # Resolved: save_skill records project roots with symlinks resolved and
    # retrieve.in_scope compares strings, and macOS's temp dir is a symlink.
    work = os.path.realpath(tempfile.mkdtemp(prefix="e13-qualify-"))
    rows, problems = [], []
    try:
        old_scripts = export_scripts(OLD_REF, os.path.join(work, "old"))
        new_scripts = export_scripts(NEW_REF, os.path.join(work, "new"))
        seven = [ROOT / e["_path"] for e in bs.seven]
        for i, d in enumerate(drafts):
            home, project = _sandbox(work, "lib%d" % i)
            problems += _install(seven + [d["path"]], home, project)
            old, err_old = delivered(old_scripts, prompt, "old-%d" % i, project, home)
            new, err_new = delivered(new_scripts, prompt, "new-%d" % i, project, home)
            home1, project1 = _sandbox(work, "alone%d" % i)
            problems += _install([d["path"]], home1, project1)
            alone, err_alone = delivered(new_scripts, prompt, "alone-%d" % i, project1, home1)
            problems += ["%s hook stderr: %s" % (_rel(d["path"]), e[-200:])
                         for e in (err_old, err_new, err_alone) if e]
            rows.append({"segment": d["segment"], "draw": d["draw"], "name": d["name"],
                         "path": _rel(d["path"]), "old": old, "new": new,
                         "qualifies": qualifies(d["name"], old, new),
                         "alone": alone, "deliverable": d["name"] in alone})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    first = first_qualifying(rows)
    result = {"trap": args.trap, "task": task, "old_ref": OLD_REF, "new_ref": NEW_REF,
              "drafts": rows, "first_qualifying": first["path"] if first else None,
              "deliverable": [r["path"] for r in rows if r["deliverable"]],
              "problems": problems, "library_untouched": untouched}
    for r in rows:
        print("%-22s draw %d  %-40s old %-5s new %-5s qualifies %-5s deliverable %s"
              % (r["segment"], r["draw"], (r["name"] or "?")[:40], r["name"] in r["old"],
                 r["name"] in r["new"], r["qualifies"], r["deliverable"]))
    print("first qualifying: %s" % result["first_qualifying"])
    print("deliverable: %d of %d" % (len(result["deliverable"]), len(rows)))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    ok = untouched and not problems
    if args.write and ok:
        out = ARCHIVE / args.trap / "qualification.json"
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % _rel(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
