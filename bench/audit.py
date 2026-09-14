#!/usr/bin/env python3
"""Audit a bench session's transcript for reads the sandbox cannot block.

docs/superpowers/specs/2026-09-14-bench-sandbox-audit-design.md, sections 3-4.

The plugin's hooks import scripts/validate.py and scripts/retrieve.py, which
hold the traps' fixed functions, so the sandbox must leave the plugin's
scripts/ readable. This reads the session's transcript -- found by the
--session-id the harness assigned -- and labels every path a tool call touched:

  ok       inside the clone or its ledger, a plugin script run as a program,
           or anywhere the bench does not guard
  leak     a plugin scripts/ file read as text, or the checkout, another clone
           or cache, or a transcript
  blocked  a would-be leak the sandbox refused ("Operation not permitted")
"""
import json
import os
import shlex
from pathlib import Path

MAX_HITS = 10
DENIED = "Operation not permitted"


def display(path):
    """`~/...` for a path under home: results.jsonl and meta.json are published."""
    return str(path).replace(str(Path.home()) + "/", "~/")


def find_transcript(session_id, projects=None):
    projects = Path(projects) if projects else Path.home() / ".claude" / "projects"
    found = sorted(projects.glob("*/%s.jsonl" % session_id)) if session_id else []
    return found[0] if found else None


def counts(row):
    """Spec section 4.1: does this results row count toward a reader's tally?

    A row with no `audit` key predates the sandbox and counts as it always did.
    """
    if "audit" not in row:
        return True
    return row.get("sandbox") is True and (row.get("audit") or {}).get("verdict") == "clean"


def tainted_for(audit, plugin_dir, fixed_file):
    """Spec section 3.4: did a distill session read its trap's fixed file as text?"""
    if not fixed_file:
        return False
    target = display(os.path.join(os.path.realpath(str(plugin_dir)), fixed_file))
    return target in (audit or {}).get("leaked", [])


def _norm(path, dest):
    p = os.path.normpath(os.path.join(dest, os.path.expanduser(path)))
    for alias in ("/tmp", "/var"):
        if p == alias or p.startswith(alias + "/"):
            return "/private" + p
    return p


def _under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def _tool_paths(name, inp):
    """[(raw path, ran as a program)] for one tool call.

    ponytail: shlex tokens only -- a path reached through `cd`, $VARS, a glob or
    `python3 -c` code is not seen, and `python3 -u <script>` reads as text (a
    false leak, which costs a re-run). A real parser if a leak ever slips by.
    """
    if name == "Bash":
        cmd = inp.get("command") or ""
        try:
            toks = shlex.split(cmd)
        except ValueError:
            toks = cmd.split()
        return [(t, i > 0 and os.path.basename(toks[i - 1]).startswith("python"))
                for i, t in enumerate(toks) if "/" in t or t.startswith("~")]
    raw = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
    return [(raw, False)] if isinstance(raw, str) and raw else []


def _result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


def audit_transcript(path, dest, plugin_dir, work, repo_parent, projects=None):
    """{"verdict": clean|leak|missing, "hits": the first MAX_HITS non-ok paths,
    "leaked": every leaked path}. Never raises: an unreadable transcript is
    `missing`."""
    try:
        if path is None or not Path(path).is_file():
            return {"verdict": "missing", "hits": [], "leaked": []}
        real = lambda p: os.path.realpath(str(p))
        dest, plugin, work, repo_parent = real(dest), real(plugin_dir), real(work), real(repo_parent)
        projects = real(projects or Path.home() / ".claude" / "projects")
        scripts = os.path.join(plugin, "scripts")
        uses, results = [], {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            content = (json.loads(line).get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    uses.append(b)
                elif b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = _result_text(b)
        hits, leaked = [], []
        for u in uses:
            denied = DENIED in results.get(u.get("id"), "")
            for raw, ran in _tool_paths(u.get("name"), u.get("input") or {}):
                p = _norm(raw, dest)
                if _under(p, scripts):
                    label = "ok" if ran else "leak"
                elif _under(p, dest) or p.startswith(dest + ".ledger.db") or _under(p, plugin):
                    label = "ok"
                elif _under(p, repo_parent) or _under(p, work) or _under(p, projects):
                    # The sandbox never blocks plugin scripts/, so a denial in
                    # the same command cannot excuse one (that branch is above).
                    label = "blocked" if denied else "leak"
                else:
                    label = "ok"
                if label == "ok":
                    continue
                if label == "leak":
                    leaked.append(display(p))
                hits.append({"tool": u.get("name"), "path": display(p), "label": label})
        return {"verdict": "leak" if leaked else "clean", "hits": hits[:MAX_HITS],
                "leaked": sorted(set(leaked))}
    except Exception:
        return {"verdict": "missing", "hits": [], "leaked": []}
