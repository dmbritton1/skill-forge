#!/usr/bin/env python3
"""Library health report (spec 14) -- writes no events.

Counts always print. A percentage prints only when the sample can carry
one: a count is true at any n, while a rate asserts something stable, and
spec 1.1 already holds that 5-15 lifetime events per skill cannot support
that claim. Below the floor the reader gets the counts and no rate at all,
rather than a hedged rate -- a number on screen gets read as a number.

Two of spec 14's eleven metrics have no instrument behind them and are
printed as such rather than omitted, so the gap stays visible.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger
import library
import retrieve
import trust

# The floor below which no percentage is printed. Chosen as the low end of
# the range spec 1.1 already calls insufficient (5-15 lifetime events), not
# derived from anything -- worth revisiting against real volume rather than
# tuned now against six skills.
MIN_RATIO_N = 10


def rate(part, whole, unit="sessions"):
    """Counts always; a percentage only when the sample can support one."""
    if whole <= 0:
        return "no %s yet" % unit
    if whole < MIN_RATIO_N:
        return "%d of %d %s (n too small for a rate)" % (part, whole, unit)
    return "%d of %d %s (%.0f%%)" % (part, whole, unit, 100.0 * part / whole)


def _bases():
    """The global store, plus the project store when cwd is inside one."""
    bases = [Path.home()]
    proj = Path.cwd().resolve()
    if proj != Path.home().resolve() and (proj / ".claude" / "skillforge").is_dir():
        bases.append(proj)
    return bases


def quarantined():
    """Store files the trust registry does not vouch for.

    Counted from the store rather than the index: an untrusted skill is
    absent from the index entirely, so the index cannot report it. That
    is the whole reason this number is worth printing -- it is the one
    part of the library nothing else surfaces.
    """
    n = 0
    for base in _bases():
        for md in trust.store_skill_files(base):
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue
            if trust.check_text(trust.skill_name(text, md.parent.name),
                                text) != "trusted":
                n += 1
    return n


def _tally(rows, key):
    out = {}
    for r in rows:
        out[r.get(key) or "-"] = out.get(r.get(key) or "-", 0) + 1
    return out


def _counts(d):
    return ", ".join("%s=%d" % kv for kv in sorted(d.items())) or "none"


def section_library(rows):
    """Counts only. Meaningful at n=1, which is why it leads the report."""
    lines = ["LIBRARY", "  skills            %d" % len(rows)]
    for key in ("kind", "scope", "tier", "bucket"):
        lines.append("  by %-14s %s" % (key, _counts(_tally(rows, key))))
    lines.append("  quarantined       %d awaiting /skillforge:review"
                 % quarantined())
    return lines


def section_context(entries, budget):
    """Standing cost is the hot tier only -- warm text is paid per prompt.

    Reported as a fill level and deliberately NOT as a percentage. It
    could honestly be one -- the denominator is a constant we chose, not
    a sample -- but then "no percentage below the floor" would stop being
    a property of the whole report and become a property of most of it,
    and a rule with an exception is one a reader has to remember rather
    than trust. `~120 of 1500 tokens` says the same thing.
    """
    hot = [e for e in entries if e.get("tier") == "hot"]
    tokens = sum(len(e.get("description") or "") for e in hot) // 4
    budget_txt = ("%d" % budget) if budget else "no budget configured"
    return ["CONTEXT COST",
            "  hot skills        %d" % len(hot),
            "  standing tokens   ~%d of %s" % (tokens, budget_txt)]


def section_usage(rows, totals):
    """Injection-to-use, reported warm-only and said so.

    `injection` rows are written for the warm tier alone; hot skills are
    materialized natively and never produce one, while detections are
    written for every tier. A library-wide ratio would therefore divide
    across two different populations and still read as relevance. The
    same defect class as reading a response key the harness never sends.
    """
    inj = totals["by_type"].get("injection", 0)
    det = totals["by_detection"]
    used = sum(det.values())
    lines = ["USAGE",
             "  warm injections   %d" % inj,
             "  detections        %s" % _counts(det),
             "  injection-to-use  %s" % rate(used, inj, "warm injections"),
             "                    (warm tier only -- hot skills are native"
             " and log no injection)"]

    # Compliance miss: the skill was used, the marker protocol drifted.
    miss = seen = 0
    for r in rows:
        u = ledger.usage_for(r["name"])
        miss += u["corroborated_only"]
        seen += u["both"] + u["corroborated_only"] + u["marker_only"]
    lines.append("  marker miss       %s" % rate(miss, seen, "used sessions"))

    # Its own line, below the ratio and outside it. A Read is the consumption
    # path detect.py could not see before, but reading is not applying: these
    # rows carry no outcome, nothing consumes them, and folding them into
    # `detections` above would let scrolling look like evidence.
    reads = ledger.read_sessions()
    if reads:
        total = sum(reads.values())
        lines.append("  text read in      %d session(s) across %d skill(s)"
                     % (total, len(reads)))
        lines.append("                    (opened the skill's own file -- not"
                     " evidence it was applied)")
    return lines


def section_outcomes(rows, totals):
    """What the library's use actually produced.

    `unknown` is printed as its own state and never folded into zero
    successes: an instrument that records nothing and a library nobody
    used look identical once you round one into the other.
    """
    oc = totals["verification_outcomes"]
    buckets = _tally(rows, "bucket")
    saved = totals["by_type"].get("save", 0)
    trusted = buckets.get("trusted", 0)
    return ["OUTCOMES",
            "  verification      success=%d, failure=%d, unknown=%d"
            % (oc["success"], oc["failure"], oc["unknown"]),
            "  buckets           %s" % _counts(buckets),
            "  survival          %s" % rate(trusted, saved, "saved skills")]


# `~<N> min (observed in source session)`, the shape distilling-failures
# tells the drafter to write. Anchored to the line start so a stray "5 min"
# elsewhere in the prose cannot be read as the cost.
COST_RE = re.compile(r"^~?\s*(\d+)\s*min", re.M)


def rediscovery_minutes(rows):
    """(total minutes, anti-skills counted) from stated rediscovery costs.

    Returns the sample size alongside the sum because one anti-skill with
    a large stated cost can dominate the total, and a bare number would
    hide that. The costs are model-written estimates from the source
    session, not measurements -- reported as the claim they are.
    """
    total = n = 0
    for r in rows:
        if r.get("kind") != "antiskill":
            continue
        try:
            text = Path(r.get("path") or "").read_text(encoding="utf-8")
        except OSError:
            continue
        parts = text.split("## Cost of rediscovery", 1)
        if len(parts) < 2:
            continue
        m = COST_RE.search(parts[1].strip())
        if not m:
            continue
        u = ledger.usage_for(r["name"])
        uses = u["both"] + u["corroborated_only"] + u["marker_only"]
        total += int(m.group(1)) * uses
        n += 1
    return total, n


def section_value(rows):
    minutes, n = rediscovery_minutes(rows)
    return ["VALUE",
            "  rediscovery saved ~%d min across %d anti-skill(s)"
            % (minutes, n),
            "                    (self-reported costs x observed uses,"
            " not measured)"]


def section_decisions():
    """What was decided on the way in, as opposed to what is in the library.

    Kept as two tallies rather than one: a reviewer's judgement and the write
    path's refusal are different acts, and summing them would produce a number
    that answers no question. Counts only -- the same reason every other
    section here refuses a rate at this n.

    `edited` and `scope_overridden` are self-reported by the model that wrote
    the draft, so they are softer than the write-path rows, which are
    observations. Said here rather than left for a reader to infer.
    """
    rows = ledger.decisions()
    if not rows:
        return ["DECISIONS", "  none recorded yet"]
    tally = {"human": {}, "system": {}}
    for r in rows:
        side = tally.get(r["actor"])
        if side is not None:
            side[r["verdict"]] = side.get(r["verdict"], 0) + 1
    def fmt(d):
        return ", ".join("%d %s" % (n, v) for v, n in sorted(d.items())) or "none"
    return ["DECISIONS",
            "  reviewer          %s" % fmt(tally["human"]),
            "                    (self-reported at save time, not observed)",
            "  write path        %s" % fmt(tally["system"]),
            "  full history      `library.py decisions`"]


def section_unmeasured():
    """Named, not omitted -- spec 14 requires the gaps stay visible."""
    return ["NOT MEASURED",
            "  hot-tier churn    no tier-change event is written;"
            " needs instrumenting sync.py",
            "  tokens per prompt payload size is derivable, but nothing"
            " counts prompts (`turn` is never written)",
            "  model-obvious     needs epsilon-holdouts (v0.3) and team"
            " volume (spec 1.1)"]


def report():
    rows = library.rows()
    idx = retrieve.load_index() or {}
    totals = ledger.event_totals()
    out = []
    for block in (section_library(rows),
                  section_context(idx.get("entries", []),
                                  idx.get("hot_budget_tokens", 0)),
                  section_usage(rows, totals),
                  section_outcomes(rows, totals),
                  section_value(rows),
                  section_decisions(),
                  section_unmeasured()):
        out.extend(block)
        out.append("")
    return "\n".join(out)


def main(argv=None):
    print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
