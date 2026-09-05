---
name: matcher-input-traps
kind: skill
scope: project
description: >
  Input reaching a text matcher can be altered on the way in, so a real match
  is reported as a confident absence.
  Use when: a matcher, scanner or probe returns a definite negative and the
  input was serialized, escaped, truncated, capped or sampled before it got
  there.
  Do NOT use when: the pattern itself is wrong — check a plain, whole-string
  input first to tell the two apart.
verification.command: "python3 tests/test_detect.py"
# One from each parent's FIX side, not the trap side: the umbrella covers
# both classes, so it should mark either correction landing in a file.
fingerprints:
  - "isinstance(v, str)"
  - "return None if unknown else 0"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-09-05
---

## Procedure

Two things happen to input before a matcher sees it, and both turn a real
match into a reported absence. Check each against the path you are writing.

1. **Serialization rewrites what the matcher tokenizes on.** If the input is
   a structured object, do not hand the serializer's output to the matcher:
   `json.dumps` escapes newlines to `\n`, quotes to `\"`, and non-ASCII to
   `\uXXXX`, so the very characters the tokenizer splits on are gone. Walk
   the structure and collect its string leaves instead, unescaped.

2. **A transform hides part of the search space.** If the input was
   truncated, capped, or sampled first — a byte ceiling, a file limit, a head
   -n — then a negative result means "not in the part I looked at", not
   "absent". Either examine the whole input, or report the negative as
   unknown rather than as a confident no.

The shared shape: the matcher is correct and the input is not what you think
it is. When a matcher works on hand-built string fixtures but misses the same
content arriving through the real path, suspect the path, not the pattern.

## Gotchas

- A partial probe that finds nothing is `None`/unknown, never `0`/absent.
  Reporting it as absent silently suppresses whatever the match would have
  enabled downstream.

- Escaping damage is invisible in a debugger that prints the decoded value.
  Compare the bytes the matcher actually receives against the bytes you
  expect it to receive.

## Verification

- `python3 tests/test_detect.py` exits 0.

  The suite feeds the matcher content through the real structured path as
  well as a plain string. A matcher fed serialized text passes the string
  case and fails the structured one, which is the asymmetry these traps
  produce.
