---
name: dev-task-router-index
description: "Shared rules for the 项目拆解器 plugin. Use with the other Dev Task Router skills to inspect repository evidence, decompose software work, classify difficulty, route tasks, build compact rolling context packs, switch the local ChatGPT execution profile when available, verify results, and create compact handoffs."
---

# 项目拆解器 — Shared Rules

## Purpose

Turn a software-development goal into a small, explicit workflow where each Task is classified by engineering difficulty first, then mapped onto the current execution surface.

The primary principle is **difficulty-first, surface-second routing**:

```text
task content
    ↓
NONE / LOW / MEDIUM / HIGH
    ↓
chat / codex / work / other
    ↓
requested model + effort
```

Do not deliberately start every task on a weak model. The first attempt should use the tier predicted from the task itself.

## Canonical conversation rule

For a complex project, Task decomposition does **not** imply conversation decomposition.

Prefer the same canonical conversation for the whole project whenever the execution surface allows it:

```text
same canonical conversation
  ↓
Task A → LOW
  ↓ local exact switch
Task B → HIGH
  ↓ local exact switch
Task C → MEDIUM
```

Do not create separate LOW/MEDIUM/HIGH chats merely to obtain different reasoning tiers. The local Windows companion exists specifically to change the current conversation profile while preserving conversation continuity.

A route is only a **requested** profile. When local exact switching is used, execution should continue only after the matching **actual** profile is verified.

A single conversation is still not an infinite context window. Before a long-running task, use `build-context-pack` to combine rolling durable project state with only the task-specific repository evidence needed now. Do not replay the complete chat transcript.

## Rolling context rule

Keep durable information outside the transient chat window in `.autodev/context.yaml`:

- project goal;
- still-valid architecture/product decisions;
- protected constraints;
- current-stage notes;
- unresolved task-specific notes;
- the commit anchor for commit-sensitive facts.

The rolling context is a compact state summary, not a second chat log. Deduplicate repeated facts. Old repository-derived facts must be refreshed when their commit anchor is stale.

For the next Task, create a budgeted Task Context Pack containing only applicable decisions, constraints, stage/task notes, acceptance, recent failure evidence, relevant repository files/facts/CI, requested route, and exact next action.

## Repository evidence before guessing

When a real GitHub repository, branch, pull request, diff, or CI result can materially change the plan, use `inspect-repository` before final decomposition/classification.

Prefer this order:

```text
user goal
  ↓
repository + branch/PR
  ↓
commit-anchored relevant files/tests/diff/CI
  ↓
Task decomposition
  ↓
Difficulty
  ↓
Surface route
```

Repository facts and user goals are different things:

- GitHub evidence describes the current implementation state;
- the user request describes the desired target state.

Do not treat user prose as proof that code already behaves a certain way. Do not treat old branch evidence as current after the branch head changes.

Use targeted evidence, not a repository dump. A normal handoff should carry only the relevant files, tests, verified facts, commit anchor, and CI state needed by the next task.

## Difficulty is not a model name

`LOW`, `MEDIUM`, and `HIGH` describe the Task.

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
8. domain risk;
9. verified repository scope and module boundaries;
10. relevant test/CI evidence.

File count is only a signal. A one-line change can still be HIGH. A repository evidence tag such as `auth`, `core-state`, `migration`, `public-api`, or `compatibility` can reveal hidden risk that was not obvious from the user wording.

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

When a local Chat route is resolved and local exact switching is available, use `switch-local-mode` before executing the next model task.

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
- service outage;
- local UI selector not found;
- ChatGPT window unavailable;
- local mode switch could not be verified.

A local mode-switch failure should be recorded as `MODE_SWITCH` (or equivalent execution infrastructure evidence), not as proof that the Task needs a stronger model.

When genuine Task failure causes promotion, record why: for example,
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

When GitHub evidence exists, prefer acceptance criteria that name the relevant test/build/check or expected diff boundary rather than generic “tests pass”.

AI text such as “done” is not completion evidence.

When local exact mode switching is used, `verified: true` for the requested profile is a prerequisite for executing the next model task; it is not itself evidence that the coding task is complete.

## Handoff rules

A handoff should contain only what the next task needs:

- current goal;
- difficulty;
- current execution surface and resolved/unresolved route;
- requested/actual profile when local switching was used;
- repository / branch / commit anchor when available;
- relevant files/modules/tests;
- constraints that must not change;
- verified facts and current CI state;
- failure evidence, if any;
- acceptance criteria;
- next action.

Prefer a generated Task Context Pack over copying the full chat history. Do not copy the full chat history or full repository into a handoff.
