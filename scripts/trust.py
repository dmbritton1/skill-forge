#!/usr/bin/env python3
"""Local trust registry (spec 11.2): skill id -> approved content hash.

A skill file is instructions destined for the model's context, so pulled
files are payloads until locally approved. trust.json lives only in the
global store and is NEVER committed. Hashes cover the exact bytes that get
materialized (CRLF-normalized, no stripping): mutable state lives in the
ledger, never in SKILL.md, so any file change -- including status lines --
re-quarantines (spec 11.2 "modification re-quarantines").
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger


def default_path():
    return Path.home() / ".claude" / "skillforge" / "trust.json"


def content_hash(text):
    text = text.replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path=None):
    p = Path(path) if path else default_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print("trust: WARNING unreadable trust.json (%s); treating all skills as untrusted"
                  % e, file=sys.stderr)
            return {}
    return {}


def save(reg, path=None):
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record(name, text, origin, path=None):
    reg = load(path)
    h = content_hash(text)
    reg[name] = {
        "hash": h,
        "approved_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "origin": origin,
    }
    save(reg, path)
    return h


def skill_name(text, fallback):
    m = re.search(r"^name:\s*(\S+)\s*$", text, re.M)
    return m.group(1) if m else fallback


def check_text(name, text, path=None):
    entry = load(path).get(name)
    if entry is None:
        return "quarantined"
    if entry["hash"] != content_hash(text):
        return "modified"
    return "trusted"


def check(file_path, path=None):
    p = Path(file_path)
    text = p.read_text(encoding="utf-8")
    return check_text(skill_name(text, p.parent.name), text, path)


def store_skill_files(base):
    """Yield every SKILL.md under <base>/.claude/skillforge/{skills,antiskills}/*/."""
    root = Path(base) / ".claude" / "skillforge"
    for sub in ("skills", "antiskills"):
        d = root / sub
        if d.is_dir():
            for skill_dir in sorted(p for p in d.iterdir() if p.is_dir()):
                md = skill_dir / "SKILL.md"
                if md.is_file():
                    yield md


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("file")
    a = sub.add_parser("approve")
    a.add_argument("file")
    q = sub.add_parser("list-quarantined")
    q.add_argument("--project-root")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        status = check(args.file)
        print(status)
        return 0 if status == "trusted" else 1

    if args.cmd == "approve":
        p = Path(args.file)
        text = p.read_text(encoding="utf-8")
        name = skill_name(text, p.parent.name)
        record(name, text, "reviewed")
        ledger.log_event("review", name, outcome="approved")
        print("approved: %s (%s)" % (name, p))
        return 0

    bases = [Path.home()]
    if args.project_root:
        bases.append(Path(args.project_root))
    found = 0
    for base in bases:
        for md in store_skill_files(base):
            status = check(md)
            if status != "trusted":
                print("%s\t%s" % (status, md))
                found += 1
    if not found:
        print("no quarantined skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
