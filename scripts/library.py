#!/usr/bin/env python3
"""Human view of the knowledge store (slice D1 design 8).

`list`   -- every trusted skill with the confidence slice C2 earned it.
`show`   -- one skill's Tier A verdicts and the findings behind them.
`delete` -- remove one skill from the store, the native tier, and the trust
            registry, then rebuild the derived indexes.
`archive`/`restore`/`archived` -- the same retirement, reversibly.

Deletion removes the skill, not its history: `events` rows survive, so a
name deleted and later re-saved does not silently inherit an old bucket.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import retrieve
import sync
import trust
# The blocking rule itself, not a copy of it: two implementations of
# "does this finding gate" would drift, and the display would start
# lying about why a skill is held back.
import validate

UNKNOWN = {"bucket": "unproven", "successes": 0, "failures": 0,
           "last_used": ""}
COLUMNS = ("name", "kind", "scope", "tier", "bucket", "critique", "executable",
           "successes", "failures", "last_used", "path")


def rows():
    """One dict per indexed skill: index metadata, confidence, Tier A verdicts."""
    entries = (retrieve.load_index() or {}).get("entries", [])
    hashes = {}
    for e in entries:
        try:
            hashes[e["name"]] = trust.content_hash(
                Path(e["path"]).read_text(encoding="utf-8"))
        except (OSError, KeyError):
            continue
    conf = ledger.confidence(hashes=hashes)
    verdicts = ledger.validations_for(hashes)
    out = []
    for e in entries:
        name = e.get("name", "")
        c = conf.get(name, UNKNOWN)
        v = verdicts.get(name, {})
        out.append({"name": name, "kind": e.get("kind", ""),
                    "scope": e.get("scope", ""), "tier": e.get("tier", ""),
                    "bucket": c["bucket"],
                    "critique": v.get("critique", ""),
                    "executable": v.get("executable", ""),
                    "successes": c["successes"], "failures": c["failures"],
                    "last_used": c["last_used"], "path": e.get("path", "")})
    return sorted(out, key=lambda r: r["name"])


def cmd_list():
    data = rows()
    if not data:
        print("library empty; nothing saved yet")
        return 0
    print("\t".join(COLUMNS))
    for r in data:
        print("\t".join(str(r[c]) for c in COLUMNS))
    return 0


def _print_findings(mode, verdict, detail):
    """One mode's verdict and the per-criterion findings behind it."""
    print("\n%s: %s" % (mode, verdict))
    try:
        findings = json.loads(detail) if detail else None
    except ValueError:
        findings = None
    if not isinstance(findings, list):
        # Executable mode records no findings, and a verdict written by an
        # older build may have none either. Say so rather than implying the
        # reasons were empty.
        print("  (no per-criterion findings recorded)")
        return
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("ok") is True:
            print("  [ok  ] %s" % f.get("criterion", "?"))
        else:
            # Which objections actually held the skill back, and which were
            # only reported. Without this the author cannot tell a blocking
            # defect from a note, and the two look identical in the text.
            grade = "%s/%s" % (f.get("basis", "textual"),
                               f.get("severity", "blocking"))
            gates = ("blocks" if validate.blocks(f) else "reported only")
            print("  [FAIL] %s  (%s -- %s)"
                  % (f.get("criterion", "?"), grade, gates))
        ev = (f.get("evidence") or "").strip()
        if ev:
            print("        quoted: %s" % ev.replace("\n", " ")[:200])
        note = (f.get("note") or "").strip()
        if note:
            print("        %s" % note[:400])


def cmd_show(name):
    """Why a skill has the verdict it has -- the half `list` cannot fit.

    `list` answers pass/fail in a column. The reasons live in the ledger's
    `detail` and reached nobody, so a critique `fail` read as an unexplained
    permanent cap: it holds a skill at `working` until its text changes, and
    the author had no way to learn what to change.
    """
    entry = next((e for e in (retrieve.load_index() or {}).get("entries", [])
                  if e.get("name") == name), None)
    if entry is None:
        print("no such skill in the index: %r" % name)
        return 1
    try:
        text = Path(entry.get("path", "")).read_text(encoding="utf-8")
    except OSError as err:
        print("cannot read %s: %s" % (entry.get("path", ""), err))
        return 1

    print("%s (%s, %s) tier=%s" % (name, entry.get("kind", ""),
                                   entry.get("scope", ""), entry.get("tier", "")))
    found = ledger.findings_for(name, trust.content_hash(text))
    for mode in ("critique", "executable"):
        if mode in found:
            _print_findings(mode, *found[mode])
        else:
            # Deliberately not silent: a missing verdict and a passing one
            # are opposite facts, and blank space reads as the second.
            print("\n%s: no %s verdict for the current text" % (mode, mode))
    u = ledger.usage_for(name)
    if not u["sessions"]:
        # Same standard as the missing-verdict branch above: silence reads
        # as a measured zero, and "never measured" is the opposite fact.
        print("\nusage: no usage data yet")
        return 0
    print("\nusage: %d session(s), injected in %d of them" % (u["sessions"], u["injections"]))
    for label, value in (("marker + corroboration", u["both"]),
                         ("corroboration only (compliance miss)", u["corroborated_only"]),
                         ("marker only (no independent signal)", u["marker_only"]),
                         ("injected, no usage signal", u["neither"])):
        print("  %-38s%d" % (label + ":", value))
    return 0


ARCHIVE = "archive"


def _resolve_store(name):
    """(store_dir, root, kind) for an indexed skill, or None after printing why.

    Shared by delete and archive so the containment check below exists once.
    Two copies of a guard that stands in front of `shutil.rmtree` and
    `os.replace` is exactly the kind of thing that drifts.
    """
    entry = next((e for e in (retrieve.load_index() or {}).get("entries", [])
                  if e.get("name") == name), None)
    if entry is None:
        print("no such skill in the index: %r" % name)
        return None
    # Resolved from the index by name, never from a path argument -- and then
    # checked against the entry's own root anyway. `store` and `root` both
    # come from the same index entry, so this does not defend against a
    # tampered index (whoever controls one controls both); it catches
    # internal inconsistency -- an entry whose path has drifted outside its
    # own declared root -- before anything destructive runs.
    store = Path(entry.get("path", "")).parent
    root = Path(entry.get("root", ""))
    if (root / ".claude" / "skillforge") not in store.parents:
        print("refusing: %s is outside the knowledge store" % store)
        return None
    # `skills` or `antiskills` -- the parent of the skill's own directory.
    return store, root, store.parent.name


def _resync(root):
    """Rebuild derived state from the skill's OWN base.

    sync() only rebuilds index.json for the bases it is given, so syncing any
    other base would strip every other skill belonging to this one out of the
    shared index. It also owns native-dir eviction, so with the trust entry
    already popped this call evicts the native copy too.
    """
    sync.sync(project_root=str(root) if root != Path.home() else None)


def cmd_archive(name):
    """Retire a skill reversibly: move the store dir aside, drop its trust."""
    resolved = _resolve_store(name)
    if resolved is None:
        return 1
    store, root, kind = resolved
    stamp = ledger.now_utc().strftime("%Y%m%dT%H%M%SZ")
    dest_parent = root / ".claude" / "skillforge" / ARCHIVE / kind
    dest_parent.mkdir(parents=True, exist_ok=True)
    # Always stamped, never conditionally: archive -> re-save -> archive again
    # is ordinary, and an unstamped name would let the second archive
    # overwrite the first -- silently losing the thing this command exists to
    # keep. A collision inside one second keeps counting up.
    dest = dest_parent / ("%s@%s" % (name, stamp))
    n = 1
    while dest.exists():
        dest = dest_parent / ("%s@%s-%d" % (name, stamp, n))
        n += 1
    os.replace(str(store), str(dest))    # same filesystem, so atomic
    reg = trust.load()
    reg.pop(name, None)
    trust.save(reg)
    ledger.log_event(ARCHIVE, name, outcome="archived")
    _resync(root)
    print("archived: %s -> %s" % (name, dest))
    return 0


def _archive_roots():
    """Every (base, kind_dir) archive directory that exists."""
    for base in {Path.home()} | {Path(e.get("root", ""))
                                 for e in (retrieve.load_index() or {}).get("entries", [])
                                 if e.get("root")}:
        for kind in ("skills", "antiskills"):
            d = base / ".claude" / "skillforge" / ARCHIVE / kind
            if d.is_dir():
                yield base, kind, d


def _archived_entries(name=None):
    """[(base, kind, dir, name, stamp)] for archived skills, oldest first."""
    out = []
    for base, kind, d in _archive_roots():
        for p in sorted(d.iterdir()):
            if not p.is_dir() or "@" not in p.name:
                continue
            nm, stamp = p.name.split("@", 1)
            if name is None or nm == name:
                out.append((base, kind, p, nm, stamp))
    return sorted(out, key=lambda r: r[4])


def cmd_archived():
    rows = _archived_entries()
    if not rows:
        print("nothing archived")
        return 0
    print("\t".join(("name", "kind", "scope", "archived")))
    for base, kind, _, nm, stamp in rows:
        print("\t".join((nm, "antiskill" if kind == "antiskills" else "skill",
                          "global" if base == Path.home() else "project", stamp)))
    return 0


def cmd_restore(name, at=None):
    """Move an archived skill back into the store. It returns QUARANTINED.

    Trust is deliberately not restored. An archived directory is plain text
    the user can edit, so re-trusting on the way back in would make archive ->
    edit -> restore a way to land unreviewed content as trusted -- exactly
    what the content hash exists to prevent. /skillforge:review approves it.
    """
    rows = [r for r in _archived_entries(name) if at is None or r[4] == at]
    if not rows:
        print("nothing archived under that name: %r" % name)
        return 1
    if len(rows) > 1:
        print("%d archived copies of %r; re-run with --at <stamp>:" % (len(rows), name))
        for _, _, _, _, stamp in rows:
            print("  %s" % stamp)
        return 1
    base, kind, src, nm, stamp = rows[0]
    dest = base / ".claude" / "skillforge" / kind / nm
    if dest.exists():
        print("refusing: a live %s named %r already exists at %s"
              % (kind[:-1], nm, dest))
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(src), str(dest))
    ledger.log_event("restore", nm, outcome="restored")
    _resync(base)
    print("restored: %s -> %s" % (nm, dest))
    print("it is QUARANTINED until approved -- run /skillforge:review")
    return 0


def cmd_delete(name):
    """Destructive. `archive` is the reversible one."""
    resolved = _resolve_store(name)
    if resolved is None:
        return 1
    store, root, _ = resolved

    shutil.rmtree(str(store), ignore_errors=True)
    reg = trust.load()
    reg.pop(name, None)
    trust.save(reg)
    ledger.log_event("delete", name, outcome="deleted")
    # (delete takes no --project-root -- passing one was the bug; _resync
    # derives the right base from the skill's own index entry.)
    _resync(root)
    print("deleted: %s" % name)
    return 0


def cmd_decisions(actor=None, verdict=None, skill=None, session=None, limit=None):
    """What the reviewer and the write path decided, newest first.

    `list` shows what is IN the library; this shows what was decided on the
    way in, including the proposals that never made it -- a rejected save
    used to print to a detached drafter's stderr and leave no trace.
    """
    rows = ledger.decisions(actor=actor, verdict=verdict, subject=skill,
                            session=session, limit=limit)
    if not rows:
        print("no decisions recorded")
        return 0
    print("\t".join(("ts", "actor", "verdict", "subject", "reason")))
    for r in rows:
        print("\t".join((r["ts"], r["actor"], r["verdict"], r["subject"],
                          r["reason"] or "")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show")
    s.add_argument("name")
    d = sub.add_parser("delete")
    d.add_argument("name")
    ar = sub.add_parser("archive")
    ar.add_argument("name")
    rs = sub.add_parser("restore")
    rs.add_argument("name")
    rs.add_argument("--at", help="stamp, when a name was archived more than once")
    sub.add_parser("archived")
    dec = sub.add_parser("decisions")
    dec.add_argument("--actor", choices=("human", "system"))
    dec.add_argument("--verdict")
    dec.add_argument("--skill", help="filter to one subject name")
    dec.add_argument("--session")
    dec.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "show":
        return cmd_show(args.name)
    if args.cmd == "archive":
        return cmd_archive(args.name)
    if args.cmd == "restore":
        return cmd_restore(args.name, at=args.at)
    if args.cmd == "archived":
        return cmd_archived()
    if args.cmd == "decisions":
        return cmd_decisions(actor=args.actor, verdict=args.verdict,
                             skill=args.skill, session=args.session,
                             limit=args.limit)
    return cmd_delete(args.name)


if __name__ == "__main__":
    sys.exit(main())
