#!/usr/bin/env python3
"""Predict whether each archived draft will be DELIVERED, before probing it.

Author mode never places the grading tests in the tree during the session
(run.py::prepare), so the trap's real error signature never appears in any
tool output and detect.py's symptom matching cannot fire. Delivery falls
entirely to retrieve.run_hook: BM25 over name + description against the
PROMPT, gated on score > 0 and matched >= MIN_MATCHED_TERMS.

So the funnel's delivery stage is a DESCRIPTION test. Recording the
prediction here, before any probe session is spent, is what makes a later
zero attributable instead of ambiguous -- and it costs nothing.

Run: python3 bench/dryrun.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "scripts"))
import retrieve
import distill
import run as bench_run

# The author task each trap is probed with -- the SAME bug as the repair task
# phase 1 distilled from.
PROBES = {"A": "sf-author-response-text",
          "B": "sf-author-fingerprint-preexisting"}


def predict(description, name, prompt):
    """What retrieve.run_hook would decide, using retrieve's own gate."""
    entry = {"name": name or "", "description": description or ""}
    ranked = retrieve.rank(prompt, [entry])
    score, matched = (ranked[0][1], ranked[0][2]) if ranked else (0, 0)
    ok = score > 0 and matched >= retrieve.MIN_MATCHED_TERMS
    return {"score": round(float(score), 4), "matched": int(matched),
            "predicted": "deliver" if ok else "no-deliver"}


def _frontmatter(text):
    """`name` and `description` from a SKILL.md, without a YAML dependency.

    description is a folded block (`description: >`), so its value is the
    indented lines that follow, not the rest of that one line.
    """
    name, desc, in_desc = None, [], False
    for line in text.splitlines():
        if line.strip() == "---" and name and not in_desc:
            break
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            in_desc = False
        elif line.startswith("description:"):
            rest = line.split(":", 1)[1].strip().lstrip(">").strip()
            if rest:
                desc.append(rest)
            in_desc = True
        elif in_desc and line.startswith((" ", "\t")):
            desc.append(line.strip())
        elif line and not line.startswith((" ", "\t")):
            in_desc = False
    return name, " ".join(desc)


def main():
    cfg = bench_run.expand(json.loads(
        (ROOT / "tasks.json").read_text(encoding="utf-8")))
    prompts = {t["id"]: t["prompt"] for t in cfg["tasks"]}
    updated = 0
    for meta_path in sorted(distill.ARCHIVE.glob("*/*/*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        draft = meta_path.parent / "SKILL.md"
        if not draft.is_file():
            continue
        name, desc = _frontmatter(draft.read_text(encoding="utf-8"))
        meta["delivery_prediction"] = predict(
            desc, name, prompts[PROBES[meta["trap"]]])
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        updated += 1
        print("%s/%s/%s -> %s (score %.3f, matched %d)" % (
            meta["trap"], meta["distiller"], meta["draw"],
            meta["delivery_prediction"]["predicted"],
            meta["delivery_prediction"]["score"],
            meta["delivery_prediction"]["matched"]))
    print("%d draft(s) predicted" % updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
