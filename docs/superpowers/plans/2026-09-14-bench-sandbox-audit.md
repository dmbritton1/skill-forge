# Bench Sandbox and Transcript Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run every bench session under a macOS `sandbox-exec` profile, audit
each session's transcript for reads the sandbox cannot block, and make every
E13 reader ignore rows whose audit is not clean.

**Architecture:** There are two new modules, each with one job:

- `bench/sandbox.py` builds, writes and self-checks the profile.
- `bench/audit.py` finds a transcript by session id, labels the paths its tool
  calls touched, and holds the `counts(row)` rule every reader uses.

`bench/run.py` gains `session_cmd()`, the single launch path, which
`bench/distill.py` also uses. It also gains `sandbox_plugin()`, which replaces
the checkout with a snapshot, and `session_audit()`, the row keys. The readers
filter with `audit.counts`.

**Tech Stack:** Python 3 stdlib, macOS `sandbox-exec` (SBPL), bash, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md`

## Global Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and `bench/real_path_check.py` are not touched (a parallel session owns them; importing them is allowed).
- No absolute home path in committed files; paths are built at runtime, and paths written to `results.jsonl` or `meta.json` go through `audit.display()` (`~/...`).
- No literal secret-shaped strings in committed files.
- Guard every commit with an explicit `|| exit 1`; the Bash tool ignores `set -e`.
- Loop in Python or over bash arrays, never over a bare `$var` (zsh does not word-split).
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest -q tests` — 877 passed at plan time; it must stay green after every task.

## Rulings made while planning (the spec stays binding where not named here)

1. **The profile denies `file-read-data file-write*`, not `file-read*`.**
   Spec 2.3 names `file-read*`. That was verified on 2026-09-14: `file-read*`
   also denies metadata, which breaks `cd` into a clone under a denied
   directory. `file-read-data` still denies `cat` and `ls` of denied paths and
   allows `cd` and `realpath`. *Cost if wrong:* a session can `stat` a denied
   path, which reveals that the path exists but not its contents.
2. **`sandboxed()` is split up.** It becomes `sandbox.write_profile()` plus
   `sandbox.wrap()`, called from `run.session_cmd()`. `counts()` lives in
   `bench/audit.py`, not `run.py`, so readers don't import run.py's
   dependencies. *Cost if wrong:* only where the code lives.
3. **Spec 4.2's "`run.py` batch summary" is `e13_probe_read.py`'s summary.**
   `run.py` prints no batch summary; the probe reader prints the `valid ...
   undelivered` lines, so the `void` column goes there, and into
   `e13_outcome_read.py`. *Cost if wrong:* none. The column appears where the
   batch is read.
4. **The audit returns a third key, `leaked`.** It lists every leaked path, not
   capped. Taint is decided from it, because `hits` is capped at 10.
5. **A result that says "Operation not permitted" never downgrades a
   plugin-`scripts/` read to blocked.** The sandbox never blocks those reads, so
   a denial in the same command came from another path. *Cost if wrong:* none.
6. **Label ceilings are accepted and marked `ponytail:` in code.** Paths reached
   through `cd`, `$VARS`, globs or `python3 -c` code are not seen. A
   `python3 -u <script>` reads as a leak, a false positive that voids the row and
   costs a re-run.
7. **The `RESULTS.md` note does not claim distill sessions read the plugin's
   copies.** A real transcript from 2026-09-14 shows a relative
   `scripts/validate.py` read, which is the clone's own stub. So the note says
   which copy was not recorded.

## File map

| file | change | responsibility |
| --- | --- | --- |
| `bench/sandbox.py` | create | profile text, profile file, command wrap, zero-session self-check |
| `bench/audit.py` | create | find transcript, label paths, verdict, `counts`, `tainted_for`, `display` |
| `bench/run.py` | modify | `SANDBOX`, `sandbox_plugin`, `session_cmd`, `session_audit`, `--no-sandbox`, `--sandbox-check`, row keys |
| `bench/distill.py` | modify | `TRAP_FILES`, launch via `session_cmd`, audit + `tainted` in `meta.json`, `--no-sandbox` |
| `bench/e13_probe_read.py` | modify | skip void rows, legacy-only `archive:` rule, `void` column |
| `bench/e13_outcome_read.py` | modify | skip void rows, `void` column |
| `bench/e13_qualify.py` | modify | exclude tainted drafts, list them |
| `bench/e13_probe.sh`, `bench/e13_outcome.sh`, `bench/e13_screen.sh` | modify | run `--sandbox-check` before any session |
| `bench/RESULTS.md` | modify | methods note |
| `tests/test_bench_sandbox.py`, `tests/test_bench_audit.py` | create | unit tests |
| `tests/test_bench_run.py`, `tests/test_bench_distill.py`, `tests/test_bench_e13_probe_read.py`, `tests/test_bench_e13_outcome_read.py`, `tests/test_bench_e13_qualify.py` | modify | new cases |

---

### Task 1: `bench/sandbox.py`

**Files:**
- Create: `bench/sandbox.py`
- Test: `tests/test_bench_sandbox.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `TEMPLATE: str`, `TEMPLATE_SHA: str` (sha256 hex of `TEMPLATE`)
  - `repo_parent(repo_root) -> str` (real path of the main checkout's parent)
  - `project_folder(dest, home=None) -> str`
  - `sandbox_profile(dest, plugin_dir, work, repo_parent_dir, home=None) -> str` (raises `ValueError` on a path containing `"` or `\`)
  - `write_profile(dest, plugin_dir, work, repo_root) -> Path` (writes `<work>/<dest name>.sb`)
  - `wrap(cmd: str, profile_path) -> str`
  - `self_check(work, repo_root, plugin_dir) -> list[str]` (problems; empty means pass)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_sandbox.py`:

```python
"""Tests for bench/sandbox.py. Run: python3 tests/test_bench_sandbox.py"""
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "bench"))
import sandbox


def _paths(tmp):
    t = pathlib.Path(os.path.realpath(tmp))
    return t / "work", t / "work" / "clone-1", t / "work" / "plugin-abc", t / "dev", t / "home"


def test_profile_denies_the_three_roots_and_allows_the_exceptions():
    with tempfile.TemporaryDirectory() as tmp:
        work, dest, plugin, dev, home = _paths(tmp)
        text = sandbox.sandbox_profile(dest, plugin, work, dev, home=home)
        assert text.startswith("(version 1)\n(allow default)")
        assert text.count("(deny file-read-data file-write*") == 3
        for root in (dev, work, home / ".claude" / "projects"):
            assert '(require-all (subpath "%s")' % root in text, root
        assert '(require-not (subpath "%s"))' % dest in text
        assert '(require-not (subpath "%s"))' % plugin in text
        for suffix in ("", "-shm", "-wal", "-journal"):
            assert '(require-not (literal "%s.ledger.db%s"))' % (dest, suffix) in text
        assert '(require-not (subpath "%s"))' % sandbox.project_folder(dest, home) in text


def test_project_folder_matches_claude_codes_naming():
    home = pathlib.Path("/nonexistent-home")
    got = sandbox.project_folder(
        "/private/tmp/skillforge-bench/sf-author-verdict-from-treatment-d-learnnogate-3-3", home)
    assert got.endswith("/.claude/projects/"
                        "-private-tmp-skillforge-bench-sf-author-verdict-from-treatment-d-learnnogate-3-3")


def test_repo_parent_is_above_this_checkout():
    parent = sandbox.repo_parent(REPO)
    assert os.path.realpath(str(REPO)).startswith(parent + "/")
    assert parent != os.path.realpath(str(REPO))
    assert not os.path.realpath(str(REPO)).startswith(os.path.join(parent, ".claude"))


def test_a_quote_in_a_path_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        work, dest, plugin, dev, home = _paths(tmp)
        try:
            sandbox.sandbox_profile(pathlib.Path(str(dest) + '"x'), plugin, work, dev, home=home)
        except ValueError:
            return
        raise AssertionError("a quoted path was accepted")


def test_wrap_quotes_the_command_and_profile():
    got = sandbox.wrap("claude -p \"hi 'there'\"", "/w/a b.sb")
    assert got.startswith("sandbox-exec -f '/w/a b.sb' sh -c ")
    assert "hi" in got


def test_template_sha_is_stable_hex():
    assert len(sandbox.TEMPLATE_SHA) == 64 and int(sandbox.TEMPLATE_SHA, 16) >= 0


def test_self_check_passes_for_real():
    """Runs sandbox-exec for real; no claude session."""
    if not shutil.which("sandbox-exec"):
        print("SKIP sandbox-exec not present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(os.path.realpath(tmp)) / "work"
        plugin = work / "plugin-test"
        (plugin / "scripts").mkdir(parents=True)
        (plugin / "scripts" / "validate.py").write_text("# stand-in\n", encoding="utf-8")
        assert sandbox.self_check(work, REPO, plugin) == []


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

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_sandbox.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'sandbox'`

- [ ] **Step 3: Implement `bench/sandbox.py`**

```python
#!/usr/bin/env python3
"""macOS sandbox for bench sessions.

docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md, section 2.

Every bench session runs under `sandbox-exec` with a profile that denies the
operator's Developer tree, the other clones and hidden-test caches under WORK,
and other sessions' transcripts -- except this session's own clone, ledger,
transcript folder and plugin snapshot. It denies file CONTENT and writes, not
metadata: denying metadata on WORK breaks `cd` into a clone inside it
(verified 2026-09-14). The zero-session check:

    python3 bench/run.py --sandbox-check
"""
import hashlib
import os
import re
import shlex
import subprocess
from pathlib import Path

TEMPLATE = """(version 1)
(allow default)
(deny file-read-data file-write*
  (require-all (subpath "{repo_parent}")
               (require-not (subpath "{plugin}"))))
(deny file-read-data file-write*
  (require-all (subpath "{work}")
               (require-not (subpath "{dest}"))
               (require-not (subpath "{plugin}"))
               (require-not (literal "{dest}.ledger.db"))
               (require-not (literal "{dest}.ledger.db-shm"))
               (require-not (literal "{dest}.ledger.db-wal"))
               (require-not (literal "{dest}.ledger.db-journal"))))
(deny file-read-data file-write*
  (require-all (subpath "{projects}")
               (require-not (subpath "{project_folder}"))))
"""
# Recorded on every row as sandbox_profile: which rules ran, without the
# per-session paths.
TEMPLATE_SHA = hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest()


def _real(path):
    return os.path.realpath(str(path))


def repo_parent(repo_root):
    """The directory holding the main checkout.

    From git's common dir, so a worktree under .claude/worktrees/ resolves to
    its main checkout's parent, not to the worktrees directory -- the sandbox
    must hide every checkout and worktree, not just this one.
    """
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         cwd=str(repo_root), capture_output=True, text=True, check=True)
    return _real(Path(out.stdout.strip()).parent.parent)


def project_folder(dest, home=None):
    """The ~/.claude/projects folder Claude Code writes this clone's transcript
    to: the real clone path with each non-alphanumeric character replaced by '-'."""
    home = Path(home) if home else Path.home()
    return os.path.join(_real(home / ".claude" / "projects"),
                        re.sub(r"[^A-Za-z0-9]", "-", _real(dest)))


def sandbox_profile(dest, plugin_dir, work, repo_parent_dir, home=None):
    home = Path(home) if home else Path.home()
    values = {"repo_parent": _real(repo_parent_dir), "plugin": _real(plugin_dir),
              "work": _real(work), "dest": _real(dest),
              "projects": _real(home / ".claude" / "projects"),
              "project_folder": project_folder(dest, home)}
    for v in values.values():
        if '"' in v or "\\" in v:
            raise ValueError("path cannot be quoted in a sandbox profile: %r" % v)
    return TEMPLATE.format(**values)


def write_profile(dest, plugin_dir, work, repo_root):
    """Write this session's profile beside its clone and return the path.

    It sits in WORK, which the profile denies; sandbox-exec reads the file
    before applying it, so that is safe.
    """
    path = Path(work) / (Path(dest).name + ".sb")
    path.write_text(sandbox_profile(dest, plugin_dir, work, repo_parent(repo_root)),
                    encoding="utf-8")
    return path


def wrap(cmd, profile_path):
    return "sandbox-exec -f %s sh -c %s" % (shlex.quote(str(profile_path)), shlex.quote(cmd))


def self_check(work, repo_root, plugin_dir):
    """Spec section 5.1, zero sessions: problems found, empty when the sandbox
    denies and allows what the spec says."""
    work = Path(work)
    dest, other = work / "sandbox-check", work / "sandbox-check-other"
    for d in (dest, other):
        d.mkdir(parents=True, exist_ok=True)
        (d / "probe.txt").write_text("probe\n", encoding="utf-8")
    profile = write_profile(dest, plugin_dir, work, repo_root)
    cases = [(Path(repo_root) / "bench" / "tasks.json", False),
             (other / "probe.txt", False),
             (dest / "probe.txt", True),
             (Path(plugin_dir) / "scripts" / "validate.py", True)]
    problems = []
    for path, readable in cases:
        if not path.is_file():
            # A missing file fails `cat` too, and would pass a deny case.
            problems.append("self-check file missing: %s" % path)
            continue
        r = subprocess.run(wrap("cat %s" % shlex.quote(str(path)), profile), shell=True,
                           capture_output=True, text=True, timeout=60)
        if (r.returncode == 0) != readable:
            problems.append("%s %s under the sandbox: %s"
                            % ("could not read" if readable else "could read", path,
                               (r.stderr or "").strip()[-200:]))
    return problems
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_sandbox.py`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add bench/sandbox.py tests/test_bench_sandbox.py || exit 1
git commit -q -m "bench: sandbox-exec profile and zero-session self-check

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 2: `bench/audit.py`

**Files:**
- Create: `bench/audit.py`
- Test: `tests/test_bench_audit.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `display(path) -> str` (home prefix replaced by `~/`)
  - `find_transcript(session_id, projects=None) -> Path | None`
  - `audit_transcript(path, dest, plugin_dir, work, repo_parent, projects=None) -> dict` (keys `verdict` in `clean|leak|missing`, `hits` as a list of `{tool, path, label}` at most 10 long, `leaked` as a sorted list of `display()` paths; never raises)
  - `counts(row) -> bool`
  - `tainted_for(audit, plugin_dir, fixed_file) -> bool`

A transcript is JSONL. The shape was verified on 2026-09-14 against a real bench
transcript:

- a tool call is a `{"type": "tool_use", "id", "name", "input"}` block inside
  `line["message"]["content"]`, where `content` is a list;
- its result is a `{"type": "tool_result", "tool_use_id", "content", "is_error"}`
  block, whose `content` is a string or a list of `{"type": "text", "text"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_audit.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_audit.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'audit'`

- [ ] **Step 3: Implement `bench/audit.py`**

```python
#!/usr/bin/env python3
"""Audit a bench session's transcript for reads the sandbox cannot block.

docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md, sections 3-4.

The plugin's hooks import scripts/validate.py and scripts/retrieve.py, which
hold the traps' fixed functions, so the sandbox must leave the plugin's
scripts/ readable. This reads the session's transcript -- found by the
--session-id the harness assigned -- and labels every path a tool call touched:

  ok       inside the clone or its ledger, a plugin script run as a program,
           or anywhere the bench does not guard
  leak     a plugin scripts/ file read as text, or the checkout, another clone
           or cache, or a transcript
  blocked  a would-be leak the sandbox refused ("Operation not permitted")
"""
import json
import os
import shlex
from pathlib import Path

MAX_HITS = 10
DENIED = "Operation not permitted"
MISSING = {"verdict": "missing", "hits": [], "leaked": []}


def display(path):
    """`~/...` for a path under home: results.jsonl and meta.json are published."""
    return str(path).replace(str(Path.home()) + "/", "~/")


def find_transcript(session_id, projects=None):
    projects = Path(projects) if projects else Path.home() / ".claude" / "projects"
    found = sorted(projects.glob("*/%s.jsonl" % session_id)) if session_id else []
    return found[0] if found else None


def counts(row):
    """Spec section 4.1: does this results row count toward a reader's tally?

    A row with no `audit` key predates the sandbox and counts as it always did.
    """
    if "audit" not in row:
        return True
    return row.get("sandbox") is True and (row.get("audit") or {}).get("verdict") == "clean"


def tainted_for(audit, plugin_dir, fixed_file):
    """Spec section 3.4: did a distill session read its trap's fixed file as text?"""
    if not fixed_file:
        return False
    target = display(os.path.join(os.path.realpath(str(plugin_dir)), fixed_file))
    return target in (audit or {}).get("leaked", [])


def _norm(path, dest):
    p = os.path.normpath(os.path.join(dest, os.path.expanduser(path)))
    for alias in ("/tmp", "/var"):
        if p == alias or p.startswith(alias + "/"):
            return "/private" + p
    return p


def _under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def _tool_paths(name, inp):
    """[(raw path, ran as a program)] for one tool call.

    ponytail: shlex tokens only -- a path reached through `cd`, $VARS, a glob or
    `python3 -c` code is not seen, and `python3 -u <script>` reads as text (a
    false leak, which costs a re-run). A real parser if a leak ever slips by.
    """
    if name == "Bash":
        cmd = inp.get("command") or ""
        try:
            toks = shlex.split(cmd)
        except ValueError:
            toks = cmd.split()
        return [(t, i > 0 and os.path.basename(toks[i - 1]).startswith("python"))
                for i, t in enumerate(toks) if "/" in t or t.startswith("~")]
    raw = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
    return [(raw, False)] if isinstance(raw, str) and raw else []


def _result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


def audit_transcript(path, dest, plugin_dir, work, repo_parent, projects=None):
    """{"verdict": clean|leak|missing, "hits": the first MAX_HITS non-ok paths,
    "leaked": every leaked path}. Never raises: an unreadable transcript is
    `missing`."""
    try:
        if path is None or not Path(path).is_file():
            return dict(MISSING)
        real = lambda p: os.path.realpath(str(p))
        dest, plugin, work, repo_parent = real(dest), real(plugin_dir), real(work), real(repo_parent)
        projects = real(projects or Path.home() / ".claude" / "projects")
        scripts = os.path.join(plugin, "scripts")
        uses, results = [], {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            content = (json.loads(line).get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    uses.append(b)
                elif b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = _result_text(b)
        hits, leaked = [], []
        for u in uses:
            denied = DENIED in results.get(u.get("id"), "")
            for raw, ran in _tool_paths(u.get("name"), u.get("input") or {}):
                p = _norm(raw, dest)
                if _under(p, scripts):
                    label = "ok" if ran else "leak"
                elif _under(p, dest) or p.startswith(dest + ".ledger.db") or _under(p, plugin):
                    label = "ok"
                elif _under(p, repo_parent) or _under(p, work) or _under(p, projects):
                    # The sandbox never blocks plugin scripts/, so a denial in
                    # the same command cannot excuse one (that branch is above).
                    label = "blocked" if denied else "leak"
                else:
                    label = "ok"
                if label == "ok":
                    continue
                if label == "leak":
                    leaked.append(display(p))
                hits.append({"tool": u.get("name"), "path": display(p), "label": label})
        return {"verdict": "leak" if leaked else "clean", "hits": hits[:MAX_HITS],
                "leaked": sorted(set(leaked))}
    except Exception:
        return dict(MISSING)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_audit.py`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add bench/audit.py tests/test_bench_audit.py || exit 1
git commit -q -m "bench: transcript audit, counts() and distill taint rule

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 3: Sandbox and audit in `bench/run.py`

**Files:**
- Modify: `bench/run.py`
  - imports: lines 25-37
  - globals: near `FORCE_HOT` (line 65)
  - after `plugin_commit` (ends at line 379)
  - `run_session`: lines 599-610
  - `one`: lines 664-679
  - `main`: lines 697-776
- Test: `tests/test_bench_run.py`

**Interfaces:**
- Consumes: `sandbox.write_profile`, `sandbox.wrap`, `sandbox.self_check`, `sandbox.repo_parent`, `sandbox.TEMPLATE_SHA` (Task 1), plus `audit.find_transcript` and `audit.audit_transcript` (Task 2).
- Produces:
  - `SANDBOX: bool` (module global, default `True`)
  - `sandbox_plugin(plugin_dir, explicit: bool) -> Path` (raises `ValueError`)
  - `session_cmd(prompt: str, dest, plugin_dir, session_id: str) -> str`
  - `session_audit(session_id, dest, plugin_dir) -> dict` (keys `sandbox`, `sandbox_profile`, `session_id`, `audit`)
  - `run_session(task, dest, plugin_dir, session_id)`
  - CLI flags `--no-sandbox` and `--sandbox-check`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_run.py`, above its `if __name__ == "__main__":` block:

```python
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
```

Add `import subprocess` to the imports at the top of `tests/test_bench_run.py`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_run.py -k "session_cmd or sandbox_plugin or session_audit"`
Expected: FAIL with `AttributeError: module 'run' has no attribute 'SANDBOX'`

- [ ] **Step 3: Implement the changes in `bench/run.py`**

1. Imports. Add `import uuid` after `import time`, and after `import libguard`
   (line 37) add:

```python
import audit
import sandbox
```

2. Globals. After the `FORCE_HOT = False` line, add:

```python
# Sandbox spec: every session runs under sandbox-exec and is audited. Off only
# via --no-sandbox, whose rows every reader voids.
SANDBOX = True
```

3. After `plugin_commit()`, before `def environment`, add:

```python
def sandbox_plugin(plugin_dir, explicit):
    """The plugin directory a sandboxed session loads (sandbox spec section 2.1).

    tasks.json's plugin_dir is the checkout, and the sandbox cannot allow the
    checkout without allowing bench/ -- hidden tests, results, drafts. A
    checkout is replaced by a snapshot of its HEAD under WORK, reused while the
    commit matches. Raises ValueError for a dirty checkout (the snapshot would
    not be the code on disk) or an explicit --plugin-dir that is not a snapshot.
    """
    plugin_dir = Path(plugin_dir)
    if (plugin_dir / SNAPSHOT_MARK).is_file():
        return plugin_dir
    if explicit:
        raise ValueError("--plugin-dir must be a run.snapshot_plugin() snapshot: %s" % plugin_dir)
    commit = plugin_commit(plugin_dir)
    if not commit or commit.endswith("+dirty"):
        raise ValueError("the plugin checkout has uncommitted changes, or is not a"
                         " checkout: %s" % plugin_dir)
    dest = WORK / ("plugin-" + commit[:7])
    mark = dest / SNAPSHOT_MARK
    if not (mark.is_file() and mark.read_text(encoding="utf-8").strip() == commit):
        snapshot_plugin(commit, dest)
    return dest


def session_cmd(prompt, dest, plugin_dir, session_id):
    """The `claude -p` command for one bench session, sandboxed unless
    --no-sandbox. distill.py launches through this too: one sandbox, not two."""
    cmd = ("claude -p %s --plugin-dir %s --permission-mode bypassPermissions"
           " --model %s --session-id %s"
           % (json.dumps(prompt), json.dumps(str(plugin_dir)), json.dumps(MODEL), session_id))
    if not SANDBOX:
        return cmd
    return sandbox.wrap(cmd, sandbox.write_profile(dest, plugin_dir, WORK, REPO_ROOT))


def session_audit(session_id, dest, plugin_dir):
    """Row keys for sandbox spec sections 2.4 and 3."""
    return {"sandbox": SANDBOX, "sandbox_profile": sandbox.TEMPLATE_SHA,
            "session_id": session_id,
            "audit": audit.audit_transcript(audit.find_transcript(session_id), dest,
                                            plugin_dir, WORK, sandbox.repo_parent(REPO_ROOT))}
```

4. Replace `run_session` with:

```python
def run_session(task, dest, plugin_dir, session_id):
    cmd = session_cmd(task["prompt"], dest, plugin_dir, session_id)
    t0 = time.time()
    try:
        r = sh(cmd, cwd=dest, timeout=SESSION_TIMEOUT_S)
        return {"ok": r.returncode == 0, "secs": round(time.time() - t0, 1),
                "tail": (r.stdout or r.stderr)[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "secs": SESSION_TIMEOUT_S, "tail": "TIMEOUT"}
```

5. In `one()`, replace `sess = run_session(task, dest, plugin_dir)` with:

```python
    session_id = str(uuid.uuid4())
    sess = run_session(task, dest, plugin_dir, session_id)
```

   After `rec.update(source_keys(arm, task, tier_at_install))`, add:

```python
    rec.update(session_audit(session_id, dest, plugin_dir))
```

6. In `main()`:
   - Add `SANDBOX` to the existing `global MODEL, FORCE_HOT, SKILL_FROM, PLUS_SKILL, INJECT_BUDGET` line.
   - Add two arguments after `--plugin-dir`:

```python
    ap.add_argument("--no-sandbox", action="store_true",
                    help="debugging only: run sessions unsandboxed. Every reader"
                         " voids the rows this writes (sandbox spec 2.4)")
    ap.add_argument("--sandbox-check", action="store_true",
                    help="zero sessions: verify the sandbox denies the checkout and"
                         " other clones and allows the clone and plugin, then exit")
```

   - After `INJECT_BUDGET = args.inject_budget`, add `SANDBOX = not args.no_sandbox`.
   - Replace the block that starts at `if not (plugin_dir / "scripts").is_dir():`
     and ends just before `global ENV, PLUGIN_SEGMENT` with:

```python
    if not (plugin_dir / "scripts").is_dir():
        print("plugin dir has no scripts/: %s" % plugin_dir, file=sys.stderr)
        return 1
    if SANDBOX or args.sandbox_check:
        try:
            plugin_dir = sandbox_plugin(plugin_dir, explicit=bool(args.plugin_dir))
        except ValueError as err:
            print("sandbox: %s" % err, file=sys.stderr)
            return 1
    if args.sandbox_check:
        WORK.mkdir(parents=True, exist_ok=True)
        problems = sandbox.self_check(WORK, REPO_ROOT, plugin_dir)
        for problem in problems:
            print("sandbox-check: %s" % problem, file=sys.stderr)
        print("sandbox check %s" % ("FAILED" if problems else "ok"))
        return 1 if problems else 0
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_run.py`
Expected: all pass, including the 7 new tests.

Run: `python3 bench/run.py --sandbox-check`
Expected: last line `sandbox check ok`, exit 0.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/run.py tests/test_bench_run.py || exit 1
git commit -q -m "bench: run.py sessions sandboxed from a plugin snapshot and audited

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 4: Sandbox, audit and taint in `bench/distill.py`

**Files:**
- Modify: `bench/distill.py`
  - imports at the top
  - `TRAPS` block (line 44)
  - `one()`: lines 208-351
  - `main()`: lines 384-420
- Test: `tests/test_bench_distill.py`

**Interfaces:**
- Consumes:
  - `bench_run.SANDBOX`, `bench_run.sandbox_plugin`, `bench_run.session_cmd`, `bench_run.session_audit` (Task 3)
  - `audit.tainted_for` (Task 2)
- Produces:
  - `TRAP_FILES: dict[str, str]`
  - `meta.json` keys `sandbox`, `sandbox_profile`, `session_id`, `audit`, `tainted`
  - CLI flag `--no-sandbox`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_distill.py`, above its `if __name__ == "__main__":` block:

```python
def test_trap_files_hold_each_traps_fixed_function():
    import distill
    repo = pathlib.Path(__file__).resolve().parent.parent
    for trap, fn in (("C", "def verdict_from"), ("D", "def transcript_slice"),
                     ("E", "def store_dir")):
        assert fn in (repo / distill.TRAP_FILES[trap]).read_text(encoding="utf-8"), trap


def test_main_refuses_to_distil_when_the_plugin_cannot_be_sandboxed():
    import distill
    old = (distill.bench_run.sandbox_plugin, distill.bench_run.SANDBOX, distill.one)
    calls = []

    def refuse(plugin_dir, explicit):
        raise ValueError("the plugin checkout has uncommitted changes")
    # distill.one is stubbed so this test can never launch a real session.
    distill.bench_run.sandbox_plugin = refuse
    distill.one = lambda *a, **kw: calls.append(a)
    try:
        assert distill.main(["--trap", "C", "--distiller", "learn", "--draws", "1"]) == 1
        assert calls == []
    finally:
        distill.bench_run.sandbox_plugin, distill.bench_run.SANDBOX, distill.one = old
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_distill.py -k "trap_files or cannot_be_sandboxed"`
Expected: 2 failed:
- `AttributeError: module 'distill' has no attribute 'TRAP_FILES'`;
- `assert 0 == 1`, because the current `main` calls the stubbed `one` and returns 0.

- [ ] **Step 3: Implement the changes in `bench/distill.py`**

1. Imports. Add `import uuid` beside the other stdlib imports, and `import audit`
   beside the existing import of `run` as `bench_run`.

2. Directly after the `TRAPS = {...}` dict, add:

```python
# Sandbox spec section 3.4: the file holding each trap's fixed function. A
# distill session that reads the PLUGIN's copy as text marks its draft tainted,
# and e13_qualify skips it.
TRAP_FILES = {"C": "scripts/validate.py", "D": "scripts/draft.py",
              "E": "scripts/save_skill.py"}
```

3. In `one()`:
   - Before `before = libguard.snapshot()`, add `session_id = str(uuid.uuid4())`.
   - Replace the three-line `cmd = ('claude -p %s --plugin-dir %s ...)` assignment with:

```python
        cmd = bench_run.session_cmd(prompt, dest, plugin_dir, session_id)
```

   - Check that `clone_dest()` (line 188) returns a path directly under
     `bench_run.WORK`; the profile only allows the clone there. If it does not,
     stop and report `BLOCKED`.
   - In the `finally:` block, directly before `d.mkdir(parents=True, exist_ok=True)`, add:

```python
        sb = bench_run.session_audit(session_id, dest, plugin_dir)
```

   - In the `meta.json` dict, after `"session_ok": st["session_ok"],`, add:

```python
            "sandbox": sb["sandbox"], "sandbox_profile": sb["sandbox_profile"],
            "session_id": sb["session_id"], "audit": sb["audit"],
            "tainted": audit.tainted_for(sb["audit"], plugin_dir, TRAP_FILES.get(trap)),
```

4. In `main()`:
   - Add the argument after `--no-novelty-gate`:

```python
    ap.add_argument("--no-sandbox", action="store_true",
                    help="debugging only: distil unsandboxed (sandbox spec 2.4)")
```

   - After the `if not all(traps) or not all(dists):` block, add:

```python
    bench_run.SANDBOX = not args.no_sandbox
    if bench_run.SANDBOX:
        try:
            plugin_dir = bench_run.sandbox_plugin(plugin_dir, explicit=False)
        except ValueError as err:
            print("sandbox: %s" % err)
            return 1
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_distill.py`
Expected: all pass.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/distill.py tests/test_bench_distill.py || exit 1
git commit -q -m "bench: distill sessions sandboxed and audited, drafts marked tainted

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 5: The E13 readers skip void rows and tainted drafts

**Files:**
- Modify:
  - `bench/e13_probe_read.py` (imports, `_is_outcome_row`, `read_probe`, `main`)
  - `bench/e13_outcome_read.py` (imports, `read_outcome`, `main`)
  - `bench/e13_qualify.py` (`counted_drafts`, `main`)
- Test:
  - `tests/test_bench_e13_probe_read.py`
  - `tests/test_bench_e13_outcome_read.py`
  - `tests/test_bench_e13_qualify.py`

**Interfaces:**
- Consumes: `audit.counts` (Task 2), and the `meta.json` key `tainted` (Task 4).
- Produces:
  - probe control and cell dicts gain `void: int`;
  - outcome arm dicts gain `void: int`;
  - `counted_drafts()` entries gain `tainted: bool`;
  - `qualification.json` gains `tainted: [repo-relative draft paths]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_e13_probe_read.py`, above `if __name__`:

```python
def sandboxed(r, verdict="clean"):
    """The row as written after the sandbox: a snapshot commit and an audit."""
    return dict(r, sandbox=True, audit={"verdict": verdict},
                env={"plugin_commit": "archive:" + "c" * 40})


def test_a_void_row_does_not_count_and_is_re_run():
    rows = [ctl()] * 3 + full(D1, 0) + [sandboxed(trt(D1, resolved=True), verdict="leak")]
    cell = pr.read_probe(rows, TASK, [D1])["cells"][D1["path"]]
    assert cell["valid"] == 3 and cell["resolved"] == 0
    assert cell["void"] == 1 and cell["rerun"] == 1


def test_a_void_control_that_resolved_does_not_void_the_batch():
    rows = [sandboxed(ctl(resolved=True), verdict="missing")] + [ctl()] * 3 + full(D1, 0)
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "complete" and res["control"]["void"] == 1


def test_a_sandboxed_snapshot_row_is_a_probe_row():
    rows = [sandboxed(ctl())] * 3 + [sandboxed(trt(D1, resolved=True))] * 3
    res = pr.read_probe(rows, TASK, [D1])
    assert res["pooled"] == [3, 3] and res["verdict"] == "working"
```

Append to `tests/test_bench_e13_outcome_read.py`, above `if __name__`:

```python
def test_a_void_row_does_not_fill_out_the_arm():
    leak = dict(row(NEW, resolved=True), sandbox=True, audit={"verdict": "leak"})
    res = outcome(arm(OLD, 0) + some_rows(NEW, 5, resolved=5) + [leak])
    assert res["arms"]["new"]["valid"] == 5 and res["arms"]["new"]["void"] == 1
    assert res["batch"] == "incomplete"
```

In `tests/test_bench_e13_qualify.py`:

- Change the `_draw` signature to
  `def _draw(archive, segment, draw, outcome="saved", name=None, draft=True, tainted=None):`
- Change its `meta.json` write to:

```python
    meta = {"outcome": outcome, "skill_name": name}
    if tainted is not None:
        meta["tainted"] = tainted
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
```

Then append, above `if __name__`:

```python
def test_counted_drafts_flag_a_tainted_draft():
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp)
        _draw(a, "learn-nogate", 1, name="clean")
        _draw(a, "learn-nogate", 2, name="read-the-fix", tainted=True)
        got = [(d["name"], d["tainted"]) for d in q.counted_drafts(a, "C")]
        assert got == [("clean", False), ("read-the-fix", True)], got
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_e13_probe_read.py tests/test_bench_e13_outcome_read.py tests/test_bench_e13_qualify.py`
Expected: FAIL with `KeyError: 'void'` / `KeyError: 'tainted'`, and the snapshot-row test failing on `pooled`.

- [ ] **Step 3: Implement the reader changes**

**`bench/e13_probe_read.py`:**

- Below `from e12_read import select`, add:

```python
from audit import counts  # noqa: E402  -- sandbox spec 4.1, one rule for every reader
```

- Replace the body of `_is_outcome_row` after its docstring with:

```python
    if r.get("extra_skills"):
        return True
    # Every sandboxed row runs from a snapshot (sandbox spec 2.1), so archive:
    # marks an outcome row only among rows written before the sandbox.
    if "sandbox" not in r and (r.get("env") or {}).get("plugin_commit", "").startswith("archive:"):
        return True
    return False
```

- In `read_probe`, directly after the `postponed` return block, add:

```python
    void = [r for r in mine if not counts(r)]
    mine = [r for r in mine if counts(r)]
```

- Replace the `out = {"control": {...}, ...}` assignment with:

```python
    void_control = sum(1 for r in void if r.get("arm") == "control")
    out = {"control": {"valid": len(ok), "needed": N_CONTROL,
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "void": void_control,
                       "rerun": len(control) - len(ok) + void_control},
           "cells": {}, "verdict": None, "pooled": None}
```

- Replace the `cell = {...}` assignment with:

```python
        void_cell = sum(1 for r in void if r.get("arm") == "treatment"
                        and _draft_path(r.get("skill_path")) == d["path"])
        cell = {"valid": len(counted), "needed": N_RUNS,
                "resolved": sum(1 for r in counted if r.get("resolved")),
                "undelivered": len(ran) - len(hit), "void": void_cell,
                "rerun": (len(trt) - len(ran)) + (len(ran) - len(hit)) + void_cell}
```

- In `main`, change the two print statements to:

```python
        print("  control %-44s valid %d/%d  resolved %d  void %d  re-run %d"
              % (q["task"], c["valid"], c["needed"], c["resolved"], c["void"], c["rerun"]))
```

```python
        print("  draft   %-44s valid %d/%d  resolved %d  undelivered %d  void %d  %s"
              % (path.replace("bench/distilled/", ""), c["valid"], c["needed"], c["resolved"],
                 c["undelivered"], c["void"], c["status"]))
```

**`bench/e13_outcome_read.py`:**

- Below `from e13_probe_read import _draft_path`, add `from audit import counts  # noqa: E402`.
- In `read_outcome`, directly after the `postponed` return block, add:

```python
    void = [r for r in mine if not counts(r)]
    mine = [r for r in mine if counts(r)]
```

- Inside the arm loop, replace the `a = {...}` assignment with:

```python
        void_arm = sum(1 for r in void if (r.get("env") or {}).get("plugin_commit") == commit
                       and _draft_path(r.get("skill_path")) == draft_path)
        a = {"valid": len(counted), "needed": N_ARM,
             "resolved": sum(1 for r in counted if r.get("resolved")),
             "mismatched": len(ran) - len(match), "void": void_arm,
             "rerun": len(trt) - len(match) + void_arm}
```

- In `main`, change the arm print to:

```python
        print("  %-3s valid %d/%d  resolved %d  mismatched %d  void %d  re-run %d  %s"
              % (label, a["valid"], a["needed"], a["resolved"], a["mismatched"], a["void"],
                 a["rerun"], a["status"]))
```

**`bench/e13_qualify.py`:**

- In `counted_drafts`, change the `out.append(...)` call to:

```python
                out.append({"segment": seg.name, "draw": int(meta.parent.name),
                            "path": draft, "name": m.get("skill_name"),
                            # Sandbox spec 3.4: its session read the trap's fixed file.
                            "tainted": bool(m.get("tainted"))})
```

- In `main`, replace `drafts = counted_drafts(ARCHIVE, args.trap)` with:

```python
    counted = counted_drafts(ARCHIVE, args.trap)
    tainted = [_rel(d["path"]) for d in counted if d["tainted"]]
    drafts = [d for d in counted if not d["tainted"]]
    for t in tainted:
        print("tainted, not qualified: %s" % t)
```

- In the `result = {...}` dict, add `"tainted": tainted,` after `"drafts": rows,`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e13_probe_read.py tests/test_bench_e13_outcome_read.py tests/test_bench_e13_qualify.py`
Expected: all pass. `test_outcome_rows_do_not_count_toward_the_probe` still passes, because its baseline and noisy dicts both carry `void: 0`.

Run: `python3 bench/e13_probe_read.py --trap C --window 2026-09-14T14:31:15 2026-09-14T15:00:00`
Expected: the stored C re-run still reads `verdict: not working (pooled 7/15)`, now with `void 0` on every line. Legacy rows are unchanged.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/e13_probe_read.py bench/e13_outcome_read.py bench/e13_qualify.py tests/test_bench_e13_probe_read.py tests/test_bench_e13_outcome_read.py tests/test_bench_e13_qualify.py || exit 1
git commit -q -m "bench: E13 readers skip void rows; qualification skips tainted drafts

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 6: Batch-script guard and the `RESULTS.md` methods note

**Files:**
- Modify: `bench/e13_probe.sh`, `bench/e13_outcome.sh`, `bench/e13_screen.sh`, `bench/RESULTS.md`

**Interfaces:**
- Consumes: `python3 bench/run.py --sandbox-check` (Task 3).
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Add the guard to each script**

In each of the three scripts, directly after the existing line
`python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }`,
insert:

```bash
# Sandbox spec section 4.4: zero sessions, before the first one.
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
```

- [ ] **Step 2: Verify the scripts**

Run: `bash -n bench/e13_probe.sh && bash -n bench/e13_outcome.sh && bash -n bench/e13_screen.sh && echo syntax-ok`
Expected: `syntax-ok`

Run: `grep -c "run.py --sandbox-check" bench/e13_probe.sh bench/e13_outcome.sh bench/e13_screen.sh`
Expected: each file `:1`

Run: `bash bench/e13_screen.sh --dry-run`
Expected: ends with `dry run: every guard passed; ...`, and `sandbox check ok` is printed before it. If an unrelated earlier guard fails, such as a non-empty global library, report that output verbatim rather than working around it.

- [ ] **Step 3: Add the methods note to `bench/RESULTS.md`**

Insert this section directly before the line `## Numbering, honestly`:

```markdown
## Sandbox and audit (from 2026-09-14)

Rows written from 2026-09-14 on carry `sandbox`, `sandbox_profile`,
`session_id` and `audit`. Each session ran under `sandbox-exec`, which denied
it the operator's Developer tree, the other clones and hidden-test caches, and
other sessions' transcripts. It loaded a snapshot of the plugin, never the
checkout. Its transcript was then audited for reads of the plugin's `scripts/`,
which the sandbox has to leave readable because the hooks import them. A row
whose audit is not `clean` counts toward no reader (`bench/audit.py`,
`counts`). Design: `docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md`.

Earlier rows ran unsandboxed and unaudited. Earlier distill sessions were seen
reading `scripts/save_skill.py` and `scripts/validate.py`, but whether they read
the plugin's copies or the clone's own was not recorded. From now on, a draft
whose session read the plugin's copy of its trap's fixed file is marked
`tainted`, and qualification skips it.
```

- [ ] **Step 4: Commit**

```bash
git add bench/e13_probe.sh bench/e13_outcome.sh bench/e13_screen.sh bench/RESULTS.md || exit 1
git commit -q -m "bench: batch scripts run the sandbox self-check; RESULTS methods note

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 7: One-session smoke (the controller runs this, not a subagent)

Spec 5.2. This spends one session. Run it only after the final whole-branch
review is clean.

**Files:**
- Modify: `bench/results.jsonl` (one appended row)

- [ ] **Step 1: Zero-session check**

Run: `python3 bench/run.py --sandbox-check`
Expected: `sandbox check ok`

- [ ] **Step 2: One sandboxed session**

Run: `python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 1 --arm control`
Expected: `control   run 1 -> unresolved` or `RESOLVED`, not `ERROR`.

- [ ] **Step 3: Check the row, transcript, audit and hooks**

Run:

```bash
python3 - <<'EOF'
import json, sqlite3, sys
sys.path.insert(0, "bench")
import audit, run
r = json.loads(open("bench/results.jsonl").read().splitlines()[-1])
print("task", r["task"], "session_ok", r.get("session_ok"), "sandbox", r.get("sandbox"))
print("plugin_commit", r["env"]["plugin_commit"])
print("transcript", audit.find_transcript(r["session_id"]) is not None)
print("audit", r["audit"]["verdict"], r["audit"]["hits"])
db = run.WORK / "sf-author-fingerprint-preexisting-control-1.ledger.db"
print("ledger events", sqlite3.connect(str(db)).execute("select count(*) from events").fetchone()[0])
EOF
```

Pass criteria, every one required:
- `session_ok True` and `sandbox True`;
- `plugin_commit archive:<sha>`;
- `transcript True`;
- audit verdict `clean`;
- `ledger events` greater than 0.

If `ledger events` is 0, re-run Step 2 with `--arm treatment` and check again before concluding the hooks failed; a control arm may log nothing. If the session fails to authenticate or start, read `session_tail` and adjust the profile, for example an extra exception for a path the CLI needs. Re-run Task 1's tests and Step 1, and record the change in the ledger.

- [ ] **Step 4: Commit the smoke row**

```bash
git add bench/results.jsonl || exit 1
git commit -q -m "bench: sandbox smoke session -- one sandboxed, audited control row

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```
