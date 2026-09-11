"""Extraction of bench clones into bench/authored/, batch-labelled.
Run: python3 tests/test_bench_extract.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import extract

TASKS = ["sf-author-response-text", "sf-author-response-text-transfer",
         "sf-author-fingerprint-preexisting"]


def test_task_is_the_longest_matching_id_not_the_first():
    """`-transfer` shares a prefix with its base task. Taking the first match
    would file every transfer artifact under the base task, and suite_for()
    would then grade it with a suite written for a different contract."""
    assert extract.task_of("sf-author-response-text-transfer-treatment-1",
                           TASKS) == "sf-author-response-text-transfer"
    assert extract.task_of("sf-author-response-text-control-2",
                           TASKS) == "sf-author-response-text"


def test_an_unknown_clone_has_no_task():
    assert extract.task_of("something-else-1", TASKS) is None


def test_arm_and_run_come_off_the_name():
    p = extract.parts_of("sf-author-response-text-control-2", TASKS)
    assert p == {"task": "sf-author-response-text", "arm": "control",
                 "segment": "", "run": 2}, p


def test_a_distillation_clone_is_unplaceable_not_mis_parsed():
    """`<trap-task>-distill-learn-1` starts with a real task id, so a naive
    prefix match claims it, calls it a treatment arm and derives the segment
    "earn" by slicing "distill-learn" at len("treatment"). The existing
    manifest records these as task None -- they author nothing and regrade
    skips them. Refusing to place them keeps that true."""
    assert extract.parts_of(
        "sf-author-response-text-distill-learn-1", TASKS) is None
    assert extract.parts_of(
        "sf-author-response-text-distill-learn-failure-2", TASKS) is None


def test_the_segment_survives_the_parse():
    """The segment is what tells the batches apart -- `-d-learnnogate-3` is an
    E7 bypass draft and `-d-learn-1` is a Q1 accepted one."""
    p = extract.parts_of(
        "sf-author-response-text-treatment-d-learnnogate-3-2", TASKS)
    assert p["segment"] == "-d-learnnogate-3", p
    assert p["arm"] == "treatment" and p["run"] == 2, p


def test_the_batch_label_prefixes_the_diff_filename():
    """E7 re-runs the control arm, and prepare() reuses the clone path, so the
    clone NAME is identical to the one Q1's control diff was extracted from.
    Without the prefix the new extraction silently overwrites that evidence.
    """
    assert extract.diff_name("sf-author-response-text-control-1", "e7") == \
        "e7-sf-author-response-text-control-1.diff"
    assert extract.diff_name("sf-author-response-text-control-1", None) == \
        "sf-author-response-text-control-1.diff"


def test_an_already_extracted_clone_is_not_duplicated():
    """Re-running extraction must be a no-op, not a second row. The manifest
    is joined against, so a duplicate entry double-counts a cell."""
    existing = [{"clone": "c1", "batch": "e7"}, {"clone": "c1"}]
    assert extract.already(existing, "c1", "e7") is True
    assert extract.already(existing, "c1", None) is True
    assert extract.already(existing, "c1", "e8") is False
    assert extract.already(existing, "c2", "e7") is False


def test_writing_appends_and_never_rewrites_prior_entries():
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        prior = [{"clone": "old", "diff": "old.diff"}]
        (d / "manifest.json").write_text(json.dumps(prior), encoding="utf-8")
        extract.write_manifest(d, prior + [{"clone": "new", "batch": "e7"}])
        got = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        assert got[0] == prior[0], got
        assert got[1]["clone"] == "new", got


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
