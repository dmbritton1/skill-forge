# Experiment register

Every benchmark run this project has done, what it answers, and where its data
is. Added 2026-09-06 after two claims below turned out to be wrong precisely
because nothing indexed the data — see "What the register caught".

## Experiments

| # | Question | Status | Data |
|---|---|---|---|
| Pilot (2026-08-11) | Does a matched skill change authoring behavior? Does a same-class one transfer? | **Done.** control 0/6, matched 5/6, transfer 0/6 | trap 1 rows in `results-round1.jsonl`; trap 2 rows in `results.jsonl` |
| E1 (2026-09-06) | Does packaging both traps as one umbrella destroy the effect? | **Answered.** umbrella 6/6 = matched 6/6. `/consolidate` unblocked. Re-measured 4/6 on 09-08 as E5's arm W — read 6/6 as one draw | `results.jsonl`, the 18 rows dated 09-05/09-06 with **no** `delivery` key |
| Q1 (2026-09-09) | Does the distiller work end to end? (= brief Q1) | **Answered.** 4/12 draws emitted; those four scored 12/12 against a 1/6 floor. Bottleneck is emission, not delivery or content | `bench/distilled/` + the 24 rows dated 2026-09-09 |
| E6 (2026-09-10) | Does an irrelevant skill *dilute* a relevant one? | **Answered.** R 6/6, R+I 6/6, zero exclusions, both skills injected on every R+I run. No dilution at n=3 per cell — rules out a large effect only. Does **not** answer E4 | `results.jsonl`, the 12 rows dated 2026-09-10 carrying `extra_skills`; the 09-09 attempt's 3 valid + 9 excluded rows are kept and not pooled |
| E4 | Does injecting an *irrelevant* skill actively hurt? (= brief Q3) | **Blocked.** Needs a task whose control is neither 0 nor 100%; no such task exists | tasks defined (`sf-author-*-irrelevant`), never run |
| E5 (2026-09-06) | Is the effect the knowledge, or the delivery path? | **Answered.** hot 5/6, warm 4/6, control 0/6 — two measurements of one arm differ by more than the arms do, so content carries it and no ranking is claimable | `results.jsonl`, the 15 rows dated 09-06 carrying `"delivery"` |
| Hot under the shipped path (2026-09-08) | Does hot delivery still work after `b35f756` moved the materialization path? | **Confirmed.** 4/6, zero injection rows, three markers. Delivery only — ranking, budget, promotion and eviction remain unevidenced | `results.jsonl`, the 6 rows dated 09-08 |
| Critique calibration | Does the critique rubric agree with hand-established verdicts? | **Run.** 6/7 before a rubric change, 7/7 after | `bench/critique-calibration/` (own README, `expected.json`, 8 result files) |

## The brief's five questions, which are the actual agenda

`docs/2026-08-29-benchmark-investigation-brief.md` ranks five questions by
value. The E-numbers are **not** those numbers. Only E4 maps cleanly.

| Brief | Question | Where it stands |
|---|---|---|
| Q1 | Does the pipeline work end to end, or only the injection half? | **Answered 2026-09-09.** It works when it emits, and it emits 4 times in 12. The four that emitted scored 12/12 against a 1/6 floor. The distiller is no longer the untested link — but the 8 novelty-gate refusals are never probed, so whether the gate is right is a new open question |
| Q2 | Is transfer real at any n? | **Replicated null, still open.** 0/6 in the pilot and 0/6 again on 2026-09-09, the second time against a floor measured in the same batch on the same pinned model. Two nulls at n=6 is not absence at a convincing n |
| Q3 | Does injection ever hurt? | = E4, **still blocked**. E6 (2026-09-10) answered the neighbouring question — an irrelevant skill alongside a relevant one cost nothing, 6/6 versus 6/6 — which makes E4 less urgent but is a different comparator and does not answer it |
| Q4 | Token cost per unit of benefit? | **No experiment exists** |
| Q5 | Does the `trusted` gate predict anything? | **Attempted 2026-09-09, no split available.** Pre-registered as a Q1 secondary and run: critique passed all 4 distilled drafts, so there is no failing group to compare against. Still unanswered, and now known to need drafts the gate *rejects* — which this design does not produce |

## Where the raw rows are

| File | Rows | Live or superseded |
|---|---|---|
| `results.jsonl` | 96 | 9 pilot (trap 2, 2026-08-11) + 18 E1 (09-05, 09-06) + 15 E5 (09-06) + 6 hot-path confirmation (09-08) + 24 Q1/Q2 (09-09) + 12 E6 attempt (09-09, 3 valid and 9 `session_ok: false`) + 12 E6 (09-10). E5's rows and later carry a `delivery` key; nothing before them does. The count read 48 until 2026-09-10 and was stale by 36 rows |
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

---

# E5 — is the effect the delivery, or the content? (2026-09-06)

## Headline

**The content carries the effect. Delivery does not decide it.** The same
anti-skill, same file, same text, delivered as standing native context scores
**5/6**; delivered by symptom injection it scores **4/6** re-measured today
and 6/6 when E1 measured it. Control is 0/6. The gap between the two delivery
paths is smaller than the gap between two measurements of the *same* path.

| Arm | Delivery | response_text | fingerprint | Combined |
|---|---|---|---|---|
| Control — no skill *(pilot)* | — | 0/3 | 0/3 | **0/6** |
| W — symptom injection *(E1, 00:50)* | warm | 3/3 | 3/3 | **6/6** |
| W — symptom injection *(re-run, 11:40)* | warm | 3/3 | 1/3 | **4/6** |
| **H — standing native context** | **hot** | **3/3** | **2/3** | **5/6** |
| H — materialized where nothing loads it | none | 0/3 | — | **0/3** |

n=3 per cell. Say so before quoting any of these numbers.

Arm W was re-run rather than reused because `bench/run.py` changed (two
harness fixes below). Both W measurements are the same code, same model, same
skill, three runs each: **6/6 and 4/6**. That spread is the resolution limit
of this design, and it is wider than the H-vs-W difference it was supposed to
adjudicate. The defensible claim is the one in bold, not a ranking.

The last row is not a designed arm. It is the first attempt at arm H, kept
because it is the cleanest internal validity check the bench has produced.

## The hot tier does not deliver, and never has

`sync.py` materializes a promoted skill to

    <base>/.claude/skills/skillforge-hot/<name>/SKILL.md

Claude Code scans **one** level under `.claude/skills/`, so it looks for
`.claude/skills/skillforge-hot/SKILL.md`, does not find one, and skips the
directory. Every skill SkillForge has ever promoted to hot has been invisible
to the model.

Measured, not inferred. One session, both paths present, nothing else
different:

    .claude/skills/skillforge-hot/matcher-input-traps/SKILL.md   not listed
    .claude/skills/flat-copy/SKILL.md   (same bytes, name changed)   listed

The model was asked to name every Skill available to it. It named `flat-copy`
and not `matcher-input-traps`. The nested copy was still on disk when the
session ended, so this is not eviction.

`docs/skillforge-architecture-v4.md` §312 states the assumption in the open —
"a directory Claude Code actually loads (`~/.claude/skills/skillforge-hot/
<name>/`)" — and every test in the repo asserts that same path, which is why
nothing caught it. The tier has no delivery signal of its own (hot skills log
no `injection` row), so there was nothing to notice.

**Fixed in 0.2.5.** Materialization now writes to
`.claude/skills/skillforge-<name>/SKILL.md` — one level under
`.claude/skills/`, which is the only depth the loader scans. The
`skillforge-` prefix replaces the nesting as the namespace `sync.py` may
evict from: that sweep now runs in the same directory as the user's own
hand-written skills and must never delete one. The legacy `skillforge-hot/`
directory carries the prefix and is not in `keep`, so the first sync after
upgrading removes it; no migration step is needed.

Verified the same way the bug was found — the model was asked to name its
skills, and named `skillforge-matcher-input-traps`. The arm H runs below
predate the fix and used the test-only lever's own flat path; the delivery
mechanism is the same one 0.2.5 now ships.

It also re-reads E1's invalid batch. That batch scored the umbrella 1/6 as a
description-triggered hot `kind: skill`. Hot delivered nothing, so 1/6 was a
control measurement with one lucky run — consistent with the pilot's 0/6, and
no longer evidence about section structure or auto-promotion.

## Delivery was asymmetric by construction, and the ledger proves it

Per-run ledgers. Arm H must show no injection row (the harness injects native
skills and SkillForge never sees it); arm W must show exactly one.

    arm H  response_text     2,3   injection=0  marker=1,1
    arm H  fingerprint     1,2,3   injection=0  marker=0,1,1
    arm W  response_text   1,2,3   injection=1  marker=1,1,1
    arm W  fingerprint     1,2,3   injection=1  marker=0,0,0

Zero injections across arm H is the load-bearing check: with symptoms dropped
from `triggers.json`, the skill arrived by one path only. A marker credited to
a skill with no injection row is itself proof of hot delivery —
`reconcile._credit_markers` credits an uninjected skill only when `index.json`
says `tier: hot`.

**Arm H response_text run 1's ledger was overwritten before it was read** and
is not in the table. Both arms pass `--arm treatment`, so their clones and
ledgers shared a path; the arm W batch deleted arm H's run-1 database. Fixed
(`-hot` in the path), but that run's delivery is unverified. Its score stands.

Marker rate: 4/5 in arm H, 3/6 in arm W. Do not read that as arm H being used
more. Marker capture is a compliance signal with known drift, n is 5 and 6,
and arm W's fingerprint cell logged zero markers while resolving one of three.

`skill_note` is not a delivery record. It reports `indexed: warm tier` for
every arm H row, because `save_skill._warm_reason` tests for the *nested*
path that the lever deliberately no longer writes. Cosmetic; the ledger is the
record.

## Two harness defects found on the way, both fixed

**Per-run ledgers were reused across batches.** `SKILLFORGE_LEDGER` points
outside the clone, so `prepare()`'s rmtree never cleared it, and a re-run of
the same task/arm/run index read the previous batch's rows as its own. E5
spent its first pass reading E1's 04:49 injections as evidence about its own
sessions. `one()` now deletes the database (and `-wal`/`-shm`) before the run.

**The task repo is SkillForge, and the model runs its test suite.** The
`response_text` prompt ends with "run `python3 tests/test_detect.py`", and the
model generalises: run 1's transcript shows `for t in tests/test_*.py`. The
clone's own `tests/test_save_skill.py` then evicted the materialized native
copy mid-session and rewrote the user-global `index.json` to `tier: warm`.
Timestamps put every eviction inside the session window, after the model had
finished implementing, so the scores stand.

Root cause, and it was never a bench problem: `save_skill.py`'s
`--project-root` defaults to `"."`, and `main()` syncs that root — so a save
run from any directory treats **the current working directory** as a project.
The suite sandboxed `HOME` but not cwd, so `sync()` judged the real cwd's
store against a trust store living in the sandbox, found nothing trusted, and
evicted. Running SkillForge's own test suite inside any project deleted that
project's hot skills. Fixed in 0.2.5: `in_sandbox` chdirs into the sandbox in
every test file that has one (`test_stats.py` already did — the rest now
match), with a regression test asserting cwd is isolated and restored.

## Limits

- **n=3 per cell.** Two measurements of arm W came back 6/6 and 4/6.
- **Two traps, one skill, one repo.** The fingerprint cell is where all the
  variance lives; `response_text` was 3/3 in all four treatment cells today.
- **The hot body is not byte-identical to the warm one.** `sync.py` appends a
  modified `MARKER_NOTE` ("this skill" rather than "a skill above") to the
  materialized copy. Inherent to hot delivery, so part of the treatment, but
  it is a difference.
- **Arm H ran before the path fix landed.** It delivered through the lever's
  own flat directory; 0.2.5 ships the same mechanism at
  `skills/skillforge-<name>/`, differing only in the directory's name. Not
  re-measured under the shipped path.
- **Bench sessions inherit the operator's full plugin set** (ponytail,
  superpowers). Constant across arms; absolute numbers are model-plus-plugins.
- Arm H clones were overwritten by the arm W batch before per-run mechanism
  notes were taken, so there is no "what it wrote" table for E5 as there is
  for E1.

## What this does to the roadmap

- **`/consolidate` is unconstrained by delivery.** E1 cleared consolidation;
  E5 says the emitted form does not have to be an anti-skill to work. Emitting
  anti-skills is still the safer default — it is the path with two independent
  measurements above control.
- **The hot tier works as of 0.2.5 and has never been measured in the wild.**
  Every number the library has recorded about hot skills was collected while
  the tier delivered nothing. `confidence × recent usage` ranking, the 1,500
  token budget, promotion and eviction pressure — all of it is now live for
  the first time, and none of it has evidence behind it yet.
- **E5's original question is answered well enough to stop.** More runs on
  this design buy resolution the n cannot support; a third trap class would
  buy more.

## Reproducing

```bash
cd ~/Developer/skill-forge
python3 bench/run.py --check      # expect: config ok: 10 task(s)

# arm H -- standing native context, symptoms suppressed
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-fingerprint-preexisting-umbrella

# arm W -- symptom injection
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-umbrella
```

`--force-hot` sets `SKILLFORGE_FORCE_HOT=<skill>` per run, the way
`SKILLFORGE_LEDGER` is set. It is refused unless the name matches a skill
exactly, and it does two things that must happen together: forces the tier
hot and materializes, and drops the skill's entries from
`triggers.json["symptoms"]`. Doing only the first delivers the skill by both
paths at once and measures nothing.

E5 rows in `results.jsonl` carry `"delivery": "hot"|"warm"`; E1's rows have no
such key. Timestamp tells the three batches apart, and nothing else does —
all three ran `--arm treatment` on the same two tasks:

| Window (09-06) | Batch |
|---|---|
| 11:17:03 – 11:18:15 | arm H against the undeliverable nested path — **invalid**, kept |
| 11:30:18 – 11:40:08 | arm H, valid |
| 11:41:24 – 11:47:31 | arm W, re-run |

Do not use `resolved` to tell them apart: the valid arm H fingerprint run 1 is
also `false`.

---

# Hot delivery under the shipped path (2026-09-08)

Not a new experiment. E5's arm H established that hot delivery works, but it
ran through the force-hot lever's own flat directory, before `b35f756` moved
materialization to `.claude/skills/skillforge-<name>/`. This is the same arm
re-run under the path 0.2.5 actually ships, so that the one measurement the
hot tier has does not describe a directory nobody will ever use.

## Headline

**Hot delivery works under the shipped path.** Six runs, `--arm treatment
--force-hot`, same umbrella anti-skill, same two tasks: **4/6**. Zero
injection rows across all six ledgers and three marker rows, which is proof of
delivery rather than an inference from the score.

| Measurement | Delivery | response_text | fingerprint | Combined |
|---|---|---|---|---|
| Control — no skill *(pilot)* | — | 0/3 | 0/3 | **0/6** |
| W — symptom injection *(E1, 09-06 00:50)* | warm | 3/3 | 3/3 | **6/6** |
| W — symptom injection *(E5 re-run, 09-06 11:40)* | warm | 3/3 | 1/3 | **4/6** |
| H — lever's flat path *(E5, 09-06 11:30)* | hot | 3/3 | 2/3 | **5/6** |
| **H — shipped path *(09-08 15:16)*** | **hot** | **3/3** | **1/3** | **4/6** |

n=3 per cell. Say so before quoting any of these numbers.

**Do not read a ranking out of that table.** Four treatment measurements of the
same skill on the same two tasks now read 6/6, 5/6, 4/6, 4/6 — and two of them
are the *same* arm measured twice. The spread within one arm is as wide as the
spread across arms, which is exactly what E5 said the design's resolution limit
is. The claim here is delivery, not superiority.

The two arms did **not** share a batch, and never have: this batch ran
`15:16:15 – 15:22:36` on 09-08 against arm W's `11:41:24 – 11:47:31` on 09-06.
`bench/run.py` and `scripts/` are byte-identical between the two — `git diff
b35f756 HEAD -- bench/run.py scripts/` is empty — so the harness is not a
variable, but the batch is.

## The arm was verified before the score was read

All three assertions, at the new path, checked live during run 1 and again
after the batch:

    <clone>/.claude/skills/skillforge-matcher-input-traps/SKILL.md   present
    triggers.json["symptoms"]                                        []
    index.json                        matcher-input-traps  tier: hot

Then the per-run ledgers. Arm H must show no injection row — the harness
injects native skills and SkillForge never sees it:

    response_text     run 1   injection=0   marker=0
    response_text     run 2   injection=0   marker=1
    response_text     run 3   injection=0   marker=1
    fingerprint       run 1   injection=0   marker=1
    fingerprint       run 2   injection=0   marker=0
    fingerprint       run 3   injection=0   marker=0

Zero injections across all six, with `symptoms` empty, means the skill arrived
by one path only. The three marker rows are the positive evidence:
`reconcile._credit_markers` writes a marker for an uninjected skill **only**
when `index.json` says `tier: hot` (`scripts/reconcile.py:303`), so each one is
a session in which the hot entry was live at Stop time. Marker rate 3/6, in the
same range as E5's 4/5 and 3/6 — a compliance signal with known drift, not a
usage rate.

Two side confirmations fell out of the batch:

- **The materialized copy survived every session.** All six clones still hold
  `skillforge-matcher-input-traps/` after the run. The `response_text` prompt
  makes the model run this repo's test suite, which before 0.2.5 evicted the
  project's hot skills mid-session; the cwd-isolation fix holds.
- **`skill_note` is now accurate.** E5 recorded it printing `indexed: warm
  tier` for every arm H row, because `save_skill._warm_reason` tested for the
  nested path. Every row in this batch reads `materialized:
  .../.claude/skills/skillforge-matcher-input-traps/SKILL.md`.

## What this does *not* validate

Delivery is the only thing measured here. The hot tier's other four mechanisms
were all bypassed or never loaded:

- **Promotion order and the `trusted`/`working` gate.** The lever forces the
  tier directly; `index.json` read `bucket: unproven` in every run. Nothing
  earned hot.
- **The 1,500-token budget.** One skill at `est_tokens: 1015` against a 1500
  budget. The budget never bound, so nothing exercised it.
- **`confidence × recent usage` ranking.** Ranking needs two candidates. There
  was one.
- **Eviction pressure.** Nothing competed for the budget, and no skill was
  demoted.

Those remain what §3.1 of the handoff called unevidenced, and this batch does
not move them.

## Limits

- **n=3 per cell**, and the resolution limit above swallows any difference this
  design could report between delivery paths.
- Same two traps, one skill, one repo as every other cell in this file. The
  `fingerprint` cell is where all the variance lives — `response_text` has now
  been 3/3 in five consecutive treatment cells.
- The hot body still is not byte-identical to the warm one (`sync.py` appends a
  modified `MARKER_NOTE`). Inherent to hot delivery, part of the treatment.
- Bench sessions inherit the operator's full plugin set (ponytail,
  superpowers). Constant across arms; absolute numbers are model-plus-plugins.
- `index.json` is user-global and last-writer-wins. It held only
  `matcher-input-traps` throughout this batch, which is *why* the markers were
  credited — and equally why an unrelated session running anywhere on the
  machine could have silently cost this batch its only usage signal.

## Reproducing

```bash
cd ~/Developer/skill-forge
python3 bench/run.py --check      # expect: config ok: 10 task(s)
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-fingerprint-preexisting-umbrella
```

These six rows in `results.jsonl` carry `"delivery": "hot"` with `ts` on
`2026-09-08`; E5's hot rows carry the same key on `2026-09-06`. Timestamp is
still the only thing that separates batches.

---

# Q1 — does the distiller work end to end? (2026-09-09)

## Headline

**Yes, when it emits — and it emits a third of the time.** Twelve draws, four
saved drafts, and every one of those four took its task from a control floor of
**1/6** to **12/12**. The eight that produced nothing were refused by the
novelty gate, not by a bug: every session fixed its bug, none timed out, none
was refused by the API, and `save_skill` rejected nothing.

The pipeline's bottleneck is **emission**, not delivery and not content. Q1 was
designed to ask whether a distilled skill helps a later session. Two-thirds of
the time there is no distilled skill.

| Stage | Result |
|---|---|
| draws | 12 |
| repair resolved | 12/12 |
| draft written | 4/12 — the other 8 aborted on the novelty gate |
| `save_skill` accepted | 4/4 |
| delivered downstream | 12/12 probe runs, all `trigger: prompt`, all `tier: warm` |
| task resolved | **12/12** |

n=3 per cell. Say so before quoting any of these numbers.

## The scores

| Arm | response_text | fingerprint | Combined |
|---|---|---|---|
| **Distilled** | **9/9** (3 drafts × 3) | **3/3** (1 draft × 3) | **12/12** |
| Control — this batch, pinned model | 1/3 | 0/3 | **1/6** |
| Transfer *(secondary, brief Q2)* | 0/3 | 0/3 | **0/6** |
| Hand-authored, matched *(2026-08-11, model unrecorded)* | 3/3 | 2/3 | 5/6 |
| Hand-authored, matched *(2026-09-05)* | 3/3 | 3/3 | 6/6 |

The ceiling comparison is **directional only**, as pre-registered. Distilled
matches or exceeds the hand-authored cells on both traps, but the distilled
column is 12 runs over 4 drafts against 6 runs over 2 skills, and this design's
own resolution limit is one arm spanning 6/6 to 4/6.

**The floor is not zero, and that matters.** The fresh control resolved 1 of 6 —
`response_text` run 1 — where the 2026-08-11 figure was 0/6. Both are small n;
the point is that these tasks are not strictly impossible cold, so 12/12 is a
real gap rather than a comparison against an artificial floor.

## Emission is a trap property, not a distiller property

|  | `learn-failure` | `learn` |
|---|---|---|
| Trap A — `json.dumps` escaping | **3/3 saved** | 0/3 |
| Trap B — truncated search | 0/3 | **1/3 saved** |

The direction inverts between traps, which at n=3 would ordinarily read as
noise. The archived reasoning says otherwise, and it is consistent within each
cell.

Trap A throws loud, distinctive assertion failures, so literal `symptoms:`
exist to be written and the anti-skill distiller emitted every time. Trap B is
silent. Every trap-B anti-skill draw refused on that ground, in its own words:

> "This bug surfaces as a bare `AssertionError` and a wrong integer in a
> database column. **Any `symptoms:` list would be invented**, and invented
> triggers pollute the detection index that the PostToolUse hook matches
> against."

> "The trap's defining property is **silence**. It emits no exception and no
> message."

The distiller would rather emit nothing than invent a trigger. That is the
anti-skill contract's symptom requirement doing exactly what it was written to
do — and it means **the anti-skill path is structurally unavailable for
symptomless traps**, which is a design finding, not a quality one.

The `/learn` arm declined trap A three times, twice citing the contract's own
step 8 — a verification that fails when the procedure is skipped would here be
this repo's test command, which means nothing in another repo.

## The aborts are unfalsifiable in this design

"A fresh Claude would already know this" is a claim the model makes about
itself. The only place it could be tested is this bench, and the eight rejected
drafts are never probed. The gate could be systematically over- or
under-refusing and Q1 cannot tell.

There is a specific reason to suspect over-refusal: control resolves these
tasks **1 in 6**. The distiller declined to record knowledge that the model
demonstrably fails to apply five times out of six. Those are different
epistemic positions — the distilling session had just fixed the bug with a
failing test in front of it, the author session starts cold — but the tension
is real and it is the most interesting thing this experiment surfaced.

Testing it means saving a rejected draft anyway and probing it. That is a
different experiment and nobody has specified it.

## What the judge found

All four drafts pass critique. Then it gets worse.

| Draft | critique | symptom shape | verification discriminates | fingerprints in the real fix |
|---|---|---|---|---|
| A/`learn-failure`/1 | pass | signature | **no** | 0/2 |
| A/`learn-failure`/2 | pass | signature | *(none declared)* | 0/2 |
| A/`learn-failure`/3 | pass | signature | *(none declared)* | 0/2 |
| B/`learn`/1 | pass | *(none — `kind: skill`)* | **no** | 1/3 |

**Not one declared verification command discriminates.** Both point at this
repo's own suite, and at `fix_commit~1` that suite *passes*, because the tests
that expose the trap do not exist yet. The command proves nothing. This is the
first time that bar has been checked by machine, and the distiller failed it
twice out of two — after articulating the exact failure mode in the arm where
it refused to emit at all.

The two blanks are legitimate: `verification.command` is optional for
anti-skills (`save_skill.py:145` requires it only for `kind: skill`), and all
four hand-authored comparators declare none either.

**Fingerprints are nearly all wrong.** One of nine appears in the reference
fix's added lines. Fingerprint-based usage detection would be blind to these
skills in production — they would be delivered, used, and invisible to outcome
tracking.

So: the drafts that scored 12/12 carry attribution machinery that does not
work. Helpfulness and instrumentation came apart completely, which is precisely
why the judge is reported beside the funnel and never merged into it.

## Symptom shape, and an asymmetry the comparators lose

Every trap-A draft emitted machine signatures — `assert injected_names(out) ==
["widget-trap"]`, `FAIL test_... AssertionError` — as `distilling-failures`
step 4 demands. Both hand-authored comparators are narration
(`"confirmed absent without examining the full input"`), in violation of the
same contract they are held against. Threat §7.9 predicted this from reading
the code; it is now observed.

It costs the distilled skills nothing here, because symptoms are structurally
dead in author mode: the grading tests are not in the tree during a probe
session, so no trap signature ever appears in tool output. Delivery fell to
BM25 over `name + description`, as designed — and the pre-registered dry run
predicted `deliver` for all four (9–14 matched terms against a threshold of 2)
**before any probe ran**. All four delivered.

## Secondaries

**Transfer (brief Q2): 0/6**, against this batch's own 1/6 floor. A same-class
skill from a different instance is indistinguishable from no skill, replicating
the pilot's 0/6 — and for the first time against a floor measured in the same
batch on the same pinned model, which is what folding it in here bought.

**Q5 (does the `trusted` gate predict anything): no split available.** Critique
passed all four distilled drafts, so there is no failing group to compare
against. Pre-registered in spec §8 before any verdict existed; reported as
uninformative rather than dropped.

## Limits

- **n=3 per cell**, and the emission counts are 3 per cell too — the 3/3 vs 0/3
  inversion between traps rests on three draws each.
- **Two traps, one repository**, both in SkillForge's own codebase.
- **The eight aborts are untested**, see above. This is the largest gap.
- **The distilled column is not n-matched to the ceiling column** (12 runs over
  4 drafts vs 6 runs over 2 skills).
- **Same-author curation is only half fixed.** The distiller wrote the skills;
  the operator still wrote the tasks and chose the traps.
- **The repair source hands over the answer** — a red assertion names the
  condition — so a distilling session sees more than a cold one would.
- Bench sessions inherit the operator's full plugin set (ponytail, superpowers).

## Containment

Sixty sessions. At close: global store empty, global index empty, `trust.json`
holding exactly the operator's two skills. The operator's project index entries
were clobbered by the clones' wholesale rewrites — the §7.7 leak, expected —
and restored with the single `sync.sync(project_root=...)` that spec §4(d)
prescribes. `drift()` clean afterwards.

Four saves reached the real library and all four were reverted: one chose
global scope and was removed with `library.py delete`; three chose project
scope and left only a trust key, caught by `new_trust_keys`. Both containment
paths fired in the first cell.

## Reproducing

```bash
cd ~/Developer/skill-forge
python3 bench/run.py --check
python3 bench/distill.py --all --draws 3      # phase 1: 12 sessions
python3 bench/dryrun.py                       # predictions, BEFORE probing
python3 -c "..."                              # probes; see plan Task 9 Step 4
python3 bench/run.py --arm control --runs 3 --task sf-author-response-text
python3 bench/run.py --arm control --runs 3 --task sf-author-fingerprint-preexisting
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-transfer
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-transfer
python3 bench/judge.py                        # 1 critique session per saved draft
```

Rows carry `skill_source: distilled` with `distiller` and `draw`; phase-1
outcomes and the judge's verdicts are in `bench/distilled/*/*/*/meta.json`,
committed. Twelve probe rows dated 2026-09-09 were preceded by twelve that
never ran — `--skill-from` was passed relative and `install_skill` shells
`save_skill.py` with `cwd` set to the clone, so every one died before its
session started. No row was written; fixed in `skill_src`.

---

# E6 — does an irrelevant skill dilute a relevant one? (2026-09-10)

Design and pre-registration:
`docs/superpowers/specs/2026-09-09-e6-dilution-design.md`. This is the re-run;
the 2026-09-09 attempt lost 9 of 12 sessions to a rate limit and is described
under "The first attempt" below.

## Headline

**No dilution detected. Both arms scored 6/6.** An irrelevant skill that
arrives, outranks the relevant skill, and occupies 45% of the injection budget
cost nothing measurable on either task.

| Arm | Skills installed | `response_text` | `fingerprint` | Total |
|---|---|---|---|---|
| **R** — relevant alone | the task's matched hand-authored anti-skill | 3/3 | 3/3 | **6/6** |
| **R+I** — relevant + irrelevant | that skill **and** `arrow-tzinfo-string-trap` | 3/3 | 3/3 | **6/6** |

**n=3 per cell**, 6 per arm, 12 sessions in one batch, arm R first. Zero
sessions excluded: all 12 carry `session_ok: true`. Model `claude-opus-5`,
warm tier, `trigger: prompt` on every injection.

This is the outcome §6 of the design calls "R+I ≈ R, both near ceiling": the
strongest available evidence that injection does not hurt. It does **not**
answer E4, which asks about an irrelevant skill versus *nothing*.

## The pre-registered checks, in order

§5 fixed four rules before any data existed. All four are satisfied.

- **Arm R reproduced its ceiling.** 6/6. §5 required that a failure here be
  the headline and the comparison be called uninterpretable. It did not fire.
- **Both arms ran in one batch, R first.** 01:18:22 to 01:31:34, 13 minutes,
  837 session-seconds.
- **All 12 sessions ran and no cell was dropped after its score was seen.**
- **No run measured crowd-out.** Every one of the 6 arm R+I runs injected
  **both** skills; every arm R run injected exactly one. The §5 rule that a
  single-injection run is reported separately and never pooled has nothing to
  report. Crowd-out and dilution are told apart from the injection rows, as
  §4 requires, not inferred from the score.

## The bad case was worse than the design claimed

The design's §3 viability table has `arrow-tzinfo-string-trap` outranking the
relevant skill on `response_text` (2.53 to 1.87) but narrowly *losing* on
`fingerprint` (2.53 to 2.55). Re-derived against `retrieve.rank` over the pool
each arm actually installs — the two skills present in the clone, not a larger
index — the irrelevant skill ranks **first on both tasks**:

| task | irrelevant | relevant |
|---|---|---|
| `sf-author-response-text` | **3.102** (7 matched) | 1.709 (5 matched) |
| `sf-author-fingerprint-preexisting` | **3.102** (7 matched) | 2.883 (6 matched) |

BM25 is corpus-relative, so the two tables are not in conflict — they rank
against different pools, and the design does not say which one it used. The
pool above is the one the experiment ran on. The qualitative claims the design
rests on both hold, and the realistic-bad-case argument holds *more* strongly
than it was written: the irrelevant skill was ranked first, injected first, and
still cost nothing.

## Budget occupancy, re-derived

The 93% figure is what makes this a dilution test rather than a crowd-out test,
so it was re-checked rather than inherited. `INJECT_BUDGET_TOKENS` is 1200 and
injection cost is `len(body) // 4`:

| skill | cost |
|---|---|
| `serialization-corrupts-matching` (relevant, rt) | 574 |
| `lossy-transform-false-negative` (relevant, fp) | 561 |
| `arrow-tzinfo-string-trap` (irrelevant) | 544 |

Pairs cost 1118 (93%) and 1105 (92%). All three payloads are `kind:
antiskill`, so `MAX_SKILLS = 3` — which caps non-anti-skills only — never
applied. The injection rows confirm the arithmetic: both skills arrived every
time.

## The first attempt (2026-09-09), and why it is postponed rather than poisoned

The 09-09 batch produced 3 valid rows and 9 with `session_ok: false`, the
latter written at 3-second intervals as `claude -p` exited 1 on the session
limit. They stay in `results.jsonl`, which is append-only, and the §8
`session_ok` exclusion rule — pre-registered before any E6 data existed — keeps
them out of every cell here. One excluded row records `resolved: true`; that is
exactly the false claim the rule exists to suppress.

Its 3 valid rows are arm R on `response_text`, 3/3. They are **not** pooled
into the cells above. E5 established that this design's cross-batch spread on
a single arm (6/6 versus 4/6, nothing changed but the batch) exceeds the
effects it can resolve, which is why §1 requires one batch.

## Limits

1. **n=3 per cell.** Six sessions per arm. Both arms at 6/6 rules out only a
   large effect: if R+I's true rate were 50% it would read 6/6 about 1.6% of
   the time, but at 75% it would read 6/6 about 18% of the time. A moderate
   dilution is entirely compatible with this result. A null here is "no large
   effect", never "no effect".
2. **Ceiling design.** The comparison measures a fall from a ceiling, so it can
   see harm and cannot see benefit. Arm R+I is already at the maximum.
3. **One irrelevant payload.** `arrow-tzinfo-string-trap` is one skill about
   one unrelated bug. A different irrelevant skill could dilute more.
4. **93% occupancy is a knife edge.** A longer irrelevant payload converts this
   into a crowd-out test. The measured figures above are what make the design
   valid today; re-check them if any payload changes.
5. **Two tasks, one repository**, both traps in SkillForge's own codebase, and
   the operator wrote the tasks, the traps, and both payloads.
6. Bench sessions inherit the operator's full plugin set, so absolute numbers
   are model-plus-plugins. The contrast is within one batch and holds.
7. **Latency carries no signal either, and should not be read as one.** Arm
   R+I took 396 session-seconds against arm R's 442. At n=6 with a ~50s spread
   inside each arm, that difference is noise, not a token-cost finding. Q4
   still has no experiment.

## What this does *not* validate

E4 (irrelevant versus nothing) is untouched and still blocked. This result
makes E4's floor problem less urgent without answering it. Q4 — token cost per
unit of benefit — is out of scope by §8; E6 measures whether a second skill
hurts, not what it costs. The hot tier injects unconditionally and at a 1,500-
token budget, and its ranking, promotion and eviction remain unevidenced; this
result is about the warm path at 1200 tokens.

## Reproducing

```bash
python3 bench/run.py --check
I="$PWD/bench/skills/arrow-tzinfo-string-trap.md"
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text --plus-skill "$I"
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting --plus-skill "$I"
```

Arm R+I rows carry `extra_skills: ["arrow-tzinfo-string-trap"]`; arm R rows
carry `extra_skills: []`. Both arms pass `--arm treatment`, and `--plus-skill`
is what puts `-plus` in the clone path segment — without it the two arms would
share a clone and the second batch would overwrite the first, as happened once
in E5. The 12 rows are dated `2026-09-10T01:18` to `01:31`.
