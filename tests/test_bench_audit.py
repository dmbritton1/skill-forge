"""Tests for bench/audit.py. Run: python3 tests/test_bench_audit.py"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import audit

DENIED = "cat: x: Operation not permitted"


class Env:
    def __init__(self, tmp):
        t = pathlib.Path(os.path.realpath(tmp))
        self.tmp = t
        self.work = t / "work"
        self.dest = self.work / "clone-1"
        self.plugin = self.work / "plugin-abc"
        self.dev = t / "dev"
        self.projects = t / "projects"

    def transcript(self, *calls):
        """calls: (tool name, input dict, result text)."""
        p = self.tmp / "t.jsonl"
        lines = [json.dumps({"type": "user", "message": {"content": "the prompt"}})]
        for i, (name, inp, result) in enumerate(calls):
            lines.append(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t%d" % i, "name": name, "input": inp}]}}))
            lines.append(json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t%d" % i, "content": result,
                 "is_error": False}]}}))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def run(self, path):
        return audit.audit_transcript(path, self.dest, self.plugin, self.work, self.dev,
                                      projects=self.projects)


def with_env(fn):
    with tempfile.TemporaryDirectory() as tmp:
        fn(Env(tmp))


def test_reads_inside_the_clone_are_clean():
    def body(e):
        res = e.run(e.transcript(("Read", {"file_path": str(e.dest / "scripts" / "validate.py")}, "ok"),
                                 ("Bash", {"command": "grep -n x scripts/validate.py"}, "ok")))
        assert res == {"verdict": "clean", "hits": [], "leaked": []}, res
    with_env(body)


def test_running_a_plugin_script_is_clean():
    def body(e):
        cmd = "python3 %s/scripts/save_skill.py draft.md --scope project" % e.plugin
        assert e.run(e.transcript(("Bash", {"command": cmd}, "saved")))["verdict"] == "clean"
    with_env(body)


def test_reading_a_plugin_script_as_text_is_a_leak():
    def body(e):
        target = e.plugin / "scripts" / "validate.py"
        res = e.run(e.transcript(("Bash", {"command": "cat %s | head" % target}, "def verdict_from")))
        assert res["verdict"] == "leak"
        assert res["leaked"] == [audit.display(str(target))]
        assert res["hits"] == [{"tool": "Bash", "path": audit.display(str(target)), "label": "leak"}]
    with_env(body)


def test_grep_on_the_plugin_scripts_dir_is_a_leak():
    def body(e):
        res = e.run(e.transcript(("Grep", {"pattern": "def", "path": str(e.plugin / "scripts")}, "x")))
        assert res["verdict"] == "leak"
    with_env(body)


def test_reading_the_checkout_or_another_clone_or_a_transcript_is_a_leak():
    def body(e):
        for p in (e.dev / "skill-forge" / "bench" / "tasks.json",
                  e.work / "cache-sf-author-verdict-from" / "x.py",
                  e.projects / "-other" / "a.jsonl"):
            assert e.run(e.transcript(("Read", {"file_path": str(p)}, "x")))["verdict"] == "leak", p
    with_env(body)


def test_a_denied_read_is_blocked_not_a_leak():
    def body(e):
        cmd = "cat %s" % (e.dev / "skill-forge" / "bench" / "tasks.json")
        res = e.run(e.transcript(("Bash", {"command": cmd}, DENIED)))
        assert res["verdict"] == "clean" and res["leaked"] == []
        assert [h["label"] for h in res["hits"]] == ["blocked"]
    with_env(body)


def test_a_denial_does_not_hide_a_plugin_script_read_in_the_same_command():
    def body(e):
        cmd = "cat %s/scripts/validate.py %s/x" % (e.plugin, e.dev)
        res = e.run(e.transcript(("Bash", {"command": cmd}, DENIED)))
        assert res["verdict"] == "leak"
    with_env(body)


def test_tmp_spelling_is_normalized():
    def body(e):
        # /tmp/... and /private/tmp/... are one place on macOS.
        dest = pathlib.Path("/private/tmp/sfb-audit-test/clone-1")
        res = audit.audit_transcript(
            e.transcript(("Read", {"file_path": "/tmp/sfb-audit-test/other/x"}, "x")),
            dest, "/private/tmp/sfb-audit-test/plugin", "/private/tmp/sfb-audit-test", e.dev,
            projects=e.projects)
        assert res["verdict"] == "leak"
    with_env(body)


def test_hits_are_capped_but_leaked_is_complete():
    def body(e):
        calls = [("Read", {"file_path": str(e.work / ("other%d" % i) / "x")}, "x") for i in range(12)]
        res = e.run(e.transcript(*calls))
        assert len(res["hits"]) == 10 and len(res["leaked"]) == 12
    with_env(body)


def test_missing_and_unparseable_transcripts_are_missing():
    def body(e):
        assert e.run(None)["verdict"] == "missing"
        assert e.run(e.tmp / "nope.jsonl")["verdict"] == "missing"
        bad = e.tmp / "bad.jsonl"
        bad.write_text("{not json\n", encoding="utf-8")
        assert e.run(bad) == {"verdict": "missing", "hits": [], "leaked": []}
    with_env(body)


def test_find_transcript_globs_by_session_id():
    def body(e):
        sid = "0b7e6f0a-1111-4222-8333-944455556666"
        f = e.projects / "-private-tmp-skillforge-bench-x" / (sid + ".jsonl")
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        assert audit.find_transcript(sid, e.projects) == f
        assert audit.find_transcript("no-such-id", e.projects) is None
        assert audit.find_transcript("", e.projects) is None
    with_env(body)


def test_counts():
    assert audit.counts({"resolved": True}) is True
    assert audit.counts({"sandbox": True, "audit": {"verdict": "clean"}}) is True
    assert audit.counts({"sandbox": True, "audit": {"verdict": "leak"}}) is False
    assert audit.counts({"sandbox": True, "audit": {"verdict": "missing"}}) is False
    assert audit.counts({"sandbox": False, "audit": {"verdict": "clean"}}) is False


def test_tainted_for_matches_only_the_traps_fixed_file():
    def body(e):
        target = e.plugin / "scripts" / "validate.py"
        res = e.run(e.transcript(("Read", {"file_path": str(target)}, "x")))
        assert audit.tainted_for(res, e.plugin, "scripts/validate.py") is True
        assert audit.tainted_for(res, e.plugin, "scripts/save_skill.py") is False
        assert audit.tainted_for(res, e.plugin, None) is False
    with_env(body)


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
