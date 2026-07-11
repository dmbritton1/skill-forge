# SkillForge v0.2 Slice B Implementation Plan — Retrieval & Tiering

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BM25 retrieval over a compiled skill index, a UserPromptSubmit injection hook with gates (two-term match, 3-skill cap with anti-skill exemption, 1200-token budget, session dedupe), hot/warm tiering with a fixed hot budget in sync, and `/skillforge:find`.

**Architecture:** `sync.py` (already the sole writer of native dirs) additionally ranks trusted skills, assigns hot/warm tiers under a 1500-token description budget, and compiles `~/.claude/skillforge/index.json`. New `scripts/retrieve.py` reads that index: hook mode (stdin JSON → additionalContext for warm matches) and `--search` mode (ungated, for `/find`). Hot skills stay native and are excluded from retrieval — native XOR retrievable, no double-fire. `save_skill.py` switches from direct materialization to a full `sync.sync()` call so every save re-tiers and re-indexes.

**Tech Stack:** Python 3.9 stdlib only (`json`, `math`, `re`, `argparse`). Tests are plain assert files with `__main__` runners (NO pytest). Existing modules: `scripts/{ledger,trust,sync,save_skill,secscan}.py`, five green test files (59 tests).

**Design doc:** `docs/superpowers/specs/2026-07-10-v0.2-slice-b-design.md`. Parent spec §8.

## Global Constraints

- Python 3.9 compatible, **stdlib only**; tests run via `python3 tests/test_<name>.py`, exit 0 = pass.
- Retrieval constants (centralized in `retrieve.py`): `K1 = 1.5`, `B = 0.75`, `MIN_MATCHED_TERMS = 2`, `MAX_SKILLS = 3`, `INJECT_BUDGET_TOKENS = 1200`.
- Hot budget: default **1500** description-tokens, overridable via env `SKILLFORGE_HOT_BUDGET` (tests shrink it).
- Token estimate everywhere: `max(1, len(text) // 4)`.
- Tokenizer: lowercase, split on non-alphanumeric, drop tokens shorter than 3 chars and pure numbers.
- Index at `~/.claude/skillforge/index.json`; session state at `~/.claude/skillforge/state/session-<id>.json`; both derived, rebuilt/managed by sync + retrieve. Trusted skills only ever enter the index.
- A skill is native XOR retrievable: `tier: hot` → materialized, excluded from hook retrieval; `tier: warm` → indexed only.
- Interim hot ranking (placeholder until Slice C buckets): ledger `(uses + injections)` DESC, then most-recent `save` event ts DESC, then name ASC.
- Hooks always exit 0; any failure = no injection, never a broken session. Session ids are sanitized (`[^A-Za-z0-9_-]` stripped) before filesystem use.
- All default paths derive from `Path.home()` at call time (sandbox-HOME testing).
- Never weaken an existing test. All five existing suites must stay green after every task.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Retriever core — tokenizer, BM25, index load, search mode

**Files:**
- Create: `scripts/retrieve.py`
- Test: `tests/test_retrieve.py`

**Interfaces:**
- Consumes: `ledger.log_event` exists (used in Task 2; imported now so the module header is final).
- Produces (Task 2 builds on these, in the same file): `tokenize(text) -> list[str]`; `bm25(query_tokens, corpus) -> list[tuple[float, int]]` (score, matched-term-count, aligned with corpus of token-lists); `load_index() -> dict | None`; `rank(query, entries) -> list[tuple[entry, float, int]]` best-first (sort key `(-score, name)`); `search(topic, limit=10) -> int` printing `name | kind | tier | scope | description | path` lines; `index_path() -> Path`; `main(argv=None) -> int` with `--search TOPIC [--limit N]` (hook mode arrives in Task 2 — for now `main` without `--search` returns 0 doing nothing); module constants per Global Constraints.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieve.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/test_retrieve.py`
Expected: `ModuleNotFoundError: No module named 'retrieve'`

- [ ] **Step 3: Implement the retriever core**

Create `scripts/retrieve.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/test_retrieve.py`
Expected: 6× `PASS`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/retrieve.py tests/test_retrieve.py
git commit -m "feat: bm25 retriever core with ungated search mode

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Retriever hook mode — gates, dedupe, budget, injection output

**Files:**
- Modify: `scripts/retrieve.py` (add `eligible`, `load_state`, `save_state`, `run_hook`; wire into `main`)
- Test: `tests/test_retrieve.py` (add hook-mode tests)

**Interfaces:**
- Consumes: everything Task 1 produced (same file); `ledger.log_event(event_type, skill, *, tier=, trigger=, session=)`.
- Produces: `run_hook(data: dict) -> int` — takes the parsed hook-stdin dict (`prompt`, `session_id`, `cwd`), prints the hook JSON (or nothing) and returns 0; `eligible(entry, cwd) -> bool`; `load_state(session) -> set`, `save_state(session, names)`. `main` without `--search` now parses stdin JSON and calls `run_hook`. Task 4 wires `python3 .../retrieve.py` into hooks.json.

- [ ] **Step 1: Add the failing hook-mode tests**

Append to `tests/test_retrieve.py` (before the `__main__` block):

```python
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
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 tests/test_retrieve.py`
Expected: the 8 new tests FAIL (`run_hook` raises AttributeError → note: AttributeError is not AssertionError, so the run aborts at the first hook test with a traceback and nonzero exit — that IS the red state; record it). Task 1's 6 tests still pass when run before the abort.

- [ ] **Step 3: Implement hook mode**

In `scripts/retrieve.py`, add after `search()`:

```python
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
```

And replace `return 0  # hook mode lands in the next task` in `main()` with:

```python
        return run_hook(json.load(sys.stdin))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/test_retrieve.py`
Expected: 14× `PASS`, exit 0. Also re-run the other four suites — still green.

- [ ] **Step 5: Commit**

```bash
git add scripts/retrieve.py tests/test_retrieve.py
git commit -m "feat: prompt-time injection hook mode with gates and dedupe

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Tiering + index compilation in sync; save path re-syncs

**Files:**
- Modify: `scripts/sync.py` (hot budget, ranking, index, state cleanup; remove `materialize_one` wrapper)
- Modify: `scripts/save_skill.py` (call `sync.sync()` instead of direct materialization)
- Test: `tests/test_sync.py`, `tests/test_save_skill.py` (additions)

**Interfaces:**
- Consumes: `trust.store_skill_files(base)`, `trust.skill_name(text, fallback)`, `trust.check_text(name, text)`; `ledger.connect()` and view `skill_aggregates(skill, uses, ..., injections, ...)`; `save_skill.parse_frontmatter` (lazy import inside sync to avoid the module cycle — save_skill imports sync at module level).
- Produces: `sync.sync(project_root=None) -> {"materialized","evicted","quarantined"}` (same signature; now also tiers, writes `index.json`, cleans stale state files); `sync.est_tokens(text) -> int`; `sync.hot_budget() -> int` (env `SKILLFORGE_HOT_BUDGET`, default 1500); `materialize_one_text(text, native_dir)` unchanged. **`sync.materialize_one` is REMOVED** — `save_skill.py` now calls `sync.sync()`. Index schema consumed by Tasks 1-2: `{"compiled_ts", "hot_budget_tokens", "entries": [{name, kind, scope, root, description, tier, est_tokens, path}]}`.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_sync.py` (before `__main__`; module already imports `os`, `pathlib`, `sync`, `trust` and defines `in_sandbox`, `put_skill`, `native_md`):

```python
def read_index(home):
    import json
    return json.loads((home / ".claude" / "skillforge" / "index.json").read_text(encoding="utf-8"))


def with_budget(value, fn):
    old = os.environ.get("SKILLFORGE_HOT_BUDGET")
    os.environ["SKILLFORGE_HOT_BUDGET"] = value
    try:
        fn()
    finally:
        if old is None:
            del os.environ["SKILLFORGE_HOT_BUDGET"]
        else:
            os.environ["SKILLFORGE_HOT_BUDGET"] = old


def test_hot_budget_overflow_goes_warm():
    def check(home):
        import ledger
        for name in ("alpha", "beta"):
            md = put_skill(home, name)
            trust.record(name, md.read_text(encoding="utf-8"), "self")
        ledger.log_event("injection", "beta")
        ledger.log_event("injection", "beta")

        def run():
            counts = sync.sync()
            tiers = {e["name"]: e["tier"] for e in read_index(home)["entries"]}
            assert tiers == {"beta": "hot", "alpha": "warm"}
            assert native_md(home, "beta").exists()
            assert not native_md(home, "alpha").exists()
            assert counts["materialized"] == 1
        with_budget("10", run)
    in_sandbox(check)


def test_index_contains_trusted_only_with_paths():
    def check(home):
        md = put_skill(home, "alpha")
        trust.record("alpha", md.read_text(encoding="utf-8"), "self")
        put_skill(home, "gamma")  # never recorded -> quarantined
        sync.sync()
        idx = read_index(home)
        names = [e["name"] for e in idx["entries"]]
        assert names == ["alpha"]
        e = idx["entries"][0]
        assert e["tier"] == "hot" and e["kind"] == "skill" and e["scope"] == "global"
        assert e["root"] == str(home)
        assert pathlib.Path(e["path"]).is_file()
        assert e["description"].startswith("A thing.")
    in_sandbox(check)


def test_stale_session_state_cleanup():
    def check(home):
        import time
        d = home / ".claude" / "skillforge" / "state"
        d.mkdir(parents=True)
        old = d / "session-old.json"
        new = d / "session-new.json"
        old.write_text("[]", encoding="utf-8")
        new.write_text("[]", encoding="utf-8")
        stale = time.time() - 8 * 86400
        os.utime(old, (stale, stale))
        sync.sync()
        assert not old.exists()
        assert new.exists()
    in_sandbox(check)
```

Append to `tests/test_save_skill.py` (before `__main__`; it already has `in_sandbox`, `write_draft`, `VALID_SKILL`, `io`, `redirect_stdout`):

```python
def test_save_with_zero_hot_budget_reports_warm():
    def check(home, tmp):
        old = os.environ.get("SKILLFORGE_HOT_BUDGET")
        os.environ["SKILLFORGE_HOT_BUDGET"] = "0"
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
            assert rc == 0
            assert "warm tier" in out.getvalue()
            assert not (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
            assert (home / ".claude/skillforge/index.json").exists()
        finally:
            if old is None:
                del os.environ["SKILLFORGE_HOT_BUDGET"]
            else:
                os.environ["SKILLFORGE_HOT_BUDGET"] = old
    in_sandbox(check)
```

(`tests/test_save_skill.py` needs `import os` added if not already present.)

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 tests/test_sync.py; python3 tests/test_save_skill.py`
Expected: the three new sync tests FAIL (no index written — `read_index` raises FileNotFoundError, which aborts the run with a traceback: that is the red state); the new save test FAILS ("warm tier" never printed). All pre-existing tests pass when run before any abort.

- [ ] **Step 3: Implement tiering + index in sync.py**

Replace `scripts/sync.py`'s imports and everything from `sync_base` through `sync` with the following (keep `native_root`, `materialize_one_text`, and `main` as they are; DELETE the old `materialize_one` wrapper and `sync_base`):

```python
import argparse
import datetime
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import trust
```

```python
def est_tokens(text):
    return max(1, len(text) // 4)


def hot_budget():
    try:
        return int(os.environ.get("SKILLFORGE_HOT_BUDGET", "1500"))
    except ValueError:
        return 1500


def _description(text):
    # ponytail: lazy import avoids a save_skill<->sync module cycle;
    # save_skill imports sync at module level, we only need its parser here
    from save_skill import parse_frontmatter
    fm, _ = parse_frontmatter(text)
    desc = (fm or {}).get("description", "")
    return desc if isinstance(desc, str) else ""


def _usage_stats():
    """{skill: [uses+injections, last_save_ts]}; empty on any ledger failure."""
    stats = {}
    try:
        con = ledger.connect()
        try:
            for skill, uses, injections in con.execute(
                    "SELECT skill, uses, injections FROM skill_aggregates"):
                stats[skill] = [(uses or 0) + (injections or 0), ""]
            for skill, ts in con.execute(
                    "SELECT skill, MAX(ts) FROM events WHERE event_type='save' GROUP BY skill"):
                stats.setdefault(skill, [0, ""])[1] = ts or ""
        finally:
            con.close()
    except Exception:
        pass
    return stats


def _write_index(items):
    p = Path.home() / ".claude" / "skillforge" / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    entries = [{"name": s["name"], "kind": s["kind"], "scope": s["scope"],
                "root": str(s["base"]), "description": s["description"],
                "tier": s["tier"], "est_tokens": est_tokens(s["text"]),
                "path": str(s["path"])} for s in items]
    p.write_text(json.dumps({
        "compiled_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "hot_budget_tokens": hot_budget(),
        "entries": entries}, indent=2), encoding="utf-8")


def _cleanup_state():
    d = Path.home() / ".claude" / "skillforge" / "state"
    if not d.is_dir():
        return
    cutoff = time.time() - 7 * 86400
    for f in d.glob("session-*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def sync(project_root=None):
    counts = {"materialized": 0, "evicted": 0, "quarantined": 0}
    bases = [Path.home()]
    if project_root:
        proj = Path(project_root)
        if proj.resolve() != Path.home().resolve() and (proj / ".claude" / "skillforge").is_dir():
            bases.append(proj)

    trusted = []
    for base in bases:
        for md in trust.store_skill_files(base):
            text = md.read_text(encoding="utf-8")
            name = trust.skill_name(text, md.parent.name)
            if trust.check_text(name, text) == "trusted":
                trusted.append({
                    "base": base, "name": name, "text": text, "path": md,
                    "kind": "antiskill" if md.parent.parent.name == "antiskills" else "skill",
                    "scope": "project" if base != Path.home() else "global",
                    "description": _description(text)})
            else:
                counts["quarantined"] += 1

    # Interim hot ranking (placeholder until slice C buckets):
    # (uses+injections) DESC, last save ts DESC, name ASC — via chained stable sorts.
    stats = _usage_stats()
    trusted.sort(key=lambda s: s["name"])
    trusted.sort(key=lambda s: stats.get(s["name"], [0, ""])[1], reverse=True)
    trusted.sort(key=lambda s: stats.get(s["name"], [0, ""])[0], reverse=True)

    budget = hot_budget()
    spent = 0
    for s in trusted:
        cost = est_tokens(s["description"])
        if spent + cost <= budget:
            s["tier"] = "hot"
            spent += cost
        else:
            s["tier"] = "warm"

    for s in trusted:
        if s["tier"] == "hot":
            materialize_one_text(s["text"], native_root(s["base"]) / s["name"])
            counts["materialized"] += 1

    for base in bases:
        keep = {s["name"] for s in trusted if s["base"] == base and s["tier"] == "hot"}
        nroot = native_root(base)
        if nroot.is_dir():
            for entry in sorted(nroot.iterdir()):
                if entry.is_dir() and entry.name not in keep:
                    shutil.rmtree(str(entry))
                    counts["evicted"] += 1

    _write_index(trusted)
    _cleanup_state()
    return counts
```

In `scripts/save_skill.py`, replace the post-save tail (the `trust.record` through the two prints) with:

```python
    trust.record(fm["name"], text, "self")
    ledger.log_event("save", fm["name"], outcome="saved")

    sync.sync(project_root=args.project_root if args.scope == "project" else None)

    native = native_dir(args.scope, fm["name"], args.project_root)
    print("saved: %s" % (dest / "SKILL.md"))
    if (native / "SKILL.md").exists():
        print("materialized: %s" % (native / "SKILL.md"))
    else:
        print("indexed: warm tier (hot budget full)")
    return 0
```

- [ ] **Step 4: Run ALL suites**

Run: `for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done`
Expected: no `FAILED:` lines. test_sync now 10 tests, test_save_skill now 20, test_retrieve 14, others unchanged. Every pre-existing sync/save test must pass against the new `sync()` (small descriptions fit the default 1500 budget, so prior expectations hold).

- [ ] **Step 5: Commit**

```bash
git add scripts/sync.py scripts/save_skill.py tests/test_sync.py tests/test_save_skill.py
git commit -m "feat: hot-budget tiering and retrieval index compiled by sync

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Wiring — UserPromptSubmit hook, /find command, README

**Files:**
- Modify: `hooks/hooks.json`
- Create: `commands/find.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `retrieve.py` hook + `--search` modes (Tasks 1-2).
- Produces: hook wiring + `/skillforge:find`. No code interfaces. Config/prompt files — verified by Task 5.

- [ ] **Step 1: Replace hooks.json**

`hooks/hooks.json` becomes:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/sync.py\" --project-root \"${CLAUDE_PROJECT_DIR:-.}\""
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/retrieve.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Create the /find command**

Create `commands/find.md`:

```markdown
---
description: Search the SkillForge library (cold-tier pull path)
argument-hint: "<topic>"
---

Search the SkillForge library for skills matching a topic.

1. Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve.py" --search "$ARGUMENTS"`
2. Present the hits as a short table: name, kind, tier, description.
3. Offer to show any hit in full; if the user asks, read the file at its
   listed path and display it.
4. No matches → say so, and if the knowledge ought to exist suggest
   /skillforge:learn to capture it.
```

- [ ] **Step 3: Update README usage section**

In `README.md`, add to the command list in `## Usage`:

```markdown
- `/skillforge:find <topic>` — search the whole library (hot + warm) and
  pull anything the automatic paths didn't surface.
```

and append after the trust-model paragraph:

```markdown
Delivery tiers (v0.2): trusted skills compete for a fixed hot budget
(1,500 description-tokens) ranked by usage — winners are materialized as
native skills; the rest stay warm in a BM25 retrieval index and are
injected per-prompt by a UserPromptSubmit hook (max 3 skills, 1,200-token
budget, session dedupe, two-matched-terms minimum). Anti-skills bypass
the count cap. Everything injected is logged to the ledger.
```

- [ ] **Step 4: Commit**

```bash
git add hooks/hooks.json commands/find.md README.md
git commit -m "feat: retrieval hook wiring, /find command, tiering docs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end verification

**Files:**
- No new files (fixes only if smoke uncovers problems).

**Interfaces:** consumes everything above.

- [ ] **Step 1: Full test suite**

```bash
for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done
```
Expected: no `FAILED:` lines across all six files.

- [ ] **Step 2: Tier-split + retrieval round trip in a sandbox HOME**

`$SCRATCH` = session scratchpad. Create two drafts:

```bash
SB="$SCRATCH/slice-b-home"; rm -rf "$SB"; mkdir -p "$SB"
cat > "$SCRATCH/b1.md" <<'EOF'
---
name: kraken-webhook-verify
kind: skill
scope: global
description: >
  Verify kraken exchange webhook signatures.
  Use when: handling kraken webhook callbacks.
  Do NOT use when: other exchanges.
verification.command: "true"
fingerprints:
  - "kraken_sig_check(payload)"
  - "KRAKEN_WEBHOOK_SECRET"
---
## Procedure
1. Verify the kraken webhook signature against the raw body.

## Verification
- `true` exits 0.
EOF
sed -e 's/kraken/csvmap/g; s/webhook/import/g; s/signatures/columns/g; s/callbacks/uploads/g; s/exchanges/formats/g; s/signature against the raw body/column mapping/g' \
    -e 's/name: csvmap-import-verify/name: csvmap-import-verify/' "$SCRATCH/b1.md" > "$SCRATCH/b2.md"
HOME="$SB" python3 scripts/save_skill.py "$SCRATCH/b1.md" --scope global
HOME="$SB" python3 scripts/save_skill.py "$SCRATCH/b2.md" --scope global
HOME="$SB" SKILLFORGE_HOT_BUDGET=10 python3 scripts/sync.py
HOME="$SB" python3 - <<'EOF'
import json, os, pathlib
idx = json.loads((pathlib.Path.home()/".claude/skillforge/index.json").read_text())
print(sorted((e["name"], e["tier"]) for e in idx["entries"]))
EOF
```
Expected: two saves succeed; after the budget-squeezed sync, exactly one entry is `hot` and one `warm` (the later-saved skill wins the recency tiebreak). Confirm the warm one's native dir is absent under `$SB/.claude/skills/skillforge-hot/`.

Then the hook (prompt targets the WARM skill — pick whichever of kraken/csvmap is warm; example assumes kraken is warm):

```bash
echo '{"session_id":"e2e","prompt":"verify a kraken webhook signature","cwd":"'"$SB"'"}' \
  | HOME="$SB" python3 scripts/retrieve.py
echo '{"session_id":"e2e","prompt":"verify a kraken webhook signature","cwd":"'"$SB"'"}' \
  | HOME="$SB" python3 scripts/retrieve.py
HOME="$SB" python3 scripts/ledger.py show kraken-webhook-verify
HOME="$SB" python3 scripts/retrieve.py --search "webhook signature"
```
Expected: first call prints hook JSON whose additionalContext contains the warm skill's full body; second call prints nothing (session dedupe); ledger `show` lists an `injection` event (`tier=warm trigger=prompt`); `--search` lists the skill regardless of tier.

- [ ] **Step 3: Hook config check**

```bash
python3 -c "import json; h=json.load(open('hooks/hooks.json')); assert 'UserPromptSubmit' in h['hooks']; print('hooks.json valid')"
```
Expected: `hooks.json valid`. (Live SessionStart/UserPromptSubmit firing in a real `claude` session remains on the follow-up list from Slice A — do not block on it here; the stdin round trip above exercises the identical code path.)

- [ ] **Step 4: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "chore: slice B end-to-end verification fixes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** Index §1 → Task 3 (`_write_index`, schema identical to spec). Hot budget §2 → Task 3 (rank, `SKILLFORGE_HOT_BUDGET`, eviction of warm natives). Retriever §3 → Tasks 1-2 (all six gates in the spec's order; try/except-exit-0; sanitized session ids). `/find` §4 → Task 1 (`--search`) + Task 4 (command). Housekeeping §5 → Task 3 (`_cleanup_state`) + Task 4 (hooks.json). Error handling → Tasks 1-3 (corrupt index → None; ledger failure → stderr, injection still emitted; state unreadable → empty set). Testing section → mapped 1:1 onto the task test lists. E2E → Task 5.
- **Deliberate simplifications:** `main()` in retrieve.py doesn't guard argparse's SystemExit (hooks never pass bad args); index rebuilt wholesale on save even for global-scope saves in a project (cheap at this scale); the sed-generated second draft in Task 5 is just a convenient distinct fixture — if sed mangles it, hand-write a csv-import draft instead.
- **Type consistency:** `run_hook(data) -> int` (Task 2) matches `main`'s call; `rank` tuple shape `(entry, score, matched)` used identically in `search`/`run_hook`; index entry keys identical across Task 3 writer, Task 1-2 readers, and both test fixture builders; `est_tokens` = `max(1, len//4)` in both sync (Task 3) and retrieve's inline cost (Task 2); `sync.sync()` signature/return unchanged from Slice A so existing callers (`main`, tests) hold; `materialize_one` deletion is safe — the only caller was `save_skill.py`, rewritten in the same task.
