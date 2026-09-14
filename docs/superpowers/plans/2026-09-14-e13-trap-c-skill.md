# E13 Trap C: Distil, Qualify, Probe, Outcome — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take trap C (`sf-author-verdict-from`, the only E13 screen survivor) through spec §5–§8: distil skills from it, qualify it for trap 2, probe whether a distilled skill makes the author task pass, and, if it qualifies, run the tokenizer outcome test.

**Architecture:** Tooling first, at zero sessions. That means a repair task for C, a pinned library pool, a `--plugin-dir` override with archived plugin snapshots, a qualification tool, and scripts plus readers for the probe and outcome batches. Session stages follow, each gated on the previous stage's pre-registered reading. The controller runs the stages. Implementer subagents do the tooling tasks.

**Tech Stack:** Python 3.9 stdlib, bash (macOS bash 3.2 for `.sh`), git. Tests are stdlib-style files with a per-test catching runner, and also run under `python3 -m pytest -q`.

**Spec:** `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md` (§4–§8, §9, §11). The E13 screen result (2026-09-14): C admitted 0/6, D 6/6 and E 6/6 rejected, reference 0/3.

## Global Constraints

- Standard library only. Add no dependencies.
- Change nothing under `scripts/`. Don't modify `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` or `bench/real_path_check.py`, which belong to the parallel `in_scope` session. Importing functions from `bench/real_path_check.py` is allowed.
- The Bash tool ignores `set -e`, so give every step that must block a commit an explicit `|| exit 1`.
- The Bash tool's shell is zsh, which doesn't word-split unquoted variables. `.sh` files run under macOS bash 3.2 with `set -u`, so never expand an empty array.
- No committed file may contain the operator's absolute home path.
- End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- `bench/tasks.json` is written only by a tool, as `json.dumps(data, indent=2) + "\n"`, and existing entries stay byte-unchanged.
- Tooling tasks (1–6) spend **zero sessions**: never run `claude`, `bench/distill.py` or `bench/run.py` beyond `--check`. Stage tasks (7–10) spend sessions, which the user authorized on 2026-09-14 ("build and test a skill for trap C"). Each stage probes the allowance first and follows §3's session-limit rule.
- Run bench tools from the repo root. `bench/budget_sweep.py` reads relative paths at import.
- Pre-registered values, copied from the spec:
  - Distillation is `learn` and `learn-failure`, `--no-novelty-gate`, 3 draws each. A draft counts only if its outcome is `saved`.
  - Qualification uses the consolidated seven plus the draft, the real `save_skill.py` and hook, a budget of 1200, and scripts from `06885c0` (old) and `9cbb472` (new). A draft qualifies if it is not delivered by the old hook and is delivered by the new one. Order: `learn` before `learn-failure`, lower draw first.
  - Delivery check: each counted draft alone, through the real hook, on the author prompt. An undeliverable draft is not probed.
  - Probe: each deliverable draft installed alone via `--skill-from`, 3 author runs, plus 3 control runs in the same batch. The batch is void if the control resolves even once. A treatment row whose `injections` don't name the draft is void and re-run; if that recurs (2 such rows), the cell is void. C is working if its deliverable drafts, pooled, resolve at least half their probe runs.
  - Outcome (only if C qualifies AND is working): the seven plus the first qualifying draft, via `--skill-from` and `--plus-skill`. Two arms of 6, old plugin snapshot `06885c0` first, then `9cbb472`. Old-arm rows must not inject the draft and new-arm rows must. A mismatched row is void and re-run; 2 in one arm voids the arm. Criterion: new minus old of **≥3** means improves, **within 1** means no large effect, **exactly 2** is ambiguous. Fisher's exact p is reported, not used as a threshold.
  - §6.2: if C is working but doesn't qualify, C is **trap 1**. Trap 2 has no candidate and goes back to the candidate list, so no outcome test runs.

## File Structure

| file | status | responsibility |
| --- | --- | --- |
| `bench/RESULTS.md` | modify | E13 screen write-up now; the C result at the end |
| `bench/results.jsonl` | modify | Session rows (screen, probe, outcome) |
| `bench/e13_preflight.py` | modify | `REPAIR_IDS`, `repair_prompt`, `repair_graded`, `repair_entry`, `write_tasks`, `--repair` |
| `tests/test_bench_e13_preflight.py` | modify | Tests for the repair additions and the trap-C registration |
| `bench/distill.py` | modify | `TRAPS["C"]` |
| `bench/dryrun.py` | modify | `PROBES["C"]` |
| `bench/budget_sweep.py` | modify | Pin `ten` to traps A and B, so the seven cannot absorb C drafts |
| `tests/test_bench_budget_sweep.py` | create | The pin, proven with a decoy C draft |
| `bench/run.py` | modify | `SNAPSHOT_MARK`, `snapshot_plugin`, the snapshot branch of `plugin_commit`, `PLUGIN_SEGMENT` in `arm_segment`, `--plugin-dir` |
| `tests/test_bench_run.py` | modify | Tests for the above |
| `bench/e13_qualify.py` | create | §6.1 qualification and §7 delivery check, writing `bench/distilled/<trap>/qualification.json` |
| `tests/test_bench_e13_qualify.py` | create | Pure-function tests |
| `bench/e13_probe_read.py` | create | §7 reader |
| `tests/test_bench_e13_probe_read.py` | create | Reader tests |
| `bench/e13_probe.sh` | create | §7 batch |
| `bench/e13_outcome_read.py` | create | §8 reader, with Fisher's exact test |
| `tests/test_bench_e13_outcome_read.py` | create | Reader tests |
| `bench/e13_outcome.sh` | create | §8 batch |
| `bench/distilled/C/` | create (by `distill.py`) | The 6 archived draws and `qualification.json` |

---

### Task 1: Record the E13 screen

The controller does this task; it needs no subagent.

**Files:**
- Modify: `bench/RESULTS.md`, `bench/results.jsonl` (the 21 rows already appended)

- [ ] **Step 1: Add the register row** to the table at the top of `bench/RESULTS.md`, directly after the E12 row, with the same column layout as the E11 row:

```markdown
| E13 screen (2026-09-14) | Do any of three new author-mode traps (C `verdict_from`, D `transcript_slice`, E `store_dir`) have a zero control floor? | **Answered: C only.** C 0/6, **admitted**: every session passed 14 of 15 graded tests and failed exactly `test_a_rewrapped_quote_still_counts_as_evidence`, the historical byte-exact-match bug. D 6/6 and E 6/6 were **rejected** at ceiling, so their docstrings suffice. Same-batch reference 0/3 (**0/24** lifetime), so the screen is valid. No injections on any row; every row records `plugin_commit` `4df0d02`, the clone history strip. C's second trap (floor measured on the raw span) never sprang | `results.jsonl`, the 21 rows dated 2026-09-14 after 09:36:06; spec `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md` §3 |
```

- [ ] **Step 2: Append a section** at the end of `bench/RESULTS.md`:

```markdown
# E13 screen — which new author traps have a zero floor? (2026-09-14)

Pre-registered in `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md` §3,
run by `bench/e13_screen.sh`, read by `bench/e13_screen_read.py --window 2026-09-14T09:36:06 -`.

| cell | control resolved | graded tests passed per session | verdict |
| --- | --- | --- | --- |
| C `sf-author-verdict-from` | 0/6 | 14/15 every session | admitted |
| D `sf-author-transcript-slice` | 6/6 | 7/7 | rejected |
| E `sf-author-store-dir` | 6/6 | 12/12 | rejected |
| reference `sf-author-fingerprint-preexisting` | 0/3 | 0/2 | screen valid |

C fails for the right reason. The one test missed in all six sessions is the
fix-added test for the historical bug: a critic's quote re-wrapped across a line
break no longer matches byte for byte. The evidence-floor test passed 6/6, so C's
second trap did not spring. D's and E's docstrings were enough for a fresh model,
which §11 threat 3 anticipated for D.

Environment: clone history stripped to one baseline commit (`4df0d02`) before
this batch, so no session could read the fix. No skill was injected on any row.
22 sessions including the allowance probe, no session failures.

## Limits

n = 6 bounds C's floor only loosely: 0/6 is consistent with a true rate up to
about 39% (§11 threat 4). The reference's lifetime 0/24 mixes environments from
before and after the history strip.
```

- [ ] **Step 3: Commit**

```bash
grep -q "$HOME" bench/RESULTS.md bench/results.jsonl && { echo "home path"; exit 1; }
git add bench/RESULTS.md bench/results.jsonl || exit 1
git commit -q -m "docs: E13 screen -- C admitted, D and E rejected at ceiling

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 2: A repair task for C, registration, and a pinned pool

§5 distils from a repair task on the same bug, and C's is decided mechanically: the fix-added tests the historical function fails. Running the zero-session check on 2026-09-14 gave exactly one, `test_a_rewrapped_quote_still_counts_as_evidence`. Separately, `bench/budget_sweep.py` builds "the consolidated seven" from **every** archived draft, so the moment C's drafts are archived they would change the library that §6.1 and §8 are defined over. That pool is pinned to traps A and B.

**Files:**
- Modify: `bench/e13_preflight.py`, `tests/test_bench_e13_preflight.py`
- Modify: `bench/distill.py` (`TRAPS`), `bench/dryrun.py` (`PROBES`)
- Modify: `bench/budget_sweep.py` (the `ten` comprehension)
- Create: `tests/test_bench_budget_sweep.py`
- Modify: `bench/tasks.json` (written by the tool)

**Interfaces:**
- Consumes: `e13_preflight.CANDIDATES`, `run_variant`, `test_names`, `_git`, `upsert`, `ROOT` (Tasks 4–5 of the previous plan).
- Produces: `REPAIR_IDS = {"C": "sf-repair-verdict-from"}`; `repair_prompt(test_path) -> str`; `repair_graded(original, fix_added) -> list[str]`; `repair_entry(letter, cand, graded) -> dict`; `write_tasks(entries) -> None`; the CLI `python3 bench/e13_preflight.py --repair --only C [--write]`; `distill.TRAPS["C"] == "sf-repair-verdict-from"`; `dryrun.PROBES["C"] == "sf-author-verdict-from"`.

- [ ] **Step 1: Write the failing tests.** Add these above `if __name__ == "__main__":` in `tests/test_bench_e13_preflight.py`:

```python
def test_repair_prompt_is_the_existing_repair_template_verbatim():
    tasks = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    ref = next(t for t in tasks if t["id"] == "sf-truncation-reports-absent")
    assert pf.repair_prompt("tests/test_retrieve.py") == ref["prompt"]


def test_repair_graded_is_the_fix_added_tests_the_original_fails():
    original = {"t_trap": False, "t_other_added": True, "t_old": False}
    assert pf.repair_graded(original, {"t_trap", "t_other_added", "t_missing"}) == ["t_trap"]


def test_repair_entry_is_a_repair_task_on_the_same_fix():
    e = pf.repair_entry("C", pf.CANDIDATES["C"], ["t_trap"])
    assert e["id"] == "sf-repair-verdict-from" and e["mode"] == "repair"
    assert e["repo"] == "{root}" and e["fix_commit"] == "c0d7d88"
    assert e["test_cmd"] == "python3 tests/test_validate.py"
    assert e["fail_to_pass"] == ["t_trap"] and e["skill"] is None
    assert "stub_cmd" not in e
    assert e["prompt"] == pf.repair_prompt("tests/test_validate.py")


def test_trap_c_is_registered_for_distillation_and_probing():
    import distill
    import dryrun
    tasks = {t["id"]: t for t in json.loads(
        (ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
    repair, author = tasks[distill.TRAPS["C"]], tasks[dryrun.PROBES["C"]]
    assert repair["mode"] == "repair" and author["mode"] == "author"
    assert repair["fix_commit"] == author["fix_commit"] == "c0d7d88"
    assert repair["fail_to_pass"] == ["test_a_rewrapped_quote_still_counts_as_evidence"]
```

Create `tests/test_bench_budget_sweep.py`:

```python
"""Tests for bench/budget_sweep.py's pools. Run: python3 tests/test_bench_budget_sweep.py

budget_sweep reads relative paths at import, so every check runs in a subprocess
with a chosen cwd rather than importing it here.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEVEN = ["bench/distilled/A/learn-failure/1/SKILL.md", "bench/distilled/A/learn-failure/2/SKILL.md",
         "bench/distilled/A/learn-failure/3/SKILL.md", "bench/distilled/B/learn-nogate/1/SKILL.md",
         "bench/distilled/B/learn-nogate/2/SKILL.md", "bench/distilled/A/consolidated/1/SKILL.md",
         "bench/distilled/B/consolidated/1/SKILL.md"]
PROBE = ("import json, budget_sweep as bs; print(json.dumps({'ten': [e['_trap'] for e in bs.ten],"
         " 'seven': [e['_path'] for e in bs.seven]}))")


def _pools(cwd):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "scripts"), str(ROOT / "bench")]))
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=str(cwd), env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_consolidated_seven_are_pinned():
    got = _pools(ROOT)
    assert got["seven"] == SEVEN
    assert set(got["ten"]) == {"A", "B"}


def test_a_later_trap_draft_does_not_join_the_pools():
    """E13 archives trap C's drafts beside A's and B's. §6.1 and §8 are defined over
    the consolidated seven, so a C draft must never enter them."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        (tmp / "bench" / "distilled").mkdir(parents=True)
        for trap in ("A", "B"):
            (tmp / "bench" / "distilled" / trap).symlink_to(ROOT / "bench" / "distilled" / trap)
        decoy = tmp / "bench" / "distilled" / "C" / "learn-nogate" / "1"
        decoy.mkdir(parents=True)
        shutil.copy(str(ROOT / SEVEN[0]), str(decoy / "SKILL.md"))
        (tmp / "bench" / "tasks.json").symlink_to(ROOT / "bench" / "tasks.json")
        got = _pools(tmp)
        assert set(got["ten"]) == {"A", "B"}, got["ten"]
        assert got["seven"] == SEVEN
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


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

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_bench_e13_preflight.py -k "repair or trap_c" ; python3 -m pytest -q tests/test_bench_budget_sweep.py`
Expected: the four pre-flight tests fail (`AttributeError`, or a `KeyError` for `C`). `test_the_consolidated_seven_are_pinned` passes, since no C draft exists yet. `test_a_later_trap_draft_does_not_join_the_pools` fails, because the decoy joins `ten`.

- [ ] **Step 3: Implement.** In `bench/budget_sweep.py`, replace the `ten = [...]` comprehension with:

```python
# Traps A and B only. §6.1 and §8 of the E13 spec are defined over "the
# consolidated seven", and this glob used to take every archived draft, so the
# first archived C draft would have silently changed that library.
ten = [entry(f, f.split('distilled/')[1][0])
       for f in sorted(glob.glob('bench/distilled/*/*/*/SKILL.md'))
       if '/consolidated/' not in f and f.split('distilled/')[1][0] in ('A', 'B')]
```

In `bench/distill.py`, change `TRAPS` to:

```python
TRAPS = {"A": "sf-escaping-breaks-symptom-match",
         "B": "sf-truncation-reports-absent",
         "C": "sf-repair-verdict-from"}
```

In `bench/dryrun.py`, change `PROBES` to:

```python
PROBES = {"A": "sf-author-response-text",
          "B": "sf-author-fingerprint-preexisting",
          "C": "sf-author-verdict-from"}
```

In `bench/e13_preflight.py`, add below `CANDIDATES`:

```python
# E13 §5: the repair task each survivor is distilled from.
REPAIR_IDS = {"C": "sf-repair-verdict-from"}
```

Add these functions directly after `upsert`:

```python
def repair_prompt(test_path):
    """The existing repair-task template, verbatim, with the test file substituted."""
    return ("The test suite %s has failing tests. Run `python3 %s` to see which ones "
            "fail, then fix the source under scripts/ so that every test passes. Do not "
            "modify anything under tests/ - the tests are correct and describe the "
            "intended behavior. When you are done, run the test command again to confirm."
            % (test_path, test_path))


def repair_graded(original, fix_added):
    """Spec section 5: the fix-added tests the historical function fails."""
    return sorted(t for t in fix_added if original.get(t) is False)


def repair_entry(letter, cand, graded):
    assert cand["own_runner"], "a repair task grades with the file's own runner"
    return {
        "id": REPAIR_IDS[letter],
        "mode": "repair",
        "repo": "{root}",
        "fix_commit": cand["fix"],
        "test_path": cand["test_path"],
        "test_cmd": "python3 %s" % cand["test_path"],
        "setup_cmd": "true",
        "fail_to_pass": list(graded),
        "prompt": repair_prompt(cand["test_path"]),
        "skill": None,
        "skill_source_commit": None,
        "selection_rule": ("E13 trap %s repair task, for distillation only (%s section 5). "
                           "Graded: the fix-added tests the historical function fails, "
                           "decided by bench/e13_preflight.py --repair." % (letter, SPEC)),
    }
```

Add directly after `_summary`:

```python
def write_tasks(entries):
    path = ROOT / "tasks.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        upsert(cfg, entry)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("wrote %s into bench/tasks.json" % sorted(e["id"] for e in entries))


def repair_main(letters, write):
    import run as bench_run
    work = Path(os.path.realpath(tempfile.mkdtemp(prefix="e13-repair-")))
    bench_run.WORK = work
    entries = []
    try:
        for letter in letters:
            cand = CANDIDATES[letter]
            fix_added = (test_names(_git("show", "%s:%s" % (cand["fix"], cand["test_path"])))
                         - test_names(_git("show", "%s~1:%s" % (cand["fix"], cand["test_path"]))))
            original, _ = run_variant(cand, "original", work)
            graded = repair_graded(original, fix_added)
            print("=== %s repair  %s  graded (%d): %s"
                  % (letter, REPAIR_IDS[letter], len(graded), graded))
            if graded:
                entries.append(repair_entry(letter, cand, graded))
            else:
                print("  INVALID: the historical function fails no fix-added test")
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    if write and entries:
        write_tasks(entries)
    return 0 if len(entries) == len(letters) else 1
```

In `main()`, add `ap.add_argument("--repair", action="store_true", help="build the section 5 repair task instead")` after the `--write` argument. Directly after `letters = args.only or sorted(CANDIDATES)`, add:

```python
    if args.repair:
        unknown = [l for l in letters if l not in REPAIR_IDS]
        if unknown:
            ap.error("no repair task defined for %s" % unknown)
        return repair_main(letters, args.write)
```

In `main()`, replace the block that starts `if args.write and valid:` and ends with its `print("wrote ...")` with:

```python
    if args.write and valid:
        write_tasks(valid.values())
```

- [ ] **Step 4: Write C's repair task with the tool, then verify**

```bash
python3 bench/e13_preflight.py --repair --only C --write || exit 1
python3 - <<'PY' || exit 1
import json, subprocess, sys
head = json.loads(subprocess.run(["git", "show", "HEAD:bench/tasks.json"], capture_output=True, text=True, check=True).stdout)
now = json.loads(open("bench/tasks.json", encoding="utf-8").read())
ok = now["tasks"][:len(head["tasks"])] == head["tasks"] and [t["id"] for t in now["tasks"][len(head["tasks"]):]] == ["sf-repair-verdict-from"]
print("existing unchanged and one repair task added:", ok)
sys.exit(0 if ok else 1)
PY
python3 bench/run.py --check || exit 1
```

Expected: `graded (1): ['test_a_rewrapped_quote_still_counts_as_evidence']`, `True`, and `config ok: 14 task(s), all paths resolve`.

- [ ] **Step 5: Run the tests.** `python3 tests/test_bench_e13_preflight.py && python3 tests/test_bench_budget_sweep.py && python3 -m pytest -q`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add bench/e13_preflight.py tests/test_bench_e13_preflight.py bench/distill.py bench/dryrun.py bench/budget_sweep.py tests/test_bench_budget_sweep.py bench/tasks.json || exit 1
git commit -q -m "bench: C's repair task and registration, and pin the consolidated seven to A and B

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 3: Archived plugin snapshots and `--plugin-dir`

§8 runs the same task against the plugin as archived at `06885c0` and at `9cbb472`. `run.py` can only take its plugin from `tasks.json`, a snapshot is not a git checkout, so `plugin_commit` would record `""`, and the two arms would share a clone path and a per-run ledger, so the second would overwrite the first (the E5 failure).

**Files:**
- Modify: `bench/run.py`
- Test: `tests/test_bench_run.py`

**Interfaces:**
- Consumes: `PLUGIN_PATHS`, `plugin_commit`, `environment`, `arm_segment` (existing).
- Produces: `SNAPSHOT_MARK = ".bench-plugin-ref"`; `snapshot_plugin(ref, dest) -> str` (the full sha); `plugin_commit(snapshot_dir) == "archive:<full sha>"`; module global `PLUGIN_SEGMENT` (`""` by default), appended by `arm_segment` for treatment; the CLI flag `--plugin-dir DIR`.

- [ ] **Step 1: Write the failing tests.** Add these above `if __name__ == "__main__":` in `tests/test_bench_run.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail.** `python3 -m pytest -q tests/test_bench_run.py -k "snapshot_plugin or differ_only_in_plugin or no_scripts"`. Expected: 3 failed.

- [ ] **Step 3: Implement.** In `bench/run.py`, add `import io` and `import tarfile` to the imports (alphabetical). Directly after `ENV = {}`, add:

```python
#: E13 section 8: "-p<sha7>" when --plugin-dir is given. Two arms that differ
#: only in the plugin would otherwise share a clone path and a per-run ledger,
#: and the second would overwrite the first's evidence (how E5 lost a batch).
PLUGIN_SEGMENT = ""
```

Directly after the `PLUGIN_PATHS = (...)` line, add:

```python
# A plugin snapshot is not a git checkout, so it carries the commit it was
# archived from in this file instead.
SNAPSHOT_MARK = ".bench-plugin-ref"


def snapshot_plugin(ref, dest):
    """Extract the plugin as it was at `ref` into `dest`, marked with its commit.

    Only the plugin's own paths (PLUGIN_PATHS that exist at `ref`), so the
    snapshot is exactly what a session loads and nothing from bench/ or docs/.
    Returns the full sha.
    """
    git = lambda *a: subprocess.run(["git", "-C", str(REPO_ROOT), *a],
                                    capture_output=True, check=True)
    sha = git("rev-parse", "%s^{commit}" % ref).stdout.decode().strip()
    present = set(git("ls-tree", "--name-only", sha).stdout.decode().split())
    paths = [p for p in PLUGIN_PATHS if p in present]
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", sha, *paths).stdout)) as t:
        t.extractall(str(dest))
    (dest / SNAPSHOT_MARK).write_text(sha + "\n", encoding="utf-8")
    return sha
```

In `plugin_commit`, as the first statement inside `try:`, add:

```python
        mark = Path(plugin_dir) / SNAPSHOT_MARK
        if mark.is_file():
            return "archive:" + mark.read_text(encoding="utf-8").strip()
```

In `arm_segment`, directly before `return seg`, add:

```python
    seg += PLUGIN_SEGMENT
```

In `main()`, add the argument after `--inject-budget`:

```python
    ap.add_argument("--plugin-dir", default=None,
                    help="E13 section 8: run against this plugin directory, e.g."
                         " a run.snapshot_plugin() snapshot, instead of tasks.json's"
                         " (test-only)")
```

Replace these lines in `main()`:

```python
    plugin_dir = Path(cfg["plugin_dir"])
    global ENV
    ENV = environment(plugin_dir)
```

with:

```python
    plugin_dir = Path(args.plugin_dir).resolve() if args.plugin_dir else Path(cfg["plugin_dir"])
    if not (plugin_dir / "scripts").is_dir():
        print("plugin dir has no scripts/: %s" % plugin_dir, file=sys.stderr)
        return 1
    global ENV, PLUGIN_SEGMENT
    ENV = environment(plugin_dir)
    PLUGIN_SEGMENT = ("-p" + ENV["plugin_commit"].split(":")[-1][:7]
                      if args.plugin_dir else "")
```

- [ ] **Step 4: Run the tests.** `python3 tests/test_bench_run.py && python3 -m pytest -q && python3 bench/run.py --check`. Expected: all pass, and the check reports `config ok: 14 task(s)`.

- [ ] **Step 5: Confirm the snapshots and the shipped budget, with zero sessions**

```bash
python3 - <<'PY' || exit 1
import sys, tempfile, pathlib, subprocess
sys.path.insert(0, "bench"); import run
ok = True
for ref in ("06885c0", "9cbb472"):
    d = pathlib.Path(tempfile.mkdtemp()) / ref
    sha = run.snapshot_plugin(ref, d)
    budget = [l for l in (d / "scripts" / "retrieve.py").read_text().splitlines() if l.startswith("INJECT_BUDGET_TOKENS")]
    print(ref, sha[:12], run.plugin_commit(d)[:20], budget, sorted(p.name for p in d.iterdir()))
    ok &= budget == ["INJECT_BUDGET_TOKENS = 1200"] and (d / "hooks" / "hooks.json").is_file()
diff = subprocess.run(["git", "diff", "--stat", "06885c0", "9cbb472", "--", "scripts", "hooks", "skills", ".claude-plugin"], capture_output=True, text=True).stdout
print(diff); ok &= diff.strip().startswith("scripts/retrieve.py") and "1 file changed" in diff
sys.exit(0 if ok else 1)
PY
```

Expected: both snapshots are marked `archive:`, carry `INJECT_BUDGET_TOKENS = 1200`, and the plugin diff between them is `scripts/retrieve.py` only.

- [ ] **Step 6: Commit**

```bash
git add bench/run.py tests/test_bench_run.py || exit 1
git commit -q -m "bench: archived plugin snapshots and --plugin-dir, with arms kept apart

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 4: Qualification and delivery check (zero sessions)

**Files:**
- Create: `bench/e13_qualify.py`
- Test: `tests/test_bench_e13_qualify.py`

**Interfaces:**
- Consumes: `real_path_check.delivered(scripts_dir, prompt, session, project, home) -> (names, stderr)`, `real_path_check.export_scripts(ref, into) -> scripts path`, `real_path_check.sandbox_env(home)`; `budget_sweep.seven` (pinned in Task 2); `dryrun.PROBES`; `libguard.snapshot()`.
- Produces: `counted_drafts(archive, letter) -> [{"segment", "draw", "path", "name"}]` in §6.1 order; `qualifies(name, old, new) -> bool`; `first_qualifying(rows) -> row | None`. The CLI `python3 bench/e13_qualify.py --trap C [--write]` writes `bench/distilled/C/qualification.json` as `{"trap", "task", "old_ref", "new_ref", "drafts": [{"segment", "draw", "name", "path", "old", "new", "qualifies", "alone", "deliverable"}], "first_qualifying": path|None, "deliverable": [path, ...], "problems": [...], "library_untouched": bool}`. Paths are repo-relative.

- [ ] **Step 1: Write the failing test.** Create `tests/test_bench_e13_qualify.py`:

```python
"""Tests for bench/e13_qualify.py. Run from the repo root: python3 tests/test_bench_e13_qualify.py"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e13_qualify as q


def _draw(archive, segment, draw, outcome="saved", name=None, draft=True):
    d = archive / "C" / segment / str(draw)
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"outcome": outcome, "skill_name": name}), encoding="utf-8")
    if draft:
        (d / "SKILL.md").write_text("---\nname: %s\n---\n" % name, encoding="utf-8")


def test_counted_drafts_follow_the_section_6_1_order_and_rules():
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp)
        _draw(a, "learn-failure-nogate", 1, name="lf1")
        _draw(a, "learn-nogate", 10, name="l10")
        _draw(a, "learn-nogate", 2, name="l2")
        _draw(a, "learn-nogate", 3, outcome="repair_unresolved", name="unresolved")
        _draw(a, "learn-nogate", 4, outcome="aborted", draft=False)
        _draw(a, "learn", 1, name="gated")
        got = [(d["segment"], d["draw"], d["name"]) for d in q.counted_drafts(a, "C")]
        assert got == [("learn-nogate", 2, "l2"), ("learn-nogate", 10, "l10"),
                       ("learn-failure-nogate", 1, "lf1")], got


def test_a_draft_qualifies_only_if_the_new_hook_alone_delivers_it():
    assert q.qualifies("x", old=["other"], new=["other", "x"]) is True
    assert q.qualifies("x", old=["x"], new=["x"]) is False
    assert q.qualifies("x", old=[], new=[]) is False
    assert q.qualifies("x", old=["x"], new=[]) is False


def test_first_qualifying_takes_the_earliest_in_order():
    rows = [{"path": "a", "qualifies": False}, {"path": "b", "qualifies": True},
            {"path": "c", "qualifies": True}]
    assert q.first_qualifying(rows)["path"] == "b"
    assert q.first_qualifying(rows[:1]) is None


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

- [ ] **Step 2: Run to verify it fails.** `python3 tests/test_bench_e13_qualify.py`. Expected: `ModuleNotFoundError: e13_qualify`.

- [ ] **Step 3: Implement.** Create `bench/e13_qualify.py`:

```python
#!/usr/bin/env python3
"""E13 trap-2 qualification (spec section 6.1) and delivery check (section 7).

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

For every counted draft of a trap, in section 6.1's order (learn before
learn-failure, lower draw first; gate-off draws only; outcome `saved` only):

  qualification  install the consolidated seven plus the draft through the real
                 save_skill.py into a sandboxed HOME and project, then run the
                 real hook on the trap's author prompt from `git archive` of
                 06885c0 (before the tokenizer fix) and of 9cbb472 (after it).
                 The draft qualifies if the old hook does not deliver it and
                 the new one does.
  delivery       install the draft ALONE and run the new hook on the same
                 prompt. A draft it does not deliver cannot act as a treatment
                 and is not probed.

Zero sessions: no `claude` runs, which is what makes the sandboxed HOME safe.
Installs use the current save_skill.py, so only the hook differs between old
and new (bench/real_path_check.py's method, whose helpers this reuses). The
operator's library must come out unchanged. Run from the repo root:

    python3 bench/e13_qualify.py --trap C --write
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bench"))
import budget_sweep as bs                                         # noqa: E402
import libguard                                                   # noqa: E402
from dryrun import PROBES                                         # noqa: E402
from real_path_check import delivered, export_scripts, sandbox_env  # noqa: E402

ARCHIVE = ROOT / "bench" / "distilled"
OLD_REF, NEW_REF = "06885c0", "9cbb472"
DISTILLERS = ("learn", "learn-failure")      # section 6.1: learn first


def counted_drafts(archive, letter):
    """Every draft section 5 counts, in section 6.1's order."""
    out = []
    for distiller in DISTILLERS:
        seg = archive / letter / (distiller + "-nogate")
        metas = sorted(seg.glob("*/meta.json"), key=lambda p: int(p.parent.name))
        for meta in metas:
            m = json.loads(meta.read_text(encoding="utf-8"))
            draft = meta.parent / "SKILL.md"
            if m.get("outcome") == "saved" and draft.is_file():
                out.append({"segment": seg.name, "draw": int(meta.parent.name),
                            "path": draft, "name": m.get("skill_name")})
    return out


def qualifies(name, old, new):
    return name not in old and name in new


def first_qualifying(rows):
    return next((r for r in rows if r["qualifies"]), None)


def _sandbox(work, tag):
    home = tempfile.mkdtemp(prefix="home-%s-" % tag, dir=work)
    project = pathlib.Path(tempfile.mkdtemp(prefix="proj-%s-" % tag, dir=work))
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    return home, project


def _install(paths, home, project):
    problems = []
    for p in paths:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_skill.py"),
                            str(pathlib.Path(p).resolve()), "--scope", "project",
                            "--project-root", str(project)],
                           capture_output=True, text=True, cwd=str(project),
                           env=sandbox_env(home), timeout=120)
        if r.returncode:
            problems.append("%s did not save: %s" % (p, (r.stdout + r.stderr)[-200:]))
    return problems


def _rel(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True, choices=sorted(PROBES))
    ap.add_argument("--write", action="store_true",
                    help="write bench/distilled/<trap>/qualification.json")
    args = ap.parse_args(argv)
    task = PROBES[args.trap]
    prompt = bs.P[task]
    drafts = counted_drafts(ARCHIVE, args.trap)
    if not drafts:
        print("no counted draft for trap %s" % args.trap)
        return 1

    before = libguard.snapshot()
    # Resolved: save_skill records project roots with symlinks resolved and
    # retrieve.in_scope compares strings, and macOS's temp dir is a symlink.
    work = os.path.realpath(tempfile.mkdtemp(prefix="e13-qualify-"))
    rows, problems = [], []
    try:
        old_scripts = export_scripts(OLD_REF, os.path.join(work, "old"))
        new_scripts = export_scripts(NEW_REF, os.path.join(work, "new"))
        seven = [ROOT / e["_path"] for e in bs.seven]
        for i, d in enumerate(drafts):
            home, project = _sandbox(work, "lib%d" % i)
            problems += _install(seven + [d["path"]], home, project)
            old, err_old = delivered(old_scripts, prompt, "old-%d" % i, project, home)
            new, err_new = delivered(new_scripts, prompt, "new-%d" % i, project, home)
            home1, project1 = _sandbox(work, "alone%d" % i)
            problems += _install([d["path"]], home1, project1)
            alone, err_alone = delivered(new_scripts, prompt, "alone-%d" % i, project1, home1)
            problems += ["%s hook stderr: %s" % (_rel(d["path"]), e[-200:])
                         for e in (err_old, err_new, err_alone) if e]
            rows.append({"segment": d["segment"], "draw": d["draw"], "name": d["name"],
                         "path": _rel(d["path"]), "old": old, "new": new,
                         "qualifies": qualifies(d["name"], old, new),
                         "alone": alone, "deliverable": d["name"] in alone})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    first = first_qualifying(rows)
    result = {"trap": args.trap, "task": task, "old_ref": OLD_REF, "new_ref": NEW_REF,
              "drafts": rows, "first_qualifying": first["path"] if first else None,
              "deliverable": [r["path"] for r in rows if r["deliverable"]],
              "problems": problems, "library_untouched": untouched}
    for r in rows:
        print("%-22s draw %d  %-40s old %-5s new %-5s qualifies %-5s deliverable %s"
              % (r["segment"], r["draw"], (r["name"] or "?")[:40], r["name"] in r["old"],
                 r["name"] in r["new"], r["qualifies"], r["deliverable"]))
    print("first qualifying: %s" % result["first_qualifying"])
    print("deliverable: %d of %d" % (len(result["deliverable"]), len(rows)))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    ok = untouched and not problems
    if args.write and ok:
        out = ARCHIVE / args.trap / "qualification.json"
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % _rel(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests.** `python3 tests/test_bench_e13_qualify.py && python3 -m pytest -q`. Expected: 3 PASS and the full suite passes. Also run `python3 bench/e13_qualify.py --trap C` and expect `no counted draft for trap C` with exit 1, because no draw exists yet.

- [ ] **Step 5: Commit**

```bash
git add bench/e13_qualify.py tests/test_bench_e13_qualify.py || exit 1
git commit -q -m "bench: E13 trap-2 qualification and delivery check

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 5: The probe batch and its reader

**Files:**
- Create: `bench/e13_probe_read.py`, `tests/test_bench_e13_probe_read.py`, `bench/e13_probe.sh`

**Interfaces:**
- Consumes: `e12_read.select(rows, windows)`; `bench/distilled/<trap>/qualification.json` (Task 4); the row keys `task`, `arm`, `resolved`, `session_ok`, `session_tail`, `skill_path` (home-relative), `injections` (`[{"skill", ...}]`).
- Produces: `read_probe(rows, task, drafts) -> {"batch": "postponed"|"void"|"incomplete"|"complete", "reason", "control", "cells": {path: {"valid", "needed", "resolved", "undelivered", "rerun", "status"}}, "verdict": "working"|"not working"|None, "pooled": [resolved, valid]}`, where `drafts` is `[{"path", "name"}]`. The CLI `python3 bench/e13_probe_read.py --trap C --window FROM TO` prints `batch: <status>` first. `bash bench/e13_probe.sh --trap C [--dry-run]`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_bench_e13_probe_read.py`:

```python
"""Tests for bench/e13_probe_read.py. Run: python3 tests/test_bench_e13_probe_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_probe_read as pr

TASK = "sf-author-verdict-from"
D1 = {"path": "bench/distilled/C/learn-nogate/1/SKILL.md", "name": "quote-rewrap"}
D2 = {"path": "bench/distilled/C/learn-failure-nogate/2/SKILL.md", "name": "byte-exact-quote"}


def ctl(resolved=False, ok=True, tail=None):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "injections": [], "skill_path": None}


def trt(d, resolved=False, delivered=True, ok=True):
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None, "skill_path": "~/x/wt/" + d["path"],
            "injections": [{"skill": d["name"]}] if delivered else [{"skill": "other"}]}


def full(d, resolved):
    return [trt(d, resolved=i < resolved) for i in range(3)]


def test_pooled_half_resolved_is_working():
    rows = [ctl()] * 3 + full(D1, 2) + full(D2, 1)
    res = pr.read_probe(rows, TASK, [D1, D2])
    assert res["batch"] == "complete" and res["pooled"] == [3, 6]
    assert res["verdict"] == "working"


def test_below_half_is_not_working():
    res = pr.read_probe([ctl()] * 3 + full(D1, 1) + full(D2, 1), TASK, [D1, D2])
    assert res["verdict"] == "not working"


def test_a_resolved_control_voids_the_batch():
    res = pr.read_probe([ctl(resolved=True), ctl(), ctl()] + full(D1, 3), TASK, [D1])
    assert res["batch"] == "void" and res["verdict"] is None


def test_a_session_limit_postpones_the_batch():
    rows = [ctl()] * 3 + full(D1, 1) + [ctl(ok=False, tail="You've hit your session limit")]
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "postponed" and res["cells"] == {}


def test_an_undelivered_row_does_not_count_and_two_void_the_cell():
    rows = [ctl()] * 3 + full(D1, 3) + [trt(D2, resolved=True, delivered=False)] + full(D2, 0)
    cell = pr.read_probe(rows, TASK, [D1, D2])["cells"][D2["path"]]
    assert cell["valid"] == 3 and cell["undelivered"] == 1 and cell["status"] == "complete"
    rows.append(trt(D2, resolved=True, delivered=False))
    res = pr.read_probe(rows, TASK, [D1, D2])
    assert res["cells"][D2["path"]]["status"] == "void"
    assert res["pooled"] == [3, 3] and res["verdict"] == "working"


def test_a_missing_cell_leaves_the_batch_incomplete():
    res = pr.read_probe([ctl()] * 3 + full(D1, 3), TASK, [D1, D2])
    assert res["batch"] == "incomplete" and res["verdict"] is None


def test_every_cell_void_is_not_working():
    rows = [ctl()] * 3 + [trt(D1, delivered=False)] * 2
    res = pr.read_probe(rows, TASK, [D1])
    assert res["batch"] == "complete" and res["verdict"] == "not working"


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

- [ ] **Step 2: Run to verify it fails.** `python3 tests/test_bench_e13_probe_read.py`. Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the reader.** Create `bench/e13_probe_read.py`:

```python
#!/usr/bin/env python3
"""Read an E13 probe batch (spec section 7).

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

A session refused at the session limit postpones the whole batch. The batch is
void if the same-batch control resolves even once. A treatment row that did
not inject its draft is not a treatment: it does not count and is re-run, and
a second such row voids that draft's cell. The trap is working if its complete
cells, pooled, resolve at least half their probe runs.

Rows are selected with --window FROM TO, exactly as in bench/e12_read.py.
Deliverable drafts and their names come from qualification.json. Run:

    python3 bench/e13_probe_read.py --trap C --window <PROBE_START> -
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402  -- one window rule, not two

N_CONTROL = 3
N_RUNS = 3
LIMIT_MARK = "session limit"


def _draft_path(skill_path):
    """The repo-relative draft path in a home-relative skill_path, or None."""
    i = (skill_path or "").find("bench/distilled/")
    return skill_path[i:] if i >= 0 else None


def read_probe(rows, task, drafts):
    mine = [r for r in rows if r.get("task") == task]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "control": None, "cells": {}, "verdict": None,
                "pooled": None,
                "reason": "a session hit the session limit: re-run the whole batch"}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if r.get("session_ok")]
    out = {"control": {"valid": len(ok), "needed": N_CONTROL,
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "rerun": len(control) - len(ok)},
           "cells": {}, "verdict": None, "pooled": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 7)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    resolved = valid = 0
    for d in drafts:
        trt = [r for r in mine if r.get("arm") == "treatment"
               and _draft_path(r.get("skill_path")) == d["path"]]
        ran = [r for r in trt if r.get("session_ok")]
        hit = [r for r in ran if d["name"] in {i.get("skill") for i in r.get("injections") or []}]
        cell = {"valid": len(hit), "needed": N_RUNS,
                "resolved": sum(1 for r in hit if r.get("resolved")),
                "undelivered": len(ran) - len(hit),
                "rerun": (len(trt) - len(ran)) + (len(ran) - len(hit))}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_RUNS else "incomplete")
        if cell["status"] == "incomplete":
            complete = False
        elif cell["status"] == "complete":
            resolved += cell["resolved"]
            valid += cell["valid"]
        out["cells"][d["path"]] = cell
    if not complete:
        out.update(batch="incomplete", reason="a cell or the control is not fully measured")
        return out
    out["pooled"] = [resolved, valid]
    out["verdict"] = "working" if valid and 2 * resolved >= valid else "not working"
    out.update(batch="complete", reason="" if valid else "every cell is void")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    q = json.loads((ROOT / "distilled" / args.trap / "qualification.json").read_text(encoding="utf-8"))
    drafts = [{"path": r["path"], "name": r["name"]} for r in q["drafts"] if r["deliverable"]]
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_probe(select(rows, args.window), q["task"], drafts)
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control %-44s valid %d/%d  resolved %d  re-run %d"
              % (q["task"], c["valid"], c["needed"], c["resolved"], c["rerun"]))
    for path, c in res["cells"].items():
        print("  draft   %-44s valid %d/%d  resolved %d  undelivered %d  %s"
              % (path.replace("bench/distilled/", ""), c["valid"], c["needed"], c["resolved"],
                 c["undelivered"], c["status"]))
    if res["verdict"]:
        print("verdict: %s (pooled %d/%d)" % (res["verdict"], res["pooled"][0], res["pooled"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the reader tests.** `python3 tests/test_bench_e13_probe_read.py && python3 -m pytest -q tests/test_bench_e13_probe_read.py`. Expected: 7 PASS.

- [ ] **Step 5: Write the batch script.** Create `bench/e13_probe.sh`, then `chmod +x bench/e13_probe.sh`:

```bash
#!/usr/bin/env bash
# E13 probe batch for one trap. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 7.
#
# 3 control sessions on the trap's author task, then each deliverable draft
# (bench/distilled/<trap>/qualification.json) installed alone, 3 runs each.
# The batch is void if the control resolves once. A session refused at the
# session limit postpones the whole batch: the script stops, and the batch is
# re-run whole later. A treatment row that did not inject its draft is re-run by
# hand: python3 bench/run.py --task <task> --runs 1 --arm treatment --skill-from <abs draft>
#
# Read with: python3 bench/e13_probe_read.py --trap <trap> --window <PROBE_START> -
# Usage: bash bench/e13_probe.sh --trap C [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
TRAP=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --trap) TRAP="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 1 ;;
  esac
done
[ -n "$TRAP" ] || { echo "usage: bash bench/e13_probe.sh --trap C [--dry-run]"; exit 1; }
Q="bench/distilled/$TRAP/qualification.json"
[ -f "$Q" ] || { echo "FATAL: $Q missing -- run bench/e13_qualify.py --trap $TRAP --write first"; exit 1; }

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }

TASK="$(python3 -c "import json; print(json.load(open('$Q'))['task'])")"
DRAFTS=()
while IFS= read -r p; do
  [ -n "$p" ] && DRAFTS+=("$p")
done < <(python3 -c "
import json
for r in json.load(open('$Q'))['drafts']:
    if r['deliverable']:
        print(r['path'])
")
[ "${#DRAFTS[@]}" -gt 0 ] || { echo "FATAL: no deliverable draft -- trap $TRAP is not a working trap (section 7)"; exit 1; }
echo "task: $TASK"
echo "deliverable drafts: ${DRAFTS[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then 3 control and 3 runs per draft"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "PROBE_START $START"
check_postponed() {
  local out
  out="$(python3 bench/e13_probe_read.py --trap "$TRAP" --window "$START" - 2>&1)"
  echo "$out"
  case "$out" in
    "batch: postponed"*) echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
  esac
}

echo "### control $TASK (n=3)"
python3 bench/run.py --task "$TASK" --runs 3 --arm control || echo "run.py exited non-zero for the control"
check_postponed
for d in "${DRAFTS[@]}"; do
  echo "### $d -> $TASK (n=3)"
  python3 bench/run.py --task "$TASK" --runs 3 --arm treatment --skill-from "$R/$d" \
    || echo "run.py exited non-zero for $d"
  check_postponed
done
echo "### E13 PROBE DONE"
```

- [ ] **Step 6: Verify the guards without a session.** `bash -n bench/e13_probe.sh && bash bench/e13_probe.sh --trap C --dry-run; echo "exit=$?"`. Expected: `FATAL: bench/distilled/C/qualification.json missing`, `exit=1`. That is correct before Task 8 runs.

- [ ] **Step 7: Full suite and commit**

```bash
python3 -m pytest -q 2>&1 | tail -1 | grep -q passed || exit 1
git add bench/e13_probe_read.py tests/test_bench_e13_probe_read.py bench/e13_probe.sh || exit 1
git commit -q -m "bench: E13 probe batch and reader

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 6: The outcome test and its reader

**Files:**
- Create: `bench/e13_outcome_read.py`, `tests/test_bench_e13_outcome_read.py`, `bench/e13_outcome.sh`

**Interfaces:**
- Consumes: `run.snapshot_plugin`, `--plugin-dir` and the `archive:<sha>` value of `env.plugin_commit` (Task 3); `qualification.json["first_qualifying"]` and the draft names (Task 4); `budget_sweep.seven` (Task 2); `e12_read.select`.
- Produces: `fisher_two_sided(a, b, c, d) -> float`; `read_outcome(rows, task, draft_name, old_commit, new_commit) -> {"batch", "reason", "arms": {"old"|"new": {"valid", "needed", "resolved", "mismatched", "rerun", "status"}}, "diff", "verdict", "p"}`. The verdict is `"improves"`, `"no large effect"`, `"ambiguous"`, `"worse (not pre-registered)"`, or None. The CLI is `python3 bench/e13_outcome_read.py --trap C --window FROM TO`. The script is `bash bench/e13_outcome.sh --trap C [--dry-run]`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_bench_e13_outcome_read.py`:

```python
"""Tests for bench/e13_outcome_read.py. Run: python3 tests/test_bench_e13_outcome_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e13_outcome_read as orr

TASK, NAME = "sf-author-verdict-from", "quote-rewrap"
OLD, NEW = "archive:" + "0" * 40, "archive:" + "9" * 40


def row(commit, resolved=False, injected=None, ok=True, tail=None):
    if injected is None:
        injected = commit == NEW
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "env": {"plugin_commit": commit},
            "injections": [{"skill": NAME}] if injected else [{"skill": "a-seven-skill"}]}


def arm(commit, resolved):
    return [row(commit, resolved=i < resolved) for i in range(6)]


def test_fisher_matches_known_values():
    assert abs(orr.fisher_two_sided(6, 0, 0, 6) - 2 / 924) < 1e-12
    assert abs(orr.fisher_two_sided(3, 3, 3, 3) - 1.0) < 1e-12


def test_three_more_resolved_improves():
    res = orr.read_outcome(arm(OLD, 1) + arm(NEW, 4), TASK, NAME, OLD, NEW)
    assert res["batch"] == "complete" and res["diff"] == 3 and res["verdict"] == "improves"


def test_the_pre_registered_bands():
    for old, new, verdict in ((2, 3, "no large effect"), (3, 2, "no large effect"),
                              (1, 3, "ambiguous"), (4, 1, "worse (not pre-registered)")):
        assert orr.read_outcome(arm(OLD, old) + arm(NEW, new), TASK, NAME, OLD, NEW)["verdict"] == verdict


def test_a_row_that_contradicts_qualification_is_void_and_two_void_the_arm():
    rows = arm(OLD, 0) + arm(NEW, 6) + [row(OLD, resolved=True, injected=True)]
    res = orr.read_outcome(rows, TASK, NAME, OLD, NEW)
    assert res["arms"]["old"]["mismatched"] == 1 and res["arms"]["old"]["valid"] == 6
    rows.append(row(OLD, injected=True))
    res = orr.read_outcome(rows, TASK, NAME, OLD, NEW)
    assert res["arms"]["old"]["status"] == "void" and res["batch"] == "void"
    assert res["verdict"] is None


def test_a_session_limit_postpones():
    rows = arm(OLD, 0) + [row(NEW, ok=False, tail="You've hit your session limit")]
    assert orr.read_outcome(rows, TASK, NAME, OLD, NEW)["batch"] == "postponed"


def test_an_unfinished_arm_is_incomplete():
    res = orr.read_outcome(arm(OLD, 0) + arm(NEW, 6)[:4], TASK, NAME, OLD, NEW)
    assert res["batch"] == "incomplete" and res["verdict"] is None


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

- [ ] **Step 2: Run to verify it fails.** `python3 tests/test_bench_e13_outcome_read.py`. Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the reader.** Create `bench/e13_outcome_read.py`:

```python
#!/usr/bin/env python3
"""Read the E13 outcome test (spec section 8): does the tokenizer fix improve outcomes?

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

Two arms of 6, told apart by env.plugin_commit: the plugin snapshot at 06885c0
(old tokenizer) and at 9cbb472 (new). Qualification predicted the old hook
leaves trap 2's draft out and the new one delivers it. A row that contradicts
that is void and re-run, and a second one voids its arm. A session refused at
the session limit postpones the whole batch.

Criterion: new minus old resolved >= 3 improves; within 1 is no large effect;
exactly 2 is ambiguous. Fisher's exact p (two-sided) is reported, never used as
a threshold. Run:

    python3 bench/e13_outcome_read.py --trap C --window <OUTCOME_START> -
"""
import argparse
import json
import subprocess
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402

N_ARM = 6
LIMIT_MARK = "session limit"
OLD_REF, NEW_REF = "06885c0", "9cbb472"


def fisher_two_sided(a, b, c, d):
    """p for the 2x2 table [[a, b], [c, d]], summing tables no likelier than it."""
    n1, n2, k = a + b, c + d, a + c
    total = comb(n1 + n2, k)
    p = lambda x: comb(n1, x) * comb(n2, k - x) / total
    observed = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1)
                        if p(x) <= observed * (1 + 1e-9)))


def _verdict(diff):
    if diff >= 3:
        return "improves"
    if abs(diff) <= 1:
        return "no large effect"
    if diff == 2:
        return "ambiguous"
    return "worse (not pre-registered)"


def read_outcome(rows, task, draft_name, old_commit, new_commit):
    mine = [r for r in rows if r.get("task") == task and r.get("arm") == "treatment"]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "arms": {}, "diff": None, "verdict": None, "p": None,
                "reason": "a session hit the session limit: re-run the whole batch"}
    arms = {}
    for label, commit, want in (("old", old_commit, False), ("new", new_commit, True)):
        trt = [r for r in mine if (r.get("env") or {}).get("plugin_commit") == commit]
        ran = [r for r in trt if r.get("session_ok")]
        match = [r for r in ran
                 if (draft_name in {i.get("skill") for i in r.get("injections") or []}) == want]
        counted = match[:N_ARM]
        a = {"valid": len(counted), "needed": N_ARM,
             "resolved": sum(1 for r in counted if r.get("resolved")),
             "mismatched": len(ran) - len(match), "rerun": len(trt) - len(match)}
        a["status"] = ("void" if a["mismatched"] >= 2 else
                       "complete" if a["valid"] >= N_ARM else "incomplete")
        arms[label] = a
    out = {"arms": arms, "diff": None, "verdict": None, "p": None}
    if any(a["status"] == "void" for a in arms.values()):
        out.update(batch="void", reason="an arm's delivery contradicted qualification twice")
    elif any(a["status"] == "incomplete" for a in arms.values()):
        out.update(batch="incomplete", reason="an arm is not fully measured")
    else:
        o, n = arms["old"]["resolved"], arms["new"]["resolved"]
        out.update(batch="complete", reason="", diff=n - o, verdict=_verdict(n - o),
                   p=fisher_two_sided(n, N_ARM - n, o, N_ARM - o))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    q = json.loads((ROOT / "distilled" / args.trap / "qualification.json").read_text(encoding="utf-8"))
    name = next(r["name"] for r in q["drafts"] if r["path"] == q["first_qualifying"])
    full = lambda ref: "archive:" + subprocess.run(
        ["git", "rev-parse", ref + "^{commit}"], cwd=str(ROOT.parent),
        capture_output=True, text=True, check=True).stdout.strip()
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_outcome(select(rows, args.window), q["task"], name, full(OLD_REF), full(NEW_REF))
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    for label, a in res["arms"].items():
        print("  %-3s valid %d/%d  resolved %d  mismatched %d  re-run %d  %s"
              % (label, a["valid"], a["needed"], a["resolved"], a["mismatched"], a["rerun"], a["status"]))
    if res["verdict"]:
        print("verdict: %s (new - old = %+d, Fisher p = %.3f)" % (res["verdict"], res["diff"], res["p"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the reader tests.** `python3 tests/test_bench_e13_outcome_read.py && python3 -m pytest -q tests/test_bench_e13_outcome_read.py`. Expected: 6 PASS.

- [ ] **Step 5: Write the batch script.** Create `bench/e13_outcome.sh`, then `chmod +x bench/e13_outcome.sh`:

```bash
#!/usr/bin/env bash
# E13 outcome test for trap 2. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 8.
#
# Library: the consolidated seven plus the trap's first qualifying draft.
# Two arms of 6, old first: the plugin as archived at 06885c0, then at 9cbb472,
# each extracted by run.snapshot_plugin and passed with --plugin-dir. Run it only
# after the probe batch read "working" -- section 6.1 makes that a condition.
# A session refused at the session limit stops the script; re-run it whole.
#
# Read with: python3 bench/e13_outcome_read.py --trap <trap> --window <OUTCOME_START> -
# Usage: bash bench/e13_outcome.sh --trap C [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
TRAP=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --trap) TRAP="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 1 ;;
  esac
done
[ -n "$TRAP" ] || { echo "usage: bash bench/e13_outcome.sh --trap C [--dry-run]"; exit 1; }
Q="bench/distilled/$TRAP/qualification.json"
[ -f "$Q" ] || { echo "FATAL: $Q missing"; exit 1; }

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }

TASK="$(python3 -c "import json; print(json.load(open('$Q'))['task'])")"
DRAFT="$(python3 -c "import json; print(json.load(open('$Q'))['first_qualifying'] or '')")"
[ -n "$DRAFT" ] || { echo "FATAL: trap $TRAP has no qualifying draft -- it cannot be trap 2 (section 6.1)"; exit 1; }
PLUS=()
while IFS= read -r p; do
  [ -n "$p" ] && PLUS+=(--plus-skill "$R/$p")
done < <(python3 -c "
import sys; sys.path[:0] = ['scripts', 'bench']; import budget_sweep as bs
for e in bs.seven:
    print(e['_path'])
")
[ "${#PLUS[@]}" -eq 14 ] || { echo "FATAL: expected the consolidated seven, got $(( ${#PLUS[@]} / 2 ))"; exit 1; }

SNAP="${SKILLFORGE_BENCH_WORK:-/tmp/skillforge-bench}/snapshots"
for ref in 06885c0 9cbb472; do
  python3 -c "import sys; sys.path.insert(0, 'bench'); import run; print(run.snapshot_plugin('$ref', '$SNAP/$ref'))" \
    || { echo "FATAL: snapshot $ref failed"; exit 1; }
done
echo "task: $TASK"
echo "draft: $DRAFT"
echo "library: the consolidated seven + draft"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed and both snapshots built; a real run probes the allowance, then 6 old and 6 new"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "OUTCOME_START $START"
for ref in 06885c0 9cbb472; do
  echo "### arm $ref (n=6)"
  python3 bench/run.py --task "$TASK" --runs 6 --arm treatment --skill-from "$R/$DRAFT" \
    "${PLUS[@]}" --plugin-dir "$SNAP/$ref" || echo "run.py exited non-zero for arm $ref"
  OUT="$(python3 bench/e13_outcome_read.py --trap "$TRAP" --window "$START" - 2>&1)"
  echo "$OUT"
  case "$OUT" in
    "batch: postponed"*) echo "STOP: session limit -- re-run this whole batch later"; exit 1 ;;
  esac
done
echo "### E13 OUTCOME DONE"
```

- [ ] **Step 6: Verify, zero sessions.** `bash -n bench/e13_outcome.sh && bash bench/e13_outcome.sh --trap C --dry-run; echo "exit=$?"`. Expected: `FATAL: bench/distilled/C/qualification.json missing`, `exit=1`.

- [ ] **Step 7: Full suite and commit**

```bash
python3 -m pytest -q 2>&1 | tail -1 | grep -q passed || exit 1
git add bench/e13_outcome_read.py tests/test_bench_e13_outcome_read.py bench/e13_outcome.sh || exit 1
git commit -q -m "bench: E13 outcome test and reader

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

### Task 7: Stage 1 — distil C (up to 6 sessions)

This task is controller-run. First fast-forward `main` with the tooling, under the same guards as before (primary tree clean, main not moved, no home path) and push it, so the plugin under test is committed.

- [ ] **Step 1: Probe the allowance.** `claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null`. If it fails, stop and report.
- [ ] **Step 2: Run both distillers**

```bash
python3 bench/distill.py --trap C --distiller learn --draws 3 --no-novelty-gate
python3 bench/distill.py --trap C --distiller learn-failure --draws 3 --no-novelty-gate
```

- [ ] **Step 3: Read the outcomes.** For each `bench/distilled/C/*-nogate/*/meta.json`, record `outcome`, `repair_resolved` and `skill_name`. A `session_failed` draw is re-run with the same command; the archive guard allows it. A session-limit hit postpones the rest to the next window.
- [ ] **Step 4: Gate.** If no draw is `saved`, C has no counted draft: stop, then write up and report (spec §4: trap 1 and trap 2 have no C candidate).
- [ ] **Step 5: Commit** `bench/distilled/C/` with the per-draw outcomes in the message. Check it for the home path first, since `meta.json` carries session tails.

### Task 8: Stage 2 — qualify and check delivery (zero sessions)

- [ ] **Step 1:** `python3 bench/e13_qualify.py --trap C --write`. Expected: exit 0, `library untouched: True`, no PROBLEM lines. `e13_qualify.py` now refuses before any work if `scripts/` or `hooks/` have drifted from `9cbb472` (a parallel branch could edit `scripts/retrieve.py` underneath this run) — a drift stops the stage: report it to the user rather than proceeding.
- [ ] **Step 2: Gate.** If `deliverable` is empty, C is not a working trap (§7). Stop, then write up and report.
- [ ] **Step 3: Commit** `bench/distilled/C/qualification.json` with the table in the message.

### Task 9: Stage 3 — probe batch (3 + 3 × deliverable drafts sessions, at most 21)

- [ ] **Step 1:** `bash bench/e13_probe.sh --trap C --dry-run`, then `bash bench/e13_probe.sh --trap C`, run in the background and logged to the scratchpad.
- [ ] **Step 2:** Read `python3 bench/e13_probe_read.py --trap C --window <PROBE_START> -`. Resolve the batch state:
  - **postponed:** re-run the whole batch in the next window.
  - **void:** re-run later as a fresh batch.
  - **incomplete** because of undelivered or failed rows: re-run those runs by hand as the script header says, then re-read.
- [ ] **Step 3: Gate.** If the verdict is `not working`, C is not a working trap. Stop, then write up and report.
- [ ] **Step 4: Commit** the new `bench/results.jsonl` rows with the reading in the message.

### Task 10: Stage 4 — outcome test (12 sessions, only if C qualifies and is working), then write-up

- [ ] **Step 1: Gate.** The outcome test runs only if BOTH hold: Task 9's probe verdict is `working`, AND `qualification.json["first_qualifying"]` is non-null.
  - If `first_qualifying` is null, C is **trap 1**. Trap 2 has no candidate (§6.2), so skip to Step 4.
  - Otherwise, if Task 9's probe also read `working`, C is **trap 2**, so run `bash bench/e13_outcome.sh --trap C --dry-run`, then the real run in the background.
- [ ] **Step 2:** Read `python3 bench/e13_outcome_read.py --trap C --window <OUTCOME_START> -`. Handle postponed, void and incomplete as in Task 9.
- [ ] **Step 3: Commit** the rows with the verdict and Fisher p in the message.
- [ ] **Step 4: Write up.** Add an E13-C register row and a section to `bench/RESULTS.md` covering distillation outcomes, the qualification table, the probe reading (using the window read in Task 9 — `e13_probe_read.py` now also ignores Stage 4 outcome rows when re-read after this stage), and the outcome verdict (or why none ran). Commit, fast-forward `main` under the guards, push, and report to the user in plain terms with a positive/negative verdict.
