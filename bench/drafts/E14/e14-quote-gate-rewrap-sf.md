---
name: e14-quote-gate-rewrap-sf
kind: skill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: a verbatim-quote evidence gate fails a quote that differs from the source text only by line breaks or indentation.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Procedure
1. The gate is the check on each passing finding's quote. The naive version is
   `ev = (f.get("evidence") or "").strip()` followed by
   `if len(ev) < MIN_EVIDENCE_CHARS or ev not in text`.
2. Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
   floor to the collapsed span:
   ```python
   ev = " ".join((f.get("evidence") or "").split())
   if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
       return "fail"
   ```
3. Leave the `ok is not True` check and the `blocks()` logic unchanged.

## Gotchas
- Models re-wrap hard-wrapped prose when they quote it, so a real quote of
  `flush() before\n   close().` comes back as `flush() before close().`, and a
  byte-exact test rejects it. `.strip()` only trims the ends of the quote.
- Collapsing only the evidence is not enough: the newline is in the source text.
- Do not switch to word-set, sorted-token or fuzzy matching. A reordered quote
  such as `close() before Call flush().` can be written without reading the
  source, and must still fail.

## Verification
- `python3 tests/test_validate.py` exits 0 with every line `PASS`.
- A quote that differs from the source only by a line break yields `"pass"`;
  the same words reordered yield `"fail"`.
