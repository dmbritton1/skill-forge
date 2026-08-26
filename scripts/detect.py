#!/usr/bin/env python3
"""PostToolUse detection hook (spec 8.1, 9.1) -- zero context, all script.

Two layers run on every tool call:
  verification -- a Bash command matching a skill's verification.command is
                  the strongest single usage signal in the system: it proves
                  the skill was applied and carries the outcome.
  symptom      -- an anti-skill's error signature appearing in tool output
                  is the trap announcing itself, so answer it in the same
                  turn (the anti-skill fast path, spec 8.1).

Failure is always silent: exit 0, no output. A broken index must never
break a tool call.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import patterns
import retrieve
import trust

MAX_OUTPUT_CHARS = 64 * 1024
MAX_ANTISKILLS = 2
INJECT_BUDGET_TOKENS = 1200
TARGET_MAX_TOKENS = 24


def triggers_path():
    return Path.home() / ".claude" / "skillforge" / "triggers.json"


def load_triggers():
    """The compiled trigger index, or None.

    Absent and corrupt are opposite situations and both yield None, so they
    are reported differently. Absent is normal -- every install is in that
    state until the first sync. Corrupt is never normal and costs the whole
    session's injection, so it says so on stderr rather than looking like a
    quiet session with nothing to inject. stdout stays clean either way:
    that is the harness's control channel.
    """
    try:
        return json.loads(triggers_path().read_text(encoding="utf-8"))
    except OSError:
        return None
    except ValueError as err:      # bad JSON, and UnicodeDecodeError for binary
        print("skillforge: triggers.json is corrupt, ignoring it: %s" % err,
              file=sys.stderr)
        return None


def bash_outcome(resp):
    """success/failure from the harness's own error flag; None when absent.

    ponytail: no stderr heuristic. Plenty of healthy tools write to stderr,
    and a false failure penalizes a skill that worked -- an unknown outcome
    is honest, a wrong one is corrosive.
    """
    if isinstance(resp, dict):
        for key in ("is_error", "isError"):
            if key in resp:
                return "failure" if resp[key] else "success"
    return None


def target_key(command):
    """Stable grouping key for "this same command, run again" (design 2).

    ponytail: the exact tokenized command, capped so a heredoc is bounded
    rather than stored whole. `pytest -x t.py` after `pytest t.py` does NOT
    group, because the inserted flag shifts the sequence -- a missed signal.
    The trade-off runs the other way too: tokenize() drops punctuation, so
    `cat a.txt > b.txt` and `cat a.txt b.txt` collide on the same key, as do
    `rm -rf /tmp/x` and `rm -rf /tmp x`. Rare, and low-harm even when it
    happens -- a spurious draft still has to clear the novelty gate and
    human approval -- but real, not one-sided. Upgrade path if either miss
    rate ever matters: key on the first token plus the longest token.
    """
    return " ".join(patterns.tokenize(command)[:TARGET_MAX_TOKENS])


def _log_signal(*args, **kwargs):
    """Breadcrumbs are best-effort like every other ledger write."""
    try:
        ledger.log_signal(*args, **kwargs)
    except Exception as err:
        print("skillforge: signal write failed: %s" % err, file=sys.stderr)


def _log(*args, **kwargs):
    """Bookkeeping never blocks delivery (design: context first)."""
    try:
        ledger.log_event(*args, **kwargs)
    except Exception as err:
        print("skillforge: ledger write failed: %s" % err, file=sys.stderr)


MAX_FLATTEN_DEPTH = 6


def _flatten(value, parts, depth):
    """Collect string leaves from a tool_response structure, unescaped.

    json.dumps() would turn every real newline into a literal backslash-n,
    which patterns.tokenize then glues onto the next line's first word
    (`...\nWidgetFlushedError` -> one token `nwidgetflushederror`) -- so any
    symptom whose signature starts a line, the normal case for an error
    message, silently never matches. Walking the structure and joining
    leaves with real newlines keeps line starts intact.
    """
    if depth > MAX_FLATTEN_DEPTH or value is None:
        return
    if isinstance(value, str):
        parts.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _flatten(v, parts, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _flatten(v, parts, depth + 1)
    else:
        parts.append(str(value))


def response_text(resp):
    if isinstance(resp, str):
        return resp[:MAX_OUTPUT_CHARS]
    parts = []
    try:
        _flatten(resp, parts, 0)
        return "\n".join(parts)[:MAX_OUTPUT_CHARS]
    except Exception:
        return str(resp)[:MAX_OUTPUT_CHARS]


def run(data):
    session = retrieve.sanitize_session(data.get("session_id"))
    resp = data.get("tool_response")
    is_bash = data.get("tool_name") == "Bash"
    command = ""
    outcome = None
    # Slice D1: the breadcrumb is written BEFORE the trigger index is
    # consulted. It has nothing to do with triggers, and load_triggers()
    # returns None on a corrupt file as well as a missing one -- leaving
    # this below the guard let a single truncated write silently disable
    # automatic capture for the whole session.
    if is_bash:
        tool_input = data.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        outcome = bash_outcome(resp)
        key = target_key(command)
        if outcome is not None and key:
            _log_signal(session, key, outcome == "success")

    idx = load_triggers()
    if not idx:
        return 0
    cwd = data.get("cwd") or os.getcwd()

    if is_bash:
        cmd_tokens = patterns.tokenize(command)
        verified = set()
        for v in idx.get("verifications", []):
            name = v.get("skill")
            if not name or name in verified or not retrieve.in_scope(v.get("root", ""), cwd):
                continue
            if patterns.matches(v.get("tokens") or [], cmd_tokens):
                verified.add(name)
                _log("detection", name, detection="verification",
                     outcome=outcome, session=session)

    hay = patterns.tokenize(response_text(resp))
    seen = retrieve.load_state(session)
    detected = set()
    picked = []
    budget = INJECT_BUDGET_TOKENS
    for s in idx.get("symptoms", []):
        name = s.get("skill")
        if not name or not retrieve.in_scope(s.get("root", ""), cwd):
            continue
        if not patterns.matches(s.get("tokens") or [], hay):
            continue
        if name not in detected:
            detected.add(name)
            _log("detection", name, detection="symptom", trigger="symptom", session=session)
        if name in seen or len(picked) >= MAX_ANTISKILLS:
            continue
        try:
            body = Path(s["path"]).read_text(encoding="utf-8")
        except (OSError, KeyError, TypeError):
            continue
        # The index says what was trusted at compile time, not what is on
        # disk now -- re-verify before anything reaches the model.
        if trust.check_text(name, body) != "trusted":
            continue
        cost = max(1, len(body) // 4)
        if cost > budget:
            continue
        budget -= cost
        picked.append((name, body, s.get("fingerprints") or []))
        seen.add(name)

    if not picked:
        return 0
    parts = ["--- SkillForge anti-skill '%s' (symptom matched in tool output): ---\n%s"
             % (name, body) for name, body, _ in picked]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "\n\n".join(parts)}}))
    try:
        retrieve.save_state(session, seen)
    except Exception as err:
        print("skillforge: state write failed: %s" % err, file=sys.stderr)
    # Snapshot only anti-skills actually being injected, never on every
    # symptom match, and share retrieve's per-hook-call probe budget so this
    # PostToolUse hook can't spawn unbounded git subprocesses.
    probes_left = retrieve.SNAPSHOT_MAX_PROBES
    for name, _, fps in picked:
        preexisting, used = retrieve.probe_fingerprints(fps, cwd, probes_left)
        probes_left -= used
        _log("injection", name, tier="warm", trigger="symptom", session=session,
             preexisting_fingerprint=preexisting)
    return 0


def main(argv=None):
    # A drafter (slice D1) is a Claude Code process spawned by these very
    # hooks. `claude -p --safe-mode` already disables hooks in the child;
    # this is the guard that survives a change in what --safe-mode covers.
    if os.environ.get("SKILLFORGE_DRAFTING"):
        return 0
    try:
        return run(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: detect failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
