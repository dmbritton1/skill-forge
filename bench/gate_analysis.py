#!/usr/bin/env python3
"""Does the delivery gate discriminate? No -- it passes everything.

retrieve.run_hook admits an entry when `score > 0 and matched >=
MIN_MATCHED_TERMS` (=2). `matched` is meant to stand for "this skill is
topically relevant to the prompt". It does not.

In bm25(), `matched += 1` runs BEFORE the IDF weight is computed:

    f = tf.get(term)
    if not f:
        continue
    matched += 1                      # <-- unweighted
    idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
    score += idf * f * ...

So a term carrying no information still counts. IDF correctly collapses a
term present in every document to ~0.03, and the SCORE reflects that -- but
the GATE never asks. Two worthless matches open it.

That would be harmless if descriptions did not share worthless terms. They
do, and partly by rule: save_skill.validate() refuses any description
without "do not use", which guarantees the tokens `not` and `use` in every
skill in the library. ("do" is dropped by tokenize's len>=3 filter. "when"
is spec 4.1 convention, present in every description here but NOT enforced
by the validator.)

The consequence is that the gate is satisfied by the house style rather than
by relevance, and the CONTROL PROMPT below -- a sentence about a cat --
clears it against every skill.

Deterministic, 0 sessions, no model, touches no state. Run:

    python3 bench/gate_analysis.py
"""
import collections
import glob
import json
import pathlib
import sys

sys.path.insert(0, "scripts")
sys.path.insert(0, "bench")
import retrieve      # noqa: E402
import save_skill    # noqa: E402
import run as bench_run  # noqa: E402

# A = escaping (22ddf37), B = truncation (ab4acfe), per bench/distill.py TRAPS.
HAND = {"serialization-corrupts-matching": "A",
        "lossy-transform-false-negative": "B",
        "arrow-tzinfo-string-trap": "-",
        "matcher-input-traps": "AB"}

# No technical content whatsoever. Nothing here should reach a session.
CONTROL_PROMPT = "the cat sat on the mat and did not move when i called"


def corpus():
    out = []
    for f in (sorted(glob.glob("bench/skills/*.md"))
              + sorted(glob.glob("bench/distilled/*/*/*/SKILL.md"))):
        txt = pathlib.Path(f).read_text(encoding="utf-8")
        fm, _ = save_skill.parse_frontmatter(txt)
        fm = fm or {}
        name = fm.get("name", "")
        trap = HAND.get(name, f.split("distilled/")[1][0] if "distilled/" in f else "?")
        out.append({"name": name, "description": fm.get("description", "") or "",
                    "_trap": trap})
    return out


def informative_matches(prompt, entry, df, n):
    """Matched terms that are NOT present in every description."""
    q = set(retrieve.tokenize(prompt))
    toks = set(retrieve.entry_tokens(entry))
    return sum(1 for t in q & toks if df[t] < n)


def main():
    entries = corpus()
    n = len(entries)
    df = collections.Counter()
    for e in entries:
        for tok in set(retrieve.entry_tokens(e)):
            df[tok] += 1

    universal = sorted(t for t, c in df.items() if c == n)
    print("corpus: %d skills | MIN_MATCHED_TERMS = %d" % (n, retrieve.MIN_MATCHED_TERMS))
    print("tokens present in ALL %d descriptions: %s" % (n, " ".join(universal)))
    print("  of these, save_skill.validate() GUARANTEES: not, use"
          " (it refuses a description without 'do not use')")
    print("  idf of a token with df == n: %.4f -- near zero score, full gate credit"
          % retrieve.math.log(1 + (n - n + 0.5) / (n + 0.5)))

    cfg = bench_run.expand(json.loads(pathlib.Path("bench/tasks.json").read_text()))
    P = {t["id"]: t["prompt"] for t in cfg["tasks"]}
    prompts = [
        ("repair  escaping", P["sf-escaping-breaks-symptom-match"], "A"),
        ("repair  truncation", P["sf-truncation-reports-absent"], "B"),
        ("author  response_text", P["sf-author-response-text"], "A"),
        ("author  fingerprint", P["sf-author-fingerprint-preexisting"], "B"),
        ("CONTROL (a cat)", CONTROL_PROMPT, None),
    ]

    print("\n%-22s %-8s %-10s %-22s %s" % (
        "prompt", "clears", "informative", "rank 1", "correct trap at"))
    print("-" * 88)
    for label, prompt, want in prompts:
        ranked = retrieve.rank(prompt, entries)
        clears = sum(1 for e, s, m in ranked
                     if s > 0 and m >= retrieve.MIN_MATCHED_TERMS)
        inf = sum(1 for e, s, m in ranked
                  if s > 0 and informative_matches(prompt, e, df, n)
                  >= retrieve.MIN_MATCHED_TERMS)
        top = ranked[0] if ranked else None
        at = ("n/a" if want is None else
              str(next((i + 1 for i, (e, s, m) in enumerate(ranked)
                        if want in e["_trap"]), None)))
        print("%-22s %-8s %-10s %-22s %s" % (
            label, "%d/%d" % (clears, n), "%d/%d" % (inf, n),
            "%s (%s)" % (top[0]["name"][:15], top[0]["_trap"]) if top else "-", at))

    print("\nREADING")
    print("  clears      -- entries admitted by the shipped gate")
    print("  informative -- entries admitted if `matched` counted only terms that")
    print("                 are NOT in every description. This is the proposed fix.")
    print("  A prompt about a cat clearing the gate against every skill is the")
    print("  defect stated as plainly as it can be.")
    print("\n  Ranking is a separate failure: rank 1 is a trap-B skill on ALL five")
    print("  prompts, including the cat. Roughly one skill fits the 1200 budget, so")
    print("  on trap-A prompts the wrong skill is the one delivered -- which is E8's")
    print("  ranking failure, now with a mechanism rather than an observation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
