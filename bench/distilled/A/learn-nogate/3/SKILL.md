---
name: flatten-not-json-dumps-before-token-matching
kind: skill
scope: project
description: >
  Feed a token matcher the raw strings out of a structured tool response,
  never json.dumps() of it, because JSON escaping welds an "n" onto the
  first word of every line after the first.
  Use when: a hook or detector matches error signatures, symptoms,
  verification commands or fingerprints against tool_response / a dict or
  list of captured output; a pattern that matches a plain string stops
  matching the same text once it arrives nested in a dict; adding a new
  field to the haystack that detect.py scans.
  Do NOT use when: the text is already a single str (match it directly);
  the consumer needs valid JSON (serializing for storage, stdout hook
  payloads, ledger rows) -- json.dumps is correct there.
verification.command: "python3 tests/test_detect.py"
fingerprints:
  - "\"\\n\".join(_strings(resp))"
  - "yield from _strings(v)"
provenance:
  repo: /private/tmp/skillforge-bench/sf-escaping-breaks-symptom-match-distill-learn-nogate-3
  commit: 4eeaa9a
  distilled: 2026-09-10
---

## Procedure
1. Find every place a pattern matcher is handed something that is not a
   plain string. In this repo that is `response_text()` in
   `scripts/detect.py`, whose result goes straight into
   `patterns.tokenize()`.
2. Do not serialize the structure. Walk it and yield the strings:
   recurse through dict values and list/tuple items, `yield` each `str`,
   `str()` other scalars.
3. Join the yielded strings with a real `"\n"` and truncate the joined
   result to the output cap, so the cap still bounds total work.
4. Leave the plain-string path alone; a `str` haystack was never broken.
5. Re-run the detector's tests. A case whose signature starts on the
   second line of a dict field is the one that flips.

## Gotchas
- The failure is silent and total, not partial. `patterns.tokenize()`
  uses `[a-z0-9_]+`, and `json.dumps()` renders a newline as backslash
  plus the letter `n`. The backslash is dropped as punctuation and the
  `n` fuses with the next word: `\nWidgetFlushedError` tokenizes as
  `nwidgetflushederror`, which equals no pattern token. Every signature
  that starts a line stops matching, and nothing logs an error.
- Real tool output is multi-line, so this hits the normal case, not an
  edge case. A test with a one-line response passes and hides it.
- Tabs, quotes and non-ASCII escape the same way (`\t`, `\"`, `\uXXXX`),
  so the bug is not limited to newlines.
- Keys are not worth including. Only values carry the signature, and
  emitting keys invents adjacencies that can produce a false match.
- Truncate after joining, not per string, or the output cap stops
  bounding the haystack.

## Verification
- `python3 tests/test_detect.py` exits 0 with every test PASS.
- Skipped procedure: restoring `json.dumps(resp, default=str)` in
  `response_text()` makes `test_symptom_on_second_line_of_dict_response_injects`
  and `test_symptom_in_nested_dict_response_injects` fail and the command
  exit 1. The command only discriminates because those two cases put the
  signature after a newline inside a dict field; in a suite whose
  responses are all single-line, it would pass either way, so add such a
  case before trusting it.
