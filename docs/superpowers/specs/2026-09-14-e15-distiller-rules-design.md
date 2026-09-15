# E15: do three writing rules make the skills distiller's output usable?

**Status:** design agreed in brainstorming on 2026-09-14, written before any
E15 session ran. Every criterion below is fixed before the data it governs.

## Why

E13 distilled three skills from trap C's repair task (`C/learn-nogate/1..3`).
When probed on trap C's author task (`sf-author-verdict-from`), they resolved
1 of 9 runs. E14 rewrote one of them by hand, kept the same fix, and the
rewritten skill resolved 4 of 6 even with E13's failure-time trigger.
Neither of E14's pre-registered factors, trigger and kind, reached its bar,
so whatever lifted it came from the rewrite.

The E14 write-up names three differences between E13's skill draft and the
rewrite. E15 turns them into rules for the skills distiller and tests whether
drafts distilled under those rules do better than E13's.

`skills/distilling-skills/SKILL.md` ships with the plugin, so the rules are
tested as a **bench-only variant** first. The shipped file changes only if
the variant clearly wins (section 5).

## 1. The variant

`bench/variants/E15/distilling-skills.md` is a copy of
`skills/distilling-skills/SKILL.md` as of the commit the spec is written on,
with exactly three additions and no other change:

1. **Contract step 4 (Generalize):** a new paragraph. Never name tests, test
   files, fixtures or line numbers that a future session may not have;
   describe what they check instead.
2. **Contract step 6 (one-shot):** a new paragraph. Write the `## Procedure`
   so it works when the code is being written for the first time, not only
   when a broken version exists to find and change. Do not open a step with
   "find the existing …" unless the procedure is only ever about existing
   code.
3. **Contract step 7 (triggers):** a new paragraph. Name the function or API
   the skill is about in the description's first sentence, and make
   `Use when:` cover writing or editing that code, not only seeing it fail.

The exact added text is fixed in the implementation plan and committed before
any session. A test checks that the variant differs from the shipped file only
by those three paragraphs.

## 2. How a session gets the variant

`bench/run.py` gains `variant_plugin(base_snapshot, variant_file, dest)`. It
copies a normal plugin snapshot, replaces `skills/distilling-skills/SKILL.md`
with the variant, and writes the snapshot mark as
`<sha>+e15-<first 12 hex of the variant's sha256>`. Every distill `meta.json`
therefore records exactly which rules ran, through the existing
`plugin_commit`.

`bench/distill.py` gains:

- `--plugin-dir`, which must be a snapshot (the sandbox already refuses
  anything else);
- `--variant <name>`, which adds `-<name>` to the distiller segment, so the
  draws archive under `bench/distilled/C/learn-e15-nogate/<draw>` and clone to
  `…-distill-learn-e15-nogate-<draw>`. E13's `learn-nogate` draws are never
  touched.

Every E15 session is sandboxed and audited.

## 3. Stages

### Stage A: smoke (1 session)

One variant distill session on trap C, archived under
`bench/distilled/C/learn-e15-smoke/1` and never probed. It passes if:

- the session starts and authenticates;
- its audit is `clean`;
- `meta.json` records the variant mark;
- it saved a draft.

A failure stops E15 until fixed. Rule compliance of the smoke draft is
reported, not gated.

### Stage B: distill (6 sessions)

Six draws on `sf-repair-verdict-from`, with the skills distiller, the variant
snapshot and the novelty gate off (as in E13). A draw **counts** if:

- its outcome is `saved`;
- its draft file exists;
- it is not `tainted`.

A session refused at the session limit postpones the stage, and the stage is
re-run whole.

### Stage C: zero-session checks

- **Delivery:** each counted draft is installed alone through the real
  `save_skill.py` into a sandboxed HOME. The HEAD prompt hook runs on trap C's
  author prompt (the E14 delivery-check method), and only delivered drafts are
  probed. The same check runs on the three baseline drafts, and all three must
  be delivered, or the probe does not run and the report says so.
- **Rule compliance (descriptive, never a gate):** for each variant draft and
  each baseline draft, record:
  - whether it names any `test_…` identifier or a file under `tests/`;
  - whether any numbered `## Procedure` step starts with the word `Find`
    (a line matching `^\s*\d+\.\s+(\*\*)?Find\b`);
  - whether `verdict_from` appears in the description's first sentence
    (the flattened description up to its first `. `).
- **Freeze:** the variant and baseline draft paths, their sha256 and
  `delivered` are written to `bench/distilled/C/e15-probe.json` and committed
  before the probe.
- **Emission gate:** if fewer than 3 variant drafts are delivered, the probe
  does not run. The result is recorded as **emission** (section 5).

### Stage D: probe (one batch, up to 30 sessions)

Run on `sf-author-verdict-from`, each draft installed alone with
`run.py --arm treatment --skill-from <draft>`:

- **control:** 3 runs, no skill;
- **variant:** each delivered E15 draft, 3 runs each (up to 18);
- **baseline:** E13's `C/learn-nogate/1`, `/2` and `/3`, 3 runs each (9),
  re-probed in the same batch rather than taken from E13's 1 of 9.

**Order:** three rounds. Each round runs every draft once, in this order:

1. start from the variant drafts and the baseline drafts interleaved (v1, b1,
   v2, b2, v3, b3, then any remaining variant drafts in order);
2. rotate that list left by the round number (0, 1, 2);
3. each round begins with one control run.

The batch script prints the full order before the first session.

**Guards before the first session:**

- the global library is empty;
- the plugin checkout is clean;
- `run.py --check` and `run.py --sandbox-check` pass;
- `e15-probe.json` exists, and every listed draft's sha256 matches it;
- `scripts/` and `hooks/` are unchanged since the commit its delivery check
  ran at;
- a one-word allowance probe succeeds.

**Counting rules** (as E14):

- **Audit:** a row `audit.counts()` rejects never counts and is repeated.
- **Undelivered:** a draft row whose injections do not name that draft does
  not count and is repeated; a second undelivered row voids that draft.
- **Failed session:** a session that failed for any reason other than the
  session limit does not count and is repeated.
- **Cap:** each draft counts its first 3 valid runs; the control counts its
  first 3.
- **Session limit:** a refusal at the session limit postpones the whole batch,
  which is re-run whole later, never stitched.
- **Control:** a valid control run that resolves voids the batch.
- **Repeats:** at most 8, after round 3.
- **Stops:** the script stops on a postponed or void batch and on reader
  output it does not recognise.

A voided variant draft drops out of V. A voided baseline draft makes the batch
incomplete for B, and d is not computed.

## 4. Measures

- **V** = resolved ÷ valid runs, pooled over the non-void delivered variant
  drafts.
- **B** = resolved ÷ valid runs, pooled over the three baseline drafts.
- **d** = V − B, reported to two decimals.
- **Fisher's exact p** (two-sided) on the pooled 2×2 (V's resolved and
  unresolved against B's), reported, never a threshold.
- **Per-draft counts** for every variant and baseline draft.

## 5. Criterion

| result | reading | shipped `skills/distilling-skills/SKILL.md` |
| --- | --- | --- |
| d ≥ +0.40 **and** V ≥ 0.50 | the rules help | change it to the variant text, as its own reviewed commit |
| −0.15 ≤ d ≤ +0.15 | no large effect | unchanged |
| any other d > −0.40 | ambiguous | unchanged; a follow-up is optional |
| d ≤ −0.40 | the rules hurt | unchanged |
| fewer than 3 variant drafts delivered | emission: the rules reduce usable output | unchanged; no probe |

**Baseline check.** E13 measured the baseline drafts at 1 of 9. If B is 5 of 9
or more, the report flags that the baseline moved, and d is read with that
caveat.

## 6. Outputs

- A register row and an E15 section in `bench/RESULTS.md`, whatever the
  outcome, including a postponed batch or an emission result.
- Committed: the variant file; the six draws and the smoke draw under
  `bench/distilled/C/`; `e15-probe.json`; the probe rows in
  `bench/results.jsonl`.
- If the rules help: a separate, reviewed commit that copies the three
  paragraphs into `skills/distilling-skills/SKILL.md`, with the E15 result
  cited in its message.

## 7. Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and
  `bench/real_path_check.py` are not touched.
- No E13 or E14 file, draft or reader changes (imports allowed).
- `skills/distilling-skills/SKILL.md` changes only under section 5's first row.
- No absolute home path in committed files.
- Guard committing steps with an explicit `|| exit 1`.

## Amendments

Both were made on 2026-09-15, after a pre-run review and before any E15
session, at the user's ruling. The sections above are left as written.

1. **Stage B, stage C: a draw that says nothing about the rules is a harness
   failure, not a non-emission.** A draw that is `session_failed`, `errored`,
   missing or `repair_unresolved` (the source session never fixed the bug), or
   that is not sandboxed, has an audit other than `clean`, or is `tainted`,
   blocks the probe. Stage B is re-run whole, and no emission result is
   recorded. Previously a tainted or unresolved draw only failed to count, so
   it could shrink the counted draws below 3 and read as "the rules reduce
   usable output". A counted draw must now also be sandboxed with a clean audit.
2. **Section 5: V needs at least 3 live variant drafts.** If voids in stage D
   leave fewer than 3, d is not computed and the batch is recorded as not
   readable, as for a void baseline draft. Previously V could rest on a single
   draft's 3 runs.
