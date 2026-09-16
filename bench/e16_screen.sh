#!/usr/bin/env bash
# E16 control screen. Composition and order are pre-registered:
# docs/superpowers/specs/2026-09-16-e16-author-traps-design.md, section 3.
#
# Control only, no skill installed in any cell. The candidates are whichever
# E16 author tasks bench/e16_preflight.py wrote into bench/tasks.json.
#
#   F  sf-author-read-markers             n=6  candidate
#   G  sf-author-event-totals             n=6  candidate
#   R  sf-author-fingerprint-preexisting  n=3  same-batch reference (0/25)
#
# 15 sessions in three interleaved rounds, each opening with the reference,
# plus up to 6 repeats. Admission needs a 0/6 floor the trap produced (section
# 3.3). A resolved reference voids the batch.
#
# Spec section 3.2 (E15 amendment 4): a failed session never counts and is
# re-run in its place. At the session limit the script waits for the reset and
# goes on; after 3 failed sessions in a row, or 3 runs that write no row, it
# stops, and --resume continues the SAME batch. Batches are never stitched:
# the CLI version, model and plugin commit must hold for every row.
#
# Read with: python3 bench/e16_screen_read.py --window <SCREEN_START> -
# Usage: bash bench/e16_screen.sh [--dry-run | --resume <SCREEN_START>]
set -u
export DISABLE_AUTOUPDATER=1  # a CLI update mid-batch would stop it
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
DRY=0
START=""
case "${1:-}" in
  --dry-run) DRY=1 ;;
  --resume) START="${2:?--resume needs the batch SCREEN_START}" ;;
  "") ;;
  *) echo "usage: bash bench/e16_screen.sh [--dry-run | --resume <SCREEN_START>]"; exit 1 ;;
esac

# A control cell must receive NOTHING. retrieve.py ranks the global store, so a
# single global skill that scored against these prompts would turn a floor
# measurement into a quiet treatment run while the row still said "control".
python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty -- control would not be control"; exit 1; }

# Every row records plugin_commit. Uncommitted plugin code would make it a lie.
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test"; exit 1
fi

# Includes the guard against a task with an empty fail_to_pass, which would
# read every control run as resolved.
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }

ORDER=()
while IFS= read -r task; do
  [ -n "$task" ] && ORDER+=("$task")
done < <(python3 bench/e16_screen_read.py --order)
[ "${#ORDER[@]}" -gt 0 ] || { echo "FATAL: could not read the screen order"; exit 1; }
echo "order (${#ORDER[@]} runs):"
printf '  %s\n' "${ORDER[@]}"

known() {  # $1: a task id; true if it appears in ORDER
  local t
  for t in "${ORDER[@]}"; do [ "$t" = "$1" ] && return 0; done
  return 1
}

CLI="$(claude --version)"
HEAD="$(git rev-parse HEAD)"
if [ -n "$START" ]; then
  ENVS="$(python3 bench/e16_screen_read.py --window "$START" - --env)" \
    || { echo "FATAL: could not read the batch's env"; exit 1; }
  if [ -n "$ENVS" ]; then
    [ "$(printf '%s\n' "$ENVS" | wc -l | tr -d ' ')" = 1 ] || { echo "$ENVS"; echo "FATAL: the batch is mixed"; exit 1; }
    case "$ENVS" in
      "$CLI|claude-opus-5|archive:$HEAD") ;;
      *) echo "batch: $ENVS"; echo "now:   $CLI|claude-opus-5|archive:$HEAD"
         echo "FATAL: the CLI or HEAD changed since the batch began -- restore them, then resume"; exit 1 ;;
    esac
  fi
fi

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed; CLI $CLI, HEAD ${HEAD:0:7}; a real run probes the allowance, then ${#ORDER[@]} sessions plus up to 6 repeats"
  exit 0
fi

allowance() {  # waits, re-probing every 10 minutes, until a session can run
  local out
  while :; do
    if out="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)"; then
      case "$out" in *limit*) ;; *) return 0 ;; esac
    fi
    echo "waiting ($(date +%H:%M)): $out"
    sleep 600
  done
}

allowance
[ -n "$START" ] || START="$(date +%Y-%m-%dT%H:%M:%S)"
echo "SCREEN_START $START"
echo "resume with: bash bench/e16_screen.sh --resume $START"

FAILS=0
while :; do
  OUT="$(python3 bench/e16_screen_read.py --window "$START" - 2>&1)" \
    || { echo "$OUT"; echo "STOP: the reader failed"; exit 1; }
  case "$OUT" in
    "screen: incomplete"*|"screen: complete"*) FAILS=0 ;;
    "screen: paused -- session limit"*) FAILS=0; echo "$OUT" | head -n 1; allowance ;;
    "screen: paused -- failed session"*)
      FAILS=$((FAILS + 1))
      if [ "$FAILS" -ge 3 ]; then
        echo "$OUT"; echo "STOP: 3 failed sessions in a row -- find the cause, then: bash bench/e16_screen.sh --resume $START"; exit 1
      fi
      sleep 120; allowance ;;
    "screen: void"*) echo "$OUT"; echo "STOP: the reference resolved -- the batch is void"; exit 1 ;;
    "screen: mixed"*) echo "$OUT"; echo "STOP: the CLI, model or plugin commit changed mid-batch"; exit 1 ;;
    *) echo "$OUT"; echo "STOP: could not read the screen -- fix bench/e16_screen_read.py, then resume"; exit 1 ;;
  esac
  NEXT="$(python3 bench/e16_screen_read.py --window "$START" - --next 2>&1)" \
    || { echo "$NEXT"; echo "STOP: could not read the next run"; exit 1; }
  [ -n "$NEXT" ] || break
  known "$NEXT" || { echo "$NEXT"; echo "STOP: unexpected --next output"; exit 1; }
  [ "$(claude --version)" = "$CLI" ] || { echo "STOP: the CLI changed to $(claude --version) -- reinstall $CLI, then resume"; exit 1; }
  [ "$(git rev-parse HEAD)" = "$HEAD" ] || { echo "STOP: HEAD moved -- check out $HEAD, then resume"; exit 1; }
  echo "### $NEXT ($(date +%H:%M:%S))"
  ROWS="$(wc -l < bench/results.jsonl)"
  python3 bench/run.py --task "$NEXT" --runs 1 --arm control --model claude-opus-5 \
    || echo "run.py exited non-zero for $NEXT"
  if [ "$(wc -l < bench/results.jsonl)" = "$ROWS" ]; then
    NOROW=$((${NOROW:-0} + 1))
    [ "$NOROW" -lt 3 ] || { echo "STOP: run.py wrote no row 3 times in a row -- find the cause, then: bash bench/e16_screen.sh --resume $START"; exit 1; }
    sleep 120; allowance
  else
    NOROW=0
  fi
done

echo "$OUT"
if ! printf '%s\n' "$OUT" | head -n 1 | grep -q '^screen: complete'; then
  echo "INCOMPLETE: runs still missing after 6 repeats -- record this screen as incomplete"
  exit 1
fi
echo "### E16 SCREEN DONE"
