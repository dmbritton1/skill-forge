# SkillForge — session handoff

Written 2026-09-06 (E1, project-keyed ledger), revised 2026-09-08 at the end
of the session that ran E5 and shipped 0.2.5. Read this before touching
anything; several things here are not discoverable from the code.

Supersedes the 2026-09-05 handoff (git history has it). Its "START HERE" is
done: `failure-detection` merged, 0.2.2 shipped. §3's E5 item is done too —
the result and what it changed are in §1 and §3.1.

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

That same cell was re-measured on 09-08 and came back **4/6** (E5's arm W).
Nothing changed between them but the batch. Treat 6/6 as one draw from a wide
distribution, not as the number.

**E1's first batch was invalid and is kept on purpose.** It scored the
umbrella 1/6 and would have killed `/consolidate`. It was measuring `kind:`
rather than generalization: the umbrella was a `kind: skill` while both
comparators are `kind: antiskill`, and that one difference carried delivery
tier, verification eligibility, and run independence with it. Both batches are
in `results.jsonl`, told apart by the store path in `skill_note`
(`skills/` = invalid, `antiskills/` = valid).

Landed 2026-09-06:

| Change | Commit |
|---|---|
| Benchmark isolated from the real library; model pinned | `c767d4a` |
| Survival stat counted save *rows*, not skills (read 20%, truth 100%) | `1ba440b` |
| Umbrella re-authored as an anti-skill; per-run ledger | `3968281` |
| E1 write-up and data | `9eabc7e` |
| Bump to 0.2.3 | `94a4dca` |

**E5 is answered, and it found something bigger than it was looking for.**
The same anti-skill delivered as standing native context scored 5/6; delivered
by symptom injection, 4/6 re-measured (6/6 when E1 measured it); control 0/6.
Two measurements of the *same* arm differ by more than the arms differ, so at
n=3 the content carries the effect and no ranking between delivery paths is
claimable. `/consolidate` is not constrained by delivery.

**The hot tier had never delivered anything, to anyone, ever.** `sync.py`
materialized to `.claude/skills/skillforge-hot/<name>/SKILL.md`. Claude Code
scans exactly ONE level under `.claude/skills`, so the loader looked for
`skillforge-hot/SKILL.md`, found nothing, and skipped the directory. Every
skill ever promoted to hot was invisible to the model, from the first release
through 0.2.4. Nothing caught it: the tier logs no `injection` row so there was
no signal to miss, and every test in the repo plus §312 of the architecture doc
asserted the same wrong path. Fixed in **0.2.5** —
`.claude/skills/skillforge-<name>/SKILL.md`, with the eviction sweep scoped to
the `skillforge-` prefix because it now shares a directory with the user's own
hand-written skills. The legacy `skillforge-hot/` dir is swept on first sync;
no migration step.

**Running the test suite inside a project deleted that project's hot skills.**
`save_skill.py`'s `--project-root` defaults to `"."` and `main()` syncs that
root, so a save from any directory treats cwd as a project. The suite sandboxed
`HOME` but not cwd, so `sync()` judged the real cwd's store against a trust
store in the sandbox, found nothing trusted, and evicted. Also fixed in 0.2.5
(`in_sandbox` chdirs into the sandbox in every test file that has one).

Landed 2026-09-08:

| Change | Commit |
|---|---|
| E5 force-hot lever, write-up, two bench harness fixes | `660e047` |
| Hot path fix, test-suite cwd isolation, bump to 0.2.5 | `b35f756` |

One phantom row was deleted from the live ledger: a `save` for
`matcher-input-traps`, a bench-only skill, written by `install_skill()` before
isolation existed. Backup at `~/.claude/skillforge/ledger.db.bak-20260906T001637`.

---

## 2. START HERE

**0.2.5 was shipped on a branch, not merged.** Unlike previous revisions of
this handoff, do not assume the install is current — check, then verify. One
command, and if it prints an error the rest of your session is fiction:

```bash
python3 ~/.claude/plugins/cache/skillforge/skillforge/0.2.5/scripts/sync.py --project-root "$PWD"
```

If that path does not exist, **0.2.5 is not installed** and the hot-tier fix
is not live: merge and `claude plugin update`. The cache is keyed by version,
so the presence of the directory is the check. A plugin update does not affect
the running session either way — `CLAUDE_PLUGIN_ROOT` resolves at session
start, so restart or you are observing old code.

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

**A hole opened when the install was fixed, and it was worse than this.**
Both live skills went `hot`, and hot skills log no `injection` row — so the one
production relevance metric went dark for exactly the skills that earned
promotion. What the 09-06 session could not know: those skills were not being
delivered at all (§1). The metric was not merely blind, it was blind to a tier
that did nothing. Both facts are now true at once: 0.2.5 makes hot deliver, and
nothing still records that it happened. `stats` lists "hot-tier churn" as
unmeasured; hot delivery itself is equally unrecorded.

---

## 3. Next steps, in priority order

### 3.1 The hot tier is live for the first time and nothing in it is validated

Every number this project has recorded about hot skills was collected while
the tier delivered nothing (§1). That makes the whole hot-tier design
unevidenced rather than merely under-measured: `confidence × recent usage`
ranking, the 1,500-token budget, promotion order, eviction pressure. None of it
has ever been exercised against a model that could see the result.

**Cheapest first move, and the harness already exists.** E5's arm H ran through
the force-hot lever's own flat directory, which differs from what 0.2.5 ships
only in the directory's *name*. Six runs re-confirms delivery under the shipped
path:

```bash
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-fingerprint-preexisting-umbrella
```

Verify the arm before scoring, the same three assertions as E5 — but at the new
path:

- `<clone>/.claude/skills/skillforge-matcher-input-traps/SKILL.md` exists;
- `~/.claude/skillforge/triggers.json` has **no** `symptoms` entry for it;
- `index.json` shows `tier: hot`.

Then read the per-run ledgers: arm H must show **zero** `injection` rows. A
`marker` row on a skill with no injection is itself proof of hot delivery —
`reconcile._credit_markers` credits an uninjected skill only when `index.json`
says `tier: hot`.

**Second-order, and it matters now in a way it did not before.** A hot skill's
marker credit depends on `index.json` saying `tier: hot` at Stop time, and
`index.json` is user-global and last-writer-wins — any session anywhere
rewrites it. That leak was harmless while nothing was hot. It is now the only
thing standing between a hot skill and its one usage signal.

**Do not spend six more sessions ranking hot against warm.** E5 already
established that two measurements of one arm span 6/6 to 4/6. This design
cannot resolve a difference smaller than that, and more runs at n=3 buy
nothing. If the hot tier needs a verdict beyond "it delivers", it needs a
different measurement, not a bigger one.

### 3.2 Build `/consolidate` (v0.3, §10 Maintainer)

Fully unblocked. E1 cleared consolidation; E5 removed the second constraint by
showing the delivery path does not decide the effect, so the emitted form is
not forced.

Three caveats belong in its design doc:

- The evidence covers **two** trap classes. Where the compression curve bends
  past two is untested, and testing it is not cheap: a third class needs a new
  trap *and* a new authoring task, not just a third skill.
- An authoring body-cap is "reasonable" on this evidence, but no number in it
  is derived from anything measured. Pick one and say it is a guess.
- Emit **anti-skills** as the default. Not because E5 forces it — it does not —
  but because that is the path with two independent measurements above control,
  and it is the delivery mechanism with production history. Hot delivery is
  two days old.

### 3.3 E4 is blocked on a task that does not exist, not on the traps

Unchanged by E5. E4 asks whether injecting an irrelevant skill actively
*hurts*. It cannot run on the current traps: control already scores 0/6 there,
scoring is binary, and there is no room to fall.

The next step is still cheap — measure the control baseline of the two
repair-mode tasks that have never been run:

```bash
python3 bench/run.py --arm control --runs 3 --task sf-escaping-breaks-symptom-match
python3 bench/run.py --arm control --runs 3 --task sf-truncation-reports-absent
```

**Predict a ceiling, not a floor.** FAIL_TO_PASS repair tasks hand over the
answer — the red assertion names the exact condition, and control resolved 4/4
on this repo's own post-cutoff bugs. If these two land at or near 3/3, E4 needs
an **authoring** task where control succeeds *sometimes*. No such task exists.
Building one is design work, not a run, and it is the real blocker.

Do not run `sf-author-*-irrelevant` until that exists. `arrow-tzinfo-string-trap`
is the payload for that arm and has no task of its own.

### 3.4 Hygiene, whenever

- **`main` is 91 commits ahead of `origin/main`** and has never been pushed.
  It was 61 at the 09-06 revision.
- Old plugin caches `0.2.0`–`0.2.4` are on disk under
  `~/.claude/plugins/cache/skillforge/skillforge/`.
- `scripts/ledger.py:564` says the paired injection-to-use figure was `22%`;
  `cc9859a`'s own commit message and §2b say `26%`. Same commit, two numbers.
- `index.json` is user-global and last-writer-wins (see §3.1 — this is no
  longer only a tidiness item).
- Bench sessions inherit the operator's **full plugin set** — ponytail and
  superpowers included. Constant across arms, so contrasts hold, but absolute
  numbers are model-plus-plugins. Isolate before quoting a figure externally.
- The survival bug (`by_type["save"]` counting rows where the metric wanted
  entities) suggests a quick audit of the other stats for the same shape.
- `/tmp/skillforge-bench` is currently empty; it accumulates a clone plus a
  ledger per run and is never cleaned, so it will grow again.

---

## 4. Things not discoverable from the code

- **Claude Code scans exactly ONE level under `.claude/skills`.** A skill must
  sit at `.claude/skills/<dir>/SKILL.md`. Nest it one deeper and it is silently
  skipped — no error, no log, nothing. This cost the hot tier its entire
  existence (§1). The *directory* name is what the model sees as the skill's
  name, not the frontmatter `name:`.
- **`save_skill.py --project-root` defaults to `"."`**, and `main()` syncs that
  root — so a save run from any directory treats the current working directory
  as a project, reads its store, and evicts its native copies. This is why the
  test suite used to delete a project's hot skills, and it is a live sharp edge
  for anything that shells out to `save_skill.py`.
- **A `marker` row on a skill with no `injection` row proves hot delivery.**
  `reconcile._credit_markers` credits an uninjected skill only when
  `index.json` says `tier: hot`. It is the only positive delivery evidence the
  hot tier produces, and it is hostage to a user-global file (§3.1).
- **Both E5 arms pass `--arm treatment`.** The clone and per-run ledger paths
  used to collide, and the second batch silently overwrote the first's
  evidence. `--force-hot` now puts `-hot` in the path. If you add a third arm,
  give it its own path segment or you will lose a batch and not notice.
- **The bench per-run ledger lives OUTSIDE the clone**, so `prepare()`'s rmtree
  never cleared it and a re-run of the same task/arm/run index read the
  previous batch's rows as its own. `one()` now deletes it first. E5's first
  pass read E1's injections as evidence about its own sessions before this was
  found.
- **`skill_note` in `results.jsonl` is not a delivery record.** It reports
  `indexed: warm tier` for a forced-hot row, because `save_skill._warm_reason`
  tests a path the lever does not write. The ledger is the record.
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

## 5. Reproducing the numbers

```bash
cd /Users/dwightbritton/Developer/skill-forge
python3 bench/run.py --check      # expect: config ok: 10 task(s)

# E1, umbrella arm (the valid one)
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting-umbrella

# E1, matched arm (ran 09-05, before the umbrella repair -- same model, not same batch)
python3 bench/run.py --arm treatment --runs 3 --task sf-author-response-text
python3 bench/run.py --arm treatment --runs 3 --task sf-author-fingerprint-preexisting

# E5 arm H -- standing native context, symptoms suppressed. --force-hot sets
# SKILLFORGE_FORCE_HOT per run the way SKILLFORGE_LEDGER is set: exact name
# match or inert, and it does BOTH gates -- forces the tier and materializes,
# AND drops the skill's symptoms from triggers.json. Only the first would
# deliver by two paths at once and measure nothing.
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-response-text-umbrella
python3 bench/run.py --arm treatment --runs 3 --force-hot --task sf-author-fingerprint-preexisting-umbrella
```

E5's rows in `results.jsonl` carry `"delivery": "hot"|"warm"`; E1's rows have no
such key. Three same-day batches ran `--arm treatment` on the same two tasks and
only the timestamp tells them apart — 11:17-11:18 is arm H against the
undeliverable nested path (**invalid**, kept on purpose), 11:30-11:40 is arm H
valid, 11:41-11:47 is arm W re-run. Full write-up in `bench/RESULTS.md`.

Each task-arm-run is a full agentic session with a 900s timeout under
`--permission-mode bypassPermissions`. Twelve sessions took 13 minutes.
Results append to `bench/results.jsonl`; every row now carries `model`.

A run that errors prints `ERROR` for that arm and continues to the next, so
read the console, not only the JSONL.
