# E6 — does an irrelevant skill dilute a relevant one?

Design written 2026-09-09, after Q1. Nothing here has been run. The viability
figures in §3 were measured; every other number is a slot.

## The question

**Does a relevant skill still work when an irrelevant one rides along with it?**

In production a session does not receive one curated skill. It receives
whatever the library matched, and hot-tier skills enter unconditionally. The
realistic failure is not "an irrelevant skill instead of a relevant one" — it is
an irrelevant skill *alongside* one, competing for attention and for the
injection budget.

## How this differs from E4, and why it is not a relabelling of it

The brief's Q3 — carried as E4 — asks whether injecting an irrelevant skill
hurts **versus nothing**. E6 asks whether it hurts **versus the relevant skill
alone**. Different comparators, different claims, and E6 does not answer E4.

E4 remains blocked for the reason it has always been blocked: it needs a task
whose control baseline is neither 0 nor 100%, and none exists. Live control
cells, superseded rows excluded:

| task | live control |
|---|---|
| `sf-author-response-text` | 1/6 |
| `sf-author-fingerprint-preexisting` | 0/6 |
| `sf-escaping-breaks-symptom-match` | 2/2 |
| `sf-truncation-reports-absent` | 2/2 |

The 1/6 looked like it might be the non-degenerate baseline E4 wants. It is
not: if the true rate is 1/6, a **harmless** arm reads 0/6 **33.5%** of the
time. There is no room to fall. (From a 50% baseline the same reading would
occur 1.6% of the time.)

E6 is answerable precisely because it inverts the direction: it measures a fall
from a **ceiling**, and Q1 established ceilings — distilled 12/12, hand-authored
matched 3/3 twice on `response_text`.

## 1. Design

Two arms, both run **in the same batch**. E5 established that this design's
spread across batches (6/6 versus 4/6 on one arm, nothing changed but the
batch) is wider than the effects it can resolve, so a cross-batch baseline is
not usable.

| Arm | Skills installed | Sessions |
|---|---|---|
| **R** — relevant alone | the task's own matched hand-authored skill | 6 |
| **R+I** — relevant plus irrelevant | that skill **and** `arrow-tzinfo-string-trap` | 6 |

Tasks: `sf-author-response-text` and `sf-author-fingerprint-preexisting`.
n=3 per cell. **12 sessions total**, ~15 minutes.

**The relevant skill is hand-authored, not distilled**, deliberately. The
question is about the library, not the distiller, so the relevant artifact must
be held constant. Q1's four distilled drafts are four different artifacts and
would confound artifact variance with the dilution effect. This is the same
reasoning E1 used when it re-authored the umbrella to hold `kind:` constant.

**No control arm.** The comparator for dilution is R, not control. Today's 1/6
floor is cited as context, with its own batch named.

## 2. Harness change

`install_skill` installs one skill. E6 needs two.

Add `--plus-skill <path>`, installing an additional skill into the same clone
store after the task's own. The clone path segment gains `-plus`, derived from
the flag rather than passed — every arm this harness has had passes
`--arm treatment`, and two arms sharing a clone path is how E5 lost a batch.

Result rows gain `extra_skills: [<name>, ...]`, empty for arm R.

## 3. Viability — measured, not assumed

Two things had to be true before this design was worth writing. Both were
checked against the code, with no sessions spent.

**The irrelevant skill is actually delivered.** Otherwise a null means "never
arrived", which is the trap Q1's pre-probe prediction exists to prevent.
`retrieve.rank` over `name + description` against each probe prompt:

| payload | `response_text` | `fingerprint` |
|---|---|---|
| `arrow-tzinfo-string-trap` (irrelevant) | **deliver**, score 2.53, matched 7 | **deliver**, score 2.53, matched 7 |
| `serialization-corrupts-matching` (relevant, rt) | deliver, score 1.87, matched 5 | — |
| `lossy-transform-false-negative` (relevant, fp) | — | deliver, score 2.55, matched 6 |

**The irrelevant skill outranks the relevant one on `response_text`** — 2.53
against 1.87. That is a finding before the experiment starts: BM25 over
`name + description` ranks a skill about `arrow` timezone handling above the
matched serialization skill for a prompt about `response_text`. E6 therefore
tests a realistic bad case rather than a contrived one, and it is the strongest
version of the question.

**Both skills fit the injection budget.** `INJECT_BUDGET_TOKENS` is 1200; the
relevant skills cost ~574 and ~561 tokens, the irrelevant one ~544. A pair
costs ~1118, 93% of budget. Both inject; neither is evicted.

That 93% is load-bearing. If the pair did not fit, R+I would measure **budget
crowd-out** — the relevant skill never arriving — rather than dilution. Those
are different findings with different fixes, and §5 requires they be told apart
from the injection rows rather than inferred from the score.

## 4. What gets measured

Per run, from the per-run ledger's `injection` rows (now copied onto the result
row):

- **Which skills injected.** Arm R+I must show both. A run showing only one
  measured crowd-out, not dilution, and is reported in its own line.
- **Trigger.** `prompt` expected for both; symptoms are dead in author mode.
- **Score.** The task's hidden tests, as every other experiment here.

## 5. Pre-registration

Fixed before any data exists.

- Both arms run in the same batch, R first.
- All 12 sessions run. No cell is dropped after its score is seen.
- Rows with `session_ok: false` are excluded and the excluded count reported,
  inheriting Q1's rule.
- **Harm is declared in advance as R+I scoring below R.** A result in the other
  direction — the irrelevant skill *helping* — is reported as-is and not
  reinterpreted.
- A run where only one skill injected is reported separately and is **not**
  pooled into the dilution cell.
- If arm R does not reproduce its ceiling, that is the headline and the
  dilution comparison is reported as uninterpretable rather than quietly read
  against a lower baseline than expected.

## 6. How to read the outcome

- **R+I ≈ R, both near ceiling.** An irrelevant skill that arrives, occupies
  half the budget, and costs nothing measurable. The strongest available
  evidence that injection does not hurt — and it makes E4's floor problem less
  urgent, without answering E4.
- **R+I clearly below R.** Injection can hurt. That is Q3's underlying concern
  answered by a different route, and it bears directly on the hot tier, which
  injects unconditionally.
- **R+I below R, but only one skill injected.** Crowd-out, not dilution. A
  budget finding, and the 1,500-token hot budget is the next thing to examine.
- **R below its own ceiling.** The batch is uninterpretable; say so.

## 7. Threats

1. **n=3 per cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6. Only a large dilution is detectable. A null is "no large effect",
   never "no effect".
2. **The ceiling is not guaranteed.** `response_text` matched is 3/3 twice;
   `fingerprint` matched is 2/3 and 3/3. If R lands at 4/6 the room to fall is
   thin and the design loses most of its power — §5 requires saying so rather
   than proceeding.
3. **One irrelevant payload.** `arrow-tzinfo-string-trap` is one skill about one
   unrelated bug. A different irrelevant skill could dilute more or less.
4. **93% budget occupancy is a knife edge.** A longer irrelevant skill would
   change the question from dilution to crowd-out. The measured figure is what
   makes this design valid today; re-check it if any payload changes.
5. **Two traps, one repository**, both in SkillForge's own codebase.
6. **Same-author curation.** The operator wrote the tasks, the traps, and both
   payloads.
7. Bench sessions inherit the operator's full plugin set.

## 8. Out of scope

E4 as specified (irrelevant versus nothing). Q4, token cost per unit of
benefit — E6 measures whether a second skill hurts, not what it costs. The
hot-tier budget, ranking, promotion and eviction, all still unevidenced.
