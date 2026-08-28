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

# Every successful save spawns critique in the background (Task 7). No suite
# may spawn a real subprocess, so the seam is stubbed inert here for every
# test in this file; the two spawn tests below install their own stub over
# top of this one and restore it (not the real Popen-backed function).
# The real function is saved first: the env-inspection tests near the
# bottom of this file call it directly (with subprocess.Popen itself
# stubbed out) to check what it builds, and would otherwise see this inert
# lambda instead.
_REAL_SPAWN_VALIDATION = save_skill._spawn_validation
save_skill._spawn_validation = lambda name, mode: None

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
symptoms:
  - "TestTrapError: the widget was already flushed"
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


def write_candidate(home):
    """A valid skill draft named widget-flush, for the spawn-on-save tests."""
    text = VALID_SKILL.replace("name: test-skill", "name: widget-flush")
    return write_draft(home, text)


def test_valid_global_skill_saves_and_materializes():
    def check(home, tmp):
        import json
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        # v0.2 slice C2: a freshly saved skill is unproven -- it does not
        # materialize until it earns a real verification success.
        assert not (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
        idx = json.loads((home / ".claude/skillforge/index.json").read_text(encoding="utf-8"))
        entry = {e["name"]: e for e in idx["entries"]}["test-skill"]
        assert entry["bucket"] == "unproven"

        ledger.log_event("detection", "test-skill", detection="verification",
                         outcome="success", session="s1")
        import sync
        sync.sync()
        assert (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_antiskill_goes_to_antiskills_dir():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_ANTISKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/antiskills/test-trap/SKILL.md").exists()
        # v0.2 slice C1: anti-skills are delivered by symptom trigger, never
        # materialized into the native hot dir (sync.py forces them warm).
        assert not (home / ".claude/skills/skillforge-hot/test-trap/SKILL.md").exists()
    in_sandbox(check)


def test_project_scope_writes_under_project_root():
    def check(home, tmp):
        proj = tmp / "myrepo"
        proj.mkdir()
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "project",
                              "--project-root", str(proj)])
        assert rc == 0
        assert (proj / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        assert not (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        # v0.2 slice C2: freshly saved is unproven, so it's warm until it
        # earns a success -- earn one and resync to exercise the native path
        # this test measures (materialization under the project root).
        ledger.log_event("detection", "test-skill", detection="verification",
                         outcome="success", session="s1")
        import sync
        sync.sync(project_root=str(proj))
        assert (proj / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
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
        # v0.2 slice C2: freshly saved is unproven -- earn a success and
        # resync so there is a native copy for the rejected second save to
        # (not) disturb, which is what "preserved" in this test measures.
        ledger.log_event("detection", "clash", detection="verification",
                         outcome="success", session="s1")
        import sync
        sync.sync()
        native = home / ".claude/skills/skillforge-hot/clash/SKILL.md"
        assert native.exists()
        assert native.read_text(encoding="utf-8") == skill

        rc2 = save_skill.main([write_draft(tmp, antiskill), "--scope", "global"])
        assert rc2 == 1
        assert native.exists()
        assert native.read_text(encoding="utf-8") == skill
        assert not (home / ".claude/skillforge/antiskills/clash").exists()
    in_sandbox(check)


def test_project_skill_collides_with_global_skill_of_same_name_rejected():
    def check(home, tmp):
        rc1 = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc1 == 0
        proj = tmp / "myrepo"
        proj.mkdir()
        rc2 = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "project",
                              "--project-root", str(proj)])
        assert rc2 == 1
        assert not (proj / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        # the global one is untouched
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_project_antiskill_collides_with_global_skill_of_same_name_rejected():
    def check(home, tmp):
        skill = VALID_SKILL.replace("name: test-skill", "name: clash")
        antiskill = VALID_ANTISKILL.replace("name: test-trap", "name: clash")
        rc1 = save_skill.main([write_draft(tmp, skill), "--scope", "global"])
        assert rc1 == 0
        proj = tmp / "myrepo"
        proj.mkdir()
        rc2 = save_skill.main([write_draft(tmp, antiskill), "--scope", "project",
                              "--project-root", str(proj)])
        assert rc2 == 1
        assert not (proj / ".claude/skillforge/antiskills/clash").exists()
    in_sandbox(check)


def test_resave_same_skill_in_place_from_home_cwd_not_rejected():
    def check(home, tmp):
        # Regression: --project-root defaults to "." and, before store_dir
        # resolved it, was compared unresolved against the always-absolute
        # Path.home() -- so from cwd == $HOME, the "project" scope
        # candidate (relative ".claude/skillforge/skills/<name>") never
        # equaled "this_dir" (absolute "~/.claude/skillforge/skills/<name>")
        # even though they're the same directory, and candidate.exists()
        # still resolved against cwd and found it -- self-rejecting every
        # re-save of an existing skill run from $HOME.
        old_cwd = os.getcwd()
        os.chdir(str(home))
        try:
            rc1 = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
            assert rc1 == 0
            rc2 = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
            assert rc2 == 0
        finally:
            os.chdir(old_cwd)
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
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


NESTED_UNDER_A_SCALAR_KEY = """---
name: test-skill
kind: skill
description:
  note: a model indented this by mistake
verification.command: "true"
---
## Procedure
1. Do the thing.

## Verification
- `true` exits 0.
"""


def test_a_nested_map_under_a_scalar_key_is_a_rejection_not_a_traceback():
    """Only `provenance`/`preconditions` are maps by contract.

    A model-written nested `description:` (or `name:`) must still parse to ""
    and come back through validate() as a REASON. Parsed as a dict it would
    survive `if not fm.get(key)` and reach desc.lower() -- validate() would
    raise instead of returning, which draft.py turns into a generic "failed"
    (losing the retry-with-errors path) and a manual save turns into a
    traceback instead of `REJECTED:`.
    """
    fm, _ = save_skill.parse_frontmatter(NESTED_UNDER_A_SCALAR_KEY)
    assert fm["description"] == "", fm
    errors = save_skill.validate(NESTED_UNDER_A_SCALAR_KEY)
    assert any("description" in e for e in errors), errors
    # The contract keys still parse as maps -- validate.executable() reads
    # provenance.repo out of the index sync.py compiles from this dict.
    assert save_skill.parse_frontmatter(VALID_SKILL)[0]["provenance"] == {
        "repo": "local/skill-forge", "distilled": "2026-07-09"}


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


def test_single_token_verification_command_warns():
    def check(home, tmp):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        # "true" is one token, so sync drops it and the skill would get no
        # usage detection at all -- the save must say so
        assert "single token" in out.getvalue()
        assert "verification.command" in out.getvalue()
    in_sandbox(check)


def test_multi_token_verification_command_does_not_warn():
    def check(home, tmp):
        good = VALID_SKILL.replace('verification.command: "true"',
                                   'verification.command: "npx probe run all"')
        out = io.StringIO()
        with redirect_stdout(out):
            rc = save_skill.main([write_draft(tmp, good), "--scope", "global"])
        assert rc == 0
        assert "single token" not in out.getvalue()
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


def test_global_save_keeps_project_entries_indexed():
    def check(home, tmp):
        import json
        proj = home / "myrepo"
        d = proj / ".claude" / "skillforge" / "skills" / "proj-skill"
        d.mkdir(parents=True)
        text = VALID_SKILL.replace("name: test-skill", "name: proj-skill")
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        import trust
        trust.record("proj-skill", text, "self")
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global",
                              "--project-root", str(proj)])
        assert rc == 0
        idx = json.loads((home / ".claude/skillforge/index.json").read_text(encoding="utf-8"))
        names = sorted(e["name"] for e in idx["entries"])
        assert names == ["proj-skill", "test-skill"]
    in_sandbox(check)


def test_antiskill_without_symptoms_rejected():
    text = VALID_ANTISKILL.replace(
        'symptoms:\n  - "TestTrapError: the widget was already flushed"\n', "")
    errors = save_skill.validate(text)
    assert any("symptoms" in e for e in errors), errors


def test_antiskill_symptom_too_short_rejected():
    text = VALID_ANTISKILL.replace(
        '"TestTrapError: the widget was already flushed"', '"Error"')
    errors = save_skill.validate(text)
    assert any("too weak" in e for e in errors), errors


def test_antiskill_symptom_short_but_multitoken_rejected():
    # Isolates the char-length rule: "ab cd" is 5 chars (< MIN_SYMPTOM_CHARS)
    # but tokenizes to 2 tokens, so only the length branch can reject it.
    text = VALID_ANTISKILL.replace(
        '"TestTrapError: the widget was already flushed"', '"ab cd"')
    errors = save_skill.validate(text)
    assert any("too weak" in e for e in errors), errors


def test_antiskill_symptom_single_token_rejected():
    text = VALID_ANTISKILL.replace(
        '"TestTrapError: the widget was already flushed"', '"WidgetFlushedError"')
    errors = save_skill.validate(text)
    assert any("too weak" in e for e in errors), errors


def test_antiskill_with_good_symptom_accepted():
    assert save_skill.validate(VALID_ANTISKILL) == []


def test_skills_do_not_need_symptoms():
    assert save_skill.validate(VALID_SKILL) == []


def test_warm_message_names_unproven_not_budget():
    def check(home, tmp):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        text = out.getvalue()
        assert "indexed: warm tier" in text
        assert "unproven" in text
        assert "hot budget full" not in text
    in_sandbox(check)


def test_a_successful_save_spawns_critique():
    def check(home, tmp):
        seen = []
        real = save_skill._spawn_validation
        save_skill._spawn_validation = lambda name, mode: seen.append((name, mode))
        try:
            rc = save_skill.main([str(write_candidate(home)), "--scope", "global"])
        finally:
            save_skill._spawn_validation = real
        assert rc == 0, rc
        assert seen == [("widget-flush", "critique")], seen
    in_sandbox(check)


def test_a_failed_save_spawns_nothing():
    def check(home, tmp):
        seen = []
        real = save_skill._spawn_validation
        save_skill._spawn_validation = lambda name, mode: seen.append((name, mode))
        try:
            bad = home / "bad.md"
            bad.write_text("no frontmatter here", encoding="utf-8")
            rc = save_skill.main([str(bad), "--scope", "global"])
        finally:
            save_skill._spawn_validation = real
        # rc == 1 as well as seen == []: a change that made the save
        # succeed while still not spawning would otherwise pass this test.
        assert rc == 1, rc
        assert seen == [], seen
    in_sandbox(check)


def _capture_popen_env(name="widget-flush", mode="critique"):
    """Call the REAL _spawn_validation with subprocess.Popen stubbed out.

    Never spawns a real process -- Popen itself is replaced -- but still
    exercises the actual env-construction logic in save_skill.py, which the
    seam-swap tests above never touch (they replace _spawn_validation
    wholesale). Returns the `env` kwarg the real function handed to Popen.
    """
    calls = []
    real_popen = save_skill.subprocess.Popen

    class DummyProc:
        pass

    def fake_popen(argv, **kwargs):
        calls.append(kwargs.get("env"))
        return DummyProc()

    save_skill.subprocess.Popen = fake_popen
    try:
        _REAL_SPAWN_VALIDATION(name, mode)
    finally:
        save_skill.subprocess.Popen = real_popen
    return calls[0]


def test_spawn_does_not_manufacture_the_drafting_flag():
    old = os.environ.pop("SKILLFORGE_DRAFTING", None)
    try:
        env = _capture_popen_env()
        assert "SKILLFORGE_DRAFTING" not in env, env
    finally:
        if old is not None:
            os.environ["SKILLFORGE_DRAFTING"] = old


def test_spawn_inherits_the_drafting_flag_when_already_set():
    old = os.environ.get("SKILLFORGE_DRAFTING")
    os.environ["SKILLFORGE_DRAFTING"] = "1"
    try:
        env = _capture_popen_env()
        assert env.get("SKILLFORGE_DRAFTING") == "1", env
    finally:
        if old is None:
            del os.environ["SKILLFORGE_DRAFTING"]
        else:
            os.environ["SKILLFORGE_DRAFTING"] = old


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
