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

SESSION_SQL = ("SELECT event_type, skill, detection, ts, preexisting_fingerprint"
               " FROM events WHERE session = ? ORDER BY id")


def _log(*args, **kwargs):
    """Bookkeeping is best-effort; one failed row never blocks another."""
    try:
        ledger.log_event(*args, **kwargs)
    except Exception as err:
        print("skillforge: ledger write failed: %s" % err, file=sys.stderr)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_ts(value):
    """Aware datetime from a ledger timestamp; None if unparseable."""
    try:
        parsed = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    # A naive timestamp would raise on comparison with an aware `now`.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def session_state(rows):
    """{skill: picture} from one session's id-ordered event rows."""
    state = {}
    for event_type, skill, detection, ts, preexisting in rows:
        s = state.setdefault(skill, {"injected_ts": None, "preexisting": None,
                                     "detections": set(), "symptom_ts": [],
                                     "settled": False})
        if event_type == "injection":
            if s["injected_ts"] is None:   # first injection of the session wins
                s["injected_ts"] = parse_ts(ts)
                s["preexisting"] = preexisting
        elif event_type == "detection":
            s["detections"].add(detection)
            if detection == "symptom":
                fired = parse_ts(ts)
                if fired:
                    s["symptom_ts"].append(fired)
        elif event_type == "reconcile":
            s["settled"] = True
    return state


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


def run(data):
    session = retrieve.sanitize_session(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()
    final = data.get("hook_event_name") == "SessionEnd"
    con = ledger.connect()
    try:
        rows = con.execute(SESSION_SQL, (session,)).fetchall()
    finally:
        con.close()
    state = session_state(rows)
    if not state:
        return 0
    entries = load_entries()
    now = now_utc()
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
    return 0


def main(argv=None):
    try:
        return run(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: reconcile failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
