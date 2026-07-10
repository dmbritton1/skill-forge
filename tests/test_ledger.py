"""Tests for the SQLite event ledger (spec 9.2). Run: python3 tests/test_ledger.py"""
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


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except AssertionError:
                failures += 1
                print("FAIL " + name)
    sys.exit(1 if failures else 0)
