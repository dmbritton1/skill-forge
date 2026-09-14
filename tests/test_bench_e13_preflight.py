"""Tests for bench/e13_preflight.py. Run: python3 tests/test_bench_e13_preflight.py"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import e13_preflight as pf

PARENT = '''import os


def unchanged(x):
    return x


def fixed(ev, text):
    return ev in text
'''

FIX = '''import os
import re


def unchanged(x):
    return x


def _unwrapped(s):
    return re.sub(r"\\s+", " ", s).strip()


def fixed(ev, text):
    return _unwrapped(ev) in _unwrapped(text)
'''


def test_changed_definitions_names_new_and_edited_only():
    assert pf.changed_definitions(PARENT, FIX) == ["_unwrapped", "fixed"]


def test_transplant_carries_the_fix_its_helper_and_its_import():
    out, names = pf.transplant(PARENT, FIX)
    assert names == ["_unwrapped", "fixed"]
    assert "import re\n" in out
    assert out.index("def _unwrapped") < out.index("def fixed"), "helper goes before its caller"
    ns = {}
    exec(compile(out, "m.py", "exec"), ns)
    assert ns["fixed"]("a  b", "x a\n b y") is True
    assert ns["unchanged"](7) == 7


def test_transplant_of_identical_sources_changes_nothing():
    out, names = pf.transplant(PARENT, PARENT)
    assert names == [] and out == PARENT


def test_test_names_and_parse_results():
    assert pf.test_names("def test_a():\n    pass\n\ndef helper():\n    pass\n") == {"test_a"}
    got = pf.parse_results("PASS test_a\nFAIL test_b: AssertionError()\nnoise\n")
    assert got == {"test_a": True, "test_b": False}


def test_assess_grades_what_the_stub_breaks_and_the_fix_repairs():
    stub = {"t_old": False, "t_trap": False, "t_unrelated": True}
    original = {"t_old": True, "t_trap": False, "t_unrelated": True}
    fix = {"t_old": True, "t_trap": True, "t_unrelated": True}
    graded, problems = pf.assess(stub, original, fix, fix_added={"t_trap"})
    assert graded == ["t_old", "t_trap"]
    assert problems == []


def test_assess_rejects_tests_that_cannot_catch_the_bug():
    stub = {"t_trap": False}
    original = {"t_trap": True}
    fix = {"t_trap": True}
    _, problems = pf.assess(stub, original, fix, fix_added={"t_trap"})
    assert any("historical bug" in p for p in problems), problems


def test_assess_rejects_a_fix_added_test_the_fix_cannot_pass():
    """Without this, a trap test that needs something the fix created would drop
    out of the graded set silently, and the task would grade everything but the
    trap."""
    stub = {"t_old": False, "t_trap": False}
    original = {"t_old": True, "t_trap": False}
    fix = {"t_old": True, "t_trap": False}
    _, problems = pf.assess(stub, original, fix, fix_added={"t_trap"})
    assert any("do not pass with the fix transplanted" in p for p in problems), problems


def test_assess_rejects_an_original_that_breaks_older_graded_tests():
    stub = {"t_old": False, "t_trap": False}
    original = {"t_old": False, "t_trap": False}
    fix = {"t_old": True, "t_trap": True}
    _, problems = pf.assess(stub, original, fix, fix_added={"t_trap"})
    assert any("did not add" in p for p in problems), problems


def test_assess_reports_a_changed_docstring():
    stub = {"t_trap": False}
    original = {"t_trap": False}
    fix = {"t_trap": True}
    _, problems = pf.assess(stub, original, fix, fix_added={"t_trap"}, docstring_ok=False)
    assert any("docstring" in p for p in problems), problems


def test_the_author_prompt_is_the_existing_template_verbatim():
    """The only proof the template is reused rather than paraphrased: rebuild the
    fingerprint task's prompt and compare it with the one in tasks.json."""
    tasks = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    fp = next(t for t in tasks if t["id"] == "sf-author-fingerprint-preexisting")
    got = pf.author_prompt("scripts/retrieve.py", ["fingerprint_preexisting(fingerprints, cwd)"],
                           "tests/test_retrieve.py")
    assert got == fp["prompt"]


def test_the_two_function_prompt_speaks_in_the_plural():
    got = pf.author_prompt("scripts/save_skill.py",
                            ["store_dir(scope, kind, name, project_root)",
                             "native_dir(scope, name, project_root)"], "tests/test_save_skill.py")
    assert "has functions `store_dir(scope, kind, name, project_root)` and `native_dir(scope, name, project_root)`" in got
    assert "whose bodies raise NotImplementedError" in got and "their docstrings" in got


def test_signatures_come_from_the_source():
    src = "def verdict_from(findings, text):\n    pass\n"
    assert pf.signatures(src, ["verdict_from"]) == ["verdict_from(findings, text)"]


def test_task_entry_keeps_root_unexpanded_and_picks_the_grading_command():
    graded = ["test_a", "test_b"]
    c = pf.task_entry("C", pf.CANDIDATES["C"], graded, ["verdict_from(findings, text)"])
    d = pf.task_entry("D", pf.CANDIDATES["D"], graded, ["transcript_slice(transcript_path, since, until)"])
    assert c["test_cmd"] == "python3 tests/test_validate.py"
    assert d["test_cmd"] == "python3 {root}/bench/run_named_tests.py tests/test_draft.py test_a test_b"
    for e in (c, d):
        assert e["mode"] == "author" and e["repo"] == "{root}"
        assert e["stub_cmd"].startswith("python3 {root}/bench/stubs/")
        assert e["fail_to_pass"] == graded and e["skill"] is None
        assert "python3 tests/" in e["prompt"], "the model is told the repo's own test command"


def test_upsert_replaces_by_id_and_appends_otherwise():
    cfg = {"tasks": [{"id": "a", "v": 1}, {"id": "b", "v": 1}]}
    pf.upsert(cfg, {"id": "a", "v": 2})
    pf.upsert(cfg, {"id": "c", "v": 1})
    assert cfg["tasks"] == [{"id": "a", "v": 2}, {"id": "b", "v": 1}, {"id": "c", "v": 1}]


def test_docstrings_match_compares_raw_docstrings_of_named_functions():
    parent = 'def f(a):\n    """Exact  text.\n\n    More.\n    """\n    return a\n'
    same = 'def f(a):\n    """Exact  text.\n\n    More.\n    """\n    raise NotImplementedError("implement me")\n'
    edited = 'def f(a):\n    """Exact text.\n\n    More.\n    """\n    raise NotImplementedError("implement me")\n'
    assert pf.docstrings_match(same, parent, ["f"]) is True
    assert pf.docstrings_match(edited, parent, ["f"]) is False, "a collapsed double space is a change"


def test_repair_prompt_is_the_existing_repair_template_verbatim():
    tasks = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    ref = next(t for t in tasks if t["id"] == "sf-truncation-reports-absent")
    assert pf.repair_prompt("tests/test_retrieve.py") == ref["prompt"]


def test_repair_graded_is_the_fix_added_tests_the_original_fails():
    original = {"t_trap": False, "t_other_added": True, "t_old": False}
    assert pf.repair_graded(original, {"t_trap", "t_other_added", "t_missing"}) == ["t_trap"]


def test_repair_entry_is_a_repair_task_on_the_same_fix():
    e = pf.repair_entry("C", pf.CANDIDATES["C"], ["t_trap"])
    assert e["id"] == "sf-repair-verdict-from" and e["mode"] == "repair"
    assert e["repo"] == "{root}" and e["fix_commit"] == "c0d7d88"
    assert e["test_cmd"] == "python3 tests/test_validate.py"
    assert e["fail_to_pass"] == ["t_trap"] and e["skill"] is None
    assert "stub_cmd" not in e
    assert e["prompt"] == pf.repair_prompt("tests/test_validate.py")


def test_trap_c_is_registered_for_distillation_and_probing():
    import distill
    import dryrun
    tasks = {t["id"]: t for t in json.loads(
        (ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
    repair, author = tasks[distill.TRAPS["C"]], tasks[dryrun.PROBES["C"]]
    assert repair["mode"] == "repair" and author["mode"] == "author"
    assert repair["fix_commit"] == author["fix_commit"] == "c0d7d88"
    assert repair["fail_to_pass"] == ["test_a_rewrapped_quote_still_counts_as_evidence"]


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
