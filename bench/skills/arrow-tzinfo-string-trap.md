---
name: arrow-tzinfo-string-trap
kind: antiskill
scope: project
description: >
  A tzinfo argument that arrives as a string is passed straight through to
  datetime construction, so the timezone is silently ignored or rejected.
  Use when: an arrow/datetime factory takes a tz or tzinfo argument and the
  resulting object has the wrong offset, or a tz string raises a type error.
  Do NOT use when: the timezone is already a tzinfo object and the offset is
  still wrong, which is a DST/localization bug rather than this trap.
symptoms:
  - "not recognized as a timestamp or datetime"
  - "tzinfo argument must be None or of a tzinfo subclass"
fingerprints:
  - "TzinfoParser.parse(tz)"
  - "isinstance(tz, str)"
provenance:
  repo: arrow-py/arrow
  distilled: 2020-01-01
---

## Trap

A factory entry point accepts `tz`/`tzinfo` that callers may pass either as a
real tzinfo object or as a string like `"US/Pacific"`. One branch of the
factory parses the string, another forwards it unparsed, and a third forgets
to forward it at all. The parsed branch is the one everybody tests, so the
gap survives.

## Symptom

Either a `ValueError`/`TypeError` complaining that the value is not a tzinfo
or is not recognized, or - worse and more common - no error at all and a
returned object in UTC or local time whose offset silently ignores the
timezone that was asked for.

## Cause

The argument has two admissible types and only one is normalized. Each
overload branch handles the argument separately, so "handled correctly" is a
per-branch property, not a per-function one. Adding a new accepted input type
to the factory adds a branch that nobody remembers to normalize.

## Fix

Normalize the timezone once, at the top of the entry point, before any
branch runs: if it is a string, parse it into a tzinfo object
(`TzinfoParser.parse(tz)` in arrow), then let every branch use the parsed
value. Then check every branch of the factory - including the ones for input
types added later - actually forwards it, and forwards it by keyword rather
than position, since a positional pass can land on a different parameter.

## Cost of rediscovery

~45 min (observed in source session)
