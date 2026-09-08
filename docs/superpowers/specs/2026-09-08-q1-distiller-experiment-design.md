# Q1 — does the distiller work end to end?

Design for the experiment answering the benchmark brief's question 1. Written
2026-09-08. Nothing here has been run; every number in the Comparators section
is pre-existing data, and every number elsewhere is a slot waiting to be filled.

## The question

`docs/2026-08-29-benchmark-investigation-brief.md` §1:

> The pilot injected *hand-authored* skills written by the person who found the
> bug. That measures a ceiling: the best possible skill, matched perfectly. It
> does not measure the distiller. The full claim is session → distilled skill →
> later session improved, and the distiller's output is the untested link.

Every result in `bench/RESULTS.md` uses a hand-authored skill. The register
calls this the largest open question in the project. This design closes the
loop: a session distills its own skill, and a later session is measured with it.

## What is being claimed, and what is not

**Primary claim under test.** A skill produced by the distiller, from a real
session, delivered to a later session, beats no skill at all. Control is 0/6 on
these two author tasks — a floor with real distance to travel, which is the
only reason n=3 can resolve anything here.

**Secondary, directional only.** Whether the distilled skill reaches the
hand-authored ceiling. The ceiling has been measured twice, at 5/6 and 6/6, and
E5 established that two measurements of one arm span 6/6 to 4/6. A difference
smaller than that spread is not claimable and will not be claimed.

**Not claimed.** Anything about transfer (= brief Q2), about harm (= E4), or
about which delivery path is better (= E5, answered: it does not decide the
effect).

---

## 1. Cells

The task table already contains the chain. For each trap, the repair task and
the author task are the *same bug*:

| | Trap A — `22ddf37`, json.dumps escaping | Trap B — `ab4acfe`, truncation |
|---|---|---|
| Phase 1 source (repair mode) | `sf-escaping-breaks-symptom-match` | `sf-truncation-reports-absent` |
| Phase 2 probe (author mode) | `sf-author-response-text` | `sf-author-fingerprint-preexisting` |
| Hand-authored comparator | `serialization-corrupts-matching` | `lossy-transform-false-negative` |

The repair tasks are ideal phase-1 sources for the same reason they are useless
to E4: the red assertion names the condition, so control resolves them 2/2. A
distiller needs a session that *succeeded* and has a real procedure to distill.

### Session budget

| Phase | Breakdown | Sessions |
|---|---|---|
| 1 — distillation | 2 distillers × 2 traps × 3 draws | 12 |
| 2 — probe | 2 distillers × 2 traps × 3 drafts × 3 runs | 36 |
| | | **48** |

At the 48–98s per session observed on 2026-09-08, roughly 50–80 minutes, plus
scoring. Phase 2 shrinks if phase 1 emits fewer than 3 saved drafts in a cell
(see §5); it never grows.

### Both distillers

`/learn-failure` (`distilling-failures`, emits `kind: antiskill`) and `/learn`
(`distilling-skills`, emits `kind: skill`) are separate arms.

E1 spent twelve sessions establishing that **a skill and an anti-skill are never
a clean A/B** — `kind:` carries delivery tier, verification eligibility, and run
independence with it. All four skills in `bench/skills/` are `kind: antiskill`.
Therefore:

- The `/learn-failure` arm has a matched hand-authored comparator and is judged
  against both control and that ceiling.
- The `/learn` arm has **no** valid ceiling comparator and is judged against
  control alone. Comparing its `kind: skill` output to a hand-authored
  anti-skill would reproduce E1's invalid batch exactly.

`/learn-failure` is also the semantically correct command for these two bugs:
both are debugging traps, and both hand-authored comparators are anti-skills
distilled from exactly these traps.

---

## 2. Comparators — existing data, exact rows

No comparator sessions are run. These cells already exist and are named
precisely, because the register's standing lesson is that data described from
memory gets described wrong.

| Comparator | Source | response_text | fingerprint | Combined |
|---|---|---|---|---|
| Control — no skill | `results-round1.jsonl` (rt) and `results.jsonl` (fp), both `ts` 2026-08-11 | 0/3 | 0/3 | **0/6** |
| Hand-authored, matched | same files, same date | 3/3 | 2/3 | **5/6** |
| Hand-authored, re-measured | `results.jsonl`, `ts` 2026-09-05 | 3/3 | 3/3 | **6/6** |

`results-round1.jsonl`'s `sf-author-fingerprint-preexisting` rows are the
**superseded** file-cap batch (0/3 in every arm, which is the signature of the
broken test, not a hard task). The live fingerprint pilot cells are in
`results.jsonl`. Do not aggregate the two files blindly; the combined figure is
wrong if you do.

The ceiling is itself a range, 5/6 to 6/6. That is the same spread problem one
level up and is why the secondary comparison is directional only.

---

## 3. The funnel — the primary output

Q1 is reported as a funnel, not a score. The distiller can fail at five
separable stages, and collapsing them into one number discards most of what the
experiment observes.

```
3 draws  →  draft written  →  save_skill accepted  →  injected downstream  →  resolved
```

Reported per distiller × trap:

| Stage | Definition | Failure means |
|---|---|---|
| Draws | 3 per cell, fixed | — |
| Draft written | the session produced a candidate SKILL.md | the novelty self-gate aborted, or the session never reached the distiller |
| `save_skill` accepted | exit 0 from the enforced write path | the distiller emits drafts its own validator refuses |
| Injected downstream | exactly one `injection` row for the skill in the probe run's ledger | the distiller wrote unusable triggers — the skill never arrived |
| Resolved | the probe task's hidden tests pass | arrived and did not help |

The fourth stage is load-bearing. The brief is explicit that a null which never
arrived is not a null, and it is the stage most likely to fail silently: a
saved skill whose `description` triggers or `symptoms` never match reads as "no
effect" while being a delivery failure.

---

## 4. Mechanics

### Phase 1 — `bench/distill.py` (new)

Per (trap, distiller, draw):

1. `prepare()` the repair task exactly as `run.py` does — clone at
   `fix_commit~1`, overlay the fix's tests, so the trap is live.
2. Export `SKILLFORGE_LEDGER` to a per-draw database, deleted first, same
   discipline as `run.py::one()`. Phase-1 sessions write `save` and `draft`
   rows; none of them may reach the real library.
3. Run one `claude -p` session whose prompt is **fixed and identical across
   every draw and both traps**, except for the repair task's own prompt text
   spliced in. It instructs the session to fix the bug, verify the tests pass,
   and then distill the session through the named distiller skill.

   *Open mechanism, first thing the implementation must confirm:* whether a
   literal `/skillforge:learn-failure` expands inside a `-p` prompt. If it does
   not, the prompt names the skill (`skillforge:distilling-failures`) for
   invocation through the Skill tool, which reaches the same contract. Whichever
   works, it is fixed across all 12 phase-1 sessions — the prompt is an
   experimental variable and must not drift between cells.
4. Extract whatever landed in the clone's store:
   - `/learn-failure` → `<clone>/.claude/skillforge/antiskills/*/SKILL.md`
   - `/learn` → `<clone>/.claude/skillforge/skills/*/SKILL.md`
   Extract the **store** copy, not a materialized native copy: `sync.py`
   appends a modified `MARKER_NOTE` to what it materializes, and that text is a
   delivery artifact rather than part of the draft.
5. Write to `bench/distilled/<trap>/<distiller>/<draw>/`:
   - `SKILL.md` — the draft verbatim, when one saved
   - `meta.json` — phase-1 outcome, `save_skill.py` stdout/stderr verbatim, the
     ledger's `save` and `draft` rows, the skill name, and the session tail

`bench/distilled/` is **committed**. Un-indexed data is what produced the two
false claims the register caught.

### The global-scope leak, and how phase 1 contains it

`save_skill.py::store_dir` resolves a `--scope global` save to
`Path.home()/.claude/skillforge/`, and the distillation contract has the *model*
choose the scope — step 5 reads "mentions repo-specific paths/conventions →
`project`; otherwise `global`". A phase-1 session that judges its trap general
would therefore write into the operator's **real library**. Phase 2 is safe
(`install_skill` forces `--scope project`); phase 1 is not, because letting the
session drive the full save path is the entire point of an end-to-end test.

Containment, chosen over the alternatives because it keeps the pipeline whole:

- Snapshot the global store, `index.json`, and `trust.json` before the batch.
- After **each** phase-1 session, diff the global store. A new entry means the
  session chose global scope.
- That is recorded as a phase-1 outcome — the scope decision is Q1 data, and
  "the distiller called a project-specific trap general" is a real finding — and
  the draft is copied into the archive exactly as a project-scoped one would be.
- The entry is then removed with `library.py delete <name>`, which unwinds the
  store, the native tier, and the trust registry and resyncs. The next session
  starts from the snapshot state.
- The batch ends with a final diff asserting the global store matches the
  opening snapshot. A mismatch invalidates the batch rather than being tidied
  away.

Rejected alternatives, and why: sandboxing `HOME` for phase 1 would isolate the
store completely but the `claude` CLI reads `HOME` for its own credentials, so
it risks breaking authentication; having the harness call `save_skill.py` itself
would be structurally safe but removes the model's invocation of the save path,
which is one of the five funnel stages Q1 exists to measure.

### Phase 2 — one flag on `bench/run.py`

`--skill-from <path>` replaces the `ROOT / "skills" / (task["skill"] + ".md")`
lookup inside `install_skill()`. Nothing else in `one()` changes: the per-run
ledger, the arm handling, and the scoring are untouched.

### Collision discipline

Both existing arms pass `--arm treatment` and silently overwrote each other's
clones and ledgers until `-hot` was added to the path. The probe segment is
therefore **derived from `--skill-from`**, not passed as a separate flag, so it
cannot be forgotten:

    sf-author-response-text-treatment-d-learnfail-2-3
                                       │         │ └── run index
                                       │         └──── draw
                                       └────────────── distiller

Phase-1 clones use `<repair-task>-distill-<distiller>-<draw>`, which collides
with nothing.

### Result rows

New keys on every phase-2 row, so batches stop being separable only by
timestamp — a limitation the register names explicitly:

| Key | Values |
|---|---|
| `skill_source` | `authored` \| `distilled` |
| `distiller` | `learn` \| `learn-failure` \| `null` |
| `draw` | `1` \| `2` \| `3` \| `null` |
| `skill_path` | the file `install_skill` actually saved |

---

## 5. Phase-1 outcomes

Three outcomes. All are recorded; none is a harness error.

1. **Aborted at the novelty self-gate.** The distillation contract states that
   aborting is a success outcome — "the knowledge is model-obvious" is the gate
   working. Recorded as an abort with its stated reason. No draft, no probes
   for that draw.
2. **Draft written, `save_skill.py` rejected it.** The `REJECTED` /
   `SECRET BLOCKED` reason is captured verbatim. This is the highest-information
   failure available: the distiller's own enforced write path refusing the
   distiller's own output.
3. **Saved.** Proceeds to phase 2.

A cell with fewer than 3 saved drafts probes only what exists, and reports its n
honestly — the emission rate is a first-class Q1 number, not an inconvenience.
**A cell with zero saved drafts is a complete Q1 answer for that distiller and
trap, and costs zero probe sessions.**

---

## 6. Retrospective judging

Phase 1 self-approves so the run stays automated and unsteered. The human gate
is recovered afterward, on the archived drafts, without anyone having steered a
live session.

Per saved draft:

- **Critique verdict** from `scripts/validate.py`, run explicitly against the
  archived draft. `save_skill.py` spawns critique detached on a create, so a
  verdict may not exist when the phase-1 session ends; the retrospective pass
  does not rely on it having landed. Precedent and worked example:
  `bench/critique-calibration/`.
- **Does `verification.command` fail when the skill is skipped?** Run it at
  `fix_commit~1`, a tree where the procedure demonstrably was not applied. Exit
  0 there means it is not a verification. The distillation contract states this
  bar and states that every skill in the library has failed it at least once;
  this is the first time it is checked by machine.
- **Do `fingerprints` match the reference fix's diff?** Matching runs against
  added lines, so a fingerprint that appears nowhere in the real fix is
  invisible to outcome tracking no matter how well the skill was applied.
- **Does `description` carry both trigger directions?** `save_skill.py` enforces
  this, so the expected rate is 100%; anything less is a bug in the enforcement,
  not in the distiller.

These are reported alongside the funnel, not merged into it. A draft can be
accepted, injected, resolve the task, and still carry a verification command
that proves nothing.

---

## 7. Threats to validity

Stated before the run, not discovered in the write-up.

1. **Session variance and distiller variance are confounded.** Three
   independent draws vary both the source session and the distillation. The fix
   would be replaying one captured transcript into N distiller sessions; there
   is no replay path, so it is not built. A cell that varies widely cannot be
   attributed to either cause.
2. **The repair source hands over the answer.** The red assertion names the
   condition, which is why control resolves these 2/2. A session may therefore
   distill "read the failing test" rather than the trap. If that is what comes
   out, that is the finding, and the archived drafts will show it plainly.
3. **Same-author curation is only half fixed.** The distiller now writes the
   skills, which is the half the brief asked for. The operator still wrote the
   tasks and chose the traps.
4. **Self-referential tasks.** Both traps are in SkillForge's own codebase,
   which narrows what any result generalizes to.
5. **The two arms use different delivery paths.** `/learn-failure`'s anti-skill
   arrives by symptom injection; `/learn`'s `kind: skill` arrives by warm
   retrieval. E5 found that the delivery path does not decide the effect, which
   is what makes this tolerable — it is not nothing.
6. **n=3 per probe cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6.
7. **`index.json` is user-global and last-writer-wins.** Forty-eight sessions
   rewrite it. Nothing else may run on the machine during the batch — including
   a one-off `claude -p` in `/tmp`.
8. **Phase 1 can write to the real library.** The distiller chooses its own
   scope, and a `global` choice lands in the operator's store. Contained by
   snapshot-diff-revert per session (§4), with a closing assertion that the
   store is unchanged — but the containment is reactive, and a batch that trips
   it is invalidated rather than repaired.
9. **Bench sessions inherit the operator's full plugin set** (ponytail,
   superpowers). Constant across arms, so contrasts hold; absolute numbers are
   model-plus-plugins.

---

## 8. Pre-registration

Fixed before any data exists, because E1's first batch was invalid and the
register caught two confidently-stated false claims:

- **All** saved drafts are probed, 3 runs each. No draft is selected, skipped,
  or re-rolled after its content is seen.
- No cell is dropped after its score is seen.
- The funnel stages in §3 are the reported output. The headline is the funnel;
  the score is one stage of it.
- The secondary comparison against the hand-authored ceiling is directional and
  will be labelled as such regardless of which direction it points.
- A phase-1 abort or rejection is a result. It is reported, not re-run.

## 9. How to read the outcome

- **Drafts save and probes beat control.** The pipeline closes end to end. Q1 is
  answered affirmatively and the distiller stops being the untested link.
- **Drafts save, probes sit at control.** The distiller emits valid artifacts
  that do not help. The funnel says at which stage — never injected (bad
  triggers, a retrieval problem) versus injected and ignored (a content
  problem). These have different fixes.
- **Drafts do not save.** The pipeline does not close, and the funnel names the
  gate that stopped it. Cheapest possible answer; costs no probe sessions.
- **The two distillers diverge.** Expected to be informative given that `kind:`
  carries delivery tier and verification eligibility, but at n=3 per cell,
  report the split and do not rank.

## 10. Out of scope

Transfer (brief Q2), harm from irrelevant injection (E4, blocked on a task that
does not exist), token cost per unit of benefit (brief Q4), and whether the
`trusted` gate predicts anything (brief Q5). Nothing here requires a new trap, a
new task, or a new repository.
