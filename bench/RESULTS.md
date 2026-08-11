# SkillForge benchmark — pilot results (2026-08-11)

## Headline

| Condition | Skill delivered | Resolved |
|---|---|---|
| Control — no skill | — | **0/3** |
| Matched skill — distilled from this same trap | 3 injections | **3/3** |
| Transfer — same-class skill from a *different* bug | 3 injections | **0/3** |

One task, three runs per arm, one model. A pilot, not a proof.

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

- n=3 per arm, one task, one trap, one model.
- The matched-skill arm measures a **ceiling** (skill written from this exact
  trap), not typical performance.
- Skills and tasks were both curated by the same author who found the bugs.
- Not replicated on the second trap (`sf-truncation-reports-absent` as an
  authoring task) — the obvious next run.

## Reproducing

    python3 bench/run.py --task sf-author-response-text --runs 3
    python3 bench/run.py --task sf-author-response-text-transfer --runs 3 --arm treatment

Raw records in `results.jsonl`; each line carries the arm, per-test outcomes,
wall time, and the ledger-confirmed skill save.
