"""At what injection budget does a CORRECT-trap skill actually get delivered?

The E8 follow-up (bench/rank_check.py) showed consolidation does not fix the
ranking failure and that the real blocker is the budget: one skill fits, and on
response_text it is the wrong one. E6 separately showed an irrelevant skill
riding alongside a relevant one costs nothing measurable -- so the fix may be
to make two fit.

Deterministic and free. Run:

    python3 bench/budget_sweep.py

Criterion, fixed before the first run: at each candidate budget, does a skill
from the MATCHING trap get delivered on BOTH tasks?

Answer, 2026-09-11: yes from 3000 -- but the curve was NOT monotonic, and the
correct skill was crowded back out at 2400.

Re-run 2026-09-13, after the selector was fixed to stop at the first entry that
does not fit: the dip is gone. The consolidated seven are correct on both tasks
from 2000 and hold at every budget above it; the ten-skill pool from 3000. The
2400 regression was an artefact of skip-and-continue, not a property of the
budget. See bench/RESULTS.md, "Budget derivation" and "Selector monotonicity".

Re-run again 2026-09-13, after 9cbb472 dropped function words from tokenization:
the consolidated seven are correct on both tasks from 1200, the shipped budget.
The case for raising it was largely a ranking defect. The unconsolidated ten
still need 3000.
"""
import sys, json, glob, pathlib
sys.path.insert(0,'scripts'); sys.path.insert(0,'bench')
import retrieve, save_skill, consolidate, run as bench_run

cfg = bench_run.expand(json.load(open('bench/tasks.json')))
P = {t['id']: t['prompt'] for t in cfg['tasks']}
TASKS = [('sf-author-response-text','A'), ('sf-author-fingerprint-preexisting','B')]

def entry(path, trap):
    txt = pathlib.Path(path).read_text(); fm,_ = save_skill.parse_frontmatter(txt)
    return {'name':fm.get('name',''),'description':fm.get('description',''),
            'kind':fm.get('kind','skill'),'scope':fm.get('scope','project'),
            'command':fm.get('verification.command'),
            'fingerprints':fm.get('fingerprints') or [],'symptoms':fm.get('symptoms') or [],
            '_trap':trap,'_cost':max(1,len(txt)//4),'_path':path}

ten = [entry(f, f.split('distilled/')[1][0])
       for f in sorted(glob.glob('bench/distilled/*/*/*/SKILL.md')) if '/consolidated/' not in f]
merges = {t: entry('bench/distilled/%s/consolidated/1/SKILL.md'%t, t) for t in 'AB'}
cls,_ = consolidate.clusters(ten)
repl = {m['_path'] for c in cls if c['scope']=='project' for m in c['members']}
seven = [e for e in ten if e['_path'] not in repl] + [merges['A'], merges['B']]

def deliver(pool, prompt, budget):
    n, out = 0, []
    for e, s, m in retrieve.rank(prompt, pool):
        if s <= 0 or m < retrieve.MIN_MATCHED_TERMS: continue
        if e['kind'] != 'antiskill' and n >= retrieve.MAX_SKILLS: continue
        if e['_cost'] > budget: break      # prefix semantics, mirrors retrieve.run_hook
        budget -= e['_cost']; n += 1; out.append(e)
    return out

BUDGETS = [1200, 1600, 2000, 2400, 3000, 3600]


# Guarded so bench/selector_check.py can import the pools and prompts without
# this sweep printing itself into that script's output.
def main():
    for label, pool in (('E8 pool (10 skills, gate relaxed)', ten), ('consolidated pool (7)', seven)):
        print('=== %s ===' % label)
        print('  %-7s %-34s %-34s %s' % ('budget','response_text (wants A)','fingerprint (wants B)','both correct?'))
        for b in BUDGETS:
            cells, ok_all = [], True
            for task, trap in TASKS:
                got = deliver(pool, P[task], b)
                ok = any(e['_trap']==trap for e in got)
                ok_all = ok_all and ok
                cells.append('%d skill(s), correct=%s' % (len(got), 'YES' if ok else 'no'))
            print('  %-7d %-34s %-34s %s' % (b, cells[0], cells[1], 'YES' if ok_all else '-'))
        print()
    print('MAX_SKILLS=%d (non-antiskills); MIN_MATCHED_TERMS=%d' % (retrieve.MAX_SKILLS, retrieve.MIN_MATCHED_TERMS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
