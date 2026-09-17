
## Background

SkillForge validates a saved skill in two independent modes. A *critique* pass
judges the text alone and asks whether a fresh instance could follow it. An
*executable* pass is a separate question entirely: it builds a throwaway
worktree, runs the skill's own declared verification command before and after a
model turn, and reports whether the command's exit status changed.

Both verdicts are keyed by the content hash of the skill file, so editing a
skill voids whatever it had earned and the verdicts are re-earned together with
its trust entry. They are stored in the ledger's `validations` table alongside
the detail the mode produced, which is what the library viewer renders when a
reader asks why a skill is capped.

Promotion reads those verdicts through a truth table rather than directly. A
skill reaches the `trusted` bucket only when several independent conjuncts hold
at once, and the bucket is recomputed on every sync rather than stored, so a
skill can move in either direction as evidence accumulates or ages out. The
hot tier draws from that bucket under a token budget; the warm tier retrieves
on relevance and does not require the same standing.

None of the above changes what this skill instructs, and nothing in this
section is a step to perform. It is included so that the surrounding
architecture is legible to a reader encountering the file on its own.
