#!/usr/bin/env python3
"""Stop/SessionEnd reconciler (spec 9.1, 9.3; slice C2 design).

Reads this session's ledger rows and decides what C1's detection events
mean: which injections became uses, and (see refire_verdict) whether an
injected anti-skill's trap fired again. Holds no state of its own --
"still unresolved" is re-derived from the ledger every run, so re-running
is idempotent by construction rather than by bookkeeping.

Cheap on purpose: Stop fires at the end of EVERY assistant turn, so the
common case (nothing unresolved) is one indexed SELECT and zero
subprocesses. Failure is always silent: exit 0, no output.
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import patterns
import retrieve

# parse_ts/now_utc live in ledger now: draft.py needs the same parsing, and
# the transcript's trailing-'Z' form has to be handled in exactly one place.
# Bound as module attributes so `reconcile.parse_ts` keeps resolving.
now_utc = ledger.now_utc
parse_ts = ledger.parse_ts

# A symptom re-firing sooner than this is the same tool output echoing back
# through a read or a grep -- detect.py logs the triggering symptom and the
# injection in the same hook call, microseconds apart, so without this floor
# every symptom-triggered anti-skill would convict itself on the evidence
# that summoned it.
MIN_ESCAPE_S = 60
# How long a skill's fate stays open: re-fires after it are a fresh trap, and
# Stop stops probing for its fingerprints (an injection the model ignored must
# not tax every remaining turn of a long session).
RECONCILE_WINDOW_S = 900
# ponytail: 1s ceiling, larger than retrieve's 150ms because this runs once
# per turn instead of once per tool call, and only when work is pending.
GIT_TIMEOUT_S = 1.0
MAX_DIFF_BYTES = 512 * 1024

# Two failures on one command, then a success. One failure then a success is
# not a struggle -- that is the case where the model already knew the answer,
# and a skill restating it would fail the novelty gate anyway.
STRUGGLE_FAILURES = 2
# Wall-clock ceiling on a detached drafter, mirrored in draft.py; the slack
# is what separates "still working" from "killed by a reboot".
DRAFT_TIMEOUT_S = 300
DRAFT_REAP_SLACK_S = 60

SESSION_SQL = ('SELECT event_type, skill, detection, ts, preexisting_fingerprint, "trigger"'
               " FROM events WHERE session = ? ORDER BY id")
SIGNAL_SQL = "SELECT target, ok, ts FROM signals WHERE session = ? ORDER BY id"


def _log(*args, **kwargs):
    """Bookkeeping is best-effort; one failed row never blocks another."""
    try:
        ledger.log_event(*args, **kwargs)
    except Exception as err:
        print("skillforge: ledger write failed: %s" % err, file=sys.stderr)


def session_state(rows):
    """{skill: picture} from one session's id-ordered event rows."""
    state = {}
    for event_type, skill, detection, ts, preexisting, trigger in rows:
        s = state.setdefault(skill, {"injected_ts": None, "preexisting": None,
                                     "injected_trigger": None,
                                     "detections": set(), "symptom_ts": [],
                                     "settled": False})
        if event_type == "injection":
            if s["injected_ts"] is None:   # first injection of the session wins
                s["injected_ts"] = parse_ts(ts)
                s["preexisting"] = preexisting
                s["injected_trigger"] = trigger
        elif event_type == "detection":
            s["detections"].add(detection)
            if detection == "symptom":
                fired = parse_ts(ts)
                if fired:
                    s["symptom_ts"].append(fired)
        elif event_type == "reconcile":
            s["settled"] = True
    return state


def struggle_targets(rows):
    """[(target, first_failure_ts, success_ts)] for each struggle-then-fix.

    A pure function of one session's id-ordered breadcrumbs, which is what
    makes the whole trigger testable without a session, a subprocess, or a
    model. The window returned is the evidence slice the drafter reads:
    from the first failure of the streak to the success that ended it, so a
    success *before* the streak never widens it.

    One signal per target per session -- a target that struggles twice is
    still one lesson, and the second draft would restate the first.
    """
    streak = {}
    seen = set()
    out = []
    for target, ok, ts in rows:
        run = streak.get(target)
        if ok:
            if run and run[0] >= STRUGGLE_FAILURES and target not in seen:
                seen.add(target)
                out.append((target, run[1], ts))
            streak[target] = None
        else:
            streak[target] = [run[0] + 1, run[1]] if run else [1, ts]
    return out


def draft_blockers(con, session):
    """(signatures already drafted this session, is a drafter still running).

    One draft per target per session, and one drafter at a time -- a session
    with five signals must not fan out five `claude` processes.
    """
    done = {r[0] for r in con.execute(
        "SELECT signature FROM drafts WHERE session = ?", (session,))}
    busy = con.execute(
        "SELECT 1 FROM drafts WHERE session = ? AND status = 'drafting' LIMIT 1",
        (session,)).fetchone() is not None
    return done, busy


def reap_stale_drafts(con, now):
    """A drafter killed by a reboot must not wedge the session forever."""
    cutoff = (now - datetime.timedelta(seconds=DRAFT_TIMEOUT_S + DRAFT_REAP_SLACK_S)
              ).isoformat(timespec="seconds")
    with con:
        con.execute("UPDATE drafts SET status = 'failed'"
                    " WHERE status = 'drafting' AND ts < ?", (cutoff,))


def load_entries():
    """{name: index entry}; empty on any failure.

    index.json is the only file this hook reads, and it is authoritative for
    the two things the ledger cannot answer: whether a skill is an anti-skill,
    and what its fingerprints tokenize to. A skill missing from it -- deleted,
    re-quarantined, or dropped by a later sync -- is skipped entirely.
    """
    idx = retrieve.load_index() or {}
    return {e.get("name"): e for e in idx.get("entries", []) if e.get("name")}


def needs_fingerprint(s, entry, now, final):
    """True if this skill is unresolved and still creditable.

    Symptom detections deliberately do NOT resolve a skill: a symptom firing
    is the trap announcing itself (it is what caused the anti-skill to be
    injected), not evidence the Fix was applied.
    """
    if s["injected_ts"] is None or s["preexisting"] != 0:
        return False   # 1 = already there, None = unknown; spec 9.1 forbids the guess
    if s["detections"] & {"verification", "fingerprint"}:
        return False
    if not entry.get("fingerprints"):
        return False
    if final:
        return True    # SessionEnd runs once, so age is not a cost concern
    return (now - s["injected_ts"]).total_seconds() <= RECONCILE_WINDOW_S


def refire_verdict(s, entry, now, final):
    """'failure', 'success', or None -- anti-skills only, once per session.

    An anti-skill's job is to stop one error recurring. The ledger records
    neither file nor route, so "the same error again" is skill identity plus
    time: a symptom detection between the escape floor and the window's end.
    A symptom after the window is a fresh trap, not a failure of this
    injection, and concludes nothing.

    Success is granted only on positive evidence that the trap was set and
    never re-fired -- never on the mere absence of a detection. A
    prompt-triggered injection (trigger='prompt') never had a trap sprung in
    the first place, so it can bank neither failure nor success here; its
    outcome, if any, comes from a verification detection like a regular
    skill. Requiring no symptom detection strictly after the injection
    timestamp (rather than only checking the window) is deliberately
    conservative: it also subsumes the post-window case, since the
    triggering symptom detect.py logs shares the injection's own timestamp
    and so is never "strictly greater".
    """
    if s["settled"] or s["injected_ts"] is None or entry.get("kind") != "antiskill":
        return None
    lo = s["injected_ts"] + datetime.timedelta(seconds=MIN_ESCAPE_S)
    hi = s["injected_ts"] + datetime.timedelta(seconds=RECONCILE_WINDOW_S)
    if any(lo <= fired <= hi for fired in s["symptom_ts"]):
        return "failure"
    # Success is only concludable once the session is over, only for a trap
    # that actually sprung (symptom-triggered), only once the model had a
    # chance to fail, and only if no symptom for this skill fired after the
    # injection -- an unresolved trap earns no verdict at all.
    if (final and s["injected_trigger"] == "symptom"
            and (now - s["injected_ts"]).total_seconds() >= MIN_ESCAPE_S
            and not any(fired > s["injected_ts"] for fired in s["symptom_ts"])):
        return "success"
    return None


def _git(args, cwd):
    try:
        proc = subprocess.run(["git"] + args, cwd=str(cwd), stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def changed_tokens(cwd):
    """Tokens of everything added to the working tree since HEAD; None if unknowable.

    One diff plus one untracked listing, tokenized once, serves every pending
    skill -- versus one `git grep` per fingerprint, which is what makes
    per-turn reconciliation affordable. Pre-session dirty state riding along
    in `git diff HEAD` is harmless: credit requires the injection to have
    recorded preexisting_fingerprint = 0.
    """
    parts = []
    diff = _git(["diff", "HEAD", "--unified=0"], cwd)
    if diff is not None:
        for line in diff[:MAX_DIFF_BYTES].splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                parts.append(line[1:])
    others = _git(["ls-files", "--others", "--exclude-standard"], cwd)
    if diff is None and others is None:
        return None   # not a usable repo -- unknown, never a false negative
    for rel in (others or "").splitlines()[:retrieve.SNAPSHOT_MAX_FILES]:
        try:
            with open(str(Path(cwd) / rel), "r", encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read(retrieve.SNAPSHOT_MAX_BYTES))
        except OSError:
            continue
    return patterns.tokenize("\n".join(parts))


def _reconcile_c2(session, cwd, rows, now, final):
    """Slice C2's work, lifted out of run() verbatim.

    Extracted so its `no events this session` early return stops skipping
    C2's own remainder only -- it used to return from run() itself, which
    would make every slice D1 addition unreachable in exactly the sessions
    that produce first drafts.
    """
    state = session_state(rows)
    if not state:
        return
    entries = load_entries()
    pending = [(name, s, entries[name]) for name, s in sorted(state.items())
               if name in entries]

    unresolved = [p for p in pending if needs_fingerprint(p[1], p[2], now, final)]
    if unresolved:
        hay = changed_tokens(cwd)
        if hay:
            for name, _, entry in unresolved:
                if any(patterns.matches(toks, hay)
                       for toks in entry.get("fingerprints") or []):
                    _log("detection", name, detection="fingerprint",
                         preexisting_fingerprint=0, session=session)

    for name, s, entry in pending:
        verdict = refire_verdict(s, entry, now, final)
        if verdict:
            # A verdict is not a detection: detection stays NULL so
            # skill_aggregates.uses (which counts detection rows) is untouched,
            # while skill_confidence picks the outcome up.
            _log("reconcile", name, trigger="refire", outcome=verdict, session=session)


def _spawn(argv, cwd):
    """Detached and never waited on; its own function so tests replace it.

    start_new_session=True cuts the child out of the hook's process group,
    so the hook returning does not signal it. SKILLFORGE_DRAFTING is the
    belt-and-braces recursion guard behind --safe-mode.
    """
    subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True,
                     env=dict(os.environ, SKILLFORGE_DRAFTING="1"))


def _spawn_drafts(data, session, cwd, signal_rows, drafted, busy):
    """At most one detached drafter per Stop, and one per session at a time."""
    if busy:
        return
    for target, since, until in struggle_targets(signal_rows):
        if target in drafted:
            continue
        try:
            draft_id = ledger.open_draft(session, target)
        except Exception as err:
            print("skillforge: draft row failed: %s" % err, file=sys.stderr)
            return
        argv = [sys.executable,
                str(Path(__file__).resolve().parent / "draft.py"), "run",
                "--draft-id", str(draft_id), "--target", target,
                "--transcript", str(data.get("transcript_path") or ""),
                "--since", str(since), "--until", str(until),
                "--cwd", str(cwd)]
        try:
            _spawn(argv, cwd)
        except Exception as err:
            print("skillforge: drafter spawn failed: %s" % err, file=sys.stderr)
            try:
                ledger.set_draft_status(draft_id, "failed")
            except Exception:
                pass
        return   # one drafter at a time, even when several targets qualify


def run(data):
    session = retrieve.sanitize_session(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()
    final = data.get("hook_event_name") == "SessionEnd"
    now = now_utc()
    con = ledger.connect()
    try:
        rows = con.execute(SESSION_SQL, (session,)).fetchall()
        reap_stale_drafts(con, now)
        signal_rows = con.execute(SIGNAL_SQL, (session,)).fetchall()
        drafted, busy = draft_blockers(con, session)
    finally:
        con.close()

    _reconcile_c2(session, cwd, rows, now, final)
    _spawn_drafts(data, session, cwd, signal_rows, drafted, busy)
    return 0


def main(argv=None):
    # A drafter (slice D1) is a Claude Code process spawned by these very
    # hooks. `claude -p --safe-mode` already disables hooks in the child;
    # this is the guard that survives a change in what --safe-mode covers.
    if os.environ.get("SKILLFORGE_DRAFTING"):
        return 0
    try:
        return run(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: reconcile failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
