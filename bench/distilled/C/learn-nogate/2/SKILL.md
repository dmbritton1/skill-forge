---
name: whitespace-insensitive-evidence-quotes
kind: skill
scope: project
description: >
  Match an LLM's "verbatim quote" evidence against source text with
  whitespace runs collapsed on both sides, keeping word order and the length
  floor strict.
  Use when: a verdict/critique gate (e.g. validate.verdict_from) rejects a
  model finding whose quoted evidence differs from the source only by line
  wrapping or indentation; a test like test_a_rewrapped_quote_still_counts_as_evidence fails.
  Do NOT use when: the evidence is missing words, reorders words, or is
  shorter than the minimum length -- those must still fail; or when the
  comparison is of code/commands where whitespace is significant.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - "flat_text = \" \".join(text.split())"
  - "ev not in flat_text"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-nogate-2
  commit: e68c710
  distilled: 2026-09-14
---

## Procedure
1. Find the evidence check in the gate. In `scripts/validate.py`,
   `verdict_from(findings, text)` had
   `ev = (f.get("evidence") or "").strip()` and
   `if len(ev) < MIN_EVIDENCE_CHARS or ev not in text: return "fail"`.
   That is a byte-exact substring test, so a hard-wrapped line quoted as
   one line never matches.
2. Before the loop over findings, flatten the source text once:
   `flat_text = " ".join(text.split())`.
3. Flatten each quote the same way instead of only stripping it:
   `ev = " ".join((f.get("evidence") or "").split())`.
4. Keep both conditions, just against the flattened strings:
   `if len(ev) < MIN_EVIDENCE_CHARS or ev not in flat_text: return "fail"`.
   The length floor is checked on the flattened quote, so padding a short
   span with spaces or newlines cannot get it past the floor.
5. Leave every other check alone: the `f.get("ok") is not True` test and
   the `blocks(f)` severity/basis filter are separate from quote matching.

## Gotchas
- Flatten BOTH sides. If you flatten only the quote, a quote that is really
  in the text fails whenever the source has a newline or indent in that span.
- Collapse whitespace only. Do not lowercase, strip punctuation, or match
  words as a set: `test_reordered_words_are_not_accepted_as_a_quote` and
  `test_evidence_absent_from_the_text_still_fails` require that a quote you
  could write without reading the file still fails.
- `str.split()` with no argument splits on any run of whitespace, including
  `\n`, `\t` and repeated spaces, and drops leading and trailing whitespace.
  `split(" ")` does not do this.
- `scripts/library.py` also reads `evidence`, but only to print it. It is
  not a gate, so it needs no change.

## Verification
- `python3 tests/test_validate.py` should print only `PASS` lines and exit 0.
- If the procedure was NOT applied (byte-exact `ev not in text`),
  `test_a_rewrapped_quote_still_counts_as_evidence` prints
  `FAIL ... AssertionError()` and the script exits 1. If matching was made
  too loose (for example, word sets), the reordered-words or absent-evidence
  tests fail and the script exits 1.
