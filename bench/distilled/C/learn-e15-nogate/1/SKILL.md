---
name: whitespace-insensitive-evidence-quote-check
kind: skill
scope: project
description: >
  How validate.verdict_from must match a model-quoted `evidence` span against the skill text: collapse whitespace on both sides, keep the length floor and word order.
  Use when: writing or editing verdict_from or any check that a critique/LLM reply's "verbatim" quote appears in a source document; a skill whose criteria all pass on substance is graded fail because the quote spans a line break.
  Do NOT use when: the comparison is meant to be byte-exact (hashes, signatures, patch application), or the problem is the ok/severity/basis grading rather than the quote match.
verification.command: "python3 -c \"import sys; sys.path.insert(0, 'scripts'); import validate as v; t='1. Call flush() before'+chr(10)+'   close().'; ok=lambda e: [{'criterion': c, 'ok': True, 'evidence': e} for c in v.SKILL_CRITERIA]; assert v.verdict_from(ok('flush() before close().'), t) == 'pass'; assert v.verdict_from(ok('close() before Call flush().'), t) == 'fail'; assert v.verdict_from(ok('flush()'), t) == 'fail'\""
fingerprints:
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
  - "ev not in \" \".join(text.split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-1
  commit: 2e9916b
  distilled: 2026-09-15
---

## Procedure
1. Treat a model's "verbatim" quote as verbatim in words, not in whitespace. When a model quotes hard-wrapped prose it re-wraps it, and it does not do so consistently even within one reply. A newline in the source often comes back as a single space.
2. Normalise both sides the same way before the containment test: `" ".join(s.split())`. This collapses every run of spaces, tabs and newlines to one space and strips the ends.
3. Apply the minimum-length floor (`MIN_EVIDENCE_CHARS`) to the normalised evidence. Otherwise padding with whitespace gets a too-short quote past the floor.
4. Keep the test a substring match on the normalised strings: `ev not in " ".join(text.split())`. Order matters: a span with its words reordered, or one that appears nowhere in the text, must still fail.
5. Leave everything else in the gate fail-closed. A finding still needs `ok is True`, and an unquotable pass still returns `fail` whatever its severity or basis.

## Gotchas
- Do not "fix" this with case-folding, punctuation stripping or token-set/bag-of-words matching. Each one loosens the anti-sycophancy property that a real quote cannot be produced without reading the text.
- Normalising only the evidence and not the text (or the reverse) still misses: the source keeps its newline plus indentation, and the quote has one space.
- `.strip()` alone is not enough. It only touches the ends, and the mismatch is inside the span.

## Verification
- `python3 -c "…"` (the `verification.command` above), run from the repo root. It builds a text with a hard-wrapped `flush() before\n   close().` and asserts three things. The one-line quote `flush() before close().` passes. A reordered quote fails. A quote below the length floor fails.
- If the procedure was NOT followed (byte-exact `ev not in text`), the first assertion raises `AssertionError` and the command exits non-zero. If matching was made order-insensitive or the floor was dropped, the second or third assertion fails instead.
