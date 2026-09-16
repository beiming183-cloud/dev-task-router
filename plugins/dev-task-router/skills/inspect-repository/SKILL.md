---
name: inspect-repository
description: "Use when a development plan or difficulty decision depends on a GitHub repository, branch, commit, pull request, diff, tests, or CI. Gather a compact, commit-anchored evidence set before decomposition or routing."
---

# Inspect Repository Context

Follow `../index/SKILL.md` first.

## Goal

Turn GitHub into a source of verified engineering facts without dumping the whole repository into context.

Use this skill before `decompose-project` or `classify-task` when repository structure, current code, a PR, a diff, or CI can materially change the task plan or difficulty.

## Preferred evidence flow

```text
user goal
  ↓
identify repository + target branch/PR
  ↓
resolve current commit SHA
  ↓
search only for relevant symbols/files
  ↓
fetch candidate implementation + nearby tests
  ↓
read relevant PR/diff when one exists
  ↓
read CI/check status for the anchored commit
  ↓
produce compact Repository Evidence
```

## GitHub rules

When a connected GitHub tool is available:

1. Resolve the repository and target ref first.
2. Anchor evidence to a concrete commit SHA whenever possible.
3. Search using task-specific symbols, filenames, UI labels, error text, or subsystem names.
4. Fetch only the files that materially affect decomposition or verification.
5. When a PR is relevant, list changed filenames before fetching per-file patches. Read only relevant patches unless the whole diff is genuinely required.
6. Locate nearby tests or CI workflows that verify the affected behavior.
7. Read current CI/check status. Fetch detailed job logs only for failures that matter to the task.
8. If the branch head changes after evidence was collected, refresh scope-sensitive evidence instead of pretending the old snapshot is current.

If GitHub access is unavailable, say repository evidence is unavailable and continue only with clearly labeled unverified assumptions. Do not fabricate branch, commit, diff, test, or CI facts.

## Context budget

Default target:

- at most 12 relevant source/test files in the handoff;
- at most 8 verified facts;
- only failing CI details that affect the requested work;
- no full repository tree unless the task is specifically repository-wide.

Expand beyond these limits only when the architecture genuinely spans more scope.

## Evidence tags

Use evidence tags only when supported by inspected code/diff, for example:

```text
security
auth
migration
core-state
public-api
compatibility
persistence
concurrency
data-loss
```

These tags are stronger than guesses from filenames alone and can raise Difficulty even for a visually small change.

## Output

Return a compact YAML block:

```yaml
source: github
repository: owner/repo
branch: feature/example
commit: <sha>
pr_number: <number or null>
relevant_files:
  - path/to/implementation
changed_files:
  - path/from/relevant/diff
 test_files:
  - path/to/test
ci_status: unknown | pending | success | failure | cancelled
ci_checks:
  - <check name>
evidence_tags:
  - <verified risk/scope tag>
facts:
  - <short verified fact>
captured_at: <timestamp if available>
```

Use `changed_files` only for actual diff/PR evidence. Use `relevant_files` for files discovered as part of the affected subsystem.

## Source-of-truth rule

Repository evidence describes the current implementation state. User instructions describe desired behavior. If they conflict, do not overwrite one with the other: report the current repository fact, then preserve the user's requested target as the task goal.

Never use “AI says complete” as repository evidence. Prefer commit, diff, tests, build status, and CI checks.
