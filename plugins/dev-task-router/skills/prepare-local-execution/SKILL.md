---
name: prepare-local-execution
description: "Use when software Tasks should run in the same local ChatGPT conversation. Build a bounded Task Context Pack, resolve and verify the requested profile, dispatch safely, resume response collection without duplicate sends, and require Checker evidence before PASS."
---

# Local Same-Conversation Execution

Follow `../index/SKILL.md` first.

## Purpose

Keep one canonical ChatGPT conversation while routing each Task at its real difficulty and carrying only the context that Task needs.

```text
Task Ready
  ↓
Task Context Pack
  ↓
Difficulty / requested profile
  ↓
verified actual-profile gate
  ↓
current canonical conversation
  ↓
response completion monitor
  ↓
Checker / Git evidence
  ↓
PASS or real failure evidence
```

Task decomposition must not become conversation decomposition.

## Hard gates before model dispatch

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

## Safe current-conversation dispatch

The Windows local sender is config-driven and must fail closed.

Require:

```text
current visible ChatGPT window
+ calibrated composer selector
+ full prompt write
+ full prompt read-back match
+ calibrated Send selector
+ duplicate-dispatch ledger clear
```

Do not use fixed screen coordinates. Do not switch to another chat. Do not claim Task completion merely because Send was clicked.

A sticky `submitting`/`submitted` dispatch record is safer than automatically sending the same Task twice after an ambiguous crash boundary.

## Response collection

Response collection is separately calibrated and disabled by default.

Use a compact baseline:

```text
assistant message count
+ SHA-256 of the latest assistant message
```

Do not persist the full old conversation as a baseline.

A response counts as complete only when a new assistant response is observed and remains unchanged for the configured confirmation polls while no calibrated busy indicator is active.

Response timeout, missing selectors, unreadable UI, or process interruption are infrastructure failures. They must not consume a model retry.

`resume` must resume an existing active dispatch only. If there is no active session, it must refuse to create a new send.

## Objective completion

Assistant prose is never sufficient PASS evidence.

```text
assistant says done ≠ PASS
message submitted ≠ PASS
response completed ≠ PASS
```

Only after a completed response may Checker/Git evidence decide the Task result.

For `require_diff`, preserve a compact pre-dispatch Git snapshot digest so a response can be resumed later without storing a giant diff snapshot in session state.

## Difficulty promotion

Infrastructure failures do not trigger promotion.

A completed model attempt that reaches objective Checker/DIFF verification and fails may provide genuine failure evidence:

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

The next model dispatch may therefore use the promoted profile.

## Deterministic NONE Tasks

`NONE` is not a cheap chat mode. It means no reasoning model is needed.

A genuine command Task may run locally and continue automatically when it passes:

```text
kind=test/build
+ known command
+ no reasoning prompt
```

If that deterministic command fails:

```text
NONE failure
→ DEBUG_TASK_REQUIRED
→ stop automatic loop
→ create a separate debug Task
→ classify that debug Task independently
```

Never turn the failing NONE command itself into LOW/MEDIUM/HIGH.

## Rolling context after PASS

After objective PASS, persist only deterministic verified facts such as:

```text
Verified PASS <task-id>
Checker verified
short dispatch id when applicable
```

Do not mine arbitrary assistant prose into durable project decisions or protected constraints.

Do not move `last_commit` merely because a local Task passed. A fresh repository evidence anchor is required before changing commit-sensitive context.

## Continuous project loop

Continuous mode may proceed through:

```text
PASSED
CHECK_FAILED → next promoted model attempt
successful deterministic NONE
```

Stop immediately on states such as:

```text
WAITING_RESPONSE
RECOVERY_REQUIRED
REVIEW_REQUIRED
DEBUG_TASK_REQUIRED
BLOCKED / FAILED
mode/context/UI infrastructure failure
```

Always enforce a finite `max_cycles` guard.

## CLI contract

Inspection only:

```text
autodev-local prepare --json
autodev-local gate --dry-run --json
autodev-local probe-conversation --json
```

After real Windows UIA calibration:

```text
autodev-local run --json
autodev-local resume --json
autodev-local continue --max-cycles 10 --json
```

`dispatch` remains a low-level diagnostic one-shot and is not the preferred project runner because it does not advance response/checker session state.

## Truthfulness boundary

The local UI driver and response collector may exist in code while the user's actual ChatGPT build is still unvalidated. Until real calibration succeeds, report them as **implemented but not live-verified** and keep their defaults disabled.
