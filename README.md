# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由 Plugin。

项目主线是 **ChatGPT / Codex Plugin + Skills**。它把复杂开发目标拆成可执行 Task，结合 GitHub 真实仓库判断工程难度，再把 Difficulty 映射到当前执行 Surface。V0.7 开始优先解决一个关键问题：**保持同一个项目会话，同时在任务边界精确切换模型/思考强度。**

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实
  ↓
Project → Stage → Step → Task
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

拆任务不等于拆聊天窗口。复杂项目默认保持一个 canonical conversation，简单 Task 少用推理，复杂 Task 多用推理。

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

## V0.7 本地 Exact Mode Switch

V0.7 candidate 新增：

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

设计原则：

- 不用固定屏幕坐标；
- 使用 Windows UI Automation / accessibility；
- selector / family / effort / verify labels 全部配置化；
- 默认禁用，必须先对当前 ChatGPT build 做一次 probe；
- `requested` 与 `actual` profile 分开记录；
- UI 动作后必须验证；
- 无法验证就失败，不允许在错误 profile 下继续 Task；
- mode-switch failure 属于执行基础设施问题，不触发 `LOW → MEDIUM → HIGH` 难度升级。

### Windows 安装

```powershell
pip install -e ".[local]"
```

然后打开 ChatGPT 桌面端并停留在要继续开发的同一个项目会话：

```powershell
autodev-mode probe --json
```

把真实 UIA 标签写入 `.autodev/local-switch.yaml`，启用后再逐档验收。只有返回：

```json
{
  "verified": true
}
```

才算 exact switch 成功。

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
switch-local-mode
create-handoff
```

当前仍是 **skill-only Plugin + lightweight local companion**；不要求服务器、数据库或 VS Code Extension。

## Python Reference Core

目前支持：

- Project / Stage / Step / Task；
- `RepositoryContext`；
- 内容级 `DifficultyClassifier`；
- `SurfaceCatalog / SurfaceDecision`；
- `ModeSwitchController`；
- RuleRouter；
- Checker / Reviewer；
- Retry / Escalation / BLOCKED；
- state / handoff / usage；
- GitHub Actions CI。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI
- **V0.2 ✅**：任务层级 + 路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation
- **V0.4 ✅**：Plugin + Skills
- **V0.5 ✅**：内容级 Difficulty + Surface Router
- **V0.6 ✅**：GitHub 真实仓库上下文
- **V0.7 🚧**：Windows 本地同会话 Exact Mode Switch
- **V0.8**：Rolling Project Context / Handoff
- **V0.9**：本地自动执行闭环
- **V1.0**：完整轻量本地多模型开发编排

## 文档

- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/V0.6.md`](docs/V0.6.md)
- [`docs/V0.7.md`](docs/V0.7.md)

## 当前状态

**V0.7 candidate on `feature/v0.7-local-exact-switch`.**

自动回归已覆盖配置、路由、dry-run、requested/actual contract 和 Plugin package。最终完成还要求 Windows 真机对当前 ChatGPT build 完成一次 LOW / MEDIUM / HIGH 三档 UIA 验收。

---

Dev Task Router 最终目标是：

> **把一个复杂项目拆成不同难度的任务，在同一个项目会话里让简单任务少想、复杂任务多想，同时始终用 GitHub、测试和 actual-profile 验证作为事实来源。**
