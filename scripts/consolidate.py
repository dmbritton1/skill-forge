"""Merge library skills that describe the same bug into one.

E8 measured the problem: with ten skills installed, BM25 handed
`sf-author-response-text` a skill about a DIFFERENT bug on all three runs,
because six near-duplicates about one lesson were splitting the field. The
task passed anyway, rescued by the symptom path -- but Q1 established that
rescue cannot exist for a symptomless trap, so the ranking failure is real
and its safety net is conditional.

This is deduplication, not generalization. E2's transfer arm was a replicated
null, so the merged skill stays about the one bug rather than climbing to a
shared parent pattern.

Design: docs/superpowers/specs/2026-09-11-consolidate-design.md
"""
import pathlib
import sys

#: Highest first. A merged skill inherits its best member's NAME, because the
#: organic half of the record (successes, failures, last_used) is keyed by
#: name while the Tier A verdicts are keyed by content hash -- so inheriting
#: lands the merge at `working`, one critique pass from `trusted`, instead of
#: `unproven` needing success in two DISTINCT projects.
BUCKET_ORDER = {"trusted": 2, "working": 1, "unproven": 0}


def normalize_command(raw):
    """The bare command, or None.

    save_skill writes the value already quoted, so the parsed string arrives
    as `"python3 tests/x.py"` -- quotes included. Strip symmetric quotes and
    surrounding whitespace so two skills that differ only in quoting still
    cluster, and so the JSON a human reads shows the command rather than its
    punctuation.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s or None


def clusters(metas):
    """(clusters, unclustered) -- group by (command, kind, scope).

    Never crosses kind or scope: a skill and an anti-skill are delivered by
    different paths, and a project skill and a global one live in different
    stores. Groups of one are not clusters.
    """
    groups = {}
    unclustered = []
    for m in metas:
        cmd = normalize_command(m.get("command"))
        if cmd is None:
            unclustered.append({"name": m["name"],
                                "reason": "no verification.command"})
            continue
        groups.setdefault((cmd, m["kind"], m["scope"]), []).append(m)

    out = []
    for (cmd, kind, scope), members in groups.items():
        if len(members) < 2:
            unclustered.append(
                {"name": members[0]["name"],
                 "reason": "only skill with this verification.command"})
            continue
        out.append({"command": cmd, "kind": kind, "scope": scope,
                    "members": members})
    return out, unclustered


def inherit_name(members):
    """The name the merged skill takes: the best member's.

    Three stable sorts rather than one composite key, because two of the
    fields sort descending (bucket, successes, recency) and one ascending
    (name), and `last_used` is a string-or-None that cannot be negated.
    Sorting is stable, so applying the weakest key first and the strongest
    last produces the intended precedence.

    The name tie-break is not cosmetic: without it the inherited name depends
    on index order, and the same library proposes a different merge on two
    consecutive runs.
    """
    ms = sorted(members, key=lambda m: m["name"])
    ms.sort(key=lambda m: (m.get("last_used") or ""), reverse=True)
    ms.sort(key=lambda m: (BUCKET_ORDER.get(m.get("bucket"), -1),
                           m.get("successes") or 0), reverse=True)
    return ms[0]["name"]


def merge_patterns(members, field):
    """Deduplicated union of one list field, in first-seen order."""
    out, seen = [], set()
    for m in members:
        for v in (m.get(field) or []):
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out
