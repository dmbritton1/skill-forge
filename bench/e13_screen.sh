#!/usr/bin/env bash
# E13 control screen. Composition is pre-registered:
# docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 3.
#
# Control only, no skill installed in any cell. The candidates are whichever
# E13 author tasks bench/e13_preflight.py wrote into bench/tasks.json. One that
# failed pre-flight is absent there, and is not screened.
#
#   C  sf-author-verdict-from             n=6  candidate
#   D  sf-author-transcript-slice         n=6  candidate
#   E  sf-author-store-dir                n=6  candidate
#   R  sf-author-fingerprint-preexisting  n=3  same-batch reference (0/21)
#
# Up to 21 sessions plus one allowance probe. Admission is 0 of 6. If R resolves
# even once, the screen is void. A session refused at the session limit
# postpones the whole screen: re-run it as one fresh batch, never stitched.
#
# Read with: python3 bench/e13_screen_read.py --window <SCREEN_START> -
#
# Usage: bash bench/e13_screen.sh [--dry-run]
#   --dry-run runs every guard and lists the cells without spending a session.
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# A control cell must receive NOTHING. retrieve.py ranks the global store, so a
# single global skill that scores against these prompts would turn a floor
# measurement into a quiet treatment run while the row still said "control".
python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty -- control would not be control"; exit 1; }

# Every row records plugin_commit. Uncommitted plugin code would make that
# commit a lie about what ran.
if [ -n "$(git status --porcelain -- scripts hooks skills .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test (scripts/ hooks/ skills/ .claude-plugin/)"
  exit 1
fi

# Includes the guard against a task with an empty fail_to_pass, which would
# read every control run as resolved.
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }

# The candidates present, in the spec's order, collected into an array.
CELLS=()
while IFS= read -r id; do
  [ -n "$id" ] && CELLS+=("$id")
done < <(python3 -c "
import json
ids = {t['id'] for t in json.load(open('bench/tasks.json'))['tasks']}
for i in ('sf-author-verdict-from', 'sf-author-transcript-slice', 'sf-author-store-dir'):
    if i in ids:
        print(i)
")
[ "${#CELLS[@]}" -gt 0 ] || { echo "FATAL: no E13 candidate passed pre-flight"; exit 1; }
echo "candidates: ${CELLS[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the session allowance, then screens each candidate n=6 and the reference n=3"
  exit 0
fi

# One session spent to protect up to 21.
PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

echo "SCREEN_START $(date +%Y-%m-%dT%H:%M:%S)"
for id in "${CELLS[@]}"; do
  echo "### $id  (control, n=6)"
  python3 bench/run.py --task "$id" --runs 6 --arm control || echo "run.py exited non-zero for $id"
done
echo "### sf-author-fingerprint-preexisting  (reference, control, n=3)"
python3 bench/run.py --task sf-author-fingerprint-preexisting --runs 3 --arm control \
  || echo "run.py exited non-zero for the reference"
echo "### E13 SCREEN DONE"
