#!/usr/bin/env python3
"""Trust-gated native materialization — the ONLY writer of native skill dirs.

Native copies under <base>/.claude/skills/skillforge-hot/ are derived,
rebuildable cache: trusted store skills get materialized, everything else
(quarantined, modified, deleted, orphaned) gets evicted. Runs on every
SessionStart so a pulled/tampered skill never rides an old trust decision
into context (spec 11.2 "modification re-quarantines").
"""
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


def native_root(base):
    return Path(base) / ".claude" / "skills" / "skillforge-hot"


def materialize_one_text(text, native_dir):
    """Idempotent write-through of skill text into its native dir."""
    native_dir = Path(native_dir)
    native_dir.mkdir(parents=True, exist_ok=True)
    target = native_dir / "SKILL.md"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")


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
        proj = Path(project_root).resolve()
        if proj != Path.home().resolve() and (proj / ".claude" / "skillforge").is_dir():
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
