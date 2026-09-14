---
name: whitespace-insensitive-evidence-gate
kind: skill
scope: project
description: >
  Make a verbatim-quote evidence check (a model's quoted span must appear in the
  source text) tolerant of re-wrapped whitespace without letting reordered or
  invented quotes through.
  Use when: validate.verdict_from (or any "evidence must be in the text" gate)
  fails a finding whose quote differs from the source only by newlines, indentation
  or runs of spaces; when a test like test_a_rewrapped_quote_still_counts_as_evidence fails.
  Do NOT use when: the quote differs in words, punctuation or word order (that is a
  real mismatch and must keep failing); when the gate is meant to be byte-exact
  (hashes, signatures, code diffs).
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-nogate-1
  distilled: 2026-09-14
---

## Procedure
1. Find the substring check in `verdict_from` in `scripts/validate.py`:
   `ev = (f.get("evidence") or "").strip()` followed by `ev not in text`.
2. Collapse whitespace on BOTH sides with the same function, then compare:
   ```python
   ev = " ".join((f.get("evidence") or "").split())
   if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
       return "fail"
   ```
3. Apply the `MIN_EVIDENCE_CHARS` floor to the normalised span, so padding a short
   quote with whitespace cannot get it past the floor.
4. Leave the rest of the gate alone: the `ok is not True` check and the
   `blocks()` severity/basis logic come before this and still apply.

## Gotchas
- If you normalise only the evidence, a quote of hard-wrapped source still misses:
  the source keeps its `\n   ` and the collapsed quote has a single space. Normalise both.
- Do not switch to word-set or fuzzy matching. The gate exists so a model cannot
  pass a criterion without really quoting the text.
  `test_reordered_words_are_not_accepted_as_a_quote` and
  `test_evidence_absent_from_the_text_still_fails` guard against that.

## Verification
- `python3 tests/test_validate.py` should exit 0 with every line `PASS`.
- Without the fix it exits 1 with
  `FAIL test_a_rewrapped_quote_still_counts_as_evidence: AssertionError()`, because
  the byte-exact `in` misses `flush() before close().` against `flush() before\n   close().`.
- If you over-relax the fix (fuzzy or order-insensitive matching), it still exits 1,
  this time through the reordered-words or absent-evidence tests.
