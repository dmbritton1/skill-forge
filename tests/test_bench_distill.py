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


def test_new_trust_keys_names_only_what_the_batch_added():
    def check(home):
        _seed(home, trust_keys=["operators-own"])
        before = libguard.snapshot()
        _seed(home, trust_keys=["operators-own", "batch-wrote-this"])
        assert libguard.new_trust_keys(before) == ["batch-wrote-this"]
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


import dryrun


def test_predict_delivers_when_the_description_shares_the_prompt_s_terms():
    out = dryrun.predict(
        "Use when: implementing response_text against a contract-only stub.",
        "response-text-trap",
        "scripts/detect.py has a function response_text whose body raises "
        "NotImplementedError. Read its docstring and implement it.")
    assert out["predicted"] == "deliver", out
    assert out["matched"] >= 2, out


def test_predict_refuses_when_nothing_overlaps():
    out = dryrun.predict(
        "Use when: configuring a Kubernetes ingress for blue-green rollout.",
        "ingress-rollout",
        "scripts/detect.py has a function response_text whose body raises "
        "NotImplementedError. Read its docstring and implement it.")
    assert out["predicted"] == "no-deliver", out


def test_predict_uses_retrieve_s_own_threshold():
    """The gate is retrieve.py's, not a number this script invents."""
    import retrieve
    out = dryrun.predict("Use when: alpha beta.", "x", "gamma delta")
    assert out["matched"] < retrieve.MIN_MATCHED_TERMS
    assert out["predicted"] == "no-deliver", out


def test_predict_handles_an_empty_description():
    out = dryrun.predict("", "x", "anything at all")
    assert out["predicted"] == "no-deliver", out
    assert out["score"] == 0


import judge


def test_symptom_shape_calls_an_error_signature_a_signature():
    assert judge.symptom_shape(
        ["KeyError: 'response_text'", "TypeError: expected str, got dict"]) == "signature"


def test_symptom_shape_calls_narration_narration():
    """Both hand-authored comparators are narration-shaped, in violation of
    the contract the distiller is held to. That asymmetry is measured, not
    scored against the distiller."""
    assert judge.symptom_shape(
        ["matched the string fixture but not the dict payload",
         "confirmed absent without examining the full input"]) == "narration"


def test_symptom_shape_none_when_absent():
    assert judge.symptom_shape([]) == "none"


def test_has_both_directions_requires_both():
    assert judge.has_both_directions(
        "Use when: probing. Do NOT use when: never.") is True
    assert judge.has_both_directions("Use when: probing.") is False
    assert judge.has_both_directions("") is False


def test_verification_discriminates_is_none_for_an_unrunnable_command():
    assert judge.verification_discriminates("", "/nonexistent", "HEAD") is None


def test_fingerprints_in_fix_reports_one_bool_per_fingerprint():
    out = judge.fingerprints_in_fix([], "/nonexistent", "HEAD")
    assert out == []


def _tiny_repo(root):
    """A two-commit git repo: HEAD adds marker.txt, HEAD~1 does not have it."""
    import subprocess as sp
    def git(*args):
        r = sp.run(["git", "-C", str(root)] + list(args),
                   capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    (root / "marker.txt").write_text("applied\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "the fix")


def test_verification_discriminates_true_when_the_command_fails_pre_fix():
    """The whole point: the command must be evaluated in a tree where the
    procedure was NOT applied. Run against the live HEAD instead, this
    returns False and the check means nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "r"
        root.mkdir()
        _tiny_repo(root)
        got = judge.verification_discriminates("test -f marker.txt", root, "HEAD~1")
        assert got is True, got


def test_verification_does_not_discriminate_when_it_passes_pre_fix():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "r"
        root.mkdir()
        _tiny_repo(root)
        got = judge.verification_discriminates("true", root, "HEAD~1")
        assert got is False, got


def test_verification_discriminates_is_none_for_an_unresolvable_sha():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "r"
        root.mkdir()
        _tiny_repo(root)
        got = judge.verification_discriminates("true", root, "nosuchref")
        assert got is None, got


def test_verification_leaves_no_worktree_behind():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "r"
        root.mkdir()
        _tiny_repo(root)
        judge.verification_discriminates("true", root, "HEAD~1")
        import subprocess as sp
        out = sp.run(["git", "-C", str(root), "worktree", "list"],
                     capture_output=True, text=True).stdout
        assert out.count("\n") == 1, out


def test_fingerprints_in_fix_matches_added_lines_only():
    """Matching runs against the ADDED lines of the reference fix, so a
    fragment that only appears in the pre-fix tree must not count."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "r"
        root.mkdir()
        _tiny_repo(root)
        got = judge.fingerprints_in_fix(["applied", "base", "absent"], root, "HEAD")
        assert got == [True, False, False], got


def test_run_py_suppresses_critique_for_every_treatment_install():
    """42 phase-2 installs would otherwise each spawn a detached `claude -p`
    critique, concurrent with the sessions being timed."""
    src = (pathlib.Path(__file__).resolve().parent.parent / "bench" / "run.py"
           ).read_text(encoding="utf-8")
    assert 'os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"' in src, src[:0]


def test_frontmatter_handles_every_folded_indicator():
    """`|` and `>-` used to come back with their own indicator glued on."""
    for ind in (">", "|", ">-"):
        name, desc = dryrun._frontmatter(
            "---\nname: x\ndescription: %s\n  Line one.\n---\n## Body\n" % ind)
        assert name == "x", (ind, name)
        assert desc.startswith("Line one."), (ind, desc)


def test_frontmatter_ignores_a_fenced_example_in_the_body():
    text = ("---\nname: real\ndescription: >\n  The real one.\n---\n"
            "## Trap\n```markdown\n---\nname: fake\ndescription: >\n"
            "  The example.\n---\n```\n")
    name, desc = dryrun._frontmatter(text)
    assert name == "real", name
    assert "example" not in desc, desc


def test_judge_reads_verification_command_from_frontmatter_not_the_body():
    """A line scan kept the LAST match, so a fenced example in the body won --
    and that string is executed under a shell."""
    import save_skill as _ss
    text = ('---\nname: real\ndescription: >\n  d.\n'
            'verification.command: "python3 tests/real.py"\n---\n'
            '## Trap\n```markdown\nverification.command: "echo pwned"\n```\n')
    fm, _ = _ss.parse_frontmatter(text)
    got = str(fm.get("verification.command") or "").strip().strip('"\'')
    assert got == "python3 tests/real.py", got


def test_distill_refuses_to_overwrite_an_archived_draw():
    """Pre-registration forbids re-rolling a draw after its content is seen."""
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        real = distill.ARCHIVE
        distill.ARCHIVE = pathlib.Path(tmp)
        try:
            d = distill.archive_dir("A", "learn", 1)
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"secs": 12.3}), encoding="utf-8")
            raised = False
            try:
                distill.one("A", "learn", 1, pathlib.Path("."), {"id": "x", "prompt": "p"})
            except RuntimeError as err:
                raised = "already archived" in str(err)
            assert raised, "an archived draw must not be silently re-rolled"
        finally:
            distill.ARCHIVE = real


def test_distill_retries_a_draw_that_never_ran():
    """A draw that died in prepare() wrote a meta.json with secs 0.0 and no
    draft. Nothing was seen, so pre-registration does not bar a retry."""
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        real = distill.ARCHIVE
        distill.ARCHIVE = pathlib.Path(tmp)
        try:
            d = distill.archive_dir("A", "learn", 1)
            d.mkdir(parents=True)
            (d / "meta.json").write_text(
                json.dumps({"outcome": "errored", "secs": 0.0}), encoding="utf-8")
            raised = False
            try:
                distill.one("A", "learn", 1, pathlib.Path("."),
                            {"id": "x", "prompt": "p"})
            except RuntimeError as err:
                raised = "already archived" in str(err)
            assert not raised, "a draw that never ran must be retryable"
        except Exception:
            pass          # it will fail later, in prepare -- that is fine
        finally:
            distill.ARCHIVE = real


def test_one_archives_and_contains_a_global_scope_draw():
    """Drives distill.one through the global-scope path with the session
    stubbed: the finally must archive the draft, invoke the containment
    delete, prune the trust key, and leave drift() clean.

    This is the branch that runs `library.py delete` against the operator's
    real store. It had no coverage at all, and four blocking defects have
    already been found in this function by reading rather than by testing.
    """
    def check(home):
        import tempfile as _tf
        with _tf.TemporaryDirectory() as tmp:
            tmpp = pathlib.Path(tmp)
            real_archive = distill.ARCHIVE
            real_work = distill.bench_run.WORK
            real_sh, real_prepare, real_score = (
                distill.bench_run.sh, distill.bench_run.prepare,
                distill.bench_run.score)
            distill.ARCHIVE = tmpp / "archive"
            # WORK too, not just ARCHIVE. one() derives its clone path AND its
            # per-run ledger path from it, and it unlinks that ledger before
            # the run -- so against the real /tmp/skillforge-bench this test
            # read a previous benchmark run's saved draft (drafts() searches
            # the project store first) and truncated that run's ledger to zero
            # bytes. This repo has already shipped one fix for a suite that
            # destroyed real state; that is not a mistake to make twice.
            distill.bench_run.WORK = tmpp / "work"
            calls = []

            class _R:
                returncode = 0
                stdout = "session done"
                stderr = ""

            def fake_sh(cmd, **kw):
                calls.append(cmd)
                if "claude -p" in cmd:
                    # The session saves globally, exactly as a model judging
                    # its trap general would.
                    d = home / ".claude" / "skillforge" / "antiskills" / "gtrap"
                    d.mkdir(parents=True, exist_ok=True)
                    (d / "SKILL.md").write_text(
                        "---\nname: gtrap\nkind: antiskill\n---\n## Trap\n",
                        encoding="utf-8")
                    reg = home / ".claude" / "skillforge" / "trust.json"
                    reg.write_text(json.dumps({"gtrap": {"origin": "self"}}),
                                   encoding="utf-8")
                elif "library.py" in cmd and "delete" in cmd:
                    import shutil
                    shutil.rmtree(
                        str(home / ".claude" / "skillforge" / "antiskills" / "gtrap"),
                        ignore_errors=True)
                return _R()

            distill.bench_run.sh = fake_sh
            distill.bench_run.prepare = lambda task, dest: None
            distill.bench_run.score = lambda task, dest: ({"t": True}, "ok")
            try:
                _seed(home)
                before = libguard.snapshot()
                out = distill.one("A", "learn-failure", 1, pathlib.Path("."),
                                  {"id": "sf-escaping-breaks-symptom-match",
                                   "prompt": "fix it"})
                d = distill.ARCHIVE / "A" / "learn-failure" / "1"
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                assert out == "saved", out
                assert (d / "SKILL.md").is_file(), "the draft must be archived"
                assert meta["chose_global_scope"] == ["gtrap"], meta["chose_global_scope"]
                assert meta["skill_name"] == "gtrap", meta["skill_name"]
                assert meta["pruned_trust"] == ["gtrap"], meta["pruned_trust"]
                assert any("library.py" in c and "delete" in c for c in calls), calls
                assert libguard.drift(before) == [], libguard.drift(before)
            finally:
                distill.ARCHIVE = real_archive
                distill.bench_run.WORK = real_work
                (distill.bench_run.sh, distill.bench_run.prepare,
                 distill.bench_run.score) = real_sh, real_prepare, real_score
    in_home(check)


def test_snapshot_narrows_project_entries_to_one_root():
    def check(home):
        _seed(home, entries=[
            {"name": "mine", "scope": "project", "root": "/repo"},
            {"name": "bench-clone", "scope": "project", "root": "/tmp/throwaway"}])
        assert libguard.snapshot("/repo")["project_index"] == ["mine"]
        assert libguard.snapshot()["project_index"] == ["bench-clone", "mine"]
    in_home(check)


def test_drift_ignores_a_bench_clone_s_project_entry():
    """The pilot draw's clone wrote an entry rooted in /tmp and drift called it
    unexpected. Every draw writes one; comparing them fires on a clean batch."""
    def check(home):
        _seed(home, entries=[{"name": "mine", "scope": "project", "root": "/repo"}])
        before = libguard.snapshot("/repo")
        _seed(home, entries=[
            {"name": "mine", "scope": "project", "root": "/repo"},
            {"name": "from-a-clone", "scope": "project", "root": "/tmp/clone-1"}])
        assert libguard.drift(before, "/repo") == []
    in_home(check)


def test_drift_still_reports_the_real_repo_s_entry_going_missing():
    """Spec section 4(d): the operator's own entries must be asserted present."""
    def check(home):
        _seed(home, entries=[{"name": "mine", "scope": "project", "root": "/repo"}])
        before = libguard.snapshot("/repo")
        _seed(home, entries=[{"name": "from-a-clone", "scope": "project",
                              "root": "/tmp/clone-1"}])
        out = libguard.drift(before, "/repo")
        assert out and "mine" in out[0], out
    in_home(check)



def test_a_refused_session_is_not_a_repair_failure():
    """A rate limit mid-batch returns non-zero without raising. Recorded as
    repair_unresolved it becomes a false claim about the distiller, written
    into the experiment's own evidence."""
    assert distill.outcome(False, False, None, 0, session_ok=False) == "session_failed"


def test_session_failed_outranks_every_other_outcome():
    for args in ((False, False, None, 0), (True, True, None, 0),
                 (True, False, "draft", 1), (True, False, "draft", 0)):
        assert distill.outcome(*args, session_ok=False) == "session_failed", args


def test_session_failed_is_not_probeable():
    assert distill.probeable("session_failed") is False


def test_outcome_defaults_to_a_healthy_session():
    """The four-argument form must keep its old meaning for existing callers."""
    assert distill.outcome(True, False, "draft", 0) == "saved"


def test_distill_retries_a_refused_session():
    """The archive guard must not lock a draw the API refused -- nothing was
    seen, so pre-registration's bar on re-rolling does not apply."""
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        real = distill.ARCHIVE
        distill.ARCHIVE = pathlib.Path(tmp)
        try:
            d = distill.archive_dir("A", "learn", 1)
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps(
                {"outcome": "session_failed", "secs": 12.3, "session_ok": False}),
                encoding="utf-8")
            raised = False
            try:
                distill.one("A", "learn", 1, pathlib.Path("."),
                            {"id": "x", "prompt": "p"})
            except RuntimeError as err:
                raised = "already archived" in str(err)
            assert not raised, "a refused session must be retryable"
        except Exception:
            pass          # it fails later in prepare; that is fine
        finally:
            distill.ARCHIVE = real

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
