"""Tests for the regrade replay driver. Run: python3 tests/test_bench_regrade.py"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import regrade


def test_probe_line_parser_reads_the_repo_pass_fail_format():
    out = "PASS test_a\nFAIL test_b: AssertionError()\nPASS test_c\n"
    detail = regrade.parse_probe_output(out)
    assert detail == {"test_a": True, "test_b": False, "test_c": True}


def test_probe_score_is_the_passing_fraction():
    r = regrade.summarize({"a": True, "b": False, "c": True, "d": True})
    assert r["probe_passed"] == 3 and r["probe_total"] == 4
    assert abs(r["probe_score"] - 0.75) < 1e-9


def test_summarize_of_an_empty_run_scores_zero_not_one():
    # A probe suite that could not start must not read as a perfect artifact.
    r = regrade.summarize({})
    assert r["probe_total"] == 0 and r["probe_score"] == 0.0


def test_summarize_treats_a_short_denominator_as_a_failed_run_not_a_partial_score():
    # A suite that dies partway (5 of 6 probes reporting) must not be scored
    # as 0.833 -- indistinguishable from a genuine 0.833. It must fail outright.
    detail = {"a": True, "b": True, "c": True, "d": True, "e": True}
    r = regrade.summarize(detail, expected=6)
    assert r["probe_total"] == 0 and r["probe_passed"] == 0
    assert r["probe_score"] == 0.0


def test_summarize_with_expected_count_matching_scores_normally():
    detail = {"a": True, "b": False}
    r = regrade.summarize(detail, expected=2)
    assert r["probe_total"] == 2 and r["probe_passed"] == 1
    assert abs(r["probe_score"] - 0.5) < 1e-9


def test_probe_suite_is_chosen_by_task():
    assert regrade.suite_for("sf-author-response-text").endswith("probe_response_text.py")
    assert regrade.suite_for(
        "sf-author-fingerprint-preexisting").endswith("probe_fingerprint_preexisting.py")


def test_unknown_task_has_no_suite():
    assert regrade.suite_for("sf-escaping-breaks-symptom-match") is None


def test_every_suite_file_has_an_expected_probe_count():
    # probe() looks up SUITE_PROBE_COUNTS by suite filename -- a suite added
    # to SUITES without a matching entry here would silently skip the guard.
    for fname in regrade.SUITES.values():
        assert fname in regrade.SUITE_PROBE_COUNTS, fname
    assert regrade.SUITE_PROBE_COUNTS["probe_response_text.py"] == 9
    assert regrade.SUITE_PROBE_COUNTS["probe_fingerprint_preexisting.py"] == 11


def test_replay_removes_the_worktree_it_created_when_apply_fails():
    # git worktree add succeeds, git apply fails: replay must not leak the
    # worktree it just created. Drive it without real git by faking
    # subprocess.run, and assert removal targets the EXACT path replay made.
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["git", "worktree", "add"]:
            return None
        if cmd[:2] == ["git", "apply"]:
            raise regrade.subprocess.CalledProcessError(1, cmd)
        if cmd[:3] == ["git", "worktree", "remove"]:
            return None
        raise AssertionError("unexpected subprocess call: %r" % (cmd,))

    orig_run = regrade.subprocess.run
    regrade.subprocess.run = fake_run
    try:
        entry = {"clone": "clone-1", "base_commit": "deadbeef", "diff": "x.diff"}
        raised = False
        try:
            regrade.replay(entry, "/tmp/regrade-test-work")
        except regrade.subprocess.CalledProcessError:
            raised = True
        assert raised, "replay must propagate the apply failure, not swallow it"
    finally:
        regrade.subprocess.run = orig_run

    expected_path = str(pathlib.Path("/tmp/regrade-test-work") / "clone-1")
    remove_calls = [c for c in calls if c[:3] == ["git", "worktree", "remove"]]
    assert len(remove_calls) == 1, (
        "expected exactly one worktree remove call, got %r" % (remove_calls,))
    assert expected_path in remove_calls[0], (
        "worktree remove must target the exact path replay created: %r" % (remove_calls[0],))


def test_per_entry_exception_other_than_subprocess_or_os_error_does_not_abort_batch():
    # A malformed manifest entry (KeyError, say) must not skip every entry
    # after it -- one bad artifact cannot be allowed to lose the whole batch.
    entries = [
        {"task": "sf-author-response-text", "clone": "clone-bad",
         "base_commit": "x", "diff": "x.diff"},
        {"task": "sf-author-response-text", "clone": "clone-2",
         "base_commit": "x", "diff": "x.diff"},
        {"task": "sf-author-response-text", "clone": "clone-3",
         "base_commit": "x", "diff": "x.diff"},
    ]
    processed = []

    def fake_replay(entry, workdir):
        if entry["clone"] == "clone-bad":
            raise KeyError("malformed manifest entry")
        return pathlib.Path(workdir) / entry["clone"]

    def fake_probe(entry, clone):
        processed.append(entry["clone"])
        return regrade.summarize({"probe": True})

    with tempfile.TemporaryDirectory() as tmp:
        authored = pathlib.Path(tmp) / "authored"
        authored.mkdir()
        (authored / "manifest.json").write_text(json.dumps(entries), encoding="utf-8")
        out_path = pathlib.Path(tmp) / "graded.jsonl"

        # main()'s finally block runs a REAL `git worktree prune` unless this
        # is faked too -- against this checkout, which holds live worktrees
        # for other work. A test suite must never touch real repo state.
        def fake_subprocess_run(cmd, **kwargs):
            return None

        orig_authored, orig_out = regrade.AUTHORED, regrade.OUT
        orig_replay, orig_probe = regrade.replay, regrade.probe
        orig_subprocess_run = regrade.subprocess.run
        regrade.AUTHORED, regrade.OUT = authored, out_path
        regrade.replay, regrade.probe = fake_replay, fake_probe
        regrade.subprocess.run = fake_subprocess_run
        try:
            regrade.main([])
        finally:
            regrade.AUTHORED, regrade.OUT = orig_authored, orig_out
            regrade.replay, regrade.probe = orig_replay, orig_probe
            regrade.subprocess.run = orig_subprocess_run

        assert processed == ["clone-2", "clone-3"], (
            "a non-subprocess exception on one entry must not abort the "
            "rest of the batch: %r" % (processed,))
        rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
        assert [r["clone"] for r in rows] == ["clone-2", "clone-3"]


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
