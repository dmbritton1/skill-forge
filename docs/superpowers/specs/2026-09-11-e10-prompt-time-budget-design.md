# E10 — does a wrong skill hurt when it arrives at prompt time beside the right one?

Design written 2026-09-11, after a review of the selector-defect handoff.
Nothing here has been run. The figures in §1 and §2 were measured; every other
number is a slot.

## The question

The handoff's next step replaces the injection selector's skip-and-continue
with stop-at-first-overflow, then raises `INJECT_BUDGET_TOKENS`. The review
found the first half changes nothing on its own. Every distilled skill costs
759–1192 tokens against a 1200 budget, so after rank 1 nothing else fits under
either selector: both deliver identical sets on both pools and both tasks at
1200. The selector only matters once the budget goes up. **The decision that
actually gates the change is whether the budget goes up.**

On the consolidated seven-skill library, a raised budget delivers two skills at
prompt time on both tasks, and one of them is about the wrong bug.

> **Does delivering a wrong-bug skill beside the right one, at prompt time,
> cost anything versus the right one alone?**

## 1. What the existing rows already say

Measured before this design, zero sessions, over every valid row in
`bench/results.jsonl` that carries `injections`, costing each injected file at
`max(1, len(whole file) // 4)`:

| batch | arm | tokens injected | resolved | when the correct skill arrived |
|---|---|---|---|---|
| E6 (2026-09-10) | R+I | 1118 (`response_text`), 1105 (`fingerprint`) | 6/6 | prompt |
| E8 (2026-09-11, 09:56) | L, `response_text` | 1831, 2829, 1831 | 3/3 | **symptom path, mid-session** |

E8's library arm carried a wrong-bug skill at prompt time
(`B/learn/1`, 1072) on every run and resolved every run, with arm M 3/3 and
control 0/3 in the same batch. E8's refused first attempt also resolved at
1831 and 2810; those rows stay excluded (E8 spec §4.1).

**No harm has been observed up to ~2800 injected tokens — but every run above
1118 had its correct skill arrive after the failure surfaced**, through
`detect.py`. A raised prompt budget puts both skills in front of the model
before any work begins. E10 closes that gap.

## 2. Payload and delivery prediction

### 2.1 The pair

`budget_sweep.seven` delivers exactly two entries on both tasks at any budget
from **1847 to 2825**, identically under skip-and-continue and
stop-at-first-overflow (every entry ranked third or lower costs at least 979):

| file | name | bug | kind | cost |
|---|---|---|---|---|
| `bench/distilled/B/consolidated/1/SKILL.md` | `capped-scan-reports-unknown-not-absent` | B — `fingerprint` | skill | 1088 |
| `bench/distilled/A/learn-failure/1/SKILL.md` | `json-dumps-breaks-token-matching` | A — `response_text` | antiskill | 759 |

Together **1847**. `save_skill.py` writes the draft byte for byte, so the
installed cost is the source cost. At a budget of 2000 the margin is 153
tokens.

**Names are not identifiers in this pool.** `B/learn/1` (1072) and
`B/consolidated/1` (1088) share the name
`capped-scan-reports-unknown-not-absent`. Every reference in this design is a
path.

### 2.2 Ranking

`retrieve.rank` over `name + description`. The pair installed alone and the
full seven give the same top two, in the same order, and every entry passes
`MIN_MATCHED_TERMS`:

| task | pool | rank 1 | rank 2 |
|---|---|---|---|
| `response_text` (wants A) | pair | `B/consolidated/1` 5.43 | `A/learn-failure/1` 4.86 |
| `response_text` | seven | `B/consolidated/1` 8.17 | `A/learn-failure/1` 6.94 |
| `fingerprint` (wants B) | pair | `B/consolidated/1` 6.71 | `A/learn-failure/1` 4.11 |
| `fingerprint` | seven | `B/consolidated/1` 11.24 | `A/learn-failure/1` 6.32 |

**Wrong skill first on `response_text`; right skill first on `fingerprint`.**
Reproduce, zero sessions:

```bash
python3 - <<'EOF'
import sys; sys.path[:0] = ['scripts', 'bench']
import retrieve, budget_sweep as bs
by = {e['_path']: e for e in bs.seven}
pair = [by['bench/distilled/B/consolidated/1/SKILL.md'],
        by['bench/distilled/A/learn-failure/1/SKILL.md']]
for label, pool in (('pair', pair), ('seven', bs.seven)):
    for task, _ in bs.TASKS:
        print(label, task, [(e['_path'], round(s, 2), m)
                            for e, s, m in retrieve.rank(bs.P[task], pool)][:2])
EOF
```

## 3. Design

### 3.1 Arms

| Arm | Installed | Budget | Sessions |
|---|---|---|---|
| **M** — matched alone | `response_text`: `A/learn-failure/1`; `fingerprint`: `B/consolidated/1` | 1200 | 6 |
| **P** — pair | both §2.1 files, on both tasks | 2000 | 6 |
| **S** — seven | `A/learn-failure/1`, `/2`, `/3`; `A/consolidated/1`; `B/consolidated/1`; `B/learn-nogate/1`, `/2` | 2000 | 6 |
| **C** — control | nothing | — | 6 |

Both tasks, **n=3 per cell**, all four arms **in one batch**, in the order M,
P, S, C per task, `response_text` first. 24 sessions.

Arm M is the comparator, not control, and both its skills are named here, not
chosen later. Both have already held the ceiling alone: `A/learn-failure/1`
3/3 on `response_text` (2026-09-09, 21:04–21:05) and `B/consolidated/1` 3/3
on `fingerprint` (E9, 2026-09-11, 15:33–15:35). Control is present because E5
showed this harness's cross-batch spread exceeds its effects, and because an
across-the-board 3/3 must not be readable as a leaked answer
(`results-leaky-stub.jsonl`).

### 3.2 Delivery prediction

Fixed here, scored in §4:

- **P and S, prompt path:** exactly the §2.1 pair, in the §2.2 order, on both
  tasks.
- **M, prompt path:** its one skill. It delivers the same at 1200 as at 2000.
- **P, symptom path:** nothing further. Its only anti-skill is already in the
  session's dedupe set by the time any tool output exists.
- **S, symptom path:** on `response_text` it may add `A/learn-failure/2` or
  `/3` mid-session, as E8 observed. Not expected on `fingerprint`. Recorded
  either way, not scored.

The selector decision does not touch any of this: §2.1's delivery is the same
under both.

### 3.3 Harness change

**`scripts/retrieve.py`** — one line in `run_hook`:

```python
budget = int(os.environ.get("SKILLFORGE_INJECT_BUDGET") or INJECT_BUDGET_TOKENS)
```

Read at call time, not import, so in-process tests see it. Unset or empty is
1200, so shipped behaviour is unchanged. A non-integer raises inside `main`'s
`try` and the hook delivers nothing, which is why `run.py` validates. A comment
marks it test-only, the precedent being `sync._force_hot`. **`detect.py` is not
touched**: the question is about prompt time.

**`bench/run.py`:**

- `--inject-budget N`, a positive integer or an argparse error; help says
  test-only.
- Exported on every run beside `SKILLFORGE_FORCE_HOT` as `str(N or "")`, so a
  previous value cannot leak into the next run.
- `arm_segment` appends `-b<N>` for treatment arms, after `-plus`: P is
  `-d-learnfailure-1-plus-b2000`, S is `-d-learnfailure-1-plus6-b2000`, control
  stays `""`. `extract.parts_of` already reads the segment as everything
  between the arm and the run index.
- The row carries `inject_budget`: N, or `null` meaning the shipped 1200, which
  is what every earlier row ran at.

**`bench/e10_batch.sh`**, on the pattern of `e8_batch.sh`: absolute
`--skill-from` paths, one `--plus-skill` for P, six for S, `--inject-budget
2000` on P and S.

**Tests, two:**

1. `tests/test_retrieve.py` — two entries that together cost more than 1200 and
   less than 2000. Unset, one is injected; with the variable at 2000, both are.
   `tests/conftest.py` restores the environment.
2. `tests/test_bench_run.py` — the segment gains `-b2000` for treatment, not
   control, and composes after `-plus`.

### 3.4 What gets measured

- **Which skills injected, and by which trigger**, from `injections` on the
  row. This is the mechanism reading §3.2 predicts.
- **Score**, the task's hidden tests.
- **Graded probes are not run.** They reproduced the binary verdict in 60 of 60
  rows across E7, E8 and E9, and these tasks are single-trap.

### 3.5 Before and after the batch

Before, costing one session: the full suite green, `python3 bench/run.py
--check`, then the session meter
(`claude -p "Reply with exactly: OK" --model claude-opus-5`). 25 sessions in
all, plus headroom for a re-run.

After: `python3 bench/extract.py --batch e10 <clone-name> ...` over the batch's
24 clones, a register row and a results section in `bench/RESULTS.md`.

## 4. Pre-registration

Fixed before any data exists.

- Arms M, P, S and C run in the **same batch**, in that order, per task.
- **n=3 per cell.** Every conclusion says so.
- All 24 sessions run. No cell is dropped after its score is seen.
- Rows with `session_ok: false` are excluded and the excluded count reported.
  If refusals truncate the batch, E10 is postponed, not answered: it re-runs in
  full, and the valid rows of the aborted attempt are excluded too. Inherited
  from E8 §4.1.
- **Arm M must reproduce 3/3 on both tasks.** If it does not, that is the
  headline and E10 is reported as uninterpretable.
- **Arm C at 2/3 or more on a task makes that task uninterpretable.** One
  resolved control run does not: `response_text` control has resolved 1 in 6
  before.
- **Harm is declared in advance as arm P or arm S scoring below arm M on a
  task.** Any single unresolved run where M is 3/3 counts.
- **§3.2 is scored as a prediction.** A run whose prompt-path delivery differs
  from it is reported on its own line with what it actually received. A
  symptom-path addition in arm P is a failed prediction; in arm S it is
  recorded only.

## 5. How to read the outcome

- **P and S hold on both tasks.** No large prompt-time harm at 1847 tokens with
  a wrong-bug skill beside the right one. The 2000 budget is licensed as far as
  n=3 licenses anything, and the next change is the size guard,
  stop-at-first-overflow in `retrieve.py`, and the raise, landed together.
- **P falls on `response_text` only.** Order matters: a wrong skill first
  misleads. A raised budget is unsafe exactly where ranking fails. Do not raise;
  ranking is the fix.
- **P falls on both tasks.** A wrong skill at prompt time hurts in either order.
  Do not raise.
- **P holds and S falls.** The pair is not the problem; something else in the
  library is. Report it and do not reach for an explanation.
- **P falls on `fingerprint` only.** No model here predicts it. Report and stop.
- **Arm M below its ceiling.** Uninterpretable; say so.

## 6. Threats

1. **n=3 per cell, with arm M at its ceiling.** Only failures can show harm. A
   null is "no large effect", never "no effect".
2. **Loud traps only.** Ranking failure on a trap with no symptoms (handoff
   §3.2) is untouched.
3. **"Wrong" is the sibling trap.** Both bugs live in this repository and both
   concern lossy text handling. A wrong skill about something unrelated might
   mislead differently.
4. **One budget, one payload.** Nothing here speaks to three skills at ~2900,
   which is what the unconsolidated ten-skill library needs.
5. **The variable is exported into the session.** The model edits an older copy
   of `scripts/retrieve.py` and the hidden tests run with
   `SKILLFORGE_INJECT_BUDGET` set. That copy predates the variable and cannot
   read it. A model that runs `env` would see it; accepted.
6. **Arm S writes to the operator's real library.** `A/learn-failure/3` and
   `B/learn-nogate/1`, `/2` are global scope and land in `Path.home()`;
   `libguard` reverts them, as it did for E8. **Run no other Claude session on
   this machine during the batch.**
7. **Same-author curation.** The operator wrote the tasks and traps; bench
   sessions wrote the payloads. Bench sessions inherit the operator's plugin
   set.
8. **Session count is the binding meter.** 25 including the meter check.
   `claude -p` exits 1 at the limit.

## 7. Out of scope

The `detect.py` budget. Stop-at-first-overflow itself, and the save-time size
guard, both of which this result gates rather than tests. Changing the shipped
1200. The three-skill case. Ranking on anything other than
`name + description`.
