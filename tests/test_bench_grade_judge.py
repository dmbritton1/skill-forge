"""Tests for the graded judge. Run: python3 tests/test_bench_grade_judge.py

No model is called here. tests/ is forbidden from invoking a model; this
suite exercises prompt construction and reply parsing only.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import grade_judge


def test_parse_reads_a_well_formed_verdict():
    text = '{"explicit_unknown": true, "bounds_documented": false, "visible_degradation": true}'
    got = grade_judge.parse(text)
    assert got == {"explicit_unknown": True, "bounds_documented": False,
                   "visible_degradation": True}


def test_parse_tolerates_prose_around_the_json():
    text = 'Here is my verdict:\n{"explicit_unknown": false, ' \
           '"bounds_documented": true, "visible_degradation": true}\nDone.'
    assert grade_judge.parse(text)["bounds_documented"] is True


def test_parse_returns_none_on_garbage():
    assert grade_judge.parse("I could not read the file.") is None


def test_parse_returns_none_when_a_criterion_is_missing():
    # A partial verdict scored as a fraction would silently invent a denominator.
    assert grade_judge.parse('{"explicit_unknown": true}') is None


def test_score_of_a_none_verdict_is_not_ok_and_not_zero():
    r = grade_judge.summarize(None)
    assert r["judge_ok"] is False
    assert r["judge_score"] is None


def test_score_is_the_fraction_of_criteria_met():
    r = grade_judge.summarize({"explicit_unknown": True, "bounds_documented": False,
                               "visible_degradation": True})
    assert r["judge_ok"] is True
    assert abs(r["judge_score"] - (2 / 3)) < 1e-9


def test_prompt_contains_the_source_and_every_criterion():
    p = grade_judge.build_prompt("def f(): pass")
    assert "def f(): pass" in p
    for key in grade_judge.CRITERIA:
        assert key in p


def test_summarize_of_a_met_verdict_records_the_judge_model():
    r = grade_judge.summarize({"explicit_unknown": True, "bounds_documented": True,
                               "visible_degradation": True})
    assert r["judge_model"] == grade_judge.JUDGE_MODEL


def test_summarize_of_a_none_verdict_still_records_the_judge_model():
    r = grade_judge.summarize(None)
    assert r["judge_model"] == grade_judge.JUDGE_MODEL


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
