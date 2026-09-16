---
name: classify-task
description: "Use when the user wants to judge the true difficulty of one or more software-development tasks, assign NONE/LOW/MEDIUM/HIGH profiles, or review whether tasks were over- or under-routed."
---

# Classify Task Difficulty

Follow `../index/SKILL.md` first.

## Goal

Classify each task from its engineering difficulty and risk, then route it directly to the matching model tier.

Do not interpret LOW/MEDIUM/HIGH as price tiers. They are difficulty tiers.

## Signals

Consider:

- blast radius;
- architecture coupling;
- ambiguity and design burden;
- state/lifecycle complexity;
- reversibility;
- verification burden;
- domain risk;
- whether the step is deterministic and needs no model.

## Output

For each task return:

```text
Task: <name>
Difficulty: NONE | LOW | MEDIUM | HIGH
Reason: <concise engineering reason>
Initial route: <same tier>
Failure route: <next tier or HIGH retry/BLOCKED>
Confidence: low | medium | high
```

Rules:

- `LOW` failure → reclassify next attempt to `MEDIUM`.
- `MEDIUM` failure → reclassify next attempt to `HIGH`.
- `HIGH` failure → stay `HIGH`; retry if another attempt is useful, otherwise `BLOCKED`.
- `NONE` command failure → create a separate debugging task and classify that task.

Do not promote when failure is clearly caused by infrastructure, permissions, rate limits, unavailable tools, missing credentials, or network issues.

When a failure causes promotion, explicitly say the original estimate was too low. Do not describe this as an intentional weak-first policy.
