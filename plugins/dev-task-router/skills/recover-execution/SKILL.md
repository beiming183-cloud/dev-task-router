---
name: recover-execution
description: "Use when local same-conversation execution was interrupted, PREPARED/submitting state is ambiguous, session/dispatch/workflow facts disagree, or repository anchors need conservative reconciliation. Recover without duplicate sends, verify the append-only evidence chain, audit durable state, and only advance repository anchors from matching GitHub/CI evidence."
---

# Recover Local Execution

Follow `../index/SKILL.md` first.

## Purpose

Recover interrupted local execution without inventing facts, duplicating a ChatGPT send, or consuming a model attempt for infrastructure uncertainty.

The recovery rule is conservative:

```text
unknown send boundary
→ inspect durable evidence
→ prove safe retry OR prove submitted/resumable
→ otherwise remain blocked
```

Never guess across an ambiguous send boundary.

## Durable evidence sources

Use the smallest authoritative sources available:

```text
.autodev/local-sessions.json
.autodev/local-dispatch.json
.autodev/local-responses/<dispatch_id>.txt
.autodev/execution-evidence.jsonl
.autodev/state.json
.autodev/repo-context.yaml
Git HEAD / worktree
GitHub commit / PR / CI evidence
```

`execution-evidence.jsonl` is an append-only compact evidence ledger with a SHA-256 hash chain. It stores event metadata and digests, not a replay of the full conversation.

## PREPARED / ambiguous-send reconciliation

Sender ordering matters: the dispatch ledger reservation is durably written before the UI send click is attempted.

Treat these cases differently:

```text
PREPARED + no dispatch reservation
→ SAFE_RETRY
```

No reservation proves the sender did not cross the reserved send boundary. Retire the old session and allow a new dispatch.

```text
PREPARED + dispatch=submitted
→ RESUME
```

Do not resend. Resume response collection for the existing dispatch.

```text
PREPARED + dispatch=submitting
+ calibrated post-baseline response activity
→ mark submitted
→ RESUME
```

```text
PREPARED + dispatch=submitting
+ no verified post-baseline activity
→ AMBIGUOUS
→ do not resend automatically
```

Missing/unreadable response selectors are infrastructure evidence, not proof that Send did or did not happen.

## Crash recovery after response/checker writes

Recovery must also be idempotent after later crash points.

Examples:

```text
response file exists + digest is valid
+ session metadata lagged
→ recover collected response state
```

```text
workflow state already records PASS / FAILED / BLOCKED
+ matching local_dispatch_id
+ session is still CHECKED / REVIEW_REQUIRED
→ reconcile session to durable workflow state
→ do not increment attempts again
```

A recovered CHECKED result for the same dispatch must never append a duplicate failure or duplicate route-history attempt.

## Execution evidence audit

Use:

```text
autodev-local evidence --json
autodev-local evidence --dispatch-id <id> --json
autodev-local audit --json
```

Audit should cross-check:

- evidence hash-chain validity;
- response file SHA-256 against session metadata;
- session task/dispatch identity against the dispatch ledger;
- workflow `local_dispatch_id` against session/evidence;
- terminal workflow state against recoverable session state.

Recoverable lag may be reported as a warning. Corrupted evidence, digest mismatch, or incompatible identities must fail closed.

## Independent Reviewer boundary

`REVIEW_REQUIRED` remains a real boundary.

The same canonical ChatGPT conversation must not be described as an independent reviewer merely because the next prompt says "review independently".

Automatic review is allowed only when an explicitly configured independent reviewer executor passes its gate. Reviewer transport/process/protocol failure is infrastructure failure and must not consume a new implementation attempt. A verified reviewer `FAIL` may count as genuine Task verification failure.

## Repository anchor synchronization

Local Checker PASS does not prove that a commit exists remotely.

Only advance rolling `last_commit` when all required facts agree:

```text
repo-context has a concrete commit
+ CI status is success
+ local Git HEAD == repo-context commit
+ relevant local worktree is clean
```

Then use:

```text
autodev-local sync-repository --json
```

If any condition fails, keep the old anchor. Never turn an uncommitted local diff into a GitHub fact.

## Difficulty semantics during recovery

Infrastructure/recovery conditions must not promote Difficulty, including:

- PREPARED ambiguity;
- selector/UI drift;
- response timeout;
- evidence audit inconsistency;
- missing reviewer transport;
- GitHub/CI refresh unavailable;
- repository anchor mismatch.

Only a completed model attempt that reaches objective task verification and fails can provide LOW→MEDIUM or MEDIUM→HIGH promotion evidence.

Deterministic NONE failure remains:

```text
DEBUG_TASK_REQUIRED
```

It must be materialized as a separate debugging Task and classified independently rather than promoted in place.

## Recommended recovery order

```text
1. autodev-local audit --json
2. autodev-local evidence --json
3. autodev-local recover --json   # only for ambiguous/PREPARED local send state
4. autodev-local resume --json    # when an existing dispatch is resumable
5. objective Checker / Review
6. refresh GitHub repository context and CI
7. autodev-local sync-repository --json when anchors truly match
8. continue the next Task
```

Do not rebuild state from full chat history when durable execution evidence already exists.

## Truthfulness boundary

Windows UIA recovery logic can be implemented and covered by synthetic regression tests before the user's real ChatGPT build is calibrated. Until live calibration succeeds, describe Windows selector recovery as **implemented but not live-verified**. Do not claim that a real selector, Send click, response detector, or mode switch has been validated on the user's machine without actual evidence.
