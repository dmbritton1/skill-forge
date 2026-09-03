"""Tests for the Stop/SessionEnd reconciler (slice C2 design 2-4).
Run: python3 tests/test_reconcile.py
"""
import datetime
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

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


class Spawner:
    """Stands in for Popen. The real drafter must never run in a suite."""

    def __init__(self, explode=False):
        self.calls = []
        self.explode = explode

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        if self.explode:
            raise OSError("no such executable")


def with_spawner(spawner, fn):
    real = reconcile._spawn
    reconcile._spawn = spawner
    try:
        return fn()
    finally:
        reconcile._spawn = real


def struggle(session="s1", target="make test"):
    ledger.log_signal(session, target, False)
    ledger.log_signal(session, target, False)
    ledger.log_signal(session, target, True)


def stop(session="s1", cwd=".", **extra):
    data = {"session_id": session, "cwd": cwd, "hook_event_name": "Stop"}
    data.update(extra)
    return reconcile.run(data)


def draft_rows():
    con = ledger.connect()
    try:
        return con.execute(
            "SELECT session, signature, status FROM drafts ORDER BY id").fetchall()
    finally:
        con.close()


def arg_of(argv, flag):
    return argv[argv.index(flag) + 1]


def test_a_struggle_spawns_one_drafter():
    def check(home):
        write_index(home, [])
        struggle()
        sp = Spawner()
        with_spawner(sp, stop)
        assert len(sp.calls) == 1
        assert draft_rows() == [("s1", "make test", "drafting")]
    in_sandbox(check)


def test_spawn_passes_the_draft_id_target_and_window():
    def check(home):
        write_index(home, [])
        struggle()
        sp = Spawner()
        with_spawner(sp, lambda: stop(transcript_path="/tmp/t.jsonl"))
        argv = sp.calls[0]
        assert "draft.py" in " ".join(argv) and "run" in argv
        assert arg_of(argv, "--target") == "make test"
        assert arg_of(argv, "--transcript") == "/tmp/t.jsonl"
        assert arg_of(argv, "--draft-id") == "1"
        assert arg_of(argv, "--since") and arg_of(argv, "--until")
    in_sandbox(check)


def test_no_struggle_spawns_nothing():
    def check(home):
        write_index(home, [])
        ledger.log_signal("s1", "make test", False)
        ledger.log_signal("s1", "make test", True)
        sp = Spawner()
        with_spawner(sp, stop)
        assert sp.calls == [] and draft_rows() == []
    in_sandbox(check)


def test_the_same_target_is_not_drafted_twice():
    def check(home):
        write_index(home, [])
        struggle()
        with_spawner(Spawner(), stop)
        ledger.set_draft_status(1, "ready")   # clear `busy`, keep the signature
        sp = Spawner()
        with_spawner(sp, stop)
        assert sp.calls == []
        assert len(draft_rows()) == 1
    in_sandbox(check)


def test_a_running_drafter_blocks_a_second_spawn():
    def check(home):
        write_index(home, [])
        struggle()
        struggle(target="make lint")
        sp = Spawner()
        with_spawner(sp, stop)
        assert len(sp.calls) == 1          # one per Stop, even with two signals
        sp2 = Spawner()
        with_spawner(sp2, stop)
        assert sp2.calls == []             # still drafting
    in_sandbox(check)


def test_second_target_drafts_once_the_first_settles():
    def check(home):
        write_index(home, [])
        struggle()
        struggle(target="make lint")
        with_spawner(Spawner(), stop)
        ledger.set_draft_status(1, "ready")
        sp = Spawner()
        with_spawner(sp, stop)
        assert arg_of(sp.calls[0], "--target") == "make lint"
    in_sandbox(check)


def test_a_failed_spawn_marks_the_row_failed():
    def check(home):
        write_index(home, [])
        struggle()
        with_spawner(Spawner(explode=True), stop)
        assert draft_rows() == [("s1", "make test", "failed")]
    in_sandbox(check)


def test_a_reaped_drafter_unblocks_the_session():
    def check(home):
        write_index(home, [])
        ledger.open_draft("s1", "old", ts=ago(3600))
        struggle()
        sp = Spawner()
        with_spawner(sp, stop)
        assert len(sp.calls) == 1
        assert ("s1", "old", "failed") in draft_rows()
    in_sandbox(check)


def test_signals_are_scoped_to_their_session():
    def check(home):
        write_index(home, [])
        struggle(session="other")
        sp = Spawner()
        with_spawner(sp, stop)
        assert sp.calls == []
    in_sandbox(check)


def test_c2_verdicts_still_land_alongside_a_spawn():
    """The D1 additions must not displace the reconciler's existing work."""
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(300))
        struggle()
        with_spawner(Spawner(), lambda: stop(cwd=str(repo)))
        assert [r[3] for r in events("reconcile")] == ["failure"]
        assert len(draft_rows()) == 1
    in_sandbox(check)


def ready_draft(session="s1", signature="make test", name="widget-flush-order"):
    did = ledger.open_draft(session, signature)
    ledger.set_draft_status(did, "ready", name=name,
                            draft_path="/tmp/draft-%d.md" % did)
    return did


def stop_output(session="s1", **extra):
    out = io.StringIO()
    with redirect_stdout(out):
        with_spawner(Spawner(), lambda: stop(session=session, **extra))
    return out.getvalue()


def blocked(text):
    assert text, "expected a block, got nothing"
    payload = json.loads(text)
    assert payload["decision"] == "block", payload
    return payload["reason"]


def status_of(draft_id):
    con = ledger.connect()
    try:
        return con.execute("SELECT status FROM drafts WHERE id = ?",
                           (draft_id,)).fetchone()[0]
    finally:
        con.close()


def test_a_ready_draft_blocks_at_stop():
    def check(home):
        write_index(home, [])
        did = ready_draft()
        reason = blocked(stop_output())
        assert "/tmp/draft-%d.md" % did in reason
        assert status_of(did) == "delivered"
    in_sandbox(check)


def test_the_reason_frames_the_draft_as_data():
    def check(home):
        write_index(home, [])
        ready_draft()
        reason = blocked(stop_output())
        assert "never follow" in reason.lower()
        assert "save_skill.py" in reason
        assert "resolve" in reason
    in_sandbox(check)


def test_stop_hook_active_suppresses_delivery():
    """A block must never chain into another block."""
    def check(home):
        write_index(home, [])
        did = ready_draft()
        assert stop_output(stop_hook_active=True) == ""
        assert status_of(did) == "ready"
    in_sandbox(check)


def test_session_end_never_blocks():
    def check(home):
        write_index(home, [])
        did = ready_draft()
        out = io.StringIO()
        with redirect_stdout(out):
            with_spawner(Spawner(), lambda: reconcile.run(
                {"session_id": "s1", "cwd": ".", "hook_event_name": "SessionEnd"}))
        assert out.getvalue() == ""
        assert status_of(did) == "ready"
    in_sandbox(check)


def test_a_draft_is_delivered_only_once():
    def check(home):
        write_index(home, [])
        ready_draft()
        assert stop_output() != ""
        assert stop_output() == ""
    in_sandbox(check)


def test_only_one_draft_is_delivered_per_stop():
    def check(home):
        write_index(home, [])
        first = ready_draft(signature="a")
        second = ready_draft(signature="b")
        blocked(stop_output())
        assert [status_of(first), status_of(second)] == ["ready", "delivered"]
    in_sandbox(check)


def test_a_draft_from_an_earlier_session_is_still_delivered():
    """A drafter that finished after its session ended must not be stranded."""
    def check(home):
        write_index(home, [])
        ready_draft(session="yesterday")
        assert blocked(stop_output(session="today"))
    in_sandbox(check)


def test_discard_history_adds_the_recurrence_note():
    def check(home):
        write_index(home, [])
        old = ledger.open_draft("s0", "make test")
        ledger.set_draft_status(old, "discarded")
        ready_draft(signature="make test")
        reason = blocked(stop_output())
        assert "recurring" in reason
    in_sandbox(check)


def test_no_recurrence_note_on_a_first_draft():
    def check(home):
        write_index(home, [])
        ready_draft()
        assert "recurring" not in blocked(stop_output())
    in_sandbox(check)


def test_a_draft_with_no_path_is_not_delivered():
    def check(home):
        write_index(home, [])
        did = ledger.open_draft("s1", "make test")
        ledger.set_draft_status(did, "ready")     # no path recorded
        assert stop_output() == ""
    in_sandbox(check)


def test_delivery_survives_a_session_with_no_c2_events():
    """The regression Task 7's extraction exists to prevent."""
    def check(home):
        write_index(home, [])
        ready_draft()
        assert blocked(stop_output())
    in_sandbox(check)


def signal_sessions():
    con = ledger.connect()
    try:
        return [r[0] for r in con.execute(
            "SELECT session FROM signals ORDER BY id")]
    finally:
        con.close()


def test_session_end_prunes_this_sessions_breadcrumbs():
    def check(home):
        write_index(home, [])
        struggle(session="s1")
        struggle(session="s2")
        with_spawner(Spawner(), lambda: reconcile.run(
            {"session_id": "s1", "cwd": ".", "hook_event_name": "SessionEnd"}))
        assert set(signal_sessions()) == {"s2"}
    in_sandbox(check)


def test_stop_does_not_prune_breadcrumbs():
    def check(home):
        write_index(home, [])
        struggle()
        with_spawner(Spawner(), stop)
        assert signal_sessions() == ["s1", "s1", "s1"]
    in_sandbox(check)


def test_session_end_keeps_the_draft_row():
    """Breadcrumbs are scratch; draft outcomes are the recurrence memory."""
    def check(home):
        write_index(home, [])
        struggle()
        with_spawner(Spawner(), stop)
        with_spawner(Spawner(), lambda: reconcile.run(
            {"session_id": "s1", "cwd": ".", "hook_event_name": "SessionEnd"}))
        assert len(draft_rows()) == 1
    in_sandbox(check)


def write_markers(root, lines):
    p = reconcile.marker_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_read_markers_collects_skill_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, ['{"skill": "alpha"}', '{"skill": "beta"}'])
        skills, corrections = reconcile.read_scratch(root)
        assert skills == {"alpha", "beta"}
        assert corrections == []


def test_read_markers_consumes_the_file():
    """Not tidiness: a surviving line would credit the next session."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = write_markers(root, ['{"skill": "alpha"}'])
        skills, corrections = reconcile.read_scratch(root)
        assert skills == {"alpha"}
        assert corrections == []
        assert not p.exists()
        assert reconcile.read_scratch(root) == (set(), [])


def test_read_markers_skips_junk_without_losing_good_lines():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, [
            "",
            "not json at all",
            '["alpha"]',                 # valid JSON, not an object
            '{"skill": 7}',              # not a string
            '{"skill": ""}',             # empty after strip
            '{"action": "did a thing"}', # no skill key
            "[" * 20000,                 # json.loads raises RecursionError,
                                          # not ValueError -- must not escape
            '{"skill": "  alpha  "}',    # stripped
        ])
        skills, corrections = reconcile.read_scratch(root)
        assert skills == {"alpha"}
        assert corrections == []


def test_read_markers_still_consumes_a_file_of_pure_junk():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = write_markers(root, ["garbage", "more garbage"])
        assert reconcile.read_scratch(root) == (set(), [])
        assert not p.exists()


def test_read_markers_caps_the_read_and_the_name():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        long_name = "n" * 400
        write_markers(root, ['{"skill": "%s"}' % long_name])
        got, corrections = reconcile.read_scratch(root)
        assert got == {"n" * reconcile.MAX_MARKER_NAME}, got
        assert corrections == []

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        filler = ['{"skill": "pad%d"}' % i
                  for i in range(reconcile.MAX_MARKER_BYTES // 20 + 200)]
        write_markers(root, filler + ['{"skill": "last"}'])
        got, corrections = reconcile.read_scratch(root)
        assert "last" not in got, "read past the size cap"
        assert got, "cap discarded everything"


def test_read_markers_on_a_missing_file_is_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert reconcile.read_scratch(pathlib.Path(tmp)) == (set(), [])


def test_read_markers_survives_binary_content():
    """errors='replace', not a crash: the file is model-written, not trusted."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = reconcile.marker_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'\xff\xfe\x00\x00\n{"skill": "alpha"}\n')
        skills, corrections = reconcile.read_scratch(root)
        assert skills == {"alpha"}
        assert corrections == []


def marker_rows():
    return [r for r in events("detection") if r[1] == "marker"]


def stop_in(root, session="s1", final=False):
    reconcile.run({"session_id": session, "cwd": str(root),
                   "hook_event_name": "SessionEnd" if final else "Stop"})


def test_marker_credits_a_warm_skill_injected_this_session():
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_marker_for_a_skill_never_injected_is_dropped():
    """The gate that stops a claim crediting a skill the model never saw."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_marker_credits_a_hot_skill_with_no_injection_event():
    """The harness injects hot skills and we never see it; without this
    exemption the marker is useless for the one tier that has no other signal."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "hot",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_marker_for_an_out_of_scope_project_skill_is_dropped():
    def check(home):
        other = home / "other-project"
        other.mkdir()
        here = home / "here"
        here.mkdir()
        write_index(home, [{"name": "alpha", "root": str(other), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(here, ['{"skill": "alpha"}'])
        stop_in(here)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_marker_for_an_unknown_name_is_dropped():
    def check(home):
        write_index(home, [])
        write_markers(home, ['{"skill": "ghost"}'])
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_second_stop_does_not_duplicate_a_marker_row():
    """Stop fires every turn; the row must be written exactly once."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert len(marker_rows()) == 1, marker_rows()
    in_sandbox(check)


def test_a_marker_does_not_carry_an_outcome():
    """A null outcome is what keeps a performative marker from promoting a skill."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert marker_rows()[0][3] is None, marker_rows()
    in_sandbox(check)


def test_a_marker_only_session_still_reconciles():
    """A hot skill's marker arrives in a session with no other ledger rows,
    so ingestion cannot sit behind the `no events` early return."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "hot",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home, session="fresh")
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_a_consumed_marker_does_not_credit_the_next_session():
    """The spec's reason for consuming the file, asserted end to end: the
    model writes no session id, so a surviving line would credit whichever
    session next injects that skill."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home, session="s1")
        ledger.log_event("injection", "alpha", session="s2", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        stop_in(home, session="s2")          # no new marker file written
        assert len(marker_rows()) == 1, marker_rows()
    in_sandbox(check)


def test_a_stop_with_no_marker_file_writes_no_marker_row():
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_a_marker_and_a_fingerprint_both_land_for_one_session():
    """The `both` cell of the truth table, produced through the real
    pipeline rather than by logging rows directly (as test_ledger.py does).

    Also pins that a marker does not resolve needs_fingerprint: crediting
    the marker must not suppress the independent fingerprint credit --
    if it did, this cell would silently and permanently empty.

    Two Stop calls, deliberately: within a single call, session_state is
    built from rows fetched BEFORE that call's own _credit_markers writes
    the marker row, so a marker credited this turn can never appear in
    this turn's own `detections` set -- a one-call test cannot observe
    needs_fingerprint reacting to it at all. The second call re-reads the
    ledger fresh and so sees the first call's marker in `state`, which is
    exactly the scenario needs_fingerprint's exclusion set governs.
    """
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [{"name": "fixer", "root": str(home), "tier": "warm",
                            "fingerprints": [["json", "dumps", "sort_keys"]]}])
        ledger.log_event("injection", "fixer", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(repo, ['{"skill": "fixer"}'])
        stop_in(repo, session="s1")             # credits the marker
        (repo / "seed.py").write_text(
            "seed = 1\nout = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        stop_in(repo, session="s1")             # should independently credit the fingerprint
        detections = events("detection")
        assert ("fixer", "marker", None, None) in detections, detections
        assert ("fixer", "fingerprint", None, None) in detections, detections
    in_sandbox(check)


def correction_rows():
    con = ledger.connect()
    try:
        return con.execute(
            "SELECT session, what, status, corroborated FROM corrections"
            " ORDER BY id").fetchall()
    finally:
        con.close()


def test_read_scratch_returns_skills_and_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, ['{"skill": "alpha"}',
                             '{"event": "correction", "what": "wrong field"}'])
        skills, corrections = reconcile.read_scratch(root)
        assert skills == {"alpha"}, skills
        assert corrections == ["wrong field"], corrections


def test_read_scratch_still_consumes_the_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = write_markers(root, ['{"event": "correction", "what": "x"}'])
        reconcile.read_scratch(root)
        assert not p.exists()
        assert reconcile.read_scratch(root) == (set(), [])


def test_read_scratch_skips_junk_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, [
            '{"event": "correction"}',                  # no what
            '{"event": "correction", "what": 7}',        # not a string
            '{"event": "correction", "what": "   "}',    # empty after strip
            '{"event": "something-else", "what": "no"}',  # wrong event
            '{"event": "correction", "what": "  real  "}',
        ])
        skills, corrections = reconcile.read_scratch(root)
        assert skills == set(), skills
        assert corrections == ["real"], corrections


def test_read_scratch_caps_a_long_correction():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, ['{"event": "correction", "what": "%s"}' % ("x" * 900)])
        _, corrections = reconcile.read_scratch(root)
        assert len(corrections[0]) == ledger.MAX_CORRECTION_CHARS, len(corrections[0])


def test_a_correction_lands_in_the_table_at_stop():
    def check(home):
        write_index(home, [])
        write_markers(home, ['{"event": "correction", "what": "wrong field"}'])
        stop_in(home)
        rows = correction_rows()
        assert len(rows) == 1, rows
        assert rows[0][0] == "s1" and rows[0][1] == "wrong field", rows
        assert rows[0][2] == "pending", rows
        assert rows[0][3] is None, "corroboration is not evaluated at ingest"
    in_sandbox(check)


def test_a_correction_only_session_reconciles():
    """A correction can arrive with no injections and no other events."""
    def check(home):
        write_index(home, [])
        write_markers(home, ['{"event": "correction", "what": "x"}'])
        stop_in(home, session="fresh")
        assert len(correction_rows()) == 1, correction_rows()
    in_sandbox(check)


def test_a_second_stop_does_not_re_ingest():
    """The file is consumed, so nothing is left to read twice."""
    def check(home):
        write_index(home, [])
        write_markers(home, ['{"event": "correction", "what": "x"}'])
        stop_in(home)
        stop_in(home)
        assert len(correction_rows()) == 1, correction_rows()
    in_sandbox(check)


def old_correction(home, what="wrong field", secs=400, session="s1"):
    """A correction old enough to have settled, with edits after it."""
    write_index(home, [])
    cid = ledger.open_correction(session, what, ts=ago(secs))
    ledger.log_edit(session, "a.py", ts=ago(secs + 10))
    ledger.log_edit(session, "a.py", ts=ago(secs - 10))
    ledger.log_edit(session, "b.py", ts=ago(secs - 20))
    return cid


def test_a_settled_correction_nominates_a_drafter():
    def check(home):
        old_correction(home)
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        assert len(sp.calls) == 1, sp.calls
        argv = sp.calls[0]
        assert "--kind" in argv and "correction" in argv, argv
        assert correction_rows()[0][2] == "nominated", correction_rows()
    in_sandbox(check)


def test_an_unsettled_correction_does_not_nominate():
    def check(home):
        old_correction(home, secs=30)
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        assert sp.calls == [], sp.calls
        assert correction_rows()[0][2] == "pending", correction_rows()
    in_sandbox(check)


def test_a_newer_correction_resets_the_settle_clock():
    """Still being corrected means the episode is not over."""
    def check(home):
        old_correction(home)
        ledger.open_correction("s1", "and this too", ts=ago(10))
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        assert sp.calls == [], sp.calls
    in_sandbox(check)


def test_a_correction_below_the_cost_floor_never_nominates():
    """One trivial edit is a typo fix, not a lesson -- and a model call."""
    def check(home):
        write_index(home, [])
        ledger.open_correction("s1", "tiny", ts=ago(400))
        ledger.log_edit("s1", "a.py", ts=ago(380))
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home, final=True))
        assert sp.calls == [], sp.calls
        assert correction_rows()[0][2] == "discarded", correction_rows()
    in_sandbox(check)


def test_an_uncorroborated_correction_still_nominates():
    """Corroboration is metadata, not a gate. This is the test that pins it."""
    def check(home):
        write_index(home, [])
        ledger.open_correction("s1", "no rework", ts=ago(400))
        ledger.log_edit("s1", "a.py", ts=ago(390))
        ledger.log_edit("s1", "b.py", ts=ago(380))
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        assert len(sp.calls) == 1, sp.calls
        assert correction_rows()[0][3] == 0, "recorded as uncorroborated"
    in_sandbox(check)


def test_corroboration_is_recorded_when_a_file_is_reworked():
    def check(home):
        old_correction(home)
        with_spawner(Spawner(), lambda: stop_in(home))
        assert correction_rows()[0][3] == 1, correction_rows()
    in_sandbox(check)


def test_session_end_nominates_regardless_of_the_clock():
    def check(home):
        write_index(home, [])
        ledger.open_correction("s1", "recent", ts=ago(10))
        ledger.log_edit("s1", "a.py", ts=ago(9))
        ledger.log_edit("s1", "a.py", ts=ago(8))
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home, final=True))
        assert len(sp.calls) == 1, sp.calls
    in_sandbox(check)


def test_one_nomination_per_correction():
    """Only one correction is seeded, so this does not isolate which cap
    holds: on the second Stop, `busy` is true (the first draft is still
    `drafting`) AND the row is no longer in `pending_corrections` (closed
    to `nominated`) -- either alone would already block a second spawn.
    Both are real, independently-sufficient caps; no test in this file
    isolates `busy` alone since nothing here seeds a `drafting` row by
    hand instead of through a real nomination.
    """
    def check(home):
        old_correction(home)
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        with_spawner(sp, lambda: stop_in(home))
        assert len(sp.calls) == 1, sp.calls
    in_sandbox(check)


def test_only_one_drafter_runs_at_a_time():
    def check(home):
        old_correction(home)
        ledger.open_correction("s1", "second", ts=ago(500))
        sp = Spawner()
        with_spawner(sp, lambda: stop_in(home))
        assert len(sp.calls) == 1, sp.calls
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
