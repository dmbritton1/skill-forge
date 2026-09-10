# Graded Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all-or-nothing `resolved` with a graded score, so the bench can resolve effects smaller than the whole task.

**Architecture:** Two independently-scored halves. A probe suite of behavioral assertions run against a replayed artifact costs zero sessions. A judge reading the artifact costs one session each. Both are recorded separately in a new `bench/graded.jsonl`; `resolved` and `results.jsonl` are untouched.

**Tech Stack:** Python 3 stdlib only. No pytest, no fixtures — this repo's suites are plain functions with a `__main__` runner printing `PASS <name>` / `FAIL <name>`, and `bench/run.py:score()` parses exactly that format.

**Spec:** `docs/superpowers/specs/2026-09-10-graded-scorer-design.md`

## Global Constraints

- **Python 3 stdlib only.** No third-party imports anywhere in this plan.
- **`tests/` must never invoke a model.** Stated in `bench/critique-calibration/README.md`. The judge half lives under `bench/` for this reason.
- **`results.jsonl` is append-only and untouched by this work.** All graded output goes to `bench/graded.jsonl`.
- **`resolved` is supplemented, never replaced.** No existing field changes meaning.
- **Probes must be strategy-agnostic.** `bench/stubs/patch_file_cap_test.py` documents a grading test that assumed a single-token grep strategy and marked a *better* implementation wrong. Every probe asserts observable behavior for a given input. The only permitted white-box probe is Probe 6, which asserts a value the contract names literally.
- **Probes are self-contained.** A probe file reads `scripts/` from the replayed clone and nothing else. It must not import from the clone's `tests/`, whose contents differ between the two base commits.
- **No probe is added, removed or reworded after scores are seen** (spec §4).
- **Test runner format is fixed:** `print("PASS " + name)` on success, `print("FAIL %s: %r" % (name, err))` on failure, `sys.exit(1 if failures else 0)`.
- **Commit trailer:** every commit ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, committed via `git commit -F -` (see `.claude/skills/skillforge-commit-trailer`).

---

### Task 1: Probe runner shared by both suites

**Files:**
- Create: `bench/probes/__init__.py` (empty)
- Create: `bench/probes/runner.py`
- Test: `bench/probes/test_runner.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `runner.load(clone_root, module_name)` returns the named module imported from `<clone_root>/scripts`. `runner.main(globals_dict)` runs every `test_*` callable in `globals_dict`, prints `PASS`/`FAIL` lines, returns the failure count. `runner.in_sandbox(fn)` calls `fn(pathlib.Path(tmp))` with `HOME` and cwd redirected to a temporary directory. `runner.git_repo(home, files)` writes `files` (a `{relpath: text}` dict) into `home/"repo"`, runs `git init -q` and `git add -A`, and returns the repo path.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the probe runner. Run: python3 bench/probes/test_runner.py"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner


def test_load_imports_from_the_given_clone_not_this_repo():
    def check(home):
        scripts = home / "scripts"
        scripts.mkdir()
        (scripts / "marker_mod.py").write_text("VALUE = 'from-clone'\n", encoding="utf-8")
        mod = runner.load(home, "marker_mod")
        assert mod.VALUE == "from-clone"
    runner.in_sandbox(check)


def test_load_reimports_a_second_clone_with_the_same_module_name():
    # Two clones both define `retrieve`. Without cache eviction the second
    # load silently returns the first clone's module and every probe after
    # the first artifact scores the wrong code.
    def check(home):
        seen = []
        for tag in ("first", "second"):
            root = home / tag
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "dup_mod.py").write_text(
                "VALUE = %r\n" % tag, encoding="utf-8")
            seen.append(runner.load(root, "dup_mod").VALUE)
        assert seen == ["first", "second"], seen
    runner.in_sandbox(check)


def test_load_evicts_transitively_imported_clone_modules():
    # `detect` imports `retrieve`, and `retrieve` is itself an authored
    # artifact. Evicting only the named module lets clone two's detect bind
    # clone one's retrieve, and every score after the first is wrong.
    def check(home):
        seen = []
        for tag in ("first", "second"):
            scripts = home / tag / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "leaf_mod.py").write_text("VALUE = %r\n" % tag, encoding="utf-8")
            (scripts / "top_mod.py").write_text(
                "import leaf_mod\nVALUE = leaf_mod.VALUE\n", encoding="utf-8")
            seen.append(runner.load(home / tag, "top_mod").VALUE)
        assert seen == ["first", "second"], seen
    runner.in_sandbox(check)


def test_in_sandbox_restores_home_and_cwd():
    before_home, before_cwd = os.environ["HOME"], os.getcwd()
    runner.in_sandbox(lambda home: None)
    assert os.environ["HOME"] == before_home
    assert os.getcwd() == before_cwd


def test_git_repo_creates_a_repo_with_the_files_staged():
    def check(home):
        repo = runner.git_repo(home, {"a.js": "hello world"})
        assert (repo / ".git").exists()
        assert (repo / "a.js").read_text() == "hello world"
    runner.in_sandbox(check)


def test_main_counts_failures_and_prints_the_repo_format():
    ns = {"test_ok": lambda: None,
          "test_bad": lambda: (_ for _ in ()).throw(AssertionError("boom"))}
    assert runner.main(ns) == 1


if __name__ == "__main__":
    sys.exit(runner.main(globals()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bench/probes/test_runner.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'runner'`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Shared harness for the graded probe suites (spec 2026-09-10 §3.1).

A probe suite scores ONE authored artifact. It imports that artifact from the
replayed clone's `scripts/` and nothing else -- never from the clone's
`tests/`, whose contents differ between the two base commits, and never from
this repo, which holds the finished implementation and would score every
artifact as perfect.
"""
import importlib
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile


def load(clone_root, module_name):
    """Import `module_name` from <clone_root>/scripts, evicting every cached clone module.

    Every clone names its modules the same thing. Without eviction the second
    artifact scored in a batch silently reuses the first one's module object,
    and the whole run grades one artifact many times.

    The eviction is deliberately broad -- ANY module already imported from a
    `scripts/` directory, not just `module_name`. detect.py imports patterns,
    ledger and retrieve, and retrieve is itself an authored artifact, so
    evicting only the named module would let a response_text clone pull the
    previous clone's retrieve. That is silent cross-contamination of exactly
    the kind the per-run ledger bug already cost this project a batch.
    """
    scripts = str(pathlib.Path(clone_root).resolve() / "scripts")
    sys.path.insert(0, scripts)
    try:
        for name in list(sys.modules):
            mod = sys.modules[name]
            path = getattr(mod, "__file__", None) or ""
            if name == module_name or os.sep + "scripts" + os.sep in path:
                del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(scripts, module_name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(scripts)


def in_sandbox(fn):
    """Run fn(tmpdir) with HOME and cwd redirected, then restore both.

    cwd is part of the sandbox, not just HOME: save_skill's --project-root
    defaults to ".", so anything that syncs treats the current directory as a
    project. Running unsandboxed once deleted a real project's hot skills.
    """
    old_home = os.environ["HOME"]
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        os.chdir(tmp)
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.chdir(old_cwd)
            os.environ["HOME"] = old_home


def git_repo(home, files):
    """A staged git repo under `home` containing `files` ({relpath: text})."""
    repo = pathlib.Path(home) / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    return repo


def main(namespace):
    """Run every test_* callable; print the repo's PASS/FAIL format.

    Returns the failure count. A probe that raises ANYTHING counts as failed:
    an artifact that raises TypeError is not partially correct.
    """
    failures = 0
    for name in sorted(namespace):
        fn = namespace[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    return failures
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bench/probes/test_runner.py`
Expected: all PASS, exit 0

- [ ] **Step 5: Commit**

```bash
git add bench/probes/__init__.py bench/probes/runner.py bench/probes/test_runner.py
git commit -F - <<'EOF'
feat(bench): probe runner for graded scoring

Imports the artifact under test from the replayed clone's scripts/ and
nothing else. Evicts the module cache on every load, because every clone
names its modules identically and without eviction the second artifact in a
batch is scored against the first one's code.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `fingerprint_preexisting` probe suite

**Files:**
- Create: `bench/probes/probe_fingerprint_preexisting.py`

**Interfaces:**
- Consumes: `runner.load`, `runner.in_sandbox`, `runner.git_repo`, `runner.main` from Task 1.
- Produces: an executable taking one argument, the clone root. Prints `PASS`/`FAIL` per probe, exits non-zero if any failed.

Eleven probes. Nine derive from the stub contract, two are the trap. Probes 7, 8 and 9 use the reversed-token decoy construction from `bench/stubs/patch_file_cap_test.py`: every decoy carries **all** of the pattern's tokens so any narrowing strategy returns it as a candidate, in **reverse order** so `patterns.matches()` correctly refuses it. That is what makes them strategy-agnostic.

- [ ] **Step 1: Write the probe suite**

```python
#!/usr/bin/env python3
"""Graded probes for retrieve.fingerprint_preexisting (spec §3.1).

Run: python3 bench/probes/probe_fingerprint_preexisting.py <clone_root>

Nine probes from the stub contract, two from the trap. The contract names
three unknown conditions -- not a git repo, git missing, timeout -- and a
fired cap is deliberately NOT among them. That omission is the trap.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner

CLONE = None
PAT = ["express", "raw", "type", "application", "json"]
HIT = "express.raw({type:'application/json'})"
# All of PAT's tokens, reversed: any grep strategy returns it, matches() refuses it.
DECOY = "json application type raw express"


def _retrieve():
    return runner.load(CLONE, "retrieve")


def test_returns_1_when_a_fingerprint_is_present():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        assert r.fingerprint_preexisting([PAT], str(repo)) == 1
    runner.in_sandbox(check)


def test_returns_0_when_no_fingerprint_is_present():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": "nothing relevant here"})
        assert r.fingerprint_preexisting([PAT], str(repo)) == 0
    runner.in_sandbox(check)


def test_returns_none_outside_a_git_repository():
    def check(home):
        r = _retrieve()
        plain = home / "plain"
        plain.mkdir()
        (plain / "a.js").write_text(HIT, encoding="utf-8")
        assert r.fingerprint_preexisting([PAT], str(plain)) is None
    runner.in_sandbox(check)


def test_returns_none_when_git_is_missing():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run

        def no_git(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                raise FileNotFoundError("git")
            return real(argv, *a, **kw)

        r.subprocess.run = no_git
        try:
            assert r.fingerprint_preexisting([PAT], str(repo)) is None
        finally:
            r.subprocess.run = real
    runner.in_sandbox(check)


def test_returns_none_when_the_subprocess_timeout_fires():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run

        def slow(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                raise subprocess.TimeoutExpired(cmd="git", timeout=0.01)
            return real(argv, *a, **kw)

        r.subprocess.run = slow
        try:
            assert r.fingerprint_preexisting([PAT], str(repo)) is None
        finally:
            r.subprocess.run = real
    runner.in_sandbox(check)


def test_passes_git_timeout_s_as_the_subprocess_timeout():
    # The one white-box probe. The contract names this constant literally,
    # so asserting the value it is called with tests the contract, not a
    # strategy. Any git invocation carrying the right timeout satisfies it.
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": HIT})
        real = subprocess.run
        seen = []

        def spy(argv, *a, **kw):
            if argv and str(argv[0]) == "git":
                seen.append(kw.get("timeout"))
            return real(argv, *a, **kw)

        r.subprocess.run = spy
        try:
            r.fingerprint_preexisting([PAT], str(repo))
        finally:
            r.subprocess.run = real
        assert r.GIT_TIMEOUT_S in seen, seen
    runner.in_sandbox(check)


def test_examines_at_most_snapshot_max_files_candidates():
    def check(home):
        r = _retrieve()
        files = {"decoy%02d.js" % i: DECOY for i in range(r.SNAPSHOT_MAX_FILES + 5)}
        repo = runner.git_repo(home, files)
        # Every candidate is a decoy, so nothing is genuinely present. An
        # implementation honoring the cap cannot have seen them all and must
        # say unknown; one ignoring the cap would confidently answer 0.
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_reads_at_most_snapshot_max_bytes_from_one_file():
    def check(home):
        r = _retrieve()
        filler = ("%s\n" % DECOY) * (r.SNAPSHOT_MAX_BYTES // len(DECOY) + 64)
        repo = runner.git_repo(home, {"big.js": filler + HIT})
        # The genuine hit sits past the byte cap. 0 would be factually wrong
        # and 1 would mean reading past the stated bound.
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_confirms_with_patterns_matches_not_the_raw_grep_hit():
    def check(home):
        r = _retrieve()
        repo = runner.git_repo(home, {"a.js": DECOY})
        # Contains every token, in the wrong order. grep finds the file;
        # patterns.matches() must reject it.
        assert r.fingerprint_preexisting([PAT], str(repo)) == 0
    runner.in_sandbox(check)


def test_unknown_when_match_past_file_cap():
    def check(home):
        r = _retrieve()
        files = {"decoy%02d.js" % i: DECOY for i in range(r.SNAPSHOT_MAX_FILES + 1)}
        files["zzz_real.js"] = HIT      # sorts last, so it is past the cap
        repo = runner.git_repo(home, files)
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


def test_unknown_when_match_past_byte_cap():
    def check(home):
        r = _retrieve()
        pad = "x" * (r.SNAPSHOT_MAX_BYTES + 4096)
        repo = runner.git_repo(home, {"a.js": DECOY + "\n" + pad + "\n" + HIT})
        assert r.fingerprint_preexisting([PAT], str(repo)) is None
    runner.in_sandbox(check)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: probe_fingerprint_preexisting.py <clone_root>", file=sys.stderr)
        sys.exit(2)
    CLONE = sys.argv[1]
    sys.exit(1 if runner.main(globals()) else 0)
```

- [ ] **Step 2: Verify the suite FAILS against the stub**

The stub raises `NotImplementedError`, so an unimplemented artifact must score zero. This is the negative oracle.

```bash
SP=$(mktemp -d)
git worktree add --detach "$SP/stub" 4eeaa9a
(cd "$SP/stub" && python3 "$OLDPWD/bench/stubs/stub_fingerprint_preexisting.py")
python3 bench/probes/probe_fingerprint_preexisting.py "$SP/stub"
```

Expected: 11 FAIL lines, exit 1.

- [ ] **Step 3: Verify the suite PASSES against the shipped implementation**

`ab4acfe` is the task's `fix_commit` — the known-correct artifact. This is the positive oracle, and it is the step that catches a probe asserting something no correct implementation does.

```bash
git worktree add --detach "$SP/fixed" ab4acfe
python3 bench/probes/probe_fingerprint_preexisting.py "$SP/fixed"
```

Expected: 11 PASS lines, exit 0.

**If any probe fails here, the probe is wrong, not the implementation.** Fix the probe and re-run both oracles. This is the only window in which a probe may be reworded — spec §4 closes it the moment archived artifacts are scored.

- [ ] **Step 4: Clean up the scratch worktrees**

```bash
git worktree remove --force "$SP/stub"; git worktree remove --force "$SP/fixed"; git worktree prune
```

- [ ] **Step 5: Commit**

```bash
git add bench/probes/probe_fingerprint_preexisting.py
git commit -F - <<'EOF'
feat(bench): eleven graded probes for fingerprint_preexisting

Nine from the stub contract, two the trap. Verified against both oracles:
all eleven fail against the stub, all eleven pass at fix_commit ab4acfe.

The cap and confirmation probes use the reversed-token decoy construction
from patch_file_cap_test.py -- every decoy carries all of the pattern's
tokens so any narrowing strategy returns it, in reverse order so
patterns.matches() refuses it. That is what keeps them strategy-agnostic.
This repo has already shipped one fix for a grading test that assumed a
single-token grep and marked a better implementation wrong.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: `response_text` probe suite

**Files:**
- Create: `bench/probes/probe_response_text.py`

**Interfaces:**
- Consumes: `runner.load`, `runner.main` from Task 1.
- Produces: an executable taking the clone root, same PASS/FAIL contract as Task 2.

Nine probes. Three from the contract (string in, structured in, truncate to `MAX_OUTPUT_CHARS`); six from enumerating the input space. Spec §5.2 records that this suite carries the weaker derivation guarantee.

- [ ] **Step 1: Write the probe suite**

```python
#!/usr/bin/env python3
"""Graded probes for detect.response_text (spec §3.1).

Run: python3 bench/probes/probe_response_text.py <clone_root>

The stub states three clauses only -- a string may arrive, a structured
object may arrive, truncate to MAX_OUTPUT_CHARS -- and deliberately says
nothing about escaping or tokenization, because naming the hazard would hand
over the knowledge the benchmark measures. Probes 4-9 therefore come from
enumerating the input space, not from the contract.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner

CLONE = None


def _detect():
    return runner.load(CLONE, "detect")


def _patterns():
    return runner.load(CLONE, "patterns")


def test_plain_string_under_the_cap_is_returned_unchanged():
    d = _detect()
    assert d.response_text("hello world") == "hello world"


def test_plain_string_over_the_cap_is_truncated():
    d = _detect()
    out = d.response_text("x" * (d.MAX_OUTPUT_CHARS + 500))
    assert len(out) == d.MAX_OUTPUT_CHARS


def test_flat_dict_yields_text_containing_its_values():
    d = _detect()
    out = d.response_text({"stdout": "connection refused"})
    assert "connection" in out and "refused" in out


def test_nested_dict_yields_text_containing_values_at_depth():
    d = _detect()
    out = d.response_text({"result": {"inner": {"msg": "connection refused"}}})
    assert "connection" in out and "refused" in out


def test_non_string_leaves_survive_into_the_text():
    d = _detect()
    out = d.response_text({"code": 500, "ok": False, "extra": None})
    assert "500" in out


def test_non_serializable_object_does_not_raise():
    d = _detect()

    class Opaque:
        pass

    out = d.response_text({"obj": Opaque()})
    assert isinstance(out, str)


def test_large_structure_never_exceeds_the_cap():
    d = _detect()
    out = d.response_text({"k%d" % i: "v" * 200 for i in range(5000)})
    assert len(out) <= d.MAX_OUTPUT_CHARS


def test_tokenize_recovers_a_flat_dict_value():
    d, p = _detect(), _patterns()
    out = d.response_text({"stderr": "TypeError: bad operand"})
    hay = p.tokenize(out)
    assert p.matches(p.tokenize("TypeError bad operand"), hay), hay[:40]


def test_tokenize_recovers_a_nested_dict_value():
    d, p = _detect(), _patterns()
    out = d.response_text({"result": {"stderr": "TypeError: bad operand"}})
    hay = p.tokenize(out)
    assert p.matches(p.tokenize("TypeError bad operand"), hay), hay[:40]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: probe_response_text.py <clone_root>", file=sys.stderr)
        sys.exit(2)
    CLONE = sys.argv[1]
    sys.exit(1 if runner.main(globals()) else 0)
```

- [ ] **Step 2: Verify the suite FAILS against the stub**

```bash
SP=$(mktemp -d)
git worktree add --detach "$SP/stub" 4eeaa9a
(cd "$SP/stub" && python3 "$OLDPWD/bench/stubs/stub_response_text.py")
python3 bench/probes/probe_response_text.py "$SP/stub"
```

Expected: 9 FAIL lines, exit 1.

- [ ] **Step 3: Verify the suite PASSES against the shipped implementation**

`22ddf37` is this task's `fix_commit`.

```bash
git worktree add --detach "$SP/fixed" 22ddf37
python3 bench/probes/probe_response_text.py "$SP/fixed"
```

Expected: 9 PASS lines, exit 0. A failure here means the probe is wrong; fix it now, before any archived artifact is scored.

- [ ] **Step 4: Clean up and commit**

```bash
git worktree remove --force "$SP/stub"; git worktree remove --force "$SP/fixed"; git worktree prune
git add bench/probes/probe_response_text.py
git commit -F - <<'EOF'
feat(bench): nine graded probes for response_text

Three from the stub contract, six from enumerating the input space -- the
stub withholds the hazard on purpose, so the contract alone cannot span the
difficulty range. Spec §5.2 records that this is a weaker derivation than
the fingerprint suite's and says why.

Verified against both oracles: all nine fail against the stub, all nine pass
at fix_commit 22ddf37.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Replay driver, probe half only

**Files:**
- Create: `bench/regrade.py`
- Test: `tests/test_bench_regrade.py`

**Interfaces:**
- Consumes: the probe executables from Tasks 2 and 3; `bench/authored/manifest.json`.
- Produces: `regrade.replay(entry, workdir)` returns the path to a prepared clone with the artifact applied. `regrade.probe(entry, clone)` returns `{"probe_passed": int, "probe_total": int, "probe_score": float, "probe_detail": {name: bool}}`. `regrade.main(argv)` writes one JSON row per manifest entry to `bench/graded.jsonl`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the regrade replay driver. Run: python3 tests/test_bench_regrade.py"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import regrade


def test_probe_line_parser_reads_the_repo_pass_fail_format():
    out = "PASS test_a\nFAIL test_b: AssertionError()\nPASS test_c\n"
    detail = regrade.parse_probe_output(out)
    assert detail == {"test_a": True, "test_b": False, "test_c": True}


def test_probe_score_is_the_passing_fraction():
    r = regrade.summarize({"a": True, "b": False, "c": True, "d": True})
    assert r["probe_passed"] == 3 and r["probe_total"] == 4
    assert abs(r["probe_score"] - 0.75) < 1e-9


def test_summarize_of_an_empty_run_scores_zero_not_one():
    # A probe suite that could not start must not read as a perfect artifact.
    r = regrade.summarize({})
    assert r["probe_total"] == 0 and r["probe_score"] == 0.0


def test_probe_suite_is_chosen_by_task():
    assert regrade.suite_for("sf-author-response-text").endswith("probe_response_text.py")
    assert regrade.suite_for(
        "sf-author-fingerprint-preexisting").endswith("probe_fingerprint_preexisting.py")


def test_unknown_task_has_no_suite():
    assert regrade.suite_for("sf-escaping-breaks-symptom-match") is None


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_bench_regrade.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'regrade'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""Replay archived artifacts and score them with the graded probe suites.

Costs ZERO sessions: it reuses `bench/authored/`, extracted before /tmp was
swept. Each entry is replayed by checking out its base commit and applying
the diff filtered to `scripts/*` -- the full diff also carries the
harness-staged hidden tests, and replaying those would reinstate the old
two-test grading instead of the new suite.

Run: python3 bench/regrade.py [--limit N]
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent
AUTHORED = ROOT / "authored"
OUT = ROOT / "graded.jsonl"

SUITES = {
    "sf-author-response-text": "probe_response_text.py",
    "sf-author-fingerprint-preexisting": "probe_fingerprint_preexisting.py",
}


def suite_for(task):
    """Absolute path to the probe suite for `task`, or None if ungraded.

    Only the two author tasks have suites. The transfer and umbrella variants
    author the SAME function, so they route through the base task's suite;
    the distillation clones author nothing and are skipped.
    """
    for base, fname in SUITES.items():
        if task == base or task.startswith(base + "-"):
            return str(ROOT / "probes" / fname)
    return None


def parse_probe_output(out):
    """{probe_name: passed} from the repo's PASS/FAIL line format."""
    detail = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("PASS "):
            detail[line[5:].strip()] = True
        elif line.startswith("FAIL "):
            detail[line[5:].split(":", 1)[0].strip()] = False
    return detail


def summarize(detail):
    """Passing count, total, and fraction. An empty run scores 0.0, not 1.0."""
    total = len(detail)
    passed = sum(1 for v in detail.values() if v)
    return {"probe_passed": passed, "probe_total": total,
            "probe_score": (passed / total) if total else 0.0,
            "probe_detail": detail}


def replay(entry, workdir):
    """Check out the base commit and apply the artifact's scripts/ changes."""
    clone = pathlib.Path(workdir) / entry["clone"]
    subprocess.run(["git", "worktree", "add", "--detach", str(clone),
                    entry["base_commit"]], cwd=str(REPO),
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    subprocess.run(["git", "apply", "--include=scripts/*",
                    str(AUTHORED / entry["diff"])], cwd=str(clone), check=True)
    return clone


def probe(entry, clone):
    suite = suite_for(entry["task"])
    r = subprocess.run([sys.executable, suite, str(clone)],
                       capture_output=True, text=True, timeout=300)
    return summarize(parse_probe_output(r.stdout + r.stderr))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    entries = json.loads((AUTHORED / "manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in entries if suite_for(e.get("task") or "")]
    if args.limit:
        entries = entries[:args.limit]

    written = 0
    with tempfile.TemporaryDirectory() as work:
        for e in entries:
            clone = None
            try:
                clone = replay(e, work)
                row = dict(e)
                row.update(probe(e, clone))
                with OUT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
                written += 1
                print("%-58s %d/%d" % (e["clone"], row["probe_passed"],
                                       row["probe_total"]))
            except (subprocess.SubprocessError, OSError) as err:
                print("ERROR %s: %r" % (e["clone"], err), file=sys.stderr)
            finally:
                if clone:
                    subprocess.run(["git", "worktree", "remove", "--force",
                                    str(clone)], cwd=str(REPO),
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    subprocess.run(["git", "worktree", "prune"], cwd=str(REPO),
                   stdout=subprocess.DEVNULL)
    print("wrote %d row(s) to %s" % (written, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_bench_regrade.py`
Expected: all PASS, exit 0

- [ ] **Step 5: Smoke-test the replay on two entries**

Run: `python3 bench/regrade.py --limit 2`
Expected: two lines like `sf-author-response-text-control-1   3/9`, then `wrote 2 row(s)`. Delete `bench/graded.jsonl` afterwards — the real run is Task 6.

- [ ] **Step 6: Verify the whole suite still passes**

Run: `for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAIL $f"; done`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
rm -f bench/graded.jsonl
git add bench/regrade.py tests/test_bench_regrade.py
git commit -F - <<'EOF'
feat(bench): replay driver for graded scoring, zero sessions

Replays each archived artifact onto its base commit and scores it with the
probe suite. The diff is filtered to scripts/* on purpose: the full diff also
carries the harness-staged hidden tests, and replaying those would reinstate
the two-test grading this work exists to replace.

An empty probe run scores 0.0, not 1.0. A suite that could not start must
never read as a perfect artifact -- the same shape of bug as score() counting
a collection error as success.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Judge half

**Files:**
- Create: `bench/grade_judge.py`
- Modify: `bench/regrade.py` — add `--judge` and merge judge fields into the row
- Test: `tests/test_bench_grade_judge.py`

**Interfaces:**
- Consumes: `validate.run_model(prompt, cwd, model=..., timeout=...)` from `scripts/validate.py`, which returns the model's text or `None` on any failure.
- Produces: `grade_judge.build_prompt(source)` returns the prompt string. `grade_judge.parse(text)` returns `{criterion: bool}` or `None` if the reply is unparseable. `grade_judge.judge(clone, task)` returns `{"judge_score": float, "judge_detail": {...}, "judge_ok": bool}`.

**`judge_ok` is the whole point of this task's error handling.** `run_model` returns `None` for a timeout, a crash, *and* a session limit alike. A refused session is not a verdict — the handoff records a rate-limited session being archived as a real result and then locked. `judge_ok: false` rows are excluded from every cell, inheriting the `session_ok` rule.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the graded judge. Run: python3 tests/test_bench_grade_judge.py

No model is called here. tests/ is forbidden from invoking a model; this
suite exercises prompt construction and reply parsing only.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import grade_judge


def test_parse_reads_a_well_formed_verdict():
    text = '{"explicit_unknown": true, "bounds_documented": false, "visible_degradation": true}'
    got = grade_judge.parse(text)
    assert got == {"explicit_unknown": True, "bounds_documented": False,
                   "visible_degradation": True}


def test_parse_tolerates_prose_around_the_json():
    text = 'Here is my verdict:\n{"explicit_unknown": false, ' \
           '"bounds_documented": true, "visible_degradation": true}\nDone.'
    assert grade_judge.parse(text)["bounds_documented"] is True


def test_parse_returns_none_on_garbage():
    assert grade_judge.parse("I could not read the file.") is None


def test_parse_returns_none_when_a_criterion_is_missing():
    # A partial verdict scored as a fraction would silently invent a denominator.
    assert grade_judge.parse('{"explicit_unknown": true}') is None


def test_score_of_a_none_verdict_is_not_ok_and_not_zero():
    r = grade_judge.summarize(None)
    assert r["judge_ok"] is False
    assert r["judge_score"] is None


def test_score_is_the_fraction_of_criteria_met():
    r = grade_judge.summarize({"explicit_unknown": True, "bounds_documented": False,
                               "visible_degradation": True})
    assert r["judge_ok"] is True
    assert abs(r["judge_score"] - (2 / 3)) < 1e-9


def test_prompt_contains_the_source_and_every_criterion():
    p = grade_judge.build_prompt("def f(): pass")
    assert "def f(): pass" in p
    for key in grade_judge.CRITERIA:
        assert key in p


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_bench_grade_judge.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'grade_judge'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""The judge half of graded scoring (spec §3.2).

SPENDS REAL MODEL CALLS -- one `claude -p` turn per artifact. Never run this
from a test; tests/ is forbidden from invoking a model.

Scores what an assertion cannot. Reported ALONGSIDE the probe score, never
merged into it: a disagreement between the halves is the signal, and merging
them is how it would be hidden.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import validate

CRITERIA = {
    "explicit_unknown":
        "Is the unknown-versus-absent distinction explicit -- a named branch,"
        " an early return, or a comment saying which is which -- rather than"
        " something that merely falls out of the control flow?",
    "bounds_documented":
        "Where a bound or cap is applied, is it explained at the point of use,"
        " rather than appearing as a bare constant?",
    "visible_degradation":
        "On unexpected input, does the code fail or degrade visibly rather"
        " than silently returning a confident answer?",
}

TARGET = {
    "sf-author-response-text": ("detect.py", "response_text"),
    "sf-author-fingerprint-preexisting": ("retrieve.py", "fingerprint_preexisting"),
}


def target_for(task):
    for base, spec in TARGET.items():
        if task == base or task.startswith(base + "-"):
            return spec
    return None


def extract(clone, task):
    """The authored function's source, or None."""
    spec = target_for(task)
    if not spec:
        return None
    fname, func = spec
    try:
        src = (pathlib.Path(clone) / "scripts" / fname).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^def %s\(.*?\n(?:.*\n)*?(?=^def |\Z)" % re.escape(func),
                  src, re.M)
    return m.group(0) if m else None


def build_prompt(source):
    lines = ["Judge this Python function against each criterion below.",
             "Answer ONLY with a JSON object mapping every criterion key to"
             " true or false. No prose, no code fences.", ""]
    for key, question in CRITERIA.items():
        lines.append("%s: %s" % (key, question))
    lines += ["", "```python", source, "```"]
    return "\n".join(lines)


def parse(text):
    """{criterion: bool}, or None if unreadable or incomplete.

    A partial verdict is rejected rather than scored: a fraction over a
    denominator the model chose is not a measurement.
    """
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(got, dict):
        return None
    if set(got) != set(CRITERIA):
        return None
    if not all(isinstance(v, bool) for v in got.values()):
        return None
    return got


def summarize(verdict):
    """judge_ok distinguishes 'could not judge' from 'judged, criteria unmet'.

    run_model returns None for a timeout, a crash AND a session limit alike.
    A refused session is not a verdict; this repo has already archived one as
    a real result and then locked it.
    """
    if verdict is None:
        return {"judge_ok": False, "judge_score": None, "judge_detail": {}}
    met = sum(1 for v in verdict.values() if v)
    return {"judge_ok": True, "judge_score": met / len(verdict),
            "judge_detail": verdict}


def judge(clone, task):
    source = extract(clone, task)
    if source is None:
        return summarize(None)
    text = validate.run_model(build_prompt(source), cwd=str(clone))
    return summarize(parse(text))


if __name__ == "__main__":
    print(__doc__)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_bench_grade_judge.py`
Expected: all PASS, exit 0

- [ ] **Step 5: Wire the judge into the replay driver**

In `bench/regrade.py`, add the import beside the others:

```python
import grade_judge
```

Add the flag inside `main`, after the existing `--limit` line:

```python
    ap.add_argument("--judge", action="store_true",
                    help="also run the judge: ONE claude -p session per artifact")
```

And merge the judge fields into the row, replacing the `row.update(probe(e, clone))` line with:

```python
                row.update(probe(e, clone))
                if args.judge:
                    row.update(grade_judge.judge(clone, e["task"]))
                    if row["judge_ok"] and row["probe_total"]:
                        row["graded"] = (row["probe_score"] + row["judge_score"]) / 2
                    else:
                        row["graded"] = None
```

- [ ] **Step 6: Verify the whole suite still passes**

Run: `for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAIL $f"; done`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add bench/grade_judge.py bench/regrade.py tests/test_bench_grade_judge.py
git commit -F - <<'EOF'
feat(bench): judge half of graded scoring, behind --judge

Three criteria an assertion cannot check, scored by one unsteered claude -p
turn per artifact via validate.run_model. Reported alongside the probe score,
never merged into it -- a disagreement between the halves is the signal.

judge_ok carries the weight here. run_model returns None for a timeout, a
crash and a session limit alike, and a refused session is not a verdict. This
repo has already archived a rate-limited session as a real result and then
locked it behind the archive guard.

A partial verdict is rejected rather than scored: a fraction over a
denominator the model picked is not a measurement.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Run it, and report against the pre-registered falsifier

**Files:**
- Create: `bench/graded.jsonl` (generated)
- Modify: `bench/RESULTS.md` — new section and a register row

**Interfaces:**
- Consumes: everything above.
- Produces: the graded corpus and its write-up.

- [ ] **Step 1: Check the session meter before the judge batch**

The judge is 42 sessions. Sessions and token quota are separate meters and the session one binds.

Run: `claude -p "Reply with exactly: OK" --model claude-opus-5 ; echo "exit=$?"`
Expected: `OK` and `exit=0`. `exit=1` with "You've hit your session limit" means stop and wait.

- [ ] **Step 2: Run the probe half across the whole corpus**

Run: `python3 bench/regrade.py`
Expected: one line per gradable entry, then `wrote N row(s)`.

- [ ] **Step 3: Evaluate the pre-registered falsifier BEFORE reading any artifact**

```bash
python3 -c "
import json, collections
rows=[json.loads(l) for l in open('bench/graded.jsonl')]
c=collections.Counter(r['probe_score'] for r in rows)
mid=sum(v for k,v in c.items() if 0.0 < k < 1.0)
print('rows', len(rows), 'distinct scores', len(c))
print('at 0.0 or 1.0:', c[0.0]+c[1.0], ' strictly between:', mid)
for k in sorted(c): print('  %.3f  %d' % (k, c[k]))
"
```

Spec §4: **if the distribution is bimodal — everything at 0.0 or 1.0 with the middle as empty as the 1-in-96 the binary scale produced — the design has failed and is reported as failed.** It is not rescued by adding or dropping probes.

- [ ] **Step 4: Verify the subsumption invariant**

Every artifact whose `resolved` was true must pass at least the probes that correspond to the old `fail_to_pass` tests. A violation is a harness bug, not a finding.

```bash
python3 -c "
import json
g={r['clone']: r for r in map(json.loads, open('bench/graded.jsonl'))}
res=[json.loads(l) for l in open('bench/results.jsonl')]
trap={'test_tokenize_recovers_a_flat_dict_value','test_tokenize_recovers_a_nested_dict_value',
      'test_unknown_when_match_past_file_cap','test_unknown_when_match_past_byte_cap'}
bad=0
for r in res:
    if not r.get('resolved'): continue
    key='%s-%s-%d' % (r['task'], r['arm'], r['run'])
    row=g.get(key)
    if not row: continue
    missed=[k for k,v in row['probe_detail'].items() if k in trap and not v]
    if missed: bad+=1; print('VIOLATION', key, missed)
print('violations:', bad)
"
```

Expected: `violations: 0`. Investigate any violation before proceeding.

- [ ] **Step 5: Run the judge half**

Run: `python3 bench/regrade.py --judge`
Expected: 42 sessions, roughly one turn each. Watch the console, not only the JSONL — the driver prints `ERROR` and continues.

- [ ] **Step 6: Report excluded rows**

```bash
python3 -c "
import json
rows=[json.loads(l) for l in open('bench/graded.jsonl') if l.strip()]
j=[r for r in rows if 'judge_ok' in r]
print('judged rows:', len(j), 'excluded (judge_ok false):', sum(1 for r in j if not r['judge_ok']))
"
```

- [ ] **Step 7: Write up the result in `bench/RESULTS.md`**

Add a section covering: the falsifier verdict from Step 3; the probe-score distribution; control cells specifically, since whether control lands in the mid-range decides E4; the subsumption check from Step 4; excluded judge rows; and where probe and judge disagree. Add a register row at the top of the file. Report probe and judge separately and never quote `graded` alone.

- [ ] **Step 8: Commit**

```bash
git add bench/graded.jsonl bench/RESULTS.md
git commit -F - <<'EOF'
bench: graded scoring run across the archived corpus

Probe half across every gradable archived artifact at zero session cost, plus
the judge half at one session each. Falsifier from spec §4 evaluated before
any artifact was read; verdict is in the write-up.

Probe and judge are reported separately. The combined `graded` is never
quoted alone, and its unweighted mean remains a guess with nothing behind it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

## Self-Review

**Spec coverage.** §1 degenerate-gradation evidence → motivates Tasks 2-3, checked in Task 6 Step 3. §2 replay viability → Task 4. §3.1 probe suite → Tasks 1-3, all 20 probes present. §3.2 judge → Task 5. §3.3 three recorded numbers and `graded.jsonl` → Task 4 Step 3 and Task 5 Step 5. §3.4 replay driver → Task 4. §3.5 calibration → **deliberately deferred**, see below. §4 pre-registration → Task 6 Steps 3-4. §5 threats → carried into the code comments they bear on. §6 outcome reading → Task 6 Step 7.

**One deliberate deviation from the spec.** §3.5 specifies a calibration corpus for the judge, and no task builds one. It is deferred because calibration needs known-correct graded verdicts, and until Task 6 Step 5 runs there is no evidence about whether the judge half disagrees with the probes at all. Building a corpus first would be tuning a rubric against examples written for it, which is the failure `bench/critique-calibration/README.md` exists to prevent. If Step 5 shows the halves disagreeing, calibration becomes the next plan. **This is a scope reduction against an approved spec and needs sign-off.**

**Placeholder scan.** No TBD, TODO, or "handle edge cases". Every code step carries runnable code.

**Type consistency.** `probe_score`, `probe_passed`, `probe_total`, `probe_detail`, `judge_ok`, `judge_score`, `judge_detail`, `graded` are spelled identically in Tasks 4, 5 and 6. `suite_for` and `target_for` share the `task == base or task.startswith(base + "-")` prefix rule, so transfer and umbrella variants route to the same suite in both modules.
