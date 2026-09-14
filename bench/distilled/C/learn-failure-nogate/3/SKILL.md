---
name: verbatim-quote-gate-breaks-on-rewrapped-llm-quotes
kind: antiskill
scope: global
description: >
  A "the model must quote the source verbatim" check done with a byte-exact
  substring test rejects real quotes because LLMs re-wrap hard-wrapped prose.
  Use when: an evidence/citation gate compares a model-supplied quote to a
  source text with `quote in text` and correct outputs fail on quotes that
  span a line break.
  Do NOT use when: the quote genuinely differs in words or word order (that
  must still fail), or the source is code where whitespace is significant.
symptoms:
  - "verdict_from(_all_ok(unwrapped), text) == \"pass\""
  - "rewrapped quote still counts as evidence"
fingerprints:
  - "\" \".join(text.split())"
  - "not in \" \".join("
provenance:
  repo: sf-repair-verdict-from-distill-learn-failure-nogate-3
  distilled: 2026-09-14
---

## Trap
An anti-sycophancy gate that accepts a finding only if its quoted evidence is
in the source: `ev = quote.strip(); ok = ev in text`. It looks exact and
safe. But the model quotes hard-wrapped prose like
`flush() before\n   close().` as `flush() before close().`, and it isn't
consistent about it even within one reply. The byte-exact test then fails
correct verdicts over a single newline, and the quote gate ends up blocking
honest output instead of sycophantic output.

## Symptom
A verdict comes back `fail` even though every criterion is `ok: true` and
the evidence span is plainly in the file when you read it. In tests:
`AssertionError` in something like
`test_a_rewrapped_quote_still_counts_as_evidence`, where
`verdict_from(_all_ok(unwrapped), text) == "pass"` fails. The misleading
part: it makes you suspect the model is inventing quotes, or that parsing or
the `ok is not True` check is broken. The real difference is whitespace only.

## Cause
`str.__contains__` compares whitespace byte for byte. `.strip()` only trims
the ends of the quote. It does nothing about a newline and indentation in
the middle of the source.

## Fix
Collapse whitespace runs on BOTH sides before comparing, and apply the
minimum-length floor to the normalised quote:

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

Normalise whitespace only. Don't sort tokens, compare bags of words, or use
fuzzy ratios. Reordered words (`close() before Call flush().`) and spans
absent from the text must still fail, because the gate exists to prove the
model actually read the text.

## Cost of rediscovery
~5 min (observed in source session; the failing test's docstring stated the
mechanism outright, so without that it would cost more)
