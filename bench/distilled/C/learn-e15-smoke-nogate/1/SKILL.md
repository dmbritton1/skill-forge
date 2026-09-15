---
name: whitespace-insensitive-verbatim-evidence-check
kind: skill
scope: global
description: >
  An evidence gate such as verdict_from() that accepts an LLM grade only if its
  "verbatim" quote appears in the graded text must collapse whitespace on both
  sides before the substring check, while still requiring the words in order.
  Use when: writing or editing code that checks a model-quoted span with
  `quote in text`; building an LLM-judge or critique pipeline that demands
  quoted evidence; a judge rejects findings whose quote differs from the source
  only by line breaks or indentation.
  Do NOT use when: the comparison must be byte-exact (hashes, signatures,
  patches); fuzzy or semantic matching is actually wanted; the quote is not
  model-generated.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - '" ".join(text.split())'
  - '" ".join((f.get("evidence") or "").split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-smoke-nogate-1
  commit: 0f1651c
  distilled: 2026-09-15
---

## Procedure
1. Normalise the quoted span with `" ".join(quote.split())`. This strips the
   ends and collapses every run of spaces, tabs and newlines to one space.
2. Normalise the source text the same way (`" ".join(text.split())`) and do the
   substring check on the two normalised strings. Normalising only the quote
   still misses, because the source's hard-wrap newline stays a newline.
3. Apply any minimum-length floor to the *normalised* quote, so padding a short
   span with whitespace cannot clear it.
4. Keep it a substring check. Do not switch to token sets, sorted words or
   fuzzy ratios: a span with the same words in a different order must still be
   rejected, or a model can "quote" without having read the text.
5. Leave every other fail-closed rule unchanged (a non-literal `ok`, missing or
   absent evidence). Whitespace is the only thing being forgiven.

## Gotchas
- Models re-wrap hard-wrapped Markdown inconsistently, even within one reply:
  one quote keeps `before\n   close()`, the next writes `before close()`.
  Byte-exact matching turns that into a false `fail` for a document that passed
  on substance.
- Use `str.split()` with no argument. `split(" ")` keeps empty strings and
  leaves newlines and tabs alone.

## Verification
- `python3 tests/test_validate.py` (run from the repo root) should print only
  PASS lines and exit 0. Its checks include: a quote `flush() before close().`
  graded against source text `flush() before\n   close().` gives `pass`; a
  word-reordered quote gives `fail`; a quote absent from the text gives `fail`;
  a quote under the length floor gives `fail`.
- If the procedure is skipped (byte-exact `ev in text`), the re-wrapped quote
  check prints FAIL and the command exits 1. If matching is loosened to word
  sets, the reordered-quote check fails instead.
- Minimal check for a codebase without that suite:
  ```python
  t = "1. Call flush() before\n   close().\n"
  assert gate(quote="flush() before close().", text=t)        # re-wrapped: accepted
  assert not gate(quote="close() before Call flush().", text=t)  # reordered: rejected
  ```
