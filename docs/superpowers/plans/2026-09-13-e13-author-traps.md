# E13 Author Traps (through the control screen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build E13's three candidate author tasks (C, D, E), decide their graded tests with a zero-session pre-flight, and leave the control screen ready to run.

**Architecture:** A per-test runner makes every test file gradeable. Shared stub helpers blank the target functions. `bench/e13_preflight.py` runs each candidate's tests three ways (stub, historical bug, transplanted fix), computes the graded set, and writes finished task entries into `bench/tasks.json`, but only for candidates that pass. `bench/run.py` gains a plugin-commit fingerprint and a guard against empty `fail_to_pass`. A screen script and a screen reader follow the E11 and E12 patterns.

**Tech Stack:** Python 3.9 standard library only, bash, git. Tests are stdlib-style files with a per-test catching runner, and also run under `python3 -m pytest -q`.

**Spec:** `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md`

**Scope:** spec §1–§3 and the parts of §9 they need. Distillation, qualification, probe batches and the outcome test (§5–§8) get their own plan once the screen results are in, because which candidates survive changes that work.

## Global Constraints

- Standard library only. Add no dependencies.
- Change nothing under `scripts/`. Don't touch `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` or `bench/real_path_check.py`, which belong to the parallel `in_scope` session.
- The Bash tool ignores `set -e`, so give every step that must block a commit an explicit `|| exit 1`.
- The shell is zsh, which doesn't word-split unquoted variables. Do loops over lists in Python or with arrays.
- No committed file may contain the operator's absolute home path.
- End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- `bench/tasks.json` must be written as `json.dumps(data, indent=2) + "\n"`, which reproduces the file byte for byte.
- This plan spends **zero sessions**. It ends with the screen ready. Running the screen spends sessions and needs the user's go-ahead.

## File Structure

| file | status | responsibility |
| --- | --- | --- |
| `bench/run_named_tests.py` | create | Runs a stdlib-style test file one test at a time, printing `PASS`/`FAIL` per test and never aborting |
| `tests/test_bench_named_tests.py` | create | Tests for the runner |
| `bench/run.py` | modify | `plugin_commit()`; `environment(plugin_dir)`; `ENV` set once `plugin_dir` is known; `check_config` rejects an empty `fail_to_pass` |
| `tests/test_bench_run.py` | modify | Tests for the three `run.py` changes |
| `bench/stubs/_stub.py` | create | `replace_functions(path, stubs)`, an AST-located replacement of top-level functions |
| `bench/stubs/stub_verdict_from.py` | create | Stub for trap C |
| `bench/stubs/stub_transcript_slice.py` | create | Stub for trap D |
| `bench/stubs/stub_store_dir.py` | create | Stub for trap E |
| `tests/test_bench_stubs.py` | create | Tests for `_stub.py` |
| `bench/e13_preflight.py` | create | Candidate definitions, transplant, grading, validity, task entries, and the three-run driver |
| `tests/test_bench_e13_preflight.py` | create | Tests for the pure functions in the pre-flight |
| `bench/e13_screen_read.py` | create | Reads the screen in spec §3 order |
| `tests/test_bench_e13_screen_read.py` | create | Tests for the reader |
| `bench/e13_screen.sh` | create | The screen batch, with guards and `--dry-run` |
| `bench/tasks.json` | modify | Author tasks, written by the pre-flight, for candidates that pass |

---

### Task 1: A per-test runner that never aborts

`bench/run.py::score` counts only `PASS <name>` lines, and a name that appears in neither a pass line nor a fail line counts as failed. `tests/test_draft.py`'s own runner aborts at its first failure, which would hide every later test from `score()`. This runner is D's grading command (spec §2.2), and it's how the pre-flight runs every candidate's tests.

**Files:**
- Create: `bench/run_named_tests.py`
- Test: `tests/test_bench_named_tests.py`

**Interfaces:**
- Produces: CLI `python3 bench/run_named_tests.py <test_file> [test_name ...]`. It prints one `PASS <name>` or `FAIL <name>: <repr>` line per test and exits 1 if anything failed. With no names it runs every `test_*` function in sorted order. Importable helpers are `load(path) -> module` and `run(module, names=None) -> int` (the failure count).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_named_tests.py`:

```python
"""Tests for bench/run_named_tests.py. Run: python3 tests/test_bench_named_tests.py"""
import pathlib
import subprocess
import sys
import tempfile

RUNNER = pathlib.Path(__file__).resolve().parent.parent / "bench" / "run_named_tests.py"

SAMPLE = '''
import sys

def test_a_passes():
    pass

def test_b_fails():
    raise AssertionError("boom")

def test_c_exits():
    sys.exit(3)

def test_d_passes_after_failures():
    pass

def helper_not_a_test():
    raise RuntimeError("must never run")
'''


def _run(*args):
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "test_sample.py"
        f.write_text(SAMPLE, encoding="utf-8")
        r = subprocess.run([sys.executable, str(RUNNER), str(f)] + list(args),
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout.splitlines()


def test_every_test_runs_even_after_failures():
    rc, lines = _run()
    assert "PASS test_a_passes" in lines
    assert any(l.startswith("FAIL test_b_fails:") for l in lines)
    assert any(l.startswith("FAIL test_c_exits:") for l in lines), lines
    assert "PASS test_d_passes_after_failures" in lines, "an earlier failure aborted the run"
    assert not any("helper_not_a_test" in l for l in lines)
    assert rc == 1


def test_named_tests_run_only_those():
    rc, lines = _run("test_a_passes", "test_d_passes_after_failures")
    assert lines == ["PASS test_a_passes", "PASS test_d_passes_after_failures"], lines
    assert rc == 0


def test_a_missing_name_is_a_failure():
    rc, lines = _run("test_a_passes", "test_nope")
    assert "PASS test_a_passes" in lines
    assert any(l.startswith("FAIL test_nope:") for l in lines)
    assert rc == 1


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

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_bench_named_tests.py`
Expected: every test prints `FAIL`, because `bench/run_named_tests.py` doesn't exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `bench/run_named_tests.py`:

```python
#!/usr/bin/env python3
"""Run a stdlib-style test file one test at a time, catching each failure.

    python3 bench/run_named_tests.py tests/test_x.py [test_name ...]

Prints `PASS <name>` or `FAIL <name>: <error>` per test, which is the format
bench/run.py::score counts. With no names, runs every `test_*` function in
sorted order. Exits 1 if any test failed or a named test does not exist.

Exists because some of this repo's test files abort at their first failure
(tests/test_draft.py's runner has no try/except), and score() counts a test it
never sees as failed, so one early failure would zero every later graded test.
SystemExit is caught too: tests that drive a main() can raise it.
"""
import importlib.util
import pathlib
import sys


def load(path):
    path = pathlib.Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def run(module, names=None):
    tests = sorted(n for n, v in vars(module).items()
                   if n.startswith("test_") and callable(v))
    failures = 0
    for name in (names or tests):
        fn = getattr(module, name, None)
        if not name.startswith("test_") or not callable(fn):
            print("FAIL %s: no such test" % name)
            failures += 1
            continue
        try:
            fn()
            print("PASS %s" % name)
        except (Exception, SystemExit) as err:
            failures += 1
            print("FAIL %s: %r" % (name, err))
    return failures


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    return 1 if run(load(argv[0]), argv[1:]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_bench_named_tests.py && python3 -m pytest -q tests/test_bench_named_tests.py`
Expected: three `PASS` lines and exit 0, then `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add bench/run_named_tests.py tests/test_bench_named_tests.py || exit 1
git commit -q -m "bench: a test runner that records every test, never aborting at the first failure

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 2: Record the plugin commit on every row, and refuse an empty `fail_to_pass`

Spec §9 requires every row to record which commit of the plugin under test ran. Today `env` records installed plugins but not `--plugin-dir`. Separately, `score()` returns `{}` for an empty `fail_to_pass`, and `all({}.values())` is `True`, so a task with nothing to grade reads every run as resolved. `check_config` must refuse that.

**Files:**
- Modify: `bench/run.py` (`environment()`, a new `plugin_commit()`, `check_config()`, and the `ENV` assignment in `main()`)
- Test: `tests/test_bench_run.py`

**Interfaces:**
- Produces: `bench_run.plugin_commit(plugin_dir) -> str`, which returns `"<sha>"`, `"<sha>+dirty"` when `scripts/`, `hooks/`, `skills/` or `.claude-plugin/` has uncommitted changes, or `""` when `plugin_dir` isn't a git checkout.
- Produces: `bench_run.environment(plugin_dir=None) -> {"cli": str, "plugins": dict, "plugin_commit": str}`.
- Produces: `check_config` returns a complaint containing `"fail_to_pass is empty"` for such a task.

- [ ] **Step 1: Write the failing tests**

Add these to `tests/test_bench_run.py`, above the `if __name__ == "__main__":` block:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest -q tests/test_bench_run.py -k "plugin_commit or environment_carries or grades_nothing"`
Expected: 4 failed. `plugin_commit` doesn't exist yet, `environment()` takes no argument, and `check_config` doesn't complain about an empty list.

- [ ] **Step 3: Write the minimal implementation**

In `bench/run.py`, replace the whole `environment()` function with:

```python
# The paths that make up the plugin under test. Dirt anywhere else -- above all
# bench/results.jsonl, which every batch appends to -- is not a change to it.
PLUGIN_PATHS = ("scripts", "hooks", "skills", ".claude-plugin")


def plugin_commit(plugin_dir):
    """The plugin under test as `<sha>`, `<sha>+dirty`, or "" if not a checkout.

    `env` records installed plugins, but the plugin a batch actually tests comes
    from --plugin-dir, which it never recorded. E13 spec section 9: with another
    session editing retrieve.py in parallel, a row must say which code ran.
    Never raises.
    """
    try:
        head = subprocess.run(["git", "-C", str(plugin_dir), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        if head.returncode:
            return ""
        dirt = subprocess.run(["git", "-C", str(plugin_dir), "status", "--porcelain",
                               "--", *PLUGIN_PATHS],
                              capture_output=True, text=True, timeout=30)
        return head.stdout.strip() + ("+dirty" if dirt.stdout.strip() else "")
    except Exception:
        return ""


def environment(plugin_dir=None):
    """CLI build, installed plugin revisions, and the commit of the plugin under
    test, for the row. Never raises: a missing file or a slow CLI must not cost
    a batch."""
    try:
        cli = sh("claude --version", timeout=30).stdout.strip()
    except Exception:
        cli = ""
    try:
        raw = (Path.home() / ".claude" / "plugins"
               / "installed_plugins.json").read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        data = {}
    return {"cli": cli, "plugins": plugin_shas(data),
            "plugin_commit": plugin_commit(plugin_dir) if plugin_dir else ""}
```

In `check_config()`, inside the `for task in cfg["tasks"]:` loop and directly after the `repo is not a git checkout` check, add:

```python
        if not task.get("fail_to_pass"):
            bad.append("%s: fail_to_pass is empty -- score() would read every run "
                       "as resolved" % task["id"])
```

In `main()`, delete these two lines:

```python
    global ENV
    ENV = environment()
```

and add them directly after `plugin_dir = Path(cfg["plugin_dir"])`, now passing the plugin directory:

```python
    global ENV
    ENV = environment(plugin_dir)
```

- [ ] **Step 4: Run the tests to verify they pass, and that the live config still checks clean**

Run: `python3 -m pytest -q tests/test_bench_run.py && python3 bench/run.py --check`
Expected: the whole file passes, and `config ok: 10 task(s), all paths resolve`. Every existing task already has a non-empty `fail_to_pass`.

- [ ] **Step 5: Commit**

```bash
git add bench/run.py tests/test_bench_run.py || exit 1
git commit -q -m "bench: record the plugin commit on every row, refuse a task that grades nothing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 3: Stub helper and the three stub scripts

Each author task blanks its target function or functions at the fix's parent commit (spec §2). The helper finds functions through the AST rather than a regex. It keeps a function's **existing docstring byte for byte**, taken from the source, so C and D carry the parent's own docstrings with no retyping, and E, whose functions had none, gets a supplied one.

**Files:**
- Create: `bench/stubs/_stub.py`
- Create: `bench/stubs/stub_verdict_from.py`, `bench/stubs/stub_transcript_slice.py`, `bench/stubs/stub_store_dir.py`
- Test: `tests/test_bench_stubs.py`

**Interfaces:**
- Produces: `stub_functions(path, names, docstrings=None) -> None`. For each top-level function in `names`, it keeps the signature and replaces the body with the docstring plus `raise NotImplementedError("implement me")`. The docstring is the existing one verbatim, or `docstrings[name]`: exact source lines including indentation and quotes, used only when given. It raises `ValueError` if a name isn't a top-level function, and the result must still parse.
- Produces: three stub scripts, each run as `python3 <script>` with `cwd` at a clone root and exiting 0 on success, 1 on failure.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_stubs.py`:

```python
"""Tests for bench/stubs/_stub.py. Run: python3 tests/test_bench_stubs.py"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench" / "stubs"))
from _stub import stub_functions

MODULE = '''import os


def keeps_its_docstring(a, b=2):
    """First line.

      Odd   spacing   that must survive exactly.
    """
    return a + b


def has_no_docstring(scope, name):
    return os.path.join(scope, name)


def untouched():
    return "still here"
'''

NEW_DOC = '''    """Supplied contract.

    Second line.
    """
'''


def _stubbed(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "mod.py"
        p.write_text(MODULE, encoding="utf-8")
        stub_functions(p, ["keeps_its_docstring", "has_no_docstring"], **kwargs)
        return p.read_text(encoding="utf-8")


def test_existing_docstring_is_kept_byte_for_byte():
    out = _stubbed(docstrings={"has_no_docstring": NEW_DOC})
    assert '    """First line.\n\n      Odd   spacing   that must survive exactly.\n    """\n' in out
    assert "return a + b" not in out


def test_a_supplied_docstring_is_used_where_none_existed():
    out = _stubbed(docstrings={"has_no_docstring": NEW_DOC})
    assert NEW_DOC in out
    assert "os.path.join" not in out


def test_stubbed_functions_raise_and_the_rest_still_works():
    ns = {}
    exec(compile(_stubbed(docstrings={"has_no_docstring": NEW_DOC}), "mod.py", "exec"), ns)
    for name, args in (("keeps_its_docstring", (1,)), ("has_no_docstring", ("a", "b"))):
        try:
            ns[name](*args)
        except NotImplementedError:
            pass
        else:
            raise AssertionError("%s did not raise NotImplementedError" % name)
    assert ns["untouched"]() == "still here"
    assert ns["keeps_its_docstring"].__code__.co_varnames[:2] == ("a", "b")


def test_a_missing_function_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "mod.py"
        p.write_text(MODULE, encoding="utf-8")
        try:
            stub_functions(p, ["no_such_function"])
        except ValueError:
            pass
        else:
            raise AssertionError("a missing function must be refused")
        assert p.read_text(encoding="utf-8") == MODULE, "a refused stub must not write"


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

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_bench_stubs.py`
Expected: an `ImportError` / `ModuleNotFoundError` for `_stub`, and a non-zero exit.

- [ ] **Step 3: Write the helper**

Create `bench/stubs/_stub.py`:

```python
"""Blank top-level functions for an author-mode bench task.

A function keeps its signature and its existing docstring, byte for byte from
the source, so a stub reproduces what the historical author had in front of
them without anyone retyping it. A function with no docstring gets the one the
caller supplies. Functions are located through the AST, not a regex, so a
decorator or an unusual signature cannot shift the cut.
"""
import ast
import pathlib

RAISE = '    raise NotImplementedError("implement me")\n'


def _docstring_lines(node, lines):
    first = node.body[0]
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return lines[first.lineno - 1:first.end_lineno]
    return None


def stub_functions(path, names, docstrings=None):
    docstrings = docstrings or {}
    path = pathlib.Path(path)
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    missing = [n for n in names if n not in nodes]
    if missing:
        raise ValueError("no top-level function named %s in %s" % (missing, path))
    for name in sorted(names, key=lambda n: nodes[n].lineno, reverse=True):
        node = nodes[name]
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        header = lines[start:node.body[0].lineno - 1]
        if name in docstrings:
            doc = docstrings[name].splitlines(keepends=True)
        else:
            doc = _docstring_lines(node, lines)
            if doc is None:
                raise ValueError("%s has no docstring and none was supplied" % name)
        lines[start:node.end_lineno] = header + doc + [RAISE]
    out = "".join(lines)
    ast.parse(out)
    path.write_text(out, encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_bench_stubs.py && python3 -m pytest -q tests/test_bench_stubs.py`
Expected: four `PASS` lines and exit 0, then `4 passed`.

- [ ] **Step 5: Write the three stub scripts**

Create `bench/stubs/stub_verdict_from.py`:

```python
#!/usr/bin/env python3
"""E13 trap C: blank validate.verdict_from so the model must author it.

The parent commit's own docstring stays, verbatim. It says a criterion must
quote "the skill text" as "a verbatim span". An implementer who takes that
literally writes an exact substring match, which is the historical bug fixed in
c0d7d88: a critic re-wraps quotes across lines. It is also silent on measuring
the evidence floor on the raw span, the second trap. Nothing is added to it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/validate.py", ["verdict_from"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed verdict_from")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `bench/stubs/stub_transcript_slice.py`:

```python
#!/usr/bin/env python3
"""E13 trap D: blank draft.transcript_slice so the model must author it.

The parent commit's own docstring stays, verbatim. It already says the tail
fallback is for a transcript whose entries carry no parseable stamp. The
historical bug (fixed in 521f609) fell back whenever the window matched
nothing, handing the drafter an unrelated slice of session. That the rule is
stated and was still broken is exactly the trap under measurement, and the
screen may find a fresh model reads it correctly (E13 spec, threat 3).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/draft.py", ["transcript_slice"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed transcript_slice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `bench/stubs/stub_store_dir.py`:

```python
#!/usr/bin/env python3
"""E13 trap E: blank save_skill.store_dir and native_dir so the model must author them.

Neither function had a docstring at the parent commit, and an author task needs
a contract, so this supplies one. That is a departure from the historical
condition (E13 spec, threat 2). Each docstring names the directory layout and
the base directory for each scope, and says nothing about resolving paths. The
historical bug (fixed in 06173b0) returned the project root unresolved, so a
relative "." never compared equal to the absolute home directory and re-saving
a skill from $HOME collided with itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions

DOCSTRINGS = {
    "store_dir": '''    """Directory a saved skill of this kind and name is stored in.

    <base>/.claude/skillforge/skills/<name>, or .../antiskills/<name> for an
    antiskill, where <base> is `project_root` for project scope and the home
    directory for global scope.
    """
''',
    "native_dir": '''    """Directory the hot copy of a skill is materialized in.

    <base>/.claude/skills/skillforge-hot/<name>, with <base> chosen as in
    store_dir.
    """
''',
}


def main():
    try:
        stub_functions("scripts/save_skill.py", ["store_dir", "native_dir"], DOCSTRINGS)
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed store_dir, native_dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Check each script against its real parent commit, with zero sessions**

Run:

```bash
python3 - <<'PY' || exit 1
import pathlib, subprocess, sys, tempfile
ROOT = pathlib.Path(".").resolve()
CASES = [("c0d7d88", "bench/stubs/stub_verdict_from.py", "scripts/validate.py"),
         ("521f609", "bench/stubs/stub_transcript_slice.py", "scripts/draft.py"),
         ("06173b0", "bench/stubs/stub_store_dir.py", "scripts/save_skill.py")]
ok = True
for fix, script, source in CASES:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "worktree", "add", "-q", "--detach", tmp, fix + "~1"],
                       cwd=str(ROOT), check=True)
        try:
            r = subprocess.run([sys.executable, str(ROOT / script)], cwd=tmp,
                               capture_output=True, text=True)
            text = (pathlib.Path(tmp) / source).read_text(encoding="utf-8")
            good = r.returncode == 0 and "NotImplementedError" in text
            print("%-40s rc=%d %s" % (script, r.returncode, "ok" if good else "FAILED " + r.stderr))
            ok &= good
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", tmp], cwd=str(ROOT), check=True)
sys.exit(0 if ok else 1)
PY
```

Expected: three `rc=0 ok` lines. Whether the stubbed tests really fail, and whether the docstrings match the parent, is verified by the pre-flight in Task 5.

- [ ] **Step 7: Commit**

```bash
git add bench/stubs/_stub.py bench/stubs/stub_verdict_from.py bench/stubs/stub_transcript_slice.py bench/stubs/stub_store_dir.py tests/test_bench_stubs.py || exit 1
git commit -q -m "bench: stub helper and E13's three stub scripts

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 4: Pre-flight logic, as pure functions

This task holds everything the pre-flight decides that doesn't need a clone: which definitions a fix changed, how to transplant them onto the parent, the graded set and validity rules from spec §2.1, the author prompt, and the task entry. Task 5 wires these to real clones.

**Files:**
- Create: `bench/e13_preflight.py` (pure functions and `CANDIDATES` only; Task 5 adds the driver)
- Test: `tests/test_bench_e13_preflight.py`

**Interfaces:**
- Produces, all in `bench/e13_preflight.py`:
  - `CANDIDATES: dict[str, dict]`, keyed `"C"`, `"D"` and `"E"`. Each value has the keys `id`, `fix`, `source`, `test_path`, `stub`, `functions` (list), `own_runner` (bool) and `verbatim_docstring` (bool).
  - `changed_definitions(parent_src, fix_src) -> list[str]`: the top-level function and class names that are new in, or differ in, `fix_src`, sorted.
  - `transplant(parent_src, fix_src) -> (str, list[str])`: `parent_src` with every changed definition taken from `fix_src` and every import the fix added. It returns the new source and the transplanted names.
  - `test_names(src) -> set[str]`: the top-level `test_*` function names.
  - `parse_results(stdout) -> dict[str, bool]`: parsed from `PASS name` / `FAIL name: ...` lines.
  - `assess(stub, original, fix, fix_added, docstring_ok=True) -> (list[str], list[str])`: the graded tests and the problems. An empty problems list means valid.
  - `signatures(src, names) -> list[str]`: for example `"verdict_from(findings, text)"`.
  - `author_prompt(source, sigs, test_path) -> str`
  - `task_entry(letter, cand, graded, sigs) -> dict`: `{root}` stays a literal placeholder, unexpanded.
  - `upsert(cfg, entry) -> dict`: replaces the task with the same `id`, or appends.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_e13_preflight.py`:

```python
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

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_bench_e13_preflight.py`
Expected: a `ModuleNotFoundError` for `e13_preflight`, and a non-zero exit.

- [ ] **Step 3: Write the minimal implementation**

Create `bench/e13_preflight.py`:

```python
#!/usr/bin/env python3
"""E13 pre-flight: build each candidate's author task and decide its graded tests.

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 2.

Zero sessions. Each candidate's fix-commit test file runs three ways against the
parent commit's code: with the stub, with the parent's original function (the
historical bug), and with the fix's changed definitions transplanted in. The
graded set is every test that fails under the stub and passes with the fix.
Only a candidate that passes every validity rule is written into
bench/tasks.json. An entry with an empty or unvalidated fail_to_pass grades
nothing, and score() reads that as resolved.
"""
import ast
import re

SPEC = "docs/superpowers/specs/2026-09-13-e13-author-traps-design.md"

CANDIDATES = {
    "C": {"id": "sf-author-verdict-from", "fix": "c0d7d88", "source": "scripts/validate.py",
          "test_path": "tests/test_validate.py", "stub": "bench/stubs/stub_verdict_from.py",
          "functions": ["verdict_from"], "own_runner": True, "verbatim_docstring": True},
    "D": {"id": "sf-author-transcript-slice", "fix": "521f609", "source": "scripts/draft.py",
          "test_path": "tests/test_draft.py", "stub": "bench/stubs/stub_transcript_slice.py",
          "functions": ["transcript_slice"], "own_runner": False, "verbatim_docstring": True},
    "E": {"id": "sf-author-store-dir", "fix": "06173b0", "source": "scripts/save_skill.py",
          "test_path": "tests/test_save_skill.py", "stub": "bench/stubs/stub_store_dir.py",
          "functions": ["store_dir", "native_dir"], "own_runner": True,
          "verbatim_docstring": False},
}

RESULT_RX = re.compile(r"^(PASS|FAIL) (test_\w+)")


def _top_level(src):
    """({name: (start, end, text)} for defs and classes, [(start, end, text)] for imports)."""
    lines = src.splitlines(keepends=True)
    defs, imports = {}, []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            defs[node.name] = (start, node.end_lineno, "".join(lines[start:node.end_lineno]))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append((node.lineno - 1, node.end_lineno,
                            "".join(lines[node.lineno - 1:node.end_lineno])))
    return defs, imports


def changed_definitions(parent_src, fix_src):
    pdefs, _ = _top_level(parent_src)
    fdefs, _ = _top_level(fix_src)
    return sorted(n for n, (_, _, text) in fdefs.items()
                  if n not in pdefs or pdefs[n][2] != text)


def transplant(parent_src, fix_src):
    """Parent source carrying every definition and import the fix added or changed.

    New definitions go directly before the first replaced one, so a helper sits
    beside its caller. Returns (source, transplanted names).
    """
    # ponytail: definitions and imports only. A fix that changes a module-level
    # constant is not carried; run 3 then fails, and the pre-flight reports it.
    names = changed_definitions(parent_src, fix_src)
    if not names:
        return parent_src, []
    pdefs, pimports = _top_level(parent_src)
    fdefs, fimports = _top_level(fix_src)
    lines = parent_src.splitlines(keepends=True)
    edits = [(pdefs[n][0], pdefs[n][1], fdefs[n][2]) for n in names if n in pdefs]
    new = sorted((n for n in names if n not in pdefs), key=lambda n: fdefs[n][0])
    if new:
        anchor = min((pdefs[n][0] for n in names if n in pdefs), default=len(lines))
        edits.append((anchor, anchor,
                      "".join(fdefs[n][2].rstrip("\n") + "\n\n\n" for n in new)))
    have = {text.strip() for _, _, text in pimports}
    added = [text for _, _, text in fimports if text.strip() not in have]
    if added:
        at = max((end for _, end, _ in pimports), default=0)
        edits.append((at, at, "".join(added)))
    # Bottom-up, and a replacement before an insertion at the same line, so no
    # edit shifts the line numbers of one still to come.
    for start, end, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        lines[start:end] = [text]
    out = "".join(lines)
    ast.parse(out)
    return out, names


def test_names(src):
    return {n.name for n in ast.parse(src).body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def parse_results(stdout):
    out = {}
    for line in stdout.splitlines():
        m = RESULT_RX.match(line.strip())
        if m:
            out[m.group(2)] = m.group(1) == "PASS"
    return out


def assess(stub, original, fix, fix_added, docstring_ok=True):
    """(graded tests, problems) under spec section 2.1. No problems means valid."""
    graded = sorted(t for t in fix if fix[t] is True and stub.get(t) is False)
    problems = []
    if not graded:
        problems.append("no graded tests: nothing fails with the stub and passes with the fix")
    unsatisfiable = sorted(t for t in fix_added if fix.get(t) is not True)
    if unsatisfiable:
        problems.append("tests the fix added do not pass with the fix transplanted: %s"
                        % unsatisfiable)
    if not any(original.get(t) is False for t in fix_added if t in graded):
        problems.append("the historical bug fails none of the graded tests the fix added")
    regressions = sorted(t for t in graded
                         if t not in fix_added and original.get(t) is not True)
    if regressions:
        problems.append("the historical function fails graded tests the fix did not add: %s"
                        % regressions)
    if not docstring_ok:
        problems.append("the stub's docstring differs from the parent's")
    return graded, problems


def signatures(src, names):
    nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    return ["%s(%s)" % (n, ast.unparse(nodes[n].args)) for n in names]


def author_prompt(source, sigs, test_path):
    """The existing author-task template, verbatim, with names substituted."""
    tail = ("do not modify anything under tests/. When you are done, run `python3 %s` "
            "and make sure you have not broken any test that was passing before your "
            "change." % test_path)
    if len(sigs) == 1:
        return ("%s has a function `%s` whose body raises NotImplementedError. Read its "
                "docstring for the contract and implement it. Do not change its signature, "
                "and %s" % (source, sigs[0], tail))
    return ("%s has functions %s whose bodies raise NotImplementedError. Read their "
            "docstrings for the contract and implement them. Do not change their "
            "signatures, and %s"
            % (source, " and ".join("`%s`" % s for s in sigs), tail))


def task_entry(letter, cand, graded, sigs):
    test_cmd = ("python3 %s" % cand["test_path"] if cand["own_runner"] else
                "python3 {root}/bench/run_named_tests.py %s %s"
                % (cand["test_path"], " ".join(graded)))
    return {
        "id": cand["id"],
        "mode": "author",
        "repo": "{root}",
        "fix_commit": cand["fix"],
        "test_path": cand["test_path"],
        "test_cmd": test_cmd,
        "setup_cmd": "true",
        "stub_cmd": "python3 {root}/%s" % cand["stub"],
        "fail_to_pass": list(graded),
        "prompt": author_prompt(cand["source"], sigs, cand["test_path"]),
        "skill": None,
        "skill_source_commit": None,
        "selection_rule": ("E13 trap %s (%s). No skill yet: control screen only until "
                           "distilled. Graded tests decided by bench/e13_preflight.py."
                           % (letter, SPEC)),
    }


def upsert(cfg, entry):
    for i, task in enumerate(cfg["tasks"]):
        if task["id"] == entry["id"]:
            cfg["tasks"][i] = entry
            return cfg
    cfg["tasks"].append(entry)
    return cfg
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_bench_e13_preflight.py && python3 -m pytest -q tests/test_bench_e13_preflight.py`
Expected: 14 `PASS` lines and exit 0, then `14 passed`. If `test_the_author_prompt_is_the_existing_template_verbatim` fails, fix `author_prompt` until it matches the prompt in `tasks.json`. Do not edit the prompt in `tasks.json`.

- [ ] **Step 5: Commit**

```bash
git add bench/e13_preflight.py tests/test_bench_e13_preflight.py || exit 1
git commit -q -m "bench: E13 pre-flight logic -- transplant, graded set, validity, task entries

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 5: The pre-flight driver, run for real (zero sessions)

This wires Task 4's logic to real clones. Each candidate is prepared three times (stub, original, fix), its tests run under `bench/run_named_tests.py`, and valid candidates are written into `bench/tasks.json`. No `claude` session is started, and every clone lives in a temporary directory.

**Files:**
- Modify: `bench/e13_preflight.py` (append `docstrings_match`, `run_variant`, `main`)
- Modify: `tests/test_bench_e13_preflight.py` (one test)
- Modify: `bench/tasks.json` (written by the tool, never by hand)

**Interfaces:**
- Consumes: `bench/run.py`'s `prepare(task, dest)`, `apply_hidden_tests(task, dest)`, `sh(cmd, cwd, timeout, env)`, `WORK` and `REPO_ROOT`; `bench/run_named_tests.py` (Task 1); the stub scripts (Task 3); and all of Task 4.
- Produces: the CLI `python3 bench/e13_preflight.py [--only C|D|E ...] [--write]`. It exits 0 only if every candidate checked was valid. With `--write`, only valid candidates are upserted into `bench/tasks.json`.
- Produces: `docstrings_match(stubbed_src, parent_src, names) -> bool`.

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_bench_e13_preflight.py`, above the `if __name__ == "__main__":` block:

```python
def test_docstrings_match_compares_raw_docstrings_of_named_functions():
    parent = 'def f(a):\n    """Exact  text.\n\n    More.\n    """\n    return a\n'
    same = 'def f(a):\n    """Exact  text.\n\n    More.\n    """\n    raise NotImplementedError("implement me")\n'
    edited = 'def f(a):\n    """Exact text.\n\n    More.\n    """\n    raise NotImplementedError("implement me")\n'
    assert pf.docstrings_match(same, parent, ["f"]) is True
    assert pf.docstrings_match(edited, parent, ["f"]) is False, "a collapsed double space is a change"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest -q tests/test_bench_e13_preflight.py -k docstrings_match`
Expected: 1 failed with `AttributeError: ... has no attribute 'docstrings_match'`.

- [ ] **Step 3: Append the driver to `bench/e13_preflight.py`**

Add these imports at the top of the file, after `import re`:

```python
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
```

Append at the end of the file:

```python
def docstrings_match(stubbed_src, parent_src, names):
    """True if every named function carries the same raw docstring in both."""
    def docs(src):
        nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
        return {n: ast.get_docstring(nodes[n], clean=False) if n in nodes else None
                for n in names}
    return docs(stubbed_src) == docs(parent_src)


def _git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True,
                          text=True, check=True).stdout


def run_variant(cand, variant, work):
    """Prepare one clone at the fix's parent and run its fix-commit tests.

    variant is "stub" (stub applied, then the hidden tests), "original" (the
    parent's own code with the fix's tests), or "fix" (the fix's changed
    definitions transplanted in). Returns ({test: passed}, clone path).
    """
    import run as bench_run
    task = {"id": "e13pf-%s-%s" % (cand["id"], variant), "repo": str(REPO_ROOT),
            "fix_commit": cand["fix"], "test_path": cand["test_path"],
            "setup_cmd": "true", "mode": "author" if variant == "stub" else "repair",
            "stub_cmd": "python3 %s" % (REPO_ROOT / cand["stub"])}
    dest = Path(work) / task["id"]
    bench_run.prepare(task, dest)
    if variant == "stub":
        bench_run.apply_hidden_tests(task, dest)
    elif variant == "fix":
        src = dest / cand["source"]
        fixed, _ = transplant(src.read_text(encoding="utf-8"),
                              _git("show", "%s:%s" % (cand["fix"], cand["source"])))
        src.write_text(fixed, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SKILLFORGE_")}
    r = bench_run.sh("python3 %s %s" % (ROOT / "run_named_tests.py", cand["test_path"]),
                     cwd=dest, timeout=900, env=env)
    return parse_results(r.stdout), dest


def _summary(results):
    return "%d pass / %d fail" % (sum(results.values()), sum(not v for v in results.values()))


def main(argv=None):
    import run as bench_run
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", choices=sorted(CANDIDATES))
    ap.add_argument("--write", action="store_true",
                    help="write valid candidates into bench/tasks.json")
    args = ap.parse_args(argv)
    letters = args.only or sorted(CANDIDATES)
    work = Path(os.path.realpath(tempfile.mkdtemp(prefix="e13-preflight-")))
    bench_run.WORK = work
    valid = {}
    try:
        for letter in letters:
            cand = CANDIDATES[letter]
            parent_src = _git("show", "%s~1:%s" % (cand["fix"], cand["source"]))
            fix_added = (test_names(_git("show", "%s:%s" % (cand["fix"], cand["test_path"])))
                         - test_names(_git("show", "%s~1:%s" % (cand["fix"], cand["test_path"]))))
            stub, stub_dest = run_variant(cand, "stub", work)
            original, _ = run_variant(cand, "original", work)
            fix, _ = run_variant(cand, "fix", work)
            doc_ok = (not cand["verbatim_docstring"]) or docstrings_match(
                (stub_dest / cand["source"]).read_text(encoding="utf-8"),
                parent_src, cand["functions"])
            graded, problems = assess(stub, original, fix, fix_added, doc_ok)
            print("=== %s  %s  (fix %s)" % (letter, cand["id"], cand["fix"]))
            print("  stub:     %s" % _summary(stub))
            print("  original: %s" % _summary(original))
            print("  fix:      %s" % _summary(fix))
            print("  tests the fix added: %s" % sorted(fix_added))
            print("  graded (%d): %s" % (len(graded), graded))
            if problems:
                print("  INVALID: " + "; ".join(problems))
            else:
                print("  VALID")
                valid[letter] = task_entry(letter, cand, graded,
                                           signatures(parent_src, cand["functions"]))
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    if args.write and valid:
        path = ROOT / "tasks.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        for entry in valid.values():
            upsert(cfg, entry)
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print("wrote %s into bench/tasks.json" % sorted(e["id"] for e in valid.values()))
    return 0 if len(valid) == len(letters) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python3 -m pytest -q tests/test_bench_e13_preflight.py`
Expected: `15 passed`.

- [ ] **Step 5: Run the pre-flight for real, without writing**

Run: `python3 bench/e13_preflight.py`
Expected, for each of C, D and E: a `stub` line with failures, an `original` line, a `fix` line, the tests the fix added, and a graded list, ending in either `VALID` or `INVALID: <problems>`. This starts no session.

- [ ] **Step 6: Gate on the result**

- **Every candidate VALID:** go to Step 7.
- **Any candidate INVALID: stop and report its problems to the user** before touching it. Spec §2.1 allows only two repairs, a justified `hidden_patch_cmd` or a grading-command change, and choosing one is a judgment call for the user. Valid candidates may still go through Step 7. An invalid one isn't written, and isn't screened unless the user approves a repair.

- [ ] **Step 7: Write the valid candidates and verify the file**

Run:

```bash
python3 bench/e13_preflight.py --write
python3 - <<'PY' || exit 1
import json, subprocess, sys
head = json.loads(subprocess.run(["git", "show", "HEAD:bench/tasks.json"],
                                 capture_output=True, text=True, check=True).stdout)
now = json.loads(open("bench/tasks.json", encoding="utf-8").read())
old_ids = [t["id"] for t in head["tasks"]]
unchanged = now["tasks"][:len(old_ids)] == head["tasks"]
new = [t["id"] for t in now["tasks"][len(old_ids):]]
print("existing tasks unchanged:", unchanged, "| added:", new)
empty = [t["id"] for t in now["tasks"] if not t.get("fail_to_pass")]
print("tasks with an empty fail_to_pass:", empty)
sys.exit(0 if unchanged and new and not empty else 1)
PY
python3 bench/run.py --check || exit 1
git diff --stat bench/tasks.json
```

Expected: `existing tasks unchanged: True`, the valid candidates' ids under `added:`, no task with an empty `fail_to_pass`, `config ok: <10 + number added> task(s), all paths resolve`, and a diff that adds lines only.

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 9: Commit, with the pre-flight's result in the message**

Put the tool's per-candidate lines from Step 5 (`graded (n)` and `VALID` or `INVALID`) under a `Pre-flight result:` heading in the message body. Then run:

```bash
git add bench/e13_preflight.py tests/test_bench_e13_preflight.py bench/tasks.json || exit 1
git commit -q -F - <<'MSG' || exit 1
bench: E13 pre-flight driver, and the author tasks it validated

Pre-flight result:
<the per-candidate graded and VALID/INVALID lines from Step 5>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

### Task 6: A screen reader that applies spec §3 in order

E12's first read went wrong by hand, so the screen gets a committed reader, built before any row exists. It reads the reference before any candidate, and reads no candidate while the reference is void or incomplete. A session refused at the session limit postpones the whole screen.

**Files:**
- Create: `bench/e13_screen_read.py`
- Test: `tests/test_bench_e13_screen_read.py`

**Interfaces:**
- Consumes: `bench/e12_read.py`'s `select(rows, windows)`, with the same window semantics: FROM exclusive, TO inclusive, `"-"` open.
- Produces: `read_screen(rows) -> {"screen": "postponed"|"void"|"incomplete"|"complete", "reason": str, "cells": {task_id: {"valid", "needed", "resolved", "rerun", "verdict"?}}}`. Candidate `verdict` is one of `"admitted"`, `"rejected"` or `"incomplete"`; the reference cell carries no verdict.
- Produces: CLI `python3 bench/e13_screen_read.py --window FROM TO`, repeatable.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e13_screen_read.py`:

```python
"""Tests for bench/e13_screen_read.py. Run: python3 tests/test_bench_e13_screen_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_screen_read as sr

REF = sr.REFERENCE
C, D, E = sr.CANDIDATES


def row(task, resolved=False, ok=True, tail=None, arm="control"):
    return {"task": task, "arm": arm, "resolved": resolved, "session_ok": ok,
            "session_tail": tail}


def ref_rows(resolved=0):
    return [row(REF, resolved=i < resolved) for i in range(sr.N_REFERENCE)]


def cand_rows(task, resolved=0, n=sr.N_CANDIDATE):
    return [row(task, resolved=i < resolved) for i in range(n)]


def test_zero_of_six_admits_and_one_resolved_rejects():
    res = sr.read_screen(ref_rows() + cand_rows(C) + cand_rows(D, resolved=1))
    assert res["screen"] == "complete", res
    assert res["cells"][C]["verdict"] == "admitted"
    assert res["cells"][D]["verdict"] == "rejected"
    assert E not in res["cells"], "a candidate with no rows was not screened"


def test_a_resolved_reference_voids_the_screen_and_hides_candidates():
    res = sr.read_screen(ref_rows(resolved=1) + cand_rows(C))
    assert res["screen"] == "void"
    assert C not in res["cells"], "candidates must not be read once the reference moved"


def test_an_unfinished_reference_reads_no_candidate():
    res = sr.read_screen(ref_rows()[:2] + cand_rows(C))
    assert res["screen"] == "incomplete"
    assert C not in res["cells"]


def test_a_session_limit_postpones_the_whole_screen():
    rows = ref_rows() + cand_rows(C, n=5) + [
        row(C, ok=False, tail="You've hit your session limit · resets 5:30pm")]
    res = sr.read_screen(rows)
    assert res["screen"] == "postponed"
    assert res["cells"] == {}, "a postponed screen is not read at all"


def test_any_other_refusal_leaves_the_cell_incomplete_and_counts_a_rerun():
    rows = ref_rows() + cand_rows(C, n=5) + [row(C, ok=False, tail="some other crash")]
    res = sr.read_screen(rows)
    cell = res["cells"][C]
    assert cell["verdict"] == "incomplete" and cell["rerun"] == 1 and cell["valid"] == 5
    assert res["screen"] == "incomplete"


def test_one_resolved_session_rejects_before_the_cell_is_full():
    res = sr.read_screen(ref_rows() + cand_rows(C, resolved=1, n=2))
    assert res["cells"][C]["verdict"] == "rejected"


def test_treatment_rows_are_not_part_of_the_screen():
    rows = ref_rows() + cand_rows(C) + [row(C, resolved=True, arm="treatment")]
    assert sr.read_screen(rows)["cells"][C]["verdict"] == "admitted"


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

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_bench_e13_screen_read.py`
Expected: a `ModuleNotFoundError` for `e13_screen_read`, and a non-zero exit.

- [ ] **Step 3: Write the minimal implementation**

Create `bench/e13_screen_read.py`:

```python
#!/usr/bin/env python3
"""Read E13's control screen in the order its spec fixes: the reference, then the candidates.

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 3.

Written before any screen row existed, because E12's first read went wrong by
hand. A session refused at the session limit postpones the whole screen, and
it is never read around. The reference is read before any candidate. While the
reference is void or incomplete, no candidate is read at all.

Rows are selected with --window FROM TO, exactly as in bench/e12_read.py
(FROM exclusive, TO inclusive, "-" for open), and the flag is repeatable.

Deterministic, 0 sessions. Run:

    python3 bench/e13_screen_read.py --window <SCREEN_START> -
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402  -- one window rule, not two

CANDIDATES = ("sf-author-verdict-from", "sf-author-transcript-slice", "sf-author-store-dir")
REFERENCE = "sf-author-fingerprint-preexisting"
N_CANDIDATE = 6
N_REFERENCE = 3
LIMIT_MARK = "session limit"


def _cell(control, task, needed):
    rows = [r for r in control if r.get("task") == task]
    valid = [r for r in rows if r.get("session_ok")]
    return {"valid": len(valid), "needed": needed,
            "resolved": sum(1 for r in valid if r.get("resolved")),
            "rerun": len(rows) - len(valid)}


def read_screen(rows):
    control = [r for r in rows if r.get("arm") == "control"]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in control):
        return {"screen": "postponed", "cells": {},
                "reason": "a session hit the session limit: re-run the whole screen "
                          "as one fresh batch (spec section 3)"}
    ref = _cell(control, REFERENCE, N_REFERENCE)
    out = {"cells": {REFERENCE: ref}}
    if ref["resolved"]:
        out.update(screen="void",
                   reason="the reference resolved, so the environment moved (spec section 3)")
        return out
    if ref["valid"] < N_REFERENCE:
        out.update(screen="incomplete",
                   reason="the reference is not fully measured, so no candidate is read yet")
        return out
    present = [t for t in CANDIDATES if any(r.get("task") == t for r in control)]
    for task in present:
        cell = _cell(control, task, N_CANDIDATE)
        cell["verdict"] = ("rejected" if cell["resolved"] else
                           "incomplete" if cell["valid"] < N_CANDIDATE else "admitted")
        out["cells"][task] = cell
    done = bool(present) and all(out["cells"][t]["verdict"] != "incomplete" for t in present)
    out.update(screen="complete" if done else "incomplete",
               reason="" if done else "a candidate is not fully measured, or none was screened")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", nargs=2, action="append", required=True,
                    metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in
            (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    res = read_screen(select(rows, args.window))
    print("screen: %s%s" % (res["screen"], " -- " + res["reason"] if res["reason"] else ""))
    for task, c in res["cells"].items():
        role = "reference" if task == REFERENCE else "candidate"
        print("  %-9s %-36s valid %d/%d  resolved %d  re-run %d  %s"
              % (role, task, c["valid"], c["needed"], c["resolved"], c["rerun"],
                 c.get("verdict", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_bench_e13_screen_read.py && python3 -m pytest -q tests/test_bench_e13_screen_read.py`
Expected: 7 `PASS` lines and exit 0, then `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add bench/e13_screen_read.py tests/test_bench_e13_screen_read.py || exit 1
git commit -q -m "bench: E13 screen reader -- reference first, a session limit postpones the screen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 7: The screen script, dry-run verified, then merge and push

This is the last task. The screen batch follows `bench/e11_screen.sh`, with three additions required by the spec and this plan: a guard that the plugin under test is clean, so every row's `plugin_commit` names real code; a session-allowance probe (spec §3); and `--dry-run`, so every guard can be verified without spending a session. The plan ends here, with the screen ready. **Running it spends sessions and needs the user's go-ahead.**

**Files:**
- Create: `bench/e13_screen.sh`

**Interfaces:**
- Consumes: `bench/run.py --check` and `--task/--runs/--arm` (Task 2); the author tasks in `bench/tasks.json` (Task 5); and `bench/e13_screen_read.py` (Task 6), named in the script's header.
- Produces: `bash bench/e13_screen.sh [--dry-run]`. A real run prints `SCREEN_START <timestamp>` for the reader's `--window`.

- [ ] **Step 1: Write the script**

Create `bench/e13_screen.sh`:

```bash
#!/usr/bin/env bash
# E13 control screen. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 3.
#
# Control only, no skill installed in any cell. The candidates are whichever
# E13 author tasks bench/e13_preflight.py wrote into bench/tasks.json. One that
# failed pre-flight is absent there, and is not screened.
#
#   C  sf-author-verdict-from             n=6  candidate
#   D  sf-author-transcript-slice         n=6  candidate
#   E  sf-author-store-dir                n=6  candidate
#   R  sf-author-fingerprint-preexisting  n=3  same-batch reference (0/21)
#
# Up to 21 sessions plus one allowance probe. Admission is 0 of 6. If R resolves
# even once, the screen is void. A session refused at the session limit
# postpones the whole screen: re-run it as one fresh batch, never stitched.
#
# Read with: python3 bench/e13_screen_read.py --window <SCREEN_START> -
#
# Usage: bash bench/e13_screen.sh [--dry-run]
#   --dry-run runs every guard and lists the cells without spending a session.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# A control cell must receive NOTHING. retrieve.py ranks the global store, so a
# single global skill that scores against these prompts would turn a floor
# measurement into a quiet treatment run while the row still said "control".
python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty -- control would not be control"; exit 1; }

# Every row records plugin_commit. Uncommitted plugin code would make that
# commit a lie about what ran.
if [ -n "$(git status --porcelain -- scripts hooks skills .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test (scripts/ hooks/ skills/ .claude-plugin/)"
  exit 1
fi

# Includes the guard against a task with an empty fail_to_pass, which would
# read every control run as resolved.
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }

# The candidates present, in the spec's order, collected into an array.
CELLS=()
while IFS= read -r id; do
  [ -n "$id" ] && CELLS+=("$id")
done < <(python3 -c "
import json
ids = {t['id'] for t in json.load(open('bench/tasks.json'))['tasks']}
for i in ('sf-author-verdict-from', 'sf-author-transcript-slice', 'sf-author-store-dir'):
    if i in ids:
        print(i)
")
[ "${#CELLS[@]}" -gt 0 ] || { echo "FATAL: no E13 candidate passed pre-flight"; exit 1; }
echo "candidates: ${CELLS[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the session allowance, then screens each candidate n=6 and the reference n=3"
  exit 0
fi

# One session spent to protect up to 21.
PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

echo "SCREEN_START $(date +%Y-%m-%dT%H:%M:%S)"
for id in "${CELLS[@]}"; do
  echo "### $id  (control, n=6)"
  python3 bench/run.py --task "$id" --runs 6 --arm control || echo "run.py exited non-zero for $id"
done
echo "### sf-author-fingerprint-preexisting  (reference, control, n=3)"
python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 3 --arm control \
  || echo "run.py exited non-zero for the reference"
echo "### E13 SCREEN DONE"
```

Then run: `chmod +x bench/e13_screen.sh`

- [ ] **Step 2: Verify every guard with a dry run (zero sessions)**

Run: `bash bench/e13_screen.sh --dry-run; echo "exit=$?"`
Expected: `config ok: ...`, then `candidates: <the ids written in Task 5>`, then `dry run: every guard passed; ...`, and `exit=0`. The dry run exits before the allowance probe, so no session starts. If a guard fires, fix its cause. Do not weaken the guard.

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add bench/e13_screen.sh || exit 1
git commit -q -m "bench: E13 screen script -- guards, allowance probe, dry run

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 5: Fast-forward main and push**

The parallel `in_scope` session may have merged into `main` in the meantime. This step fast-forwards only, and stops if a real merge is needed.

```bash
P="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"   # the primary checkout, where main lives
[ -z "$(git -C "$P" status --short)" ] || { echo "PRIMARY TREE DIRTY -- stop and report"; exit 1; }
[ "$(git rev-list --count HEAD..main)" = "0" ] || { echo "MAIN HAS MOVED -- stop: this needs a real merge, report to the user"; exit 1; }
if git grep -l "$HOME" HEAD -- bench tests docs; then echo "HOME PATH IN A COMMITTED FILE -- stop"; exit 1; fi
git -C "$P" merge --ff-only "$(git rev-parse HEAD)" || exit 1
git -C "$P" push origin main || exit 1
echo "ahead: $(git -C "$P" rev-list --count origin/main..main)  behind: $(git -C "$P" rev-list --count main..origin/main)"
```

Expected: the push succeeds, followed by `ahead: 0  behind: 0`.

- [ ] **Step 6: Hand back to the user**

Report which candidates the pre-flight admitted, and their graded-test counts; any candidate that was invalid, with its problems; and that the screen is ready. Say that it costs up to 22 sessions (21 plus the probe), and wait for the user's go-ahead before running `bash bench/e13_screen.sh`.
