# E18: is critique's negative direction about length or about outcome?

**Status:** written 2026-09-16, before any E18 call ran. A **probe**, not a
test — §3 says what it cannot settle.

## Why

E17 read d = −0.44, the "predicts backwards" band, and its own threat 4 fired:
the three baseline drafts are the three *shortest* files and the six variant
drafts the six longest, a perfect rank separation, r(bytes, passes) = −0.70.
"Critique prefers drafts that do not work" and "critique prefers shorter
drafts" make the same prediction over that corpus.

The missing cell is **short and working**. E14's hand-written drafts are
exactly that: 2012–2043 bytes, shorter than all nine E17 drafts (min 2590),
and they resolved 4–6 of 6 on `sf-author-verdict-from`.

| | short | long |
| --- | --- | --- |
| **works** | **E18 (this probe)** | E17 V — 4/18 |
| **does not work** | E17 B — 6/9 | — |

## 1. Corpus, and why it is small

Only two of the four E14 drafts are `kind: skill`. The other two, and all four
`bench/skills/*.md`, are anti-skills, which `rubric_for` answers with
`ANTISKILL_CRITERIA` — a different rubric, not poolable with E17's nine.

**Primary (skill rubric, comparable to E17):** 2 drafts × 3 calls = 6.

```
bench/drafts/E14/e14-quote-gate-rewrap-sf.md   2012 bytes   4/6 on the task
bench/drafts/E14/e14-quote-gate-rewrap-sw.md   2025 bytes   5/6 on the task
```

**Secondary (anti-skill rubric, new ground):** 2 drafts × 3 calls = 6.

```
bench/drafts/E14/e14-quote-gate-rewrap-af.md   2030 bytes   6/6 on the task
bench/drafts/E14/e14-quote-gate-rewrap-aw.md   2043 bytes   6/6 on the task
```

E17 §6 lists anti-skills as something it could not answer, because every
member of its corpus was a skill. These two are the first `ANTISKILL_CRITERIA`
data this project has, and they are reported separately — never pooled with
the primary.

12 calls in total. Method, containment and the inconclusive rule are E17's,
reused by importing `bench/e17_q5.py`: `validate.critique()` called directly,
no ledger row, no trust entry, nothing installed, `SKILLFORGE_VALIDATE_MODEL`
unset. Amendment 1's transport guard applies.

## 2. The pre-registered reading

`Pe` = passes / 6 over the two **skill** drafts. Against E17's measured
anchors — B (short, does not work) **0.67**, V (long, works) **0.22**:

| Pe | reading |
| --- | --- |
| ≥ 0.50 | **length** — short-and-working patterns with short-and-broken |
| ≤ 0.25 | **outcome** — short-and-working patterns with long-and-working |
| otherwise | **neither cleanly** |

Stability is reported as E17 reports it: whether each draft's 3 calls agree.

## 3. What this cannot settle, stated before the data

- **n = 6 calls over 2 drafts.** At that size the gap between 0.67 and 0.22 is
  visible but carries no significance, and no p-value is computed. This probe
  can **point**; it cannot settle the confound. A result in the middle band
  should be read as "still confounded", not as a finding.
- **Length is not isolated, only extended.** These drafts are shorter *and*
  hand-written *and* about a different trap framing than E15's distilled six.
  A "length" reading is really "the short hand-written ones pass too".
- **Different authorship.** E17's nine are distiller output; these four were
  written by hand for E14. Nothing separates authorship from length here.
- **No length-matched construction.** Truncating the long drafts to match
  would break their content and confound differently, so it was rejected.

## 4. Why it is worth 12 calls anyway

If `Pe` lands high, E17's "predicts backwards" headline is explained by
verbosity, and that merges with Q4 — the distiller writes drafts that cost
~1,100 tokens per resolution *and* are likelier to be rejected by the gate —
into a fourth candidate rule for `distilling-skills`. That is actionable in a
way "the gate predicts backwards" is not. If `Pe` lands low, the backwards
reading survives its strongest challenge at a cost of 12 calls.
