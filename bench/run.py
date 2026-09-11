#!/usr/bin/env python3
"""Paired A/B benchmark: does an injected SkillForge skill change task outcomes?

One task = a real bug-fix commit from a public repo. The working tree is the
commit's PARENT (buggy source) plus the commit's OWN tests, so the tests the
fix introduced start red -- the model has to turn them green. Scoring is the
repo's own test result, never turns-to-completion (spec 7: high-variance and
gameable).

The two arms differ in exactly one thing: whether the skill is present in the
clone's project-scoped store. Same prompt, same model, same tree, same plugin.
The global store stays empty, so nothing leaks into the control arm.

Usage:
    python3 bench/run.py --check          # verify the config before spending
    python3 bench/run.py --task arrow-968-tzinfo-kwarg --runs 1
    python3 bench/run.py --all --runs 3

Paths in tasks.json are written `{root}` and expanded to the repository this
file lives in. They were absolute, under a checkout that has since moved and
a worktree that has since been deleted -- which left every task broken with
no signal, because a failed clone or stub command reads as a failed task.
--check exists so that is visible in a second rather than after a run.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libguard

ROOT = Path(__file__).resolve().parent
# The repository this harness lives in. tasks.json writes `{root}` rather than
# an absolute path: every path in it used to be hardcoded under a checkout
# that has since moved AND a worktree that has since been deleted, which left
# the whole harness dead without saying so -- `git clone` of a missing path is
# just a failed task.
REPO_ROOT = ROOT.parent
# Outside the repo on purpose: a clone under bench/work/ sits inside a
# project whose skill store retrieve.in_scope() accepts (cwd.startswith
# (root)), so the real library is retrievable in every bench session --
# control and treatment alike. Keeping the clones out of the tree is the
# whole isolation; it also stops work/ accumulating inside the checkout.
WORK = Path(os.environ.get("SKILLFORGE_BENCH_WORK", "/tmp/skillforge-bench"))
RESULTS = ROOT / "results.jsonl"
SESSION_TIMEOUT_S = 900
# Pinned, not the account default: a cross-date comparison is only sound
# if the model is known, and the 2026-08-11 pilot did not record one.
DEFAULT_MODEL = "claude-opus-5"
MODEL = DEFAULT_MODEL
# E5 arm H: deliver the treatment skill hot instead of warm. Off = the env var
# is exported empty, which sync._force_hot() reads as "no override".
FORCE_HOT = False
# Q1: absolute path to a distilled draft, replacing the task's hand-authored
# skill. Off = None. The clone path segment is DERIVED from this (arm_segment)
# rather than passed, because a forgotten segment is the exact bug that let
# E5's two arms overwrite each other.
SKILL_FROM = None
# E6: an ADDITIONAL skill installed beside the task's own, to ask whether an
# irrelevant one riding along dilutes a relevant one. Off = None.
PLUS_SKILL = None


def expand(value):
    """Substitute `{root}` in any string, recursively through the config."""
    if isinstance(value, str):
        return value.replace("{root}", str(REPO_ROOT))
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def check_config(cfg):
    """Every path the config names, and whether it is actually there.

    Returns a list of complaints. A stale path is otherwise invisible: the
    clone or the stub command just fails inside a task and reads as a task
    failure rather than a broken harness.
    """
    bad = []
    if not (Path(cfg["plugin_dir"]) / "scripts").is_dir():
        bad.append("plugin_dir has no scripts/: %s" % cfg["plugin_dir"])
    for task in cfg["tasks"]:
        if not (Path(task["repo"]) / ".git").exists():
            bad.append("%s: repo is not a git checkout: %s" % (task["id"], task["repo"]))
        for key in ("stub_cmd", "hidden_patch_cmd"):
            cmd = task.get(key)
            if not cmd:
                continue
            for tok in cmd.split():
                if tok.endswith(".py") and not Path(tok).exists():
                    bad.append("%s: %s names a missing script: %s"
                               % (task["id"], key, tok))
    return bad


def sh(cmd, cwd=None, timeout=600, env=None):
    return subprocess.run(cmd, shell=True, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=timeout,
                          env=env or os.environ.copy())


def prepare(task, dest):
    """Build the starting tree.

    repair mode  -- clone at the fix's parent and overlay the fix's tests, so
                    the tests the fix introduced start red (FAIL_TO_PASS).
    author mode  -- clone at the fix's parent, run stub_cmd to blank out the
                    implementation, and DO NOT place the tests: the model
                    authors against a spec and never sees what will grade it.
                    This is the only mode that measures knowledge rather than
                    the ability to read a failing assertion.
    """
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache = WORK / ("cache-" + task["id"])
    if not cache.exists():
        r = sh("git clone -q %s %s" % (task["repo"], cache), timeout=900)
        if r.returncode:
            raise RuntimeError("clone failed: " + r.stderr[:400])
    sh("git clone -q %s %s" % (cache, dest), timeout=900)
    sh("git checkout -q %s~1" % task["fix_commit"], cwd=dest)
    if task.get("mode", "repair") == "repair":
        sh("git checkout -q %s -- %s" % (task["fix_commit"], task["test_path"]), cwd=dest)
    else:
        r = sh(task["stub_cmd"], cwd=dest, timeout=300)
        if r.returncode:
            raise RuntimeError("stub failed: " + (r.stderr or r.stdout)[-400:])
    r = sh(task["setup_cmd"], cwd=dest, timeout=1800)
    if r.returncode:
        raise RuntimeError("setup failed: " + (r.stderr or r.stdout)[-400:])


def apply_hidden_tests(task, dest):
    """Author mode: bring in the grading tests only after the session ends.

    `hidden_patch_cmd` optionally rewrites one of those tests. It exists
    because a grading test that encodes the reference implementation's
    strategy rather than the contract will fail a BETTER implementation --
    which is what the first file-cap test did.
    """
    sh("git checkout -q %s -- %s" % (task["fix_commit"], task["test_path"]), cwd=dest)
    if task.get("hidden_patch_cmd"):
        r = sh(task["hidden_patch_cmd"], cwd=dest, timeout=300)
        if r.returncode:
            raise RuntimeError("hidden patch failed: " + (r.stderr or r.stdout)[-400:])


def skill_src(task):
    """The SKILL.md install_skill saves: the task's own, or Q1's override.

    ABSOLUTE, always. install_skill shells save_skill.py with `cwd=dest` -- the
    throwaway clone -- so a relative --skill-from resolves against the clone and
    is not there. Twelve probes died on that before any session started, and it
    also kept `skill_path` on the result row relative, which is worthless
    provenance once the cwd that gave it meaning is gone.
    """
    return (Path(SKILL_FROM).resolve() if SKILL_FROM
            else ROOT / "skills" / (task["skill"] + ".md"))


def distilled_parts():
    """(distiller, draw) from --skill-from, or None when it is not set.

    Validates the layout instead of indexing into it. A relative path used to
    resolve against cwd and yield plausible-but-wrong ancestor names, and that
    same parse feeds `distiller`/`draw` into results.jsonl -- bogus attribution
    written silently into the evidence, which is worse than the collision the
    segment exists to prevent. Fail loudly here instead.
    """
    if not SKILL_FROM:
        return None
    p = Path(SKILL_FROM).resolve()
    parts = p.parts
    if p.name != "SKILL.md" or len(parts) < 5 or parts[-5] != "distilled":
        raise ValueError(
            "--skill-from must be <...>/distilled/<trap>/<distiller>/<draw>/SKILL.md,"
            " got %s" % SKILL_FROM)
    return parts[-3], parts[-2]


def arm_segment(arm):
    """Path-unique segment per treatment arm, derived from the run's config.

    Every arm this harness has ever had passes `--arm treatment`, so without
    this the clone AND the per-run ledger share a path and the second batch
    silently overwrites the first one's evidence. It did, once (E5).
    """
    if arm != "treatment":
        return ""
    if FORCE_HOT:
        return "-hot"
    seg = ""
    if SKILL_FROM:
        distiller, draw = distilled_parts()
        seg = "-d-%s-%s" % (distiller.replace("-", ""), draw)
    # "-plus" for exactly one extra, which is what E6's twelve archived clones
    # and their manifest entries are named. E8 installs nine, and letting it
    # share E6's segment would put two arms under one clone path -- how E5
    # lost a batch.
    n = len(PLUS_SKILL or ())
    if n:
        seg += "-plus" + (str(n) if n > 1 else "")
    return seg


def skill_name(path):
    """The `name:` from a SKILL.md's frontmatter, or None.

    A distilled draft's name is whatever the distiller chose, so it cannot be
    read off the task config the way a hand-authored one can.
    """
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip() or None
    return None


def tier_of(name):
    """That skill's tier in the user-global index, or None.

    retrieve.eligible() requires tier == "warm", so a skill that landed hot
    produces no injection row at all -- and the funnel's delivery stage would
    read the strongest delivery path as a delivery failure. Asserted rather
    than assumed: b35f756 already cost a batch to exactly this class of bug.
    """
    p = Path.home() / ".claude" / "skillforge" / "index.json"
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for e in idx.get("entries", []):
        if e.get("name") == name:
            return e.get("tier")
    return None


def source_keys(arm, task, tier_at_install):
    """The five provenance keys on a result row.

    Control installs no skill, so every source key is null -- "authored" would
    be a lie. Extracted from one() because the rec dict is otherwise only
    reachable by spending a session, and these keys are the only thing that
    tells a Q1 batch from the batches before it.
    """
    if arm != "treatment":
        return {"skill_source": None, "distiller": None, "draw": None,
                "skill_path": None, "tier_at_install": None}
    parts = distilled_parts()
    return {"skill_source": "distilled" if parts else "authored",
            "distiller": parts[0] if parts else None,
            "draw": int(parts[1]) if parts else None,
            "skill_path": str(skill_src(task)),
            "tier_at_install": tier_at_install}


def injections(db):
    """Injection rows for one run, copied out of the per-run ledger.

    The funnel's delivery stage lives ONLY in these sqlite files under /tmp.
    They are not committed, and one() deletes them at the start of any re-run
    of the same cell -- so a reboot, a /tmp reap, or a partial re-run destroys
    the most-argued-about stage of the primary output with no way back short
    of re-running the batch. Copying them onto the row makes them durable.

    Empty on any failure: this is evidence capture, never a gate.
    """
    try:
        import sqlite3
        con = sqlite3.connect(str(db))
        rows = [{"skill": r[0], "trigger": r[1], "tier": r[2]}
                for r in con.execute(
                    "select skill, trigger, tier from events"
                    " where event_type='injection' order by id")]
        con.close()
        return rows
    except Exception:
        return []


def _save_one(src, dest, plugin_dir):
    r = sh('python3 "%s/scripts/save_skill.py" "%s" --scope project --project-root "%s"'
           % (plugin_dir, src, dest), cwd=dest)
    if r.returncode:
        raise RuntimeError("save_skill failed: " + (r.stdout + r.stderr)[-400:])
    return r.stdout.strip()


def extra_skill_names():
    """Names of every skill installed BESIDE the task's own, else [].

    E6 installed one; E8 installs nine. This list is the only record on the
    row of what the arm actually put in the library.
    """
    return [skill_name(Path(p).resolve()) for p in (PLUS_SKILL or ())]


def install_skill(task, dest, plugin_dir):
    """Put the skill in the clone's PROJECT store via the enforced save path.

    E6 installs a second one after it. Order matters only in that the task's
    own goes first; retrieve ranks them itself at injection time, and on
    `response_text` the IRRELEVANT skill outranks the relevant one -- which is
    the case E6 exists to test.
    """
    notes = [_save_one(skill_src(task), dest, plugin_dir)]
    for extra in (PLUS_SKILL or ()):
        notes.append(_save_one(Path(extra).resolve(), dest, plugin_dir))
    return "\n".join(notes)


def score(task, dest):
    """{name: passed} for the FAIL_TO_PASS set, plus the raw tail.

    Handles both pytest ("FAILED <nodeid>") and this repo's own stdlib
    runners ("PASS <name>" / "FAIL <name>"). A test whose name appears in
    neither a pass nor a fail line counts as NOT passed -- a collection
    error must never read as success.
    """
    r = sh(task["test_cmd"], cwd=dest, timeout=900)
    out = r.stdout + r.stderr
    passed = set()
    for line in out.splitlines():
        line = line.strip()
        is_fail = line.startswith("FAILED") or line.startswith("FAIL ") or " FAILED" in line
        is_pass = line.startswith("PASS ")
        for name in task["fail_to_pass"]:
            if name in line:
                if is_pass:
                    passed.add(name)
                elif is_fail:
                    passed.discard(name)
    return ({n: (n in passed) for n in task["fail_to_pass"]}, out[-600:])


def run_session(task, dest, plugin_dir):
    cmd = ('claude -p %s --plugin-dir %s --permission-mode bypassPermissions'
           ' --model %s'
           % (json.dumps(task["prompt"]), json.dumps(str(plugin_dir)),
              json.dumps(MODEL)))
    t0 = time.time()
    try:
        r = sh(cmd, cwd=dest, timeout=SESSION_TIMEOUT_S)
        return {"ok": r.returncode == 0, "secs": round(time.time() - t0, 1),
                "tail": (r.stdout or r.stderr)[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "secs": SESSION_TIMEOUT_S, "tail": "TIMEOUT"}


def one(task, arm, run_idx, plugin_dir):
    # `-hot` in the name, or E5's two arms collide: both pass --arm treatment,
    # so the clone AND the per-run ledger would share a path and the second
    # batch would silently overwrite the first one's evidence. It did.
    dest = WORK / ("%s-%s%s-%d" % (task["id"], arm, arm_segment(arm), run_idx))
    # PER RUN, not per batch. Every child inherits it -- the session,
    # save_skill.py, and the hooks the session fires -- so bench events never
    # reach the real library, where each throwaway clone would count as its
    # own `project` and corroborate skills across disposable checkouts.
    #
    # Per run because the ledger is what confidence is computed from: a batch
    # ledger let run 1's verification success promote the skill to `working`,
    # so run 2 got it materialized hot while run 1 had it warm. Runs inside a
    # cell must be independent trials, not a sequence that learns.
    ledger_db = dest.parent / (dest.name + ".ledger.db")
    # Deleted, not just pointed at: the .db lives OUTSIDE dest, so prepare()'s
    # rmtree never clears it and a re-run of the same task/arm/run index reads
    # a previous batch's rows as its own. E5 spent a while reading E1's
    # injections as its own before this was noticed.
    for suffix in ("", "-shm", "-wal"):
        Path(str(ledger_db) + suffix).unlink(missing_ok=True)
    os.environ["SKILLFORGE_LEDGER"] = str(ledger_db)
    # Same per-run discipline: exported unconditionally so a previous run's
    # value can never leak into this one.
    os.environ["SKILLFORGE_FORCE_HOT"] = (
        task["skill"] if FORCE_HOT and arm == "treatment" else "")
    # Phase 2 saves a skill per treatment run, and a create spawns a detached
    # `claude -p` critique that is never waited on. 42 of those would run
    # concurrently with the sessions being timed, skewing `secs` and turning
    # rate-limit pressure into a false `resolved: false`. Q1 runs critique
    # retrospectively instead (bench/judge.py).
    os.environ["SKILLFORGE_NO_CRITIQUE"] = "1"
    authoring = task.get("mode", "repair") == "author"
    prepare(task, dest)
    if not authoring:
        pre, _ = score(task, dest)
        if any(pre.values()):
            # A test that is already green cannot measure anything.
            print("  WARNING: %s already passing at baseline" %
                  [n for n, ok in pre.items() if ok])
    trust_before = libguard.snapshot()
    skill_note = install_skill(task, dest, plugin_dir) if arm == "treatment" else ""
    installed = skill_name(skill_src(task)) if arm == "treatment" else None
    tier_at_install = tier_of(installed) if installed else None
    if arm == "treatment" and tier_at_install != "warm":
        print("  WARNING: %s installed at tier %r, not warm -- retrieve.eligible()"
              " will skip it and no injection row will be logged"
              % (installed, tier_at_install))
    sess = run_session(task, dest, plugin_dir)
    if authoring:
        apply_hidden_tests(task, dest)
    post, tail = score(task, dest)
    rec = {"task": task["id"], "arm": arm, "run": run_idx,
           "resolved": all(post.values()), "per_test": post,
           "session_ok": sess["ok"], "secs": sess["secs"], "model": MODEL,
           "delivery": "hot" if os.environ["SKILLFORGE_FORCE_HOT"] else "warm",
           "skill_note": skill_note, "test_tail": tail,
           "injections": injections(ledger_db),
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rec.update(source_keys(arm, task, tier_at_install))
    rec["extra_skills"] = extra_skill_names() if arm == "treatment" else []
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    # Every treatment install writes a key into the operator's real
    # trust.json -- trust.py resolves it to Path.home() regardless of scope.
    # 42 unpruned keys make the batch's closing drift assertion fire on a
    # clean run.
    pruned = libguard.new_trust_keys(trust_before)
    if pruned:
        libguard.prune_trust(pruned)
    print("  %-9s run %d -> %s (%.0fs)" %
          (arm, run_idx, "RESOLVED" if rec["resolved"] else "unresolved", sess["secs"]))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--check", action="store_true",
                    help="verify every path in tasks.json resolves, then exit")
    ap.add_argument("--arm", choices=("treatment", "control", "both"), default="both")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force-hot", action="store_true",
                    help="E5 arm H: deliver the treatment skill hot, with its"
                         " symptom triggers suppressed (test-only)")
    ap.add_argument("--plus-skill", action="append", default=None,
                    help="install this SKILL.md IN ADDITION to the task's own."
                         " Repeatable: E6 passed one, E8 passes nine"
                         " (test-only)")
    ap.add_argument("--skill-from", default=None,
                    help="Q1: install this SKILL.md instead of the task's own."
                         " The path decides the clone segment (test-only)")
    args = ap.parse_args(argv)
    global MODEL, FORCE_HOT, SKILL_FROM, PLUS_SKILL
    MODEL = args.model
    FORCE_HOT = args.force_hot
    SKILL_FROM = args.skill_from
    PLUS_SKILL = args.plus_skill

    cfg = expand(json.loads((ROOT / "tasks.json").read_text(encoding="utf-8")))
    problems = check_config(cfg)
    if problems:
        for problem in problems:
            print("config: %s" % problem, file=sys.stderr)
        if args.check:
            return 1
        print("config: refusing to run against a broken config", file=sys.stderr)
        return 1
    if args.check:
        print("config ok: %d task(s), all paths resolve" % len(cfg["tasks"]))
        return 0
    plugin_dir = Path(cfg["plugin_dir"])
    tasks = [t for t in cfg["tasks"] if args.all or t["id"] == args.task]
    if not tasks:
        print("no matching task; use --all or --task <id>")
        return 1
    arms = ("control", "treatment") if args.arm == "both" else (args.arm,)

    WORK.mkdir(parents=True, exist_ok=True)
    print("model %s | work %s | ledger per run (SKILLFORGE_LEDGER)" % (MODEL, WORK))
    for task in tasks:
        print("%s (skill %s from %s)" % (task["id"], task["skill"], task["skill_source_commit"]))
        for run_idx in range(1, args.runs + 1):
            for arm in arms:
                try:
                    one(task, arm, run_idx, plugin_dir)
                except Exception as e:
                    print("  %-9s run %d -> ERROR %s" % (arm, run_idx, e))
    print("\nresults appended to %s" % RESULTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
