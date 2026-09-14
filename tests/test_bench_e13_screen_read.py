"""Tests for bench/e13_screen_read.py. Run: python3 tests/test_bench_e13_screen_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_screen_read as sr

REF = sr.REFERENCE
C, D, E = sr.CANDIDATES


def row(task, resolved=False, ok=True, tail=None, arm="control"):
    return {"task": task, "arm": arm, "resolved": resolved, "session_ok": ok,
            "session_tail": tail}


def ref_rows(resolved=0):
    return [row(REF, resolved=i < resolved) for i in range(sr.N_REFERENCE)]


def cand_rows(task, resolved=0, n=sr.N_CANDIDATE):
    return [row(task, resolved=i < resolved) for i in range(n)]


def test_zero_of_six_admits_and_one_resolved_rejects():
    res = sr.read_screen(ref_rows() + cand_rows(C) + cand_rows(D, resolved=1), expected=(C, D))
    assert res["screen"] == "complete", res
    assert res["cells"][C]["verdict"] == "admitted"
    assert res["cells"][D]["verdict"] == "rejected"
    assert E not in res["cells"], "a candidate excluded from expected was not screened"


def test_expected_candidate_with_no_rows_is_incomplete_not_dropped():
    res = sr.read_screen(ref_rows() + cand_rows(C) + cand_rows(D, resolved=1))
    assert E in res["cells"], "a candidate with no rows must still be reported when expected"
    cell = res["cells"][E]
    assert cell["valid"] == 0 and cell["needed"] == sr.N_CANDIDATE
    assert cell["verdict"] == "incomplete"
    assert res["screen"] == "incomplete", "a missing expected candidate cannot read as complete"


def test_a_resolved_reference_voids_the_screen_and_hides_candidates():
    res = sr.read_screen(ref_rows(resolved=1) + cand_rows(C))
    assert res["screen"] == "void"
    assert C not in res["cells"], "candidates must not be read once the reference moved"


def test_an_unfinished_reference_reads_no_candidate():
    res = sr.read_screen(ref_rows()[:2] + cand_rows(C))
    assert res["screen"] == "incomplete"
    assert C not in res["cells"]


def test_a_session_limit_postpones_the_whole_screen():
    rows = ref_rows() + cand_rows(C, n=5) + [
        row(C, ok=False, tail="You've hit your session limit · resets 5:30pm")]
    res = sr.read_screen(rows)
    assert res["screen"] == "postponed"
    assert res["cells"] == {}, "a postponed screen is not read at all"


def test_any_other_refusal_leaves_the_cell_incomplete_and_counts_a_rerun():
    rows = ref_rows() + cand_rows(C, n=5) + [row(C, ok=False, tail="some other crash")]
    res = sr.read_screen(rows)
    cell = res["cells"][C]
    assert cell["verdict"] == "incomplete" and cell["rerun"] == 1 and cell["valid"] == 5
    assert res["screen"] == "incomplete"


def test_one_resolved_session_rejects_before_the_cell_is_full():
    res = sr.read_screen(ref_rows() + cand_rows(C, resolved=1, n=2))
    assert res["cells"][C]["verdict"] == "rejected"


def test_treatment_rows_are_not_part_of_the_screen():
    rows = ref_rows() + cand_rows(C) + [row(C, resolved=True, arm="treatment")]
    assert sr.read_screen(rows)["cells"][C]["verdict"] == "admitted"


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
