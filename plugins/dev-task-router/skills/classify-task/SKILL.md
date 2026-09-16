---
name: classify-task
description: "Use when the user wants to judge the true difficulty of one or more software-development tasks, assign NONE/LOW/MEDIUM/HIGH profiles, or review whether tasks were over- or under-routed. Use repository evidence when it can materially change the answer."
---

# Classify Task Difficulty

Follow `../index/SKILL.md` first.

## Goal

Classify the task from its engineering difficulty and risk **before** choosing a concrete model.

Keep these decisions separate:

```text
task content + verified repository evidence
  ↓
Difficulty = NONE / LOW / MEDIUM / HIGH
  ↓
route-model
  ↓
surface-specific model / effort
```

Do not interpret LOW/MEDIUM/HIGH as price tiers or as specific model families.

## Repository-aware classification

If the user names a repository, branch, PR, commit, file, or existing implementation and the real code can change the difficulty decision, use `inspect-repository` first.

Repository evidence can reveal that a task is broader or riskier than the wording suggests, for example:

- several affected files across multiple module roots;
- a public API or compatibility boundary;
- shared state/history/persistence ownership;
- auth/security/migration code;
- failing CI that changes a debugging task's uncertainty;
- related tests showing a wider regression surface.

Do not automatically raise difficulty just because a repository is large. Use only the **relevant** scope.

A commit SHA plus inspected relevant files should normally increase classification confidence. Missing or stale repository context should lower confidence when architecture matters.

## Signals

Judge from task intent plus verified scope. Consider:

- blast radius;
- architecture coupling;
- ambiguity and design burden;
- state/lifecycle complexity;
- concurrency, persistence, history, selection, transactions;
- reversibility;
- verification burden;
- cross-module or public-interface impact;
- security, auth, migration, billing, release, data-loss, or compatibility risk;
- relevant changed files and module roots;
- nearby tests and current CI evidence;
- whether the step is deterministic and needs no reasoning model.

File count is only a signal. A one-line change can still be HIGH when it changes core semantics.

## Anti-pattern: keyword-only routing

Do not classify solely because a task says "small change" or `kind: simple_edit`.

Example:

```text
"Change one auth flag used across modules while preserving backward compatibility"
```

may be HIGH even though the textual edit is small.

Likewise, do not classify a task as HIGH solely because a repository has many files. If inspection shows the requested work is isolated to one bounded file and an existing test, keep it LOW/MEDIUM as appropriate.

## Difficulty guidance

### NONE

Deterministic execution with no reasoning need: run a known test/build/formatter, collect an artifact, or inspect an already-produced result.

### LOW

Localized, mechanical, bounded work: docs, label/string change, straightforward rename, file/symbol lookup, handoff formatting, or a simple test that follows an established pattern.

### MEDIUM

Ordinary implementation/debugging in an established architecture with bounded impact: normal feature work, conventional bugs, local refactors, several related files with clear interfaces, non-trivial tests.

### HIGH

Architecture, core semantics, cross-module state, concurrency, persistence, migrations, security/auth, compatibility-sensitive changes, unclear regressions, or tasks where a wrong change can silently damage broad behavior.

## Confidence

Return `low`, `medium`, or `high`.

Confidence describes how clear the classification is, not how capable the target model is.

Use lower confidence when:
- important repository context is missing;
- the task description is ambiguous;
- the risk depends on unknown architecture;
- the classification sits near a LOW/MEDIUM or MEDIUM/HIGH boundary.

Use higher confidence when a current commit anchor, relevant implementation files, tests, and scope evidence all agree.

## Traits

Return compact traits such as:

```text
localized
coding
debugging
architecture
stateful
cross-module
broad-scope
high-risk
ambiguous
review
deterministic
commit-anchored
pr-context
tests-known
ci-success
ci-failure
```

Do not invent a trait when there is no evidence for it.

## Output

For each task return:

```text
Task: <name>
Difficulty: NONE | LOW | MEDIUM | HIGH
Reason: <concise engineering reason>
Traits: <comma-separated traits>
Confidence: low | medium | high
Repository anchor: <commit SHA or unavailable>
Relevant scope: <compact relevant files/modules>
Initial difficulty route: <same tier>
Failure difficulty route: <next tier or HIGH retry/BLOCKED>
```

Then, if the execution surface is known, call the `route-model` logic to map the classified difficulty to that surface.

Rules:

- `LOW` failure → reclassify next attempt to `MEDIUM`.
- `MEDIUM` failure → reclassify next attempt to `HIGH`.
- `HIGH` failure → stay `HIGH`; retry if another attempt is useful, otherwise `BLOCKED`.
- `NONE` command failure → create a separate debugging task and classify that task.

Do not promote when failure is clearly caused by infrastructure, permissions, rate limits, unavailable tools, missing credentials, or network issues.

When a failure causes promotion, explicitly say the original estimate was too low. Do not describe this as an intentional weak-first policy.
