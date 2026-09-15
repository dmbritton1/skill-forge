---
name: verbatim-evidence-whitespace-normalize
kind: skill
scope: global
description: >
  Matching an LLM judge's quoted "evidence" span against the source text (e.g. a verdict_from(findings, text) gate) must collapse whitespace runs on both sides before the substring check, while keeping word order and the minimum-length floor.
  Use when: writing or editing code that accepts a model's verbatim quote as proof (evidence/citation/quote fields checked with `in text`), or when a judge's pass on hard-wrapped prose is rejected over a newline or indentation difference.
  Do NOT use when: the quote must match byte-for-byte (hashes, code diffs, signatures), when fuzzy or semantic matching is actually wanted, or when the source has no line wrapping.
verification.command: "python3 tests/test_validate.py"
fingerprints:
  - '" ".join((f.get("evidence") or "").split())'
  - 'ev not in " ".join(text.split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-2
  commit: f87c2ef
  distilled: 2026-09-15
---

## Procedure
1. Normalise the quoted span by collapsing every whitespace run to one space
   and trimming the ends: `ev = " ".join((f.get("evidence") or "").split())`.
   Models re-wrap quoted prose inconsistently, even within a single reply, so a
   raw `ev in text` fails a real quote over one newline plus indentation.
2. Normalise the source text the same way before the containment check:
   `ev not in " ".join(text.split())`. Normalising only one side does not work:
   the source still holds `before\n   close()` while the quote says
   `before close()`.
3. Apply the minimum-length floor (e.g. `len(ev) < MIN_EVIDENCE_CHARS`) to the
   NORMALISED span, so padding a short span with spaces or newlines cannot get
   it past the floor.
4. Keep it a substring check on ordered text. Do not switch to token sets, word
   bags or similarity ratios: the gate is supposed to prove the judge actually
   read the text, and reordered words must still fail.
5. Keep failing closed. A non-`True` `ok`, a missing or short span, or a span
   that is absent after normalising all still mean `fail`.

## Gotchas
- `str.split()` with no argument splits on every Unicode whitespace run
  (newline, tab, NBSP) and drops empty strings. `split(" ")` does not, and
  misses newlines.
- Don't normalise case or punctuation as well. That starts accepting
  paraphrases, and the anti-sycophancy property goes away.

## Verification
- `python3 tests/test_validate.py` should exit 0. With the procedure skipped
  (a raw `ev in text`), it exits 1: a quote whose only difference from the
  skill text is a line break plus indentation is graded `fail` when it should
  be `pass`. The same run checks that the gate is still on. Evidence that
  appears nowhere, evidence shorter than the floor, and the same words in a
  different order must all still be graded `fail`.
