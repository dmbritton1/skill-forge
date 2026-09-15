# E15 Distiller Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run E15. Trap C is distilled under a bench-only variant of `distilling-skills` with three added writing rules, and the variant drafts are probed against E13's skill drafts in one pre-registered batch.

**Architecture:**

- **The variant.** It lives at `bench/variants/E15/`. `run.variant_plugin()` swaps it into a copy of the normal plugin snapshot, and marks the copy so every distill `meta.json` records which rules ran.
- **Distillation.** `distill.py` gains `--plugin-dir` and `--variant`, so the variant's draws archive under their own segment.
- **Tools.** `e15_prep.py` checks delivery and rule compliance and freezes the drafts. `e15_read.py` owns the probe order and the criterion. Two scripts run the distill stages and the probe.
- **No existing file changes** beyond the `run.py`/`distill.py` additions.

**Tech Stack:** Python 3 stdlib (`fractions` for exact thresholds), bash, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md`

## Global Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and `bench/real_path_check.py` are not touched (imports allowed).
- No E13 or E14 file, draft or reader changes (imports allowed).
- `skills/distilling-skills/SKILL.md` changes only under spec section 5's first row, and only in Task 6.
- No absolute home path in committed files.
- Guard every commit with an explicit `|| exit 1`; the Bash tool ignores `set -e`.
- Loop in Python or over bash arrays, never over a bare `$var`.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- No step before Task 6 may launch a real `claude` session. `run.py --check`, `--sandbox-check`, the scripts' `--dry-run` and every `e15_prep.py`/`e15_read.py` command are zero-session and allowed.
- Full suite: `python3 -m pytest -q tests` — 958 passed at plan time; it must stay green after every task.

## Rulings made while planning

1. **Smoke archive name.** The smoke archives under `bench/distilled/C/learn-e15-smoke-nogate/1`, not the spec's `learn-e15-smoke/1`. `--no-novelty-gate` appends `-nogate` to every segment, and the spec's smoke runs with the gate off like the draws. *Cost if wrong:* none.
2. **Distill `meta.json` gains `plugin_commit`.** Spec section 2 assumed the variant mark reaches `meta.json` "through the existing `plugin_commit`", but distill's `meta.json` never recorded it. *Cost if wrong:* none; the new key is additive.
3. **`e15-probe.json` is written even when the probe is not allowed.** It is the committed evidence for an emission result. `--check-frozen` refuses it. *Cost if wrong:* none.
4. **The probe script stops on a void baseline draft, but not on a void variant draft.** A void baseline makes d uncomputable. A void variant draft only drops out of V (spec section 3). *Cost if wrong:* a batch continues with one variant draft fewer.
5. **A postponed distill stage cannot simply be re-run.** `distill.py` refuses to re-roll an archived draw, so the controller first moves `learn-e15-nogate/` aside to `learn-e15-nogate-postponed-<n>/`, commits it as excluded, and then re-runs the stage whole. *Cost if wrong:* none.
6. **The variant test compares against the spec commit.** It uses `git show 2719e97:skills/distilling-skills/SKILL.md`, not the working file. The spec fixes "the commit the spec is written on", and a later ship would otherwise break the test. *Cost if wrong:* none.

## File map

| file | change | responsibility |
| --- | --- | --- |
| `bench/variants/E15/distilling-skills.md` | create | shipped skill + three rule paragraphs |
| `tests/test_bench_e15_variant.py` | create | variant = shipped at `2719e97` + exactly the three paragraphs |
| `bench/run.py` | modify | `variant_plugin()` |
| `bench/distill.py` | modify | `variant` segment, `--plugin-dir`, `--variant`, `plugin_commit` in meta |
| `tests/test_bench_run.py`, `tests/test_bench_distill.py` | modify | new cases |
| `bench/e15_read.py` | create | probe drafts, order, counting, V/B/d, band, `--order`, `--todo` |
| `tests/test_bench_e15_read.py` | create | reader tests |
| `bench/e15_prep.py` | create | counted drafts, delivery, compliance, freeze, `--write`, `--check-frozen` |
| `tests/test_bench_e15_prep.py` | create | prep tests |
| `bench/e15_distill.sh`, `bench/e15_probe.sh` | create | stage scripts with guards |
| `bench/distilled/C/…`, `bench/distilled/C/e15-probe.json`, `bench/results.jsonl`, `bench/RESULTS.md` | modify (Task 6) | data and write-up |

---

### Task 1: The variant file

**Files:**
- Create: `bench/variants/E15/distilling-skills.md`
- Test: `tests/test_bench_e15_variant.py`

**Interfaces:**
- Consumes: `git show 2719e97:skills/distilling-skills/SKILL.md`, the shipped skill at the spec commit.
- Produces: `bench/variants/E15/distilling-skills.md`, used by Task 2's tests and Task 5's distill script.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e15_variant.py`:

```python
"""E15 spec section 1: the variant is the shipped distilling-skills at the spec
commit plus exactly three paragraphs. Run: python3 tests/test_bench_e15_variant.py"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_COMMIT = "2719e97"
VARIANT = ROOT / "bench" / "variants" / "E15" / "distilling-skills.md"

RULE_GENERALIZE = """   **Name nothing a future session may not have.** Do not name tests, test
   files, fixtures or line numbers from this session. The session that uses
   the skill may be writing the code before any test exists, or may never see
   the test that caught the bug. Describe what the check verifies instead
   ("a value with a trailing newline must still parse")."""

RULE_ONE_SHOT = """   **Write the procedure for someone writing the code, not only fixing it.**
   The session that uses this skill may be implementing the function for the
   first time, with no broken version in front of it. Phrase each step as
   what the code must do ("compare the two values after normalising
   whitespace"), not as a search for the old mistake ("find the existing
   check and change it"). Do not start a step with "Find" unless the
   procedure is only ever about code that already exists."""

RULE_TRIGGERS = """   **Name the code, and the moment of writing it.** Put the function, class
   or API the skill is about in the description's first sentence, and make
   `Use when:` cover writing or editing that code, not only the moment it
   fails. A skill whose only trigger is a failure is never used by a session
   that has not failed yet."""

ANCHORS = (
    ('   "would a fresh Claude in a different repo benefit?"\n', RULE_GENERALIZE),
    ("   the procedure worked).\n", RULE_ONE_SHOT),
    ("   triggers fight over-injection; save_skill.py rejects drafts without them.\n", RULE_TRIGGERS),
)


def shipped_at_spec_commit():
    return subprocess.run(["git", "show", SPEC_COMMIT + ":skills/distilling-skills/SKILL.md"],
                          cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


def test_variant_is_shipped_plus_exactly_three_paragraphs():
    expected = shipped_at_spec_commit()
    for anchor, rule in ANCHORS:
        assert expected.count(anchor) == 1, anchor
        expected = expected.replace(anchor, anchor + "\n" + rule + "\n")
    assert VARIANT.read_text(encoding="utf-8") == expected


def test_the_rules_carry_no_trap_c_vocabulary():
    for _, rule in ANCHORS:
        for word in ("verdict", "evidence", "quote", "rewrap", "wrap"):
            assert word not in rule.lower(), (word, rule[:40])


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

Run: `python3 -m pytest -q tests/test_bench_e15_variant.py`
Expected: `test_variant_is_shipped_plus_exactly_three_paragraphs` FAILS with `FileNotFoundError`; `test_the_rules_carry_no_trap_c_vocabulary` passes.

- [ ] **Step 3: Build the variant file from the test's own constants**

```bash
mkdir -p bench/variants/E15 || exit 1
python3 - <<'EOF' || exit 1
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("t", "tests/test_bench_e15_variant.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
text = t.shipped_at_spec_commit()
for anchor, rule in t.ANCHORS:
    text = text.replace(anchor, anchor + "\n" + rule + "\n")
pathlib.Path("bench/variants/E15/distilling-skills.md").write_text(text, encoding="utf-8")
print("wrote", len(text), "chars")
EOF
```

Then read the file and confirm that each rule sits at the end of contract steps 4, 6 and 7, separated from the next step by a blank line.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e15_variant.py`
Expected: 2 passed

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/variants/E15/distilling-skills.md tests/test_bench_e15_variant.py || exit 1
git commit -q -m "bench: E15 variant of distilling-skills -- three writing rules, nothing else changed

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 2: Variant snapshots and variant distills

**Files:**
- Modify: `bench/run.py` (imports; add `variant_plugin` after `sandbox_plugin`)
- Modify: `bench/distill.py` (`_segment`, `archive_dir`, `clone_dest`, `one`, `main`)
- Test: `tests/test_bench_run.py`, `tests/test_bench_distill.py`

**Interfaces:**
- Consumes:
  - `run.SNAPSHOT_MARK`, `run.sandbox_plugin(plugin_dir, explicit)`, `run.plugin_commit(plugin_dir)`, `run.WORK` (existing)
  - the variant file from Task 1
- Produces:
  - `run.variant_plugin(base, variant_file, dest, tag="e15") -> Path` (raises `ValueError`)
  - `distill._segment(distiller, novelty_gate, variant=None) -> str`
  - `distill.archive_dir(trap, distiller, draw, novelty_gate=True, variant=None) -> Path`
  - `distill.clone_dest(task, distiller, draw, novelty_gate=True, variant=None) -> Path`
  - `distill.one(trap, distiller, draw, plugin_dir, task, novelty_gate=True, variant=None)`
  - CLI `distill.py --plugin-dir <snapshot> --variant <name>`
  - `meta.json` key `plugin_commit`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bench_run.py`, above its `if __name__` block:

```python
def _fake_snapshot(root, sha="a" * 40):
    (root / "skills" / "distilling-skills").mkdir(parents=True)
    (root / "skills" / "distilling-skills" / "SKILL.md").write_text("shipped\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "validate.py").write_text("# code\n", encoding="utf-8")
    (root / bench_run.SNAPSHOT_MARK).write_text(sha + "\n", encoding="utf-8")
    return root


def test_variant_plugin_swaps_only_the_distilling_skill_and_marks_the_variant():
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        base = _fake_snapshot(t / "base")
        variant = t / "variant.md"
        variant.write_text("with rules\n", encoding="utf-8")
        got = bench_run.variant_plugin(base, variant, t / "out")
        assert got == t / "out"
        assert (got / "skills" / "distilling-skills" / "SKILL.md").read_text(encoding="utf-8") == "with rules\n"
        assert (got / "scripts" / "validate.py").read_text(encoding="utf-8") == "# code\n"
        h = hashlib.sha256(b"with rules\n").hexdigest()[:12]
        assert (got / bench_run.SNAPSHOT_MARK).read_text(encoding="utf-8") == "a" * 40 + "+e15-" + h + "\n"
        assert bench_run.plugin_commit(got) == "archive:" + "a" * 40 + "+e15-" + h
        assert (base / "skills" / "distilling-skills" / "SKILL.md").read_text(encoding="utf-8") == "shipped\n"


def test_variant_plugin_refuses_a_base_that_is_not_a_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "base").mkdir()
        (t / "v.md").write_text("x\n", encoding="utf-8")
        try:
            bench_run.variant_plugin(t / "base", t / "v.md", t / "out")
        except ValueError:
            return
        raise AssertionError("a non-snapshot base was accepted")


def test_variant_plugin_replaces_an_existing_destination():
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        base = _fake_snapshot(t / "base")
        (t / "v.md").write_text("x\n", encoding="utf-8")
        (t / "out").mkdir()
        (t / "out" / "stale.txt").write_text("old\n", encoding="utf-8")
        got = bench_run.variant_plugin(base, t / "v.md", t / "out")
        assert not (got / "stale.txt").exists()
```

Append to `tests/test_bench_distill.py`, above its `if __name__` block:

```python
def test_a_variant_gets_its_own_archive_and_clone_segment():
    import distill
    assert distill.archive_dir("C", "learn", 2, novelty_gate=False, variant="e15").parts[-3:] == (
        "C", "learn-e15-nogate", "2")
    assert distill.clone_dest({"id": "sf-x"}, "learn", 2, novelty_gate=False,
                              variant="e15").name == "sf-x-distill-learn-e15-nogate-2"
    assert distill.archive_dir("C", "learn", 2, novelty_gate=False).parts[-2] == "learn-nogate"


def test_main_passes_the_plugin_dir_and_variant_to_one():
    import distill
    old = (distill.bench_run.sandbox_plugin, distill.bench_run.SANDBOX, distill.one)
    calls, checked = [], []
    with tempfile.TemporaryDirectory() as tmp:
        snap = pathlib.Path(tmp).resolve()

        def fake_sandbox_plugin(plugin_dir, explicit):
            checked.append((pathlib.Path(plugin_dir), explicit))
            return pathlib.Path(plugin_dir)
        distill.bench_run.sandbox_plugin = fake_sandbox_plugin
        # distill.one is stubbed so this test can never launch a real session.
        distill.one = lambda *a, **kw: calls.append((a, kw))
        try:
            rc = distill.main(["--trap", "C", "--distiller", "learn", "--draws", "1",
                               "--no-novelty-gate", "--plugin-dir", str(snap), "--variant", "e15"])
        finally:
            distill.bench_run.sandbox_plugin, distill.bench_run.SANDBOX, distill.one = old
    assert rc == 0
    assert checked == [(snap, True)]
    (args, kw), = calls
    assert args[3] == snap and kw["variant"] == "e15" and kw["novelty_gate"] is False


def test_main_refuses_a_variant_without_a_plugin_dir():
    import distill
    old = (distill.bench_run.SANDBOX, distill.one)
    calls = []
    distill.one = lambda *a, **kw: calls.append(a)
    try:
        assert distill.main(["--trap", "C", "--distiller", "learn", "--draws", "1",
                             "--variant", "e15"]) == 1
    finally:
        distill.bench_run.SANDBOX, distill.one = old
    assert calls == []
```

Also add one assertion to an existing test that reads an archived `meta.json` after calling `distill.one`. Find the first test in `tests/test_bench_distill.py` that calls `distill.one(...)` and then loads `meta.json` with `json.loads`. Right after the load, add:

```python
    assert "plugin_commit" in meta
```

Use whatever name that test gives the loaded dict. If no existing test loads `meta.json` after `distill.one`, report NEEDS_CONTEXT instead of writing a new session-driving test.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest -q tests/test_bench_run.py -k variant_plugin tests/test_bench_distill.py -k "variant or plugin_dir or plugin_commit"`
Expected: FAIL with `AttributeError: module 'run' has no attribute 'variant_plugin'`, a `TypeError` on the unexpected `variant` keyword, and a failure on the missing `plugin_commit`.

- [ ] **Step 3: Implement `run.variant_plugin`**

In `bench/run.py`, add `import hashlib` to the stdlib imports. Add this directly after `sandbox_plugin`:

```python
def variant_plugin(base, variant_file, dest, tag="e15"):
    """A copy of snapshot `base` whose skills/distilling-skills/SKILL.md is
    `variant_file` (E15 spec section 2).

    Marked `<sha>+<tag>-<first 12 hex of the variant's sha256>`, so
    plugin_commit() -- and through it every distill meta.json -- records which
    rules ran. The base snapshot is never modified.
    """
    base, dest = Path(base), Path(dest)
    mark = base / SNAPSHOT_MARK
    if not mark.is_file():
        raise ValueError("variant base is not a run.snapshot_plugin() snapshot: %s" % base)
    variant = Path(variant_file).read_bytes()
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.copytree(str(base), str(dest))
    target = dest / "skills" / "distilling-skills" / "SKILL.md"
    if not target.is_file():
        raise ValueError("snapshot has no skills/distilling-skills/SKILL.md: %s" % base)
    target.write_bytes(variant)
    sha = mark.read_text(encoding="utf-8").strip().split("+")[0]
    (dest / SNAPSHOT_MARK).write_text(
        "%s+%s-%s\n" % (sha, tag, hashlib.sha256(variant).hexdigest()[:12]), encoding="utf-8")
    return dest
```

- [ ] **Step 4: Implement the `distill.py` changes**

Replace `_segment`, `archive_dir` and `clone_dest` with:

```python
def _segment(distiller, novelty_gate, variant=None):
    """`learn`, `learn-nogate`, or with a variant `learn-e15-nogate` -- never two
    arms under one path.

    Q1's 12 draws are archived and committed under the plain segment, and E7
    re-runs two of its cells. Sharing a path would either overwrite that
    record or trip the archive guard and lose the draw. E5 lost a whole batch
    to two arms sharing a clone path; the suffix is derived here, once, rather
    than passed in by each caller. E15's variant draws get their own segment
    for the same reason.
    """
    seg = distiller + ("-" + variant if variant else "")
    return seg if novelty_gate else seg + "-nogate"


def archive_dir(trap, distiller, draw, novelty_gate=True, variant=None):
    return ARCHIVE / trap / _segment(distiller, novelty_gate, variant) / str(draw)


def clone_dest(task, distiller, draw, novelty_gate=True, variant=None):
    return bench_run.WORK / ("%s-distill-%s-%d"
                             % (task["id"], _segment(distiller, novelty_gate, variant),
                                draw))
```

In `one()`:

- change the signature to `def one(trap, distiller, draw, plugin_dir, task, novelty_gate=True, variant=None):`
- change `dest = clone_dest(task, distiller, draw, novelty_gate)` to `dest = clone_dest(task, distiller, draw, novelty_gate, variant)`
- change `d = archive_dir(trap, distiller, draw, novelty_gate)` to `d = archive_dir(trap, distiller, draw, novelty_gate, variant)`
- in the `meta.json` dict, directly after `"novelty_gate": novelty_gate,`, add:

```python
            # E15: which plugin -- and so which distilling rules -- this draw ran
            # under. A variant snapshot's mark carries `+e15-<hash>`.
            "variant": variant,
            "plugin_commit": bench_run.plugin_commit(plugin_dir),
```

In `main()`, add two arguments after `--no-sandbox`:

```python
    ap.add_argument("--plugin-dir", default=None,
                    help="E15: distil against this run.snapshot_plugin() snapshot (for"
                         " example a run.variant_plugin() copy) instead of HEAD")
    ap.add_argument("--variant", default=None,
                    help="E15: archive and clone under <distiller>-<variant>[-nogate];"
                         " requires --plugin-dir")
```

Replace the block from `bench_run.SANDBOX = not args.no_sandbox` down to just before `bench_run.WORK.mkdir(...)` with:

```python
    if args.variant and not args.plugin_dir:
        # A variant name without its rules would label HEAD's draws as the variant's.
        print("--variant requires --plugin-dir")
        return 1
    if args.plugin_dir:
        plugin_dir = Path(args.plugin_dir).resolve()
    bench_run.SANDBOX = not args.no_sandbox
    if bench_run.SANDBOX or args.plugin_dir:
        try:
            plugin_dir = bench_run.sandbox_plugin(plugin_dir, explicit=bool(args.plugin_dir))
        except ValueError as err:
            print("sandbox: %s" % err)
            return 1
```

In the draw loop, change the `one(...)` call to pass the variant:

```python
                    one(trap, distiller, draw, plugin_dir, by_id[TRAPS[trap]],
                        novelty_gate=not args.no_novelty_gate, variant=args.variant)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_run.py tests/test_bench_distill.py`
Expected: all pass, including the 6 new tests and the added assertion.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add bench/run.py bench/distill.py tests/test_bench_run.py tests/test_bench_distill.py || exit 1
git commit -q -m "bench: variant plugin snapshots and variant distills; distill meta records plugin_commit

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 3: The reader, `bench/e15_read.py`

**Files:**
- Create: `bench/e15_read.py`
- Test: `tests/test_bench_e15_read.py`

**Interfaces:**
- Consumes:
  - `audit.counts(row)`
  - `e12_read.select(rows, windows)`
  - `e13_outcome_read.fisher_two_sided(a, b, c, d)`
- Produces:
  - constants `TASK = "sf-author-verdict-from"`, `N_DRAFT = 3`, `N_CONTROL = 3`, `ROUNDS = 3`, `RECORD` (path of `bench/distilled/C/e15-probe.json`)
  - `probe_drafts(record) -> list[{"group", "path", "name"}]`
  - `order(drafts) -> list[str]`
  - `draft_of(row, drafts) -> dict | None`
  - `band(d: Fraction, v: Fraction) -> str`
  - `read_batch(rows, drafts) -> dict`
  - `todo(res, drafts) -> list[str]`
  - CLI `--order`, `--window FROM TO [--todo]`, `--record PATH`
  - output: first line `batch: <postponed|void|incomplete|complete>...`, then one line per draft starting `  variant ` or `  baseline ` and ending with its status

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e15_read.py`:

```python
"""Tests for bench/e15_read.py. Run: python3 tests/test_bench_e15_read.py"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from fractions import Fraction

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
import e15_read as er

TASK = er.TASK
V = [{"group": "variant", "path": "bench/distilled/C/learn-e15-nogate/%d/SKILL.md" % i, "name": "v%d" % i}
     for i in (1, 2, 3, 4)]
B = [{"group": "baseline", "path": "bench/distilled/C/learn-nogate/%d/SKILL.md" % i, "name": "b%d" % i}
     for i in (1, 2, 3)]
DRAFTS = V + B


def ctl(resolved=False, ok=True, tail=None, audit="clean"):
    return {"task": TASK, "arm": "control", "resolved": resolved, "session_ok": ok,
            "session_tail": tail, "skill_path": None, "injections": [],
            "sandbox": True, "audit": {"verdict": audit}}


def trt(d, resolved=False, delivered=True, ok=True, audit="clean"):
    return {"task": TASK, "arm": "treatment", "resolved": resolved, "session_ok": ok,
            "session_tail": None, "skill_path": "~/x/wt/" + d["path"],
            "injections": [{"skill": d["name"] if delivered else "other"}],
            "sandbox": True, "audit": {"verdict": audit}}


def full(resolved):
    """Three valid runs per draft; `resolved` maps draft name to its count."""
    rows = []
    for d in DRAFTS:
        rows += [trt(d, resolved=i < resolved.get(d["name"], 0)) for i in range(3)]
    return rows


def test_order_interleaves_rotates_and_opens_each_round_with_a_control():
    o = er.order(DRAFTS)
    p = lambda d: d["path"]
    assert o[:8] == ["control", p(V[0]), p(B[0]), p(V[1]), p(B[1]), p(V[2]), p(B[2]), p(V[3])]
    assert o[8:16] == ["control", p(B[0]), p(V[1]), p(B[1]), p(V[2]), p(B[2]), p(V[3]), p(V[0])]
    assert o[16] == "control" and len(o) == 24
    assert o.count("control") == 3 and all(o.count(p(d)) == 3 for d in DRAFTS)


def test_probe_drafts_keeps_delivered_rows_variants_first():
    record = {"drafts": [
        {"group": "baseline", "path": "b1", "name": "b1", "delivered": True},
        {"group": "variant", "path": "v1", "name": "v1", "delivered": True},
        {"group": "variant", "path": "v2", "name": "v2", "delivered": False}]}
    assert [d["path"] for d in er.probe_drafts(record)] == ["v1", "b1"]


def test_draft_of_does_not_confuse_the_baseline_and_variant_segments():
    assert er.draft_of(trt(V[0]), DRAFTS) is V[0]
    assert er.draft_of(trt(B[0]), DRAFTS) is B[0]
    assert er.draft_of(ctl(), DRAFTS) is None


def test_bands():
    for d, v, reading in ((Fraction(2, 5), Fraction(1, 2), "the rules help"),
                          (Fraction(2, 5), Fraction(4, 9), "ambiguous"),
                          (Fraction(3, 20), Fraction(1, 2), "no large effect"),
                          (Fraction(-3, 20), Fraction(0), "no large effect"),
                          (Fraction(1, 5), Fraction(1, 2), "ambiguous"),
                          (Fraction(-39, 100), Fraction(0), "ambiguous"),
                          (Fraction(-2, 5), Fraction(0), "the rules hurt")):
        assert er.band(d, v) == reading, (d, v, reading)


def test_a_complete_batch_computes_v_b_and_d():
    res = er.read_batch([ctl()] * 3 + full({"v1": 3, "v2": 3, "v3": 2, "v4": 1, "b1": 1}), DRAFTS)
    m = res["measures"]
    assert res["batch"] == "complete"
    assert m["V"] == [9, 12] and m["B"] == [1, 9]
    assert m["d"] == 0.64 and m["reading"] == "the rules help"
    assert 0.0 <= m["p"] <= 1.0 and m["baseline_moved"] is False


def test_a_baseline_of_five_of_nine_is_flagged_as_moved():
    res = er.read_batch([ctl()] * 3 + full({"b1": 2, "b2": 2, "b3": 1}), DRAFTS)
    assert res["measures"]["baseline_moved"] is True


def test_a_resolved_valid_control_voids_the_batch():
    res = er.read_batch([ctl(resolved=True), ctl(), ctl()] + full({}), DRAFTS)
    assert res["batch"] == "void" and res["measures"] is None


def test_a_session_limit_postpones_the_batch():
    rows = [ctl()] * 3 + full({}) + [dict(ctl(ok=False), session_tail="You've hit your session limit")]
    assert er.read_batch(rows, DRAFTS)["batch"] == "postponed"


def test_invalid_and_undelivered_rows_do_not_count():
    rows = [ctl()] * 3 + full({}) + [trt(V[0], resolved=True, audit="leak"),
                                    trt(V[0], resolved=True, ok=False),
                                    trt(V[0], resolved=True, delivered=False)]
    c = er.read_batch(rows, DRAFTS)["drafts"][V[0]["path"]]
    assert c["valid"] == 3 and c["resolved"] == 0 and c["invalid"] == 2 and c["undelivered"] == 1


def test_a_void_variant_draft_drops_out_of_v():
    rows = [ctl()] * 3 + full({"v1": 3}) + [trt(V[0], delivered=False)] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["drafts"][V[0]["path"]]["status"] == "void"
    assert res["batch"] == "complete" and res["measures"]["V"] == [0, 9]


def test_a_void_baseline_draft_means_d_is_not_computed():
    rows = [ctl()] * 3 + full({}) + [trt(B[1], delivered=False)] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["batch"] == "complete" and res["measures"] is None and "baseline" in res["reason"]


def test_each_draft_counts_only_its_first_three_valid_runs():
    rows = [ctl()] * 3 + full({}) + [trt(V[1], resolved=True)]
    assert er.read_batch(rows, DRAFTS)["drafts"][V[1]["path"]]["resolved"] == 0


def test_missing_runs_leave_the_batch_incomplete_and_todo_names_them():
    rows = [ctl()] * 2 + [r for r in full({}) if er.draft_of(r, DRAFTS) is not B[2]] + [trt(B[2])] * 2
    res = er.read_batch(rows, DRAFTS)
    assert res["batch"] == "incomplete" and res["measures"] is None
    assert er.todo(res, DRAFTS) == ["control", B[2]["path"]]


def test_cli_order_and_window_requirement():
    with tempfile.TemporaryDirectory() as tmp:
        record = pathlib.Path(tmp) / "e15-probe.json"
        record.write_text(json.dumps({"drafts": [dict(d, delivered=True) for d in DRAFTS]}),
                          encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert er.main(["--order", "--record", str(record)]) == 0
        assert buf.getvalue().splitlines() == er.order(DRAFTS)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                er.main(["--record", str(record)])
        except SystemExit as exit_:
            assert exit_.code != 0
        else:
            raise AssertionError("--window was not required")


def test_cli_first_line_and_draft_lines():
    with tempfile.TemporaryDirectory() as tmp:
        record = pathlib.Path(tmp) / "e15-probe.json"
        record.write_text(json.dumps({"drafts": [dict(d, delivered=True) for d in DRAFTS]}),
                          encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            er.main(["--window", "2999-01-01T00:00:00", "-", "--record", str(record)])
        lines = buf.getvalue().splitlines()
        assert lines[0].startswith("batch: incomplete")
        assert sum(1 for l in lines if l.startswith("  variant ")) == 4
        assert sum(1 for l in lines if l.startswith("  baseline ")) == 3


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

Run: `python3 -m pytest -q tests/test_bench_e15_read.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'e15_read'`

- [ ] **Step 3: Implement `bench/e15_read.py`**

```python
#!/usr/bin/env python3
"""Read the E15 probe batch (spec sections 3-5).

docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md

Variant drafts (distilled under bench/variants/E15/distilling-skills.md) and
E13's three skill drafts (the baseline), each installed alone, 3 runs each,
plus a same-batch control of 3, in three interleaved rounds.

A row refused at the session limit postpones the batch. A valid control that
resolves voids it. A row audit.counts() rejects, a failed session, or a draft
row that did not inject its draft does not count; a second undelivered row
voids that draft. A void variant draft drops out of V; a void baseline draft
means d is not computed. Each draft counts its first 3 valid runs.

V and B are pooled resolved/valid; d = V - B. d >= +0.40 with V >= 0.50: the
rules help. |d| <= 0.15: no large effect. d <= -0.40: the rules hurt.
Otherwise ambiguous. Fisher's p is reported, never a threshold. Run:

    python3 bench/e15_read.py --order
    python3 bench/e15_read.py --window <E15_START> -
    python3 bench/e15_read.py --window <E15_START> - --todo
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit import counts  # noqa: E402
from e12_read import select  # noqa: E402
from e13_outcome_read import fisher_two_sided  # noqa: E402

TASK = "sf-author-verdict-from"
N_DRAFT = 3
N_CONTROL = 3
ROUNDS = 3
LIMIT_MARK = "session limit"
RECORD = ROOT / "distilled" / "C" / "e15-probe.json"


def probe_drafts(record):
    """The drafts the probe runs: delivered variant drafts in record order, then the baseline."""
    rows = [r for r in record["drafts"] if r["delivered"]]
    pick = lambda group: [{"group": group, "path": r["path"], "name": r["name"]}
                          for r in rows if r["group"] == group]
    return pick("variant") + pick("baseline")


def order(drafts):
    """Spec section 3: v1, b1, v2, b2, v3, b3, remaining variants; rotated left
    by the round number; each round opens with a control run."""
    v = [d["path"] for d in drafts if d["group"] == "variant"]
    b = [d["path"] for d in drafts if d["group"] == "baseline"]
    mixed = []
    for i in range(max(len(v), len(b))):
        mixed += v[i:i + 1] + b[i:i + 1]
    out = []
    for r in range(ROUNDS):
        k = r % len(mixed)
        out += ["control"] + mixed[k:] + mixed[:k]
    return out


def draft_of(row, drafts):
    path = row.get("skill_path") or ""
    return next((d for d in drafts if path.endswith(d["path"])), None)


def band(d, v):
    if d >= Fraction(2, 5) and v >= Fraction(1, 2):
        return "the rules help"
    if abs(d) <= Fraction(3, 20):
        return "no large effect"
    if d <= -Fraction(2, 5):
        return "the rules hurt"
    return "ambiguous"


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def read_batch(rows, drafts):
    mine = [r for r in rows if r.get("task") == TASK]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "reason": "a session hit the session limit: re-run the whole batch",
                "control": None, "drafts": {}, "measures": None}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if _valid(r)]
    out = {"control": {"valid": min(len(ok), N_CONTROL), "needed": N_CONTROL,
                       # Every VALID control run: one valid resolution voids the
                       # batch. An invalid row never counts, so its resolution does not.
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "invalid": len(control) - len(ok)},
           "drafts": {}, "measures": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 3)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    for d in drafts:
        trt = [r for r in mine if r.get("arm") == "treatment" and draft_of(r, drafts) is d]
        valid = [r for r in trt if _valid(r)]
        hit = [r for r in valid if d["name"] in {i.get("skill") for i in r.get("injections") or []}]
        counted = hit[:N_DRAFT]
        cell = {"group": d["group"], "valid": len(counted), "needed": N_DRAFT,
                "resolved": sum(1 for r in counted if r.get("resolved")),
                "undelivered": len(valid) - len(hit), "invalid": len(trt) - len(valid)}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_DRAFT else "incomplete")
        complete = complete and cell["status"] != "incomplete"
        out["drafts"][d["path"]] = cell
    if not complete:
        out.update(batch="incomplete", reason="the control or a draft is not fully measured")
        return out
    cells = list(out["drafts"].values())
    if any(c["group"] == "baseline" and c["status"] == "void" for c in cells):
        out.update(batch="complete", reason="a baseline draft is void: d is not computed")
        return out
    live = [c for c in cells if c["group"] == "variant" and c["status"] != "void"]
    if not live:
        out.update(batch="complete", reason="every variant draft is void: d is not computed")
        return out
    vr, vv = sum(c["resolved"] for c in live), sum(c["valid"] for c in live)
    base = [c for c in cells if c["group"] == "baseline"]
    br, bv = sum(c["resolved"] for c in base), sum(c["valid"] for c in base)
    d = Fraction(vr, vv) - Fraction(br, bv)
    out["measures"] = {"V": [vr, vv], "B": [br, bv], "d": round(float(d), 2),
                       "reading": band(d, Fraction(vr, vv)),
                       "p": fisher_two_sided(vr, vv - vr, br, bv - br),
                       "baseline_moved": br >= 5}
    out.update(batch="complete", reason="")
    return out


def todo(res, drafts):
    """One entry per run still needed, for bench/e15_probe.sh's repeat loop."""
    if res["batch"] != "incomplete":
        return []
    need = ["control"] * (N_CONTROL - res["control"]["valid"])
    for d in drafts:
        cell = res["drafts"][d["path"]]
        if cell["status"] == "incomplete":
            need += [d["path"]] * (N_DRAFT - cell["valid"])
    return need


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", nargs=2, action="append", metavar=("FROM", "TO"))
    ap.add_argument("--todo", action="store_true", help="print only the runs still needed")
    ap.add_argument("--order", action="store_true", help="print the pre-registered run order")
    ap.add_argument("--record", default=str(RECORD), help="e15-probe.json (tests pass a copy)")
    args = ap.parse_args(argv)
    drafts = probe_drafts(json.loads(Path(args.record).read_text(encoding="utf-8")))
    if args.order:
        for arm in order(drafts):
            print(arm)
        return 0
    if not args.window:
        ap.error("--window is required unless --order")
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_batch(select(rows, args.window), drafts)
    if args.todo:
        for arm in todo(res, drafts):
            print(arm)
        return 0
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control  valid %d/%d  resolved %d  invalid %d"
              % (c["valid"], c["needed"], c["resolved"], c["invalid"]))
    for path, c in res["drafts"].items():
        print("  %-8s %-34s valid %d/%d  resolved %d  undelivered %d  invalid %d  %s"
              % (c["group"], path.replace("bench/distilled/C/", ""), c["valid"], c["needed"],
                 c["resolved"], c["undelivered"], c["invalid"], c["status"]))
    m = res["measures"]
    if m:
        print("V %d/%d  B %d/%d  d = %+.2f -- %s (Fisher p = %.3f)"
              % (m["V"][0], m["V"][1], m["B"][0], m["B"][1], m["d"], m["reading"], m["p"]))
        if m["baseline_moved"]:
            print("baseline: B %d/%d -- MOVED (E13 measured 1/9)" % (m["B"][0], m["B"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e15_read.py`
Expected: 15 passed

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bench/e15_read.py tests/test_bench_e15_read.py || exit 1
git commit -q -m "bench: E15 reader -- probe order, counting rules, V/B/d and bands

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 4: Delivery, compliance and freeze, `bench/e15_prep.py`

**Files:**
- Create: `bench/e15_prep.py`
- Test: `tests/test_bench_e15_prep.py`

**Interfaces:**
- Consumes:
  - `e15_read.TASK`, `e15_read.RECORD` (Task 3)
  - `e14_deliver.sha256(path)`, `e14_deliver.drifted(commit, root)`
  - `e13_qualify._install(paths, home, project)`, `e13_qualify._sandbox(work, tag)`
  - `real_path_check.delivered(...)`, `real_path_check.export_scripts(ref, into)`
  - `save_skill.parse_frontmatter(text)`
  - `libguard.snapshot()`
- Produces:
  - `VARIANT_SEG` (Path of `bench/distilled/C/learn-e15-nogate`), `BASELINE` (the three repo-relative baseline paths)
  - `counted_variant_drafts(seg) -> list[Path]`
  - `compliance(text) -> {"names_test": bool, "find_step": bool, "fn_first": bool}`
  - `allowed(rows) -> bool`
  - `stale(record, root) -> list[str]`
  - CLI `--write` and `--check-frozen`
  - `e15-probe.json`: `{"task", "commit", "drafts": [{group, path, name, sha256, delivered, compliance}], "probe_allowed", "library_untouched"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_e15_prep.py`:

```python
"""Tests for bench/e15_prep.py. Run from the repo root: python3 tests/test_bench_e15_prep.py"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import e15_prep as ep

DRAFT = """---
name: x
kind: skill
description: >
  %s
  Use when: %s.
  Do NOT use when: never.
---

## Procedure
%s
"""


def test_compliance_flags_each_rule_independently():
    clean = DRAFT % ("A gate such as validate.verdict_from rejects quotes.", "writing it",
                     "1. Compare both sides after collapsing whitespace.")
    assert ep.compliance(clean) == {"names_test": False, "find_step": False, "fn_first": True}
    assert ep.compliance(clean + "\nSee test_a_thing.\n")["names_test"] is True
    assert ep.compliance(clean + "\nRun tests/test_validate.py.\n")["names_test"] is True
    found = DRAFT % ("A gate such as validate.verdict_from rejects quotes.", "x",
                     "1. **Find** the substring check.")
    assert ep.compliance(found)["find_step"] is True
    late = DRAFT % ("A strict quote gate rejects re-wrapped quotes.", "editing validate.verdict_from",
                    "1. Collapse whitespace.")
    assert ep.compliance(late)["fn_first"] is False


def test_compliance_of_the_first_e13_baseline_draft_is_as_the_e14_write_up_describes():
    text = (ROOT / ep.BASELINE[0]).read_text(encoding="utf-8")
    assert ep.compliance(text) == {"names_test": True, "find_step": True, "fn_first": False}


def test_counted_variant_drafts_keep_saved_untainted_drafts_in_draw_order():
    with tempfile.TemporaryDirectory() as tmp:
        seg = pathlib.Path(tmp)

        def draw(n, outcome="saved", draft=True, tainted=False):
            d = seg / str(n)
            d.mkdir()
            (d / "meta.json").write_text(json.dumps({"outcome": outcome, "tainted": tainted}),
                                         encoding="utf-8")
            if draft:
                (d / "SKILL.md").write_text("x\n", encoding="utf-8")
        draw(10)
        draw(2)
        draw(3, tainted=True)
        draw(4, outcome="aborted", draft=False)
        draw(5, draft=False)
        assert [p.parent.name for p in ep.counted_variant_drafts(seg)] == ["2", "10"]


def test_allowed_needs_three_delivered_variants_and_all_three_baselines():
    v = lambda d: {"group": "variant", "delivered": d}
    b = lambda d: {"group": "baseline", "delivered": d}
    assert ep.allowed([v(True)] * 3 + [b(True)] * 3) is True
    assert ep.allowed([v(True)] * 2 + [v(False)] * 4 + [b(True)] * 3) is False
    assert ep.allowed([v(True)] * 6 + [b(True)] * 2 + [b(False)]) is False


def test_stale_names_changed_or_missing_drafts_by_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "a.md").write_text("one\n", encoding="utf-8")
        record = {"drafts": [{"path": "a.md", "sha256": ep.sha256(root / "a.md")},
                             {"path": "gone.md", "sha256": "0" * 64}]}
        assert ep.stale(record, root) == ["gone.md"]
        (root / "a.md").write_text("two\n", encoding="utf-8")
        assert ep.stale(record, root) == ["a.md", "gone.md"]


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

Run: `python3 -m pytest -q tests/test_bench_e15_prep.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'e15_prep'`

- [ ] **Step 3: Implement `bench/e15_prep.py`**

```python
#!/usr/bin/env python3
"""E15 stage C (spec section 3): delivery, rule compliance and freeze. Zero sessions.

docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md

Installs each counted variant draft (bench/distilled/C/learn-e15-nogate) and
each of E13's three skill drafts ALONE through the real save_skill.py into a
sandboxed HOME, runs HEAD's prompt hook on trap C's author prompt, records
delivery and the three descriptive rule-compliance flags, and freezes the
drafts' sha256 in bench/distilled/C/e15-probe.json. The probe is allowed only
if at least 3 variant drafts and all 3 baseline drafts are delivered; the
record is written either way (plan ruling 3). Run from the repo root:

    python3 bench/e15_prep.py --write          # check and record
    python3 bench/e15_prep.py --check-frozen   # probe guard
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bench")]
import libguard                                                   # noqa: E402
import save_skill                                                 # noqa: E402
from e13_qualify import _install, _sandbox                         # noqa: E402
from e14_deliver import drifted, sha256                            # noqa: E402
from e15_read import RECORD, TASK                                  # noqa: E402
from real_path_check import delivered, export_scripts              # noqa: E402

VARIANT_SEG = ROOT / "bench" / "distilled" / "C" / "learn-e15-nogate"
BASELINE = tuple("bench/distilled/C/learn-nogate/%d/SKILL.md" % d for d in (1, 2, 3))
MIN_VARIANT = 3


def counted_variant_drafts(seg):
    """Spec section 3 stage B: saved, draft present, not tainted -- in draw order."""
    out = []
    for meta in sorted(pathlib.Path(seg).glob("*/meta.json"), key=lambda p: int(p.parent.name)):
        m = json.loads(meta.read_text(encoding="utf-8"))
        draft = meta.parent / "SKILL.md"
        if m.get("outcome") == "saved" and draft.is_file() and not m.get("tainted"):
            out.append(draft)
    return out


def compliance(text):
    """Spec section 3 stage C: descriptive only, never a gate."""
    fm, body = save_skill.parse_frontmatter(text)
    desc = " ".join(str((fm or {}).get("description") or "").split())
    first = desc.split(". ", 1)[0]
    return {"names_test": bool(re.search(r"\btest_\w+|\btests/", text)),
            "find_step": bool(re.search(r"^\s*\d+\.\s+(\*\*)?Find\b", body or "", re.M)),
            "fn_first": "verdict_from" in first}


def allowed(rows):
    variants = [r for r in rows if r["group"] == "variant" and r["delivered"]]
    baseline = [r for r in rows if r["group"] == "baseline"]
    return (len(variants) >= MIN_VARIANT and len(baseline) == len(BASELINE)
            and all(r["delivered"] for r in baseline))


def stale(record, root):
    """Paths whose draft is missing or changed since `record` was written."""
    return [r["path"] for r in record["drafts"]
            if not (pathlib.Path(root) / r["path"]).is_file()
            or sha256(pathlib.Path(root) / r["path"]) != r["sha256"]]


def check_frozen():
    if not RECORD.is_file():
        print("FATAL: %s missing -- run bench/e15_prep.py --write" % RECORD.relative_to(ROOT))
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if not record.get("probe_allowed"):
        print("FATAL: e15-probe.json does not allow the probe (emission, or a baseline draft undelivered)")
        return 1
    changed = stale(record, ROOT)
    if changed:
        print("FATAL: draft(s) changed since e15-probe.json: %s" % ", ".join(changed))
        return 1
    if drifted(record["commit"], ROOT):
        print("FATAL: scripts/ or hooks/ changed since the delivery check ran at %s" % record["commit"][:7])
        return 1
    print("drafts frozen: %d probe drafts, none changed"
          % sum(1 for r in record["drafts"] if r["delivered"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write bench/distilled/C/e15-probe.json")
    ap.add_argument("--check-frozen", action="store_true", help="exit 1 unless the probe may run")
    args = ap.parse_args(argv)
    if args.check_frozen:
        return check_frozen()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "hooks"],
                           cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if dirty:
        print("FATAL: uncommitted changes under scripts/ or hooks/")
        return 1
    cfg = json.loads((ROOT / "bench" / "tasks.json").read_text(encoding="utf-8"))
    prompt = next(t for t in cfg["tasks"] if t["id"] == TASK)["prompt"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()
    drafts = ([("variant", p) for p in counted_variant_drafts(VARIANT_SEG)]
              + [("baseline", ROOT / p) for p in BASELINE])

    before = libguard.snapshot()
    work = os.path.realpath(tempfile.mkdtemp(prefix="e15-prep-"))
    rows, problems = [], []
    try:
        scripts = export_scripts("HEAD", os.path.join(work, "head"))
        for i, (group, path) in enumerate(drafts):
            text = path.read_text(encoding="utf-8")
            name = (save_skill.parse_frontmatter(text)[0] or {}).get("name")
            home, project = _sandbox(work, "d%d" % i)
            problems += _install([path], home, project)
            got, err = delivered(scripts, prompt, "e15-prep-%d" % i, project, home)
            if err:
                problems.append("%s hook stderr: %s" % (path.name, err[-200:]))
            rows.append({"group": group, "path": str(path.relative_to(ROOT)), "name": name,
                         "sha256": sha256(path), "delivered": name in got,
                         "compliance": compliance(text)})
    finally:
        shutil.rmtree(work, ignore_errors=True)

    untouched = libguard.snapshot() == before
    for r in rows:
        c = r["compliance"]
        print("%-8s %-44s delivered %-5s names_test %-5s find_step %-5s fn_first %s"
              % (r["group"], r["path"].replace("bench/distilled/C/", ""), r["delivered"],
                 c["names_test"], c["find_step"], c["fn_first"]))
    print("operator's library untouched: %s" % untouched)
    for p in problems:
        print("PROBLEM: " + p)
    probe_ok = allowed(rows)
    print("probe allowed: %s" % probe_ok)
    if untouched and not problems:
        if args.write:
            RECORD.write_text(json.dumps({"task": TASK, "commit": commit, "drafts": rows,
                                          "probe_allowed": probe_ok, "library_untouched": untouched},
                                         indent=2) + "\n", encoding="utf-8")
            print("wrote %s" % RECORD.relative_to(ROOT))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest -q tests/test_bench_e15_prep.py`
Expected: 5 passed

Run: `python3 -m pytest -q tests`
Expected: all pass.

Run: `python3 bench/e15_prep.py`, without `--write`.
Expected:
- no variant draw exists yet, so only the three baseline rows print, each `delivered True` with `names_test True`;
- `probe allowed: False`;
- `operator's library untouched: True`;
- exit 0.

This is zero sessions, and nothing is written.

- [ ] **Step 5: Commit**

```bash
git add bench/e15_prep.py tests/test_bench_e15_prep.py || exit 1
git commit -q -m "bench: E15 prep -- delivery, rule compliance and freeze for variant and baseline drafts

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 5: Stage scripts, `bench/e15_distill.sh` and `bench/e15_probe.sh`

**Files:**
- Create: `bench/e15_distill.sh`, `bench/e15_probe.sh`

**Interfaces:**
- Consumes:
  - `run.sandbox_plugin`, `run.variant_plugin`, `run.REPO_ROOT` (Task 2)
  - `distill.py --plugin-dir --variant --no-novelty-gate` (Task 2)
  - `e15_prep.py --check-frozen` (Task 4)
  - `e15_read.py --order`, `--window FROM -`, `--todo` (Task 3)
- Produces:
  - `bash bench/e15_distill.sh --stage smoke|draws [--dry-run]`
  - `bash bench/e15_probe.sh [--dry-run]`, which prints `E15_START <ts>`

- [ ] **Step 1: Write `bench/e15_distill.sh`**

```bash
#!/usr/bin/env bash
# E15 stages A (smoke) and B (draws). Pre-registered:
# docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md, section 3.
#
# Builds a HEAD plugin snapshot with bench/variants/E15/distilling-skills.md
# swapped in, then distils trap C's repair task under it with the novelty gate
# off. Stage smoke: 1 draw under learn-e15-smoke-nogate, checked. Stage draws:
# 6 draws under learn-e15-nogate. A session refused at the session limit
# postpones the stage (plan ruling 5).
#
# Usage: bash bench/e15_distill.sh --stage smoke|draws [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
STAGE=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --stage) STAGE="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 1 ;;
  esac
done
case "$STAGE" in
  smoke) SEG="learn-e15-smoke-nogate"; VARIANT="e15-smoke"; DRAWS=1 ;;
  draws) SEG="learn-e15-nogate"; VARIANT="e15"; DRAWS=6 ;;
  *) echo "usage: bash bench/e15_distill.sh --stage smoke|draws [--dry-run]"; exit 1 ;;
esac

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin bench/variants)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test or the variant"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
if [ -e "bench/distilled/C/$SEG" ]; then
  echo "FATAL: bench/distilled/C/$SEG already exists -- a stage is never re-rolled over its archive (plan ruling 5)"; exit 1
fi

SNAP="$(python3 -c "
import sys; sys.path.insert(0, 'bench'); import run
base = run.sandbox_plugin(run.REPO_ROOT, explicit=False)
print(run.variant_plugin(base, 'bench/variants/E15/distilling-skills.md', str(base) + '-e15', 'e15'))
")" || { echo "FATAL: could not build the variant snapshot"; exit 1; }
echo "variant snapshot: $SNAP"
echo "mark: $(cat "$SNAP/.bench-plugin-ref")"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed and the variant snapshot is built; a real run probes the allowance, then $DRAWS distill session(s) under $SEG"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

python3 bench/distill.py --trap C --distiller learn --draws "$DRAWS" --no-novelty-gate \
  --plugin-dir "$SNAP" --variant "$VARIANT" || echo "distill.py exited non-zero"

python3 - "$SEG" <<'PY' || { echo "STOP: session limit during stage $STAGE -- see plan ruling 5 before re-running"; exit 1; }
import glob, json, sys
hit = [p for p in sorted(glob.glob("bench/distilled/C/%s/*/meta.json" % sys.argv[1]))
       if "session limit" in (json.load(open(p)).get("session_tail") or "")]
for p in hit:
    print("session limit: " + p)
sys.exit(1 if hit else 0)
PY

if [ "$STAGE" = "smoke" ]; then
  python3 - <<'PY' || { echo "FATAL: smoke failed -- fix before stage draws"; exit 1; }
import json, sys
m = json.load(open("bench/distilled/C/learn-e15-smoke-nogate/1/meta.json"))
problems = []
if m.get("outcome") != "saved":
    problems.append("outcome %r" % m.get("outcome"))
if m.get("sandbox") is not True:
    problems.append("not sandboxed")
if (m.get("audit") or {}).get("verdict") != "clean":
    problems.append("audit %r" % (m.get("audit") or {}).get("verdict"))
if "+e15-" not in (m.get("plugin_commit") or ""):
    problems.append("plugin_commit %r" % m.get("plugin_commit"))
print("smoke: " + ("PASS" if not problems else "FAIL -- " + "; ".join(problems)))
sys.exit(1 if problems else 0)
PY
fi
echo "### E15 STAGE $STAGE DONE"
```

- [ ] **Step 2: Write `bench/e15_probe.sh`**

```bash
#!/usr/bin/env bash
# E15 stage D probe. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md, section 3.
#
# Control x3, each delivered variant draft x3, E13's three skill drafts x3, in
# three interleaved rounds (bench/e15_read.py --order). Repeats follow round 3,
# at most 8. The script stops on a postponed or void batch, on a void baseline
# draft (plan ruling 4), and on any reader output it does not recognise.
#
# Read with: python3 bench/e15_read.py --window <E15_START> -
# Usage: bash bench/e15_probe.sh [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
TASK="sf-author-verdict-from"

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
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
python3 bench/e15_prep.py --check-frozen || { echo "FATAL: E15 probe drafts not frozen, or the probe is not allowed"; exit 1; }

ORDER=()
while IFS= read -r arm; do
  [ -n "$arm" ] && ORDER+=("$arm")
done < <(python3 bench/e15_read.py --order)
[ "${#ORDER[@]}" -gt 0 ] || { echo "FATAL: could not read the probe order"; exit 1; }
echo "order (${#ORDER[@]} runs):"
printf '  %s\n' "${ORDER[@]}"

known() {  # $1: an arm name; true if it is "control" or appears in ORDER
  local a
  for a in "${ORDER[@]}"; do [ "$a" = "$1" ] && return 0; done
  return 1
}

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 8 repeats"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "E15_START $START"

check_read() {  # $1: reader output; stops the script on anything but a live batch
  case "$1" in
    "batch: incomplete"*|"batch: complete"*) ;;
    "batch: postponed"*) echo "$1"; echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
    "batch: void"*) echo "$1"; echo "STOP: the control resolved -- the batch is void"; exit 1 ;;
    *) echo "$1"; echo "STOP: could not read the batch -- fix bench/e15_read.py and re-run this whole batch later"; exit 1 ;;
  esac
  if printf '%s\n' "$1" | grep -qE '^  baseline .* void$'; then
    echo "$1"; echo "STOP: a baseline draft voided -- d cannot be computed (plan ruling 4)"; exit 1
  fi
}

run_one() {  # $1: control | a draft path from ORDER
  if [ "$1" = "control" ]; then
    python3 bench/run.py --task "$TASK" --runs 1 --arm control --model claude-opus-5 \
      || echo "run.py exited non-zero for control"
  else
    python3 bench/run.py --task "$TASK" --runs 1 --arm treatment --model claude-opus-5 \
      --skill-from "$R/$1" || echo "run.py exited non-zero for $1"
  fi
  local out
  out="$(python3 bench/e15_read.py --window "$START" - 2>&1)" \
    || { echo "$out"; echo "STOP: the reader failed"; exit 1; }
  check_read "$out"
}

for arm in "${ORDER[@]}"; do
  echo "### $arm"
  run_one "$arm"
done

EXTRA=0
while [ "$EXTRA" -lt 8 ]; do
  TODO_OUT="$(python3 bench/e15_read.py --window "$START" - --todo 2>&1)" \
    || { echo "$TODO_OUT"; echo "STOP: could not read the batch's remaining runs"; exit 1; }
  NEXT="$(printf '%s\n' "$TODO_OUT" | head -n 1)"
  [ -n "$NEXT" ] || break
  known "$NEXT" || { echo "$TODO_OUT"; echo "STOP: unexpected --todo output"; exit 1; }
  echo "### repeat $NEXT"
  run_one "$NEXT"
  EXTRA=$((EXTRA + 1))
done

FINAL_OUT="$(python3 bench/e15_read.py --window "$START" - 2>&1)" \
  || { echo "$FINAL_OUT"; echo "STOP: the reader failed on the final read"; exit 1; }
check_read "$FINAL_OUT"
echo "$FINAL_OUT"
if printf '%s\n' "$FINAL_OUT" | head -n 1 | grep -q '^batch: incomplete'; then
  echo "INCOMPLETE: runs still missing after 8 repeats -- record this batch as incomplete and re-run it whole later"
  exit 1
fi
echo "### E15 PROBE DONE"
```

- [ ] **Step 3: Verify without spending a session**

Run: `chmod +x bench/e15_distill.sh bench/e15_probe.sh && bash -n bench/e15_distill.sh && bash -n bench/e15_probe.sh && echo syntax-ok`
Expected: `syntax-ok`

Run: `bash bench/e15_distill.sh --stage smoke --dry-run`
Expected:
- `variant snapshot: <WORK>/plugin-<sha7>-e15`;
- a `mark:` line containing `+e15-`;
- `dry run: every guard passed ...`, exit 0.

Run: `bash bench/e15_distill.sh --stage draws --dry-run`
Expected: the same, with `6 distill session(s) under learn-e15-nogate`.

Run: `bash bench/e15_probe.sh --dry-run`
Expected: `FATAL: bench/distilled/C/e15-probe.json missing ...` and then `FATAL: E15 probe drafts not frozen, or the probe is not allowed`, exit 1. No record exists until Task 6, so this is the correct dry-run result now.

Demonstrate `check_read` without a session, using a throwaway snippet that is not committed. Source only the function definition, then show three outputs:
- a `Traceback` input prints a STOP line and exits 1;
- `batch: incomplete -- x` followed by `  baseline learn-nogate/2/SKILL.md ... void` prints the baseline STOP and exits 1;
- `batch: incomplete -- x` followed by `  variant learn-e15-nogate/1/SKILL.md ... void` returns normally.

Run: `python3 -m pytest -q tests`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bench/e15_distill.sh bench/e15_probe.sh || exit 1
git commit -q -m "bench: E15 stage scripts -- variant distill (smoke, draws) and probe, fail closed

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

---

### Task 6: Run E15 and record it (the controller runs this, not a subagent)

This spends about 1 + 6 + up to 38 sessions. Run it only after the final whole-branch review is clean. Start each batch right after a session-limit reset where possible.

**Files:**
- Modify: `bench/distilled/C/…`, `bench/distilled/C/e15-probe.json`, `bench/results.jsonl`, `bench/RESULTS.md`
- Modify, only if the rules help: `skills/distilling-skills/SKILL.md`

- [ ] **Step 1: Stage A, the smoke**

Run in the background, logging to the scratchpad: `bash bench/e15_distill.sh --stage smoke`
Expected: `smoke: PASS` and `### E15 STAGE smoke DONE`. On `FATAL: smoke failed`, stop E15, report the `meta.json` problems and the session tail, and fix before continuing.

Report the smoke draft's rule compliance. It is reported only, never a gate (spec section 3, stage A):

Run: `python3 -c "import sys; sys.path[:0]=['scripts','bench']; import e15_prep; print(e15_prep.compliance(open('bench/distilled/C/learn-e15-smoke-nogate/1/SKILL.md').read()))"`

```bash
git add bench/distilled/C/learn-e15-smoke-nogate || exit 1
git commit -q -m "bench: E15 stage A -- variant distill smoke

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 2: Stage B, the six draws**

Run in the background: `bash bench/e15_distill.sh --stage draws`
Expected: `### E15 STAGE draws DONE`.

On `STOP: session limit`, apply plan ruling 5:
1. `git mv` or `mv` `bench/distilled/C/learn-e15-nogate` to `bench/distilled/C/learn-e15-nogate-postponed-1`;
2. commit it as excluded;
3. wait for the reset;
4. re-run this step.

```bash
git add bench/distilled/C/learn-e15-nogate || exit 1
git commit -q -m "bench: E15 stage B -- six variant draws

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 3: Stage C, the freeze**

Run: `python3 bench/e15_prep.py --write`
Expected: one row per counted variant draft and three baseline rows, `probe allowed: <True|False>`, and `wrote bench/distilled/C/e15-probe.json`.

```bash
git add bench/distilled/C/e15-probe.json || exit 1
git commit -q -m "bench: E15 stage C -- delivery, compliance and freeze

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

If `probe allowed: False` because fewer than 3 variant drafts were delivered, skip to Step 5 and record an **emission** result. If a baseline draft was undelivered, record that instead. Either way, the probe does not run.

- [ ] **Step 4: Stage D, the probe**

Run in the background: `bash bench/e15_probe.sh`
Then read the batch independently: `python3 bench/e15_read.py --window <E15_START from the log> -`.

- **Postponed:** commit the rows as a postponed batch, wait for the reset, and re-run this step whole.
- **Incomplete after the repeat cap:** record it as incomplete; never stitch.

```bash
git add bench/results.jsonl || exit 1
git commit -q -m "bench: E15 probe batch -- <batch status, V, B, d, reading>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 5: Record it in `bench/RESULTS.md`**

Add a register row after the latest row under `## Experiments`, and an `# E15` section at the end of the file with:

- stage A and stage B outcomes, including saves, taints and counted draws;
- the `e15_prep.py` table: delivery and the three compliance flags for every variant and baseline draft;
- the reader's full output (per-draft counts, V, B, d, reading, Fisher p, baseline flag), or the emission or incomplete status;
- the section 5 reading that applies, and what it means for the shipped skill;
- a limits line: 3 runs per draft, one trap, the rules bundled so no single rule is identified, and thinking not visible.

```bash
git add bench/RESULTS.md || exit 1
git commit -q -m "docs: E15 -- <one-line result>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

- [ ] **Step 6: Ship the rules, only if the reading is "the rules help"**

Copy the three rule paragraphs from `bench/variants/E15/distilling-skills.md` into `skills/distilling-skills/SKILL.md` at the same three places. Confirm the two files are then identical with `cmp`, and run `python3 -m pytest -q tests`. Commit on its own:

```bash
git add skills/distilling-skills/SKILL.md || exit 1
git commit -q -m "skills: distilling-skills gains three writing rules -- E15: <V>, <B>, d = <d>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || exit 1
```

For any other reading, do not touch the shipped file.
