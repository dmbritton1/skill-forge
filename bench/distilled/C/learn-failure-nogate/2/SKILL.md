---
name: verbatim-quote-check-breaks-on-rewrapped-whitespace
kind: antiskill
scope: global
description: >
  A byte-exact `quote in source` check on LLM-quoted evidence fails real quotes
  whose line breaks or indentation the model re-wrapped.
  Use when: a gate checks that model output quotes a document verbatim
  (evidence spans, citations, grounding checks), and it rejects quotes that
  are clearly in the source.
  Do NOT use when: the quote really changes words or word order. That is a
  genuine mismatch and should still fail. Also skip this if the source is
  code, where whitespace carries meaning.
symptoms:
  - "rewrapped quote still counts as evidence AssertionError"
  - "verdict fail despite every criterion ok"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
provenance:
  repo: sf-repair-verdict-from-distill-learn-failure-nogate-2
  distilled: 2026-09-14
---

## Trap
`ev = evidence.strip(); ok = ev in text` looks like the strictest and safest
anti-sycophancy check. But a model quoting hard-wrapped prose normalises
whitespace, and it does so inconsistently within a single reply.
`"flush() before close()."` is not a substring of `"flush() before\n   close()."`,
so a quote that is correct in substance fails.

## Symptom
The gate returns `fail` (e.g. `verdict_from(...) == "fail"`, or
`AssertionError` in a test like `test_a_rewrapped_quote_still_counts_as_evidence`).
Every finding has `ok: true` and a quote that visibly appears in the document.
This makes you suspect the model hallucinated the span or the severity or
length-floor logic is wrong. The only real difference is a newline plus
indentation.

## Cause
Python's `in` compares bytes exactly. `.strip()` only trims the ends of the
quote. It does nothing about whitespace runs inside the quote or inside the
source text.

## Fix
Collapse whitespace runs on BOTH sides before matching. Apply the length floor
to the normalised quote. Do not switch to token-set or fuzzy matching, because
word order must still count (a reordered "quote" must fail):

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

## Cost of rediscovery
~3 min (observed in source session, where a failing test pointed straight at
it). Without that test it shows up as a skill that is spuriously rejected.
