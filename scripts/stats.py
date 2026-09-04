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
