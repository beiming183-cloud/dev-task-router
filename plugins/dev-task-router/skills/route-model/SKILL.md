---
name: route-model
description: "Use after task difficulty has been classified to map NONE/LOW/MEDIUM/HIGH onto the models available in the current execution surface, such as ChatGPT chat, Codex, or Work. Keep difficulty classification separate from model-family selection."
---

# Route Difficulty to an Execution Surface

Follow `../index/SKILL.md` first.

## Core rule

Use two separate decisions:

```text
Task content
  ↓
Difficulty classification
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
Current surface
  ↓
Surface-specific model / effort
```

Do not change task difficulty just because a different surface exposes different model names.

## Current surface model shape

The user's current environment has these planning assumptions:

### Chat

Chat uses the Sol family with three reasoning efforts:

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Treat this as a configurable surface mapping, not as part of the difficulty definition.

### Codex / Work

Codex and Work expose a broader pool containing the families:

```text
lunar
terra
sol
astra
```

with effort choices:

```text
low
medium
high
```

Do not invent an ordering such as `lunar < terra < sol < astra` unless the user or current product configuration explicitly provides that ordering.

If no family-to-difficulty policy is configured, output the classified difficulty plus the available pool and mark model-family selection as unresolved.

## Failure handling

A real reasoning/implementation failure is evidence that the original route may have been too low:

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

After the difficulty is updated, run the surface mapping again.

Infrastructure failures such as missing credentials, unavailable tools, network failures, permissions, or rate limits do not change task difficulty.

## Output

Return:

```text
Surface: chat | codex | work | <other>
Difficulty: NONE | LOW | MEDIUM | HIGH
Route status: resolved | unresolved
Model family: <family or unresolved>
Effort: <low/medium/high or unresolved>
Reason: <why this surface mapping was selected>
Candidate pool: <only when unresolved>
```
