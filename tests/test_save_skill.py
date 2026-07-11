"""Tests for the enforced save path (spec 4, 6, 11.1). Run: python3 tests/test_save_skill.py"""
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import save_skill

import ledger
import trust

VALID_SKILL = """---
name: test-skill
kind: skill
scope: global
description: >
  A test skill for the save path.
  Use when: testing SkillForge.
  Do NOT use when: doing anything real.
verification.command: "true"
fingerprints:
  - "do_the_thing --alpha"
  - "thing_output=42"
provenance:
  repo: local/skill-forge
  distilled: 2026-07-09
---
## Procedure
1. Do the thing.

## Verification
- `true` exits 0.
"""

VALID_ANTISKILL = """---
name: test-trap
kind: antiskill
scope: global
description: >
  A test trap. Use when: testing.
  Do NOT use when: doing anything real.
---
## Trap
Doing the wrong thing.

## Symptom
It fails.

## Cause
Wrongness.

## Fix
Do the right thing.

## Cost of rediscovery
~5 min
"""


def in_sandbox(fn):
    """Run fn(home, tmp) with HOME pointed at a fresh temp dir."""
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp), pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def write_draft(tmp, text):
    draft = tmp / "draft.md"
    draft.write_text(text, encoding="utf-8")
    return str(draft)


def test_valid_global_skill_saves_and_materializes():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        assert (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_antiskill_goes_to_antiskills_dir():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_ANTISKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/antiskills/test-trap/SKILL.md").exists()
        assert (home / ".claude/skills/skillforge-hot/test-trap/SKILL.md").exists()
    in_sandbox(check)


def test_project_scope_writes_under_project_root():
    def check(home, tmp):
        proj = tmp / "myrepo"
        proj.mkdir()
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "project",
                              "--project-root", str(proj)])
        assert rc == 0
        assert (proj / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        assert (proj / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
        assert not (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_secret_blocks_save():
    def check(home, tmp):
        bad = VALID_SKILL + '\n2. Set api_key = "sk_live_' + "a" * 24 + '"\n'
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
        assert not (home / ".claude/skillforge/skills/test-skill").exists()
        assert not (home / ".claude/skills/skillforge-hot/test-skill").exists()
    in_sandbox(check)


def test_missing_verification_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("## Verification", "## Notes")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
        assert not (home / ".claude/skillforge/skills/test-skill").exists()
    in_sandbox(check)


def test_antiskill_missing_section_rejected():
    def check(home, tmp):
        bad = VALID_ANTISKILL.replace("## Cause", "## Reason")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_description_without_do_not_use_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("Do NOT use when: doing anything real.", "Always applicable.")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_bad_name_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("name: test-skill", "name: Test Skill!")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_missing_frontmatter_rejected():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, "## Procedure\njust a body\n"),
                              "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_folded_description_is_parsed():
    fm, _ = save_skill.parse_frontmatter(VALID_SKILL)
    assert "Do NOT use when" in fm["description"]
    assert fm["name"] == "test-skill"


def test_cross_kind_name_collision_rejected_and_native_copy_preserved():
    def check(home, tmp):
        skill = VALID_SKILL.replace("name: test-skill", "name: clash")
        antiskill = VALID_ANTISKILL.replace("name: test-trap", "name: clash")
        rc1 = save_skill.main([write_draft(tmp, skill), "--scope", "global"])
        assert rc1 == 0
        rc2 = save_skill.main([write_draft(tmp, antiskill), "--scope", "global"])
        assert rc2 == 1
        native = home / ".claude/skills/skillforge-hot/clash/SKILL.md"
        assert native.exists()
        assert native.read_text(encoding="utf-8") == skill
        assert not (home / ".claude/skillforge/antiskills/clash").exists()
    in_sandbox(check)


def test_invalid_kind_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("kind: skill", "kind: bogus")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_crlf_frontmatter_is_parsed():
    def check(home, tmp):
        crlf = VALID_SKILL.replace("\n", "\r\n")
        assert save_skill.validate(crlf) == []
    in_sandbox(check)


def test_frontmatter_fence_without_trailing_newline_is_detected():
    draft = "---\nname: x\nkind: skill\ndescription: d\n---"
    errors = save_skill.validate(draft)
    assert "missing frontmatter (--- fenced block)" not in errors


def test_missing_verification_command_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace('verification.command: "true"\n', "")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_antiskill_without_verification_command_ok():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_ANTISKILL), "--scope", "global"])
        assert rc == 0
    in_sandbox(check)


def test_parse_dotted_key_and_list():
    fm, _ = save_skill.parse_frontmatter(VALID_SKILL)
    assert fm["verification.command"] == '"true"' or fm["verification.command"] == "true"
    assert fm["fingerprints"] == ["do_the_thing --alpha", "thing_output=42"]


def test_save_auto_trusts_and_logs():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        reg = trust.load()
        assert reg["test-skill"]["origin"] == "self"
        con = ledger.connect()
        rows = con.execute(
            "SELECT event_type, outcome FROM events WHERE skill='test-skill'").fetchall()
        con.close()
        assert ("save", "saved") in rows
    in_sandbox(check)


def test_few_fingerprints_warns_but_saves():
    def check(home, tmp):
        bad = VALID_SKILL.replace('  - "thing_output=42"\n', "")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 0
        assert "WARNING" in out.getvalue()
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_save_with_zero_hot_budget_reports_warm():
    def check(home, tmp):
        old = os.environ.get("SKILLFORGE_HOT_BUDGET")
        os.environ["SKILLFORGE_HOT_BUDGET"] = "0"
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
            assert rc == 0
            assert "warm tier" in out.getvalue()
            assert not (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
            assert (home / ".claude/skillforge/index.json").exists()
        finally:
            if old is None:
                del os.environ["SKILLFORGE_HOT_BUDGET"]
            else:
                os.environ["SKILLFORGE_HOT_BUDGET"] = old
    in_sandbox(check)


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except AssertionError:
                failures += 1
                print("FAIL " + name)
    sys.exit(1 if failures else 0)
