#!/usr/bin/env python3
"""Shared matcher for symptoms, verifications, and fingerprints (spec 9.1).

Token-normalized so formatting never decides a match: quotes, whitespace
and punctuation vanish, and an added flag or a variable id inside a
pattern still matches -- raw-string grep silently undercounts usage, and
an undercounted skill gets its triggers narrowed as punishment for a
matching bug.

ponytail: no regex. These patterns are model-authored and matched inside
blocking hooks, where one pathological pattern costs a session; a windowed
subsequence covers real error signatures without a regex engine. If true
alternation ever proves necessary, add it as a separate pattern entry.
"""
import re

TOKEN_RX = re.compile(r"[a-z0-9_]+")

# Gap tolerance: enough for reformatting and inserted arguments, not enough
# for two tokens that merely coexist somewhere in a large file.
WINDOW_FACTOR = 3
WINDOW_SLACK = 8


def tokenize(text):
    return TOKEN_RX.findall(str(text).lower())


def window(pattern_tokens):
    return WINDOW_FACTOR * len(pattern_tokens) + WINDOW_SLACK


def matches(pattern_tokens, hay_tokens):
    """True if pattern's tokens appear in order within a bounded span."""
    if not pattern_tokens:
        return False
    span = window(pattern_tokens)
    first = pattern_tokens[0]
    need = len(pattern_tokens)
    for start, tok in enumerate(hay_tokens):
        if tok != first:
            continue
        if need == 1:
            return True
        pi = 1
        for hi in range(start + 1, min(len(hay_tokens), start + span)):
            if hay_tokens[hi] == pattern_tokens[pi]:
                pi += 1
                if pi == need:
                    return True
    return False
