---
name: whitespace-insensitive-evidence-quote
kind: skill
scope: project
description: >
  How verdict_from in scripts/validate.py must match a critique finding's
  `evidence` span against the skill text: collapse whitespace on both sides,
  keep word order, apply the length floor to the collapsed span.
  Use when: writing or editing verdict_from or any other check that a
  model-returned "verbatim" quote really appears in a source text; or when a
  skill whose criteria all pass on substance is graded `fail` because a quote
  differs from the file by a newline or indentation.
  Do NOT use when: the quote must be byte-exact for a non-model reason (e.g.
  patch application or hashing); or when changing severity/basis gating in
  blocks(), which is about objections, not quotes.
verification.command: "python3 -c \"import sys; sys.path.insert(0,'scripts'); import validate as v; t='1. Call flush() before'+chr(10)+'   close().'+chr(10); ok=lambda e:[{'criterion':c,'ok':True,'evidence':e} for c in v.SKILL_CRITERIA]; assert v.verdict_from(ok('flush() before close().'),t)=='pass'; assert v.verdict_from(ok('close() before flush().'),t)=='fail'; assert v.verdict_from(ok('a span that appears nowhere'),t)=='fail'; assert v.verdict_from(ok('flush()'),t)=='fail'\""
fingerprints:
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
  - "ev not in \" \".join(text.split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-5
  commit: dfbcf25
  distilled: 2026-09-15
---

## Procedure
1. Normalise the model's evidence span by collapsing every whitespace run
   (spaces, tabs, newlines) to a single space and stripping the ends:
   `ev = " ".join((f.get("evidence") or "").split())`.
2. Normalise the source text the same way before the containment test:
   `ev not in " ".join(text.split())`. Both sides must use the identical
   normalisation, or a quote of hard-wrapped prose still misses.
3. Apply the minimum-length floor (`MIN_EVIDENCE_CHARS`) to the normalised
   span, not the raw one, so padding a two-character quote with whitespace
   cannot get it past the floor.
4. Keep this a substring test on the normalised strings. Do not switch to
   token sets, sorted words or fuzzy ratios: the gate exists so that a pass
   cannot be produced without reading the file, and reordered words must
   still fail.
5. Leave the `ok is not True` check and the blocks() severity/basis filter
   before the evidence check untouched; normalisation only changes what
   counts as a real quote for a passing criterion.

## Gotchas
- The model re-wraps quotes inconsistently, even within one reply: one
  finding keeps the newline, the next joins the lines. Exact matching then
  fails a correct skill for a difference of one newline, and nothing in
  the verdict says so.
- Normalising only the evidence (not the text) looks like a fix but still
  fails whenever the source line break sits inside the quoted span.
- Loosening past whitespace turns the anti-sycophancy gate off. Only
  whitespace differences should be forgiven.

## Verification
- Run `verification.command` from the repo root. It builds a skill text
  whose sentence is wrapped across a newline plus indentation, then checks
  four things: an unwrapped quote passes, a reordered quote fails, a span
  that isn't in the text fails, and a span shorter than the floor fails.
  It exits 0 only when all four hold.
- If the procedure was not followed (the byte-exact `ev not in text`
  check), the first assertion raises AssertionError and the command exits
  non-zero. If matching was loosened too far (e.g. word sets), the
  reordered-quote assertion fails.
