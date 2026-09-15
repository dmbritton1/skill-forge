---
name: verbatim-evidence-whitespace-normalised
kind: skill
scope: project
description: >
  How validate.verdict_from must match a critique finding's quoted `evidence`
  span against the skill text: collapse whitespace runs on both sides, keep
  word order and the length floor.
  Use when: writing or editing verdict_from, MIN_EVIDENCE_CHARS, or any gate
  that accepts an LLM-quoted span only if it appears in a source document;
  or when a skill whose criteria all pass on substance still gets verdict "fail".
  Do NOT use when: parsing the critique reply JSON, building the critique
  prompt/nonce delimiters, or grading severity/basis of non-ok findings.
verification.command: "python3 -c \"import sys; sys.path.insert(0, 'scripts'); import validate as v; mk=lambda e: [{'criterion': c, 'ok': True, 'evidence': e} for c in v.SKILL_CRITERIA]; t='## Procedure\\n1. Call flush() before\\n   close().\\n'; assert v.verdict_from(mk('flush() before close().'), t) == 'pass'; assert v.verdict_from(mk('close() before Call flush().'), t) == 'fail'; assert v.verdict_from(mk('not anywhere in this skill'), t) == 'fail'; assert v.verdict_from(mk('Call'), t) == 'fail'; print('ok')\""
fingerprints:
  - "\" \".join((f.get(\"evidence\") or \"\").split())"
  - "ev not in \" \".join(text.split())"
provenance:
  repo: /private/tmp/skillforge-bench/sf-repair-verdict-from-distill-learn-e15-nogate-6
  commit: 5e38a88
  distilled: 2026-09-15
---

## Procedure
1. The quoted-evidence gate exists so a criterion cannot pass on assertion
   alone: an `ok: true` finding counts only if its `evidence` is a real span
   of the skill text. Keep that property, but compare the skill's words, not
   its line breaks.
2. Normalise the evidence with `" ".join(ev.split())`. This strips the ends
   and turns every run of spaces, tabs or newlines into one space.
3. Normalise the source text the same way (`" ".join(text.split())`) and
   check `ev not in normalised_text`. Plain substring containment, so word
   order and punctuation still have to match exactly.
4. Apply the `MIN_EVIDENCE_CHARS` floor to the normalised evidence, so padding
   a short span with whitespace cannot get it over the floor.
5. Leave the `ok is not True` check before this unchanged. Normalisation
   applies only to the evidence comparison.

## Gotchas
- Critique models re-wrap hard-wrapped prose when they quote it, and they
  don't do it consistently even within one reply. Byte-exact `ev in text`
  fails a good skill over a single newline, and the result looks like a real
  "fail" verdict, not a parsing error.
- Don't loosen further (casefolding, token sets, fuzzy ratio). Once reordered
  or paraphrased words pass, a model can make up evidence without reading the
  text, and the anti-sycophancy gate stops working.
- `str.split()` with no argument is the right tool. `split(" ")` leaves
  newlines and tabs inside the tokens.

## Verification
- `verification.command` (run from the repo root) should print `ok`. It checks
  four things: a quote whose line break became a space passes, reordered words
  fail, a span not in the text fails, and a span shorter than the floor fails.
- If the procedure was NOT followed (a byte-exact `ev in text`), the first
  assertion raises `AssertionError` and the command exits non-zero. If it was
  over-loosened (order- or case-insensitive), the second assertion fails.
