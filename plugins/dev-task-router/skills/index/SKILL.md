---
name: dev-task-router-index
description: "Shared rules for the 项目拆解器 plugin. Use with the other Dev Task Router skills to decompose software work, classify difficulty, choose model tiers, define verification, and create compact handoffs."
---

# 项目拆解器 — Shared Rules

## Purpose

Turn a software-development goal into a small, explicit workflow that uses different model tiers for different task difficulties.

The primary principle is **difficulty-first routing**:

```text
task difficulty
      ↓
NONE / LOW / MEDIUM / HIGH
      ↓
matching model profile
```

Do not deliberately start every task on a weak model. Classify first, then route directly to the matching tier.

If the assigned model fails the task, treat that failure as evidence that the original difficulty classification may have been too low. The next attempt should normally be reclassified upward by one tier:

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry or BLOCKED
```

This is not a weak-first strategy. The first attempt must still use the best tier predicted from the task itself.

## Difficulty rubric

### NONE

Use when no reasoning model is needed and the step is deterministic, for example:

- run tests;
- run a formatter or linter;
- run a build command;
- collect an existing artifact;
- inspect an already-produced exit code.

If a deterministic NONE step fails, do not pretend that rerunning the same command with a model fixes it. Create or route a separate debugging/analysis task whose difficulty is classified from the failure evidence.

### LOW

Use for localized, mechanical, low-risk work with clear instructions and little architectural reasoning, for example:

- locate files or symbols;
- rename a small identifier;
- update documentation;
- modify a simple string, label, or configuration value;
- add a straightforward test following an existing pattern;
- produce a handoff from already-known facts.

### MEDIUM

Use for ordinary implementation or debugging that requires code understanding but has a bounded impact, for example:

- implement a normal feature in an established architecture;
- fix a conventional bug;
- modify several related files with clear interfaces;
- refactor a local module while preserving behavior;
- add non-trivial tests for an existing subsystem.

### HIGH

Use for tasks where mistakes have wide consequences or where architecture and ambiguity dominate, for example:

- architecture design or architecture review;
- cross-module state changes;
- concurrency, persistence, security, migration, or compatibility-sensitive work;
- changes to core interaction semantics;
- difficult regressions with unclear causes;
- final review of a high-risk change.

## Classification factors

Judge difficulty from the task itself, not from token price. Consider:

1. blast radius — how many modules or behaviors can be affected;
2. architectural coupling — whether the task crosses important boundaries;
3. ambiguity — how much design work is still unresolved;
4. statefulness — whether history, persistence, selection, transactions, concurrency, or lifecycle behavior is involved;
5. reversibility — how easy it is to detect and undo a mistake;
6. verification cost — whether success is obvious or needs broad regression testing;
7. domain risk — security, data loss, migration, billing, auth, release, or other high-impact areas.

File count is only a signal. One-line changes can still be HIGH if they alter central semantics.

## Model-profile mapping

Prefer abstract profiles in plans:

- `NONE`
- `LOW`
- `MEDIUM`
- `HIGH`

If the user provides concrete models, map those profiles to the user's models. If not, keep the abstract profile names instead of inventing model availability.

When working inside ChatGPT, do not claim that this skill changed the active model unless the product explicitly performed that switch. A skill-only plugin can recommend the profile and prepare the next task/handoff; automatic model switching requires product support or a separate execution integration.

## Failure reclassification policy

Default behavior for model-executed tasks:

```text
initial classification → matching model tier
failure                → promote one tier
success                → keep the recorded classification
```

More specifically:

- `LOW` failure: reclassify the next attempt as `MEDIUM`.
- `MEDIUM` failure: reclassify the next attempt as `HIGH`.
- `HIGH` failure: remain `HIGH`; retry only when another attempt is useful, otherwise mark `BLOCKED`.
- `NONE` command failure: create a new debugging task and classify that debugging task separately.

Record why the reclassification happened, for example: `previous LOW attempt failed verification; complexity underestimated`.

A failure caused by infrastructure, permissions, missing credentials, rate limits, or unavailable tools is not evidence of task difficulty. In those cases, keep the difficulty unchanged and report the real blocker.

## Decomposition rules

Prefer this hierarchy:

```text
Project
  └─ Stage
      └─ Step
          └─ Task
```

A Task should be small enough that one model can understand its goal, relevant context, constraints, expected artifacts, and checks without replaying the full project history.

Separate these kinds of work when useful:

- repository discovery;
- architecture analysis;
- implementation;
- tests/builds;
- review;
- documentation/handoff.

Do not split work into tiny tasks solely to increase task count. Split when doing so changes the required context, model tier, verification, or ownership.

## Verification rules

For each implementation task, define at least one objective completion signal when possible:

- tests pass;
- build succeeds;
- expected file or artifact exists;
- expected Git diff exists;
- exact behavior is demonstrated;
- reviewer checks stated acceptance criteria.

AI text such as “done” is not completion evidence.

## Handoff rules

A handoff should contain only what the next task needs:

- current goal;
- task difficulty and selected profile;
- relevant files or modules;
- constraints that must not change;
- completed facts and latest verified state;
- acceptance criteria;
- unresolved issue, if any;
- next action.

Do not copy the full chat history into a handoff.
