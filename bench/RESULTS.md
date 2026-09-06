# Experiment register

Every benchmark run this project has done, what it answers, and where its data
is. Added 2026-09-06 after two claims below turned out to be wrong precisely
because nothing indexed the data — see "What the register caught".

## Experiments

| # | Question | Status | Data |
|---|---|---|---|
| Pilot (2026-08-11) | Does a matched skill change authoring behavior? Does a same-class one transfer? | **Done.** control 0/6, matched 5/6, transfer 0/6 | trap 1 rows in `results-round1.jsonl`; trap 2 rows in `results.jsonl` |
| E1 (2026-09-06) | Does packaging both traps as one umbrella destroy the effect? | **Answered.** umbrella 6/6 = matched 6/6. `/consolidate` unblocked | `results.jsonl`, the 18 rows carrying `"model": "claude-opus-5"` |
| E4 | Does injecting an *irrelevant* skill actively hurt? (= brief Q3) | **Blocked.** Needs a task whose control is neither 0 nor 100%; no such task exists | tasks defined (`sf-author-*-irrelevant`), never run |
| E5 | Is the effect the knowledge, or the delivery path? | **Designed, not run.** Needs a force-hot lever that does not exist | none; design in `docs/session-handoff.md` §3.1 |
| Critique calibration | Does the critique rubric agree with hand-established verdicts? | **Run.** 6/7 before a rubric change, 7/7 after | `bench/critique-calibration/` (own README, `expected.json`, 8 result files) |

## The brief's five questions, which are the actual agenda

`docs/2026-08-29-benchmark-investigation-brief.md` ranks five questions by
value. The E-numbers are **not** those numbers. Only E4 maps cleanly.

| Brief | Question | Where it stands |
|---|---|---|
| Q1 | Does the pipeline work end to end, or only the injection half? | **No experiment exists.** Every result in this file uses a *hand-authored* skill. The claim is session → distilled skill → later session improved, and the distiller is the untested link. This is the largest open question in the project |
| Q2 | Is transfer real at any n? | **Partial.** Transfer 0/6 at n=3 in the pilot. Establishing transfer, or its absence at a convincing n, is unfinished |
| Q3 | Does injection ever hurt? | = E4, blocked |
| Q4 | Token cost per unit of benefit? | **No experiment exists** |
| Q5 | Does the `trusted` gate predict anything? | **Not answered.** Critique calibration measures the rubric's *accuracy against known verdicts* — not whether skills that pass it outperform skills that fail it. That needs bench runs split on critique verdict, and nobody has done it |

## Where the raw rows are

| File | Rows | Live or superseded |
|---|---|---|
| `results.jsonl` | 27 | 9 pilot (trap 2, 2026-08-11) + 18 from E1 day |
| `results-round1.jsonl` | 18 | **Mixed.** Trap 1's pilot rows are LIVE — the headline table's 0/3, 3/3, 0/3 for response_text come from here. Only trap 2's six rows are superseded by the file-cap repair |
| `results-leaky-stub.jsonl` | 12 | Superseded *as an authoring design* — but it holds the only control data for the two repair-mode tasks, and that data is live |

## Numbering, honestly

The E-labels grew by accretion and do not form a series. E1 came from the
pilot's "roadmap risk" note, not from the brief. E4 is the brief's Q3. E5 was
coined on 2026-09-06 in the handoff. **There is no E2 or E3.** Do not read a
gap as a missing experiment.

## What the register caught

Writing this table found two claims that were stated confidently in this file
and in the handoff, and were wrong:

1. **"The two repair-mode tasks have never been run."** They have.
   `results-leaky-stub.jsonl` holds four clean control runs from 2026-08-10 —
   `sf-escaping-breaks-symptom-match` 2/2 and `sf-truncation-reports-absent`
   2/2, every hidden test green, both sessions healthy. Their control rate is
   **100%**, not unknown. This is the same 4/4 already written up below under
   "Three earlier designs that measured nothing"; nobody connected the two.
   The consequence is in the E4 section.

2. **"`results-round1.jsonl` is the superseded round."** Half of it is the
   live trap-1 pilot data this file's own headline table reports.

Both are the same failure: data with no index, described from memory.

---

# SkillForge benchmark — pilot results (2026-08-11)

## Headline

Two authoring tasks, three runs per condition each, one model. Both traps now
score on two valid hidden tests (the file-cap test was repaired -- see below).

| Condition | Trap 1 (response_text) | Trap 2 (fingerprint snapshot) | Combined |
|---|---|---|---|
| Control — no skill | 0/3 | 0/3 | **0/6** |
| Matched — skill from this same trap | 3/3 | 2/3 | **5/6** |
| Transfer — same-class skill, *different* bug | 0/3 | 0/3 | **0/6** |

Every treatment run was ledger-confirmed as actually injected (9 and 12
injections across rounds, one per run), so both transfer nulls are real nulls
rather than delivery failures.

The direction replicated across two independent traps. The transfer arm was
indistinguishable from control both times.

The one matched-arm miss (trap 2, run 3) is a genuine miss, not a scoring
artifact: that run applied both caps (`[:SNAPSHOT_MAX_FILES]`,
`[:SNAPSHOT_MAX_BYTES]`) but never set the unknown flag when they truncated,
so it silently returned 0. The skill was injected; the model did not apply it.

## The file-cap test was invalid, and is now repaired

First run of trap 2 scored 0/3 in *every* arm including matched -- the
signature of a broken test rather than a hard task.

It was broken because it encoded the reference implementation's *strategy*
rather than the contract. The reference greps the single longest token, so 20
decoy files swamp it and the cap bites. A matched run instead used `git grep
--all-match` over every token: only the real file came back, the cap never
bit, it found the fingerprint and returned 1 -- correct, and better. The test
asserted None, so the better implementation scored zero. That same run
contained `if len(files) > SNAPSHOT_MAX_FILES: unknown = True`, so it
demonstrably held the knowledge while being marked wrong.

The repaired test (`bench/stubs/patch_file_cap_test.py`) removes the
assumption: every decoy carries ALL of the pattern's tokens, so any narrowing
strategy returns them and the cap bites either way; the decoys hold those
tokens in reverse order so `patterns.matches` correctly refuses them; and the
genuine occurrence sits in a file that sorts past the cap. The fingerprint
really is present, so answering 0 is factually wrong rather than merely
unjustified, and answering 1 requires reading past the stated cap. Only
"unknown" is defensible, whatever narrowing strategy is used.

Validated in all three directions before rerunning: it passes the reference
implementation, passes the `--all-match` implementation it previously
punished, and still fails the pre-fix code that lacks unknown-on-truncation.

Two lessons for the harness: a hidden test must assert the contract, never the
reference implementation's approach; and a condition scoring 0 across *all*
arms should be treated as a suspect test before it is treated as a result.

## What the task is

`sf-author-response-text`, an **authoring** task. The tree is `22ddf37~1` with
`detect.response_text` replaced by a contract-only stub. The model implements it
from the docstring and **never sees the grading tests**, which are applied
afterward. Scoring is binary on two hidden tests, per spec §7 (verification
success, never turns-to-completion).

The trap: `tool_response` is usually a dict, and `json.dumps` escapes newlines
to a literal backslash-n, which the tokenizer then glues onto the next word —
so every symptom whose signature begins a line silently stops matching.

## Mechanism, not just counts

| Arm | Run | What it wrote | Hidden tests failed |
|---|---|---|---|
| control | 1 | flat join, comment: *"no tool nests them deeper"* | nested |
| control | 2 | `json.dumps(resp, ensure_ascii=False, default=str)` | both |
| control | 3 | `json.dumps(resp, default=str)` | both |
| matched | 1–3 | depth-capped leaf walker | none |
| transfer | 1 | `json.dumps(resp, default=str)` | both |
| transfer | 3 | shallow dict handling | nested |

Depth-capping appears in all three matched-skill runs and no control run. It is
a specific instruction in that skill's Fix section, so the influence is
traceable rather than merely correlated.

## Three earlier designs that measured nothing

Recorded because each null was informative:

1. **Public-repo repair task** (arrow #968): control resolved it. No headroom.
2. **Post-cutoff repair tasks** (this repo's own bugs, code days old): control
   resolved 4/4. This killed the contamination hypothesis — the bugs *cannot*
   be in training data. The real cause is structural: **a FAIL_TO_PASS task
   hands over the answer**, because the red assertion names the exact
   condition. One control session derived the entire escaping insight from the
   failing test. Every SWE-bench-style benchmark is FAIL_TO_PASS, so that whole
   family structurally cannot measure what a skill contributes.
3. **First authoring attempt**: the stub docstring said the object was one
   "whose string leaves hold the tool's output" — which prescribes the
   leaf-walking fix. Both arms scored 6/6. The leak check had grepped for
   `escape|newline|json|serial` and sailed past it. Preserved in
   `results-leaky-stub.jsonl`.

## What this suggests

Skills change authoring behavior when they are **specific and matched**.
Abstract same-class knowledge did not transfer at this n — the transfer arm was
indistinguishable from control, despite being injected every run.

**Roadmap risk this raises:** v0.3's `/consolidate` generalizes sibling skill
clusters into a shared parent pattern. If specificity is what carries the
value, generalization may destroy the thing being measured here. Worth testing
before building it.

**Secondary:** retrieval precision matters more than recall. A thematically
related skill that fires costs tokens and delivers nothing.

## Limits

- n=3 per condition per trap (n=6 combined), two traps, one model.
- Trap 2's file-cap test was repaired and revalidated; both traps now rest
  on two valid tests each.
- The matched-skill arm measures a **ceiling** (skill written from this exact
  trap), not typical performance.
- Skills and tasks were both curated by the same author who found the bugs.
- Replicated on the second trap at 2/3, with the one miss traced to the model
  not applying an injected skill rather than to scoring.
- Round-1 records in `results-round1.jsonl`. Note this file is MIXED: trap 1's
  rows there are the live pilot data reported above, and only trap 2's six rows
  are superseded by the file-cap repair. See the register.

## Reproducing

    python3 bench/run.py --task sf-author-response-text --runs 3
    python3 bench/run.py --task sf-author-response-text-transfer --runs 3 --arm treatment

Raw records in `results.jsonl`; each line carries the arm, per-test outcomes,
wall time, and the ledger-confirmed skill save.

---

# E1 — does an umbrella skill destroy the effect? (2026-09-06)

## Headline

One anti-skill carrying BOTH trap classes performs identically to two
anti-skills each carrying one. **Consolidation is safe.**

| Condition | Trap 1 (response_text) | Trap 2 (fingerprint snapshot) | Combined |
|---|---|---|---|
| Control — no skill *(pilot)* | 0/3 | 0/3 | **0/6** |
| Transfer — same-class, different bug *(pilot)* | 0/3 | 0/3 | **0/6** |
| Matched — one skill per trap | 3/3 | 3/3 | **6/6** |
| **Umbrella — one skill, both traps** | **3/3** | **3/3** | **6/6** |

Matched was re-measured today rather than compared against the pilot's 5/6.
`bench/run.py` did not pin a model and the pilot did not record one, so a
cross-date comparison was confounded by construction. Both rows above ran on
`claude-opus-5`, now pinned via `--model` and written onto every
`results.jsonl` record.

**The two rows above are not from one batch, and the write-up said they were.**
Matched ran 20:25-20:31 on 09-05, in the same batch as the *invalid* umbrella
run; the valid umbrella ran 00:50-00:57 on 09-06, after the repair commit. The
model was pinned and recorded identically for both, so the confound that
motivated re-measuring matched is still controlled -- but this is a same-day
same-model comparison, not a same-batch one. The harness change between them
did not reach matched: all six matched rows record `indexed: warm tier` and
were never materialized, which is what the per-run ledger would have produced
anyway. Stated here rather than quietly fixed, because "same batch" was the
stated reason to trust the comparison.

This unblocks v0.3 `/consolidate`, and makes an authoring body-cap
reasonable: specificity survived packaging.

## Delivery was symmetric, and that is the whole result

Per-run ledgers, six runs:

    sf-author-response-text-umbrella-1..3          injection=1  marker=0/1/1
    sf-author-fingerprint-preexisting-umbrella-1..3  injection=1  marker=1/1/1

Every run saved to `antiskills/`, stayed warm, was never materialized hot, and
logged exactly one injection — the same delivery path the matched arm took.
The umbrella was not merely present; it was delivered identically to the
skills it replaces.

## Mechanism, not just counts

| Task | Run | What it wrote |
|---|---|---|
| response_text | 1 | leaf walker, `MAX_DEPTH = 8` |
| response_text | 2 | leaf walker, `MAX_DEPTH = 8` as the cycle guard |
| response_text | 3 | recursive leaf walk over dict/list/tuple |
| fingerprint | 1 | `return None if capped else 0` |
| fingerprint | 2 | `unknown = unknown or truncated`; `return None if unknown else 0` |
| fingerprint | 3 | `return None if incomplete else 0` |

Both halves of the umbrella fired, on their own traps, in the same session
population. Depth-capping is a specific instruction in the umbrella's Fix
section and appears in the response_text runs; three-valued return is the
other half and appears in all three fingerprint runs, under three different
variable names — the instruction, not the wording, is what carried.

## The first batch measured the wrong thing (kept, because the error is the finding)

The first E1 batch scored umbrella **1/6** against matched 6/6, which reads as
"generalization destroys the effect" and would have killed `/consolidate`.

It was invalid. The umbrella was authored as `kind: skill` while both
comparators are `kind: antiskill`, and that single difference forked three:

**Delivery.** Anti-skills are symptom-triggered and never spend hot budget;
skills are description-matched and hot-eligible. Each comparator logged 3
injections and 3 markers across its 3 runs. The umbrella logged 1 and 1.

**Grading.** The umbrella declared `verification.command: python3
tests/test_detect.py` — which *is* `test_cmd` for
`sf-author-response-text-umbrella`. Scoring the task fired the skill's own
verification, logged three successes, promoted it to `working`, and
materialized it hot for 5 of 6 runs. The anti-skills declare no
`verification.command`, could never earn organic confidence, and stayed warm.
One arm was graded by its own grader.

**Independence.** Because promotion happened mid-cell, run 1's outcome changed
how run 2 was delivered. A cell was a sequence that learns, not three trials.
`SKILLFORGE_LEDGER` now points at a per-run file.

The repair changed packaging only: `kind: antiskill`, the union of both
parents' symptoms verbatim, no `verification.command`, body content unchanged
in substance and restructured into the Trap/Symptom/Cause/Fix sections
anti-skills require.

**Lesson for the harness, alongside the pilot's two:** an arm must differ from
its comparator in exactly the variable under test. Kind, delivery tier, and
verification eligibility all ride along on `kind:`, so a skill and an
anti-skill are never a clean A/B.

## A sharper question this raises

The same knowledge scored 1/6 as a description-triggered `kind: skill`
delivered hot, and 6/6 as a symptom-triggered anti-skill delivered warm. That
is a delivery-mechanism effect, not a generalization effect, and it is larger
than anything E1 set out to measure.

It is not a finding — the skill version also differed in section structure and
in confidence trajectory, so it is still multi-variable. But it is the most
interesting thing in this batch: for trap-shaped knowledge, symptom triggering
may be doing the work that description matching does not. Testing it needs one
skill, one kind, delivered two ways.

## Limits

- n=3 per cell, 6 per condition, two traps, one model (`claude-opus-5`).
- 6/6 vs 6/6 is consistent with "no difference" but cannot size one. A true
  difference smaller than roughly a third would be invisible at this n.
- The umbrella covers two trap classes. Nothing here says how far that scales;
  the compression curve, if there is one, is untested past two.
- Both arms measure a **ceiling** — skills written from these exact traps.
- Bench sessions inherit the operator's full plugin set, so the measurement is
  of model-plus-plugins rather than a bare model. Constant across arms, so it
  does not confound the contrast, but the absolute numbers carry it.
- The umbrella and both parents were authored by the same person who found the
  bugs.

## Reproducing

    python3 bench/run.py --check
    python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-umbrella
    python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-umbrella
    python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text
    python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting

Control is deliberately not rerun: it installs no skill, so it is identical
across every variant of a trap and was measured at 0/6 in the pilot.

Records carrying `"model": "claude-opus-5"` in `results.jsonl` are this
experiment. The invalid batch is the six umbrella rows whose `skill_note`
saves into `.claude/skillforge/skills/` — the valid ones save into
`antiskills/`, which is exactly the change that repaired the experiment. Not
`materialized`: run 1 of the invalid batch was still warm when it ran, because
promotion had not happened yet. The six matched rows are shared by both
batches; they were only run once.

## E4 is not ready

`sf-author-*-irrelevant` exists but must not be run. E4 asks whether injecting
an irrelevant skill actively hurts — and control already scores 0/6 on these
traps, so there is no room to fall and scoring is binary. The experiment cannot
detect harm here. It needs a task whose control baseline is neither 0 nor 100%.

**The obvious candidates are already ruled out.** An earlier draft of this
section proposed the two repair-mode tasks and said their control rate was
unknown. It is not: `results-leaky-stub.jsonl` holds four clean control runs
from 2026-08-10 — `sf-escaping-breaks-symptom-match` 2/2,
`sf-truncation-reports-absent` 2/2, every hidden test green. Control is at the
**ceiling** there, which is the same wall as the floor: no room to fall, no
harm detectable. That is the pilot's own finding about FAIL_TO_PASS repair
tasks, which hand over the answer in the failing assertion.

So E4 needs a task that does not exist yet: an **authoring** task where control
succeeds *sometimes*. Building it is design work, not a run, and it is the real
blocker behind E4. Do not spend sessions re-measuring the repair tasks.
