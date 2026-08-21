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
