#!/usr/bin/env python3
"""Library health report (spec 14) -- read-only, zero writes.

Counts always print. A percentage prints only when the sample can carry
one: a count is true at any n, while a rate asserts something stable, and
spec 1.1 already holds that 5-15 lifetime events per skill cannot support
that claim. Below the floor the reader gets the counts and no rate at all,
rather than a hedged rate -- a number on screen gets read as a number.

Two of spec 14's eleven metrics have no instrument behind them and are
printed as such rather than omitted, so the gap stays visible.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
