#!/usr/bin/env bash
# E14 Stage 1 batch. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md, section 4.
#
# 27 sessions: the control x3 and each draft x6, installed alone, in fixed
# interleaved rounds. Repeats (void, failed or undelivered rows) follow round 6,
# at most 8 (plan ruling 2). A session refused at the session limit postpones
# the whole batch; a resolved control voids it. Either stops the script.
#
# Read with: python3 bench/e14_read.py --window <E14_START> -
# Usage: bash bench/e14_probe.sh [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
TASK="sf-author-verdict-from"
D="$R/bench/drafts/E14"

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
# Sandbox spec section 4.4: zero sessions, before the first one.
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
python3 bench/e14_deliver.py --check-frozen || { echo "FATAL: E14 drafts not frozen and delivered"; exit 1; }

# Spec section 4: rounds 1, 3 and 5 open with a control run.
ORDER=(control sf sw af aw
       sw af aw sf
       control af aw sf sw
       aw sf sw af
       control sf sw af aw
       sw af aw sf)
echo "order: ${ORDER[*]}"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 8 repeats"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "E14_START $START"

run_one() {  # $1: control | sf | sw | af | aw
  if [ "$1" = "control" ]; then
    python3 bench/run.py --task "$TASK" --runs 1 --arm control --model claude-opus-5 \
      || echo "run.py exited non-zero for control"
  else
    python3 bench/run.py --task "$TASK" --runs 1 --arm treatment --model claude-opus-5 \
      --skill-from "$D/e14-quote-gate-rewrap-$1.md" || echo "run.py exited non-zero for $1"
  fi
  local out
  out="$(python3 bench/e14_read.py --window "$START" - 2>&1)"
  case "$out" in
    "batch: incomplete"*|"batch: complete"*) ;;
    "batch: postponed"*) echo "$out"; echo "STOP: session limit -- re-run this whole batch later as one fresh batch"; exit 1 ;;
    "batch: void"*) echo "$out"; echo "STOP: the control resolved -- the batch is void (spec section 4)"; exit 1 ;;
    *) echo "$out"; echo "STOP: could not read the batch -- fix bench/e14_read.py and re-run this whole batch later"; exit 1 ;;
  esac
}

for arm in "${ORDER[@]}"; do
  echo "### $arm"
  run_one "$arm"
done

EXTRA=0
while [ "$EXTRA" -lt 8 ]; do
  TODO_OUT="$(python3 bench/e14_read.py --window "$START" - --todo 2>&1)" \
    || { echo "$TODO_OUT"; echo "STOP: could not read the batch's remaining runs"; exit 1; }
  NEXT="$(printf '%s\n' "$TODO_OUT" | head -n 1)"
  [ -n "$NEXT" ] || break
  echo "### repeat $NEXT"
  run_one "$NEXT"
  EXTRA=$((EXTRA + 1))
done

python3 bench/e14_read.py --window "$START" -
echo "### E14 DONE"
