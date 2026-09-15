"""Tests for the bench harness's Q1 additions. Run: python3 tests/test_bench_run.py"""
import json
import os
import pathlib
import subprocess
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
    bench_run.INJECT_BUDGET = None


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


def test_authored_skill_from_must_also_be_absolute():
    """The absolute-path rule is not a distilled-tree rule. install_skill
    shells save_skill.py with cwd set to the throwaway clone, so a relative
    authored path resolves against the clone and is not there -- the same way
    twelve Q1 probes died before any session started."""
    _reset()
    bench_run.SKILL_FROM = "bench/skills/arrow-tzinfo-string-trap.md"
    try:
        try:
            bench_run.distilled_parts()
        except ValueError:
            pass
        else:
            raise AssertionError("a relative authored --skill-from must be refused")
    finally:
        _reset()


def test_arm_segment_encodes_an_authored_skill_by_its_stem():
    """E12 needs a hand-written skill from bench/skills/ as an arm. The bench
    has two legitimate skill sources; --skill-from only understood the
    distilled tree, so an authored path raised and the arm could not run."""
    _reset()
    bench_run.SKILL_FROM = "/x/bench/skills/arrow-tzinfo-string-trap.md"
    try:
        assert bench_run.distilled_parts() is None
        assert bench_run.arm_segment("treatment") == "-s-arrowtzinfostringtrap"
        assert bench_run.arm_segment("control") == ""
    finally:
        _reset()


def test_arm_segment_separates_authored_arms_from_each_other():
    """Two authored arms in one batch must not share a clone path -- that is
    how E5 lost a batch."""
    _reset()
    try:
        bench_run.SKILL_FROM = "/x/bench/skills/arrow-tzinfo-string-trap.md"
        irrelevant = bench_run.arm_segment("treatment")
        bench_run.SKILL_FROM = "/x/bench/skills/serialization-corrupts-matching.md"
        relevant = bench_run.arm_segment("treatment")
        assert irrelevant != relevant
        assert "" not in (irrelevant, relevant)
    finally:
        _reset()


def test_a_malformed_distilled_path_still_raises():
    """The relaxation must stay narrow. A mistyped path inside a distilled
    tree is a typo, not an authored skill: turning it into a silent "authored"
    row is exactly the bogus attribution distilled_parts() exists to stop."""
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/A/learn-failure/SKILL.md"
    try:
        try:
            bench_run.distilled_parts()
        except ValueError:
            pass
        else:
            raise AssertionError("a malformed distilled path must still raise")
    finally:
        _reset()


def test_source_keys_calls_an_authored_skill_authored():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/skills/arrow-tzinfo-string-trap.md"
    try:
        keys = bench_run.source_keys("treatment", {"skill": "unused"}, "warm")
        assert keys["skill_source"] == "authored"
        assert keys["distiller"] is None and keys["draw"] is None
        assert keys["skill_path"].endswith("arrow-tzinfo-string-trap.md")
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


def test_arm_segment_records_the_injection_budget():
    """E10 runs two budgets in one batch. Without a segment for it, the
    2000-token arm shares a clone AND a ledger path with the 1200 one, and
    the second run overwrites the first one's evidence."""
    _reset()
    bench_run.INJECT_BUDGET = 2000
    try:
        assert bench_run.arm_segment("treatment") == "-b2000"
        assert bench_run.arm_segment("control") == ""
        bench_run.PLUS_SKILL = ["/x/bench/distilled/trapB/consolidated/1/SKILL.md"]
        assert bench_run.arm_segment("treatment") == "-plus-b2000"
        bench_run.PLUS_SKILL = None
        bench_run.SKILL_FROM = "/x/bench/distilled/A/learn-failure/1/SKILL.md"
        assert bench_run.arm_segment("treatment") == "-d-learnfailure-1-b2000"
    finally:
        _reset()


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


def test_session_tail_is_recorded_only_when_the_session_failed():
    """E12's batch hit the session limit and recorded 13 rows of
    `session_ok: false` with the reason discarded -- run_session captured the
    CLI's tail and one() dropped it, so diagnosing a postponed batch cost a
    probe session to learn what the batch already knew."""
    ok = bench_run.session_keys({"ok": True, "secs": 54.0, "tail": "final message"})
    assert ok["session_ok"] is True
    assert ok["secs"] == 54.0
    assert ok["session_tail"] is None, "a successful session's tail is not diagnostic"

    bad = bench_run.session_keys(
        {"ok": False, "secs": 2.0, "tail": "You've hit your session limit"})
    assert bad["session_ok"] is False
    assert "session limit" in bad["session_tail"]


def test_session_tail_is_scrubbed_of_the_home_path():
    """results.jsonl is published, and the tail can quote --plugin-dir, which
    is a path under the operator's home."""
    import os
    home = os.path.expanduser("~")
    got = bench_run.session_keys(
        {"ok": False, "secs": 1.0,
         "tail": "error: --plugin-dir %s/Developer/x not found" % home})
    assert home not in got["session_tail"], got["session_tail"]
    assert "~/Developer/x" in got["session_tail"], got["session_tail"]


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


def test_skill_path_on_the_row_is_written_home_relative():
    """The recorded value is scrubbed at the source, not after each batch.

    skill_src() must stay ABSOLUTE -- install_skill shells save_skill.py with
    cwd set to the throwaway clone. But nothing requires the value RECORDED on
    the row to be absolute, and leaving it so put the operator's home path back
    into published evidence three times (2026-09-10, e50b61c, and again today).
    """
    _reset()
    import os
    home = os.path.expanduser("~")
    bench_run.SKILL_FROM = home + "/somewhere/bench/skills/a-skill.md"
    try:
        keys = bench_run.source_keys("treatment", {"skill": "unused"}, "warm")
        assert keys["skill_path"].startswith("~/"), keys["skill_path"]
        assert home not in keys["skill_path"], keys["skill_path"]
        # the installed path itself is still absolute
        assert pathlib.Path(str(bench_run.skill_src({"skill": "unused"}))).is_absolute()
    finally:
        _reset()


def test_skill_path_recorded_on_the_row_is_unambiguous():
    """Was `..._is_absolute`. The guard is against a CWD-RELATIVE value, which
    skill_src() calls "worthless provenance once the cwd that gave it meaning
    is gone" -- absolute was simply the form that achieved that. A `~/` path is
    equally unambiguous and keeps the operator's home out of published
    evidence, so the assertion now names the intent rather than the old
    mechanism. Still resolved, never passed through.
    """
    _reset()
    bench_run.SKILL_FROM = "bench/distilled/A/learn-failure/1/SKILL.md"
    try:
        keys = bench_run.source_keys("treatment", {"skill": "unused"}, "warm")
        got = keys["skill_path"]
        assert got.startswith(("/", "~/")), got
        assert got != bench_run.SKILL_FROM, "the path was recorded unresolved"
        assert got.endswith("bench/distilled/A/learn-failure/1/SKILL.md"), got
    finally:
        _reset()


def test_plus_skill_gets_its_own_clone_segment():
    """E6's two arms both pass --arm treatment. Without a distinct segment they
    share a clone AND a per-run ledger, which is how E5 lost a batch."""
    _reset()
    plain = bench_run.arm_segment("treatment")
    bench_run.PLUS_SKILL = ["bench/skills/arrow-tzinfo-string-trap.md"]
    try:
        assert bench_run.arm_segment("treatment") == "-plus"
        assert bench_run.arm_segment("treatment") != plain
        assert bench_run.arm_segment("control") == ""
    finally:
        _reset()


def test_plus_skill_composes_with_skill_from():
    _reset()
    bench_run.SKILL_FROM = "/x/bench/distilled/trapA/learn/1/SKILL.md"
    bench_run.PLUS_SKILL = ["bench/skills/arrow-tzinfo-string-trap.md"]
    try:
        assert bench_run.arm_segment("treatment") == "-d-learn-1-plus"
    finally:
        _reset()


def test_extra_skill_names_reads_the_frontmatter():
    _reset()
    assert bench_run.extra_skill_names() == []
    bench_run.PLUS_SKILL = ["bench/skills/arrow-tzinfo-string-trap.md"]
    try:
        assert bench_run.extra_skill_names() == ["arrow-tzinfo-string-trap"]
    finally:
        _reset()


# --- E8: a library, not a pair ---------------------------------------------


def _segment_with_plus(paths):
    """Segment only -- it must not depend on the files existing."""
    real = bench_run.PLUS_SKILL
    bench_run.PLUS_SKILL = paths
    try:
        return bench_run.arm_segment("treatment")
    finally:
        bench_run.PLUS_SKILL = real


def _names_with_plus(paths):
    real = bench_run.PLUS_SKILL
    bench_run.PLUS_SKILL = paths
    try:
        return bench_run.extra_skill_names()
    finally:
        bench_run.PLUS_SKILL = real


def test_one_plus_skill_still_produces_e6s_archived_segment():
    """E6's twelve clones and their diffs are archived under `-plus`. Renaming
    the one-extra case would orphan them from their manifest entries."""
    assert _segment_with_plus(["/tmp/x/SKILL.md"]) == "-plus"


def test_no_plus_skill_leaves_the_segment_alone():
    for empty in ([], None):
        assert _segment_with_plus(empty) == "", empty
        assert _names_with_plus(empty) == [], empty


def test_many_plus_skills_carry_the_count_in_the_segment():
    """E8 installs nine extras. Sharing `-plus` with E6 would put two
    different arms under one clone path, which is how E5 lost a batch."""
    assert _segment_with_plus(
        ["/tmp/%d/SKILL.md" % i for i in range(9)]) == "-plus9"


def test_every_extra_skill_is_named_on_the_row():
    """extra_skills is the only record of what arm L actually installed."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i in range(3):
            d = pathlib.Path(tmp) / str(i)
            d.mkdir()
            md = d / "SKILL.md"
            md.write_text("---\nname: skill-%d\nkind: skill\n---\n" % i,
                          encoding="utf-8")
            paths.append(str(md))
        names = _names_with_plus(paths)
    assert names == ["skill-0", "skill-1", "skill-2"], names

def test_plugin_shas_reads_installed_plugins():
    """E10's control break could not be attributed after the fact, because no
    row recorded what was live. Sha when present; version when the entry has
    no sha (swift-lsp carries none); the name is dropped for neither."""
    data = {"version": 2, "plugins": {
        "ponytail@ponytail": [{"gitCommitSha": "c4d1925", "version": "4.8.3"}],
        "swift-lsp@official": [{"version": "1.0.0"}],
        "broken@x": [{}],
    }}
    got = bench_run.plugin_shas(data)
    assert got["ponytail@ponytail"] == "c4d1925"
    assert got["swift-lsp@official"] == "1.0.0"
    assert got["broken@x"] == ""
    assert bench_run.plugin_shas({}) == {}


def _git_repo_with_plugin_file(root):
    import subprocess
    run = lambda *a: subprocess.run(["git", *a], cwd=str(root), check=True,
                                    capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (root / "scripts").mkdir()
    (root / "scripts" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "bench").mkdir()
    (root / "bench" / "results.jsonl").write_text("", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                          capture_output=True, text=True).stdout.strip()


def test_plugin_commit_names_the_commit_and_flags_plugin_edits_only():
    """Every batch appends to bench/results.jsonl, so dirt outside the plugin's
    own paths must not mark the row: otherwise every row after the first reads
    +dirty and the flag means nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(os.path.realpath(tmp))
        sha = _git_repo_with_plugin_file(root)
        assert bench_run.plugin_commit(root) == sha
        (root / "bench" / "results.jsonl").write_text("{}\n", encoding="utf-8")
        assert bench_run.plugin_commit(root) == sha, "bench/ dirt must not count"
        (root / "scripts" / "x.py").write_text("x = 2\n", encoding="utf-8")
        assert bench_run.plugin_commit(root) == sha + "+dirty"


def test_plugin_commit_is_empty_outside_a_git_checkout():
    with tempfile.TemporaryDirectory() as tmp:
        assert bench_run.plugin_commit(tmp) == ""


def test_environment_carries_the_plugin_commit():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(os.path.realpath(tmp))
        sha = _git_repo_with_plugin_file(root)
        env = bench_run.environment(root)
        assert env["plugin_commit"] == sha
        assert set(env) == {"cli", "plugins", "plugin_commit"}
    assert bench_run.environment()["plugin_commit"] == ""


def test_check_config_refuses_a_task_that_grades_nothing():
    """score() returns {} for an empty fail_to_pass, and all({}.values()) is
    True, so such a task would read every run -- control included -- as
    resolved."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "scripts").mkdir()
        (root / ".git").mkdir()
        cfg = {"plugin_dir": str(root), "tasks": [
            {"id": "grades-nothing", "repo": str(root), "fail_to_pass": []},
            {"id": "grades-something", "repo": str(root), "fail_to_pass": ["test_x"]},
        ]}
        bad = bench_run.check_config(cfg)
        assert any("grades-nothing" in b and "fail_to_pass is empty" in b for b in bad), bad
        assert not any("grades-something" in b for b in bad), bad


def _repo_with_a_fix_and_a_later_commit(root):
    """parent -> fix (changes src.py and adds a test) -> later (writes the answer down)."""
    import subprocess
    run = lambda *a: subprocess.run(["git", *a], cwd=str(root), check=True,
                                    capture_output=True)
    sha = lambda: subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                                 capture_output=True, text=True).stdout.strip()
    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (root / "tests").mkdir()
    (root / "src.py").write_text("def f():\n    return 'parent'\n", encoding="utf-8")
    (root / "tests" / "test_x.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "parent")
    (root / "src.py").write_text("def f():\n    return 'fixed'\n", encoding="utf-8")
    (root / "tests" / "test_x.py").write_text(
        "def test_old():\n    pass\n\ndef test_trap():\n    pass\n", encoding="utf-8")
    run("commit", "-qam", "fix")
    fix = sha()
    (root / "ANSWERS.md").write_text("the fix is in %s\n" % fix, encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "later")
    return fix


def _prepared(mode):
    """(dest, fix sha, root) after prepare(), with WORK pointed at a temp dir."""
    import atexit
    import shutil
    import subprocess
    tmp = pathlib.Path(os.path.realpath(tempfile.mkdtemp()))
    atexit.register(shutil.rmtree, str(tmp), True)
    root = tmp / "repo"
    root.mkdir()
    fix = _repo_with_a_fix_and_a_later_commit(root)
    stub = tmp / "stub.py"
    stub.write_text("open('src.py', 'w').write('def f():\\n    raise NotImplementedError\\n')\n",
                    encoding="utf-8")
    task = {"id": "strip-" + mode, "repo": str(root), "fix_commit": fix,
            "test_path": "tests/test_x.py", "setup_cmd": "true", "mode": mode,
            "stub_cmd": "python3 %s" % stub}
    saved, bench_run.WORK = bench_run.WORK, tmp / "work"
    try:
        dest = tmp / "work" / task["id"]
        bench_run.prepare(task, dest)
        if mode == "author":
            before = subprocess.run(["git", "status", "--porcelain"], cwd=str(dest),
                                    capture_output=True, text=True).stdout
            bench_run.apply_hidden_tests(task, dest)
            return dest, fix, before
        return dest, fix, None
    finally:
        bench_run.WORK = saved


def _git_out(dest, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=str(dest), capture_output=True, text=True)


def test_prepare_leaves_no_history_to_read_the_answer_from():
    """A session sitting at the fix's parent could `git show <fix>:<test_path>`
    and read the hidden graded tests, and `git log --all` reaches every later
    commit -- for E13, the spec and stubs that describe each trap. The clone
    must hold exactly one commit: the starting tree."""
    for mode in ("author", "repair"):
        dest, fix, _ = _prepared(mode)
        assert _git_out(dest, "rev-list", "--all", "--count").stdout.strip() == "1", mode
        assert _git_out(dest, "cat-file", "-e", fix).returncode != 0, "%s: fix commit reachable" % mode
        assert not (dest / "ANSWERS.md").exists()
        assert "ANSWERS" not in _git_out(dest, "log", "--all", "--stat").stdout, mode


def test_author_baseline_is_the_stubbed_tree_so_git_diff_hides_the_original():
    """The stub was an uncommitted edit, so `git diff` showed the parent's own
    implementation being deleted -- the historical code, one command away."""
    dest, _, status_before_tests = _prepared("author")
    assert status_before_tests == "", status_before_tests
    assert "NotImplementedError" in (dest / "src.py").read_text(encoding="utf-8")
    assert "parent" not in _git_out(dest, "log", "-p", "--all").stdout


def test_hidden_tests_still_arrive_from_the_fix_after_the_strip():
    dest, _, _ = _prepared("author")
    assert "def test_trap" in (dest / "tests" / "test_x.py").read_text(encoding="utf-8")


def test_repair_baseline_carries_the_fix_tests_and_the_parent_source():
    dest, _, _ = _prepared("repair")
    assert "def test_trap" in (dest / "tests" / "test_x.py").read_text(encoding="utf-8")
    assert "'parent'" in (dest / "src.py").read_text(encoding="utf-8")
    assert _git_out(dest, "status", "--porcelain").stdout == ""


def test_snapshot_plugin_extracts_the_plugin_and_marks_its_commit():
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        snap = pathlib.Path(os.path.realpath(tmp)) / "snap"
        sha = bench_run.snapshot_plugin("HEAD", snap)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(bench_run.REPO_ROOT),
                              capture_output=True, text=True).stdout.strip()
        assert sha == head
        assert (snap / "scripts" / "retrieve.py").is_file()
        assert (snap / "hooks" / "hooks.json").is_file()
        assert (snap / "commands").is_dir(), "commands/ missing -- not a complete plugin"
        assert not (snap / "bench").exists() and not (snap / "tests").exists()
        assert bench_run.plugin_commit(snap) == "archive:" + sha


def test_arm_segment_separates_arms_that_differ_only_in_plugin():
    saved = (bench_run.SKILL_FROM, bench_run.PLUS_SKILL, bench_run.FORCE_HOT,
             bench_run.INJECT_BUDGET, bench_run.PLUGIN_SEGMENT)
    try:
        bench_run.SKILL_FROM = bench_run.PLUS_SKILL = bench_run.INJECT_BUDGET = None
        bench_run.FORCE_HOT = False
        bench_run.PLUGIN_SEGMENT = "-p06885c0"
        assert bench_run.arm_segment("treatment") == "-p06885c0"
        bench_run.PLUGIN_SEGMENT = "-p9cbb472"
        assert bench_run.arm_segment("treatment") == "-p9cbb472"
        bench_run.PLUGIN_SEGMENT = ""
        assert bench_run.arm_segment("treatment") == ""
    finally:
        (bench_run.SKILL_FROM, bench_run.PLUS_SKILL, bench_run.FORCE_HOT,
         bench_run.INJECT_BUDGET, bench_run.PLUGIN_SEGMENT) = saved


def test_main_refuses_a_plugin_dir_with_no_scripts():
    with tempfile.TemporaryDirectory() as tmp:
        assert bench_run.main(["--task", "sf-author-verdict-from", "--plugin-dir", tmp]) == 1


def test_main_refuses_a_plugin_dir_it_cannot_attribute_to_a_commit():
    """scripts/ exists but the dir is neither a git checkout nor a
    snapshot_plugin() snapshot -- plugin_commit() returns "" and, without this
    guard, PLUGIN_SEGMENT would collapse to the constant "-p" for every such
    dir. Two batches pointed at two such dirs would then share a clone path
    and a per-run ledger -- the E5 collision this task exists to prevent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        (pathlib.Path(tmp) / "scripts").mkdir()
        assert bench_run.main(["--task", "sf-author-verdict-from", "--plugin-dir", tmp]) == 1


# --- secret scrub: results.jsonl is published; GitHub push protection blocked
# a push on 2026-09-14 over a test fixture quoted in test_tail -----------------


def _fake_stripe_key():
    """Built at runtime so no committed file holds a literal secret-shaped
    string -- GitHub scans test files too."""
    return "sk_" + "live_" + "a1b2" * 6


def _fake_assigned_secret():
    return "api_key" + "=" + '"' + "s3cr3t" + "value1" + '"'


def test_scrub_secrets_redacts_known_patterns_in_nested_structures():
    stripe = _fake_stripe_key()
    assigned = _fake_assigned_secret()
    value = {
        "tail": "before " + stripe + " after",
        "nested": ["prefix " + assigned + " suffix", 42, None, True],
    }
    got = bench_run.scrub_secrets(value)
    assert stripe not in got["tail"], got["tail"]
    assert "[redacted:stripe-key]" in got["tail"], got["tail"]
    assert got["tail"] == "before [redacted:stripe-key] after", got["tail"]
    assert assigned not in got["nested"][0], got["nested"][0]
    assert "[redacted:assigned-secret]" in got["nested"][0], got["nested"][0]
    assert got["nested"][0] == "prefix [redacted:assigned-secret] suffix", got["nested"][0]
    assert got["nested"][1] == 42
    assert got["nested"][2] is None
    assert got["nested"][3] is True


def test_scrub_secrets_round_trips_a_clean_row():
    """A row with nothing secret-shaped must come back byte-identical, so
    json.dumps of a clean row is unchanged."""
    row = {
        "task": "sf-author-store-dir", "arm": "treatment", "run": 1,
        "resolved": True, "per_test": {"test_a": True, "test_b": False},
        "injections": [{"skill": "x", "trigger": "y", "tier": "warm"}],
        "secs": 12.5, "session_ok": True, "session_tail": None,
        "extra_skills": [], "ts": "2026-09-14T00:00:00",
    }
    assert json.dumps(bench_run.scrub_secrets(row)) == json.dumps(row)


def _with_work(fn):
    """Run fn(work) with bench_run.WORK and SANDBOX swapped, then restore both."""
    old_work, old_sandbox = bench_run.WORK, bench_run.SANDBOX
    with tempfile.TemporaryDirectory() as tmp:
        bench_run.WORK = pathlib.Path(os.path.realpath(tmp))
        try:
            fn(bench_run.WORK)
        finally:
            bench_run.WORK, bench_run.SANDBOX = old_work, old_sandbox


def test_session_cmd_is_sandboxed_by_default_and_carries_the_session_id():
    def body(work):
        bench_run.SANDBOX = True
        cmd = bench_run.session_cmd("fix it", work / "clone-1", work / "plugin-x", "sid-123")
        assert cmd.startswith("sandbox-exec -f ")
        assert "--session-id sid-123" in cmd and "--plugin-dir" in cmd
        assert (work / "clone-1.sb").is_file()
    _with_work(body)


def test_session_cmd_without_the_sandbox_is_the_plain_command():
    def body(work):
        bench_run.SANDBOX = False
        cmd = bench_run.session_cmd("fix it", work / "clone-1", work / "plugin-x", "sid-123")
        assert cmd.startswith("claude -p ") and "--session-id sid-123" in cmd
        assert not (work / "clone-1.sb").exists()
    _with_work(body)


def test_sandbox_plugin_passes_a_snapshot_through():
    with tempfile.TemporaryDirectory() as tmp:
        snap = pathlib.Path(tmp)
        (snap / bench_run.SNAPSHOT_MARK).write_text("a" * 40 + "\n", encoding="utf-8")
        assert bench_run.sandbox_plugin(snap, explicit=True) == snap


def test_sandbox_plugin_refuses_an_explicit_non_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            bench_run.sandbox_plugin(pathlib.Path(tmp), explicit=True)
        except ValueError:
            return
        raise AssertionError("an explicit non-snapshot plugin dir was accepted")


def test_sandbox_plugin_refuses_a_dirty_checkout():
    old = bench_run.plugin_commit
    bench_run.plugin_commit = lambda p: "b" * 40 + "+dirty"
    try:
        bench_run.sandbox_plugin(bench_run.REPO_ROOT, explicit=False)
    except ValueError:
        return
    finally:
        bench_run.plugin_commit = old
    raise AssertionError("a dirty checkout was accepted")


def test_sandbox_plugin_snapshots_a_clean_checkout_under_work():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(bench_run.REPO_ROOT),
                          capture_output=True, text=True, check=True).stdout.strip()
    old = bench_run.plugin_commit

    def body(work):
        bench_run.plugin_commit = lambda p: head
        got = bench_run.sandbox_plugin(bench_run.REPO_ROOT, explicit=False)
        assert got == work / ("plugin-" + head[:7])
        assert (got / "scripts" / "validate.py").is_file()
        assert (got / bench_run.SNAPSHOT_MARK).read_text(encoding="utf-8").strip() == head
        assert not (got / "bench").exists()
        assert bench_run.sandbox_plugin(bench_run.REPO_ROOT, explicit=False) == got
    try:
        _with_work(body)
    finally:
        bench_run.plugin_commit = old


def test_session_audit_records_the_keys_and_a_missing_transcript():
    def body(work):
        bench_run.SANDBOX = True
        keys = bench_run.session_audit("no-such-session-id", work / "clone-1", work / "plugin-x")
        assert keys["sandbox"] is True and keys["session_id"] == "no-such-session-id"
        assert keys["sandbox_profile"] == bench_run.sandbox.TEMPLATE_SHA
        assert keys["audit"]["verdict"] == "missing"
    _with_work(body)


def test_session_audit_never_raises_when_repo_parent_fails():
    """git can fail (missing binary, detached worktree oddity); a raise here
    costs run.py a results row and leaves distill.py's meta.json unwritten
    (session_audit runs inside a finally there)."""
    def body(work):
        bench_run.SANDBOX = True
        old = bench_run.sandbox.repo_parent

        def boom(_):
            raise RuntimeError("boom")
        bench_run.sandbox.repo_parent = boom
        try:
            keys = bench_run.session_audit("no-such-session-id", work / "clone-1", work / "plugin-x")
            assert keys["audit"] == {"verdict": "missing", "hits": [], "leaked": []}
        finally:
            bench_run.sandbox.repo_parent = old
    _with_work(body)


def _fake_snapshot(root, sha="a" * 40):
    (root / "skills" / "distilling-skills").mkdir(parents=True)
    (root / "skills" / "distilling-skills" / "SKILL.md").write_text("shipped\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "validate.py").write_text("# code\n", encoding="utf-8")
    (root / bench_run.SNAPSHOT_MARK).write_text(sha + "\n", encoding="utf-8")
    return root


def test_variant_plugin_swaps_only_the_distilling_skill_and_marks_the_variant():
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        base = _fake_snapshot(t / "base")
        variant = t / "variant.md"
        variant.write_text("with rules\n", encoding="utf-8")
        got = bench_run.variant_plugin(base, variant, t / "out")
        assert got == t / "out"
        assert (got / "skills" / "distilling-skills" / "SKILL.md").read_text(encoding="utf-8") == "with rules\n"
        assert (got / "scripts" / "validate.py").read_text(encoding="utf-8") == "# code\n"
        h = hashlib.sha256(b"with rules\n").hexdigest()[:12]
        assert (got / bench_run.SNAPSHOT_MARK).read_text(encoding="utf-8") == "a" * 40 + "+e15-" + h + "\n"
        assert bench_run.plugin_commit(got) == "archive:" + "a" * 40 + "+e15-" + h
        assert (base / "skills" / "distilling-skills" / "SKILL.md").read_text(encoding="utf-8") == "shipped\n"


def test_variant_plugin_refuses_a_base_that_is_not_a_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "base").mkdir()
        (t / "v.md").write_text("x\n", encoding="utf-8")
        try:
            bench_run.variant_plugin(t / "base", t / "v.md", t / "out")
        except ValueError:
            return
        raise AssertionError("a non-snapshot base was accepted")


def test_variant_plugin_replaces_an_existing_destination():
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        base = _fake_snapshot(t / "base")
        (t / "v.md").write_text("x\n", encoding="utf-8")
        (t / "out").mkdir()
        (t / "out" / "stale.txt").write_text("old\n", encoding="utf-8")
        got = bench_run.variant_plugin(base, t / "v.md", t / "out")
        assert not (got / "stale.txt").exists()


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
