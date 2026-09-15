---
name: whitespace-insensitive-evidence-quotes
kind: skill
scope: project
description: >
  How validate.verdict_from must match a critique finding's verbatim `evidence` span against the skill text: collapse whitespace on both sides, keep word order exact.
  Use when: writing or editing validate.verdict_from, MIN_EVIDENCE_CHARS, or any check that an LLM reply's quoted span appears in a source text; or when a critique whose criteria all pass on substance still returns "fail".
  Do NOT use when: changing how findings are parsed (parse_findings), how objections gate (blocks: severity/basis), or the prompt wording itself.
verification.command: "cd scripts && python3 -c \"import validate as v; ok=lambda e:[{'criterion':c,'ok':True,'evidence':e} for c in v.SKILL_CRITERIA]; t='1. Call flush() before'+chr(10)+'   close().'+chr(10); assert v.verdict_from(ok('flush() before close().'), t)=='pass'; assert v.verdict_from(ok('close() before flush().'), t)=='fail'; assert v.verdict_from(ok('a'+' '*11+'b'), 'a b '*9)=='fail'\""
fingerprints:
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
  - "ev not in \" \".join(text.split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-3
  commit: 1b15044
  distilled: 2026-09-15
---

## Procedure
1. Normalise the evidence span by collapsing every whitespace run (spaces,
   newlines, indentation) to a single space and trimming the ends:
   `ev = " ".join((f.get("evidence") or "").split())`.
2. Normalise the skill text the same way and test containment against that:
   `ev not in " ".join(text.split())`. Both sides must be normalised; doing
   only one still misses a quote the model re-wrapped.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the NORMALISED span, so padding a
   tiny quote with spaces cannot clear the floor.
4. Keep everything else about the gate strict: a passing finding whose span is
   absent from the text, shorter than the floor, or has its words reordered
   must still make the verdict "fail".

## Gotchas
- Collapse whitespace to one space, never delete it: removing it would let
  `flushbefore` match `flush before` and blur word boundaries.
- Do not reach for fuzzy matching (difflib ratios, token sets). The
  anti-sycophancy property is that a real quote cannot be produced without
  reading the file; order-insensitive matching breaks it.
- The critique model normalises whitespace inconsistently even within one
  reply, so a byte-exact `in` check fails correct skills at random-looking
  criteria.

## Verification
- `verification.command` above (run from the repo root) exits 0 when the
  procedure is applied. It asserts three things: a quote re-wrapped across a
  newline + indentation passes; the same words reordered fail; a span that is
  only long enough because of padded spaces fails the length floor.
- If the procedure is skipped (byte-exact `ev not in text`), the first
  assertion raises `AssertionError` and the command exits 1. If only the text
  is normalised but the floor is checked on the raw span, the third assertion
  exits 1.
