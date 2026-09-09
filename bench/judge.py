#!/usr/bin/env python3
"""Judge the archived drafts, after the fact, without steering a live session.

Phase 1 self-approves so the run stays automated and unsteered. This is where
the human gate is recovered -- on files, with the batch already finished.

Five checks per saved draft. They are reported ALONGSIDE the funnel, never
merged into it: a draft can be accepted, delivered, resolve the task, and
still carry a verification command that proves nothing.

Run: python3 bench/judge.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "scripts"))
import validate
import distill
import dryrun

# An error signature carries a machine-shaped token: an exception class, a
# dotted path, a bracketed literal, a call. Narration is prose about what the
# code did. Deliberately crude -- this is a description of the draft, not a
# gate on it.
SIGNATURE = re.compile(r"[A-Z][a-zA-Z]*(Error|Exception)|[\w.]+\(|::|\[['\"]|--\w")


def symptom_shape(entries):
    """"signature" | "narration" | "none".

    distilling-failures step 4 demands literal error signatures. Both
    hand-authored comparators are narration. Measured so the write-up can say
    which side of that asymmetry a draft landed on.
    """
    if not entries:
        return "none"
    hits = sum(1 for e in entries if SIGNATURE.search(e or ""))
    return "signature" if hits * 2 >= len(entries) else "narration"


def has_both_directions(description):
    """save_skill enforces this, so the expected rate is 100%. Anything less
    is a bug in the enforcement, not in the distiller."""
    d = (description or "").lower()
    return "use when:" in d and "do not use when:" in d


def verification_discriminates(command, repo, parent_sha):
    """Does verification.command FAIL where the procedure was NOT applied?

    Run at fix_commit~1, a tree where the skill demonstrably has not been
    applied. Exit 0 there means the command is not a verification. The
    distillation contract states this bar and states that every skill in the
    library has failed it at least once; this is the first machine check.

    None when the command could not be run at all -- unknown, not a pass.
    """
    if not command:
        return None
    try:
        wt = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", parent_sha],
            capture_output=True, text=True, timeout=60)
        if wt.returncode:
            return None
        r = subprocess.run(command, shell=True, cwd=str(repo),
                           capture_output=True, text=True, timeout=300)
        return r.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return None


def fingerprints_in_fix(fps, repo, fix_sha):
    """One bool per fingerprint: does it appear in the real fix's added lines?

    Matching runs against added lines, so a fingerprint that appears nowhere
    in the reference fix is invisible to outcome tracking no matter how well
    the skill was applied.
    """
    if not fps:
        return []
    try:
        r = subprocess.run(["git", "-C", str(repo), "show", fix_sha],
                           capture_output=True, text=True, timeout=120)
        if r.returncode:
            return [False] * len(fps)
        added = "\n".join(l[1:] for l in r.stdout.splitlines()
                          if l.startswith("+") and not l.startswith("+++"))
    except (OSError, subprocess.SubprocessError):
        return [False] * len(fps)
    return [bool(f) and f in added for f in fps]


def _list_field(text, field):
    """A simple `field:` YAML list from a SKILL.md, without a YAML dependency."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith(field + ":"):
            inside = True
            continue
        if inside:
            stripped = line.strip()
            if stripped.startswith("- "):
                out.append(stripped[2:].strip().strip('"\''))
            elif stripped and not line.startswith((" ", "\t")):
                break
    return out


def main():
    plugin_root = ROOT.parent
    cfg = json.loads((ROOT / "tasks.json").read_text(encoding="utf-8"))
    fixes = {t["id"]: t["fix_commit"] for t in cfg["tasks"]}
    judged = 0
    for meta_path in sorted(distill.ARCHIVE.glob("*/*/*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        draft = meta_path.parent / "SKILL.md"
        if not draft.is_file():
            continue
        text = draft.read_text(encoding="utf-8")
        name, desc = dryrun._frontmatter(text)
        kind = "antiskill" if meta["distiller"] == "learn-failure" else "skill"
        fix = fixes[meta["task"]]
        command = ""
        for line in text.splitlines():
            if line.startswith("verification.command:"):
                command = line.split(":", 1)[1].strip().strip('"\'')
        verdict, detail = validate.critique(
            text, {"name": name, "kind": kind, "description": desc}, plugin_root)
        meta["judgement"] = {
            "critique_verdict": verdict,
            "critique_detail": detail,
            "symptom_shape": symptom_shape(_list_field(text, "symptoms")),
            "both_trigger_directions": has_both_directions(desc),
            "verification_discriminates": verification_discriminates(
                command, plugin_root, fix + "~1"),
            "fingerprints_in_fix": fingerprints_in_fix(
                _list_field(text, "fingerprints"), plugin_root, fix),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        judged += 1
        print("%s/%s/%s -> critique %s | symptoms %s | verification %s" % (
            meta["trap"], meta["distiller"], meta["draw"], verdict,
            meta["judgement"]["symptom_shape"],
            meta["judgement"]["verification_discriminates"]))
    print("%d draft(s) judged" % judged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
