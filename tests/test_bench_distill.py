"""Tests for the Q1 phase-1 harness. Run: python3 tests/test_bench_distill.py"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import libguard


def in_home(fn):
    """Run fn(home) with HOME pointed at a fresh temp dir."""
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old


def _seed(home, *, stores=(), entries=(), trust_keys=()):
    d = home / ".claude" / "skillforge"
    (d / "skills").mkdir(parents=True, exist_ok=True)
    (d / "antiskills").mkdir(parents=True, exist_ok=True)
    for kind, name in stores:
        p = d / kind / name
        p.mkdir(parents=True, exist_ok=True)
        (p / "SKILL.md").write_text("---\nname: %s\n---\n" % name, encoding="utf-8")
    (d / "index.json").write_text(json.dumps({"entries": list(entries)}), encoding="utf-8")
    (d / "trust.json").write_text(
        json.dumps({k: {"origin": "self"} for k in trust_keys}), encoding="utf-8")


def test_snapshot_reads_stores_index_and_trust():
    def check(home):
        _seed(home,
              stores=[("antiskills", "alpha")],
              entries=[{"name": "alpha", "scope": "global"},
                       {"name": "beta", "scope": "project", "root": "/repo"}],
              trust_keys=["alpha"])
        s = libguard.snapshot()
        assert s["stores"] == ["antiskills/alpha"], s["stores"]
        assert s["global_index"] == ["alpha"], s["global_index"]
        assert s["project_index"] == ["beta"], s["project_index"]
        assert s["trust"] == ["alpha"], s["trust"]
    in_home(check)


def test_snapshot_on_a_bare_home_is_empty_not_an_error():
    def check(home):
        s = libguard.snapshot()
        assert s == {"stores": [], "global_index": [], "project_index": [],
                     "trust": []}, s
    in_home(check)


def test_new_global_skills_names_what_a_session_added():
    def check(home):
        _seed(home)
        before = libguard.snapshot()
        _seed(home, stores=[("antiskills", "leaked")])
        assert libguard.new_global_skills(before) == ["leaked"]
    in_home(check)


def test_prune_trust_drops_only_the_named_keys():
    def check(home):
        _seed(home, trust_keys=["keep", "drop"])
        assert libguard.prune_trust(["drop"]) == 1
        after = json.loads(
            (home / ".claude" / "skillforge" / "trust.json").read_text(encoding="utf-8"))
        assert sorted(after) == ["keep"], after
    in_home(check)


def test_drift_is_empty_when_nothing_changed():
    def check(home):
        _seed(home, stores=[("skills", "a")], entries=[{"name": "a", "scope": "global"}],
              trust_keys=["a"])
        assert libguard.drift(libguard.snapshot()) == []
    in_home(check)


def test_drift_ignores_compiled_ts_and_entry_order():
    """index.json is rewritten wholesale on every sync, so a byte comparison
    reports drift on every run. Only the entry NAME SET is meaningful."""
    def check(home):
        _seed(home, entries=[{"name": "a", "scope": "global"},
                             {"name": "b", "scope": "global"}])
        before = libguard.snapshot()
        d = home / ".claude" / "skillforge"
        (d / "index.json").write_text(json.dumps(
            {"compiled_ts": "2026-09-08T00:00:00+00:00",
             "entries": [{"name": "b", "scope": "global"},
                         {"name": "a", "scope": "global"}]}), encoding="utf-8")
        assert libguard.drift(before) == []
    in_home(check)


def test_drift_reports_a_dropped_project_entry():
    """library.py delete's _resync calls sync(project_root=None), whose bases
    is [Path.home()] alone -- so it rebuilds index.json without the operator's
    project skills. Derived and self-healing, but the assertion must see it."""
    def check(home):
        _seed(home, entries=[{"name": "proj", "scope": "project", "root": "/repo"}])
        before = libguard.snapshot()
        d = home / ".claude" / "skillforge"
        (d / "index.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
        out = libguard.drift(before)
        assert len(out) == 1 and "project" in out[0].lower(), out
    in_home(check)


def test_drift_reports_a_leaked_global_store_entry():
    def check(home):
        _seed(home)
        before = libguard.snapshot()
        _seed(home, stores=[("skills", "leaked")])
        out = libguard.drift(before)
        assert any("leaked" in m for m in out), out
    in_home(check)


def test_snapshot_survives_a_structurally_wrong_index():
    """index.json parsing to a LIST rather than a dict used to reach
    .get("entries") and raise. drift() is the containment assertion for an
    unattended batch: it must report an anomaly, never abort the batch."""
    def check(home):
        _seed(home)
        d = home / ".claude" / "skillforge"
        (d / "index.json").write_text("[]", encoding="utf-8")
        s = libguard.snapshot()
        assert s["global_index"] == [] and s["project_index"] == [], s
    in_home(check)


def test_snapshot_survives_a_structurally_wrong_trust_file():
    def check(home):
        _seed(home)
        d = home / ".claude" / "skillforge"
        (d / "trust.json").write_text('"not a registry"', encoding="utf-8")
        assert libguard.snapshot()["trust"] == []
    in_home(check)


def test_a_wrong_shaped_index_reports_drift_rather_than_raising():
    def check(home):
        _seed(home, entries=[{"name": "proj", "scope": "project", "root": "/repo"}])
        before = libguard.snapshot()
        d = home / ".claude" / "skillforge"
        (d / "index.json").write_text("null", encoding="utf-8")
        out = libguard.drift(before)
        assert out and any("proj" in m for m in out), out
    in_home(check)


def test_prune_trust_writes_the_same_format_as_trust_py():
    """scripts/trust.py:47 writes indent=2, sort_keys=True, trailing newline."""
    def check(home):
        _seed(home, trust_keys=["b", "a", "drop"])
        libguard.prune_trust(["drop"])
        text = (home / ".claude" / "skillforge" / "trust.json").read_text(encoding="utf-8")
        assert text.endswith("\n"), "trust.json must end with a newline"
        assert text.index('"a"') < text.index('"b"'), "keys must be sorted"
    in_home(check)


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
