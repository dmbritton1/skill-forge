"""Tests for BM25 retrieval (slice B design §3). Run: python3 tests/test_retrieve.py"""
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import retrieve


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


BODY_TMPL = """---
name: %(name)s
kind: %(kind)s
description: %(desc)s
---
## Procedure
1. %(desc)s
"""


def put_body(home, name, kind="skill", desc="a body", pad=0):
    d = home / ".claude" / "skillforge" / ("antiskills" if kind == "antiskill" else "skills") / name
    d.mkdir(parents=True, exist_ok=True)
    text = BODY_TMPL % {"name": name, "kind": kind, "desc": desc} + ("x" * pad)
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return str(d / "SKILL.md")


def entry(home, name, desc, kind="skill", tier="warm", pad=0):
    return {"name": name, "kind": kind, "scope": "global", "root": str(home),
            "description": desc, "tier": tier, "est_tokens": 10,
            "path": put_body(home, name, kind, desc, pad)}


def write_index(home, entries):
    p = home / ".claude" / "skillforge" / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_tokenize_drops_noise():
    toks = retrieve.tokenize("Set up-to-date API, v2 42 OK!")
    assert "api" in toks
    assert "set" in toks
    assert "42" not in toks   # pure number
    assert "up" not in toks   # shorter than 3
    assert "ok" not in toks


def test_bm25_prefers_rare_term_overlap():
    corpus = [retrieve.tokenize("stripe webhook signature verification endpoint"),
              retrieve.tokenize("generic project setup and code style notes"),
              retrieve.tokenize("stripe payments dashboard configuration")]
    scores = retrieve.bm25(retrieve.tokenize("add a stripe webhook endpoint"), corpus)
    assert scores[0][0] > scores[1][0]
    assert scores[0][0] > scores[2][0]
    assert scores[0][1] >= 3  # stripe, webhook, endpoint all matched


def test_rank_sorts_best_first_and_is_deterministic():
    def check(home):
        entries = [entry(home, "zeta-skill", "kubernetes ingress routing"),
                   entry(home, "alpha-skill", "kubernetes ingress routing")]
        ranked = retrieve.rank("kubernetes ingress", entries)
        assert ranked[0][0]["name"] == "alpha-skill"  # equal score, name tiebreak
        assert ranked[0][1] > 0
    in_sandbox(check)


def test_load_index_missing_or_corrupt_returns_none():
    def check(home):
        assert retrieve.load_index() is None
        p = home / ".claude" / "skillforge" / "index.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        assert retrieve.load_index() is None
    in_sandbox(check)


def test_search_prints_hot_and_warm():
    def check(home):
        write_index(home, [entry(home, "hot-stripe", "stripe webhook handling", tier="hot"),
                           entry(home, "warm-stripe", "stripe webhook retries", tier="warm")])
        out = io.StringIO()
        with redirect_stdout(out):
            rc = retrieve.main(["--search", "stripe webhook"])
        assert rc == 0
        text = out.getvalue()
        assert "hot-stripe" in text and "warm-stripe" in text
    in_sandbox(check)


def test_search_no_match_says_so():
    def check(home):
        write_index(home, [entry(home, "warm-stripe", "stripe webhook retries")])
        out = io.StringIO()
        with redirect_stdout(out):
            rc = retrieve.main(["--search", "quantum chromodynamics"])
        assert rc == 0
        assert "no matches" in out.getvalue()
    in_sandbox(check)


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except AssertionError:
                failures += 1
                print("FAIL " + name)
    sys.exit(1 if failures else 0)
