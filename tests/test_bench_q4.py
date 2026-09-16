"""Tests for bench/q4_token_cost.py. Run: python3 tests/test_bench_q4.py

Never invokes a model and never reads the live results file: every case feeds
fixed rows. The skill files it names are real, because the reader prices the
bytes on disk.
"""
import pathlib
import sys
from fractions import Fraction

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "bench"))
import q4_token_cost as q4

DRAFT = "bench/distilled/C/learn-e15-nogate/1/SKILL.md"
NAME = "whitespace-insensitive-evidence-quote-check"


def row(task, arm="control", resolved=False, ok=True, inj=None, path=None):
    return {"task": task, "arm": arm, "resolved": resolved, "session_ok": ok,
            "injections": inj, "skill_path": path,
            "sandbox": True, "audit": {"verdict": "clean"}}


def treatment(task, resolved, n, skills=1):
    inj = [{"skill": NAME}] + [{"skill": "other"}] * (skills - 1)
    return [row(task, "treatment", resolved=i < resolved, inj=inj,
                path="/somewhere/else/" + DRAFT) for i in range(n)]


def floor_rows(task, n=6, resolved=0):
    return [row(task, resolved=i < resolved) for i in range(n)]


def test_a_zero_floor_task_is_priced_and_the_cost_is_the_whole_file():
    rows = floor_rows("t") + treatment("t", 3, 3)
    grid = q4.cells(rows, q4.controls(rows))
    cell = grid[("t", DRAFT)]
    assert cell == {"resolved": 3, "n": 3, "cost": len(
        (REPO / DRAFT).read_text(encoding="utf-8")) // 4}, cell
    assert q4.price(cell, Fraction(0)) == cell["cost"], "3/3 costs one file per resolution"


def test_half_a_lift_doubles_the_price():
    rows = floor_rows("t") + treatment("t", 2, 4)
    cell = q4.cells(rows, q4.controls(rows))[("t", DRAFT)]
    assert q4.price(cell, Fraction(0)) == cell["cost"] * 2


def test_a_draft_that_never_resolves_has_no_price():
    rows = floor_rows("t") + treatment("t", 0, 5)
    cell = q4.cells(rows, q4.controls(rows))[("t", DRAFT)]
    assert q4.price(cell, Fraction(0)) is None, "a bill is not a price"


def test_a_task_whose_control_can_not_rise_is_not_read():
    rows = floor_rows("ceil", resolved=6) + treatment("ceil", 6, 6)
    assert q4.cells(rows, q4.controls(rows)) == {}


def test_a_control_floor_below_the_minimum_n_is_not_read():
    rows = floor_rows("thin", n=q4.MIN_CONTROL_N - 1) + treatment("thin", 3, 3)
    assert q4.cells(rows, q4.controls(rows)) == {}


def test_a_run_that_injected_two_skills_is_unattributable():
    rows = floor_rows("t") + treatment("t", 3, 3, skills=2)
    assert q4.cells(rows, q4.controls(rows)) == {}, "cost cannot be split between two skills"


def test_a_row_the_audit_rejects_does_not_pay_or_count():
    rows = floor_rows("t") + treatment("t", 3, 3)
    rows[-1]["audit"] = {"verdict": "leak"}
    assert q4.cells(rows, q4.controls(rows))[("t", DRAFT)]["n"] == 2


def test_a_row_naming_a_skill_the_file_does_not_is_dropped():
    rows = floor_rows("t") + treatment("t", 3, 3)
    for r in rows[-3:]:
        r["injections"] = [{"skill": "a-different-skill"}]
    assert q4.cells(rows, q4.controls(rows)) == {}


def test_a_draft_this_repo_does_not_hold_is_dropped():
    rows = floor_rows("t") + treatment("t", 3, 3)
    for r in rows[-3:]:
        r["skill_path"] = "/x/bench/distilled/C/learn-e15-nogate/99/SKILL.md"
    assert q4.cells(rows, q4.controls(rows)) == {}


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
