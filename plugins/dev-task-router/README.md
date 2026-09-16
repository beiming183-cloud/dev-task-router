# 项目拆解器 Plugin

Dev Task Router 的轻量 OpenAI Plugin 包。

当前仍保持 **skill-only + lightweight local companion**：不要求 MCP server、自建服务器、数据库或 VS Code Extension。

## 核心原则

```text
Task decomposition != conversation decomposition
```

复杂项目默认保持同一个 canonical conversation。不同 Task 可以使用不同 reasoning profile，但不为了 LOW / MEDIUM / HIGH 人为拆成多个聊天窗口。

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实
  ↓
Project → Stage → Step → Task
  ↓
Rolling Project Context + Task Context Pack
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
requested profile
  ↓
本地 exact mode switch
  ↓ verified
当前 canonical conversation
  ↓
response monitor
  ↓
Checker / Git evidence
  ↓
Rolling Context delta
  ↓
next Task
```

## Skills

- `index`：共享难度、上下文、仓库证据、失败重分类和验证规则；
- `inspect-repository`：读取 task-specific repo / branch / commit / files / tests / PR / diff / CI；
- `decompose-project`：结合真实仓库范围拆 Stage / Step / Task；
- `classify-task`：输出 Difficulty / Reason / Confidence / Traits；
- `route-model`：把难度映射到 Chat / Codex / Work；
- `build-context-pack`：从 rolling context + repository evidence 生成预算化当前 Task 工作集；
- `switch-local-mode`：Windows 本地同会话切换 requested model / effort，并验证 actual profile；
- `prepare-local-execution`：安全发送、response resume、Checker、NONE 与 continuous-loop 规则；
- `create-handoff`：生成 next-task-first compact handoff。

## Rolling context / Context Pack

`.autodev/context.yaml` 保存跨 Task 仍然有价值的信息，不是聊天记录副本。

正常 Task Context Pack 只携带：

```text
Project / Stage / Step / Task
project goal
applicable decisions
protected constraints
stage/task notes
acceptance
recent failure evidence
relevant files/facts/CI
requested execution profile
exact next action
```

不重复完整聊天历史，也不 dump 整个仓库。

PASS 后只自动写入 Checker 已验证的最小事实，不从 assistant prose 自动生成永久 decision/constraint。

## 当前 Chat Surface

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记模型池，但没有明确配置时不猜 family 强弱顺序。

## Local exact switch

Windows local companion 使用 UI Automation/accessibility，不使用固定屏幕坐标。

```text
autodev-mode probe --json
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

只有 `verified: true` 且 actual family/effort 与 requested 完全一致，才允许模型 Task 进入 conversation。

## Local execution loop

检查/运行命令：

```text
autodev-local prepare --json
autodev-local gate --dry-run --json
autodev-local probe-conversation --json

autodev-local run --json
autodev-local resume --json
autodev-local continue --max-cycles 10 --json
```

模型 Task：

```text
verified route
→ composer full read-back
→ duplicate guard
→ Send
→ stable response completion
→ Checker / Git evidence
```

`resume` 只恢复已存在的 active dispatch，没有 session 时禁止创建新发送。

真正 deterministic `NONE` command 可自动执行并继续；失败则 `DEBUG_TASK_REQUIRED`，不会把 NONE 直接提升成模型 Task。

## Failure reclassification

只有完成一次真实模型执行后，Checker/DIFF 失败才能作为 Difficulty promotion 证据：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

UI selector、ChatGPT 窗口、mode switch、response timeout、权限/依赖/网络等基础设施问题都不提升 Difficulty。

## 当前边界

V0.8 自动回归已覆盖 safe submit / response resume / Checker / rolling delta / deterministic NONE / bounded continuous loop。

Windows exact mode switch、composer、Send、assistant-message selectors 仍需要对用户实际 ChatGPT Windows build 做一次真机 UIA 校准。默认配置保持关闭；未验证前只称为**已实现、未 live-verified**。
