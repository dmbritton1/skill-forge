---
name: matcher-input-traps
kind: antiskill
scope: project
description: >
  Input reaching a text matcher is altered on the way in - escaped by a
  serializer, or cut short by a cap - so a real match is reported as a
  confident absence. Use when: a matcher, scanner or probe returns a definite
  negative and the input was serialized, escaped, truncated, capped or
  sampled before it got there. Do NOT use when: the pattern itself is wrong -
  check a plain, whole-string input first to tell the two apart.
# The union of both parents' symptoms, verbatim. E1 varies ONE thing --
# whether the knowledge is packaged as one general anti-skill or two specific
# ones -- so the trigger surface must be identical to the two it replaces.
symptoms:
  - "matched the string fixture but not the dict payload"
  - "token glued to the start of the next line"
  - "returned 0 when the searched region was truncated"
  - "confirmed absent without examining the full input"
# One from each parent's FIX side, not the trap side: the umbrella covers
# both classes, so it should mark either correction landing in a file.
fingerprints:
  - "isinstance(v, str)"
  - "return None if unknown else 0"
provenance:
  repo: dmbritton1/skill-forge
  distilled: 2026-09-05
---

## Trap

Two different things happen to input before a matcher sees it, and both turn
a real match into a reported absence.

**The input is serialized.** A matcher accepts either a string or a
structured object, and for the structured case someone reaches for the
nearest flattener - `json.dumps`, `repr`, `str()` on a dict. All three escape
control characters: a real newline becomes the two characters backslash and
n. The tokenizer then reads that `n` as an ordinary character and glues it
onto the adjacent word.

**The input is cut short.** A search routine bounds its own work - the first
N candidate files, the first N bytes of each, the first N probes - and still
returns a two-valued answer. The bound is invisible in the return value, so
"I looked everywhere and it is not there" and "I looked at part of it and did
not see it" collapse into the same answer.

## Symptom

The matcher works perfectly on hand-built string fixtures and silently fails
on real input. Under escaping, any pattern whose first token begins a line
stops matching, because that token now carries a leading `n`. Under a cap, a
scan reports absent while the match sits past the ceiling. Nothing raises in
either case; the feature just never fires, and a suite built from string
fixtures stays green.

## Cause

Both are the same mistake at different points on the input path: a stage that
was added for another purpose changed what the matcher receives, and the
return contract was never widened to say so.

Serializing and flattening are different jobs - a serializer's contract is
round-trip fidelity, which requires escaping, while a matcher wants the
original bytes. Bounds are added for latency or memory, separately and later
than a return type that was written as a boolean when the work was still
unbounded. Each stage is locally correct. The damage only shows where it
meets the matcher.

## Fix

Flatten without escaping: walk the structure and collect its string leaves,
joining them with real separators, rather than serializing it. Cap the
recursion depth so a pathological input cannot blow the stack.

Make the return three-valued: found, absent, unknown. Every place that
truncates, caps, or samples must set the unknown flag when it discards
unexamined input AND no match was found. A positive result stays valid under
truncation - finding it early is proof - but a negative is only "absent" if
the search was complete. Check the caller treats unknown as its own case
rather than coercing it to false.

Then add a test whose signature does NOT start at offset zero of a value -
second line of a multi-line string, and nested one level down - because a
fixture with the pattern at the start passes under both the broken and the
fixed version.

## Cost of rediscovery

~90 min (observed in source session)
