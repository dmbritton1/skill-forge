# E7 — is the novelty gate over-refusing?

Design written 2026-09-10, after E6 and the graded scorer. Nothing here has
been run. The figures in §2 were measured from `bench/distilled/` and
`bench/results.jsonl`; every other number is a slot.

## The question

**Does the distiller's novelty self-gate refuse drafts that would have
worked?**

Q1 established that the distiller emits 4 times in 12, and that the four it
emitted scored 12/12 — verified here: the 12 rows in `results.jsonl` carrying
`skill_source: distilled` are all resolved, with no excluded sessions. The eight
refusals were never tested. Every one of them is the same self-assessment —
*a fresh Claude already knows this* — and it is unfalsifiable as long as the
refused drafts are never written.

The reason to doubt it: across every non-leaky batch, control resolves these
two tasks **once in fifteen attempts**. The gate is declining to record
knowledge the model demonstrably does not apply.

## Why this is the top of the chain

`/consolidate` is blocked because the library is empty. The library is empty
because the distiller rarely emits. The distiller rarely emits because of this
gate. Three deferred items in the handoff resolve to one measurement.

E6 sharpened it further. An irrelevant skill that arrives, outranks the
relevant one, and occupies 93% of the injection budget cost nothing
measurable (R 6/6, R+I 6/6, n=3 per cell). The gate's entire justification is
that junk saves pollute the library. Pollution now measures as close to free
on the one axis anyone has measured, while refusal measurably costs a working
skill. That asymmetry is what makes the gate worth testing rather than
trusting.

## 1. What the archive actually shows

The 12 Q1 draws are archived under `bench/distilled/<trap>/<distiller>/<draw>/`.
Read from `meta.json` — `outcome`, and the refusal reasoning in
`session_tail`:

| cell | task probed | outcome | reason given |
|---|---|---|---|
| A / learn-failure / 1,2,3 | `response_text` | **saved** ×3 | — |
| B / learn / 1 | `fingerprint` | **saved** | — |
| A / learn / 1,2,3 | `response_text` | aborted ×3 | novelty gate |
| B / learn / 2,3 | `fingerprint` | aborted ×2 | novelty gate |
| B / learn-failure / 1,2,3 | — | aborted ×3 | novelty gate **and** symptom shape |

**The eight refusals are not one population, and this is the finding that
shapes the design.** All eight cite the novelty gate. The three trap-B
anti-skill draws cite a second, independent blocker: trap B is silent, so no
literal error signature exists, and `distilling-failures` step 4 requires one.
Their own words — any `symptoms:` list "would be invented, and invented
triggers pollute the detection index". Suspending the novelty gate cannot
produce a draft from those three; the symptom requirement still blocks.

**E7 therefore targets the five `learn` refusals only.** Including the other
three would confound two mechanisms in one cell and is the kind of pooling
this project has already been burned by.

**A partial yield is expected.** Two of the five (`A/learn/1`, `A/learn/2`)
also name step 8, the requirement that `verification.command` fail when the
procedure is skipped. `A/learn/2` states it directly: "I cannot write a
verification command that fails when..." So a draw may clear the novelty gate
and still abort. §5 requires that be reported as its own result rather than
counted as a refusal — a gate that blocks emission is worth localizing, and
if it is step 8 rather than step 2, that is the answer to a different and more
useful question than the one asked.

**The drafts themselves do not exist.** `drafts_found` is 0 on every aborted
draw and nothing was written to disk. Only the reasoning survives. E7 re-runs
the draws under the lever; it does not recover the originals. §7 threat 1.

## 2. The comparator, re-derived

Historical control cells, counted from the files rather than quoted:

| task | `results.jsonl` | `results-round1.jsonl` |
|---|---|---|
| `sf-author-response-text` | 1/3 (09-09) | 0/3 (08-11) |
| `sf-author-fingerprint-preexisting` | 0/3 (08-11), 0/3 (09-09) | 0/3 (08-11) |

The rows are distinct — zero overlap on `(task, arm, run, ts)`. Pooled across
both files, control resolves 1 of 15.

**The "1/6 and 0/6" carried in three prior specs cannot be reproduced from one
consistent rule.** 1/6 for `response_text` requires pooling `round1` with the
September cell; 0/6 for `fingerprint` requires excluding `round1` and pooling
the two cells in the live file. One file is in for one task and out for the
other. Every reading puts both floors at or near zero, so nothing downstream
of those specs changes — but the figure is not re-derivable as stated and this
design does not repeat it.

`bench/results-leaky-stub.jsonl` is excluded entirely. Its 3/3 control is 3/3
because that stub leaked the answer.

**This is why E7 runs its own control in the same batch.** E5 measured one arm
twice across batches and got 6/6 and 4/6, a spread wider than the effects this
harness resolves. A cross-batch baseline is not usable, and an ambiguous one
is worse.

## 3. Design

### 3.1 The lever

`bench/distill.py:54` ends its prompt with:

> Follow its contract exactly, including the novelty self-gate -- aborting
> because the knowledge is model-obvious is a good outcome, not a failure.

`--no-novelty-gate` replaces that clause with one suspending step 2 and
leaving every other contract step in force. It is a bench lever, like
`--plus-skill` and the force-hot flag. **No product code changes** — neither
`skills/distilling-skills/SKILL.md` nor `save_skill.py` is touched, so the
gate this experiment questions remains exactly as shipped.

Result rows and `meta.json` gain `novelty_gate: false` so the arm is readable
from the data rather than inferred from the batch date. Every prior arm this
harness has had was told apart by a flag it recorded; E5 lost a batch to two
arms sharing a clone path, so the clone segment gains `-nogate` as well.

### 3.2 Arms

| Arm | Phase 1 | Phase 2 | Sessions |
|---|---|---|---|
| **B** — bypassed | 3 draws per trap, `learn`, gate suspended | 3 probes per emitted draft | 6 + up to 18 |
| **C** — control | — | 3 per task, no skill installed | 6 |

Both traps. `learn` only. **n=3 per cell.** Up to 30 sessions, and 18 is a
ceiling rather than a cost — a draw that aborts anyway yields no probes.

Phase 2 follows Q1 exactly: trap A drafts probe `sf-author-response-text`,
trap B drafts probe `sf-author-fingerprint-preexisting`, three runs each.

**No fresh accepted-draft arm.** Q1's accepted drafts are archived under
`bench/distilled/` and their scores are in `results.jsonl`; re-running them
would cost 12 sessions to re-measure a ceiling. They are cited as historical
context with their batch named, and the binding comparison is B against C in
one batch.

### 3.3 What gets measured

Per phase-1 draw: `outcome`, and for an abort, **which contract step** the
session names. Per phase-2 run:

- **Delivery.** From the run's `injections` rows. A draft that never arrived
  makes a null mean "never delivered", which is the trap Q1's pre-probe
  prediction exists to prevent.
- **Score.** The task's hidden tests, as every other experiment here.
- **Graded probe score**, secondary. The 20-probe suite runs over the phase-2
  clones at zero session cost via `bench/regrade.py`. It is reported and not
  leaned on: 27 of 42 artifacts tied at a perfect probe score on 2026-09-10,
  every matched-treatment cell among them, so the treatment-side ceiling is
  untouched and this instrument may add nothing here.

**The judge is out of scope.** Its three criteria discriminate between tasks,
not between artifacts (r = -0.308), and 42 sessions bought that negative. It
is not re-run.

## 4. Viability

**The lever reaches the decision.** The refusals are model judgements made
inside the distilling session, not code paths in `save_skill.py`:
`rejections` is `[]` and `drafts_found` is 0 on all eight. Nothing was
submitted and rejected — the session declined to submit. So the prompt is the
only surface that can suspend the gate, and it is sufficient to.

**Phase 2 is a path already walked.** Q1 ran exactly this shape — four saved
drafts, three probes each, 12 rows in `results.jsonl` carrying
`skill_source: distilled`. E7 changes one clause in one prompt and reuses the
rest.

## 5. Pre-registration

Fixed before any data exists.

- Arms B and C run in the **same batch**. Phase 1 first, then phase 2 with
  arm C interleaved rather than run as a trailing block.
- **n=3 per cell.** Every conclusion says so.
- All draws run. No cell is dropped after its outcome is seen.
- Rows with `session_ok: false` are excluded and the excluded count reported,
  inheriting Q1's rule.
- **A phase-1 draw that aborts at a step other than the novelty gate is
  reported on its own line, with the step it names, and is not counted as a
  novelty refusal.** This is E6's crowd-out rule in a different costume, and
  it exists because two of the five target draws already name step 8.
- **A phase-2 run whose draft did not inject is reported separately and not
  pooled into its cell.**
- **Over-refusal is declared in advance as arm B scoring above arm C.** A
  result in the other direction — bypassed drafts scoring at or below control
  — vindicates the gate and is reported as-is, not reinterpreted.
- Binary `resolved` is the primary measure. The graded probe score is
  secondary and is reported beside it, never instead of it.
- If zero drafts emit under the lever, that is the headline and the phase-2
  comparison is reported as not run rather than as a null.

## 6. How to read the outcome

- **B near ceiling, C at its floor.** The gate is over-refusing: it declined
  skills that work. The library is being starved, `/consolidate` has a reason
  to exist, and the next question is what replaces a self-assessment the model
  is measurably bad at.
- **B ≈ C, both low.** The gate is right and Q1's most interesting loose end
  closes. Emission stops being the bottleneck to attack, and the 4-in-12 rate
  is a feature.
- **B spread wide.** The gate is neither right nor wrong but uninformative,
  and the useful output is whatever separates the drafts that worked from the
  ones that did not — which is a rubric, not a rate.
- **Few or no drafts emit, most aborting at step 8.** The blocking gate is the
  verification command, not novelty. E7 answers a question nobody asked and
  the one it was aimed at stays open; say so plainly rather than reporting a
  thin novelty result.

## 7. Threats

1. **Re-running is not recovering.** The five refused drafts were never
   written. E7 measures drafts the gate *would* refuse, drawn fresh from the
   same cells under the same traps — not the specific eight Q1 declined. The
   distiller is stochastic and a re-drawn session may reach a different
   lesson.
2. **n=3 per cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6. Only a large effect is detectable. A null is "no large effect",
   never "no effect".
3. **Suspending a gate changes more than the gate.** A session told to skip
   its own quality check may write a worse draft than one that passed the
   check honestly, in ways step 2 was not the only thing preventing. The
   measured direction is still interpretable — a draft that works despite
   this is stronger evidence, not weaker — but a null is confounded.
4. **The repo has moved since 2026-09-09.** Phase-1 sessions run against a
   working tree that now documents this entire experimental programme,
   including `bench/RESULTS.md` naming both traps. Q1's draws ran against a
   thinner repo. Clones are made at `fix_commit~1`, so the *code* matches, but
   the docs do not.
5. **One distiller, two traps, one repository.** Same limitation E6 carried.
6. **Same-author curation.** The operator wrote the tasks, the traps, the
   distilling skills and the gate now under test.
7. Bench sessions inherit the operator's full plugin set.
8. **Session count is the binding meter, not tokens.** Up to 30 sessions.
   Check the meter before the batch; `claude -p` exits 1 when the session
   limit is hit, and that exit code is the only thing separating a postponed
   experiment from a poisoned one.

## 8. Out of scope

The three trap-B anti-skill refusals, which are blocked by symptom shape as
well and need their own design. Changing the gate — E7 measures it, and what
replaces it if it is wrong is a separate decision. The judge. `/consolidate`,
which this unblocks or does not. E4, which the graded scorer moved and nobody
has run.
