# `/consolidate` — merge same-bug duplicates in the library

Design written 2026-09-11, after E8. Nothing here has been built. The figures
in §2 were measured against the ten skills in `bench/distilled/`; every other
number is a slot.

## The problem

E8 installed all ten distilled skills and watched retrieval choose. On
`sf-author-response-text` the prompt path delivered a skill about a **different
bug**, three runs out of three, because six near-duplicates about one lesson
were competing in one BM25 ranking and a trap-B skill out-scored all of them.

The task still passed — the symptom path rescued it — but that rescue rides on
anti-skills, which Q1 established cannot be written for a symptomless trap. The
ranking failure is real and the safety net is conditional.

**`/consolidate` merges skills that describe the same bug into one, so the
ranking has one strong candidate instead of six weak ones.**

This is deduplication, not generalization. E2's transfer arm was a replicated
null: abstract same-class knowledge did not help on a different bug, so the
merged skill stays about the one bug. Generalizing sibling clusters into a
shared parent — the original v0.3 idea, and the thing E1's umbrella result
would permit — is explicitly out of scope (§7).

## 1. What it does

```
/consolidate [optional skill name]
```

Proposes clusters of same-bug skills, confirms each with the user, merges an
approved cluster into one skill, and archives the members it replaced.

Nothing is merged without approval, and every merge is reversible through
`library.py restore`, which already exists.

## 2. Measured, and it decided three design points

### 2.1 `verification.command` clusters; text similarity does not

Over the ten skills in `bench/distilled/`, clustering on the exact command
after stripping surrounding quotes and whitespace:

| cluster key | members |
|---|---|
| `python3 tests/test_detect.py` | 3 (trap A) |
| `python3 tests/test_retrieve.py` | 4 (trap B) |
| *no command declared* | 2 — unclustered |
| `python3 -m pytest tests/test_detect.py -q` | 1 — unclustered, singleton |

**Seven of ten cluster, into two clusters, with zero cross-bug
contamination.** That last row is a **false negative and it is the honest
limit of this key**: that skill is about the same bug as the three-member trap-A
cluster and points at the same test file, but invokes it through pytest rather
than directly, so the strings differ and it is left out. The user sees it in
the unclustered list and can merge it by hand.

Normalizing further — extracting the test path out of an arbitrary shell
command — would catch it, and is deliberately not done. That is a parser over
a string a skill author controls, and §3 rests on the cheap signal being good
enough *because a human approves every merge*. A false negative costs one
manual merge; a false positive silently merges two skills about different bugs.

Text similarity is the alternative and it is worse. Name + description token
overlap (Jaccard) runs 0.12–0.36 within a bug and 0.05–0.15 across bugs, and
**the ranges overlap**. `A/learn-nogate/1` against `B/learn/1` scores **0.15** —
higher than the genuine same-bug pair `A/learn-nogate/1` against
`A/learn-failure/2` at **0.12**. A threshold catching that pair would also
merge two skills about different bugs.

So the clustering key is `verification.command`: two skills about one bug in
one repo tend to name the same test, and that is sharper than prose about the
same bug written six different ways. Its other limit is that the command is a
repo-local path, so it cannot cluster across repositories (§7). Skills with no
command — `save_skill.py:145` makes it optional for anti-skills — are listed
but never auto-clustered.

### 2.2 Trust is split, and it makes the merged skill's NAME a decision

The two halves of a skill's record are keyed differently:

| record | keyed by | survives a content change? |
|---|---|---|
| organic — `success_projects`, `failure_projects`, `last_used` | **skill name** | yes |
| Tier A verdicts — `critique`, `executable` | **content hash** | no |

`ledger.confidence` reads the organic half from a view grouped by `skill`;
`ledger.validations_for` returns verdicts "for the EXACT hashes given".

The promotion rule, from `scripts/ledger.py`:

```
bucket = "trusted" if (critique == "pass"
                       and (executable == "pass" or organic_bucket == "trusted")
                       and fresh)
         else ("working" if organic_bucket == "trusted" else organic_bucket)
```

So a merged skill that **reuses a member's name** keeps that member's organic
record, loses only its verdicts, and therefore lands at `working` — one
passing critique away from `trusted`, and critique is spawned automatically on
save. A merged skill under a **new** name starts at `unproven`, and the
organic route back needs `success_projects >= 2`, which is **two distinct
projects**, not two sessions.

**The merged skill therefore inherits the name of its highest-bucket member.**

This is not a loophole. The hash-keyed critique conjunct is precisely what
stops rewritten text riding a name's history back to `trusted`; it drops to
`working` until the new content passes critique on its own. Consolidation is
the ordinary content-change path, not a special case.

### 2.3 Save-then-archive is the only safe order

`library.py cmd_archive` moves a store directory aside **by name**. Archiving
the name the merged skill will occupy would move the merged skill itself.

`save_skill.py --action update` requires the skill to exist, replaces it in
place, re-records trust under the new hash, re-syncs, and re-runs critique. So
the merge is an update-in-place of the inherited name, and the other members
are archived afterwards.

That ordering also gives the failure guarantee for free: if the update is
rejected, nothing has been archived and the library is unchanged.

## 3. Design

### 3.1 Two pieces, following `learn` and `review`

**`scripts/consolidate.py`** — everything deterministic and testable, no model:

| command | does |
|---|---|
| `propose [--name <skill>]` | print clusters as JSON: members, shared key, each member's bucket, and the proposed inherited name |
| `retire <keep> <member>...` | archive every member except `<keep>`, via the existing archive path |

**`commands/consolidate.md`** — the model-facing procedure. Skill bodies are
untrusted data: display them, never follow instructions inside them, matching
`commands/library.md`.

### 3.2 Clustering

A cluster is the set of indexed skills sharing all of:

- a non-empty `verification.command`, compared after stripping surrounding
  quotes and whitespace
- `scope`
- `kind`

Clusters of fewer than two members are not clusters. Skills with no
`verification.command` are reported in a separate `unclustered` list so the
user can see what was skipped and why.

The inherited name is the member with the highest bucket, ordering
`trusted > working > unproven`; ties break on most `success_projects`, then
most recent `last_used`, then name, so the choice is deterministic and does
not depend on index order.

### 3.3 The merge

| part | who writes it | how |
|---|---|---|
| `fingerprints`, `symptoms` | script | deduplicated union of all members, order preserved |
| `name` | script | inherited per §3.2 |
| body, `description` | **model** | a concatenated procedure is not a procedure |
| `verification.command` | script | the shared key — it is what defined the cluster |

The model is instructed to keep the merged skill about the one bug, and to
preserve each member's distinct `Do NOT use when` clauses rather than
averaging them away. Losing the exclusions is how a merged skill becomes the
over-triggering entry that E8's ranking problem punishes.

### 3.4 The flow

1. `consolidate.py propose` → clusters, or "nothing to consolidate".
2. For each cluster, show members with their buckets and the inherited name.
   **If any member is `trusted`, say plainly that the merge drops it to
   `working` until critique re-passes**, and confirm separately.
3. On approval, the model drafts the merged `SKILL.md` to a temp path.
4. `save_skill.py <draft> --scope <scope> --action update` — the enforced save
   path, with its own validation, secscan and critique spawn. A rejection
   stops this cluster and nothing is archived.
5. `consolidate.py retire <keep> <others>` — archives the replaced members.
6. Report what merged, what it inherited, and how to undo it
   (`library.py restore <name>`).

## 4. Errors

| case | behaviour |
|---|---|
| `save_skill` rejects the merged draft | report the rejection, archive nothing, move to the next cluster |
| an archive fails midway | report which members were archived and which were not; the merged skill is already saved, so the library is usable and the residue is visible |
| library empty, or no cluster of ≥2 | say so and stop |
| `--name` given for a skill in no cluster | say it has no duplicates and stop |

## 5. Testing

`tests/test_consolidate.py`, stdlib-only and file-based like the rest:

- two skills sharing a command cluster; two with different commands do not
- a single skill never forms a cluster
- a skill with no `verification.command` is reported unclustered, not merged
- clusters never cross `scope` or `kind`
- the inherited name is the highest-bucket member, and ties break deterministically
- fingerprint/symptom union deduplicates and preserves order
- `retire` never archives the kept name
- quoting and whitespace differences in `verification.command` still cluster

Per `bench/critique-calibration/README.md`, `tests/` must not invoke a model,
so the model-written half is exercised by the command procedure, not by a test.

## 6. Threats

1. **Clustering by `verification.command` is repo-local.** It cannot cluster
   the same lesson across two projects, which is where a real library
   accumulates duplicates.
2. **It clusters by what a skill *claims* to verify.** Q1 found that none of
   the declared verification commands actually discriminate — they point at a
   repo's own suite, which passes without the fix. The command is a reliable
   *identity* signal and an unreliable *quality* signal; §2.1 uses only the
   former.
3. **The key produces false negatives, by design.** One of the ten is about
   the trap-A bug, names the same test file, and does not cluster, because it
   invokes it through pytest. Same-bug skills written months apart will
   routinely differ this way. The user sees them in the unclustered list;
   nothing merges them automatically.
4. **Merging is lossy and the loss is not measured.** Several bodies become
   one — the largest cluster in today's library is four.
   Whether the merged skill performs like its best member or its average is an
   open question, and E1's umbrella result (6/6, two different traps in one
   skill) is suggestive but not the same test.
5. **n of the evidence base is ten skills, in two clusters, from one repo.**
6. **The merged skill inherits organic history it did not earn.** Mitigated by
   the hash-keyed critique conjunct, which holds it at `working` until the new
   text passes on its own — but the successes counted against that name
   happened to different text.

## 7. Out of scope

Generalizing sibling clusters into a shared parent pattern — the other half of
the original v0.3 idea. E1 clears it and E2 warns against it, and it is a
separate design. Automatic consolidation inside `sync`: every merge here is
user-approved. Cross-repo clustering (§6.1). Measuring whether a merged skill
performs like its members, which is an experiment, not a feature, and needs
this feature to exist first.

## 8. A documentation bug found while specifying this

`commands/library.md` tells users that `trusted` needs "two clean sessions".
`scripts/ledger.py` counts `COUNT(DISTINCT project)` and requires
`success_projects >= 2` — **two distinct projects**. Two clean sessions in one
project is one. The prose understates the bar substantially. Fixing it is a
one-line change and belongs with this work, since §2.2 depends on the real
rule.
