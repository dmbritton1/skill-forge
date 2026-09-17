# SkillForge — session handoff

> **Newer:** `docs/handoff-2026-09-15-e15.md` covers the bench sandbox, E14 and
> E15 (built, not yet run), with step-by-step instructions for E15's real run.

Written 2026-09-11, at the end of the session that answered E7, E8 and E9,
built `/consolidate`, and ended by diagnosing a defect in the injection
selector. Supersedes the 2026-09-11 morning revision (git history has it).
Read this before touching anything; several things here are not discoverable
from the code.

---

## 0. THE OPERATIONAL THING THAT WILL BITE YOU FIRST

**There are two separate meters and you are probably watching the wrong one.**

Token quota and *session count* are limited independently. `claude -p` exits
**1** when the session allowance is gone and prints one line:

```
You've hit your session limit · resets 1:10am (America/New_York)
```

That exit code is the only thing separating a postponed experiment from a
poisoned one — see §4.

**Size batches against sessions, not tokens.** A 60-session batch costs about
4% of quota and a large fraction of the session allowance. Check the meter
before planning a batch:

```bash
claude -p "Reply with exactly: OK" --model claude-opus-5
```

This fired twice during this session — once mid-E8, once during a task
re-review. Both were absorbed by the pre-registered `session_ok: false`
exclusion rule rather than corrupting a cell. That rule is why these
interruptions cost time instead of evidence.

---

## 1. What this session did

Eight pieces of work, in order. All of it is on one branch, none of it is
pushed. Every experiment is n=3 per cell unless stated.

**1. Repaired the test suite.** It was 103 failures deep and every one was
pollution, from two independent leaks. `bench/distill.py` sets three
`SKILLFORGE_*` environment variables process-wide and never restores them, and
`SKILLFORGE_LEDGER` outranks `HOME`, so sandbox helpers were reading a real
batch's rows. Separately, three test files stub `sync._spawn_validation` at
module scope, and `test_sync.py` was capturing `test_guard.py`'s inert lambda
because that file imports first alphabetically. Both are fixed by
`tests/conftest.py`, which restores the environment around every test and
captures the genuine function before pytest imports any test module.

**2. E7 — is the distiller's novelty self-gate over-refusing? Yes.**
Suspending step 2 of the distiller prompt alone took emission from **1 in 6**
to **6 in 6**. Those six drafts scored **16 of 18** against a same-batch
control of **0 of 6**, and every one of the six beat the floor. The gate was
refusing skills that work.

**3. E8 — does retrieval survive a library of ten? Yes, but not for the
predicted reason.** Matched 3/3, library-of-ten 3/3, control 0/3, on both
tasks. Depth did not hurt. But on `sf-author-response-text` the prompt path
delivered a **wrong-trap** skill 3 times out of 3, and the **symptom path
rescued it** 3 times out of 3. That rescue rides on anti-skills, which Q1
showed cannot exist for a silent trap, so the dangerous case was never tested.

**4. Built `/consolidate`.** Spec, plan, then five tasks of subagent-driven
development with a review after each, one final review, and one fix wave.
`scripts/consolidate.py` is the deterministic half — clustering by
verification command, name inheritance, pattern union, propose and retire.
`commands/consolidate.md` is the model procedure. 31 tests.

**5. E9 — does a consolidated skill still work? Yes, and it fits.** Merges
compressed three and two skills to **44%** and **54%** of their concatenation,
landing at 1095 and 1088 tokens against the 1200 budget, and passing
`save_skill.validate` clean. Retrieval 3/3, knowledge 3/3, control 0/3 on both
tasks, zero exclusions.

**6. E8 follow-up — does consolidating fix E8's ranking failure? No, it makes
it worse.** The correct skill fell from rank 3 to rank 5 after merging. A
description covering three skills matches any single prompt less specifically
than a single-purpose one, and BM25 rewards specificity. This is brief Q2's
transfer null reappearing one layer down, and nothing in the `/consolidate` design
anticipated it.

**7. Budget derivation — what budget delivers a correct skill?** 3000 works.
The curve is **not monotonic**: at 2000 the correct skill is delivered, at
2400 it is crowded back out, at 3000 it returns.

**8. Diagnosed the selector defect behind that dip, and measured three fixes.**
This is where the session ended and where §2 picks up.

---

## 2. The selector is monotone now — shipped 2026-09-13

Reproduce free with `python3 bench/selector_check.py`. Zero sessions.

Both delivery paths used to walk a ranked list and `continue` past any entry
too expensive for the remaining budget. A cheaper lower-ranked skill could
therefore occupy space a dearer higher-ranked one would have taken, and which
one won depended on the budget in a way that was not monotone: **more budget
could deliver a strictly worse set.**

Measured over a budget grid of 600–4000 in steps of 50, across two pools
(E8's ten skills, and the consolidated seven) and both tasks:

| selector | flips | shrinks | lowest budget correct on both tasks |
|---|---|---|---|
| `continue` (pre-2026-09-13) | 3 | 15 | ten **1750, not held above**; seven 1850 |
| **`break` (shipped)** | **0** | **0** | ten 2900; seven 1850 |
| highest-scoring affordable subset | 8 | 57 | both **not held above** |

A *flip* is the correct skill being delivered at one budget and gone at the
next one up. A *shrink* is the delivered set failing to contain the set below
it.

`retrieve.run_hook` now stops at the first entry that does not fit. Delivery is
the longest rank-ordered prefix that fits, and a prefix can only grow as the
budget grows.

**It cost nothing on a consolidated library.** The seven-skill pool needs 1850
either way; the difference is that the result now holds above that point
instead of depending on two costs straddling a threshold. The cost falls
entirely on the duplicate-heavy ten-skill pool, where the stable threshold is
2900 against an unstable 1750. That is the first legible payoff `/consolidate`
has shown since the E8 follow-up found it worsened ranking.

**Re-measured after `9cbb472` dropped function words from tokenization:** the
consolidated pool's lowest stable budget is now **1100**, below the shipped 1200,
and the ten-skill pool's is 2800. `break` still scores 0 flips and 0 shrinks.

**A cleverer selector was tested and is worse.** Choosing the affordable subset
with the highest total score more than triples the flips and quadruples the
shrinks. An optimal subset is not stable under a growing budget either —
dropping one item for two cheaper ones is exactly the move that loses a correct
skill. This was measured, not assumed.

### What taking it decided, and what it costs

The old intent was that an oversized entry should be skipped so a cheaper
lower-ranked one gets in. Taking `break` decided that intent was wrong. The
case: brief Q2's transfer arm measured a plausible-but-wrong skill at **0/6**,
so "something is better than nothing" was never supported by this project's own
data.

The case for hesitating, as this section recorded it, was that a cheap correct
skill below an expensive wrong one is what rescued `response_text` at budget
2000. **That argument is void** — E10 retired `response_text` on 2026-09-13
after its control resolved 6/6. The case for `break` is therefore stronger than
this section could have known when it was written.

**The cost is real and broader than the payload.** Delivery is a prefix, so an
entry that overflows the budget suppresses everything beneath it — anti-skills
included, even though `MAX_SKILLS` otherwise lets them past the skill cap.
§3.3's save-time size guard, shipped the same day, is what makes that
tolerable: an entry too large for the whole budget can no longer be saved.
Libraries that predate the guard keep the exposure.

**The symptom path did not need this fix.** Earlier revisions of this section
and of §3.1 claimed `detect.run_hook` needed "a flag that halts admission while
the scan continues," because its detection telemetry is written earlier in the
same loop. That reasoning holds only for a path that ranks. `detect.py` does
not: it walks `idx["symptoms"]` in compile order under `MAX_ANTISKILLS = 2`, so
there is no rank-ordered prefix to preserve and no monotonicity defect to
repair. It keeps its `continue` deliberately, and
`test_budget_skips_oversized_antiskill` pins that.

---

## 3. Next steps, in priority order

**E10 ran on 2026-09-13 and half of it is void — read `bench/RESULTS.md`'s E10
section before planning anything.** `fingerprint` came back clean (M 3/3, P
3/3, S 3/3, C 0/3: no large prompt-time harm at 1847 tokens). `response_text`
is void because **control resolved 3/3, and 3/3 again on a dedicated
re-measure** — 6/6 against a 1/13 history, zero injections, clean library.
**That task is retired as a discriminator.** It is not a general capability
shift: `fingerprint`'s control ran minutes earlier in the same batch and stayed
at 0/3, 0/18 lifetime. `response_text` was simply the marginal trap — its floor
was never zero. A control floor decays; read it as a live number before putting
a task in a batch.

**E11 then screened the two never-run tasks and rejected both** — A 6/6, B 6/6
control at n=6 each, ceiling rather than marginal, against a same-batch
reference that held at 0/3. Both are `mode: repair`, which shows the model the
failing tests; the spec pre-registered that as the weaker trap before the batch.
**The bench now has exactly one usable trap**, `fingerprint_preexisting` at
0/21. Ten task ids carry just **two** `fix_commit`s — `22ddf37` and `ab4acfe`,
five ids each — so the four tasks are two bugs crossed with two modes. The
`-transfer`/`-irrelevant`/`-umbrella` variants share `prompt`, `stub_cmd` and
`test_path` byte-for-byte and differ only in which skill is paired, and control
never sees the skill, so one floor covers a whole family.

**The `ab4acfe` bug reads 0/21 in author mode and 6/6 in repair mode.** Same
bug, same tests. That within-bug contrast is the tightest evidence this project
has that *mode*, not bug difficulty, sets the floor. (An earlier revision of
this line said "four distinct bugs", which was wrong and hid that comparison.)
Screening is finished as a source of supply. See §3.8.

**E12 (2026-09-13) found no large harm from an irrelevant skill.** Every arm
scored 12/12, on repair-mode tasks whose tests are visible. That is the third
harm null. The cost this bench has actually measured is the *missed* skill, not
the wrong one, so the delivery gate and ranking are the next target (see the
delivery-gate section of `bench/RESULTS.md`). The gate was fixed the same day
(`9cbb472`): function words are dropped at tokenization, which also improved
ranking. See §3.1 for what that does to the budget question.

### 3.1 Land the selector fix, then re-derive the budget — **STEPS 1–8 DONE 2026-09-13**

In order:

1. ~~Change `retrieve.run_hook` to stop at the first entry that does not fit.~~
   **Done.** One `continue` became a `break`; the other four in that loop
   (dedupe, `MAX_SKILLS`, unreadable body, untrusted) are not budget decisions
   and were left alone.
2. ~~Change `detect.run_hook` to the flag form~~ — **this step is wrong and
   should be struck.** `detect.py` does not rank: it walks `idx["symptoms"]`
   in compile order under `MAX_ANTISKILLS = 2`, so "longest rank-ordered
   prefix" has no meaning there, and `test_budget_skips_oversized_antiskill`
   pins the current behaviour deliberately. The monotone-selector problem is
   the prompt path's alone.
3. ~~Replace `test_budget_skips_oversized_entry` with a test of the new
   intent.~~ **Done** —
   `test_budget_stops_at_the_first_entry_that_does_not_fit`. Both fixture
   entries score 0.6251; `rank()` breaks the tie by name ascending, so
   `big-terraform` is genuinely rank 1 and nothing survives it.
4. ~~Add a **budget monotonicity property test** over the real hook.~~
   **Done** — `test_budget_monotonic_over_a_sweep`, 27 budget steps through
   the real hook via `SKILLFORGE_INJECT_BUDGET`, asserting each delivered set
   contains the one below it. This is the test that would have caught the bug.
5. ~~Add a **rank fidelity test**.~~ **Done** —
   `test_nothing_is_delivered_below_an_entry_refused_on_cost`.
6. ~~Add an **anti-skill test on the prompt path**.~~ **Done** —
   `test_budget_stop_also_suppresses_antiskill_below_it`. The behaviour is
   pinned, not discovered later: prefix semantics suppress anti-skills below
   the overflow point even though `MAX_SKILLS` lets them past the skill cap.
7. **Struck — moot, not skipped.** This existed to protect detection logging
   through step 2's change to `detect.py`. Step 2 is struck, `detect.py` is
   untouched, and a test guarding a change that was never made protects
   nothing. Its concern is already covered by
   `test_budget_skips_oversized_antiskill`, which pins the symptom path's
   deliberate `continue`.
8. ~~`bench/budget_sweep.py` re-implements the selector by hand.~~ **Done** —
   updated in the same commit, as its own warning demanded. `selector_check.py`
   was relabelled too: its `continue` arm is no longer "today's code".

**§3.3's size guard landed first (2026-09-13), which de-risked step 1.** Under
`break` an oversized skill at rank 1 blocks everything beneath it; such a skill
can no longer be saved, so the worst case is a library that predates the guard
rather than one the guard let through.

**Re-deriving the budget is what remains of this section.** Under `break` on a consolidated library the
target is around **1850 for two skills**, not 3000 for three, which is a much
smaller step past E6's measured no-harm at ~1118 tokens for two.

**E10 tested that step and licensed only half of it.** At 1847 tokens a
wrong-bug skill riding *behind* the correct one cost nothing on `fingerprint`
(3/3 against a 0/3 control, n=3). The case that motivates the raise in the
first place — E8's ranking failure, where the correct skill is the one that
comes **second** — went void with the `response_text` control. So the raise is
evidenced for the ordering that never needed it, and unevidenced for the
ordering that does. A re-run needs a task whose control still sits at the
floor.

**2026-09-13, after the tokenizer fix (`9cbb472`): the budget question has
largely dissolved.** The raise was motivated by E8's ranking failure, where the
wrong skill won `response_text` at 1200. With function words no longer scored, a
consolidated library delivers the correct skill on both tasks **at the shipped
1200** (`bench/budget_sweep.py`), and `selector_check` puts its lowest stable
budget at 1100. Only the unconsolidated ten-skill pool still needs about 3000. So
consolidate, and keep the budget at 1200 unless a session measurement says
otherwise. The real install-and-inject path confirms this (`bench/real_path_check.py`,
4 of 4). No session can measure the effect on outcomes until a new trap exists.

### 3.2 What happens when ranking fails on a trap with no symptoms?

Unchanged from the last handoff, and still the one experiment that would
settle whether the novelty gate can be relaxed in the shipped distiller.

E8 showed the symptom path rescuing a prompt-path ranking failure 3 of 3, and
also showed that rescue is only available where anti-skills exist. Q1 showed
anti-skills are structurally impossible for a silent trap. Nobody has run
**ranking failure on a symptomless trap**, which is exactly where depth would
bite.

It is not runnable against the current pool.
`capped-scan-reports-unknown-not-absent` ranks **first on both** probe
prompts, so the silent trap's matched skill is never out-ranked. Making it
runnable needs either a third trap or payloads chosen to invert that ranking,
and **the ranking must be measured before the batch, not after** — the E8
spec's §2.2 table is the pattern.

Until it is run, treat "depth is safe" as established for loud traps only.

### 3.3 A size guard at save time — **DONE 2026-09-13**

`save_skill.validate()` now refuses a draft the selector could never inject.
An oversized skill used to save cleanly, index cleanly, and then be skipped on
every selection pass with nothing telling the author. Every distilled skill
costs **759–1192** tokens against a **1200** budget, so this was one bad draft
away from biting; E9's merges fit by drafting luck, not by design.

The cost is charged with `retrieve.injection_cost()` — one definition, now
reused by the prompt path (`retrieve.py`), the symptom path (`detect.py`) and
the guard, where the formula had previously been duplicated in two files and
could have drifted. It measures the **whole file including frontmatter**,
because that is what both selectors read off disk and charge for.

The guard uses the **shipped** `INJECT_BUDGET_TOKENS`, never
`SKILLFORGE_INJECT_BUDGET`: that env var is a bench-only runtime lever, and
letting it relax a save-time guard would persist skills that fit a batch's
raised budget and can never inject in production.

Two tests pin the boundary in both directions — oversized rejected, and
large-but-under-budget still saves. The second matters: a guard that rejected
every large skill would pass the first and still be wrong.

### 3.4 E4 is still blocked, and the graded scorer did not unblock it

E4 asks whether an irrelevant skill hurts **versus nothing**. It needs a task
whose control baseline is neither 0 nor 100%.

A previous revision argued the blocker was binary scoring and that a graded
rubric would give control partial credit. **That scorer was built and the
argument did not survive it.** The probe suite reproduces the binary
`resolved` verdict in 40 of 42 rows, 24 of 24 for E7, 18 of 18 for E8 and 18
of 18 for E9. Control does score off zero — 0.636 and 0.778 — but **no
artifact has ever scored below that floor**, so the room to fall is asserted,
not observed. The 2026-09-10 batch reads **0.852** for `response_text`
instead, because its control cell contains the single resolved run behind that
task's 1/6. Both are correct for their own batch and 0.778 is
the cleaner floor. Do not treat the two as a contradiction.

These two tasks are single-trap: a session either sees the trap or it does
not. **Do not build more probes for them.** E4 needs a genuinely mid-range
task.

**E11 (2026-09-13) suggests "mid-range" may be the wrong requirement.** Harm
cannot be measured on a floor task: a control at 0/21 has nowhere to fall, and
every trap ever chosen as a discriminator was chosen for exactly that property.
E11 measured two `repair`-mode tasks at **6/6 control with zero variance** —
the opposite property, maximum headroom to fall, and a baseline tight enough
that a drop of two or three runs is legible at n=6. Those two tasks are
candidate *harm* detectors even though E11 rejected them as benefit
discriminators.

This is a proposal and needs its own pre-registration. Its threat is specific:
a repair-mode session reads the failing tests, so an irrelevant skill has to be
disruptive enough to survive that signal before harm appears. A null would be
ambiguous between "no harm" and "the tests rescued it" — write that down before
the batch, not after. Nothing above in this section is superseded: the
leaky-stub warning and the re-derive-don't-quote rule still hold.

**E12 ran that proposal on 2026-09-13 and found no large harm.** Control,
relevant and irrelevant all scored 12/12, with the pre-registered caveat that
visible failing tests may have rescued the session. E4 is now answered for
repair mode at ceiling only. **Don't spend more sessions on harm.** It is the
third null after E6 and E10, and no author-mode task has the headroom to run the
other half. See E12 in `bench/RESULTS.md`.

**Control figures: re-derive them, do not quote them.** The "1/6 and 0/6"
carried in three specs cannot be reproduced from one consistent rule. E7's own
same-batch control is **0/6**, measured 2026-09-11, and that one is clean.

**Do not pool across `results-leaky-stub.jsonl`.** Its author-task rows are
3/3 *because that stub leaked the answer*. Pooling makes `response_text`
control look like 44% and makes E4 look unblocked. It is not.

### 3.5 The hot tier: 4 of 5 mechanisms still unevidenced

Delivery is confirmed (2026-09-08). Promotion order, the 1,500-token budget,
ranking and eviction have never been exercised against a model that could see
the result.

**Corrected 2026-09-16 — the blocker named here was wrong.** It was not that
"the force-hot lever takes a single exact name": `--plus-skill` already
installs N skills, and `--force-hot` is not a narrow version of what is needed
— it assigns `tier = "hot"` directly and its own comment says it "bypasses
kind, bucket, budget", so forcing two names would exercise none of the
machinery. The real blocker was **eligibility**: an installed skill lands
`unproven`, and `sync` gives `unproven` tier `warm`. `bench/run.py --seed-uses N`
now writes the ledger history a real skill earns and lets `sync` decide.

Also: this logic is **not** untested. `tests/test_sync.py` covers budget
overflow, promotion order, the unproven gate and eviction. What has never
happened is a *bench arm* reaching it.

Reading the code while building that lever found a real defect — the promoter
was non-monotonic in its budget, fixed 2026-09-16 (`bench/hot_check.py`, and
the Hot tier section of `bench/RESULTS.md`). An arm is now possible; E5's
null on delivery path is why it is not yet motivated.

### 3.6 `/consolidate` has never been run end to end against a real library

E9 tested the *output* of a consolidation, using merges produced by hand from
the proposal. The command's own propose-save-retire loop against the
operator's live library has not been exercised. `cmd_retire` fails closed on a
`keep` that is not in the index, which is the dangerous half, but the path is
untested in anger.

### 3.7 Hygiene

- **The branch is 8 commits ahead of `main` and of `origin/main`**, both at
  `e50b61c`. Nothing since the E9 pre-registration is pushed.
- `/tmp/skillforge-bench` holds the bench clones and their ledgers. The
  per-run ledgers are the **only** copy of delivery evidence for batches
  before 2026-09-09; rows from that date onward carry `injections` on the row
  itself.

---

### 3.8 Trap supply is the binding constraint

**Corrected 2026-09-16: there are TWO usable traps, not one.**

| task | control | with a good skill |
| --- | --- | --- |
| `sf-author-fingerprint-preexisting` | 0/28 lifetime | pilot 5/6 |
| `sf-author-verdict-from` | 0/23 lifetime | E15 variant drafts 18/18 |

E13 §6 read trap C as serving neither of its traps; that measured E13's own
drafts, not the task, and E15 then took the same task to 18/18. A task with a
zero floor that a good skill takes to ceiling is a working trap. `response_text`
is retired by E10; both repair-mode candidates were rejected by E11 at 6/6.

**The trap well is dry in this shape, and E16 is the evidence.** Of five
candidates ever screened by stubbing a function under its own docstring, three
resolved at ceiling (D, E, G), one floored at 1/6 (F) and one was admitted (C).
E16 spent 15 sessions for no new trap. `2026-09-16-e16-author-traps-design.md`
§1.1 records why each of the other 27 open fix commits fails the shape, so the
field is exhausted for this construction. More traps need a different
construction, not a longer commit list.

What E11 established about what to write:

- **Author mode only.** Repair mode hands the session three red assertions that
  describe the intended behaviour. What is left is reading comprehension, which
  a skill cannot improve because the information is already in the session.
- **Screen before use, and screen cheaply.** Control cells need no skill and no
  treatment arm. A candidate costs 6 sessions, about 6 minutes, and the RED
  pre-flight (`prepare()` + `score()`, no model) costs nothing at all.
- **Run a same-batch reference every time.** E10's break was caught only
  because a second task's control ran in the same batch and did not move; E11
  made that a numbered rule, and it is what licenses reading the result.
- **A non-zero floor rejects.** 1/13 was a warning this project read as noise
  for four batches.

New traps must be real review findings against code the model cannot have seen.
That constraint is weaker than it first looks: the cutoff is May 2026 and this
repository's entire history postdates it, so recency rules nothing out.

`bench/trap_candidates.py` (deterministic, 0 sessions) ranks the **48** fix
commits since 2026-08-09 that touch both `scripts/` and `tests/`, scoring for
author-mode shape: one source file, one or two functions touched, several new
tests, a docstring contract to stub against. **Twelve score 9 or better.** The
ranking puts both known-good traps inside its top ten — `22ddf37` at 5,
`ab4acfe` at 10 — which is the only evidence that its ordering means anything.

An earlier revision of this section said the supply "is not deep" because both
current bugs date from 2026-08-10. That was wrong: it mistook the date those two
bugs happen to carry for a constraint on which bugs are eligible.

---

## 4. Things not discoverable from the code

- **A refused session is not a result, and the code knows it.** `meta.json`
  records `session_ok`, `session_failed` outranks every other outcome, it is
  never probeable, and a refused draw is retryable. Rows with
  `session_ok: false` are **excluded from every cell** by rules pre-registered
  before any data existed. This fired on E6's first attempt and on E8's, and
  is why both are postponed rather than poisoned.
- **The test suite used to be polluted by the bench.** `bench/distill.py`
  exports `SKILLFORGE_*` process-wide without restoring, and `SKILLFORGE_LEDGER`
  beats `HOME`, so a sandboxed test could read a real batch's rows. Three test
  files also stub `sync._spawn_validation` at module scope and the capture
  order depends on alphabetical import. `tests/conftest.py` closes both. If
  you add a test file that stubs a `sync` internal, read that conftest first.
- **The tests must never invoke a model and must never mutate the operator's
  real library.** Stated in `bench/critique-calibration/README.md`. This repo
  has already shipped one fix for a suite that destroyed real state, and one
  for a test that truncated a real run's ledger to zero bytes.
- **The two injection budgets are independent.** `retrieve.py` carries 1200
  for the prompt path and `detect.py` carries its own 1200 for the symptom
  path. A spec section of mine claimed only one skill could ever inject; it
  was falsified by E8's data because it modelled only the prompt path.
- **`MAX_SKILLS = 3` never binds at today's budget.** The budget binds at one
  skill. That is why the count cap looks dead in the code.
- **Injection cost is the WHOLE file**, frontmatter included:
  `max(1, len(body) // 4)`. An early cost model of mine used the post-frontmatter
  body and was wrong by 250–300 tokens per skill.
- **The compiled index already carries `est_tokens`, using the identical
  formula, and both selectors ignore it.** They recompute from disk, which is
  correct — the body has to be read anyway to re-verify trust. But it means
  any look-ahead selector has a free price list available and does not need to
  read every candidate.
- **`consolidate.clusters()` never crosses scope.** My first derivation of
  E9's cluster table grouped trap B as one cluster of four; the shipped code
  finds three clusters. Corrected before any session ran. Do not re-derive
  cluster counts from a skill list by eye.
- **`verification.command` does not partition the library cleanly.** The
  `/consolidate` spec originally claimed it split the ten perfectly. It does
  not — one anti-skill points at a different test file. 7 of 10 in 2 clusters,
  3 unclustered, and the false negative is deliberate.
- **`verification.command` is optional for anti-skills.** `save_skill.py`
  requires it only for `kind: skill`. A blank is not a defect.
- **`bench/extract.py` has two parse rules that look wrong and are not.** The
  task is the **longest** matching id, and the arm head must **open** with
  `control` or `treatment` — distillation clones are deliberately unplaceable
  and return None. Both bugs were caught by checking against all 54
  pre-existing manifest entries, which still reproduce exactly.
- **`drift()` compares project entries for ONE root.** Comparing all of them
  reports drift on a clean batch, because every clone writes a transient
  `/tmp`-rooted entry.
- **Containment writes to the operator's real library and reverts.** A
  distilling session picks its own scope; `--scope global` lands in
  `Path.home()`. `trust.json` is user-global **regardless of scope**, so every
  save leaves a key and nothing else prunes it.
- **The register at the top of `bench/RESULTS.md` is the index.** It exists
  because confidently-stated claims in that file turned out to be wrong. I
  added another this session — the budget-derivation section named
  `retrieve.inject`, a function that does not exist; the loop is
  `retrieve.run_hook`. The first fix missed two copies, in RESULTS.md's E9
  section and `bench/rank_check.py`; both are now fixed. The E8 and E9 specs
  keep the wrong name as pre-registered record. **Re-derive from
  the files; do not describe them from memory.**
- **The evidence now fingerprints its environment — and it still would not have
  caught this.** Rows carry `env` (CLI build, every loaded plugin's sha) as of
  `8e0cf16`. It earns its place by making the next environment change visible at
  a glance instead of by transcript archaeology. It does not make model drift
  detectable: every field it records was identical across the batches where
  `response_text` control read 0/3 and 6/6. `model` stays a moving alias —
  `claude-opus-5` has no dated snapshot to pin to.
- **The SDD execution ledgers are gone.** `.superpowers/sdd/` is git-ignored
  and no longer exists in this worktree. The rulings made during
  `/consolidate`'s build survive only in the commit messages.

- **Scope matching compares paths as strings.** `save_skill.py` records a
  project root with symlinks resolved, but `retrieve.in_scope()` doesn't resolve
  anything. A caller that passes an unresolved `cwd` silently puts every project
  skill out of scope. Real sessions are fine, because Claude Code sends a
  physical `cwd` (E12's re-run under `/tmp` still logged 24/24 prompt
  injections). Any tool that calls the hook directly has to resolve its paths
  first, as `bench/real_path_check.py` does.

---

## 5. Where the work is

Branch `claude/e7-novelty-gate-bypass`, in the worktree at
`~/Developer/skill-forge/.claude/worktrees/main-parent-spec-status-9c1e7b`.
Eight commits ahead of `main` and `origin/main`, both at `e50b61c`. Run
everything from the worktree.

**777 tests passing. Tree clean.**

New or changed this session:

| File | What it does |
|---|---|
| `tests/conftest.py` | Environment restore and the real `_spawn_validation` capture. Fixes 103 failures |
| `bench/distill.py` | `--no-novelty-gate`, the lever E7 needed; segment and archive paths carry it |
| `bench/run.py` | `--plus-skill` is repeatable, so a whole library can be installed |
| `bench/extract.py` | Batch-labelled artifact extraction, so a new batch cannot overwrite Q1's evidence |
| `bench/regrade.py` | `--batch` selection over `graded.jsonl` |
| `scripts/consolidate.py` | Clustering, name inheritance, pattern union, propose, retire |
| `commands/consolidate.md` | The model half of `/consolidate` |
| `tests/test_consolidate.py` | 31 tests |
| `bench/rank_check.py` | Does consolidation fix E8's ranking? Deterministic, 0 sessions |
| `bench/budget_sweep.py` | What budget delivers a correct skill? Deterministic, 0 sessions |
| `bench/selector_check.py` | Which selector is monotone? Deterministic, 0 sessions |

Specs written this session, all pre-registered before their data:
`docs/superpowers/specs/2026-09-10-e7-novelty-gate-design.md`,
`2026-09-11-e8-library-depth-design.md`,
`2026-09-11-consolidate-design.md`,
`2026-09-11-e9-consolidation-design.md`. The `/consolidate` plan is at
`docs/superpowers/plans/2026-09-11-consolidate.md`.

Batch scripts are in git rather than `/tmp`: `bench/e7_phase2.sh`,
`bench/e8_batch.sh`, `bench/e9_batch.sh`.
