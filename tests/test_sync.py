"""Tests for trust-gated native sync. Run: python3 tests/test_sync.py"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import sync
import trust

SKILL = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
---
## Procedure
1. Do it.
"""


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def put_skill(base, name, text=None):
    d = base / ".claude" / "skillforge" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(text if text is not None else SKILL % name, encoding="utf-8")
    return md


ANTISKILL = """---
name: %s
kind: antiskill
description: A trap. Do NOT use otherwise.
symptoms:
  - "WidgetFlushedError: the widget was already flushed"
fingerprints:
  - "await widget.flush({ force: true })"
---
## Trap
t
## Symptom
s
## Cause
c
## Fix
f
"""

SKILL_WITH_TRIGGERS = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "npx stripe trigger payment_intent.succeeded"
fingerprints:
  - "express.raw({type: 'application/json'})"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def put_antiskill(base, name, text=None):
    d = base / ".claude" / "skillforge" / "antiskills" / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(text if text is not None else ANTISKILL % name, encoding="utf-8")
    return md


def read_json(home, filename):
    import json
    return json.loads((home / ".claude" / "skillforge" / filename).read_text(encoding="utf-8"))


def native_md(base, name):
    return base / ".claude" / "skills" / "skillforge-hot" / name / "SKILL.md"


def test_trusted_skill_materialized():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures materialization, not the gate
        counts = sync.sync()
        assert counts["materialized"] == 1 and counts["quarantined"] == 0
        assert native_md(home, "alpha").read_text(encoding="utf-8") == SKILL % "alpha"
    in_sandbox(check)


def test_untrusted_skill_quarantined_not_materialized():
    def check(home):
        put_skill(home, "alpha")
        counts = sync.sync()
        assert counts["quarantined"] == 1 and counts["materialized"] == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_modified_store_evicts_native():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures eviction, not the gate
        sync.sync()
        assert native_md(home, "alpha").exists()
        md.write_text(md.read_text(encoding="utf-8") + "\nEXTRA LINE\n", encoding="utf-8")
        counts = sync.sync()
        assert counts["quarantined"] == 1 and counts["evicted"] == 1
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_orphan_native_dir_evicted():
    def check(home):
        stale = home / ".claude" / "skills" / "skillforge-hot" / "ghost"
        stale.mkdir(parents=True)
        (stale / "SKILL.md").write_text("boo", encoding="utf-8")
        counts = sync.sync()
        assert counts["evicted"] == 1
        assert not stale.exists()
    in_sandbox(check)


def test_project_root_store_synced():
    def check(home):
        proj = home / "myrepo"
        md = put_skill(proj, "beta")
        trust.record("beta", md.read_text(encoding="utf-8"), "self")
        earn_success("beta")   # hot-eligible: this test measures project-root sync, not the gate
        counts = sync.sync(project_root=str(proj))
        assert counts["materialized"] == 1
        assert native_md(proj, "beta").exists()
    in_sandbox(check)


def test_corrupt_trust_json_quarantines_and_exits_zero():
    def check(home):
        put_skill(home, "alpha")
        reg = home / ".claude" / "skillforge" / "trust.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text("{not json", encoding="utf-8")
        rc = sync.main([])
        assert rc == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_sync_is_idempotent():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures idempotency, not the gate
        first = sync.sync()
        second = sync.sync()
        assert first["materialized"] == second["materialized"] == 1
        assert second["evicted"] == 0
    in_sandbox(check)


def read_index(home):
    import json
    return json.loads((home / ".claude" / "skillforge" / "index.json").read_text(encoding="utf-8"))


def with_budget(value, fn):
    old = os.environ.get("SKILLFORGE_HOT_BUDGET")
    os.environ["SKILLFORGE_HOT_BUDGET"] = value
    try:
        fn()
    finally:
        if old is None:
            del os.environ["SKILLFORGE_HOT_BUDGET"]
        else:
            os.environ["SKILLFORGE_HOT_BUDGET"] = old


def test_hot_budget_overflow_goes_warm():
    def check(home):
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        # Both are hot-ELIGIBLE (the gate is not what this test measures);
        # beta outranks alpha on bucket, so the single slot is beta's.
        earn_success("alpha", session="s1")             # working
        earn_success("beta", session="s1")               # trusted
        earn_success("beta", session="s2")

        def run():
            counts = sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}
            assert native_md(home, "beta").exists()
            assert not native_md(home, "alpha").exists()
            assert counts["materialized"] == 1
        with_budget("10", run)
    in_sandbox(check)


def test_index_contains_trusted_only_with_paths():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")   # hot-eligible: this test measures index contents, not the gate
        put_skill(home, "gamma")  # never recorded -> quarantined
        sync.sync()
        idx = read_index(home)
        names = [e["name"] for e in idx["entries"]]
        assert names == ["alpha"]
        e = idx["entries"][0]
        assert e["tier"] == "hot" and e["kind"] == "skill" and e["scope"] == "global"
        assert e["root"] == str(home)
        assert pathlib.Path(e["path"]).is_file()
        assert e["description"].startswith("A thing.")
    in_sandbox(check)


def test_stale_session_state_cleanup():
    def check(home):
        import time
        d = home / ".claude" / "skillforge" / "state"
        d.mkdir(parents=True)
        old = d / "session-old.json"
        new = d / "session-new.json"
        old.write_text("[]", encoding="utf-8")
        new.write_text("[]", encoding="utf-8")
        stale = time.time() - 8 * 86400
        os.utime(old, (stale, stale))
        sync.sync()
        assert not old.exists()
        assert new.exists()
    in_sandbox(check)


def test_project_root_recorded_resolved():
    def check(home):
        import json, os
        proj = home / "myrepo"
        md = put_skill(proj, "beta")
        trust.record("beta", md.read_text(encoding="utf-8"), "self")
        old = os.getcwd()
        os.chdir(str(proj))
        try:
            sync.sync(project_root=".")
        finally:
            os.chdir(old)
        idx = json.loads((home / ".claude" / "skillforge" / "index.json").read_text(encoding="utf-8"))
        roots = {e["name"]: e["root"] for e in idx["entries"]}
        assert pathlib.Path(roots["beta"]).is_absolute()
        assert pathlib.Path(roots["beta"]) == proj.resolve()
    in_sandbox(check)


def test_triggers_compiled_from_trusted_skills():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        md2 = put_skill(home, "stripe-hook", SKILL_WITH_TRIGGERS % "stripe-hook")
        trust.record("stripe-hook", md2.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert [s["skill"] for s in trig["symptoms"]] == ["widget-trap"]
        assert trig["symptoms"][0]["tokens"] == [
            "widgetflushederror", "the", "widget", "was", "already", "flushed"]
        assert trig["symptoms"][0]["path"] == str(md)
        assert trig["symptoms"][0]["root"] == str(home)
        assert [v["skill"] for v in trig["verifications"]] == ["stripe-hook"]
        assert trig["verifications"][0]["tokens"] == [
            "npx", "stripe", "trigger", "payment_intent", "succeeded"]
    in_sandbox(check)


def test_quarantined_antiskill_symptoms_excluded():
    def check(home):
        put_antiskill(home, "widget-trap")   # never trusted
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"] == []
    in_sandbox(check)


def test_antiskills_are_never_hot():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["widget-trap"]["tier"] == "warm"
        assert not native_md(home, "widget-trap").exists()
    in_sandbox(check)


def test_antiskills_do_not_consume_hot_budget():
    def check(home):
        # "aaa-trap" sorts BEFORE "zeta" once both are eligible and tied.
        md = put_antiskill(home, "aaa-trap")
        trust.record("aaa-trap", md.read_text(encoding="utf-8"), "self")
        md2 = put_skill(home, "zeta")
        trust.record("zeta", md2.read_text(encoding="utf-8"), "self")
        # Both earn eligibility, and identical timestamps make the tiebreak
        # name ASC -- so "aaa-trap" would take the only slot if anti-skills
        # still competed. That ordering is what gives this test its force.
        stamp = "2026-01-01T00:00:00+00:00"
        earn_success("aaa-trap", session="s1", ts=stamp)
        earn_success("zeta", session="s1", ts=stamp)
        os.environ["SKILLFORGE_HOT_BUDGET"] = "8"   # room for exactly one description
        try:
            sync.sync()
        finally:
            del os.environ["SKILLFORGE_HOT_BUDGET"]
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["zeta"]["tier"] == "hot"     # the antiskill did not eat the budget
        assert entries["aaa-trap"]["tier"] == "warm"
    in_sandbox(check)


SKILL_WITH_SYMPTOMS = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "npx stripe trigger payment_intent.succeeded"
symptoms:
  - "SomeError: this should never fire from a plain skill"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def test_skill_kind_symptoms_excluded_from_triggers():
    def check(home):
        # save_skill.validate never forbids `symptoms:` on kind: skill -- only
        # a kind: antiskill entry should compile into triggers.json's symptom
        # list, framed and budgeted as an anti-skill by detect.py.
        md = put_skill(home, "stripe-hook", SKILL_WITH_SYMPTOMS % "stripe-hook")
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"] == []
        assert [v["skill"] for v in trig["verifications"]] == ["stripe-hook"]
    in_sandbox(check)


def test_antiskill_symptom_entries_carry_fingerprints():
    def check(home):
        md = put_antiskill(home, "widget-trap")
        trust.record("widget-trap", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["symptoms"][0]["fingerprints"] == [
            ["await", "widget", "flush", "force", "true"]]
    in_sandbox(check)


SKILL_SINGLE_TOKEN = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "pytest"
fingerprints:
  - "make"
  - "express.raw({type: 'application/json'})"
---
## Procedure
1. Do it.
## Verification
Run the command.
"""


def test_single_token_verification_and_fingerprint_patterns_dropped():
    def check(home):
        # A verification.command or fingerprint that tokenizes to one common
        # word ("pytest", "make") would match nearly every unrelated Bash
        # call or file, inflating skill_aggregates.uses.
        md = put_skill(home, "single-tok", SKILL_SINGLE_TOKEN % "single-tok")
        trust.record("single-tok", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        trig = read_json(home, "triggers.json")
        assert trig["verifications"] == []   # "pytest" tokenizes to 1 token
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["single-tok"]["fingerprints"] == [
            ["express", "raw", "type", "application", "json"]]  # "make" dropped
    in_sandbox(check)


def test_index_carries_tokenized_fingerprints():
    def check(home):
        md = put_skill(home, "stripe-hook", SKILL_WITH_TRIGGERS % "stripe-hook")
        trust.record("stripe-hook", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entries = {e["name"]: e for e in read_json(home, "index.json")["entries"]}
        assert entries["stripe-hook"]["fingerprints"] == [
            ["express", "raw", "type", "application", "json"]]
    in_sandbox(check)


def earn_success(name, session="s1", ts=None):
    """Give a skill one successful session, the bar for `working`."""
    import ledger
    ledger.log_event("detection", name, detection="verification",
                     outcome="success", session=session, ts=ts)


def test_index_entries_carry_a_bucket():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "unproven"
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "working"
    in_sandbox(check)


def test_unproven_skill_never_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        counts = sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "warm"
        assert counts["materialized"] == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_working_skill_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "hot"
        assert native_md(home, "alpha").exists()
    in_sandbox(check)


def test_trusted_outranks_working_for_a_scarce_hot_slot():
    def check(home):
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        earn_success("alpha", session="s1")          # working
        earn_success("beta", session="s1")           # trusted: two sessions
        earn_success("beta", session="s2")

        def run():
            sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}, tiers
        with_budget("10", run)
    in_sandbox(check)


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
