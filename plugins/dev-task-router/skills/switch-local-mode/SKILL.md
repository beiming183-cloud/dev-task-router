---
name: switch-local-mode
description: "Use when a routed development task should stay in the same local ChatGPT conversation but needs a different model/reasoning profile. Resolve the requested profile, invoke the calibrated local companion, and require verification before execution continues."
---

# Switch Local ChatGPT Mode

Follow `../index/SKILL.md` first.

## Purpose

Keep one canonical project conversation while changing the **current conversation's local execution profile** between tasks.

```text
same conversation
      ↓
next Task
      ↓
Difficulty
      ↓
Surface route
      ↓
Local ModeSwitchController
      ↓
verify actual profile
      ↓
execute Task
```

Do not create a new chat merely to obtain a different reasoning tier.

## Local exact-switch contract

The local companion exposes a route-first interface. The Skill decides the desired route; the Windows companion handles the UI implementation.

For Chat, the current project configuration may resolve:

```text
LOW    → sol / low
MEDIUM → sol / medium
HIGH   → sol / high
```

Never infer an unresolved Codex/Work family ordering.

## Safety

Local switching must be safe-by-default:

- no fixed screen coordinates;
- use Windows UI Automation/accessibility labels;
- require one-time calibration against the user's current ChatGPT build;
- verify the selected profile after the UI action;
- if verification fails, stop instead of claiming the switch succeeded;
- keep `requested` and `actual` profile separate.

The default `.autodev/local-switch.yaml` is disabled until calibrated.

## Calibration flow

On the user's Windows machine, with ChatGPT open on the canonical project conversation:

```text
pip install -e ".[local]"
autodev-mode probe --json
```

Use the probe output to fill stable selector/model/reasoning accessibility labels in:

```text
.autodev/local-switch.yaml
```

Then enable the profile and verify each route:

```text
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

A successful exact switch must return `verified: true`.

## Failure handling

A mode-switch failure is an execution-infrastructure failure, not evidence that the coding task is harder.

Do **not** promote:

```text
LOW → MEDIUM
MEDIUM → HIGH
```

because a button/selector could not be found, UI automation permission is missing, ChatGPT is not open, or the requested profile cannot be verified.

Instead report `MODE_SWITCH` / local-infrastructure failure and stop before sending the task under the wrong profile.
