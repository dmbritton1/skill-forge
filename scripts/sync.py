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
import patterns
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


def _meta(text):
    # ponytail: lazy import avoids a save_skill<->sync module cycle;
    # save_skill imports sync at module level, we only need its parser here
    from save_skill import parse_frontmatter
    fm, _ = parse_frontmatter(text)
    fm = fm or {}
    desc = fm.get("description", "")
    return {
        "description": desc if isinstance(desc, str) else "",
        "symptoms": _token_lists(fm.get("symptoms")),
        "fingerprints": _token_lists(fm.get("fingerprints")),
        "verification": _token_lists([fm.get("verification.command")]),
    }


def _token_lists(value):
    """[[token, ...], ...] from a frontmatter list; empties dropped.

    Single-token lists are dropped too: a verification.command or
    fingerprint that tokenizes to one common word (`pytest`, `make`) would
    then match nearly every Bash call or file, logging a bogus detection on
    every unrelated command and inflating skill_aggregates.uses (which feeds
    hot ranking). save_skill enforces a 2-token floor on symptoms already;
    this is the same floor for the other two pattern kinds.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not item:
            continue
        toks = patterns.tokenize(item)
        if len(toks) >= 2:
            out.append(toks)
    return out


BUCKET_RANK = {"trusted": 0, "working": 1, "unproven": 2}
HOT_ELIGIBLE = ("trusted", "working")
UNKNOWN = ("unproven", 0, "")


def _confidence():
    """{skill: (bucket, success_sessions, last_used)}; empty on any ledger failure.

    An empty map reads as `unproven` everywhere, which is the safe direction:
    a broken ledger empties the hot tier instead of promoting on stale data.
    """
    stats = {}
    try:
        con = ledger.connect()
        try:
            for skill, wins, last_used, bucket in con.execute(
                    "SELECT skill, success_sessions, last_used, bucket"
                    " FROM skill_confidence"):
                stats[skill] = (bucket or "unproven", wins or 0, last_used or "")
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
                "tier": s["tier"], "bucket": s["bucket"],
                "est_tokens": est_tokens(s["text"]),
                "fingerprints": s["fingerprints"],
                "path": str(s["path"])} for s in items]
    p.write_text(json.dumps({
        "compiled_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "hot_budget_tokens": hot_budget(),
        "entries": entries}, indent=2), encoding="utf-8")


def _write_triggers(items):
    """Compile the PostToolUse hook's index: small on purpose, it loads per tool call."""
    p = Path.home() / ".claude" / "skillforge" / "triggers.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    # kind-filtered: validate() never forbids `symptoms:` on a kind: skill,
    # but only anti-skills spend the anti-skill budget and get framed as one
    # (detect.py). Fingerprints ride along on each symptom entry so the
    # PostToolUse hook can snapshot at injection time without a second file.
    syms = [{"skill": s["name"], "path": str(s["path"]), "root": str(s["base"]),
             "tokens": toks, "fingerprints": s["fingerprints"]}
            for s in items if s["kind"] == "antiskill" for toks in s["symptoms"]]
    vers = [{"skill": s["name"], "root": str(s["base"]), "tokens": toks}
            for s in items for toks in s["verification"]]
    p.write_text(json.dumps({
        "compiled_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "symptoms": syms, "verifications": vers}, indent=2), encoding="utf-8")


def _cleanup_state():
    d = Path.home() / ".claude" / "skillforge" / "state"
    if not d.is_dir():
        return
    cutoff = time.time() - 7 * 86400
    for f in d.glob("session-*"):   # .json and any crash-orphaned .json.tmp
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
                meta = _meta(text)
                trusted.append({
                    "base": base, "name": name, "text": text, "path": md,
                    "kind": "antiskill" if md.parent.parent.name == "antiskills" else "skill",
                    "scope": "project" if base != Path.home() else "global",
                    "description": meta["description"],
                    "symptoms": meta["symptoms"],
                    "fingerprints": meta["fingerprints"],
                    "verification": meta["verification"]})
            else:
                counts["quarantined"] += 1

    # Hot ranking (slice C2 design 5): bucket, then successful sessions, then
    # recency, then name -- via chained stable sorts, last sort = primary key.
    conf = _confidence()
    for s in trusted:
        s["bucket"] = conf.get(s["name"], UNKNOWN)[0]
    trusted.sort(key=lambda s: s["name"])
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)[2], reverse=True)
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)[1], reverse=True)
    trusted.sort(key=lambda s: BUCKET_RANK.get(s["bucket"], 2))

    budget = hot_budget()
    spent = 0
    for s in trusted:
        # Anti-skills are delivered by symptom trigger (spec 8.1), not by
        # standing description -- so they never spend hot budget.
        if s["kind"] == "antiskill":
            s["tier"] = "warm"
            continue
        # A skill that has never demonstrably worked does not get to sit in
        # every session's standing context (spec 7). Warm still retrieves it
        # on relevance, which is how it earns its way out of `unproven`.
        if s["bucket"] not in HOT_ELIGIBLE:
            s["tier"] = "warm"
            continue
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
    _write_triggers(trusted)
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
