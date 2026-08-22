# SkillForge v0.2 Slice C2 Implementation Plan — Outcome Interpretation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the detection events slice C1 writes into decisions — which injections became uses, which anti-skills failed, what confidence each skill has earned — and spend that confidence on hot-tier eligibility and injection wording.

**Architecture:** A second SQL view, `skill_confidence`, derives three buckets (`unproven`/`working`/`trusted`) from outcome events, counting distinct sessions rather than rows. A new `scripts/reconcile.py` registered on Stop and SessionEnd reads the current session's ledger rows, credits fingerprint-only usage from one `git diff HEAD`, and settles anti-skill re-fire verdicts; it holds no state of its own, so re-running is idempotent. `sync.py` compiles each skill's bucket into `index.json` and gates the hot tier on `working`-or-better; `retrieve.py` hedges the preamble of `unproven` injections.

**Tech Stack:** Python 3.9 stdlib only (`json`, `sqlite3`, `subprocess`, `datetime`, `pathlib`). Tests are plain assert files with `__main__` runners (NO pytest). Existing modules: `scripts/{ledger,trust,sync,retrieve,detect,patterns,save_skill,secscan}.py`, eight green suites (145 tests).

**Design doc:** `docs/superpowers/specs/2026-08-21-v0.2-slice-c2-design.md`. Parent spec §1.1, §7, §9.1, §9.3.

## Global Constraints

- Python 3.9 compatible, **stdlib only**; no pip installs, runtime or dev.
- **pytest is not installed.** Tests are plain `def test_*()` functions with an `assert`-based `__main__` runner, run as `python3 tests/test_<name>.py` (exit 0 = pass). Copy the runner block from any existing suite.
- **Never weaken an existing test.** All eight suites must be green after every task. Task 4 changes two existing test fixtures; the assertions they make must survive unchanged.
- Every hook exits 0 always and prints nothing on failure. A hook failure must never break a tool call or a session.
- Ledger writes are best-effort: wrap every `log_event` so a failure never suppresses anything.
- All default paths derive from `Path.home()` at call time (sandbox-HOME testing).
- Compiled indexes are derived state, rebuilt wholesale by `sync.sync()`, trusted skills only.
- Reconciler constants (centralized in `reconcile.py`): `MIN_ESCAPE_S = 60`, `RECONCILE_WINDOW_S = 900`, `GIT_TIMEOUT_S = 1.0`, `MAX_DIFF_BYTES = 512 * 1024`.
- Snapshot caps are reused from `retrieve.py`, never redefined: `SNAPSHOT_MAX_FILES = 20`, `SNAPSHOT_MAX_BYTES = 200 * 1024`.
- Bucket names are exactly `"unproven"`, `"working"`, `"trusted"`.
- Confidence counts **distinct sessions**, never outcome rows.
- The reconciler never reads a `SKILL.md` and never writes to `additionalContext`, so it needs no `trust.check_text`. If a later change makes it emit skill text, that exemption ends.
- Commit messages end with: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

---

### Task 1: Confidence view

**Files:**
- Modify: `scripts/ledger.py` (the `SCHEMA` string, lines 14-36)
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: the existing `events` table and `ledger.connect(path)`.
- Produces (every later task depends on these): a view `skill_confidence` with columns `skill`, `success_sessions`, `failure_sessions`, `last_used`, `bucket`. `bucket` is one of `'unproven'`, `'working'`, `'trusted'`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ledger.py`, above the `__main__` runner block:

```python
def bucket_of(db, skill):
    con = ledger.connect(db)
    try:
        row = con.execute(
            "SELECT bucket FROM skill_confidence WHERE skill = ?", (skill,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def days_ago(n):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=n)).isoformat(timespec="seconds")


def test_bucket_unproven_without_outcomes():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("injection", "foo", session="s1", path=db)
        assert bucket_of(db, "foo") == "unproven"


def test_bucket_working_after_one_success():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("detection", "foo", detection="verification",
                         outcome="success", session="s1", path=db)
        assert bucket_of(db, "foo") == "working"


def test_two_successes_in_one_session_do_not_reach_trusted():
    # C1 dedupes verification detections per hook call, not per session, so a
    # verification command run twice in one session writes two success rows.
    # Spec 7's bar is k>=2 real SESSIONS -- rows must not stand in for them.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for _ in range(2):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session="s1", path=db)
        assert bucket_of(db, "foo") == "working"
        ledger.log_event("detection", "foo", detection="verification",
                         outcome="success", session="s2", path=db)
        assert bucket_of(db, "foo") == "trusted"


def test_failure_demotes_one_step_at_a_time():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, path=db)
        assert bucket_of(db, "foo") == "trusted"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="failure", session="s3", path=db)
        assert bucket_of(db, "foo") == "working"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="failure", session="s4", path=db)
        assert bucket_of(db, "foo") == "unproven"


def test_trusted_decays_to_working_after_90_days():
    # Also the direct test that julianday() parses the ledger's timestamp
    # format: if it returned NULL the freshness clause would go NULL, the
    # first WHEN would never fire, and NOTHING would ever be trusted.
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, ts=days_ago(120), path=db)
        assert bucket_of(db, "foo") == "working"
        con = ledger.connect(db)
        try:
            assert con.execute("SELECT julianday(ts) FROM events LIMIT 1").fetchone()[0] is not None
        finally:
            con.close()


def test_fresh_success_still_reaches_trusted():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for s in ("s1", "s2"):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", session=s, path=db)
        assert bucket_of(db, "foo") == "trusted"


def test_unsessioned_successes_count_as_one_session():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        for _ in range(3):
            ledger.log_event("detection", "foo", detection="verification",
                             outcome="success", path=db)
        assert bucket_of(db, "foo") == "working"


def test_reconcile_rows_do_not_inflate_uses():
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "ledger.db"
        ledger.log_event("reconcile", "foo", trigger="refire",
                         outcome="success", session="s1", path=db)
        con = ledger.connect(db)
        try:
            uses = con.execute(
                "SELECT uses FROM skill_aggregates WHERE skill='foo'").fetchone()[0]
        finally:
            con.close()
        assert uses == 0
```

Add `import datetime` to the imports at the top of the file if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_ledger.py`
Expected: FAIL with `sqlite3.OperationalError: no such table: skill_confidence`.

- [ ] **Step 3: Add the view to the schema**

In `scripts/ledger.py`, append to the `SCHEMA` string, after the `skill_aggregates` view:

```sql
CREATE VIEW IF NOT EXISTS skill_confidence AS
WITH t AS (
  SELECT skill,
    COUNT(DISTINCT CASE WHEN outcome = 'success' THEN COALESCE(session, '') END)
      AS success_sessions,
    COUNT(DISTINCT CASE WHEN outcome = 'failure' THEN COALESCE(session, '') END)
      AS failure_sessions,
    MAX(CASE WHEN event_type = 'detection' THEN ts END) AS last_used
  FROM events GROUP BY skill)
SELECT skill, success_sessions, failure_sessions, last_used,
  CASE
    WHEN success_sessions >= 2 AND failure_sessions = 0
         AND (last_used IS NULL OR julianday('now') - julianday(last_used) <= 90)
      THEN 'trusted'
    WHEN success_sessions >= 1 AND success_sessions > failure_sessions THEN 'working'
    ELSE 'unproven'
  END AS bucket
FROM t;
```

Add this comment directly above the `SCHEMA` assignment:

```python
# Views are created with IF NOT EXISTS, which does NOT update the definition
# of a view that already exists. Changing skill_confidence later (slice D ANDs
# in the Tier A conjunct) requires an explicit one-time DROP + CREATE
# migration -- not a DROP on every connect(), because detect.py connects on
# every tool call and DDL means a write transaction.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_ledger.py`
Expected: PASS, 15 tests.

- [ ] **Step 5: Verify no existing suite regressed**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/ledger.py tests/test_ledger.py
git commit -m "feat: session-scoped confidence buckets as a ledger view

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Reconciler — fingerprint usage credit

**Files:**
- Create: `scripts/reconcile.py`
- Modify: `hooks/hooks.json`
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Consumes: `ledger.connect()`, `ledger.log_event(...)`, `patterns.tokenize`, `patterns.matches`, `retrieve.sanitize_session`, `retrieve.load_index`, `retrieve.SNAPSHOT_MAX_FILES`, `retrieve.SNAPSHOT_MAX_BYTES`. Index entries carry `name`, `kind`, and pre-tokenized `fingerprints` (a list of token lists).
- Produces (Task 3 extends the same module): `parse_ts(value)`, `now_utc()`, `session_state(rows) -> dict`, `load_entries() -> dict`, `changed_tokens(cwd) -> list|None`, `needs_fingerprint(s, entry, now, final) -> bool`, `run(data) -> int`, `main(argv=None) -> int`, and the module constants. `session_state` returns `{skill: {"injected_ts", "preexisting", "detections", "symptom_ts", "settled"}}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reconcile.py`:

```python
"""Tests for the Stop/SessionEnd reconciler (slice C2 design 2-4).
Run: python3 tests/test_reconcile.py
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import reconcile


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def git_repo(root):
    """A real repo with one commit, so `git diff HEAD` has a HEAD to diff."""
    root.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(list(a), cwd=str(root), check=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    run("git", "config", "commit.gpgsign", "false")
    (root / "seed.py").write_text("seed = 1\n", encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed")
    return root


def write_index(home, entries):
    p = home / ".claude" / "skillforge" / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def ago(seconds):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def events(event_type):
    con = ledger.connect()
    try:
        return con.execute(
            'SELECT skill, detection, "trigger", outcome FROM events'
            " WHERE event_type = ? ORDER BY id", (event_type,)).fetchall()
    finally:
        con.close()


def fire(cwd, session="s1", event="Stop"):
    return reconcile.run({"session_id": session, "hook_event_name": event,
                          "cwd": str(cwd)})


SKILL_ENTRY = {"name": "fixer", "kind": "skill",
               "fingerprints": [["json", "dumps", "sort_keys"]]}


def test_fingerprint_in_tracked_diff_credits_one_use():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "seed.py").write_text(
            "seed = 1\nout = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        assert fire(repo) == 0
        assert events("detection") == [("fixer", "fingerprint", None, None)]
    in_sandbox(check)


def test_fingerprint_in_untracked_file_counts():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_credit_is_not_written_twice():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        fire(repo)
        fire(repo, event="SessionEnd")
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_existing_verification_suppresses_fingerprint_credit():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        ledger.log_event("detection", "fixer", detection="verification",
                         outcome="success", session="s1", ts=ago(60))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        kinds = [r[1] for r in events("detection")]
        assert kinds == ["verification"], kinds
    in_sandbox(check)


def test_preexisting_fingerprint_blocks_credit():
    for preexisting in (1, None):
        def check(home, preexisting=preexisting):
            repo = git_repo(home / "repo")
            write_index(home, [SKILL_ENTRY])
            ledger.log_event("injection", "fixer", session="s1",
                             preexisting_fingerprint=preexisting, ts=ago(120))
            (repo / "new.py").write_text(
                "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
            fire(repo)
            assert events("detection") == []
        in_sandbox(check)


def test_no_fingerprint_match_writes_nothing():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text("print('unrelated')\n", encoding="utf-8")
        fire(repo)
        assert events("detection") == []
    in_sandbox(check)


def test_skill_missing_from_index_is_skipped():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        assert fire(repo) == 0
        assert events("detection") == []
    in_sandbox(check)


def test_stop_stops_probing_after_the_window():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0,
                         ts=ago(reconcile.RECONCILE_WINDOW_S + 60))
        (repo / "new.py").write_text(
            "out = json.dumps(payload, sort_keys=True)\n", encoding="utf-8")
        fire(repo)
        assert events("detection") == []
        # SessionEnd runs once, so it probes regardless of age
        fire(repo, event="SessionEnd")
        assert len(events("detection")) == 1
    in_sandbox(check)


def test_non_git_cwd_writes_nothing_and_exits_zero():
    def check(home):
        plain = home / "plain"
        plain.mkdir()
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        assert fire(plain) == 0
        assert events("detection") == []
    in_sandbox(check)


def test_empty_and_malformed_payloads_exit_zero():
    def check(home):
        assert reconcile.run({}) == 0
        assert reconcile.run({"session_id": None, "cwd": str(home)}) == 0
    in_sandbox(check)


def test_missing_index_exits_zero():
    def check(home):
        repo = git_repo(home / "repo")
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=0, ts=ago(120))
        assert fire(repo) == 0
        assert events("detection") == []
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_reconcile.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconcile'`.

- [ ] **Step 3: Write the reconciler**

Create `scripts/reconcile.py`:

```python
#!/usr/bin/env python3
"""Stop/SessionEnd reconciler (spec 9.1, 9.3; slice C2 design).

Reads this session's ledger rows and decides what C1's detection events
mean: which injections became uses, and (see refire_verdict) whether an
injected anti-skill's trap fired again. Holds no state of its own --
"still unresolved" is re-derived from the ledger every run, so re-running
is idempotent by construction rather than by bookkeeping.

Cheap on purpose: Stop fires at the end of EVERY assistant turn, so the
common case (nothing unresolved) is one indexed SELECT and zero
subprocesses. Failure is always silent: exit 0, no output.
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import patterns
import retrieve

# A symptom re-firing sooner than this is the same tool output echoing back
# through a read or a grep -- detect.py logs the triggering symptom and the
# injection in the same hook call, microseconds apart, so without this floor
# every symptom-triggered anti-skill would convict itself on the evidence
# that summoned it.
MIN_ESCAPE_S = 60
# How long a skill's fate stays open: re-fires after it are a fresh trap, and
# Stop stops probing for its fingerprints (an injection the model ignored must
# not tax every remaining turn of a long session).
RECONCILE_WINDOW_S = 900
# ponytail: 1s ceiling, larger than retrieve's 150ms because this runs once
# per turn instead of once per tool call, and only when work is pending.
GIT_TIMEOUT_S = 1.0
MAX_DIFF_BYTES = 512 * 1024

SESSION_SQL = ("SELECT event_type, skill, detection, ts, preexisting_fingerprint"
               " FROM events WHERE session = ? ORDER BY id")


def _log(*args, **kwargs):
    """Bookkeeping is best-effort; one failed row never blocks another."""
    try:
        ledger.log_event(*args, **kwargs)
    except Exception as err:
        print("skillforge: ledger write failed: %s" % err, file=sys.stderr)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_ts(value):
    """Aware datetime from a ledger timestamp; None if unparseable."""
    try:
        parsed = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    # A naive timestamp would raise on comparison with an aware `now`.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def session_state(rows):
    """{skill: picture} from one session's id-ordered event rows."""
    state = {}
    for event_type, skill, detection, ts, preexisting in rows:
        s = state.setdefault(skill, {"injected_ts": None, "preexisting": None,
                                     "detections": set(), "symptom_ts": [],
                                     "settled": False})
        if event_type == "injection":
            if s["injected_ts"] is None:   # first injection of the session wins
                s["injected_ts"] = parse_ts(ts)
                s["preexisting"] = preexisting
        elif event_type == "detection":
            s["detections"].add(detection)
            if detection == "symptom":
                fired = parse_ts(ts)
                if fired:
                    s["symptom_ts"].append(fired)
        elif event_type == "reconcile":
            s["settled"] = True
    return state


def load_entries():
    """{name: index entry}; empty on any failure.

    index.json is the only file this hook reads, and it is authoritative for
    the two things the ledger cannot answer: whether a skill is an anti-skill,
    and what its fingerprints tokenize to. A skill missing from it -- deleted,
    re-quarantined, or dropped by a later sync -- is skipped entirely.
    """
    idx = retrieve.load_index() or {}
    return {e.get("name"): e for e in idx.get("entries", []) if e.get("name")}


def needs_fingerprint(s, entry, now, final):
    """True if this skill is unresolved and still creditable.

    Symptom detections deliberately do NOT resolve a skill: a symptom firing
    is the trap announcing itself (it is what caused the anti-skill to be
    injected), not evidence the Fix was applied.
    """
    if s["injected_ts"] is None or s["preexisting"] != 0:
        return False   # 1 = already there, None = unknown; spec 9.1 forbids the guess
    if s["detections"] & {"verification", "fingerprint"}:
        return False
    if not entry.get("fingerprints"):
        return False
    if final:
        return True    # SessionEnd runs once, so age is not a cost concern
    return (now - s["injected_ts"]).total_seconds() <= RECONCILE_WINDOW_S


def _git(args, cwd):
    try:
        proc = subprocess.run(["git"] + args, cwd=str(cwd), stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def changed_tokens(cwd):
    """Tokens of everything added to the working tree since HEAD; None if unknowable.

    One diff plus one untracked listing, tokenized once, serves every pending
    skill -- versus one `git grep` per fingerprint, which is what makes
    per-turn reconciliation affordable. Pre-session dirty state riding along
    in `git diff HEAD` is harmless: credit requires the injection to have
    recorded preexisting_fingerprint = 0.
    """
    parts = []
    diff = _git(["diff", "HEAD", "--unified=0"], cwd)
    if diff is not None:
        for line in diff[:MAX_DIFF_BYTES].splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                parts.append(line[1:])
    others = _git(["ls-files", "--others", "--exclude-standard"], cwd)
    if diff is None and others is None:
        return None   # not a usable repo -- unknown, never a false negative
    for rel in (others or "").splitlines()[:retrieve.SNAPSHOT_MAX_FILES]:
        try:
            with open(str(Path(cwd) / rel), "r", encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read(retrieve.SNAPSHOT_MAX_BYTES))
        except OSError:
            continue
    return patterns.tokenize("\n".join(parts))


def run(data):
    session = retrieve.sanitize_session(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()
    final = data.get("hook_event_name") == "SessionEnd"
    con = ledger.connect()
    try:
        rows = con.execute(SESSION_SQL, (session,)).fetchall()
    finally:
        con.close()
    state = session_state(rows)
    if not state:
        return 0
    entries = load_entries()
    now = now_utc()
    pending = [(name, s, entries[name]) for name, s in sorted(state.items())
               if name in entries]

    unresolved = [p for p in pending if needs_fingerprint(p[1], p[2], now, final)]
    if unresolved:
        hay = changed_tokens(cwd)
        if hay:
            for name, _, entry in unresolved:
                if any(patterns.matches(toks, hay)
                       for toks in entry.get("fingerprints") or []):
                    _log("detection", name, detection="fingerprint",
                         preexisting_fingerprint=0, session=session)
    return 0


def main(argv=None):
    try:
        return run(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: reconcile failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_reconcile.py`
Expected: PASS, 11 tests.

- [ ] **Step 5: Register the hook on Stop and SessionEnd**

In `hooks/hooks.json`, add two entries alongside the existing three, matching their exact shape:

```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/reconcile.py\""
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/reconcile.py\""
          }
        ]
      }
    ]
```

- [ ] **Step 6: Verify the hook file is valid JSON and the script survives junk stdin**

Run: `python3 -c "import json;d=json.load(open('hooks/hooks.json'));print(sorted(d['hooks']))"`
Expected: `['PostToolUse', 'SessionEnd', 'SessionStart', 'Stop', 'UserPromptSubmit']`

Run: `echo 'not json' | python3 scripts/reconcile.py; echo "exit=$?"`
Expected: `exit=0` (a diagnostic on stderr is fine; nothing on stdout).

- [ ] **Step 7: Verify no existing suite regressed**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add scripts/reconcile.py tests/test_reconcile.py hooks/hooks.json
git commit -m "feat: Stop/SessionEnd reconciler credits fingerprint-only usage

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Reconciler — anti-skill re-fire verdicts

**Files:**
- Modify: `scripts/reconcile.py` (add `refire_verdict`, extend `run`)
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Consumes: everything Task 2 produced, unchanged. `session_state` already collects `symptom_ts` and `settled`.
- Produces: `refire_verdict(s, entry, now, final) -> str|None` returning `"failure"`, `"success"`, or `None`. Writes rows with `event_type='reconcile'`, `trigger='refire'`, `detection` NULL, `outcome` set.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reconcile.py`, above the `__main__` runner:

```python
TRAP_ENTRY = {"name": "trap", "kind": "antiskill",
              "fingerprints": [["widget", "flush", "guard"]]}


def inject_trap(seconds_ago):
    """An anti-skill injection plus the symptom detection that triggered it.

    detect.py writes both in one hook call, so they share a timestamp -- the
    MIN_ESCAPE_S floor is what stops this pair from reading as a re-fire.
    """
    ledger.log_event("detection", "trap", detection="symptom",
                     trigger="symptom", session="s1", ts=ago(seconds_ago))
    ledger.log_event("injection", "trap", tier="warm", trigger="symptom",
                     session="s1", preexisting_fingerprint=1, ts=ago(seconds_ago))


def test_refire_inside_window_is_one_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(300))
        fire(repo)
        assert events("reconcile") == [("trap", None, "refire", "failure")]
        fire(repo)
        fire(repo, event="SessionEnd")
        assert len(events("reconcile")) == 1   # settled skills are not re-settled
    in_sandbox(check)


def test_triggering_symptom_alone_is_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        fire(repo)
        assert events("reconcile") == []
    in_sandbox(check)


def test_echo_inside_the_escape_floor_is_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1",
                         ts=ago(600 - (reconcile.MIN_ESCAPE_S - 10)))
        fire(repo)
        assert events("reconcile") == []
    in_sandbox(check)


def test_refire_past_the_window_is_a_fresh_trap_not_a_failure():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(reconcile.RECONCILE_WINDOW_S + 600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(60))
        fire(repo)
        assert events("reconcile") == []
    in_sandbox(check)


def test_session_end_without_refire_is_a_success():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        fire(repo)
        assert events("reconcile") == []       # Stop alone never concludes success
        fire(repo, event="SessionEnd")
        assert events("reconcile") == [("trap", None, "refire", "success")]
    in_sandbox(check)


def test_session_end_inside_the_escape_floor_concludes_nothing():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(reconcile.MIN_ESCAPE_S - 20)
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_regular_skills_get_no_refire_verdict():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [SKILL_ENTRY])
        ledger.log_event("injection", "fixer", session="s1",
                         preexisting_fingerprint=1, ts=ago(600))
        ledger.log_event("detection", "fixer", detection="symptom",
                         trigger="symptom", session="s1", ts=ago(300))
        fire(repo, event="SessionEnd")
        assert events("reconcile") == []
    in_sandbox(check)


def test_verdicts_are_scoped_to_their_own_session():
    def check(home):
        repo = git_repo(home / "repo")
        write_index(home, [TRAP_ENTRY])
        inject_trap(600)
        ledger.log_event("detection", "trap", detection="symptom",
                         trigger="symptom", session="s2", ts=ago(300))
        fire(repo)          # the re-fire belongs to s2, not s1
        assert events("reconcile") == []
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_reconcile.py`
Expected: FAIL on `test_refire_inside_window_is_one_failure` — `events("reconcile")` is `[]` because no verdict is written yet.

- [ ] **Step 3: Add the verdict rule**

In `scripts/reconcile.py`, add after `needs_fingerprint`:

```python
def refire_verdict(s, entry, now, final):
    """'failure', 'success', or None -- anti-skills only, once per session.

    An anti-skill's job is to stop one error recurring. The ledger records
    neither file nor route, so "the same error again" is skill identity plus
    time: a symptom detection between the escape floor and the window's end.
    A symptom after the window is a fresh trap, not a failure of this
    injection, and concludes nothing.
    """
    if s["settled"] or s["injected_ts"] is None or entry.get("kind") != "antiskill":
        return None
    lo = s["injected_ts"] + datetime.timedelta(seconds=MIN_ESCAPE_S)
    hi = s["injected_ts"] + datetime.timedelta(seconds=RECONCILE_WINDOW_S)
    if any(lo <= fired <= hi for fired in s["symptom_ts"]):
        return "failure"
    # Success is only concludable once the session is over, and only if the
    # model actually had a chance to fail.
    if final and (now - s["injected_ts"]).total_seconds() >= MIN_ESCAPE_S:
        return "success"
    return None
```

In `run`, insert before `return 0`:

```python
    for name, s, entry in pending:
        verdict = refire_verdict(s, entry, now, final)
        if verdict:
            # A verdict is not a detection: detection stays NULL so
            # skill_aggregates.uses (which counts detection rows) is untouched,
            # while skill_confidence picks the outcome up.
            _log("reconcile", name, trigger="refire", outcome=verdict, session=session)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_reconcile.py`
Expected: PASS, 19 tests.

- [ ] **Step 5: Verify no existing suite regressed**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/reconcile.py tests/test_reconcile.py
git commit -m "feat: anti-skill re-fire verdicts from timestamped symptom detections

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Bucket-gated hot ranking

**Files:**
- Modify: `scripts/sync.py` (replace `_usage_stats` at lines 88-104; the ranking block at lines 178-183; the budget walk at 187-198; `_write_index` at 107-118)
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: the `skill_confidence` view from Task 1.
- Produces: `index.json` entries gain a `"bucket"` key (`"unproven"` / `"working"` / `"trusted"`). Task 5 reads it. `sync._confidence()` replaces `sync._usage_stats()`, which is deleted — grep confirms nothing else references it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sync.py`, above the `__main__` runner:

```python
def earn_success(name, session="s1", ts=None):
    """Give a skill one successful session, the bar for `working`."""
    import ledger
    ledger.log_event("detection", name, detection="verification",
                     outcome="success", session=session, ts=ts)


def test_index_entries_carry_a_bucket():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "unproven"
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["bucket"] == "working"
    in_sandbox(check)


def test_unproven_skill_never_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        counts = sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "warm"
        assert counts["materialized"] == 0
        assert not native_md(home, "alpha").exists()
    in_sandbox(check)


def test_working_skill_goes_hot():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        earn_success("alpha")
        sync.sync()
        entry = read_index(home)["entries"][0]
        assert entry["tier"] == "hot"
        assert native_md(home, "alpha").exists()
    in_sandbox(check)


def test_trusted_outranks_working_for_a_scarce_hot_slot():
    def check(home):
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        earn_success("alpha", session="s1")          # working
        earn_success("beta", session="s1")           # trusted: two sessions
        earn_success("beta", session="s2")

        def run():
            sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}, tiers
        with_budget("10", run)
    in_sandbox(check)
```

Then update the two existing tests whose fixtures assume an empty ledger makes a skill hot. **Their assertions do not change** — only the setup, so they keep testing budget overflow and anti-skill exclusion rather than accidentally testing the new gate.

In `test_hot_budget_overflow_goes_warm`, replace the two `ledger.log_event("injection", "beta")` lines with:

```python
        # Both are hot-ELIGIBLE (the gate is not what this test measures);
        # beta outranks alpha on bucket, so the single slot is beta's.
        earn_success("alpha", session="s1")             # working
        earn_success("beta", session="s1")              # trusted
        earn_success("beta", session="s2")
```

and delete the now-unused `import ledger` line if nothing else in that function uses it.

In `test_antiskills_do_not_consume_hot_budget`, add after both `trust.record` calls:

```python
        # Both earn eligibility, and identical timestamps make the tiebreak
        # name ASC -- so "aaa-trap" would take the only slot if anti-skills
        # still competed. That ordering is what gives this test its force.
        stamp = "2026-01-01T00:00:00+00:00"
        earn_success("aaa-trap", session="s1", ts=stamp)
        earn_success("zeta", session="s1", ts=stamp)
```

and replace the stale comment about "the interim ranking (no ledger history)" with:

```python
        # "aaa-trap" sorts BEFORE "zeta" once both are eligible and tied.
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_sync.py`
Expected: FAIL on `test_index_entries_carry_a_bucket` with `KeyError: 'bucket'`.

- [ ] **Step 3: Replace usage stats with confidence**

In `scripts/sync.py`, delete `_usage_stats` entirely and add in its place:

```python
BUCKET_RANK = {"trusted": 0, "working": 1, "unproven": 2}
HOT_ELIGIBLE = ("trusted", "working")
UNKNOWN = ("unproven", 0, "")


def _confidence():
    """{skill: (bucket, success_sessions, last_used)}; empty on any ledger failure.

    An empty map reads as `unproven` everywhere, which is the safe direction:
    a broken ledger empties the hot tier instead of promoting on stale data.
    """
    stats = {}
    try:
        con = ledger.connect()
        try:
            for skill, wins, last_used, bucket in con.execute(
                    "SELECT skill, success_sessions, last_used, bucket"
                    " FROM skill_confidence"):
                stats[skill] = (bucket or "unproven", wins or 0, last_used or "")
        finally:
            con.close()
    except Exception:
        pass
    return stats
```

- [ ] **Step 4: Gate and reorder the hot walk**

Replace the interim ranking block (the comment plus the four sort lines) with:

```python
    # Hot ranking (slice C2 design 5): bucket, then successful sessions, then
    # recency, then name -- via chained stable sorts, last sort = primary key.
    conf = _confidence()
    for s in trusted:
        s["bucket"] = conf.get(s["name"], UNKNOWN)[0]
    trusted.sort(key=lambda s: s["name"])
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)[2], reverse=True)
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)[1], reverse=True)
    trusted.sort(key=lambda s: BUCKET_RANK.get(s["bucket"], 2))
```

In the budget walk, add the gate directly after the anti-skill check:

```python
        # A skill that has never demonstrably worked does not get to sit in
        # every session's standing context (spec 7). Warm still retrieves it
        # on relevance, which is how it earns its way out of `unproven`.
        if s["bucket"] not in HOT_ELIGIBLE:
            s["tier"] = "warm"
            continue
```

- [ ] **Step 5: Compile the bucket into the index**

In `_write_index`, add `"bucket": s["bucket"],` to the entry dict so hooks never query the ledger.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tests/test_sync.py`
Expected: PASS, 23 tests, including the two updated ones.

- [ ] **Step 7: Confirm nothing else referenced the deleted helper**

Run: `grep -rn "_usage_stats" scripts/ tests/`
Expected: no output.

- [ ] **Step 8: Verify no existing suite regressed**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done`
Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add scripts/sync.py tests/test_sync.py
git commit -m "feat: hot tier gated on working-or-better, buckets compiled into the index

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Hedged wording for unproven injections

**Files:**
- Modify: `scripts/retrieve.py` (the `picked` tuples and the `parts` list in `run_hook`, lines 249-296)
- Test: `tests/test_retrieve.py`

**Interfaces:**
- Consumes: the `"bucket"` key Task 4 compiles into `index.json` entries.
- Produces: `preamble(name, bucket) -> str`. `picked` becomes a 4-tuple `(name, body, preexisting, bucket)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retrieve.py`, above the `__main__` runner (match the file's existing helper names for building an index and capturing hook stdout):

```python
def test_unproven_injection_is_hedged():
    assert retrieve.preamble("foo", "unproven") == (
        "--- SkillForge retrieved skill 'foo' (unproven -- never verified in a"
        " real session; apply only if it clearly fits): ---")


def test_working_and_trusted_injections_are_not_hedged():
    for bucket in ("working", "trusted"):
        assert retrieve.preamble("foo", bucket) == (
            "--- SkillForge retrieved skill 'foo' (apply if relevant): ---")


def test_missing_bucket_is_treated_as_unproven():
    # An index compiled before slice C2 has no bucket key. Hedging is the
    # safe default: it understates confidence rather than inventing it.
    assert "unproven" in retrieve.preamble("foo", None)
```

```python
def test_hedge_reaches_the_injected_context():
    def check(home):
        write_index(home, [dict(entry(home, "stripe-webhook",
                                      "stripe webhook signature verification"),
                                bucket="unproven")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "apply only if it clearly fits" in ctx
        assert "(apply if relevant)" not in ctx
        # the existing name parser must keep working on a hedged header
        assert injected_names(out) == ["stripe-webhook"]
    in_sandbox(check)


def test_working_skill_reaches_context_unhedged():
    def check(home):
        write_index(home, [dict(entry(home, "stripe-webhook",
                                      "stripe webhook signature verification"),
                                bucket="working")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "(apply if relevant)" in ctx
        assert "unproven" not in ctx
    in_sandbox(check)
```

Note the constraint these two tests pin down: `injected_names` (the existing helper at `tests/test_retrieve.py:131`) parses lines starting with `--- SkillForge retrieved skill '` and splits on the first quote pair. The hedged header must keep that prefix and keep the skill name in the first quotes, or several existing tests break. The `preamble` format string above satisfies this; do not reorder it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_retrieve.py`
Expected: FAIL with `AttributeError: module 'retrieve' has no attribute 'preamble'`.

- [ ] **Step 3: Add the preamble function**

In `scripts/retrieve.py`, add above `run_hook`:

```python
def preamble(name, bucket):
    """Injection header, hedged for skills nothing has ever confirmed.

    The paired A/B benchmark's transfer arm scored 0/6 -- a plausible,
    same-class skill, ledger-confirmed delivered every time, that did not fit
    the bug. Naming that state is the one thing the model cannot read off the
    skill body. A missing bucket (a pre-C2 index) hedges too: understating
    confidence is the safe direction.
    """
    note = ("apply if relevant" if bucket in ("working", "trusted")
            else "unproven -- never verified in a real session;"
                 " apply only if it clearly fits")
    return "--- SkillForge retrieved skill '%s' (%s): ---" % (name, note)
```

- [ ] **Step 4: Carry the bucket through `run_hook`**

Change the append to a 4-tuple:

```python
        picked.append((name, body, preexisting, e.get("bucket")))
```

Replace the `parts` construction with:

```python
    parts = ["%s\n%s" % (preamble(name, bucket), body)
             for name, body, _, bucket in picked]
```

And widen the ledger loop's unpacking:

```python
    for name, _, preexisting, _bucket in picked:
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 tests/test_retrieve.py`
Expected: PASS, 32 tests.

- [ ] **Step 6: Verify no existing suite regressed**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done`
Expected: no output.

Note: `detect.py`'s anti-skill preamble is deliberately untouched. A symptom that just matched in tool output is the strongest relevance evidence the system produces; hedging it would weaken the highest-precision channel.

- [ ] **Step 7: Commit**

```bash
git add scripts/retrieve.py tests/test_retrieve.py
git commit -m "feat: hedge injection wording for unproven skills

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation and whole-slice verification

**Files:**
- Modify: `README.md` (the status paragraph, lines 60-63)

**Interfaces:**
- Consumes: everything above. Produces: no code.

- [ ] **Step 1: Update the README status paragraph**

Replace the "Not yet built: slice C2 ... and slice D" sentence so slice C2 is listed as shipped, and add a short paragraph in the body describing what the reconciler does. Keep the existing voice — declarative, no marketing. It must state:

- The reconciler runs at the end of every turn and at session end, costs one ledger read when nothing is pending, and derives everything from the ledger so re-runs are idempotent.
- A skill's confidence is `unproven`, `working`, or `trusted`, counted in distinct sessions, and only `working`-or-better skills compete for the hot tier.
- `trusted` here means repeatedly verified in real sessions; the parent spec's Tier A conjunct arrives in slice D.
- `unproven` skills are injected with hedged wording.

- [ ] **Step 2: Run the full suite**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done; echo done`
Expected: `done` with no FAILED lines.

- [ ] **Step 3: Count the tests**

Run: `grep -c '^def test_' tests/test_*.py`
Expected: 9 suites; the total should be 180 — 145 existing plus 8 (ledger), 19 (reconcile), 4 (sync), 4 (retrieve).

- [ ] **Step 4: Verify every hook still exits 0 on garbage input**

Run:

```bash
for h in retrieve detect reconcile; do
  echo 'not json' | python3 "scripts/$h.py" >/dev/null 2>&1; echo "$h exit=$?"
done
```

Expected: `exit=0` for all three.

- [ ] **Step 5: Smoke-test a real promotion cycle end to end**

Save this to the scratchpad (NOT into the repo) and run it with `python3`. It exercises the whole slice against real files: save, compile, gate, promote, materialize.

```python
import json, os, pathlib, sys, tempfile
sys.path.insert(0, "scripts")

old_home = os.environ["HOME"]
with tempfile.TemporaryDirectory() as tmp:
    os.environ["HOME"] = tmp
    try:
        home = pathlib.Path(tmp)
        import ledger, sync, trust
        d = home / ".claude" / "skillforge" / "skills" / "demo"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: demo\nkind: skill\n"
            "description: Demo skill for the smoke test. Do NOT use otherwise.\n"
            'verification.command: "pytest tests/test_demo.py"\n'
            "---\n## Procedure\n1. Do it.\n## Verification\nRun the command.\n",
            encoding="utf-8")
        trust.record("demo", (d / "SKILL.md").read_text(encoding="utf-8"), "self")

        sync.sync()
        e = json.loads((home / ".claude/skillforge/index.json").read_text())["entries"][0]
        assert (e["bucket"], e["tier"]) == ("unproven", "warm"), e
        print("unproven -> warm, not materialized:",
              not (home / ".claude/skills/skillforge-hot/demo/SKILL.md").exists())

        for session in ("smoke-1", "smoke-2"):
            ledger.log_event("detection", "demo", detection="verification",
                             outcome="success", session=session)
        sync.sync()
        e = json.loads((home / ".claude/skillforge/index.json").read_text())["entries"][0]
        assert (e["bucket"], e["tier"]) == ("trusted", "hot"), e
        native = home / ".claude/skills/skillforge-hot/demo/SKILL.md"
        assert native.exists()
        print("two sessions -> trusted, hot, materialized:", native.exists())
    finally:
        os.environ["HOME"] = old_home
```

Expected output: two `True` lines and no assertion error. Report it.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document the slice C2 outcome interpretation layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## After the last task

Run a whole-branch review before merging. Slices A, B, and C1 each caught real defects at this stage, including one Critical that every task-level review missed and only the whole-branch review found. Do not skip it.
