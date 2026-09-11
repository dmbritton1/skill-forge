"""Extract what a bench session authored, into bench/authored/.

`bench/run.py` never cleans its work directory, so a clone survives until the
next run under the same path segment overwrites it. This copies `git diff
HEAD` out of named clones and records them in the manifest that
`bench/regrade.py` replays, so the artifacts outlive `/tmp`.

The `--batch` label exists because E7 re-runs the control arm. `prepare()`
derives the clone path from task, arm and segment, so E7's control clone has
the SAME name as the one Q1's control diff was extracted from. Unlabelled,
the new extraction overwrites that file and the manifest keeps pointing at it
-- the old evidence gone with nothing in the data saying so. The label
prefixes the filename and rides on the entry.

Usage:
    python3 bench/extract.py --batch e7 <clone-name> [<clone-name> ...]
    python3 bench/extract.py --batch e7 --list      # what is on disk
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run as bench_run

AUTHORED = ROOT / "authored"


def task_of(clone, tasks):
    """The task id this clone belongs to: the LONGEST id that prefixes it.

    Not the first match. `sf-author-response-text-transfer` starts with
    `sf-author-response-text`, and filing a transfer artifact under the base
    task would hand it to a probe suite written for a different contract.
    """
    hits = [t for t in tasks if clone == t or clone.startswith(t + "-")]
    return max(hits, key=len) if hits else None


def parts_of(clone, tasks):
    """{task, arm, segment, run} off the clone directory name, or None.

    run.py builds the name as "<task>-<arm><segment>-<run>", so this is that
    construction read backwards rather than a guess at the shape.
    """
    task = task_of(clone, tasks)
    if task is None:
        return None
    rest = clone[len(task) + 1:]
    head, _, run = rest.rpartition("-")
    if not run.isdigit():
        return None
    # The head must OPEN with the arm. A distillation clone's head is
    # "distill-learn", which starts with neither -- and slicing it at
    # len("treatment") yields the segment "earn". Those clones author nothing
    # and the manifest records them as unplaceable; keep it that way rather
    # than inventing an arm for them.
    for arm in ("control", "treatment"):
        if head == arm or head.startswith(arm + "-"):
            return {"task": task, "arm": arm,
                    "segment": head[len(arm):], "run": int(run)}
    return None


def diff_name(clone, batch):
    return ("%s-%s.diff" % (batch, clone)) if batch else ("%s.diff" % clone)


def already(entries, clone, batch):
    for e in entries:
        if e.get("clone") == clone and e.get("batch") == batch:
            return True
    return False


def write_manifest(authored, entries):
    (authored / "manifest.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8")


def extract_one(clone_name, batch, tasks, authored, work):
    clone = pathlib.Path(work) / clone_name
    if not (clone / ".git").exists():
        raise RuntimeError("no clone at %s" % clone)
    parts = parts_of(clone_name, tasks)
    if parts is None:
        raise RuntimeError("cannot place %s against any known task" % clone_name)
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=str(clone),
                          capture_output=True, text=True, check=True).stdout
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(clone),
                          capture_output=True, text=True, check=True).stdout.strip()
    name = diff_name(clone_name, batch)
    (authored / name).write_text(diff, encoding="utf-8")
    entry = {"clone": clone_name}
    entry.update(parts)
    entry["base_commit"] = base
    entry["diff"] = name
    entry["diff_lines"] = len(diff.splitlines())
    if batch:
        entry["batch"] = batch
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("clones", nargs="*")
    ap.add_argument("--batch")
    ap.add_argument("--list", action="store_true",
                    help="print the clones on disk and exit")
    args = ap.parse_args(argv)

    cfg = bench_run.expand(json.loads(
        (ROOT / "tasks.json").read_text(encoding="utf-8")))
    tasks = [t["id"] for t in cfg["tasks"]]
    work = bench_run.WORK

    if args.list:
        for d in sorted(p.name for p in work.iterdir() if (p / ".git").exists()):
            print("%-58s %s" % (d, parts_of(d, tasks) or "unplaceable"))
        return 0

    entries = json.loads(
        (AUTHORED / "manifest.json").read_text(encoding="utf-8"))
    added = skipped = 0
    for clone in args.clones:
        if already(entries, clone, args.batch):
            print("skip %s (already extracted for batch %r)" % (clone, args.batch))
            skipped += 1
            continue
        entries.append(extract_one(clone, args.batch, tasks, AUTHORED, work))
        added += 1
        print("%-58s %s" % (clone, entries[-1]["diff"]))
    write_manifest(AUTHORED, entries)
    print("added %d, skipped %d, manifest now %d" % (added, skipped, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
