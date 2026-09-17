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
| E4 | Does injecting an *irrelevant* skill actively hurt? (= brief Q3) | **Partly answered by E12 (2026-09-13): no large harm on repair-mode tasks at ceiling**, C 12/12 against I 12/12. The author-mode version still cannot run, because no author task has headroom (`fingerprint_preexisting` 0/21, `response_text` retired). The old framing, "needs a mid-range task", was the error: measuring harm needs a ceiling, not a middle. The graded scorer did not unblock it | E12's rows and spec; the original `sf-author-*-irrelevant` tasks were never run |
| E5 (2026-09-06) | Is the effect the knowledge, or the delivery path? | **Answered.** hot 5/6, warm 4/6, control 0/6 — two measurements of one arm differ by more than the arms do, so content carries it and no ranking is claimable | `results.jsonl`, the 15 rows dated 09-06 carrying `"delivery"` |
| Hot under the shipped path (2026-09-08) | Does hot delivery still work after `b35f756` moved the materialization path? | **Confirmed.** 4/6, zero injection rows, three markers. Delivery only — ranking, budget, promotion and eviction remain unevidenced | `results.jsonl`, the 6 rows dated 09-08 |
| Graded scoring (2026-09-10) | Can this bench resolve anything smaller than all-or-nothing? | **Probe half partial, judge half no.** 20 probes over 42 archived artifacts, 0 sessions: falsifier did not fire, the scale is unpinned from zero, but the graded score reproduces the binary `resolved` verdict in 40 of 42 rows — the unblocking of E4 is provisional, not established. The judge's 42 sessions produced a clean negative — its criteria discriminate between tasks, not artifacts (r = -0.308) | `bench/graded.jsonl` (42 rows), `bench/authored/` (54 diffs) |
| E7 (2026-09-11) | Is the distiller's novelty self-gate over-refusing? | **Answered: yes.** Suspending step 2 alone took emission from 1/6 to **6/6**. Those six drafts scored **16/18** against a same-batch control of **0/6** — every one of the six beat the floor. n=3 per cell, and the 18 runs are 6 artifacts × 3, not 18 independent draws | `bench/distilled/*/learn-nogate/` (6 draws), the 24 rows in `results.jsonl` dated 2026-09-11, 24 `batch: e7` rows in `bench/graded.jsonl`; the 2026-09-10T21:01 control row is **excluded** (spec §5.1) |
| E8 (2026-09-11) | Does retrieval survive a library of ten? | **Answered, and the mechanism is not the one predicted.** M 3/3, L 3/3, C 0/3 on **both** tasks. On `response_text` the prompt path delivered a **wrong-trap** skill 3/3 and the **symptom path rescued it** 3/3. The rescue rides on anti-skills, which cannot exist for a silent trap — so the dangerous case was never tested. First attempt refused at the session limit and excluded | `results.jsonl`, the 18 rows dated 2026-09-11 after 00:50 carrying `extra_skills` of 9 or 0; 18 `batch: e8` rows in `bench/graded.jsonl`; the 13 refused + 5 valid rows of the 00:41–00:46 attempt are **excluded** (spec §4.1) |
| E9 (2026-09-11) | Does a consolidated skill still work? | **Answered: yes, and it fits.** Merges compressed 3 and 2 skills to **44%** and **54%** of their concatenation, landing at 1095 and 1088 tokens against a 1200 budget. R 3/3, K 3/3, C 0/3 on both tasks, zero exclusions. n=3 per cell, and every trap-A member was already at ceiling so that half could only hold or fall | `bench/distilled/*/consolidated/1/`, the 18 rows in `results.jsonl` dated 2026-09-11 after 15:10, 18 `batch: e9` rows in `bench/graded.jsonl` |
| E8 follow-up (2026-09-11, **re-run 2026-09-13**) | Does consolidating the library fix E8's ranking failure? | **It didn't then. It does now.** Under the original tokenizer the correct skill fell from rank 3 (8.40) to rank 5 (4.70) after merging, and only rank 1 ever injects. After `9cbb472` dropped function words, the consolidated seven put the matching trap at rank 1 on **both** tasks, while the unconsolidated ten still miss `response_text`. The old result came from the function-word defect, not from consolidation itself | `bench/rank_check.py` — deterministic, 0 sessions |
| Budget derivation (2026-09-11, re-run twice 2026-09-13) | What injection budget delivers a *correct* skill? | **The shipped 1200, on a consolidated library.** The 2026-09-11 reading (3000, dipping at 2400) came from skip-and-continue, and under `break` it read 2000. After `9cbb472` dropped function words, the consolidated seven are correct on both tasks from **1200** and hold above it. The case for raising the budget was largely a ranking defect. The unconsolidated ten still need 3000 | `bench/budget_sweep.py` — deterministic, 0 sessions |
| Selector monotonicity (2026-09-11, **fixed 2026-09-13**) | Why is the budget curve not monotonic, and what fixes it? | **Diagnosed and shipped.** Skip-and-continue broke set monotonicity at 15 of 69 budget steps and flipped the correct skill away at 3. `retrieve.run_hook` now stops at the first entry that doesn't fit: **0 flips, 0 shrinks**. A score-maximising subset did **worse** (8 flips, 57 shrinks) and was rejected. The lowest stable budget was ten 2900 / seven 1850. After `9cbb472` it is ten 2800 / seven **1100**, and `break` still scores 0 and 0 | `bench/selector_check.py` — deterministic, 0 sessions |
| E10 (2026-09-13) | Does a wrong-bug skill hurt at prompt time beside the right one? | **Half answered, half void.** `fingerprint`: M 3/3, P 3/3, S 3/3, C 0/3 — no large prompt-time harm at 1847 tokens with a wrong-bug skill alongside, n=3. But that task ranks the **correct** skill first. `response_text`, which ranks the wrong one first and is the case that motivated raising the budget, is **void: control resolved 3/3, and 3/3 again on a dedicated re-measure — 6/6 against a 1/13 history. The task is retired as a discriminator.** Prompt-path delivery matched the pre-registered prediction **12/12** | `results.jsonl`, the 24 rows dated 2026-09-13; `bench/authored/e10-*.diff` (24); spec `docs/superpowers/specs/2026-09-11-e10-prompt-time-budget-design.md` |
| E11 (2026-09-13) | After `response_text` was retired, can either never-run task serve as a discriminator? | **Answered: no — both rejected.** A 6/6, B 6/6 control at n=6 each: **ceiling, not marginal**, every graded test green in every session. Same-batch reference R held at 0/3 (**0/21** lifetime), so the screen is valid. Repair mode shows the model the failing tests and is structurally the weaker trap, exactly as §4.4 pre-registered. **The bench now has exactly one trap.** The two rejects have maximum headroom to fall, which may make them *harm* detectors for E4 — a proposal, not a result | `results.jsonl`, the 15 rows dated 2026-09-13 after 13:36; spec `docs/superpowers/specs/2026-09-13-e11-trap-screening-design.md` |
| Delivery gate (2026-09-13, **fixed same day**) | Does the retrieval gate discriminate at all? | **It didn't. Fixed in `9cbb472`.** Before the fix, all 16 skills cleared `score > 0 and matched >= 2` on all four task prompts and on a control prompt about a cat, because function words scored as topic: common ones opened the gate and rare ones decided rank 1. `tokenize` now drops a fixed stopword list (NLTK english plus `use`). A frequency-based filter was rejected because it would admit nothing in a one-skill library. After the fix: the cat 0/16, real prompts 5–10/16, the correct trap at rank 1 on 3/4 prompts (was 2/4), dedupe unchanged | `bench/gate_analysis.py` — deterministic, 0 sessions |
| Real-path delivery (2026-09-13) | Does the real install-and-inject path deliver what the deterministic tools predict? | **Yes, 4 of 4.** Both pools went in through the real `save_skill.py` under a sandboxed HOME, and the real hook ran before and after `9cbb472`. On the consolidated library, `response_text` went from the wrong trap to the right one. The unconsolidated ten stayed wrong, and `fingerprint` was right both times. No session batch followed, because no current task can show an outcome change | `bench/real_path_check.py` — deterministic, 0 sessions |
| E12 (2026-09-13) | Does an irrelevant injected skill actively hurt? | **No large harm.** C 12/12, relevant R 12/12, irrelevant I 12/12 — 6/6 in every cell, zero exclusions, one environment. The pre-registered §4.4 caveat governs: repair-mode tasks show the model its failing tests, so this cannot tell "no harm" from "the tests rescued it". Answers E4 for repair mode at ceiling only. Third consecutive harm null, after E6 and E10 | `results.jsonl`, the 36 rows from 2026-09-13T17:36:28; `bench/e12_read.py`; spec `docs/superpowers/specs/2026-09-13-e12-irrelevant-injection-harm-design.md` |
| E13 screen (2026-09-14) | Do any of three new author-mode traps (C `verdict_from`, D `transcript_slice`, E `store_dir`) have a zero control floor? | **Answered: C only.** C 0/6, **admitted**: every session passed 14 of 15 graded tests and failed exactly `test_a_rewrapped_quote_still_counts_as_evidence`, the historical byte-exact-match bug. D 6/6 and E 6/6 were **rejected** at ceiling, so their docstrings suffice. Same-batch reference 0/3 (**0/24** lifetime), so the screen is valid. No injections on any row; every clone's history was stripped to a single fresh baseline commit, with the plugin under test at `4df0d02`. C's second trap (floor measured on the raw span) never sprang | `results.jsonl`, the 21 rows dated 2026-09-14 after 09:36:06; spec `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md` §3 |
| E13 trap C (2026-09-14) | Does a skill distilled from trap C make its author task pass, and can C carry the tokenizer outcome test? | **Answered: no — C is not a working trap, so the outcome test did not run.** Distillation saved 6/6 draws, every repair resolved. Qualification: `learn-failure` 1 and 3 qualify (the old tokenizer misses them, the new one delivers them); 5 of 6 are deliverable alone. Probe, one fresh batch after a postponed attempt: control 0/3, the three `learn` skills **1/9**, the two `learn-failure` anti-skills **6/6**; pooled **7/15**, one short of the pre-registered half. The skill/anti-skill split is exploratory, not pre-registered. Under §6, C serves neither trap 1 nor trap 2, and both go back to the candidate list | `bench/distilled/C/` (6 draws + `qualification.json`); `results.jsonl`, the 18 rows after 2026-09-14T14:31:15. The 15 rows from 14:09:15 to 14:24:53 are the attempt postponed at the session limit and are **excluded** |
| E14 stage 1 (2026-09-14) | On trap C, does a draft's trigger wording (failure-time vs write-time) or its kind (skill vs anti-skill) decide whether the author session applies the fix? | **Answered: neither reaches the pre-registered bar.** Four hand-written drafts carrying the same fix: skill-failure 4/6, skill-write 5/6, anti-failure 6/6, anti-write 6/6, control 0/3, zero repeats or exclusions. Trigger **+1** (no large effect, p = 1.000); kind **+3** (ambiguous, p = 0.217). The baseline **moved**: skill-failure resolved 4/6 where E13 predicted at most 1, so rewriting the E13 skill draft recovered most of its failure on its own. Stage 2 is not triggered | `results.jsonl`, the 27 rows after 2026-09-14T21:03:29; `bench/drafts/E14/` (+ `delivery.json`); `bench/e14_read.py`; spec `docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md` |
| E14 drafts as trap 2 (2026-09-14) | Can any E14 draft carry the tokenizer outcome test (old hook `06885c0` misses it, new hook `9cbb472` delivers it)? | **No — 0 of 4 qualify.** Installed with the consolidated seven through the real `save_skill.py` into a sandboxed HOME, every draft was delivered by the old hook, the new hook and HEAD alike. The rewrite names `validate.verdict_from` up front, which ranks it first even under the pre-fix tokenizer. The outcome test stays blocked; the operator's library was untouched | Throwaway spike, not committed (E13 qualification method via `e13_qualify` helpers) — deterministic, 0 sessions |
| E15 (2026-09-16) | Do three writing rules for the skills distiller (no test names, write the Procedure for first-time code, name the function up front) make its drafts work on trap C's author task? | **Answered: yes — the rules help.** Six drafts distilled under the variant rules resolved **18/18**; E13's three skill drafts, re-probed in the same batch, **0/9**; control 0/3. d = **+1.00**, Fisher p < 0.001. Every variant draft obeyed all three rules, and every baseline draft broke all three. Per spec §5 the rules go into the shipped `distilling-skills` as their own reviewed commit. Two probe batches were cut off at the session limit and are **excluded**; spec amendment 4 (pause and resume) came before the third | `results.jsonl`, the 32 rows after 2026-09-16T10:06:14 (the 15 rows 2026-09-15 12:10:52–12:26:06 and the 25 rows 19:56:46–20:26:39 are **excluded**); `bench/distilled/C/learn-e15-nogate/` + `e15-probe.json`; spec `docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md` |
| E16 screen (2026-09-16) | Do either of the two remaining well-shaped fix commits (F `read_markers`, G `event_totals`) have a zero control floor? | **Answered: no — both rejected.** G 6/6, ceiling, like E13's D and E. F **1/6**, and the five unresolved sessions each failed **exactly** `test_read_markers_skips_junk_without_losing_good_lines` and nothing else — the trap springs, but not reliably, and a non-zero floor rejects. Same-batch reference 0/3 (**0/28** lifetime), so the screen is valid. First batch to pause at the session limit and resume (E15 amendment 4): one environment across a 2h45m gap. Corrects the register: the bench had **two** working traps before this screen, not one | `results.jsonl`, the 16 rows after 2026-09-16T11:44:14 (one `session_ok: false` limit cut-off, re-run in place); spec `docs/superpowers/specs/2026-09-16-e16-author-traps-design.md`; `bench/e16_preflight.py`, `bench/e16_screen.sh`, `bench/e16_screen_read.py` |
| Q4 token cost (2026-09-16) | What does a unit of benefit cost in injected tokens? (= brief Q4) | **Answered, and the two traps agree without being made to: ~1,100 tokens per additional resolved run** — 1,100 on `fingerprint_preexisting`, 1,091 on `verdict_from`, across five experiments. Hand-written drafts are the cheapest by far (E14's four at 503–510 tokens, 42% of budget, best price **507**); distilled drafts cost 647–1,192 (up to **99% of the 1,200 budget**, eight tokens of headroom). Two E13 baseline drafts are bill-only: ~18,500 tokens for zero resolutions | `bench/q4_token_cost.py` — deterministic, 0 sessions. Prices only tasks whose control floor is measured at zero, which it derives rather than hardcodes |
| E17 (2026-09-16) | Does the critique conjunct of the `trusted` gate predict whether a skill works? (= brief Q5) | **Answered: no, and its verdict is not even reproducible.** 27 calls over E15's nine frozen drafts. **Stability: 5 of 9 drafts gave different verdicts on unchanged text** (4 unanimous, needs 7) — that half is clean and is the finding. On prediction: V (the six drafts that resolve 18/18) passed **4/18**; B (the three that resolve 0/9) passed **6/9**; d = **−0.44**, the pre-registered "predicts backwards" band, Fisher p = 0.039. **But do not read the direction:** spec threat 4 fires completely — the three B drafts are the three *shortest* and the six V drafts the six longest, a perfect rank separation, r(bytes, passes) = −0.70, and dropping one baseline draft moves d to −0.28 (p = 0.307). What survives: critique does **not** prefer the drafts that work. The spec's §4 prediction of a degenerate d ≈ 0 was wrong | `bench/e17-q5-results.json`; `bench/e17_q5.py --read`; spec `docs/superpowers/specs/2026-09-16-e17-critique-gate-prediction-design.md` + amendment 1 |
| Critique calibration | Does the critique rubric agree with hand-established verdicts? | **Run.** 6/7 before a rubric change, 7/7 after | `bench/critique-calibration/` (own README, `expected.json`, 8 result files) |

## The brief's five questions, which are the actual agenda

`docs/2026-08-29-benchmark-investigation-brief.md` ranks five questions by
value. The E-numbers are **not** those numbers. Only E4 maps cleanly.

| Brief | Question | Where it stands |
|---|---|---|
| Q1 | Does the pipeline work end to end, or only the injection half? | **Answered 2026-09-09.** It works when it emits, and it emits 4 times in 12. The four that emitted scored 12/12 against a 1/6 floor. The distiller is no longer the untested link — but the 8 novelty-gate refusals are never probed, so whether the gate is right is a new open question |
| Q2 | Is transfer real at any n? | **Replicated null, still open.** 0/6 in the pilot and 0/6 again on 2026-09-09, the second time against a floor measured in the same batch on the same pinned model. Two nulls at n=6 is not absence at a convincing n |
| Q3 | Does injection ever hurt? | = E4. **Partly answered 2026-09-13 by E12:** no large harm from an irrelevant skill on repair-mode tasks whose tests are visible. Together with E6 and E10 that makes three nulls, so injection has never yet been shown to hurt on this bench. Author-mode harm is still untested, for want of headroom |
| Q4 | Token cost per unit of benefit? | **Answered 2026-09-16, deterministically.** ~1,100 tokens per additional resolved run, and the two working traps agree to within nine tokens. Hand-written drafts price at ~507 and distilled ones at 798–2,142; two drafts have no price at all, only a bill. `bench/q4_token_cost.py` |
| Q5 | Does the `trusted` gate predict anything? | **Answered 2026-09-16 by E17: no.** Critique's verdict is not reproducible on unchanged text — 5 of 9 drafts flipped across three calls — and it does not prefer the drafts that work (V 4/18 against B 6/9). The negative *direction* is not claimable: draft length is perfectly rank-confounded with the groups. The 2026-09-09 attempt failed for want of a split; E15's drafts supplied one |

## Where the raw rows are

| File | Rows | Live or superseded |
|---|---|---|
| `results.jsonl` | 96 | 9 pilot (trap 2, 2026-08-11) + 18 E1 (09-05, 09-06) + 15 E5 (09-06) + 6 hot-path confirmation (09-08) + 24 Q1/Q2 (09-09) + 12 E6 attempt (09-09, 3 valid and 9 `session_ok: false`) + 12 E6 (09-10). E5's rows and later carry a `delivery` key; nothing before them does. The count read 48 until 2026-09-10 and was stale by 36 rows |
| `results-round1.jsonl` | 18 | **Mixed.** Trap 1's pilot rows are LIVE — the headline table's 0/3, 3/3, 0/3 for response_text come from here. Only trap 2's six rows are superseded by the file-cap repair |
| `results-leaky-stub.jsonl` | 12 | Superseded *as an authoring design* — but it holds the only control data for the two repair-mode tasks, and that data is live |

## Sandbox and audit (from 2026-09-14)

Rows written from 2026-09-14 on carry `sandbox`, `sandbox_profile`,
`session_id` and `audit`. Each session ran under `sandbox-exec`, which denied
it the operator's Developer tree, the other clones and hidden-test caches, and
other sessions' transcripts. It loaded a snapshot of the plugin, never the
checkout. Its transcript was then audited for reads of the plugin's `scripts/`,
which the sandbox has to leave readable because the hooks import them. A row
whose audit is not `clean` counts toward no reader (`bench/audit.py`,
`counts`). Design: `docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md`.

Earlier rows ran unsandboxed and unaudited. Earlier distill sessions were seen
reading `scripts/save_skill.py` and `scripts/validate.py`, but whether they read
the plugin's copies or the clone's own was not recorded. From now on, a draft
whose session read the plugin's copy of its trap's fixed file is marked
`tainted`, and qualification skips it.

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

---

# Graded scoring — the probe half works, the judge half does not (2026-09-10)

Design: `docs/superpowers/specs/2026-09-10-graded-scorer-design.md`.
Plan: `docs/superpowers/plans/2026-09-10-graded-scorer.md`.
Data: `bench/graded.jsonl`, 42 rows, one per surviving archived artifact.

## Headline

**Across 42 artifacts, the 20-probe suite adds one bit about two artifacts
beyond what the binary `resolved` already reported.** Joining the graded rows
to `results.jsonl` on task/arm/run matches 42 of 42. Every `resolved: false`
artifact scores 0.636 (fingerprint) or 0.778 (response_text), without
exception. Every `resolved: true` artifact scores 1.000, except exactly two at
0.889 (`sf-author-response-text-treatment-plus-3` and
`sf-author-response-text-umbrella-treatment-hot-2`). The scale is no longer
pinned at zero — but no artifact has yet demonstrated a score below the
observed floor, so whether an experiment run on this scale can detect a fall
is untested, not established.

**The judge half added nothing and its 42 sessions bought a negative result.**
The three criteria discriminate between *tasks*, not between artifacts.

## Why this was built

`resolved` is `all(per_test.values())`. Three experiments hit the ceiling that
creates: E4 cannot run because a 0/6 control has nowhere to fall by
construction; E6 returned 6/6 against 6/6; E5 measured one arm twice at 6/6 and
4/6.

The cheap option was checked first and does not work. Each task already
declares two `fail_to_pass` tests and every row records `per_test`, so a 0/1/2
scale already exists. Across all 96 rows of `results.jsonl`: 38 at zero, 57 at
two, and **one** in the middle. The existing gradation is degenerate.

## The probe half — 20 probes, zero sessions

`bench/probes/` holds 11 probes for `fingerprint_preexisting` (nine from the
stub contract, two the trap) and 9 for `response_text` (three from the
contract, six from enumerating the input space). `bench/regrade.py` replays
each archived diff onto its base commit, filtered to `scripts/*`, and scores it.

Each suite was gated on two oracles before any artifact was scored: every probe
must FAIL against the stub and PASS at the task's `fix_commit`. Both gates held.

**The falsifier did not fire.** Spec §4 pre-registered that a bimodal
distribution means the design failed and is reported as failed rather than
tuned. Result:

| probe_score | rows |
|---|---|
| 0.636 | 8 |
| 0.778 | 5 |
| 0.889 | 2 |
| 1.000 | 27 |

15 of 42 land strictly between the endpoints. The subsumption invariant holds
on the rows where it is checkable, and the coverage is thin. **The count depends
on the join, so the join is stated here rather than left implicit:** restrict to
the 18 rows whose `segment` is empty (a segmented clone's task/arm/run triple is
not unique), then for each take the **latest by `ts`** among the `session_ok`
rows sharing that triple. That yields **7** artifacts whose matching run
`resolved`, and all 7 pass both of their trap probes — 0 violations.

Joining differently gives a different denominator, which is the point: requiring
a *unique* match instead of the latest one leaves **1** checkable row, because
several batches reuse the same triple. Neither number is wrong; a coverage
figure quoted without its join is not reproducible. The invariant is unrefuted,
not fully checked.

### Control comes off zero, but not off its own floor

| task | control (graded) | matched treatment | control (binary) |
|---|---|---|---|
| `fingerprint_preexisting` | 0.636, flat | 1.000 | 0/6 |
| `response_text` | 0.778, 0.778, 1.000 | 1.000 | 1/6 |

E4 needed a baseline that is neither 0 nor 100%, and the blockage was **the
scorer, not the task** — the diagnosis in the 09-09 handoff §3.2 was right.
But joining these 42 rows back to `results.jsonl` on task/arm/run (42 of 42
match) shows every `resolved: false` artifact sitting at exactly 0.636 or
0.778 and every `resolved: true` artifact at 1.000 except two at 0.889. Across
the whole corpus, nothing has ever scored below that floor. The scale is
unpinned from zero, but "room to fall" is asserted, not evidenced — no
artifact has yet fallen, so whether this scale can detect a fall on a run
where an intervention makes things worse is untested.

Two more things are visible in the graded numbers, at n=3 and not claimed as
findings, but only one of them is *new*:

- **Not new:** transfer sits **at** control on `fingerprint` (0.636) and
  **below** it on `response_text` (0.778 against 0.852). Binary scoring
  already showed this — 0/3 versus 0/3 on `fingerprint`, 0/3 versus 1/3 on
  `response_text` — the graded numbers just add decimal places.
- **New:** E6's R+I arm dips slightly on `response_text`, 0.963 against 1.000,
  where the binary read was a flat 6/6 versus 6/6. This is the one piece of
  information the graded suite surfaced that binary scoring did not.

Matched treatment saturates at 1.000 in every cell measured so far; the floor
moved, the ceiling did not.

## The judge half — 42 sessions, one clean negative

Three criteria, one unsteered `claude -p` turn per artifact, pinned to
`claude-opus-5` and recorded as `judge_model` on every row. 42 verdicts from 42
attempts, **zero** `judge_ok: false` exclusions. The machinery worked.

The criteria do not.

| task | n | judge_score | probe_score |
|---|---|---|---|
| `fingerprint` | 18 | 0.667–1.000 (mean 0.963) | 0.636–1.000 |
| `response_text` | 24 | 0.000–0.333 (mean 0.042) | 0.778–1.000 |

Which criteria ever fire tells the whole story:

| task | explicit_unknown | bounds_documented | visible_degradation |
|---|---|---|---|
| `fingerprint` (n=18) | 18 | 18 | 16 |
| `response_text` (n=24) | 0 | 3 | 0 |

On `fingerprint` the criteria saturate at the ceiling; on `response_text` they
saturate at the floor. **Within either task the judge discriminates nothing.**
Its entire variance is between tasks.

This is a defect in the criteria, which were written into the spec by their
author and are `fingerprint_preexisting`-shaped: that contract names three
unknown conditions and three bounds, so its artifacts all satisfy them, while
`response_text` has no unknown case and one trivial cap.

**The apparent ceiling break was a pooling artifact.** Across all 27 artifacts
the probes tie at 1.000, the judge shows three levels — which reads as the
judge resolving what the probes cannot. Split by task it evaporates: the 10
tied `fingerprint` artifacts are *all* at 1.000, and 16 of the 17 tied
`response_text` artifacts are all at 0.000. One level each.

Pearson r between the halves is **-0.308** — weakly *negative*, driven by the
same task confound. Functionally wrong control code scores 0.889 on
`fingerprint`'s judge criteria while functionally correct code scores 0.000 on
`response_text`'s.

This replicates the Q1 finding that a judge here reached the opposite
conclusion from the scores, and it vindicates spec §3.3's refusal to merge the
halves. The merged `graded` mean reads control 0.594 (n=6) against **matched
treatment alone** 0.778 (n=6) — filtering by arm and segment but not task, as
an earlier pass here did, also pools the `-transfer` tasks into "matched
treatment" and reads 0.691, which is not the matched-treatment figure.
Either way, merging compresses a real 0.636-versus-1.000 probe gap into noise.
**Do not quote `graded`.**

## What it cost, and the lesson

Spec §3.5 specified a calibration corpus for the judge. The plan deliberately
deferred it, arguing that calibration before any judge run would be tuning a
rubric against examples written for it. That reasoning was wrong, and this is
the second time in this project that an argument against a cheap up-front check
turned out backwards.

A fixed corpus with hand-established verdicts spanning **both** tasks is
exactly what `bench/critique-calibration/README.md` argues for, and it would
have exposed task-shaped criteria for a fraction of 42 sessions. The judge half
is not salvageable by re-running it; it needs criteria that mean something for
both contracts, and then calibration before spending again.

## Limits

1. **n=3 per cell**, unchanged by any of this.
2. **One artifact per cell, not one per row.** `prepare()` recreates a clone per
   path segment, so batches re-run under the same segment overwrote their
   predecessors long ago.
3. **The treatment-side ceiling is untouched.** 27 of 42 artifacts tie at a
   perfect probe score, including every matched-treatment cell, so the
   comparisons the bench most wants to make remain unresolvable.
4. **`response_text`'s probes carry a weaker derivation** than `fingerprint`'s:
   six of nine come from input-space enumeration rather than the contract,
   because the stub deliberately withholds the hazard.
5. **The suite is far coarser than 11 (or 9) independent degrees.** Measured,
   not estimated: `fingerprint` shows exactly **2** observed levels (0.636 and
   1.000) across all 42 rows; `response_text` shows **3** (0.778, 0.889,
   1.000). In every low-scoring `fingerprint` row the same four probes fail as
   one block and never independently —
   `test_examines_at_most_snapshot_max_files_candidates`,
   `test_reads_at_most_snapshot_max_bytes_from_one_file`,
   `test_unknown_when_match_past_file_cap`, and
   `test_unknown_when_match_past_byte_cap` — because all four assert `is None`,
   which only truncation-aware code returns; an implementation that honours
   both caps perfectly but reports `0` instead of `None` fails all four. They
   are one probe wearing four names, not four independent degrees.
6. **Spec §3.1's prediction failed.** It predicted probes 1-9 would span the
   middle of the scale while probes 10-11 sat at the top. The observed
   distribution is bimodal at the block level (see item 5) — the middle is not
   spanned, it's a single step. The spec is not edited to match; this failure
   is recorded here only.
7. **A graded score does not by itself unblock E4.** It removes the scoring
   floor. Whether an experiment run on this scale detects anything is untested.

## Reproducing

```bash
python3 bench/probes/probe_fingerprint_preexisting.py <clone_root>   # 11 probes
python3 bench/probes/probe_response_text.py <clone_root>             #  9 probes
rm -f bench/graded.jsonl && python3 bench/regrade.py                 # probe half, 0 sessions
rm -f bench/graded.jsonl && python3 bench/regrade.py --judge         # + judge, 42 sessions
```

`bench/regrade.py` **appends**. Delete `bench/graded.jsonl` before any re-run
or the corpus doubles, which corrupts every n without changing any mean.


# E7 — is the novelty gate over-refusing? (2026-09-11)

Spec and pre-registration:
`docs/superpowers/specs/2026-09-10-e7-novelty-gate-design.md`.

**Yes. The gate refused skills that work.**

Q1's distiller emitted 4 times in 12 and refused 8, every refusal on the same
self-assessment — *a fresh Claude already knows this*. Nothing had ever tested
it, because a refused draft is never written. E7 suspended that one step and
probed what came out.

## What was run

`--no-novelty-gate` replaces one clause of the bench prompt: step 2 of the
distilling contract is suspended, every other step stays in force. **No
product code changed** — neither `skills/distilling-skills/SKILL.md` nor
`save_skill.py` — so the gate under test ships exactly as it is.

| Phase | Arm | Sessions |
|---|---|---|
| 1 | 6 bypass draws, 3 per trap, `learn` only | 6 |
| 2 | control, both tasks | 6 |
| 2 | the 6 emitted drafts, 3 probes each | 18 |

## Phase 1 — the gate was the only thing stopping emission

| | gate on (Q1) | gate suspended (E7) |
|---|---|---|
| `learn` draws that emitted | **1 of 6** | **6 of 6** |

Every draw: `session_ok` true, repair resolved, exactly one draft, zero
`save_skill` rejections, containment reverted, global store left clean. Two
draws chose global scope and were removed by the containment path.

**Step 8 stopped nothing.** Two of the five refusals E7 targets had cited the
verification-command requirement alongside novelty, so a partial yield was
expected and §5 carries a rule for reporting a draw that aborts elsewhere.
That rule had nothing to report.

Delivery was predicted before probing, per Q1's rule that a null must never be
allowed to mean "never arrived". All six predicted `deliver`, BM25 2.479 to
3.767, 6 to 11 terms matched.

## Phase 2 — the drafts work

| arm | binary | graded probe score |
|---|---|---|
| control, `response_text` | 0/3 | 0.778 |
| `A/learn-nogate/1` | 3/3 | 1.000 |
| `A/learn-nogate/2` | 3/3 | 1.000 |
| `A/learn-nogate/3` | 3/3 | 1.000 |
| control, `fingerprint` | 0/3 | 0.636 |
| `B/learn-nogate/1` | 2/3 | 0.879 |
| `B/learn-nogate/2` | 3/3 | 1.000 |
| `B/learn-nogate/3` | 2/3 | 0.879 |
| **bypassed, pooled** | **16/18** | |
| **control, pooled** | **0/6** | |

24 rows, **zero exclusions**. Every treatment run injected exactly one skill
at `trigger: prompt`, so §5's non-delivery rule had nothing to report and the
two `fingerprint` misses are genuine misses rather than a draft that never
arrived.

§5 declared over-refusal in advance as arm B scoring above arm C. It does, on
both tasks, and **every one of the six drafts individually beat the floor**.

## How far this goes, and where it stops

**n=3 per cell.** Every statement here inherits that.

**The 18 treatment runs are 6 artifacts × 3 runs, not 18 independent draws.**
Pooling them gives Fisher exact p = 0.0002, and that figure is quoted only to
be discounted: it assumes an independence the design does not have. The honest
statement is the artifact-level one — six drafts, six floors cleared, the
weakest at 2 of 3 against a control that scored 0 of 6 in the same batch.

**Re-running is not recovering.** The five refused drafts were never written;
`drafts_found` is 0 on every aborted draw. E7 measures drafts the gate *would*
refuse, drawn fresh from the same cells, not the specific eight Q1 declined.

**Suspending a gate changes more than the gate** (spec §7.3). A session told
to skip its own quality check may write a worse draft for reasons step 2 was
not the only thing preventing. That confound runs against the observed
direction, not with it: these drafts cleared the floor *despite* it.

**One orphan row is excluded.** Phase 2 was stopped by hand after one session
on 2026-09-10 to stay inside a usage limit, then restarted whole. That row
(`sf-author-response-text`, control, unresolved, 21:01:40) is excluded under
spec §5.1, a ruling written while the batch was stopped rather than after. It
sat at the floor either way.

## The graded scorer added nothing, again

The 20-probe suite reproduced the binary verdict in **24 of 24** E7 rows. The
two `fingerprint` artifacts that scored 7/11 are exactly the two runs that
failed; nothing else moved off 1.000. This is the 2026-09-10 finding
replicated on fresh artifacts: 40 of 42 then, 24 of 24 now. **These tasks are
single-trap — a session either sees the trap or it does not — and no scorer
can manufacture middle ground the work does not contain.** The instrument
works; there is nothing here for it to resolve.

Control did come off zero (0.636 and 0.778) and no artifact scored below that
floor, so the floor remains observed rather than probed.

**The `response_text` control graded 0.852 on 2026-09-10 and 0.778 here, and
the difference is not noise.** The earlier cell was one artifact at 1.000 and
two at 0.778 — the 1.000 is the single resolved control run behind that task's
1/6. E7's control cell contains no resolved run, so it sits flat at 0.778.
Both figures are correct for their own batch, and 0.778 is the cleaner floor because nothing in it resolved.

This is also why `--batch` exists. E7's control clones reuse Q1's clone names
and overwrote them in `/tmp`; the 2026-09-10 artifacts survive only because
their diffs were already extracted under the unprefixed filenames, and the new
extraction was forbidden from writing over them.

## What this changes

The gate's justification is that junk saves pollute the library. E6 measured
that pollution as close to free: an irrelevant skill that arrived, outranked
the relevant one and took 93% of the injection budget cost nothing detectable.
E7 measures the other side: refusal costs a working skill, six times out of
six.

`/consolidate` was blocked because the library is empty, the library is empty
because the distiller rarely emits, and the distiller rarely emits because of
this gate. That chain now has a measured break in it.

**What E7 does not say** is what should replace the gate. It measures that a
self-assessment of "the model already knows this" is wrong on these two traps.
It does not establish that no gate is needed, and a library with no filter at
all is untested in either direction.

## Reproducing

```bash
python3 bench/distill.py --trap A --distiller learn --draws 3 --no-novelty-gate
python3 bench/distill.py --trap B --distiller learn --draws 3 --no-novelty-gate
python3 bench/dryrun.py                    # delivery prediction, before probing
bash bench/e7_phase2.sh                    # 24 sessions, control interleaved
python3 bench/extract.py --batch e7 <clone>...
python3 bench/regrade.py --batch e7        # graded half, 0 sessions
```

`bench/distill.py` refuses to re-roll an archived draw. `bench/regrade.py`
appends, so `--batch` is what keeps a second grading run from writing a
duplicate copy of every row already in the file.


# E8 — does retrieval survive a library with depth? (2026-09-11)

Spec and pre-registration:
`docs/superpowers/specs/2026-09-11-e8-library-depth-design.md`.

**Depth did not hurt. But the reason is not the one the design predicted, and
the case that should worry anyone was never tested.**

E7 showed the novelty gate refuses skills that work, which argues for relaxing
it. Nothing licensed that: every experiment before this ran with a library of
one or two. E8 installed all ten distilled skills and asked whether the task
still gets what it needs.

## Result

| task | M — matched alone | L — all ten | C — control |
|---|---|---|---|
| `response_text` | 3/3 | **3/3** | 0/3 |
| `fingerprint` | 3/3 | **3/3** | 0/3 |

18 rows, **zero exclusions** in the counted batch. Arm M reproduced its
ceiling on both tasks, which §4 made a precondition. Graded probe scores
agree: 1.000 for every treatment cell, 0.778 and 0.667 for control.

## The mechanism, which is the actual finding

§2.2 predicted that on `response_text` the prompt path would deliver a
**wrong-trap** skill, because the top two BM25 ranks over all ten are both
trap-B skills. **That held 3 of 3** — and 5 of 5 counting the refused batch's
valid rows.

What the design missed is that delivery has two independent paths:

| task | arm | prompt path | symptom path |
|---|---|---|---|
| `response_text` | L run 1 | `capped-scan-reports-unknown-not-absent` (wrong trap) | `json-dumps-breaks-token-matching` |
| `response_text` | L run 2 | same wrong-trap skill | `json-dumps-breaks-token-matching`, `json-escaping-defeats-token-match` |
| `response_text` | L run 3 | same wrong-trap skill | `json-dumps-breaks-token-matching` |
| `fingerprint` | L runs 1–3 | `capped-scan-reports-unknown-not-absent` (**right** trap) | — |

**Ranking failed on `response_text` every single time, and the symptom path
rescued it every single time.** `scripts/detect.py` carries its own
`INJECT_BUDGET_TOKENS = 1200`, independent of `scripts/retrieve.py`'s and
refilling per tool call. The relevant skill arrived after the failure
surfaced, which is exactly when it is useful.

**§2.1 of the spec is falsified and recorded as such.** It claimed only one
skill could ever inject, from one 1200-token budget against skills costing 759
to 1192 tokens. It modelled the prompt path and treated it as the whole
system. Observed: two and three skills delivered.

## Three limits, and the third is the important one

**1. Only `response_text` actually tested depth.** On `fingerprint`, arm L's
prompt path delivered the *same single skill* as arm M, because that skill is
rank 1 among all ten. Adding nine skills changed nothing about what arrived.
"L holds on `fingerprint`" is not evidence that depth is safe there — it is
evidence that ranking happened to pick correctly, and the arm is a null by
construction.

**2. n=3 per cell.** As everywhere here.

**3. The rescue path cannot exist for a silent trap.** Of the ten skills, only
three carry a `symptoms:` list — the three trap-A **anti-skills**. The seven
`learn` skills carry none:

| cell | symptoms declared |
|---|---|
| `A/learn-failure/1,2,3` (anti-skills) | 2 each |
| all seven `learn` skills | 0 |

Q1 established why: the anti-skill path is **structurally unavailable** for a
symptomless trap. Every trap-B anti-skill draw refused, in their own words,
because any `symptoms:` list "would be invented, and invented triggers pollute
the detection index".

So the rescue that saved `response_text` rides on an artifact class that
cannot be produced for a trap like `fingerprint`. **E8 never ran the dangerous
combination — ranking failure on a silent trap — because ranking happened not
to fail there.** That combination is where library depth would actually bite,
and it remains untested.

This also corrects E6, which recorded `prompt` as the expected trigger and
symptoms as "dead in author mode". True of E6's hand-authored payloads; false
of these distilled anti-skills, whose symptoms are drawn from real assertion
text and do fire.

## What this does and does not license

**Does:** at a library of ten, with a loud trap, retrieval survives picking
the wrong skill. Combined with E6 — an irrelevant skill riding along costs
nothing detectable — the case against relaxing the novelty gate is weaker than
it was, on the evidence available.

**Does not:** license relaxing it outright. The safety margin measured here is
supplied by anti-skills the distiller *cannot write* for silent traps, and
those are exactly the traps Q1 found the distiller refuses most. A library
grown under a relaxed gate would be rich in `learn` skills carrying no
symptoms and thin in the anti-skills that did the rescuing.

**The next question is narrower than "is depth safe".** It is: *what happens
when ranking fails on a trap with no symptoms to fall back on?* Answering it
needs a library where the matched skill for a silent trap is out-ranked —
which the current pool does not produce, since `capped-scan-reports-unknown-not-absent`
ranks first on both prompts.

## First attempt: refused, and excluded

The 00:41–00:46 batch hit the session limit at 00:45:11. 13 of 18 rows carry
`session_ok: false`; the 5 valid rows are excluded too, under spec §4.1, for
the reason E7 §5.1 excluded its orphan — a row from an aborted batch pooled
into a later one is E5's defect and nothing on the row records which batch it
came from. Their **mechanism** readings are kept and quoted above, because
they are observations of what injected rather than scores.

## Reproducing

```bash
bash bench/e8_batch.sh                     # 18 sessions, M/L/C per task
python3 bench/extract.py --batch e8 <clone>...
python3 bench/regrade.py --batch e8        # graded half, 0 sessions
```


# E9 — does a consolidated skill still work? (2026-09-11)

Spec and pre-registration:
`docs/superpowers/specs/2026-09-11-e9-consolidation-design.md`.

**Yes, on both tasks, and the merged skills fit the delivery budget with room
to spare.**

`/consolidate` shipped earlier the same day. Its own spec put this question out
of scope until the feature existed (consolidate spec §7). It exists now.

## The question the viability pass turned this into

E8 measured the delivery budget: `INJECT_BUDGET_TOKENS` is 1200 and
`retrieve.run_hook` costs an entry at `max(1, len(whole file) // 4)`. The
clusters do not remotely fit:

| cluster | members | member costs | concatenated |
|---|---|---|---|
| `test_detect.py`, project | 3 | 798, 869, 817 | 2484 |
| `test_retrieve.py`, project | 2 | 957, 1072 | 2029 |
| `test_retrieve.py`, global | 2 | 1192, 1096 | 2288 |

So a merge must compress several skills into roughly the size of **one**, or
it can never be injected. **And `save_skill.validate` enforces no size limit** —
checked, there is none. An oversized merge saves cleanly, indexes cleanly,
reports as a healthy library entry, and silently never arrives. That, not a
lower score, was the failure worth looking for.

## Phase 1 — the compression, recorded before any probing

Each merge was written by a fresh subagent that read only the member files and
`commands/consolidate.md` step 4, was told the character ceiling, and **was
told nothing about any member's score**. A merger that knew which member
scored best would be curating, not consolidating.

| cluster | members | concatenated | merged | share | fits 1200 |
|---|---|---|---|---|---|
| A | 3 | 2484 | **1095** | 44% | yes |
| B | 2 | 2029 | **1088** | 54% | yes |

Both also pass `save_skill.validate` with zero errors, which closes half of
spec threat 1: these drafts would survive the enforced save path, not merely
be written. Both predicted `deliver` before probing, BM25 3.411 and 4.562.

Neither merger was re-run to get a smaller or better draft — §4 forbids it,
and the first draft each produced is the artifact reported here.

## Phase 2 — the merge holds the ceiling

| task | R — named member | K — consolidated | C — control |
|---|---|---|---|
| `response_text` | 3/3 | **3/3** | 0/3 |
| `fingerprint` | 3/3 | **3/3** | 0/3 |

18 rows, **zero exclusions**. Arm R reproduced its ceiling on both tasks,
which §4 made a precondition. Every treatment run injected exactly one skill
at `trigger: prompt`, so §4's non-delivery rule had nothing to report. Graded
probe scores agree exactly: 1.000 for every treatment cell against 0.778 and
0.636 for control — the binary verdict reproduced in 18 of 18 rows, after 40
of 42 (2026-09-10), 24 of 24 (E7) and 18 of 18 (E8).

**One reading artifact worth naming.** On `fingerprint`, arms R and K inject
the *same skill name* — `capped-scan-reports-unknown-not-absent` — because the
merge inherits its highest-bucket member's name and that member is arm R. The
two arms differ in file content, not in name, and are told apart on the row by
`skill_path`. That is name inheritance working as designed (consolidate spec
§2.2), not a mix-up.

## What this does and does not establish

**Does:** a machine-written merge of three skills about one bug, compressed to
44% of their combined size, performs like the member it replaced and fits the
budget. The ranking failure E8 measured — six near-duplicates splitting a BM25
field and handing the task a skill about the wrong bug — has a fix that works.

**Does not:** say whether a merge matches its *best* member or its *average*.
§2 established that is not answerable here: all three trap-A members already
scored 3/3, so that cluster had no headroom by construction, and the trap-B
cluster spans 2/3 to 3/3, a spread of one run at n=3.

**Does not** exercise the shipped command end to end. E9 measures the artifact
the drafting step produces; `/consolidate` also installs into a real library
and saves through `save_skill.py`. That plumbing has tests (31 of them) but no
integration run.

**The size result generalizes worse than the score result.** Two clusters, of
three and two members, both compressing to about half. A cluster of eight, or
one whose members genuinely disagree, might not compress without losing
something the score would catch. Nothing here bounds that.

## A gap this leaves open

`save_skill` accepts a skill of any size, and an oversized one is
undeliverable but indistinguishable from a healthy entry in `library.py list`.
E9's merges fit, so the gap did not bite — but it was luck of the drafting,
not a property of the system. A size warning at save time, or a check in the
command file, would make it visible. That is a change, not a measurement, and
is out of scope here (§7).

## Reproducing

```bash
# phase 1 drafts are archived under bench/distilled/<trap>/consolidated/1/
python3 bench/dryrun.py                  # delivery prediction, before probing
bash bench/e9_batch.sh                   # 18 sessions, R/K/C per task
python3 bench/extract.py --batch e9 <clone>...
python3 bench/regrade.py --batch e9      # graded half, 0 sessions
```


# E8 follow-up — does consolidation fix the ranking failure? (2026-09-11)

**No. It makes it worse.** Reproduce with `python3 bench/rank_check.py` — the
check is deterministic BM25 over the archived skills and costs no sessions.

## Why this was asked

E8 installed ten skills and watched the prompt path hand
`sf-author-response-text` a skill about a **different bug** on all three runs,
because six near-duplicates about one lesson split the field. `/consolidate`
was prioritised as the fix for exactly that, built, and validated by E9. This
closes the loop.

Criterion, fixed before the first run: on each task, does a skill from the
**matching trap** win rank 1 and inject within budget?

## Result

| pool | `response_text` (wants trap A) | `fingerprint` (wants trap B) |
|---|---|---|
| **before** — E8's ten | `truncation-reports-unknown` (**trap B**) | `capped-scan-reports-unknown-not-absent` (trap B) ✓ |
| **after** — consolidated, seven | `capped-scan-reports-unknown-not-absent` (**trap B**) | same ✓ |

The `before` row reproduces E8's live observation exactly, which is what
licenses reading the `after` row.

On `response_text` the wrong-trap skill still wins. Consolidation changed
*which* trap-B skill wins, not *that* one does.

## Two mechanisms, and the second is the surprise

**Merging lowered the correct skill's rank.**

| pool | best trap-A entry on the `response_text` prompt |
|---|---|
| before | rank **3**, score **8.40** (`flatten-structured-output-for-token-matching`) |
| after | rank **5**, score **4.70** (the merge that replaced it and two siblings) |

A description covering three skills matches any one probe prompt less
specifically than a single-purpose description does. BM25 rewards specificity,
and merging spends it. **This is brief Q2's transfer null reappearing one
layer down** — the transfer arm found abstract same-class knowledge did not
help on a different bug (0/6 in the pilot, 0/6 again on 2026-09-09); this finds general descriptions do not rank. Same principle, different
mechanism, and nothing in the `/consolidate` design anticipated it.

**The budget makes rank 1 the only rank that matters.** In the consolidated
pool, rank 1 costs 1088 of 1200, leaving 112. The next four entries are all
trap A — the correct bug — at ranks 2 through 5, and they cost 759, 979, 998
and 1095. **None can fit in 112 tokens.** So even a ranking that put the right
skill second would deliver nothing.

## What this changes

`/consolidate` is not withdrawn: E9 measured it doing what it claims — a merge
of three skills holds its member's ceiling at 44% of the size (3/3 against a
0/3 control, n=3 per cell). The feature works. **The justification for
prioritising it does not survive.**

The real blocker is the injection budget, not library sprawl. One skill fits.
Until that changes, retrieval is a winner-take-all contest decided by a BM25
score over `name + description`, and E6 already showed that score ranking an
unrelated `arrow` timezone skill above a matched one.

So the next move on this thread is **not** more consolidation. It is one of:
raise `INJECT_BUDGET_TOKENS`; make skills cheaper (every distilled skill costs
759–1192 against a 1200 budget); or rank on something better than
`name + description`. Nothing here says which, and all three are untested.

## Limits

Seven skills in the consolidated pool, from one repository, two traps, both
written by the operator. BM25 is corpus-relative, so both the before and after
scores are properties of *these* pools and do not transfer as absolute
numbers — the rank ordering is the claim, not the magnitudes.

Only two of the three clusters were merged. The third is global-scope and E9
did not produce a merge for it, so the `after` pool understates consolidation
rather than flattering it.


# Budget derivation — what budget delivers a correct skill? (2026-09-11)

Reproduce with `python3 bench/budget_sweep.py`. Deterministic, no sessions.

The E8 follow-up left the blocker as the injection budget: one skill fits, and
on `sf-author-response-text` it is a skill about the wrong bug. E6 separately
found an irrelevant skill riding alongside a relevant one cost nothing
measurable (R 6/6, R+I 6/6, n=3 per cell). So the fix might just be making two
fit. This asks at what budget that happens.

Criterion, fixed before the first run: at each candidate budget, does a skill
from the **matching trap** get delivered on **both** tasks?

## Result — and the curve goes the wrong way in the middle

Against the ten-skill pool E8 installed:

| budget | `response_text` (wants A) | `fingerprint` (wants B) | both correct |
|---|---|---|---|
| **1200** (today) | 1 skill, **wrong** | 1 skill, right | no |
| 1600 | 1 skill, **wrong** | 1 skill, right | no |
| 2000 | 2 skills, right | 2 skills, right | **yes** |
| **2400** | 2 skills, **wrong** | 2 skills, right | **no** |
| 3000 | 3 skills, right | 3 skills, right | **yes** |
| 3600 | 3 skills, right | 3 skills, right | **yes** |

**Raising the budget from 2000 to 2400 removes the correct skill.** That is not
a typo and not noise — it is deterministic, and the trace explains it:

| rank | skill | trap | cost | at 2000 | at 2400 |
|---|---|---|---|---|---|
| 1 | `truncation-reports-unknown` | B | 957 | taken, 1043 left | taken, 1443 left |
| 2 | `capped-scan-reports-unknown-not-absent` | B | 1072 | **skipped**, 1072 > 1043 | **taken**, 371 left |
| 3 | `flatten-structured-output-for-token-matching` | **A** | 869 | **taken** | **skipped**, 869 > 371 |

`retrieve.run_hook` walks the ranked list and `continue`s past anything over the
remaining budget. So at 2000 the second wrong-trap skill does not fit, and the
correct skill slips in behind it. At 2400 it does fit, and crowds the correct
skill out.

**Greedy skip-and-continue over a rank-ordered list is not monotonic in
budget.** More budget can deliver a strictly worse set. The 2000 result is
therefore an accident of two costs straddling a threshold, not a property to
rely on — and the same accident is what makes 2400 a regression.

The consolidated seven-skill pool has no such dip (2400 is fine there), which
is coincidence rather than a virtue of consolidation: different costs, the
straddle lands elsewhere.

> **Superseded 2026-09-13.** Everything above describes the skip-and-continue
> selector, which no longer ships. `retrieve.run_hook` now stops at the first
> entry that does not fit, and the 2400 crowding-out does not reproduce. On the
> re-run the consolidated seven are correct on both tasks from **2000** and hold
> above it; the ten-skill pool from 3000. The paragraphs below about 3000 being
> "the first budget that does not depend on a cost coincidence" were reasoning
> about the old selector — under a prefix selector no result depends on a
> coincidence, because a prefix can only grow.

## What follows

**3000 is the first budget that delivers a correct skill on both tasks without
depending on a cost coincidence** — at that point three skills fit and
`MAX_SKILLS = 3` becomes the binding cap instead, which makes the outcome
stable rather than accidental.

**That is 2.5× today's budget, and it is past the evidence.** E6 measured
no-harm with **two** skills totalling ~1118 tokens. Three skills at ~2900
tokens is extrapolation from that, not a finding. Whether that much injected
context costs anything is exactly the kind of question E6's design answers for
one payload and not for three.

**The non-monotonicity is worth fixing regardless of the budget chosen.** A
selector that considered the ranked candidates as a set rather than greedily
in order would not have a range where more budget is worse. Nothing here
establishes what that selector should be, and changing it is a change, not a
measurement.

## Limits

Ten skills, two traps, one repository, all operator-written, and BM25 scores
are corpus-relative — the ranks are the claim, not the magnitudes. The sweep
models the **prompt path only**; `detect.py` carries its own separate 1200
budget for symptom-triggered delivery (E8 §4.1), and E8 measured that path
rescuing exactly this failure when the trap is loud enough to produce symptoms.


# Selector monotonicity — why the curve dips, and what fixes it (2026-09-11)

Reproduce with `python3 bench/selector_check.py`. Deterministic, no sessions.

The budget derivation above left one loose end: greedy skip-and-continue is not
monotonic in the budget, and it argued the fix mattered "regardless of the
budget chosen" without saying what the fix is. This measures three candidates.

Two failures are counted, over a budget grid of 600–4000 in steps of 50, for
each of two pools (E8's ten, and the consolidated seven) and both tasks — 69
budget steps, 4 pool-task combinations:

- **flip** — the correct-trap skill is delivered at one budget and gone at the
  next one up. The user-visible defect.
- **shrink** — the delivered set at one budget is not a superset of the set
  below it. The invariant underneath.

All three selectors share every non-budget gate. They differ only in what they
do with an entry that does not fit.

## Result

| selector | flips | shrinks | lowest budget correct on both tasks |
|---|---|---|---|
| `continue` (today) | 3 | 15 | ten **1750, not held above**; seven 1850 |
| `break` | **0** | **0** | ten 2900; seven 1850 |
| highest-scoring affordable subset | 8 | 57 | both **not held above** |

**Stopping at the first entry that does not fit is the only one of the three
that is monotone.** It delivers the longest rank-ordered prefix that fits, and
a prefix can only grow as the budget grows.

**It costs nothing on a consolidated library.** The seven-skill pool needs
1850 either way; the difference is that under `break` the result is stable
above that point rather than accidental. The cost appears only on the
duplicate-heavy ten-skill pool, where the threshold rises from an unstable
1750 to a stable 2900. This is the first thing that makes `/consolidate`'s
value legible after the E8 follow-up found it worsened ranking.

**The obvious smarter answer is worse than doing nothing.** Choosing the
affordable subset with the highest total BM25 score more than triples the
flips and quadruples the shrinks. An optimal subset is not stable under a
growing budget either — dropping one item for two cheaper ones is exactly the
move that loses a correct skill. Sophistication in the selector is not the
axis that helps.

## What this costs, and what it breaks

`break` also drops the delivered payload in the case the old tests blessed.
`test_budget_skips_oversized_entry` asserted that an oversized entry is skipped
so a cheaper lower-ranked one gets in; under `break` nothing is delivered there.

**Shipped 2026-09-13.** That test was replaced by four
(`test_budget_stops_at_the_first_entry_that_does_not_fit`, a budget
monotonicity sweep, a rank-fidelity test, and one pinning anti-skill
suppression). The suite stands at **785 passing**. Taking the change was a
decision that the documented intent was wrong: brief Q2's transfer arm measured
a plausible-but-wrong skill at 0/6, so "something is better than nothing" was
never supported by this project's own data.

**The real cost is broader than the payload.** Delivery is now a prefix, so an
entry that overflows the budget suppresses everything beneath it — anti-skills
included, even though `MAX_SKILLS` otherwise lets them past the skill cap. The
save-time size guard (shipped the same day) is what makes that tolerable: an
entry too large for the whole budget can no longer be saved. Libraries that
predate the guard keep the exposure.

**The symptom path does NOT need this fix, and an earlier revision of this
section was wrong to say so.** It claimed `detect.run_hook` needed "a flag that
halts admission while the scan continues." `detect.py` does not rank: it walks
`idx["symptoms"]` in compile order under `MAX_ANTISKILLS = 2`, so there is no
rank-ordered prefix to preserve and no monotonicity defect to repair. It keeps
its `continue` deliberately, and `test_budget_skips_oversized_antiskill` pins
that.

## Limits

Same limits as the budget derivation: ten skills, two traps, one repository,
operator-written, prompt path only. Monotonicity itself is a property of the
algorithm rather than of this corpus, but "costs nothing on a consolidated
library" is a claim about these seven skills and their sizes.


# E10 — does a wrong skill hurt at prompt time beside the right one? (2026-09-13)

Spec and pre-registration:
`docs/superpowers/specs/2026-09-11-e10-prompt-time-budget-design.md`.
Batch script `bench/e10_batch.sh`. 24 sessions, **zero exclusions**.

## Result

| task | M (matched alone, 1200) | P (pair, 2000) | S (seven, 2000) | C |
|---|---|---|---|---|
| `fingerprint` | 3/3 | 3/3 | 3/3 | **0/3** |
| `response_text` | 3/3 | 3/3 | 3/3 | **3/3** |

**`fingerprint` is readable, and shows no harm.** Arm M reproduced its ceiling,
control sat at the floor, and neither treatment arm fell. Harm was pre-declared
as P or S scoring below M; neither did.

**`response_text` is void.** Pre-registration §4: arm C at 2/3 or more makes
that task uninterpretable. Its three ceiling-level treatment arms carry no
signal, because the floor rose to meet them.

## The half that survived is the easier half

Both tasks received the *same two skills* — §2.2's ranking put
`B/consolidated/1` (1088) first and `A/learn-failure/1` (759) second on both
prompts. The tasks differ only in **which of those two is the correct one**:

| task | rank 1 | rank 2 | correct skill arrives |
|---|---|---|---|
| `fingerprint` | `capped-scan…` (correct) | `json-dumps-breaks…` (wrong bug) | **first** |
| `response_text` | `capped-scan…` (wrong bug) | `json-dumps-breaks…` (correct) | **second** |

So E10 measured "a wrong skill riding *behind* the right one costs nothing"
and lost the cell that asked "does a wrong skill arriving *first* mislead?"
**The budget raise is still unlicensed for the case that motivated it** — the
E8 ranking failure, where the correct skill is the one that comes second.

## Delivery — the prediction held 12 of 12

Every P and S run received `capped-scan-reports-unknown-not-absent` then
`json-dumps-breaks-token-matching` at `trigger: prompt`, in that order, on both
tasks. Zero deviations from §3.2. Symptom-path additions appeared only on
S/`response_text` (`json-escaping-defeats-token-match` on 3 of 3,
`json-dumps-fuses-tokens-across-newlines` on 1) and never on P or on
`fingerprint` — also as predicted.

The lever behaved: rows carry `inject_budget: 2000` on P and S and `null` on M
and C, and the three clone segments (`-d…`, `-d…-plus-b2000`,
`-d…-plus6-b2000`) kept the arms off each other's clones and ledgers.

## The control break, which matters more than the result

`sf-author-response-text` control resolved **3 of 3, with zero injections**.

| batch | control on `response_text` |
|---|---|
| Q1 (09-09) | 1/3 |
| E6 (09-10) | 0/1 |
| E7 (09-11a) | 0/3 |
| E8/E9 (09-11b) | 0/6 |
| **E10 (09-13)** | **3/3** |

One in thirteen before, three for three now — roughly a 1-in-2000 event at the
historical rate. Ruled out by inspection, not assumption:

- **Contamination.** Control rows carry `injections: []`, and after the batch
  the operator's library held no skills, an empty index, and only the two
  project trust keys. `libguard` reverted cleanly.
- **Vacuous scoring.** `per_test` carries both grading test names; E9's control
  rows carry the same two names set to `false`.
- **Task drift.** `bench/tasks.json` is untouched since before E9, and both
  batches' controls reproduce the same stub contract docstring.
- **The clone teaching the answer.** Same pinned base commit `4eeaa9a`, no
  `.claude/skills`, no `CLAUDE.md`.
- **Plugin set.** Only `frontend-design` changed (2026-09-13 09:30), which has
  no bearing on a token-matching trap.

What the three control sessions actually did: each independently rewrote
`response_text` to walk the structure and join raw string leaves, each with its
own comment naming the escaping failure — `bench/authored/e10-sf-author-
response-text-control-{1,2,3}.diff`.

**Remaining candidates: the model behind the `claude-opus-5` alias, the CLI
build, or variance. None is falsifiable from this evidence**, because a row
records `model` — a moving alias — and nothing about the CLI or plugin
versions. Today's CLI is 2.1.266.

## What this costs

1. **Any conclusion resting on a control measured in a different batch is
   suspect on this task.** Same-batch controls are what caught it, which is
   exactly why E5's rule exists.
2. **The bench needs an environment fingerprint on the row** — resolved model
   id, CLI version, plugin versions and shas. Without it, a control shift
   cannot be attributed after the fact, only noticed.
3. **`sf-author-response-text` may be burned as a discriminating task.** Before
   reusing it, re-measure control; if it stays at ceiling, E4 and every future
   comparison need a different trap.

## Limits

n=3 per cell. One budget (2000), one payload (1847 tokens), loud traps only,
`fingerprint`'s ordering only, two traps in one repository, all
operator-curated. A null here is "no large effect", never "no effect".

## The control re-measure, and what actually broke

Three more `sf-author-response-text` control sessions, run alone on 2026-09-13
at 13:07–13:09 against the same worktree, same pinned base, empty library.

**3 of 3 resolved, zero injections.** Six for six across both of today's
batches. The reading criterion was fixed before the run: control ≥ 2/3 means
the E10 result was not an outlier and the task is burned as a discriminator.
It reads at the ceiling. **`sf-author-response-text` is retired as a
discriminating task.**

These are the first rows in the register to carry the `env` field — CLI build
and every loaded plugin's sha. It landed as designed and is now on every row
going forward.

### It is not a general capability shift

The same E10 batch ran three `sf-author-fingerprint-preexisting` controls at
12:49–12:51 — minutes before the `response_text` controls, same machine, same
CLI, same plugin set, same process.

| task | control before 09-13 | control on 09-13 |
| --- | --- | --- |
| `sf-author-fingerprint-preexisting` | 0/15 | 0/3 |
| `sf-author-response-text` | 1/13 | **6/6** |

Counts exclude `session_ok: false` rows (a refused batch of three on 09-11).

A change that lifted every session's baseline competence would have moved both.
One moved to the ceiling and the other did not move at all, in the same batch.

The parsimonious reading is that **`response_text` was always the marginal
trap**. Its control floor was never zero — it was 1/13, a trap the model
occasionally beat unaided. `fingerprint-preexisting` has never once been solved
without the skill in 18 control sessions. A modest capability increase crosses a
marginal threshold and leaves a hard one untouched; that is what the two columns
show. Naming the exact upstream change is not possible from this machine, and no
longer buys anything: the action is the same under every remaining hypothesis.

### What this actually costs

Narrower than feared, and different in kind.

1. **One trap, not the register.** E10's `response_text` half stays void. Every
   result resting on `fingerprint-preexisting` — its control floor intact at
   0/18 — stands.
2. **A control floor is a measurement, not a constant.** It decays. A trap with
   a non-zero historical floor is a trap on its way out, and 1/13 was the
   warning this project read as noise for four batches.
3. **Trap inventory is now the binding constraint.** `fingerprint-preexisting`
   is the one task with a demonstrated zero floor. E4 was already blocked
   needing a mid-range task; the bench now also needs a replacement for
   `response_text` before any comparison that depends on two traps.

### The standing check this earns

Before a task is used in a batch, its control cell is read as a live number, not
inherited from the register. Any task whose control floor is non-zero over its
history is a candidate for retirement, not a discriminator. Same-batch controls
(E5) remain the rule; this is the rule that says which tasks are worth putting
in a batch at all.

# E11 — trap screening: which tasks still have a zero control floor? (2026-09-13)

Pre-registered before any session ran:
`docs/superpowers/specs/2026-09-13-e11-trap-screening-design.md`. Control only,
15 sessions, one batch, 13:36–13:50.

## Result

| cell | task | mode | control | verdict |
| --- | --- | --- | --- | --- |
| A | `sf-escaping-breaks-symptom-match` | repair | **6/6** | REJECTED (§4.1) |
| B | `sf-truncation-reports-absent` | repair | **6/6** | REJECTED (§4.1) |
| R | `sf-author-fingerprint-preexisting` | author | **0/3** | reference held — **0/21** lifetime |

15 of 15 sessions valid, zero exclusions, zero injections in every cell, and no
`already passing at baseline` warning fired. The reference cell did not move, so
§4.2 does not void the screen.

**Neither candidate is marginal — both are at the ceiling.** All three graded
tests passed in all six sessions on both tasks, in a median of about 53 seconds.
This is not a trap the model occasionally beats; it is a trap it never loses to.

## §4.4 predicted this, which is what makes it a finding

Both candidates are `mode: repair`: the model is shown the failing tests and
asked to fix the source. Author mode hides the tests and grades against a
contract the session never sees. The spec called repair mode "structurally the
weaker trap" and pre-registered a non-zero floor as the *expected* outcome
before the batch ran.

Recording that in advance is the difference between a finding and a
rationalisation. The measured result is stronger than the prediction: not merely
non-zero, but saturated.

**A failing test is the answer.** Showing a model three red assertions that
describe the intended behaviour hands it the specification. What remains is
reading comprehension, not knowledge — and reading comprehension is exactly what
a skill cannot improve, because the session already has the information.

## The bench has exactly one trap

**Corrected 2026-09-13: there are two bugs here, not four.** `bench/tasks.json`
holds ten ids carrying exactly two `fix_commit`s, five each. The four *tasks*
are those two bugs crossed with two modes.

| bug | author-mode task | floor | repair-mode task | floor |
| --- | --- | --- | --- | --- |
| `22ddf37` escaping | `sf-author-response-text` | 1/13 → 6/6, retired (E10) | `sf-escaping-breaks-symptom-match` | **6/6**, rejected |
| `ab4acfe` truncation | `sf-author-fingerprint-preexisting` | **0/21**, the only survivor | `sf-truncation-reports-absent` | **6/6**, rejected |

**Read the `ab4acfe` row across.** Same bug, same `fix_commit`, same
`test_path` — **0/21 in author mode and 6/6 in repair mode.** That is a
within-bug comparison with the bug held fixed, and it isolates *mode* as the
cause far more tightly than comparing one task against another ever could.
`22ddf37` shows the same shape: its author task sat at 1/13 for four batches
while its repair task is at ceiling.

An earlier revision of this section called these "four distinct bugs". That was
wrong, and the error concealed the strongest evidence in this experiment.

Every future comparison needing two traps is blocked until new **author-mode**
tasks are written. Screening is finished as a source of supply; authoring is the
critical path.

## What this may unblock: harm has been measured in the wrong direction

E4 — "does injecting an irrelevant skill actively hurt?" — has been blocked for
its whole life on the want of "a mid-range task." That framing may be the error.

**Harm cannot be measured on a floor task.** A control at 0/21 has nowhere to
fall; any effect an irrelevant skill has is invisible against zero. Every trap
this bench has ever used as a discriminator was chosen for a floor of zero,
which is precisely the property that makes it useless for detecting harm.

A task whose control sits at **6/6 with zero variance** has the opposite
property: maximum headroom to fall, and a tight enough baseline that a drop of
two or three runs is legible at n=6. Cells A and B are now two such tasks,
measured in a clean batch with a held reference.

**This is a design proposal, not a result.** It needs its own pre-registration,
and it carries a real threat: a repair-mode session reads the failing tests, so
an irrelevant skill must be disruptive enough to survive that signal before it
shows up as harm. A null would then be ambiguous between "no harm" and "the
tests rescued it." That has to be written down before the batch, not after.

## Limits

n=6 per candidate. 0/6 would have been consistent with a true floor up to about
39% at 95%; 6/6 bounds the floor from the other side just as loosely, and the
honest claim is "no control failure observed at n=6", not "the floor is 1.0".
Both candidates are one repository, operator-curated, two bugs of the same class
(a transform upstream of a decision producing a wrong negative). The reference
cell is n=3.

# The delivery gate does not discriminate (2026-09-13)

Reproduce with `python3 bench/gate_analysis.py`. Deterministic, no sessions.

Found while pre-flighting E12, which needed to know whether an *irrelevant*
skill would even be delivered before it could measure whether one does harm.
The answer was yes — and then yes for everything else too.

## The result

`retrieve.run_hook` admits an entry when `score > 0 and matched >=
MIN_MATCHED_TERMS` (=2). Across all four task prompts, plus a control prompt
with no technical content at all:

| prompt | clears the gate | ...counting only informative terms | rank 1 | correct trap at rank |
| --- | --- | --- | --- | --- |
| repair `escaping` | 16/16 | 14/16 | trap B | **5** |
| repair `truncation` | 16/16 | 14/16 | trap B | 1 |
| author `response_text` | 16/16 | 16/16 | trap B | **3** |
| author `fingerprint` | 16/16 | 15/16 | trap B | 1 |
| **control — "the cat sat on the mat and did not move when i called"** | **16/16** | **1/16** | trap B | n/a |

**A sentence about a cat admits every skill in the library.** That is the
finding, and it needs no interpretation.

## The mechanism

In `bm25()`, `matched` is incremented before the IDF weight exists:

```python
f = tf.get(term)
if not f:
    continue
matched += 1                      # unweighted
idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
score += idf * f * ...
```

IDF does its job — a token present in all 16 descriptions scores **0.0299**,
near zero. The *score* knows the term is worthless. The *gate* never asks. Two
worthless matches open it.

That would be harmless if descriptions did not share worthless terms. Four are
universal here — `not`, `the`, `use`, `when` — and **two of them are mandated**.
`save_skill.validate()` refuses any description lacking `"do not use"`, which
guarantees `not` and `use` in every skill in the library.

Precisely: the validator enforces the substring `"do not use"`, so `not` and
`use` are guaranteed (`do` is dropped by `tokenize`'s `len >= 3` filter).
`when` is spec 4.1 convention — present in all 16 descriptions, but **not**
enforced. So the gate is satisfied by house style before topic is considered.

## Raising the threshold does not fix it

At `MIN_MATCHED_TERMS = 5`, 14–16 of 16 still clear. At 7, 5–13 still clear.
The universal terms are not the only shared ones, and pushing the threshold up
starts excluding genuinely relevant skills before it excludes irrelevant ones.
This is not a threshold problem.

## What would fix it, measured but not shipped

Counting only terms that are **not** present in every description separates the
cat from the real prompts: **1/16 versus 14–16/16**. That is a real
discriminator, and it is worth stating that it could have come out otherwise —
a fix that also gutted the real prompts would be no fix.

**This is a measurement, not a change.** `retrieve.py` is untouched. Shipping it
alters what every session receives, so it needs its own tests and a look at what
it does to live delivery first. The obvious variants — weight `matched` by IDF,
or ignore terms with `df == n` — are not equivalent on a corpus that grows.

## Ranking is a second, independent failure

**Rank 1 is a trap-B skill on all five prompts, including the cat.** The top of
the ranking is essentially prompt-independent on this corpus. On the two trap-A
prompts the correct skill sits at rank 3 and rank 5, and roughly one skill fits
the 1200 budget, so the skill actually delivered is the wrong one.

This is E8's ranking failure — "on `response_text` the prompt path delivered a
wrong-trap skill 3/3" — now with a mechanism instead of an observation. The E8
follow-up found consolidation made ranking *worse*; that is consistent with a
ranker whose top slot barely depends on the query.

## What it means for the experiments already run

Nothing already measured is invalidated: every experiment recorded which skills
were delivered, and those records stand. What changes is the interpretation of
**delivery** as evidence of retrieval working. It was not selecting; it was
admitting everything and letting BM25's ordering pick, from a top slot that
hardly moves with the prompt.

E12's arm I is unaffected and arguably strengthened — a genuinely irrelevant
skill really is retrieved and delivered by the shipped system on these prompts,
so measuring whether it does harm is measuring something real rather than
contrived.

## Limits

Sixteen skills, one library, all operator-written, four task prompts plus one
control. Universality of a term is a property of *this* corpus: `not` and `use`
are guaranteed by the validator at any corpus size, but `the` and `when` are
not, and a larger library would change the df table and possibly the proposed
fix's numbers. BM25 scores are corpus-relative — the ranks are the claim, not
the magnitudes.

# E12: does an irrelevant injected skill actively hurt? (2026-09-13)

Pre-registered in `docs/superpowers/specs/2026-09-13-e12-irrelevant-injection-harm-design.md`.
The criterion was fixed at `239e1fd` before any data existed. Both amendments
also landed before the data they govern: the `--skill-from` lever (§3.3,
`d36c34e`), then the §4.2 clarification and the decision to re-run all 36
sessions (`6577028`).

## Result: no large harm in either arm

| arm | installed | escaping | truncation | pooled |
| --- | --- | --- | --- | --- |
| C | nothing | 6/6 | 6/6 | **12/12** |
| R | the skill distilled from the task's own bug | 6/6 | 6/6 | **12/12** |
| I | `arrow-tzinfo-string-trap` (timezone handling) | 6/6 | 6/6 | **12/12** |

Read with `python3 bench/e12_read.py --window 2026-09-13T17:36:28 -`, in the
order the spec fixes. **§4.2 held:** the control cell was complete at 12 valid
sessions, and no treatment row was missing its skill. Then **§4.1:** R and I
each came in 0 of 12 below control, which the spec calls *no large harm*.
Fisher's exact p is 1.000 for both contrasts, reported as a statistic rather
than used as a threshold.

All 36 sessions were valid, with zero exclusions, run 17:36–18:13 under one
environment fingerprint (CLI 2.1.266, skillforge `b712e4b`). Sessions took
43–84s, median 58s. Delivery went exactly as designed: `arrow-tzinfo` arrived
12 times, each relevant skill 6 times, and no control row received an
injection.

## How to read it

This is §5's "neither below C" case: **no large harm at ~550 tokens on these
tasks.**

The reading is bounded by §4.4, which was written before the data. These are
repair-mode tasks, so the session sees the failing tests, and that is a strong
signal an irrelevant skill would have to overcome. This result cannot separate
"no harm" from "the tests rescued it". What it supports is **no large harm on a
task whose tests are visible**, never "irrelevant injection is harmless".

Arm I was not a contrivance. The delivery-gate analysis above shows shipped
retrieval really does admit this skill on these prompts, and here it arrived
12 times out of 12.

The three-arm split in §3.2 was built to separate "irrelevance harms" from
"injected context harms". That needs at least one arm to move, and none did, so
the split had nothing to resolve.

## What it answers

E4's question, **for repair-mode tasks at ceiling**. It does not answer it for
author mode, and it can't: `fingerprint_preexisting` sits at 0/21 with no
headroom, and `response_text` was retired this morning. E4 stays partly open.

## The pattern

This is the third harm null in a row:

- **E6:** an irrelevant skill alongside a relevant one, 6/6 against 6/6.
- **E10:** a wrong-bug skill riding behind the correct one at 1847 tokens (the `fingerprint` half).
- **E12:** an irrelevant skill alone, 12/12 against 12/12.

On this bench, injected context has never yet cost anything measurable. Read
that next to the delivery-gate finding. Retrieval admits everything, and on two
of four prompts the correct skill doesn't reach rank 1. The measured loss is the
**missed** skill, not the wrong one. So whatever precision is worth here, it is
worth it through getting the right skill to rank 1, not through keeping wrong
skills out.

## How it was run, including what went wrong

- **The smoke test caught a harness mismatch before any batch session.**
  `--skill-from` accepted only distilled-corpus paths, and all three arm skills
  are hand-written. The fix was a narrow lever extension, with §3.3 amended
  before any data existed.
- **The first attempt hit the session limit** after 23 of 36 sessions
  (`48af694`). Its rows are kept as evidence and excluded from this analysis
  (`6577028`). All 36 were re-run instead of the 13 missing, so §4.1's pooled
  analysis would not span a session-limit boundary.
- **An ad-hoc reader misread that attempt as void.** It compared 6 valid
  control sessions against a threshold written for 12. The fix was
  `bench/e12_read.py`, which tells an unfinished cell from a void one, plus a
  clarification to §4.2 written before any truncation-task data.
- **Refusals are now diagnosable.** The harness records `session_tail` when a
  session fails (`f1f9be9`). The first attempt's refusal reason was thrown
  away, and it took a probe session to recover it.

## Limits

n=6 per cell, 12 pooled, so only large effects are ruled out. One payload size,
about 550 tokens. Two bugs of the same class, in one repository. Repair mode
only.

# Function words dropped at tokenization (2026-09-13)

Commit `9cbb472`. This is the root cause behind the delivery-gate finding above, and its fix.

## Root cause: one defect, two symptoms

Function words were being scored as if they carried topic.

- **Common ones opened the gate.** `the`, `not`, `when` and `use` appear in every
  house-style description. IDF correctly drove their score to about zero, but the
  gate still counted them as matches, so any two of them opened it.
- **Rare ones decided the ranking.** `you`, `are` and `did` appear in only a few
  short descriptions, and IDF rewarded them for that rarity. The cat prompt's
  rank-1 skill was chosen on the word `did` alone (+2.52).

`retrieve.py` described its noise control as two layers, IDF plus a
≥2-matched-term gate. The intent was right: "2 distinct matched terms" was always
meant to mean 2 meaningful ones. The layers just didn't compose.

## The fix, and why not the obvious one

`tokenize()` now drops NLTK's english stopword list (179 words, copied rather than
imported) plus `use`, which `save_skill.validate()` guarantees in every
description. The list was fixed before anything was measured.

The obvious fix was frequency-based: ignore terms that appear in every document.
It was rejected. IDF runs over the session's *eligible* skills, which can be a
single skill, and with one skill every term is in every document. That filter
would never inject anything, and this was verified rather than assumed. A fixed
list behaves the same at one skill as at a thousand.

## Pre-registered check: six criteria, all passed

| criterion | before | after |
| --- | --- | --- |
| cat prompt admitted | 16/16 | **0/16** |
| correct skill still admitted, all 4 task prompts | yes | yes |
| one-skill library injects on a matching prompt | yes | yes |
| one-skill library injects on the cat prompt | **yes** | **no** |
| correct trap at rank 1 | 2/4 | **3/4** |
| cross-trap false duplicates | 0 | 0 |

Same-trap duplicate flags stayed at 7, so dedupe is unaffected on this corpus.

## What moved in the deterministic tools

| tool | before | after |
| --- | --- | --- |
| `gate_analysis`: real prompts admitted | 16/16 each | 5–10/16 |
| `rank_check`: consolidated library, `response_text` | wrong trap | **correct trap** |
| `selector_check`: `break`, lowest stable budget | ten 2900 / seven 1850 | ten 2800 / seven **1100** |
| `budget_sweep`: consolidated library at 1200 | wrong on `response_text` | **correct on both** |

## What this changes about earlier findings

- **The budget.** The argument for raising 1200 was that the wrong skill won
  `response_text` at 1200. A consolidated library now delivers the correct skill
  there. The budget derivation, selector_check's 1850, and E10's motivation were
  all measured against the old tokenizer. Those readings still describe that code
  accurately, but they no longer describe shipped retrieval.
- **E8 follow-up.** "Consolidation makes ranking worse" was true of the old
  tokenizer. Under the fixed one, consolidation *helps* ranking.
- **E12.** E12's remark that shipped retrieval admits the timezone skill on its prompts describes the pre-fix tokenizer. Under the fixed tokenizer, in a one-skill library as E12 ran, it clears the gate on 0 of 2 repair prompts. E12 stands as a measurement, because arm I's skill was installed and delivered by construction, but its point about ecological validity no longer describes shipped retrieval.
- **Session experiments, E5 through E12.** Their measurements are unaffected,
  because every row recorded what was actually delivered.

## Limits

The corpus is 16 skills, 4 prompts and 2 traps. The results are consistent with
this root cause but don't prove it generalises. What keeps this from being a
result tuned to the bench is that the list was fixed in advance, not the size of
the check. `response_text` still ranks the wrong skill first on the unconsolidated
library: it loses on the content words `function`, `make` and `test`, and the list
was not adjusted to chase that. No session has measured whether the fix changes
*outcomes*, and none of the current tasks can. See below.

## Confirmed through the real install-and-inject path

Reproduce with `python3 bench/real_path_check.py --baseline 06885c0`. It runs no
sessions.

The deterministic tools model delivery in-process. Sessions take a different path:
skills go in through `save_skill.py`, which compiles an index, and `retrieve.py`
reads that index as a hook. This check installed both pools through the real save
path into a sandboxed HOME and called the real hook once before the fix and once
after. Between the two commits, `scripts/` differs only in `retrieve.py`, so the
tokenizer is the only thing that changed.

| pool | task | before the fix | after the fix |
| --- | --- | --- | --- |
| ten | `response_text` | wrong trap | wrong trap |
| ten | `fingerprint` | right | right |
| seven | `response_text` | wrong trap | **right** |
| seven | `fingerprint` | right | right |

All four cells matched the prediction written down before the run. After the fix,
the real path agreed with `budget_sweep`'s model in every cell, all 17 skills saved
cleanly, and the operator's library was unchanged.

## Why no session batch followed

A session batch would add only the model's outcome, and no current task can show
that changing. The fix changes delivery only on `response_text`, whose control
already solves 6/6 without any skill, so better delivery can't raise its score.
`fingerprint` has headroom (0/21), but its correct skill already ranked first
before the fix, so there is nothing to compare. Measuring outcome needs a new
author-mode trap that the control can't solve unaided and whose delivered skill
the fix actually changes.

## A latent path mismatch found along the way

The first version of this check delivered nothing in any cell, before the fix or
after it. `save_skill.py` records a project root with symlinks resolved, but
`retrieve.in_scope()` compares paths as plain strings. The check's sandbox sat in
macOS's temp dir, `/var/folders`, which is a symlink to `/private/var/folders`.
So the unresolved `cwd` it passed never matched the recorded root, and every skill
was out of scope.

Real sessions aren't affected. Claude Code sends a physical `cwd`: bench sessions
run under `/tmp/skillforge-bench`, which is itself a symlink to `/private/tmp`,
and all 24 treatment rows in E12's re-run still recorded prompt-path injections.
The check now resolves its sandbox directory to match. `in_scope()` itself is
unchanged. Hardening it is a separate change, because `retrieve.py`, `detect.py`
and `reconcile.py` all use it, and `retrieve.project_key()` already resolves
`cwd` while `in_scope()` doesn't.

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

Environment: each clone's history was stripped to a single fresh baseline
commit before this batch, so no session could read the fix; the plugin under
test was at `4df0d02`. No skill was injected on any row. 22 sessions including
the allowance probe, no session failures.

## Limits

n = 6 bounds C's floor only loosely: 0/6 is consistent with a true rate up to
about 39% (§11 threat 4). The reference's lifetime 0/24 mixes environments from
before and after the history strip.

# E13 trap C — distil, qualify, probe (2026-09-14)

Pre-registered in `docs/superpowers/specs/2026-09-13-e13-author-traps-design.md`
§5–§8, planned in `docs/superpowers/plans/2026-09-14-e13-trap-c-skill.md`. C was
the only survivor of the E13 screen.

**Result: C is not a working trap.** Its deliverable drafts resolved 7 of 15 probe
runs, one short of the pre-registered half. Under §6 it serves neither trap 1 nor
trap 2, so the §8 outcome test on the tokenizer fix did not run, and both traps go
back to the candidate list (§4).

## Stage 1: distillation (6 sessions)

`bench/distill.py --trap C`, both distillers, novelty gate off, 3 draws each, from
the repair task `sf-repair-verdict-from` (graded:
`test_a_rewrapped_quote_still_counts_as_evidence`, the one fix-added test the
historical function fails).

| draw | outcome | skill |
| --- | --- | --- |
| `learn-nogate/1` | saved | `whitespace-insensitive-evidence-gate` |
| `learn-nogate/2` | saved | `whitespace-insensitive-evidence-quotes` |
| `learn-nogate/3` | saved | `whitespace-tolerant-quote-evidence` |
| `learn-failure-nogate/1` | saved | `verbatim-quote-gate-breaks-on-rewrapped-text` |
| `learn-failure-nogate/2` | saved | `verbatim-quote-check-breaks-on-rewrapped-whitespace` |
| `learn-failure-nogate/3` | saved | `verbatim-quote-gate-breaks-on-rewrapped-llm-quotes` |

Every repair resolved, with no rejections and no session failures. The three
anti-skills chose global scope and were contained; the operator's library was
empty afterwards.

## Stage 2: qualification and delivery (0 sessions)

`bench/e13_qualify.py --trap C`: the consolidated seven plus each draft, installed
through the real `save_skill.py`, with the real hook run on C's author prompt at the
shipped 1200 budget from `06885c0` (before the tokenizer fix) and `9cbb472` (after
it). `scripts/` was unchanged since `9cbb472`.

| draw | old hook delivers | new hook delivers | qualifies | delivered alone |
| --- | --- | --- | --- | --- |
| `learn-nogate/1`–`3` | yes | yes | no | yes |
| `learn-failure-nogate/1` | no | yes | **yes** | yes |
| `learn-failure-nogate/2` | no | no | no | **no** |
| `learn-failure-nogate/3` | no | yes | **yes** | yes |

The first qualifying draft was `learn-failure-nogate/1`. Five of six were
deliverable, so five were probed.

## Stage 3: probe batch (18 sessions)

`bench/e13_probe.sh --trap C`, read by
`bench/e13_probe_read.py --trap C --window 2026-09-14T14:31:15 -`.

| cell | resolved | injected its draft |
| --- | --- | --- |
| control | 0/3 | — |
| `learn-nogate/1` | 0/3 | 3/3 |
| `learn-nogate/2` | 0/3 | 3/3 |
| `learn-nogate/3` | 1/3 | 3/3 |
| `learn-failure-nogate/1` | 3/3 | 3/3 |
| `learn-failure-nogate/3` | 3/3 | 3/3 |
| **pooled drafts** | **7/15** | |

The batch is valid: the control held at 0/3, every treatment row injected its
draft, and no session failed. The criterion is pooled resolution of at least half,
and 7/15 is below it.

A first attempt at 14:09:15 hit the session limit during `learn-failure-nogate/1`.
§3 and §7 require a postponed batch to be re-run whole, so its 15 rows are kept but
excluded, and nothing was read from them.

## What the split suggests (exploratory, not pre-registered)

The pooled figure hides a clean split. The three `learn` skills resolved 1 of 9,
no better than the control. They are procedures that spell out the fix, collapsing
whitespace on both sides of the evidence comparison, and two of them name
`verdict_from` itself. The two `learn-failure` anti-skills resolved 6 of 6. They
describe the trap instead: a byte-exact check on a model's quote rejects real
quotes that the model re-wrapped across a line break. Every failing session missed
the same test, `test_a_rewrapped_quote_still_counts_as_evidence`. The two
anti-skills that went 6/6 are also the two drafts that qualify for the tokenizer
test.

The two groups differ in more than wording. The anti-skills are `kind: antiskill`
at global scope and the skills are `kind: skill` at project scope, so their
framing, and possibly their delivery, differ too. Every probe row still recorded
its draft as injected.

That is a hypothesis for a future pre-registered experiment, not a finding. The
pooling rule was fixed before any delivery was seen, and it governs here. Each cell
is n = 3, and the anti-skill cells come from two draws of one distiller.

## Limits

- n = 3 per draft and 3 control runs; 7/15 against a half-bar is close to the line.
- One library (the consolidated seven) and one model.
- The distillers ran with the novelty gate off (§11 threat 5).
- The operator's global library was containment-checked, but sessions run with
  bypassed permissions and could read files on disk (history strip, 2026-09-14).

# E14 stage 1 — does a draft's trigger or its kind decide whether it is used? (2026-09-14)

Spec: `docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md`, written
before any E14 session. Plan: `docs/superpowers/plans/2026-09-14-e14-trigger-kind.md`.

## Headline

**Neither factor reaches the pre-registered bar, and the baseline moved.**

| cell | trigger | kind | resolved |
| --- | --- | --- | --- |
| control | — | — | 0/3 |
| sf | failure | skill | 4/6 |
| sw | write | skill | 5/6 |
| af | failure | anti-skill | 6/6 |
| aw | write | anti-skill | 6/6 |

- **Trigger effect** = (SW + AW) − (SF + AF) = **+1**: no large effect (Fisher p = 1.000).
- **Kind effect** = (AF + AW) − (SF + SW) = **+3**: ambiguous (Fisher p = 0.217).
- **Baseline check:** E13 predicted SF ≤ 1 and AF ≥ 5. AF held (6/6); **SF moved (4/6)**.
- **Stage 2 is not triggered** (no effect reached +4).

Reader output, verbatim (`python3 bench/e14_read.py --window 2026-09-14T21:03:29 -`):

```
batch: complete
  control  valid 3/3  resolved 0  invalid 0
  sf       valid 6/6  resolved 4  undelivered 0  invalid 0  complete
  sw       valid 6/6  resolved 5  undelivered 0  invalid 0  complete
  af       valid 6/6  resolved 6  undelivered 0  invalid 0  complete
  aw       valid 6/6  resolved 6  undelivered 0  invalid 0  complete
trigger effect: +1 -- no large effect (Fisher p = 1.000)
kind effect: +3 -- ambiguous (Fisher p = 0.217)
baseline: SF 4/6 (MOVED), AF 6/6 (as predicted)
```

## What the batch was

- 27 sessions in the pre-registered interleaved order, 21:03–21:32, on
  `claude-opus-5`. No repeats were needed: every row was sandboxed, audited
  `clean`, delivered its draft, and ended its session normally.
- Every row ran against one plugin snapshot, `archive:e2ca580`. The delivery
  check ran at `36977b5`, and the batch guard confirmed `scripts/` and `hooks/`
  are unchanged between them.
- Repeats would have run in reader order (control, then sf, sw, af, aw) rather
  than strictly "in the order they arise" (spec §4). This was recorded as a ruling
  before the batch; no repeat ran, so it did not apply.

## Reading

**What this rules out.** The E13 split (anti-skills 6/6, skills 1/9) does not
replicate as a large trigger effect: a write-time `Use when:` line gained one
run over a failure-time one.

**What it cannot settle.** Anti-skills beat skills again (12/12 against 9/12),
but +3 is inside the pre-registered ambiguous band.

**The baseline moved, and that is the main finding.** The skill-failure draft
kept E13's failure-time trigger, yet resolved 4/6 where the E13 skill drafts
resolved 1/9. Whatever made those drafts fail was mostly in the rewrite, not in
the trigger or the kind. Differences between E13's `C/learn-nogate/1` and this
cell, all identical across E14's four cells and so not tested here:

- the description now names `validate.verdict_from` as an example of the gate
  in its first sentence, rather than only inside the `Use when:` line;
- the hidden test's name (`test_a_rewrapped_quote_still_counts_as_evidence`) is
  gone from the trigger and the Verification section;
- Procedure step 1 describes the naive check as "the naive version", instead of
  telling the session to find an existing substring check in a function whose
  body is a stub.

This list is exploratory. Which of these matters is a new, unregistered question.

## Limits and caveats

- 6 runs per cell, one trap, hand-written drafts. Session reasoning is not
  visible: thinking blocks are stored empty.
- **Kind is a bundle, as the spec allows.** Only the skills carry the
  Verification lines. Only the anti-skills say "anti-sycophancy" and "no
  exception is raised". The skills give the fix before the explanation, the
  anti-skills after it.
- **All four drafts quote strings from the hidden test's fixtures**
  (`flush() before\n   close().` and `close() before Call flush().`, both in
  `tests/test_validate.py` at `c0d7d88`). This is inherited from the E13 drafts
  and identical in every cell, so it does not confound the comparison, but
  absolute resolve rates may be higher because of it.
- The batch script's final summary read does not fail closed on a reader crash
  (parked at the final review). The verdict above comes from an independent
  read, not from the script's last line.

## Data

- `results.jsonl`: the 27 rows after 2026-09-14T21:03:29.
- `bench/drafts/E14/`: the four drafts and `delivery.json`.
- `bench/e14_read.py`, `bench/e14_deliver.py`, `bench/e14_probe.sh`.

# E15 — do three writing rules make the skills distiller's drafts work? (2026-09-16)

Spec: `docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md`, written
before any E15 session, with four dated amendments. Handoff:
`docs/handoff-2026-09-15-e15.md`.

## Headline

**The rules help, by the largest margin the design can show.**

| arm | drafts | resolved |
| --- | --- | --- |
| control (no skill) | — | 0/3 |
| variant (distilled under the three rules) | 6 | **18/18** |
| baseline (E13's `C/learn-nogate/1..3`) | 3 | **0/9** |

- **d = V − B = +1.00**: "the rules help" (spec §5 row 1: d ≥ +0.40 and V ≥ 0.50). Fisher p < 0.001.
- **Baseline check:** E13 measured these drafts at 1/9; here 0/9. Not moved.
- **Consequence:** the three paragraphs go into `skills/distilling-skills/SKILL.md`, as their own reviewed commit.

Reader output, verbatim (`python3 bench/e15_read.py --window 2026-09-16T10:06:14 -`):

```
batch: complete
  control  valid 3/3  resolved 0  invalid 0
  variant  learn-e15-nogate/1/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 2  complete
  variant  learn-e15-nogate/2/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 0  complete
  variant  learn-e15-nogate/3/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 0  complete
  variant  learn-e15-nogate/4/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 0  complete
  variant  learn-e15-nogate/5/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 0  complete
  variant  learn-e15-nogate/6/SKILL.md        valid 3/3  resolved 3  undelivered 0  invalid 0  complete
  baseline learn-nogate/1/SKILL.md            valid 3/3  resolved 0  undelivered 0  invalid 0  complete
  baseline learn-nogate/2/SKILL.md            valid 3/3  resolved 0  undelivered 0  invalid 0  complete
  baseline learn-nogate/3/SKILL.md            valid 3/3  resolved 0  undelivered 0  invalid 0  complete
V 18/18  B 0/9  d = +1.00 -- the rules help (Fisher p = 0.000)
```

## Stages A–C

- **A, smoke (1 session):** passed — saved, sandboxed, audit `clean`, variant
  mark recorded (`+e15-9dacd4a3905a`). Never probed. Its draft named
  `tests/test_validate.py` in its verification command (`names_test` true); the
  other two rules held.
- **B, draws (6 sessions), attempt 1** (`49f3ae3`, kept as
  `learn-e15-nogate-postponed-1`): 6/6 saved, but draws 2, 4 and 5 were
  `tainted`, a harness failure under amendment 1. Draws 4 and 5 only did
  `cd <snapshot>/scripts` and read `save_skill.py`; draw 2 read `validate.py`
  after a `cd` the audit could not follow. Amendment 3 (only the fixed file
  taints; the audit follows `cd`) was made, and the stage re-run whole. The
  attempt-1 draws were not re-scored.
- **B, attempt 2** (`83953c2`): 6/6 saved, sandboxed, none tainted. Draws 2–4
  have audit `leak` confined to the snapshot's `scripts/save_skill.py`, which
  amendment 3 allows. All six counted; no harness failure.
- **C, delivery, compliance, freeze** (`3b23ebe`, run at `83953c2`): every
  draft delivered alone by HEAD's prompt hook; operator's library untouched.

| draft | delivered | names a test | a `Find` step | function in first sentence |
| --- | --- | --- | --- | --- |
| variant 1–6 | all | none | none | all six |
| baseline 1–3 | all | all three | all three | none |

The variant drafts obeyed the rules completely and the baseline drafts broke
all three, so the comparison is between drafts that actually differ on the
rules, not between two labels.

## What the batch was

- Attempt 3: 32 sessions, 10:06–10:31 on 2026-09-16, one window, all on CLI
  2.1.266, `claude-opus-5`, plugin commit `945f8df`. The pre-registered order
  (30 runs) plus two repeats.
- The two repeats replaced variant 1 rows that `audit.counts()` rejected: their
  audit flagged the bench workdir's own `before.txt` and `after.txt`. Both
  rejected rows also resolved, so excluding them changes nothing.
- **Mechanism.** Every unresolved session — all three controls and all nine
  baseline runs — failed exactly one graded test,
  `test_a_rewrapped_quote_still_counts_as_evidence`, the byte-exact-match bug
  trap C was admitted for. Every variant run passed it.
- **Two earlier batches are excluded.** Attempt 1 (`E15_START`
  2026-09-15T12:10:52, 15 rows) and attempt 2 (19:56:46, 25 rows, 36 minutes
  into a fresh window) were cut off at the session limit; under the original
  §3 a postponed batch is re-run whole. A batch needs 31–39 sessions and a
  window held about 25, so **amendment 4** (2026-09-16) let a batch pause at
  the limit and resume, re-running a cut-off session in place, with one CLI,
  model and plugin commit required across the batch. Attempt 3 fitted in one
  window, so the resume path never ran.

## Limits and caveats

- **Pre-registration was bent, and in the open.** Amendment 4 was written after
  40 rows from the excluded attempts had been visible, and those rows already
  leaned the same way. It changed only how a session-limit cut-off is handled,
  was triggered by the clock rather than the outcomes, and was not exercised.
  The bands, counts and drafts were fixed before any probe.
- **The sandbox bias runs one way.** The E13 baseline drafts were distilled
  unsandboxed and unaudited; the variant drafts under both (ruling 3). The
  baseline sessions could read more and still scored 1/9 then and 0/9 now, so a
  "help" result is the readable direction.
- **One trap, one task, 3 runs per draft.** Pooled V and B rest on 18 and 9
  runs. The effect is saturated (18/18 against 0/9), so its size here says
  nothing about other traps.
- **The three rules are bundled.** No single rule is identified. E14 already
  showed a hand rewrite with all three differences at 4/6.
- **Fixture strings don't explain it.** All six variant drafts and baseline
  drafts 1 and 3 quote the hidden test's fixture text (`flush() before …`),
  yet baseline 1 and 3 resolved 0/6.
- **Different distill dates.** The variant drafts were distilled on
  2026-09-15, E13's on 2026-09-14, both on `claude-opus-5`, which has no dated
  snapshot. The probe itself re-ran both groups in one batch.
- **Reasoning isn't visible:** thinking blocks are stored empty.
- **Resolution** (from the handoff's power check): at V 0.67 / B 0.11 "help" is
  read about 82% of the time. The observed rates are well past that.

## Data

- `results.jsonl`: the 32 rows after 2026-09-16T10:06:14. Excluded: the 15
  rows 2026-09-15T12:10:52–12:26:06 and the 25 rows 19:56:46–20:26:39.
- `bench/distilled/C/learn-e15-nogate/` (the six draws),
  `learn-e15-nogate-postponed-1/` (stage B attempt 1, excluded),
  `learn-e15-smoke-nogate/`, `e15-probe.json`.
- `bench/variants/E15/distilling-skills.md`; `bench/e15_prep.py`,
  `bench/e15_read.py`, `bench/e15_distill.sh`, `bench/e15_probe.sh`.

---

# E16 screen — do either of two new author traps have a zero floor? (2026-09-16)

Spec: `docs/superpowers/specs/2026-09-16-e16-author-traps-design.md`, written
before any E16 session ran.

## Headline

**Both rejected. The trap well is dry in this shape.**

| cand | fix | function | control | verdict |
| --- | --- | --- | --- | --- |
| F | `ea4c47f` | `reconcile.read_markers` | **1/6** | rejected — non-zero floor |
| G | `58ce279` | `ledger.event_totals` | **6/6** | rejected — ceiling |
| R | `ab4acfe` | reference | **0/3** (0/28 lifetime) | the screen is valid |

Reader output, verbatim
(`python3 bench/e16_screen_read.py --window 2026-09-16T11:44:14 -`):

```
screen: complete
  reference sf-author-fingerprint-preexisting  valid 3/3  resolved 0  invalid 0
  candidate sf-author-read-markers             valid 6/6  resolved 1  invalid 1  rejected  unresolved: trap 5, wider 0
  candidate sf-author-event-totals             valid 6/6  resolved 6  invalid 0  rejected  unresolved: trap 0, wider 0
```

## F is not the same kind of rejection as G

G resolved 6 of 6: the docstring suffices and there is no trap, exactly as E13
found for D and E.

F did not. It resolved 1 of 6, and **each of the five unresolved sessions
failed exactly one graded test of 64** —
`test_read_markers_skips_junk_without_losing_good_lines`, the historical bug's
own. Five sessions implemented `read_markers` correctly in every other
respect and wrote an `except` clause too narrow for `RecursionError`. The trap
is real and it springs; it is not reliable.

**It is still rejected, and the rule that rejects it is the right one.** A 1/6
floor is the same figure as `response_text`'s 1/6, which this project read as
noise for four batches before E10 retired the task at 6/6. Spec §3.3 fixed
"any valid control row resolved rejects" before the data existed, and
reinterpreting it now to keep a nearly-good trap is the exact failure mode the
pre-registration exists to prevent.

Section 3.3's attribution gate never became load-bearing: it exists to catch a
0/6 floor the trap did not produce, and neither candidate reached 0/6. It did
its second job, which was to make the difference between F and G legible
instead of collapsing both into "rejected".

## The first batch to pause and resume

E16 is the first screen to run under E15 amendment 4 rather than E13's
postpone-and-re-run-whole rule, and the machinery worked unattended:

- 12 runs at 11:44–11:54, then the session limit. The cut-off row
  (`sf-author-read-markers`, 11:54:43, 8 seconds after the previous run) is
  `session_ok: false`, shows 64 failing tests because it was killed mid-run,
  does not count, and did not take its slot.
- The script polled every 10 minutes for 2h45m and resumed at **14:42:38**,
  two seconds after the 2:40pm reset.
- Every row of the batch carries one environment —
  `2.1.266 (Claude Code) | claude-opus-5 | archive:cb24585` — so the reader
  read it as one batch rather than `mixed`.

Interleaving earned its place: each cell's six runs are spread across both
windows, so the window boundary is not confounded with any one candidate.

## What this corrects

`docs/session-handoff.md` §3.8 says the bench has one usable trap. It had
**two** before this screen, and still does. From every valid control row in
`results.jsonl`:

| task | control | with a good skill |
| --- | --- | --- |
| `sf-author-fingerprint-preexisting` | 0/28 | pilot 5/6 |
| `sf-author-verdict-from` | 0/23 | E15 variant drafts 18/18 |

E13 §6 read trap C as serving neither of its traps. That measured E13's own
drafts, not the task; E15 then took the same task to 18/18. A task with a zero
floor that a good skill takes to ceiling is a working trap.

## Limits and caveats

- **Two candidates, not a survey.** They were the only two open fix commits
  whose change is one top-level function that existed at the parent carrying a
  docstring. Spec §1.1 records why each of the other 27 fails that shape, so
  the field is exhausted for this construction — not for author-mode traps in
  general.
- **The pre-flight departure did not decide anything.** §2.1 counts tests the
  fix added *or changed*, because F's fix modified an existing test. Both
  candidates were VALID and both were rejected on session data, so the rule
  change never carried a verdict.
- **F's floor rests on 6 runs.** 1/6 and 0/6 are one session apart. The
  rejection is a pre-registered decision, not a claim that F could never be a
  trap at larger n.
- **Threat 1 was the outcome, twice.** Both docstrings state the property the
  historical bug broke, and a fresh model mostly just reads them correctly.
  Three of five candidates screened this way (D, E, G) resolved at ceiling.
- **Nothing follows.** §4's distillation is not triggered, and §1.1's
  next-in-line (`7a1d3ac`) needs a fresh contract of the kind E13's trap E
  already failed at 6/6.

## Data

- `results.jsonl`: the 16 rows after 2026-09-16T11:44:14. Fifteen valid, one
  `session_ok: false` (the limit cut-off), re-run in place under amendment 4.
- Spec `docs/superpowers/specs/2026-09-16-e16-author-traps-design.md`.
- `bench/e16_preflight.py`, `bench/e16_screen.sh`, `bench/e16_screen_read.py`,
  `bench/stubs/stub_read_markers.py`, `bench/stubs/stub_event_totals.py`.
- Tasks `sf-author-read-markers` and `sf-author-event-totals` stay in
  `bench/tasks.json`: their pre-flight is valid and their floors are now
  measured, which is exactly the record a later session needs in order not to
  re-screen them.

---

# Q4 — what does a unit of benefit cost in tokens? (2026-09-16)

`bench/q4_token_cost.py`. Deterministic, 0 sessions, no model. This row read
"No experiment exists" until today; none was needed, because every input was
already on disk.

## The metric

For one task and one injected skill:

```
cost  = retrieve.injection_cost(whole file)      -- what the selector charges
lift  = treatment resolved rate - control rate
price = cost / lift                              -- tokens per ADDITIONAL resolution
```

The script imports `retrieve.injection_cost` rather than restating it, so the
number is the one the shipped selector charges, frontmatter included. It reads
only tasks whose control floor is **measured at zero** — derived, not
hardcoded, which selects exactly the two working traps. Rows are filtered by
`audit.counts` plus `session_ok`, as every other reader filters them.

## Headline

**~1,100 tokens per additional resolved run, and the two traps agree to within
nine tokens without being made to.**

| trap | control | paid | gained | price |
| --- | --- | --- | --- | --- |
| `sf-author-fingerprint-preexisting` | 0/28 | 30,810 tok | 28 | **1,100 tok each** |
| `sf-author-verdict-from` | 0/23 | 77,520 tok | 71 | **1,091 tok each** |

Two traps, different skills, across the pilot, E7, E9, E13, E14 and E15.

## Three things that fell out

**Hand-written drafts are the cheapest benefit on this bench.** E14's four
hand-written drafts cost 503–510 tokens — 42% of the 1,200 budget — at 4–6 of
6, for a best price of **507 tok/resolution**. E15's distilled drafts, on the
same trap and the same task, cost 798–945 (66–79% of budget) for a best price
of 798. The distillers write long, and the selector charges every byte.

**Distilled drafts crowd the budget ceiling.** Trap B's sit at 80–99% of
1,200; `B/learn-nogate/1` is 1,192 — eight tokens of headroom. This
*corroborates* handoff §3.3 rather than discovering it: the save-time size
guard shipped 2026-09-13 for exactly this reason, and quotes the same
759–1,192 range. Q4 adds the wider corpus and the consequence — the guard
refuses an oversized draft rather than shortening it, so the distillers'
length habit now surfaces as a refused save instead of a silent
non-injection, and the cheapest drafts on the bench are the hand-written ones
at 42% of budget.

**Two drafts have no price, only a bill.** `C/learn-nogate/1` and `/2` resolved
0 of 13 each, at 647 and 779 tokens: ~18,500 tokens paid for zero resolutions.
`C/learn-nogate/3` is the expensive tail at 2,142 tok/resolution.

## Limits and caveats

- **It prices benefit where benefit exists, and nowhere else.** Both priced
  tasks have a control of exactly zero, so `lift` is just the treatment rate.
  The metric is untested against a mid-range control, because this bench has
  never had one.
- **Not read:** repair-mode tasks (control already at ceiling, no room to
  lift), `sf-author-response-text` (retired, control 7/19), and E16's two
  rejected candidates. The script prints each with its control.
- **Multi-skill runs are excluded.** When two skills inject, the cost cannot
  be attributed to one, which drops the dilution arms of E6, E10 and E12 —
  harm measurements, not benefit measurements.
- **Lifetime rows, pooled across batches.** This is a cost ratio rather than a
  contrast between arms, so it does not need one batch's window. It therefore
  inherits every batch's environment differences.
- **Cost is exact; benefit is not.** `injection_cost` is a formula over bytes.
  The resolved rates behind `lift` carry the n of their own experiments, some
  as low as 3.
- **Price is not value.** Tokens per resolution says nothing about whether the
  resolution was worth 1,100 tokens of every future prompt.

## Data

- `bench/q4_token_cost.py` (`--json` for the raw cells);
  `tests/test_bench_q4.py`, nine cases on fixed rows, no model.
- `results.jsonl`, every valid row carrying a resolvable `skill_path`;
  the draft files under `bench/distilled/`, `bench/drafts/` and `bench/skills/`.

---

# E17 — does the critique gate predict whether a skill works? (2026-09-16)

Spec: `docs/superpowers/specs/2026-09-16-e17-critique-gate-prediction-design.md`,
written before any call, plus amendment 1 (also before any call). Brief Q5.

27 `claude -p` critique calls over E15's nine frozen drafts — no bench session,
no clone, no ledger row, no trust entry. The corpus splits cleanly on
**outcome**: V (`learn-e15-nogate/1..6`) resolves 18/18 on
`sf-author-verdict-from`, B (`learn-nogate/1..3`) resolves 0/9.

## Headline

**Q5 is answered: no. The gate does not prefer the drafts that work, and its
verdict is not reproducible on unchanged text.**

```
stability: unstable -- 4 of 9 drafts unanimous over 3 calls (needs 7)
  V   learn-e15-nogate/1   fail fail fail    fail
  V   learn-e15-nogate/2   fail pass fail    fail
  V   learn-e15-nogate/3   pass fail pass    pass
  V   learn-e15-nogate/4   fail fail fail    fail
  V   learn-e15-nogate/5   fail fail fail    fail
  V   learn-e15-nogate/6   fail fail pass    fail
  B   learn-nogate/1       pass pass pass    pass
  B   learn-nogate/2       pass fail pass    pass
  B   learn-nogate/3       fail fail pass    fail
V 4/18  B 6/9  delta = -0.44 -- the gate predicts backwards (Fisher p = 0.039)
```

## The stable half: the verdict does not reproduce

**Five of nine drafts returned different verdicts across three calls on byte-identical
text.** Four were unanimous; §3.2 needed seven.

This half is clean. It has no confound, it does not depend on which group a
draft is in, and it is a property of the shipped promotion gate rather than of
this corpus: `critique == "pass"` is a required conjunct of `trusted` in
`ledger.confidence()`, and re-running it on an unchanged file can change the
answer. `validate.main()` early-returns on an existing verdict for a hash, so
in production **whichever verdict landed first is the one that sticks**, and
this measurement says it is close to a coin-flip for half the library.

It also corroborates `bench/critique-calibration/`, which saw case 07 read
`pass`, `pass`, `fail` at n=2. E17 puts that at n=9 drafts × 3.

## The unstable half: do not read the direction

d = −0.44 lands in the pre-registered "predicts backwards" band, and it is
reported because it was pre-registered. **It should not be believed as a claim
about outcome**, for two reasons decided before the data:

**Threat 4 fired completely.** Draft length is perfectly rank-separated from
group — the three B drafts are the three shortest files, the six V drafts the
six longest, with no overlap:

| bytes | group | passes |
| --- | --- | --- |
| 2590 | B | 3/3 |
| 2856 | B | 1/3 |
| 3116 | B | 2/3 |
| 3192 | V | 1/3 |
| 3212 | V | 2/3 |
| 3351 | V | 0/3 |
| 3435 | V | 0/3 |
| 3672 | V | 0/3 |
| 3782 | V | 1/3 |

r(bytes, passes) = **−0.70**. "Critique prefers the drafts that do not work"
and "critique prefers shorter drafts" make the same prediction here, and this
corpus cannot separate them. The second is independently plausible: the
calibration corpus records that critique's objections are usually real, and a
longer file offers more surface to object to.

**It is fragile to one draft.** `B/learn-nogate/1` is 3/3. Drop it and
d = −0.28 with p = 0.307 — the ambiguous band.

**What survives both:** critique does not prefer the working drafts. V 4/18
against B 6/9 rules out the useful direction at this n whatever explains the
negative one.

## The spec's own prediction was wrong

§4 was written in advance and said the likely result was degenerate — pass
everything or fail everything, d ≈ 0 — because critique passed all 4 Q1 drafts
and failed all 9 hand-written calibration skills. It did neither. Recording
that here because §4 existed precisely so the prediction could be scored.

## What it changed in the shipped path

E17's stable half is a defect, not a curiosity, and `scripts/validate.py` now
carries the fix. `main()` cached any non-`inconclusive` verdict against the
content hash and early-returned on it forever after, so **one unlucky critique
capped a skill permanently, for that text**, with editing the file the only
escape — and the notice from `3095587` told the author to "read the findings,
fix the skill", advice that is wrong when the failure was noise.

A critique `fail` is now **re-asked once, and cached only if it reproduces.**

The asymmetry is deliberate and only the veto is re-asked. `critique == "pass"`
is necessary but **not sufficient** in `ledger.confidence()` — promotion still
needs an executable pass or organic trust, plus `fresh` — so a false pass costs
nothing on its own, while a false fail is an unconditional cap. Re-asking is
also strictly more protective than a best-of-three majority at a third of the
cost: for a draft that passes a third of the time, two consecutive fails happen
44% of the time against a majority-of-three's 74%. The cost is one extra call,
on the failing path only, once per content hash.

This is the same rule R12 already applied to `inconclusive` — a transient must
not become permanent — extended to the other answer E17 showed is not
reproducible. `executable` mode is untouched: its transient failures are
already `inconclusive`, and a re-ask would spend a second worktree and model
call on every one.

Knock-on: `bench/e13_qualify.py` guards on `plugin_drift(NEW_REF)` and now
refuses to run, because `scripts/` has moved past `9cbb472`. That is the guard
working. A future trap-2 qualification must re-pin its own snapshot.

## Limits and caveats

- **The fix is not measured.** It follows from E17's instability plus a reading
  of `confidence()`, and no batch has been run against it. What is measured is
  that the verdict flips; that re-asking helps is arithmetic, not evidence.
- **The findings were not saved.** The first run kept only verdicts, so this
  experiment cannot say *why* critique failed the drafts that work — which is
  exactly what would separate "length" from "outcome". `bench/critique-calibration/run.py`
  has always saved them; `bench/e17_q5.py` now does too, from this commit on.
  Testing the length hypothesis costs another 27 calls.
- **n is small and one-sided.** B is 3 drafts, 9 calls. Fisher p = 0.039 is
  reported and not thresholded, per this project's convention.
- **One trap, one bug, one distiller.** All nine drafts are `learn` drafts
  about `validate.verdict_from`. Nothing generalises beyond this corpus.
- **Critique judges legibility, not whether the fix lands** (threat 1). Its
  rubric is `followable`, `preconditions`, `checkable`. "Does not predict
  outcome" is not an indictment of the rubric; it is a statement about what
  the `trusted` conjunct buys. The instability finding *is* a defect claim,
  and it stands on its own.
- **Different model from the bench rows.** Critique runs on `sonnet`
  (`validate.DEFAULT_MODEL`); the V/B outcomes were measured on
  `claude-opus-5`. Recorded, not controlled — the shipped gate is what Q5 asks
  about.
- **Amendment 1 never fired.** No call came back inconclusive, so no draft was
  dropped and the transport guard was not exercised.

## Data

- `bench/e17-q5-results.json` (9 drafts × 3 verdicts); `bench/e17_q5.py`
  (`--read`, `--dry-run`); `tests/test_bench_e17_q5.py`, 11 cases on fixed
  verdicts, no model.
- The corpus is unmodified: `bench/distilled/C/learn-e15-nogate/1..6/SKILL.md`
  and `bench/distilled/C/learn-nogate/1..3/SKILL.md`.
