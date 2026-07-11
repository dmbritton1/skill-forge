#!/usr/bin/env python3
"""Trust-gated native materialization — the ONLY writer of native skill dirs.

Native copies under <base>/.claude/skills/skillforge-hot/ are derived,
rebuildable cache: trusted store skills get materialized, everything else
(quarantined, modified, deleted, orphaned) gets evicted. Runs on every
SessionStart so a pulled/tampered skill never rides an old trust decision
into context (spec 11.2 "modification re-quarantines").
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust


def native_root(base):
    return Path(base) / ".claude" / "skills" / "skillforge-hot"


def materialize_one_text(text, native_dir):
    """Idempotent write-through of skill text into its native dir."""
    native_dir = Path(native_dir)
    native_dir.mkdir(parents=True, exist_ok=True)
    target = native_dir / "SKILL.md"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")


def materialize_one(md_path, native_dir):
    """Read one SKILL.md and delegate to materialize_one_text. Used by save_skill.py."""
    materialize_one_text(Path(md_path).read_text(encoding="utf-8"), native_dir)


def sync_base(base, counts):
    base = Path(base)
    trusted = set()
    for md in trust.store_skill_files(base):
        text = md.read_text(encoding="utf-8")
        name = trust.skill_name(text, md.parent.name)
        if trust.check_text(name, text) == "trusted":
            trusted.add(name)
            materialize_one_text(text, native_root(base) / name)
            counts["materialized"] += 1
        else:
            counts["quarantined"] += 1
    nroot = native_root(base)
    if nroot.is_dir():
        for entry in sorted(nroot.iterdir()):
            if entry.is_dir() and entry.name not in trusted:
                shutil.rmtree(str(entry))
                counts["evicted"] += 1
    return counts


def sync(project_root=None):
    counts = {"materialized": 0, "evicted": 0, "quarantined": 0}
    sync_base(Path.home(), counts)
    if project_root:
        proj = Path(project_root)
        if proj.resolve() != Path.home().resolve() and (proj / ".claude" / "skillforge").is_dir():
            sync_base(proj, counts)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root")
    args = ap.parse_args(argv)
    try:
        counts = sync(project_root=args.project_root)
        if counts["quarantined"]:
            print("skillforge: %d skill(s) quarantined pending /skillforge:review"
                  % counts["quarantined"])
    except Exception as e:
        print("skillforge: sync failed: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
