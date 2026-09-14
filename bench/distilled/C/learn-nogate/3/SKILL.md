---
name: whitespace-tolerant-quote-evidence
kind: skill
scope: project
description: >
  Make a verbatim-quote evidence gate (LLM critique must quote the text it
  judges) accept re-wrapped quotes without accepting invented or reordered ones.
  Use when: an LLM-judge / critique verdict fails a quote that is really in the
  source text but differs by a newline or indentation; editing
  validate.verdict_from or any `evidence in text` containment check over
  model-written spans.
  Do NOT use when: the evidence should match fuzzily (paraphrase, reordered
  words, case changes) -- that disables the anti-sycophancy gate; or the check
  compares structured data rather than prose quotes.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-nogate-3
  commit: 55820b9
  distilled: 2026-09-14
---

## Procedure
1. Find the containment check on the model's quote, e.g.
   `ev = (f.get("evidence") or "").strip()` followed by `ev not in text`.
   Byte-exact matching fails a real quote whenever the model re-wraps
   hard-wrapped prose, which it does inconsistently even inside one reply.
2. Normalise BOTH sides the same way: collapse every whitespace run to a
   single space with `" ".join(s.split())`. Apply it to the evidence and to the
   source text, then do the same `in` check.
3. Apply the minimum-length floor (e.g. `MIN_EVIDENCE_CHARS`) to the
   normalised span, so padding a short quote with spaces cannot get past it.
4. Leave every other gate unchanged: the `ok is not True` check and the
   blocking-severity logic have nothing to do with whitespace.

## Gotchas
- Collapse whitespace to one space; do not delete it. With
  `"".join(s.split())`, words that were separate in the source can match a
  quote that runs them together.
- Normalising only the evidence is not enough. The newline is in the source
  text, so `"flush() before close()."` still misses
  `"flush() before\n   close()."` unless the text is collapsed too.
- Do not reach for difflib, lowercasing, or token-set matching. The point of
  the gate is that a real quote cannot be produced without reading the text,
  so reordered words must still fail.

## Verification
- `python3 tests/test_validate.py` should exit 0 with every line `PASS`.
  If the procedure is skipped, `test_a_rewrapped_quote_still_counts_as_evidence`
  prints `FAIL ... AssertionError()` and the script exits non-zero. It did
  exactly that at commit 55820b9 before the fix. Going too far (word-order-
  or length-insensitive matching) fails
  `test_reordered_words_are_not_accepted_as_a_quote`,
  `test_evidence_absent_from_the_text_still_fails` or
  `test_evidence_shorter_than_the_floor_still_fails` instead.
