# E12 — does an irrelevant injected skill actively hurt?

**Status:** pre-registered 2026-09-13, before any session was run.

## The question

E4 (= brief Q3) has been open for the life of this project: **does injecting an
irrelevant skill actively hurt, versus injecting nothing?**

E6 answered the neighbouring question — an irrelevant skill *alongside a
relevant one* cost nothing, 6/6 versus 6/6 — but that is a different comparator
and does not answer E4.

## 1. Why E4 was blocked, and why it is not any more

The register records E4 as needing "a task whose control baseline is neither 0
nor 100%". **That framing is the error.**

**Harm cannot be measured on a floor task.** A control at 0/21 has nowhere to
fall. Every trap this bench ever selected as a discriminator was selected for a
zero floor — which is exactly the property that makes it useless for detecting
harm. That is why E4 stayed blocked while the bench accumulated traps.

E11 (2026-09-13) rejected two tasks as benefit discriminators for the opposite
reason: their control sits at the **ceiling**.

| task | mode | control, measured 2026-09-13 |
| --- | --- | --- |
| `sf-escaping-breaks-symptom-match` | repair | **6/6** |
| `sf-truncation-reports-absent` | repair | **6/6** |

Six of six, all three graded tests green in every session, median ~53s. Maximum
headroom to fall, and a baseline tight enough that a drop of two or three runs
is legible at n=6. What disqualified them for E11 is precisely what qualifies
them here.

## 2. Pre-flight — delivery, at zero session cost

An irrelevant skill cannot hurt if it never arrives. Delivery is gated on
`score > 0 and matched >= MIN_MATCHED_TERMS` (=2), and a genuinely irrelevant
skill is one that shares few terms with the prompt — so the gate that makes it
irrelevant could also keep it out.

Checked with `retrieve.rank()`, the shipped ranker, against both prompts:

| skill | role | score | matched | cost |
| --- | --- | --- | --- | --- |
| `arrow-tzinfo-string-trap` | irrelevant | 2.5259 | 7 | 544 |
| `lossy-transform-false-negative` | relevant to truncation | 1.8547 | 4 | 561 |
| `serialization-corrupts-matching` | relevant to escaping | 1.8663 | 5 | 574 |

**All three deliver on both prompts, and so do all 16 skills in the corpus.**

The reason matters: the repair prompts are generic scaffolding — "The test suite
… has failing tests. Run … then fix the source under scripts/". BM25 matches
*procedural boilerplate*, not topic. A timezone skill matching 7 terms against a
prompt about failing tests is the gate doing nothing useful.

Two consequences. First, the arm is **ecologically valid**: the shipped system
really would retrieve this skill on this prompt, so arm I is not a contrivance.
Second, this is a finding about retrieval in its own right, recorded here so it
is not discovered later and mistaken for a result of this experiment.

## 3. Design

### 3.1 Arms

Three arms per task, **all in one batch**, n=6 per cell. 36 sessions.

| arm | what is installed | payload |
| --- | --- | --- |
| C | nothing | — |
| R | the skill distilled from **this task's own bug** | 561–574 tokens |
| I | `arrow-tzinfo-string-trap` (timezone handling) | 544 tokens |

Arm R's mapping is the **swap** of `tasks.json`'s crossover pairing, because
this experiment wants genuine relevance rather than same-class transfer:

- `sf-escaping-breaks-symptom-match` (fix `22ddf37`) → `serialization-corrupts-matching`, distilled from `22ddf37`
- `sf-truncation-reports-absent` (fix `ab4acfe`) → `lossy-transform-false-negative`, distilled from `ab4acfe`

### 3.2 Why three arms and not two

A two-arm C-versus-I test confounds two explanations. Three arms separate them,
and the payloads are size-matched to within 30 tokens (544 / 561 / 574) so the
comparison is not about how much context was spent:

- **I below C, R at C** → irrelevance is what harms. Retrieval precision is
  load-bearing.
- **I and R both below C** → injection itself harms and relevance is beside the
  point. This would be the more consequential finding, and no two-arm design
  could distinguish it.
- **Neither below C** → no large harm from either at ~550 tokens.

### 3.3 Harness

No change. `bench/run.py --task <id> --runs 6 --arm control`, and
`--arm treatment --skill-from <abs path>` for R and I. `--skill-from` decides
the clone segment, so the three arms cannot collide.

## 4. Pre-registration

### 4.1 The criterion, fixed before data

Primary analysis is **pooled across both tasks**, 12 sessions per arm.
Per-task is secondary and reported but not decisive at n=6.

- **Harm declared** when a treatment arm is **≥ 3 of 12 below C**.
- **No large harm** when a treatment arm is within 1 of 12 of C.
- **Ambiguous** in between, and reported as ambiguous rather than resolved
  toward the tidier story.

Fisher's exact p is reported alongside for each contrast. It is a **reported
statistic, not a threshold** — n=6 per cell detects only large effects, and no
p-value is being used to license a claim this design cannot support.

### 4.2 Validity conditions that void the batch

- **C below 10 of 12.** The whole design rests on control sitting at the
  ceiling. If it has decayed since this morning, there is no headroom, and the
  batch measures nothing. Void, do not reinterpret.
- **An arm R or I row whose `injections` does not name the installed skill.**
  A treatment row where nothing arrived is not a treatment row. Void that row
  and re-run it; if it recurs, the arm is void.

### 4.3 Exclusions

Rows with `session_ok: false` are excluded and re-run, never scored. A refused
batch is postponed, not poisoned.

**The delivery smoke test is excluded by construction.** Before the batch, one
arm-I session is run to confirm `--skill-from` on a repair-mode task actually
lands the skill in `injections` — these two tasks have never had a treatment arm
run at all. That row is a mechanical check, is excluded from every analysis
here, and is named in the write-up. It is run **after** this spec is committed,
so it cannot inform the criterion.

### 4.4 The threat that is stated in advance, not afterwards

**Repair mode shows the model the failing tests.** That is a strong signal an
irrelevant skill must overcome before it can do damage. A null in arm I is
therefore ambiguous between "irrelevant injection does not harm" and "the
failing tests rescued it", and this design cannot separate those.

Writing that down now is what stops a null from being reported later as the
stronger claim. If arm I comes back at 12/12, the honest conclusion is "no large
harm **on a task whose tests are visible**", never "irrelevant injection is
harmless".

## 5. How to read the outcome

- **I ≥ 3 below C, R at C** — irrelevant injection actively harms. E4 answered
  in the affirmative for this setting; retrieval precision is load-bearing.
- **I and R both ≥ 3 below C** — injected context harms regardless of
  relevance at ~550 tokens. Larger than E4 and would reframe the budget work.
- **Neither below C** — no large harm at this payload size, subject to §4.4.
- **C below 10/12** — void (§4.2).

## 6. What this does and does not discharge

It answers E4's question **for repair-mode tasks at ceiling**. It does **not**
discharge E4 for author-mode tasks, and cannot: `fingerprint_preexisting` sits
at 0/21 with no headroom, and `response_text` was retired this morning. E4
stays partially open, and the register should say so.

## 7. Threats

1. **§4.4's visible tests.** The main one.
2. **n = 6 per cell, 12 pooled.** Large effects only. 12/12 versus 8/12 is
   Fisher p ≈ 0.09 — real-looking and not significant at this n.
3. **One payload size.** ~550 tokens. Harm may be a function of volume, and
   this holds volume roughly fixed by design to isolate relevance.
4. **Two bugs of the same class**, one repository, operator-curated.
5. **Ceiling baselines have a shelf life.** They were measured hours before
   this batch; §4.2 re-measures rather than inheriting them.

## 8. Out of scope

Author-mode tasks. Payload-size scaling. The retrieval-gate finding in §2,
which deserves its own investigation and is recorded, not pursued.
