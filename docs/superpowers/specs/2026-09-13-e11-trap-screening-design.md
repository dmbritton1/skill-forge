# E11 — trap screening: which tasks still have a control floor of zero?

**Status:** pre-registered 2026-09-13, before any session was run.

## The question

E10 retired `sf-author-response-text`. How many usable discriminators does the
bench still have, and can either of the two never-run tasks serve as one?

A task is a usable discriminator only if the model cannot solve it **without**
the skill. That is the control floor, and it is a property of the task's stub
and tests — not of the skill paired with it.

## 1. What the existing rows already say

`bench/tasks.json` holds ten ids, but they collapse to **four distinct bugs**.
The `-transfer`, `-irrelevant` and `-umbrella` variants share their parent's
`prompt`, `stub_cmd` and `test_path` byte-for-byte and differ only in `skill`.
Control installs no skill, so a floor measured on any one variant is the floor
for all four.

| distinct bug | ids | mode | control floor |
| --- | --- | --- | --- |
| `fingerprint_preexisting` author task | 4 | author | **0/18** — intact |
| `response_text` author task | 4 | author | 1/13 before 09-13, **6/6** on 09-13 — retired (E10) |
| json.dumps escaping (`22ddf37`) | 1 | repair | **never run** |
| truncation-reports-absent (`ab4acfe`) | 1 | repair | **never run** |

So the bench has exactly **one** trap with a demonstrated zero floor, and two
candidates that have never produced a single row.

## 2. Pre-flight — already done, zero sessions

Both candidates were built with `run.py::prepare` and scored with
`run.py::score` on 2026-09-13. Both start **fully red**, 3 of 3 `fail_to_pass`
each, and `prepare()` works on its repair-mode branch, which no batch had ever
exercised. A task whose graded tests start green measures nothing; neither does.

## 3. Design

### 3.1 Arms

Control only. No skill is installed in any cell.

| cell | task | n | purpose |
| --- | --- | --- | --- |
| A | `sf-escaping-breaks-symptom-match` | 6 | candidate |
| B | `sf-truncation-reports-absent` | 6 | candidate |
| R | `sf-author-fingerprint-preexisting` | 3 | same-batch reference, known 0/18 |

15 sessions, one batch, one environment.

There is no treatment arm. A floor is a property of the task, and a treatment
cell cannot raise or lower it.

### 3.2 Why n = 6

`response_text`'s floor was 1/13 — roughly 8% — and stayed invisible at n=3 for
four consecutive batches. Six sessions reliably catch a floor above about 20%.
It does not catch 8%; nothing affordable does. See §6.

### 3.3 Why a reference cell

E10's control break was caught only because a second task's control ran in the
same batch and did not move. Cell R is that check, made deliberate: if the
known-good trap moves, the screen is measuring the environment, not the tasks.

### 3.4 Harness change

**None.** `bench/run.py --task <id> --runs N --arm control`, as shipped. Every
row carries `env` (CLI build, plugin shas) as of `8e0cf16`.

## 4. Pre-registration

### 4.1 The criterion, fixed before data

- **0/6 → ADMITTED**, provisionally. The task may be used as a discriminator,
  and same-batch controls remain mandatory in every batch that uses it.
- **≥ 1/6 → NOT ADMITTED.** Any non-zero floor disqualifies.

The strictness is deliberate and is E10's lesson: a non-zero floor is not noise,
it is a trap already on its way out. 1/13 was a warning this project read as
noise for four batches.

### 4.2 The reference cell can void the batch

If cell R resolves **≥ 1/3**, the known-good trap has moved and **the entire
screen is void** — both candidate cells included, regardless of what they read.
A floor measured while the environment is shifting is not a floor.

### 4.3 Exclusions

Rows with `session_ok: false` are excluded and the session re-run. They are
never scored. A refused batch is postponed, not poisoned.

### 4.4 The mode caveat, stated in advance

Both candidates are `mode: repair`: the model is shown the failing tests and
asked to fix the source. Author mode hides the tests and measures knowledge.
Repair mode is **structurally the weaker trap**, so a non-zero floor is the
expected outcome, not a surprise. Predicting it here is what makes a null
informative rather than a rationalisation afterwards.

## 5. How to read the outcome

- **Both 0/6** — the bench has three usable traps. E4's blockage is a
  task-difficulty problem, not a supply problem.
- **One 0/6** — two usable traps. Enough for a batch needing a second trap.
- **Neither 0/6** — repair-mode tasks cannot serve as discriminators at this
  model. The bench has exactly one trap, and new **author-mode** tasks must be
  written before any experiment needing two can run. This is the outcome §4.4
  predicts, and it would make authoring, not screening, the critical path.
- **Cell R ≥ 1/3** — void; re-run when the environment settles.

## 6. Threats

1. **n = 6 bounds the floor loosely.** 0/6 is consistent with a true floor up to
   about 39% at 95% confidence; 0/18 with about 15%. "Admitted" means "no floor
   detected at n=6", never "floor is zero". This is why §4.1 keeps same-batch
   controls mandatory.
2. **Repair mode is the weaker trap.** §4.4.
3. **Screening is a snapshot.** A floor decays. Admission is provisional and
   expires; the live number in a batch governs, not this row.
4. **Clone-name reuse.** Both candidates are new ids, so their clone segments
   are new. Cell R reuses `fingerprint`'s existing segment, as every prior
   batch has.

## 7. Out of scope

Authoring new author-mode tasks. E4 itself. Any treatment arm. The `--batch`
label for unique clone names, still deferred.
