---
name: whitespace-insensitive-evidence-quote-gate
kind: skill
scope: project
description: >
  Matching a model-quoted evidence span against the source text in validate.verdict_from (the critique anti-sycophancy gate) must collapse whitespace on both sides before the substring check.
  Use when: writing or editing verdict_from or any check that a model's "verbatim" quote appears in a document; a critique reply fails a skill whose criteria all passed on substance; changing MIN_EVIDENCE_CHARS or the evidence comparison.
  Do NOT use when: the comparison must be byte-exact by design (hashes, signatures, secret scans); matching fuzzy paraphrase or reordered words; grading severity/basis of objections (blocks()).
verification.command: >
  python3 -c "import sys; sys.path.insert(0, 'scripts'); import validate as v; t = '1. Call flush() before' + chr(10) + '   close().' + chr(10); ok = lambda e: [{'criterion': 'c', 'ok': True, 'evidence': e}]; assert v.verdict_from(ok('flush() before close().'), t) == 'pass', 'rewrapped quote rejected'; assert v.verdict_from(ok('close() before Call flush().'), t) == 'fail', 'reordered words accepted'; assert v.verdict_from(ok('not in the skill text at all'), t) == 'fail', 'absent quote accepted'; assert v.verdict_from(ok('flush()'), t) == 'fail', 'short quote accepted'"
fingerprints:
  - '" ".join((f.get("evidence") or "").split())'
  - 'ev not in " ".join(text.split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-2
  commit: 98acdf7
  distilled: 2026-09-15
---

## Procedure
1. Treat the model's `evidence` field as untrusted prose: default a missing
   value to `""`, then normalise it with `" ".join(ev.split())`. That
   collapses newlines, runs of spaces and indentation into single spaces and
   strips the ends.
2. Normalise the skill text the same way (`" ".join(text.split())`) and do
   a plain substring test (`ev in normalised_text`). Critique models re-wrap
   hard-wrapped Markdown when they quote it, and they are not consistent
   about it even within one reply. So a byte-exact `ev in text` fails good
   skills over a single newline.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the *normalised* span, so padding
   a short quote with whitespace cannot get it past the floor.
4. Change only whitespace. Keep the words in order, keep case and
   punctuation, and do no fuzzy matching. The gate works because a real
   quote cannot be produced without reading the text. Anything looser than
   whitespace (reordered words, paraphrase) turns it back into "looks good".
5. Leave the rest of the gate alone: `ok is not True` still fails closed,
   and an unquotable PASS still returns `fail` whatever its severity or basis.

## Gotchas
- `.strip()` alone is not enough. It fixes leading and trailing whitespace
  but not a newline plus indentation in the middle of the span, and that is
  exactly what re-wrapped list items produce.
- Normalise both sides. If you only normalise the evidence, a single-spaced
  quote still misses wrapped source text.
- Don't loosen the check with case-folding or token-set matching "while
  you're there". A quote with its words reordered must still fail.

## Verification
- `python3 -c "…"` (the `verification.command` above), run from the repo
  root, should exit 0. It checks four cases: a quote of wrapped text
  rewritten on one line passes; the same words reordered fail; a quote that
  isn't in the text fails; a quote shorter than the floor fails.
- If the procedure was NOT followed (a byte-exact `ev not in text`), the
  first assert raises `AssertionError: rewrapped quote rejected` and the
  command exits non-zero. If it was over-applied (word-order- or
  case-insensitive matching), the second assert fails instead.
