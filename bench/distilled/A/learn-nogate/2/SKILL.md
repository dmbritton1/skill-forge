---
name: flatten-structured-output-for-token-matching
kind: skill
scope: project
description: >
  Build the text haystack from a structured tool response by flattening its
  leaf values, never by JSON-serializing it, so a pattern still matches past
  the first line.
  Use when: a hook or matcher tokenizes tool output that can arrive as a dict
  or a list; a pattern matches a plain string but stops matching the same
  text nested in a dict; you are about to call json.dumps() on data whose
  text will be tokenized, grepped, or substring-searched.
  Do NOT use when: the serialized form is the product itself, such as JSON
  written to disk, an API payload, or a log record parsed back as JSON; or
  the haystack is already a plain string.
verification.command: "python3 tests/test_detect.py"
fingerprints:
  - "join(response_text(v, depth + 1) for v in resp)"
  - "def response_text(resp, depth=0)"
  - "MAX_RESPONSE_DEPTH = 8"
provenance:
  repo: /private/tmp/skillforge-bench/sf-escaping-breaks-symptom-match-distill-learn-nogate-2
  commit: 4eeaa9a
  distilled: 2026-09-10
---

## Procedure

1. Find every place a structured tool response becomes text that will be
   searched or tokenized. In this repo that is `response_text()` in
   `scripts/detect.py`, whose result feeds `patterns.tokenize()`.
2. Return a string unchanged, truncated to the output cap.
3. For a dict, take `list(resp.values())` and drop the keys. Keys are
   envelope names like `stdout` or `content`. They are not part of the error
   text, and they insert noise tokens between the real ones, which eats the
   matcher's bounded gap window.
4. For a dict or a list, recurse into the values and join the results with a
   real newline. Carry a depth counter and stop recursing past a small cap so
   a pathological structure cannot exhaust the stack inside a hook.
5. For anything else, use `str()`.
6. Apply the truncation cap at every level, so a deep structure cannot
   assemble a haystack larger than the cap.

## Gotchas

- `json.dumps()` writes a real newline as a backslash followed by `n`. A
  tokenizer built on `[a-z0-9_]+` reads that `n` as a word character and
  glues it to the next line's first word, so `WidgetFlushedError` on line two
  becomes the token `nwidgetflushederror` and the pattern never matches. Tabs,
  quotes, and any non-ASCII escaped to `\uXXXX` corrupt tokens the same way.
- The failure is silent and one-sided. A signature on the first line of the
  payload still matches, so the matcher looks alive while missing most real
  output. Write the test with the signature on the second line, never the
  first.
- Keeping dict keys in the haystack is the quieter form of the same bug.
  Every key spends tokens out of the bounded match window.
- Do not repair the damage afterwards by unescaping the serialized string.
  Flatten before any escaping happens.
- Cover nesting deeper than one level. An implementation that handles only a
  flat dict passes the obvious test and fails on a real tool response.

## Verification

- `python3 tests/test_detect.py` exits 0 and prints PASS for every case.
- Two of its cases carry the signature on the second line of a response, one
  flat and one nested two levels deep.
- When the procedure is skipped and `response_text()` serializes the response
  instead, the newline before the signature becomes a backslash and an `n`,
  the tokenizer emits a glued token, no symptom match fires, and those two
  cases fail with exit 1.
