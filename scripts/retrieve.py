#!/usr/bin/env python3
"""BM25 retrieval over the skill index (parent spec §8; slice B design).

Hook mode (default): reads UserPromptSubmit JSON on stdin and emits
additionalContext with matching warm skills. Search mode (--search):
ungated top-N over hot and warm alike, for /skillforge:find.

Word-noise control is two-layer: BM25's IDF weighting makes common-word
overlap nearly worthless, and the >=2-distinct-matched-terms gate refuses
to inject on the strength of any single matched term.
"""
import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger

K1 = 1.5
B = 0.75
MIN_MATCHED_TERMS = 2
MAX_SKILLS = 3
INJECT_BUDGET_TOKENS = 1200

TOKEN_RX = re.compile(r"[a-z0-9]+")


def index_path():
    return Path.home() / ".claude" / "skillforge" / "index.json"


def state_dir():
    return Path.home() / ".claude" / "skillforge" / "state"


def tokenize(text):
    return [t for t in TOKEN_RX.findall(text.lower())
            if len(t) >= 3 and not t.isdigit()]


def bm25(query_tokens, corpus):
    """[(score, matched_term_count)] aligned with corpus (list of token lists)."""
    n = len(corpus)
    if n == 0:
        return []
    avgdl = (sum(len(d) for d in corpus) / n) or 1.0
    df = {}
    for doc in corpus:
        for t in set(doc):
            df[t] = df.get(t, 0) + 1
    out = []
    q = set(query_tokens)
    for doc in corpus:
        tf = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        score, matched = 0.0, 0
        for term in q:
            f = tf.get(term)
            if not f:
                continue
            matched += 1
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * len(doc) / avgdl))
        out.append((score, matched))
    return out


def load_index():
    try:
        return json.loads(index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def entry_tokens(e):
    return tokenize(e.get("name", "").replace("-", " ") + " " + e.get("description", ""))


def rank(query, entries):
    """[(entry, score, matched)] best-first; deterministic (-score, name)."""
    qt = tokenize(query)
    if not qt or not entries:
        return []
    scored = bm25(qt, [entry_tokens(e) for e in entries])
    ranked = [(e, s, m) for e, (s, m) in zip(entries, scored)]
    ranked.sort(key=lambda t: (-t[1], t[0].get("name", "")))
    return ranked


def search(topic, limit=10):
    idx = load_index()
    if not idx:
        print("no index yet; save a skill or start a session to build it")
        return 0
    hits = [r for r in rank(topic, idx.get("entries", [])) if r[1] > 0][:limit]
    if not hits:
        print("no matches")
        return 0
    for e, score, matched in hits:
        print("%s | %s | %s | %s | %s | %s" % (
            e.get("name", ""), e.get("kind", ""), e.get("tier", ""),
            e.get("scope", ""), e.get("description", "").strip(), e.get("path", "")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--search")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)
    try:
        if args.search is not None:
            return search(args.search, args.limit)
        return 0  # hook mode lands in the next task
    except Exception as e:
        print("skillforge: retrieve failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
