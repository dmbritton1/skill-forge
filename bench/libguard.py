#!/usr/bin/env python3
"""Keep Q1's 60 sessions out of the operator's real SkillForge library.

Three separate leaks, none of which the bench's existing SKILLFORGE_LEDGER
isolation covers:

1. The global STORE. save_skill.store_dir resolves --scope global to
   Path.home(), and the distillation contract has the MODEL choose the scope
   ("mentions repo-specific paths/conventions -> project; otherwise global").
   A phase-1 session that judges its trap general writes into the real store.
2. trust.json. trust.py resolves it to Path.home() unconditionally and
   save_skill records on EVERY save, project-scoped ones included.
3. index.json. User-global and last-writer-wins.

Nothing here sandboxes HOME: the `claude` CLI reads it for credentials, so
swapping it risks breaking authentication mid-batch. Containment is therefore
reactive -- snapshot, diff after each session, revert, assert at close -- and
a batch whose drift cannot be reverted is invalidated rather than repaired.
"""
import json
from pathlib import Path

KINDS = ("skills", "antiskills")


def _root():
    # Read per call, never cached at import: the tests move HOME.
    return Path.home() / ".claude" / "skillforge"


def _read_json(name, default):
    """Parsed contents of one state file, or `default`.

    Guards the SHAPE as well as the read. A missing or unparseable file is an
    expected state and degrades to empty, which drift() then reports as a
    difference -- the safe direction. A file that parses to the WRONG shape
    would otherwise reach .get()/sorted() and raise, and an uncaught exception
    in the containment assertion aborts checking for the whole batch instead
    of flagging one anomaly.
    """
    try:
        value = json.loads((_root() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _store_names():
    out = []
    for kind in KINDS:
        d = _root() / kind
        if not d.is_dir():
            continue
        out += ["%s/%s" % (kind, p.name) for p in d.iterdir() if p.is_dir()]
    return sorted(out)


def _index_names(scope):
    entries = _read_json("index.json", {}).get("entries", [])
    return sorted(e.get("name", "") for e in entries if e.get("scope") == scope)


def snapshot():
    """The four pieces of user-global state a batch can disturb."""
    return {"stores": _store_names(),
            "global_index": _index_names("global"),
            "project_index": _index_names("project"),
            "trust": sorted(_read_json("trust.json", {}))}


def new_global_skills(before):
    """Bare names added to the global store since `before`."""
    added = set(_store_names()) - set(before["stores"])
    return sorted(n.split("/", 1)[1] for n in added)


def new_trust_keys(before):
    """Trust registry keys added since `before`.

    trust.py resolves trust.json to Path.home() UNCONDITIONALLY and save_skill
    records on every save, project-scoped ones included -- so a batch that
    never leaks a single global-scope skill still leaves one key per save in
    the operator's real registry. drift() compares those key sets, so without
    this the closing assertion fires on a clean batch: either a good batch is
    discarded or the operator learns to ignore the assertion.

    Diffed against the snapshot rather than pruned by name: a distilled draft
    that happens to pick an existing skill's name must not delete the
    operator's genuine entry.
    """
    return sorted(set(snapshot()["trust"]) - set(before["trust"]))


def prune_trust(names):
    """Drop `names` from trust.json. Returns keys removed."""
    data = _read_json("trust.json", {})
    removed = 0
    for n in names:
        if data.pop(n, None) is not None:
            removed += 1
    if removed:
        (_root() / "trust.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return removed


def drift(before):
    """Human-readable mismatches against `before`; empty list means clean.

    Compares SETS of names, never index.json's bytes: sync rewrites the file
    wholesale on every run, so `compiled_ts` and entry order change constantly
    and a byte comparison would report drift on a clean batch.
    """
    now = snapshot()
    out = []
    for key, label in (("stores", "global store"),
                       ("global_index", "global index entries"),
                       ("project_index", "project index entries"),
                       ("trust", "trust.json keys")):
        gone = sorted(set(before[key]) - set(now[key]))
        extra = sorted(set(now[key]) - set(before[key]))
        if gone:
            out.append("%s missing: %s" % (label, ", ".join(gone)))
        if extra:
            out.append("%s unexpected: %s" % (label, ", ".join(extra)))
    return out
