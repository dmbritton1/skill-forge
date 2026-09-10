---
name: json-dumps-fuses-tokens-across-newlines
kind: antiskill
scope: project
description: >
  json.dumps() on a tool response escapes real newlines into a literal
  backslash-n, and a [a-z0-9_]+ tokenizer reads that surviving "n" as the
  first letter of the next word, so any pattern whose match spans a line
  break silently stops matching.
  Use when: a token or substring matcher over tool output, file content, or
  any serialized blob finds nothing, and every signature it misses happens
  to start a line.
  Do NOT use when: the matcher misses a signature that sits mid-line, or the
  haystack was never passed through a JSON/repr serializer.
symptoms:
  - "assert injected_names(out) == [\"widget-trap\"]"
  - "FAIL test_symptom_on_second_line_of_dict_response_injects AssertionError"
fingerprints:
  - "isinstance(node, dict): stack[:0] = list(node.values())"
  - "text = node if isinstance(node, str) else str(node)"
provenance:
  repo: skill-forge
  distilled: 2026-09-09
---

## Trap
Flattening a structured tool response into one searchable string with
`json.dumps(resp, default=str)`. It looks like the safe, total way to handle
a dict, a list, or a string alike, and it is the obvious rung to reach for.
It also corrupts the text it produces, in a way that only shows up for
patterns that cross a line boundary.

## Symptom
No exception, no stderr, no partial match. The hook exits 0 and prints
nothing, exactly as it does when there is genuinely nothing to report.
In this repo it surfaced only as a test assertion:

```
FAIL test_symptom_on_second_line_of_dict_response_injects: AssertionError()
assert injected_names(out) == ["widget-trap"]
```

The misleading part: silence points you at the matcher. Single-line
signatures still match, `patterns.matches` has its own passing tests, and
the pattern tokens in the index look correct, so the natural next suspects
are the window size, the gap tolerance, and the token regex. All three are
fine. The haystack was already wrong before the matcher ever saw it.

## Cause
`json.dumps` encodes a real newline as the two characters `\` and `n`.
The tokenizer `[a-z0-9_]+` does not match the backslash, but `n` is a word
character, so it is not a separator either. The `n` is absorbed into the
following word:

```
"Running webhook test...\nWidgetFlushedError: ..."
  -> json.dumps -> ...test...\nWidgetFlushedError...
  -> tokenize   -> ["running", "webhook", "test", "nwidgetflushederror", ...]
```

The first token of the pattern never appears, so the match fails at token
zero. The same fusion hits `\t`, `\r` and `\"` -> `t`, `r` and nothing.
This is worse than dropped whitespace: escaping does not add noise between
tokens, it destroys one real token by welding a letter onto its front.

## Fix
Never serialize a haystack you intend to match against. Walk the structure
and collect its own string leaves, joined by real newlines:

```python
def response_text(resp):
    parts, total, stack = [], 0, [resp]
    while stack and total < MAX_OUTPUT_CHARS:
        node = stack.pop(0)
        if isinstance(node, dict):
            stack[:0] = list(node.values())
        elif isinstance(node, (list, tuple)):
            stack[:0] = list(node)
        else:
            text = node if isinstance(node, str) else str(node)
            parts.append(text)
            total += len(text) + 1
    return "\n".join(parts)[:MAX_OUTPUT_CHARS]
```

The same rule covers `repr()`, `str()` on a dict, and `%r`: each escapes
newlines the same way. Any test that only feeds a single-line string will
pass over this bug, so cover a signature that starts a line and one nested
a level deep.

## Cost of rediscovery
~10 min observed here, because the failing test carried a comment naming
the cause. ~45 min without that hint: the matcher, the window factor and
the trigger index all look correct under inspection, and the failure gives
no error text to search for.
