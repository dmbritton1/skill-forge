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


def run_hook_capture(data):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = retrieve.run_hook(data)
    return rc, out.getvalue()


def hook_data(home, prompt, session="sess1"):
    return {"prompt": prompt, "session_id": session, "cwd": str(home)}


def injected_names(output):
    if not output.strip():
        return []
    ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
    return [line.split("'")[1] for line in ctx.splitlines()
            if line.startswith("--- SkillForge retrieved skill '")]


def test_hook_injects_matching_warm_skill():
    def check(home):
        write_index(home, [
            entry(home, "stripe-webhook", "stripe webhook signature verification"),
            entry(home, "csv-import", "bulk csv import with schema mapping")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert rc == 0
        assert injected_names(out) == ["stripe-webhook"]
        payload = json.loads(out)["hookSpecificOutput"]
        assert payload["hookEventName"] == "UserPromptSubmit"
        assert "## Procedure" in payload["additionalContext"]
        import ledger
        con = ledger.connect()
        rows = con.execute(
            "SELECT event_type, tier, \"trigger\", session FROM events WHERE skill='stripe-webhook'"
        ).fetchall()
        con.close()
        assert ("injection", "warm", "prompt", "sess1") in rows
    in_sandbox(check)


def test_hot_entries_never_hook_injected():
    def check(home):
        write_index(home, [entry(home, "stripe-webhook",
                                  "stripe webhook signature verification", tier="hot")])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert rc == 0 and out.strip() == ""
    in_sandbox(check)


def test_single_matched_term_rejected():
    def check(home):
        write_index(home, [entry(home, "vercel-deploy",
                                  "vercel deploy pipeline for static sites")])
        rc, out = run_hook_capture(hook_data(home, "deploy the thing now please"))
        assert rc == 0 and out.strip() == ""
    in_sandbox(check)


def test_max_three_skills_antiskill_exempt():
    def check(home):
        ents = [entry(home, "k8s-%s" % c, "kubernetes ingress routing rules")
                for c in "abcd"]
        ents.append(entry(home, "k8s-trap", "kubernetes ingress routing rules",
                          kind="antiskill"))
        write_index(home, ents)
        rc, out = run_hook_capture(hook_data(home, "fix the kubernetes ingress"))
        names = injected_names(out)
        assert "k8s-trap" in names
        assert "k8s-d" not in names
        assert len(names) == 4  # 3 skills + 1 antiskill
    in_sandbox(check)


def test_budget_skips_oversized_entry():
    def check(home):
        write_index(home, [
            entry(home, "big-terraform", "terraform module registry publishing", pad=10000),
            entry(home, "small-terraform", "terraform module registry basics")])
        rc, out = run_hook_capture(hook_data(home, "publish a terraform module registry entry"))
        names = injected_names(out)
        assert "small-terraform" in names
        assert "big-terraform" not in names
    in_sandbox(check)


def test_session_dedupe():
    def check(home):
        write_index(home, [entry(home, "stripe-webhook",
                                  "stripe webhook signature verification")])
        rc1, out1 = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        rc2, out2 = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert injected_names(out1) == ["stripe-webhook"]
        assert out2.strip() == ""
        other = run_hook_capture(hook_data(home, "add a stripe webhook endpoint", session="sess2"))
        assert injected_names(other[1]) == ["stripe-webhook"]
    in_sandbox(check)


def test_project_entry_scoped_to_its_root():
    def check(home):
        proj = home / "myrepo"
        proj.mkdir()
        e = entry(home, "repo-conventions", "kraken api pagination conventions")
        e["root"] = str(proj)
        e["scope"] = "project"
        write_index(home, [e])
        rc, out = run_hook_capture(
            {"prompt": "kraken api pagination", "session_id": "s", "cwd": str(home / "elsewhere")})
        assert out.strip() == ""
        rc, out = run_hook_capture(
            {"prompt": "kraken api pagination", "session_id": "s2", "cwd": str(proj / "src")})
        assert injected_names(out) == ["repo-conventions"]
    in_sandbox(check)


def test_corrupt_index_hook_silent():
    def check(home):
        p = home / ".claude" / "skillforge" / "index.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{bad", encoding="utf-8")
        rc, out = run_hook_capture(hook_data(home, "anything at all here"))
        assert rc == 0 and out.strip() == ""
    in_sandbox(check)


def test_entry_missing_path_skipped_not_fatal():
    def check(home):
        good = entry(home, "stripe-webhook", "stripe webhook signature verification")
        bad = {"name": "broken-entry", "kind": "skill", "scope": "global",
               "root": str(home), "description": "stripe webhook signature checks",
               "tier": "warm", "est_tokens": 10}
        write_index(home, [bad, good])
        rc, out = run_hook_capture(hook_data(home, "add a stripe webhook endpoint"))
        assert rc == 0
        assert injected_names(out) == ["stripe-webhook"]
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
