"""Tests for the regrade replay driver. Run: python3 tests/test_bench_regrade.py"""
import json
import pathlib
import sys

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


def test_probe_suite_is_chosen_by_task():
    assert regrade.suite_for("sf-author-response-text").endswith("probe_response_text.py")
    assert regrade.suite_for(
        "sf-author-fingerprint-preexisting").endswith("probe_fingerprint_preexisting.py")


def test_unknown_task_has_no_suite():
    assert regrade.suite_for("sf-escaping-breaks-symptom-match") is None


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
