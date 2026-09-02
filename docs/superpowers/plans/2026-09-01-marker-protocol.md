# Marker Protocol and Usage Truth Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth usage detector — the model declares which skills it applied, and the Stop reconciler turns those declarations into ledger events that can be cross-checked against the existing passive signals.

**Architecture:** The model appends `{"skill": "<name>"}` lines to `.claude/skillforge/session-usage.jsonl`, prompted by a note delivered two ways: appended to the injection payload for warm skills, appended to the materialized body for hot ones. The Stop reconciler reads and consumes that file, writing one `detection='marker'` event per skill per session under the same crediting rule the verification layer uses. The §9.1 truth table is never stored — which of `{marker, fingerprint, verification}` rows exist per `(session, skill)` is a query, exposed through `ledger.usage_for` and `library show`.

**Tech Stack:** Python 3.9, standard library only. SQLite (WAL) for the ledger. No test framework.

**Spec:** `docs/superpowers/specs/2026-09-01-marker-protocol-design.md` — read it before starting; it carries the reasoning this plan only executes.

## Global Constraints

- **Python 3.9, standard library only.** No pip installs, at runtime or for development.
- **pytest is NOT installed.** Tests are plain `def test_*()` functions with an `assert`-based `__main__` runner. Run a suite with `python3 tests/test_<name>.py`; exit code 0 means pass.
- Two runner styles exist and you must match the file you are editing. `test_ledger.py`, `test_sync.py`, `test_retrieve.py`, `test_detect.py` catch per test and print `PASS`/`FAIL %s: %r`, continuing after a failure. `test_reconcile.py` and `test_library.py` are bare — they abort at the first failing assertion and print no `FAIL` line. A bare suite that stops early with no output after some `PASS` lines has failed.
- **No suite may invoke a model, run a skill-authored command, or create a git worktree.** Nothing in this plan needs any of those.
- **Never weaken an existing test** to make a change pass.
- **Hooks exit 0 always and print nothing on stdout on failure.** stdout is the harness's control channel; diagnostics go to stderr. `detect.py`, `retrieve.py` and `reconcile.py` are hooks.
- **Ledger writes are best-effort.** Wrap them so one failed row never blocks delivery; `reconcile._log` already does this.
- Skill text and marker files are **untrusted input**. Parse defensively; never pass their contents to a model.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Do not `git stash` — the stash stack is shared across worktrees.

---

## File Structure

| File | Responsibility in this change |
|---|---|
| `scripts/ledger.py` | `usage_for` (the truth-table query) and the partial unique index that caps markers at one row per skill per session. |
| `scripts/reconcile.py` | `marker_path`, `read_markers` (read-and-consume the scratch file), `_credit_markers` (the gates), and the relaxed early return in `_reconcile_c2`. |
| `scripts/retrieve.py` | `MARKER_NOTE`, the single canonical wording; appended to the warm injection payload. |
| `scripts/detect.py` | Appends `retrieve.MARKER_NOTE` to the anti-skill payload. |
| `scripts/sync.py` | Appends `retrieve.MARKER_NOTE` to the text handed to `materialize_one_text`, reaching hot skills. |
| `scripts/library.py` | Prints the truth-table cells in `cmd_show`. |

Tasks are ordered by dependency: the ledger primitive first, then ingestion and crediting, then the two delivery routes, then the read surface.

---

### Task 1: Ledger — `usage_for` and the marker uniqueness index

**Files:**
- Modify: `scripts/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ledger.usage_for(skill, *, path=None) -> dict` with integer keys `sessions`, `injections`, `both`, `corroborated_only`, `marker_only`, `neither`. The four cells `both + corroborated_only + marker_only + neither` always sum to `sessions`. Returns all zeros on any failure. Task 6 consumes it.

**Context you need:** `events` already has every column required — `event_type`, `skill`, `session`, `detection`. There is no schema version bump and no migration. The partial unique indexes live in a loop *outside* the `SCHEMA` string (search `idx_events_one_verdict`), which is why adding one there reaches databases that already exist. `log_event` performs a plain `INSERT` and does not catch `IntegrityError`, so a duplicate raises to the caller; every hook caller already wraps its writes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger.py`, above the `if __name__ == "__main__":` block:

```python
def test_usage_for_partitions_sessions_into_truth_table_cells():
    """The cell is derived from which rows exist, never stored."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        # s1: marker and fingerprint agree
        ledger.log_event("injection", "alpha", session="s1", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="fingerprint", path=db)
        # s2: fingerprint with no marker -- a compliance miss
        ledger.log_event("injection", "alpha", session="s2", path=db)
        ledger.log_event("detection", "alpha", session="s2", detection="fingerprint", path=db)
        # s3: marker with nothing corroborating it
        ledger.log_event("injection", "alpha", session="s3", path=db)
        ledger.log_event("detection", "alpha", session="s3", detection="marker", path=db)
        # s4: injected and never used
        ledger.log_event("injection", "alpha", session="s4", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 4, u
        assert u["injections"] == 4, u
        assert u["both"] == 1, u
        assert u["corroborated_only"] == 1, u
        assert u["marker_only"] == 1, u
        assert u["neither"] == 1, u
        assert u["both"] + u["corroborated_only"] + u["marker_only"] + u["neither"] \
            == u["sessions"], u


def test_usage_for_counts_verification_as_corroboration():
    """Verification is a stronger corroborator than fingerprint, not a weaker one."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "alpha", session="s1", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s1", detection="verification",
                         outcome="success", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["both"] == 1, u
        assert u["marker_only"] == 0, u


def test_usage_for_counts_a_hot_marker_with_no_injection():
    """Hot skills have no injection event; their markers still land in a cell."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 1, u
        assert u["injections"] == 0, u
        assert u["marker_only"] == 1, u


def test_usage_for_ignores_other_skills():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "beta", session="s1", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 0, u


def test_usage_for_returns_zeros_on_a_broken_db():
    """Read helpers never raise into a caller; a bad path reads as no data."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "nope" / "ledger.db"
        u = ledger.usage_for("alpha", path=bad)
        assert u["sessions"] == 0, u
        assert u["both"] == 0, u


def test_one_marker_row_per_skill_per_session():
    """The index is the backstop for reconcile's own dedupe check."""
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        try:
            ledger.log_event("detection", "alpha", session="s1", detection="marker",
                             path=db)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("second marker row for the same session was accepted")
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 1, u


def test_marker_index_does_not_block_a_different_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "alpha", session="s1", detection="marker", path=db)
        ledger.log_event("detection", "alpha", session="s2", detection="marker", path=db)
        u = ledger.usage_for("alpha", path=db)
        assert u["sessions"] == 2, u
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_ledger.py
```

Expected: `FAIL test_usage_for_... AttributeError("module 'ledger' has no attribute 'usage_for'")` and `FAIL test_one_marker_row_per_skill_per_session: AssertionError('second marker row for the same session was accepted')`. Exit code 1.

- [ ] **Step 3: Add the partial unique index**

In `scripts/ledger.py`, find the loop that creates `idx_events_one_verdict` and add one more entry to the same tuple:

```python
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_one_marker"
        " ON events(session, skill) WHERE event_type = 'detection'"
        " AND detection = 'marker'",
```

- [ ] **Step 4: Implement `usage_for`**

Add near `findings_for` in `scripts/ledger.py`:

```python
USAGE_SQL = (
    "SELECT COALESCE(session, ''),"
    "       MAX(event_type = 'injection'),"
    "       MAX(event_type = 'detection' AND detection = 'marker'),"
    "       MAX(event_type = 'detection'"
    "           AND detection IN ('fingerprint', 'verification'))"
    " FROM events WHERE skill = ? GROUP BY COALESCE(session, '')")

USAGE_ZERO = {"sessions": 0, "injections": 0, "both": 0,
              "corroborated_only": 0, "marker_only": 0, "neither": 0}


def usage_for(skill, *, path=None):
    """The §9.1 truth table for one skill, counted in sessions.

    The cell a session falls in is which rows exist for it, so this is a
    query rather than a stored judgment -- which is what lets a marker at
    turn 3 and a fingerprint at turn 7 need no adjudication step between
    them. `corroborated_only` is the compliance-miss rate's numerator (the
    skill was used, the usage protocol drifted); `marker_only` is the
    performative rate's (claimed, nothing independent agrees) -- though it
    also collects skills whose correct application leaves no fingerprint,
    which is why it is reported rather than penalized.

    Zeros on any failure: this feeds a display, and a read helper that
    raises into `library show` would trade a missing number for no output.
    """
    out = dict(USAGE_ZERO)
    try:
        con = connect(path)
        try:
            for _session, inj, marker, corroborated in con.execute(USAGE_SQL, (skill,)):
                out["sessions"] += 1
                out["injections"] += 1 if inj else 0
                if marker and corroborated:
                    out["both"] += 1
                elif corroborated:
                    out["corroborated_only"] += 1
                elif marker:
                    out["marker_only"] += 1
                else:
                    out["neither"] += 1
        finally:
            con.close()
    except Exception as err:
        print("skillforge: usage read failed: %s" % err, file=sys.stderr)
        return dict(USAGE_ZERO)
    return out
```

Check the top of `ledger.py` for `import sys`; add it if absent.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 tests/test_ledger.py
```

Expected: every line `PASS`, exit code 0.

- [ ] **Step 6: Run the full suite for regressions**

```bash
for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done; echo done
```

Expected: only `done`. The new index applies to existing databases through the loop, so no other suite should change behaviour.

- [ ] **Step 7: Commit**

```bash
git add scripts/ledger.py tests/test_ledger.py && git commit -m "feat: derive the usage truth table from events

usage_for buckets each of a skill's sessions by which detection rows it
holds, so the 9.1 truth table is a query rather than a stored judgment.
A partial unique index caps markers at one row per skill per session.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Reconciler — read and consume the marker file

**Files:**
- Modify: `scripts/reconcile.py`
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `reconcile.marker_path(cwd) -> pathlib.Path` and `reconcile.read_markers(cwd) -> set` of skill-name strings, deleting the file as it reads. Task 3 consumes both.

**Context you need:** `tests/test_reconcile.py` uses the **bare** runner — it aborts at the first failing assertion and prints no `FAIL` line, so judge it by exit code and by which `PASS` lines stop appearing. The file already has an `in_sandbox(fn)` helper that swaps `$HOME` for a temp directory and calls `fn(tmp_path)`.

The file is consumed rather than accumulated for a specific reason: the model has no session id to write, so the file is not session-scoped, and a line surviving from an earlier session would credit the current one the next time that skill is injected. `read_markers` must therefore delete the file even when it parses nothing useful out of it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reconcile.py`, above the `if __name__ == "__main__":` block:

```python
def write_markers(root, lines):
    p = reconcile.marker_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_read_markers_collects_skill_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, ['{"skill": "alpha"}', '{"skill": "beta"}'])
        assert reconcile.read_markers(root) == {"alpha", "beta"}


def test_read_markers_consumes_the_file():
    """Not tidiness: a surviving line would credit the next session."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = write_markers(root, ['{"skill": "alpha"}'])
        assert reconcile.read_markers(root) == {"alpha"}
        assert not p.exists()
        assert reconcile.read_markers(root) == set()


def test_read_markers_skips_junk_without_losing_good_lines():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write_markers(root, [
            "",
            "not json at all",
            '["alpha"]',                 # valid JSON, not an object
            '{"skill": 7}',              # not a string
            '{"skill": ""}',             # empty after strip
            '{"action": "did a thing"}', # no skill key
            '{"skill": "  alpha  "}',    # stripped
        ])
        assert reconcile.read_markers(root) == {"alpha"}


def test_read_markers_still_consumes_a_file_of_pure_junk():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = write_markers(root, ["garbage", "more garbage"])
        assert reconcile.read_markers(root) == set()
        assert not p.exists()


def test_read_markers_caps_the_read_and_the_name():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        long_name = "n" * 400
        write_markers(root, ['{"skill": "%s"}' % long_name])
        got = reconcile.read_markers(root)
        assert got == {"n" * reconcile.MAX_MARKER_NAME}, got

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        filler = ['{"skill": "pad%d"}' % i
                  for i in range(reconcile.MAX_MARKER_BYTES // 20 + 200)]
        write_markers(root, filler + ['{"skill": "last"}'])
        got = reconcile.read_markers(root)
        assert "last" not in got, "read past the size cap"
        assert got, "cap discarded everything"


def test_read_markers_on_a_missing_file_is_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert reconcile.read_markers(pathlib.Path(tmp)) == set()


def test_read_markers_survives_binary_content():
    """errors='replace', not a crash: the file is model-written, not trusted."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        p = reconcile.marker_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'\xff\xfe\x00\x00\n{"skill": "alpha"}\n')
        assert reconcile.read_markers(root) == {"alpha"}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_reconcile.py
```

Expected: aborts with `AttributeError: module 'reconcile' has no attribute 'marker_path'`, exit code 1. (Bare runner — you will see earlier `PASS` lines and then the traceback.)

- [ ] **Step 3: Implement `marker_path` and `read_markers`**

Add the constants beside the other module-level limits in `scripts/reconcile.py` (near `MAX_DIFF_BYTES`):

```python
# The marker scratch file is model-written and reaches no model: a script
# reads it and turns it into rows. Both caps are anti-wedge, not security --
# a runaway loop appending markers must not turn every Stop into a large read.
MAX_MARKER_BYTES = 64 * 1024
MAX_MARKER_NAME = 128
```

Add the functions after `changed_tokens`:

```python
def marker_path(cwd):
    return Path(cwd) / ".claude" / "skillforge" / "session-usage.jsonl"


def read_markers(cwd):
    """Skill names the model claimed to apply; the file is consumed on read.

    Consumed, not accumulated: the model has no session id to write, so the
    file is not session-scoped, and a line surviving from an earlier session
    would credit this one the next time that skill is injected. The unlink
    therefore happens even when nothing parses -- a file of junk that stays
    on disk is a file re-read at every Stop forever.

    Untrusted input. Bad lines are skipped rather than raising, and a name
    is only a candidate here: `_credit_markers` still checks it against the
    index, the scope, and the injection gate before it becomes a row.
    """
    p = marker_path(cwd)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")[:MAX_MARKER_BYTES]
    except OSError:
        return set()
    try:
        p.unlink()
    except OSError:
        pass          # read succeeded; a stale file is better than losing the names
    out = set()
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue   # blank lines, prose, and the tail the size cap bisected
        if not isinstance(obj, dict):
            continue
        name = obj.get("skill")
        if isinstance(name, str) and name.strip():
            out.add(name.strip()[:MAX_MARKER_NAME])
    return out
```

`json` and `Path` are already imported in `reconcile.py`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 tests/test_reconcile.py
```

Expected: exit code 0, a `PASS` line for each test including the seven new ones.

- [ ] **Step 5: Commit**

```bash
git add scripts/reconcile.py tests/test_reconcile.py && git commit -m "feat: read and consume the marker scratch file

read_markers parses the model-written session-usage.jsonl defensively and
deletes it, because the file carries no session id -- a surviving line
would credit the next session that injects the same skill.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Reconciler — credit markers under the injection gate

**Files:**
- Modify: `scripts/reconcile.py`
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Consumes: `reconcile.read_markers(cwd)` and `reconcile.marker_path(cwd)` from Task 2; `reconcile.load_entries()`, `reconcile.session_state(rows)`, `reconcile._log` already exist.
- Produces: `detection='marker'` rows in `events`. Task 6 reads them through `ledger.usage_for`.

**Context you need — read this before writing code.** The crediting rule is `credited()` from `scripts/detect.py`, restated. A claim of use is a proxy, and an ungated proxy credits a skill whose text never reached the model — the exact confound the outcome-attribution work closed for the verification layer. The hot exemption exists because the harness injects hot skills from the native directory and SkillForge never observes it, so requiring an injection event would make markers useless for the one tier that has no other signal.

`_reconcile_c2` currently opens with `state = session_state(rows)` followed by `if not state: return`. Marker ingestion must run **above** that guard: a hot skill can produce a marker with no other ledger events at all, so its session has empty `state`. The guard becomes `if not state and not markers: return`, which keeps the reconciler's cheap path cheap — `load_entries()` still runs only when there is work, and the common no-marker case costs one failed `open` on top of the indexed SELECT the hook already does every turn.

`load_entries()` returns `{name: index_entry}`, where an entry carries `root` and `tier`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reconcile.py`, above the `if __name__ == "__main__":` block. `write_index`, `write_markers`, `in_sandbox` and `events` already exist in the file.

```python
def marker_rows():
    return [r for r in events("detection") if r[1] == "marker"]


def stop_in(root, session="s1", final=False):
    reconcile.run({"session_id": session, "cwd": str(root),
                   "hook_event_name": "SessionEnd" if final else "Stop"})


def test_marker_credits_a_warm_skill_injected_this_session():
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_marker_for_a_skill_never_injected_is_dropped():
    """The gate that stops a claim crediting a skill the model never saw."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_marker_credits_a_hot_skill_with_no_injection_event():
    """The harness injects hot skills and we never see it; without this
    exemption the marker is useless for the one tier that has no other signal."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "hot",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_marker_for_an_out_of_scope_project_skill_is_dropped():
    def check(home):
        other = home / "other-project"
        other.mkdir()
        here = home / "here"
        here.mkdir()
        write_index(home, [{"name": "alpha", "root": str(other), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(here, ['{"skill": "alpha"}'])
        stop_in(here)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_marker_for_an_unknown_name_is_dropped():
    def check(home):
        write_index(home, [])
        write_markers(home, ['{"skill": "ghost"}'])
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)


def test_second_stop_does_not_duplicate_a_marker_row():
    """Stop fires every turn; the row must be written exactly once."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert len(marker_rows()) == 1, marker_rows()
    in_sandbox(check)


def test_a_marker_does_not_carry_an_outcome():
    """A null outcome is what keeps a performative marker from promoting a skill."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home)
        assert marker_rows()[0][3] is None, marker_rows()
    in_sandbox(check)


def test_a_marker_only_session_still_reconciles():
    """A hot skill's marker arrives in a session with no other ledger rows,
    so ingestion cannot sit behind the `no events` early return."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "hot",
                            "fingerprints": []}])
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home, session="fresh")
        assert [r[0] for r in marker_rows()] == ["alpha"], marker_rows()
    in_sandbox(check)


def test_a_consumed_marker_does_not_credit_the_next_session():
    """The spec's reason for consuming the file, asserted end to end: the
    model writes no session id, so a surviving line would credit whichever
    session next injects that skill."""
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        write_markers(home, ['{"skill": "alpha"}'])
        stop_in(home, session="s1")
        ledger.log_event("injection", "alpha", session="s2", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        stop_in(home, session="s2")          # no new marker file written
        assert len(marker_rows()) == 1, marker_rows()
    in_sandbox(check)


def test_a_stop_with_no_marker_file_writes_no_marker_row():
    def check(home):
        write_index(home, [{"name": "alpha", "root": str(home), "tier": "warm",
                            "fingerprints": []}])
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt", preexisting_fingerprint=0)
        stop_in(home)
        assert marker_rows() == [], marker_rows()
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_reconcile.py
```

Expected: aborts on `test_a_marker_only_session_still_reconciles` or an earlier new test with an `AssertionError` showing `[]` where a row was expected. Exit code 1.

- [ ] **Step 3: Implement `_credit_markers` and relax the early return**

Add to `scripts/reconcile.py`, immediately above `_reconcile_c2`:

```python
def _credit_markers(session, cwd, state, entries, markers):
    """One detection='marker' row per claimed skill that is entitled to it.

    This is detect.credited()'s rule restated, deliberately: a marker is a
    claim of use, a claim is a proxy, and an ungated proxy credits a skill
    whose text never reached the model. Hot is exempt for the same reason it
    is there -- the harness injects hot skills from the native directory and
    we never observe it, so demanding an injection event would make the
    marker useless for the one tier with no other signal.

    The row carries no outcome. That is what bounds a performative marker:
    skill_confidence derives buckets from outcome counts, so a marker can
    move `uses` and `last_used` and can never promote anything.
    """
    for name in sorted(markers):
        entry = entries.get(name)
        if not entry or not retrieve.in_scope(entry.get("root", ""), cwd):
            continue
        s = state.get(name)
        if s and "marker" in s["detections"]:
            continue        # Stop fires every turn; one row per session
        if entry.get("tier") == "hot" or (s and s["injected_ts"] is not None):
            _log("detection", name, detection="marker", session=session)
```

Then change the opening of `_reconcile_c2` from:

```python
    state = session_state(rows)
    if not state:
        return
    entries = load_entries()
```

to:

```python
    state = session_state(rows)
    # Read above the `no events` guard: a hot skill's marker arrives in a
    # session with no injection row of its own, so gating ingestion on other
    # events existing would drop exactly the tier the marker exists to reach.
    markers = read_markers(cwd)
    if not state and not markers:
        return
    entries = load_entries()
    _credit_markers(session, cwd, state, entries, markers)
```

Leave the rest of `_reconcile_c2` unchanged; `pending` and everything below it still guard on `state` naturally because `state.items()` is empty.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 tests/test_reconcile.py
```

Expected: exit code 0.

- [ ] **Step 5: Verify the gate by mutation**

Temporarily change the last condition in `_credit_markers` to `if True:` and re-run:

```bash
python3 tests/test_reconcile.py
```

Expected: `test_marker_for_a_skill_never_injected_is_dropped` fails. Restore that line, then drop the `entry.get("tier") == "hot" or` clause; re-run and confirm `test_marker_credits_a_hot_skill_with_no_injection_event` fails. Restore it, then comment out the `p.unlink()` call in `read_markers` (Task 2); re-run and confirm `test_a_consumed_marker_does_not_credit_the_next_session` fails.

**Restore the correct implementation before continuing.** A gate no test defends is a gate the next refactor deletes silently.

- [ ] **Step 6: Run the full suite for regressions**

```bash
for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done; echo done
```

Expected: only `done`.

- [ ] **Step 7: Commit**

```bash
git add scripts/reconcile.py tests/test_reconcile.py && git commit -m "feat: credit markers under the injection gate

A marker becomes a detection row only when the name resolves in the index,
is in scope, has no row yet this session, and the skill was either injected
this session or is hot -- detect.credited()'s rule restated so the codebase
holds one answer to 'may this skill claim credit'.

Ingestion runs above the 'no events' early return: a hot skill's marker
arrives in a session with no injection row of its own.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Delivery — the marker note on injected payloads

**Files:**
- Modify: `scripts/retrieve.py`, `scripts/detect.py`
- Test: `tests/test_retrieve.py`, `tests/test_detect.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `retrieve.MARKER_NOTE` (a `str`). Task 5 imports it into `sync.py`.

**Context you need:** both hooks build a list of strings called `parts` and emit `"\n\n".join(parts)` as `additionalContext` inside a `hookSpecificOutput` JSON object on stdout. The note goes in once per payload, not once per skill — repeating it for three injected skills is three times the tokens for one instruction. `detect.py` already does `import retrieve`, so there is exactly one copy of the wording.

Both suites use the **try/except** runner: they print `PASS`/`FAIL` per test and continue.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_retrieve.py`, above the `if __name__ == "__main__":` block. Find how existing tests in that file drive `retrieve.run_hook` and capture stdout, and match that helper rather than inventing one.

```python
def test_injection_payload_carries_the_marker_note():
    def check(home):
        write_index(home, [entry(home, "stripe-webhook",
                                 "stripe webhook signature verification")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert rc == 0
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "session-usage.jsonl" in ctx, ctx
    in_sandbox(check)


def test_marker_note_appears_once_for_several_skills():
    """One instruction per payload; three copies is three times the tokens."""
    def check(home):
        write_index(home, [
            entry(home, "stripe-webhook", "stripe webhook signature verification"),
            entry(home, "stripe-refund", "stripe webhook refund reconciliation")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert rc == 0
        assert len(injected_names(out)) == 2, injected_names(out)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert ctx.count("session-usage.jsonl") == 1, ctx
    in_sandbox(check)


def test_no_injection_means_no_marker_note():
    """The note is charged to sessions that inject, and to no others."""
    def check(home):
        write_index(home, [entry(home, "stripe-webhook",
                                 "stripe webhook signature verification")])
        rc, out = run_hook_capture(hook_data(home, "quantum chromodynamics lecture"))
        assert rc == 0
        assert "session-usage.jsonl" not in out, out
    in_sandbox(check)
```

`run_hook_capture(data) -> (rc, stdout)`, `hook_data(home, prompt, session="sess1")`,
`entry(home, name, desc, ...) -> dict` and `write_index(home, entries)` all already
exist in that file; `entry` builds an index dict and does not register it, which is
why each test passes its result to `write_index`.

`injected_names` parses lines beginning `--- SkillForge retrieved skill '`. The
marker note begins `--- SkillForge: if you apply`, so it does not match that prefix
and no existing assertion in this file changes.

Add to `tests/test_detect.py`, above its `if __name__ == "__main__":` block, using that file's existing `run_capture`, `tool_data`, `put_antiskill`, `write_triggers` and `symptom_entry` helpers:

```python
def test_antiskill_payload_carries_the_marker_note():
    def check(home):
        path = put_antiskill(home, "widget-trap")
        write_triggers(home, symptoms=[symptom_entry(home, "widget-trap", path)])
        out = run_capture(tool_data(
            home, "WidgetFlushedError: the widget was already flushed"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "session-usage.jsonl" in ctx, ctx
    in_sandbox(check)


def test_no_antiskill_match_means_no_marker_note():
    def check(home):
        path = put_antiskill(home, "widget-trap")
        write_triggers(home, symptoms=[symptom_entry(home, "widget-trap", path)])
        out = run_capture(tool_data(home, "everything is fine"))
        assert "session-usage.jsonl" not in out, out
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_retrieve.py; python3 tests/test_detect.py
```

Expected: `FAIL test_injection_payload_carries_the_marker_note` and `FAIL test_antiskill_payload_carries_the_marker_note`, both `AssertionError`. The two negative tests pass already — that is fine and expected; they exist to pin the "zero cost when nothing is injected" property so a later change cannot quietly make the note unconditional.

- [ ] **Step 3: Add `MARKER_NOTE` and append it in `retrieve.py`**

Add beside the other module constants in `scripts/retrieve.py`:

```python
# Delivered with the skills it governs rather than from a standing engine
# skill: a native skill's body is progressively disclosed, so a protocol
# living there is in context only once the model has decided to go read the
# protocol -- which is the behaviour the protocol exists to prompt.
MARKER_NOTE = ('--- SkillForge: if you apply any skill above, append one line to'
               ' .claude/skillforge/session-usage.jsonl (create it if absent):'
               ' {"skill": "<skill-name>"} ---')
```

In `run_hook`, after `parts` is built and before the `print(json.dumps(...))`:

```python
    parts.append(MARKER_NOTE)
```

- [ ] **Step 4: Append it in `detect.py`**

In `scripts/detect.py`, in `run`, after `parts` is built and before its `print(json.dumps(...))`:

```python
    parts.append(retrieve.MARKER_NOTE)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 tests/test_retrieve.py; python3 tests/test_detect.py
```

Expected: all `PASS`, exit code 0 from both.

- [ ] **Step 6: Commit**

```bash
git add scripts/retrieve.py scripts/detect.py tests/test_retrieve.py tests/test_detect.py && git commit -m "feat: ask for a usage marker alongside injected skills

MARKER_NOTE rides the injection payload once, so it is charged to sessions
that inject and costs nothing in sessions that do not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Delivery — the marker note in materialized hot bodies

**Files:**
- Modify: `scripts/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `retrieve.MARKER_NOTE` from Task 4.
- Produces: nothing later tasks depend on.

**Context you need — why this is not an engine skill.** Hot skills are injected by the harness from `<base>/.claude/skills/skillforge-hot/`, which SkillForge never observes, so the Task 4 preamble never reaches them. `sync.materialize_one_text` is the single point where a hot skill's text lands there — `save_skill.native_dir` uses that path only for collision checks and never materializes — so appending the note to the text `sync` writes puts the instruction in the skill's own body. The body loads exactly when the model intends to apply that skill, which is the moment the instruction is needed.

This does not disturb the trust registry: `hashes` and `trust.check_text` both run on `s["text"]`, the source store file, and nothing re-reads the materialized copy. `materialize_one_text`'s idempotence survives because it compares the target against the text it is handed, which now includes the note.

`sync.py` does not currently import `retrieve`. Adding it introduces no cycle — `retrieve` imports `ledger`, `patterns` and `trust`, none of which import `sync`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sync.py`, above the `if __name__ == "__main__":` block. The
file already has `in_sandbox`, `put_skill(base, name)` returning the store
`SKILL.md` path, `native_md(base, name)` returning the materialized path,
`earn_success(name)` (one successful session, the bar for `working`, which is
hot-eligible), and the `SKILL` template string.

```python
def make_hot(home, name):
    """Trusted plus one success = `working` = hot-eligible. Returns the store file."""
    md = put_skill(home, name)
    trust.record(name, md.read_text(encoding="utf-8"), "self")
    earn_success(name)
    return md


def test_materialized_hot_body_carries_the_marker_note():
    """The harness injects hot skills; this body is the only text we control."""
    def check(home):
        make_hot(home, "alpha")
        sync.sync()
        body = native_md(home, "alpha").read_text(encoding="utf-8")
        assert "session-usage.jsonl" in body, body
        assert body.startswith(SKILL % "alpha"), "the skill's own text was lost"
    in_sandbox(check)


def test_rematerializing_does_not_append_the_note_twice():
    """materialize_one_text compares the target against the text it is handed."""
    def check(home):
        make_hot(home, "alpha")
        sync.sync()
        sync.sync()
        body = native_md(home, "alpha").read_text(encoding="utf-8")
        assert body.count("session-usage.jsonl") == 1, body
    in_sandbox(check)


def test_the_note_does_not_reach_the_source_store_file():
    """Trust hashes the store file; appending there would quarantine the skill."""
    def check(home):
        md = make_hot(home, "alpha")
        sync.sync()
        assert "session-usage.jsonl" not in md.read_text(encoding="utf-8")
    in_sandbox(check)


def test_a_hot_skill_stays_trusted_after_materialization():
    """If the derived copy were re-hashed, sync would quarantine every hot
    skill on the run after it materialized one."""
    def check(home):
        make_hot(home, "alpha")
        sync.sync()
        counts = sync.sync()
        assert counts["quarantined"] == 0, counts
        assert counts["materialized"] == 1, counts
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_sync.py
```

Expected: `FAIL test_materialized_hot_body_carries_the_marker_note: AssertionError`. The other three pass already — they are regression pins for the trust and idempotence properties the change must not break, and they must keep passing after Step 3.

- [ ] **Step 3: Append the note at materialization**

In `scripts/sync.py`, add to the imports:

```python
import retrieve
```

Then change the materialization loop from:

```python
    for s in trusted:
        if s["tier"] == "hot":
            materialize_one_text(s["text"], native_root(s["base"]) / s["name"])
            counts["materialized"] += 1
```

to:

```python
    for s in trusted:
        if s["tier"] == "hot":
            # The harness injects hot skills from the native directory and we
            # never see it, so the retrieval preamble cannot reach them. The
            # body is the one text we control, and it loads exactly when the
            # model intends to apply the skill. Appended to the derived copy
            # only -- the store file is what trust hashes.
            materialize_one_text(s["text"] + "\n\n" + retrieve.MARKER_NOTE + "\n",
                                 native_root(s["base"]) / s["name"])
            counts["materialized"] += 1
```

- [ ] **Step 4: Update the three existing assertions that compare materialized text exactly**

Three assertions currently require the materialized body to equal the source
text byte for byte. They are correct today and wrong after this change; each
needs to keep measuring what it measures while allowing the appended note.

`tests/test_sync.py:110`, in `test_trusted_skill_materialized` — change:

```python
        assert native_md(home, "alpha").read_text(encoding="utf-8") == SKILL % "alpha"
```

to:

```python
        assert native_md(home, "alpha").read_text(
            encoding="utf-8").startswith(SKILL % "alpha")
```

`tests/test_save_skill.py:223`, in the name-clash test — change:

```python
        assert native.read_text(encoding="utf-8") == skill
```

to:

```python
        assert native.read_text(encoding="utf-8").startswith(skill)
        preserved = native.read_text(encoding="utf-8")
```

`tests/test_save_skill.py:228`, the second occurrence a few lines below, is the
one that measures "the rejected save did not disturb the native copy". Change:

```python
        assert native.read_text(encoding="utf-8") == skill
```

to:

```python
        assert native.read_text(encoding="utf-8") == preserved
```

That last change makes the test *stronger* than it was: it now pins the whole
body against its own earlier value rather than against a template, so any
disturbance at all fails it.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 tests/test_sync.py; python3 tests/test_save_skill.py
```

Expected: all `PASS` from `test_sync.py`, exit code 0 from both. If `test_a_hot_skill_stays_trusted_after_materialization` fails, the note reached the source file rather than the derived copy — check that you appended at the call site, not inside `materialize_one_text`.

- [ ] **Step 6: Run the full suite for regressions**

```bash
for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done; echo done
```

Expected: only `done`. `tests/test_library.py` also touches materialized paths but only asserts `.exists()`, so it is unaffected.

- [ ] **Step 7: Commit**

```bash
git add scripts/sync.py tests/test_sync.py tests/test_save_skill.py && git commit -m "feat: carry the marker note into materialized hot bodies

Hot skills are injected by the harness from the native directory, so the
retrieval preamble never reaches them. materialize_one_text is the single
point where their text is written, and the body loads exactly when the
model intends to apply the skill.

Appended to the derived copy only: trust hashes the store file, and
nothing re-reads the materialized one.

Three assertions comparing materialized text byte-for-byte are updated to
allow the appended note; the save_skill 'preserved' assertion now pins the
body against its own earlier value, which is stricter than the template
comparison it replaces.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Read surface — the truth table in `library show`

**Files:**
- Modify: `scripts/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `ledger.usage_for(skill, *, path=None)` from Task 1, returning keys `sessions`, `injections`, `both`, `corroborated_only`, `marker_only`, `neither`.
- Produces: nothing later tasks depend on.

**Context you need:** `cmd_show(name)` already prints a header line and then Tier A findings per mode. Note the comment on its missing-verdict branch — a missing verdict and a passing one are opposite facts, and blank space reads as the second. Apply the same standard here: a skill with no usage data must say so rather than printing a row of zeros with no explanation.

`tests/test_library.py` uses the **bare** runner — it aborts at the first failing assertion.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_library.py`, above the `if __name__ == "__main__":` block, using the file's existing `put_skill`, `capture` and `in_sandbox` helpers:

```python
def test_show_prints_the_usage_truth_table():
    """The measurement is worthless if it lands in a table nobody reads."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        ledger.log_event("injection", "alpha", session="s1", tier="warm",
                         trigger="prompt")
        ledger.log_event("detection", "alpha", session="s1", detection="marker")
        ledger.log_event("detection", "alpha", session="s1", detection="fingerprint")
        ledger.log_event("injection", "alpha", session="s2", tier="warm",
                         trigger="prompt")
        ledger.log_event("detection", "alpha", session="s2", detection="fingerprint")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "usage" in out.lower(), out
        assert "compliance miss" in out.lower(), out
    in_sandbox(check)


def test_show_says_a_skill_has_no_usage_data_rather_than_printing_zeros():
    """A missing measurement and a measured zero are opposite facts."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "no usage" in out.lower(), out
    in_sandbox(check)


def test_show_still_works_when_only_a_marker_exists():
    """A hot skill's first signal arrives with no injection row beside it."""
    def check(home):
        put_skill(home, "alpha")
        sync.sync()
        ledger.log_event("detection", "alpha", session="s1", detection="marker")
        rc, out = capture(["show", "alpha"])
        assert rc == 0, rc
        assert "uncorroborated" in out.lower(), out
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 tests/test_library.py
```

Expected: aborts on `test_show_prints_the_usage_truth_table` with `AssertionError`, exit code 1.

- [ ] **Step 3: Print the cells in `cmd_show`**

In `scripts/library.py`, add just before `return 0` at the end of `cmd_show`:

```python
    u = ledger.usage_for(name)
    if not u["sessions"]:
        # Same standard as the missing-verdict branch above: silence reads
        # as a measured zero, and "never measured" is the opposite fact.
        print("\nusage: no usage data yet")
        return 0
    print("\nusage: %d session(s), %d injection(s)" % (u["sessions"], u["injections"]))
    print("  marker + corroboration:            %d" % u["both"])
    print("  corroboration only (compliance miss): %d" % u["corroborated_only"])
    print("  marker only (uncorroborated):      %d" % u["marker_only"])
    print("  injected, no usage signal:         %d" % u["neither"])
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 tests/test_library.py
```

Expected: exit code 0, a `PASS` line per test.

- [ ] **Step 5: Run the full suite**

```bash
for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done; echo done
```

Expected: only `done`.

- [ ] **Step 6: Commit**

```bash
git add scripts/library.py tests/test_library.py && git commit -m "feat: show the usage truth table per skill

library show prints the four cells: signals agreeing, corroboration with
no marker (the compliance-miss rate), marker with nothing corroborating
it, and injected-but-unused.

A skill with no usage data says so rather than printing zeros -- a missing
measurement and a measured zero are opposite facts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `python3 tests/test_ledger.py`, `test_reconcile.py`, `test_retrieve.py`, `test_detect.py`, `test_sync.py` and `test_library.py` all exit 0, as does every other suite in `tests/`.
- A marker for an uninjected warm skill writes no row; the same marker for a hot skill does.
- `library show <name>` prints the four truth-table cells, or says there is no usage data.
- No new dependency, no schema version bump, no test weakened.
