# Bench sandbox and transcript audit

**Status:** design agreed in brainstorming on 2026-09-14. No sandboxed session
has run yet. Everything below is on by default for every batch.

## Why

Bench sessions run `claude -p --permission-mode bypassPermissions` with the
user's full file access. Nothing stops a session reading:

- the checkout, including `bench/` with its hidden tests, results and drafts;
- other clones under `/tmp/skillforge-bench`, and the hidden-test caches;
- other sessions' transcripts under `~/.claude/projects`.

No author session is known to have done so. Distill sessions have read
`scripts/save_skill.py` and `scripts/validate.py`. Bench project memory folders
were checked on 2026-09-14: 171 exist, all empty.

A sandbox cannot close everything. The plugin's hooks import `validate.py` and
`retrieve.py`, which contain the fixed functions of the bench's traps, so the
plugin's `scripts/` must stay readable. An audit of each session's transcript
covers that gap.

## 1. Approach

Every session is wrapped in macOS `sandbox-exec`. Approaches considered and
rejected:

- **Permission deny rules via `--settings`.** Sessions bypass permissions, and
  `Bash` can `cat` a denied path, so deny rules only deter.
- **A container or a separate macOS user.** Strongest, but 1 to 2 days of work
  and a separate login token. Out of proportion for the bench.

Known costs: `sandbox-exec` is deprecated, and the profile may need tuning
rounds. Section 5's checks exist to find those before a batch spends sessions.

## 2. The sandbox

### 2.1 Sessions load a snapshot, never the checkout

`tasks.json` sets `plugin_dir` to `{root}`, the checkout, so allowing the plugin
directory would allow `bench/`. With the sandbox on:

- when `plugin_dir` is not a snapshot (it has no `.bench-plugin-ref`), `run.py`
  and `distill.py` call the existing `snapshot_plugin("HEAD", WORK /
  "plugin-<sha7>")` once per batch and load that;
- they refuse to start if `plugin_commit()` of the checkout ends in `+dirty`,
  because a snapshot of `HEAD` would not be the code on disk;
- an explicit `--plugin-dir` must already be a snapshot, or the batch refuses.

Every sandboxed row therefore records `plugin_commit` as `archive:<sha>`.

### 2.2 One launch function

`bench/run.py` gains `sandboxed(cmd, dest, plugin_dir, session_id)`. It writes
the profile for this session and returns the command wrapped as
`sandbox-exec -f <profile> sh -c <cmd>`. `run_session` and the session launch in
`distill.py::one` both go through it. The sandbox applies to every child the
session starts, including hooks and `python3` scripts.

### 2.3 The profile

The profile is `(allow default)` followed by `(deny file-read* file-write* ...)`
rules for these locations, so a session can neither read nor alter them:

| denied | except |
| --- | --- |
| the user's `Developer/` tree (the repo's parent) | nothing |
| `WORK` (`/tmp/skillforge-bench`, both the `/tmp` and `/private/tmp` spellings) | this session's clone `dest`, its `dest.ledger.db*` files, and the snapshot `plugin_dir` |
| `~/.claude/projects` | this session's own project folder (the clone path with each non-alphanumeric character replaced by `-`) |

Hidden-test caches live under `WORK` and are denied by the second row. The
exceptions allow both reads and writes, so the session can write its clone, its
ledger and its transcript. Everything else remains allowed:

- the CLI's own files under `~/.claude` and `~/.nvm`;
- the Keychain;
- the network;
- scratch space under `/tmp`;
- the global skill store.

The profile text is built by one pure function, `sandbox_profile(dest,
plugin_dir, home, work, repo_parent)`, so tests can read it without starting
anything.

### 2.4 What each row records

- `sandbox`: `true`, or `false` under `--no-sandbox`;
- `sandbox_profile`: the sha256 of the profile template, with its paths left as
  placeholders;
- `session_id`, from section 3.

`--no-sandbox` exists for debugging only. Section 4 voids its rows, and no batch
script passes it.

## 3. The audit

### 3.1 Finding the transcript

`run.py` and `distill.py` generate a `uuid4` per session, pass `--session-id
<uuid>`, and record it as `session_id`. After the session exits, the audit globs
`~/.claude/projects/*/<uuid>.jsonl`. If no file matches, the verdict is
`missing`.

### 3.2 What is checked

`bench/audit.py` exposes `audit_transcript(path, dest, plugin_dir, work, repo)`.
It walks every `tool_use` block and collects:

- the `file_path` or `path` argument of `Read`, `Grep`, `Glob`, `Edit` and
  `Write`;
- every absolute path or `~` path in the `command` of a `Bash` call.

It also records whether the matching `tool_result` contains
`Operation not permitted`.

Each path gets a label:

- **ok:**
  - inside `dest`, the run's ledger, or `/tmp` scratch space outside `WORK`;
  - a path under `plugin_dir/scripts/` that a `Bash` command runs as a program,
    i.e. the path directly follows `python3` or `python`.
- **leak:**
  - any path under `plugin_dir/scripts/` read as text: `Read` or `Grep`, or a
    `Bash` command that does not run it as a program (`cat`, `grep`, `sed`,
    `head`, `less` and similar);
  - any path in the repo checkout, in `WORK` outside `dest`, or in
    `~/.claude/projects`.
- **blocked:** a would-be leak whose result says `Operation not permitted`. The
  sandbox stopped it, so it is recorded but is not a leak.

### 3.3 The verdict

`audit` on the row is `{"verdict": "clean" | "leak" | "missing", "hits": [...]}`.

- `hits` lists at most the first 10 non-ok paths, each as `{tool, path, label}`.
- The verdict is `leak` if any hit is labelled leak, and `clean` otherwise;
  blocked hits alone leave it clean.
- The audit never raises. If it cannot parse the transcript, the verdict is
  `missing`.

### 3.4 Distill sessions

Distill sessions are expected to run, and have historically read,
`save_skill.py` and `validate.py`. Their audit is recorded in `meta.json` and
never voids the draft. A draft is `tainted` for its trap when a leak hit reads
the file holding that trap's fixed function:

| trap | file |
| --- | --- |
| C | `scripts/validate.py` |
| D | `scripts/draft.py` |
| E | `scripts/save_skill.py` |

The mapping lives next to `distill.TRAPS`.

## 4. How readers and scripts use it

### 4.1 One counting rule

`counts(row)` in `bench/run.py` is used by every reader:

- a row with no `audit` key predates this change and counts exactly as before;
- a row with an `audit` key counts only if `sandbox` is true and the verdict is
  `clean`;
- any other row is void and counts as neither a pass nor a fail.

Past results are unchanged.

### 4.2 Void rows are re-run like undelivered ones

- `run.py`'s batch summary adds a `void N` column beside `undelivered`, and its
  completeness check counts only rows for which `counts()` is true.
- `e13_probe_read.py` skips void rows before taking a cell's first 3 delivered
  runs.
- `e13_probe_read.py` currently excludes every `archive:` row to keep out
  outcome-batch rows. Every sandboxed row is now `archive:`, so that exclusion
  applies only to rows with no `sandbox` key. For sandboxed rows, a non-empty
  `extra_skills` alone marks an outcome-batch row.
- `e13_outcome_read.py` skips void rows before Fisher's test.

### 4.3 Qualification

`e13_qualify.py` excludes drafts marked `tainted` and lists them under `tainted`
in `qualification.json`.

### 4.4 Batch scripts

`e13_probe.sh`, `e13_outcome.sh` and `e13_screen.sh` run the section 5.1
self-check before their first session, and stop the batch if it fails.

### 4.5 Methods note

A methods note in `bench/RESULTS.md` records:

- the date sandboxing started;
- that earlier rows ran unsandboxed and unaudited;
- that earlier distill sessions read plugin scripts.

## 5. Verification

### 5.1 Zero-session self-check

`python3 bench/run.py --sandbox-check` runs, under a profile built for a scratch
clone `WORK/sandbox-check`:

- `cat` of a file in the repo checkout must fail;
- `cat` of a file in another directory under `WORK` must fail;
- `cat` of a file in the scratch clone must succeed;
- `cat` of the snapshot's `scripts/validate.py` must succeed.

It exits non-zero on any mismatch.

### 5.2 One-session smoke

Before the first real batch, one sandboxed session runs on any author task with
`--runs 1`. It passes if:

- the CLI authenticates;
- a hook fires (its ledger has an event row);
- the transcript is found by `session_id`;
- the audit returns a verdict.

This is a manual gate, recorded in the plan. It is not a committed test.

### 5.3 Tests (no sessions)

- **`sandbox_profile`:** contains each deny, and the exceptions for `dest`, the
  snapshot and the project folder.
- **`audit_transcript`:** fixtures for each label:
  - `Read` of a clone file (ok);
  - `python3 <snapshot>/scripts/save_skill.py` (ok);
  - `cat <snapshot>/scripts/validate.py` (leak);
  - `Read` of the checkout (leak);
  - a denied `cat` (blocked);
  - an unparseable file and a missing one (missing).
- **Distill taint:** a transcript reading `validate.py` taints trap C and not
  trap E.
- **`counts()`:** legacy, clean, leak, missing, and `sandbox: false` rows.
- **Readers:** one void row added to each existing test for `e13_probe_read`,
  `e13_outcome_read` and `e13_qualify`, plus a sandboxed `archive:` control row
  that the probe reader must count.
- **Snapshot:** refusal of a dirty checkout, and of a non-snapshot
  `--plugin-dir`.
- **`sandbox-exec`:** one test runs 5.1 for real, skipped when the binary is
  absent.

## 6. Constraints

- Nothing under `scripts/` changes.
- `scripts/retrieve.py`, `scripts/detect.py`, `scripts/reconcile.py` and
  `bench/real_path_check.py` are not touched.
- No absolute home path in committed files; the profile builds paths at runtime.
- Guard committing steps with an explicit `|| exit 1`.
