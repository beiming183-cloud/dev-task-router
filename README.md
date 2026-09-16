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
Execution Evidence / Recovery / Audit
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

## V0.9 — Execution Evidence / Recovery / Repository Sync

V0.9 stacked Draft PR #9 在 V0.8 的执行状态机上补齐“崩溃之后还能知道发生了什么”。重点不是更激进地自动发送，而是让执行边界可恢复、可审计、可与 GitHub 事实对齐。

### Append-only Execution Evidence

本地运行证据：

```text
.autodev/execution-evidence.jsonl
```

使用 SHA-256 hash chain 串联 compact event，记录 PREPARED / SUBMITTED / RESPONSE_COLLECTED / CHECKED / STATE_RECORDED 等边界，不复制完整聊天记录。

`evidence` 可检查链完整性；`audit` 交叉核验 response digest、session、dispatch ledger、workflow `local_dispatch_id` 和 terminal state。

### PREPARED / ambiguous-send 恢复

核心原则：**未知发送边界不猜测，也不自动二次发送。**

```text
PREPARED + 无 dispatch reservation → SAFE_RETRY
PREPARED + submitted              → RESUME
PREPARED + submitting + 已验证 post-baseline 活动 → RESUME
PREPARED + submitting + 无法证明发送结果          → AMBIGUOUS / stop
```

后续 crash point 也支持幂等恢复，例如 response 文件已落盘但 session metadata 尚未更新，或 workflow state 已记录结果但 session 仍停在 `CHECKED`/`REVIEW_REQUIRED`。同一 dispatch 恢复时不能重复增加 attempt 或重复追加 failure。

### Independent Reviewer 边界

同一个 canonical ChatGPT conversation 不能因为再发一句“独立审查”就算 independent Reviewer。

V0.9 只有在显式配置了独立外部 reviewer executor 且 gate 通过时才允许自动 Review；Reviewer executable/transport/process/protocol 故障属于基础设施问题，不消耗新的实现 attempt。明确的 Reviewer `FAIL` 才能作为真正 Task 验证失败证据。

### Repository anchor 同步

本地 Checker PASS 不等于 GitHub 上已经有对应 commit。

只有：

```text
repo-context commit 已知
+ CI == success
+ local HEAD == repo-context commit
+ 业务 worktree 干净
```

才允许通过 `sync-repository` 推进 rolling `last_commit`，避免把未 commit/push 的本地代码误写成远端事实。

### V0.9 CLI

```text
autodev-local recover --json
autodev-local evidence --json
autodev-local evidence --dispatch-id <id> --json
autodev-local audit --json
autodev-local sync-repository --json
```

Windows selector/model/effort/composer/response 的真实客户端校准仍由用户暂缓，因此相关 UIA 能力只称为**已实现、未 live-verified**，默认继续关闭。

## V1.0 — Release Readiness Candidate

`feature/v1.0-readiness` 正在把 V0.7–V0.9 收敛成正式发布门禁。它不会用 Linux CI 冒充 Windows ChatGPT 真机验收。

Readiness 被明确拆成：

```text
automated_ready
live_windows_ready
release_ready = automated_ready && live_windows_ready
```

当前自动可验证部分新增：

- privacy-safe UI fingerprint，只跟踪实际依赖的 selector；
- baseline 存在后，真实 mode switch 前执行 UI drift guard；
- LOW / MEDIUM / HIGH profile calibration 必须来自真实 `verified=true`；
- calibration 与 UI fingerprint 绑定，UI drift 后自动 stale；
- end-to-end calibration 反查 SUBMITTED / RESPONSE_COLLECTED / CHECKED / PASS evidence，而不是只信 registry；
- deterministic NONE failure 自动 materialize 独立 debug candidate；
- `activate-debug` 把 debug Task 显式插到 source 前，debug PASS 后再重新开放原 NONE command 复验；
- 允许 plan 只追加新 Task，但禁止删除已有 durable Task state；
- usage 记录真实 duration；拿不到 provider token 时保持 `null`；
- calibration 按初始难度统计 pass / attempts / duration / token coverage；
- HIGH-first one-shot PASS 只列入人工复核候选，不自动降档，也不宣称 lower profile 会成功；
- calibration/readiness 报告保持只读，不因为“查看”而推进 workflow timestamp。

CLI 增加：

```text
autodev-readiness fingerprint [--record] --json
autodev-readiness calibration --json
autodev-readiness readiness [--probe-ui] --json

autodev-mode calibrate-profile LOW|MEDIUM|HIGH
autodev-local activate-debug [task_id] --json
```

当前完整自动回归：**154 passed**。

这仍不是正式 V1.0：最终必须在目标 Windows ChatGPT build 上完成 model/effort/composer/Send/response selectors、LOW/MEDIUM/HIGH exact switch 和三档真实 end-to-end calibration，并得到：

```text
release_ready = true
```

在此之前 package/plugin 不提前冒充正式 `1.0.0`，V1.0 PR 保持 Draft。

详见 [`docs/V1.0.md`](docs/V1.0.md)。

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
recover-execution
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
- append-only execution evidence / consistency audit；
- conservative crash recovery；
- independent Reviewer gate；
- strict repository anchor synchronization；
- deterministic NONE runner + independently-classified debug recovery；
- bounded local project loop；
- UI fingerprint / profile calibration / readiness gate；
- descriptive outcome / duration / reported-token calibration；
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
- **V0.9 🚧 Draft**：execution evidence + recovery + audit + independent Reviewer + repository sync
- **V1.0 🚧 Readiness Draft**：UI drift/profile/e2e calibration + debug activation + usage/time/token/outcome diagnostics；等待 Windows live gate

## 文档

- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/V0.6.md`](docs/V0.6.md)
- [`docs/V0.7.md`](docs/V0.7.md)
- [`docs/V0.8.md`](docs/V0.8.md)
- [`docs/V0.9.md`](docs/V0.9.md)
- [`docs/V1.0.md`](docs/V1.0.md)

## 当前状态

```text
main: V0.6
PR #7 Draft: V0.7 foundation
PR #8 Draft (stacked on #7): V0.8 execution loop
PR #9 Draft (stacked on #8): V0.9 recovery/evidence
feature/v1.0-readiness: V1.0 readiness candidate
```

V0.7/V0.8/V0.9/V1.0 的自动回归可以继续推进，但 Windows 真机校准暂缓期间不会把相关 UIA 能力写成“已 live-verified”或把 V1.0 写成正式发布。

---

Dev Task Router 的目标是：

> **把一个复杂项目拆成不同难度的 Task，在同一个项目会话里让简单任务少想、复杂任务多想，同时用 Rolling Context、GitHub、客观 Checker、execution evidence 和 actual-profile 验证维持长期正确性。**
