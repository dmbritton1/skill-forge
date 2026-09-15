# E14 Trigger × Kind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run E14 Stage 1: four hand-written trap C drafts in a 2×2 of trigger (failure vs write) × kind (skill vs anti-skill). The drafts are delivery-checked, probed in one pre-registered 27-session batch, and read against a fixed criterion.

**Architecture:** E14 gets its own files and changes no E13 file:

- the four drafts, under `bench/drafts/E14/`;
- `bench/e14_read.py`, the reader: counting rules, effects and bands;
- `bench/e14_deliver.py`, a zero-session delivery check that freezes each draft's sha256 into `delivery.json`;
- `bench/e14_probe.sh`, the batch script: guards, then the fixed interleaved order, then repeats.

It reuses `audit.counts`, `e12_read.select`, `e13_outcome_read.fisher_two_sided`, `e13_qualify._install`/`_sandbox` and `real_path_check.delivered`/`export_scripts`, all by import only.

**Tech Stack:** Python 3 stdlib, bash, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md`

## Global Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and `bench/real_path_check.py` are not touched (imports allowed).
- No E13 file changes; E13's readers and results stay as they are (imports allowed).
- No absolute home path in committed files.
- Guard every commit with an explicit `|| exit 1`; the Bash tool ignores `set -e`.
- Loop in Python or over bash arrays, never over a bare `$var` (zsh does not word-split).
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- No step before Task 5 may launch a real `claude` session. `bench/run.py --check`, `--sandbox-check` and `bench/e14_probe.sh --dry-run` are zero-session and allowed.
- Full suite: `python3 -m pytest -q tests` — 924 passed at plan time; it must stay green after every task.

## Rulings made while planning

1. **Draft file names.** Spec section 2 names the files `bench/drafts/E14/{sf,sw,af,aw}/SKILL.md`. Instead they are `bench/drafts/E14/e14-quote-gate-rewrap-{sf,sw,af,aw}.md`, for two reasons:
   - `run.distilled_parts()` rejects any file named `SKILL.md` outside `bench/distilled/`.
   - `run.arm_segment()` names an authored draft's clone after the file stem, so four `SKILL.md` files would share one clone path.
   
   *Cost if wrong:* none. The spec's contents and names are otherwise unchanged.
2. **Repeats are capped.** The script appends at most 8 repeat runs after round 6, and stops once the reader's `--todo` list is empty. The spec does not cap repeats; a cap stops a stuck cell spending the allowance. *Cost if wrong:* a batch that needed more than 8 repeats reads `incomplete` and is re-run whole.
3. **A void batch stops the script.** Once a control run has resolved, the batch is void (spec section 4), so the remaining sessions could measure nothing. *Cost if wrong:* none.
4. **The delivery check refuses a dirty `scripts/` or `hooks/`.** It runs the hook from `git archive HEAD`, so uncommitted changes would make it check code that is not on disk. *Cost if wrong:* none.
5. **The drafts were checked while planning.** On 2026-09-14 the Task 1 texts were written to scratch and checked with zero sessions:
   - lengths 2012–2043 characters, within 2%;
   - each saves through the real `save_skill.validate`;
   - no hidden test names;
   - the real HEAD hook delivered each draft installed alone;
   - the operator's library was untouched.
   
   Task 2 re-runs this check as the committed gate.

## File map

| file | change | responsibility |
| --- | --- | --- |
| `bench/drafts/E14/e14-quote-gate-rewrap-{sf,sw,af,aw}.md` | create | the four arms |
| `tests/test_bench_e14_drafts.py` | create | the drafts hold everything identical except trigger and kind |
| `bench/e14_read.py` | create | select rows, count, effects, bands, baseline check, `--todo` |
| `tests/test_bench_e14_read.py` | create | reader unit tests |
| `bench/e14_deliver.py` | create | zero-session delivery check, `delivery.json`, `--check-frozen` |
| `tests/test_bench_e14_deliver.py` | create | gate and freeze unit tests |
| `bench/drafts/E14/delivery.json` | create (generated) | frozen draft hashes, delivery result |
| `bench/e14_probe.sh` | create | guards, fixed order, repeats, stop on postponed or void |
| `bench/results.jsonl`, `bench/RESULTS.md` | modify (Task 5) | batch rows, register row and section |

---

### Task 1: The four drafts

**Files:**
- Create: `bench/drafts/E14/e14-quote-gate-rewrap-sf.md`, `bench/drafts/E14/e14-quote-gate-rewrap-sw.md`, `bench/drafts/E14/e14-quote-gate-rewrap-af.md`, `bench/drafts/E14/e14-quote-gate-rewrap-aw.md`
- Test: `tests/test_bench_e14_drafts.py`

**Interfaces:**
- Consumes: `save_skill.validate(text) -> list[str]` and `save_skill.parse_frontmatter(text) -> (dict|None, str)`, both existing in `scripts/save_skill.py`.
- Produces: the four draft files at the paths above. Task 2's reader hard-codes the name `e14-quote-gate-rewrap-<cell>`, so the test here defines the same constants locally.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e14_drafts.py`:

```python
"""E14 spec section 2: the four drafts differ only in trigger and kind.
Run: python3 tests/test_bench_e14_drafts.py"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import save_skill

CELLS = ("sf", "sw", "af", "aw")
USE = {
    "f": "Use when: a verbatim-quote evidence gate fails a quote that differs from "
         "the source text only by line breaks or indentation.",
    "w": "Use when: writing or editing a gate that checks model-quoted evidence "
         "against source text with a substring test, e.g. `evidence in text`.",
}
FIX = ('ev = " ".join((f.get("evidence") or "").split()) '
       'if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()): '
       'return "fail"')
NAIVE = ('ev = (f.get("evidence") or "").strip()', "ev not in text")
FRAMING = "looks like the strictest, safest"


def flat(s):
    return " ".join(s.split())


def text(cell):
    return (ROOT / "bench" / "drafts" / "E14" / ("e14-quote-gate-rewrap-%s.md" % cell)).read_text(
        encoding="utf-8")


def test_every_draft_saves_cleanly():
    for c in CELLS:
        assert save_skill.validate(text(c)) == [], (c, save_skill.validate(text(c)))


def test_name_and_kind_match_the_cell():
    for c in CELLS:
        fm, _ = save_skill.parse_frontmatter(text(c))
        assert fm["name"] == "e14-quote-gate-rewrap-" + c
        assert fm["kind"] == ("skill" if c[0] == "s" else "antiskill")


def test_the_use_when_line_is_the_cells_trigger_and_nothing_else_differs_in_description():
    rest = set()
    for c in CELLS:
        fm, _ = save_skill.parse_frontmatter(text(c))
        desc = flat(fm["description"])
        assert desc.count("Use when:") == 1, c
        assert flat(USE[c[1]]) in desc, c
        rest.add(desc.replace(flat(USE[c[1]]), ""))
    assert len(rest) == 1, rest


def test_fingerprints_are_identical():
    fps = {repr(save_skill.parse_frontmatter(text(c))[0].get("fingerprints")) for c in CELLS}
    assert len(fps) == 1 and "None" not in fps, fps


def test_same_kind_drafts_have_identical_bodies():
    body = lambda c: save_skill.parse_frontmatter(text(c))[1]
    assert body("sf") == body("sw")
    assert body("af") == body("aw")


def test_every_draft_carries_the_fix_and_the_naive_check():
    for c in CELLS:
        t = flat(text(c))
        assert FIX in t, c
        for piece in NAIVE:
            assert piece in t, (c, piece)


def test_only_anti_skills_carry_the_trap_framing():
    for c in CELLS:
        assert (FRAMING in flat(text(c))) == (c[0] == "a"), c


def test_no_draft_names_a_hidden_test():
    for c in CELLS:
        assert set(re.findall(r"test_[a-z_]+", text(c))) <= {"test_validate"}, c


def test_lengths_are_within_ten_percent():
    lens = [len(text(c)) for c in CELLS]
    assert min(lens) >= 0.9 * max(lens), lens


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

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m pytest -q tests/test_bench_e14_drafts.py`
Expected: FAIL with `FileNotFoundError` for `bench/drafts/E14/e14-quote-gate-rewrap-sf.md`

- [ ] **Step 3: Create the four drafts, verbatim**

`bench/drafts/E14/e14-quote-gate-rewrap-sf.md`:

````markdown
---
name: e14-quote-gate-rewrap-sf
kind: skill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: a verbatim-quote evidence gate fails a quote that differs from the source text only by line breaks or indentation.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Procedure
1. The gate is the check on each passing finding's quote. The naive version is
   `ev = (f.get("evidence") or "").strip()` followed by
   `if len(ev) < MIN_EVIDENCE_CHARS or ev not in text`.
2. Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
   floor to the collapsed span:
   ```python
   ev = " ".join((f.get("evidence") or "").split())
   if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
       return "fail"
   ```
3. Leave the `ok is not True` check and the `blocks()` logic unchanged.

## Gotchas
- Models re-wrap hard-wrapped prose when they quote it, so a real quote of
  `flush() before\n   close().` comes back as `flush() before close().`, and a
  byte-exact test rejects it. `.strip()` only trims the ends of the quote.
- Collapsing only the evidence is not enough: the newline is in the source text.
- Do not switch to word-set, sorted-token or fuzzy matching. A reordered quote
  such as `close() before Call flush().` can be written without reading the
  source, and must still fail.

## Verification
- `python3 tests/test_validate.py` exits 0 with every line `PASS`.
- A quote that differs from the source only by a line break yields `"pass"`;
  the same words reordered yield `"fail"`.
````

`bench/drafts/E14/e14-quote-gate-rewrap-sw.md`: identical to `-sf` except these two lines:

- `name: e14-quote-gate-rewrap-sw`
- `  Use when: writing or editing a gate that checks model-quoted evidence against source text with a substring test, e.g. `evidence in text`.`

The full file:

````markdown
---
name: e14-quote-gate-rewrap-sw
kind: skill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: writing or editing a gate that checks model-quoted evidence against source text with a substring test, e.g. `evidence in text`.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Procedure
1. The gate is the check on each passing finding's quote. The naive version is
   `ev = (f.get("evidence") or "").strip()` followed by
   `if len(ev) < MIN_EVIDENCE_CHARS or ev not in text`.
2. Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
   floor to the collapsed span:
   ```python
   ev = " ".join((f.get("evidence") or "").split())
   if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
       return "fail"
   ```
3. Leave the `ok is not True` check and the `blocks()` logic unchanged.

## Gotchas
- Models re-wrap hard-wrapped prose when they quote it, so a real quote of
  `flush() before\n   close().` comes back as `flush() before close().`, and a
  byte-exact test rejects it. `.strip()` only trims the ends of the quote.
- Collapsing only the evidence is not enough: the newline is in the source text.
- Do not switch to word-set, sorted-token or fuzzy matching. A reordered quote
  such as `close() before Call flush().` can be written without reading the
  source, and must still fail.

## Verification
- `python3 tests/test_validate.py` exits 0 with every line `PASS`.
- A quote that differs from the source only by a line break yields `"pass"`;
  the same words reordered yield `"fail"`.
````

`bench/drafts/E14/e14-quote-gate-rewrap-af.md`:

````markdown
---
name: e14-quote-gate-rewrap-af
kind: antiskill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: a verbatim-quote evidence gate fails a quote that differs from the source text only by line breaks or indentation.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
symptoms:
  - "verdict fail although every criterion is ok"
  - "evidence not in text"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Trap
Checking each passing finding's quote with
`ev = (f.get("evidence") or "").strip()` followed by
`if len(ev) < MIN_EVIDENCE_CHARS or ev not in text` looks like the strictest,
safest anti-sycophancy check. But models re-wrap hard-wrapped prose when they
quote it, so a real quote of `flush() before\n   close().` comes back as
`flush() before close().`, and the byte-exact test rejects it.

## Symptom
The gate returns `"fail"` for a finding whose quote is visibly in the source
text, and no exception is raised.

## Cause
`.strip()` only trims the ends of the quote. A newline and indentation inside
the source still have to match byte for byte.

## Fix
Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
floor to the collapsed span:

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

Collapsing only the evidence is not enough: the newline is in the source text.
Leave the `ok is not True` check and the `blocks()` logic unchanged. Do not
switch to word-set, sorted-token or fuzzy matching. A reordered quote such as
`close() before Call flush().` can be written without reading the source, and
must still fail.
````

`bench/drafts/E14/e14-quote-gate-rewrap-aw.md`:

````markdown
---
name: e14-quote-gate-rewrap-aw
kind: antiskill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: writing or editing a gate that checks model-quoted evidence against source text with a substring test, e.g. `evidence in text`.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
symptoms:
  - "verdict fail although every criterion is ok"
  - "evidence not in text"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Trap
Checking each passing finding's quote with
`ev = (f.get("evidence") or "").strip()` followed by
`if len(ev) < MIN_EVIDENCE_CHARS or ev not in text` looks like the strictest,
safest anti-sycophancy check. But models re-wrap hard-wrapped prose when they
quote it, so a real quote of `flush() before\n   close().` comes back as
`flush() before close().`, and the byte-exact test rejects it.

## Symptom
The gate returns `"fail"` for a finding whose quote is visibly in the source
text, and no exception is raised.

## Cause
`.strip()` only trims the ends of the quote. A newline and indentation inside
the source still have to match byte for byte.

## Fix
Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
floor to the collapsed span:

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

Collapsing only the evidence is not enough: the newline is in the source text.
Leave the `ok is not True` check and the `blocks()` logic unchanged. Do not
switch to word-set, sorted-token or fuzzy matching. A reordered quote such as
`close() before Call flush().` can be written without reading the source, and
must still fail.
````

If the drafts are only available from a copy of this plan, copy each block's content exactly, including the trailing newline. Every byte is part of the experiment.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e14_drafts.py`
Expected: 9 passed

If `test_the_use_when_line_is_the_cells_trigger_and_nothing_else_differs_in_description` fails only because `parse_frontmatter` folds the `description` differently than `flat()` expects, report BLOCKED with the parsed value. Do not edit a draft to make a test pass.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/drafts/E14 tests/test_bench_e14_drafts.py || exit 1
git commit -q -m "bench: E14 drafts -- trigger x kind on trap C, identical otherwise

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 2: The reader, `bench/e14_read.py`

**Files:**
- Create: `bench/e14_read.py`
- Test: `tests/test_bench_e14_read.py`

**Interfaces:**
- Consumes:
  - `audit.counts(row) -> bool`
  - `e12_read.select(rows, windows) -> list`, with `windows` a list of `(FROM, TO)` pairs, FROM exclusive, TO inclusive or `"-"`
  - `e13_outcome_read.fisher_two_sided(a, b, c, d) -> float`
- Produces:
  - `TASK = "sf-author-verdict-from"`, `CELLS = ("sf", "sw", "af", "aw")`, `N_CELL = 6`, `N_CONTROL = 3`
  - `draft_name(cell) -> str`
  - `cell_of(row) -> str | None`
  - `band(effect: int) -> str`
  - `read_batch(rows) -> dict` with keys:
    - `batch`: `postponed` | `void` | `incomplete` | `complete`
    - `reason`: str
    - `control`: `{valid, needed, resolved, invalid}` or None
    - `cells`: `{cell: {valid, needed, resolved, undelivered, invalid, status}}`
    - `effects`: `{"trigger": {diff, reading, p}, "kind": {...}}` or None
    - `baseline`: `{"sf": int, "af": int, "sf_as_predicted": bool, "af_as_predicted": bool}` or None
  - `todo(res) -> list[str]`: one entry per run still needed, `"control"` first, then cells in `CELLS` order
  - CLI: `python3 bench/e14_read.py --window FROM TO [--todo]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e14_read.py`:

```python
"""Tests for bench/e14_read.py. Run: python3 tests/test_bench_e14_read.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e14_read as er

TASK = er.TASK


def ctl(resolved=False, ok=True, tail=None, audit="clean"):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "skill_path": None, "injections": [],
            "sandbox": True, "audit": {"verdict": audit}}


def trt(cell, resolved=False, delivered=True, ok=True, audit="clean"):
    name = er.draft_name(cell)
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None,
            "skill_path": "~/x/wt/bench/drafts/E14/%s.md" % name,
            "injections": [{"skill": name if delivered else "other"}],
            "sandbox": True, "audit": {"verdict": audit}}


def cells(**resolved):
    """Six valid delivered rows per cell; `resolved` gives each cell's count."""
    rows = []
    for c in er.CELLS:
        rows += [trt(c, resolved=i < resolved.get(c, 0)) for i in range(6)]
    return rows


def test_cell_of_reads_the_draft_path():
    assert er.cell_of(trt("aw")) == "aw"
    assert er.cell_of(ctl()) is None
    assert er.cell_of({"skill_path": "~/x/bench/drafts/E14/other.md"}) is None


def test_bands():
    for diff, reading in ((4, "factor matters"), (7, "factor matters"), (3, "ambiguous"),
                          (2, "ambiguous"), (1, "no large effect"), (0, "no large effect"),
                          (-1, "no large effect"), (-2, "ambiguous"), (-3, "ambiguous"),
                          (-4, "opposite effect (not pre-registered)")):
        assert er.band(diff) == reading, (diff, reading)


def test_a_complete_batch_computes_both_effects():
    res = er.read_batch([ctl()] * 3 + cells(sf=0, sw=4, af=5, aw=6))
    assert res["batch"] == "complete"
    assert res["effects"]["trigger"]["diff"] == (4 + 6) - (0 + 5)
    assert res["effects"]["kind"]["diff"] == (5 + 6) - (0 + 4)
    assert res["effects"]["trigger"]["reading"] == "factor matters"
    assert 0.0 <= res["effects"]["kind"]["p"] <= 1.0
    assert res["baseline"] == {"sf": 0, "af": 5, "sf_as_predicted": True, "af_as_predicted": True}


def test_baseline_flags_a_moved_baseline():
    res = er.read_batch([ctl()] * 3 + cells(sf=2, af=4))
    assert res["baseline"]["sf_as_predicted"] is False
    assert res["baseline"]["af_as_predicted"] is False


def test_a_resolved_control_voids_the_batch():
    res = er.read_batch([ctl(resolved=True), ctl(), ctl()] + cells())
    assert res["batch"] == "void" and res["effects"] is None


def test_a_session_limit_postpones_the_batch():
    res = er.read_batch([ctl()] * 3 + cells() + [trt("sf", ok=False)] +
                        [dict(trt("sw", ok=False), session_tail="You've hit your session limit")])
    assert res["batch"] == "postponed" and res["cells"] == {}


def test_void_audit_failed_session_and_undelivered_rows_do_not_count():
    rows = [ctl()] * 3 + cells() + [trt("sf", resolved=True, audit="leak"),
                                    trt("sf", resolved=True, ok=False),
                                    trt("sf", resolved=True, delivered=False)]
    cell = er.read_batch(rows)["cells"]["sf"]
    assert cell["valid"] == 6 and cell["resolved"] == 0
    assert cell["invalid"] == 2 and cell["undelivered"] == 1 and cell["status"] == "complete"


def test_two_undelivered_rows_void_the_cell_and_no_effect_is_computed():
    rows = [ctl()] * 3 + cells() + [trt("aw", delivered=False)] * 2
    res = er.read_batch(rows)
    assert res["cells"]["aw"]["status"] == "void"
    assert res["batch"] == "complete" and res["effects"] is None
    assert "aw" in res["reason"]


def test_a_cell_counts_only_its_first_six_valid_runs():
    rows = [ctl()] * 3 + cells(sw=0) + [trt("sw", resolved=True)]
    assert er.read_batch(rows)["cells"]["sw"]["resolved"] == 0


def test_a_missing_run_leaves_the_batch_incomplete_and_todo_names_it():
    rows = [ctl()] * 2 + [r for r in cells() if not (er.cell_of(r) == "af")] + [trt("af")] * 5
    res = er.read_batch(rows)
    assert res["batch"] == "incomplete" and res["effects"] is None
    assert er.todo(res) == ["control", "af"]


def test_todo_is_empty_for_complete_void_and_postponed_batches():
    assert er.todo(er.read_batch([ctl()] * 3 + cells())) == []
    assert er.todo(er.read_batch([ctl(resolved=True)] + cells())) == []
    assert er.todo(er.read_batch([dict(ctl(ok=False), session_tail="session limit")])) == []


def test_rows_for_other_tasks_are_ignored():
    rows = [ctl()] * 3 + cells() + [dict(trt("sf", resolved=True), task="other")] * 3
    assert er.read_batch(rows)["cells"]["sf"]["resolved"] == 0


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

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m pytest -q tests/test_bench_e14_read.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'e14_read'`

- [ ] **Step 3: Implement `bench/e14_read.py`**

```python
#!/usr/bin/env python3
"""Read the E14 batch (spec sections 4-5): trigger x kind on trap C.

docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md

Four hand-written drafts -- skill/anti-skill x failure-time/write-time
trigger -- each installed alone, 6 runs, plus a same-batch control of 3.

A row refused at the session limit postpones the whole batch. A resolved
control voids it. A row audit.counts() rejects, a failed session, or a draft
row that did not inject its draft does not count and is repeated; a second
undelivered row voids that cell, and a void cell means no effect is computed.
Each cell counts its first 6 valid runs, the control its first 3.

Trigger effect = (SW + AW) - (SF + AF); kind effect = (AF + AW) - (SF + SW).
+4 or more: the factor matters. -1..+1: no large effect. Otherwise ambiguous,
except -4 or less, which is reported but not pre-registered. Fisher's p is
reported, never a threshold. Run:

    python3 bench/e14_read.py --window <E14_START> -
    python3 bench/e14_read.py --window <E14_START> - --todo
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit import counts  # noqa: E402
from e12_read import select  # noqa: E402
from e13_outcome_read import fisher_two_sided  # noqa: E402

TASK = "sf-author-verdict-from"
CELLS = ("sf", "sw", "af", "aw")
N_CELL = 6
N_CONTROL = 3
LIMIT_MARK = "session limit"
DRAFT_DIR = "bench/drafts/E14/"


def draft_name(cell):
    return "e14-quote-gate-rewrap-" + cell


def cell_of(row):
    """The E14 cell a treatment row installed, from its skill_path, or None."""
    path = row.get("skill_path") or ""
    return next((c for c in CELLS if path.endswith(DRAFT_DIR + draft_name(c) + ".md")), None)


def band(effect):
    if effect >= 4:
        return "factor matters"
    if effect <= -4:
        return "opposite effect (not pre-registered)"
    if abs(effect) <= 1:
        return "no large effect"
    return "ambiguous"


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def _effect(high, low):
    """Effect of (high cells) - (low cells), each side pooled over 12 runs."""
    return {"diff": high - low, "reading": band(high - low),
            "p": fisher_two_sided(high, 2 * N_CELL - high, low, 2 * N_CELL - low)}


def read_batch(rows):
    mine = [r for r in rows if r.get("task") == TASK]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "reason": "a session hit the session limit: re-run the whole batch",
                "control": None, "cells": {}, "effects": None, "baseline": None}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if _valid(r)]
    out = {"control": {"valid": min(len(ok), N_CONTROL), "needed": N_CONTROL,
                       # Every valid control run, not just the first 3: one
                       # resolution anywhere voids the batch (spec section 4).
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "invalid": len(control) - len(ok)},
           "cells": {}, "effects": None, "baseline": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 4)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    for c in CELLS:
        trt = [r for r in mine if r.get("arm") == "treatment" and cell_of(r) == c]
        valid = [r for r in trt if _valid(r)]
        hit = [r for r in valid
               if draft_name(c) in {i.get("skill") for i in r.get("injections") or []}]
        counted = hit[:N_CELL]
        cell = {"valid": len(counted), "needed": N_CELL,
                "resolved": sum(1 for r in counted if r.get("resolved")),
                "undelivered": len(valid) - len(hit), "invalid": len(trt) - len(valid)}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_CELL else "incomplete")
        complete = complete and cell["status"] != "incomplete"
        out["cells"][c] = cell
    if not complete:
        out.update(batch="incomplete", reason="the control or a cell is not fully measured")
        return out
    void = [c for c in CELLS if out["cells"][c]["status"] == "void"]
    if void:
        out.update(batch="complete",
                   reason="cell(s) %s void: neither effect is computed" % ", ".join(void))
        return out
    R = {c: out["cells"][c]["resolved"] for c in CELLS}
    out["effects"] = {"trigger": _effect(R["sw"] + R["aw"], R["sf"] + R["af"]),
                      "kind": _effect(R["af"] + R["aw"], R["sf"] + R["sw"])}
    out["baseline"] = {"sf": R["sf"], "af": R["af"],
                       "sf_as_predicted": R["sf"] <= 1, "af_as_predicted": R["af"] >= 5}
    out.update(batch="complete", reason="")
    return out


def todo(res):
    """One entry per run still needed, for bench/e14_probe.sh's repeat loop."""
    if res["batch"] != "incomplete":
        return []
    need = ["control"] * (N_CONTROL - res["control"]["valid"])
    for c in CELLS:
        cell = res["cells"][c]
        if cell["status"] == "incomplete":
            need += [c] * (N_CELL - cell["valid"])
    return need


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    ap.add_argument("--todo", action="store_true",
                    help="print only the runs still needed, one per line")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_batch(select(rows, args.window))
    if args.todo:
        for arm in todo(res):
            print(arm)
        return 0
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control  valid %d/%d  resolved %d  invalid %d"
              % (c["valid"], c["needed"], c["resolved"], c["invalid"]))
    for cell, c in res["cells"].items():
        print("  %-7s  valid %d/%d  resolved %d  undelivered %d  invalid %d  %s"
              % (cell, c["valid"], c["needed"], c["resolved"], c["undelivered"], c["invalid"],
                 c["status"]))
    if res["effects"]:
        for name, e in res["effects"].items():
            print("%s effect: %+d -- %s (Fisher p = %.3f)" % (name, e["diff"], e["reading"], e["p"]))
        b = res["baseline"]
        print("baseline: SF %d/6 (%s), AF %d/6 (%s)"
              % (b["sf"], "as predicted" if b["sf_as_predicted"] else "MOVED",
                 b["af"], "as predicted" if b["af_as_predicted"] else "MOVED"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e14_read.py`
Expected: 12 passed

Run: `python3 bench/e14_read.py --window 2026-09-14T23:59:59 -`
Expected: `batch: incomplete -- the control or a cell is not fully measured` and a `control  valid 0/3 ...` line. No row lies in the window, so this only checks that the CLI runs.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/e14_read.py tests/test_bench_e14_read.py || exit 1
git commit -q -m "bench: E14 reader -- counting rules, trigger and kind effects, bands

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 3: The delivery check, `bench/e14_deliver.py`

**Files:**
- Create: `bench/e14_deliver.py`
- Create (generated): `bench/drafts/E14/delivery.json`
- Test: `tests/test_bench_e14_deliver.py`

**Interfaces:**
- Consumes:
  - `e14_read.CELLS`, `e14_read.TASK`, `e14_read.draft_name(cell)` (Task 2)
  - `e13_qualify._install(paths, home, project) -> list[str]` and `e13_qualify._sandbox(work, tag) -> (home, project)`
  - `real_path_check.delivered(scripts_dir, prompt, session, project, home) -> (list[str], str)` and `real_path_check.export_scripts(ref, into) -> Path`
  - `libguard.snapshot()`
  - the four drafts (Task 1)
- Produces:
  - `draft_path(cell) -> Path`
  - `sha256(path) -> str`
  - `gate(rows) -> bool`
  - `stale(record, root) -> list[str]`
  - `delivery.json`: `{"task", "ref": "HEAD", "commit", "drafts": [{cell, name, path, sha256, delivered}], "library_untouched"}`
  - CLI: `python3 bench/e14_deliver.py [--write | --check-frozen]`; `--check-frozen` exits 1 unless `delivery.json` exists, passes the gate, and no draft has changed

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e14_deliver.py`:

```python
"""Tests for bench/e14_deliver.py. Run from the repo root: python3 tests/test_bench_e14_deliver.py"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e14_deliver as ed


def _rows(delivered=(True, True, True, True)):
    return [{"cell": c, "delivered": d} for c, d in zip(("sf", "sw", "af", "aw"), delivered)]


def test_the_gate_needs_all_four_delivered():
    assert ed.gate(_rows()) is True
    assert ed.gate(_rows((True, False, True, True))) is False
    assert ed.gate(_rows()[:3]) is False


def test_draft_paths_are_the_committed_drafts():
    for c in ("sf", "sw", "af", "aw"):
        assert ed.draft_path(c).is_file(), c


def test_stale_names_a_draft_changed_since_it_was_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "a.md").write_text("one\n", encoding="utf-8")
        (root / "b.md").write_text("two\n", encoding="utf-8")
        record = {"drafts": [{"cell": "sf", "path": "a.md", "sha256": ed.sha256(root / "a.md")},
                             {"cell": "sw", "path": "b.md", "sha256": ed.sha256(root / "b.md")}]}
        assert ed.stale(record, root) == []
        (root / "b.md").write_text("changed\n", encoding="utf-8")
        assert ed.stale(record, root) == ["sw"]
        (root / "a.md").unlink()
        assert ed.stale(record, root) == ["sf", "sw"]


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

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m pytest -q tests/test_bench_e14_deliver.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'e14_deliver'`

- [ ] **Step 3: Implement `bench/e14_deliver.py`**

```python
#!/usr/bin/env python3
"""E14 delivery check (spec section 3). Zero sessions.

docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md

Installs each E14 draft ALONE through the real save_skill.py into a sandboxed
HOME and project, runs the plugin's prompt hook (from `git archive HEAD`) on
the task's author prompt, and records whether that draft was delivered. All
four must be. delivery.json freezes each draft's sha256, and the batch script
refuses to start if a draft changed since. Run from the repo root:

    python3 bench/e14_deliver.py --write          # check and record
    python3 bench/e14_deliver.py --check-frozen   # batch guard
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import libguard                                                   # noqa: E402
from e13_qualify import _install, _sandbox                         # noqa: E402
from e14_read import CELLS, TASK, draft_name                       # noqa: E402
from real_path_check import delivered, export_scripts              # noqa: E402

DRAFTS = ROOT / "bench" / "drafts" / "E14"
RECORD = DRAFTS / "delivery.json"


def draft_path(cell):
    return DRAFTS / (draft_name(cell) + ".md")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def gate(rows):
    return len(rows) == len(CELLS) and all(r["delivered"] for r in rows)


def stale(record, root):
    """Cells whose draft is missing or changed since `record` was written."""
    out = []
    for r in record["drafts"]:
        p = pathlib.Path(root) / r["path"]
        if not p.is_file() or sha256(p) != r["sha256"]:
            out.append(r["cell"])
    return out


def check_frozen():
    if not RECORD.is_file():
        print("FATAL: %s missing -- run bench/e14_deliver.py --write" % RECORD.relative_to(ROOT))
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if not gate(record["drafts"]):
        print("FATAL: delivery.json records a draft that was not delivered")
        return 1
    changed = stale(record, ROOT)
    if changed:
        print("FATAL: draft(s) changed since delivery.json: %s" % ", ".join(changed))
        return 1
    print("drafts frozen: all %d delivered, none changed" % len(record["drafts"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write bench/drafts/E14/delivery.json")
    ap.add_argument("--check-frozen", action="store_true",
                    help="exit 1 unless delivery.json passes and no draft changed")
    args = ap.parse_args(argv)
    if args.check_frozen:
        return check_frozen()
    # The hook runs from `git archive HEAD`, so uncommitted plugin code would
    # make this check a different plugin from the one on disk.
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "hooks"],
                           cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if dirty:
        print("FATAL: uncommitted changes under scripts/ or hooks/")
        return 1
    cfg = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))
    prompt = next(t for t in cfg["tasks"] if t["id"] == TASK)["prompt"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()

    before = libguard.snapshot()
    # Resolved: save_skill records project roots with symlinks resolved and
    # macOS's temp dir is a symlink (same reason as e13_qualify).
    work = os.path.realpath(tempfile.mkdtemp(prefix="e14-deliver-"))
    rows, problems = [], []
    try:
        scripts = export_scripts("HEAD", os.path.join(work, "head"))
        for i, cell in enumerate(CELLS):
            home, project = _sandbox(work, cell)
            problems += _install([draft_path(cell)], home, project)
            got, err = delivered(scripts, prompt, "e14-deliver-%d" % i, project, home)
            if err:
                problems.append("%s hook stderr: %s" % (cell, err[-200:]))
            rows.append({"cell": cell, "name": draft_name(cell),
                         "path": str(draft_path(cell).relative_to(ROOT)),
                         "sha256": sha256(draft_path(cell)),
                         "delivered": draft_name(cell) in got})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    for r in rows:
        print("%-3s %-28s delivered %s" % (r["cell"], r["name"], r["delivered"]))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    ok = gate(rows) and untouched and not problems
    print("gate: %s" % ("pass" if ok else "FAIL"))
    if args.write and ok:
        RECORD.write_text(json.dumps({"task": TASK, "ref": "HEAD", "commit": commit,
                                      "drafts": rows, "library_untouched": untouched},
                                     indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % RECORD.relative_to(ROOT))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests, then the real check**

Run: `python3 -m pytest -q tests/test_bench_e14_deliver.py`
Expected: 3 passed

Run: `python3 -m pytest -q tests`
Expected: all pass.

Commit the code first, so the HEAD export matches disk:

```bash
git add bench/e14_deliver.py tests/test_bench_e14_deliver.py || exit 1
git commit -q -m "bench: E14 delivery check -- each draft alone through the real hook, hashes frozen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

Run: `python3 bench/e14_deliver.py --write`
Expected: all four lines `delivered True`, `operator's library untouched: True`, `gate: pass`, `wrote bench/drafts/E14/delivery.json`.

If any draft is not delivered, stop and report BLOCKED with the output. The spec allows only adding shared retrieval words to both drafts of that trigger, and that edit is the controller's decision to make.

Run: `python3 bench/e14_deliver.py --check-frozen`
Expected: `drafts frozen: all 4 delivered, none changed`, exit 0.

- [ ] **Step 5: Commit the record**

```bash
git add bench/drafts/E14/delivery.json || exit 1
git commit -q -m "bench: E14 delivery record -- all four drafts delivered alone

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 4: The batch script, `bench/e14_probe.sh`

**Files:**
- Create: `bench/e14_probe.sh`

**Interfaces:**
- Consumes:
  - `python3 bench/run.py --check` and `--sandbox-check`
  - `python3 bench/e14_deliver.py --check-frozen` (Task 3)
  - `python3 bench/e14_read.py --window FROM - [--todo]` (Task 2)
  - `run.py --task sf-author-verdict-from --runs 1 --arm control`
  - `run.py ... --arm treatment --skill-from <absolute draft path>`
- Produces: the batch. Every row is appended to `bench/results.jsonl` by `run.py`, and the script prints `E14_START <timestamp>` for the reader's window.

- [ ] **Step 1: Write `bench/e14_probe.sh`**

```bash
#!/usr/bin/env bash
# E14 Stage 1 batch. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md, section 4.
#
# 27 sessions: the control x3 and each draft x6, installed alone, in fixed
# interleaved rounds. Repeats (void, failed or undelivered rows) follow round 6,
# at most 8 (plan ruling 2). A session refused at the session limit postpones
# the whole batch; a resolved control voids it. Either stops the script.
#
# Read with: python3 bench/e14_read.py --window <E14_START> -
# Usage: bash bench/e14_probe.sh [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
TASK="sf-author-verdict-from"
D="$R/bench/drafts/E14"

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
# Sandbox spec section 4.4: zero sessions, before the first one.
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
python3 bench/e14_deliver.py --check-frozen || { echo "FATAL: E14 drafts not frozen and delivered"; exit 1; }

# Spec section 4: rounds 1, 3 and 5 open with a control run.
ORDER=(control sf sw af aw
       sw af aw sf
       control af aw sf sw
       aw sf sw af
       control sf sw af aw
       sw af aw sf)
echo "order: ${ORDER[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 8 repeats"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "E14_START $START"

run_one() {  # $1: control | sf | sw | af | aw
  if [ "$1" = "control" ]; then
    python3 bench/run.py --task "$TASK" --runs 1 --arm control \
      || echo "run.py exited non-zero for control"
  else
    python3 bench/run.py --task "$TASK" --runs 1 --arm treatment \
      --skill-from "$D/e14-quote-gate-rewrap-$1.md" || echo "run.py exited non-zero for $1"
  fi
  local out
  out="$(python3 bench/e14_read.py --window "$START" - 2>&1)"
  case "$out" in
    "batch: postponed"*) echo "$out"; echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
    "batch: void"*) echo "$out"; echo "STOP: the control resolved -- the batch is void (spec section 4)"; exit 1 ;;
  esac
}

for arm in "${ORDER[@]}"; do
  echo "### $arm"
  run_one "$arm"
done

EXTRA=0
while [ "$EXTRA" -lt 8 ]; do
  NEXT="$(python3 bench/e14_read.py --window "$START" - --todo | head -n 1)"
  [ -n "$NEXT" ] || break
  echo "### repeat $NEXT"
  run_one "$NEXT"
  EXTRA=$((EXTRA + 1))
done

python3 bench/e14_read.py --window "$START" -
echo "### E14 DONE"
```

- [ ] **Step 2: Verify without spending a session**

Run: `chmod +x bench/e14_probe.sh && bash -n bench/e14_probe.sh && echo syntax-ok`
Expected: `syntax-ok`

Run: `python3 -c "import collections,re; t=open('bench/e14_probe.sh').read(); o=re.search(r'ORDER=\(([^)]*)\)', t).group(1).split(); print(collections.Counter(o))"`
Expected: `Counter({'sf': 6, 'sw': 6, 'af': 6, 'aw': 6, 'control': 3})`

Run: `bash bench/e14_probe.sh --dry-run`
Expected: the order line and then `dry run: every guard passed; ...`. If an earlier guard fails for a reason outside this task, such as a non-empty global library, report DONE_WITH_CONCERNS with the output verbatim.

- [ ] **Step 3: Commit**

```bash
git add bench/e14_probe.sh || exit 1
git commit -q -m "bench: E14 batch script -- guards, fixed interleaved order, capped repeats

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 5: Run the batch and record it (the controller runs this, not a subagent)

Spends 27 to 35 sessions. Run only after the final whole-branch review is clean, and start it right after a session-limit reset.

**Files:**
- Modify: `bench/results.jsonl` (batch rows), `bench/RESULTS.md` (register row and E14 section)

- [ ] **Step 1: Start the batch in the background**

Run, in the background, with the log in the scratchpad: `bash bench/e14_probe.sh > <scratchpad>/e14_probe.log 2>&1`
Expected on completion: `### E14 DONE`, or a `STOP:` line.

- [ ] **Step 2: Read it**

Run: `python3 bench/e14_read.py --window <E14_START from the log> -`

- **Postponed:** commit the rows as a postponed batch (Step 3 with that wording), wait for the reset, and re-run Step 1 whole.
- **Incomplete after the repeat cap:** record it as incomplete. Do not run more sessions by hand; stitching is forbidden.

- [ ] **Step 3: Commit the rows**

```bash
git add bench/results.jsonl || exit 1
git commit -q -m "bench: E14 stage 1 batch -- <batch status, trigger effect, kind effect>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 4: Record it in `bench/RESULTS.md`**

Add a register row to the table under `## Experiments`, in the same column format as the E13 rows, and an `# E14` section at the end of the file with:

- the reader's full output (the cell table, both effects with bands and Fisher p, and the baseline line);
- the reading from spec section 5 that applies (trigger only / kind only / both / neither), or the batch status if not complete;
- whether Stage 2 is triggered (either effect +4 or more) and which factor it would vary;
- one limits line: 6 runs per cell, one trap, hand-written drafts, thinking not visible.

```bash
git add bench/RESULTS.md || exit 1
git commit -q -m "docs: E14 stage 1 -- <one-line result>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```
