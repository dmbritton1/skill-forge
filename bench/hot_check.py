"""Is the HOT promoter monotonic in its budget, and does it charge the right bytes?

`bench/selector_check.py` asked this of the warm/prompt selector in 2026-09-11
and found a real defect: `retrieve.run_hook` walked the ranked list and
`continue`d past any entry too expensive for what remained, so a cheaper
lower-ranked entry took space a dearer higher-ranked one would have had. It
broke set monotonicity at 15 of 69 budget steps. The fix was `break`.

`sync.sync()`'s hot promoter has the same shape and was never looked at. It is
covered by no deterministic tool in this directory -- selector_check,
budget_sweep, rank_check, gate_analysis and real_path_check all analyse
retrieve/detect, never sync. This is that tool.

Three questions, all free:

  1. INVERSIONS. At one budget, is a lower-ranked eligible skill hot while a
     higher-ranked eligible one is warm? Visible without a grid, and the direct
     signature of skip-and-continue.
  2. SHRINKS / DEMOTIONS. Across a budget grid, is the hot set at each step a
     superset of the step below? A demotion names the skill that went hot at
     one budget and warm at the next.
  3. COST BASIS. `sync.est_tokens(description)` against
     `retrieve.injection_cost(whole file)`, which is what every other path
     charges. handoff 3.3 consolidated that formula into ONE definition
     "reused by the prompt path, the symptom path and the guard" -- sync kept
     its own copy, so this also reports whether the two have drifted.

The pool's COSTS and descriptions are real (budget_sweep's `ten` and `seven`,
the archived distilled skills). The RANKING inputs are synthetic and stated:
every skill is `working` with a distinct success count, so rank order is the
pool order and the sweep isolates cost-versus-budget behaviour, which is the
thing under test. Buckets are not varied because BUCKET_RANK sorts before
successes and would only relabel the same ordering.

Deterministic, 0 sessions, no model. Run: python3 bench/hot_check.py
"""
import sys

sys.path.insert(0, "scripts")
sys.path.insert(0, "bench")
import retrieve                      # noqa: E402
import sync                          # noqa: E402
import budget_sweep as bs            # noqa: E402

POOLS = (("ten", bs.ten), ("seven", bs.seven))
GRID = range(50, 3001, 25)


def hot_pool(pool):
    """budget_sweep's entries, ranked as sync ranks them (see the module note)."""
    out = []
    for i, e in enumerate(pool):
        out.append(dict(e, bucket="working", successes=len(pool) - i,
                        _desc_cost=sync.est_tokens(e["description"]),
                        _file_cost=retrieve.injection_cost(
                            open(e["_path"], encoding="utf-8").read())))
    out.sort(key=lambda s: s["successes"], reverse=True)
    out.sort(key=lambda s: sync.BUCKET_RANK.get(s["bucket"], 2))
    return out


def promote(ranked, budget, stop):
    """sync.sync()'s hot loop, with `stop` choosing break over skip-and-continue."""
    hot, spent = [], 0
    for s in ranked:
        if s["kind"] == "antiskill" or s["bucket"] not in sync.HOT_ELIGIBLE:
            continue
        cost = s["_desc_cost"]
        if spent + cost <= budget:
            hot.append(s["name"])
            spent += cost
        elif stop:
            break
    return hot


def inversions(ranked, budget, stop):
    """Eligible skills that are warm while a LOWER-ranked eligible one is hot."""
    hot = promote(ranked, budget, stop)
    eligible = [s["name"] for s in ranked
                if s["kind"] != "antiskill" and s["bucket"] in sync.HOT_ELIGIBLE]
    out, seen_warm = [], []
    for name in eligible:
        if name in hot:
            out += [(w, name) for w in seen_warm]
        else:
            seen_warm.append(name)
    return out


def sweep(ranked, stop):
    """(shrinks, demotions) across the grid."""
    shrinks, demotions, prev = 0, [], None
    for b in GRID:
        hot = set(promote(ranked, b, stop))
        if prev is not None and not hot >= prev:
            shrinks += 1
            demotions += sorted(prev - hot)
        prev = hot
    return shrinks, demotions


def main():
    print("hot budget grid %d..%d step %d; shipped default %d\n"
          % (GRID[0], GRID[-1], GRID[1] - GRID[0], sync.hot_budget()))
    print("  %-8s %-26s %-8s %-10s %s"
          % ("pool", "rule", "shrinks", "inversions", "skills demoted by a bigger budget"))
    for pool_name, pool in POOLS:
        ranked = hot_pool(pool)
        for label, stop in (("continue (today)", False), ("break", True)):
            shrinks, demotions = sweep(ranked, stop)
            inv = sum(len(inversions(ranked, b, stop)) for b in GRID)
            print("  %-8s %-26s %-8d %-10d %s"
                  % (pool_name, label, shrinks, inv,
                     ", ".join(sorted(set(demotions))) or "-"))

    print("\ncost basis: sync charges the DESCRIPTION; every other path charges the whole file")
    same = sync.est_tokens("x" * 400) == retrieve.injection_cost("x" * 400)
    print("  sync.est_tokens and retrieve.injection_cost agree on a fixed string: %s"
          % ("yes -- one duplicated definition, not yet drifted" if same
             else "NO -- the duplicated formulas have DRIFTED"))
    ranked = hot_pool(bs.seven)
    print("  %-34s %8s %8s %6s" % ("skill (pool: seven)", "desc", "file", "ratio"))
    for s in ranked:
        print("  %-34s %8d %8d %5.1fx"
              % (s["name"][:34], s["_desc_cost"], s["_file_cost"],
                 s["_file_cost"] / s["_desc_cost"]))
    tot_d = sum(s["_desc_cost"] for s in ranked)
    tot_f = sum(s["_file_cost"] for s in ranked)
    print("  %-34s %8d %8d %5.1fx" % ("TOTAL", tot_d, tot_f, tot_f / tot_d))
    print("\n  all seven are hot at the shipped %d by description (%d), and cost %d"
          % (sync.hot_budget(), tot_d, tot_f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
