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
