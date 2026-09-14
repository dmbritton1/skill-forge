"""Tests for bench/e13_qualify.py. Run from the repo root: python3 tests/test_bench_e13_qualify.py"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e13_qualify as q


def _draw(archive, segment, draw, outcome="saved", name=None, draft=True):
    d = archive / "C" / segment / str(draw)
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"outcome": outcome, "skill_name": name}), encoding="utf-8")
    if draft:
        (d / "SKILL.md").write_text("---\nname: %s\n---\n" % name, encoding="utf-8")


def test_counted_drafts_follow_the_section_6_1_order_and_rules():
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp)
        _draw(a, "learn-failure-nogate", 1, name="lf1")
        _draw(a, "learn-nogate", 10, name="l10")
        _draw(a, "learn-nogate", 2, name="l2")
        _draw(a, "learn-nogate", 3, outcome="repair_unresolved", name="unresolved")
        _draw(a, "learn-nogate", 4, outcome="aborted", draft=False)
        _draw(a, "learn", 1, name="gated")
        got = [(d["segment"], d["draw"], d["name"]) for d in q.counted_drafts(a, "C")]
        assert got == [("learn-nogate", 2, "l2"), ("learn-nogate", 10, "l10"),
                       ("learn-failure-nogate", 1, "lf1")], got


def test_a_draft_qualifies_only_if_the_new_hook_alone_delivers_it():
    assert q.qualifies("x", old=["other"], new=["other", "x"]) is True
    assert q.qualifies("x", old=["x"], new=["x"]) is False
    assert q.qualifies("x", old=[], new=[]) is False
    assert q.qualifies("x", old=["x"], new=[]) is False


def test_first_qualifying_takes_the_earliest_in_order():
    rows = [{"path": "a", "qualifies": False}, {"path": "b", "qualifies": True},
            {"path": "c", "qualifies": True}]
    assert q.first_qualifying(rows)["path"] == "b"
    assert q.first_qualifying(rows[:1]) is None


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
