---
name: json-escaping-defeats-token-match
kind: antiskill
scope: global
description: >
  Serializing a structured value with json.dumps before pattern-matching over it
  silently corrupts the text: escaped newlines fuse into adjacent tokens and
  line-anchored patterns stop matching, with no error.
  Use when: a matcher runs over tool output, a file, or an API response that was
  flattened to a string, and patterns that clearly should hit return nothing.
  Do NOT use when: the JSON text really is the subject being matched (matching
  key names or the wire format itself), or the matcher failed loudly.
symptoms:
  - "json.dumps(resp, default=str)"
  - "tokenize(json.dumps"
fingerprints:
  - "response_text(v) for v in resp.values()"
  - "\"\\n\".join(parts)"
provenance:
  repo: skill-forge
  distilled: 2026-09-09
---

## Trap
You need to run a pattern matcher over a value that may be a string or a nested
dict, so you flatten it first with `json.dumps(resp, default=str)`. It looks
like a safe, total, dependency-free way to get text out of anything. It is not
safe: `json.dumps` is an *escaping* serializer, and every real newline in the
payload becomes the two characters backslash and `n`.

## Symptom
No exception, no warning, no log line. Patterns simply stop matching, and
`matches()` returns an empty result on input a human can read and confirm
contains the signature verbatim. In the source session this surfaced only as
`AssertionError: assert [] == ['widget-trap']` from a test written on purpose to
catch it.

It wrongly makes you suspect the matcher: the window size, the gap tolerance,
the token order rules, the trust or scope check gating the result. All of those
are fine. The corruption happened before the matcher was ever called.

Because the failure is silent, the practical detector is the code shape, not a
runtime signature. Treat `json.dumps` feeding anything that later tokenizes or
greps as the trigger.

## Cause
An identifier-style tokenizer such as `re.compile(r"[a-z0-9_]+")` drops the
backslash but keeps the `n`, so the escape's letter fuses onto the first token
of the next line:

```
"Running test...\nWidgetFlushedError: ..."   real text
"Running test...\\nWidgetFlushedError: ..."  after json.dumps
-> tokens: [running, test, nwidgetflushederror, ...]
```

`widgetflushederror` is now gone from the token stream and `nwidgetflushederror`
took its place. Any pattern anchored on the first token of a line loses its
anchor. That is most error signatures, since an error signature normally starts
a line rather than sitting at offset 0 of the whole response. So the patterns
most worth matching are exactly the ones this breaks.

The same fusion hits `\t`, `\r` and `\"` (adding `t`, `r` and nothing), and it
survives case folding and punctuation stripping, so the usual normalization
steps do not undo it.

## Fix
Walk the structure and join the leaf strings with real newlines. Never route
text through an escaping serializer on its way to a matcher.

```python
def response_text(resp):
    if isinstance(resp, str):
        return resp[:MAX_OUTPUT_CHARS]
    if isinstance(resp, dict):
        parts = [response_text(v) for v in resp.values()]
    elif isinstance(resp, (list, tuple)):
        parts = [response_text(v) for v in resp]
    else:
        return str(resp)[:MAX_OUTPUT_CHARS]
    return "\n".join(parts)[:MAX_OUTPUT_CHARS]
```

Note that `str(some_dict)` is the same trap with a different mask: it renders
`'a\nb'` with a visible backslash too. Recurse to the leaves; do not stringify a
container.

Guard it with a test whose fixture puts the signature on the *second* line of a
nested value. A fixture with the signature at offset 0 passes either way and
proves nothing.

## Cost of rediscovery
~45 min. The source session had a test pointing straight at the mechanism, so it
cost about 10 there. Without such a test the layer just never fires and the
clock runs until someone notices a match that should have happened and did not.
