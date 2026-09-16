"""Tests for bench/e16_screen_read.py. Run: python3 tests/test_bench_e16_screen_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e16_screen_read as sr

REF = sr.REFERENCE
F, G = sr.CANDIDATES
ENV = {"cli": "1.0.0", "plugin_commit": "archive:abc1234"}


def row(task, resolved=False, ok=True, tail=None, failed=(), env=ENV, audit="clean"):
    graded = {sr.TRAP_TEST[task]: not failed} if task in sr.TRAP_TEST else {}
    for name in failed:
        graded[name] = False
    return {"task": task, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "per_test": graded, "env": env, "model": "claude-opus-5",
            "sandbox": True, "audit": {"verdict": audit}}


def ref_rows(resolved=0):
    return [row(REF, resolved=i < resolved) for i in range(sr.N_REFERENCE)]


def cand_rows(task, resolved=0, n=sr.N_CANDIDATE, wider=0):
    out = []
    for i in range(n):
        fail = [sr.TRAP_TEST[task]] + (["test_something_else"] if i < wider else [])
        out.append(row(task, resolved=i < resolved,
                       failed=() if i < resolved else fail))
    return out


def test_zero_of_six_on_the_trap_admits_and_one_resolved_rejects():
    res = sr.read_screen(ref_rows() + cand_rows(F) + cand_rows(G, resolved=1), expected=(F, G))
    assert res["screen"] == "complete", res
    assert res["cells"][F]["verdict"] == "admitted", res["cells"][F]
    assert res["cells"][F]["trap"] == 6
    assert res["cells"][G]["verdict"] == "rejected", res["cells"][G]


def test_a_zero_floor_the_trap_did_not_produce_is_not_an_admission():
    """Candidate F grades 64 tests: a session that never implemented the contract
    also reads 0/6, and that floor says nothing about the trap (spec 3.3)."""
    res = sr.read_screen(ref_rows() + cand_rows(F, wider=4), expected=(F,))
    cell = res["cells"][F]
    assert cell["resolved"] == 0 and cell["trap"] == 2 and cell["wider"] == 4, cell
    assert cell["verdict"] == "floor not attributable", cell


def test_a_bare_majority_of_trap_rows_admits():
    res = sr.read_screen(ref_rows() + cand_rows(F, wider=2), expected=(F,))
    assert res["cells"][F]["verdict"] == "admitted", res["cells"][F]


def test_a_resolved_reference_voids_the_screen_and_hides_candidates():
    res = sr.read_screen(ref_rows(resolved=1) + cand_rows(F), expected=(F,))
    assert res["screen"] == "void"
    assert F not in res["cells"], "candidates must not be read once the reference moved"


def test_no_candidate_carries_a_verdict_until_the_reference_is_complete():
    res = sr.read_screen(ref_rows()[:2] + cand_rows(F), expected=(F,))
    assert res["screen"] == "incomplete"
    assert "verdict" not in res["cells"][F], "a verdict before the reference is established"


def test_the_session_limit_pauses_rather_than_postponing():
    rows = ref_rows() + cand_rows(F, n=5) + [
        row(F, ok=False, tail="You've hit your session limit · resets 5:30pm")]
    res = sr.read_screen(rows, expected=(F,))
    assert res["screen"] == "paused" and res["reason"] == "session limit", res
    assert res["cells"][F]["valid"] == 5, "the failed session must not count"


def test_a_failed_session_that_is_not_the_limit_also_pauses():
    rows = ref_rows() + cand_rows(F, n=5) + [row(F, ok=False, tail="boom")]
    res = sr.read_screen(rows, expected=(F,))
    assert res["screen"] == "paused" and res["reason"] == "failed session", res


def test_a_failed_session_does_not_take_its_slot_in_the_order():
    rows = ref_rows() + [row(F, ok=False, tail="boom")]
    res = sr.read_screen(rows, expected=(F, G))
    assert sr.next_run(rows, res, (F, G)) == F, "the failed run is re-run in place"


def test_the_order_is_three_interleaved_rounds_opening_with_the_reference():
    plan = sr.order((F, G))
    assert len(plan) == sr.N_REFERENCE + 2 * sr.N_CANDIDATE
    assert plan.count(REF) == sr.N_REFERENCE
    assert plan.count(F) == plan.count(G) == sr.N_CANDIDATE
    assert plan[0] == REF and plan[5] == REF, plan


def test_mixed_rows_are_unreadable():
    rows = ref_rows() + cand_rows(F)
    rows[-1]["env"] = {"cli": "9.9.9", "plugin_commit": "archive:abc1234"}
    res = sr.read_screen(rows, expected=(F,))
    assert res["screen"] == "mixed", res


def test_a_row_the_audit_rejects_does_not_count():
    rows = ref_rows() + cand_rows(F, n=5) + [row(F, audit="leak")]
    res = sr.read_screen(rows, expected=(F,))
    assert res["cells"][F]["valid"] == 5 and res["cells"][F]["invalid"] == 1, res["cells"][F]


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
