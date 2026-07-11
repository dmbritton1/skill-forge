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


def native_md(base, name):
    return base / ".claude" / "skills" / "skillforge-hot" / name / "SKILL.md"


def test_trusted_skill_materialized():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
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
        import ledger
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        ledger.log_event("injection", "beta")
        ledger.log_event("injection", "beta")

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
