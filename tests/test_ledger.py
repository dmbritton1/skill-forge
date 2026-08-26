"""Tests for the SQLite event ledger (spec 9.2). Run: python3 tests/test_ledger.py"""
import datetime
import pathlib
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger


def test_log_event_writes_row():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("save", "foo", outcome="saved", path=db)
        con = ledger.connect(db)
        rows = con.execute("SELECT event_type, skill, outcome FROM events").fetchall()
        con.close()
        assert rows == [("save", "foo", "saved")]


def test_ts_defaults_to_utc_iso():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("save", "foo", path=db)
        con = ledger.connect(db)
        ts = con.execute("SELECT ts FROM events").fetchone()[0]
        con.close()
        assert ts.startswith("20") and "T" in ts


def test_aggregate_view():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "foo", tier="warm", trigger="prompt", path=db)
        ledger.log_event("detection", "foo", detection="verification", outcome="success", path=db)
        ledger.log_event("detection", "foo", detection="fingerprint", outcome="failure", path=db)
        ledger.log_event("save", "bar", outcome="saved", path=db)
        con = ledger.connect(db)
        row = con.execute(
            "SELECT uses, successes, failures, injections FROM skill_aggregates WHERE skill='foo'"
        ).fetchone()
        con.close()
        assert row == (2, 1, 1, 1)


def test_wal_mode_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        con = ledger.connect(db)
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        con.close()
        assert mode == "wal"


def test_concurrent_writers():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"

        def worker(n):
            for i in range(25):
                ledger.log_event("detection", "skill-%d" % n, outcome="success", path=db)

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        con = ledger.connect(db)
        count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.close()
        assert count == 50


def test_concurrent_writers_on_nonexistent_db_lose_nothing():
    # Reproduces the original bug: PRAGMA journal_mode=WAL takes a brief
    # exclusive lock that ignores busy_timeout, so two connections racing to
    # CREATE the db (not just write to an existing one) can collide right in
    # connect(). Two threads is the count that reproduced it reliably.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        assert not db.exists()
        errs = []

        def worker(n):
            try:
                for _ in range(25):
                    ledger.log_event("detection", "skill-%d" % n, outcome="success", path=db)
            except Exception as e:
                errs.append("%s: %s" % (type(e).__name__, e))

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errs == [], errs
        con = ledger.connect(db)
        count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.close()
        assert count == 50


def test_duplicate_fingerprint_credit_is_blocked_by_unique_index():
    # Guards the C2 invariant: one fingerprint credit per (session, skill).
    # log_event has no catch of its own -- every production caller of it for
    # detection='fingerprint' rows (reconcile.py's _log) already wraps the
    # call in try/except, so this IntegrityError never reaches a hook.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", detection="fingerprint",
                         preexisting_fingerprint=0, session="s1", path=db)
        try:
            ledger.log_event("detection", "foo", detection="fingerprint",
                             preexisting_fingerprint=0, session="s1", path=db)
            raised = False
        except ledger.sqlite3.IntegrityError:
            raised = True
        assert raised
        con = ledger.connect(db)
        count = con.execute(
            "SELECT COUNT(*) FROM events WHERE detection='fingerprint'").fetchone()[0]
        con.close()
        assert count == 1


def test_cli_log_and_show():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        rc = ledger.main(["log", "--event-type", "save", "--skill", "foo",
                          "--outcome", "saved", "--path", str(db)])
        assert rc == 0
        rc = ledger.main(["show", "foo", "--path", str(db)])
        assert rc == 0


def test_aggregate_view_zero_not_null_for_outcome_free_skills():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "quiet", path=db)
        con = ledger.connect(db)
        row = con.execute(
            "SELECT uses, successes, failures, injections FROM skill_aggregates WHERE skill='quiet'"
        ).fetchone()
        con.close()
        assert row == (0, 0, 0, 1)


def bucket_of(db, skill):
    con = ledger.connect(db)
    try:
        row = con.execute(
            "SELECT bucket FROM skill_confidence WHERE skill = ?", (skill,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def days_ago(n):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=n)).isoformat(timespec="seconds")


def signals(db):
    con = ledger.connect(db)
    try:
        return con.execute(
            "SELECT session, target, ok FROM signals ORDER BY id").fetchall()
    finally:
        con.close()


def drafts(db):
    con = ledger.connect(db)
    try:
        return con.execute(
            "SELECT id, session, signature, name, status, path FROM drafts"
            " ORDER BY id").fetchall()
    finally:
        con.close()


def test_log_signal_roundtrips():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_signal("s1", "python3 tests foo py", False, path=db)
        ledger.log_signal("s1", "python3 tests foo py", True, path=db)
        assert signals(db) == [("s1", "python3 tests foo py", 0),
                              ("s1", "python3 tests foo py", 1)]


def test_log_signal_coerces_truthiness_to_int():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_signal("s1", "t", "yes", path=db)
        assert signals(db) == [("s1", "t", 1)]


def test_signals_never_reach_skill_confidence():
    """Design decision 11: breadcrumbs must not be able to corrupt a bucket."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", outcome="success", session="s1", path=db)
        ledger.log_event("detection", "foo", outcome="success", session="s2", path=db)
        assert bucket_of(db, "foo") == "trusted"
        for _ in range(20):
            ledger.log_signal("s1", "foo", False, path=db)
        assert bucket_of(db, "foo") == "trusted"


def test_open_draft_returns_id_and_starts_drafting():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        first = ledger.open_draft("s1", "make test", path=db)
        second = ledger.open_draft("s1", "make lint", path=db)
        assert second > first
        assert drafts(db) == [(first, "s1", "make test", None, "drafting", None),
                              (second, "s1", "make lint", None, "drafting", None)]


def test_set_draft_status_touches_only_named_columns():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        did = ledger.open_draft("s1", "make test", path=db)
        ledger.set_draft_status(did, "ready", name="flush-first",
                                draft_path="/tmp/1.md", path=db)
        assert drafts(db) == [(did, "s1", "make test", "flush-first", "ready", "/tmp/1.md")]
        ledger.set_draft_status(did, "delivered", path=db)
        assert drafts(db) == [(did, "s1", "make test", "flush-first", "delivered",
                              "/tmp/1.md")]


def test_prune_signals_by_session_spares_other_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_signal("s1", "t", False, path=db)
        ledger.log_signal("s2", "t", False, path=db)
        ledger.prune_signals(session="s1", path=db)
        assert signals(db) == [("s2", "t", 0)]


def test_prune_signals_by_ttl_spares_fresh_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        stale = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=48)).isoformat(timespec="seconds")
        ledger.log_signal("old", "t", False, ts=stale, path=db)
        ledger.log_signal("new", "t", False, path=db)
        ledger.prune_signals(older_than_hours=24, path=db)
        assert signals(db) == [("new", "t", 0)]


def test_prune_signals_never_touches_events():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "foo", session="s1", path=db)
        ledger.log_signal("s1", "t", False, path=db)
        ledger.prune_signals(session="s1", older_than_hours=0, path=db)
        con = ledger.connect(db)
        try:
            assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        finally:
            con.close()


def test_parse_ts_accepts_a_trailing_z():
    """Transcripts stamp UTC as `...Z`, which 3.9's fromisoformat rejects."""
    parsed = ledger.parse_ts("2026-08-24T13:32:00.000Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.hour == 13


def test_parse_ts_accepts_the_ledgers_own_format():
    assert ledger.parse_ts("2026-08-24T13:32:00+00:00") is not None


def test_parse_ts_rejects_garbage():
    assert ledger.parse_ts("not a time") is None
    assert ledger.parse_ts(None) is None


def test_bucket_unproven_without_outcomes():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "foo", session="s1", path=db)
        assert bucket_of(db, "foo") == "unproven"


def test_bucket_working_after_one_success():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", detection="verification",
                         outcome="success", session="s1", path=db)
        assert bucket_of(db, "foo") == "working"


def test_two_successes_in_one_session_do_not_reach_trusted():
    # C1 dedupes verification detections per hook call, not per session, so a
    # verification command run twice in one session writes two success rows.
    # Spec 7's bar is k>=2 real SESSIONS -- rows must not stand in for them.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for _ in range(2):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session="s1", path=db)
        assert bucket_of(db, "foo") == "working"
        ledger.log_event("detection", "foo", detection="verification",
                         outcome="success", session="s2", path=db)
        assert bucket_of(db, "foo") == "trusted"


def test_failure_demotes_one_step_at_a_time():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, path=db)
        assert bucket_of(db, "foo") == "trusted"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="failure", session="s3", path=db)
        assert bucket_of(db, "foo") == "working"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="failure", session="s4", path=db)
        assert bucket_of(db, "foo") == "unproven"


def test_trusted_decays_to_working_after_90_days():
    # Also the direct test that julianday() parses the ledger's timestamp
    # format: if it returned NULL the freshness clause would go NULL, the
    # first WHEN would never fire, and NOTHING would ever be trusted.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, ts=days_ago(120), path=db)
        assert bucket_of(db, "foo") == "working"
        con = ledger.connect(db)
        try:
            assert con.execute("SELECT julianday(ts) FROM events LIMIT 1").fetchone()[0] is not None
        finally:
            con.close()


def test_fresh_success_still_reaches_trusted():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, path=db)
        assert bucket_of(db, "foo") == "trusted"


def test_unsessioned_successes_count_as_one_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for _ in range(3):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", path=db)
        assert bucket_of(db, "foo") == "working"


def test_reconcile_rows_do_not_inflate_uses():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="success", session="s1", path=db)
        con = ledger.connect(db)
        try:
            uses = con.execute(
                "SELECT uses FROM skill_aggregates WHERE skill='foo'").fetchone()[0]
        finally:
            con.close()
        assert uses == 0


def test_session_query_uses_the_session_index():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", session="s1", path=db)
        con = ledger.connect(db)
        try:
            plan = con.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM events WHERE session = ?",
                ("s1",)).fetchall()
        finally:
            con.close()
        plan_text = " ".join(str(row) for row in plan)
        assert "idx_events_session" in plan_text, plan_text
        assert "SCAN events" not in plan_text, plan_text


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    sys.exit(1 if failures else 0)
