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


def triggers_path():
    return Path.home() / ".claude" / "skillforge" / "triggers.json"


def load_triggers():
    try:
        return json.loads(triggers_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
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


def _log(*args, **kwargs):
    """Bookkeeping never blocks delivery (design: context first)."""
    try:
        ledger.log_event(*args, **kwargs)
    except Exception as err:
        print("skillforge: ledger write failed: %s" % err, file=sys.stderr)


def response_text(resp):
    if isinstance(resp, str):
        return resp[:MAX_OUTPUT_CHARS]
    try:
        return json.dumps(resp, default=str)[:MAX_OUTPUT_CHARS]
    except (TypeError, ValueError):
        return str(resp)[:MAX_OUTPUT_CHARS]


def run(data):
    idx = load_triggers()
    if not idx:
        return 0
    session = retrieve.sanitize_session(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()
    resp = data.get("tool_response")

    if data.get("tool_name") == "Bash":
        tool_input = data.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        cmd_tokens = patterns.tokenize(command)
        outcome = bash_outcome(resp)
        for v in idx.get("verifications", []):
            name = v.get("skill")
            if not name or not retrieve.in_scope(v.get("root", ""), cwd):
                continue
            if patterns.matches(v.get("tokens") or [], cmd_tokens):
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
        picked.append((name, body))
        seen.add(name)

    if not picked:
        return 0
    parts = ["--- SkillForge anti-skill '%s' (symptom matched in tool output): ---\n%s"
             % (name, body) for name, body in picked]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "\n\n".join(parts)}}))
    retrieve.save_state(session, seen)
    for name, _ in picked:
        _log("injection", name, tier="warm", trigger="symptom", session=session)
    return 0


def main(argv=None):
    try:
        return run(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: detect failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
