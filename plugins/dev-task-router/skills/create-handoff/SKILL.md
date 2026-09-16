---
name: create-handoff
description: "Use when a development task is about to move to another model, reasoning tier, conversation, or execution step and the user wants a compact handoff that preserves only the context needed to continue."
---

# Create Development Handoff

Follow `../index/SKILL.md` first.

## Goal

Create the smallest reliable handoff for the next task or model. Do not replay the full conversation.

## Include

- project and current stage/step/task;
- current task difficulty and selected model profile;
- why that profile was chosen;
- if the task was promoted after failure, the previous tier and verified failure reason;
- relevant files/modules/symbols only;
- constraints that must not change;
- latest verified state, test/build/commit evidence when available;
- acceptance criteria;
- unresolved blocker or open question;
- exact next action.

## Output format

```md
# Handoff

Project: ...
Stage / Step / Task: ...
Difficulty: ...
Route: ...
Classification reason: ...

## Verified state
- ...

## Relevant context
- ...

## Preserve
- ...

## Acceptance
- ...

## Failure evidence
- none | ...

## Next action
...
```

Keep the handoff factual. Do not invent completed work, test results, commits, files, or model switches.
