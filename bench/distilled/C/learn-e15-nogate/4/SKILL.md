---
name: whitespace-insensitive-evidence-quote-gate
kind: skill
scope: project
description: >
  How validate.verdict_from should check that a critique finding's quoted `evidence` span really appears in the skill text: collapse whitespace on both sides, keep word order and the MIN_EVIDENCE_CHARS floor.
  Use when: writing or editing verdict_from or any other check that a model-written quote must appear verbatim in a source document; when a skill fails critique even though every criterion is ok and its evidence differs from the text only in line breaks or indentation.
  Do NOT use when: the finding is not ok (the severity/basis rules decide those); the comparison is between code or other whitespace-significant text; you want fuzzy or paraphrase matching (that turns the anti-sycophancy gate off).
verification.command: >-
  python3 -c 'import sys; sys.path.insert(0, "scripts"); import validate as v; ok = lambda e: [{"criterion": c, "ok": True, "evidence": e} for c in v.SKILL_CRITERIA]; t = "1. Call flush() before" + chr(10) + "   close()." + chr(10); assert v.verdict_from(ok("flush() before close()."), t) == "pass", "rewrapped quote rejected"; assert v.verdict_from(ok("close() before flush()."), t) == "fail", "reordered words accepted"; assert v.verdict_from(ok("flush()"), t) == "fail", "sub-floor span accepted"'
fingerprints:
  - '" ".join((f.get("evidence") or "").split())'
  - 'ev not in " ".join(text.split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-4
  commit: 985bc62
  distilled: 2026-09-15
---

## Procedure
1. For each finding with `ok is True`, normalise its evidence as
   `ev = " ".join((f.get("evidence") or "").split())`. `str.split()` with no
   argument splits on any whitespace run (spaces, tabs, newlines) and drops
   leading and trailing whitespace, so this also does the old `.strip()`.
2. Normalise the skill text the same way, `" ".join(text.split())`, and test
   `ev in` that string. Both sides must be normalised: a quote that joins
   two lines only matches once the newline and indentation in the text
   become a single space.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the *normalised* span, so padding a
   short quote with whitespace cannot get it past the floor.
4. Keep it a substring check on the ordered words. Do not use a set of words,
   a token overlap score or a fuzzy ratio. A real quote must still be
   impossible to produce without reading the text.
5. Any failure (span too short, or not found) still returns `"fail"` right
   away, whatever severity or basis the model gave the finding.

## Gotchas
- Critique models re-wrap hard-wrapped Markdown prose when they quote it, and
  they do it inconsistently, even within one reply. A byte-exact `ev in text`
  fails skills that passed on substance, over a single newline.
- Normalising only the evidence is not enough. The text still has
  `"before\n   close()"`, so the quote still misses.

## Verification
- Run the `verification.command` from the repo root. It builds a skill text
  whose sentence is hard-wrapped with indentation, then checks three things:
  a re-wrapped quote of it passes, the same words reordered fail, and a
  7-character span fails the floor. It should exit 0 silently.
- If the procedure was skipped (byte-exact `ev in text`), the first assert
  fails with `AssertionError: rewrapped quote rejected`. If the match was
  loosened past word order, the second assert fails instead.
