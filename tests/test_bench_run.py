"""Tests for the bench harness's Q1 additions. Run: python3 tests/test_bench_run.py"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import run as bench_run
import backfill

DRAFT = """---
name: distilled-thing
kind: antiskill
scope: project
description: >
  A distilled anti-skill.
  Use when: probing.
  Do NOT use when: never.
---
## Trap
"""


def _reset():
    bench_run.SKILL_FROM = None
    bench_run.FORCE_HOT = False
    bench_run.PLUS_SKILL = None


def test_arm_segment_is_empty_for_control_and_plain_treatment():
    _reset()
    assert bench_run.arm_segment("control") == ""
    assert bench_run.arm_segment("treatment") == ""


def test_arm_segment_marks_the_hot_arm():
    _reset()
    bench_run.FORCE_HOT = True
    try:
        assert bench_run.arm_segment("treatment") == "-hot"
        assert bench_run.arm_segment("control") == ""
    finally:
        _reset()


def test_arm_segment_encodes_distiller_and_draw():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn-failure/2/SKILL.md"
    try:
        assert bench_run.arm_segment("treatment") == "-d-learnfailure-2"
    finally:
        _reset()


def test_arm_segment_separates_the_three_treatment_arms():
    """The bug this exists to prevent: every arm passes --arm treatment, so
    without a distinct segment two batches share a clone AND a ledger path
    and the second silently overwrites the first's evidence. It did, once."""
    _reset()
    plain = bench_run.arm_segment("treatment")
    bench_run.FORCE_HOT = True
    hot = bench_run.arm_segment("treatment")
    bench_run.FORCE_HOT = False
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn/1/SKILL.md"
    dist = bench_run.arm_segment("treatment")
    _reset()
    assert len({plain, hot, dist}) == 3, (plain, hot, dist)


def test_skill_src_defaults_to_the_task_and_is_overridden():
    _reset()
    task = {"skill": "matcher-input-traps"}
    assert bench_run.skill_src(task).name == "matcher-input-traps.md"
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn/1/SKILL.md"
    try:
        assert str(bench_run.skill_src(task)) == \
            "/x/bench/distilled/trapA/learn/1/SKILL.md"
    finally:
        _reset()


def test_skill_name_reads_the_frontmatter():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "SKILL.md"
        p.write_text(DRAFT, encoding="utf-8")
        assert bench_run.skill_name(p) == "distilled-thing"


def test_skill_name_is_none_when_absent():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "SKILL.md"
        p.write_text("no frontmatter here\n", encoding="utf-8")
        assert bench_run.skill_name(p) is None


def test_tier_of_reads_the_user_global_index():
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            d = pathlib.Path(tmp) / ".claude" / "skillforge"
            d.mkdir(parents=True)
            (d / "index.json").write_text(json.dumps(
                {"entries": [{"name": "distilled-thing", "tier": "warm"}]}),
                encoding="utf-8")
            assert bench_run.tier_of("distilled-thing") == "warm"
            assert bench_run.tier_of("absent") is None
        finally:
            os.environ["HOME"] = old


def test_tier_of_survives_a_missing_index():
    old = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            assert bench_run.tier_of("anything") is None
        finally:
            os.environ["HOME"] = old


def test_distilled_parts_is_none_without_skill_from():
    _reset()
    assert bench_run.distilled_parts() is None


def test_distilled_parts_reads_a_well_formed_archive_path():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn-failure/2/SKILL.md"
    try:
        assert bench_run.distilled_parts() == ("learn-failure", "2")
    finally:
        _reset()


def test_distilled_parts_rejects_a_relative_path():
    """It used to resolve against cwd and return plausible ancestor names,
    which went straight into results.jsonl as `distiller` and `draw`."""
    _reset()
    bench_run.SKILL_FROM = "SKILL.md"
    try:
        raised = False
        try:
            bench_run.distilled_parts()
        except ValueError:
            raised = True
        assert raised, "a relative --skill-from must be refused, not resolved"
    finally:
        _reset()


def test_distilled_parts_rejects_a_short_path():
    _reset()
    bench_run.SKILL_FROM = "/SKILL.md"
    try:
        raised = False
        try:
            bench_run.distilled_parts()
        except ValueError:
            raised = True
        assert raised, "a path too short to carry the layout must be refused"
    finally:
        _reset()


def test_distilled_parts_rejects_a_wrong_layout():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/elsewhere/trapA/learn/1/SKILL.md"
    try:
        raised = False
        try:
            bench_run.distilled_parts()
        except ValueError:
            raised = True
        assert raised, "the archive root must be named distilled/"
    finally:
        _reset()


def test_source_keys_are_all_null_for_control():
    _reset()
    keys = bench_run.source_keys("control", {"skill": "x"}, None)
    assert set(keys) == {"skill_source", "distiller", "draw", "skill_path",
                         "tier_at_install"}, keys
    assert all(v is None for v in keys.values()), keys


def test_source_keys_label_a_hand_authored_treatment_run():
    _reset()
    keys = bench_run.source_keys("treatment", {"skill": "matcher-input-traps"}, "warm")
    assert keys["skill_source"] == "authored"
    assert keys["distiller"] is None and keys["draw"] is None
    assert keys["skill_path"].endswith("matcher-input-traps.md")
    assert keys["tier_at_install"] == "warm"


def test_source_keys_label_a_distilled_treatment_run():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn-failure/3/SKILL.md"
    try:
        keys = bench_run.source_keys("treatment", {"skill": "unused"}, "warm")
        assert keys["skill_source"] == "distilled"
        assert keys["distiller"] == "learn-failure"
        assert keys["draw"] == 3 and isinstance(keys["draw"], int)
        assert keys["skill_path"] == "/x/bench/distilled/trapA/learn-failure/3/SKILL.md"
    finally:
        _reset()


def test_backfill_labels_treatment_and_control_rows():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "r.jsonl"
        p.write_text(
            json.dumps({"task": "t", "arm": "treatment", "resolved": True}) + "\n" +
            json.dumps({"task": "t", "arm": "control", "resolved": False}) + "\n",
            encoding="utf-8")
        assert backfill.backfill(p) == 2
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["skill_source"] == "authored"
        assert rows[1]["skill_source"] is None


def test_backfill_is_idempotent_and_leaves_new_rows_alone():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "r.jsonl"
        p.write_text(
            json.dumps({"arm": "treatment", "skill_source": "distilled"}) + "\n",
            encoding="utf-8")
        assert backfill.backfill(p) == 0
        assert backfill.backfill(p) == 0
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["skill_source"] == "distilled"


def test_backfill_preserves_every_other_field():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "r.jsonl"
        original = {"task": "t", "arm": "treatment", "per_test": {"a": True},
                    "secs": 1.5, "ts": "2026-08-11T00:00:00"}
        p.write_text(json.dumps(original) + "\n", encoding="utf-8")
        backfill.backfill(p)
        row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
        for k, v in original.items():
            assert row[k] == v, (k, row.get(k), v)



def test_skill_src_is_absolute_even_when_skill_from_is_relative():
    """install_skill runs save_skill.py with cwd set to the clone, so a
    relative path resolves against the clone and is not there. Twelve probes
    died on this."""
    _reset()
    bench_run.SKILL_FROM = "bench/distilled/A/learn-failure/1/SKILL.md"
    try:
        got = bench_run.skill_src({"skill": "unused"})
        assert got.is_absolute(), got
        assert str(got).endswith("bench/distilled/A/learn-failure/1/SKILL.md"), got
    finally:
        _reset()


def test_skill_path_recorded_on_the_row_is_absolute():
    _reset()
    bench_run.SKILL_FROM = "bench/distilled/A/learn-failure/1/SKILL.md"
    try:
        keys = bench_run.source_keys("treatment", {"skill": "unused"}, "warm")
        assert pathlib.Path(keys["skill_path"]).is_absolute(), keys["skill_path"]
    finally:
        _reset()


def test_plus_skill_gets_its_own_clone_segment():
    """E6's two arms both pass --arm treatment. Without a distinct segment they
    share a clone AND a per-run ledger, which is how E5 lost a batch."""
    _reset()
    plain = bench_run.arm_segment("treatment")
    bench_run.PLUS_SKILL = "bench/skills/arrow-tzinfo-string-trap.md"
    try:
        assert bench_run.arm_segment("treatment") == "-plus"
        assert bench_run.arm_segment("treatment") != plain
        assert bench_run.arm_segment("control") == ""
    finally:
        _reset()


def test_plus_skill_composes_with_skill_from():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn/1/SKILL.md"
    bench_run.PLUS_SKILL = "bench/skills/arrow-tzinfo-string-trap.md"
    try:
        assert bench_run.arm_segment("treatment") == "-d-learn-1-plus"
    finally:
        _reset()


def test_extra_skill_names_reads_the_frontmatter():
    _reset()
    assert bench_run.extra_skill_names() == []
    bench_run.PLUS_SKILL = "bench/skills/arrow-tzinfo-string-trap.md"
    try:
        assert bench_run.extra_skill_names() == ["arrow-tzinfo-string-trap"]
    finally:
        _reset()

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
