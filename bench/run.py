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
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libguard
import audit
import sandbox

ROOT = Path(__file__).resolve().parent
# The repository this harness lives in. tasks.json writes `{root}` rather than
# an absolute path: every path in it used to be hardcoded under a checkout
# that has since moved AND a worktree that has since been deleted, which left
# the whole harness dead without saying so -- `git clone` of a missing path is
# just a failed task.
REPO_ROOT = ROOT.parent
# scrub_secrets() below reuses the plugin's own scanner rather than a second
# copy of its rules. Appended, not inserted at 0, so it never shadows the
# bench-local sys.path.insert() above it.
sys.path.append(str(REPO_ROOT / "scripts"))
from secscan import RULES as SECRET_RULES
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
# Sandbox spec: every session runs under sandbox-exec and is audited. Off only
# via --no-sandbox, whose rows every reader voids.
SANDBOX = True
# Q1: absolute path to a distilled draft, replacing the task's hand-authored
# skill. Off = None. The clone path segment is DERIVED from this (arm_segment)
# rather than passed, because a forgotten segment is the exact bug that let
# E5's two arms overwrite each other.
SKILL_FROM = None
# E6: an ADDITIONAL skill installed beside the task's own, to ask whether an
# irrelevant one riding along dilutes a relevant one. Off = None.
PLUS_SKILL = None
#: Test-only (E10): per-run override for retrieve.py's injection budget, in
#: tokens. None = the shipped 1200. arm_segment carries it into the clone
#: path, because a batch runs two budgets and they must not share a clone.
INJECT_BUDGET = None

#: What was running when this batch produced its rows. Captured once in main().
#: E10's control break on sf-author-response-text (0/3 historically, 3/3 on
#: 2026-09-13) could be narrowed by elimination but never attributed, because
#: no row recorded the environment. This does not capture the served model --
#: `claude-opus-5` is an alias with no dated snapshot, and nothing local
#: reports what it resolved to. Same-batch controls remain the only defence
#: against a model-side change.
ENV = {}

#: E13 section 8: "-p<sha7>" when --plugin-dir is given. Two arms that differ
#: only in the plugin would otherwise share a clone path and a per-run ledger,
#: and the second would overwrite the first's evidence (how E5 lost a batch).
PLUGIN_SEGMENT = ""


def scrub_secrets(value):
    """`value` with every secret-scanner hit replaced by "[redacted:<rule>]".

    Recurses through dicts and lists; a string has each RULES pattern applied
    in order; anything else (int, bool, None) is returned unchanged. A clean
    value comes back equal, so json.dumps of a clean row/meta is unchanged.

    Committed records only: bench/results.jsonl and bench/distilled/*/meta.json
    are published. GitHub push protection blocked a push on 2026-09-14 because
    save_skill's secret-block message quoted the FAKE Stripe key from
    tests/test_save_skill.py's fixture into a row's test_tail -- any batch
    that runs the save_skill tests reproduces that fixture.
    """
    if isinstance(value, str):
        for name, rx in SECRET_RULES:
            value = rx.sub("[redacted:%s]" % name, value)
        return value
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub_secrets(v) for k, v in value.items()}
    return value


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
        if not task.get("fail_to_pass"):
            bad.append("%s: fail_to_pass is empty -- score() would read every run "
                       "as resolved" % task["id"])
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

    Either way the clone then keeps NO history: one commit holding exactly the
    starting tree (strip_history).
    """
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache = cache_dir(task)
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
    strip_history(dest)
    r = sh(task["setup_cmd"], cwd=dest, timeout=1800)
    if r.returncode:
        raise RuntimeError("setup failed: " + (r.stderr or r.stdout)[-400:])


def cache_dir(task):
    return WORK / ("cache-" + task["id"])


def strip_history(dest):
    """Replace the clone's history with one commit of its current tree.

    A clone at the fix's parent still reaches the fix commit and everything
    after it: `git show <fix>:<test_path>` prints the hidden graded tests, and
    `git log --all` walks to the tip, which for E13 holds the spec and stub
    scripts describing each trap. 149 past sessions browsed history heavily
    and never went forward, but that was restraint, not isolation.

    The baseline is taken AFTER the stub or test overlay, so the model starts
    with a clean `git status`, `git diff`/`git stash` still work, and the
    author-mode stub no longer shows the parent's own implementation as a
    deleted hunk. Not closed: the operator's real checkout and past bench
    transcripts are still readable on disk to a bypassPermissions session.
    """
    shutil.rmtree(str(dest / ".git"))
    for cmd in ("git init -q", "git add -A",
                "git -c user.name=bench -c user.email=bench@localhost"
                " -c commit.gpgsign=false commit -q --no-verify -m baseline"):
        r = sh(cmd, cwd=dest)
        if r.returncode:
            raise RuntimeError("history strip failed at %r: %s"
                               % (cmd, (r.stderr or r.stdout)[-400:]))


def apply_hidden_tests(task, dest):
    """Author mode: bring in the grading tests only after the session ends.

    Read from the cache, because the clone no longer has the fix commit
    (strip_history). A failure raises: silently keeping the pre-session test
    file would grade every run against tests that were never hidden.

    `hidden_patch_cmd` optionally rewrites one of those tests. It exists
    because a grading test that encodes the reference implementation's
    strategy rather than the contract will fail a BETTER implementation --
    which is what the first file-cap test did.
    """
    r = subprocess.run(["git", "-C", str(cache_dir(task)), "show",
                        "%s:%s" % (task["fix_commit"], task["test_path"])],
                       capture_output=True, timeout=60)
    if r.returncode:
        raise RuntimeError("hidden tests unavailable: "
                           + r.stderr.decode("utf-8", "replace")[-400:])
    target = dest / task["test_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(r.stdout)
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
    # The bench has two legitimate skill sources: hand-written bench/skills/
    # and model-distilled bench/distilled/. The FILENAME tells them apart -- a
    # distilled draft is always SKILL.md inside <trap>/<distiller>/<draw>/, a
    # hand-written skill is a bare <name>.md. So a non-SKILL.md file is an
    # AUTHORED skill, not an error; source_keys() already records that.
    #
    # Anything NAMED SKILL.md is claiming to be a distilled draft and is held
    # to the full layout below. That is deliberate: a malformed path there is a
    # typo, and turning it into a silent "authored" row is exactly the bogus
    # attribution this function exists to prevent. E12 section 3.3.
    if p.name != "SKILL.md":
        # An authored path has no layout check to fall back on, so the
        # absolute-path rule has to be stated here: install_skill shells
        # save_skill.py with cwd=dest -- the throwaway clone -- so a relative
        # path resolves against the clone and is not there. A distilled path
        # gets this for free below, which refuses "SKILL.md" and "/SKILL.md"
        # alike; hoisting the check above that branch broke a relative
        # distilled path the layout check deliberately tolerates.
        if not Path(SKILL_FROM).is_absolute():
            raise ValueError(
                "--skill-from must be an absolute path, got %s" % SKILL_FROM)
        return None
    if len(parts) < 5 or parts[-5] != "distilled":
        raise ValueError(
            "--skill-from must be <...>/distilled/<trap>/<distiller>/<draw>/SKILL.md,"
            " got %s" % SKILL_FROM)
    return parts[-3], parts[-2]


def plugin_shas(data):
    """{plugin name: commit sha, or version when the entry carries no sha}.

    installed_plugins.json is {"version": N, "plugins": {name: [entry, ...]}}.
    swift-lsp carries a version and no gitCommitSha, so the fallback is real
    rather than defensive. A name with neither maps to "" and is kept: knowing
    a plugin was installed matters even when its revision is unknown.
    """
    out = {}
    for name, entries in (data.get("plugins") or {}).items():
        entry = entries[0] if isinstance(entries, list) and entries else entries
        if isinstance(entry, dict):
            out[name] = entry.get("gitCommitSha") or entry.get("version") or ""
    return out


# The paths that make up the plugin under test. Dirt anywhere else -- above all
# bench/results.jsonl, which every batch appends to -- is not a change to it.
# Both archived snapshots (06885c0 and HEAD) ship commands/, and spec section 8
# calls both "complete plugins" -- a snapshot missing it would not be one.
PLUGIN_PATHS = ("scripts", "hooks", "skills", "commands", ".claude-plugin")

# A plugin snapshot is not a git checkout, so it carries the commit it was
# archived from in this file instead.
SNAPSHOT_MARK = ".bench-plugin-ref"


def snapshot_plugin(ref, dest):
    """Extract the plugin as it was at `ref` into `dest`, marked with its commit.

    Only the plugin's own paths (PLUGIN_PATHS that exist at `ref`), so the
    snapshot is exactly what a session loads and nothing from bench/ or docs/.
    Returns the full sha.
    """
    git = lambda *a: subprocess.run(["git", "-C", str(REPO_ROOT), *a],
                                    capture_output=True, check=True)
    sha = git("rev-parse", "%s^{commit}" % ref).stdout.decode().strip()
    present = set(git("ls-tree", "--name-only", sha).stdout.decode().split())
    paths = [p for p in PLUGIN_PATHS if p in present]
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", sha, *paths).stdout)) as t:
        t.extractall(str(dest))
    (dest / SNAPSHOT_MARK).write_text(sha + "\n", encoding="utf-8")
    return sha


def plugin_commit(plugin_dir):
    """The plugin under test as `<sha>`, `<sha>+dirty`, or "" if not a checkout.

    `env` records installed plugins, but the plugin a batch actually tests comes
    from --plugin-dir, which it never recorded. E13 spec section 9: with another
    session editing retrieve.py in parallel, a row must say which code ran.
    Never raises.
    """
    try:
        mark = Path(plugin_dir) / SNAPSHOT_MARK
        if mark.is_file():
            return "archive:" + mark.read_text(encoding="utf-8").strip()
        head = subprocess.run(["git", "-C", str(plugin_dir), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        if head.returncode:
            return ""
        dirt = subprocess.run(["git", "-C", str(plugin_dir), "status", "--porcelain",
                               "--", *PLUGIN_PATHS],
                              capture_output=True, text=True, timeout=30)
        return head.stdout.strip() + ("+dirty" if dirt.stdout.strip() else "")
    except Exception:
        return ""


def sandbox_plugin(plugin_dir, explicit):
    """The plugin directory a sandboxed session loads (sandbox spec section 2.1).

    tasks.json's plugin_dir is the checkout, and the sandbox cannot allow the
    checkout without allowing bench/ -- hidden tests, results, drafts. A
    checkout is replaced by a snapshot of its HEAD under WORK, reused while the
    commit matches. Raises ValueError for a dirty checkout (the snapshot would
    not be the code on disk) or an explicit --plugin-dir that is not a snapshot.
    """
    plugin_dir = Path(plugin_dir)
    if (plugin_dir / SNAPSHOT_MARK).is_file():
        return plugin_dir
    if explicit:
        raise ValueError("--plugin-dir must be a run.snapshot_plugin() snapshot: %s" % plugin_dir)
    commit = plugin_commit(plugin_dir)
    if not commit or commit.endswith("+dirty"):
        raise ValueError("the plugin checkout has uncommitted changes, or is not a"
                         " checkout: %s" % plugin_dir)
    dest = WORK / ("plugin-" + commit[:7])
    mark = dest / SNAPSHOT_MARK
    if not (mark.is_file() and mark.read_text(encoding="utf-8").strip() == commit):
        snapshot_plugin(commit, dest)
    return dest


def variant_plugin(base, variant_file, dest, tag="e15"):
    """A copy of snapshot `base` whose skills/distilling-skills/SKILL.md is
    `variant_file` (E15 spec section 2).

    Marked `<sha>+<tag>-<first 12 hex of the variant's sha256>`, so
    plugin_commit() -- and through it every distill meta.json -- records which
    rules ran. The base snapshot is never modified.
    """
    base, dest = Path(base), Path(dest)
    mark = base / SNAPSHOT_MARK
    if not mark.is_file():
        raise ValueError("variant base is not a run.snapshot_plugin() snapshot: %s" % base)
    variant = Path(variant_file).read_bytes()
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.copytree(str(base), str(dest))
    target = dest / "skills" / "distilling-skills" / "SKILL.md"
    if not target.is_file():
        raise ValueError("snapshot has no skills/distilling-skills/SKILL.md: %s" % base)
    target.write_bytes(variant)
    sha = mark.read_text(encoding="utf-8").strip().split("+")[0]
    (dest / SNAPSHOT_MARK).write_text(
        "%s+%s-%s\n" % (sha, tag, hashlib.sha256(variant).hexdigest()[:12]), encoding="utf-8")
    return dest


def session_cmd(prompt, dest, plugin_dir, session_id):
    """The `claude -p` command for one bench session, sandboxed unless
    --no-sandbox. distill.py launches through this too: one sandbox, not two."""
    cmd = ("claude -p %s --plugin-dir %s --permission-mode bypassPermissions"
           " --model %s --session-id %s"
           % (json.dumps(prompt), json.dumps(str(plugin_dir)), json.dumps(MODEL), session_id))
    if not SANDBOX:
        return cmd
    return sandbox.wrap(cmd, sandbox.write_profile(dest, plugin_dir, WORK, REPO_ROOT))


def session_audit(session_id, dest, plugin_dir):
    """Row keys for sandbox spec sections 2.4 and 3.

    Never raises: repo_parent() shells out to git (check=True), and a raise
    here loses a paid session's results row in run.py, or -- distill.py calls
    this inside a `finally` -- leaves meta.json unwritten.
    """
    try:
        own_project = sandbox.project_folder(dest)
        aud = audit.audit_transcript(audit.find_transcript(session_id), dest, plugin_dir,
                                     WORK, sandbox.repo_parent(REPO_ROOT), own_project=own_project)
    except Exception:
        aud = {"verdict": "missing", "hits": [], "leaked": []}
    return {"sandbox": SANDBOX, "sandbox_profile": sandbox.TEMPLATE_SHA,
            "session_id": session_id, "audit": aud}


def environment(plugin_dir=None):
    """CLI build, installed plugin revisions, and the commit of the plugin under
    test, for the row. Never raises: a missing file or a slow CLI must not cost
    a batch."""
    try:
        cli = sh("claude --version", timeout=30).stdout.strip()
    except Exception:
        cli = ""
    try:
        raw = (Path.home() / ".claude" / "plugins"
               / "installed_plugins.json").read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        data = {}
    return {"cli": cli, "plugins": plugin_shas(data),
            "plugin_commit": plugin_commit(plugin_dir) if plugin_dir else ""}


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
        parts = distilled_parts()
        if parts:
            distiller, draw = parts
            seg = "-d-%s-%s" % (distiller.replace("-", ""), draw)
        else:
            # Authored skill: the stem is what distinguishes one arm from
            # another, and E12 runs two of them in one batch.
            seg = "-s-%s" % Path(SKILL_FROM).stem.replace("-", "")
    # "-plus" for exactly one extra, which is what E6's twelve archived clones
    # and their manifest entries are named. E8 installs nine, and letting it
    # share E6's segment would put two arms under one clone path -- how E5
    # lost a batch.
    n = len(PLUS_SKILL or ())
    if n:
        seg += "-plus" + (str(n) if n > 1 else "")
    if INJECT_BUDGET:
        seg += "-b%d" % INJECT_BUDGET
    seg += PLUGIN_SEGMENT
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
            # RECORDED home-relative, while skill_src() stays absolute for
            # install_skill. results.jsonl is published, and an absolute path
            # puts the operator's home directory into it -- restored by hand
            # three times now (2026-09-10, e50b61c, 2026-09-13) because each
            # batch wrote it back. Scrubbing at the source ends that.
            "skill_path": _home_relative(skill_src(task)),
            "tier_at_install": tier_at_install}


def _home_relative(text):
    """`~/...` wherever the operator's home path appears in `text`.

    results.jsonl is published. Written as a replace rather than a prefix
    strip because a session tail quotes the home path mid-string -- an error
    naming --plugin-dir, for instance. For a bare path the two are identical.
    """
    return str(text).replace(str(Path.home()) + "/", "~/")


def session_keys(sess):
    """The session's own outcome keys, including WHY it failed.

    Extracted from one() for the same reason source_keys was: the rec dict is
    otherwise only reachable by spending a session.

    run_session captures the CLI's output tail and one() used to drop it, so
    E12's batch recorded 13 rows of `session_ok: false` with the reason
    discarded -- and diagnosing it cost a probe session to learn what the
    batch already knew ("You've hit your session limit").

    Recorded ONLY on failure. A successful session's tail is the model's final
    message: large, on every row, already evidenced by the authored diff, and
    not diagnostic. A session that succeeds while behaving oddly still leaves
    no trace here; that is a deliberate trade, not an oversight.
    """
    return {"session_ok": sess["ok"], "secs": sess["secs"],
            "session_tail": None if sess["ok"]
                            else _home_relative(sess.get("tail") or "")}


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


def run_session(task, dest, plugin_dir, session_id):
    cmd = session_cmd(task["prompt"], dest, plugin_dir, session_id)
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
    # Same per-run discipline: exported unconditionally so a previous run's
    # value can never leak into this one.
    os.environ["SKILLFORGE_INJECT_BUDGET"] = str(INJECT_BUDGET or "")
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
    session_id = str(uuid.uuid4())
    sess = run_session(task, dest, plugin_dir, session_id)
    if authoring:
        apply_hidden_tests(task, dest)
    post, tail = score(task, dest)
    rec = {"task": task["id"], "arm": arm, "run": run_idx,
           "resolved": all(post.values()), "per_test": post,
           "model": MODEL,
           "env": ENV,
           "inject_budget": INJECT_BUDGET,
           "delivery": "hot" if os.environ["SKILLFORGE_FORCE_HOT"] else "warm",
           "skill_note": skill_note, "test_tail": tail,
           "injections": injections(ledger_db),
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rec.update(session_keys(sess))
    rec.update(source_keys(arm, task, tier_at_install))
    rec.update(session_audit(session_id, dest, plugin_dir))
    rec["extra_skills"] = extra_skill_names() if arm == "treatment" else []
    # results.jsonl is published; scrub before writing, not the print below --
    # GitHub push protection blocked a push on 2026-09-14 over a fixture
    # secret quoted in test_tail.
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(scrub_secrets(rec)) + "\n")
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
    ap.add_argument("--inject-budget", type=int, default=None,
                    help="E10: run the prompt hook at this injection budget"
                         " in tokens instead of the shipped 1200 (test-only)")
    ap.add_argument("--plugin-dir", default=None,
                    help="E13 section 8: run against this plugin directory, e.g."
                         " a run.snapshot_plugin() snapshot, instead of tasks.json's"
                         " (test-only)")
    ap.add_argument("--no-sandbox", action="store_true",
                    help="debugging only: run sessions unsandboxed. Every reader"
                         " voids the rows this writes (sandbox spec 2.4)")
    ap.add_argument("--sandbox-check", action="store_true",
                    help="zero sessions: verify the sandbox denies the checkout and"
                         " other clones and allows the clone and plugin, then exit")
    args = ap.parse_args(argv)
    global MODEL, FORCE_HOT, SKILL_FROM, PLUS_SKILL, INJECT_BUDGET, SANDBOX
    MODEL = args.model
    FORCE_HOT = args.force_hot
    SKILL_FROM = args.skill_from
    PLUS_SKILL = args.plus_skill
    INJECT_BUDGET = args.inject_budget
    SANDBOX = not args.no_sandbox
    if INJECT_BUDGET is not None and INJECT_BUDGET <= 0:
        # retrieve.main swallows the ValueError a bad value would raise and
        # then delivers nothing, silently. Fail here instead.
        ap.error("--inject-budget must be a positive integer")

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
    plugin_dir = Path(args.plugin_dir).resolve() if args.plugin_dir else Path(cfg["plugin_dir"])
    if not (plugin_dir / "scripts").is_dir():
        print("plugin dir has no scripts/: %s" % plugin_dir, file=sys.stderr)
        return 1
    if SANDBOX or args.sandbox_check:
        try:
            plugin_dir = sandbox_plugin(plugin_dir, explicit=bool(args.plugin_dir))
        except ValueError as err:
            print("sandbox: %s" % err, file=sys.stderr)
            return 1
    if args.sandbox_check:
        WORK.mkdir(parents=True, exist_ok=True)
        problems = sandbox.self_check(WORK, REPO_ROOT, plugin_dir)
        for problem in problems:
            print("sandbox-check: %s" % problem, file=sys.stderr)
        print("sandbox check %s" % ("FAILED" if problems else "ok"))
        return 1 if problems else 0
    global ENV, PLUGIN_SEGMENT
    ENV = environment(plugin_dir)
    if args.plugin_dir and not ENV["plugin_commit"]:
        print("plugin dir is neither a git checkout nor a marked snapshot,"
              " so no row could record its commit: %s" % plugin_dir, file=sys.stderr)
        return 1
    PLUGIN_SEGMENT = ("-p" + ENV["plugin_commit"].split(":")[-1][:7]
                      if args.plugin_dir else "")
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
