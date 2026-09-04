---
name: serialization-corrupts-matching
kind: antiskill
scope: project
description: >
  Data is serialized on the way into a text matcher, and the serializer's
  escaping rewrites the very characters the matcher tokenizes on, so real
  matches silently fail. Use when: a matcher works on hand-built string
  fixtures but misses the same content arriving as a structured object.
  Do NOT use when: the pattern itself is wrong - check a plain-string input
  first to tell the two apart.
symptoms:
  - "matched the string fixture but not the dict payload"
  - "token glued to the start of the next line"
fingerprints:
  - "json.dumps(resp"
  - "isinstance(v, str)"
provenance:
  repo: skill-forge
  distilled: 2026-08-10
---

## Trap

A matcher accepts either a string or a structured object. For the structured
case someone reaches for the nearest flattener - `json.dumps`, `repr`,
`str()` on a dict - to get text to match against. All three escape control
characters: a real newline becomes the two characters backslash and n. The
tokenizer then reads that `n` as an ordinary character and glues it onto the
adjacent word.

## Symptom

The matcher works perfectly on string fixtures and silently fails on real
structured input. Any pattern whose first token begins a line stops matching,
because that token now carries a leading `n`. Nothing raises; the feature
just never fires, and a test suite built from string fixtures stays green.

## Cause

Serializing and flattening are different jobs. A serializer's contract is
round-trip fidelity, which requires escaping; a matcher wants the original
bytes. Reaching for the serializer is convenient and wrong, and the damage is
invisible unless a fixture happens to put the pattern somewhere other than
the very start of a value.

## Fix

Flatten without escaping: walk the structure and collect its string leaves,
joining them with real separators, rather than serializing it. Cap the
recursion depth so a pathological input cannot blow the stack. Then add a
test whose signature does NOT start at offset zero of a value - second line
of a multi-line string, and nested one level down - because a fixture with
the pattern at the start passes under both the broken and the fixed version.

## Cost of rediscovery

~50 min (observed in source session)
