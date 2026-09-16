---
name: route-model
description: "Use after task difficulty has been classified to map NONE/LOW/MEDIUM/HIGH onto the models available in the current execution surface, such as ChatGPT chat, Codex, or Work. Keep difficulty classification separate from model-family selection."
---

# Route Difficulty to an Execution Surface

Follow `../index/SKILL.md` first.

## Core rule

Use separate decisions:

```text
Task content
  ↓
Difficulty classification
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
Current surface
  ↓
requested model / effort
  ↓
local exact switch when available
```

Do not change task difficulty just because a different surface exposes different model names.

## Chat

Current project mapping:

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Treat this as a configurable surface mapping, not as part of the difficulty definition.

When the project is running locally on Windows and the local companion is calibrated, a resolved Chat route should be passed to `switch-local-mode` **without opening a new conversation**.

The router's output is only the requested profile. The mode switch is not complete until the local companion reports the matching actual profile with `verified: true`.

## Codex / Work

Codex and Work expose a broader pool containing:

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

If no family-to-difficulty policy is configured, output the classified difficulty plus the available pool and mark model-family selection as unresolved. An unresolved route must not be sent to the local switcher.

## Failure handling

A real reasoning/implementation failure is evidence that the original route may have been too low:

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

After difficulty changes, run the surface mapping again.

A mode-switch failure is different. If the local UI selector is missing, ChatGPT is not open, accessibility access fails, or actual profile verification fails, keep the same Difficulty and report `MODE_SWITCH` instead of promoting the coding task.

## Output

Return:

```text
Surface: chat | codex | work | <other>
Difficulty: NONE | LOW | MEDIUM | HIGH
Route status: resolved | unresolved
Requested model family: <family or unresolved>
Requested effort: <low/medium/high or unresolved>
Mode enforcement: local_exact | unresolved | none
Reason: <why this mapping was selected>
Candidate pool: <only when unresolved>
```

When a local exact switch is attempted, append:

```text
Actual model family: <family or unknown>
Actual effort: <effort or unknown>
Verified: true | false
```
