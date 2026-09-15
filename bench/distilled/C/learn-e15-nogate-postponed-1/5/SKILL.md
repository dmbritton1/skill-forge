---
name: whitespace-insensitive-evidence-quote-gate
kind: skill
scope: project
description: >
  validate.verdict_from's evidence gate must match a model-quoted span against the skill text with whitespace collapsed on both sides, not byte-exact `ev not in text`.
  Use when: writing or editing verdict_from, or any check that a critique/LLM-judge "evidence" quote appears verbatim in a source document; a correct skill fails critique because its quote was re-wrapped across a line break.
  Do NOT use when: the quote must also be order- or case-insensitive (that defeats the anti-sycophancy property), or when matching code/diffs where whitespace is significant.
verification.command: >
  python3 -c "import sys; sys.path.insert(0, 'scripts'); import validate as v; ok = lambda e: [{'criterion': c, 'ok': True, 'evidence': e} for c in v.SKILL_CRITERIA]; t = '1. Call flush() before' + chr(10) + '   close().' + chr(10); assert v.verdict_from(ok('flush() before close().'), t) == 'pass'; assert v.verdict_from(ok('close() before Call flush().'), t) == 'fail'; assert v.verdict_from(ok('a span that appears nowhere'), t) == 'fail'; assert v.verdict_from(ok('flush()'), t) == 'fail'"
fingerprints:
  - '" ".join(text.split())'
  - '" ".join(str(f.get("evidence") or "").split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-5
  commit: 309fc6b
  distilled: 2026-09-15
---

## Procedure
1. A passing finding's `evidence` counts only if it is a real quote of the
   skill text. Normalise BOTH the quote and the text with
   `" ".join(s.split())` (collapses every run of spaces, tabs and newlines to
   one space and trims the ends), then test `ev in normalised_text`.
   Models re-flow hard-wrapped prose when quoting it, inconsistently even
   within one reply, so byte-exact matching fails correct skills over a
   single newline.
2. Apply the minimum-length floor (`MIN_EVIDENCE_CHARS`) to the NORMALISED
   quote, so padding a short span with whitespace cannot clear the floor.
3. Coerce before splitting: `str(f.get("evidence") or "")`. The reply is
   model-written JSON; a non-string evidence value must fail the match, not
   raise.
4. Normalise whitespace only. Keep the substring test order- and
   case-sensitive: the gate's purpose is that a quote cannot be produced
   without reading the text, so a reordered or paraphrased span must still
   fail.
5. Leave the rest of the gate unchanged: a non-`True` `ok` that blocks
   returns `fail`; an unquotable pass returns `fail` regardless of
   severity/basis.

## Gotchas
- `.strip()` alone is not enough — it only trims the ends; the interior
  newline plus indentation is what breaks the match.
- Normalising only the quote (not the text) still misses: the text keeps its
  `\n   ` and the collapsed quote has a single space.

## Verification
- From the repo root, `verification.command` asserts four things against
  `verdict_from`: a quote re-wrapped across a line break passes; reordered
  words fail; a span absent from the text fails; a span under the length
  floor fails. It exits 0 only when all hold.
- If the procedure was NOT followed (byte-exact `ev not in text`), the first
  assertion raises `AssertionError` and the command exits 1. If whitespace
  normalisation was overdone into word-bag matching, the reordered-words
  assertion exits 1.
