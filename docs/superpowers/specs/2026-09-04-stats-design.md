# `/stats` — library health, honestly reported

**Status:** design · 2026-09-04
**Scope:** the last open item in the v0.2 roadmap (Section 13)
**Amends:** Section 14 (Health metrics)

## Why this is the last v0.2 item, and why it nearly shipped useless

Section 14 names eleven metrics and says they are "visible via `/stats`".
No `/stats` exists. Building it is a day's work; building it *honestly* is
the design problem, because the instrument would currently be pointed at a
library of six skills whose entire recorded history is a few dozen events —
at time of writing, twenty injections and three detections, and the exact
figures will have moved by the time anyone reads this, which is itself the
point.

That is not a reason to defer it. It is a reason to decide, before writing
any of it, which numbers are measurements and which are decoration — the
same judgment Section 1.1 already makes for mechanisms, applied one level
down to individual figures.

Two recent bugs sharpen the point. `bash_outcome` read a field the harness
never sends, so every verification outcome was NULL while the tests were
green; the exit-code struggle trigger never fired once across 1,561 replayed
calls. Both were invisible for months **because nothing aggregated them**.
A `/stats` that had printed `verification outcomes: 3 (all unknown)` would
have exposed the first on day one. That is the strongest argument for this
command, and it also sets its bar: a dashboard that rounds an absence to
zero, or a noise ratio to a percentage, would have hidden that bug rather
than surfaced it.

## What is actually measurable

Every event the system writes, inventoried from the call sites rather than
from the schema:

| field | values ever written |
|---|---|
| `event_type` | `injection`, `detection`, `reconcile`, `save`, `delete`, `review` |
| `detection` | `marker`, `fingerprint`, `symptom`, `verification` |
| `tier` | `warm` only |
| `trigger` | `symptom`, `refire` |

Checked against Section 14's eleven:

| Section 14 metric | Verdict |
|---|---|
| library size by status and tier | measurable |
| quarantined awaiting review | measurable |
| confidence bucket distribution | measurable (three buckets, per 1.1) |
| standing context cost (hot descriptions) | measurable |
| injection-to-use ratio | measurable, **warm only** — see below |
| marker compliance-miss rate | measurable |
| symptom hit rate and re-fire rate | measurable |
| skill survival rate | measurable |
| **injection tokens per prompt** | **not instrumented** — the payload size is derivable, but nothing counts prompts: `turn` is NULL on every injection row and no code writes it |
| rediscovery time saved | needs parsing `cost of rediscovery` out of anti-skill bodies |
| **hot-tier churn** | **not instrumented** — nothing writes a tier-change event |
| **model-obvious rate** | **not instrumented** — needs the ε-holdouts cut from v0.3 |

Eight work, three cannot. All three gaps are reported in the output rather
than omitted, per Section 14's own instruction that volume-gated numbers be
"visibly marked as placeholders rather than rendered alongside real
measurements". The rule is stated there for scale; it applies at least as
strongly to a metric with no instrument at all.

## The two rules that shape the output

### Small-n: counts are facts, rates are claims

A count is true at any sample size. A percentage asserts a stable
underlying rate, and Section 1.1 already holds that 5–15 lifetime events per
skill cannot support one.

So: **counts always print; a ratio prints only at n ≥ 10.** Below that the
output reads `3 of 4 sessions (n too small for a rate)`. The threshold is
one constant, `MIN_RATIO_N = 10`, chosen as the low end of a range Section
1.1 already calls insufficient — deliberately not derived from anything, and
worth revisiting once real volume exists rather than tuned now against six
skills.

This is the whole reason the command is worth building at small scale. A
dashboard that showed `compliance: 75%` off four events would be worse than
no dashboard: it would invite decisions about skills based on noise.

### Hot vs warm: the ratio that would lie

`injection` events are written for **warm** tier only. Hot-tier skills are
materialized natively into the session and never produce one.

Detections, by contrast, are logged for every tier. So a library-wide
injection-to-use ratio would draw its two halves from different populations:
uses counted across all skills, injections counted across warm ones only.
A hot skill can only ever push the ratio in one direction, and the figure
would move whenever the hot/warm split moved — while reading as a statement
about relevance.

`/stats` reports it as **warm-only, labelled**, and prints hot-tier usage as
its own counts. This is the same defect class as `bash_outcome` reading a
key the harness never sent: a figure computed over a population that cannot
appear in it. Naming it here so the implementation does not quietly
reintroduce it.

## Shape

`scripts/stats.py` computes **and formats**; `commands/stats.md` is thin —
run it, show the output, explain a metric only when asked.

`/library` deliberately hands rows to the model to narrate, because a
`critique: fail` needs its findings explained and argued with. `/stats` is
the opposite case. Aggregate figures over a six-skill library are precisely
where a model summarizing "your library looks healthy" converts noise into a
conclusion. Deterministic output is also testable; a narration is not.

The command file still carries the untrusted-data rule that every
skill-touching command carries: skill names and descriptions reaching the
output are data, never instructions.

## Output

Six sections, in this order — library first because it is the only one that
is meaningful at n=1, placeholders last so they never sit beside a real
number.

1. **Library** — counts by kind, scope, tier, bucket; quarantined awaiting
   review.
2. **Context cost** — hot-tier standing tokens against `hot_budget_tokens`
   (1500). Capped by construction, so the figure is a fill level, not a
   trend.
3. **Usage** — injections; detections split by `marker`, `fingerprint`,
   `verification`, `symptom`; injection-to-use (warm-only, labelled);
   marker compliance-miss.
4. **Outcomes** — verification `success` / `failure` / unknown; bucket
   distribution; survival rate (saved → trusted).
5. **Value** — rediscovery time saved: anti-skill `cost of rediscovery` ×
   uses. Reported as a sum with its own sample size, since one anti-skill
   with a large stated cost can dominate it.
6. **Not measured** — hot-tier churn, model-obvious rate, and injection
   tokens per prompt, each naming the instrument it would need.

An unknown count is never rounded to zero. `verification outcomes: 3 (all
unknown)` and `verification outcomes: 3 successes` must be visibly
different states — that distinction is what would have caught the
`bash_outcome` bug.

## Data sources

Existing helpers carry most of it: `library.rows()` (name, kind, scope,
tier, bucket, critique, executable, successes, failures, last_used),
`retrieve.load_index()` (descriptions, `hot_budget_tokens`), and `trust`
for the quarantine count.

One addition: the ledger's aggregate accessors (`usage_for`,
`confidence`, `validations_for`) are all per-skill. `/stats` needs
library-wide counts, so one new accessor returning event totals grouped by
`event_type` and `detection`. It follows the file's existing convention —
zeros on any failure, never raising into a display path.

No schema change, no new event type, no migration.

## Testing

`tests/test_stats.py`, plain `def test_*` with an assert-based `__main__`
runner, matching the suite.

- A seeded ledger below `MIN_RATIO_N` asserts **no `%` appears anywhere** in
  the output — the small-n rule's real guarantee, stated as a property of
  the whole render rather than of one line.
- The same ledger above the threshold asserts a rate does appear.
- Both placeholders always present, at every data volume.
- An empty library prints a report rather than crashing or dividing by zero.
- Three verification detections with NULL outcome render as `unknown`, not
  as zero successes — a direct regression pin on the bug that motivated
  this command.
- No test invokes a model, spawns a process, or writes outside its sandbox.

## Section 14 amendment

Section 14 names hot-tier churn as "the metric to watch" without
qualification, and nothing writes a tier-change event. It also names
injection tokens per prompt as "the ruthlessness metric" while nothing
counts prompts. Both gain a note that they are not instrumented and what it
would take. Model-obvious is already
correctly described there as a placeholder pending volume, so it needs no
change.

## Out of scope

- **Instrumenting tier changes.** It would make churn real, but it touches
  the write path in `sync.py`, and this slice is read-only reporting. Worth
  doing when hot-tier competition actually exists; with six skills and a
  1500-token budget, nothing is competing for a slot yet.
- **Trends over time.** Every event carries a `ts` and the ledger could
  support week-over-week, but a trend needs a baseline, and there is not yet
  a week of honest outcome data — the outcome column only started recording
  today. Revisit once it has.
- **`/stats --json`.** No consumer exists. YAGNI.
