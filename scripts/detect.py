#!/usr/bin/env python3
"""PostToolUse detection hook (spec 8.1, 9.1) -- zero context, all script.

Two layers run on every tool call:
  verification -- a Bash command matching a skill's verification.command is
                  the strongest single usage signal in the system: it proves
                  the skill was applied and carries the outcome.
  symptom      -- an anti-skill's error signature appearing in tool output
                  is the trap announcing itself, so answer it in the same
                  turn (the anti-skill fast path, spec 8.1).

Failure is always silent on stdout: exit 0, nothing on the control channel.
A broken index must never break a tool call. Diagnostics go to stderr,
which the harness does not parse.
"""
import json
import os
import re
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
# Edit/Write name their target `file_path`; NotebookEdit uses notebook_path.
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path",
              "NotebookEdit": "notebook_path"}


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


# A failed Bash call arrives as a plain string whose first line is
# "Error: Exit code N". Anchored so it cannot match the phrase appearing
# later inside ordinary command output.
EXIT_CODE_RE = re.compile(r"^Error: Exit code \d+")


def bash_outcome(resp):
    """success / failure / None, from the shapes the harness actually sends.

    Measured over 12,678 real Bash results: a command that ran returns a
    DICT (stdout, stderr, interrupted, isImage, noOutputExpected, sometimes
    returnCodeInterpretation or gitOperation) carrying no error flag of any
    kind, and a command that failed returns a plain STRING beginning
    "Error: Exit code N".

    The previous version looked for `is_error`/`isError` inside the dict.
    Neither key occurs in any of the 11,729 real dicts, and the 950 real
    failures are not dicts at all, so it returned None on every call in
    production -- leaving success_sessions permanently 0 and no skill ever
    promotable. Its tests passed only because the fixture invented the key.

    A string that is NOT "Exit code N" is the harness refusing, blocking, or
    the user rejecting -- 356 of those 950. Those are unknown, never failure:
    a false failure penalizes a skill that worked, and an unknown outcome is
    honest where a wrong one is corrosive. Same reason there is still no
    stderr heuristic; plenty of healthy tools write to stderr.
    """
    if isinstance(resp, dict):
        # ponytail: interrupted means the user stopped it, so the
        # verification never finished -- unknown, not success.
        return None if resp.get("interrupted") else "success"
    if isinstance(resp, str) and EXIT_CODE_RE.match(resp):
        return "failure"
    return None


def _log_edit(*args, **kwargs):
    """Breadcrumbs are best-effort like every other ledger write."""
    try:
        ledger.log_edit(*args, **kwargs)
    except Exception as err:
        print("skillforge: edit write failed: %s" % err, file=sys.stderr)


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


def credited(entry, name, injected):
    """May a verification match count as evidence about this skill?

    Only if the skill's text actually reached the model. The command match
    is a proxy for "the skill was used", and an unguarded proxy credits a
    skill for a command the user would have run anyway: the ledger holds a
    detection for a skill written to be unusable and never read, because it
    declared a command that was run repeatedly for unrelated reasons. That
    outcome is the sole input to success_sessions, which is the sole input
    to the organic half of the Tier A conjunct.

    Hot skills are exempt, deliberately. The harness injects them from the
    native directory and we never observe it, so requiring an injection
    would freeze last_used, decay them out of hot, drop them to warm where
    they ARE visibly injected, and oscillate. Retention on the weaker signal
    is the smaller cost; earning trust on it is not, and earning happens at
    warm.

    A missing `tier` means a triggers.json written before this field
    existed. Gate it: sync rewrites the file at every SessionStart, so the
    window is one session, and not-crediting is the direction that cannot
    manufacture evidence.
    """
    return entry.get("tier") == "hot" or name in injected


def run(data):
    session = retrieve.sanitize_session(data.get("session_id"))
    key = EDIT_TOOLS.get(data.get("tool_name"))
    if key:
        tool_input = data.get("tool_input")
        edited = tool_input.get(key, "") if isinstance(tool_input, dict) else ""
        if edited:
            _log_edit(session, str(edited), data.get("prompt_id"))

    resp = data.get("tool_response")
    is_bash = data.get("tool_name") == "Bash"

    idx = load_triggers()
    if not idx:
        return 0
    cwd = data.get("cwd") or os.getcwd()

    # Read once, above the verification loop as well as the symptom loop
    # below: it is the set of skills whose text actually reached the model
    # this session, and that is exactly the population entitled to claim
    # credit for what happened next.
    seen = retrieve.load_state(session)

    if is_bash:
        tool_input = data.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        cmd_tokens = patterns.tokenize(command)
        outcome = bash_outcome(resp)
        verified = set()
        for v in idx.get("verifications", []):
            name = v.get("skill")
            if not name or name in verified or not retrieve.in_scope(v.get("root", ""), cwd):
                continue
            if patterns.matches(v.get("tokens") or [], cmd_tokens):
                verified.add(name)
                if not credited(v, name, seen):
                    continue
                _log("detection", name, detection="verification",
                     outcome=outcome, session=session)

    hay = patterns.tokenize(response_text(resp))
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
    parts.append(retrieve.MARKER_NOTE)
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
