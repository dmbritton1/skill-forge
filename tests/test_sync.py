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
