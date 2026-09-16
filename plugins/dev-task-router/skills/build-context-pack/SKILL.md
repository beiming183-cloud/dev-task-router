---
name: build-context-pack
description: "Use before executing the next task in a long-running project to compress the same conversation's rolling project state into a small task-specific context pack. Preserve decisions and constraints, include only relevant repository evidence, and detect stale commit-anchored context."
---

# Build a Task Context Pack

Follow `../index/SKILL.md` first.

## Purpose

Task decomposition must not become conversation decomposition. Keep the complex project in one canonical conversation whenever possible, but do not rely on unlimited chat history.

Maintain three layers:

```text
current conversation
+ rolling project context
+ task-specific repository evidence
```

The rolling context is a compact durable summary, not a transcript.

## Rolling project context

Keep only information that should survive across multiple tasks:

- project goal;
- architectural/product decisions that still apply;
- protected constraints that later tasks must not break;
- current-stage notes;
- task-specific notes that are still unresolved;
- the commit anchor used when commit-sensitive facts were recorded.

Deduplicate semantically identical entries. Do not append full assistant answers, full chat turns, or whole repository summaries.

## Task context pack

For one task, select only:

```text
Project / Stage / Step / Task
goal
applicable decisions
protected constraints
current stage notes
current task notes
acceptance criteria
recent failure evidence
commit-anchored relevant files/facts/CI
requested execution profile
exact next action
```

Prefer the most recent/applicable entries when a budget is exceeded. Older non-essential entries may be omitted, but protected constraints and still-valid architecture decisions should not be silently rewritten.

## Stale context

If rolling context is anchored to commit A but repository evidence is now anchored to commit B:

```text
stale_context: true
```

Refresh commit-sensitive facts before implementation. Do not treat an old decision as stale merely because the commit moved if it is explicitly a durable project decision; only repository-derived implementation facts require refresh.

## Same-conversation rule

The context pack is for keeping one long project conversation precise and recoverable. Do not open a new conversation merely because the next task uses a different reasoning effort.

Local exact mode switching should happen in the same conversation when available:

```text
Task difficulty
→ requested profile
→ local exact switch
→ verify actual profile
→ execute with this context pack
```

## Output

Return a compact pack with:

```text
Task Context Pack
Project goal
Decisions that still apply
Protected constraints
Stage context
Task-specific context
Acceptance
Recent failure evidence
Repository evidence
Requested execution profile
Exact next action
Stale-context warning (only when needed)
```

Do not copy the full conversation history into the pack.
