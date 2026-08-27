# SkillForge — Architecture Specification

*A self-improving skill library, packaged as a Claude Code plugin. The system observes coding sessions, distills successful workflows and instructive failures into skills, validates them empirically, injects them into future tasks, and continuously scores, compresses, and prunes its own knowledge.*

Version: draft 0.7 · July 2026 — adds volume-gated activation (1.1), three-bucket confidence, executable Tier A with organic cap-lift, Tier B repositioned as on-demand with replayed-prompt tasks, BM25-first retrieval, committed-file content purity + churn controls; 0.6 added the attribution pipeline; 0.5 security model; 0.4 tiered delivery

---

## 1. Design principles

**Engine and knowledge are separate.** The plugin is the engine (commands, hooks, distiller, scorer). Learned skills are data that live outside the plugin, so the engine can be updated without clobbering knowledge, and knowledge can be versioned in git independently of the engine.

**Every skill must earn and keep its place.** Nothing enters the library without passing a quality gate, and nothing stays without maintaining a confidence score fed by real usage outcomes. The library defends itself.

**Push over pull.** Skill delivery never depends on the model remembering to look something up. Native skill descriptions plus a prompt-time injection hook guarantee relevant knowledge is in context before work begins.

**Context tokens are the scarce resource.** The system optimizes for relevance density — the smallest injection that improves the outcome — not for library size. Skills get shorter as they mature, and injection is gated by confidence and match quality.

**Failures are first-class knowledge.** Debugging dead ends and corrected mistakes are distilled into anti-skills (gotchas), which are often higher-value per token than success procedures.

### 1.1 Volume-gated activation

Parts of this design need event volume to mean anything, and the deployment story is single-user until v1.0. Rather than shipping instruments that read as precise while running on 5–15 lifetime events per skill, each mechanism activates at the scale where its numbers are measurements — with an explicit substitute below that scale. This table doubles as an honest capabilities statement: it says which `/stats` numbers are measured and which are placeholders awaiting volume.

| Mechanism | Activates at | Substitute below that scale |
|---|---|---|
| Deterministic detection (markers, verification/symptom matching, snapshots) | Personal (facts at n=1) | — |
| Event ledger | Personal (events can't be reconstructed later) | — |
| Confidence buckets (unproven / working / trusted) | Personal | — |
| Executable Tier A + organic cap-lift | Personal | — |
| Staged rollout as the per-skill instrument | Personal | — |
| Fine-grained beta gating with lower bounds | Team | Three buckets |
| ε-holdouts, model-obvious rate | Team | Distiller novelty self-gate |
| Judge calibration | Team | Judge verdicts escalate to manual audit |
| Tier B A/B trials as default gate | Team (on-demand earlier) | Executable Tier A + staged rollout |
| Per-author signing | Team (layered on PR queue) | Content-hash review |

---

## 2. System overview

```
                        ┌─────────────────────────────────────────┐
                        │           CLAUDE CODE SESSION           │
                        └─────────────────────────────────────────┘
                             │                          ▲
              session events │                          │ injected skills
                             ▼                          │
   ┌──────────────┐   ┌──────────────┐          ┌───────────────┐
   │  Stop hook    │   │ PostToolUse  │          │ UserPrompt-   │
   │  (capture     │   │ hook         │          │ Submit hook   │
   │  candidates)  │   │ (outcomes)   │          │ (retrieval)   │
   └──────┬───────┘   └──────┬───────┘          └───────▲───────┘
          │                  │                          │
          ▼                  ▼                          │
   ┌──────────────┐   ┌──────────────┐          ┌───────┴───────┐
   │  DISTILLER    │──▶│   LEDGER     │◀────────│   RETRIEVER   │
   │  (skill +     │   │ (confidence, │          │ (match, rank, │
   │  anti-skill   │   │  usage, rot) │          │  gate, inject)│
   │  generation)  │   └──────┬───────┘          └───────▲───────┘
   └──────┬───────┘          │                          │
          ▼                  ▼                          │
   ┌──────────────┐   ┌──────────────┐                  │
   │  VALIDATOR    │──▶│ SKILL STORE  │──────────────────┘
   │ (empirical    │   │ (global +    │
   │  A/B gate)    │   │  project)    │
   └──────────────┘   └──────┬───────┘
                             │
                      ┌──────▼───────┐
                      │ MAINTAINER   │
                      │ (consolidate,│
                      │ compress,    │
                      │ audit, decay)│
                      └──────────────┘
```

Six subsystems: **Capture**, **Distiller**, **Validator**, **Store + Ledger**, **Retriever**, **Maintainer**. Each is described below after the data model.

---

## 3. Plugin layout (the engine)

```
skillforge/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── distilling-skills/SKILL.md      # teaches Claude the distillation procedure
│   ├── distilling-failures/SKILL.md    # teaches anti-skill extraction
│   └── skillforge-usage/SKILL.md       # teaches Claude how to apply/report on skills
├── commands/
│   ├── learn.md            # /skillforge:learn   — distill current session (success path)
│   ├── learn-failure.md    # /skillforge:learn-failure — distill a gotcha/anti-skill
│   ├── find.md             # /skillforge:find    — search the library (cold-tier pull path)
│   ├── consolidate.md      # /skillforge:consolidate — dedup, merge, generalize
│   ├── audit.md            # /skillforge:audit   — review low-confidence & stale skills
│   ├── review.md           # /skillforge:review  — approve/reject quarantined pulled skills
│   └── stats.md            # /skillforge:stats   — library health dashboard
├── hooks/
│   └── hooks.json          # Stop, UserPromptSubmit, PostToolUse wiring
├── scripts/
│   ├── retrieve.py         # keyword+embedding matcher used by UserPromptSubmit hook
│   ├── symptoms.py         # PostToolUse symptom matcher (anti-skill fast path, Section 8.1)
│   ├── ledger.py           # read/update confidence ledger
│   ├── trust.py            # local trust registry ops + pull quarantine check (Section 11)
│   ├── secscan.py          # blocking secret scan used by the distiller and write path
│   ├── capture_check.py    # Stop-hook heuristic: "was this session skill-worthy?"
│   └── outcome.py          # PostToolUse outcome recorder
└── README.md
```

Notes on the engine:

The three engine skills are how the plugin programs the model itself. `distilling-skills` is the distillation prompt as a native, auto-triggering skill; improving it (Section 10, meta-loop) improves everything downstream. Scripts are plain Python with no server process — hooks shell out to them. This keeps v0.x fully local and serverless; the optional MCP backend (Section 12) slots in behind `retrieve.py` and `ledger.py` later without changing anything above them.

---

## 4. Knowledge store (the data)

Learned knowledge lives outside the plugin, split by scope:

```
~/.claude/skillforge/                      # GLOBAL scope (follows the user)
├── skills/
│   └── stripe-webhook-integration/
│       └── SKILL.md
├── antiskills/
│   └── bodyparser-breaks-stripe-sig/
│       └── SKILL.md
├── ledger.db                              # SQLite event ledger + derived aggregates (9.2), all scopes
├── embeddings.db                          # sqlite-vec index over descriptions
├── symptoms.json                          # compiled anti-skill symptom patterns (8.1)
├── verifications.json                     # compiled verification-command patterns (9.1)
├── trust.json                             # local trust registry: skill id → approved hash (11.2); NEVER committed
├── hot/                                   # materialized SKILL.md copies for the hot tier (8)
└── archive/                               # deprecated skills (never delete, demote)

<repo>/.claude/skillforge/                 # PROJECT scope (follows the repo, in git)
├── skills/
├── antiskills/
└── manifest.json                          # provenance snapshot (see 4.3)
```

Project-scoped skills ride along in git, so teammates inherit them by pulling — team distribution with zero infrastructure. Distribution is zero-infrastructure; *trust is not* — a pulled skill is untrusted content until locally reviewed, regardless of what status its frontmatter claims (Section 11). Global skills capture stack-level and personal knowledge. The distiller decides scope at save time (default heuristic: mentions repo-specific paths/conventions → project; otherwise global; user can override).

### 4.1 Skill format

```markdown
---
name: stripe-webhook-integration
kind: skill                    # skill | antiskill | preference
scope: global                  # global | project
description: >
  Set up a Stripe webhook endpoint with signature verification.
  Use when: adding Stripe webhooks, handling payment events.
  Do NOT use when: consuming webhooks from other providers, or
  when the project uses Stripe's official Next.js integration.
status: validated              # ledger-owned; stripped from committed (project-scope) files — see 11.2
preconditions:
  stack: [node, express]
  deps: { stripe: ">=14" }
provenance:
  repo: acme/storefront
  commit: abc1234
  distilled: 2026-07-07
  source_session: <session-id>
canonical_example: src/api/webhooks.ts@abc1234
---

## Procedure
1. Mount the webhook route BEFORE any body-parsing middleware...
2. ...

## Gotchas
- Signature verification requires the raw request body...

## Verification
- `stripe trigger payment_intent.succeeded` should return 200 and log the event.
```

Format rules: the `description` field always contains both positive triggers and explicit *do-NOT-use-when* cases (fights over-triggering). `Verification` is mandatory — a skill without a way to check success can't participate in outcome tracking — and is emitted twice: as prose for the model, and as a structured `verification.command` frontmatter field for machine matching (9.1). Frontmatter also carries `fingerprints`: 2–3 distinctive code fragments used for passive usage detection. Mutable state (`status`, confidence, anything ledger-derived) is ledger-owned: it is stripped from project-scoped files before commit, so routine maintenance never churns the content hash the trust registry reviews (11.2) — only genuine body/trigger changes do. `canonical_example` points at real code at a pinned commit; pointing beats paraphrasing (with a content-hash fallback for when the pin dangles).

### 4.2 Anti-skill format

Same frontmatter with `kind: antiskill`, but the body is inverted — it documents the trap, not a procedure:

```markdown
## Trap
Adding `express.json()` globally silently breaks Stripe signature
verification on the webhook route.

## Symptom
`StripeSignatureVerificationError` despite correct secret; wasted time
suspecting the webhook secret or clock skew.

## Cause
Signature is computed over the raw body; global JSON parsing consumes it.

## Fix
`express.raw({type: 'application/json'})` scoped to the webhook route only.

## Cost of rediscovery
~40 min (observed in source session)
```

Anti-skills are injected more aggressively than skills (they're short, and the downside of a miss is high), and the `Symptom` field doubles as a machine-matchable trigger — it powers the symptom-triggered fast path in Section 8.1. They're also cheaper to validate — the Trap/Symptom/Cause/Fix structure is checkable by inspection.

### 4.3 The ledger

`ledger.db` (SQLite) is the system's memory about its memory. Its source of truth is an *event table* — one row per injection, detection, holdout, or postmortem verdict (schema in 9.2) — from which per-skill aggregates are derived as views. The aggregate view per skill looks like:

```json
{
  "stripe-webhook-integration": {
    "confidence": 0.82,
    "uses": 7,
    "successes": 6,
    "failures": 1,
    "last_used": "2026-07-01",
    "last_validated": "2026-06-12",
    "failure_postmortems": [
      {"date": "2026-06-20", "verdict": "task_diverged", "note": "Deno runtime, precondition miss"}
    ],
    "tokens": 412,
    "injections": 11,
    "injection_to_use_ratio": 0.63
  }
}
```

`injection_to_use_ratio` (how often an injected skill was actually applied — measured by the detection pipeline in 9.1, not assumed) is the key relevance-density metric — a skill that keeps getting injected but never used is burning context and gets its triggers narrowed at audit time.

---

## 5. Capture subsystem

Two paths into the pipeline, one manual and one automatic:

**Manual:** `/skillforge:learn` at the end of a feature, or `/skillforge:learn-failure` after escaping a debugging pit. The command kicks off the distiller (Section 6) with the current session as source material. Manual capture ships in v0.1 and remains the ground truth path.

**Automatic (Stop hook):** when Claude finishes a response, `capture_check.py` runs a cheap heuristic over the session: Did the session involve multiple non-trivial tool-use cycles? Did tests go from failing to passing? Was there a long struggle followed by a fix (anti-skill signal)? Did the user issue a correction (preference signal)? If any fire AND retrieval finds no existing skill covering the work, the hook surfaces a one-line suggestion: *"This looks skill-worthy (webhook setup, ~14 turns). Run /skillforge:learn?"* — suggestion, never silent auto-save. Human-in-the-loop at capture is what keeps garbage out cheaply; automation squeezes friction, not judgment.

A third capture channel, **preference capture**, watches for user corrections ("we don't use default exports", "test first"). These distill into `kind: preference` micro-skills — one to three lines each — that are injected as a compact block rather than individually. The block is subject to the same scarcity rules as everything else: preferences that go unreinforced (never re-observed, never violated-then-corrected) age out of the injected block at audit time, and a preference the user contradicts is evicted immediately — a monotonically growing preference block would violate the token-scarcity principle from the inside.

---

## 6. Distiller

Input: session transcript (or user summary) + capture type. Output: a candidate skill file. The procedure lives in the `distilling-skills` engine skill so it auto-triggers when the `/learn` commands run.

The distillation contract:

1. **Generalize** — strip project-specific incidentals unless scope is project; the test is "would a fresh Claude instance in a different repo benefit?"
2. **Answer the one-shot question** — "what would I tell a fresh instance of myself so it could do this in one pass?" Procedure, gotchas, verification.
3. **Self-gate on novelty** — explicitly ask: *would a fresh Claude actually not know this?* If the skill restates model-obvious knowledge, abort the save. This single check kills roughly half of junk saves for free.
4. **Write negative triggers** — the do-NOT-use-when cases are mandatory frontmatter.
5. **Duplicate check** — embed the candidate description, query nearest neighbors in `embeddings.db`. Close match → propose update/merge of the existing skill instead of inserting a sibling.
6. **Assign scope and provenance**, snapshot relevant dependency versions into `preconditions`.
7. **Secret scan (mandatory, blocking)** — the source material is a session transcript, which routinely contains API keys, tokens, connection strings, and proprietary code. Before any save, run pattern-based secret detection (gitleaks-style rules) over the candidate skill *and* its provenance fields; project-scoped saves get a second pass since they are headed for git. Hits block the save and surface the offending lines for redaction. See Section 11.
8. **Emit attribution artifacts** — `fingerprints` (distinctive, not generic; the Fix section for anti-skills) and a structured `verification.command`. These power the usage-detection pipeline (9.1); a skill without them is invisible to outcome tracking.
9. **Symptom specificity lint (anti-skills)** — reject `Symptom` patterns below a minimum specificity (no bare `Error`, no single common token); an over-broad symptom would fire the 8.1 fast path on every session. The lint checks the pattern against a corpus of generic tool output and blocks save on high match rates.

New skills enter as `status: candidate` with `confidence: 0.5`. They are injected only with a hedge ("candidate skill, verify before trusting") until validated.

---

## 7. Validator (empirical gate)

Candidates are promoted to `validated` by evidence, not by existing. Two tiers:

At single-user volume, one bad skill costs more than ten missed measurements — so the rigor lives here, at the source, rather than in downstream statistics.

**Tier A — adversarial gate (cheap, always runs):** a fresh-context subagent reads *only the skill text* — no session context — and the gate has two modes:

- **Executable mode (preferred):** the subagent must actually follow the skill in a scratch worktree and run its `verification.command`. "Can a fresh instance follow this?" answered empirically, per candidate, decorrelated by construction. This attacks the failure mode that actually hurts at this scale: confidently-written skills that don't work.
- **Critique mode (fallback, recorded):** many verifications aren't hermetically runnable (`stripe trigger` needs CLI + keys; some verifications need the surrounding project). Where execution is impossible, the subagent critiques instead: is the procedure followable without the source session in mind? Are preconditions complete? Is the verification actually checkable? The fallback is *recorded* — it is a weaker pass, and the bucket cap below makes that consequential.

**Bucket cap and organic lift:** a skill reaches the `trusted` bucket (and hot-tier eligibility) only when **critique-mode Tier A has passed AND (executable Tier A has passed OR k≥2 real-session verification successes have accrued via the 9.1 verification layer)**. The two halves test different properties: execution/organic successes test *validity* (the procedure works), while the fresh-context critique tests *legibility* (a fresh session can follow it — the model that succeeded organically had full session context, so legibility goes otherwise untested). Organic evidence substitutes for the sandbox — real sessions have the environment the sandbox lacks — but nothing substitutes for the fresh-context read. Until the cap lifts, a working skill sits at `working`: injected normally, just not granted standing context.

**Tier B — A/B trial (expensive, strictly on-demand):** an instrument for skills you're suspicious of, not a default gate — staged rollout (candidate → hedged injection → real deterministic outcomes) is the primary per-skill instrument, uses real tasks, and is already built. When Tier B does run: task specs come from *replayed real prompts* that later matched the skill's triggers (the retrieval log already holds them — decorrelated from the skill's authoring session by construction; a distiller-written sibling task is correlated homework grading itself), k≥3 paired runs per arm, scored on verification success — never turns-to-completion, which is high-variance and gameable. Tier B results write `last_validated`, which the staleness auditor uses.

Practical stance: v0.2 ships Tier A (both modes); Tier B arrives when there's something specific to be suspicious of.

---

## 8. Retriever & delivery tiers

A skill's trigger can live in three places, and only one of them costs context. Native skill descriptions sit in the model's context on every prompt (~50 tokens each, forever) — that is the price of mid-task self-selection, and it must be *earned*, not granted by default. Naively materializing every learned skill as a native SKILL.md makes the standing overhead O(library size): at 300 skills that's ~15k tokens per prompt before the retriever injects anything, and it also creates a double-fire path (native load + hook injection of the same skill). Delivery is therefore tiered, with each skill living in exactly **one** tier:

**HOT — native descriptions, fixed budget.** A hard token allowance for native SKILL.md descriptions (default **1,500 tokens total**, roughly 25–30 skills). Only skills in this tier are materialized where Claude Code loads them. Hot delivery buys the one thing no other mechanism replicates: mid-task recall — fifteen turns into "build the checkout flow," the model hits a Stripe webhook and self-selects the skill even though no prompt ever said "Stripe." Hot-tier eligibility requires the `trusted` bucket (Section 7's cap rule); eligible skills compete for slots on `confidence × recent usage`, and the Maintainer promotes and evicts at audit time (Section 10). Mechanically, `hot/` is not itself scanned by Claude Code — promotion write-throughs the SKILL.md into a directory Claude Code actually loads (`~/.claude/skills/skillforge-hot/<name>/`), and eviction removes it; `hot/` is the system's record of what's currently materialized. The budget is a constant chosen once, so the fixed cost is flat *by construction* — library growth becomes eviction pressure, not context pressure.

**WARM — retriever index only.** Everything `validated` but not hot lives solely in the retrieval index. Zero standing cost; descriptions exist only on disk and spend tokens only when a match fires. Retrieval is **BM25-only in v0.2** — hybrid BM25+embedding retrieval requires embedding the query inside a blocking hook, and with no daemon a transformer embedder cold-loads in seconds, not the <200ms budget (an API call breaks fully-local). BM25 over short, keyword-dense descriptions is adequate under ~100 skills; the upgrade path is **static embeddings** (model2vec-class: tens-of-ms load, no daemon) when the library outgrows keywords, and a persistent process only at the MCP tier where a server exists anyway. On each user prompt, `retrieve.py` runs the match and applies the gate:

```
score = match_quality × confidence × freshness
inject if score > threshold, subject to:
  - max 3 skills + matching anti-skills + preference block
  - hard token budget (default 1,200 tokens per prompt)
  - anti-skills exempt from the max-3 count cap but not the token budget
  - candidate-status skills injected with hedge wording
  - precondition check against current repo (deps, stack) — mismatch → skip & flag stale
  - session dedupe: a skill already injected this session is not re-injected
  - ε-holdout: ~5% of would-be injections of history-rich skills are
    silently withheld and logged (9.1); never anti-skills or candidates
```

Warm delivery's blind spot is the mid-task case — the prompt said "checkout flow," so the webhook skill never matched. That gap is covered from two sides: the hot tier (for proven skills) and symptom triggers (below).

**COLD — pull only.** Candidates, probation, and the long tail are reachable only through `/skillforge:find <topic>` and the distiller's duplicate check. A single ~80-token meta-entry in the `skillforge-usage` engine skill tells the model the library exists and when to search it. Pull as a *primary* path violates the push-over-pull principle — it depends on the model remembering to look — but as the fallback tier for low-confidence skills the failure mode is acceptable: a missed cold skill costs a rediscovery, not a proven win.

### 8.1 Symptom-triggered injection (anti-skill fast path)

Anti-skills carry their own trigger: the `Symptom` field is literally an error signature. The Maintainer compiles all anti-skill symptoms into a lightweight pattern index (`symptoms.json` — strings and regexes, no embeddings, no LLM). A PostToolUse hook greps tool output (stderr, test failures) against it and injects the matching anti-skill the moment `StripeSignatureVerificationError` appears in a test run.

This is push keyed off the *actual* mid-task signal rather than the model noticing, and it costs tokens only on a hit. Since anti-skills are the highest-value-per-token asset in the store, symptom triggering is their primary delivery channel — the trap announces itself, and the system answers it. Prompt-time retrieval remains a secondary channel for anti-skills whose symptoms are behavioral rather than textual.

Every injection, from any tier or trigger, is logged to the ledger (feeding `injection_to_use_ratio`).

---

## 9. Outcome tracking & confidence

Confidence is only as good as the usage and outcome signals feeding it, and "the model was told about a skill" is not "the model used the skill." Section 9.1 defines how usage and outcomes are actually detected; 9.2 defines the event substrate they land in; 9.3 bounds what all of it costs. The design rule throughout: no single signal is trusted — each layer audits the one above it — and bookkeeping is done by scripts, not context.

### 9.1 Usage detection & attribution pipeline

**At distill time**, every skill ships with its own detection artifacts:

- **Fingerprints** — 2–3 distinctive code fragments from the procedure (`express.raw({type: 'application/json'})` qualifies; `npm install` does not). For anti-skills, fingerprint the *Fix* section — "using" an anti-skill means the Fix lands in the code. Fingerprints are stored and matched as **normalized token patterns through the same tokenizer as `verifications.json`** (whitespace/quote normalization, token-sequence matching) — raw-string grep silently undercounts on formatting differences, and an undercounted `injection_to_use_ratio` narrows a good skill's triggers as punishment for a matching bug.
- **Structured verification** — a `verification.command` frontmatter field the distiller emits directly (never parsed out of markdown prose). The Maintainer compiles all of these into `verifications.json` as normalized token patterns — same machinery as `symptoms.json` — so `npx stripe trigger ...` or an added flag still matches.

**At injection time**, before the skill enters context, the retriever does two things:

- **Holdout roll (ε ≈ 5%)** — for skills with sufficient ledger history, silently withhold the injection and log a holdout event. Never applied to anti-skills (asymmetric downside) or candidates (no history to protect). Holdouts answer *library-level* questions — what fraction of skills are model-obvious — and calibrate the distiller's novelty gate with data instead of introspection; at personal-use volume they rarely reach significance on any single skill (Tier B remains the per-skill instrument). Holdouts silently degrade the session they run in, so the mechanism is user-visible, toggleable, and holdout events are queryable — "why didn't my skill fire" must be answerable.
- **Fingerprint snapshot** — one scoped grep of the repo for the injected skill's fingerprints, recording `preexisting: true/false` per pattern. Absent-at-injection → present-in-diff is far stronger causal evidence than a Stop-time grep alone (though still not proof on its own; snapshot + holdout triangulate).

**During the session**, three passive detectors run:

- **Marker layer** — the `skillforge-usage` engine skill instructs the model to append `{skill, action, ts}` to a session scratch file (`.claude/skillforge/session-usage.jsonl`) when it applies an injected skill. Explicit intent, durable across context compaction, PostToolUse-timestamped — and expected to be imperfect: models forget the protocol and sometimes mark performatively. That is what the layers below are for. A compliance reminder fires only on detected drift (injections N+ turns old with zero scratch writes), not per turn.
- **Verification layer** — the PostToolUse hook matches Bash calls against `verifications.json`. A hit is the strongest single event in the system: it proves usage, captures the outcome (exit status, output), and attributes correctly when multiple skills were injected — each skill's verification is its own.
- **Symptom layer** — the same hook keeps matching `symptoms.json`, which gives anti-skills their inverted usage semantics: symptom fires → anti-skill injected (8.1); the *same* symptom re-fires within the trap scope (same file/route, within N turns) → the anti-skill failed to get the model out of the trap — the crispest failure signal in the system, and free. Escape with no re-fire → success. A symptom firing fresh in a *different* location later is a new trap and a successful re-trigger, not a failure. Note the accepted asymmetry: since anti-skills are never held out, their *preventive* value (prompt-time injection, trap never approached) is estimated, not measured; their measured value comes from rescues.

**At Stop time**, the reconciler cross-checks all signals per injected skill: grep the session diff for fingerprints, then apply the truth table — marker + fingerprint/verification agree → clean usage event; fingerprint present with no marker → count as used, log a *compliance miss* (meta-loop input: the usage protocol is drifting, the skill is fine); marker present with no fingerprint and no verification → discount as likely performative. For holdouts: fingerprint appeared despite no injection → a *model-obvious* event, accumulated across the library to calibrate the novelty gate (distillation contract step 3) empirically.

**On failure only**, a gated judge (cheap model, own context) runs — never on the happy path. Preconditions: skills were injected this session AND a failure signal fired (tests regressed, verification failed, user corrected). It reads the injected skills plus the session diff and outputs one postmortem verdict as strict JSON: `skill_misleading` (full penalty, flag for revision), `task_diverged` (zero skill penalty — the charge lands on the retriever's account as trigger-narrowing pressure; the skill was right for a task it shouldn't have been matched to), or `skill_needs_update` (freeze injection, queue for distiller revision). To close the laundering path — a genuinely misleading skill the judge repeatedly misclassifies as diverged never degrading — N `task_diverged` verdicts on the same skill *with usage events attached* escalates it to the manual audit queue: no penalty, no infinite free passes. Two constraints:

- **Credit assignment precedes the judge:** only skills with a usage event (marker, fingerprint, or verification) are penalizable. An injected-but-unused skill that coincided with a failure teaches you about the retriever, not the skill — its event feeds retrieval stats, its ledger is untouched.
- **The judge is audited, not trusted:** periodically re-run it on sessions where the mechanical signals were unambiguous and score agreement. This is a tripwire, not a certification — the unambiguous sessions are by construction the easy cases — but a judge that fails even those has no business writing verdicts.

### 9.2 Event ledger

The substrate for all of the above is an event table, not aggregates — one row per injection, detection, holdout, or verdict:

```
{skill, session, turn, tier, trigger, detection: marker|verification|fingerprint|judge|holdout,
 preexisting_fingerprint, outcome, ts}
```

Aggregates (confidence, `injection_to_use_ratio`, compliance-miss rate, model-obvious rate) are derived views over events. This ordering is load-bearing: aggregates can always be derived from events; events can never be reconstructed from aggregates — and questions like "how often does the marker disagree with the fingerprint" are exactly the meta-loop inputs an aggregate-only schema cannot answer. The ledger lives in SQLite (`ledger.db`, alongside the sqlite-vec index), which also eliminates the concurrent-hook write races a flat JSON file invites.

### 9.3 Cost budget

Nearly the entire pipeline is scripts, not context. Zero context tokens: snapshot greps, symptom/verification matching, Stop reconciliation, all event writes. Holdouts are *negative* tokens. The context costs: ~100–150 tokens of marker protocol in the `skillforge-usage` engine skill (paid once, hot tier), ~40–60 tokens per marker write (skills are applied 1–3 times in sessions that use them at all → ~100–200 tokens per skill-using session, ~1–2% overhead on the 1,200-token injection budget, zero in sessions with no injections), and a ~30-token drift reminder that should be rare by construction. The judge runs in its own context (never the user's), on failure sessions only — dollar cost, not context cost, and small. The budget that actually needs enforcing is **hook latency**, since UserPromptSubmit and PostToolUse block: <50ms added per PostToolUse, <200ms per UserPromptSubmit including retrieval; Stop-time reconciliation may be lazy — nothing downstream needs it synchronously. Greps are scoped (`git ls-files`, a handful of patterns per injected skill) and matching runs against the compiled indexes.

**Confidence update:** at personal scale (1.1), confidence is **three coarse buckets** — `unproven` (candidate, hedged injection), `working` (Tier A critique passed + no unresolved failures), `trusted` (the Section 7 cap rule satisfied) — driven by Tier A results, deterministic events, and manual audit, because per-skill event counts (5–15 lifetime injections) can't support anything finer without producing numbers that look like measurements and are noise. The full beta machinery — per-skill (α, β) from ledger successes/failures, gating on a lower confidence bound so 6-of-7 and 60-of-70 are treated as the different beliefs they are — activates at team volume; the event ledger records everything needed to switch it on retroactively. Invariants at both scales: failure knocks down harder than success bumps up (asymmetry is deliberate; a misleading skill is worse than a missing one), and time decay — unused for 90 days drifts toward unknown, not toward dead; disuse is not disproof.

**Failure attribution** is the judge verdict from 9.1, recorded as an event; postmortems accumulate and drive audit priorities.

**Lifecycle by confidence:**

```
candidate (0.5) ──validated──▶ active (>0.6) ──▶ trusted (>0.85, injected proactively)
     │                             │
     └──── fails Tier A            ├─ falls below 0.4 ──▶ probation (hedged injection only)
              ▼                    └─ probation + more failures ──▶ deprecated → archive/
           rejected
```

Nothing is deleted; deprecated skills move to `archive/` with their ledger history intact, because a deprecated skill plus its postmortems is training data for the meta-loop.

---

## 10. Maintainer

Runs via `/skillforge:consolidate` and `/skillforge:audit` (manually or on a schedule):

**Consolidation** — nearest-neighbor scan over embeddings; near-duplicates are merged; sibling clusters ("add REST endpoint" / "add webhook endpoint" / "add GraphQL resolver") are *generalized*: extract the shared parent pattern, reduce children to deltas or fold them in entirely. Conflict detection runs here too — two skills matching the same triggers with contradictory advice force a resolution (merge, scope-split, or supersede) rather than silently coexisting.

**Compression** — skills with ≥5 successful uses get rewritten tighter by the distiller; proven skills need less explanation. Target: token count monotonically decreases with maturity. Two guards: a compressed skill is a *different artifact* inheriting trust the verbose version earned — compression can strip exactly the clause that handled the edge case — so every compression triggers a fresh Tier A pass and a bucket demotion (`trusted` → `working`) until re-earned. And in v0.x, **compression and consolidation do not touch project-scoped (committed) skills at all**: a body rewrite must churn the content hash — that's the trust gate working — but on a shared scope one teammate's `/consolidate` would flood everyone else's `/review` queue, and review fatigue turns the gate into theater. Global skills have an audience of one, so churn there is free; project-scope rewrites wait for the team tier's PR queue to absorb the review load.

**Staleness audit** — cross-check `preconditions` against current environments (a hook can watch package.json changes); mismatches freeze injection and queue revalidation. Also surfaces: low `injection_to_use_ratio` (narrow the triggers), confidence < 0.4 (revise or deprecate), `last_validated` older than N months for trusted skills (re-run Tier B).

**Hot-tier management** — at each audit, re-rank all validated skills by `confidence × recent usage` and refill the hot tier's fixed description budget (Section 8): winners get materialized as native SKILL.md files, evictees fall back to the warm index. Eviction is not demotion — a warm skill loses nothing but its standing context slot. The audit also recompiles `symptoms.json` from current anti-skills and `verifications.json` from current `verification.command` fields (both from trusted skills only, per Section 11).

**Meta-loop** — periodically feed the distiller its own track record: five skills that reached `trusted` and five that died, with postmortems, and ask it to revise the `distilling-skills` engine skill. The system learning how to learn is the highest-leverage loop in the design and costs almost nothing since the ledger already holds the data.

---

## 11. Security model

The system has two attack surfaces that ordinary skill libraries don't: it *writes* content distilled from private sessions, and it *injects* content pulled from repos directly into the model's context. Each needs its own boundary.

### 11.1 Outbound: secrets don't leave the session

Session transcripts routinely contain API keys, bearer tokens, connection strings, internal hostnames, and proprietary code — and the distiller's whole job is to copy things out of transcripts into files on disk, some of which get committed to git. The mitigations:

- **Blocking secret scan at distill time** (distillation contract step 7): gitleaks-style pattern rules over the full candidate skill, including frontmatter, `canonical_example`, and provenance. Hits block the save; the distiller surfaces the lines and re-drafts with redactions.
- **Project-scope double check:** anything destined for `<repo>/.claude/skillforge/` gets a second scan at write time, independent of the distiller — defense in depth against a distiller revision (meta-loop!) weakening step 7.
- **Provenance minimization:** provenance stores repo, commit, and session *id* — never transcript excerpts. The ledger and `manifest.json` are subject to the same rule; `manifest.json` is the only ledger-adjacent file that enters git.
- **Sharing scrub (v1.0):** global-scope skills still carry `provenance.repo` and `canonical_example` paths — internal repo names and file layout. Fine for personal use; before any library-sharing path ships, a scrub pass strips or generalizes these fields on export.

### 11.2 Inbound: pulled skills are payloads until proven otherwise

A skill file is, by design, instructions that get placed in the model's context. That means `git pull` on any repo with a `.claude/skillforge/` directory is a prompt-injection delivery channel: a malicious or compromised repo can ship "skills" that instruct the model to exfiltrate data, weaken code, or rewrite the library itself. Committed frontmatter (`status: trusted`, high confidence) is attacker-controlled and therefore meaningless.

The boundary is a **local trust registry** — `~/.claude/skillforge/trust.json`, never committed — mapping skill IDs to content hashes the local user has approved:

```
On retrieval (any tier, any trigger):
  hash(skill file) present in trust.json?
    yes → eligible for injection per its ledger status
    no  → QUARANTINED: never injected, never hot-tier
          materialized, never compiled into symptoms.json,
          excluded from /find results by default
```

Rules that fall out of this:

- **Self-distilled skills are auto-trusted** — the local user watched them get created; the distiller writes the hash to `trust.json` at save time.
- **Committed files carry content only.** `status`, confidence, and all ledger-derived state are stripped from project-scoped files before commit — mutable state lives in each user's local ledger. This is what keeps the gate socially sustainable: routine maintenance and outcome tracking never change committed hashes, so `/review` prompts fire only on genuine body or trigger changes.
- **Pulled skills arrive quarantined** regardless of committed status. `/skillforge:audit` (and a dedicated `/skillforge:review`) lists new arrivals with a diff-style view; approval is per-skill and records the hash. Committed status/confidence are treated as *advisory* — a reviewed skill starts locally as `candidate` with its own fresh ledger entry, earning trust through the same lifecycle as everything else.
- **Modification re-quarantines.** Any hash change on pull — even to a previously approved skill — drops it back to quarantine. A one-line edit to a trusted skill is exactly how an attacker would ride an established trust decision.
- **Trust is per-machine, not per-team.** Teammates each review independently in v0.x; the team tier (Section 12) moves review to a PR queue, but the local registry remains the final gate — server compromise must not equal context compromise.

### 11.3 Engine integrity

The hooks execute `scripts/*.py` from the *plugin*, never code from the knowledge store — learned skills are data to the engine, prose to the model, and executable to nothing. The meta-loop's revisions to `distilling-skills` are the one place learned content edits the engine; those revisions are versioned, diffed for review like a pulled skill, and metric-gated (Section 10). `symptoms.json` is compiled exclusively from trusted anti-skills so a quarantined file can't register regex triggers.

---

## 12. Optional MCP backend (team tier)

Everything above runs serverless. The MCP server enters only when the library outgrows local flat storage or becomes shared:

```
Tools:  search_skills, get_skill, save_skill, report_outcome, consolidate
Resource: skills://index
Storage: SQLite (+ sqlite-vec) locally → Postgres/pgvector for remote team server
```

Integration is a drop-in swap: `retrieve.py` and `ledger.py` call the server instead of local files; the server materializes project-scoped skills back into repos' `.claude/skillforge/` directories so native triggering keeps working. Team additions: new auto-distilled skills land as PRs against the shared library (review queue, not silent merge), per-user preference overrides, and usage analytics ("this skill saved ~2h across the team this month") to justify curation.

---

## 13. Build roadmap

**v0.1 — the loop exists (a weekend):** plugin scaffold, `/learn` + `/learn-failure` with the distillation engine skills, blocking secret scan on every save (security is not a later milestone — the first project-scoped skill ever committed must already be scanned), storage layout, skills written to global/project stores, native triggering only (the whole library fits inside the hot budget at this size). No hooks, no ledger.

**v0.2 — the loop closes (week 2–3):** delivery tiering (hot budget, warm retrieval index, `/find` for cold), UserPromptSubmit retrieval hook (BM25-only — see Section 8) with token budget and session dedupe, symptom-triggered anti-skill injection via PostToolUse, local trust registry with quarantine-on-pull and `/review`, SQLite event ledger + confidence updates, the usage-detection core (marker protocol, verification/fingerprint matching, injection-time snapshots — 9.1), Stop-hook capture suggestions, Tier A validation, `/stats`.

**v0.3 — the loop maintains itself:** `/consolidate` with generalization + conflict detection (global scope only until team tier), `/audit` with staleness checks, compression pass with Tier A re-pass + bucket demotion, static-embedding retrieval upgrade if the library has outgrown BM25, preference capture with eviction, failure-gated judge postmortems with credit assignment, ε-holdout sampling and judge calibration tripwire (9.1).

**v0.4 — the loop proves itself:** Tier B A/B validation in worktrees, meta-loop distiller revision.

**v1.0 — the loop scales:** MCP backend, team review queue, marketplace packaging.

## 14. Health metrics

Track from v0.2 onward, visible via `/stats`, with volume-gated numbers (1.1) visibly marked as placeholders rather than rendered alongside real measurements: library size by status and tier; quarantined skills awaiting review; confidence bucket distribution (median beta confidence at team scale, per 1.1); standing context cost (hot descriptions — capped by construction, so the metric to watch is hot-tier churn: healthy competition for slots, not thrash); injection tokens per prompt (should stay flat as the library grows — the ruthlessness metric); injection-to-use ratio (relevance density, now event-measured); marker compliance-miss rate (usage-protocol drift, meta-loop input); model-obvious rate from holdouts (novelty-gate calibration — team-scale, shown as a placeholder until volume per 1.1); symptom-trigger hit rate and re-fire rate (anti-skill fast-path value and failure signal); skill survival rate (candidates → trusted, the distiller quality metric); and estimated rediscovery time saved (sum of anti-skill `cost of rediscovery` × uses — the number that tells you whether any of this is worth it).

The mature system is not the one that knows the most. It is the one most ruthless about what it says, when.
