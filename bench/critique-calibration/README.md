# Critique calibration corpus

Nine hand-written skills whose correct verdicts were established by reading
the code, and in two cases by running `git` in a scratch repository. `run.py`
critiques them for real and compares against `expected.json`.

```bash
python3 bench/critique-calibration/run.py                # all cases
python3 bench/critique-calibration/run.py 08 09          # by prefix
python3 bench/critique-calibration/run.py --save after   # keep raw findings
```

**This spends real model calls — one `claude -p` turn per case.** It is not a
test suite and must never be run from one; `tests/` is forbidden from
invoking a model, which is why the corpus lives here.

## Why it exists

Rubric changes are otherwise untestable. Tuning against freshly written
examples means grading your own homework: you write something, it fails, you
adjust the rubric until it passes, and you have learned nothing except that
you can move a threshold. Fixed inputs with known answers turn that into a
measurement.

The corpus is deliberately unbalanced — eight must-fail, one must-pass. Only
the positive control can detect over-loosening; without it, a rubric that
passes everything is indistinguishable from one that passes nothing. Case 01
is the floor: it is session-dependent and unverifiable, so any change that
lets it pass has broken the gate no matter what else improved.

## What it measured

Adding `basis` (textual vs empirical) and `severity` (blocking vs minor) to
each finding, and gating only on blocking textual objections:

| | before | after |
|---|---|---|
| cases matching ground truth | 6/7 | 7/7 |
| grade distribution | n/a | 9 blocking, 6 minor, 1 empirical |

The single `empirical` grade landed on the one objection that was actually
false — the model marked its own unverifiable claim as unverifiable, and that
is what let the correct skill through. Every failing case still carried at
least one blocking textual finding, so none passed by accident.

## What it did not establish

**There is no validated positive control.** Case 07 was labelled the control
and had to be relabelled must-fail: on a later run the model found a real
defect in it that I had missed. Cases 08 and 09 were written to replace it —
08 with every claim measured beforehand, 09 fixing the three defects found in
08 — and both failed on further valid objections.

So the corpus can currently detect over-tightening but **not** over-loosening,
and the 7/7 above is weaker evidence than it looks: it was measured while case
07 was still mislabelled.

Nine skills were written across this exercise and none passed. Nearly every
objection checked out. That is the finding the corpus exists to record, and it
argues against further rubric tuning rather than for it — a reviewer that is
usually right and rejects everything is a process problem, not a threshold
problem.
