# Brief: design a benchmark that shows whether SkillForge helps

You are investigating how to measure whether SkillForge meaningfully improves
a coding agent's output. Produce a benchmark *design*, not a benchmark. The
deliverable is a spec someone can then build and run.

Read this whole brief before proposing anything. Most of the obvious designs
have already been tried here and measured nothing, and the reasons are
specific and worth more than a fresh start.

---

## What SkillForge claims

It watches a coding session, notices a struggle that ended in a success,
distills that into a skill file, and injects relevant skills into later
sessions. Skills live in three tiers: **cold** (searchable), **warm**
(injected when a prompt or a tool-output symptom matches), **hot** (injected
into every session unconditionally, for skills that earned `trusted`).

The claim under test is that this loop makes later sessions better. Nothing
currently establishes that.

## Start here: prior art you must read before designing anything

A pilot benchmark exists on the unmerged branch
`claude/project-status-roadmap-4c408a`, under `bench/`. Read
`bench/RESULTS.md` in full, and `bench/run.py` and `bench/tasks.json` for the
harness shape.

```bash
git show claude/project-status-roadmap-4c408a:bench/RESULTS.md
git ls-tree -r --name-only claude/project-status-roadmap-4c408a -- bench/
```

Its headline, across two independent traps, three runs per condition:

| Condition | Combined |
|---|---|
| Control — no skill | 0/6 |
| Matched — skill distilled from this exact trap | 5/6 |
| Transfer — same-class skill, different bug | 0/6 |

Every treatment run was ledger-confirmed as actually injected, so the transfer
null is a real null rather than a delivery failure.

**Four hard-won lessons in that document. Do not spend budget rediscovering
them.**

1. **FAIL_TO_PASS tasks structurally cannot measure this.** A failing test
   names the exact condition, so the task hands over the answer; one control
   session derived the whole insight from the red assertion. Every
   SWE-bench-style benchmark is FAIL_TO_PASS. That entire family is out.
2. **Leaky stubs.** A stub docstring that describes the object being handled
   can prescribe the fix. Their first attempt scored 6/6 in *both* arms
   because of one phrase, and the leak check grepped for the obvious keywords
   and sailed past it.
3. **A condition scoring 0 in every arm is a suspect test, not a hard task.**
   One of their hidden tests encoded the reference implementation's
   *strategy*, so a better implementation scored zero while demonstrably
   holding the knowledge.
4. **No headroom is the default failure.** Public-repo and recent-bug repair
   tasks were both resolved by the control arm. If the base model solves it,
   there is nothing for a skill to add.

## What has changed since that pilot

- **Slice D1** added automatic capture (struggle→success breadcrumbs, detached
  drafting).
- **Slice D2** added Tier A validation: a `critique` verdict on the skill text
  and an `executable` verdict that runs the skill's own `verification.command`
  in a throwaway worktree. `trusted` now requires a critique pass in addition
  to organic evidence.
- **Outcome attribution was just repaired.** Before that fix, a skill was
  credited with a success whenever a Bash command pattern-matched its
  `verification.command`, with no requirement it was ever injected or read.
  See `docs/superpowers/specs/2026-08-29-outcome-attribution-design.md`.
- **Critique currently passes almost nothing** — nine hand-written skills, zero
  passes, with nearly every objection substantively correct. See
  `bench/critique-calibration/README.md` on `main`, which is a worked example
  of the corpus-with-ground-truth pattern and of that pattern's limits.

## The questions worth answering, roughly in order of value

**1. Does the pipeline work end to end, or only the injection half?**
The pilot injected *hand-authored* skills written by the person who found the
bug. That measures a ceiling: the best possible skill, matched perfectly. It
does not measure the distiller. The full claim is session → distilled skill →
later session improved, and the distiller's output is the untested link.

**2. Is transfer real at any n?** This is the load-bearing question. If skills
only help on the exact trap they were distilled from, SkillForge is a cache,
not a learner — still useful, but a much smaller claim, and one that should be
stated honestly in the README. The pilot's transfer arm was indistinguishable
from control at n=3. Establishing transfer, or establishing its absence at a
convincing n, is the single most valuable result available.

**3. Does injection ever hurt?** Never measured. Hot-tier skills enter every
session unconditionally and cost tokens. A wrong or stale skill could plausibly
mislead. A benchmark that can only detect improvement is half a benchmark.

**4. What is the token cost per unit of benefit?** Hot tier trades context
budget for guidance on every session, including the ones where it is
irrelevant.

**5. Does the `trusted` gate predict anything?** Now partly answerable: do
skills that pass critique outperform those that fail it? If not, the gate is
ceremony.

## Traps specific to *this* system

- **Selection effect.** Choosing benchmark tasks after seeing which skills you
  have is rigging. Fix the task set first, or draw skills and tasks from
  disjoint sources.
- **Same-author curation.** In the pilot, one person found the bugs, wrote the
  skills, and wrote the tasks. Consider having the distiller produce skills
  from sessions that someone else's tasks then probe.
- **Self-referential tasks.** The pilot's tasks are on SkillForge's own
  codebase. Convenient, and it narrows what the result generalizes to.
- **Verify delivery, always.** Confirm from the ledger that each treatment run
  actually received the skill. Without that, a null is ambiguous between "no
  effect" and "never arrived." The pilot did this and it is why its transfer
  null is trustworthy.
- **Attribution.** Do not reuse the ledger's own success counts as your outcome
  measure. They are a proxy — a skill can be injected, ignored, and still
  credited when a matching command runs. Score the benchmark independently.

## Open design questions — investigate and recommend

- **What is the outcome measure?** The pilot used binary hidden-test pass,
  chosen deliberately over turns-to-completion. Is that right for measuring
  *quality* rather than capability? What would detect a subtler improvement —
  fewer defects, better structure, fewer wrong turns?
- **Where does headroom come from,** given repair tasks leak the answer and the
  base model is strong? The pilot's answer was authoring-from-contract tasks
  against a stubbed function. Are there other shapes — tasks with a
  non-obvious environmental gotcha, tasks where the naive solution is subtly
  wrong?
- **How many runs, and how do you handle model nondeterminism?** The pilot ran
  n=3 and its own limits section flags that as thin.
- **Can any of this be automated cheaply enough to run on every slice,** or is
  it necessarily a periodic manual exercise?
- **Is there a cheaper leading indicator** that correlates with the expensive
  benchmark, so the loop is not "spend a day to learn anything"?

## What a good deliverable looks like

A spec that names: the task family and why it has headroom; the arms; the
outcome measure and how it is scored blind; how delivery is verified; the
sample size and what effect it could detect; the specific way the design could
fool you and what guards against it; and an estimate of cost per run.

Say plainly which of the questions above your design does **not** answer.
Every prior design that measured nothing here is documented; that honesty is
what makes the pilot's one real result trustworthy.
