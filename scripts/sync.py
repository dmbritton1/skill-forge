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
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import patterns
import trust
import validate


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
    cmd = fm.get("verification.command")
    prov = fm.get("provenance")
    return {
        "description": desc if isinstance(desc, str) else "",
        "symptoms": _token_lists(fm.get("symptoms")),
        "fingerprints": _token_lists(fm.get("fingerprints")),
        "verification": _token_lists([cmd]),
        # validate.executable() reads provenance.repo to know which repo to
        # reproduce in. Frontmatter is untrusted (spec 11.2): anything but a
        # mapping reads as absent rather than raising into the hook.
        "provenance": prov if isinstance(prov, dict) else {},
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
UNKNOWN = {"bucket": "unproven", "successes": 0, "failures": 0,
           "last_used": ""}
# Catches sessions that died without a clean SessionEnd -- a crash, a kill,
# a closed terminal. A day is long enough that no live session is swept.
SIGNAL_TTL_HOURS = 24


def _write_json(p, obj):
    """Atomic: a reader must never see a half-written index.

    Both compiled indexes are rewritten wholesale on every sync, while the
    hooks read them on every tool call and every prompt. A bare write_text
    truncates first and fills second, so a crash, a kill, or a full disk in
    that gap leaves a truncated file -- and both readers treat unparseable
    as absent, silently disabling injection for the rest of the session.

    Same directory as the destination, or os.replace is not atomic.
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp-%d" % os.getpid())
    try:
        tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(p))
    finally:
        # Nothing globs this directory, so an orphan is only litter -- but it
        # is litter written exactly when the disk is already full, and unlike
        # retrieve.save_state's temps, _cleanup_state never sweeps it.
        try:
            tmp.unlink(missing_ok=True)   # already gone after a good replace
        except OSError:
            pass


def _write_index(items):
    p = Path.home() / ".claude" / "skillforge" / "index.json"
    entries = [{"name": s["name"], "kind": s["kind"], "scope": s["scope"],
                "root": str(s["base"]), "description": s["description"],
                "tier": s["tier"], "bucket": s["bucket"],
                "est_tokens": est_tokens(s["text"]),
                "fingerprints": s["fingerprints"],
                "provenance": s["provenance"],
                "path": str(s["path"])} for s in items]
    _write_json(p, {
        "compiled_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "hot_budget_tokens": hot_budget(),
        "entries": entries})


def _write_triggers(items):
    """Compile the PostToolUse hook's index: small on purpose, it loads per tool call."""
    p = Path.home() / ".claude" / "skillforge" / "triggers.json"
    # kind-filtered: validate() never forbids `symptoms:` on a kind: skill,
    # but only anti-skills spend the anti-skill budget and get framed as one
    # (detect.py). Fingerprints ride along on each symptom entry so the
    # PostToolUse hook can snapshot at injection time without a second file.
    syms = [{"skill": s["name"], "path": str(s["path"]), "root": str(s["base"]),
             "tokens": toks, "fingerprints": s["fingerprints"]}
            for s in items if s["kind"] == "antiskill" for toks in s["symptoms"]]
    vers = [{"skill": s["name"], "root": str(s["base"]), "tokens": toks}
            for s in items for toks in s["verification"]]
    _write_json(p, {
        "compiled_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "symptoms": syms, "verifications": vers})


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


def executable_candidates(trusted, conf, verdicts):
    """Names eligible for an executable run, best evidence first.

    Ordered rather than threshold-gated (slice D2 design 3): gating on
    organic successes would deadlock skills whose whole value is mid-task
    recall -- they never match a prompt, so they never earn a success, so
    they would never validate, so they would never reach the tier that
    surfaces them.

    A skill that can only ever answer `inconclusive` is excluded here rather
    than left to the verdict cache: validate.py deliberately does not record
    an `inconclusive` (ruling R12), so an ineligible candidate would be
    picked again every session and burn the one slot forever. The refusals
    are validate.unattemptable's, not a second copy of them -- an anti-skill,
    a command that is absent or needs a shell, a provenance.repo that is not
    a local git repo.
    """
    out = []
    for s in trusted:
        v = verdicts.get(s["name"], {})
        if v.get("critique") != "pass" or v.get("executable"):
            continue
        # `"text" in s`: every entry sync() builds carries the skill text, so
        # the guard runs for real. The ordering unit tests pass bare
        # {"name", "saved_ts"} entries, which carry no text to decide on.
        if "text" in s and validate.unattemptable(s["text"], s):
            continue
        out.append(s)
    out.sort(key=lambda s: s.get("saved_ts", 0), reverse=True)
    out.sort(key=lambda s: conf.get(s["name"], UNKNOWN).get("successes", 0),
             reverse=True)
    return [s["name"] for s in out]


def _spawn_validation(name, mode):
    """Detached, never waited on; its own function so tests replace it.

    Plain os.environ, NOT dict(os.environ, SKILLFORGE_DRAFTING="1") -- same
    reasoning as save_skill._spawn_validation: validate.py's main() returns 0
    as its first statement when that flag is set, so forcing it here would
    make every scheduled run a silent no-op. Inheriting os.environ unchanged
    still lets the flag through when it is genuinely set (sync running inside
    a drafting session), which is the one case where going inert is correct.
    """
    argv = [sys.executable,
            str(Path(__file__).resolve().parent / "validate.py"), mode,
            "--skill", name]
    subprocess.Popen(argv, cwd=str(Path(__file__).resolve().parent.parent),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True,
                     env=os.environ)


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
                    "verification": meta["verification"],
                    "provenance": meta["provenance"],
                    # "most recently saved": the store file's own mtime. Every
                    # save path writes it, and it needs no ledger row.
                    "saved_ts": md.stat().st_mtime})
            else:
                counts["quarantined"] += 1

    # Hot ranking (slice C2 design 5): bucket, then successful sessions, then
    # recency, then name -- via chained stable sorts, last sort = primary key.
    #
    # Tier A is enforced here, not in the view: verdicts are keyed by content
    # hash, and only this loop knows each skill's current text.
    hashes = {s["name"]: trust.content_hash(s["text"]) for s in trusted}
    conf = ledger.confidence(hashes=hashes)
    for s in trusted:
        s["bucket"] = conf.get(s["name"], UNKNOWN)["bucket"]
    trusted.sort(key=lambda s: s["name"])
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)["last_used"], reverse=True)
    trusted.sort(key=lambda s: conf.get(s["name"], UNKNOWN)["successes"], reverse=True)
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
    # One per session: executable mode is an agentic run, not a single turn.
    try:
        names = executable_candidates(
            trusted, conf, ledger.validations_for(hashes))
        if names:
            _spawn_validation(names[0], "executable")
    except Exception as err:
        print("skillforge: executable schedule failed: %s" % err, file=sys.stderr)
    _cleanup_state()
    try:
        ledger.prune_signals(older_than_hours=SIGNAL_TTL_HOURS)
    except Exception:
        pass    # a stale breadcrumb is harmless; a failed sync is not
    return counts


def main(argv=None):
    # A drafter (slice D1) is a Claude Code process spawned by these very
    # hooks. `claude -p --safe-mode` already disables hooks in the child;
    # this is the guard that survives a change in what --safe-mode covers.
    if os.environ.get("SKILLFORGE_DRAFTING"):
        return 0
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
