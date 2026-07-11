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


def load_state(session):
    try:
        p = state_dir() / ("session-%s.json" % session)
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def save_state(session, names):
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ("session-%s.json" % session)).write_text(
        json.dumps(sorted(names)), encoding="utf-8")


def eligible(e, cwd):
    if e.get("tier") != "warm":
        return False
    root = e.get("root", "")
    if not root:
        return False
    if Path(root) == Path.home():
        return True
    return cwd == root or cwd.startswith(root.rstrip("/") + "/")


def run_hook(data):
    prompt = data.get("prompt", "")
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", ""))) or "unknown"
    cwd = data.get("cwd") or os.getcwd()
    idx = load_index()
    if not idx:
        return 0
    warm = [e for e in idx.get("entries", []) if eligible(e, cwd)]
    seen = load_state(session)
    picked = []
    skills = 0
    budget = INJECT_BUDGET_TOKENS
    for e, score, matched in rank(prompt, warm):
        if score <= 0 or matched < MIN_MATCHED_TERMS:
            continue
        if e.get("name") in seen:
            continue
        if e.get("kind") != "antiskill" and skills >= MAX_SKILLS:
            continue
        try:
            body = Path(e["path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        cost = max(1, len(body) // 4)
        if cost > budget:
            continue
        budget -= cost
        picked.append((e, body))
        if e.get("kind") != "antiskill":
            skills += 1
    if not picked:
        return 0
    parts = ["--- SkillForge retrieved skill '%s' (apply if relevant): ---\n%s"
             % (e["name"], body) for e, body in picked]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n\n".join(parts)}}))
    save_state(session, seen | {e["name"] for e, _ in picked})
    for e, _ in picked:
        try:
            ledger.log_event("injection", e["name"], tier="warm",
                             trigger="prompt", session=session)
        except Exception as err:
            print("skillforge: ledger write failed: %s" % err, file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--search")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)
    try:
        if args.search is not None:
            return search(args.search, args.limit)
        return run_hook(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: retrieve failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
