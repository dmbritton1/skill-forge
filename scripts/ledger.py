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
CREATE VIEW IF NOT EXISTS skill_aggregates AS
SELECT skill,
  COALESCE(SUM(event_type = 'detection'), 0)  AS uses,
  COALESCE(SUM(outcome = 'success'), 0)       AS successes,
  COALESCE(SUM(outcome = 'failure'), 0)       AS failures,
  COALESCE(SUM(event_type = 'injection'), 0)  AS injections,
  MAX(CASE WHEN event_type = 'detection' THEN ts END) AS last_used
FROM events GROUP BY skill;
"""


def default_path():
    return Path.home() / ".claude" / "skillforge" / "ledger.db"


def connect(path=None):
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
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
