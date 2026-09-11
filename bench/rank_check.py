"""Does consolidating a library fix the ranking failure E8 measured?

E8 installed ten skills and watched the prompt path hand
`sf-author-response-text` a skill about a DIFFERENT bug on all three runs,
because six near-duplicates about one lesson split the BM25 field. /consolidate
was prioritised as the fix for exactly that. This checks whether it is one.

Deterministic and free -- pure BM25 over the archived skills, no sessions. Run:

    python3 bench/rank_check.py

Criterion, fixed before the first run: on each task, does a skill from the
MATCHING trap win rank 1 and inject within budget?

Answer, 2026-09-11: no. See bench/RESULTS.md, "E8 follow-up".
"""
import sys, json, glob, pathlib
sys.path.insert(0, 'scripts'); sys.path.insert(0, 'bench')
import retrieve, save_skill, consolidate, run as bench_run

cfg = bench_run.expand(json.load(open('bench/tasks.json')))
prompts = {t['id']: t['prompt'] for t in cfg['tasks']}
TASKS = [('sf-author-response-text', 'A'), ('sf-author-fingerprint-preexisting', 'B')]

def entry(path, trap):
    txt = pathlib.Path(path).read_text()
    fm, _ = save_skill.parse_frontmatter(txt)
    return {'name': fm.get('name',''), 'description': fm.get('description',''),
            'kind': fm.get('kind','skill'), 'scope': fm.get('scope','project'),
            'command': fm.get('verification.command'),
            'fingerprints': fm.get('fingerprints') or [],
            'symptoms': fm.get('symptoms') or [],
            '_trap': trap, '_cost': max(1, len(txt)//4), '_path': path}

def deliver(pool, prompt):
    """Replicates retrieve.run_hook's prompt-path selection: rank, then skip
    anything over remaining budget, capped at MAX_SKILLS non-antiskills."""
    budget, n, out = retrieve.INJECT_BUDGET_TOKENS, 0, []
    for e, s, m in retrieve.rank(prompt, pool):
        if s <= 0 or m < retrieve.MIN_MATCHED_TERMS: continue
        if e['kind'] != 'antiskill' and n >= retrieve.MAX_SKILLS: continue
        if e['_cost'] > budget: continue
        budget -= e['_cost']; n += 1; out.append((e, s))
    return out

# BEFORE: the ten E8 installed.
before = [entry(f, f.split('distilled/')[1][0])
          for f in sorted(glob.glob('bench/distilled/*/*/*/SKILL.md'))
          if '/consolidated/' not in f]

# AFTER: clustered members replaced by their merge. Only the two clusters E9
# actually merged are replaced; the global cluster stays as its two members,
# which understates consolidation rather than flattering it.
merges = {'A': entry('bench/distilled/A/consolidated/1/SKILL.md', 'A'),
          'B': entry('bench/distilled/B/consolidated/1/SKILL.md', 'B')}
cls, _ = consolidate.clusters(before)
replaced = set()
for c in cls:
    if c['scope'] == 'project':
        for m in c['members']: replaced.add(m['_path'])
after = [e for e in before if e['_path'] not in replaced] + [merges['A'], merges['B']]

for label, pool in (('BEFORE (E8: 10 skills)', before), ('AFTER (consolidated: %d)' % len(after), after)):
    print('=== %s ===' % label)
    for task, trap in TASKS:
        got = deliver(pool, prompts[task])
        names = [(e['name'], e['_trap'], round(s,2)) for e, s in got]
        ok = any(e['_trap'] == trap for e, _ in got)
        print('  %-26s (want trap %s) -> %s' % (task.replace('sf-author-',''), trap, names))
        print('       matching-trap skill delivered: %s' % ('YES' if ok else 'NO'))
    print()
