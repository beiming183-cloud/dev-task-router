---
name: dev-task-router-index
description: "Shared rules for the 项目拆解器 plugin. Use with the other Dev Task Router skills to decompose software work, classify difficulty, choose surface-specific model routes, define verification, and create compact handoffs."
---

# 项目拆解器 — Shared Rules

## Purpose

Turn a software-development goal into a small, explicit workflow where each task is classified by engineering difficulty first, then mapped onto the models available in the current execution surface.

The primary principle is **difficulty-first, surface-second routing**:

```text
task content
    ↓
NONE / LOW / MEDIUM / HIGH
    ↓
chat / codex / work / other
    ↓
surface-specific model + effort
```

Do not deliberately start every task on a weak model. The first attempt should use the tier predicted from the task itself.

## Difficulty is not a model name

`LOW`, `MEDIUM`, and `HIGH` describe the task.

They do not mean:
- cheapest / medium-price / expensive;
- Lunar / Terra / Sol / Astra;
- a specific provider;
- a fixed reasoning effort across all products.

Concrete model selection happens after difficulty classification.

## Difficulty rubric

### NONE

Use when no reasoning model is needed and the step is deterministic:

- run known tests;
- run a formatter or linter;
- run a build;
- collect an existing artifact;
- inspect an already-produced exit code.

If a NONE step fails, create a debugging/analysis task and classify that new task separately.

### LOW

Localized, mechanical, low-risk work with clear instructions and little architectural reasoning:

- locate files or symbols;
- rename a small identifier;
- update documentation;
- change a label/string/config value;
- add a straightforward test following an existing pattern;
- create a handoff from already-known facts.

### MEDIUM

Ordinary implementation/debugging that requires code understanding but has bounded impact:

- implement a normal feature in an established architecture;
- fix a conventional bug;
- modify related files with clear interfaces;
- refactor a local module while preserving behavior;
- add non-trivial tests for an existing subsystem.

### HIGH

Tasks where mistakes have broad consequences or architecture/ambiguity dominate:

- architecture design/review;
- core state semantics;
- cross-module state changes;
- concurrency, persistence, transactions;
- security/auth, migration, billing, release, data-loss risk;
- compatibility-sensitive changes;
- difficult regressions with unclear causes;
- final review of a high-risk change.

## Classification factors

Consider:

1. blast radius;
2. architectural coupling;
3. ambiguity/design burden;
4. statefulness and lifecycle complexity;
5. reversibility;
6. verification cost;
7. cross-module/public-interface impact;
8. domain risk.

File count is only a signal. A one-line change can still be HIGH.

## Surface mapping

Use the `route-model` skill after classification.

Current project configuration may expose:

```text
chat:
  LOW    → 5.6 Sol Low
  MEDIUM → 5.6 Sol Medium
  HIGH   → 5.6 Sol High

codex/work:
  families: lunar / terra / sol / astra
  efforts:  low / medium / high
```

Do not invent a strength ordering between Codex/Work families when the user has not configured one.

## Failure reclassification

A genuine reasoning/implementation failure is evidence that the first difficulty estimate may have been too low:

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry or BLOCKED
```

This is not weak-first routing: the first attempt still uses the best predicted tier.

Do not promote when the failure is clearly infrastructure-related, including:
- missing credentials;
- unavailable tools;
- permissions;
- network/DNS failures;
- rate limits/quota;
- service outage.

When promotion happens, record why: for example,
`previous MEDIUM attempt failed verification; complexity underestimated`.

## Decomposition rules

Prefer:

```text
Project
  └─ Stage
      └─ Step
          └─ Task
```

A Task should have:
- one coherent goal;
- enough context for one model invocation;
- a clear acceptance boundary;
- a coherent verification method.

Split when context, difficulty, verification, ownership, or handoff value changes. Do not split just to increase task count.

## Verification rules

For implementation tasks define objective evidence when possible:

- tests pass;
- build succeeds;
- expected artifact exists;
- expected Git diff exists;
- exact behavior is demonstrated;
- reviewer checks explicit acceptance criteria.

AI text such as “done” is not completion evidence.

## Handoff rules

A handoff should contain only what the next task needs:

- current goal;
- difficulty;
- current execution surface and resolved/unresolved route;
- relevant files/modules;
- constraints that must not change;
- verified facts;
- failure evidence, if any;
- acceptance criteria;
- next action.

Do not copy the full chat history into a handoff.
