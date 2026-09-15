"""Tests for bench/e14_read.py. Run: python3 tests/test_bench_e14_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e14_read as er

TASK = er.TASK


def ctl(resolved=False, ok=True, tail=None, audit="clean"):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "skill_path": None, "injections": [],
            "sandbox": True, "audit": {"verdict": audit}}


def trt(cell, resolved=False, delivered=True, ok=True, audit="clean"):
    name = er.draft_name(cell)
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None,
            "skill_path": "~/x/wt/bench/drafts/E14/%s.md" % name,
            "injections": [{"skill": name if delivered else "other"}],
            "sandbox": True, "audit": {"verdict": audit}}


def cells(**resolved):
    """Six valid delivered rows per cell; `resolved` gives each cell's count."""
    rows = []
    for c in er.CELLS:
        rows += [trt(c, resolved=i < resolved.get(c, 0)) for i in range(6)]
    return rows


def test_cell_of_reads_the_draft_path():
    assert er.cell_of(trt("aw")) == "aw"
    assert er.cell_of(ctl()) is None
    assert er.cell_of({"skill_path": "~/x/bench/drafts/E14/other.md"}) is None


def test_bands():
    for diff, reading in ((4, "factor matters"), (7, "factor matters"), (3, "ambiguous"),
                          (2, "ambiguous"), (1, "no large effect"), (0, "no large effect"),
                          (-1, "no large effect"), (-2, "ambiguous"), (-3, "ambiguous"),
                          (-4, "opposite effect (not pre-registered)")):
        assert er.band(diff) == reading, (diff, reading)


def test_a_complete_batch_computes_both_effects():
    res = er.read_batch([ctl()] * 3 + cells(sf=0, sw=4, af=5, aw=6))
    assert res["batch"] == "complete"
    assert res["effects"]["trigger"]["diff"] == (4 + 6) - (0 + 5)
    assert res["effects"]["kind"]["diff"] == (5 + 6) - (0 + 4)
    assert res["effects"]["trigger"]["reading"] == "factor matters"
    assert 0.0 <= res["effects"]["kind"]["p"] <= 1.0
    assert res["baseline"] == {"sf": 0, "af": 5, "sf_as_predicted": True, "af_as_predicted": True}


def test_baseline_flags_a_moved_baseline():
    res = er.read_batch([ctl()] * 3 + cells(sf=2, af=4))
    assert res["baseline"]["sf_as_predicted"] is False
    assert res["baseline"]["af_as_predicted"] is False


def test_a_resolved_control_voids_the_batch():
    res = er.read_batch([ctl(resolved=True), ctl(), ctl()] + cells())
    assert res["batch"] == "void" and res["effects"] is None


def test_a_session_limit_postpones_the_batch():
    res = er.read_batch([ctl()] * 3 + cells() + [trt("sf", ok=False)] +
                        [dict(trt("sw", ok=False), session_tail="You've hit your session limit")])
    assert res["batch"] == "postponed" and res["cells"] == {}


def test_void_audit_failed_session_and_undelivered_rows_do_not_count():
    rows = [ctl()] * 3 + cells() + [trt("sf", resolved=True, audit="leak"),
                                    trt("sf", resolved=True, ok=False),
                                    trt("sf", resolved=True, delivered=False)]
    cell = er.read_batch(rows)["cells"]["sf"]
    assert cell["valid"] == 6 and cell["resolved"] == 0
    assert cell["invalid"] == 2 and cell["undelivered"] == 1 and cell["status"] == "complete"


def test_two_undelivered_rows_void_the_cell_and_no_effect_is_computed():
    rows = [ctl()] * 3 + cells() + [trt("aw", delivered=False)] * 2
    res = er.read_batch(rows)
    assert res["cells"]["aw"]["status"] == "void"
    assert res["batch"] == "complete" and res["effects"] is None
    assert "aw" in res["reason"]


def test_a_cell_counts_only_its_first_six_valid_runs():
    rows = [ctl()] * 3 + cells(sw=0) + [trt("sw", resolved=True)]
    assert er.read_batch(rows)["cells"]["sw"]["resolved"] == 0


def test_a_missing_run_leaves_the_batch_incomplete_and_todo_names_it():
    rows = [ctl()] * 2 + [r for r in cells() if not (er.cell_of(r) == "af")] + [trt("af")] * 5
    res = er.read_batch(rows)
    assert res["batch"] == "incomplete" and res["effects"] is None
    assert er.todo(res) == ["control", "af"]


def test_todo_is_empty_for_complete_void_and_postponed_batches():
    assert er.todo(er.read_batch([ctl()] * 3 + cells())) == []
    assert er.todo(er.read_batch([ctl(resolved=True)] + cells())) == []
    assert er.todo(er.read_batch([dict(ctl(ok=False), session_tail="session limit")])) == []


def test_rows_for_other_tasks_are_ignored():
    rows = [ctl()] * 3 + cells() + [dict(trt("sf", resolved=True), task="other")] * 3
    assert er.read_batch(rows)["cells"]["sf"]["resolved"] == 0


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
