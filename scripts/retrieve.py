#!/usr/bin/env python3
"""BM25 retrieval over the skill index (parent spec §8; slice B design).

Hook mode (default): reads UserPromptSubmit JSON on stdin and emits
additionalContext with matching warm skills. Search mode (--search):
ungated top-N over hot and warm alike, for /skillforge:find.

Word-noise control is two-layer: BM25's IDF weighting makes common-word
overlap nearly worthless, and the >=2-distinct-matched-terms gate refuses
to inject on the strength of any single matched term.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import patterns
import trust

K1 = 1.5
B = 0.75
MIN_MATCHED_TERMS = 2
MAX_SKILLS = 3
INJECT_BUDGET_TOKENS = 1200
GIT_TIMEOUT_S = 0.15
SNAPSHOT_MAX_FILES = 20
SNAPSHOT_MAX_BYTES = 200 * 1024
SNAPSHOT_MAX_PROBES = 12

TOKEN_RX = re.compile(r"[a-z0-9]+")


def index_path():
    return Path.home() / ".claude" / "skillforge" / "index.json"


def state_dir():
    return Path.home() / ".claude" / "skillforge" / "state"


def tokenize(text):
    return [t for t in TOKEN_RX.findall(text.lower())
            if len(t) >= 3 and not t.isdigit()]


def bm25(query_tokens, corpus):
    """[(score, matched_term_count)] aligned with corpus (list of token lists)."""
    n = len(corpus)
    if n == 0:
        return []
    avgdl = (sum(len(d) for d in corpus) / n) or 1.0
    df = {}
    for doc in corpus:
        for t in set(doc):
            df[t] = df.get(t, 0) + 1
    out = []
    q = set(query_tokens)
    for doc in corpus:
        tf = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        score, matched = 0.0, 0
        for term in q:
            f = tf.get(term)
            if not f:
                continue
            matched += 1
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * len(doc) / avgdl))
        out.append((score, matched))
    return out


def load_index():
    try:
        return json.loads(index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def entry_tokens(e):
    return tokenize(e.get("name", "").replace("-", " ") + " " + e.get("description", ""))


def rank(query, entries):
    """[(entry, score, matched)] best-first; deterministic (-score, name)."""
    qt = tokenize(query)
    if not qt or not entries:
        return []
    scored = bm25(qt, [entry_tokens(e) for e in entries])
    ranked = [(e, s, m) for e, (s, m) in zip(entries, scored)]
    ranked.sort(key=lambda t: (-t[1], t[0].get("name", "")))
    return ranked


def search(topic, limit=10):
    idx = load_index()
    if not idx:
        print("no index yet; save a skill or start a session to build it")
        return 0
    hits = [r for r in rank(topic, idx.get("entries", [])) if r[1] > 0][:limit]
    if not hits:
        print("no matches")
        return 0
    for e, score, matched in hits:
        print("%s | %s | %s | %s | %s | %s" % (
            e.get("name", ""), e.get("kind", ""), e.get("tier", ""),
            e.get("scope", ""), e.get("description", "").strip(), e.get("path", "")))
    return 0


def load_state(session):
    try:
        p = state_dir() / ("session-%s.json" % session)
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def save_state(session, names):
    # ponytail: atomic replace, no lock. Tmp filename is process-unique
    # (pid-suffixed) so two hooks racing in one session -- detect.py now
    # fires on every parallel tool call, not just once per prompt -- never
    # truncate the SAME tmp path into each other; that could os.replace a
    # partial/empty file into position and lose the whole session's dedupe
    # set, not just cause one duplicate injection. sync._cleanup_state globs
    # "session-*" so an orphaned pid-suffixed tmp is still swept.
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ("session-%s.json.tmp-%d" % (session, os.getpid()))
    tmp.write_text(json.dumps(sorted(names)), encoding="utf-8")
    os.replace(str(tmp), str(d / ("session-%s.json" % session)))


def sanitize_session(value):
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or "")) or "unknown"


def in_scope(root, cwd):
    """Global entries are always in scope; project entries only inside their root."""
    if not root:
        return False
    if Path(root) == Path.home():
        return True
    return cwd == root or cwd.startswith(root.rstrip("/") + "/")


def eligible(e, cwd):
    return e.get("tier") == "warm" and in_scope(e.get("root", ""), cwd)


def fingerprint_preexisting(fingerprints, cwd):
    """1 if any fingerprint is already in the repo, 0 if none are, None if unknown.

    Two stages: `git grep` on the pattern's longest literal token narrows to
    candidate files at C speed, then the token matcher confirms. Unknown is
    reported as None rather than guessed -- a false "preexisting" silently
    suppresses a real usage credit later (spec 9.1).

    ponytail: 150ms subprocess ceiling because this runs inside a blocking
    hook; a repo big enough to blow it reports unknown instead of stalling.
    """
    if not fingerprints:
        return None
    unknown = False
    for tokens in fingerprints:
        if not tokens:
            continue
        literal = max(tokens, key=len)
        try:
            # grep.fullName=false forced regardless of the user's global git
            # config: with it on, `git grep -l` prints repo-root-relative
            # paths instead of cwd-relative ones, `Path(cwd) / rel` then
            # points nowhere, the read below raises, and the loop used to
            # just continue -- silently reporting "not preexisting" (0)
            # instead of unknown. That's the over-crediting direction the
            # NULL-not-a-guess rule exists to prevent.
            proc = subprocess.run(
                ["git", "-c", "grep.fullName=false", "grep", "-F", "-i", "-l", "--", literal],
                cwd=str(cwd), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=GIT_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError):
            unknown = True
            continue
        if proc.returncode not in (0, 1):   # 1 = no match; anything else = not a usable repo
            unknown = True
            continue
        names = [f for f in proc.stdout.decode("utf-8", "replace").splitlines() if f]
        if len(names) > SNAPSHOT_MAX_FILES:
            unknown = True   # more candidates than we examined -- absence isn't proof
        for rel in names[:SNAPSHOT_MAX_FILES]:
            try:
                with open(str(Path(cwd) / rel), "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read(SNAPSHOT_MAX_BYTES + 1)
            except OSError:
                # git found this file but we couldn't read it -- an unknown
                # answer, not a confirmed absence.
                unknown = True
                continue
            truncated = len(text) > SNAPSHOT_MAX_BYTES
            if patterns.matches(tokens, patterns.tokenize(text[:SNAPSHOT_MAX_BYTES])):
                return 1
            if truncated:
                unknown = True   # match may live past the byte cap -- absence isn't proof
    return None if unknown else 0


def probe_fingerprints(fps, cwd, probes_left):
    """Probe up to `probes_left` of an entry's fingerprints; (preexisting, used).

    An entry with more fingerprints than the remaining budget is probed
    partially rather than skipped outright -- skipping meant an entry with
    more than SNAPSHOT_MAX_PROBES fingerprints could never be snapshotted,
    even as the first entry of a fresh hook run. A match in the probed
    subset is still an honest 1; probed-clean with patterns left unprobed is
    None (unknown), never a false 0 -- checking fewer patterns than exist is
    not proof none of them were already there.
    """
    if not fps:
        return None, 0
    probe = fps[:probes_left]
    if not probe:
        return None, 0
    result = fingerprint_preexisting(probe, cwd)
    if result != 1 and len(probe) < len(fps):
        result = None
    return result, len(probe)


def preamble(name, bucket):
    """Injection header, hedged for skills nothing has ever confirmed.

    The paired A/B benchmark's transfer arm scored 0/6 -- a plausible,
    same-class skill, ledger-confirmed delivered every time, that did not fit
    the bug. Naming that state is the one thing the model cannot read off the
    skill body. A missing bucket (a pre-C2 index) hedges too: understating
    confidence is the safe direction.
    """
    note = ("apply if relevant" if bucket in ("working", "trusted")
            else "unproven -- not proven in a real session;"
                 " apply only if it clearly fits")
    return "--- SkillForge retrieved skill '%s' (%s): ---" % (name, note)


def run_hook(data):
    prompt = data.get("prompt", "")
    session = sanitize_session(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()
    idx = load_index()
    if not idx:
        return 0
    warm = [e for e in idx.get("entries", []) if eligible(e, cwd)]
    seen = load_state(session)
    picked = []
    skills = 0
    budget = INJECT_BUDGET_TOKENS
    probes_left = SNAPSHOT_MAX_PROBES
    for e, score, matched in rank(prompt, warm):
        name = e.get("name")
        if not name or score <= 0 or matched < MIN_MATCHED_TERMS:
            continue
        # session dedupe; picked names go in too, so a name held by both the
        # global and the project store is delivered once, not twice
        if name in seen:
            continue
        if e.get("kind") != "antiskill" and skills >= MAX_SKILLS:
            continue
        try:
            body = Path(e["path"]).read_text(encoding="utf-8")
        except (OSError, KeyError, TypeError):
            continue
        if trust.check_text(name, body) != "trusted":
            continue
        cost = max(1, len(body) // 4)
        if cost > budget:
            continue
        budget -= cost
        preexisting, used = probe_fingerprints(e.get("fingerprints") or [], cwd, probes_left)
        probes_left -= used
        picked.append((name, body, preexisting, e.get("bucket")))
        seen.add(name)
        if e.get("kind") != "antiskill":
            skills += 1
    if not picked:
        return 0
    parts = ["%s\n%s" % (preamble(name, bucket), body)
             for name, body, _, bucket in picked]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n\n".join(parts)}}))
    # Bookkeeping never blocks delivery (context is already printed above):
    # an unguarded save_state that raised here used to return with the
    # context delivered but zero ledger rows logged for the injection.
    try:
        save_state(session, seen)
    except Exception as err:
        print("skillforge: state write failed: %s" % err, file=sys.stderr)
    for name, _, preexisting, _bucket in picked:
        try:
            ledger.log_event("injection", name, tier="warm",
                             trigger="prompt", session=session,
                             preexisting_fingerprint=preexisting)
        except Exception as err:
            print("skillforge: ledger write failed: %s" % err, file=sys.stderr)
    return 0


def main(argv=None):
    # A drafter (slice D1) is a Claude Code process spawned by these very
    # hooks. `claude -p --safe-mode` already disables hooks in the child;
    # this is the guard that survives a change in what --safe-mode covers.
    if os.environ.get("SKILLFORGE_DRAFTING"):
        return 0
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--search")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)
    try:
        if args.search is not None:
            return search(args.search, args.limit)
        return run_hook(json.load(sys.stdin))
    except Exception as e:
        print("skillforge: retrieve failed: %s" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
