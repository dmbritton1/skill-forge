"""Is the injection selector monotonic in the budget? No -- and here is the fix.

The budget derivation (bench/budget_sweep.py) found that raising the budget
from 2000 to 2400 REMOVES the correct skill on `response_text`. That is not a
property of those two numbers. It is a property of how retrieve.run_hook and
detect.run_hook spend the budget: they walk the ranked list and `continue`
past any entry too expensive for what remains, so a cheaper lower-ranked entry
can occupy space a dearer higher-ranked one would have taken -- and which one
wins depends on the budget in a way that is not monotone.

Two failures are counted over a budget grid, for each pool and task:

  flips   -- the correct-trap skill was delivered at budget B and is NOT
             delivered at the next budget up. The user-visible defect.
  shrinks -- the delivered set at the next budget up is not a superset of the
             set below it. The underlying invariant violation.

Three selectors are compared. All three share every non-budget gate; they
differ only in what they do when an entry does not fit.

  continue  -- today's code: skip it, keep walking.
  break     -- stop; deliver the longest rank-ordered prefix that fits.
  knapsack  -- deliver the affordable subset with the highest total score.

Deterministic and free. Run:

    python3 bench/selector_check.py

Answer, 2026-09-11: `break` is the only one with zero flips and zero shrinks.
`knapsack` is worse than today's code, not better -- an optimal subset is not
stable under a growing budget either. See docs/session-handoff.md section 2.

Re-run 2026-09-13, after 9cbb472 dropped function words from tokenization:
`break` still has 0 flips and 0 shrinks. Its lowest stable budget is now ten 2800
/ seven 1100 (was 2900 / 1850), so a consolidated library is correct below the
shipped 1200.
"""
import itertools
import sys

sys.path.insert(0, 'scripts')
sys.path.insert(0, 'bench')
import retrieve                      # noqa: E402
import budget_sweep as bs            # noqa: E402

# The pools, prompts and per-entry costs are budget_sweep's, unchanged: `ten`
# is E8's library with the novelty gate relaxed, `seven` is that library after
# /consolidate merges its same-bug clusters.
POOLS = (('ten', bs.ten), ('seven', bs.seven))
GRID = range(600, 4001, 50)


def admissible(pool, prompt):
    """Ranked entries passing every gate that does not depend on the budget."""
    return [(e, s) for e, s, m in retrieve.rank(prompt, pool)
            if s > 0 and m >= retrieve.MIN_MATCHED_TERMS]


def greedy(pool, prompt, budget, stop):
    picked, n = [], 0
    for e, _ in admissible(pool, prompt):
        if e['kind'] != 'antiskill' and n >= retrieve.MAX_SKILLS:
            continue
        if e['_cost'] > budget:
            if stop:
                break
            continue
        budget -= e['_cost']
        n += 1
        picked.append(e)
    return picked


def knapsack(pool, prompt, budget, _stop=None):
    """Highest total BM25 score that fits. Exhaustive -- fine at this pool size."""
    cand = admissible(pool, prompt)
    best, best_score = [], -1.0
    for r in range(len(cand), -1, -1):
        for combo in itertools.combinations(cand, r):
            if sum(1 for e, _ in combo if e['kind'] != 'antiskill') > retrieve.MAX_SKILLS:
                continue
            if sum(e['_cost'] for e, _ in combo) > budget:
                continue
            score = sum(s for _, s in combo)
            if score > best_score:
                best, best_score = [e for e, _ in combo], score
        if best:
            break
    return best


SELECTORS = (('continue (pre-2026-09-13)', lambda p, q, b: greedy(p, q, b, False)),
             ('break (today)', lambda p, q, b: greedy(p, q, b, True)),
             ('knapsack', knapsack))


def failures(select, pool, prompt, trap):
    """(flips, shrinks) across the budget grid."""
    flips, shrinks, prev = [], [], None
    for b in GRID:
        got = select(pool, prompt, b)
        names = {e['name'] for e in got}
        ok = any(e['_trap'] == trap for e in got)
        if prev is not None:
            if prev[0] and not ok:
                flips.append(b)
            if not names >= prev[1]:
                shrinks.append(b)
        prev = (ok, names)
    return flips, shrinks


def stable_from(select, pool):
    """Lowest budget delivering a correct skill on BOTH tasks and never losing it."""
    for b in GRID:
        if all(any(e['_trap'] == t for e in select(pool, bs.P[k], b))
               for k, t in bs.TASKS):
            held = all(all(any(e['_trap'] == t for e in select(pool, bs.P[k], c))
                           for k, t in bs.TASKS)
                       for c in GRID if c >= b)
            return b, held
    return None, False


def main():
    print('budget grid %d..%d step %d; %d pools x %d tasks\n'
          % (GRID[0], GRID[-1], GRID[1] - GRID[0], len(POOLS), len(bs.TASKS)))
    print('  %-16s %-8s %-8s %s' % ('selector', 'flips', 'shrinks', 'lowest budget correct on both'))
    for label, select in SELECTORS:
        flips = shrinks = 0
        for _, pool in POOLS:
            for task, trap in bs.TASKS:
                f, s = failures(select, pool, bs.P[task], trap)
                flips += len(f)
                shrinks += len(s)
        where = []
        for name, pool in POOLS:
            b, held = stable_from(select, pool)
            where.append('%s=%s%s' % (name, b, '' if held else ' (not held above)'))
        print('  %-16s %-8d %-8d %s' % (label, flips, shrinks, ', '.join(where)))
    print('\nflips   = correct skill delivered at one budget, gone at the next')
    print('shrinks = delivered set at one budget is not a superset of the one below')
    return 0


if __name__ == '__main__':
    sys.exit(main())
