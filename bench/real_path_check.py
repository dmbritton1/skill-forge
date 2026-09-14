#!/usr/bin/env python3
"""Does the REAL install-and-inject path deliver what the deterministic model predicts?

bench/budget_sweep.py and rank_check.py model delivery in-process: they call
retrieve.rank over frontmatter they parse themselves. A session doesn't take that
path. Skills go in through save_skill.py, which compiles an index, and
retrieve.py reads that index as a hook on stdin. This script installs each pool
through the real save_skill.py into a sandboxed HOME and project, calls the real
hook once per task, and checks the delivered skill against budget_sweep.deliver
at the shipped budget.

--baseline REF also runs the hook from `git archive REF scripts`, so a retrieval
change can be compared before and after through the real path. Installs always
use the current save_skill.py, so the only thing that differs is the hook.

Zero sessions. No `claude` is invoked, which is what makes a sandboxed HOME safe
(the CLI would need the real HOME for credentials). The operator's library is
snapshotted before and after and must come out unchanged. Run from the repo
root, like the other bench tools:

    python3 bench/real_path_check.py
    python3 bench/real_path_check.py --baseline 06885c0

2026-09-13, with --baseline 06885c0 (the commit before 9cbb472 dropped function
words): the real path agreed with the model in 4 of 4 cases. On the consolidated
pool, response_text went from the wrong trap to the right one. The
unconsolidated ten stayed wrong, and fingerprint was right both before and
after. See bench/RESULTS.md.
"""
import argparse
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bench"))
import budget_sweep as bs   # noqa: E402
import libguard             # noqa: E402

TASKS = (("response_text", "sf-author-response-text", "A"),
         ("fingerprint", "sf-author-fingerprint-preexisting", "B"))


def sandbox_env(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SKILLFORGE_")}
    env["HOME"] = home
    env["SKILLFORGE_NO_CRITIQUE"] = "1"
    return env


def delivered(scripts_dir, prompt, session, project, home):
    """Skill names the real hook injects, plus its stderr."""
    r = subprocess.run([sys.executable, str(scripts_dir / "retrieve.py")],
                       input=json.dumps({"prompt": prompt, "session_id": session,
                                         "cwd": str(project)}),
                       capture_output=True, text=True, cwd=str(project),
                       env=sandbox_env(home), timeout=60)
    if not r.stdout.strip():
        return [], r.stderr.strip()
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    return ([l.split("'")[1] for l in ctx.splitlines()
             if l.startswith("--- SkillForge retrieved skill '")], r.stderr.strip())


def export_scripts(ref, into):
    tar = subprocess.run(["git", "archive", "--format=tar", ref, "scripts"],
                         cwd=str(ROOT), capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(into)
    return pathlib.Path(into) / "scripts"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", help="also run the hook from `git archive REF scripts`")
    args = ap.parse_args()

    before = libguard.snapshot()
    # Resolved on purpose. save_skill records the project root with symlinks
    # resolved, and retrieve.in_scope compares paths as strings. An unresolved
    # cwd would put every skill out of scope and deliver nothing; macOS's temp
    # dir, /var/folders, is a symlink to /private/var/folders. Claude Code sends
    # a physical cwd, and this mirrors it.
    work = os.path.realpath(tempfile.mkdtemp(prefix="real-path-"))
    problems, rows = [], []
    try:
        base = export_scripts(args.baseline, os.path.join(work, "baseline")) if args.baseline else None
        for label, pool in (("ten", bs.ten), ("seven", bs.seven)):
            trap = {e["name"]: e["_trap"] for e in pool}
            home = tempfile.mkdtemp(prefix="home-", dir=work)
            project = pathlib.Path(tempfile.mkdtemp(prefix="proj-", dir=work))
            subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
            for e in pool:
                r = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_skill.py"),
                                    str((ROOT / e["_path"]).resolve()), "--scope", "project",
                                    "--project-root", str(project)],
                                   capture_output=True, text=True, cwd=str(project),
                                   env=sandbox_env(home), timeout=120)
                if r.returncode:
                    problems.append("%s: %s did not save: %s"
                                    % (label, e["name"], (r.stdout + r.stderr)[-160:]))
            for tlabel, tid, want in TASKS:
                cur, err = delivered(ROOT / "scripts", bs.P[tid],
                                     "cur-%s-%s" % (label, tlabel), project, home)
                if err:
                    problems.append("%s/%s hook stderr: %s" % (label, tlabel, err[-160:]))
                old = None
                if base:
                    old, err = delivered(base, bs.P[tid],
                                         "base-%s-%s" % (label, tlabel), project, home)
                    if err:
                        problems.append("%s/%s baseline hook stderr: %s" % (label, tlabel, err[-160:]))
                model = [x["name"] for x in bs.deliver(pool, bs.P[tid], 1200)]
                rows.append((label, tlabel, want, trap, old, cur, model))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    def cell(names, trap, want):
        if names is None:
            return "-"
        ok = any(want in trap.get(n, "") for n in names)
        return "%s %s" % ("RIGHT" if ok else "wrong", ", ".join(n[:28] for n in names) or "(nothing)")

    print("%-6s %-14s %-4s %-38s %-38s %s" % (
        "pool", "task", "want", ("baseline " + args.baseline) if args.baseline else "",
        "current", "agrees with model"))
    agree = 0
    for label, tlabel, want, trap, old, cur, model in rows:
        ok = cur == model
        agree += ok
        print("%-6s %-14s %-4s %-38s %-38s %s" % (
            label, tlabel, want, cell(old, trap, want), cell(cur, trap, want),
            "yes" if ok else "NO, model predicted %s" % model))
    untouched = libguard.snapshot() == before
    print("\ncurrent real path agrees with budget_sweep's model: %d of %d" % (agree, len(rows)))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    return 0 if agree == len(rows) and untouched and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
