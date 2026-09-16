---
name: create-handoff
description: "Use when a development task is about to move to another model, reasoning tier, conversation, or execution step and the user wants a compact handoff that preserves only the context needed to continue, including verified repository evidence when available."
---

# Create Development Handoff

Follow `../index/SKILL.md` first.

## Goal

Create the smallest reliable handoff for the next task or model. Do not replay the full conversation or dump the full repository.

## Include

- project and current stage/step/task;
- current task difficulty and selected model profile;
- why that profile was chosen;
- repository / branch / commit anchor when repository evidence exists;
- PR number and current CI/check state when relevant;
- only the relevant files/modules/symbols/tests needed by the next task;
- compact verified repository facts;
- if the task was promoted after failure, the previous tier and verified failure reason;
- constraints that must not change;
- latest verified test/build/diff evidence;
- acceptance criteria;
- unresolved blocker or open question;
- exact next action.

## Freshness rule

Treat a commit SHA as the evidence anchor. If the next task discovers that the branch head moved, refresh GitHub evidence before relying on old diff/CI/scope conclusions.

A user requirement is a desired target, not proof of current repository behavior. Keep current facts and desired changes separate.

## Context budget

Prefer no more than:

- 12 relevant files/tests;
- 8 verified facts;
- the CI checks that materially affect the task;
- one concise failure summary per relevant failed attempt.

Expand only when the architecture truly requires more context.

## Output format

```md
# Handoff

Project: ...
Stage / Step / Task: ...
Difficulty: ...
Route: ...
Classification reason: ...
Repository: owner/repo
Branch: ...
Commit: ...
PR: none | ...
CI: unknown | pending | success | failure | cancelled

## Verified state
- ...

## Relevant repository context
- path/to/file: why it matters
- path/to/test: what it verifies

## Preserve
- ...

## Acceptance
- ...

## Failure evidence
- none | ...

## Next action
...
```

Keep the handoff factual. Do not invent completed work, test results, commits, files, CI status, or model switches.
