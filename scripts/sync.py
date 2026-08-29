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
    # `tier` rides along so detect.py can tell a hot skill from a warm one
    # without opening index.json on every tool call. It decides whether a
    # verification match is credited: warm skills must have been injected
    # this session, hot ones are exempt because the harness injects them
    # from the native directory and we never see it happen.
    vers = [{"skill": s["name"], "root": str(s["base"]), "tier": s["tier"],
             "tokens": toks}
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


def _ordered(cands, conf, attempts, mode):
    """Best evidence first, then most recently saved, attempted ones last.

    The two evidence sorts are slice D2 design 3. The third is the forward
    progress guarantee: an attempt row means "we ran this mode against this
    exact text and got no verdict", and some of those refusals are permanent
    for the text (the vacuity gate is deterministic for a text and a repo
    HEAD). Deprioritized rather than excluded -- exclusion would drop a
    genuinely transient failure forever, while sorting last still guarantees
    every other candidate gets its turn first.
    """
    cands.sort(key=lambda s: s.get("saved_ts", 0.0), reverse=True)
    cands.sort(key=lambda s: conf.get(s["name"], UNKNOWN).get("successes", 0),
               reverse=True)
    cands.sort(key=lambda s: mode in attempts.get(s["name"], ()))
    return [s["name"] for s in cands]


def critique_candidates(trusted, conf, verdicts, attempts=None):
    """Trusted skills with no critique verdict for their current hash.

    save_skill's spawn-on-save used to be the ONLY critique call site, which
    left two holes. A skill obtained by `git pull` and approved through
    /skillforge:review was never critiqued at all -- and executable_candidates
    requires a critique pass, so it was capped at `working` permanently,
    against design decision 1 ("quarantined and pulled skills get critique").
    And a lost spawn -- a killed process, a sleeping machine, an unparseable
    reply -- had no retry path anywhere, so one transient model failure capped
    a skill forever.

    Re-offering here is idempotent and nearly free: validate.main returns
    early on an existing verdict for the hash, and the per-(skill, mode) flock
    makes a concurrent run a no-op, so a repeat spawn costs one Popen that
    exits immediately. Rate-limited to one per session by main(), the same
    discipline as executable -- hence the ordering, which is executable's.

    No unattemptable() filter: those are executable's preconditions (a
    worktree, a runnable command, a local repo). Critique reads text, so every
    trusted skill can always answer it.
    """
    out = [s for s in trusted if not verdicts.get(s["name"], {}).get("critique")]
    return _ordered(out, conf, attempts or {}, "critique")


def executable_candidates(trusted, conf, verdicts, attempts=None):
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
        if validate.unattemptable(s["text"], s):
            continue
        out.append(s)
    # 0.0, not 0 (in _ordered): real entries carry a float saved_ts (sync()
    # sets it from st_mtime), and int-vs-float compares fine either way --
    # that was never the hazard. The real one: some callers' entries carry
    # saved_ts as an ISO date string ("2026-01-01"), filtered out of `out`
    # before reaching that sort today. If a future filter change ever let one
    # through, comparing a str against a numeric default would raise straight
    # into the caller's except -- which contains it, but "contained" means
    # scheduling silently stops.
    return _ordered(out, conf, attempts or {}, "executable")


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
    counts = {"materialized": 0, "evicted": 0, "quarantined": 0,
              "executable_candidates": [], "critique_candidates": []}
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
    # Selected here because only this scope has each skill's text and hash --
    # but NOT spawned here. sync() also runs after every save (save_skill) and
    # every delete (library), which would make "one run per session" three
    # runs in a session with two saves; main() is the SessionStart entry point
    # and the one that carries the drafting guard, so it does the spawning.
    try:
        verdicts = ledger.validations_for(hashes)
        attempts = ledger.attempts_for(hashes)
        counts["executable_candidates"] = executable_candidates(
            trusted, conf, verdicts, attempts)
        counts["critique_candidates"] = critique_candidates(
            trusted, conf, verdicts, attempts)
    except Exception as err:
        print("skillforge: candidate select failed: %s" % err, file=sys.stderr)
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
        # One of each per session, and this is what makes that true:
        # SessionStart runs main() once, while sync() itself runs again after
        # every save and delete. Detached, never waited on -- an executable run
        # is an agentic run, not a single turn.
        #
        # Critique is scheduled here as well as spawned by save_skill, because
        # save is not the only way a skill arrives: `git pull` plus
        # /skillforge:review produces a trusted skill that was never saved
        # locally and so was never critiqued, and executable mode needs a
        # critique pass first -- so it was capped at `working` permanently. The
        # same re-offer is the only retry path for a spawn that was lost.
        for key, mode in (("executable_candidates", "executable"),
                          ("critique_candidates", "critique")):
            try:
                names = counts[key]
                if names:
                    _spawn_validation(names[0], mode)
            except Exception as err:
                print("skillforge: %s schedule failed: %s" % (mode, err),
                      file=sys.stderr)
    except Exception as e:
        print("skillforge: sync failed: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
