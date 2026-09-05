"""Tests for the /stats health report. Run: python3 tests/test_stats.py"""
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
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


def _antiskill(home, name, minutes):
    d = home / ".claude" / "skillforge" / "antiskills" / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text("---\nname: %s\nkind: antiskill\n---\n\n## Trap\nx\n\n"
                 "## Cost of rediscovery\n~%d min (observed in source"
                 " session)\n" % (name, minutes))
    return p


def test_rediscovery_parses_the_stated_cost():
    def check(home):
        p = _antiskill(home, "trap-a", 45)
        rows = [{"name": "trap-a", "kind": "antiskill", "path": str(p)}]
        total, n = stats.rediscovery_minutes(rows)
        assert n == 1, (total, n)
        assert total >= 0, (total, n)
    in_sandbox(check)


def test_rediscovery_ignores_skills_without_the_heading():
    def check(home):
        p = _skill(home, "plain")
        rows = [{"name": "plain", "kind": "antiskill", "path": str(p)}]
        assert stats.rediscovery_minutes(rows) == (0, 0)
    in_sandbox(check)


def test_rediscovery_ignores_an_unreadable_path():
    rows = [{"name": "gone", "kind": "antiskill", "path": "/nope/SKILL.md"}]
    assert stats.rediscovery_minutes(rows) == (0, 0)


def test_unmeasured_section_names_all_three_gaps_and_what_they_need():
    text = "\n".join(stats.section_unmeasured()).lower()
    assert "churn" in text, text
    assert "model-obvious" in text, text
    assert "holdout" in text, text
    assert "prompt" in text, text
    assert "turn" in text, text


def test_report_runs_on_an_empty_install_without_crashing():
    """No index, no store, no ledger -- the first-run case."""
    def check(home):
        text = stats.report()
        assert "LIBRARY" in text, text
        assert "NOT MEASURED" in text, text
        assert "%" not in text.split("CONTEXT COST")[0], text
    in_sandbox(check)


def test_no_percentage_anywhere_in_a_small_sample_report():
    """The small-n rule as a property of the WHOLE render, not one line.

    Testing rate() alone would not catch a section that formats its own
    percentage and bypasses the helper -- which is exactly how a rule
    with one carve-out erodes. Seeded well under MIN_RATIO_N.
    """
    def check(home):
        for _ in range(4):
            ledger.log_event("injection", "a", tier="warm", session="s1")
            ledger.log_event("detection", "a", detection="verification",
                             session="s1")
        assert "%" not in stats.report(), stats.report()
    in_sandbox(check)


def test_a_percentage_appears_once_the_sample_clears_the_floor():
    """The load-bearing pair to the small-sample test above.

    Proving "no %" below the floor is only half the rule; nothing else
    proves a % ever appears once the sample is big enough. A report whose
    denominators were clamped (e.g. wrapped in `min(x, 9)`) would still
    pass every "small sample" test and never print a rate at any volume
    -- this is the test that would catch that.

    Also seeds a mixed outcome set (success, failure, and no outcome at
    all) in the same ledger and checks the report surfaces all three
    distinctly: a NULL outcome must show as its own `unknown=N`, never
    folded into the success or failure count.
    """
    def check(home):
        for i in range(12):
            ledger.log_event("injection", "a", tier="warm", session="s%d" % i)
        for i in range(6):
            ledger.log_event("detection", "a", detection="verification",
                             outcome="success", session="s%d" % i,
                             project="/repo/%d/.git" % i)
        for i in range(6, 9):
            ledger.log_event("detection", "a", detection="verification",
                             outcome="failure", session="s%d" % i,
                             project="/repo/%d/.git" % i)
        for i in range(9, 12):
            ledger.log_event("detection", "a", detection="verification",
                             session="s%d" % i)
        text = stats.report()
        assert "%" in text, text
        oc_lines = [l for l in text.splitlines() if "success=" in l]
        assert oc_lines, text
        assert "success=6" in oc_lines[0], oc_lines[0]
        assert "failure=3" in oc_lines[0], oc_lines[0]
        assert "unknown=3" in oc_lines[0], oc_lines[0]
    in_sandbox(check)


def test_main_exits_zero_and_prints_the_report():
    def check(home):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = stats.main([])
        assert rc == 0, rc
        assert "LIBRARY" in out.getvalue(), out.getvalue()
    in_sandbox(check)


def test_decisions_section_says_so_when_nothing_was_decided():
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            text = "\n".join(stats.section_decisions())
            assert "DECISIONS" in text, text
            assert "none recorded" in text, text
        finally:
            os.environ["HOME"] = old


def test_decisions_section_splits_human_from_system():
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            ledger.log_decision("human", "approved", "a")
            ledger.log_decision("human", "edited", "b")
            ledger.log_decision("system", "rejected", "c")
            text = "\n".join(stats.section_decisions())
            assert "1 approved" in text and "1 edited" in text, text
            assert "1 rejected" in text, text
            # The two axes must not be summed into one meaningless total:
            # a human judgement and a write-path refusal are different acts.
            assert "reviewer" in text.lower(), text
            assert "write path" in text.lower(), text
        finally:
            os.environ["HOME"] = old


def test_decisions_section_is_in_the_report():
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            ledger.log_decision("system", "secret_blocked", "leaky")
            assert "DECISIONS" in stats.report()
        finally:
            os.environ["HOME"] = old


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
