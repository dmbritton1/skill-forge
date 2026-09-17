"""Tests for bench/hot_check.py. Run: python3 tests/test_bench_hot_check.py

No model, no archived files: every case builds its own ranked pool, so the
logic is tested without depending on what happens to sit in bench/distilled/.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "scripts"))
import hot_check as hc


def s(name, cost, bucket="working", kind="skill"):
    return {"name": name, "_desc_cost": cost, "bucket": bucket, "kind": kind}


def test_promote_spends_the_budget_in_rank_order():
    ranked = [s("a", 10), s("b", 10), s("c", 10)]
    assert hc.promote(ranked, 25, stop=True) == ["a", "b"]
    assert hc.promote(ranked, 5, stop=True) == []


def test_promote_skips_antiskills_and_ineligible_buckets():
    ranked = [s("anti", 1, kind="antiskill"), s("new", 1, bucket="unproven"), s("ok", 1)]
    assert hc.promote(ranked, 100, stop=True) == ["ok"]


def test_continue_lets_a_cheaper_lower_ranked_skill_jump_the_queue():
    # The signature of skip-and-continue: `big` does not fit, `small` does, so
    # a lower-ranked skill is hot while a higher-ranked one is warm.
    ranked = [s("big", 100), s("small", 5)]
    assert hc.promote(ranked, 50, stop=False) == ["small"]
    assert hc.promote(ranked, 50, stop=True) == [], "break must stop at the first misfit"
    assert hc.inversions(ranked, 50, stop=False) == [("big", "small")]
    assert hc.inversions(ranked, 50, stop=True) == []


def test_continue_is_not_monotone_in_the_budget_and_break_is():
    # At a budget that fits only `small`, the hot set is {small}. Raise it
    # enough for `big` alone and `small` is DEMOTED -- a bigger budget
    # delivering strictly less, which is the invariant violation.
    ranked = [s("big", 100), s("small", 60)]
    assert hc.promote(ranked, 60, stop=False) == ["small"]
    assert hc.promote(ranked, 100, stop=False) == ["big"]
    grid = hc.GRID
    try:
        hc.GRID = range(60, 121, 20)
        shrinks_continue, demoted = hc.sweep(ranked, stop=False)
        shrinks_break, _ = hc.sweep(ranked, stop=True)
    finally:
        hc.GRID = grid
    assert shrinks_continue > 0 and "small" in demoted, (shrinks_continue, demoted)
    assert shrinks_break == 0, shrinks_break


def test_sweep_reports_no_shrink_when_the_set_only_grows():
    ranked = [s("a", 10), s("b", 10)]
    grid = hc.GRID
    try:
        hc.GRID = range(10, 41, 10)
        assert hc.sweep(ranked, stop=True) == (0, [])
    finally:
        hc.GRID = grid


def test_the_two_cost_formulas_are_still_in_agreement():
    """sync.est_tokens duplicates retrieve.injection_cost (handoff 3.3 said
    that formula was consolidated into one definition; sync kept a copy).
    This fails the day they drift, which is the whole risk of a duplicate."""
    import retrieve
    import sync
    for text in ("", "x", "y" * 399, "z" * 400, "w" * 4001):
        assert sync.est_tokens(text) == retrieve.injection_cost(text), repr(text[:8])


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
