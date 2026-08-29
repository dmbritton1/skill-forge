#!/usr/bin/env python3
"""Human view of the knowledge store (slice D1 design 8).

`list`   -- every trusted skill with the confidence slice C2 earned it.
`show`   -- one skill's Tier A verdicts and the findings behind them.
`delete` -- remove one skill from the store, the native tier, and the trust
            registry, then rebuild the derived indexes.

Deletion removes the skill, not its history: `events` rows survive, so a
name deleted and later re-saved does not silently inherit an old bucket.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import retrieve
import sync
import trust

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
        mark = "ok  " if f.get("ok") is True else "FAIL"
        print("  [%s] %s" % (mark, f.get("criterion", "?")))
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
    return 0


def cmd_delete(name):
    entry = next((e for e in (retrieve.load_index() or {}).get("entries", [])
                  if e.get("name") == name), None)
    if entry is None:
        print("no such skill in the index: %r" % name)
        return 1
    # Resolved from the index by name, never from a path argument -- and then
    # checked against the entry's own root anyway. `store` and `root` both
    # come from the same index entry, so this does not defend against a
    # tampered index (whoever controls one controls both); it catches
    # internal inconsistency -- an entry whose path has drifted outside its
    # own declared root -- before shutil.rmtree runs.
    store = Path(entry.get("path", "")).parent
    root = Path(entry.get("root", ""))
    if (root / ".claude" / "skillforge") not in store.parents:
        print("refusing: %s is outside the knowledge store" % store)
        return 1

    shutil.rmtree(str(store), ignore_errors=True)
    reg = trust.load()
    reg.pop(name, None)
    trust.save(reg)
    ledger.log_event("delete", name, outcome="deleted")
    # Re-sync from the skill's OWN base, resolved from its index entry above:
    # sync() only rebuilds index.json for the bases it's given, so syncing
    # any other base would strip every other skill belonging to this one
    # out of the shared index until someone re-syncs from the right root.
    # (This is why delete takes no --project-root -- passing one was the bug.)
    # sync() also owns native-dir eviction (its docstring: "the ONLY writer
    # of native skill dirs") -- with the trust entry already popped above,
    # this same call evicts the skill's native copy too, so no separate
    # rmtree is needed here.
    sync.sync(project_root=str(root) if root != Path.home() else None)
    print("deleted: %s" % name)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show")
    s.add_argument("name")
    d = sub.add_parser("delete")
    d.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "show":
        return cmd_show(args.name)
    return cmd_delete(args.name)


if __name__ == "__main__":
    sys.exit(main())
