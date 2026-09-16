---
name: classify-task
description: "Use when the user wants to judge the true difficulty of one or more software-development tasks, assign NONE/LOW/MEDIUM/HIGH profiles, or review whether tasks were over- or under-routed."
---

# Classify Task Difficulty

Follow `../index/SKILL.md` first.

## Goal

Classify the task from its engineering difficulty and risk **before** choosing a concrete model.

Keep these two decisions separate:

```text
task content
  ↓
Difficulty = NONE / LOW / MEDIUM / HIGH
  ↓
route-model
  ↓
surface-specific model / effort
```

Do not interpret LOW/MEDIUM/HIGH as price tiers or as specific model families.

## Signals

Judge from the task itself. Consider:

- blast radius;
- architecture coupling;
- ambiguity and design burden;
- state/lifecycle complexity;
- concurrency, persistence, history, selection, transactions;
- reversibility;
- verification burden;
- cross-module or public-interface impact;
- security, auth, migration, billing, release, data-loss, or compatibility risk;
- whether the step is deterministic and needs no reasoning model.

File count is only a signal. A one-line change can still be HIGH when it changes core semantics.

## Anti-pattern: keyword-only routing

Do not classify solely because a task says "small change" or `kind: simple_edit`.

Example:

```text
"Change one auth flag used across modules while preserving backward compatibility"
```

may be HIGH even though the textual edit is small.

Use task intent and consequences, not the apparent number of edited lines.

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

## Traits

Also return compact traits that help the later surface router and handoff, such as:

```text
localized
coding
debugging
architecture
stateful
cross-module
high-risk
ambiguous
review
deterministic
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
