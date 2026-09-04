"""Tests for the SQLite event ledger (spec 9.2). Run: python3 tests/test_ledger.py"""
import datetime
import io
import os
import pathlib
import sqlite3
import sys
import tempfile
import threading
from contextlib import redirect_stderr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


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
            "SELECT organic_bucket FROM skill_confidence WHERE skill = ?", (skill,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def days_ago(n):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=n)).isoformat(timespec="seconds")


def drafts(db):
    con = ledger.connect(db)
    try:
        return con.execute(
            "SELECT id, session, signature, name, status, path FROM drafts"
            " ORDER BY id").fetchall()
    finally:
        con.close()


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


def test_validation_roundtrips_for_its_own_hash():
    def check(home):
        ledger.record_validation("widget-trap", "hash-aaa", "critique", "pass")
        got = ledger.validations_for({"widget-trap": "hash-aaa"})
        assert got == {"widget-trap": {"critique": "pass"}}, got
    in_sandbox(check)


def test_a_verdict_does_not_survive_an_edit():
    """The whole point of hash-keying: pass critique, edit the body, and the
    pass must NOT carry over to the new text."""
    def check(home):
        ledger.record_validation("widget-trap", "hash-aaa", "critique", "pass")
        got = ledger.validations_for({"widget-trap": "hash-bbb"})
        assert got == {}, got
    in_sandbox(check)


def test_recording_the_same_key_twice_replaces_rather_than_duplicates():
    def check(home):
        ledger.record_validation("w", "h", "executable", "inconclusive")
        ledger.record_validation("w", "h", "executable", "pass")
        assert ledger.validations_for({"w": "h"}) == {"w": {"executable": "pass"}}
        con = ledger.connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM validations").fetchone()[0]
        finally:
            con.close()
        assert n == 1, n
    in_sandbox(check)


def test_both_modes_coexist_for_one_skill():
    def check(home):
        ledger.record_validation("w", "h", "critique", "pass")
        ledger.record_validation("w", "h", "executable", "fail")
        assert ledger.validations_for({"w": "h"}) == {
            "w": {"critique": "pass", "executable": "fail"}}
    in_sandbox(check)


def test_validations_never_reach_skill_confidence():
    """A failed validation must not be counted as a real-session failure.

    skill_confidence counts outcome='failure' across events. This is the
    same trap the scratch tables are kept out of events to avoid.
    """
    def check(home):
        ledger.log_event("detection", "w", outcome="success", session="s1")
        ledger.log_event("detection", "w", outcome="success", session="s2")
        ledger.record_validation("w", "h", "executable", "fail")
        con = ledger.connect()
        try:
            row = con.execute(
                "SELECT failure_sessions FROM skill_confidence WHERE skill = 'w'"
            ).fetchone()
        finally:
            con.close()
        assert row[0] == 0, row
    in_sandbox(check)


C2_VIEW = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, skill TEXT NOT NULL,
  session TEXT, turn INTEGER, tier TEXT, "trigger" TEXT, detection TEXT,
  preexisting_fingerprint INTEGER, outcome TEXT, ts TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS skill_confidence AS
SELECT skill, 0 AS success_sessions, 0 AS failure_sessions,
       NULL AS last_used, 'unproven' AS bucket
FROM events GROUP BY skill;
"""


def test_migration_renames_the_bucket_column_on_an_existing_database():
    """A C2-era database has a view with a `bucket` column. CREATE VIEW IF NOT
    EXISTS will not replace it, so connect() must migrate explicitly."""
    def check(home):
        p = home / ".claude" / "skillforge" / "ledger.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = sqlite3.connect(str(p))
        old.executescript(C2_VIEW)
        old.close()

        con = ledger.connect()
        try:
            cols = [d[0] for d in con.execute(
                "SELECT * FROM skill_confidence LIMIT 0").description]
        finally:
            con.close()
        assert "organic_bucket" in cols, cols
        assert "bucket" not in cols, cols
    in_sandbox(check)


def test_migration_records_its_version_and_does_not_repeat():
    def check(home):
        ledger.connect().close()
        con = ledger.connect()
        try:
            v = con.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        finally:
            con.close()
        assert v and int(v[0]) == ledger.SCHEMA_VERSION, v
    in_sandbox(check)


def test_a_fresh_database_gets_the_new_view_directly():
    def check(home):
        con = ledger.connect()
        try:
            cols = [d[0] for d in con.execute(
                "SELECT * FROM skill_confidence LIMIT 0").description]
        finally:
            con.close()
        assert "organic_bucket" in cols, cols
    in_sandbox(check)


def _seed(skill, successes, failures=0, age_days=0):
    ts = days_ago(age_days) if age_days else None
    for i in range(successes):
        ledger.log_event("detection", skill, outcome="success",
                         session="s-ok-%d" % i, ts=ts)
    for i in range(failures):
        ledger.log_event("detection", skill, outcome="failure",
                         session="s-bad-%d" % i, ts=ts)


def test_conjunct_truth_table():
    """This rule decides what sits in context on every prompt, so every
    combination is checked rather than sampled."""
    cases = [
        # (critique, executable, organic_successes, age_days, expected_bucket)
        (None,       None,   0, 0, "unproven"),
        (None,       None,   2, 0, "working"),    # organic alone is NOT enough
        ("pass",     None,   0, 0, "unproven"),
        ("pass",     None,   1, 0, "working"),
        ("pass",     None,   2, 0, "trusted"),    # critique + k>=2
        ("pass",     "pass", 0, 0, "trusted"),    # executable substitutes for k>=2
        ("pass",     "fail", 2, 0, "trusted"),    # fail vetoes nothing
        ("pass",     "inconclusive", 2, 0, "trusted"),
        ("fail",     "pass", 2, 0, "working"),    # nothing substitutes for critique
        ("inconclusive", "pass", 2, 0, "working"),
        # Freshness is a TOP-LEVEL conjunct: an executable pass carries the
        # middle disjunct but must not carry this one, or a skill validated
        # once would sit in context forever.
        ("pass",     "pass", 2, 400, "working"),
    ]
    for i, (crit, exe, wins, age, want) in enumerate(cases):
        def check(home, crit=crit, exe=exe, wins=wins, age=age, want=want, i=i):
            name = "s%d" % i
            _seed(name, wins, age_days=age)
            if crit:
                ledger.record_validation(name, "h", "critique", crit)
            if exe:
                ledger.record_validation(name, "h", "executable", exe)
            conf = ledger.confidence(hashes={name: "h"})
            if not (wins or crit or exe):
                # No events and no hash-matching verdict, so nothing put this
                # skill in the map at all. Assert that absence directly: read
                # through a caller-side default and the row would pass even if
                # the conjunct never ran.
                assert name not in conf, conf
                return
            got = conf[name]["bucket"]
            assert got == want, "%r -> %r, want %r" % (
                (crit, exe, wins, age), got, want)
        in_sandbox(check)


def test_confidence_without_hashes_refuses_to_answer_bucket():
    """A caller that forgets the hashes must not silently get the weaker,
    pre-D2 answer."""
    def check(home):
        _seed("w", 2)
        entry = ledger.confidence()["w"]
        assert entry["organic_bucket"] == "trusted", entry
        assert "bucket" not in entry, entry
    in_sandbox(check)


def test_an_edited_skill_loses_its_conjunct():
    def check(home):
        _seed("w", 2)
        ledger.record_validation("w", "old-hash", "critique", "pass")
        assert ledger.confidence(hashes={"w": "old-hash"})["w"]["bucket"] == "trusted"
        assert ledger.confidence(hashes={"w": "new-hash"})["w"]["bucket"] == "working"
    in_sandbox(check)


def test_an_attempt_roundtrips_for_its_own_hash_and_is_idempotent():
    def check(home):
        ledger.record_attempt("w", "h", "executable")
        ledger.record_attempt("w", "h", "executable")
        assert ledger.attempts_for({"w": "h"}) == {"w": {"executable"}}
        assert ledger.attempts_for({"w": "other-hash"}) == {}
        con = ledger.connect()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM validation_attempts").fetchone()[0]
        finally:
            con.close()
        assert n == 1, n
    in_sandbox(check)


def test_an_attempt_is_not_a_verdict():
    """Finding 4's whole constraint. `pass`/`fail`/`inconclusive` is a closed
    set that feeds the conjunct, so "we tried this text and got no verdict"
    must be invisible to validations_for and to confidence -- otherwise a
    bookkeeping row would decide what enters context on every prompt.

    Mutation proof: record the attempt as a validations row instead (any mode,
    any verdict string) and one of these three assertions fails.
    """
    def check(home):
        _seed("w", 2)
        ledger.record_validation("w", "h", "critique", "pass")
        before = ledger.confidence(hashes={"w": "h"})["w"]["bucket"]
        assert before == "trusted", before
        ledger.record_attempt("w", "h", "executable")
        assert ledger.validations_for({"w": "h"}) == {"w": {"critique": "pass"}}
        assert ledger.confidence(hashes={"w": "h"})["w"]["bucket"] == "trusted"
    in_sandbox(check)



def test_findings_carry_the_detail_for_their_own_hash():
    """The verdict says what; only the detail says why -- and it is hash-scoped."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "l.db"
        detail = '[{"criterion": "followable", "ok": false}]'
        ledger.record_validation("s", "h1", "critique", "fail",
                                 detail=detail, path=db)
        got = ledger.findings_for("s", "h1", path=db)
        assert got == {"critique": ("fail", detail)}, got
        assert ledger.findings_for("s", "h2", path=db) == {}, "stale hash leaked"


def test_findings_survive_a_verdict_with_no_detail():
    """record_validation's detail is optional; reading must not assume it."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "l.db"
        ledger.record_validation("s", "h1", "executable", "pass", path=db)
        assert ledger.findings_for("s", "h1", path=db) == {
            "executable": ("pass", None)}, ledger.findings_for("s", "h1", path=db)


def test_findings_are_empty_when_the_ledger_cannot_be_read():
    """Best-effort like every other read: a broken ledger shows nothing, not a crash."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "l.db"
        bad.write_text("not a database", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            assert ledger.findings_for("s", "h1", path=bad) == {}
        assert "skillforge:" in err.getvalue(), err.getvalue()


def test_usage_for_partitions_sessions_into_truth_table_cells():
    """The cell is derived from which rows exist, never stored."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        # s1: marker and fingerprint agree
        ledger.log_event("injection", "alpha", session="s1", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="fingerprint", path=db)
        # s2: fingerprint with no marker -- a compliance miss
        ledger.log_event("injection", "alpha", session="s2", path=db)
        ledger.log_event("detection", "alpha", session="s2", detection="fingerprint", path=db)
        # s3: marker with nothing corroborating it
        ledger.log_event("injection", "alpha", session="s3", path=db)
        ledger.log_event("detection", "alpha", session="s3", detection="marker", path=db)
        # s4: injected and never used
        ledger.log_event("injection", "alpha", session="s4", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 4, u
        assert u["injections"] == 4, u
        assert u["both"] == 1, u
        assert u["corroborated_only"] == 1, u
        assert u["marker_only"] == 1, u
        assert u["neither"] == 1, u
        assert u["both"] + u["corroborated_only"] + u["marker_only"] + u["neither"] \
            == u["sessions"], u


def test_usage_for_counts_verification_as_corroboration():
    """Verification is a stronger corroborator than fingerprint, not a weaker one."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "alpha", session="s1", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="verification",
                         outcome="success", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["both"] == 1, u
        assert u["marker_only"] == 0, u


def test_usage_for_counts_a_hot_marker_with_no_injection():
    """Hot skills have no injection event; their markers still land in a cell."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 1, u
        assert u["injections"] == 0, u
        assert u["marker_only"] == 1, u


def test_usage_for_ignores_other_skills():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "beta", session="s1", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 0, u


def test_usage_for_returns_zeros_on_a_broken_db():
    """Read helpers never raise into a caller; a bad path reads as no data."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "l.db"
        bad.write_text("not a database", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            u = ledger.usage_for("alpha", path=bad)
        assert u["sessions"] == 0, u
        assert u["both"] == 0, u
        assert "skillforge:" in err.getvalue(), err.getvalue()


def test_one_marker_row_per_skill_per_session():
    """The index is the backstop for reconcile's own dedupe check."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        try:
            ledger.log_event("detection", "alpha", session="s1", detection="marker",
                             path=db)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("second marker row for the same session was accepted")
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 1, u


def test_marker_index_does_not_block_a_different_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s2", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 2, u


def test_usage_for_ignores_sessionless_lifecycle_rows():
    """save/review/delete are logged with session=None; they are not sessions."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("save", "alpha", outcome="saved", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 0, u
        assert u["neither"] == 0, u


def test_usage_for_ignores_symptom_only_sessions():
    """A symptom detection with nothing injected is not a session that used it."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="symptom", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 0, u
        assert u["neither"] == 0, u


def test_log_edit_writes_a_row():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "scripts/a.py", "p1", path=db)
        con = ledger.connect(db)
        rows = con.execute(
            "SELECT session, prompt_id, path FROM edits").fetchall()
        con.close()
        assert rows == [("s1", "p1", "scripts/a.py")], rows


def test_log_edit_allows_a_missing_prompt_id():
    """Stop may not carry prompt_id; the column is nullable on purpose."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "scripts/a.py", path=db)
        con = ledger.connect(db)
        assert con.execute("SELECT prompt_id FROM edits").fetchone() == (None,)
        con.close()


def test_open_and_read_pending_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        a = ledger.open_correction("s1", "wrong API field", ts="2026-09-03T10:00:00+00:00", path=db)
        b = ledger.open_correction("s1", "wrong auth header", ts="2026-09-03T10:05:00+00:00", path=db)
        got = ledger.pending_corrections("s1", path=db)
        assert [g[0] for g in got] == [a, b], got          # oldest first
        assert got[0][1] == "wrong API field", got
        assert got[0][2] == "2026-09-03T10:00:00+00:00", got


def test_pending_corrections_ignores_other_sessions_and_closed_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.open_correction("other", "not mine", path=db)
        cid = ledger.open_correction("s1", "mine", path=db)
        assert len(ledger.pending_corrections("s1", path=db)) == 1
        ledger.close_correction(cid, "nominated", corroborated=True, path=db)
        assert ledger.pending_corrections("s1", path=db) == []


def test_close_correction_records_status_and_corroboration():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        cid = ledger.open_correction("s1", "mine", path=db)
        ledger.close_correction(cid, "nominated", corroborated=False, path=db)
        con = ledger.connect(db)
        row = con.execute(
            "SELECT status, corroborated FROM corrections WHERE id = ?",
            (cid,)).fetchone()
        con.close()
        assert row == ("nominated", 0), row


def test_corroboration_is_null_until_evaluated():
    """A pending correction has no verdict yet -- 0 and NULL are different facts."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        cid = ledger.open_correction("s1", "mine", path=db)
        con = ledger.connect(db)
        row = con.execute(
            "SELECT corroborated FROM corrections WHERE id = ?", (cid,)).fetchone()
        con.close()
        assert row == (None,), row


def test_edit_count_since_counts_only_later_edits_in_this_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "a.py", ts="2026-09-03T10:00:00+00:00", path=db)
        ledger.log_edit("s1", "b.py", ts="2026-09-03T10:10:00+00:00", path=db)
        ledger.log_edit("s1", "c.py", ts="2026-09-03T10:20:00+00:00", path=db)
        ledger.log_edit("other", "d.py", ts="2026-09-03T10:20:00+00:00", path=db)
        assert ledger.edit_count_since("s1", "2026-09-03T10:05:00+00:00", path=db) == 2


def test_rework_after_needs_the_same_file_on_both_sides():
    """Rework means a file touched again -- not merely more edits."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "a.py", ts="2026-09-03T10:00:00+00:00", path=db)
        ledger.log_edit("s1", "a.py", ts="2026-09-03T10:10:00+00:00", path=db)
        assert ledger.rework_after("s1", "2026-09-03T10:05:00+00:00", path=db) is True


def test_rework_after_is_false_when_later_edits_touch_other_files():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "a.py", ts="2026-09-03T10:00:00+00:00", path=db)
        ledger.log_edit("s1", "b.py", ts="2026-09-03T10:10:00+00:00", path=db)
        assert ledger.rework_after("s1", "2026-09-03T10:05:00+00:00", path=db) is False


def test_rework_after_ignores_other_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "a.py", ts="2026-09-03T10:00:00+00:00", path=db)
        ledger.log_edit("other", "a.py", ts="2026-09-03T10:10:00+00:00", path=db)
        assert ledger.rework_after("s1", "2026-09-03T10:05:00+00:00", path=db) is False


def test_prune_scratch_clears_both_tables_for_one_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_edit("s1", "a.py", path=db)
        ledger.open_correction("s1", "mine", path=db)
        ledger.log_edit("keep", "b.py", path=db)
        ledger.prune_scratch(session="s1", path=db)
        con = ledger.connect(db)
        assert con.execute("SELECT COUNT(*) FROM edits").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == 0
        con.close()


def test_prune_scratch_sweeps_by_ttl():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        old = (ledger.now_utc() - datetime.timedelta(hours=48)).isoformat(timespec="seconds")
        ledger.log_edit("s1", "a.py", ts=old, path=db)
        ledger.open_correction("s1", "stale", ts=old, path=db)
        ledger.log_edit("s1", "b.py", path=db)
        ledger.prune_scratch(older_than_hours=24, path=db)
        con = ledger.connect(db)
        assert con.execute("SELECT COUNT(*) FROM edits").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == 0
        con.close()


def test_event_totals_counts_by_type_and_detection():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "a", tier="warm", session="s1", path=db)
        ledger.log_event("injection", "b", tier="warm", session="s1", path=db)
        ledger.log_event("detection", "a", detection="marker", session="s1", path=db)
        ledger.log_event("detection", "a", detection="verification",
                         outcome="success", session="s1", path=db)
        t = ledger.event_totals(path=db)
        assert t["by_type"] == {"injection": 2, "detection": 2}, t
        assert t["by_detection"] == {"marker": 1, "verification": 1}, t


def test_event_totals_counts_null_outcome_as_unknown():
    """The bug this whole command exists to surface.

    bash_outcome returned None for every call ever made, so every
    verification landed with a NULL outcome. A report that folded those
    into 'no successes' would have hidden it; 'unknown' shows it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for _ in range(3):
            ledger.log_event("detection", "a", detection="verification",
                             session="s1", path=db)
        t = ledger.event_totals(path=db)
        assert t["verification_outcomes"] == {
            "success": 0, "failure": 0, "unknown": 3}, t


def test_event_totals_is_all_zeros_on_an_empty_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        t = ledger.event_totals(path=db)
        assert t["by_type"] == {}, t
        assert t["by_detection"] == {}, t
        assert t["verification_outcomes"] == {
            "success": 0, "failure": 0, "unknown": 0}, t


def test_event_totals_never_raises_into_a_display():
    """Ledger reads are best-effort; a display gets zeros, not a traceback."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "not-a-db"
        bad.write_text("this is not sqlite")
        err = io.StringIO()
        with redirect_stderr(err):
            t = ledger.event_totals(path=bad)
        assert t["by_type"] == {}, t
        assert "skillforge" in err.getvalue(), err.getvalue()


def test_event_totals_sums_null_and_empty_outcome_into_unknown():
    """GROUP BY outcome returns NULL and '' as separate rows; both must

    land in 'unknown' by addition, not overwrite each other -- the bug
    was `out[key] = n` clobbering the first row's count with the second's.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "a", detection="verification",
                         outcome=None, session="s1", path=db)
        ledger.log_event("detection", "a", detection="verification",
                         outcome="", session="s1", path=db)
        ledger.log_event("detection", "a", detection="verification",
                         outcome="", session="s1", path=db)
        t = ledger.event_totals(path=db)
        assert t["verification_outcomes"] == {
            "success": 0, "failure": 0, "unknown": 3}, t


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
