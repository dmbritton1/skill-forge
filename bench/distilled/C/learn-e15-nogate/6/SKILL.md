---
name: verbatim-evidence-whitespace-insensitive
kind: skill
scope: project
description: >
  How validate.verdict_from must match a critique finding's quoted `evidence` span against the skill text: whitespace-insensitive, but still verbatim in word order and above MIN_EVIDENCE_CHARS.
  Use when: writing or editing verdict_from, the evidence gate, or any check that a model-quoted span "appears in" a document; or when a skill whose criteria all pass on substance is graded fail.
  Do NOT use when: changing severity/basis gating (blocks()), the `ok is not True` check, critique prompt wording, or fuzzy/semantic matching of paraphrases.
verification.command: "python3 -c \"import sys; sys.path.insert(0,'scripts'); import validate as v; ok=lambda e:[{'criterion':c,'ok':True,'evidence':e} for c in v.SKILL_CRITERIA]; t='## Procedure\\n1. Call flush() before\\n   close().\\n'; assert v.verdict_from(ok('flush() before close().'),t)=='pass'; assert v.verdict_from(ok('close() before Call flush().'),t)=='fail'; assert v.verdict_from(ok('appears nowhere in the skill'),t)=='fail'; assert v.verdict_from(ok('Call'),t)=='fail'\""
fingerprints:
  - "\" \".join(str(f.get(\"evidence\") or \"\").split())"
  - "ev not in \" \".join(text.split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-6
  commit: ff3fcf2
  distilled: 2026-09-15
---

## Procedure
1. In `verdict_from`, for every finding that has `ok is True`, normalise the
   evidence by collapsing all runs of whitespace to one space:
   `ev = " ".join(str(f.get("evidence") or "").split())`. `str()` guards
   against non-string JSON values. `split()` with no argument also strips
   the ends, so no separate `.strip()` is needed.
2. Normalise the skill text the same way, then test for a substring:
   `ev not in " ".join(text.split())`. Both sides have to be normalised. If
   only the evidence is, a quote of hard-wrapped prose still misses.
3. Apply the `MIN_EVIDENCE_CHARS` floor to the normalised span, so padding
   a short span with whitespace cannot get past it.
4. Keep this a substring test on the joined text. Do not compare sets or
   sorted lists of words: the gate has to reject a span whose words are
   reordered, so a pass still needs a real quote.
5. A pass whose evidence is too short or not found returns `"fail"`, however
   the finding graded severity or basis.

## Gotchas
- Critique quotes hard-wrapped Markdown and rewraps the whitespace when it
  does, and it doesn't do this consistently even within one reply. With
  byte-exact matching, a skill failed for a single newline.
- Don't loosen the check any further than whitespace (no case folding, no
  punctuation stripping, no fuzzy ratio). This check is the only thing
  stopping a "looks good" pass with no quote behind it.

## Verification
- Run `verification.command` from the repo root. It exits 0 when a rewrapped
  quote passes AND reordered words, a span that isn't in the text, and a
  4-character span all fail.
- If the procedure is skipped and matching stays byte-exact, the first assert
  fails (AssertionError, exit 1). If the matching is loosened to word sets,
  the second assert fails.
