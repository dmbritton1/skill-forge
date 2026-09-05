# SkillForge — session handoff

Written 2026-09-05, at the end of the session that shipped `/stats` and the
promotion fix. Read this before touching anything; several things here are
not discoverable from the code.

---

## 1. Where things stand

**v0.2 is functionally complete.** Every item in §13's v0.2 list is built.
The single largest unbuilt subsystem is **§10 Maintainer** (`/consolidate`,
`/audit`, the compression pass, the meta-loop) — that section is essentially
v0.3 in full.

Three structural bugs were found and fixed this session. All three had the
same shape: *a mechanism that had never once fired in production, with green
tests.*

| Bug | Why it survived |
|---|---|
| The exit-code struggle trigger never fired | Replaying 1,561 real Bash calls produced zero struggles — the keys that failed twice never recovered, and the keys that recovered never failed twice |
| `bash_outcome` returned `None` on every call ever made | Its test fixture invented an `is_error` field that occurs in **zero** of 12,678 real payloads |
| `PostToolUse` never delivers failures | Nothing aggregated outcomes, so 100% NULL looked identical to "nobody used the library" |

**The loop closed for the first time during this session.** A verification
command logged `outcome='success'` — the first non-NULL outcome the ledger
has ever held — and one skill moved to `working`. That is the first promotion
in the project's history.

---

## 2. START HERE — four steps, then restart

Nothing built after Aug 28 runs until the plugin is reinstalled. Skipping
this means every observation you make is about stale code.

```bash
git checkout main && git merge --ff-only failure-detection
```

Then bump `.claude-plugin/plugin.json` to `0.2.2`, commit, and:

```bash
claude plugin marketplace update skillforge && claude plugin update skillforge
```

**Then fully quit and reopen Claude Code.** Not a new tab — the plugin root
is resolved at process start and baked into the registered hook commands.

**Verify the new session is actually on `0.2.2` before trusting any result:**
make one file edit, then check that `edits` grew. If it did not, the session
is still on the old plugin root and nothing else you observe means anything.

---

## 3. The verification protocol

Everything below is built, merged, and **has never run in a live session**.
This is the session that finds out whether the design works.

**Baseline as of this writing** — run `/skillforge:stats` first and compare:

```
verification outcomes: success=1, failure=0, unknown=3
buckets:               unproven=5, working=1
corrections=0  edits=1  drafts=0
```

**Test 1 — does failure detection work?** (the branch you are merging)

```bash
python3 tests/test_guard.py; exit 1
```

Before this branch that produced nothing at all. After it, `/skillforge:stats`
should show `failure=1`. That single number is the whole acceptance test.

**Test 2 — does capture work?** Do real work in this repo and **correct the
model when it is genuinely wrong**. Do not stage a correction and do not tell
it you are testing — if you say "I'm testing the correction trigger," it
writes a marker because you asked, and you have learned nothing. The trigger
needs 2+ file edits after the correction, then either 5 minutes or the session
ending. End the session to settle it, then check `corrections`.

**Test 3 — the original goal.** The thing that started this project: an
integration you had to troubleshoot for an hour, which should be one-shot the
next time. Every mechanism for that now exists. Whether it works is open.

`drafts` may stay empty even if capture works — a correction only nominates a
drafter when it clears the edit floor and settles. `corrections > 0` with
`drafts = 0` means the system is being appropriately conservative, not broken.

---

## 4. Landmines — the expensive things to rediscover

**The plugin cache is keyed on `plugin.json`'s version.**
`~/.claude/plugins/cache/skillforge/skillforge/<version>/`. The marketplace
source points at the working tree, which makes it *look* live. It is not. If
the version does not change, no amount of committing ships anything. This cost
a month of silent staleness.

**pytest is NOT installed.** Tests are plain `def test_*()` with an
assert-based `__main__` runner. Run `python3 tests/test_<name>.py`; exit 0 is
the pass signal. There are **two runner styles** — some files abort at the
first failure and print no `FAIL` line at all. Never read absence of "FAIL" as
proof; check the exit code.

**A test fixture that invents a payload shape is worse than no test.** The
`bash_outcome` bug survived months because three green tests fed it a field
the harness never sends. When testing against an external contract, verify the
shape against real data first.

**Assert the contract, not the implementation's strategy.** Documented in
`bench/RESULTS.md`, where a hidden test punished a *better* implementation
because it encoded the reference approach.

**`EnterWorktree` branches from `origin/main`, not local `main`.** Happened
three times. Fast-forward immediately after creating a worktree, before doing
any work.

**Run `sdd-workspace` AFTER entering the worktree**, or the ledger lands in the
main repo while briefs and reports land in the worktree, and reviewers report
the ledger as missing.

**Hooks must exit 0 always and print nothing on stdout on failure.** stdout is
the harness's control channel. `sync.py` is the deliberate exception — its
stdout *is* read as context. A `try` block in a hook is load-bearing for the
exit-0 contract, not just for error reporting; moving code across one has
broken this twice.

**Never `git stash`** — the stash stack is shared across worktrees.

---

## 5. Measured facts worth not re-deriving

Real Bash `tool_response` shapes, from 12,678 results across 1,109
transcripts:

| shape | count | means |
|---|---|---|
| `dict` (`stdout`/`stderr`/`interrupted`/…) | 11,729 | success |
| `str` `^Error: Exit code N` | 594 | genuine failure |
| `str`, anything else | 356 | harness refused / blocked / user rejected |

`is_error` exists on the transcript's `tool_result` block but **not** in the
hook's `tool_response`. Different objects; the old code read the one lacking
it.

That 356 is why classification is content-based rather than trusting the event
name: promotion gates on `failure_sessions = 0`, so **one false failure is
permanent**. Unknown is honest; wrong is corrosive.

Only four hook events add stdout to context: `UserPromptSubmit`,
`UserPromptExpansion`, `SessionStart`, `PostModelSwitch`. `SessionStart`
re-fires with `source: "compact"` after every compaction, which is how the
correction note repairs itself in long sessions.

---

## 6. Open items, ranked

1. **Verify the loop live** (§3 above). Highest value by far — every mechanism
   is built and unproven, and one session of real use answers more than any
   feature would.
2. **Deferred minors from `/stats`**, all small: `_bases()`'s project-store
   branch has zero test coverage (the sandbox sets `HOME` and `cwd` to the same
   dir, so the branch that matters in production never fires in tests);
   `COST_RE` is safe only because `## Cost of rediscovery` is the last section
   of the anti-skill template; `r["name"]` vs `r.get(key)` inconsistency in
   `stats.py`.
3. **§10 Maintainer / v0.3** — `/consolidate`, `/audit`, compression with
   bucket demotion, preference capture, the meta-loop. Large, and better
   scoped once real usage data exists.
4. **Housekeeping**: `origin/claude/project-status-roadmap-4c408a` is redundant
   (its commits are in `main`); two other branches are checked out in worktrees
   belonging to other sessions — leave those alone.

`/stats` itself is now the instrument for deciding what to build next. Prefer
reading it over guessing.
