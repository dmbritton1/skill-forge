#!/usr/bin/env python3
"""Human view of the knowledge store (slice D1 design 8).

`list`   -- every trusted skill with the confidence slice C2 earned it.
`delete` -- remove one skill from the store, the native tier, and the trust
            registry, then rebuild the derived indexes.

Deletion removes the skill, not its history: `events` rows survive, so a
name deleted and later re-saved does not silently inherit an old bucket.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import retrieve
import sync
import trust

UNKNOWN = {"organic_bucket": "unproven", "successes": 0, "failures": 0,
           "last_used": ""}
COLUMNS = ("name", "kind", "scope", "tier", "bucket", "successes", "failures",
           "last_used", "path")


def rows():
    """One dict per indexed skill, index metadata joined to ledger confidence."""
    # TASK 9 REPLACES THIS: reads the organic half only, so the library shows
    # the organic bucket, not the Tier A one. Task 9 passes hashes and
    # restores ["bucket"].
    conf = ledger.confidence()
    out = []
    for e in (retrieve.load_index() or {}).get("entries", []):
        c = conf.get(e.get("name"), UNKNOWN)
        out.append({"name": e.get("name", ""), "kind": e.get("kind", ""),
                    "scope": e.get("scope", ""), "tier": e.get("tier", ""),
                    "bucket": c["organic_bucket"], "successes": c["successes"],
                    "failures": c["failures"], "last_used": c["last_used"],
                    "path": e.get("path", "")})
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
    d = sub.add_parser("delete")
    d.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        return cmd_list()
    return cmd_delete(args.name)


if __name__ == "__main__":
    sys.exit(main())
