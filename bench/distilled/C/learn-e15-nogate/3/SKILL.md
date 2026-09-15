---
name: whitespace-insensitive-evidence-match
kind: skill
scope: project
description: >
  How validate.verdict_from must match a critique finding's quoted `evidence`
  span against the skill text: whitespace-collapsed on both sides, still
  order-sensitive, length floor applied to the collapsed span.
  Use when: writing or editing verdict_from or any check that a model-written
  quote "appears verbatim" in a source document; a critique grades a skill
  `fail` although every criterion is ok and the quote is visibly in the file.
  Do NOT use when: the fail comes from `ok` not being literal True, from a
  blocking textual objection, or from a span shorter than MIN_EVIDENCE_CHARS;
  or when the comparison is of code/commands where whitespace is meaningful.
verification.command: python3 -c "import sys; sys.path.insert(0,'scripts'); import validate as v; t='## Procedure\n1. Call flush() before\n   close().\n'; ok=lambda e:[{'criterion':c,'ok':True,'evidence':e} for c in v.SKILL_CRITERIA]; assert v.verdict_from(ok('flush() before close().'),t)=='pass'; assert v.verdict_from(ok('close() before Call flush().'),t)=='fail'; assert v.verdict_from(ok('appears nowhere in the skill'),t)=='fail'"
fingerprints:
  - '" ".join((f.get("evidence") or "").split())'
  - 'ev not in " ".join(text.split())'
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-3
  commit: 2909d68
  distilled: 2026-09-15
---

## Procedure
1. Normalise the quoted evidence by collapsing every whitespace run
   (spaces, tabs, newlines) to one space and trimming the ends:
   `ev = " ".join((f.get("evidence") or "").split())`.
2. Normalise the skill text the same way, and test containment against that
   result: `ev not in " ".join(text.split())`. Both sides must be normalised.
   If only the quote is, a hard-wrapped span in the file still fails to match.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the normalised `ev`, so padding a
   short span with whitespace cannot get it past the floor.
4. Keep the plain substring test. Do not switch to word sets, sorted tokens
   or fuzzy ratios. The gate stops sycophancy because a model cannot produce
   the words in the right order without reading the file, and reordered
   words must still fail.
5. Leave the other gates as they are: `ok is not True` still fails closed,
   and a span that appears nowhere in the text still fails.

## Gotchas
- Critique models re-wrap hard-wrapped prose when they quote it, and they do
  it inconsistently within one reply. Byte-exact matching fails a skill that
  passes on substance because of a single newline.
- `.strip()` alone is not enough. It only trims the ends, so a newline plus
  indentation inside the span still breaks the match.

## Verification
- Run `verification.command` from the repo root. It exits 0 only when all
  three hold: (a) a quote whose line break the file has but the quote
  replaces with a space grades `pass`; (b) the same words reordered grade
  `fail`; (c) a span absent from the text grades `fail`.
- With byte-exact matching (the skill not applied), (a) raises
  AssertionError and the command exits 1. If the check is loosened to word
  sets, (b) fails instead.
