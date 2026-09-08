"""Tests for the library view and delete path (slice D1 design 8).
Run: python3 tests/test_library.py
"""
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import library
import sync
import trust

SKILL = """---
name: %s
kind: skill
description: A thing. Do NOT use otherwise.
verification.command: "python3 tests/test_thing.py"
---

## Procedure
1. Do it.

## Verification
- `python3 tests/test_thing.py` should exit 0.
"""


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
    # cwd is part of the sandbox, not just HOME. save_skill's --project-root
    # defaults to ".", so sync() treats whatever directory the suite happens to
    # run in as a project -- and then evicts that project's materialized hot
    # skills, because the trust store it judges them against lives in the
    # sandbox HOME and knows nothing about them. Running this suite inside a
    # real project used to delete that project's native copies.
        os.chdir(tmp)
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.chdir(old_cwd)
            os.environ["HOME"] = old_home


def put_skill(home, name):
    d = home / ".claude" / "skillforge" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    text = SKILL % name
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    trust.record(name, text, "self")
    sync.sync()
    return d


def capture(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = library.main(argv)
    return rc, out.getvalue()


def test_confidence_reports_both_sides():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", outcome="success", session="s1",
                         project="/repo/a/.git", path=db)
        ledger.log_event("detection", "foo", outcome="failure", session="s2",
                         project="/repo/b/.git", path=db)
        conf = ledger.confidence(path=db)
        assert conf["foo"]["successes"] == 1
        assert conf["foo"]["failures"] == 1
        # Contract update, not a softened assertion: without hashes there is
        # deliberately no "bucket" key at all -- see
        # test_confidence_without_hashes_refuses_to_answer_bucket.
        assert conf["foo"]["organic_bucket"] == "unproven"


def test_list_reports_bucket_and_counts():
    def check(home):
        put_skill(home, "alpha")
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        rows = {r["name"]: r for r in library.rows()}
        assert rows["alpha"]["bucket"] == "working"
        assert rows["alpha"]["successes"] == 1
        assert rows["alpha"]["failures"] == 0
    in_sandbox(check)


def test_list_of_an_empty_library_says_so():
    def check(home):
        sync.sync()
        rc, out = capture(["list"])
        assert rc == 0
        assert "empty" in out
    in_sandbox(check)


def test_list_names_every_trusted_skill():
    def check(home):
        put_skill(home, "alpha")
        put_skill(home, "beta")
        rc, out = capture(["list"])
        assert rc == 0
        assert "alpha" in out and "beta" in out
    in_sandbox(check)


def test_delete_removes_store_native_and_trust_entry():
    def check(home):
        store = put_skill(home, "alpha")
        # A fresh skill is `unproven`, so sync leaves it warm and never
        # materializes it. Give it a verified session so it earns `working`
        # and goes hot -- without this the native-dir assertion below passes
        # because the directory never existed, not because delete removed it.
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        sync.sync()
        native = home / ".claude" / "skills" / "skillforge-alpha"
        assert native.exists(), "precondition: skill must be hot before delete"
        assert "alpha" in trust.load()
        rc, _ = capture(["delete", "alpha"])
        assert rc == 0
        assert not store.exists()
        assert not native.exists()
        assert "alpha" not in trust.load()
    in_sandbox(check)


def test_delete_drops_it_from_the_index():
    def check(home):
        put_skill(home, "alpha")
        capture(["delete", "alpha"])
        assert [r["name"] for r in library.rows()] == []
    in_sandbox(check)


def test_delete_keeps_the_ledger_history():
    """Deleting a skill removes the skill, not the evidence about it."""
    def check(home):
        put_skill(home, "alpha")
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        capture(["delete", "alpha"])
        con = ledger.connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM events WHERE skill = 'alpha'"
                            ).fetchone()[0]
        finally:
            con.close()
        assert n >= 2      # the detection, plus the delete event
    in_sandbox(check)


def test_delete_of_an_unknown_name_exits_nonzero():
    def check(home):
        sync.sync()
        rc, out = capture(["delete", "nope"])
        assert rc == 1
        assert "no such skill" in out
    in_sandbox(check)


def test_delete_refuses_an_entry_outside_the_store():
    """A tampered index must not be able to point deletion anywhere."""
    def check(home):
        put_skill(home, "alpha")
        outside = home / "elsewhere"
        outside.mkdir()
        (outside / "SKILL.md").write_text("x", encoding="utf-8")
        idx = home / ".claude" / "skillforge" / "index.json"
        idx.write_text(idx.read_text(encoding="utf-8").replace(
            str(home / ".claude" / "skillforge" / "skills" / "alpha" / "SKILL.md"),
            str(outside / "SKILL.md")), encoding="utf-8")
        rc, out = capture(["delete", "alpha"])
        assert rc == 1
        assert "outside" in out
        assert outside.exists()
    in_sandbox(check)


def test_list_shows_both_verdicts():
    def check(home):
        path = put_skill(home, "widget-flush")
        text = (pathlib.Path(path) / "SKILL.md").read_text(encoding="utf-8")
        h = trust.content_hash(text)
        ledger.record_validation("widget-flush", h, "critique", "pass")
        ledger.record_validation("widget-flush", h, "executable", "fail")
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["critique"] == "pass", row
        assert row["executable"] == "fail", row
    in_sandbox(check)


def test_an_unvalidated_skill_shows_a_blank_not_a_pass():
    def check(home):
        put_skill(home, "widget-flush")
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["critique"] == "", row
        assert row["executable"] == "", row
    in_sandbox(check)


def test_delete_of_a_project_skill_does_not_strip_the_shared_index():
    """Re-sync after delete must use the skill's OWN root, not the caller's
    cwd -- else index.json is rebuilt without every other skill belonging
    to that (unvisited) project."""
    def check(home):
        proj = home / "myrepo"
        for name in ("alpha", "kept"):
            d = proj / ".claude" / "skillforge" / "skills" / name
            d.mkdir(parents=True, exist_ok=True)
            text = SKILL % name
            (d / "SKILL.md").write_text(text, encoding="utf-8")
            trust.record(name, text, "self")
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        sync.sync(project_root=str(proj))

        native = proj / ".claude" / "skills" / "skillforge-alpha"
        assert native.exists(), "precondition: alpha must be hot before delete"
        assert any(r["name"] == "kept" for r in library.rows()), \
            "precondition: kept must be indexed before delete"

        old_cwd = os.getcwd()
        os.chdir(str(home))   # cwd != proj -- delete must not depend on it
        try:
            rc, _ = capture(["delete", "alpha"])
        finally:
            os.chdir(old_cwd)

        assert rc == 0
        assert not native.exists()
        assert any(r["name"] == "kept" for r in library.rows()), \
            "a sibling project skill must survive deleting another one"
    in_sandbox(check)



FINDINGS = json.dumps([{
    "criterion": "followable",
    "ok": False,
    "evidence": "1. Do it.",
    "note": "A fresh instance cannot tell what the step refers to.",
}])


def _hash_of(home, name):
    md = home / ".claude" / "skillforge" / "skills" / name / "SKILL.md"
    return trust.content_hash(md.read_text(encoding="utf-8"))


def test_show_prints_the_criterion_and_its_quoted_evidence():
    """A verdict says a skill failed; only the findings say what to fix."""
    def check(home):
        put_skill(home, "alpha")
        ledger.record_validation("alpha", _hash_of(home, "alpha"), "critique",
                                 "fail", detail=FINDINGS)
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "followable" in out, out
        assert "1. Do it." in out, out
        assert "A fresh instance cannot" in out, out
    in_sandbox(check)


def test_show_says_a_skill_is_unvalidated_rather_than_printing_nothing():
    """Silence reads as 'passed'; the whole defect this fixes is invisibility."""
    def check(home):
        put_skill(home, "alpha")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert out.strip(), "printed nothing at all"
        assert "no critique" in out.lower() or "not validated" in out.lower(), out
    in_sandbox(check)


def test_show_hides_findings_written_against_older_text():
    """Findings quote spans; against edited text they would quote a dead file."""
    def check(home):
        put_skill(home, "alpha")
        ledger.record_validation("alpha", _hash_of(home, "alpha"), "critique",
                                 "fail", detail=FINDINGS)
        md = home / ".claude" / "skillforge" / "skills" / "alpha" / "SKILL.md"
        edited = md.read_text(encoding="utf-8") + "\n## Gotchas\n- None.\n"
        md.write_text(edited, encoding="utf-8")
        trust.record("alpha", edited, "self")
        sync.sync()
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "followable" not in out, "stale findings leaked: %s" % out
    in_sandbox(check)


def test_show_rejects_a_name_that_is_not_in_the_index():
    def check(home):
        put_skill(home, "alpha")
        rc, out = capture(["show", "nope"])
        assert rc == 1, rc
    in_sandbox(check)


def test_show_prints_the_usage_truth_table():
    """The measurement is worthless if it lands in a table nobody reads."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt")
        ledger.log_event("detection", "alpha", session="s1", detection="marker")
        ledger.log_event("detection", "alpha", session="s1", detection="fingerprint")
        ledger.log_event("injection", "alpha", session="s2", tier="warm",
                         trigger="prompt")
        ledger.log_event("detection", "alpha", session="s2", detection="fingerprint")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "usage" in out.lower(), out
        assert "compliance miss" in out.lower(), out
    in_sandbox(check)


def test_show_says_a_skill_has_no_usage_data_rather_than_printing_zeros():
    """A missing measurement and a measured zero are opposite facts."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "no usage" in out.lower(), out
    in_sandbox(check)


def test_show_still_works_when_only_a_marker_exists():
    """A hot skill's first signal arrives with no injection row beside it."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        ledger.log_event("detection", "alpha", session="s1", detection="marker")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "no independent signal" in out.lower(), out
    in_sandbox(check)


def test_show_reaches_no_usage_data_past_a_real_save_row():
    """save_skill.py logs a sessionless 'save' row on the real production path
    (see scripts/save_skill.py) -- unlike put_skill's fixture, which writes
    the file directly and logs nothing. That row must not count as a session
    or the "no usage data yet" branch is unreachable in production."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        ledger.log_event("save", "alpha", outcome="saved")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "no usage" in out.lower(), out
    in_sandbox(check)

def test_decisions_reports_empty_library():
    def check(home):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = library.main(["decisions"])
        assert rc == 0
        assert "no decisions recorded" in out.getvalue(), out.getvalue()
    in_sandbox(check)


def test_decisions_prints_actor_verdict_subject_and_reason():
    def check(home):
        ledger.log_decision("system", "rejected", "foo", reason="missing verification")
        ledger.log_decision("human", "approved", "bar")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = library.main(["decisions"])
        assert rc == 0
        text = out.getvalue()
        for want in ("system", "rejected", "foo", "missing verification",
                     "human", "approved", "bar"):
            assert want in text, (want, text)
    in_sandbox(check)


def test_decisions_filters_by_verdict():
    def check(home):
        ledger.log_decision("system", "rejected", "foo")
        ledger.log_decision("human", "approved", "bar")
        out = io.StringIO()
        with redirect_stdout(out):
            library.main(["decisions", "--verdict", "rejected"])
        text = out.getvalue()
        assert "foo" in text and "bar" not in text, text
    in_sandbox(check)


def test_decisions_filters_by_skill():
    def check(home):
        ledger.log_decision("human", "approved", "foo")
        ledger.log_decision("human", "approved", "bar")
        out = io.StringIO()
        with redirect_stdout(out):
            library.main(["decisions", "--skill", "bar"])
        text = out.getvalue()
        assert "bar" in text and "foo" not in text, text
    in_sandbox(check)


def test_decisions_filter_with_no_match_says_so():
    def check(home):
        ledger.log_decision("human", "approved", "foo")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = library.main(["decisions", "--verdict", "discarded"])
        assert rc == 0
        assert "no decisions recorded" in out.getvalue(), out.getvalue()
    in_sandbox(check)


def archived_dirs(home, kind="skills"):
    d = home / ".claude" / "skillforge" / "archive" / kind
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_archive_moves_the_store_dir_instead_of_destroying_it():
    def check(home):
        store = put_skill(home, "alpha")
        text = (store / "SKILL.md").read_text(encoding="utf-8")
        rc, _ = capture(["archive", "alpha"])
        assert rc == 0
        assert not store.exists(), "store dir should be gone"
        names = archived_dirs(home)
        assert len(names) == 1 and names[0].startswith("alpha@"), names
        moved = (home / ".claude/skillforge/archive/skills" / names[0] / "SKILL.md")
        assert moved.read_text(encoding="utf-8") == text, "content must survive"
    in_sandbox(check)


def test_archive_evicts_native_copy_and_trust_entry():
    def check(home):
        put_skill(home, "alpha")
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        sync.sync()
        native = home / ".claude" / "skills" / "skillforge-alpha"
        assert native.exists(), "precondition: skill must be hot before archive"
        capture(["archive", "alpha"])
        assert not native.exists()
        assert "alpha" not in trust.load()
        assert [r["name"] for r in library.rows()] == []
    in_sandbox(check)


def test_archive_preserves_kind_for_antiskills():
    def check(home):
        d = home / ".claude" / "skillforge" / "antiskills" / "trap"
        d.mkdir(parents=True, exist_ok=True)
        text = ("---\nname: trap\nkind: antiskill\n"
                "description: A trap. Do NOT use otherwise.\n"
                "symptoms:\n  - \"BoomError: the widget exploded\"\n---\n\n"
                "## Trap\nDoing it wrong.\n\n## Symptom\nBoom.\n\n"
                "## Cause\nBecause.\n\n## Fix\nDo not.\n")
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        trust.record("trap", text, "self")
        sync.sync()
        rc, _ = capture(["archive", "trap"])
        assert rc == 0
        assert archived_dirs(home, "antiskills"), "antiskill must archive under antiskills/"
        assert not archived_dirs(home, "skills")
    in_sandbox(check)


def test_archive_logs_an_event_and_keeps_history():
    def check(home):
        put_skill(home, "alpha")
        ledger.log_event("detection", "alpha", outcome="success", session="s1",
                         project="/repo/a/.git")
        capture(["archive", "alpha"])
        con = ledger.connect()
        types = [r[0] for r in con.execute(
            "SELECT event_type FROM events WHERE skill='alpha'")]
        con.close()
        assert "archive" in types, types
        assert "detection" in types, "archiving removes the skill, not the evidence"
    in_sandbox(check)


def test_restore_puts_it_back_but_quarantined():
    def check(home):
        store = put_skill(home, "alpha")
        capture(["archive", "alpha"])
        rc, _ = capture(["restore", "alpha"])
        assert rc == 0
        assert (store / "SKILL.md").exists(), "file must be back in the store"
        # Trust is NOT restored: the content hash is the only thing standing
        # between an edited-while-archived file and a trusted skill.
        assert "alpha" not in trust.load()
        assert [r["name"] for r in library.rows()] == [], "quarantined, so unindexed"
        assert archived_dirs(home) == [], "archive entry consumed"
    in_sandbox(check)


def test_restore_refuses_when_a_live_skill_holds_the_name():
    def check(home):
        put_skill(home, "alpha")
        capture(["archive", "alpha"])
        put_skill(home, "alpha")
        rc, out = capture(["restore", "alpha"])
        assert rc == 1, out
        assert archived_dirs(home), "archived copy must survive a refused restore"
    in_sandbox(check)


def test_restore_is_ambiguous_when_a_name_was_archived_twice():
    def check(home):
        put_skill(home, "alpha")
        capture(["archive", "alpha"])
        put_skill(home, "alpha")
        capture(["archive", "alpha"])
        assert len(archived_dirs(home)) == 2, archived_dirs(home)
        rc, out = capture(["restore", "alpha"])
        assert rc == 1, out
        assert "--at" in out, out
        rc, _ = capture(["restore", "alpha", "--at",
                         archived_dirs(home)[0].split("@", 1)[1]])
        assert rc == 0
        assert len(archived_dirs(home)) == 1
    in_sandbox(check)


def test_restore_reports_an_unknown_name():
    def check(home):
        rc, out = capture(["restore", "nope"])
        assert rc == 1
        assert "nope" in out, out
    in_sandbox(check)


def test_archived_lists_what_is_there():
    def check(home):
        rc, out = capture(["archived"])
        assert rc == 0 and "nothing archived" in out, out
        put_skill(home, "alpha")
        capture(["archive", "alpha"])
        rc, out = capture(["archived"])
        assert rc == 0
        assert "alpha" in out and "skill" in out, out
    in_sandbox(check)


def test_delete_is_still_destructive():
    """Today's choice, pinned: archive is additive, delete still means gone."""
    def check(home):
        store = put_skill(home, "alpha")
        capture(["delete", "alpha"])
        assert not store.exists()
        assert archived_dirs(home) == [], "delete must not archive"
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
