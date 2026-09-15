---
name: whitespace-insensitive-evidence-quote-gate
kind: skill
scope: project
description: >
  How validate.verdict_from() must match a critique finding's quoted `evidence` against the skill text: whitespace-insensitive, but still order-sensitive and length-floored.
  Use when: writing or editing verdict_from() or any check that a model-written quote appears verbatim in a document; a criterion that passed on substance is graded fail because the model re-wrapped a hard-wrapped line when quoting it.
  Do NOT use when: the model's grading (ok true/false, severity, basis) is the problem rather than evidence matching; changing the critique prompt or rubric; fuzzy or semantic matching is actually wanted.
verification.command: >
  python3 -c "import sys; sys.path.insert(0, 'scripts'); import validate as v; t = '1. Call flush() before\n   close().\n'; ok = lambda e: [{'criterion': c, 'ok': True, 'evidence': e, 'note': 'n'} for c in v.SKILL_CRITERIA]; assert v.verdict_from(ok('flush() before close().'), t) == 'pass'; assert v.verdict_from(ok('close() before flush().'), t) == 'fail'; assert v.verdict_from(ok('nowhere in this text'), t) == 'fail'"
fingerprints:
  - '" ".join((f.get("evidence") or "").split())'
  - '" ".join(text.split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-4
  commit: 2d5dc7b
  distilled: 2026-09-15
---

## Procedure
1. Collapse every whitespace run to a single space on BOTH sides before the
   containment check: `ev = " ".join((f.get("evidence") or "").split())` and
   compare against `" ".join(text.split())`. Critique models re-wrap
   hard-wrapped prose when quoting it, and not consistently within one reply,
   so a newline-plus-indent in the skill text often comes back as one space.
2. Keep the check a substring test (`ev in normalised_text`). Do not switch to
   word sets, token overlap, or fuzzy ratios: the gate exists so that a quote
   cannot be produced without reading the text, and words in a different
   order must still fail.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the normalised evidence, so padding
   a short span with whitespace cannot get it over the floor.
4. Leave the `ok is not True` check ahead of the evidence check unchanged:
   normalisation only affects how a PASS gets matched to the text, never how a
   failing finding blocks.

## Gotchas
- `.strip()` only removes whitespace at the ends of the quote. A line break
  in the middle still misses, so strip-only matching looks right until you hit
  a multi-line quote.
- Normalise the text too, not just the evidence. If the skill text keeps its
  `\n   ` and the evidence becomes a single space, it still misses.
- The critique prompt can keep asking for "character-for-character" quotes.
  The strict wording keeps models honest, and the lenient match covers what
  they actually send back.

## Verification
- Run the `verification.command` above from the repo root. It should exit 0.
  It asserts that a quote of `flush() before\n   close().` written with a
  single space passes, that the same words reordered fail, and that a span
  absent from the text fails.
- If the procedure is skipped (byte-exact `ev not in text`), the first
  assertion raises `AssertionError` and the command exits 1. This was checked
  against the pre-fix `verdict_from`. If normalisation is overdone (word-set
  matching), the reordered-words assertion fails instead.
