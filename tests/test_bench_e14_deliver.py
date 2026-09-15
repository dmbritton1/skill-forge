"""Tests for bench/e14_deliver.py. Run from the repo root: python3 tests/test_bench_e14_deliver.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e14_deliver as ed

HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                      capture_output=True, text=True, check=True).stdout.strip()


def _rows(delivered=(True, True, True, True)):
    return [{"cell": c, "delivered": d} for c, d in zip(("sf", "sw", "af", "aw"), delivered)]


def test_the_gate_needs_all_four_delivered():
    assert ed.gate(_rows()) is True
    assert ed.gate(_rows((True, False, True, True))) is False
    assert ed.gate(_rows()[:3]) is False


def test_the_gate_needs_exactly_the_four_cells():
    rows = [{"cell": "sf", "delivered": True} for _ in range(4)]
    assert ed.gate(rows) is False


def test_draft_paths_are_the_committed_drafts():
    for c in ("sf", "sw", "af", "aw"):
        assert ed.draft_path(c).is_file(), c


def test_stale_names_a_draft_changed_since_it_was_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "a.md").write_text("one\n", encoding="utf-8")
        (root / "b.md").write_text("two\n", encoding="utf-8")
        record = {"drafts": [{"cell": "sf", "path": "a.md", "sha256": ed.sha256(root / "a.md")},
                             {"cell": "sw", "path": "b.md", "sha256": ed.sha256(root / "b.md")}]}
        assert ed.stale(record, root) == []
        (root / "b.md").write_text("changed\n", encoding="utf-8")
        assert ed.stale(record, root) == ["sw"]
        (root / "a.md").unlink()
        assert ed.stale(record, root) == ["sf", "sw"]


def test_drifted_is_false_for_a_commit_with_no_scripts_hooks_changes_since():
    assert ed.drifted(HEAD, ROOT) is False
    record = json.loads(ed.RECORD.read_text(encoding="utf-8"))
    assert ed.drifted(record["commit"], ROOT) is False


def test_drifted_is_true_for_a_commit_that_differs_under_scripts():
    # 06885c0 is known to differ from HEAD in scripts/retrieve.py.
    assert ed.drifted("06885c0", ROOT) is True


def test_drifted_is_true_for_a_nonsense_ref():
    assert ed.drifted("0" * 40, ROOT) is True


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
