---
name: flatten-not-json-dumps-before-token-matching
kind: skill
scope: project
description: >
  Build the text a pattern matcher tokenizes by walking a structured tool
  response's string leaves, never by json.dumps()-serializing it, because
  JSON's newline escaping welds an "n" onto the first word of every line
  after the first and silently kills matches past line one.
  Use when: a hook or detector matches symptoms, fingerprints, or
  verification signatures against tool_response, or any dict/list of
  captured output; a pattern matches a plain string but stops matching once
  the same text is nested; adding a new field to the haystack detect.py or
  retrieve.py scans.
  Do NOT use when: the haystack is already a plain string, such as the
  UserPromptSubmit prompt (match it directly); or the serialized form is
  the actual product -- JSON written to disk, an API payload, stdout hook
  payloads, ledger rows, or a log record parsed back as JSON -- json.dumps
  is correct there.
verification.command: "python3 tests/test_detect.py"
fingerprints:
  - "\"\\n\".join(_leaf_strings(resp))"
  - "yield from _leaf_strings(v)"
  - "def _leaf_strings(obj):"
  - "join(response_text(v, depth + 1) for v in resp)"
  - "def response_text(resp, depth=0)"
  - "MAX_RESPONSE_DEPTH = 8"
  - "\"\\n\".join(_strings(resp))"
  - "yield from _strings(v)"
---

## Procedure

1. Find the function that turns a structured tool payload into match text
   -- in this repo `response_text()` in `scripts/detect.py`, whose result
   feeds `patterns.tokenize()` (`[a-z0-9_]+`).
2. Do not serialize the payload. `json.dumps()` renders a real newline as
   backslash-`n`; the tokenizer drops the backslash as punctuation and
   fuses the `n` onto the next word, so `\nWidgetFlushedError` tokenizes as
   `nwidgetflushederror` and matches nothing. Tabs, quotes, and `\uXXXX`
   escapes corrupt tokens the same way.
3. Walk the structure instead: for a dict, recurse into `.values()` only
   (drop the keys -- envelope names like `stdout` insert noise tokens and
   eat the matcher's bounded gap window); for a list/tuple, recurse into
   items; `yield` each `str` leaf as-is; `str()` any other scalar so
   numbers and booleans still contribute tokens. Carry a depth counter and
   cap it so a pathological structure can't exhaust the stack inside a hook.
   Leave an already-plain-`str` payload untouched -- it was never broken.
4. Join the yielded leaves with a real `"\n"`, THEN truncate to the output
   cap. Truncating per-leaf, or before joining, changes what the cap means.
5. Tokenize the joined text once; match every pattern against that list.
6. Re-run the suite and confirm every test prints PASS.

## Gotchas

- The failure is silent and total, not partial: a signature on the first
  line of the payload still matches (nothing precedes it to corrupt), so
  the matcher looks alive while missing every signature that starts a
  later line -- the normal shape of real, multi-line tool output. A
  single-line test payload hides this bug completely; the test must place
  the signature on the second line of a nested dict field to discriminate.
- Recursion is load-bearing, not defensive: payloads nest text under keys
  like `{"file": {"content": ...}}`, so a walker that only reads a
  top-level `stdout` key fails the same way serializing does.
- Do not repair this by unescaping the serialized string after the fact --
  flatten before any escaping happens.
- The same escaping trap applies to any text reaching the tokenizer: before
  feeding the matcher, ask whether the string passed through a serializer,
  shell quote, or HTML escape on the way in.
- Injection paths are siblings that drift: `detect.py` (symptom-triggered)
  and `retrieve.py` (prompt-triggered) each write their own `injection`
  ledger row. A field added to one is silently NULL in the other, and NULL
  being a legal value hides it. Grep every `log_event("injection"` call
  site and update them together.

## Verification

- `python3 tests/test_detect.py` exits 0 and prints PASS for every case.
- The suite must include a case with the signature on the second line of a
  dict field (and one nested two levels deep): reverting to
  `json.dumps(resp, default=str)` in `response_text()` makes exactly those
  cases fail with exit 1, while single-line-only tests would pass either
  way and prove nothing.
