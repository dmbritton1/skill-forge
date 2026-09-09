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


import distill


def test_outcome_ranks_repair_failure_above_everything_else():
    """A session that fixed nothing and then distilled confidently must not
    enter the funnel as a healthy emission just because save_skill exited 0."""
    assert distill.outcome(False, False, "draft", 0) == "repair_unresolved"
    assert distill.outcome(False, True, None, None) == "repair_unresolved"


def test_outcome_separates_a_timeout_from_an_abort():
    """Both produce no draft. Only one is the novelty gate working."""
    assert distill.outcome(True, True, None, None) == "timed_out"
    assert distill.outcome(True, False, None, None) == "aborted"


def test_outcome_reports_a_rejected_draft():
    assert distill.outcome(True, False, "draft", 1) == "rejected"


def test_a_rejection_with_no_draft_is_not_an_abort():
    """save_skill leaves nothing in the store when it refuses, so a rejection
    and a novelty-gate abort look identical from the filesystem. Ordering
    `rejected` first is what keeps the most informative failure the distiller
    can produce from being relabelled as the gate working."""
    assert distill.outcome(True, False, None, 1) == "rejected"


def test_outcome_saved_is_the_only_probeable_one():
    assert distill.outcome(True, False, "draft", 0) == "saved"
    probeable = [o for o in ("repair_unresolved", "timed_out", "aborted",
                             "rejected", "saved") if distill.probeable(o)]
    assert probeable == ["saved"], probeable


def test_extract_finds_the_store_copy_not_the_native_one():
    """sync.py appends a rewritten MARKER_NOTE to the materialized copy only,
    so the native copy is a delivery artifact, not the draft."""
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp)
            store = clone / ".claude" / "skillforge" / "antiskills" / "trap-thing"
            store.mkdir(parents=True)
            store.joinpath("SKILL.md").write_text("STORE COPY\n", encoding="utf-8")
            native = clone / ".claude" / "skills" / "skillforge-trap-thing"
            native.mkdir(parents=True)
            native.joinpath("SKILL.md").write_text("NATIVE COPY\n", encoding="utf-8")
            found = distill.extract(clone, "learn-failure")
            assert found is not None
            assert found.read_text(encoding="utf-8") == "STORE COPY\n"
    in_home(check)


def test_extract_looks_in_the_kind_directory_the_distiller_writes():
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp)
            store = clone / ".claude" / "skillforge" / "skills" / "a-skill"
            store.mkdir(parents=True)
            store.joinpath("SKILL.md").write_text("X\n", encoding="utf-8")
            assert distill.extract(clone, "learn") is not None
            assert distill.extract(clone, "learn-failure") is None
    in_home(check)


def test_extract_is_none_when_nothing_saved():
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            assert distill.extract(pathlib.Path(tmp), "learn-failure") is None
    in_home(check)


def test_archive_dir_shape_matches_what_arm_segment_parses():
    d = distill.archive_dir("trapA", "learn-failure", 2)
    assert d.parts[-3:] == ("trapA", "learn-failure", "2"), d.parts[-3:]


def test_preflight_blocks_when_the_global_store_is_dirty():
    """distilling-failures step 3 runs `ls ~/.claude/skillforge/antiskills/`.
    A leaked draft turns the next draw from independent into dependent, because
    the session proposes UPDATING it instead of drafting fresh."""
    def check(home):
        _seed(home, stores=[("antiskills", "leftover")])
        out = distill.preflight()
        assert out and "leftover" in out[0], out
    in_home(check)


def test_preflight_passes_on_a_clean_store():
    def check(home):
        _seed(home)
        assert distill.preflight() == []
    in_home(check)


def test_extract_finds_a_global_scope_save():
    """The distiller picks its own scope, and --scope global writes to
    Path.home(), not the clone. This used to read as `aborted` -- and then
    containment deleted the draft before anything archived it."""
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp)
            store = home / ".claude" / "skillforge" / "antiskills" / "global-trap"
            store.mkdir(parents=True)
            store.joinpath("SKILL.md").write_text("GLOBAL COPY\n", encoding="utf-8")
            found = distill.extract(clone, "learn-failure")
            assert found is not None, "a global-scope save must still be found"
            assert found.read_text(encoding="utf-8") == "GLOBAL COPY\n"
    in_home(check)


def test_extract_prefers_the_project_store_over_the_global_one():
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp)
            proj = clone / ".claude" / "skillforge" / "antiskills" / "a"
            proj.mkdir(parents=True)
            proj.joinpath("SKILL.md").write_text("PROJECT\n", encoding="utf-8")
            glob_ = home / ".claude" / "skillforge" / "antiskills" / "b"
            glob_.mkdir(parents=True)
            glob_.joinpath("SKILL.md").write_text("GLOBAL\n", encoding="utf-8")
            assert distill.extract(clone, "learn-failure").read_text(
                encoding="utf-8") == "PROJECT\n"
    in_home(check)


def test_drafts_counts_every_save_across_both_stores():
    """Taking the first is defensible; taking it silently is not."""
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp)
            for name in ("a", "b"):
                p = clone / ".claude" / "skillforge" / "antiskills" / name
                p.mkdir(parents=True)
                p.joinpath("SKILL.md").write_text(name, encoding="utf-8")
            g = home / ".claude" / "skillforge" / "antiskills" / "c"
            g.mkdir(parents=True)
            g.joinpath("SKILL.md").write_text("c", encoding="utf-8")
            assert len(distill.drafts(clone, "learn-failure")) == 3
    in_home(check)


def test_drafts_is_empty_when_nothing_saved():
    def check(home):
        with tempfile.TemporaryDirectory() as tmp:
            assert distill.drafts(pathlib.Path(tmp), "learn-failure") == []
    in_home(check)


def test_ledger_rows_records_a_read_failure():
    """A failed read and an uneventful session both yield empty lists, and
    `rejects` comes only from here -- so without this field a real rejection
    that fails to read back is indistinguishable from `aborted`."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "not-a-database.db"
        bad.write_text("this is not sqlite", encoding="utf-8")
        rows = distill._ledger_rows(bad)
        assert rows["events"] == [] and rows["decisions"] == []
        assert rows["read_error"] is not None, "a read failure must be recorded"


def test_ledger_rows_reads_a_real_ledger_and_reports_no_error():
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "l.db"
        con = sqlite3.connect(str(db))
        con.execute("create table events (id integer primary key, event_type text,"
                    " skill text, outcome text, ts text)")
        con.execute("create table decisions (id integer primary key, actor text,"
                    " verdict text, subject text, reason text)")
        con.execute("insert into events (event_type, skill, outcome, ts)"
                    " values ('save','x','saved','t')")
        con.execute("insert into decisions (actor, verdict, subject, reason)"
                    " values ('system','rejected','x','no verification.command')")
        con.commit(); con.close()
        rows = distill._ledger_rows(db)
        assert rows["read_error"] is None, rows["read_error"]
        assert len(rows["events"]) == 1 and len(rows["decisions"]) == 1
        assert rows["decisions"][0]["verdict"] == "rejected"


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
