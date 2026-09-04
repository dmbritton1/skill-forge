# SkillForge benchmark — pilot results (2026-08-11)

## Headline

Two authoring tasks, three runs per condition each, one model. Both traps now
score on two valid hidden tests (the file-cap test was repaired -- see below).

| Condition | Trap 1 (response_text) | Trap 2 (fingerprint snapshot) | Combined |
|---|---|---|---|
| Control — no skill | 0/3 | 0/3 | **0/6** |
| Matched — skill from this same trap | 3/3 | 2/3 | **5/6** |
| Transfer — same-class skill, *different* bug | 0/3 | 0/3 | **0/6** |

Every treatment run was ledger-confirmed as actually injected (9 and 12
injections across rounds, one per run), so both transfer nulls are real nulls
rather than delivery failures.

The direction replicated across two independent traps. The transfer arm was
indistinguishable from control both times.

The one matched-arm miss (trap 2, run 3) is a genuine miss, not a scoring
artifact: that run applied both caps (`[:SNAPSHOT_MAX_FILES]`,
`[:SNAPSHOT_MAX_BYTES]`) but never set the unknown flag when they truncated,
so it silently returned 0. The skill was injected; the model did not apply it.

## The file-cap test was invalid, and is now repaired

First run of trap 2 scored 0/3 in *every* arm including matched -- the
signature of a broken test rather than a hard task.

It was broken because it encoded the reference implementation's *strategy*
rather than the contract. The reference greps the single longest token, so 20
decoy files swamp it and the cap bites. A matched run instead used `git grep
--all-match` over every token: only the real file came back, the cap never
bit, it found the fingerprint and returned 1 -- correct, and better. The test
asserted None, so the better implementation scored zero. That same run
contained `if len(files) > SNAPSHOT_MAX_FILES: unknown = True`, so it
demonstrably held the knowledge while being marked wrong.

The repaired test (`bench/stubs/patch_file_cap_test.py`) removes the
assumption: every decoy carries ALL of the pattern's tokens, so any narrowing
strategy returns them and the cap bites either way; the decoys hold those
tokens in reverse order so `patterns.matches` correctly refuses them; and the
genuine occurrence sits in a file that sorts past the cap. The fingerprint
really is present, so answering 0 is factually wrong rather than merely
unjustified, and answering 1 requires reading past the stated cap. Only
"unknown" is defensible, whatever narrowing strategy is used.

Validated in all three directions before rerunning: it passes the reference
implementation, passes the `--all-match` implementation it previously
punished, and still fails the pre-fix code that lacks unknown-on-truncation.

Two lessons for the harness: a hidden test must assert the contract, never the
reference implementation's approach; and a condition scoring 0 across *all*
arms should be treated as a suspect test before it is treated as a result.

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
- Trap 2's file-cap test was repaired and revalidated; both traps now rest
  on two valid tests each.
- The matched-skill arm measures a **ceiling** (skill written from this exact
  trap), not typical performance.
- Skills and tasks were both curated by the same author who found the bugs.
- Replicated on the second trap at 2/3, with the one miss traced to the model
  not applying an injected skill rather than to scoring.
- Round-1 records (broken file-cap test) kept in `results-round1.jsonl`.

## Reproducing

    python3 bench/run.py --task sf-author-response-text --runs 3
    python3 bench/run.py --task sf-author-response-text-transfer --runs 3 --arm treatment

Raw records in `results.jsonl`; each line carries the arm, per-test outcomes,
wall time, and the ledger-confirmed skill save.
