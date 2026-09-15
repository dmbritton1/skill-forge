---
name: e14-quote-gate-rewrap-aw
kind: antiskill
scope: project
description: >
  A verbatim-quote evidence gate, such as validate.verdict_from, that checks a
  model's quoted span against the source text with a byte-exact substring test
  rejects real quotes that differ from the source only by whitespace.
  Use when: writing or editing a gate that checks model-quoted evidence against source text with a substring test, e.g. `evidence in text`.
  Do NOT use when: the quote differs in words, punctuation or word order (that
  must keep failing); or the comparison is of code where whitespace matters.
symptoms:
  - "verdict fail although every criterion is ok"
  - "evidence not in text"
fingerprints:
  - "\" \".join(text.split())"
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
---

## Trap
Checking each passing finding's quote with
`ev = (f.get("evidence") or "").strip()` followed by
`if len(ev) < MIN_EVIDENCE_CHARS or ev not in text` looks like the strictest,
safest anti-sycophancy check. But models re-wrap hard-wrapped prose when they
quote it, so a real quote of `flush() before\n   close().` comes back as
`flush() before close().`, and the byte-exact test rejects it.

## Symptom
The gate returns `"fail"` for a finding whose quote is visibly in the source
text, and no exception is raised.

## Cause
`.strip()` only trims the ends of the quote. A newline and indentation inside
the source still have to match byte for byte.

## Fix
Collapse whitespace runs on BOTH sides, and apply the `MIN_EVIDENCE_CHARS`
floor to the collapsed span:

```python
ev = " ".join((f.get("evidence") or "").split())
if len(ev) < MIN_EVIDENCE_CHARS or ev not in " ".join(text.split()):
    return "fail"
```

Collapsing only the evidence is not enough: the newline is in the source text.
Leave the `ok is not True` check and the `blocks()` logic unchanged. Do not
switch to word-set, sorted-token or fuzzy matching. A reordered quote such as
`close() before Call flush().` can be written without reading the source, and
must still fail.
