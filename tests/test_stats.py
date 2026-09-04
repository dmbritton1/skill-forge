"""Tests for the /stats health report. Run: python3 tests/test_stats.py"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import stats
import trust


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


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        os.chdir(tmp)
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.chdir(old_cwd)
            os.environ["HOME"] = old_home


def _skill(home, name, kind="skills", trusted=True):
    """Write a store file, and register it as trusted unless told not to."""
    d = home / ".claude" / "skillforge" / kind / name
    d.mkdir(parents=True, exist_ok=True)
    text = "---\nname: %s\nkind: skill\n---\n\n## Procedure\n1. do it\n" % name
    (d / "SKILL.md").write_text(text)
    if trusted:
        trust.record(name, text, "self")
    return d / "SKILL.md"


def test_library_section_counts_by_kind_and_bucket():
    def check(home):
        rows = [{"name": "a", "kind": "skill", "scope": "global",
                 "tier": "hot", "bucket": "trusted", "successes": 2,
                 "failures": 0, "path": ""},
                {"name": "b", "kind": "antiskill", "scope": "project",
                 "tier": "warm", "bucket": "unproven", "successes": 0,
                 "failures": 0, "path": ""}]
        text = "\n".join(stats.section_library(rows))
        assert "skills            2" in text, text
        assert "antiskill" in text, text
        assert "trusted" in text, text
    in_sandbox(check)


def test_library_section_survives_an_empty_library():
    def check(home):
        text = "\n".join(stats.section_library([]))
        assert text.strip(), "an empty library must still print a section"
        assert "%" not in text, text
    in_sandbox(check)


def test_quarantined_counts_store_files_the_registry_does_not_vouch_for():
    """An untrusted skill is absent from the index entirely, so the count
    has to come from the store, not the index."""
    def check(home):
        _skill(home, "good", trusted=True)
        _skill(home, "bad", trusted=False)
        assert stats.quarantined() == 1, stats.quarantined()
    in_sandbox(check)


def test_context_section_reports_fill_against_the_budget():
    entries = [{"name": "a", "tier": "hot", "description": "x" * 400},
               {"name": "b", "tier": "warm", "description": "y" * 4000}]
    text = "\n".join(stats.section_context(entries, 1500))
    assert "1500" in text, text
    assert "100" in text, text          # 400 chars // 4 == 100 tokens
    assert "4000" not in text, "warm descriptions are not standing cost"
    assert "%" not in text, "the no-percentage rule holds with no exception"


def test_context_section_handles_a_missing_budget():
    text = "\n".join(stats.section_context([], 0))
    assert text.strip(), text


def test_usage_section_labels_the_ratio_warm_only():
    """Injections are logged for warm tier alone while detections are
    logged for every tier, so a library-wide ratio would draw its two
    halves from different populations. Saying 'warm' is the fix."""
    totals = {"by_type": {"injection": 4, "detection": 2},
              "by_detection": {"marker": 1, "verification": 1},
              "verification_outcomes": {"success": 1, "failure": 0,
                                        "unknown": 0}}
    text = "\n".join(stats.section_usage([], totals)).lower()
    assert "warm" in text, text


def test_usage_section_withholds_the_rate_on_a_small_sample():
    totals = {"by_type": {"injection": 4, "detection": 2},
              "by_detection": {"marker": 1},
              "verification_outcomes": {"success": 0, "failure": 0,
                                        "unknown": 0}}
    text = "\n".join(stats.section_usage([], totals))
    assert "%" not in text, text


def test_outcomes_section_shows_unknown_rather_than_zero_successes():
    """The regression pin for the bug that motivated this command."""
    totals = {"by_type": {"detection": 3}, "by_detection": {"verification": 3},
              "verification_outcomes": {"success": 0, "failure": 0,
                                        "unknown": 3}}
    text = "\n".join(stats.section_outcomes([], totals))
    assert "unknown" in text.lower(), text
    assert "3" in text, text


def test_outcomes_section_reports_survival_without_a_rate_when_small():
    rows = [{"name": "a", "kind": "skill", "bucket": "trusted", "path": ""},
            {"name": "b", "kind": "skill", "bucket": "unproven", "path": ""}]
    totals = {"by_type": {"save": 2}, "by_detection": {},
              "verification_outcomes": {"success": 0, "failure": 0,
                                        "unknown": 0}}
    text = "\n".join(stats.section_outcomes(rows, totals))
    assert "%" not in text, text
    assert "trusted" in text, text


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
