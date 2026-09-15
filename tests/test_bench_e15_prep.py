"""Tests for bench/e15_prep.py. Run from the repo root: python3 tests/test_bench_e15_prep.py"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e15_prep as ep

DRAFT = """---
name: x
kind: skill
description: >
  %s
  Use when: %s.
  Do NOT use when: never.
---

## Procedure
%s
"""


def test_compliance_flags_each_rule_independently():
    clean = DRAFT % ("A gate such as validate.verdict_from rejects quotes.", "writing it",
                     "1. Compare both sides after collapsing whitespace.")
    assert ep.compliance(clean) == {"names_test": False, "find_step": False, "fn_first": True}
    assert ep.compliance(clean + "\nSee test_a_thing.\n")["names_test"] is True
    assert ep.compliance(clean + "\nRun tests/test_validate.py.\n")["names_test"] is True
    found = DRAFT % ("A gate such as validate.verdict_from rejects quotes.", "x",
                     "1. **Find** the substring check.")
    assert ep.compliance(found)["find_step"] is True
    late = DRAFT % ("A strict quote gate rejects re-wrapped quotes.", "editing validate.verdict_from",
                    "1. Collapse whitespace.")
    assert ep.compliance(late)["fn_first"] is False


def test_compliance_of_the_first_e13_baseline_draft_is_as_the_e14_write_up_describes():
    text = (ROOT / ep.BASELINE[0]).read_text(encoding="utf-8")
    assert ep.compliance(text) == {"names_test": True, "find_step": True, "fn_first": False}


def test_counted_variant_drafts_keep_saved_untainted_drafts_in_draw_order():
    with tempfile.TemporaryDirectory() as tmp:
        seg = pathlib.Path(tmp)

        def draw(n, outcome="saved", draft=True, tainted=False):
            d = seg / str(n)
            d.mkdir()
            (d / "meta.json").write_text(json.dumps({"outcome": outcome, "tainted": tainted}),
                                         encoding="utf-8")
            if draft:
                (d / "SKILL.md").write_text("x\n", encoding="utf-8")
        draw(10)
        draw(2)
        draw(3, tainted=True)
        draw(4, outcome="aborted", draft=False)
        draw(5, draft=False)
        assert [p.parent.name for p in ep.counted_variant_drafts(seg)] == ["2", "10"]


def test_allowed_needs_three_delivered_variants_and_all_three_baselines():
    v = lambda d: {"group": "variant", "delivered": d}
    b = lambda d: {"group": "baseline", "delivered": d}
    assert ep.allowed([v(True)] * 3 + [b(True)] * 3) is True
    assert ep.allowed([v(True)] * 2 + [v(False)] * 4 + [b(True)] * 3) is False
    assert ep.allowed([v(True)] * 6 + [b(True)] * 2 + [b(False)]) is False


def test_stale_names_changed_or_missing_drafts_by_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "a.md").write_text("one\n", encoding="utf-8")
        record = {"drafts": [{"path": "a.md", "sha256": ep.sha256(root / "a.md")},
                             {"path": "gone.md", "sha256": "0" * 64}]}
        assert ep.stale(record, root) == ["gone.md"]
        (root / "a.md").write_text("two\n", encoding="utf-8")
        assert ep.stale(record, root) == ["a.md", "gone.md"]


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
