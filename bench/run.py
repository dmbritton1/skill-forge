#!/usr/bin/env python3
"""Paired A/B benchmark: does an injected SkillForge skill change task outcomes?

One task = a real bug-fix commit from a public repo. The working tree is the
commit's PARENT (buggy source) plus the commit's OWN tests, so the tests the
fix introduced start red -- the model has to turn them green. Scoring is the
repo's own test result, never turns-to-completion (spec 7: high-variance and
gameable).

The two arms differ in exactly one thing: whether the skill is present in the
clone's project-scoped store. Same prompt, same model, same tree, same plugin.
The global store stays empty, so nothing leaks into the control arm.

Usage:
    python3 bench/run.py --task arrow-968-tzinfo-kwarg --runs 1
    python3 bench/run.py --all --runs 3
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
RESULTS = ROOT / "results.jsonl"
SESSION_TIMEOUT_S = 900


def sh(cmd, cwd=None, timeout=600, env=None):
    return subprocess.run(cmd, shell=True, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=timeout,
                          env=env or os.environ.copy())


def prepare(task, dest):
    """Build the starting tree.

    repair mode  -- clone at the fix's parent and overlay the fix's tests, so
                    the tests the fix introduced start red (FAIL_TO_PASS).
    author mode  -- clone at the fix's parent, run stub_cmd to blank out the
                    implementation, and DO NOT place the tests: the model
                    authors against a spec and never sees what will grade it.
                    This is the only mode that measures knowledge rather than
                    the ability to read a failing assertion.
    """
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache = WORK / ("cache-" + task["id"])
    if not cache.exists():
        r = sh("git clone -q %s %s" % (task["repo"], cache), timeout=900)
        if r.returncode:
            raise RuntimeError("clone failed: " + r.stderr[:400])
    sh("git clone -q %s %s" % (cache, dest), timeout=900)
    sh("git checkout -q %s~1" % task["fix_commit"], cwd=dest)
    if task.get("mode", "repair") == "repair":
        sh("git checkout -q %s -- %s" % (task["fix_commit"], task["test_path"]), cwd=dest)
    else:
        r = sh(task["stub_cmd"], cwd=dest, timeout=300)
        if r.returncode:
            raise RuntimeError("stub failed: " + (r.stderr or r.stdout)[-400:])
    r = sh(task["setup_cmd"], cwd=dest, timeout=1800)
    if r.returncode:
        raise RuntimeError("setup failed: " + (r.stderr or r.stdout)[-400:])


def apply_hidden_tests(task, dest):
    """Author mode: bring in the grading tests only after the session ends."""
    sh("git checkout -q %s -- %s" % (task["fix_commit"], task["test_path"]), cwd=dest)


def install_skill(task, dest, plugin_dir):
    """Put the skill in the clone's PROJECT store via the enforced save path."""
    src = ROOT / "skills" / (task["skill"] + ".md")
    r = sh('python3 "%s/scripts/save_skill.py" "%s" --scope project --project-root "%s"'
           % (plugin_dir, src, dest), cwd=dest)
    if r.returncode:
        raise RuntimeError("save_skill failed: " + (r.stdout + r.stderr)[-400:])
    return r.stdout.strip()


def score(task, dest):
    """{name: passed} for the FAIL_TO_PASS set, plus the raw tail.

    Handles both pytest ("FAILED <nodeid>") and this repo's own stdlib
    runners ("PASS <name>" / "FAIL <name>"). A test whose name appears in
    neither a pass nor a fail line counts as NOT passed -- a collection
    error must never read as success.
    """
    r = sh(task["test_cmd"], cwd=dest, timeout=900)
    out = r.stdout + r.stderr
    passed = set()
    for line in out.splitlines():
        line = line.strip()
        is_fail = line.startswith("FAILED") or line.startswith("FAIL ") or " FAILED" in line
        is_pass = line.startswith("PASS ")
        for name in task["fail_to_pass"]:
            if name in line:
                if is_pass:
                    passed.add(name)
                elif is_fail:
                    passed.discard(name)
    return ({n: (n in passed) for n in task["fail_to_pass"]}, out[-600:])


def run_session(task, dest, plugin_dir):
    cmd = ('claude -p %s --plugin-dir %s --permission-mode bypassPermissions'
           % (json.dumps(task["prompt"]), json.dumps(str(plugin_dir))))
    t0 = time.time()
    try:
        r = sh(cmd, cwd=dest, timeout=SESSION_TIMEOUT_S)
        return {"ok": r.returncode == 0, "secs": round(time.time() - t0, 1),
                "tail": (r.stdout or r.stderr)[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "secs": SESSION_TIMEOUT_S, "tail": "TIMEOUT"}


def one(task, arm, run_idx, plugin_dir):
    dest = WORK / ("%s-%s-%d" % (task["id"], arm, run_idx))
    authoring = task.get("mode", "repair") == "author"
    prepare(task, dest)
    if not authoring:
        pre, _ = score(task, dest)
        if any(pre.values()):
            # A test that is already green cannot measure anything.
            print("  WARNING: %s already passing at baseline" %
                  [n for n, ok in pre.items() if ok])
    skill_note = install_skill(task, dest, plugin_dir) if arm == "treatment" else ""
    sess = run_session(task, dest, plugin_dir)
    if authoring:
        apply_hidden_tests(task, dest)
    post, tail = score(task, dest)
    rec = {"task": task["id"], "arm": arm, "run": run_idx,
           "resolved": all(post.values()), "per_test": post,
           "session_ok": sess["ok"], "secs": sess["secs"],
           "skill_note": skill_note, "test_tail": tail,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print("  %-9s run %d -> %s (%.0fs)" %
          (arm, run_idx, "RESOLVED" if rec["resolved"] else "unresolved", sess["secs"]))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--arm", choices=("treatment", "control", "both"), default="both")
    args = ap.parse_args(argv)

    cfg = json.loads((ROOT / "tasks.json").read_text(encoding="utf-8"))
    plugin_dir = Path(cfg["plugin_dir"])
    tasks = [t for t in cfg["tasks"] if args.all or t["id"] == args.task]
    if not tasks:
        print("no matching task; use --all or --task <id>")
        return 1
    arms = ("control", "treatment") if args.arm == "both" else (args.arm,)

    WORK.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        print("%s (skill %s from %s)" % (task["id"], task["skill"], task["skill_source_commit"]))
        for run_idx in range(1, args.runs + 1):
            for arm in arms:
                try:
                    one(task, arm, run_idx, plugin_dir)
                except Exception as e:
                    print("  %-9s run %d -> ERROR %s" % (arm, run_idx, e))
    print("\nresults appended to %s" % RESULTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
