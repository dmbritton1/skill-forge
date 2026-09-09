# Q1 Distiller Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-phase harness that lets a session distill its own skill and a later session be measured with it, then run the 60-session batch and write it up.

**Architecture:** Phase 1 (`bench/distill.py`) runs a repair session, scores the repair, and extracts whatever the distiller saved into a committed archive under `bench/distilled/`. Phase 2 is the existing `bench/run.py` with one new flag, `--skill-from`, pointing at an archived draft. Two support scripts sit between them: `bench/dryrun.py` predicts delivery before any probe session is spent, and `bench/judge.py` scores the archived drafts retrospectively. `bench/libguard.py` keeps the operator's real library out of the experiment.

**Tech Stack:** Python 3 stdlib only (no pytest, no fixtures — this repo's suites are plain `assert` functions with a `__main__` runner printing `PASS <name>` / `FAIL <name>`). SQLite via `scripts/ledger.py`. Sessions are `claude -p --permission-mode bypassPermissions --model claude-opus-5`.

**Spec:** `docs/superpowers/specs/2026-09-08-q1-distiller-experiment-design.md`

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include these.

- **n=3 per cell.** Say so in anything you conclude.
- **60 sessions:** 12 phase-1, 36 phase-2 probe, 6 phase-2 control, 6 phase-2 transfer (brief Q2,
  folded in as a pre-registered secondary — spec §1 and §8).
- **Model is pinned** to `claude-opus-5` on every session. Never the account default.
- **The floor is this batch's own control arm.** The 2026-08-11 figure is corroboration and is labelled as such. Every historical `control` row lacks a `model` key.
- **All drafts from a resolved repair are probed, 3 runs each.** No draft is selected, skipped, or re-rolled after its content is seen.
- **A draft from an unresolved repair is archived and reported, never probed.**
- **No cell is dropped after its score is seen.**
- **A stage-5 zero is reported against the pre-probe BM25 prediction** recorded before the run, not reinterpreted afterward.
- **A phase-1 abort, timeout, or rejection is a result.** Reported, not re-run.
- **Nothing else may run on the machine during the batch** — including a one-off `claude -p` in `/tmp`. `index.json` and `trust.json` are user-global and last-writer-wins.
- **`bench/distilled/` is committed.** Un-indexed data is what produced the two false claims the register caught.
- **The phase-1 prompt is fixed** across all 12 phase-1 sessions, except for the repair task's own prompt text spliced in. It is an experimental variable and must not drift between cells.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/save_skill.py` *(modify)* | Gains one env-var seam suppressing the post-save critique spawn |
| `bench/run.py` *(modify)* | Phase 2: `--skill-from`, derived clone segment, five new result keys, warm-tier assertion |
| `bench/libguard.py` *(new)* | Snapshot / diff / prune / restore of the operator's global library. Used by `distill.py`; standalone-testable |
| `bench/distill.py` *(new)* | Phase 1: preconditions, prepare, session, repair scoring, extraction, `meta.json` |
| `bench/dryrun.py` *(new)* | Pre-probe BM25 delivery prediction over the archive |
| `bench/judge.py` *(new)* | Retrospective judging of archived drafts |
| `bench/backfill.py` *(new)* | One-shot, idempotent `skill_source` backfill of the two historical results files |
| `tests/test_bench_run.py` *(new)* | Covers `run.py`'s new pure helpers and `backfill.py` |
| `tests/test_bench_distill.py` *(new)* | Covers `libguard.py`, `distill.py`'s pure parts, `dryrun.py`, `judge.py`'s pure parts |
| `tests/test_save_skill.py` *(modify)* | Two tests for the critique seam |

Phase 1's and phase 2's session-running paths are not unit-tested — they shell out to `claude`. Every part that can be tested without a session is factored into a pure function so that it is.

---

## Task 1: Suppress the post-save critique spawn

`save_skill.py:420` calls `_spawn_validation` on **every** create — `subprocess.Popen(..., start_new_session=True)`, detached, never waited on — and `validate.py critique` is itself a real `claude -p` child. Unsuppressed, this batch spawns up to 48 extra sessions, violating the "nothing else may run" constraint, adding unbudgeted cost, and racing `library.py delete` during phase-1 containment.

**Deviation from the review, and why.** The review proposed a `--no-critique` flag. A flag cannot work: the phase-1 session invokes `save_skill.py` *itself* — that invocation is the pipeline stage under test — so nothing is in a position to pass one. It must be an environment variable, inherited by the session and by every child it spawns, exactly as `SKILLFORGE_LEDGER` and `SKILLFORGE_FORCE_HOT` already are.

**Files:**
- Modify: `scripts/save_skill.py` (new function near `_spawn_validation` at :203; call site at :413-421)
- Test: `tests/test_save_skill.py`

**Interfaces:**
- Consumes: nothing
- Produces: `SKILLFORGE_NO_CRITIQUE=1` suppresses both critique paths in `save_skill.main()`. `bench/distill.py` (Task 5) and `bench/judge.py` (Task 7) both export it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_save_skill.py`, above the `if __name__ == "__main__":` block. Note the file already stubs `save_skill._spawn_validation` inert at module level, so these install their own stub over the top and restore it — the established pattern in this file.

```python
def test_no_critique_env_suppresses_the_detached_spawn():
    def check(home, tmp):
        seen = []
        real = save_skill._spawn_validation
        save_skill._spawn_validation = lambda name, mode: seen.append((name, mode))
        os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"
        try:
            assert save_skill.main(
                [write_draft(tmp, VALID_SKILL), "--scope", "global"]) == 0
        finally:
            save_skill._spawn_validation = real
            os.environ.pop("SKILLFORGE_NO_CRITIQUE", None)
        assert seen == [], seen
    in_sandbox(check)


def test_critique_spawns_when_the_env_var_is_absent():
    def check(home, tmp):
        seen = []
        real = save_skill._spawn_validation
        save_skill._spawn_validation = lambda name, mode: seen.append((name, mode))
        os.environ.pop("SKILLFORGE_NO_CRITIQUE", None)
        try:
            assert save_skill.main(
                [write_draft(tmp, VALID_SKILL), "--scope", "global"]) == 0
        finally:
            save_skill._spawn_validation = real
        assert seen == [("test-skill", "critique")], seen
    in_sandbox(check)


def test_no_critique_env_suppresses_the_blocking_update_path():
    def check(home, tmp):
        assert save_skill.main(
            [write_draft(tmp, VALID_SKILL), "--scope", "global"]) == 0
        seen = []
        real = save_skill._run_validation
        save_skill._run_validation = lambda name, mode: seen.append((name, mode))
        os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"
        try:
            assert save_skill.main(
                [write_draft(tmp, VALID_SKILL), "--scope", "global",
                 "--action", "update"]) == 0
        finally:
            save_skill._run_validation = real
            os.environ.pop("SKILLFORGE_NO_CRITIQUE", None)
        assert seen == [], seen
    in_sandbox(check)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_save_skill.py`
Expected: `FAIL test_no_critique_env_suppresses_the_detached_spawn` and `FAIL test_no_critique_env_suppresses_the_blocking_update_path` (both see the stub called). `test_critique_spawns_when_the_env_var_is_absent` should already PASS — it pins current behaviour so Step 3 cannot silently disable critique for everyone.

- [ ] **Step 3: Add the seam**

In `scripts/save_skill.py`, immediately above `def _spawn_validation` (line 203):

```python
def _critique_suppressed():
    """Test-only (Q1 bench): skip the post-save critique.

    An env var rather than a flag, because the one caller that needs it
    cannot pass one: Q1's phase-1 session invokes save_skill.py itself, and
    that invocation is the pipeline stage under test. Same lever shape as
    SKILLFORGE_LEDGER and SKILLFORGE_FORCE_HOT, read at exactly one point.

    Why it exists: a create spawns critique detached and never waits on it,
    so a 60-session batch would fire up to 54 extra `claude -p` children --
    unbudgeted, and racing the containment `library.py delete` for the same
    name. Q1 runs critique retrospectively instead (bench/judge.py).
    """
    return os.environ.get("SKILLFORGE_NO_CRITIQUE", "").strip() == "1"
```

Then change the call site at line 413-421 from:

```python
    try:
        if args.action == "update":
```

to:

```python
    try:
        if _critique_suppressed():
            pass
        elif args.action == "update":
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_save_skill.py`
Expected: all PASS, including the two pre-existing spawn tests.

- [ ] **Step 5: Run the whole suite for regressions**

Run: `for f in tests/test_*.py; do printf '%-32s ' "$f"; python3 "$f" >/dev/null 2>&1 && echo OK || echo FAIL; done`
Expected: 16 OK.

- [ ] **Step 6: Commit**

```bash
git add scripts/save_skill.py tests/test_save_skill.py
git commit -m "feat: SKILLFORGE_NO_CRITIQUE seam, so a bench batch stops spawning 48 sessions"
```

---

## Task 2: Phase 2 — `--skill-from`, clone segment, result keys, warm assertion

**Files:**
- Modify: `bench/run.py` (module globals ~:55; `install_skill` :145-153; `one` :194-247; `main` argparse :254-263)
- Test: `tests/test_bench_run.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces, all module-level in `bench/run.py`:
  - `SKILL_FROM: str | None` — absolute path to a distilled draft
  - `skill_src(task) -> Path` — the SKILL.md `install_skill` saves
  - `arm_segment(arm) -> str` — the clone-path segment, derived not passed
  - `skill_name(path) -> str | None` — the `name:` from a draft's frontmatter
  - `tier_of(name) -> str | None` — that skill's tier in the user-global index
  - Result rows gain `skill_source`, `distiller`, `draw`, `skill_path`, `tier_at_install`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_run.py`:

```python
"""Tests for the bench harness's Q1 additions. Run: python3 tests/test_bench_run.py"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import run as bench_run

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

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_run.py`
Expected: FAIL on every test — `AttributeError: module 'run' has no attribute 'arm_segment'`.

- [ ] **Step 3: Add the module global**

In `bench/run.py`, immediately after the `FORCE_HOT = False` line (:55):

```python
# Q1: absolute path to a distilled draft, replacing the task's hand-authored
# skill. Off = None. The clone path segment is DERIVED from this (arm_segment)
# rather than passed, because a forgotten segment is the exact bug that let
# E5's two arms overwrite each other.
SKILL_FROM = None
```

- [ ] **Step 4: Add the four helpers**

In `bench/run.py`, immediately above `def install_skill` (:145):

```python
def skill_src(task):
    """The SKILL.md install_skill saves: the task's own, or Q1's override."""
    return Path(SKILL_FROM) if SKILL_FROM else ROOT / "skills" / (task["skill"] + ".md")


def arm_segment(arm):
    """Path-unique segment per treatment arm, derived from the run's config.

    Every arm this harness has ever had passes `--arm treatment`, so without
    this the clone AND the per-run ledger share a path and the second batch
    silently overwrites the first one's evidence. It did, once (E5).
    """
    if arm != "treatment":
        return ""
    if FORCE_HOT:
        return "-hot"
    if SKILL_FROM:
        # .../distilled/<trap>/<distiller>/<draw>/SKILL.md
        parts = Path(SKILL_FROM).resolve().parts
        return "-d-%s-%s" % (parts[-3].replace("-", ""), parts[-2])
    return ""


def skill_name(path):
    """The `name:` from a SKILL.md's frontmatter, or None.

    A distilled draft's name is whatever the distiller chose, so it cannot be
    read off the task config the way a hand-authored one can.
    """
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip() or None
    return None


def tier_of(name):
    """That skill's tier in the user-global index, or None.

    retrieve.eligible() requires tier == "warm", so a skill that landed hot
    produces no injection row at all -- and the funnel's delivery stage would
    read the strongest delivery path as a delivery failure. Asserted rather
    than assumed: b35f756 already cost a batch to exactly this class of bug.
    """
    p = Path.home() / ".claude" / "skillforge" / "index.json"
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for e in idx.get("entries", []):
        if e.get("name") == name:
            return e.get("tier")
    return None
```

- [ ] **Step 5: Run to verify the helper tests pass**

Run: `python3 tests/test_bench_run.py`
Expected: all PASS.

- [ ] **Step 6: Wire the helpers into `install_skill` and `one`**

In `install_skill` (:145), replace the `src = ...` line:

```python
def install_skill(task, dest, plugin_dir):
    """Put the skill in the clone's PROJECT store via the enforced save path."""
    src = skill_src(task)
```

In `one` (:194), replace the `dest = ...` assignment:

```python
    dest = WORK / ("%s-%s%s-%d" % (task["id"], arm, arm_segment(arm), run_idx))
```

After the `skill_note = install_skill(...)` line, add the tier read:

```python
    skill_note = install_skill(task, dest, plugin_dir) if arm == "treatment" else ""
    installed = skill_name(skill_src(task)) if arm == "treatment" else None
    tier_at_install = tier_of(installed) if installed else None
    if arm == "treatment" and tier_at_install != "warm":
        print("  WARNING: %s installed at tier %r, not warm -- retrieve.eligible()"
              " will skip it and no injection row will be logged"
              % (installed, tier_at_install))
```

Then extend the `rec` dict with the five new keys:

```python
    parts = Path(SKILL_FROM).resolve().parts if SKILL_FROM else None
    rec = {"task": task["id"], "arm": arm, "run": run_idx,
           "resolved": all(post.values()), "per_test": post,
           "session_ok": sess["ok"], "secs": sess["secs"], "model": MODEL,
           "delivery": "hot" if os.environ["SKILLFORGE_FORCE_HOT"] else "warm",
           "skill_source": None if arm != "treatment" else (
               "distilled" if SKILL_FROM else "authored"),
           "distiller": parts[-3] if (parts and arm == "treatment") else None,
           "draw": int(parts[-2]) if (parts and arm == "treatment") else None,
           "skill_path": str(skill_src(task)) if arm == "treatment" else None,
           "tier_at_install": tier_at_install,
           "skill_note": skill_note, "test_tail": tail,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
```

- [ ] **Step 7: Add the CLI flag**

In `main`, after the `--force-hot` argument (:257-259):

```python
    ap.add_argument("--skill-from", default=None,
                    help="Q1: install this SKILL.md instead of the task's own."
                         " The path decides the clone segment (test-only)")
```

And in the globals block below `args = ap.parse_args(argv)`:

```python
    global MODEL, FORCE_HOT, SKILL_FROM
    MODEL = args.model
    FORCE_HOT = args.force_hot
    SKILL_FROM = args.skill_from
```

- [ ] **Step 8: Verify the config check still passes**

Run: `python3 bench/run.py --check`
Expected: `config ok: 10 task(s), all paths resolve`

- [ ] **Step 9: Run both suites**

Run: `python3 tests/test_bench_run.py && for f in tests/test_*.py; do python3 "$f" >/dev/null 2>&1 || echo "FAIL $f"; done`
Expected: all PASS from the first, no FAIL lines from the second.

- [ ] **Step 10: Commit**

```bash
git add bench/run.py tests/test_bench_run.py
git commit -m "feat(bench): --skill-from for Q1, with the arm segment derived not passed"
```

---

## Task 3: Backfill `skill_source` onto the historical rows

Every pre-existing row lacks the five new keys, so a filter on `skill_source == "authored"` silently excludes the comparators the whole design depends on. The spec prefers a backfill over a documented read rule, on its own argument that un-indexed data is what produced the register's two false claims.

**Files:**
- Create: `bench/backfill.py`
- Modify: `bench/results.jsonl`, `bench/results-round1.jsonl` (data)
- Test: `tests/test_bench_run.py` (append)

**Interfaces:**
- Consumes: nothing
- Produces: `backfill.backfill(path) -> int` (rows changed). Idempotent.

`results-leaky-stub.jsonl` is deliberately **not** backfilled — it is superseded as an authoring design and only its control rows are live. The read rule for it is stated in the spec.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bench_run.py`, above the `__main__` block:

```python
import backfill


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_run.py`
Expected: `ModuleNotFoundError: No module named 'backfill'`.

- [ ] **Step 3: Write `bench/backfill.py`**

```python
#!/usr/bin/env python3
"""One-shot, idempotent: label historical result rows with `skill_source`.

Rows written before Q1 carry none of the source keys, so a filter on
`skill_source == "authored"` silently excludes the pilot and E1 comparators
that every Q1 claim is read against. A documented read rule would work until
someone forgot it; the register's own lesson is that un-indexed data gets
described from memory and described wrong.

Only `skill_source` is backfilled. `distiller`, `draw` and `skill_path` are
genuinely unknown for a historical row and inventing them would be worse than
their absence. `results-leaky-stub.jsonl` is not backfilled: it is superseded
as an authoring design and only its control rows are live.

Run: python3 bench/backfill.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ("results.jsonl", "results-round1.jsonl")


def backfill(path):
    """Add `skill_source` to rows lacking it. Returns rows changed."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    out, changed = [], 0
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if "skill_source" not in row:
            # control installs no skill at all, so "authored" would be a lie.
            row["skill_source"] = None if row.get("arm") == "control" else "authored"
            changed += 1
        out.append(json.dumps(row))
    if changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def main():
    for name in FILES:
        print("%s: %d row(s) labelled" % (name, backfill(ROOT / name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `python3 tests/test_bench_run.py`
Expected: all PASS.

- [ ] **Step 5: Run the backfill on the real data**

Run: `python3 bench/backfill.py`
Expected: `results.jsonl: 48 row(s) labelled` and `results-round1.jsonl: 18 row(s) labelled`.

- [ ] **Step 6: Verify the data is intact**

Run:
```bash
python3 -c "
import json, collections
c = collections.Counter()
for f in ('bench/results.jsonl','bench/results-round1.jsonl'):
    for l in open(f):
        r = json.loads(l); c[(r['arm'], r['skill_source'])] += 1
print(sorted(c.items()))
print('rows:', sum(c.values()))
"
```
Expected: `[(('control', None), 9), (('treatment', 'authored'), 57)]` and `rows: 66`. Re-running `python3 bench/backfill.py` must report `0 row(s) labelled` for both files.

- [ ] **Step 7: Commit**

```bash
git add bench/backfill.py bench/results.jsonl bench/results-round1.jsonl tests/test_bench_run.py
git commit -m "chore(bench): label historical rows with skill_source, so Q1 filters find the comparators"
```

---

## Task 4: `bench/libguard.py` — keep the real library out of the experiment

`save_skill.py::store_dir` resolves a `--scope global` save to `Path.home()/.claude/skillforge/`, and the distillation contract has the **model** choose the scope. A phase-1 session that judges its trap general writes into the operator's real library. Separately, `trust.py:24` resolves `trust.json` to `Path.home()` unconditionally and `save_skill.py:390` records on every save, so all 48 saves touch the real trust registry.

**Files:**
- Create: `bench/libguard.py`
- Test: `tests/test_bench_distill.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `snapshot() -> dict` with keys `stores`, `global_index`, `project_index`, `trust` (all sorted lists of names)
  - `new_global_skills(before) -> list[str]` — global store entries added since `before`
  - `prune_trust(names) -> int` — drop those keys from `trust.json`
  - `drift(before) -> list[str]` — human-readable mismatches against `before`, empty when clean

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_distill.py`:

```python
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

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_distill.py`
Expected: `ModuleNotFoundError: No module named 'libguard'`.

- [ ] **Step 3: Write `bench/libguard.py`**

```python
#!/usr/bin/env python3
"""Keep Q1's 60 sessions out of the operator's real SkillForge library.

Three separate leaks, none of which the bench's existing SKILLFORGE_LEDGER
isolation covers:

1. The global STORE. save_skill.store_dir resolves --scope global to
   Path.home(), and the distillation contract has the MODEL choose the scope
   ("mentions repo-specific paths/conventions -> project; otherwise global").
   A phase-1 session that judges its trap general writes into the real store.
2. trust.json. trust.py resolves it to Path.home() unconditionally and
   save_skill records on EVERY save, project-scoped ones included.
3. index.json. User-global and last-writer-wins.

Nothing here sandboxes HOME: the `claude` CLI reads it for credentials, so
swapping it risks breaking authentication mid-batch. Containment is therefore
reactive -- snapshot, diff after each session, revert, assert at close -- and
a batch whose drift cannot be reverted is invalidated rather than repaired.
"""
import json
from pathlib import Path

KINDS = ("skills", "antiskills")


def _root():
    # Read per call, never cached at import: the tests move HOME.
    return Path.home() / ".claude" / "skillforge"


def _read_json(name, default):
    try:
        return json.loads((_root() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _store_names():
    out = []
    for kind in KINDS:
        d = _root() / kind
        if not d.is_dir():
            continue
        out += ["%s/%s" % (kind, p.name) for p in d.iterdir() if p.is_dir()]
    return sorted(out)


def _index_names(scope):
    entries = _read_json("index.json", {}).get("entries", [])
    return sorted(e.get("name", "") for e in entries if e.get("scope") == scope)


def snapshot():
    """The four pieces of user-global state a batch can disturb."""
    return {"stores": _store_names(),
            "global_index": _index_names("global"),
            "project_index": _index_names("project"),
            "trust": sorted(_read_json("trust.json", {}))}


def new_global_skills(before):
    """Bare names added to the global store since `before`."""
    added = set(_store_names()) - set(before["stores"])
    return sorted(n.split("/", 1)[1] for n in added)


def prune_trust(names):
    """Drop `names` from trust.json. Returns keys removed."""
    data = _read_json("trust.json", {})
    removed = 0
    for n in names:
        if data.pop(n, None) is not None:
            removed += 1
    if removed:
        (_root() / "trust.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8")
    return removed


def drift(before):
    """Human-readable mismatches against `before`; empty list means clean.

    Compares SETS of names, never index.json's bytes: sync rewrites the file
    wholesale on every run, so `compiled_ts` and entry order change constantly
    and a byte comparison would report drift on a clean batch.
    """
    now = snapshot()
    out = []
    for key, label in (("stores", "global store"),
                       ("global_index", "global index entries"),
                       ("project_index", "project index entries"),
                       ("trust", "trust.json keys")):
        gone = sorted(set(before[key]) - set(now[key]))
        extra = sorted(set(now[key]) - set(before[key]))
        if gone:
            out.append("%s missing: %s" % (label, ", ".join(gone)))
        if extra:
            out.append("%s unexpected: %s" % (label, ", ".join(extra)))
    return out
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `python3 tests/test_bench_distill.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bench/libguard.py tests/test_bench_distill.py
git commit -m "feat(bench): libguard, because the distiller picks its own scope"
```

---

## Task 5: `bench/distill.py` — phase 1

**Files:**
- Create: `bench/distill.py`
- Test: `tests/test_bench_distill.py` (append)

**Interfaces:**
- Consumes: `libguard.snapshot`, `libguard.new_global_skills`, `libguard.prune_trust` (Task 4); `run.prepare`, `run.score`, `run.sh`, `run.WORK`, `run.REPO_ROOT`, `run.MODEL` (existing + Task 2)
- Produces:
  - `DISTILLERS = {"learn-failure": "antiskills", "learn": "skills"}`
  - `outcome(repair_resolved, timed_out, draft, save_rc) -> str` — one of `repair_unresolved`, `timed_out`, `aborted`, `rejected`, `saved`
  - `extract(clone, distiller) -> Path | None` — the store copy of whatever saved
  - `archive_dir(trap, distiller, draw) -> Path` — `bench/distilled/<trap>/<distiller>/<draw>`
  - `preflight() -> list[str]` — reasons the next draw must not start

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_distill.py`, above the `__main__` block:

```python
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


def test_extract_looks_in_the_kind_directory_the_distiller_writes():
    with tempfile.TemporaryDirectory() as tmp:
        clone = pathlib.Path(tmp)
        store = clone / ".claude" / "skillforge" / "skills" / "a-skill"
        store.mkdir(parents=True)
        store.joinpath("SKILL.md").write_text("X\n", encoding="utf-8")
        assert distill.extract(clone, "learn") is not None
        assert distill.extract(clone, "learn-failure") is None


def test_extract_is_none_when_nothing_saved():
    with tempfile.TemporaryDirectory() as tmp:
        assert distill.extract(pathlib.Path(tmp), "learn-failure") is None


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_distill.py`
Expected: `ModuleNotFoundError: No module named 'distill'`.

- [ ] **Step 3: Write `bench/distill.py`**

```python
#!/usr/bin/env python3
"""Q1 phase 1: a session fixes a bug, distills its own skill, and the draft is
archived for a later session to be measured with.

One draw = one repair session + one distillation. Three draws per
(trap, distiller). The draft is extracted to bench/distilled/, which is
COMMITTED -- un-indexed data is what produced the two false claims the
register caught.

Five outcomes, none of them a harness error (spec section 5). The one worth
naming: `repair_unresolved`. A session that flails, fixes nothing, and then
dutifully distills a confident anti-skill about a mechanism it never found
produces a clean `save_skill` exit 0 and would otherwise enter the funnel as
a healthy emission. It is archived and reported, and never probed.

Usage:
    python3 bench/distill.py --trap A --distiller learn-failure --draws 3
    python3 bench/distill.py --all --draws 3
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libguard
import run as bench_run

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "distilled"

# Which store directory each distiller writes into, which is also the only
# reliable way to tell what `kind:` it emitted.
DISTILLERS = {"learn-failure": "antiskills", "learn": "skills"}

# The repair task that carries each trap, and the skill each distiller is
# asked to produce from it. The probe task for the same trap is the author
# task on the SAME bug -- see the spec's cell table.
TRAPS = {"A": "sf-escaping-breaks-symptom-match",
         "B": "sf-truncation-reports-absent"}

# Sized for repair PLUS a full distillation (transcript review, novelty gate,
# duplicate check, draft, secret scan, save). run.py's 900s is sized for an
# author-mode session that writes one function; nothing in the record measures
# this workload, so this is a ceiling to be replaced by a piloted number.
PHASE1_TIMEOUT_S = 1800

PROMPT = (
    "%s\n\n"
    "When the tests pass, distill what you learned in this session using the "
    "%s skill. Follow its contract exactly, including the novelty self-gate -- "
    "aborting because the knowledge is model-obvious is a good outcome, not a "
    "failure. There is no human here to approve the draft: review it yourself "
    "as if you were the reviewer, and if you would approve it, save it.")


def probeable(out):
    """Only a saved draft from a resolved repair earns probe sessions."""
    return out == "saved"


def outcome(repair_resolved, timed_out, draft, reject_count):
    """One of five, checked in priority order.

    repair_unresolved outranks everything: whatever the distiller produced,
    it produced it from a session that did not fix the bug, and that fact
    must not be laundered by a clean save.

    `rejected` is checked BEFORE `aborted` because a rejection also leaves no
    draft in the store -- testing "no draft" first would make `rejected`
    unreachable and silently relabel the single most informative failure the
    distiller can produce as the novelty gate working.
    """
    if not repair_resolved:
        return "repair_unresolved"
    if timed_out:
        return "timed_out"
    if reject_count:
        return "rejected"
    if draft is None:
        return "aborted"
    return "saved"


def extract(clone, distiller):
    """The store copy of whatever the distiller saved, or None.

    The STORE copy, never the native one under .claude/skills/: sync.py
    appends a rewritten MARKER_NOTE to the materialized copy, and that text
    is part of hot delivery rather than part of the draft.
    """
    d = Path(clone) / ".claude" / "skillforge" / DISTILLERS[distiller]
    if not d.is_dir():
        return None
    for child in sorted(d.iterdir()):
        md = child / "SKILL.md"
        if md.is_file():
            return md
    return None


def archive_dir(trap, distiller, draw):
    return ARCHIVE / trap / distiller / str(draw)


def preflight():
    """Reasons the next draw must not start.

    Checked per DRAW, not per batch. distilling-failures step 3's duplicate
    check runs `ls ~/.claude/skillforge/antiskills/`, so one leaked draft
    makes the next session propose UPDATING it rather than drafting fresh --
    silently converting an independent draw into a dependent one.
    """
    dirty = libguard.snapshot()["stores"]
    if dirty:
        return ["global store is not empty: %s" % ", ".join(dirty)]
    return []


def one(trap, distiller, draw, plugin_dir, task):
    dest = bench_run.WORK / ("%s-distill-%s-%d" % (task["id"], distiller, draw))
    ledger_db = dest.parent / (dest.name + ".ledger.db")
    for suffix in ("", "-shm", "-wal"):
        Path(str(ledger_db) + suffix).unlink(missing_ok=True)
    os.environ["SKILLFORGE_LEDGER"] = str(ledger_db)
    os.environ["SKILLFORGE_FORCE_HOT"] = ""
    # Phase 1 runs critique retrospectively (bench/judge.py). Left on, each
    # save spawns a detached `claude -p` that races the containment delete.
    os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"

    blockers = preflight()
    if blockers:
        raise RuntimeError("preflight: " + "; ".join(blockers))
    before = libguard.snapshot()

    bench_run.prepare(task, dest)
    prompt = PROMPT % (task["prompt"], "skillforge:distilling-%s" %
                       ("failures" if distiller == "learn-failure" else "skills"))
    cmd = ('claude -p %s --plugin-dir %s --permission-mode bypassPermissions'
           ' --model %s' % (json.dumps(prompt), json.dumps(str(plugin_dir)),
                            json.dumps(bench_run.MODEL)))
    t0 = time.time()
    timed_out = False
    try:
        sess = bench_run.sh(cmd, cwd=dest, timeout=PHASE1_TIMEOUT_S)
        tail = (sess.stdout or sess.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        timed_out, tail = True, "TIMEOUT"
    secs = round(time.time() - t0, 1)

    post, test_tail = bench_run.score(task, dest)
    repair_resolved = all(post.values())

    draft = extract(dest, distiller)
    rows = _ledger_rows(ledger_db)
    # The session calls save_skill.py itself, so the harness never sees its
    # exit code. A refusal is observable only here: save_skill logs a system
    # decision row for every REJECTED / SECRET BLOCKED / name collision.
    rejects = [r for r in rows["decisions"] if r["actor"] == "system"]
    out = outcome(repair_resolved, timed_out, draft, len(rejects))

    leaked = libguard.new_global_skills(before)
    if leaked:
        for name in leaked:
            bench_run.sh('python3 "%s/scripts/library.py" delete %s'
                         % (bench_run.REPO_ROOT, name), cwd=str(bench_run.REPO_ROOT))
        libguard.prune_trust(leaked)

    d = archive_dir(trap, distiller, draw)
    d.mkdir(parents=True, exist_ok=True)
    if draft is not None:
        (d / "SKILL.md").write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "trap": trap, "distiller": distiller, "draw": draw,
        "task": task["id"], "model": bench_run.MODEL,
        "outcome": out, "probeable": probeable(out),
        "repair_resolved": repair_resolved, "per_test": post,
        "timed_out": timed_out, "secs": secs,
        "chose_global_scope": leaked,
        "ledger_rows": rows["events"],
        "rejections": rejects,
        "session_tail": tail, "test_tail": test_tail,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2), encoding="utf-8")
    print("  %-13s trap %s draw %d -> %s (%.0fs)" % (distiller, trap, draw, out, secs))
    return out


def _ledger_rows(db):
    """{"events": [...], "decisions": [...]} for this draw.

    `decisions` is load-bearing, not provenance: it is the ONLY place a
    rejection is observable, because the session invokes save_skill.py itself
    and the harness never sees that process's exit code. Empty on failure,
    which classifies as `aborted` -- the conservative reading.
    """
    out = {"events": [], "decisions": []}
    try:
        import sqlite3
        con = sqlite3.connect(str(db))
        out["events"] = [
            {"event_type": r[0], "skill": r[1], "outcome": r[2], "ts": r[3]}
            for r in con.execute(
                "select event_type, skill, outcome, ts from events"
                " where event_type in ('save','draft') order by id")]
        out["decisions"] = [
            {"actor": r[0], "verdict": r[1], "subject": r[2], "reason": r[3]}
            for r in con.execute(
                "select actor, verdict, subject, reason from decisions"
                " order by id")]
        con.close()
    except Exception:
        pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", choices=sorted(TRAPS))
    ap.add_argument("--distiller", choices=sorted(DISTILLERS))
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)

    cfg = bench_run.expand(json.loads(
        (ROOT / "tasks.json").read_text(encoding="utf-8")))
    by_id = {t["id"]: t for t in cfg["tasks"]}
    plugin_dir = Path(cfg["plugin_dir"])

    traps = sorted(TRAPS) if args.all else [args.trap]
    dists = sorted(DISTILLERS) if args.all else [args.distiller]
    if not all(traps) or not all(dists):
        print("need --all, or both --trap and --distiller")
        return 1

    bench_run.WORK.mkdir(parents=True, exist_ok=True)
    print("model %s | archive %s | timeout %ds"
          % (bench_run.MODEL, ARCHIVE, PHASE1_TIMEOUT_S))
    for trap in traps:
        for distiller in dists:
            for draw in range(1, args.draws + 1):
                try:
                    one(trap, distiller, draw, plugin_dir, by_id[TRAPS[trap]])
                except Exception as e:
                    print("  %-13s trap %s draw %d -> ERROR %s"
                          % (distiller, trap, draw, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `python3 tests/test_bench_distill.py`
Expected: all PASS.

- [ ] **Step 5: Verify the CLI is wired without spending a session**

Run: `python3 bench/distill.py --draws 0 --all`
Expected: the header line `model claude-opus-5 | archive .../bench/distilled | timeout 1800s` and nothing else. `--draws 0` runs no sessions.

- [ ] **Step 6: Commit**

```bash
git add bench/distill.py tests/test_bench_distill.py
git commit -m "feat(bench): Q1 phase 1, with an unresolved repair as its own outcome"
```

---

## Task 6: `bench/dryrun.py` — predict delivery before spending probe sessions

Symptoms are structurally dead in author mode: `distilling-failures` step 4 mandates literal error signatures, `detect.py` matches those against `tool_response`, and `run.py::prepare` never places the grading tests during an author-mode session. Delivery therefore falls entirely to `retrieve.run_hook`'s BM25 over `name + description` against the prompt, gated on `score > 0` and `matched >= MIN_MATCHED_TERMS`.

Recording that prediction **before** the probes turns a stage-5 zero from ambiguous into attributable.

**Files:**
- Create: `bench/dryrun.py`
- Test: `tests/test_bench_distill.py` (append)

**Interfaces:**
- Consumes: `distill.archive_dir` (Task 5); `retrieve.rank`, `retrieve.MIN_MATCHED_TERMS` (existing)
- Produces: `predict(description, name, prompt) -> dict` with keys `score`, `matched`, `predicted` (`"deliver"` / `"no-deliver"`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_distill.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_distill.py`
Expected: `ModuleNotFoundError: No module named 'dryrun'`.

- [ ] **Step 3: Write `bench/dryrun.py`**

```python
#!/usr/bin/env python3
"""Predict whether each archived draft will be DELIVERED, before probing it.

Author mode never places the grading tests in the tree during the session
(run.py::prepare), so the trap's real error signature never appears in any
tool output and detect.py's symptom matching cannot fire. Delivery falls
entirely to retrieve.run_hook: BM25 over name + description against the
PROMPT, gated on score > 0 and matched >= MIN_MATCHED_TERMS.

So the funnel's delivery stage is a DESCRIPTION test. Recording the
prediction here, before any probe session is spent, is what makes a later
zero attributable instead of ambiguous -- and it costs nothing.

Run: python3 bench/dryrun.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "scripts"))
import retrieve
import distill
import run as bench_run

# The author task each trap is probed with -- the SAME bug as the repair task
# phase 1 distilled from.
PROBES = {"A": "sf-author-response-text",
          "B": "sf-author-fingerprint-preexisting"}


def predict(description, name, prompt):
    """What retrieve.run_hook would decide, using retrieve's own gate."""
    entry = {"name": name or "", "description": description or ""}
    ranked = retrieve.rank(prompt, [entry])
    score, matched = (ranked[0][1], ranked[0][2]) if ranked else (0, 0)
    ok = score > 0 and matched >= retrieve.MIN_MATCHED_TERMS
    return {"score": round(float(score), 4), "matched": int(matched),
            "predicted": "deliver" if ok else "no-deliver"}


def _frontmatter(text):
    """`name` and `description` from a SKILL.md, without a YAML dependency.

    description is a folded block (`description: >`), so its value is the
    indented lines that follow, not the rest of that one line.
    """
    name, desc, in_desc = None, [], False
    for line in text.splitlines():
        if line.strip() == "---" and name and not in_desc:
            break
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            in_desc = False
        elif line.startswith("description:"):
            rest = line.split(":", 1)[1].strip().lstrip(">").strip()
            if rest:
                desc.append(rest)
            in_desc = True
        elif in_desc and line.startswith((" ", "\t")):
            desc.append(line.strip())
        elif line and not line.startswith((" ", "\t")):
            in_desc = False
    return name, " ".join(desc)


def main():
    cfg = bench_run.expand(json.loads(
        (ROOT / "tasks.json").read_text(encoding="utf-8")))
    prompts = {t["id"]: t["prompt"] for t in cfg["tasks"]}
    updated = 0
    for meta_path in sorted(distill.ARCHIVE.glob("*/*/*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        draft = meta_path.parent / "SKILL.md"
        if not draft.is_file():
            continue
        name, desc = _frontmatter(draft.read_text(encoding="utf-8"))
        meta["delivery_prediction"] = predict(
            desc, name, prompts[PROBES[meta["trap"]]])
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        updated += 1
        print("%s/%s/%s -> %s (score %.3f, matched %d)" % (
            meta["trap"], meta["distiller"], meta["draw"],
            meta["delivery_prediction"]["predicted"],
            meta["delivery_prediction"]["score"],
            meta["delivery_prediction"]["matched"]))
    print("%d draft(s) predicted" % updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `python3 tests/test_bench_distill.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bench/dryrun.py tests/test_bench_distill.py
git commit -m "feat(bench): predict delivery from the description, since symptoms are dead in author mode"
```

---

## Task 7: `bench/judge.py` — retrospective judging

Phase 1 self-approves so the run stays unsteered. The human gate is recovered here, on the archived drafts, with nobody having steered a live session.

**Files:**
- Create: `bench/judge.py`
- Test: `tests/test_bench_distill.py` (append)

**Interfaces:**
- Consumes: `distill.ARCHIVE` (Task 5); `validate.critique(text, entry, plugin_root) -> (verdict, detail)` (existing, `scripts/validate.py:484`)
- Produces:
  - `symptom_shape(entries) -> str` — `"signature"`, `"narration"`, or `"none"`
  - `has_both_directions(description) -> bool`
  - `verification_discriminates(command, repo, parent_sha) -> bool | None`
  - `fingerprints_in_fix(fps, repo, fix_sha) -> list[bool]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_distill.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tests/test_bench_distill.py`
Expected: `ModuleNotFoundError: No module named 'judge'`.

- [ ] **Step 3: Write `bench/judge.py`**

```python
#!/usr/bin/env python3
"""Judge the archived drafts, after the fact, without steering a live session.

Phase 1 self-approves so the run stays automated and unsteered. This is where
the human gate is recovered -- on files, with the batch already finished.

Five checks per saved draft. They are reported ALONGSIDE the funnel, never
merged into it: a draft can be accepted, delivered, resolve the task, and
still carry a verification command that proves nothing.

Run: python3 bench/judge.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "scripts"))
import validate
import distill
import dryrun

# An error signature carries a machine-shaped token: an exception class, a
# dotted path, a bracketed literal, a call. Narration is prose about what the
# code did. Deliberately crude -- this is a description of the draft, not a
# gate on it.
SIGNATURE = re.compile(r"[A-Z][a-zA-Z]*(Error|Exception)|[\w.]+\(|::|\[['\"]|--\w")


def symptom_shape(entries):
    """"signature" | "narration" | "none".

    distilling-failures step 4 demands literal error signatures. Both
    hand-authored comparators are narration. Measured so the write-up can say
    which side of that asymmetry a draft landed on.
    """
    if not entries:
        return "none"
    hits = sum(1 for e in entries if SIGNATURE.search(e or ""))
    return "signature" if hits * 2 >= len(entries) else "narration"


def has_both_directions(description):
    """save_skill enforces this, so the expected rate is 100%. Anything less
    is a bug in the enforcement, not in the distiller."""
    d = (description or "").lower()
    return "use when:" in d and "do not use when:" in d


def verification_discriminates(command, repo, parent_sha):
    """Does verification.command FAIL where the procedure was NOT applied?

    Run at fix_commit~1, a tree where the skill demonstrably has not been
    applied. Exit 0 there means the command is not a verification. The
    distillation contract states this bar and states that every skill in the
    library has failed it at least once; this is the first machine check.

    None when the command could not be run at all -- unknown, not a pass.
    """
    if not command:
        return None
    try:
        wt = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", parent_sha],
            capture_output=True, text=True, timeout=60)
        if wt.returncode:
            return None
        r = subprocess.run(command, shell=True, cwd=str(repo),
                           capture_output=True, text=True, timeout=300)
        return r.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return None


def fingerprints_in_fix(fps, repo, fix_sha):
    """One bool per fingerprint: does it appear in the real fix's added lines?

    Matching runs against added lines, so a fingerprint that appears nowhere
    in the reference fix is invisible to outcome tracking no matter how well
    the skill was applied.
    """
    if not fps:
        return []
    try:
        r = subprocess.run(["git", "-C", str(repo), "show", fix_sha],
                           capture_output=True, text=True, timeout=120)
        if r.returncode:
            return [False] * len(fps)
        added = "\n".join(l[1:] for l in r.stdout.splitlines()
                          if l.startswith("+") and not l.startswith("+++"))
    except (OSError, subprocess.SubprocessError):
        return [False] * len(fps)
    return [bool(f) and f in added for f in fps]


def _list_field(text, field):
    """A simple `field:` YAML list from a SKILL.md, without a YAML dependency."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith(field + ":"):
            inside = True
            continue
        if inside:
            stripped = line.strip()
            if stripped.startswith("- "):
                out.append(stripped[2:].strip().strip('"\''))
            elif stripped and not line.startswith((" ", "\t")):
                break
    return out


def main():
    plugin_root = ROOT.parent
    cfg = json.loads((ROOT / "tasks.json").read_text(encoding="utf-8"))
    fixes = {t["id"]: t["fix_commit"] for t in cfg["tasks"]}
    judged = 0
    for meta_path in sorted(distill.ARCHIVE.glob("*/*/*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        draft = meta_path.parent / "SKILL.md"
        if not draft.is_file():
            continue
        text = draft.read_text(encoding="utf-8")
        name, desc = dryrun._frontmatter(text)
        kind = "antiskill" if meta["distiller"] == "learn-failure" else "skill"
        fix = fixes[meta["task"]]
        command = ""
        for line in text.splitlines():
            if line.startswith("verification.command:"):
                command = line.split(":", 1)[1].strip().strip('"\'')
        verdict, detail = validate.critique(
            text, {"name": name, "kind": kind, "description": desc}, plugin_root)
        meta["judgement"] = {
            "critique_verdict": verdict,
            "critique_detail": detail,
            "symptom_shape": symptom_shape(_list_field(text, "symptoms")),
            "both_trigger_directions": has_both_directions(desc),
            "verification_discriminates": verification_discriminates(
                command, plugin_root, fix + "~1"),
            "fingerprints_in_fix": fingerprints_in_fix(
                _list_field(text, "fingerprints"), plugin_root, fix),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        judged += 1
        print("%s/%s/%s -> critique %s | symptoms %s | verification %s" % (
            meta["trap"], meta["distiller"], meta["draw"], verdict,
            meta["judgement"]["symptom_shape"],
            meta["judgement"]["verification_discriminates"]))
    print("%d draft(s) judged" % judged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `python3 tests/test_bench_distill.py`
Expected: all PASS.

- [ ] **Step 5: Run the whole suite**

Run: `for f in tests/test_*.py; do printf '%-32s ' "$f"; python3 "$f" >/dev/null 2>&1 && echo OK || echo FAIL; done`
Expected: 18 OK (16 original + 2 new bench files).

- [ ] **Step 6: Commit**

```bash
git add bench/judge.py tests/test_bench_distill.py
git commit -m "feat(bench): retrospective judging, including whether a verification discriminates"
```

---

## Task 8: Pilot one draw — confirm the mechanism, then time it

Two things the plan cannot assert without running them: whether the distiller skill is reachable from a `-p` prompt, and what a phase-1 session actually costs. Both are gates on the batch.

**Files:** none modified unless the pilot fails.

- [ ] **Step 1: Confirm nothing else is running**

Run: `pgrep -fl "claude -p" ; echo "---"; python3 -c "
import sys; sys.path.insert(0,'bench'); import libguard, json
print(json.dumps(libguard.snapshot(), indent=1))"`
Expected: no `claude -p` processes. The snapshot's `stores` must be `[]`; `project_index` will list the operator's own skills, which is fine and is what gets restored at close.

- [ ] **Step 2: Run one draw**

Run: `python3 bench/distill.py --trap A --distiller learn-failure --draws 1`
Expected: one line, `learn-failure   trap A draw 1 -> <outcome> (<n>s)`.

- [ ] **Step 3: Confirm the distiller was actually reached**

Run: `python3 -c "
import json; m=json.load(open('bench/distilled/A/learn-failure/1/meta.json'))
print('outcome     ', m['outcome'])
print('repair      ', m['repair_resolved'], m['per_test'])
print('secs        ', m['secs'])
print('ledger rows ', m['ledger_rows'])
print('global leak ', m['chose_global_scope'])
print('tail'); print(m['session_tail'][-800:])"`

Expected: `ledger_rows` contains a `save` or `draft` row, which is the proof the distiller ran. **If `outcome` is `aborted` and `ledger_rows` is empty, the skill was never reached** — the `-p` prompt did not resolve `skillforge:distilling-failures`. In that case edit `PROMPT` in `bench/distill.py` to invoke it the other way (a literal `/skillforge:learn-failure` on its own line) and re-run this task from Step 2. Record which form worked in the spec's §4; it is fixed for all 12 sessions either way.

- [ ] **Step 4: Set the real timeout**

Read `secs` from Step 3. If it exceeds half of `PHASE1_TIMEOUT_S`, raise the constant to ~4× the observed time and note the observed number in the docstring, replacing "a ceiling to be replaced by a piloted number". If it is comfortably under, lower the constant to ~4× observed so a hung session fails fast rather than burning 30 minutes.

- [ ] **Step 5: Confirm containment worked**

Run: `python3 -c "
import sys; sys.path.insert(0,'bench'); import libguard, json
print(json.dumps(libguard.snapshot()['stores']))"`
Expected: `[]`. A non-empty result means a global save was not reverted — stop and fix `one()`'s containment before spending 53 more sessions.

- [ ] **Step 6: Discard the pilot draw**

Run: `rm -rf bench/distilled/A/learn-failure/1`

The pilot ran under an unpiloted timeout and possibly a rewritten prompt, so it is not one of the 12. Deleting it is not cherry-picking: the pre-registration fixes the batch's composition, and this draw predates the batch.

- [ ] **Step 7: Commit any changes the pilot forced**

```bash
git add bench/distill.py docs/superpowers/specs/2026-09-08-q1-distiller-experiment-design.md
git commit -m "chore(bench): pilot one phase-1 draw; fix the prompt form and the timeout"
```

---

## Task 9: Run the batch and write it up

- [ ] **Step 1: Phase 1 — 12 sessions**

Run: `python3 bench/distill.py --all --draws 3`
Expected: 12 outcome lines. Read them; a cell with zero probeable drafts is a complete Q1 answer for that distiller and trap and costs no probe sessions.

- [ ] **Step 2: Record the delivery predictions before any probe runs**

Run: `python3 bench/dryrun.py`
Expected: one line per saved draft. **This must run before Step 4** — a prediction recorded after the probes is not a prediction.

- [ ] **Step 3: Commit the archive**

```bash
git add bench/distilled
git commit -m "bench: Q1 phase 1 -- 12 draws, archived with their predictions"
```

- [ ] **Step 4: Phase 2 — probes, only for `probeable` drafts**

Run:
```bash
python3 -c "
import json, pathlib, subprocess
probes = {'A': 'sf-author-response-text', 'B': 'sf-author-fingerprint-preexisting'}
for m in sorted(pathlib.Path('bench/distilled').glob('*/*/*/meta.json')):
    meta = json.loads(m.read_text())
    if not meta['probeable']:
        print('skip', m.parent, meta['outcome']); continue
    subprocess.run(['python3', 'bench/run.py', '--arm', 'treatment', '--runs', '3',
                    '--task', probes[meta['trap']],
                    '--skill-from', str(m.parent / 'SKILL.md')], check=False)
"
```
Expected: 3 lines per probeable draft. Watch for the `WARNING: ... installed at tier` line from Task 2 — it means `retrieve.eligible()` will skip the skill and no injection row will be logged.

- [ ] **Step 5: Phase 2 — the control arm, this batch, pinned model**

Run:
```bash
python3 bench/run.py --arm control --runs 3 --task sf-author-response-text
python3 bench/run.py --arm control --runs 3 --task sf-author-fingerprint-preexisting
```
Expected: 6 rows. **This is the floor.** The 2026-08-11 figure is corroboration.

- [ ] **Step 5b: Phase 2 — the transfer arm (brief Q2), 6 sessions**

Folded into this batch because it needs a same-configuration floor and Step 5 is the only place one exists (spec §1, "Why the transfer arm rides this batch"). Run it **after** Step 5, so the floor it is read against is already on disk.

Run:
```bash
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-transfer
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-transfer
```
Expected: 6 rows, tagged `skill_source: authored`, `distiller: null`, `draw: null`. No `--skill-from` — these tasks name their own crossed hand-authored skill in `tasks.json`. Nothing collides: `dest` is `<task-id>-<arm><segment>-<run>`, and `arm_segment` returns `""` for a treatment run with no `--skill-from`, so these land at `sf-author-response-text-transfer-treatment-1` — distinct from both `sf-author-response-text-treatment-1` (Step 5's control uses `-control-`) and every `...-treatment-d-<distiller>-<draw>-N` clone from Step 4.

This is a **secondary**. It does not enter the Q1 funnel and it is not a Q1 finding.

- [ ] **Step 6: Judge the drafts**

Run: `python3 bench/judge.py`
Expected: one line per saved draft. This spawns real `claude -p` children through `validate.critique`, so run it only after every session-spending step is finished.

- [ ] **Step 7: Assert the library is intact**

Run: `python3 -c "
import sys, json; sys.path.insert(0,'bench'); import libguard
print(json.dumps(libguard.snapshot(), indent=1))"`

Compare against the Task 8 Step 1 snapshot. `stores`, `global_index` and `trust` must match. If `project_index` lost the operator's own skills, restore with:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts'); import sync
sync.sync(project_root='$PWD')"
```
Drift that survives the restore **invalidates the batch**; say so rather than tidying it away.

- [ ] **Step 8: Build the funnel**

Run:
```bash
python3 -c "
import json, pathlib, collections, sqlite3, glob
funnel = collections.defaultdict(lambda: collections.Counter())
for m in sorted(pathlib.Path('bench/distilled').glob('*/*/*/meta.json')):
    meta = json.loads(m.read_text()); k = (meta['trap'], meta['distiller'])
    funnel[k]['draws'] += 1
    funnel[k]['repair_resolved'] += bool(meta['repair_resolved'])
    funnel[k]['draft'] += (m.parent / 'SKILL.md').is_file()
    funnel[k]['saved'] += meta['outcome'] == 'saved'
rows = [json.loads(l) for l in open('bench/results.jsonl')]
q1 = [r for r in rows if r.get('skill_source') == 'distilled']
for r in q1:
    funnel[(None, r['distiller'])]['resolved'] += bool(r['resolved'])
    funnel[(None, r['distiller'])]['probes'] += 1
for k in sorted(funnel, key=str): print(k, dict(funnel[k]))
"
```

Then read the delivery stage from the per-run ledgers, which is the stage that is invisible in `results.jsonl`:
```bash
python3 -c "
import sqlite3, glob, os
for db in sorted(glob.glob('/tmp/skillforge-bench/*-d-*.ledger.db')):
    con = sqlite3.connect(db)
    rows = con.execute(\"select event_type, trigger from events where event_type='injection'\").fetchall()
    con.close()
    print(os.path.basename(db), rows)
"
```
Expected: an `injection` row with `trigger='prompt'` for each delivered probe. Report the `prompt` / `symptom` split rather than collapsing it into "injected". A zero here must be read against that draft's `delivery_prediction`.

- [ ] **Step 8b: The two secondaries**

Transfer (Q2), read against Step 5's floor:
```bash
python3 -c "
import json, collections
agg = collections.defaultdict(lambda: [0, 0])
for l in open('bench/results.jsonl'):
    r = json.loads(l)
    if r['ts'][:10] != __import__('time').strftime('%Y-%m-%d'): continue
    agg[(r['task'], r['arm'])][0] += bool(r['resolved'])
    agg[(r['task'], r['arm'])][1] += 1
for k in sorted(agg): print('%-46s %-9s %d/%d' % (k[0], k[1], *agg[k]))
"
```
Expected: the two `-transfer` cells beside this batch's control cells. Report transfer vs. the fresh floor; the pilot's 0/6 is corroboration with its missing `model` key stated.

Then Q5 — the group-by declared in spec §8, run after Step 6 so the verdicts exist:
```bash
python3 -c "
import json, pathlib, collections
verdict = {}
for m in pathlib.Path('bench/distilled').glob('*/*/*/meta.json'):
    meta = json.loads(m.read_text())
    j = meta.get('judgement')
    if j: verdict[(meta['distiller'], meta['draw'])] = j['critique_verdict']
agg = collections.defaultdict(lambda: [0, 0])
for l in open('bench/results.jsonl'):
    r = json.loads(l)
    if r.get('skill_source') != 'distilled': continue
    v = verdict.get((r['distiller'], r['draw']), 'unjudged')
    agg[v][0] += bool(r['resolved']); agg[v][1] += 1
for v in sorted(agg): print('critique %-10s -> %d/%d probes resolved' % (v, *agg[v]))
"
```
Expected: one line per distinct verdict. **A single line means every draft got the same verdict and there is no group to compare** — most likely all-fail, since critique passed 0 of 9 hand-written skills. Report that as "the gate rejected every distilled draft", not as a blank cell. Both secondaries are labelled as such; neither enters the funnel.

- [ ] **Step 9: Write the results section**

Append to `bench/RESULTS.md`, in the style of the E5 and hot-path sections. It must contain, at minimum:

- The funnel per distiller × trap — six stages, not a score.
- The fresh control cell as the floor, with the 2026-08-11 figure named as corroboration and its missing `model` key stated.
- n=3 per probe cell, said plainly.
- Every stage-5 zero read against its pre-recorded `delivery_prediction`.
- The ceiling comparison labelled directional, whichever way it points.
- The judgement table: critique verdicts, symptom shapes, and how many verification commands discriminate.
- Threat 9 restated where a reader will meet it: both hand-authored comparators carry narration-shaped symptoms in violation of the contract the distiller is held to, so a distilled draft that emits error signatures is being compared against skills that did not.

- The two secondaries from Step 8b, in their own subsection, labelled secondary and kept out of the funnel: transfer against this batch's floor, and probe resolve rate grouped by critique verdict.

Then update the experiment register at the top of `bench/RESULTS.md`: a Q1 row, and the `results.jsonl` row count. The register's brief-questions table also needs three edits, or it will keep saying nobody has done work this batch did:

- **Q2** — no longer "Partial. Transfer 0/6 at n=3 in the pilot". Add this batch's transfer cells and the fact that they are the first measured against a same-configuration floor on a recorded model.
- **Q5** — no longer "needs bench runs split on critique verdict, and nobody has done it". State what the split showed, including "every draft drew the same verdict, so there was no group to compare" if that is what happened.
- **Q1** — the row itself, replacing "No experiment exists."

- [ ] **Step 10: Commit**

```bash
git add bench/RESULTS.md bench/results.jsonl bench/distilled
git commit -m "bench: Q1 -- does the distiller work end to end"
```

---

## Self-Review

**Spec coverage.** Every section maps to a task: §1 cells → Tasks 5, 9; §2 comparators → Task 9 Step 5 (fresh control) and Step 9 (write-up); §3 funnel → Tasks 6, 9 Step 8; §4 mechanics → Tasks 1, 2, 4, 5; §5 outcomes → Task 5; §6 retrospective judging → Task 7; §7 threats → Task 9 Step 9; §8 pre-registration → Global Constraints and Task 9's ordering; §9 how to read → Task 9 Step 9; §10 out of scope → nothing built.

**One deliberate deviation from the spec, now reconciled**: the spec originally said "add a `--no-critique` seam to `save_skill.py`". Task 1 implements an environment variable instead, because the phase-1 session invokes `save_skill.py` itself and no flag can reach that call. Spec §4 was rewritten to match once Task 1 landed, so the two no longer disagree — this note is history, not an outstanding action.

**Type consistency.** `arm_segment` builds `-d-<distiller-with-hyphens-stripped>-<draw>` while `run.py`'s result rows and `distill.archive_dir` keep the raw `learn-failure`. That is intentional — the path segment must be unambiguous, the data must be readable — and `test_arm_segment_encodes_distiller_and_draw` pins the stripped form. `distill.outcome` returns the same five strings `distill.probeable` and Task 9's funnel script test against. `dryrun._frontmatter` is reused by `judge.main` rather than reimplemented.

**Known gap, accepted.** The session-running paths in `distill.one` and `run.one` have no unit tests; they shell out to `claude`. Task 8 is the integration test, and it gates the batch.
