#!/usr/bin/env bash
# E15 stages A (smoke) and B (draws). Pre-registered:
# docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md, section 3.
#
# Builds a HEAD plugin snapshot with bench/variants/E15/distilling-skills.md
# swapped in, then distils trap C's repair task under it with the novelty gate
# off. Stage smoke: 1 draw under learn-e15-smoke-nogate, checked. Stage draws:
# 6 draws under learn-e15-nogate. A session refused at the session limit
# postpones the stage (plan ruling 5).
#
# Usage: bash bench/e15_distill.sh --stage smoke|draws [--dry-run]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$R" || exit 1
STAGE=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --stage) STAGE="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 1 ;;
  esac
done
case "$STAGE" in
  smoke) SEG="learn-e15-smoke-nogate"; VARIANT="e15-smoke"; DRAWS=1 ;;
  draws) SEG="learn-e15-nogate"; VARIANT="e15"; DRAWS=6 ;;
  *) echo "usage: bash bench/e15_distill.sh --stage smoke|draws [--dry-run]"; exit 1 ;;
esac

python3 -c "
import sys; sys.path.insert(0, 'bench'); import libguard
snap = libguard.snapshot()
bad = snap['stores'] or snap['global_index']
if bad:
    print('global store/index not empty: %r' % (bad,)); sys.exit(1)
" || { echo "FATAL: operator's global library is non-empty"; exit 1; }
if [ -n "$(git status --porcelain -- scripts hooks skills commands .claude-plugin bench/variants)" ]; then
  echo "FATAL: uncommitted changes in the plugin under test or the variant"; exit 1
fi
python3 bench/run.py --check || { echo "FATAL: bench config check failed"; exit 1; }
python3 bench/run.py --sandbox-check || { echo "FATAL: sandbox self-check failed"; exit 1; }
if [ -e "bench/distilled/C/$SEG" ]; then
  echo "FATAL: bench/distilled/C/$SEG already exists -- a stage is never re-rolled over its archive (plan ruling 5)"; exit 1
fi

SNAP="$(python3 -c "
import sys; sys.path.insert(0, 'bench'); import run
base = run.sandbox_plugin(run.REPO_ROOT, explicit=False)
print(run.variant_plugin(base, 'bench/variants/E15/distilling-skills.md', str(base) + '-e15', 'e15'))
")" || { echo "FATAL: could not build the variant snapshot"; exit 1; }
echo "variant snapshot: $SNAP"
echo "mark: $(cat "$SNAP/.bench-plugin-ref")"

if [ "$DRY" = 1 ]; then
  echo "dry run: every guard passed and the variant snapshot is built; a real run probes the allowance, then $DRAWS distill session(s) under $SEG"
  exit 0
fi

PROBE="$(claude -p 'reply with the single word: ok' --model claude-opus-5 < /dev/null 2>&1)" \
  || { echo "FATAL: session probe failed: $PROBE"; exit 1; }

python3 bench/distill.py --trap C --distiller learn --draws "$DRAWS" --no-novelty-gate \
  --plugin-dir "$SNAP" --variant "$VARIANT" || echo "distill.py exited non-zero"

python3 - "$SEG" <<'PY' || { echo "STOP: session limit during stage $STAGE -- see plan ruling 5 before re-running"; exit 1; }
import glob, json, sys
hit = [p for p in sorted(glob.glob("bench/distilled/C/%s/*/meta.json" % sys.argv[1]))
       if "session limit" in (json.load(open(p)).get("session_tail") or "")]
for p in hit:
    print("session limit: " + p)
sys.exit(1 if hit else 0)
PY

if [ "$STAGE" = "smoke" ]; then
  python3 - <<'PY' || { echo "FATAL: smoke failed -- fix before stage draws"; exit 1; }
import json, sys
m = json.load(open("bench/distilled/C/learn-e15-smoke-nogate/1/meta.json"))
problems = []
if m.get("outcome") != "saved":
    problems.append("outcome %r" % m.get("outcome"))
if m.get("sandbox") is not True:
    problems.append("not sandboxed")
if (m.get("audit") or {}).get("verdict") != "clean":
    problems.append("audit %r" % (m.get("audit") or {}).get("verdict"))
if "+e15-" not in (m.get("plugin_commit") or ""):
    problems.append("plugin_commit %r" % m.get("plugin_commit"))
print("smoke: " + ("PASS" if not problems else "FAIL -- " + "; ".join(problems)))
sys.exit(1 if problems else 0)
PY
fi
echo "### E15 STAGE $STAGE DONE"
