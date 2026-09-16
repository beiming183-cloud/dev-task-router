---
name: prepare-local-execution
description: "Use when the next software Task should run in the same local ChatGPT conversation. Build the Task Context Pack, resolve the requested profile, enforce stale-context and exact-mode-switch gates, and do not dispatch until the actual profile is verified."
---

# Prepare Local Same-Conversation Execution

Follow `../index/SKILL.md` first.

## Purpose

Turn the next unresolved Task into a safe local execution envelope without changing conversations.

```text
Task Ready
  ↓
Task Context Pack
  ↓
Difficulty
  ↓
requested profile
  ↓
execution gate
  ↓
current canonical conversation
```

This Skill prepares and gates execution. It must not claim the coding Task has run merely because the gate is open.

## Hard gates

A model Task must not enter the current conversation when any of these is true:

```text
STALE_CONTEXT
ROUTE_UNRESOLVED
MODE_SWITCH_UNAVAILABLE
MODE_SWITCH
PROFILE_MISMATCH
```

For non-NONE Tasks, require all of:

1. rolling context belongs to the current project;
2. commit-sensitive context is not stale;
3. surface route resolves to a concrete requested profile;
4. local exact switch returns `verified: true`;
5. actual family/effort match requested family/effort.

Only then may a conversation backend receive the Task.

## Deterministic Tasks

`NONE` is not a cheap chat mode. It means no reasoning model is needed.

A genuine deterministic build/test/formatter command should stay out of the ChatGPT conversation and run through the deterministic executor.

A Task named `test` that still contains an analysis/implementation prompt is not automatically NONE.

## Retry safety

Preparation and mode switching are infrastructure steps. They must not increment the Task attempt counter.

Therefore failures such as:

- UI selector changed;
- ChatGPT window unavailable;
- requested profile could not be verified;
- stale repository context;
- route configuration missing;

must not consume a model retry or trigger `LOW → MEDIUM → HIGH`.

Only a genuine reasoning/implementation/check/review failure after dispatch can provide evidence for Difficulty promotion.

## Dispatch truthfulness

Opening the execution gate means only:

```text
context valid
+
requested profile resolved
+
actual profile verified
```

It does **not** mean:

```text
Task executed
code changed
tests passed
Task completed
```

Those require actual conversation execution plus objective Checker/Reviewer/Git evidence.

## Current CLI contract

Preparation without touching ChatGPT UI:

```text
autodev-local prepare --json
```

Inspect the gate without a real switch:

```text
autodev-local gate --dry-run --json
```

After local UIA calibration, attempt the real switch gate:

```text
autodev-local gate --switch --json
```

The actual conversation-send backend is a separate V0.8 step and must not be fabricated before it is implemented and verified.

## Output

Report:

```text
Task
Difficulty
Context Pack
Requested profile
Actual profile (when available)
Switch verified
Allowed to dispatch
Blocker
Message
```
