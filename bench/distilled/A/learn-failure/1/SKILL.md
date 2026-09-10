---
name: json-dumps-breaks-token-matching
kind: antiskill
scope: project
description: >
  json.dumps() of a tool response before token matching escapes real
  newlines to backslash-n, fusing the escape letter onto the next line's
  first word and silently killing every pattern whose signature starts a
  line.
  Use when: a symptom/pattern match over tool output misses although the
  signature is plainly present, or output is flattened for matching with
  json.dumps.
  Do NOT use when: the match runs over a genuine JSON document whose own
  escapes matter, or the pattern legitimately fails because the tokens
  differ.
symptoms:
  - "assert injected_names(out) == [\"widget-trap\"]"
  - "json.dumps(resp, default=str)"
fingerprints:
  - "parts = [response_text(v) for v in resp.values()]"
  - "return \"\\n\".join(parts)[:MAX_OUTPUT_CHARS]"
verification.command: "python3 -m pytest tests/test_detect.py -q"
provenance:
  repo: sf-escaping-breaks-symptom-match-distill-learn-failure-1
  distilled: 2026-09-09
---

## Trap
A tool response arrives as a dict, so it gets flattened to a searchable
string with `json.dumps(resp, default=str)` before the token matcher runs.
That looks like the obvious way to make a nested structure greppable, and
it passes every test whose fixture puts the error signature on the first
line.

## Symptom
The matcher returns nothing for output that visibly contains the pattern:

    assert injected_names(out) == ["widget-trap"]
    AssertionError: assert [] == ['widget-trap']

while the same signature at offset 0 of a plain string matches fine. It
makes you suspect the matcher: the gap window, the token regex, scope
checks, trust re-verification, dedupe state. All of those are innocent.

## Cause
`json.dumps` escapes a real newline into the two characters backslash and
`n`. The tokenizer's character class (`[a-z0-9_]+`) does not include the
backslash but does include `n`, so `...test\nWidgetFlushedError` tokenizes
as `test`, `nwidgetflushederror`. The pattern's first token
(`widgetflushederror`) no longer exists in the haystack. Every signature
that begins a line, which is nearly all of them, is defeated. Nothing
errors; the match count just quietly drops to zero.

## Fix
Flatten by walking the structure and joining raw values, never by
serializing:

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

The rule generalizes: any serializer between text and a matcher (JSON,
`repr()`, `shlex.quote`, HTML escaping) rewrites the exact characters the
matcher tokenizes on. Match the raw text, and keep at least one fixture
whose signature sits on the second line.

## Cost of rediscovery
~10 min (observed in source session)
