# E10 Budget Lever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the bench a per-run injection-budget lever, so E10 can run a 1200-token arm and a 2000-token arm in one batch.

**Architecture:** `retrieve.run_hook` reads `SKILLFORGE_INJECT_BUDGET` at call time and falls back to the shipped `INJECT_BUDGET_TOKENS = 1200`, exactly as `sync._force_hot` reads `SKILLFORGE_FORCE_HOT`. `bench/run.py` gains `--inject-budget N`, exports the variable per run, encodes it in the clone-path segment so two budgets cannot share a clone or a ledger, and records it on the result row. A batch script composes the four arms. `scripts/detect.py` is not touched.

**Tech Stack:** Python 3 standard library only, pytest (plus each test file's own `__main__` runner), bash.

**Spec:** `docs/superpowers/specs/2026-09-11-e10-prompt-time-budget-design.md`

## Global Constraints

- **The tests must never invoke a model and must never mutate the operator's real library.** Stated in `bench/critique-calibration/README.md`. Every test here runs in the existing `in_sandbox` helper.
- **Restore any environment variable a test sets, in a `finally`.** `tests/conftest.py` restores the environment per test under pytest, but each test file also runs standalone via `python3 tests/test_x.py`, where no fixture runs.
- **The shipped default must not change.** With `SKILLFORGE_INJECT_BUDGET` unset or empty, the budget is 1200.
- **`scripts/detect.py` is out of scope.** The symptom path keeps its own 1200.
- **Skills are identified by path, never by name.** `bench/distilled/B/learn/1/SKILL.md` and `bench/distilled/B/consolidated/1/SKILL.md` share the name `capped-scan-reports-unknown-not-absent`.
- **Commit messages end with the project trailer:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, passed on stdin via `git commit -F -` so blank lines survive.
- **The full suite is 777 tests before this plan**, 779 after it.

---

### Task 1: Budget override in the prompt hook

**Files:**
- Modify: `scripts/retrieve.py:318`
- Test: `tests/test_retrieve.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the environment variable `SKILLFORGE_INJECT_BUDGET`, read inside `retrieve.run_hook(data)`. A decimal string sets the prompt-path budget in tokens; unset or empty means `INJECT_BUDGET_TOKENS` (1200). Task 2 writes it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_retrieve.py`, directly after `test_budget_skips_oversized_entry`. `os` is already imported at the top of that file.

```python
def test_budget_override_env_admits_a_second_entry():
    """Bench-only lever (E10 spec section 3.3): the prompt path honours
    SKILLFORGE_INJECT_BUDGET. The two entries cost 812 and 810 tokens, so at
    the shipped 1200 only the first fits and at 2000 both do."""
    def check(home):
        write_index(home, [
            entry(home, "terraform-registry-a",
                  "terraform module registry publishing", pad=3100),
            entry(home, "terraform-registry-b",
                  "terraform module registry basics", pad=3100)])
        prompt = "publish a terraform module registry entry"
        rc, out = run_hook_capture(hook_data(home, prompt))
        assert len(injected_names(out)) == 1

        os.environ["SKILLFORGE_INJECT_BUDGET"] = "2000"
        try:
            rc, out = run_hook_capture(hook_data(home, prompt, session="sess2"))
            assert sorted(injected_names(out)) == ["terraform-registry-a",
                                                   "terraform-registry-b"]
        finally:
            del os.environ["SKILLFORGE_INJECT_BUDGET"]
    in_sandbox(check)
```

Two details that matter. The second call passes `session="sess2"` because `run_hook` dedupes by session and would otherwise deliver nothing. The `finally` is required because this file also runs standalone, where `conftest.py`'s fixture does not.

- [ ] **Step 2: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_retrieve.py::test_budget_override_env_admits_a_second_entry -v`

Expected: FAIL on `assert sorted(injected_names(out)) == [...]`, because the hook ignores the variable and still delivers one skill. The list on the left will hold a single name.

- [ ] **Step 3: Write the minimal implementation**

In `scripts/retrieve.py`, inside `run_hook`, replace line 318:

```python
    budget = INJECT_BUDGET_TOKENS
```

with:

```python
    # Test-only lever (bench/run.py --inject-budget, E10 spec section 3.3):
    # a budget arm needs a per-run override. Read here rather than at import
    # so the in-process tests see it; unset or empty means the shipped 1200.
    budget = int(os.environ.get("SKILLFORGE_INJECT_BUDGET") or INJECT_BUDGET_TOKENS)
```

`os` is already imported in that module. Do not touch `scripts/detect.py`.

- [ ] **Step 4: Run the test and watch it pass**

Run: `python3 -m pytest tests/test_retrieve.py -v`

Expected: PASS, the whole file green.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `778 passed`. If anything else fails, stop: that is pollution or a real regression, not this change.

- [ ] **Step 6: Commit**

```bash
git add scripts/retrieve.py tests/test_retrieve.py
git commit -F - <<'EOF'
feat(retrieve): per-run injection budget override for the bench

E10 runs a 1200-token arm and a 2000-token arm in one batch, and
INJECT_BUDGET_TOKENS is a module constant. run_hook now reads
SKILLFORGE_INJECT_BUDGET at call time, falling back to the shipped 1200,
on the pattern of sync._force_hot. detect.py keeps its own budget: E10
asks about prompt-time delivery.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `--inject-budget` in the bench driver

**Files:**
- Modify: `bench/run.py` — globals near line 60, `arm_segment` (lines 190-212), the per-run export (lines 379-385), the result row (lines 409-419), `main`'s argument parser (lines 435-460)
- Test: `tests/test_bench_run.py`

**Interfaces:**
- Consumes: `SKILLFORGE_INJECT_BUDGET` from Task 1.
- Produces: the module global `bench_run.INJECT_BUDGET` (an `int` or `None`), the CLI flag `--inject-budget N`, a clone-path segment suffix `-b<N>`, and the result-row key `inject_budget` (`int` or `null`, where `null` means the shipped 1200). Task 3 passes the flag.

- [ ] **Step 1: Write the failing test**

In `tests/test_bench_run.py`, add the new global to `_reset` so it cannot leak between tests:

```python
def _reset():
    bench_run.SKILL_FROM = None
    bench_run.FORCE_HOT = False
    bench_run.PLUS_SKILL = None
    bench_run.INJECT_BUDGET = None
```

Then add this test after `test_arm_segment_separates_the_three_treatment_arms`:

```python
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
    finally:
        _reset()
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_bench_run.py::test_arm_segment_records_the_injection_budget -v`

Expected: FAIL with `AssertionError: '' != '-b2000'`, from the test body's first assertion comparing `arm_segment("treatment")` against `'-b2000'` (assigning a module attribute in `_reset` cannot raise `AttributeError`).

- [ ] **Step 3: Add the global and the segment**

In `bench/run.py`, beside the existing `SKILL_FROM` / `PLUS_SKILL` globals near line 60:

```python
#: Test-only (E10): per-run override for retrieve.py's injection budget, in
#: tokens. None = the shipped 1200. arm_segment carries it into the clone
#: path, because a batch runs two budgets and they must not share a clone.
INJECT_BUDGET = None
```

In `arm_segment`, after the `-plus` block and before `return seg`:

```python
    if INJECT_BUDGET:
        seg += "-b%d" % INJECT_BUDGET
    return seg
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `python3 -m pytest tests/test_bench_run.py -v`

Expected: PASS, the whole file green.

- [ ] **Step 5: Wire the flag, the export and the row**

Three edits in `bench/run.py`, none of them test-covered on their own (`run_one` has no test harness), so apply them together and review by reading.

In `main`, beside `--plus-skill`:

```python
    ap.add_argument("--inject-budget", type=int, default=None,
                    help="E10: run the prompt hook at this injection budget"
                         " in tokens instead of the shipped 1200 (test-only)")
```

Just below, extend the `global` statement and assign, keeping the existing lines:

```python
    global MODEL, FORCE_HOT, SKILL_FROM, PLUS_SKILL, INJECT_BUDGET
    MODEL = args.model
    FORCE_HOT = args.force_hot
    SKILL_FROM = args.skill_from
    PLUS_SKILL = args.plus_skill
    INJECT_BUDGET = args.inject_budget
    if INJECT_BUDGET is not None and INJECT_BUDGET <= 0:
        # retrieve.main swallows the ValueError a bad value would raise and
        # then delivers nothing, silently. Fail here instead.
        ap.error("--inject-budget must be a positive integer")
```

In `run_one`, directly after the `SKILLFORGE_FORCE_HOT` export:

```python
    # Same per-run discipline: exported unconditionally so a previous run's
    # value can never leak into this one.
    os.environ["SKILLFORGE_INJECT_BUDGET"] = str(INJECT_BUDGET or "")
```

In the `rec` dictionary, beside `"model": MODEL`:

```python
           "inject_budget": INJECT_BUDGET,
```

`null` on a row means the shipped 1200, which is what every row before E10 ran at.

- [ ] **Step 6: Verify the flag end to end without spending a session**

Run: `python3 bench/run.py --check`

Expected: `config ok: 10 task(s), all paths resolve`, exit 0. The count is
every task in `bench/tasks.json`, not just E10's two probes.

Run: `python3 bench/run.py --inject-budget 0 --check`

Expected: exit 2, with `--inject-budget must be a positive integer` on stderr.

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `779 passed`.

- [ ] **Step 8: Commit**

```bash
git add bench/run.py tests/test_bench_run.py
git commit -F - <<'EOF'
feat(bench): --inject-budget, and a clone segment that carries it

E10 runs arms at 1200 and 2000 in one batch. The budget goes into the
clone path segment because every arm passes --arm treatment, so without it
two arms share a clone and a ledger -- how E5 lost a batch. The row records
inject_budget, null meaning the shipped 1200, which every earlier row used.

A non-positive value is rejected at the flag: retrieve.main swallows the
error a bad value raises and then silently delivers nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: The E10 batch script

**Files:**
- Create: `bench/e10_batch.sh`

**Interfaces:**
- Consumes: `--inject-budget` from Task 2, plus the existing `--skill-from`, `--plus-skill`, `--runs` and `--arm` flags.
- Produces: nothing later tasks read. Running it is a separate, manual act.

- [ ] **Step 1: Write the script**

Create `bench/e10_batch.sh` with exactly this content:

```bash
#!/usr/bin/env bash
# E10 -- does a wrong-bug skill hurt at prompt time? Composition is
# pre-registered:
# docs/superpowers/specs/2026-09-11-e10-prompt-time-budget-design.md
#
# Four arms per task IN ONE BATCH, in the order M, P, S, C (spec section 4),
# response_text first. M = the matched skill alone at the shipped 1200.
# P = the pair at 2000. S = the consolidated seven at 2000. C = nothing.
# n=3 per cell, 24 sessions.
#
# Check the session meter BEFORE running this; `claude -p` exits 1 when the
# session allowance is gone, and a truncated batch is postponed, not answered.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R"

# --skill-from must be ABSOLUTE: install_skill shells save_skill.py with cwd
# set to the clone, so a relative path resolves against the clone.
D="$R/bench/distilled"
A_SKILL="$D/A/learn-failure/1/SKILL.md"    # 759, trap A, wants response_text
B_SKILL="$D/B/consolidated/1/SKILL.md"     # 1088, trap B, wants fingerprint
SEVEN=("$A_SKILL" \
       "$D/A/learn-failure/2/SKILL.md" \
       "$D/A/learn-failure/3/SKILL.md" \
       "$D/A/consolidated/1/SKILL.md" \
       "$B_SKILL" \
       "$D/B/learn-nogate/1/SKILL.md" \
       "$D/B/learn-nogate/2/SKILL.md")

# $1 task, $2 its matched skill, $3 the other half of the pair
arms() {
  local task="$1" matched="$2" other="$3" s
  local plus=()

  echo "### M  $task  (matched alone, shipped budget)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched"

  echo "### P  $task  (pair, budget 2000)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched" --plus-skill "$other" --inject-budget 2000

  for s in "${SEVEN[@]}"; do
    [ "$s" = "$matched" ] || plus+=(--plus-skill "$s")
  done
  echo "### S  $task  (seven, budget 2000, ${#plus[@]} extras passed / 2)"
  python3 bench/run.py --task "$task" --runs 3 --arm treatment \
    --skill-from "$matched" "${plus[@]}" --inject-budget 2000

  echo "### C  $task"
  python3 bench/run.py --task "$task" --runs 3 --arm control
}

arms sf-author-response-text "$A_SKILL" "$B_SKILL"
arms sf-author-fingerprint-preexisting "$B_SKILL" "$A_SKILL"
echo "### E10 DONE"
```

- [ ] **Step 2: Check the syntax and the paths, spending no sessions**

Run: `bash -n bench/e10_batch.sh`

Expected: no output, exit 0.

Run:

```bash
for f in bench/distilled/A/learn-failure/{1,2,3} bench/distilled/A/consolidated/1 \
         bench/distilled/B/consolidated/1 bench/distilled/B/learn-nogate/{1,2}; do
  test -f "$f/SKILL.md" && echo "ok $f" || echo "MISSING $f"
done
```

Expected: seven `ok` lines, no `MISSING`.

- [ ] **Step 3: Confirm the segments the batch will produce**

Run:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, 'bench')
import run as bench_run
bench_run.SKILL_FROM = "/x/bench/distilled/A/learn-failure/1/SKILL.md"
for plus, budget in ((None, None), (["/x/one"], 2000), (["/x/%d" % i for i in range(6)], 2000)):
    bench_run.PLUS_SKILL, bench_run.INJECT_BUDGET = plus, budget
    print(bench_run.arm_segment("treatment"))
EOF
```

Expected, in order:

```
-d-learnfailure-1
-d-learnfailure-1-plus-b2000
-d-learnfailure-1-plus6-b2000
```

Three distinct segments mean arms M, P and S cannot overwrite each other's clone or ledger.

- [ ] **Step 4: Make it executable and commit**

```bash
chmod +x bench/e10_batch.sh
git add bench/e10_batch.sh
git commit -F - <<'EOF'
bench: E10 batch script -- four arms, two budgets, one batch

M, P, S, C per task in that order, response_text first, n=3, 24 sessions.
P and S pass --inject-budget 2000; M runs at the shipped 1200. Paths, not
names: B/learn/1 and B/consolidated/1 share a skill name and only the
second is in this pool.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

## Running the batch (not part of the implementation)

The code above spends no sessions. Running the experiment does, and it is a deliberate, separate act governed by the spec:

1. **Check the session meter first.** `claude -p "Reply with exactly: OK" --model claude-opus-5`. That check itself costs one session, for 25 in all.
2. **Run no other Claude session on this machine during the batch.** Arm S installs three global-scope skills into the operator's real library, and `libguard` reverts them afterwards.
3. **Run it:** `bash bench/e10_batch.sh`, and keep the output.
4. **Verify the prediction before reading any score.** Every P and S row's `injections` should hold `capped-scan-reports-unknown-not-absent` then `json-dumps-breaks-token-matching`, both at `trigger: prompt`. Deviations are reported per spec section 4.
5. **Then extract and write up:** `python3 bench/extract.py --batch e10 <clone-name> ...`, then a register row and a results section in `bench/RESULTS.md`.
