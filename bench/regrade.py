#!/usr/bin/env python3
"""Replay archived artifacts and score them with the graded probe suites.

Costs ZERO sessions: it reuses `bench/authored/`, extracted before /tmp was
swept. Each entry is replayed by checking out its base commit and applying
the diff filtered to `scripts/*` -- the full diff also carries the
harness-staged hidden tests, and replaying those would reinstate the old
two-test grading instead of the new suite.

Run: python3 bench/regrade.py [--limit N]
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent
AUTHORED = ROOT / "authored"
OUT = ROOT / "graded.jsonl"

SUITES = {
    "sf-author-response-text": "probe_response_text.py",
    "sf-author-fingerprint-preexisting": "probe_fingerprint_preexisting.py",
}


def suite_for(task):
    """Absolute path to the probe suite for `task`, or None if ungraded.

    Only the two author tasks have suites. The transfer and umbrella variants
    author the SAME function, so they route through the base task's suite;
    the distillation clones author nothing and are skipped.
    """
    for base, fname in SUITES.items():
        if task == base or task.startswith(base + "-"):
            return str(ROOT / "probes" / fname)
    return None


def parse_probe_output(out):
    """{probe_name: passed} from the repo's PASS/FAIL line format."""
    detail = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("PASS "):
            detail[line[5:].strip()] = True
        elif line.startswith("FAIL "):
            detail[line[5:].split(":", 1)[0].strip()] = False
    return detail


def summarize(detail):
    """Passing count, total, and fraction. An empty run scores 0.0, not 1.0."""
    total = len(detail)
    passed = sum(1 for v in detail.values() if v)
    return {"probe_passed": passed, "probe_total": total,
            "probe_score": (passed / total) if total else 0.0,
            "probe_detail": detail}


def replay(entry, workdir):
    """Check out the base commit and apply the artifact's scripts/ changes.

    If the apply fails after the worktree is created, remove that exact
    worktree before re-raising -- otherwise it leaks and only the trailing
    `git worktree prune` (after the whole batch) ever sweeps it up.
    """
    clone = pathlib.Path(workdir) / entry["clone"]
    subprocess.run(["git", "worktree", "add", "--detach", str(clone),
                    entry["base_commit"]], cwd=str(REPO),
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    try:
        subprocess.run(["git", "apply", "--include=scripts/*",
                        str(AUTHORED / entry["diff"])], cwd=str(clone), check=True)
    except Exception:
        subprocess.run(["git", "worktree", "remove", "--force", str(clone)],
                       cwd=str(REPO), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        raise
    return clone


def probe(entry, clone):
    suite = suite_for(entry["task"])
    r = subprocess.run([sys.executable, suite, str(clone)],
                       capture_output=True, text=True, timeout=300)
    return summarize(parse_probe_output(r.stdout + r.stderr))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    entries = json.loads((AUTHORED / "manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in entries if suite_for(e.get("task") or "")]
    if args.limit:
        entries = entries[:args.limit]

    written = 0
    try:
        with tempfile.TemporaryDirectory() as work:
            for e in entries:
                clone = None
                try:
                    clone = replay(e, work)
                    row = dict(e)
                    row.update(probe(e, clone))
                    with OUT.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row) + "\n")
                    written += 1
                    print("%-58s %d/%d" % (e["clone"], row["probe_passed"],
                                           row["probe_total"]))
                except Exception as err:
                    # Broad on purpose: a malformed manifest entry (KeyError)
                    # or anything else must not abort the rest of the batch.
                    # Print it, don't swallow it -- same precedent as run.py.
                    print("ERROR %s: %r" % (e.get("clone", "?"), err),
                          file=sys.stderr)
                finally:
                    if clone:
                        subprocess.run(["git", "worktree", "remove", "--force",
                                        str(clone)], cwd=str(REPO),
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
    finally:
        # Guaranteed even if the loop above exits abnormally.
        subprocess.run(["git", "worktree", "prune"], cwd=str(REPO),
                       stdout=subprocess.DEVNULL)
    print("wrote %d row(s) to %s" % (written, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
