#!/usr/bin/env python3
"""Validate, secret-scan, and save a distilled skill (spec 4, 6, 11.1).

The single enforced write path into the knowledge store. Validates
format, runs the blocking secret scan, writes SKILL.md into the store,
and materializes a native copy where Claude Code loads skills once it
clears the hot-tier gate (v0.2: working-or-better confidence, ranked by
usage within a fixed token budget).

Usage: save_skill.py DRAFT.md --scope {global,project} [--project-root DIR]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secscan import scan_text
import ledger
import patterns
import sync
import trust

REQUIRED_KEYS = ("name", "kind", "description")
KINDS = ("skill", "antiskill", "preference")
NAME_RX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ANTISKILL_SECTIONS = ("## Trap", "## Symptom", "## Cause", "## Fix")
MIN_SYMPTOM_CHARS = 8
MIN_SYMPTOM_TOKENS = 2


def parse_frontmatter(text):
    """Return (dict, body) from a --- fenced frontmatter block, or (None, text).

    ponytail: line-based parse, no YAML dep -- the distiller controls the
    format. Handles top-level `key: value` and folded scalars (`key: >`);
    nested maps (e.g. preconditions) are skipped, not needed for validation.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    try:
        end = text.index("\n---\n", 4)
        body_start = end + 5
    except ValueError:
        if text.endswith("\n---"):
            end = len(text) - 4
            body_start = len(text)
        else:
            return None, text
    fm = {}
    lines = text[4:end].split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z][\w.-]*):\s*(.*)$", lines[i])
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
            if val == "":
                items = []
                j = i + 1
                while j < len(lines) and re.match(r"^\s+-\s+", lines[j]):
                    item = re.sub(r"^\s+-\s+", "", lines[j]).strip()
                    if len(item) >= 2 and item[0] == item[-1] and item[0] in "'\"":
                        item = item[1:-1]
                    items.append(item)
                    j += 1
                if items:
                    fm[key] = items
                    i = j
                    continue
            fm[key] = val
        i += 1
    return fm, text[body_start:]


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
    if kind == "skill" and not fm.get("verification.command"):
        errors.append("skills require frontmatter 'verification.command' (v0.2 slice A design §4)")
    if kind == "antiskill":
        for section in ANTISKILL_SECTIONS:
            if section not in body:
                errors.append("antiskills require a %r section (spec 4.2)" % section)
        syms = fm.get("symptoms")
        if not isinstance(syms, list) or not syms:
            errors.append("antiskills require a 'symptoms:' frontmatter list of literal "
                          "error signatures (v0.2 slice C1 design §1)")
        else:
            for s in syms:
                s = str(s)
                if len(s) < MIN_SYMPTOM_CHARS or len(patterns.tokenize(s)) < MIN_SYMPTOM_TOKENS:
                    errors.append(
                        "symptom %r is too weak to match on: need at least %d characters "
                        "and %d tokens" % (s, MIN_SYMPTOM_CHARS, MIN_SYMPTOM_TOKENS))
    return errors


def store_dir(scope, kind, name, project_root):
    sub = "antiskills" if kind == "antiskill" else "skills"
    # .resolve() so "." (the --project-root default) resolves against cwd
    # the same way Path.home() is already absolute -- sync.sync() already
    # applies this discipline; without it, the collision guard's relative
    # "project" candidate never equals the absolute "global" this_dir even
    # when they're the same directory, so re-saving from $HOME self-rejects.
    base = Path(project_root).resolve() if scope == "project" else Path.home().resolve()
    return base / ".claude" / "skillforge" / sub / name


def native_dir(scope, name, project_root):
    base = Path(project_root).resolve() if scope == "project" else Path.home().resolve()
    return base / ".claude" / "skills" / "skillforge-hot" / name


def _warm_reason(name):
    """Why `name` landed warm instead of hot, read from the index sync just wrote.

    Two real reasons: not yet hot-eligible (bucket unproven), or hot-eligible
    but budget-full. Never raises -- a missing/unreadable index falls back to
    the budget wording rather than breaking the save path.
    """
    try:
        idx = json.loads((Path.home() / ".claude" / "skillforge" / "index.json")
                         .read_text(encoding="utf-8"))
        for e in idx.get("entries", []):
            if e.get("name") == name:
                if e.get("bucket") not in ("working", "trusted"):
                    return "unproven -- earns hot once a real session verifies it"
                break
    except Exception:
        pass
    return "hot budget full"


def _spawn_validation(name, mode):
    """Detached, never waited on; its own function so tests replace it.

    Plain os.environ, NOT dict(os.environ, SKILLFORGE_DRAFTING="1"): unlike
    draft.py, validate.py's own main() self-checks that flag (it is not a
    registered hook, but Task 4 gave it the same guard anyway) and returns
    before doing anything if it is set. Forcing it here would make every
    real save spawn a critique run that no-ops instantly -- critique would
    never actually run. Inheriting os.environ unchanged still lets the flag
    through when it is genuinely already set (save_skill running inside a
    drafting session), which is the one case where going inert is correct;
    validate.py sets it on its own `claude -p` child itself (validate.py:54,
    :72), so that nested session's hooks still go inert regardless.
    """
    argv = [sys.executable,
            str(Path(__file__).resolve().parent / "validate.py"), mode,
            "--skill", name]
    subprocess.Popen(argv, cwd=str(Path(__file__).resolve().parent.parent),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True,
                     env=os.environ)


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

    # Name collisions are checked across both kinds AND both scopes.
    # Same-scope opposite-kind: skills and antiskills of the same name share
    # one native dir (skills/skillforge-hot/<name>) and would clobber each
    # other's native copy. Cross-scope (either kind): trust.json is keyed by
    # name alone (spec 11.2), so a project antiskill named `foo` saved while
    # a global skill `foo` exists overwrites the one registry entry -- the
    # global one then hashes differently on the next sync, gets quarantined,
    # and its native copy is evicted; approving it back breaks the project
    # one, a permanent flip-flop. Fail closed on any of the four candidates,
    # skipping any that resolve to this save's own destination (global and
    # project store roots can coincide in odd setups).
    other_kind = "skill" if fm["kind"] == "antiskill" else "antiskill"
    other_scope = "project" if args.scope == "global" else "global"
    this_dir = store_dir(args.scope, fm["kind"], fm["name"], args.project_root)
    checked = set()
    for scope, kind in ((args.scope, other_kind),
                        (other_scope, fm["kind"]),
                        (other_scope, other_kind)):
        candidate = store_dir(scope, kind, fm["name"], args.project_root)
        if candidate == this_dir or candidate in checked:
            continue
        checked.add(candidate)
        if candidate.exists():
            print("REJECTED: name %r already used by a %s in the %s scope "
                  "(%s; native copies or the shared trust registry entry "
                  "would collide); pick a different name"
                  % (fm["name"], kind, scope, candidate))
            return 1

    fps = fm.get("fingerprints")
    if not isinstance(fps, list) or len(fps) < 2:
        print("WARNING: fewer than 2 fingerprints; outcome tracking (v0.2 slice C) will not see this skill")

    # sync drops single-token patterns (they would match nearly every command
    # or file), so a one-word command compiles to nothing and the skill gets
    # no usage detection at all -- silently, unless we say so here.
    for label, value in (("verification.command", fm.get("verification.command")),
                         ("fingerprints", fm.get("fingerprints"))):
        for item in (value if isinstance(value, list) else [value]):
            if item and len(patterns.tokenize(item)) < MIN_SYMPTOM_TOKENS:
                print("WARNING: %s %r is a single token; it will be dropped at "
                      "compile time and never match" % (label, item))

    dest = store_dir(args.scope, fm["kind"], fm["name"], args.project_root)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")

    trust.record(fm["name"], text, "self")
    ledger.log_event("save", fm["name"], outcome="saved")

    sync.sync(project_root=args.project_root)

    native = native_dir(args.scope, fm["name"], args.project_root)
    print("saved: %s" % (dest / "SKILL.md"))
    if (native / "SKILL.md").exists():
        print("materialized: %s" % (native / "SKILL.md"))
    else:
        print("indexed: warm tier (%s)" % _warm_reason(fm["name"]))

    # Legibility is checked on every save, detached: critique reads only the
    # text, so it needs no environment and the user waits on nothing.
    try:
        _spawn_validation(fm["name"], "critique")
    except Exception as err:
        print("skillforge: validation spawn failed: %s" % err, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
