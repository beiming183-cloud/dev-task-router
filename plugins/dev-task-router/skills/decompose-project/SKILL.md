---
name: decompose-project
description: "Use when the user wants to break a software project or feature into stages, steps, and tasks, especially when different tasks should use different model tiers or reasoning effort. Produce a difficulty-routed execution plan with verification and handoff boundaries."
---

# Decompose Project

Before using this skill, follow the shared rules in `../index/SKILL.md`.

## Goal

Convert a broad development request into an executable plan where each task has the right difficulty tier from the start.

## Workflow

1. Resolve the project goal and non-negotiable constraints.
2. Use available repository/project context when it materially changes the plan. If critical context is missing, ask only for what blocks useful decomposition.
3. Identify architecture-sensitive work before ordinary implementation.
4. Build `Project → Stage → Step → Task` only as deeply as useful.
5. Classify every Task as `NONE`, `LOW`, `MEDIUM`, or `HIGH` using the shared rubric.
6. Give each Task a concise reason for its classification.
7. Define objective verification for implementation tasks.
8. Mark handoff boundaries where the next task would benefit from a fresh context or different model tier.
9. Review the plan for waste: HIGH should not be used for mechanical work, and LOW should not be used for architecture-critical work.

## Preferred sequencing

Do not force a fixed LOW → MEDIUM → HIGH order. Sequence work by engineering dependency.

A common pattern is:

```text
repo discovery        LOW
architecture analysis HIGH
normal implementation MEDIUM
core/semantic change  HIGH
mechanical cleanup    LOW
regression tests      NONE / MEDIUM
final risk review     HIGH
handoff/docs          LOW
```

The actual sequence may differ. Dependency order is more important than alternating tiers.

## Failure handling

Initial routing must come from the predicted task difficulty. If a model-executed task later fails for a genuine reasoning/implementation reason, treat that as evidence that the original classification was too low and promote the next attempt by one tier:

```text
LOW → MEDIUM → HIGH
```

Do not promote on infrastructure failures such as missing credentials, permissions, rate limits, unavailable tools, or network errors.

For a HIGH task, a genuine failure stays HIGH; retry only when useful, otherwise mark the task BLOCKED.

## Output

Start with a compact summary:

```text
Project: <name>
Goal: <goal>
Stages: <count>
Tasks: <count>
Model mix: NONE xN / LOW xN / MEDIUM xN / HIGH xN
```

Then provide a task table with these fields:

| Stage | Step | Task | Difficulty | Why | Verification | Handoff |
| --- | --- | --- | --- | --- | --- | --- |

After the table, provide a machine-friendly YAML block using this shape:

```yaml
project: <project-name>
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
            reason: <one-line classification reason>
            max_attempts: <1-3>
            escalate_after: 1
            acceptance:
              - <objective acceptance criterion>
            handoff: true | false
```

For model-executed tasks, normally set enough retry budget for upward reclassification: LOW can progress to MEDIUM/HIGH, MEDIUM can progress to HIGH, and HIGH can retry at HIGH. Keep deterministic NONE steps separate from model-based debugging tasks.

## Quality checks before finalizing

- Every HIGH task has a concrete architectural/risk reason.
- Every LOW task is actually localized and mechanically bounded.
- Deterministic test/build steps use NONE when no model reasoning is needed.
- No task depends on hidden conversation context if it is marked as a handoff boundary.
- Acceptance criteria describe observable outcomes, not “AI says complete”.
- Failure promotion reflects corrected difficulty classification, not a deliberate weak-first policy.
