# E20: a fourth distiller rule — the verification must exercise every step

**Status:** design written 2026-09-17, before any E20 session. **Not run, and
the rule is NOT in the shipped skill.** E15's precedent governs: its three
rules went into `skills/distilling-skills/SKILL.md` only after the probe read
V 18/18 against B 0/9. A fourth rule ships on the same terms or not at all.

## Why

E17's capture run (amendment 2) critiqued the six E15 drafts with findings
recorded. `checkable` drew an objection in **16 of 18 calls**, always the same
one, and it is **correct**: every draft states as step 3 of its own procedure

> "Apply the minimum-length floor (`MIN_EVIDENCE_CHARS`) to the normalised
> evidence. Otherwise padding with whitespace gets a too-short quote past the
> floor."

and every draft's `verification.command` asserts only the rewrapped, reordered
and absent cases. **Six of six drafts declare a step their own verification
never tests.** That is the calibration corpus's case 02 defect, and following
it found a live bug in `validate.py` (fixed 2026-09-17).

This matters beyond tidiness. `critique == "pass"` is a required conjunct of
`trusted` in `ledger.confidence()`, so a skill that fails `checkable` is capped
at `working` and never reaches the hot tier. E15's rules improved **outcomes**;
this one targets the property that actually gates **promotion**.

## 1. The rule under test

Added to the variant copy of `distilling-skills` only:

> **Your verification must exercise every step of your Procedure.** For each
> step, name the assertion that fails when that step is skipped. If a step has
> no such assertion, either add one or remove the step — a step the
> verification cannot see is a claim the reader has to take on trust.

## 2. Shape, reusing E15's harness unchanged

E15's machinery is built and proved: `bench/e15_prep.py`, `e15_distill.sh`,
`e15_probe.sh`, `e15_read.py`, with amendment 4's pause-and-resume.

- **Stage B — distillation.** 6 draws under the variant rules (E15's three plus
  this one), novelty gate off, on trap C's repair task. ~6 sessions.
- **Stage C — delivery, compliance, freeze.** 0 sessions. A draft counts only
  if its repair resolved, it is sandboxed with a clean audit, and it is not
  tainted (E15 amendments 1 and 3).
- **Stage D — the probe.** Two measures, and this is where E20 differs from
  E15, because the thing being improved is not the outcome:

  **Primary, 0 sessions: critique.** Each new draft and each of E15's six
  drafts critiqued 3× in one batch — 36 calls. `Pn` = new drafts' pass rate,
  `Po` = E15 drafts'. `Δc = Pn − Po`.

  **Secondary, sessions: the task.** The new drafts probed on
  `sf-author-verdict-from` exactly as E15 probed, against a same-batch control.
  This is a **guard, not the headline**: the rule must not cost outcome.

## 3. Pre-registered reading

| Δc | reading |
| --- | --- |
| ≥ +0.40 with `Pn` ≥ 0.50 | **the rule helps** — ship it |
| ≤ +0.15 | no large effect — do not ship |
| otherwise | ambiguous — do not ship |

**The guard binds independently.** If the new drafts resolve the task at a rate
more than one run below E15's 18/18 per-draft ceiling, the rule is **not
shipped whatever Δc says**. A rule that buys critique approval by making
skills worse is the failure mode this design exists to catch.

Fisher's p reported, never thresholded. Critique's verdict flips on ~70% of
texts (E17/E18/E19 pooled), so 3 calls per draft is a floor, not a comfort:
**with `Pn` and `Po` each resting on 18 calls, Δc is measured through that
noise, and the ±0.40 band is set wide for exactly that reason.**

## 4. Threats

1. **Circularity.** The rule is derived from critique's own objection, and the
   primary measure is critique. E20 can show the distiller can be told to
   satisfy the grader; it cannot show the resulting skills are better. §2's
   secondary measure is the only outcome evidence, and it is a guard.
2. **One trap, one bug.** Trap C again. Everything E15's write-up said about
   that applies here.
3. **The gate is noisy.** See §3.
4. **Teaching to the test.** A draft could add an assertion per step
   mechanically without the assertion being meaningful. Nothing here detects
   that; a later reading of the drafts' `verification.command` by hand is the
   only check, and it is not pre-registered as a gate.
5. **The bug is already fixed.** The drafts' step 3 now describes what
   `validate.py` does. That removes a confound rather than adding one, but it
   means E20's drafts are distilled against a repo whose code moved on
   2026-09-17.

## 5. Cost

~6 distill sessions, 36 critique calls, and one probe batch on the order of
E15's (31–39 sessions, likely spanning a session-limit pause). Not a local
batch. It needs its own sitting.
