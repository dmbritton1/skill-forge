# E9 — does a consolidated skill still work?

Design written 2026-09-11, after `/consolidate` shipped. Nothing here has been
run. The figures in §2 were measured; every other number is a slot.

## The question

`/consolidate` merges library skills that describe the same bug into one. The
spec that designed it put this question out of scope deliberately
(§7: "whether a merged skill performs like its members ... is an experiment,
not a feature, and needs this feature to exist first"). It exists now.

**Does the merged artifact still work, and can it even be delivered?**

E1 is the nearest prior evidence and it is not the same test: a *hand-authored*
umbrella covering two different traps scored 6/6, matching the specific skill.
E9 tests a *machine-merged* consolidation of several skills about one bug,
which is what the shipped command actually produces.

## 1. Why the second half of that question is the real one

E8 measured the delivery budget. `INJECT_BUDGET_TOKENS` is 1200 and
`retrieve.inject` costs an entry at `max(1, len(whole file) // 4)`.

Measured over the two mergeable clusters in `bench/distilled/`:

| cluster (key = `verification.command`) | members | member cost | naive concatenation |
|---|---|---|---|
| `python3 tests/test_detect.py` (trap A) | 3 | 798, 869, 817 | **2484** |
| `python3 tests/test_retrieve.py` (trap B) | 4 | 1192, 1096, 957, 1072 | **4317** |

Against a budget of **1200**.

So a merged skill has to compress three or four skills into roughly the size
of **one** of them, or it can never be injected. That reframes the experiment:
the interesting failure is not "the merge scores worse", it is "the merge is
undeliverable".

**Nothing stops that happening silently.** `save_skill.validate` enforces no
size limit — checked, there is none. An oversized merged skill saves cleanly,
indexes cleanly, reports as a healthy library entry, and simply never injects.
Whether the feature needs a size guard depends on what E9 finds, and adding
one is out of scope here (§7).

## 2. Viability

**Two clusters are mergeable, and they are the ones the shipped clustering
key finds.** A third group of two anti-skills declares no
`verification.command` at all, so `clusters()` leaves it unclustered by design
(consolidate spec §2.1); E9 does not touch it.

**Per-member scores already exist**, from E7 and Q1, and they shape what is
answerable:

| member | task | score |
|---|---|---|
| `A/learn-nogate/1`, `/2`, `/3` | `response_text` | 3/3 each |
| `B/learn-nogate/1` | `fingerprint` | 2/3 |
| `B/learn-nogate/2` | `fingerprint` | 3/3 |
| `B/learn-nogate/3` | `fingerprint` | 2/3 |
| `B/learn/1` | `fingerprint` | 3/3 |

**Every trap-A member is already at ceiling**, so that cluster cannot show a
merge outperforming its average — it can only hold or fall. Trap B has a
little spread (2/3 twice, 3/3 twice) and no more. So "does the merge match its
best member or its average" is **not answerable at this n**, and E9 does not
claim to answer it. The answerable question is whether merging **breaks** a
ceiling that every member holds.

## 3. Design

### 3.1 Phase 1 — produce the merged drafts (2 sessions, not bench sessions)

One fresh subagent per cluster. It reads the member `SKILL.md` files and
follows `commands/consolidate.md` Step 4 verbatim — the same instructions the
shipped command gives — and writes one merged draft.

**It is told nothing about any member's score**, and nothing about the budget
finding in §1 beyond what Step 4 already says. A merger that knew which member
scored best would be curating, not consolidating.

Drafts land in `bench/consolidated/<trap>/SKILL.md`.

### 3.2 Phase 2 — probe (18 sessions)

| Arm | Installed | Sessions |
|---|---|---|
| **R** — representative member | the named member below | 6 |
| **K** — consolidated | that cluster's merged draft | 6 |
| **C** — control | nothing | 6 |

Both tasks, **n=3 per cell**, all three arms **in one batch**, order R, K, C.

**Arm R's member is named here, not chosen once scores are visible.** For
`response_text` it is `A/learn-nogate/2`; for `fingerprint` it is `B/learn/1`.
Both are the arm-M members E8 used, both scored 3/3 there, so arm R is
expected to reproduce a known ceiling and §4 makes that a precondition.

### 3.3 What gets measured

- **Merged draft size**, in the same `len(file) // 4` units `retrieve` uses,
  recorded **before any probing**. This is a primary result, not a diagnostic.
- **Whether the merged skill injected**, from the run's `injections` rows.
- **Score**, the task's hidden tests.
- **Graded probe score**, secondary, expected to add nothing: it reproduced
  the binary verdict in 40 of 42 rows (2026-09-10), 24 of 24 (E7) and 18 of 18
  (E8).

## 4. Pre-registration

Fixed before any data exists.

- Arms R, K and C run in the **same batch**, in that order, per task.
- **n=3 per cell.** Every conclusion says so.
- All 18 sessions run. No cell is dropped after its score is seen.
- Rows with `session_ok: false` are excluded and the excluded count reported.
- **Arm R must reproduce its ceiling.** If it does not, that is the headline
  and the consolidation comparison is reported as uninterpretable rather than
  read against a lower baseline. Inherited from E6 §5.
- **Harm is declared in advance as arm K scoring below arm R.** A result in
  the other direction is reported as-is and not reinterpreted.
- **The size result stands on its own.** If a merged draft exceeds 1200
  tokens, that is recorded as a result before probing, and the probe still
  runs — whether an oversized skill injects is exactly what §1 says nobody has
  observed.
- **A run where the merged skill did not inject is reported separately and is
  not pooled into its cell.** A null from a skill that never arrived is a
  delivery finding, not a content finding. Inherited from Q1.
- The phase-1 merger is not re-run to get a smaller or better draft. The first
  draft each cluster produces is the artifact. Re-rolling until the merge
  looks good is what pre-registration exists to forbid.

## 5. How to read the outcome

- **K fits the budget and holds R's ceiling.** Consolidation works, and the
  ranking problem E8 found has a usable fix.
- **K fits but scores below R.** Compression costs effectiveness. The feature
  works mechanically and is not worth using at this compression ratio.
- **K does not fit, and does not inject.** Consolidation produces
  undeliverable skills. The feature needs a size guard before anyone uses it,
  and the right next change is to `save_skill` or the command file, not to the
  clustering.
- **K does not fit but injects anyway.** The §1 model of the budget is wrong;
  report that and stop, because everything E8 concluded rests on it.
- **Arm R below its ceiling.** Uninterpretable; say so.

## 6. Threats

1. **The merge is produced by a subagent following the command file, not by
   the shipped end-to-end flow.** `/consolidate` installs into a real library
   and saves through `save_skill.py`; E9 exercises only the drafting step.
   The plumbing has tests; the artifact is what is under measurement here.
   A draft that would have been rejected by `save_skill` is a gap this design
   does not catch.
2. **Every trap-A member is at ceiling**, so that cluster can only hold or
   fall (§2). Half the design has no headroom by construction.
3. **n=3 per cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6 (E5). Only a large effect is detectable.
4. **Two clusters, one repository, both traps written by the operator.**
5. **The members are near-duplicates of each other.** A real library's
   duplicates would be written months apart against different code.
6. **Session count is the binding meter.** 18 bench sessions plus 2 drafting
   subagents. Check the meter before the batch.

## 7. Out of scope

Adding a size guard to `save_skill` or to `commands/consolidate.md`, which is
the likely fix if §5's third case fires — E9 measures, it does not repair.
Whether a merged skill matches its best member or its average, which §2 shows
is not answerable at this n. The anti-skill cluster with no
`verification.command`. Running the shipped `/consolidate` end to end against a
real library, which is an integration test rather than an experiment.
