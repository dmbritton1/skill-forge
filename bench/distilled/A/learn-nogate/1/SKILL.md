---
name: matching-text-in-tool-payloads
kind: skill
scope: project
description: >
  Build match text for a SkillForge hook by walking the tool payload's string
  leaves, never by serializing it.
  Use when: a hook must match patterns (symptoms, verifications, fingerprints)
  against a structured tool_response or any nested JSON payload; a symptom that
  is visibly present in tool output is not being detected; adding a new field to
  one of the injection paths in detect.py or retrieve.py.
  Do NOT use when: matching against an already-flat string such as the
  UserPromptSubmit prompt, or when the payload is being stored or transmitted
  rather than matched (serialize freely there).
verification.command: "python3 tests/test_detect.py"
fingerprints:
  - "\"\\n\".join(_leaf_strings(resp))"
  - "yield from _leaf_strings(v)"
  - "def _leaf_strings(obj):"
provenance:
  repo: /private/tmp/skillforge-bench/sf-escaping-breaks-symptom-match-distill-learn-nogate-1
  commit: 4eeaa9a
  distilled: 2026-09-10
---

## Procedure

1. Find the function that turns the tool payload into match text. In
   `scripts/detect.py` that is `response_text`, whose result feeds
   `patterns.tokenize`.
2. Do not serialize the payload. `json.dumps` escapes a real newline to
   backslash-n, and `patterns.TOKEN_RX` (`[a-z0-9_]+`) then reads the escape
   letter as part of the following word: `"...test\nWidgetFlushedError"`
   tokenizes as `test`, `nwidgetflushederror`. Any signature that starts a
   line, which is the normal shape of tool output, can never match.
3. Walk the structure instead. Recurse through dict values and list items,
   yield every `str` leaf as-is, and `str()` any non-string leaf so numbers and
   booleans still contribute tokens.
4. Join the leaves with a newline, then truncate the joined result to the
   size cap. Truncating per leaf changes what the cap means.
5. Tokenize the joined text once and match every pattern against that one
   token list.
6. Run the suite and confirm every test prints PASS.

## Gotchas

- Recursion is load-bearing, not defensive. Payloads put their text under
  nested keys such as `{"file": {"content": ...}}`, so a walker that only
  reads a top-level `stdout` key misses them and fails the same way
  serializing does.
- The same escaping trap applies to any text the tokenizer sees. Before
  feeding the matcher, ask whether the string passed through a serializer,
  a shell quote, or an HTML escape on the way in.
- Injection paths are siblings that drift. `detect.py` (symptom-triggered)
  and `retrieve.py` (prompt-triggered) each write their own `injection` row.
  A ledger column added to one is silently NULL in the other, and the
  aggregate looks fine because NULL is a legal value. Grep for every
  `log_event("injection"` call site and update them together.

## Verification

- `python3 tests/test_detect.py` prints PASS for all 22 tests and exits 0.
- It discriminates: with a serializing `response_text`, the payload-shaped
  tests (`test_symptom_on_second_line_of_dict_response_injects` and
  `test_symptom_in_nested_dict_response_injects`) FAIL, because the newline
  escape corrupts the first token of the error signature.
