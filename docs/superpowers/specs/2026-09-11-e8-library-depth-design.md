# E8 — does retrieval survive a library with depth?

Design written 2026-09-11, after E7. Nothing here has been run. The figures in
§2 were measured; every other number is a slot.

## The question

**When the library holds ten skills instead of one, does the task still get
the skill it needs?**

E7 established that the distiller's novelty gate was refusing skills that
work: emission went 1/6 → 6/6 with the gate suspended, and those drafts scored
16/18 against a same-batch control of 0/6. The obvious product change is to
relax the gate.

Nothing licenses that yet. **Every experiment this project has run used a
library of one or two.** The gate's stated purpose is to stop junk accumulating,
and E6 measured one irrelevant skill alongside one relevant one as costing
nothing detectable — but one is not depth. Relaxing a filter without knowing
what the unfiltered library does to retrieval is the change this bench exists
to prevent.

## 1. The payload already exists, and it is realistic

E7 and Q1 between them left **ten distilled skills** in `bench/distilled/`,
each written by a different session:

| lesson | skills |
|---|---|
| trap A — JSON escaping breaks token matching | 6 |
| trap B — a capped scan cannot report absent | 4 |

They were not authored to be a test fixture. They are what the distiller
actually produces when it is allowed to emit, near-duplicates and all, which
is precisely the library a relaxed gate would build.

## 2. Viability — measured, and it decided the design

### 2.1 Only one skill can inject

`INJECT_BUDGET_TOKENS` is 1200 and `retrieve.inject` costs an entry at
`max(1, len(whole file) // 4)` — the **whole file**, frontmatter included, not
the body after it. Measured over the ten:

| | |
|---|---|
| cheapest skill | 759 tokens |
| dearest skill | 1192 tokens |
| budget | 1200 |
| skills that fit after the first | **0** |

**`MAX_SKILLS = 3` is a dead letter.** The budget binds at one. E6 fit two
because its hand-authored payloads cost ~550 each; the distiller writes skills
1.4× to 2.2× that size. This is a finding in its own right and it holds
whatever E8 returns.

### 2.2 Ranking, and a predicted dissociation

`retrieve.rank` over `name + description` for each probe prompt, against the
pool of all ten:

| task | rank 1 | rank 2 | rank 3 |
|---|---|---|---|
| `response_text` (trap A) | **B/learn-nogate/3** 9.70 | B/learn/1 9.57 | A/learn-nogate/2 8.40 |
| `fingerprint` (trap B) | **B/learn/1** 13.80 | B/learn-nogate/3 9.70 | A/learn-failure/2 6.93 |

Combine with §2.1 — only rank 1 injects:

| task | the one skill delivered | matching trap? |
|---|---|---|
| `response_text` | `truncation-reports-unknown` | **no** |
| `fingerprint` | `capped-scan-reports-unknown-not-absent` | yes |

**On `response_text` the top two ranks are both trap-B skills**, so the
matched skill does not merely lose its slot to a near-duplicate — it loses to
a skill about a different bug. This mirrors E6's finding that BM25 over
`name + description` ranked an unrelated `arrow` timezone skill above the
matched serialization skill, and it is the same defect at depth.

**The prediction, fixed here before any session:** arm L falls to control on
`response_text` and holds its ceiling on `fingerprint`. A dissociation between
two tasks is a far narrower target than a uniform effect, which is what makes
this worth 18 sessions.

## 3. Design

### 3.1 Arms

| Arm | Installed | Sessions |
|---|---|---|
| **M** — matched alone | the task's highest-ranked *relevant* draft | 6 |
| **L** — library | all ten drafts | 6 |
| **C** — control | nothing | 6 |

Both tasks, **n=3 per cell**, all three arms **in one batch**. 18 sessions.

**Arm M's skill is named here, not chosen later.** For `response_text` it is
`A/learn-nogate/2` (`flatten-structured-output-for-token-matching`, rank 3
overall, rank 1 among trap-A drafts). For `fingerprint` it is `B/learn/1`
(`capped-scan-reports-unknown-not-absent`, rank 1 overall). Both scored 3/3
in their own batches, so arm M is expected to reproduce a known ceiling; §5
makes that a precondition rather than a hope.

Arm M is the comparator, not control. Control is present because E5 showed
this harness's cross-batch spread exceeds its effects, so the floor has to be
measured in the same batch as the fall.

### 3.2 Harness change

`--plus-skill` installs one additional skill. E8 needs nine. It becomes
repeatable, and the clone path segment carries the count: `-plus` for exactly
one, preserving E6's archived segments byte for byte, and `-plus<N>` above
that. `extra_skills` on the result row already records the names.

### 3.3 What gets measured

- **Which skill injected**, from the run's `injections` rows. This is the
  primary mechanism reading, and §2.2 predicts exactly one per run.
- **Score**, the task's hidden tests.
- **Graded probe score**, secondary and expected to add nothing: it reproduced
  the binary verdict in 40 of 42 rows on 2026-09-10 and 24 of 24 on E7.

## 4. Pre-registration

Fixed before any data exists.

- Arms M, L and C run in the **same batch**, in that order, per task.
- **n=3 per cell.** Every conclusion says so.
- All 18 sessions run. No cell is dropped after its score is seen.
- Rows with `session_ok: false` are excluded and the excluded count reported.
- **Arm M must reproduce its ceiling.** If it does not, that is the headline
  and the depth comparison is reported as uninterpretable rather than read
  against a lower baseline than expected. Inherited from E6 §5.
- **Harm is declared in advance as arm L scoring below arm M.** A result in the
  other direction — depth helping — is reported as-is and not reinterpreted.
- **The §2.2 prediction is recorded as a prediction and scored as one.** If
  arm L holds up on `response_text` despite receiving a wrong-trap skill, that
  is reported as the prediction failing, not quietly reframed.
- A run whose injected skill is not the one §2.2 predicts is reported on its
  own line with the skill it actually received.

### 4.1 Amendment, 2026-09-11 — the first attempt was refused, and §2.1 is wrong

**The batch hit the session limit at 00:45:11.** 13 of 18 rows carry
`session_ok: false` and are excluded under §4. What survives is arm M
`response_text` 3/3 and arm L `response_text` 2 of 3 runs — **no control arm
and no `fingerprint` data at all**. E8 is postponed, not answered, and no
score from this attempt is reported as a result. Same rule, same reason, as
E6's first attempt.

**§2.1 is falsified, and by valid sessions.** It claimed only one skill can
ever inject. Observed: arm L delivered **two** skills on one run and **three**
on another.

The error was scope. §2.1 modelled `scripts/retrieve.py`, the
UserPromptSubmit path, and treated its 1200-token budget as the whole story.
`scripts/detect.py` carries **its own `INJECT_BUDGET_TOKENS = 1200`** for the
symptom-triggered PostToolUse path. The two budgets are independent and the
second one refills per event, so total delivery is not bounded by the first.

**§2.2's ranking prediction held exactly.** On `response_text` the single
prompt-path arrival was `capped-scan-reports-unknown-not-absent` — rank 1, and
a trap-B skill, as predicted. The matched skill did lose its prompt-path slot
to a skill about a different bug.

**What arrived anyway changes the question.** Both valid arm-L runs then
received a *relevant* trap-A skill at `trigger: symptom`, after the failure
surfaced, and both resolved:

| run | prompt path | symptom path |
|---|---|---|
| L1 | `capped-scan-reports-unknown-not-absent` (wrong trap) | `json-dumps-breaks-token-matching` |
| L2 | `capped-scan-reports-unknown-not-absent` (wrong trap) | `json-dumps-breaks-token-matching`, `json-dumps-fuses-tokens-across-newlines` |

This also corrects something E6 recorded: its §4 expected `prompt` for both
arms and called symptoms "dead in author mode". That was true of E6's
hand-authored payloads. These distilled skills carry literal symptom lists
drawn from real assertion text, and those symptoms fire.

**§5's predicted dissociation is withdrawn.** It rested on the matched skill
never arriving on `response_text`, and it does arrive. The question E8 now
asks is sharper and was not the one it was designed for:

> **Does symptom-triggered delivery rescue a task whose prompt-path ranking
> picked the wrong skill?**

Two valid runs say yes. Two runs is not an answer.

**Ruling for the re-run**, written before it exists: the 5 valid rows from
this attempt are **excluded** and the batch runs all 18 again. They are
excluded for the reason E7 §5.1 excluded its orphan — a row from an aborted
batch pooled into a later one is E5's defect, and nothing on the row records
which batch it came from. The mechanism readings above are kept, because they
are observations of what injected, not scores.

## 5. How to read the outcome

- **L falls on `response_text`, holds on `fingerprint`.** The predicted
  dissociation. Library depth breaks retrieval through the budget, the gate
  cannot simply be relaxed, and the fix is ranking and size — not a filter on
  what gets written.
- **L falls on both.** Depth hurts more broadly than the mechanism in §2
  explains; the reading is the same but the cause is not established.
- **L holds on both.** A wrong-trap skill did not stop the task. That is E4's
  underlying question answered from an unexpected direction, and it is the
  strongest case for relaxing the gate.
- **L holds on `response_text` and falls on `fingerprint`.** The §2 model is
  wrong. Report it and stop rather than reaching for an explanation.
- **Arm M below its ceiling.** Uninterpretable; say so.

## 6. Threats

1. **n=3 per cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6 (E5). Only a large effect is detectable. A null is "no large
   effect", never "no effect".
2. **"Irrelevant" here means the other trap, not unrelated.** Both traps live
   in this repo and both are about bounded/lossy text handling. A truly
   unrelated library might rank differently, and probably worse.
3. **Ten is still small.** It is an order up from one, not a real library.
4. **The ten are near-duplicates in two clusters.** That is realistic for this
   distiller and unrepresentative of a library grown across many projects.
5. **Arm L confounds two mechanisms**: worse ranking and a tighter budget.
   §2.2 predicts which one dominates, but a single arm cannot separate them.
   Separating them needs a budget lever, which this design does not add.
6. **Same-author curation.** The operator wrote the tasks, the traps and the
   distilling skills; the ten payloads were written by bench sessions.
7. Bench sessions inherit the operator's full plugin set.
8. **Session count is the binding meter, not tokens.** 18 sessions. Check the
   meter before the batch; `claude -p` exits 1 when the limit is hit.

## 7. Out of scope

Changing `INJECT_BUDGET_TOKENS`, `MAX_SKILLS` or the ranking function — E8
measures what the shipped ones do at depth. Changing the novelty gate, which
E7 measured and this design does not act on. `/consolidate`, which is the
candidate fix if depth does hurt. The hot tier, whose budget and eviction
remain unevidenced for the same reason they always have been.
