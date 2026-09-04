---
name: lossy-transform-false-negative
kind: antiskill
scope: project
description: >
  A transform applied before a match - truncation, capping, sampling - hides
  part of the search space, and the negative result is reported as a
  confident "absent" instead of "unknown". Use when: a matcher, scanner or
  probe returns a definite negative and the data it examined was capped,
  truncated, or sampled first. Do NOT use when: the whole input really was
  examined and the match genuinely is not there.
symptoms:
  - "returned 0 when the searched region was truncated"
  - "confirmed absent without examining the full input"
fingerprints:
  - "unknown = True"
  - "return None if unknown else 0"
provenance:
  repo: skill-forge
  distilled: 2026-08-10
---

## Trap

A search routine bounds its own work - reads only the first N candidate
files, only the first N bytes of each, only the first N probes - and then
returns a two-valued answer: found or not-found. The bound is invisible in
the return value, so "I looked everywhere and it is not there" and "I looked
at part of it and did not see it" collapse into the same answer.

## Symptom

A definite negative for input that was never fully examined: a scan reports
absent while the match sits past the cap, or a probe reports clean because
the budget ran out before it got there. Nothing errors, and the caller has no
way to tell the two cases apart.

## Cause

Bounds are added for latency or memory, separately and later from the
function's return contract, which was written as a boolean when the work was
still unbounded. Each cap is locally correct - it does bound the work - and
the loss of information is only visible where the caps meet the return type.

## Fix

Make the return three-valued: found, absent, unknown. Every place that
truncates, caps, or samples must set the unknown flag when it discards
unexamined input AND no match was found, so the function returns unknown
rather than absent. A positive result stays valid under truncation - finding
it early is proof - but a negative is only "absent" if the search was
complete. Then check the caller treats unknown as its own case rather than
coercing it to false.

## Cost of rediscovery

~40 min (observed in source session)
