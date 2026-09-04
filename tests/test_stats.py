"""Tests for the /stats health report. Run: python3 tests/test_stats.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import stats


def test_no_percentage_below_the_threshold():
    """The rule the whole command turns on.

    A count is true at any n. A percentage asserts a stable underlying
    rate, and spec 1.1 holds that 5-15 lifetime events cannot support one.
    """
    out = stats.rate(3, 4)
    assert "%" not in out, out
    assert "3 of 4" in out, out


def test_a_percentage_appears_at_the_threshold():
    out = stats.rate(5, 10)
    assert "%" in out, out
    assert "50%" in out, out


def test_the_threshold_boundary_is_exact():
    """Nine is noise, ten is a rate. An off-by-one here silently changes
    which numbers the user is invited to believe."""
    assert "%" not in stats.rate(9, 9), stats.rate(9, 9)
    assert "%" in stats.rate(9, 10), stats.rate(9, 10)


def test_zero_sample_says_so_without_dividing():
    out = stats.rate(0, 0, unit="injections")
    assert "%" not in out, out
    assert "injections" in out, out


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
