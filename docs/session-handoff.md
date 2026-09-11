# SkillForge — session handoff

Written 2026-09-09, at the end of the session that built the Q1 harness, ran
it, and answered the brief's largest open question. Supersedes the 2026-09-08
revision (git history has it). Read this before touching anything; several
things here are not discoverable from the code.

---

## 0. THE OPERATIONAL THING THAT WILL BITE YOU FIRST

**There are two separate meters and you are probably watching the wrong one.**

Token quota and *session count* are limited independently. This session spent
roughly 75 `claude -p` sessions (62 bench clones plus subagents) and ended at
**46% of token quota** — and then could not start a single further session:

```
You've hit your session limit · resets 1:10am (America/New_York)
```

`claude -p` exits **1** in that state and prints that one line. That exit code
is the only thing separating a postponed experiment from a poisoned one — see
§4.

**Size future batches against sessions, not tokens.** A 60-session batch costs
about 4% of quota and a large fraction of the session allowance. If you plan a
batch, check the session meter first; the quota figure will tell you nothing
useful.

---

## 1. Where things stand

**Brief Q1 is answered.** The distiller works end to end — when it emits, and
it emits 4 times in 12. Those four scored **12/12** against a fresh control
floor of **1/6**, delivered on every run, warm tier, `trigger: prompt`. Every
session fixed its bug; nothing timed out, nothing was refused, `save_skill`
rejected nothing. The bottleneck is **emission**, not delivery and not content.

Full write-up: `bench/RESULTS.md`, section "Q1 — does the distiller work end to
end?". Three findings inside it that are worth knowing before you read
anything else:

- **Emission is a property of the trap, not the distiller.** Trap A throws
  loud assertion failures so literal `symptoms:` exist, and the anti-skill arm
  emitted 3/3. Trap B is silent, and every anti-skill draw refused because "any
  symptoms list would be **invented**, and invented triggers pollute the
  detection index". The anti-skill path is structurally unavailable for
  symptomless traps.
- **The judge found the opposite of the scores.** All four drafts pass
  critique, and **not one declared `verification.command` discriminates** —
  both point at this repo's own suite, which *passes* at `fix_commit~1` because
  the tests exposing the trap do not exist yet. One fingerprint in nine appears
  in the real fix. The drafts that scored 12/12 carry attribution machinery
  that does not work.
- **The 8 novelty-gate refusals are unfalsifiable here.** "A fresh Claude
  already knows this" is a self-assessment, and the rejected drafts are never
  probed. Meanwhile control resolves these tasks 1 in 6 — so the distiller
  declined to record knowledge the model demonstrably fails to apply five times
  out of six. **This is the most interesting thing the experiment surfaced and
  nothing tests it.**

**Brief Q2 (transfer) is a replicated null.** 0/6 again, and for the first time
against a floor measured in the same batch on the same pinned model.

**Brief Q5 was attempted and came back uninformative.** Critique passed all
four drafts, so there is no failing group to split on. It needs drafts the gate
*rejects*, which this design does not produce.

**E6 is answered.** No dilution at n=3 per cell. See §2.

---

## 2. START HERE — E7 is answered, and it changes the priority list

**The novelty self-gate was refusing skills that work.** Full write-up in
`bench/RESULTS.md`, section "E7 — is the novelty gate over-refusing?".
Pre-registration: `docs/superpowers/specs/2026-09-10-e7-novelty-gate-design.md`.

| | gate on (Q1) | gate suspended (E7) |
|---|---|---|
| `learn` draws that emitted | 1 of 6 | **6 of 6** |
| those drafts, probed | — | **16/18**, against same-batch control **0/6** |

Zero exclusions across 24 phase-2 rows. Every treatment run injected exactly
one skill at `trigger: prompt`. Every one of the six drafts individually beat
the floor; the weakest was 2 of 3.

Read the limits before using it. **n=3 per cell.** The 18 treatment runs are
6 artifacts × 3 runs, not 18 independent draws — the pooled Fisher p of 0.0002
is in the write-up only to be discounted. And E7 re-ran the draws rather than
recovering Q1's refused drafts, which were never written.

**What E7 does NOT say is what replaces the gate.** It measures that "a fresh
Claude already knows this" is wrong on these two traps. A library with no
filter at all is untested in either direction, and that is now the open
question rather than whether the gate is too strict.

**Two things are settled that were not before:**

- **The graded scorer is finished, and the answer is that it adds nothing
  here.** It reproduced the binary verdict in 40 of 42 rows on 2026-09-10 and
  24 of 24 on E7's fresh artifacts. These tasks are single-trap — a session
  either sees the trap or it does not — so no scorer can manufacture middle
  ground the work does not contain. **Do not build more probes for these two
  tasks.** The instrument works; there is nothing for it to resolve.
- **`/consolidate`'s blocker has a measured break in it.** It was blocked
  because the library is empty, which was because the distiller rarely emits,
  which was because of this gate.

## 3. Next steps, in priority order

### 3.2 E4 is still blocked, and the scorer did not unblock it

E4 asks whether an irrelevant skill hurts **versus nothing**. It needs a task
whose control baseline is neither 0 nor 100%.

The 2026-09-09 revision of this file argued the real blocker was binary
scoring, and that a graded rubric over the authored function would give control
partial credit and therefore room to lose. **That scorer was built, and the
argument did not survive it.** The 20-probe suite reproduces the binary
`resolved` verdict in 40 of 42 rows (2026-09-10) and 24 of 24 (E7). Control
does score off zero — 0.636 and 0.778 — but **no artifact has ever scored
below that floor**, so the room to fall is asserted, not observed.

These two tasks are single-trap: a session either sees the trap or it does
not. No scorer manufactures middle ground the work does not contain. E4 needs
a genuinely mid-range task, and building more probes for these two will not
produce one.

**Control figures: re-derive them, do not quote them.** The "1/6 and 0/6"
carried in three specs cannot be reproduced from one consistent rule — 1/6
needs `results-round1.jsonl` pooled in, 0/6 needs it left out. Every reading
puts both floors at or near zero, so nothing downstream changed, but the
figure is not what it claims. E7's own same-batch control is **0/6**, measured
2026-09-11, and that one is clean.

**Do not pool across `results-leaky-stub.jsonl`.** Its author-task rows are 3/3
*because that stub leaked the answer*. Pooling makes `response_text` control
look like 44% and makes E4 look unblocked. It is not.

### 3.3 What should replace the novelty gate? (new, from E7)

E7 answered the question this slot used to hold: the gate is over-refusing.
The successor question is what goes in its place, and it is genuinely open.

The gate's justification is that junk saves pollute the library. Two
measurements now bracket it. E6: an irrelevant skill that arrived, outranked
the relevant one and occupied 93% of the injection budget cost **nothing
detectable** (R 6/6, R+I 6/6, n=3 per cell). E7: refusal cost a working skill
**six times out of six**. Pollution looks cheap on the one axis measured;
refusal looks expensive.

That does **not** license removing the gate. E6 measured one irrelevant skill
against one relevant one in a library of two. Nobody has measured a library of
fifty, where retrieval has to choose, and eviction and ranking are still four
of five hot-tier mechanisms with no evidence behind them (§3.5). "No filter"
is untested in either direction.

The cheap next probe: keep emitting with the gate off and measure whether
retrieval still finds the right skill as the library grows. That is a
different shape of experiment from everything here so far — it needs a library
with depth, not another n=3 cell.

### 3.4 Build `/consolidate` (v0.3)

Cleared by E1 in September, unconstrained by E5, still not written. It is the
v0.3 feature the whole experimental programme was gating.

### 3.5 The hot tier: 4 of 5 mechanisms still unevidenced

Delivery is confirmed (2026-09-08). Promotion order, the 1,500-token budget,
`confidence × recent usage` ranking, and eviction pressure have never been
exercised against a model that could see the result. Needs an arm with two or
more hot-eligible skills that together exceed the budget; the force-hot lever
takes a single exact name and cannot express that.

### 3.6 Hygiene

- **`main` is 32 commits behind this branch** and this work is unmerged.
  E6 ran on `claude/e6-dilution-experiment-84c0d2`, which was fast-forwarded
  onto `claude/skillforge-hot-tier-validation-569edb` first; the two share a
  history and either can be merged.
- `main` has never been pushed to `origin`.
- `/tmp/skillforge-bench` holds 62 clones and their ledgers. Harmless, in
  `/tmp`, but the per-run ledgers are the *only* copy of delivery evidence for
  batches before 2026-09-09 — rows from that date onward carry `injections`
  on the row itself.

---

## 4. Things not discoverable from the code

- **A refused session is not a result, and the code now knows it.**
  `bench_run.sh` *returns* on a non-zero exit rather than raising, so before
  this session a rate-limited session flowed on to `score()`, found the repair
  unresolved, and was archived as `repair_unresolved` — a false claim about the
  distiller, and then *locked*, because the archive guard refuses a re-run once
  `secs > 0`. Now: `meta.json` records `session_ok`, `session_failed` is an
  outcome ranked above every other, it is never probeable, and a refused draw is
  retryable. Phase 2 rows with `session_ok: false` are **excluded from every
  cell** by a rule pre-registered in spec §8 *before any data existed*. This
  fired on E6's first attempt and is why E6 is postponed rather than poisoned.
- **`--skill-from` must be absolute.** `install_skill` shells `save_skill.py`
  with `cwd` set to the clone, so a relative path resolves against the clone and
  is not there. Twelve probes died before any session started. `skill_src` now
  resolves. I had explicitly ruled *against* the guard that would have caught
  this, on the grounds it would break the batch driver; the reasoning was
  backwards.
- **The test suite used to run against the real bench work directory.**
  `test_one_archives_and_contains_a_global_scope_draw` redirected `ARCHIVE` and
  `HOME` but not `bench_run.WORK`, so it read a real run's saved draft and
  **truncated that run's ledger to zero bytes**. Fixed; a sentinel file proves
  the suite leaves `/tmp/skillforge-bench` byte-identical. This repo has shipped
  one fix for a suite that destroyed real state already (0.2.5, hot skills).
- **`verification.command` is optional for anti-skills.** `save_skill.py:145`
  requires it only for `kind: skill`. All four hand-authored comparators declare
  none. A blank is not a defect.
- **`drift()` compares project entries for ONE root.** Comparing all of them
  reports drift on a clean batch, because every clone writes a transient
  `/tmp`-rooted entry. Spec §4(d) asks only about the operator's own root.
- **Containment writes to the operator's real library and reverts.** A
  distilling session picks its own scope; `--scope global` lands in
  `Path.home()`. Both revert paths fired during Q1: one draw went global and was
  removed with `library.py delete`; three went project-scoped and left only a
  trust key, caught by `new_trust_keys`. `trust.json` is user-global
  **regardless of scope**, so every save leaves a key and nothing else prunes it.
- **The register at the top of `bench/RESULTS.md` is the index.** It exists
  because two confidently-stated claims in that file turned out to be wrong.
  I added a third in this session — a Q1 row reading "Answered … This is the
  largest open question in the project" — by swapping a leading phrase and
  leaving the sentence. Re-derive from the files; do not describe them from
  memory.
- **0.2.6 is on this branch, not merged and not installed.** The installed
  cache is 0.2.5 at `b712e4b`. It does not matter for the bench, which passes
  `--plugin-dir` at the repo root and never reads the cache. It matters the
  moment anyone runs the bench against the installed plugin.

---

## 5. Where the work is

Branch `claude/skillforge-hot-tier-validation-569edb`, in the worktree at
`~/Developer/skill-forge/.claude/worktrees/skillforge-hot-tier-validation-569edb`.
30 commits ahead of `main`. Run everything from the worktree.

New this session, all tested (18 suites, 25 + 60 bench tests):

| File | What it does |
|---|---|
| `bench/distill.py` | Phase 1: repair session → distiller → archive. Six outcomes |
| `bench/libguard.py` | Snapshot / diff / prune / restore of the operator's real library |
| `bench/dryrun.py` | Predicts delivery from `name + description` before probing |
| `bench/judge.py` | Retrospective critique, symptom shape, does the verification discriminate |
| `bench/backfill.py` | One-shot `skill_source` label on historical rows |
| `bench/run.py` | `--skill-from`, `--plus-skill`, derived clone segments, `injections` on the row |

The SDD execution ledger — every ruling made on your behalf, ~29 of them — is
at `.superpowers/sdd/2026-09-08-q1-distiller-experiment/progress.md`. It is
git-ignored and will not survive a `git clean -fdx`.
