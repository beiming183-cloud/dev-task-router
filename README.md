# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由 Plugin。

项目主线是 **ChatGPT / Codex Plugin + Skills + lightweight local companion**。它把复杂开发目标拆成可验证 Task，结合 GitHub 仓库事实判断工程难度，并尽量在**同一个 canonical ChatGPT conversation**里按 Task 切换 reasoning profile，而不是为不同难度反复开新窗口。

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
verified actual profile
  ↓
current canonical ChatGPT conversation
  ↓
response monitor
  ↓
Checker / Git evidence
  ↓
Rolling Context delta
  ↓
next Task
```

核心原则：

```text
Task decomposition != conversation decomposition
```

拆 Task 不等于拆聊天窗口。简单 Task 少用推理，复杂 Task 多用推理；聊天历史变长时，用 compact Task Context Pack 保留当前真正需要的信息，而不是反复发送完整聊天和完整仓库。

## Difficulty 与模型分层

当前项目 Chat 配置：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前只登记模型池和 effort；未明确配置 route 时保持 `unresolved`，项目不会自行编造 family 强弱顺序。

## V0.7 — Same-Conversation Foundation

V0.7 Draft PR #7 建立了两块基础：

### Local Exact Mode Switch

```text
RequestedProfile
SwitchResult
ModeSwitchBackend
ModeSwitchController
WindowsUIAModeSwitchBackend
```

本地配置：

```text
.autodev/local-switch.yaml
```

原则：Windows UI Automation/accessibility、禁止固定屏幕坐标、requested/actual 分离、切换后必须 `verified: true`、模式切换失败属于基础设施错误而不是 Task 难度不足。

### Rolling Project Context / Task Context Pack

```text
.autodev/context.yaml
RollingProjectContext
ContextBudget
TaskContextPack
ContextPackBuilder
```

只携带当前 Task 需要的 goal / decisions / constraints / stage notes / task notes / acceptance / recent failures / relevant repo facts，并支持 commit-anchor stale detection。

`handoff.md` 使用 **Next Task Context Pack first**，已 PASSED 的老任务不反复展开。

Windows 真机 LOW/MEDIUM/HIGH 校准目前由用户暂缓，因此 V0.7 仍保持 Draft。

## V0.8 — 本地同会话自动执行闭环

V0.8 stacked Draft PR #8 已把自动可验证部分推进到：

```text
Task Ready
→ fresh Context Pack
→ route
→ exact-profile gate
→ safe current-conversation submit
→ resumable response collection
→ Checker / Git digest
→ PASS / real failure
→ bounded continuous loop
```

### 安全发送

`.autodev/local-conversation.yaml` 默认关闭。Windows sender：

- 只使用当前可见 ChatGPT conversation；
- 不使用固定坐标；
- composer 写入后完整 read-back；
- 只有文本完全一致才允许 Send；
- `.autodev/local-dispatch.json` 防重复发送；
- 模糊 crash 边界宁可阻塞，也不自动二次发送。

### Response Monitor / Resume

响应采集同样默认关闭并要求真实 UIA selector 校准。

发送前只保存 assistant-message 数量和 latest-message SHA-256，不保存完整旧聊天。新 response 必须在停止变化后经过额外稳定确认，才算 completed。

运行状态：

```text
.autodev/local-sessions.json
.autodev/local-responses/<dispatch_id>.txt
```

`WAITING_RESPONSE` 不增加模型 attempts。`resume` 只恢复已有 dispatch；没有 active session 时拒绝新发。

### Checker 才能 PASS

```text
message submitted ≠ PASS
response completed ≠ PASS
assistant says done ≠ PASS
```

只有 Checker / require_diff / 后续 Review 等客观证据才能推进 Task 状态。

真正模型执行后的 CHECK/DIFF failure 才能触发：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

UI、selector、mode switch、response timeout 等基础设施错误不升级 Difficulty。

### Deterministic NONE

真正的 test/build command 不进入聊天：

```text
NONE command PASS → 自动进入下一 Task
NONE command FAIL → DEBUG_TASK_REQUIRED
```

失败的 NONE 不会被改成 LOW/MEDIUM/HIGH，也不会自动重复执行；应创建独立 debug Task 并重新分类。

### Rolling Context 增量写回

PASS 后只自动记录机器确定的事实，例如 `Verified PASS <task>` 和 short dispatch id。不会把任意 assistant prose 自动升级成 durable decision / protected constraint，也不会未经新仓库证据擅自移动 `last_commit`。

### CLI

```text
autodev-local prepare --json
autodev-local gate --dry-run --json
autodev-local probe-conversation --json

autodev-local run --json
autodev-local resume --json
autodev-local continue --max-cycles 10 --json
```

`continue` 可以跨 PASS、真实 CHECK failure 的升级重试、成功的 deterministic NONE；遇到 WAITING_RESPONSE、REVIEW_REQUIRED、DEBUG_TASK_REQUIRED、BLOCKED/FAILED 或基础设施错误立即停，并受 `max_cycles` 硬上限保护。

自动回归当前达到 **89 passed**。这不等于 Windows ChatGPT 真机验收；真实 selector/model/effort/composer/response labels 仍需以后在目标客户端校准。

## GitHub Repository Context

V0.6 已支持：

```text
repository / branch / commit / PR
relevant implementation files / tests
changed files / diff
CI/check status
verified facts / evidence tags
```

仓库证据描述**当前实现事实**，用户要求描述**目标状态**；两者不能混淆。

## Plugin Skills

```text
index
inspect-repository
decompose-project
classify-task
route-model
build-context-pack
switch-local-mode
prepare-local-execution
create-handoff
```

当前仍是 **skill-only Plugin + lightweight local companion**；不要求服务器、数据库、VS Code Extension 或 Agent Swarm。

## Python Reference Core

当前包括：

- Project / Stage / Step / Task；
- RepositoryContext；
- RollingProjectContext / TaskContextPack；
- DifficultyClassifier；
- SurfaceCatalog / SurfaceDecision；
- ModeSwitchController；
- safe current-conversation sender；
- response monitor / resumable local session；
- deterministic NONE runner；
- bounded local project loop；
- Checker / Reviewer contract；
- Retry / escalation / BLOCKED；
- compact handoff / state / usage；
- GitHub Actions CI。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI
- **V0.2 ✅**：任务层级 + 路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation
- **V0.4 ✅**：Plugin + Skills
- **V0.5 ✅**：内容级 Difficulty + Surface Router
- **V0.6 ✅**：GitHub 真实仓库上下文
- **V0.7 🚧 Draft**：同会话 Exact Mode Switch + Rolling Context / Task Context Pack
- **V0.8 🚧 Draft**：安全发送 + response resume + Checker + bounded continuous loop
- **V0.9**：稳定性 / UI drift / repository execution evidence / recovery 校准
- **V1.0**：完整轻量本地多模型开发编排

## 文档

- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/V0.6.md`](docs/V0.6.md)
- [`docs/V0.7.md`](docs/V0.7.md)
- [`docs/V0.8.md`](docs/V0.8.md)

## 当前状态

```text
main: V0.6
PR #7 Draft: V0.7 foundation
PR #8 Draft (stacked on #7): V0.8 execution loop
```

V0.7/V0.8 的自动回归可以继续推进，但 Windows 真机校准暂缓期间不会把 Draft 标成“已完成并验证”。

---

Dev Task Router 的目标是：

> **把一个复杂项目拆成不同难度的 Task，在同一个项目会话里让简单任务少想、复杂任务多想，同时用 Rolling Context、GitHub、客观 Checker 和 actual-profile 验证维持长期正确性。**
