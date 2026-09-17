"""Tests for bench/e13_qualify.py. Run from the repo root: python3 tests/test_bench_e13_qualify.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e13_qualify as q


def _draw(archive, segment, draw, outcome="saved", name=None, draft=True, tainted=None):
    d = archive / "C" / segment / str(draw)
    d.mkdir(parents=True)
    meta = {"outcome": outcome, "skill_name": name}
    if tainted is not None:
        meta["tainted"] = tainted
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
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


def test_plugin_drift_flags_a_ref_that_differs_under_scripts_or_hooks():
    """06885c0 differs from HEAD in scripts/retrieve.py (the tokenizer fix).

    NEW_REF no longer matches HEAD either, as of 2026-09-16: the E17 fix to
    scripts/validate.py moved scripts/ past 9cbb472. e13_qualify.main() now
    refuses to run with its FATAL, which is the guard WORKING -- qualification
    would no longer match the plugin under test. A future trap-2 qualification
    must re-pin NEW_REF to its own snapshot rather than assume HEAD.
    """
    assert q.plugin_drift("06885c0") is True
    assert q.plugin_drift(q.NEW_REF) is True
    # Both directions, or a plugin_drift that always returned True would pass.
    # HEAD is the only ref the tree can equal, and only while it is clean under
    # those paths -- true in CI and a fresh checkout, false mid-edit.
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "scripts", "hooks"],
                      cwd=str(q.ROOT)).returncode == 0:
        assert q.plugin_drift("HEAD") is False


def test_counted_drafts_flag_a_tainted_draft():
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp)
        _draw(a, "learn-nogate", 1, name="clean")
        _draw(a, "learn-nogate", 2, name="read-the-fix", tainted=True)
        got = [(d["name"], d["tainted"]) for d in q.counted_drafts(a, "C")]
        assert got == [("clean", False), ("read-the-fix", True)], got


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
