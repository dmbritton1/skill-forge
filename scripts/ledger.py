#!/usr/bin/env python3
"""SQLite event ledger (spec 4.3, 9.2).

One row per event; aggregates are derived views, never stored columns —
events can always rebuild aggregates, aggregates can never rebuild events.
WAL mode so concurrent hook processes can write without racing.
"""
import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

# Views are created with IF NOT EXISTS, which does NOT update the definition
# of a view that already exists. Changing skill_confidence later (slice D ANDs
# in the Tier A conjunct) requires an explicit one-time DROP + CREATE
# migration -- not a DROP on every connect(), because detect.py connects on
# every tool call and DDL means a write transaction.
# `signals` is deliberately NOT part of `events`: events.skill is NOT NULL and
# a breadcrumb has no skill, and any breadcrumb carrying outcome='failure'
# would be counted by skill_confidence and corrupt a real skill's bucket.
# `validations` is separate for the same reason: a verdict of 'fail' is not a
# real-session failure, and skill_confidence counts outcome='failure' across
# every events row. It is also keyed by content hash, which events has no
# column for and no reason to grow one.
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  event_type TEXT NOT NULL,
  skill TEXT NOT NULL,
  session TEXT,
  turn INTEGER,
  tier TEXT,
  "trigger" TEXT,
  detection TEXT,
  preexisting_fingerprint INTEGER,
  outcome TEXT,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session);
CREATE VIEW IF NOT EXISTS skill_aggregates AS
SELECT skill,
  COALESCE(SUM(event_type = 'detection'), 0)  AS uses,
  COALESCE(SUM(outcome = 'success'), 0)       AS successes,
  COALESCE(SUM(outcome = 'failure'), 0)       AS failures,
  COALESCE(SUM(event_type = 'injection'), 0)  AS injections,
  MAX(CASE WHEN event_type = 'detection' THEN ts END) AS last_used
FROM events GROUP BY skill;
CREATE VIEW IF NOT EXISTS skill_confidence AS
WITH t AS (
  SELECT skill,
    COUNT(DISTINCT CASE WHEN outcome = 'success' THEN COALESCE(session, '') END)
      AS success_sessions,
    COUNT(DISTINCT CASE WHEN outcome = 'failure' THEN COALESCE(session, '') END)
      AS failure_sessions,
    MAX(CASE WHEN event_type = 'detection' THEN ts END) AS last_used
  FROM events GROUP BY skill)
SELECT skill, success_sessions, failure_sessions, last_used,
  CASE
    WHEN success_sessions >= 2 AND failure_sessions = 0
         AND (last_used IS NULL OR julianday('now') - julianday(last_used) <= 90)
      THEN 'trusted'
    WHEN success_sessions >= 1 AND success_sessions > failure_sessions THEN 'working'
    ELSE 'unproven'
  END AS bucket
FROM t;
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY,
  session TEXT NOT NULL,
  target TEXT NOT NULL,
  ok INTEGER NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session, id);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY,
  session TEXT,
  signature TEXT NOT NULL,
  name TEXT,
  status TEXT NOT NULL,
  path TEXT,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_signature ON drafts(signature);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE TABLE IF NOT EXISTS validations (
  id INTEGER PRIMARY KEY,
  skill TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  mode TEXT NOT NULL,
  verdict TEXT NOT NULL,
  detail TEXT,
  ts TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_validations_key
  ON validations(skill, content_hash, mode);
"""


def default_path():
    return Path.home() / ".claude" / "skillforge" / "ledger.db"


def connect(path=None):
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5)
    # WAL is a durable, file-level property -- once set it stays set, so only
    # attempt the switch when it isn't already in effect. Setting it needs a
    # brief exclusive lock that does NOT honor timeout=5 above, so two
    # processes opening a fresh db at the same instant can collide; the loser
    # raises OperationalError right here, and since connect() is called from
    # inside log_event, an uncaught exception would silently drop the
    # caller's event. Swallow it: the winner already left the file in WAL
    # mode, which is the only outcome we actually wanted.
    if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
        try:
            con.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
    con.executescript(SCHEMA)
    # One fingerprint credit and one verdict per (session, skill) are design
    # invariants (spec 9.1/9.3), enforced here as partial unique indexes
    # rather than inside SCHEMA's executescript: a pre-existing ledger that
    # already has duplicate rows (from before this fix, or a race that slipped
    # through) would fail CREATE INDEX, and since SCHEMA runs unconditionally
    # on every connect(), that exception would propagate out of connect() and
    # take every hook down with it. Each attempt is isolated and best-effort
    # instead -- a legacy ledger just keeps its duplicates, everyone else gets
    # the guard.
    for stmt in (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_one_fingerprint_credit"
        " ON events(session, skill) WHERE event_type = 'detection'"
        " AND detection = 'fingerprint'",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_one_verdict"
        " ON events(session, skill) WHERE event_type = 'reconcile'",
    ):
        try:
            con.execute(stmt)
        except sqlite3.DatabaseError:
            pass
    return con


def log_event(event_type, skill, *, outcome=None, session=None, turn=None,
              tier=None, trigger=None, detection=None,
              preexisting_fingerprint=None, ts=None, path=None):
    ts = ts or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    con = connect(path)
    try:
        with con:
            con.execute(
                'INSERT INTO events (event_type, skill, session, turn, tier,'
                ' "trigger", detection, preexisting_fingerprint, outcome, ts)'
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_type, skill, session, turn, tier, trigger, detection,
                 preexisting_fingerprint, outcome, ts))
    finally:
        con.close()


def confidence(path=None):
    """{skill: {"bucket", "successes", "failures", "last_used"}}; empty on failure.

    An empty map reads as `unproven` everywhere, which is the safe
    direction: a broken ledger empties the hot tier rather than promoting on
    stale data. A dict rather than a tuple because two consumers now read
    different fields from it, and positional drift between them would be
    silent.
    """
    stats = {}
    try:
        con = connect(path)
        try:
            for skill, wins, losses, last_used, bucket in con.execute(
                    "SELECT skill, success_sessions, failure_sessions,"
                    " last_used, bucket FROM skill_confidence"):
                stats[skill] = {"bucket": bucket or "unproven",
                                "successes": wins or 0, "failures": losses or 0,
                                "last_used": last_used or ""}
        finally:
            con.close()
    except Exception:
        pass
    return stats


def record_validation(skill, content_hash, mode, verdict, *, detail=None,
                      ts=None, path=None):
    """One Tier A verdict for one exact skill text (slice D2 design 6).

    Keyed by content hash, so editing a skill voids its verdicts exactly as
    it voids its trust entry -- both get re-earned together.
    """
    ts = ts or now_utc().isoformat(timespec="seconds")
    con = connect(path)
    try:
        with con:
            con.execute(
                "INSERT INTO validations (skill, content_hash, mode, verdict,"
                " detail, ts) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(skill, content_hash, mode) DO UPDATE SET"
                " verdict = excluded.verdict, detail = excluded.detail,"
                " ts = excluded.ts",
                (skill, content_hash, mode, verdict, detail, ts))
    finally:
        con.close()


def validations_for(skills_hashes, *, path=None):
    """{skill: {mode: verdict}} for the EXACT hashes given; {} on failure.

    A skill whose current text does not match the hash a verdict was
    recorded against simply does not appear -- there is no partial credit
    for an edited skill.
    """
    out = {}
    if not skills_hashes:
        return out
    try:
        con = connect(path)
        try:
            for skill, h in skills_hashes.items():
                for mode, verdict in con.execute(
                        "SELECT mode, verdict FROM validations"
                        " WHERE skill = ? AND content_hash = ?", (skill, h)):
                    out.setdefault(skill, {})[mode] = verdict
        finally:
            con.close()
    except Exception as err:
        print("skillforge: validation read failed: %s" % err, file=sys.stderr)
        return {}
    return out


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_ts(value):
    """Aware datetime from an ISO-8601 stamp; None if unparseable.

    Python 3.9's fromisoformat rejects a trailing 'Z', which is exactly the
    form session transcripts use -- without normalizing it first, every
    transcript entry parses as None and the evidence window silently
    collapses to the tail fallback.
    """
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    # A naive timestamp would raise on comparison with an aware `now`.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def log_signal(session, target, ok, *, ts=None, path=None):
    """One tool-call breadcrumb (slice D1 design 2).

    Scratch, not history: pruned at SessionEnd and swept by TTL at sync.
    Never an `events` row -- see the note above SCHEMA.
    """
    ts = ts or now_utc().isoformat(timespec="seconds")
    con = connect(path)
    try:
        with con:
            con.execute("INSERT INTO signals (session, target, ok, ts)"
                        " VALUES (?,?,?,?)", (session, target, 1 if ok else 0, ts))
    finally:
        con.close()


def open_draft(session, signature, *, ts=None, path=None):
    """Insert a `drafting` row and return its id."""
    ts = ts or now_utc().isoformat(timespec="seconds")
    con = connect(path)
    try:
        with con:
            cur = con.execute(
                "INSERT INTO drafts (session, signature, status, ts)"
                " VALUES (?,?,'drafting',?)", (session, signature, ts))
            return cur.lastrowid
    finally:
        con.close()


def set_draft_status(draft_id, status, *, name=None, draft_path=None, path=None):
    """Advance one draft row; columns left None keep their current value.

    The SET list is assembled from string literals in this function only --
    every caller-supplied value is bound, never interpolated.
    """
    sets, vals = ["status = ?"], [status]
    if name is not None:
        sets.append("name = ?")
        vals.append(name)
    if draft_path is not None:
        sets.append("path = ?")
        vals.append(str(draft_path))
    vals.append(draft_id)
    con = connect(path)
    try:
        with con:
            con.execute("UPDATE drafts SET %s WHERE id = ?" % ", ".join(sets), vals)
    finally:
        con.close()


def prune_signals(session=None, older_than_hours=None, path=None):
    """Delete breadcrumbs: one finished session's, or anything past the TTL.

    ponytail: two DELETEs, no VACUUM. The table is small by construction --
    it never survives a day -- so reclaiming pages costs more than it saves.
    """
    con = connect(path)
    try:
        with con:
            if session is not None:
                con.execute("DELETE FROM signals WHERE session = ?", (session,))
            if older_than_hours is not None:
                cutoff = (now_utc() - datetime.timedelta(hours=older_than_hours)
                          ).isoformat(timespec="seconds")
                con.execute("DELETE FROM signals WHERE ts < ?", (cutoff,))
    finally:
        con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("log")
    lg.add_argument("--event-type", required=True)
    lg.add_argument("--skill", required=True)
    for opt in ("outcome", "session", "tier", "trigger", "detection"):
        lg.add_argument("--" + opt)
    lg.add_argument("--turn", type=int)
    lg.add_argument("--path")
    sh = sub.add_parser("show")
    sh.add_argument("skill")
    sh.add_argument("--path")
    args = ap.parse_args(argv)

    if args.cmd == "log":
        log_event(args.event_type, args.skill, outcome=args.outcome,
                  session=args.session, turn=args.turn, tier=args.tier,
                  trigger=args.trigger, detection=args.detection,
                  path=args.path)
        return 0

    con = connect(args.path)
    try:
        agg = con.execute(
            "SELECT uses, successes, failures, injections, last_used"
            " FROM skill_aggregates WHERE skill = ?", (args.skill,)).fetchone()
        print("aggregate: %s" % (agg,))
        for row in con.execute(
                'SELECT ts, event_type, "trigger", detection, outcome FROM events'
                " WHERE skill = ? ORDER BY id DESC LIMIT 20", (args.skill,)):
            print("%s %s trigger=%s detection=%s outcome=%s" % row)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
