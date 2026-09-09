#!/usr/bin/env python3
"""Q1 phase 1: a session fixes a bug, distills its own skill, and the draft is
archived for a later session to be measured with.

One draw = one repair session + one distillation. Three draws per
(trap, distiller). The draft is extracted to bench/distilled/, which is
COMMITTED -- un-indexed data is what produced the two false claims the
register caught.

Five outcomes, none of them a harness error (spec section 5). The one worth
naming: `repair_unresolved`. A session that flails, fixes nothing, and then
dutifully distills a confident anti-skill about a mechanism it never found
produces a clean `save_skill` exit 0 and would otherwise enter the funnel as
a healthy emission. It is archived and reported, and never probed.

Usage:
    python3 bench/distill.py --trap A --distiller learn-failure --draws 3
    python3 bench/distill.py --all --draws 3
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libguard
import run as bench_run

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "distilled"

# Which store directory each distiller writes into, which is also the only
# reliable way to tell what `kind:` it emitted.
DISTILLERS = {"learn-failure": "antiskills", "learn": "skills"}

# The repair task that carries each trap, and the skill each distiller is
# asked to produce from it. The probe task for the same trap is the author
# task on the SAME bug -- see the spec's cell table.
TRAPS = {"A": "sf-escaping-breaks-symptom-match",
         "B": "sf-truncation-reports-absent"}

# Sized for repair PLUS a full distillation (transcript review, novelty gate,
# duplicate check, draft, secret scan, save). run.py's 900s is sized for an
# author-mode session that writes one function; nothing in the record measures
# this workload, so this is a ceiling to be replaced by a piloted number.
PHASE1_TIMEOUT_S = 1800

PROMPT = (
    "%s\n\n"
    "When the tests pass, distill what you learned in this session using the "
    "%s skill. Follow its contract exactly, including the novelty self-gate -- "
    "aborting because the knowledge is model-obvious is a good outcome, not a "
    "failure. There is no human here to approve the draft: review it yourself "
    "as if you were the reviewer, and if you would approve it, save it.")


def probeable(out):
    """Only a saved draft from a resolved repair earns probe sessions."""
    return out == "saved"


def outcome(repair_resolved, timed_out, draft, reject_count):
    """One of five, checked in priority order.

    repair_unresolved outranks everything: whatever the distiller produced,
    it produced it from a session that did not fix the bug, and that fact
    must not be laundered by a clean save.

    `rejected` is checked BEFORE `aborted` because a rejection also leaves no
    draft in the store -- testing "no draft" first would make `rejected`
    unreachable and silently relabel the single most informative failure the
    distiller can produce as the novelty gate working.
    """
    if not repair_resolved:
        return "repair_unresolved"
    if timed_out:
        return "timed_out"
    if reject_count:
        return "rejected"
    if draft is None:
        return "aborted"
    return "saved"


def _draft_dirs(clone, distiller):
    """Every store a save could have landed in, in search order.

    The clone's PROJECT store first, then the operator's GLOBAL store:
    save_skill.store_dir resolves --scope global to Path.home(), and the
    distillation contract has the MODEL choose the scope. A global save is a
    normal outcome for a trap the model judges general, not an edge case --
    and it used to read as `aborted` and then be deleted by containment
    before anything archived it.
    """
    kind = DISTILLERS[distiller]
    return [Path(clone) / ".claude" / "skillforge" / kind,
            Path.home() / ".claude" / "skillforge" / kind]


def drafts(clone, distiller):
    """Every SKILL.md this draw saved, project store before global.

    Returns a list so the caller can record how many there were. Taking the
    first silently is what this replaces.
    """
    out = []
    for d in _draft_dirs(clone, distiller):
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            md = child / "SKILL.md"
            if md.is_file():
                out.append(md)
    return out


def extract(clone, distiller):
    """The store copy of what the draw saved, or None.

    The STORE copy, never the native one under .claude/skills/: sync.py
    appends a rewritten MARKER_NOTE to the materialized copy, and that text
    is part of hot delivery rather than part of the draft.
    """
    found = drafts(clone, distiller)
    return found[0] if found else None


def archive_dir(trap, distiller, draw):
    return ARCHIVE / trap / distiller / str(draw)


def preflight():
    """Reasons the next draw must not start.

    Checked per DRAW, not per batch. distilling-failures step 3's duplicate
    check runs `ls ~/.claude/skillforge/antiskills/`, so one leaked draft
    makes the next session propose UPDATING it rather than drafting fresh --
    silently converting an independent draw into a dependent one.
    """
    dirty = libguard.snapshot()["stores"]
    if dirty:
        return ["global store is not empty: %s" % ", ".join(dirty)]
    return []


def one(trap, distiller, draw, plugin_dir, task):
    dest = bench_run.WORK / ("%s-distill-%s-%d" % (task["id"], distiller, draw))
    ledger_db = dest.parent / (dest.name + ".ledger.db")
    for suffix in ("", "-shm", "-wal"):
        Path(str(ledger_db) + suffix).unlink(missing_ok=True)
    os.environ["SKILLFORGE_LEDGER"] = str(ledger_db)
    os.environ["SKILLFORGE_FORCE_HOT"] = ""
    # Phase 1 runs critique retrospectively (bench/judge.py). Left on, each
    # save spawns a detached `claude -p` that races the containment delete.
    os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"

    blockers = preflight()
    if blockers:
        raise RuntimeError("preflight: " + "; ".join(blockers))
    before = libguard.snapshot()

    bench_run.prepare(task, dest)
    prompt = PROMPT % (task["prompt"], "skillforge:distilling-%s" %
                       ("failures" if distiller == "learn-failure" else "skills"))
    cmd = ('claude -p %s --plugin-dir %s --permission-mode bypassPermissions'
           ' --model %s' % (json.dumps(prompt), json.dumps(str(plugin_dir)),
                            json.dumps(bench_run.MODEL)))
    t0 = time.time()
    timed_out = False
    try:
        sess = bench_run.sh(cmd, cwd=dest, timeout=PHASE1_TIMEOUT_S)
        tail = (sess.stdout or sess.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        timed_out, tail = True, "TIMEOUT"
    secs = round(time.time() - t0, 1)

    post, test_tail = bench_run.score(task, dest)
    repair_resolved = all(post.values())

    found = drafts(dest, distiller)
    draft = found[0] if found else None
    # Read the TEXT now, not the path. The containment step below deletes a
    # global-scope save from the real library, and a Path captured before
    # that would be a dangling read by the time the archive is written.
    draft_text = draft.read_text(encoding="utf-8") if draft is not None else None
    rows = _ledger_rows(ledger_db)
    # The session calls save_skill.py itself, so the harness never sees its
    # exit code. A refusal is observable only here: save_skill logs a system
    # decision row for every REJECTED / SECRET BLOCKED / name collision.
    rejects = [r for r in rows["decisions"] if r["actor"] == "system"]
    out = outcome(repair_resolved, timed_out, draft, len(rejects))

    leaked = libguard.new_global_skills(before)
    if leaked:
        for name in leaked:
            bench_run.sh('python3 "%s/scripts/library.py" delete %s'
                         % (bench_run.REPO_ROOT, name), cwd=str(bench_run.REPO_ROOT))
        libguard.prune_trust(leaked)

    d = archive_dir(trap, distiller, draw)
    d.mkdir(parents=True, exist_ok=True)
    if draft_text is not None:
        (d / "SKILL.md").write_text(draft_text, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "trap": trap, "distiller": distiller, "draw": draw,
        "task": task["id"], "model": bench_run.MODEL,
        "outcome": out, "probeable": probeable(out),
        "repair_resolved": repair_resolved, "per_test": post,
        "timed_out": timed_out, "secs": secs,
        "chose_global_scope": leaked,
        "drafts_found": len(found),
        "ledger_read_error": rows["read_error"],
        "ledger_rows": rows["events"],
        "rejections": rejects,
        "session_tail": tail, "test_tail": test_tail,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2), encoding="utf-8")
    print("  %-13s trap %s draw %d -> %s (%.0fs)" % (distiller, trap, draw, out, secs))
    return out


def _ledger_rows(db):
    """{"events": [...], "decisions": [...]} for this draw.

    `decisions` is load-bearing, not provenance: it is the ONLY place a
    rejection is observable, because the session invokes save_skill.py itself
    and the harness never sees that process's exit code. Empty on failure,
    which classifies as `aborted` -- but `read_error` is recorded, because
    "could not read" and "nothing to read" must not look identical in the
    archive.
    """
    out = {"events": [], "decisions": [], "read_error": None}
    try:
        import sqlite3
        con = sqlite3.connect(str(db))
        out["events"] = [
            {"event_type": r[0], "skill": r[1], "outcome": r[2], "ts": r[3]}
            for r in con.execute(
                "select event_type, skill, outcome, ts from events"
                " where event_type in ('save','draft') order by id")]
        out["decisions"] = [
            {"actor": r[0], "verdict": r[1], "subject": r[2], "reason": r[3]}
            for r in con.execute(
                "select actor, verdict, subject, reason from decisions"
                " order by id")]
        con.close()
    except Exception as err:
        out["read_error"] = repr(err)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", choices=sorted(TRAPS))
    ap.add_argument("--distiller", choices=sorted(DISTILLERS))
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)

    cfg = bench_run.expand(json.loads(
        (ROOT / "tasks.json").read_text(encoding="utf-8")))
    by_id = {t["id"]: t for t in cfg["tasks"]}
    plugin_dir = Path(cfg["plugin_dir"])

    traps = sorted(TRAPS) if args.all else [args.trap]
    dists = sorted(DISTILLERS) if args.all else [args.distiller]
    if not all(traps) or not all(dists):
        print("need --all, or both --trap and --distiller")
        return 1

    bench_run.WORK.mkdir(parents=True, exist_ok=True)
    print("model %s | archive %s | timeout %ds"
          % (bench_run.MODEL, ARCHIVE, PHASE1_TIMEOUT_S))
    for trap in traps:
        for distiller in dists:
            for draw in range(1, args.draws + 1):
                try:
                    one(trap, distiller, draw, plugin_dir, by_id[TRAPS[trap]])
                except Exception as e:
                    print("  %-13s trap %s draw %d -> ERROR %s"
                          % (distiller, trap, draw, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
