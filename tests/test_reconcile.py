"""Tests for the Stop/SessionEnd reconciler (slice C2 design 2-4).
Run: python3 tests/test_reconcile.py
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import reconcile


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def git_repo(root):
    """A real repo with one commit, so `git diff HEAD` has a HEAD to diff."""
    root.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(list(a), cwd=str(root), check=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    run("git", "config", "commit.gpgsign", "false")
    (root / "seed.py").write_text("seed = 1\n", encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed")
    return root


def write_index(home, entries):
    p = home / ".claude" / "skillforge" / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def ago(seconds):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def events(event_type):
    con = ledger.connect()
    try:
        return con.execute(
            'SELECT skill, detection, "trigger", outcome FROM events'
            " WHERE event_type = ? ORDER BY id", (event_type,)).fetchall()
    finally:
        con.close()


def fire(cwd, session="s1", event="Stop"):
    return reconcile.run({"session_id": session, "hook_event_name": event,
                          "cwd": str(cwd)})


SKILL_ENTRY = {"name": "fixer", "kind": "skill",
               "fingerprints": [["json", "dumps", "sort_keys"]]}


def test_fingerprint_in_tracked_diff_credits_one_use():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "seed.py").write_text(
            "seed = 1\nout = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        assert fire(repo) == 0
        assert events("detection") == [("fixer", "fingerprint", None, None)]
    in_sandbox(check)


def test_fingerprint_in_untracked_file_counts():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_credit_is_not_written_twice():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        fire(repo)
        fire(repo, event="SessionEnd")
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_existing_verification_suppresses_fingerprint_credit():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        ledger.log_event("detection", "fixer", detection="verification",
                         outcome="success", session="s1", ts=ago(60))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        kinds = [r[1] for r in events("detection")]
        assert kinds == ["verification"], kinds
    in_sandbox(check)


def test_preexisting_fingerprint_blocks_credit():
    for preexisting in (1, None):
        def check(home, preexisting=preexisting):
            repo = git_repo(home / "repo")
            write_index(home, [SKILL_ENTRY])
            ledger.log_event("injection", "fixer", session="s1",
                             preexisting_fingerprint=preexisting, ts=ago(120))
            (repo / "new.py").write_text(
                "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
            fire(repo)
            assert events("detection") == []
        in_sandbox(check)


def test_no_fingerprint_match_writes_nothing():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text("print('unrelated')\n", encoding="utf-8")
        fire(repo)
        assert events("detection") == []
    in_sandbox(check)


def test_skill_missing_from_index_is_skipped():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        assert fire(repo) == 0
        assert events("detection") == []
    in_sandbox(check)


def test_stop_stops_probing_after_the_window():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0,
                         ts=ago(reconcile.RECONCILE_WINDOW_S + 60))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        assert events("detection") == []
        # SessionEnd runs once, so it probes regardless of age
        fire(repo, event="SessionEnd")
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_non_git_cwd_writes_nothing_and_exits_zero():
    def check(home):
        plain = home / "plain"
        plain.mkdir()
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        assert fire(plain) == 0
        assert events("detection") == []
    in_sandbox(check)


def test_empty_and_malformed_payloads_exit_zero():
    def check(home):
        assert reconcile.run({}) == 0
        assert reconcile.run({"session_id": None, "cwd": str(home)}) == 0
    in_sandbox(check)


def test_missing_index_exits_zero():
    def check(home):
        repo = git_repo(home / "repo")
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        assert fire(repo) == 0
        assert events("detection") == []
    in_sandbox(check)


TRAP_ENTRY = {"name": "trap", "kind": "antiskill",
              "fingerprints": [["widget", "flush", "guard"]]}


def inject_trap(seconds_ago):
    """An anti-skill injection plus the symptom detection that triggered it.

    detect.py writes both in one hook call, so they share a timestamp -- the
    MIN_ESCAPE_S floor is what stops this pair from reading as a re-fire.
    """
    ledger.log_event("detection", "trap", detection="symptom",
                     trigger="symptom", session="s1", ts=ago(seconds_ago))
    ledger.log_event("injection", "trap", tier="warm", trigger="symptom",
                     session="s1", preexisting_fingerprint=1, ts=ago(seconds_ago))


def test_refire_inside_window_is_one_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(300))
        fire(repo)
        assert events("reconcile") == [("trap", None, "refire", "failure")]
        fire(repo)
        fire(repo, event="SessionEnd")
        assert len(events("reconcile")) == 1   # settled skills are not re-settled
    in_sandbox(check)


def test_triggering_symptom_alone_is_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        fire(repo)
        assert events("reconcile") == []
    in_sandbox(check)


def test_echo_inside_the_escape_floor_is_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1",
                         ts=ago(600 - (reconcile.MIN_ESCAPE_S - 10)))
        fire(repo)
        assert events("reconcile") == []
    in_sandbox(check)


def test_refire_past_the_window_is_a_fresh_trap_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(reconcile.RECONCILE_WINDOW_S + 600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(60))
        fire(repo)
        assert events("reconcile") == []
        # The trap demonstrably fired again, just after the window -- it must
        # not be credited a bogus success at SessionEnd for lack of evidence.
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_prompt_triggered_injection_with_no_detection_gets_no_verdict():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        # Injected on plain keyword relevance -- its trap never sprung, so
        # there is no evidence either way. It must not bank a free success.
        ledger.log_event("injection", "trap", tier="warm", trigger="prompt",
                         session="s1", preexisting_fingerprint=1, ts=ago(600))
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_session_end_without_refire_is_a_success():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        fire(repo)
        assert events("reconcile") == []       # Stop alone never concludes success
        fire(repo, event="SessionEnd")
        assert events("reconcile") == [("trap", None, "refire", "success")]
    in_sandbox(check)


def test_session_end_inside_the_escape_floor_concludes_nothing():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(reconcile.MIN_ESCAPE_S - 20)
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_regular_skills_get_no_refire_verdict():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=1, ts=ago(600))
        ledger.log_event("detection", "fixer", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(300))
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def inject_trap_at(base, seconds_ago):
    """Same pair as inject_trap, but timestamped off one frozen `base` instant
    instead of a fresh now() call -- boundary tests need the injection and
    the later symptom to be an *exact* number of seconds apart, and two
    independent ago() calls (each its own now()) can drift across a second
    boundary between the two statements.
    """
    ts = (base - datetime.timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
    ledger.log_event("detection", "trap", detection="symptom",
                     trigger="symptom", session="s1", ts=ts)
    ledger.log_event("injection", "trap", tier="warm", trigger="symptom",
                     session="s1", preexisting_fingerprint=1, ts=ts)


def symptom_at(base, seconds_ago):
    ts = (base - datetime.timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
    ledger.log_event("detection", "trap", detection="symptom",
                     trigger="symptom", session="s1", ts=ts)


def test_refire_exactly_at_min_escape_s_is_a_failure():
    # Pins the closed interval's lower edge: [T_inject + MIN_ESCAPE_S, ...].
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        base = datetime.datetime.now(datetime.timezone.utc)
        inject_trap_at(base, 600)
        symptom_at(base, 600 - reconcile.MIN_ESCAPE_S)
        fire(repo)
        assert events("reconcile") == [("trap", None, "refire", "failure")]
    in_sandbox(check)


def test_refire_exactly_at_reconcile_window_s_is_a_failure():
    # Pins the closed interval's upper edge: [..., T_inject + RECONCILE_WINDOW_S].
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        base = datetime.datetime.now(datetime.timezone.utc)
        inject_trap_at(base, reconcile.RECONCILE_WINDOW_S)
        symptom_at(base, 0)
        fire(repo)
        assert events("reconcile") == [("trap", None, "refire", "failure")]
    in_sandbox(check)


def test_refire_one_second_past_the_window_gets_no_verdict():
    # One second beyond RECONCILE_WINDOW_S must fall outside the closed
    # interval entirely -- an off-by-one (<= vs <) here would wrongly convict.
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        base = datetime.datetime.now(datetime.timezone.utc)
        inject_trap_at(base, reconcile.RECONCILE_WINDOW_S + 1)
        symptom_at(base, 0)
        fire(repo)
        assert events("reconcile") == []
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_verdicts_are_scoped_to_their_own_session():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s2", ts=ago(300))
        fire(repo)          # the re-fire belongs to s2, not s1
        assert events("reconcile") == []
    in_sandbox(check)


def sig(target, ok, ts="2026-08-24T10:00:00+00:00"):
    return (target, 1 if ok else 0, ts)


def test_two_failures_then_success_is_a_signal():
    out = reconcile.struggle_targets([
        sig("make test", False, "t1"), sig("make test", False, "t2"),
        sig("make test", True, "t3")])
    assert out == [("make test", "t1", "t3")]


def test_one_failure_then_success_is_not_a_struggle():
    assert reconcile.struggle_targets([
        sig("make test", False, "t1"), sig("make test", True, "t2")]) == []


def test_success_resets_the_streak():
    """fail, pass, fail, pass never reaches two consecutive failures."""
    assert reconcile.struggle_targets([
        sig("t", False, "t1"), sig("t", True, "t2"),
        sig("t", False, "t3"), sig("t", True, "t4")]) == []


def test_failures_without_a_fix_produce_nothing():
    assert reconcile.struggle_targets([
        sig("t", False, "t1"), sig("t", False, "t2"), sig("t", False, "t3")]) == []


def test_interleaved_targets_are_tracked_separately():
    out = reconcile.struggle_targets([
        sig("a", False, "1"), sig("b", False, "2"),
        sig("a", False, "3"), sig("b", True, "4"),
        sig("a", True, "5")])
    assert out == [("a", "1", "5")]


def test_three_failures_then_success_still_signals():
    out = reconcile.struggle_targets([
        sig("t", False, "1"), sig("t", False, "2"),
        sig("t", False, "3"), sig("t", True, "4")])
    assert out == [("t", "1", "4")]


def test_repeat_struggle_on_one_target_yields_one_signal():
    out = reconcile.struggle_targets([
        sig("t", False, "1"), sig("t", False, "2"), sig("t", True, "3"),
        sig("t", False, "4"), sig("t", False, "5"), sig("t", True, "6")])
    assert out == [("t", "1", "3")]


def test_window_starts_at_the_first_failure_of_the_streak():
    """A success before the streak must not widen the evidence window."""
    out = reconcile.struggle_targets([
        sig("t", True, "1"), sig("t", False, "2"),
        sig("t", False, "3"), sig("t", True, "4")])
    assert out == [("t", "2", "4")]


def test_draft_blockers_reports_signatures_and_busy():
    def check(home):
        ledger.open_draft("s1", "make test")
        con = ledger.connect()
        try:
            done, busy = reconcile.draft_blockers(con, "s1")
            assert done == {"make test"}
            assert busy is True
            done2, busy2 = reconcile.draft_blockers(con, "s2")
            assert done2 == set() and busy2 is False
        finally:
            con.close()
    in_sandbox(check)


def test_draft_blockers_not_busy_once_the_row_settles():
    def check(home):
        did = ledger.open_draft("s1", "make test")
        ledger.set_draft_status(did, "ready")
        con = ledger.connect()
        try:
            done, busy = reconcile.draft_blockers(con, "s1")
            assert done == {"make test"} and busy is False
        finally:
            con.close()
    in_sandbox(check)


def test_reap_stale_drafts_flips_only_old_drafting_rows():
    def check(home):
        fresh = ledger.open_draft("s1", "fresh")
        stale = ledger.open_draft("s1", "stale", ts=ago(3600))
        ready = ledger.open_draft("s1", "ready", ts=ago(3600))
        ledger.set_draft_status(ready, "ready")
        con = ledger.connect()
        try:
            reconcile.reap_stale_drafts(con, reconcile.now_utc())
            got = dict(con.execute("SELECT id, status FROM drafts"))
        finally:
            con.close()
        assert got[fresh] == "drafting"
        assert got[stale] == "failed"
        assert got[ready] == "ready"
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
