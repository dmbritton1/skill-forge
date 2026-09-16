"""Tests for bench/e17_q5.py's reading. Run: python3 tests/test_bench_e17_q5.py

Never invokes a model: every case feeds read_results() fixed verdicts.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e17_q5 as q5


def records(v_calls, b_calls):
    """v_calls: 6 lists of verdicts; b_calls: 3."""
    out = {}
    for i, calls in enumerate(v_calls, 1):
        out["distilled/C/learn-e15-nogate/%d/SKILL.md" % i] = {
            "group": "V", "bytes": 3400, "calls": list(calls)}
    for i, calls in enumerate(b_calls, 1):
        out["distilled/C/learn-nogate/%d/SKILL.md" % i] = {
            "group": "B", "bytes": 2800, "calls": list(calls)}
    return out


P3 = ["pass"] * 3
F3 = ["fail"] * 3


def test_a_clean_split_reads_as_the_gate_predicting():
    res = q5.read_results(records([P3] * 6, [F3] * 3))
    m = res["measures"]
    assert m["V"] == [18, 18] and m["B"] == [0, 9], m
    assert m["delta"] == 1.0 and m["reading"] == "the gate predicts", m
    assert res["stability"] == "stable" and res["unanimous"] == 9


def test_passing_everything_reads_as_no_prediction():
    res = q5.read_results(records([P3] * 6, [P3] * 3))
    assert res["measures"]["delta"] == 0.0
    assert res["measures"]["reading"] == "the gate does not predict"


def test_failing_everything_also_reads_as_no_prediction():
    """The degenerate result the spec predicts in section 4 is still readable."""
    res = q5.read_results(records([F3] * 6, [F3] * 3))
    assert res["measures"]["reading"] == "the gate does not predict", res["measures"]


def test_the_backwards_direction_has_its_own_band():
    res = q5.read_results(records([F3] * 6, [P3] * 3))
    assert res["measures"]["delta"] == -1.0
    assert res["measures"]["reading"] == "the gate predicts backwards"


def test_a_high_delta_with_a_low_v_rate_is_ambiguous_not_a_prediction():
    """delta clears +0.40 but V is under half, so section 3.1 withholds the call."""
    v = [["pass", "fail", "fail"]] * 6   # V = 6/18
    res = q5.read_results(records(v, [F3] * 3))
    assert res["measures"]["delta"] == 0.33, res["measures"]
    assert res["measures"]["reading"] == "ambiguous"


def test_flapping_verdicts_are_unstable_even_when_delta_is_clean():
    v = [["pass", "pass", "fail"]] * 6
    res = q5.read_results(records(v, [F3] * 3))
    assert res["unanimous"] == 3, res["unanimous"]
    assert res["stability"] == "unstable"
    assert res["measures"] is not None, "instability must not void delta"


def test_one_inconclusive_keeps_the_draft_and_shrinks_its_denominator():
    v = [["pass", "pass", "inconclusive"]] + [P3] * 5
    res = q5.read_results(records(v, [F3] * 3))
    d = res["drafts"]["distilled/C/learn-e15-nogate/1/SKILL.md"]
    assert d["live"] and d["graded"] == 2
    assert res["measures"]["V"] == [17, 17], res["measures"]


def test_two_inconclusives_drop_the_draft():
    v = [["inconclusive", "inconclusive", "pass"]] + [P3] * 5
    res = q5.read_results(records(v, [F3] * 3))
    assert not res["drafts"]["distilled/C/learn-e15-nogate/1/SKILL.md"]["live"]
    assert res["live"]["V"] == 5
    assert res["measures"]["V"] == [15, 15], res["measures"]


def test_a_group_below_three_live_drafts_is_not_read():
    bad = ["inconclusive"] * 3
    res = q5.read_results(records([P3] * 6, [bad, bad, F3]))
    assert res["measures"] is None
    assert "fewer than 3 live" in res["reason"], res["reason"]


def test_a_partial_run_is_not_read_and_stability_is_not_claimed():
    rec = records([P3] * 6, [F3] * 3)
    rec.pop("distilled/C/learn-nogate/3/SKILL.md")
    res = q5.read_results(rec)
    assert res["measures"] is None
    assert res["stability"] == "not measured", res["stability"]


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
