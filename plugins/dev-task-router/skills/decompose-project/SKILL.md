---
name: decompose-project
description: "Use when the user wants to break a software project or feature into stages, steps, and tasks, especially when different tasks should use different model tiers or reasoning effort. Use targeted repository evidence when available."
---

# Decompose Project

Before using this skill, follow the shared rules in `../index/SKILL.md`.

## Goal

Convert a broad development request into an executable plan where each Task is independently classifiable by engineering difficulty, backed by relevant repository facts when available, then mapped to the user's current execution surface.

## Workflow

1. Resolve the project goal and non-negotiable constraints.
2. If a real repository can materially change scope, use `inspect-repository` before finalizing the plan.
3. Anchor repository-aware decisions to a commit SHA whenever possible.
4. Identify the relevant implementation files, module boundaries, tests, current diff/PR, and CI checks without loading the whole repository.
5. Identify architecture-sensitive work before ordinary implementation.
6. Build `Project → Stage → Step → Task` only as deeply as useful.
7. Stop splitting when a Task has one coherent goal, one context boundary, one verification story, and can reasonably be owned by one model invocation.
8. Classify every Task as `NONE`, `LOW`, `MEDIUM`, or `HIGH` using `classify-task` with the relevant repository evidence.
9. Record a concise reason, confidence, traits, and relevant-file boundary.
10. Define objective verification using the real tests/build/checks when known.
11. Mark handoff boundaries where the next task would benefit from fresh context or a different model route.
12. If the current surface is known, map each difficulty using `route-model`.
13. Review the plan for waste: HIGH should not be used for mechanical work, and LOW should not be used for architecture-critical work.

## Repository scope rules

Do not turn repository inspection into a full-repo summarization task.

Normally carry forward only:

- repository / branch / commit;
- relevant implementation files;
- related tests;
- relevant changed files from an existing diff/PR;
- CI/check names that verify the task;
- compact verified facts;
- evidence tags that materially affect risk.

If repository evidence and the user's request disagree, keep both explicit: current code is the verified starting point, while the user request is the desired target.

## Do not over-split

Do not create separate tasks just because individual files differ.

Split when at least one of these changes:

- required context;
- difficulty tier;
- responsible model;
- verification method;
- architecture boundary;
- handoff value.

Keep tasks together when splitting would create artificial coordination overhead.

## Preferred sequencing

Do not force a fixed LOW → MEDIUM → HIGH order. Sequence work by engineering dependency.

A common pattern is:

```text
repo discovery        LOW
architecture analysis HIGH
normal implementation MEDIUM
core/semantic change  HIGH
mechanical cleanup    LOW
regression test run   NONE
test analysis         MEDIUM
final risk review     HIGH
handoff/docs          LOW
```

The actual sequence may differ. Dependency order is more important than alternating tiers.

## Surface-aware routing

Difficulty and concrete model selection are separate fields.

For example:

```text
Task difficulty: HIGH
Surface: chat
Surface route: 5.6 Sol High
```

but on Codex or Work:

```text
Task difficulty: HIGH
Surface: codex
Surface route: unresolved from configured pool
```

when the project has not configured which family/effort should serve HIGH.

Do not invent a Lunar/Terra/Sol/Astra ranking.

## Output

Start with a compact summary:

```text
Project: <name>
Goal: <goal>
Repository: <owner/repo or unavailable>
Anchor: <branch@commit or unavailable>
Surface: <chat/codex/work/other/unknown>
Stages: <count>
Tasks: <count>
Difficulty mix: NONE xN / LOW xN / MEDIUM xN / HIGH xN
```

Then provide a task table with these fields:

| Stage | Step | Task | Relevant scope | Difficulty | Confidence | Traits | Why | Verification | Surface route | Handoff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

After the table, provide a machine-friendly YAML block using this shape:

```yaml
project: <project-name>
repository:
  name: <owner/repo or null>
  branch: <branch or null>
  commit: <sha or null>
  pr_number: <number or null>
surface: <chat | codex | work | other | unknown>
stages:
  - id: <stage-id>
    title: <stage-title>
    steps:
      - id: <step-id>
        title: <step-title>
        tasks:
          - id: <task-id>
            title: <task-title>
            kind: <task-kind>
            level: LOW | MEDIUM | HIGH | NONE
            confidence: low | medium | high
            traits:
              - <trait>
            relevant_files:
              - <verified relevant path>
            reason: <one-line classification reason>
            max_attempts: <integer>
            escalate_after: 1
            acceptance:
              - <objective criterion tied to a real test/build/diff when known>
            surface_route:
              status: resolved | unresolved
              family: <family or null>
              effort: <effort or null>
            handoff: true | false
```

`escalate_after: 1` means a genuine model-execution failure is evidence that the original classification was too low, so the next attempt is promoted one tier. Infrastructure failures do not count as difficulty failures.

## Quality checks before finalizing

- Every HIGH task has a concrete architecture/risk/repository-scope reason.
- Every LOW task is actually localized and mechanically bounded.
- Deterministic test/build steps use NONE when no reasoning model is needed.
- Repository-sensitive decisions are anchored to current evidence, preferably a commit SHA.
- Relevant files are a targeted subset, not an indiscriminate repository dump.
- Acceptance criteria name observable checks; use real tests/build/CI when known.
- No Task depends on hidden conversation context if it is marked as a handoff boundary.
- Surface model selection never changes the underlying task difficulty.
- An unresolved Codex/Work model pool remains unresolved rather than guessing a family ranking.
