# 项目拆解器 Plugin

Dev Task Router 的轻量 OpenAI Plugin 包。

V0.7 继续保持 **skill-only + lightweight local companion**：不要求 MCP server、自建服务器、数据库或 VS Code。

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
当前 Surface
  ↓
requested profile
  ↓
本地 exact mode switch（可用时）
  ↓ verified
同一个 canonical conversation
```

## Skills

- `index`：共享难度、上下文、仓库证据、失败重分类和验证规则；
- `inspect-repository`：读取 task-specific repo / branch / commit / files / tests / PR / diff / CI；
- `decompose-project`：结合真实仓库范围自动拆 Stage / Step / Task；
- `classify-task`：输出 Difficulty / Reason / Confidence / Traits；
- `route-model`：把难度映射到 Chat / Codex / Work；
- `build-context-pack`：从 rolling context + repository evidence 生成预算化当前 Task 工作集；
- `switch-local-mode`：Windows 本地同会话切换 requested model / effort，并要求验证 actual profile；
- `create-handoff`：生成 next-task-first compact handoff。

## Rolling context

`.autodev/context.yaml` 只保存跨 Task 仍有价值的信息：

```text
project goal
still-valid decisions
protected constraints
stage notes
task notes
last commit anchor
```

它不是聊天记录副本。

当 `context.last_commit` 与当前 repository commit 不一致时，Task Context Pack 标记 `stale_context: true`，要求刷新 commit-sensitive facts。

## Context Pack

一个正常 Task Context Pack 只携带：

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

## 当前 Chat Surface

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记模型池，但没有用户明确配置时不猜 family 强弱顺序。

## Local exact switch

Windows local companion 使用 UI Automation/accessibility，不使用固定屏幕坐标。

```text
autodev-mode probe --json
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

只有 `verified: true` 才能声称 requested profile 已经成为 actual profile。

UI selector 找不到、ChatGPT 未打开、权限/依赖/网络失败都属于基础设施问题，不触发 Task Difficulty 上调。

## Failure reclassification

真实实现/推理失败：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

不是 weak-first。

## 当前边界

V0.7 的 Rolling Context / Context Pack 可由 CI 自动验证；Windows exact mode switch 仍需要对用户当前 ChatGPT build 做一次真机 UIA 校准。未验证前不会声称本地自动切档已经完成。
