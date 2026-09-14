---
name: verbatim-quote-gate-breaks-on-rewrapped-text
kind: antiskill
scope: global
description: >
  A "the model must quote the source verbatim" check done as a byte-exact
  substring match rejects real quotes whose only difference is a line break.
  Use when: an LLM-evidence / citation gate fails a reply whose quoted span
  plainly exists in the source but crosses a hard-wrapped line.
  Do NOT use when: the quoted words really are absent, paraphrased, or
  reordered -- those must keep failing.
symptoms:
  - "verdict fail although every criterion is ok"
  - "evidence not in text"
  - "rewrapped quote still counts as evidence"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
provenance:
  repo: sf-repair-verdict-from-distill-learn-failure-nogate-1
  distilled: 2026-09-14
---

## Trap
Checking model-quoted evidence with `ev.strip()` then `ev not in text` looks
like the strictest, safest anti-sycophancy check. But models normalise
whitespace when they quote hard-wrapped prose, and they do it inconsistently
within a single reply. So a quote taken from `"flush() before\n   close()."`
comes back as `"flush() before close()."`, and the byte-exact match rejects it.

## Symptom
`verdict_from(...)` returns `"fail"` for a reply where every finding has
`ok: true` and the evidence span is visibly in the skill text. No exception is
raised. The failing test is `test_a_rewrapped_quote_still_counts_as_evidence`
(`AssertionError()`). This makes you suspect the grading or severity logic
(`blocks()`, `ok is not True`), or the length floor. None of them is the cause.

## Cause
`.strip()` removes whitespace only at the ends of the span. The newline and
indentation inside the source still have to match exactly, and a quote the
model has rewrapped cannot match.

## Fix
Collapse runs of whitespace on **both** sides before the substring test, and
apply the length floor to the collapsed span:

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

Do not go further and compare word sets or sorted tokens. That would pass a
reordered quote such as `"close() before Call flush()."`, which the model can
write without ever reading the source, and the gate exists to stop exactly
that. The check should ignore whitespace but still require the words in order.

## Cost of rediscovery
~5 min (observed in source session: one failing test, fixed in a single edit;
the risk is the overcorrection to order-insensitive matching, not the search)
