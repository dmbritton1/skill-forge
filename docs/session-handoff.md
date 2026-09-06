# SkillForge — session handoff

Written 2026-09-06, at the end of the session that merged the project-keyed
ledger to `main` and ran E1. Read this before touching anything; several
things here are not discoverable from the code.

Supersedes the 2026-09-05 handoff (git history has it). Its "START HERE" is
done: `failure-detection` merged, 0.2.2 shipped.

---

## 1. Where things stand

**The install was broken for a week and is now fixed.** The live ledger had
been migrated to schema v4 by an unmerged branch while the installed plugin
still ran v3 code, so every confidence read died on `no such column:
success_sessions`. `confidence()` catches that and returns `{}` — which reads
as "every skill unproven" — so the hot tier was empty and no skill could be
promoted, silently, for as long as the mismatch stood. Merged and shipped as
**0.2.3**.

**E1 is answered: consolidation is safe.** One anti-skill carrying both trap
classes scored **6/6**, identical to two anti-skills each carrying one. See
`bench/RESULTS.md` for the full write-up. This was the single item the rest of
the roadmap waited on — **v0.3 `/consolidate` is unblocked**.

**E1's first batch was invalid and is kept on purpose.** It scored the
umbrella 1/6 and would have killed `/consolidate`. It was measuring `kind:`
rather than generalization: the umbrella was a `kind: skill` while both
comparators are `kind: antiskill`, and that one difference carried delivery
tier, verification eligibility, and run independence with it. Both batches are
in `results.jsonl`, told apart by the store path in `skill_note`
(`skills/` = invalid, `antiskills/` = valid).

Also landed this session:

| Change | Commit |
|---|---|
| Benchmark isolated from the real library; model pinned | `c767d4a` |
| Survival stat counted save *rows*, not skills (read 20%, truth 100%) | `1ba440b` |
| Umbrella re-authored as an anti-skill; per-run ledger | `3968281` |
| E1 write-up and data | `9eabc7e` |
| Bump to 0.2.3 | `94a4dca` |

One phantom row was deleted from the live ledger: a `save` for
`matcher-input-traps`, a bench-only skill, written by `install_skill()` before
isolation existed. Backup at `~/.claude/skillforge/ledger.db.bak-20260906T001637`.

---

## 2. START HERE

The install is already correct as of this writing. Verify rather than assume —
one command, and if it prints an error the rest of your session is fiction:

```bash
python3 ~/.claude/plugins/cache/skillforge/skillforge/0.2.4/scripts/sync.py --project-root "$PWD"
```

Silence (plus the usual correction-logging line) is success. `skillforge:
confidence read failed:` means the code and the ledger schema have diverged
again — check `SCHEMA_VERSION` in the installed `scripts/ledger.py` against
`select value from meta where key='schema_version'` in
`~/.claude/skillforge/ledger.db`.

Expect existing skills to read `unproven` on organic evidence. That is
correct, not a regression: corroboration is now keyed on **project**, and
every pre-existing event row has `project = NULL`, so past successes cannot
say where they happened. They still show `trusted` in the index because Tier A
executable validation carries them. Organic corroboration rebuilds as new
project-tagged events land.

---

## 2b. Do not trust a ratio out of `stats.py` without checking it

`injection-to-use` reported **93%**. Paired per session it is **26%**. It was
computing `sum(detections) / count(injections)`: a session that ran one
verification command eight times counted as eight uses, while 21 injections
followed by nothing contributed only to the denominator. Fixed in `cc9859a`.

That is the **third** instance of this defect class here, after `bash_outcome`
and the survival stat. Before quoting any ratio from `stats.py`, check that
its numerator and denominator count the same kind of thing.

What the production numbers actually say, post-fix:

- **Delivery works.** 15 of 16 sessions got an injection; 27 across the
  library's life.
- **Relevance is mediocre and now honestly reported.** 6 of 23 injected
  sessions showed any same-session use.
- **The marker protocol is barely alive.** 1 of 16 sessions logged a marker.
  Verification-command runs are carrying the usage signal instead, and those
  fire whether or not the skill influenced anything.
- **Helpfulness is not measured and production cannot measure it.**
  `outcome='success'` means a verification command exited 0. There is no
  counterfactual anywhere in the telemetry. The only causal evidence in the
  project is the bench.
- **Recall is unmeasurable.** Nothing records a session where a skill should
  have fired and did not.

**A hole opened when the install was fixed.** Both live skills are now `hot`,
and hot skills log no `injection` row — so the one production relevance metric
goes dark precisely for the skills that earned promotion. `stats` already
lists "hot-tier churn" as unmeasured. Nothing records hot delivery at all.

---

## 3. Next steps, in priority order

### 3.1 E5 — is the effect delivery, or content? (6 sessions, do this first)

**The finding that raises it.** The same knowledge, same words, scored
**1/6** as a description-triggered `kind: skill` delivered hot, and **6/6** as
a symptom-triggered anti-skill delivered warm. That is a bigger delta than
anything E1 set out to measure, and it is currently a hypothesis, not a
finding — the skill version also differed in section structure and in
confidence trajectory, so it is still multi-variable.

**Why it goes before `/consolidate`.** If delivery is what carries the effect,
it decides what `/consolidate` should *emit*. Consolidating a cluster into a
`kind: skill` would be building the losing arm of an experiment nobody ran.
Six sessions now is cheaper than rewriting the feature later.

It also puts a question mark over the **hot tier itself**, which is core
architecture rather than a v0.3 feature. If standing native context does not
reach the model at the moment trap knowledge matters, the hot tier's whole
value proposition needs re-examining.

**Design — hold everything constant except the delivery path.**

| Arm | Delivery | Sessions |
|---|---|---|
| W (warm) | symptom-triggered injection — *reuse today's 6/6* | 0 new |
| H (hot) | materialized into native standing context, symptoms suppressed | 6 |
| control | no skill — reuse the pilot's 0/6 | 0 new |

Both arms use **the same file**: `bench/skills/matcher-input-traps.md`, the
umbrella anti-skill, unchanged. Same text, same kind, same tasks
(`sf-author-response-text-umbrella`, `sf-author-fingerprint-preexisting-umbrella`),
three runs each.

Arm W is reusable rather than re-run because the model is now pinned and
recorded (`claude-opus-5` on every row), and today's valid batch already ran
under the current harness — `3968281` landed the per-run ledger *and* the
anti-skill re-authoring together, before that batch. If you change anything in
`bench/run.py` before running E5, re-run arm W too.

**Prerequisite: a force-hot lever. There is no way to do this today.** Two
gates keep an anti-skill warm, and E5 needs both bypassed for arm H only:

1. `scripts/sync.py` — anti-skills are pinned warm before the bucket check
   even runs:
   `if s["kind"] == "antiskill": s["tier"] = "warm"; continue`.
   `HOT_ELIGIBLE = ("trusted", "working")` also gates it, and a fresh
   per-run ledger makes every skill `unproven`.
2. `scripts/sync.py::_write_triggers` compiles symptoms for **every**
   anti-skill regardless of tier. Force materialization alone and the skill
   arrives by *both* paths at once, which measures nothing.

So the lever must do two things: force the skill into the hot tier and
materialize it, **and** drop its entries from `triggers.json["symptoms"]`.
Something like `SKILLFORGE_FORCE_HOT=<name>` honored at both points, set by
`run.py` per run the way `SKILLFORGE_LEDGER` already is. Roughly four lines.
It is test-only scaffolding — mark it as such, and make it refuse to do
anything unless the name matches exactly.

**Verify the arm before spending sessions on it.** Hot skills log no
`injection` row (the harness injects them from the native directory and
SkillForge never sees it), so the delivery check that validated E1 does not
work here. Instead assert, in one run, before scoring:

- `<clone>/.claude/skills/skillforge-hot/matcher-input-traps/SKILL.md` exists;
- `~/.claude/skillforge/triggers.json` has **no** `symptoms` entry for it;
- `index.json` shows `tier: hot`.

Then the usage signal is the `marker` detection, which works in both arms.

**How to read it:**

- **Hot ≈ 6/6.** Delivery does not carry the effect. The invalid batch's 1/6
  came from something else — section structure, or the auto-promotion
  artifact. The hot tier is vindicated and `/consolidate` is unconstrained.
- **Hot ≈ 1/6.** Delivery *is* the effect. `/consolidate` must emit
  anti-skills, and the hot tier needs a serious re-think for trap-shaped
  knowledge.
- **Between.** Partial. Report the split per trap; two traps at n=3 cannot
  resolve much more than direction.

**Known limit going in:** the hot body is not byte-identical to the warm one.
`sync.py` appends a modified `MARKER_NOTE` to the materialized copy ("this
skill" rather than "a skill above"). That difference is inherent to hot
delivery, so it is part of the treatment rather than a confound — but say so
in the write-up rather than letting a reader find it.

### 3.2 Unblock E4 — measure first, and expect the opposite problem

E4 asks whether injecting an irrelevant skill actively *hurts*. It cannot run
on the current traps: control already scores 0/6 there, scoring is binary, and
there is no room to fall.

The next step is cheap — measure the control baseline of the two repair-mode
tasks that have never been run:

```bash
python3 bench/run.py --arm control --runs 3 --task sf-escaping-breaks-symptom-match
python3 bench/run.py --arm control --runs 3 --task sf-truncation-reports-absent
```

**Predict a ceiling, not a floor.** The pilot already established that
FAIL_TO_PASS repair tasks hand over the answer — the red assertion names the
exact condition, and control resolved 4/4 on this repo's own post-cutoff bugs.
If these two land at or near 3/3, E4 is not merely blocked on *these* tasks;
it needs an **authoring** task where control succeeds *sometimes* — partial
baseline, neither floor nor ceiling. No such task exists. Building one is
design work, not a run, and it is the real blocker behind E4.

Do not run `sf-author-*-irrelevant` until that exists. `arrow-tzinfo-string-trap`
is the payload for that arm and has no task of its own.

### 3.3 Build `/consolidate` (v0.3, §10 Maintainer)

E1 cleared it. Two caveats belong in its design doc:

- The evidence covers **two** trap classes. Where the compression curve bends
  past two is untested, and testing it is not cheap: a third class needs a new
  trap *and* a new authoring task, not just a third skill.
- An authoring body-cap is "reasonable" on this evidence, but no number in it
  is derived from anything measured. Pick one and say it is a guess.

If E5 comes back hot ≈ 1/6, add a third: `/consolidate` emits anti-skills.

### 3.4 Hygiene, whenever

- `/tmp/skillforge-bench` accumulates a clone plus a ledger per run, never
  cleaned. Harmless, in `/tmp`, but it grows.
- Bench sessions inherit the operator's **full plugin set** — ponytail and
  superpowers included. Constant across arms, so contrasts hold, but absolute
  numbers are model-plus-plugins. Isolate before quoting a figure externally.
- `index.json` is user-global and last-writer-wins: any session anywhere
  rewrites it, including a one-off `claude -p` in `/tmp`. Derived and
  self-healing, so the cost is transient — but it is the same class of leak the
  ledger had, and it is not isolated.
- The survival bug (`by_type["save"]` counting rows where the metric wanted
  entities) suggests a quick audit of the other stats for the same shape.
- Old plugin caches `0.2.0`–`0.2.2` are still on disk under
  `~/.claude/plugins/cache/skillforge/skillforge/`.
- `main` is **61 commits ahead of `origin/main`** and has never been pushed.

---

## 4. Things not discoverable from the code

- **`bench/run.py` clones live outside the repo now** (`/tmp/skillforge-bench`,
  override `SKILLFORGE_BENCH_WORK`). This is not tidiness. A clone under
  `bench/work/` sits inside a project whose skill store `retrieve.in_scope()`
  accepts — `cwd.startswith(root)` — so the real library was retrievable inside
  every bench session, both arms.
- **`SKILLFORGE_LEDGER` is per run, not per batch.** Per batch let run 1's
  verification success promote a skill to `working`, so run 2 received it hot
  while run 1 had it warm. A cell was a sequence that learns, not three trials.
- **A skill and an anti-skill are never a clean A/B.** Kind, delivery tier, and
  verification eligibility all ride along on `kind:`. This cost E1 twelve
  sessions; it is written up in `bench/RESULTS.md` as the third harness lesson
  alongside the pilot's two.
- **A skill whose `verification.command` is the task's own `test_cmd` grades
  itself.** The invalid umbrella declared `python3 tests/test_detect.py`, which
  *is* `test_cmd` for `sf-author-response-text-umbrella`, so scoring the task
  logged three verification successes and promoted it mid-experiment.
- **`claude plugin update` is the refresh path**, and the cache is keyed by
  version — ship a bump with any change you intend to actually run, or you are
  overwriting a directory in place and testing something ambiguous.
- **A plugin update does not affect the running session.** `CLAUDE_PLUGIN_ROOT`
  resolves at session start. Restart, or you are observing old code.

---

## 5. Reproducing today's numbers

```bash
cd /Users/dwightbritton/Developer/skill-forge
python3 bench/run.py --check      # expect: config ok: 10 task(s)

# E1, umbrella arm (the valid one)
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-umbrella

# E1, matched arm (ran 09-05, before the umbrella repair -- same model, not same batch)
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting
```

Each task-arm-run is a full agentic session with a 900s timeout under
`--permission-mode bypassPermissions`. Twelve sessions took 13 minutes.
Results append to `bench/results.jsonl`; every row now carries `model`.

A run that errors prints `ERROR` for that arm and continues to the next, so
read the console, not only the JSONL.
