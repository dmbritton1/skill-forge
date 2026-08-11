# SkillForge benchmark — pilot results (2026-08-11)

## Headline

Two authoring tasks, three runs per condition each, one model. Scored on
valid hidden tests only (see "The file-cap test is invalid" below).

| Condition | Trap 1 (response_text) | Trap 2 (byte cap) | Combined |
|---|---|---|---|
| Control — no skill | 0/3 | 0/3 | **0/6** |
| Matched — skill from this same trap | 3/3 | 2/3 | **5/6** |
| Transfer — same-class skill, *different* bug | 0/3 | 0/3 | **0/6** |

Every treatment run was ledger-confirmed as actually injected, so both nulls
are real nulls rather than delivery failures.

A pilot, not a proof — but the direction replicated across two independent
traps, and the transfer arm was indistinguishable from control both times.

## The file-cap test is invalid

The second trap shipped two hidden tests. `test_snapshot_unknown_when_match_
past_file_cap` scored 0/9 across every arm including matched, which is the
signature of a broken test rather than a hard task.

It is broken because it encodes the reference implementation's *strategy*,
not the contract. The reference greps the single longest token, so 20 decoy
files swamp it, the cap bites, and the correct answer is "unknown". A matched
run instead used `git grep --all-match` over every token: only the real file
comes back, the cap never bites, it finds the fingerprint and returns 1 —
which is correct, and better. The test asserts None, so the better
implementation scored zero.

That same run contains `if len(files) > SNAPSHOT_MAX_FILES: unknown = True`,
so it *demonstrably had the knowledge* while being marked wrong. The binary
resolved-metric then hid this: one broken test dropped the whole task to
0/3 in every arm, and only the per-test decomposition showed matched 2/3 vs
control 0/3 on the valid test.

Lesson for the harness: hidden tests must assert the contract, never the
reference implementation's approach — and a condition that scores 0 across
*all* arms should be treated as a suspect test before it is treated as a
result.

## What the task is

`sf-author-response-text`, an **authoring** task. The tree is `22ddf37~1` with
`detect.response_text` replaced by a contract-only stub. The model implements it
from the docstring and **never sees the grading tests**, which are applied
afterward. Scoring is binary on two hidden tests, per spec §7 (verification
success, never turns-to-completion).

The trap: `tool_response` is usually a dict, and `json.dumps` escapes newlines
to a literal backslash-n, which the tokenizer then glues onto the next word —
so every symptom whose signature begins a line silently stops matching.

## Mechanism, not just counts

| Arm | Run | What it wrote | Hidden tests failed |
|---|---|---|---|
| control | 1 | flat join, comment: *"no tool nests them deeper"* | nested |
| control | 2 | `json.dumps(resp, ensure_ascii=False, default=str)` | both |
| control | 3 | `json.dumps(resp, default=str)` | both |
| matched | 1–3 | depth-capped leaf walker | none |
| transfer | 1 | `json.dumps(resp, default=str)` | both |
| transfer | 3 | shallow dict handling | nested |

Depth-capping appears in all three matched-skill runs and no control run. It is
a specific instruction in that skill's Fix section, so the influence is
traceable rather than merely correlated.

## Three earlier designs that measured nothing

Recorded because each null was informative:

1. **Public-repo repair task** (arrow #968): control resolved it. No headroom.
2. **Post-cutoff repair tasks** (this repo's own bugs, code days old): control
   resolved 4/4. This killed the contamination hypothesis — the bugs *cannot*
   be in training data. The real cause is structural: **a FAIL_TO_PASS task
   hands over the answer**, because the red assertion names the exact
   condition. One control session derived the entire escaping insight from the
   failing test. Every SWE-bench-style benchmark is FAIL_TO_PASS, so that whole
   family structurally cannot measure what a skill contributes.
3. **First authoring attempt**: the stub docstring said the object was one
   "whose string leaves hold the tool's output" — which prescribes the
   leaf-walking fix. Both arms scored 6/6. The leak check had grepped for
   `escape|newline|json|serial` and sailed past it. Preserved in
   `results-leaky-stub.jsonl`.

## What this suggests

Skills change authoring behavior when they are **specific and matched**.
Abstract same-class knowledge did not transfer at this n — the transfer arm was
indistinguishable from control, despite being injected every run.

**Roadmap risk this raises:** v0.3's `/consolidate` generalizes sibling skill
clusters into a shared parent pattern. If specificity is what carries the
value, generalization may destroy the thing being measured here. Worth testing
before building it.

**Secondary:** retrieval precision matters more than recall. A thematically
related skill that fires costs tokens and delivers nothing.

## Limits

- n=3 per condition per trap (n=6 combined), two traps, one model.
- Trap 2's file-cap test is invalid and excluded; that trap therefore rests
  on a single valid test.
- The matched-skill arm measures a **ceiling** (skill written from this exact
  trap), not typical performance.
- Skills and tasks were both curated by the same author who found the bugs.
- Replicated on the second trap, but weakly: 2/3 on one valid test.
- The invalid file-cap test should be rewritten to assert the contract
  (decoys containing every token, pattern genuinely absent, so any narrowing
  strategy truncates and must answer "unknown") and rerun.

## Reproducing

    python3 bench/run.py --task sf-author-response-text --runs 3
    python3 bench/run.py --task sf-author-response-text-transfer --runs 3 --arm treatment

Raw records in `results.jsonl`; each line carries the arm, per-test outcomes,
wall time, and the ledger-confirmed skill save.
