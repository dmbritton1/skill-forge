# Q1 — does the distiller work end to end?

Design for the experiment answering the benchmark brief's question 1. Written
2026-09-08; revised the same day against an adversarial review that checked
every claim in the first draft against the code. Nothing here has been run.
Every number in §2 is pre-existing data; every number elsewhere is a slot.

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
session, delivered to a later session, beats no skill at all — measured against
a control arm run **in this batch, on the pinned model**, not against the
2026-08-11 floor (see §2, and F1 in the review log).

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

The repair tasks are plausible phase-1 sources for the same reason they are
useless to E4: the red assertion names the condition. Their control rate is 2/2
each — but from 2026-08-10, at an unrecorded model, n=2. That is a reason to
expect success, not a licence to assume it, which is why §4 scores the repair.

### Session budget

| Phase | Breakdown | Sessions |
|---|---|---|
| 1 — distillation | 2 distillers × 2 traps × 3 draws | 12 |
| 2 — probe | 2 distillers × 2 traps × 3 drafts × 3 runs | 36 |
| 2 — control | 2 tasks × 3 runs, this batch, pinned model | 6 |
| 2 — transfer (brief Q2) | 2 transfer tasks × 3 runs, hand-authored crossed skill | 6 |
| | | **60** |

Phase 2 shrinks if phase 1 emits fewer probeable drafts (§5); it never grows.

### Why the transfer arm rides this batch

The transfer arm is brief Q2, not Q1, and it is folded in for one reason: it
needs a floor measured under the same configuration, and this batch is the only
one that has one.

`sf-author-response-text-transfer` and `sf-author-fingerprint-preexisting-transfer`
already exist in `tasks.json`, already carry the crossed hand-authored skill,
and already ran 0/3 each — on 2026-08-11, **with no `model` key**, the same F1
defect that forced Q1 to run its own control. Re-measured in a separate batch
later, transfer would need its own control cell as well (+6 treatment **and** +6
control = 12), because comparing it against this batch's floor would be a
cross-batch comparison — precisely what E5 established is untrustworthy here:
two measurements of *one arm* spanned 6/6 to 4/6 with nothing changed but the
batch. Folded in, it costs 6.

It changes nothing else. `run.py` needs no flag — the transfer tasks name their
own skill — the clone segments cannot collide (`dest` derives from the task id),
and the rows land tagged `skill_source: authored`, `distiller: null`,
distinguishable from every Q1 row by task id alone.

**Runtime is stated for phase 2 only.** Across all 78 timed rows in the three
results files: min 27.5s, median 72.3s, mean 74.3s, p90 100.1s, max 245.6s. The
48 phase-2 sessions are author-mode sessions of exactly that shape, so ~60
minutes is a sound estimate for them. It is **not** sound for phase 1: those
sessions do a repair *and* a full distillation (transcript review, novelty gate,
duplicate check, draft, secret scan, save), and nothing in the record measures
that workload. `secs` also excludes `git clone` and `setup_cmd`, which run
outside `run_session`. **Time one pilot draw, then state phase 1's cost.** Do
not extrapolate.

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

---

## 2. Comparators

### The floor is measured in this batch

**Every `control` row this project has ever recorded carries no `model` key.**
Verified across all three results files: `results.jsonl` (3 control rows,
2026-08-11), `results-round1.jsonl` (6, 2026-08-11), `results-leaky-stub.jsonl`
(8, 2026-08-10/11). Every row carrying `model: claude-opus-5` is a *treatment*
row. `run.py:46-49` pins the model precisely because "a cross-date comparison is
only sound if the model is known, and the 2026-08-11 pilot did not record one."

So the historical 0/6 floor cannot carry the primary claim. The 2026-09-05
re-measure re-ran the treatment arm and did not re-run control, so the gap has
never been observed under one configuration. This batch runs its own control:

    python3 bench/run.py --arm control --runs 3 --task sf-author-response-text
    python3 bench/run.py --arm control --runs 3 --task sf-author-fingerprint-preexisting

The fresh cell is **the floor**. The 2026-08-11 figure is corroboration, and is
reported as such — not the other way round.

### Existing cells, exact rows

Named precisely because the register's standing lesson is that data described
from memory gets described wrong.

| Comparator | Source | response_text | fingerprint | Combined |
|---|---|---|---|---|
| Control — no skill (corroborating) | `results-round1.jsonl` (rt) and `results.jsonl` (fp), both `ts` 2026-08-11, **model unrecorded** | 0/3 | 0/3 | **0/6** |
| Hand-authored, matched | same files, same date, **model unrecorded** | 3/3 | 2/3 | **5/6** |
| Hand-authored, re-measured | `results.jsonl`, `ts` 2026-09-05, `claude-opus-5` | 3/3 | 3/3 | **6/6** |

`results-round1.jsonl`'s `sf-author-fingerprint-preexisting` rows are the
**superseded** file-cap batch (0/3 in every arm, the signature of the broken
test, not a hard task). The live fingerprint pilot cells are in `results.jsonl`.
Do not aggregate the two files blindly; the combined figure is wrong if you do.

The ceiling is itself a range, 5/6 to 6/6. Same spread problem one level up, and
why the secondary comparison is directional only.

---

## 3. The funnel — the primary output

Q1 is reported as a funnel, not a score. The distiller can fail at six separable
stages, and collapsing them into one number discards most of what the experiment
observes.

```
3 draws → repair resolved → draft written → save_skill accepted → delivered downstream → task resolved
```

Reported per distiller × trap:

| Stage | Definition | Failure means |
|---|---|---|
| Draws | 3 per cell, fixed | — |
| Repair resolved | the phase-1 session's own FAIL_TO_PASS tests pass | the session distilled from a bug it never fixed |
| Draft written | a candidate SKILL.md was produced | the novelty self-gate aborted, or the session timed out |
| `save_skill` accepted | exit 0 from the enforced write path | the distiller emits drafts its own validator refuses |
| Delivered downstream | an `injection` row for the skill in the probe run's ledger | the description never matched the probe prompt |
| Resolved | the probe task's hidden tests pass | arrived and did not help |

### Stage 5 is a description test, not a symptom test

This is the correction that most changes how the result must be read.

`distilling-failures` step 4 mandates that `symptoms:` entries be "the literal
error text or signature someone would see (exception name, error message
fragment)"; its template says `<literal error signature 1>`. `detect.py` matches
those against `tool_response` and `error` text. But **author mode never places
the grading tests in the tree during the session** — `run.py::prepare` skips
them and `apply_hidden_tests` runs only after the session ends — so the trap's
real error signature never appears in any tool output during a probe. A
distilled anti-skill that obeys its own contract is therefore structurally
incapable of firing on symptoms in phase 2.

Delivery for both arms falls entirely to `retrieve.run_hook`: BM25 over
`name + description` against the **prompt**, gated on `score > 0` and
`matched >= MIN_MATCHED_TERMS` (=2) at `retrieve.py:322`, and on
`trust.check_text(name, body) == "trusted"` at `retrieve.py:334`. The trust gate
passes for a freshly distilled skill — `save_skill.py:390` records it with
`origin="self"` — but it is a silent-zero path and the plan asserts it rather
than assuming it.

Two consequences, both binding:

1. Record which trigger actually fired. The ledger row already carries
   `trigger: prompt` versus `trigger: symptom`; report the split rather than
   collapsing it into "injected".
2. **Pre-probe dry run, zero session cost.** For each saved draft, rank the
   probe task's prompt against the draft's description with `retrieve.rank`, and
   record the score and `matched` count in `meta.json`. A draft scoring below
   `MIN_MATCHED_TERMS` is a *predicted* stage-5 failure, known before a single
   probe session is spent, which makes the eventual zero attributable instead of
   ambiguous.

A stage-5 zero must not be written up as "the distiller wrote unusable
triggers." The honest reading is that the contract and the probe disagree about
what a symptom is. See §7.9 for the asymmetry this creates against the
hand-authored comparators.

---

## 4. Mechanics

### Phase 1 — `bench/distill.py` (new)

Per (trap, distiller, draw):

1. **Precondition, checked per draw and not merely per batch:**
   `~/.claude/skillforge/skills/` and `~/.claude/skillforge/antiskills/` are
   empty. `distilling-failures` step 3's duplicate check runs
   `ls ~/.claude/skillforge/antiskills/`, so a leaked draft from an earlier draw
   would make the next session "propose updating it" instead of drafting fresh —
   silently converting an independent draw into a dependent one. One `os.listdir`;
   it makes a containment failure loud instead of contaminating.
2. `prepare()` the repair task exactly as `run.py` does — clone at
   `fix_commit~1`, overlay the fix's tests, so the trap is live.
3. Export `SKILLFORGE_LEDGER` to a per-draw database, deleted first, same
   discipline as `run.py::one()`.
4. Run one `claude -p` session whose prompt is **fixed and identical across
   every draw and both traps**, except for the repair task's own prompt text
   spliced in. It instructs the session to fix the bug, verify the tests pass,
   and then distill the session through the named distiller skill.

   The prompt names the skill (`skillforge:distilling-failures` /
   `skillforge:distilling-skills`) for invocation through the Skill tool — this
   is what ships. *Open mechanism, first thing the implementation must
   confirm:* whether that form actually reaches the distillation contract, not
   which of two forms to pick. If it does not, a literal `/skillforge:learn-failure`
   is the fallback. Whichever works is fixed across all 12 phase-1 sessions —
   the prompt is an experimental variable and must not drift between cells.

   Phase 1 sets its own timeout explicitly. `SESSION_TIMEOUT_S = 900` is sized
   for author-mode sessions and may be tight for repair-plus-distillation.
5. **Score the repair** with `run.py::score(task, dest)`, before extraction.
   Repair mode already has the tests in the tree, so this is one call and no
   `apply_hidden_tests`. Record `repair_resolved`.
6. Extract whatever landed in the clone's store:
   - `/learn-failure` → `<clone>/.claude/skillforge/antiskills/*/SKILL.md`
   - `/learn` → `<clone>/.claude/skillforge/skills/*/SKILL.md`

   Extract the **store** copy, not a materialized native copy:
   `save_skill.py:388` writes the draft verbatim, while `sync.py:413` appends a
   rewritten `MARKER_NOTE` to the hot copy only. That text is a delivery
   artifact, not part of the draft.
7. Write to `bench/distilled/<trap>/<distiller>/<draw>/`:
   - `SKILL.md` — the draft verbatim, when one saved
   - `meta.json` — `repair_resolved`, the phase-1 outcome (§5), `save_skill.py`
     stdout/stderr verbatim, the ledger's `save` and `draft` rows, the skill
     name, the chosen scope, the pre-probe BM25 score and `matched` count (§3),
     the session tail, and whether the session hit its timeout

`bench/distilled/` is **committed**. Un-indexed data is what produced the two
false claims the register caught.

### Suppressing the inline critique

`save_skill.py:420` calls `_spawn_validation` on **every create** —
`subprocess.Popen(..., start_new_session=True)`, detached and never waited on —
and `validate.py critique` is itself a real `claude -p` child. Left alone, this
batch spawns up to 54 extra detached sessions — one per save, so 12 in
phase 1 and 42 across phase 2's treatment and transfer installs — which
violates §7.7's own rule
that nothing else may run during the batch, adds an unbudgeted token cost, and
in phase 1 races the containment `library.py delete` for the same name.

**Add a `SKILLFORGE_NO_CRITIQUE=1` env-var seam to `save_skill.py`**, not a
flag: the phase-1 session invokes `save_skill.py` itself — that is the point
of phase 1 — so nothing in the harness is positioned to pass it a command-line
flag, while an exported environment variable reaches the child regardless of
who invokes it. Have §6's retrospective pass run `validate.py` explicitly. §6
already wants the verdict retrospectively, so the inline spawn buys this
experiment nothing. Phase 2 exports the same variable for its 42 treatment
installs, for the identical reason.

### The global-scope leak, and how phase 1 contains it

`save_skill.py::store_dir` resolves a `--scope global` save to
`Path.home()/.claude/skillforge/`, and the distillation contract has the *model*
choose the scope — step 5 reads "mentions repo-specific paths/conventions →
`project`; otherwise `global`". A phase-1 session that judges its trap general
writes into the operator's **real library**.

Phase 2 cannot write to the global *store* (`install_skill` forces
`--scope project`), but it is **not** otherwise isolated: `trust.py:24` resolves
`trust.json` to `Path.home()` unconditionally and `save_skill.py:390` calls
`trust.record` on every save, so all 48 saves write into the operator's real
trust registry, and `index.json` is user-global too.

Containment, chosen over the alternatives because it keeps the pipeline whole:

- **At batch open**, snapshot: the directory contents of
  `~/.claude/skillforge/{skills,antiskills}/`, the *set* of `index.json` entries
  with `scope == "global"`, the set of project-scoped entries rooted at the real
  repo, and `trust.json`'s key set.
- **After each phase-1 session**, diff the global store. A new entry means the
  session chose global scope. That is recorded as a phase-1 outcome — the scope
  decision is Q1 data, and "the distiller called a project-specific trap
  general" is a real finding — and the draft is archived exactly as a
  project-scoped one would be.
- Remove the entry with `library.py delete <name>`. Note what this does *not*
  do: `_resync` calls `sync.sync(project_root=None)`, whose `bases` is
  `[Path.home()]` alone (`sync.py:330`), so the rebuild drops the operator's
  project-scoped entries out of `index.json`. That state is derived and
  self-healing — the next sync in the real project restores it, as observed on
  2026-09-08 when a bench batch left `index.json` holding only the bench skill
  while the materialized copies survived untouched — but the assertion below
  must not be fooled by it.
- **At batch close**, assert: (a) the store directories match the opening
  snapshot, (b) the *set* of `scope == "global"` index entries matches — never a
  byte comparison of `index.json`, and ignore `compiled_ts`, (c) `trust.json`'s
  key set matches after pruning the batch's names, and (d) the project entries
  rooted at the real repo are present; if not, restore with one
  `sync.sync(project_root=<real repo>)`.
- A mismatch that survives the restore invalidates the batch rather than being
  tidied away.

Rejected alternatives: sandboxing `HOME` for phase 1 would isolate the store
completely, but the `claude` CLI reads `HOME` for its own credentials, so it
risks breaking authentication; having the harness call `save_skill.py` itself
would be structurally safe but removes the model's invocation of the save path,
which is one of the funnel stages Q1 exists to measure.

### Phase 2 — one flag on `bench/run.py`

`--skill-from <path>` replaces the `ROOT / "skills" / (task["skill"] + ".md")`
lookup inside `install_skill()`. Nothing else in `one()` changes.

After `install_skill`, read the index entry and **assert `tier == "warm"`**,
recording it on the result row. `retrieve.eligible()` requires `tier == "warm"`
(`retrieve.py:172`), so a skill that landed hot would produce no `injection` row
at all and stage 5 would read the strongest delivery path as a delivery failure.
A fresh save is warm today (`_warm_reason`: "unproven — earns hot once a real
session verifies it"), so this holds — and it is exactly the class of failure
`b35f756` already cost a batch. Two lines.

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
| `tier_at_install` | `warm` expected; asserted, not assumed |

**Backfill the historical rows.** Every pre-existing row lacks these keys, so a
filter on `skill_source == "authored"` silently excludes the comparators this
design depends on. Backfill `results.jsonl` and `results-round1.jsonl` once and
commit it — `arm == "control"` → `skill_source: null`, otherwise `authored` —
rather than relying on a documented read rule. §4's own argument applies:
un-indexed data is what produced the two false claims the register caught. The
read rule (missing key → `authored`; control → `null`) is stated here as a
fallback for `results-leaky-stub.jsonl`, which is not backfilled.

---

## 5. Phase-1 outcomes

Five outcomes. All are recorded; none is a harness error.

1. **Repair unresolved.** The session did not fix the bug. The draft is
   archived and reported as its own funnel row, and is **not probed**. A
   distiller that writes a confident skill about a mechanism the session never
   found is a finding worth naming loudly, and it must not launder itself into
   the probe numbers by way of a clean `save_skill` exit 0.
2. **Timed out.** Distinguished from an abort in `meta.json`. A timeout landing
   mid-distillation otherwise reads as "no draft written", which is
   indistinguishable from the novelty gate firing.
3. **Aborted at the novelty self-gate.** The distillation contract states that
   aborting is a success outcome — "the knowledge is model-obvious" is the gate
   working. Recorded with its stated reason. No draft, no probes.
4. **Draft written, `save_skill.py` rejected it.** The `REJECTED` /
   `SECRET BLOCKED` reason is captured verbatim. The highest-information failure
   available: the distiller's own enforced write path refusing its own output.
5. **Saved, repair resolved.** Proceeds to phase 2.

A cell with fewer than 3 probeable drafts probes only what qualifies and reports
its n honestly — the emission rate is a first-class Q1 number, not an
inconvenience. **A cell with zero probeable drafts is a complete Q1 answer for
that distiller and trap, and costs zero probe sessions.**

---

## 6. Retrospective judging

Phase 1 self-approves so the run stays automated and unsteered. The human gate
is recovered afterward, on the archived drafts, without anyone having steered a
live session.

Per saved draft:

- **Critique verdict** from `scripts/validate.py`, run explicitly against the
  archived draft. With the inline spawn suppressed (§4), this is the only place
  critique runs, which is where the design wanted it anyway.
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
- **Symptom shape.** Are the `symptoms:` entries error signatures, as the
  contract demands, or narration, as both hand-authored comparators are? This is
  the measurement behind §7.9, and it costs nothing to record.

Reported alongside the funnel, not merged into it. A draft can be accepted,
delivered, resolve the task, and still carry a verification command that proves
nothing.

---

## 7. Threats to validity

Stated before the run, not discovered in the write-up.

1. **Session variance and distiller variance are confounded.** Three
   independent draws vary both the source session and the distillation. The fix
   would be replaying one captured transcript into N distiller sessions; there
   is no replay path, so it is not built. A cell that varies widely cannot be
   attributed to either cause.
2. **The repair source hands over the answer.** The red assertion names the
   condition. A session may therefore distill "read the failing test" rather
   than the trap. If that is what comes out, that is the finding, and the
   archived drafts will show it plainly.
3. **Same-author curation is only half fixed.** The distiller now writes the
   skills, which is the half the brief asked for. The operator still wrote the
   tasks and chose the traps.
4. **Self-referential tasks.** Both traps are in SkillForge's own codebase,
   which narrows what any result generalizes to.
5. **The two arms use different delivery paths.** Both arrive by warm retrieval
   in practice (§3), but `/learn-failure`'s output additionally carries
   `symptoms:` that are dead in author mode, while `/learn`'s never had them.
   E5 found that the delivery path does not decide the effect, which is what
   makes this tolerable — it is not nothing.
6. **n=3 per probe cell**, against a harness whose own spread on one arm is 6/6
   versus 4/6.
7. **`index.json` and `trust.json` are user-global.** Fifty-four sessions
   rewrite them. Nothing else may run on the machine during the batch —
   including a one-off `claude -p` in `/tmp`. The batch's own inline critique
   children are suppressed for this reason (§4).
8. **Phase 1 can write to the real library.** The distiller chooses its own
   scope, and a `global` choice lands in the operator's store. Contained by
   snapshot-diff-revert per session with a precise closing assertion (§4) — but
   the containment is reactive, and a batch that trips it and cannot restore is
   invalidated rather than repaired.
9. **The comparators' trigger shape is asymmetric with the contract's.** Both
   hand-authored anti-skills carry narration-shaped symptoms —
   `"confirmed absent without examining the full input"` — written by someone
   who knew the probe would be author-mode. `distilling-failures` step 4 demands
   literal error signatures. That asymmetry is in the comparison from the start;
   it is not something the distiller failed at, and the write-up must not
   score it as one.
10. **Bench sessions inherit the operator's full plugin set** (ponytail,
    superpowers). Constant across arms, so contrasts hold; absolute numbers are
    model-plus-plugins.

---

## 8. Pre-registration

Fixed before any data exists, because E1's first batch was invalid and the
register caught two confidently-stated false claims:

- The floor is this batch's own control arm on the pinned model. The 2026-08-11
  figure is corroboration and is labelled as such.
- **All** drafts from a resolved repair are probed, 3 runs each. No draft is
  selected, skipped, or re-rolled after its content is seen.
- A draft from an **unresolved** repair is archived and reported, never probed.
  This rule is fixed now, not after seeing how many there are.
- No cell is dropped after its score is seen.
- The funnel stages in §3 are the reported output. The headline is the funnel;
  the score is one stage of it.
- A stage-5 zero is reported against the pre-probe BM25 prediction recorded
  before the run, not reinterpreted afterward.
- The secondary comparison against the hand-authored ceiling is directional and
  will be labelled as such regardless of which direction it points.
- A phase-1 abort, timeout, or rejection is a result. It is reported, not re-run.

### The two folded-in questions, declared before any data exists

Both are secondary. Neither may be reported as a Q1 finding, and neither may be
dropped from the write-up if it points the wrong way.

- **Transfer (brief Q2).** The two transfer tasks are run at n=3 each against
  this batch's control. The comparison is transfer vs. the fresh floor, and — as
  a separate, directional line — transfer vs. the matched hand-authored cells.
  The pilot's 0/6 is corroboration with its missing `model` key stated, exactly
  as the control is handled in §2.
- **Does the `trusted` gate predict anything (brief Q5)?** Reported as probe
  resolve rate grouped by each draft's `critique_verdict` from `judge.py`. The
  group-by is declared **here**, before any verdict or score exists, so that it
  is a pre-registered secondary rather than a pattern found afterward. It costs
  no sessions: `meta.json` and `results.jsonl` are both committed, so the
  analysis can be run at any later date, by any session, from git alone.
  Critique passed 0 of 9 hand-written skills, so the likely outcome is that no
  draft passes and there is no group to compare. **That is the finding**, and it
  is reported as "the gate rejected every distilled draft", not as a blank.

## 9. How to read the outcome

- **Drafts save and probes beat the fresh control.** The pipeline closes end to
  end. Q1 is answered affirmatively and the distiller stops being the untested
  link.
- **Drafts save, probes sit at control.** The distiller emits valid artifacts
  that do not help. The funnel says at which stage — never delivered (a
  description that does not match the probe prompt, predicted in advance by the
  BM25 dry run) versus delivered and ignored (a content problem). Different
  fixes.
- **Drafts do not save, or repairs do not resolve.** The pipeline does not
  close, and the funnel names the gate that stopped it. Cheapest possible
  answer; costs no probe sessions.
- **The two distillers diverge.** Expected to be informative given that `kind:`
  carries delivery tier and verification eligibility, but at n=3 per cell,
  report the split and do not rank.

## 10. Out of scope

Harm from irrelevant injection (E4, blocked on a task that does not exist) and
token cost per unit of benefit (brief Q4). Nothing here requires a new trap, a
new task, or a new repository.

Transfer (Q2) and the `trusted` gate (Q5) were out of scope in the first draft
and are now folded in as **pre-registered secondaries** (§8). Neither is a Q1
result. Q2 rides this batch because it needs a same-configuration floor and this
batch is the only one that has one; Q5 rides it because the batch produces its
data anyway and only the analysis was missing. Q1's headline is still the funnel
in §3, and a Q2 or Q5 result does not change it in either direction.

---

## Review log

Revised against an adversarial review that checked the first draft against the
code at `925810d`. Ten findings; every mechanical claim independently verified
before adoption.

| # | Finding | Disposition |
|---|---|---|
| F1 | Control floor never measured on the pinned model — every control row lacks `model` | Adopted. 6 control sessions; 48 → 54 |
| F2 | Phase 1 never checked the repair succeeded | Adopted. §4 step 5, §5 outcome 1, §8 |
| F3 | Symptoms are dead in author mode; stage 5 is a description test | Adopted in full — §3, the BM25 dry run, §7.9 |
| F4 | `library.py delete`'s resync drops project entries from `index.json` | Adopted, **narrowed**. Mechanics confirmed at `sync.py:330`; the state is derived and self-healing, so the defect is an imprecise assertion, not library mutation |
| F5 | `trust.json` is global regardless of scope | Adopted. "Phase 2 is safe" corrected; key set snapshotted |
| F6 | Every create spawns a detached critique child | Adopted, **as an env var, not the flag this row originally proposed** — the phase-1 session invokes `save_skill.py` itself, so nothing can pass it one. See §4 |
| F7 | Time estimate low "by an order of magnitude" | **Partly rejected.** 42 probes × median 72.3s ≈ 50 min, which is what the draft said. Adopted the real point: do not extrapolate author-mode timings to phase 1, pilot it, and distinguish timeout from abort |
| F8 | Historical rows lack `skill_source` | Adopted, backfill preferred over a read rule |
| F9 | Duplicate check reads the operator's real library | Adopted. Per-draw precondition, §4 step 1 |
| F10 | Stage 5 assumes the skill lands warm | Adopted. Asserted after `install_skill` |
