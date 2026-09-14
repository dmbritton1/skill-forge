"""Tests for bench/e13_outcome_read.py. Run: python3 tests/test_bench_e13_outcome_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_outcome_read as orr

TASK, NAME = "sf-author-verdict-from", "quote-rewrap"
DRAFT_PATH = "bench/distilled/C/learn-nogate/1/SKILL.md"
OLD, NEW = "archive:" + "0" * 40, "archive:" + "9" * 40


def row(commit, resolved=False, injected=None, ok=True, tail=None, skill_path=None,
        extra_skills=None):
    if injected is None:
        injected = commit == NEW
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "env": {"plugin_commit": commit},
            "skill_path": "~/x/wt/" + (skill_path or DRAFT_PATH),
            "extra_skills": ["s%d" % i for i in range(7)] if extra_skills is None else extra_skills,
            "injections": [{"skill": NAME}] if injected else [{"skill": "a-seven-skill"}]}


def arm(commit, resolved):
    return [row(commit, resolved=i < resolved) for i in range(6)]


def some_rows(commit, n, resolved=0, **kw):
    return [row(commit, resolved=i < resolved, **kw) for i in range(n)]


def outcome(rows, task=TASK, name=NAME, draft_path=DRAFT_PATH, old=OLD, new=NEW):
    return orr.read_outcome(rows, task, name, draft_path, old, new)


def test_fisher_matches_known_values():
    assert abs(orr.fisher_two_sided(6, 0, 0, 6) - 2 / 924) < 1e-12
    assert abs(orr.fisher_two_sided(3, 3, 3, 3) - 1.0) < 1e-12


def test_three_more_resolved_improves():
    res = outcome(arm(OLD, 1) + arm(NEW, 4))
    assert res["batch"] == "complete" and res["diff"] == 3 and res["verdict"] == "improves"


def test_the_pre_registered_bands():
    for old, new, verdict in ((2, 3, "no large effect"), (3, 2, "no large effect"),
                              (1, 3, "ambiguous"), (3, 1, "ambiguous"),
                              (4, 1, "worse (not pre-registered)"),
                              (6, 2, "worse (not pre-registered)")):
        assert outcome(arm(OLD, old) + arm(NEW, new))["verdict"] == verdict, (old, new, verdict)


def test_a_row_that_contradicts_qualification_is_void_and_two_void_the_arm():
    rows = arm(OLD, 0) + arm(NEW, 6) + [row(OLD, resolved=True, injected=True)]
    res = outcome(rows)
    assert res["arms"]["old"]["mismatched"] == 1 and res["arms"]["old"]["valid"] == 6
    rows.append(row(OLD, injected=True))
    res = outcome(rows)
    assert res["arms"]["old"]["status"] == "void" and res["batch"] == "void"
    assert res["verdict"] is None


def test_a_session_limit_postpones():
    rows = arm(OLD, 0) + [row(NEW, ok=False, tail="You've hit your session limit")]
    assert outcome(rows)["batch"] == "postponed"


def test_an_unfinished_arm_is_incomplete():
    res = outcome(arm(OLD, 0) + arm(NEW, 6)[:4])
    assert res["batch"] == "incomplete" and res["verdict"] is None


def test_a_wrong_draft_path_row_is_not_counted():
    """A hand re-run with the wrong --skill-from must not fill out the arm."""
    other_draft = "bench/distilled/C/learn-nogate/2/SKILL.md"
    rows = arm(OLD, 0) + some_rows(NEW, 5, resolved=5) + [
        row(NEW, resolved=True, skill_path=other_draft)]
    res = outcome(rows)
    assert res["arms"]["new"]["valid"] == 5
    assert res["batch"] == "incomplete"


def test_a_wrong_extra_skill_count_row_is_not_counted():
    """A hand re-run missing a --plus-skill must not fill out the arm either."""
    rows = arm(OLD, 0) + some_rows(NEW, 5, resolved=5) + [
        row(NEW, resolved=True, extra_skills=["only-one"])]
    res = outcome(rows)
    assert res["arms"]["new"]["valid"] == 5
    assert res["batch"] == "incomplete"


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
