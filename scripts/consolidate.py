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
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import library
import retrieve
import save_skill

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


def load_metas():
    """One meta per indexed skill, index metadata joined to its frontmatter.

    `library.rows()` has the live bucket and confidence but not the
    verification command or the skill's root: `sync._write_index` stores only
    a tokenized form of the command and `rows()` doesn't pass the index's
    `root` field through. So the command, fingerprints and symptoms are read
    back out of each skill's own file, via the parser save_skill already owns,
    and root comes from a name->root map built off `retrieve.load_index()` --
    the same index `rows()` itself reads.

    A skill whose file has gone missing, or whose file is not valid UTF-8
    text, is skipped rather than fatal -- the index can outlive a
    hand-deleted store, and one bad row must not stop the user seeing the
    rest of their library.
    """
    idx = retrieve.load_index() or {}
    roots = {e.get("name"): e.get("root") for e in idx.get("entries", [])}
    out = []
    for r in library.rows():
        try:
            text = pathlib.Path(r["path"]).read_text(encoding="utf-8")
        except (OSError, ValueError):    # ValueError: UnicodeDecodeError
            continue
        fm, _ = save_skill.parse_frontmatter(text)
        if not fm:
            continue
        fps = fm.get("fingerprints")
        syms = fm.get("symptoms")
        out.append({"name": r["name"], "kind": r["kind"], "scope": r["scope"],
                    "bucket": r["bucket"], "successes": r["successes"],
                    "last_used": r["last_used"], "path": r["path"],
                    "root": roots.get(r["name"]),
                    "command": fm.get("verification.command"),
                    "fingerprints": fps if isinstance(fps, list) else [],
                    "symptoms": syms if isinstance(syms, list) else []})
    return out


def proposal(metas, name=None):
    """{"clusters": [...], "unclustered": [...]} -- what a merge would do.

    Members carry name, bucket, successes and path and nothing else. This dict
    is printed for a model to read, and a skill's BODY is untrusted data that
    must not ride along in it.
    """
    cls, unclustered = clusters(metas)
    out = []
    for c in cls:
        if name is not None and not any(m["name"] == name for m in c["members"]):
            continue
        out.append({
            "command": c["command"], "kind": c["kind"], "scope": c["scope"],
            # Members share a scope, so they share a root -- take the first's.
            "root": c["members"][0].get("root"),
            "keep": inherit_name(c["members"]),
            "members": [{"name": m["name"], "bucket": m["bucket"],
                         "successes": m["successes"], "path": m["path"]}
                        for m in c["members"]],
            "fingerprints": merge_patterns(c["members"], "fingerprints"),
            "symptoms": merge_patterns(c["members"], "symptoms"),
        })
    if name is not None:
        unclustered = [u for u in unclustered if u["name"] == name]
    return {"clusters": out, "unclustered": unclustered}


def cmd_propose(name=None):
    print(json.dumps(proposal(load_metas(), name=name), indent=2))
    return 0


def cmd_retire(keep, names):
    """Archive every name except `keep`, reversibly.

    Archiving, never deleting: `library.py restore` is the undo, and it
    already exists. `keep` is filtered out rather than assumed absent --
    `cmd_archive` moves a store directory by NAME, and the merged skill lives
    at the kept name, so archiving it would move the merge itself.

    `keep` is a positional argv token written by a model following
    commands/consolidate.md, not something this function derives itself --
    so it is verified against the live library before anything is archived.
    If `keep` is not currently a real library skill (stale proposal, typo,
    wrong cluster), archiving the rest around it would destroy the merge
    output and leave nothing live, so this fails closed and archives nothing.

    A failure does not stop the loop. Stopping would leave the library in a
    state nobody chose: merged skill saved, some members retired, the rest
    silently not.
    """
    if not any(r["name"] == keep for r in library.rows()):
        print("consolidate: keep %r is not in the library; archiving nothing"
              % keep, file=sys.stderr)
        return 1
    rc = 0
    for n in names:
        if n == keep:
            continue
        if library.cmd_archive(n) != 0:
            print("consolidate: could not archive %r" % n, file=sys.stderr)
            rc = 1
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("propose")
    pr.add_argument("--name", default=None,
                    help="only the cluster containing this skill")
    rt = sub.add_parser("retire")
    rt.add_argument("keep")
    rt.add_argument("names", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "propose":
        return cmd_propose(args.name)
    if args.cmd == "retire":
        return cmd_retire(args.keep, args.names)
    return 1


if __name__ == "__main__":
    sys.exit(main())
