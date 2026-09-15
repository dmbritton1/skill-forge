---
name: whitespace-insensitive-evidence-quote-gate
kind: skill
scope: project
description: >
  How verdict_from in scripts/validate.py must match a critique finding's quoted
  evidence against the skill text: collapse whitespace on both sides, keep word order.
  Use when: writing or editing verdict_from, the evidence/quote check of an LLM-judge
  gate, or any "the model must quote the source verbatim" check; or when a
  correct quote is rejected because the model rewrapped a line.
  Do NOT use when: the check is about criterion grading (ok/severity/basis) rather
  than quote matching, or exact byte matching is actually required (hashes, code diffs).
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "flat = \" \".join(text.split())"
  - "ev not in flat"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-1
  commit: 5beff9d
  distilled: 2026-09-15
---

## Procedure
1. Normalise the source text once, before looping over findings:
   `flat = " ".join(text.split())`. This turns every run of spaces, tabs and
   newlines into a single space.
2. Normalise each finding's evidence the same way:
   `ev = " ".join((f.get("evidence") or "").split())`. This also does the job
   `.strip()` did, so drop the `.strip()`.
3. Apply the length floor to the normalised `ev`
   (`len(ev) < MIN_EVIDENCE_CHARS`), then require a substring match:
   `ev not in flat` → `"fail"`.
4. Leave every other rule as it was: only a literal `ok is True` counts as a
   pass, and an unquotable pass fails no matter how it was graded.

## Gotchas
- Models rewrap hard-wrapped prose when they quote it, and not consistently
  within one reply. With byte-exact `ev in text`, a skill fails on a single
  newline even when every criterion passed on substance.
- Collapse whitespace to one space. Do not delete it: deleting it would
  accept run-together text like "flushbefore".
- Do not go further and match a bag of words or ignore case. The point of the
  gate is that a quote cannot be produced without reading the text, so
  reordered words must still fail.
- Normalise both sides. If only the evidence is normalised, a source that
  contains a newline plus indentation still misses.

## Verification
- `python3 tests/test_validate.py` should exit 0. It checks four things: a
  quote whose line break became a space passes; a span that is not in the
  text fails; a span below the length floor fails; reordered words fail.
  Without the normalisation (byte-exact `ev in text`) the rewrapped-quote case
  fails and the command exits 1. I checked this by stashing the fix.
