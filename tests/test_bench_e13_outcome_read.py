"""Tests for bench/e13_outcome_read.py. Run: python3 tests/test_bench_e13_outcome_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_outcome_read as orr

TASK, NAME = "sf-author-verdict-from", "quote-rewrap"
OLD, NEW = "archive:" + "0" * 40, "archive:" + "9" * 40


def row(commit, resolved=False, injected=None, ok=True, tail=None):
    if injected is None:
        injected = commit == NEW
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "env": {"plugin_commit": commit},
            "injections": [{"skill": NAME}] if injected else [{"skill": "a-seven-skill"}]}


def arm(commit, resolved):
    return [row(commit, resolved=i < resolved) for i in range(6)]


def test_fisher_matches_known_values():
    assert abs(orr.fisher_two_sided(6, 0, 0, 6) - 2 / 924) < 1e-12
    assert abs(orr.fisher_two_sided(3, 3, 3, 3) - 1.0) < 1e-12


def test_three_more_resolved_improves():
    res = orr.read_outcome(arm(OLD, 1) + arm(NEW, 4), TASK, NAME, OLD, NEW)
    assert res["batch"] == "complete" and res["diff"] == 3 and res["verdict"] == "improves"


def test_the_pre_registered_bands():
    for old, new, verdict in ((2, 3, "no large effect"), (3, 2, "no large effect"),
                              (1, 3, "ambiguous"), (4, 1, "worse (not pre-registered)")):
        assert orr.read_outcome(arm(OLD, old) + arm(NEW, new), TASK, NAME, OLD, NEW)["verdict"] == verdict


def test_a_row_that_contradicts_qualification_is_void_and_two_void_the_arm():
    rows = arm(OLD, 0) + arm(NEW, 6) + [row(OLD, resolved=True, injected=True)]
    res = orr.read_outcome(rows, TASK, NAME, OLD, NEW)
    assert res["arms"]["old"]["mismatched"] == 1 and res["arms"]["old"]["valid"] == 6
    rows.append(row(OLD, injected=True))
    res = orr.read_outcome(rows, TASK, NAME, OLD, NEW)
    assert res["arms"]["old"]["status"] == "void" and res["batch"] == "void"
    assert res["verdict"] is None


def test_a_session_limit_postpones():
    rows = arm(OLD, 0) + [row(NEW, ok=False, tail="You've hit your session limit")]
    assert orr.read_outcome(rows, TASK, NAME, OLD, NEW)["batch"] == "postponed"


def test_an_unfinished_arm_is_incomplete():
    res = orr.read_outcome(arm(OLD, 0) + arm(NEW, 6)[:4], TASK, NAME, OLD, NEW)
    assert res["batch"] == "incomplete" and res["verdict"] is None


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
