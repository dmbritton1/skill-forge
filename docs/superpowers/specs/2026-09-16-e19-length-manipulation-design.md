# E19: separate length from outcome by manipulating length directly

**Status:** design written 2026-09-16, before any E19 call ran. **Not yet
approved to run.**

## Why the observational route is exhausted

E17 found `d = −0.44` and its threat 4 fired completely: its three baseline
drafts were the three shortest files and its six variant drafts the six
longest, a perfect rank separation. E18 went looking for the missing cell,
short-and-working, and found only two such drafts in the whole repository —
`Pe = 0.33`, the pre-registered "still confounded" band.

There is no more natural material. Every `bench/skills/*.md` is an anti-skill;
every distilled draft is long; the only short skills are E14's two. **Length
and outcome cannot be separated by choosing a better corpus.** They have to be
separated by changing one while holding the other fixed.

E17 also turned up the harder fact, which E19 does not attempt to explain:
three drafts that resolve the task 18/18 fail critique **3 of 3** — p = 0, not
noise. Whatever E19 finds about length, that stands.

## 1. The design: paired, within-draft

Five short drafts, each critiqued in two forms, **in one batch**:

| arm | text |
| --- | --- |
| `bare` | the draft exactly as it is on disk |
| `padded` | the draft plus the **whole** constant block, +1395 bytes |

```
B   learn-nogate/{1,2,3}/SKILL.md              2590, 3116, 2856 bytes   0/9 on the task
E14 e14-quote-gate-rewrap-{sf,sw}.md           2012, 2025 bytes         4/6, 5/6 on the task
```

5 drafts × 2 arms × 3 calls = **30 calls.** Both arms run in the same batch;
E17's and E18's existing verdicts are **not** reused as the `bare` arm, because
this project does not stitch batches and E10's break was caught only by a
same-batch control.

Outcome does not need re-measuring: the question is whether **critique's
verdict moves with length when content is held as fixed as it can be.** That
makes E19 zero sessions.

## 2. The manipulation, and its irreducible flaw

**You cannot lengthen a document without changing it.** There is no
information-free padding. This is stated here rather than discovered later.

The mitigation is that the treatment is **identical for every draft**: the
whole of `bench/fixtures/e19_pad.md` (1395 bytes), true, non-instructional,
adding no claim any skill depends on, and drawing whatever objection it draws
equally everywhere. In a paired comparison that objection is a constant, so
what E19 measures is not pure length but **"this draft, plus a fixed neutral
addendum, versus this draft"**. The spec claims nothing more.

A first draft of this design padded each file to a common target length of
3400 bytes instead. That was **rejected before running**: it would have given
one draft 25 lines of padding and another 7, so the amount of added surface
would itself have varied with how short the draft started — confounding the
treatment with the very property under test. A constant addition keeps the
treatment identical and lets the final length vary:

```
learn-nogate/1    2590 -> 3985     e14-...-sf   2012 -> 3407
learn-nogate/2    3116 -> 4511     e14-...-sw   2025 -> 3420
learn-nogate/3    2856 -> 4251
```

Every padded form is at or above the V band's floor of 3192, which is what
"made long" has to mean here. Three sit above its ceiling, which is more dose
in the same direction, not a different treatment.

**Rejected alternatives, with reasons:**

- **Padding with the real `validate.py` source.** True and relevant, but it
  adds *information* — critique could verify the skill's claims against it,
  which moves the verdict for a reason that is not length.
- **Stripping rationale from the long drafts to shorten them.** Cleaner in
  principle, since removal adds nothing, but "what counts as rationale" is a
  judgement made per draft by the person running the experiment. Not
  mechanical, so not reproducible.
- **Reusing E17/E18 verdicts as the `bare` arm.** Halves the cost and stitches
  two batches. Refused.

## 3. The pre-registered reading

`Pb` = passes / 15 on `bare`, `Pp` = passes / 15 on `padded`,
`Δ = Pp − Pb`.

| Δ | reading |
| --- | --- |
| ≤ −0.30 | **length is implicated** — the same content, longer, is judged worse, which is the mechanism E17's direction could reduce to |
| ≥ +0.30 | **length is not the driver** — and E17's inverted direction survives its strongest challenge |
| otherwise | **no large effect of length at this size** |

Fisher's exact p is reported and never thresholded, per this project's
convention. Per-draft pairs are printed, because 5 paired drafts is a small
enough n that one draft carrying the result must be visible.

**Stability is reported as E17 and E18 report it.** Pooled across those two,
9 of 13 drafts (69%) returned different verdicts on byte-identical text. E19
adds 10 more draft-forms, and if that rate holds, its own Δ is measured through
the same noise — which is itself worth stating in the write-up.

## 4. What E19 cannot do

- **It cannot rescue the gate.** Section 0 of the E17 write-up and the caching
  table in this session's analysis show every cache rule caps more working
  drafts than broken ones. E19 explains a mechanism; it does not make critique
  predict outcome.
- **It cannot explain the p = 0 drafts.** Three working drafts fail critique
  unanimously. Length may explain the *gradient*; it does not explain a
  reproducible rejection.
- **One trap, one bug.** Every draft is about `validate.verdict_from`.
- **The padded forms have no outcome.** They were never run on the task and
  nothing here claims they would still resolve it.

## 5. Cost

30 `claude -p` calls, zero bench sessions, zero clones, zero writes. Method,
containment, the inconclusive rule and amendment 1's transport guard are E17's,
imported.
