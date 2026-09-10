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

**E6 is designed, built, and did not run.** See §2.

---

## 2. START HERE — E6 is one command, after the session window resets

`docs/superpowers/specs/2026-09-09-e6-dilution-design.md` asks whether an
irrelevant skill **dilutes** a relevant one. It is not E4 (§3.2).

Everything is ready. The harness change (`--plus-skill`) is committed and
tested, and three viability facts were measured for free before the design was
written:

- the irrelevant payload **is delivered** (predicted `deliver`, 7 matched terms
  on both tasks), so a null cannot mean "never arrived";
- it **outranks the relevant skill** on `response_text` — 2.53 to 1.87. BM25
  ranks a skill about `arrow` timezone handling above the matched serialization
  skill. E6 therefore tests a realistic bad case;
- both skills fit the 1200-token injection budget at **93% occupancy**, which
  is what keeps this a dilution test rather than a crowd-out test.

```bash
cd /Users/dwightbritton/Developer/skill-forge   # then the worktree, see §5
python3 bench/run.py --check
I="$PWD/bench/skills/arrow-tzinfo-string-trap.md"
# arm R first, both arms in ONE batch (E5: cross-batch comparison is untrustworthy)
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text --plus-skill "$I"
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting --plus-skill "$I"
```

12 sessions, ~12 minutes. **Then** read §5 of the design for the pre-registered
rules — in particular: a run where only *one* skill injected measured crowd-out,
not dilution, and is reported separately rather than pooled.

The previous attempt left 3 valid rows and 9 excluded ones in `results.jsonl`.
They are correctly labelled; `results.jsonl` is append-only and the exclusion
rule keeps them out of the re-run's cells. Do not delete them.

---

## 3. Next steps, in priority order

### 3.1 Run E6 (§2). 12 sessions.

### 3.2 E4 is still blocked, and the diagnosis changed

E4 asks whether an irrelevant skill hurts **versus nothing**. It needs a task
whose control baseline is neither 0 nor 100%. Live control cells, superseded
rows excluded:

| task | live control |
|---|---|
| `sf-author-response-text` | 1/6 |
| `sf-author-fingerprint-preexisting` | 0/6 |
| `sf-escaping-breaks-symptom-match` | 2/2 |
| `sf-truncation-reports-absent` | 2/2 |

**1/6 is not the mid-range baseline it looks like.** If the true rate is 1/6, a
*harmless* arm reads 0/6 **33.5%** of the time. No room to fall. (From 50%, the
same reading occurs 1.6% of the time.)

**Do not pool across `results-leaky-stub.jsonl`.** Its author-task rows are 3/3
*because that stub leaked the answer*. Pooling them makes `response_text`
control look like 44% and makes E4 look unblocked. It is not. I made this exact
mistake in this session and caught it only by re-deriving from the files.

**The real blocker may be binary scoring, not the task.** `resolved` is
all-or-nothing, so a 0/6 control has nowhere to fall *by construction*. A graded
rubric over the authored function (does it cap? does it set the unknown flag?
does it handle the nested case?) gives control partial credit, and partial
credit has room to lose. The pilot rejected *turns-to-completion* as
high-variance and gameable; that rejection does not extend to a rubric over the
artifact. This reframes E4 from "we need a task that does not exist" to "we need
a scorer we have not written", which is tractable work on a known target.

A graded scorer would also sharpen everything else here. Several of this
project's resolution problems trace back to three bits of information per cell.

### 3.3 Probe a rejected draft (new, from Q1)

The eight novelty-gate refusals are never tested. Take one, save it anyway, and
probe it. If it scores like the accepted ones, the gate is over-refusing and the
library is being starved. Nobody has specified this experiment; it is cheap
(the drafts' reasoning is archived in `bench/distilled/*/*/*/meta.json`, but the
drafts themselves were never written, so you would need to re-run those draws
with the gate bypassed).

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

- **`main` is 30 commits behind this branch** and this work is unmerged.
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
`/Users/dwightbritton/Developer/skill-forge/.claude/worktrees/skillforge-hot-tier-validation-569edb`.
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
