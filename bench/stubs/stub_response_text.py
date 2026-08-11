#!/usr/bin/env python3
"""Blank out detect.response_text so the model must author it.

The replacement docstring states the CONTRACT only -- what goes in, what
comes out, and the cap. It deliberately says nothing about escaping,
serialization, newlines, or tokenization: naming the hazard would hand over
the very knowledge the benchmark is trying to measure.
"""
import re
import sys
from pathlib import Path

STUB = '''def response_text(resp):
    """Return searchable text for a PostToolUse tool_response.

    `resp` is whatever the harness put in tool_response: a plain string for
    some tools, and for most tools a structured object.

    The result is handed to patterns.tokenize() and matched against
    anti-skill symptom patterns. Truncate the result to MAX_OUTPUT_CHARS.
    """
    raise NotImplementedError("implement me")
'''


def main():
    p = Path("scripts/detect.py")
    src = p.read_text(encoding="utf-8")
    m = re.search(r"^def response_text\(resp\):\n(?:.*\n)*?(?=^def |\Z)", src, re.M)
    if not m:
        print("stub: response_text not found", file=sys.stderr)
        return 1
    p.write_text(src[:m.start()] + STUB + "\n" + src[m.end():], encoding="utf-8")
    if "NotImplementedError" not in p.read_text(encoding="utf-8"):
        print("stub: replacement did not take", file=sys.stderr)
        return 1
    print("stubbed response_text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
