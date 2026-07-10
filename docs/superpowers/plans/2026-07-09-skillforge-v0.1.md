# SkillForge v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship SkillForge v0.1 per spec Section 13 — a Claude Code plugin with `/skillforge:learn` and `/skillforge:learn-failure` that distill sessions into skills/anti-skills, block secrets on every save, write to the global/project knowledge stores, and materialize skills where Claude Code loads them natively. No hooks, no ledger, no retrieval.

**Architecture:** The plugin is the engine; learned skills are data living outside it (`~/.claude/skillforge/` global, `<repo>/.claude/skillforge/` project). Two engine skills teach the model the distillation procedure; two slash commands trigger them; one script (`save_skill.py`) is the single enforced write path — it validates format, runs the blocking secret scan (`secscan.py`), writes to the store, and copies the skill into a directory Claude Code natively loads (v0.1 = everything is hot; the library fits).

**Tech Stack:** Python 3.9 stdlib only (no third-party deps; no PyYAML — minimal line-based frontmatter parsing). Tests are plain `assert` functions with a stdlib runner (pytest is NOT installed on this machine). Plugin structure per Claude Code plugin conventions (`.claude-plugin/plugin.json`, `commands/`, `skills/`, `scripts/`).

**Spec:** `/Users/dwightbritton/Downloads/skillforge-architecture-v4.md` (draft 0.7). v0.1 scope is Section 13: "plugin scaffold, /learn + /learn-failure with the distillation engine skills, blocking secret scan on every save, storage layout, skills written to global/project stores, native triggering only. No hooks, no ledger."

## Global Constraints

- Python 3.9 compatible, **stdlib only** — no pip installs, runtime or dev.
- The secret scan is **blocking with no bypass flag** (spec 11.1: "Hits block the save"). `save_skill.py` is the only write path and always scans.
- Skill names are kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`); one directory per skill containing exactly `SKILL.md`.
- Store paths exactly per spec Section 4: global `~/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`; project `<repo>/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`.
- Native materialization: global → `~/.claude/skills/skillforge-hot/<name>/SKILL.md`; project → `<repo>/.claude/skills/skillforge-hot/<name>/SKILL.md` (spec Section 8: Claude Code does not scan the store itself).
- Skill `description` frontmatter must contain a "Do NOT use" clause (spec 4.1) — enforced in code.
- Skills (`kind: skill`) require a `## Verification` section; anti-skills require `## Trap`, `## Symptom`, `## Cause`, `## Fix` sections — enforced in code.
- All paths derive from `Path.home()` / `os.environ["HOME"]` so tests can redirect with a temp HOME.
- Every commit message ends with the line: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Run all tests with `python3 tests/test_<name>.py` (each file self-runs; exit code 0 = pass).

**Deliberately deferred to v0.2+ (do not build):** hooks, ledger, retrieval index, embeddings/duplicate-check automation, `fingerprints` and `verification.command` frontmatter (attribution pipeline), symptom lint, trust registry, `hot/` bookkeeping directory, tiering, `/find`, `/stats`, Tier A/B validation.

## File Structure

```
skill-forge/                              # this repo = the plugin
├── .claude-plugin/plugin.json            # plugin manifest
├── .gitignore
├── README.md                             # what it is, install, usage
├── commands/
│   ├── learn.md                          # /skillforge:learn
│   └── learn-failure.md                  # /skillforge:learn-failure
├── skills/
│   ├── distilling-skills/SKILL.md        # distillation contract (spec §6)
│   └── distilling-failures/SKILL.md      # anti-skill extraction (spec §4.2, §6)
├── scripts/
│   ├── secscan.py                        # blocking secret scan (spec §11.1)
│   └── save_skill.py                     # validate + scan + store + materialize
├── tests/
│   ├── test_secscan.py
│   └── test_save_skill.py
└── docs/superpowers/plans/               # this plan
```

---

### Task 1: Plugin scaffold + git init

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Produces: a valid Claude Code plugin root that later tasks drop `commands/`, `skills/`, `scripts/` into. Plugin name is `skillforge` (commands surface as `/skillforge:learn` etc.).

- [ ] **Step 1: Initialize git**

```bash
cd /Users/dwightbritton/Desktop/skill-forge
git init -b main
```

- [ ] **Step 2: Write the plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "skillforge",
  "version": "0.1.0",
  "description": "Self-improving skill library: distills coding sessions into skills and anti-skills, scans them for secrets, and serves them back natively in future sessions."
}
```

- [ ] **Step 3: Write .gitignore**

Create `.gitignore`:

```
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 4: Write README stub**

Create `README.md`:

```markdown
# SkillForge

A self-improving skill library for Claude Code, v0.1. Distills coding
sessions into reusable skills (`/skillforge:learn`) and debugging
dead-ends into anti-skills (`/skillforge:learn-failure`), blocks secrets
on every save, and materializes skills where Claude Code loads them.

Engine (this plugin) and knowledge (learned skills) are separate:

- Global store: `~/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`
- Project store: `<repo>/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`
- Native copies: `~/.claude/skills/skillforge-hot/` (global) or
  `<repo>/.claude/skills/skillforge-hot/` (project)

## Install (local development)

    claude --plugin-dir /Users/dwightbritton/Desktop/skill-forge

## Usage

- `/skillforge:learn [optional topic hint]` — distill the current session
  into a skill. Shows a draft for approval, then saves.
- `/skillforge:learn-failure [optional topic hint]` — distill a debugging
  trap into an anti-skill (Trap/Symptom/Cause/Fix format).

## Tests

    python3 tests/test_secscan.py
    python3 tests/test_save_skill.py

v0.1 scope: no hooks, no ledger, no retrieval — see
`docs/superpowers/plans/2026-07-09-skillforge-v0.1.md`.
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: skillforge plugin scaffold (v0.1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Secret scanner (`secscan.py`)

**Files:**
- Create: `scripts/secscan.py`
- Test: `tests/test_secscan.py`

**Interfaces:**
- Produces: `scan_text(text: str) -> list[tuple[int, str, str]]` — list of `(lineno, rule_name, stripped_line)` hits, empty list when clean. CLI: `python3 scripts/secscan.py FILE...` → exit 0 clean, exit 1 with `path:lineno: rule: line` per hit on stdout, exit 2 on usage error. Task 3 imports `scan_text` from this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_secscan.py`:

```python
"""Tests for the blocking secret scan (spec 11.1). Run: python3 tests/test_secscan.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from secscan import scan_text


def rules_hit(text):
    return {rule for _, rule, _ in scan_text(text)}


def test_detects_aws_access_key():
    assert "aws-access-key" in rules_hit("key = AKIAIOSFODNN7EXAMPLE")


def test_detects_github_token():
    assert "github-token" in rules_hit("export GH=ghp_" + "a1B2" * 9 + "x")


def test_detects_stripe_live_key():
    assert "stripe-key" in rules_hit("stripe.api_key = sk_live_" + "a" * 24)


def test_detects_slack_token():
    assert "slack-token" in rules_hit("token: xoxb-123456789012-abcdefghij")


def test_detects_private_key_block():
    assert "private-key-block" in rules_hit("-----BEGIN RSA PRIVATE KEY-----")
    assert "private-key-block" in rules_hit("-----BEGIN OPENSSH PRIVATE KEY-----")


def test_detects_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
    assert "jwt" in rules_hit("Authorization: " + jwt)


def test_detects_bearer_token():
    assert "bearer-token" in rules_hit("curl -H 'Authorization: Bearer abcdef1234567890ABCDEF99'")


def test_detects_connection_string_with_password():
    assert "connection-string" in rules_hit("DATABASE_URL=postgres://admin:hunter2secret@db.internal:5432/app")


def test_detects_quoted_secret_assignment():
    assert "assigned-secret" in rules_hit('api_key = "9f8e7d6c5b4a3210ffff"')
    assert "assigned-secret" in rules_hit("password: 'correct-horse-battery'")


def test_reports_line_numbers():
    hits = scan_text("clean line\nkey = AKIAIOSFODNN7EXAMPLE\n")
    assert hits[0][0] == 2


def test_clean_skill_text_passes():
    clean = """---
name: stripe-webhook-integration
kind: skill
description: >
  Set up a Stripe webhook endpoint with signature verification.
  Do NOT use when consuming webhooks from other providers.
---
## Procedure
1. Mount `express.raw({type: 'application/json'})` BEFORE any json middleware.
2. Read the signing secret from the environment; never hardcode it.

## Gotchas
- Signature verification requires the raw request body.

## Verification
- `stripe trigger payment_intent.succeeded` should return 200 and log the event.
"""
    assert scan_text(clean) == []


def test_plain_urls_are_not_connection_strings():
    assert scan_text("See https://docs.stripe.com/webhooks for details.") == []


def test_unquoted_prose_about_secrets_passes():
    assert scan_text("Read the webhook signing secret from the Stripe dashboard.") == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
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

Run: `python3 tests/test_secscan.py`
Expected: `ModuleNotFoundError: No module named 'secscan'` (import fails before any test runs).

- [ ] **Step 3: Implement the scanner**

Create `scripts/secscan.py`:

```python
#!/usr/bin/env python3
"""Blocking secret scan for skill drafts (spec 11.1).

Gitleaks-style pattern rules over candidate skill text. Any hit blocks
the save; the offending lines are printed for redaction. No bypass flag
by design.

Usage: secscan.py FILE...   (exit 0 clean, 1 hits, 2 usage error)
"""
import re
import sys

RULES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("stripe-key", re.compile(r"\b[rs]k_(live|test)_[0-9a-zA-Z]{24,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-.=]{16,}")),
    # user:password@host — plain URLs without credentials don't match
    ("connection-string", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@")),
    # quoted value assigned to a secret-ish name; unquoted prose passes
    ("assigned-secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
]


def scan_text(text):
    """Return [(lineno, rule_name, stripped_line)] for every rule hit."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in RULES:
            if rx.search(line):
                hits.append((lineno, name, line.strip()))
    return hits


def main(paths):
    failed = False
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for lineno, rule, line in scan_text(text):
            print("%s:%d: %s: %s" % (path, lineno, rule, line))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: secscan.py FILE...", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/test_secscan.py`
Expected: every line `PASS test_...`, exit 0. If a specific rule test fails, fix that regex — do not loosen the clean-text tests to compensate.

- [ ] **Step 5: Commit**

```bash
git add scripts/secscan.py tests/test_secscan.py
git commit -m "feat: blocking secret scan (spec 11.1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Save path (`save_skill.py`)

**Files:**
- Create: `scripts/save_skill.py`
- Test: `tests/test_save_skill.py`

**Interfaces:**
- Consumes: `scan_text(text) -> list[(lineno, rule, line)]` from `scripts/secscan.py` (same directory, plain `from secscan import scan_text`).
- Produces: CLI `python3 scripts/save_skill.py DRAFT.md --scope {global,project} [--project-root DIR]` → exit 0 and prints `saved: <store path>` + `materialized: <native path>`; exit 1 and prints `REJECTED: <reason>` per validation error or `SECRET BLOCKED <path>:<line>: <rule>: <text>` per scan hit. Also importable: `main(argv) -> int`, `validate(text) -> list[str]`, `parse_frontmatter(text) -> (dict | None, body)`. Tasks 4–5 tell the model to run this CLI.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_save_skill.py`:

```python
"""Tests for the enforced save path (spec 4, 6, 11.1). Run: python3 tests/test_save_skill.py"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import save_skill

VALID_SKILL = """---
name: test-skill
kind: skill
scope: global
description: >
  A test skill for the save path.
  Use when: testing SkillForge.
  Do NOT use when: doing anything real.
provenance:
  repo: local/skill-forge
  distilled: 2026-07-09
---
## Procedure
1. Do the thing.

## Verification
- `true` exits 0.
"""

VALID_ANTISKILL = """---
name: test-trap
kind: antiskill
scope: global
description: >
  A test trap. Use when: testing.
  Do NOT use when: doing anything real.
---
## Trap
Doing the wrong thing.

## Symptom
It fails.

## Cause
Wrongness.

## Fix
Do the right thing.

## Cost of rediscovery
~5 min
"""


def in_sandbox(fn):
    """Run fn(home, tmp) with HOME pointed at a fresh temp dir."""
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp), pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def write_draft(tmp, text):
    draft = tmp / "draft.md"
    draft.write_text(text, encoding="utf-8")
    return str(draft)


def test_valid_global_skill_saves_and_materializes():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        assert (home / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_antiskill_goes_to_antiskills_dir():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, VALID_ANTISKILL), "--scope", "global"])
        assert rc == 0
        assert (home / ".claude/skillforge/antiskills/test-trap/SKILL.md").exists()
        assert (home / ".claude/skills/skillforge-hot/test-trap/SKILL.md").exists()
    in_sandbox(check)


def test_project_scope_writes_under_project_root():
    def check(home, tmp):
        proj = tmp / "myrepo"
        proj.mkdir()
        rc = save_skill.main([write_draft(tmp, VALID_SKILL), "--scope", "project",
                              "--project-root", str(proj)])
        assert rc == 0
        assert (proj / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
        assert (proj / ".claude/skills/skillforge-hot/test-skill/SKILL.md").exists()
        assert not (home / ".claude/skillforge/skills/test-skill/SKILL.md").exists()
    in_sandbox(check)


def test_secret_blocks_save():
    def check(home, tmp):
        bad = VALID_SKILL + '\n2. Set api_key = "sk_live_' + "a" * 24 + '"\n'
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
        assert not (home / ".claude/skillforge/skills/test-skill").exists()
        assert not (home / ".claude/skills/skillforge-hot/test-skill").exists()
    in_sandbox(check)


def test_missing_verification_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("## Verification", "## Notes")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
        assert not (home / ".claude/skillforge/skills/test-skill").exists()
    in_sandbox(check)


def test_antiskill_missing_section_rejected():
    def check(home, tmp):
        bad = VALID_ANTISKILL.replace("## Cause", "## Reason")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_description_without_do_not_use_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("Do NOT use when: doing anything real.", "Always applicable.")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_bad_name_rejected():
    def check(home, tmp):
        bad = VALID_SKILL.replace("name: test-skill", "name: Test Skill!")
        rc = save_skill.main([write_draft(tmp, bad), "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_missing_frontmatter_rejected():
    def check(home, tmp):
        rc = save_skill.main([write_draft(tmp, "## Procedure\njust a body\n"),
                              "--scope", "global"])
        assert rc == 1
    in_sandbox(check)


def test_folded_description_is_parsed():
    fm, _ = save_skill.parse_frontmatter(VALID_SKILL)
    assert "Do NOT use when" in fm["description"]
    assert fm["name"] == "test-skill"


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

Run: `python3 tests/test_save_skill.py`
Expected: `ModuleNotFoundError: No module named 'save_skill'`.

- [ ] **Step 3: Implement the save path**

Create `scripts/save_skill.py`:

```python
#!/usr/bin/env python3
"""Validate, secret-scan, and save a distilled skill (spec 4, 6, 11.1).

The single enforced write path into the knowledge store. Validates
format, runs the blocking secret scan, writes SKILL.md into the store,
and materializes a native copy where Claude Code loads skills (v0.1:
every skill is hot -- the whole library fits in the budget).

Usage: save_skill.py DRAFT.md --scope {global,project} [--project-root DIR]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secscan import scan_text

REQUIRED_KEYS = ("name", "kind", "description")
KINDS = ("skill", "antiskill", "preference")
NAME_RX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ANTISKILL_SECTIONS = ("## Trap", "## Symptom", "## Cause", "## Fix")


def parse_frontmatter(text):
    """Return (dict, body) from a --- fenced frontmatter block, or (None, text).

    ponytail: line-based parse, no YAML dep -- the distiller controls the
    format. Handles top-level `key: value` and folded scalars (`key: >`);
    nested maps (e.g. preconditions) are skipped, not needed for validation.
    """
    if not text.startswith("---\n"):
        return None, text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return None, text
    fm = {}
    lines = text[4:end].split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", lines[i])
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in (">", "|", ">-", "|-"):
                block = []
                i += 1
                while i < len(lines) and (lines[i].startswith(" ") or not lines[i].strip()):
                    block.append(lines[i].strip())
                    i += 1
                fm[key] = " ".join(b for b in block if b)
                continue
            fm[key] = val
        i += 1
    return fm, text[end + 5:]


def validate(text):
    """Return a list of human-readable rejection reasons (empty = valid)."""
    fm, body = parse_frontmatter(text)
    if fm is None:
        return ["missing frontmatter (--- fenced block)"]
    errors = []
    for key in REQUIRED_KEYS:
        if not fm.get(key):
            errors.append("missing frontmatter key: %s" % key)
    kind = fm.get("kind", "")
    if kind and kind not in KINDS:
        errors.append("kind must be one of %s, got %r" % (list(KINDS), kind))
    name = fm.get("name", "")
    if name and not NAME_RX.match(name):
        errors.append("name must be kebab-case, got %r" % name)
    desc = fm.get("description", "")
    if desc and "do not use" not in desc.lower():
        errors.append("description must include a 'Do NOT use when' clause (spec 4.1)")
    if kind == "skill" and "## Verification" not in body:
        errors.append("skills require a '## Verification' section (spec 4.1)")
    if kind == "antiskill":
        for section in ANTISKILL_SECTIONS:
            if section not in body:
                errors.append("antiskills require a %r section (spec 4.2)" % section)
    return errors


def store_dir(scope, kind, name, project_root):
    sub = "antiskills" if kind == "antiskill" else "skills"
    base = Path(project_root) if scope == "project" else Path.home()
    return base / ".claude" / "skillforge" / sub / name


def native_dir(scope, name, project_root):
    base = Path(project_root) if scope == "project" else Path.home()
    return base / ".claude" / "skills" / "skillforge-hot" / name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("draft", help="path to the drafted SKILL.md")
    ap.add_argument("--scope", choices=("global", "project"), required=True)
    ap.add_argument("--project-root", default=".",
                    help="repo root for --scope project (default: cwd)")
    args = ap.parse_args(argv)

    text = Path(args.draft).read_text(encoding="utf-8")

    errors = validate(text)
    if errors:
        for e in errors:
            print("REJECTED: %s" % e)
        return 1

    # Blocking scan at the write path (spec 11.1) -- runs unconditionally,
    # independent of any scan the distiller already ran on the draft.
    hits = scan_text(text)
    if hits:
        for lineno, rule, line in hits:
            print("SECRET BLOCKED %s:%d: %s: %s" % (args.draft, lineno, rule, line))
        print("Save blocked. Redact the lines above and retry.")
        return 1

    fm, _ = parse_frontmatter(text)
    dest = store_dir(args.scope, fm["kind"], fm["name"], args.project_root)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")

    native = native_dir(args.scope, fm["name"], args.project_root)
    native.mkdir(parents=True, exist_ok=True)
    (native / "SKILL.md").write_text(text, encoding="utf-8")

    print("saved: %s" % (dest / "SKILL.md"))
    print("materialized: %s" % (native / "SKILL.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/test_save_skill.py`
Expected: all `PASS`, exit 0.
Also re-run: `python3 tests/test_secscan.py` — still all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add scripts/save_skill.py tests/test_save_skill.py
git commit -m "feat: enforced save path with validation and blocking scan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Distillation engine skill + /learn command

**Files:**
- Create: `skills/distilling-skills/SKILL.md`
- Create: `commands/learn.md`

**Interfaces:**
- Consumes: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_skill.py" DRAFT --scope ... [--project-root ...]` from Task 3 (exit 0 = saved, 1 = rejected/blocked with printed reasons).
- Produces: `/skillforge:learn` command; the `distilling-skills` skill that both the command and organic "distill this into a skill" requests trigger.

These are prompt files — no tests; verified by the Task 6 end-to-end pass. Content below is complete; write it verbatim.

- [ ] **Step 1: Write the engine skill**

Create `skills/distilling-skills/SKILL.md`:

````markdown
---
name: distilling-skills
description: >
  Distillation procedure for turning the current coding session into a
  reusable SkillForge skill. Use when: /skillforge:learn runs, or the
  user asks to capture/distill/save what was learned this session.
  Do NOT use when: distilling a failure, trap, or debugging dead-end
  (use distilling-failures), or when writing plugin/engine skills by hand.
---

# Distilling a Session into a Skill

Produce one candidate SKILL.md from the current session, get the user's
approval, then save it through the enforced write path. Never write skill
files directly — `save_skill.py` is the only save path (it validates,
secret-scans, and materializes).

## The distillation contract

Work through these in order. Aborting is a success outcome — say why in
one line and stop.

1. **Identify the distillable unit.** One procedure that worked, small
   enough to state as numbered steps. If the session contains several,
   ask the user which one (or use the topic hint from the command).

2. **Novelty self-gate.** Ask honestly: *would a fresh Claude instance
   actually not know this?* If the skill restates model-obvious knowledge
   (standard library usage, common framework patterns, anything you could
   produce without this session), ABORT the save and tell the user why.
   This kills junk saves.

3. **Duplicate check.** List existing skills:
   `ls ~/.claude/skillforge/skills/ 2>/dev/null; ls .claude/skillforge/skills/ 2>/dev/null`
   If an existing skill covers this, propose updating it instead of
   creating a sibling.

4. **Generalize.** Strip project-specific incidentals (paths, names,
   versions) unless the knowledge is genuinely project-specific. Test:
   "would a fresh Claude in a different repo benefit?"

5. **Assign scope.** Mentions repo-specific paths/conventions → `project`;
   otherwise `global`. Tell the user which you chose; they can override.

6. **Answer the one-shot question.** Write the body as what you would
   tell a fresh instance of yourself so it could do this in one pass:
   `## Procedure` (numbered steps), `## Gotchas` (if any), and a
   mandatory `## Verification` (a concrete command or check that proves
   the procedure worked).

7. **Write both trigger directions.** The `description` frontmatter MUST
   contain "Use when:" cases AND "Do NOT use when:" cases. Negative
   triggers fight over-injection; save_skill.py rejects drafts without them.

8. **Secret scan the draft yourself** before showing it:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/secscan.py" <draft-path>`
   Session transcripts routinely contain keys, tokens, and connection
   strings. Redact hits (replace with `<REDACTED>` placeholders that keep
   the instruction meaningful). save_skill.py scans again regardless.

## Skill format

```markdown
---
name: kebab-case-name
kind: skill
scope: global            # or project
description: >
  One-line summary.
  Use when: <positive triggers>.
  Do NOT use when: <negative triggers>.
provenance:
  repo: <org/repo or local dir name>
  commit: <short sha if in git, else omit>
  distilled: <YYYY-MM-DD>
---

## Procedure
1. ...

## Gotchas
- ...

## Verification
- `<command>` should <observable result>.
```

## Saving

1. Write the draft to the session scratchpad (not the store).
2. Show the full draft to the user and ask for approval. Human-in-the-loop
   at capture is what keeps garbage out — never silent auto-save.
3. On approval:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_skill.py" <draft-path> --scope <global|project> [--project-root <repo>]`
   (`--project-root` is the repo root; required in practice for project scope.)
4. Exit 0 → report the two printed paths. Exit 1 → fix the printed
   `REJECTED`/`SECRET BLOCKED` reasons and retry; never hand-copy the file
   into the store to work around a rejection.
````

- [ ] **Step 2: Write the /learn command**

Create `commands/learn.md`:

```markdown
---
description: Distill the current session into a reusable skill
argument-hint: "[optional topic hint]"
---

Distill this session into a SkillForge skill using the distilling-skills
skill — follow its contract exactly, including the novelty self-gate
(aborting because the knowledge is model-obvious is a good outcome, not a
failure), the duplicate check, the mandatory secret scan, and user
approval before saving.

Topic hint (may be empty): $ARGUMENTS
```

- [ ] **Step 3: Commit**

```bash
git add skills/distilling-skills/SKILL.md commands/learn.md
git commit -m "feat: distilling-skills engine skill and /learn command

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Anti-skill distillation + /learn-failure command

**Files:**
- Create: `skills/distilling-failures/SKILL.md`
- Create: `commands/learn-failure.md`

**Interfaces:**
- Consumes: same `save_skill.py` CLI as Task 4.
- Produces: `/skillforge:learn-failure` command; the `distilling-failures` skill.

- [ ] **Step 1: Write the engine skill**

Create `skills/distilling-failures/SKILL.md`:

````markdown
---
name: distilling-failures
description: >
  Anti-skill extraction: distill a debugging dead-end, trap, or corrected
  mistake from the current session into a SkillForge anti-skill.
  Use when: /skillforge:learn-failure runs, or the user asks to capture a
  gotcha/trap/failure so it never costs time again.
  Do NOT use when: distilling a successful procedure (use
  distilling-skills), or when the failure was a one-off typo with no
  reusable lesson.
---

# Distilling a Failure into an Anti-skill

Anti-skills document the trap, not a procedure. They are often
higher-value per token than success skills: short, and the downside of a
miss is a repeated multi-hour debugging pit.

## Procedure

1. **Find the trap.** Locate the point in the session where time was lost:
   what looked correct but wasn't? What was suspected first (wrongly)?
   Estimate the time cost from the transcript.

2. **Novelty self-gate.** Would a fresh Claude fall into this trap? If the
   mistake was a one-off (typo, stale cache, misread) with no reusable
   lesson, ABORT and say so.

3. **Duplicate check.**
   `ls ~/.claude/skillforge/antiskills/ 2>/dev/null; ls .claude/skillforge/antiskills/ 2>/dev/null`
   Existing anti-skill for this trap → propose updating it.

4. **Write the Symptom for a machine, not a narrator.** The Symptom
   section should lead with the literal error text or signature someone
   would see (exception name, error message fragment), then the misleading
   part — what it makes you wrongly suspect. In v0.2 this field becomes a
   machine-matchable trigger, so specificity matters: never a bare
   "Error" or a single common word.

5. **Assign scope** (same heuristic as skills: repo-specific → project,
   else global), **secret-scan the draft**
   (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/secscan.py" <draft-path>`),
   and redact any hits.

## Anti-skill format

All four of Trap/Symptom/Cause/Fix are mandatory — save_skill.py rejects
drafts missing any of them.

```markdown
---
name: kebab-case-name
kind: antiskill
scope: global            # or project
description: >
  One-line summary of the trap.
  Use when: <symptom or situation that should trigger this>.
  Do NOT use when: <situations that look similar but aren't this trap>.
provenance:
  repo: <org/repo or local dir name>
  distilled: <YYYY-MM-DD>
---

## Trap
What looked correct but silently breaks things.

## Symptom
The literal error/signature observed, and what it wrongly makes you suspect.

## Cause
The actual mechanism.

## Fix
The correction, concretely (code fragment if short).

## Cost of rediscovery
~<N> min (observed in source session)
```

## Saving

Identical to distilling-skills: draft in the scratchpad, show the user,
on approval run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_skill.py" <draft-path> --scope <global|project> [--project-root <repo>]`
and report the printed paths; on exit 1 fix the printed reasons and retry.
Never write into the store directly.
````

- [ ] **Step 2: Write the /learn-failure command**

Create `commands/learn-failure.md`:

```markdown
---
description: Distill a debugging trap from this session into an anti-skill
argument-hint: "[optional topic hint]"
---

Distill the failure/trap from this session into a SkillForge anti-skill
using the distilling-failures skill — follow its contract exactly,
including the novelty self-gate, the machine-readable Symptom rule, the
mandatory secret scan, and user approval before saving.

Topic hint (may be empty): $ARGUMENTS
```

- [ ] **Step 3: Commit**

```bash
git add skills/distilling-failures/SKILL.md commands/learn-failure.md
git commit -m "feat: distilling-failures engine skill and /learn-failure command

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: End-to-end verification

**Files:**
- No new files (fixes only, if the smoke test finds problems).

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Run the full test suite**

```bash
python3 tests/test_secscan.py && python3 tests/test_save_skill.py
```
Expected: all `PASS`, both exit 0.

- [ ] **Step 2: Smoke-test the save pipeline against a sandbox HOME**

Write a realistic draft to the scratchpad (use the session scratchpad
directory; `$SCRATCH` below stands for it) and run the real CLI with HOME
redirected:

```bash
cat > "$SCRATCH/draft.md" <<'EOF'
---
name: smoke-test-skill
kind: skill
scope: global
description: >
  Smoke test. Use when: verifying skillforge v0.1.
  Do NOT use when: anything else.
provenance:
  repo: local/skill-forge
  distilled: 2026-07-09
---
## Procedure
1. Run the smoke test.

## Verification
- `true` exits 0.
EOF
HOME="$SCRATCH/fakehome" python3 scripts/save_skill.py "$SCRATCH/draft.md" --scope global
find "$SCRATCH/fakehome" -name SKILL.md
```
Expected: exit 0; `find` lists
`.claude/skillforge/skills/smoke-test-skill/SKILL.md` and
`.claude/skills/skillforge-hot/smoke-test-skill/SKILL.md`.

Then plant a secret and confirm the block:

```bash
printf '\nSet STRIPE_KEY = "sk_live_%s"\n' "$(printf 'a%.0s' {1..24})" >> "$SCRATCH/draft.md"
HOME="$SCRATCH/fakehome2" python3 scripts/save_skill.py "$SCRATCH/draft.md" --scope global
echo "exit: $?"
find "$SCRATCH/fakehome2" -name SKILL.md
```
Expected: `SECRET BLOCKED` line(s), exit 1, `find` lists nothing.

- [ ] **Step 3: Verify the plugin loads in Claude Code**

```bash
claude --plugin-dir /Users/dwightbritton/Desktop/skill-forge -p "/skillforge:learn" --max-turns 1 2>&1 | head -20
```
Expected: the command resolves (output shows the distillation prompt being
acted on, not "unknown command"). If `--plugin-dir` is not a supported
flag in the installed Claude Code version, check `claude --help` for the
current local-plugin mechanism and update README's install section to
match reality — do not skip this step; native command/skill loading is
the v0.1 delivery mechanism.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: v0.1 end-to-end verification fixes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
(Skip the commit if nothing changed.)

---

## Self-review notes

- **Spec coverage (v0.1 items, Section 13):** plugin scaffold → Task 1; `/learn` + `/learn-failure` with distillation engine skills → Tasks 4–5; blocking secret scan on every save → Tasks 2–3 (scan enforced in the single write path, plus distiller-side scan instruction = the spec 11.1 double-check for project scope); storage layout + global/project stores → Task 3; native triggering only → Task 3 materialization + Task 6 Step 3. No hooks, no ledger — none built.
- **Deliberate v0.1 simplifications** (all spec-sanctioned deferrals, listed in Global Constraints): no `fingerprints`/`verification.command` frontmatter (attribution is v0.2; the audit backfills), no embeddings duplicate-check (`ls` + model judgment at this library size), no `hot/` bookkeeping dir (materialization is direct; the Maintainer that needs the record is v0.2+), no `status`-stripping on commit (trust registry is v0.2; single-user until then).
- **Type consistency:** `scan_text` signature identical in Tasks 2 and 3; `save_skill.py` CLI identical in Tasks 3, 4, 5, 6; store/native paths identical in Task 3 code, its tests, and Global Constraints.
