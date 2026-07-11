---
description: Search the SkillForge library (cold-tier pull path)
argument-hint: "<topic>"
---

Search the SkillForge library for skills matching a topic.

1. Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve.py" --search "$ARGUMENTS"`
2. Present the hits as a short table: name, kind, tier, description.
3. Offer to show any hit in full; if the user asks, read the file at its
   listed path and display it.
4. No matches → say so, and if the knowledge ought to exist suggest
   /skillforge:learn to capture it.
