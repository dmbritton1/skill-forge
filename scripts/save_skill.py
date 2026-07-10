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
import ledger
import sync
import trust

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

    # Skills and antiskills of the same name share one native dir
    # (skills/skillforge-hot/<name>); a same-named pair from opposite
    # kinds would silently clobber each other's native copy there even
    # though their store dirs differ. Reject the second save instead.
    other_kind = "skill" if fm["kind"] == "antiskill" else "antiskill"
    other_dir = store_dir(args.scope, other_kind, fm["name"], args.project_root)
    if other_dir.exists():
        print("REJECTED: name %r already used by a %s in this scope "
              "(native copies would collide); pick a different name"
              % (fm["name"], other_kind))
        return 1

    fps = fm.get("fingerprints")
    if not isinstance(fps, list) or len(fps) < 2:
        print("WARNING: fewer than 2 fingerprints; outcome tracking (v0.2 slice C) will not see this skill")

    dest = store_dir(args.scope, fm["kind"], fm["name"], args.project_root)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")

    trust.record(fm["name"], text, "self")
    ledger.log_event("save", fm["name"], outcome="saved")

    native = native_dir(args.scope, fm["name"], args.project_root)
    sync.materialize_one(dest / "SKILL.md", native)

    print("saved: %s" % (dest / "SKILL.md"))
    print("materialized: %s" % (native / "SKILL.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
