# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由 Plugin。

项目主线是 **ChatGPT / Codex Plugin + Skills**。它把复杂开发目标拆成可执行 Task，结合 GitHub 真实仓库判断工程难度，再把 Difficulty 映射到当前执行 Surface。V0.7 的核心是：**不拆聊天窗口，在同一个项目会话里切换 reasoning profile，并用 Rolling Context 控制长项目上下文。**

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
Surface route
  ↓
requested profile
  ↓
Local ModeSwitchController
  ↓ verified
同一个 canonical ChatGPT conversation
```

核心原则：

```text
Task decomposition != conversation decomposition
```

拆任务不等于拆聊天窗口。复杂项目默认保持一个 canonical conversation，简单 Task 少用推理，复杂 Task 多用推理；聊天历史很长时，用 compact context pack 保留真正重要的信息，而不是重新发送完整历史。

## Difficulty 与模型分层

当前 Chat 配置：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记可用池：

```text
families: lunar / terra / sol / astra
efforts:  low / medium / high
```

项目不会擅自猜 Codex/Work family 强弱顺序；未配置 route 时保持 `unresolved`。

## V0.7 Same-Conversation Foundation

### Local Exact Mode Switch

V0.7 candidate 包含：

```text
RequestedProfile
SwitchResult
ModeSwitchController
ModeSwitchBackend
DryRunModeSwitchBackend
WindowsUIAModeSwitchBackend
```

本地配置：

```text
.autodev/local-switch.yaml
```

本地 CLI：

```text
autodev-mode probe --json
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

原则：不用固定屏幕坐标；使用 Windows UI Automation / accessibility；selector / family / effort / verify labels 配置化；`requested` 与 `actual` 分开；切换后必须验证；mode-switch failure 不触发 Difficulty promotion。

Windows 真机验收目前由用户暂缓，因此 PR #7 保持 Draft。

### Rolling Project Context

`autodev init` 现在生成：

```text
.autodev/context.yaml
```

只保存跨 Task 仍然有价值的信息：

```text
project goal
decisions
protected constraints
stage notes
task notes
last commit anchor
```

Python Core：

```text
RollingProjectContext
ContextBudget
TaskContextPack
ContextPackBuilder
```

CLI：

```text
autodev context
autodev context --json
autodev context --import <yaml/json>
autodev context-pack <task-id>
autodev context-pack <task-id> --json
```

Context Pack 默认只携带当前 Task 真正需要的：仍有效的 decisions/constraints、当前 stage/task notes、acceptance、最近 failure evidence、相关 repo files/facts/CI、requested profile 和 exact next action。

如果 `context.last_commit` 与当前 repository commit 不一致，会标记：

```text
stale_context: true
```

提示刷新 commit-sensitive facts。

### Handoff

`handoff.md` 已改成 **Next Task Context Pack first**：

```text
当前项目状态
↓
下一个 Task 的 compact context pack
↓
最多 10 个 unresolved Task
```

已经 PASSED 的老任务不再反复展开，避免长项目 handoff 越滚越大。

## GitHub Repository Context

V0.6 已支持：

```text
repository / branch / commit / PR
相关实现文件
相关测试
changed files / diff
CI/check 状态
verified facts / evidence tags
```

仓库证据描述当前实现状态，用户要求描述目标状态；两者不能混淆。

## 失败后重新分类

真实实现/推理失败：

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

权限、凭据、网络、工具不可用、UI selector 找不到、模式切换验证失败等基础设施问题不应该提升 Task Difficulty。

## Plugin Skills

```text
index
inspect-repository
decompose-project
classify-task
route-model
build-context-pack
switch-local-mode
create-handoff
```

当前仍是 **skill-only Plugin + lightweight local companion**；不要求服务器、数据库或 VS Code Extension。

## Python Reference Core

目前支持：

- Project / Stage / Step / Task；
- `RepositoryContext`；
- `RollingProjectContext / TaskContextPack`；
- 内容级 `DifficultyClassifier`；
- `SurfaceCatalog / SurfaceDecision`；
- `ModeSwitchController`；
- RuleRouter；
- Checker / Reviewer；
- Retry / Escalation / BLOCKED；
- compact handoff / state / usage；
- GitHub Actions CI。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI
- **V0.2 ✅**：任务层级 + 路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation
- **V0.4 ✅**：Plugin + Skills
- **V0.5 ✅**：内容级 Difficulty + Surface Router
- **V0.6 ✅**：GitHub 真实仓库上下文
- **V0.7 🚧**：同会话 Exact Mode Switch + Rolling Context / Task Context Pack
- **V0.8**：本地自动执行闭环
- **V0.9**：稳定性 / 恢复 / 路由校准
- **V1.0**：完整轻量本地多模型开发编排

## 文档

- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/V0.6.md`](docs/V0.6.md)
- [`docs/V0.7.md`](docs/V0.7.md)

## 当前状态

**V0.7 candidate on `feature/v0.7-local-exact-switch`.**

自动部分已经进入回归；Windows 真机 LOW / MEDIUM / HIGH UIA 验收暂缓。PR #7 保持 Draft，不会在未验证本地 exact switch 的情况下假装 V0.7 已完成。

---

Dev Task Router 最终目标是：

> **把一个复杂项目拆成不同难度的任务，在同一个项目会话里让简单任务少想、复杂任务多想，同时用 Rolling Context、GitHub、测试和 actual-profile 验证维持长期正确性。**
