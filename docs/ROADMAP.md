# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → 同会话精确切换 + Rolling Context → 本地自动执行闭环 → recovery / evidence / audit。**

V1.0 前继续保持轻量，不要求自建服务器、数据库集群、VS Code Extension 或 Agent Swarm。

核心产品约束：**Task decomposition 不等于 conversation decomposition。** 复杂项目默认保持一个 canonical conversation；简单 Task 用低推理，复杂 Task 用高推理，优先在同一会话原地切换 execution profile。

---

## V0.1 — 最小可运行闭环 ✅

完成 CLI、状态机、YAML plan、CommandExecutor、checks 和 CI。

## V0.2 — 任务层级与多模型路由 ✅

完成 Project → Stage → Step → Task、`NONE / LOW / MEDIUM / HIGH`、RuleRouter、Model Profile、Executor Registry、Handoff。

## V0.3 — 验证、重试与升级闭环 ✅

完成 Checker、Reviewer、Retry、Escalation、BLOCKED、失败历史和人工 retry。

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

首次仍按预测难度直接分配；这不是 weak-first。

---

## V0.4 — ChatGPT / Codex Plugin + Skill 化 ✅

完成 Skill-only Plugin、marketplace、Plugin package 回归测试和 Python package `0.4.0`。

验证：**23 passed**。

---

## V0.5 — 内容级复杂度判断 + Surface Router ✅

完成 `DifficultyClassifier / DifficultyAssessment`、Task 拆分停止条件、`SurfaceCatalog / SurfaceDecision`、`route-model` Skill，以及 Chat / Codex / Work 的分层路由配置。

不猜 Lunar / Terra / Sol / Astra 强弱顺序。

完整回归：**29 passed**。

---

## V0.6 — GitHub 真实仓库上下文 ✅

完成 `RepositoryContext`、repo/branch/commit/PR/diff/test/CI evidence、repository-aware Difficulty、commit-anchored handoff、`inspect-repository` Skill，以及测试文件不计入业务 module_count 的误判修复。

核心原则：

```text
GitHub evidence = 当前实现事实
User request    = 目标状态
```

验证：branch CI + PR merge-ref CI 均通过，完整回归 **37 passed**。PR #6 已 squash merge 到 `main`。

---

## V0.7 — Same-Conversation Foundation 🚧 Draft

目标：让复杂项目长期保持**同一个 canonical ChatGPT conversation**，同时支持按 Task 切 reasoning profile，并控制长项目上下文。

### A. Local Exact Mode Switch

已实现 candidate：

- `RequestedProfile / SwitchResult`
- `ModeSwitchController / ModeSwitchBackend`
- `DryRunModeSwitchBackend / WindowsUIAModeSwitchBackend`
- `.autodev/local-switch.yaml`
- `autodev-mode probe`
- `autodev-mode switch LOW|MEDIUM|HIGH`
- requested / actual profile 分离
- Windows UI Automation/accessibility 驱动
- 禁止固定屏幕坐标
- selector / family / effort / verify labels 配置化
- 默认禁用，必须先校准
- `verified: true` 才认为切换成功
- MODE_SWITCH 基础设施失败不提升 Difficulty
- Skill：`switch-local-mode`

Windows 真机校准由用户暂缓，因此 PR #7 保持 Draft；其余自动可验证开发继续推进。

### B. Rolling Project Context / Task Context Pack

已实现：

- `.autodev/context.yaml`
- `RollingProjectContext / ContextBudget`
- `TaskContextPack / ContextPackBuilder`
- project goal / decisions / constraints / stage notes / task notes
- normalized dedupe
- commit-anchor stale detection
- repository facts/files/CI budgets
- recent failures / acceptance budgets
- `autodev context / context-pack`
- handoff 使用 **Next Task Context Pack first**
- PASSED 历史任务不反复展开
- Skill：`build-context-pack`

---

## V0.8 — 本地同会话自动执行闭环 🚧 Draft

V0.8 是 stacked Draft PR #8，base 为 V0.7 branch。自动可验证 candidate 已从“发送前 gate”推进到完整本地状态机骨架。

### A. Execution gate ✅

```text
Task Ready
→ fresh Context Pack
→ Difficulty / requested profile
→ actual-profile verification
→ dispatch gate
```

阻塞：

```text
STALE_CONTEXT
ROUTE_UNRESOLVED
MODE_SWITCH_UNAVAILABLE
MODE_SWITCH
PROFILE_MISMATCH
```

基础设施失败不增加 attempts。

### B. Safe current-conversation sender ✅ code / ⏸ live validation

已实现：

- `WindowsUIAConversationBackend`
- 当前可见 ChatGPT conversation
- composer selector
- full prompt write/read-back verification
- Send selector
- 禁止固定坐标
- `.autodev/local-dispatch.json`
- sticky submitting/submitted duplicate guard
- duplicate check before touching UI

默认关闭；Windows 真机 selector 尚未校准。

### C. Response monitor / resume ✅ code / ⏸ live validation

已实现：

- `ResponseSnapshot`
- compact `ResponseBaseline`
- `ConversationResponseMonitor`
- `LocalResponseConfig`
- `WindowsUIAResponseSnapshotSource`
- conservative stable-response completion
- `.autodev/local-sessions.json`
- `.autodev/local-responses/`
- `WAITING_RESPONSE`
- same-dispatch resume without resend
- `CHECKED` crash recovery idempotency

Response baseline 只保存 message count + latest-message SHA-256，不保存整个旧 conversation。

### D. Checker / failure semantics ✅

- response completed 不等于 PASS；
- assistant 自称完成不等于 PASS；
- Checker / Git evidence 才决定 Task；
- `require_diff` 使用 compact pre-dispatch Git snapshot digest；
- UI / response timeout 不消耗模型 attempt；
- 真正 CHECK/DIFF failure 才触发下一次 Difficulty promotion；
- `REVIEW_REQUIRED` 保持独立 Review 边界，不用同一 conversation 假装独立 reviewer。

### E. Rolling Context delta ✅

PASS 后只写入机器验证事实：

```text
Verified PASS <task>
Checker verified
short dispatch id
```

不从 assistant prose 自动生成 durable decision/constraint，不自动移动 `last_commit`。新 Task 每次 prepare 都重新读取 rolling/repository context，并同步刷新 handoff。

### F. Deterministic NONE ✅

成功：

```text
NONE command → checks → PASS → next Task
```

失败：

```text
NONE command → DEBUG_TASK_REQUIRED → stop
```

失败的 NONE 不提升到 LOW/MEDIUM/HIGH，也不会自动重复执行；调试必须作为独立 Task 重新分类。

### G. Bounded continuous loop ✅

CLI：

```text
autodev-local run --json
autodev-local resume --json
autodev-local continue --max-cycles 10 --json
```

可继续：

```text
PASSED
CHECK_FAILED → promoted retry
successful deterministic NONE
```

必须停止：

```text
WAITING_RESPONSE
RECOVERY_REQUIRED
REVIEW_REQUIRED
DEBUG_TASK_REQUIRED
FAILED / BLOCKED
infrastructure failure
```

`max_cycles` 防止无限运行。

V0.8 candidate 自动回归达到 **89 passed**。这不是 Windows ChatGPT 真机验收，PR #8 仍保持 Draft。

---

## V0.9 — Execution Evidence / Recovery / Repository Sync 🚧 Draft candidate

V0.9 的目标是让 V0.8 的本地执行状态机在真实长期运行中具备**可恢复、可审计、可与远端事实对齐**的能力，而不是通过更激进的自动化掩盖不确定性。

### A. Append-only execution evidence ✅

已实现：

- `.autodev/execution-evidence.jsonl`；
- compact event，不复制完整 chat history；
- SHA-256 hash chain；
- model execution 与 deterministic NONE 都能写 evidence；
- 幂等 event key，恢复时不重复追加同一边界证据；
- `autodev-local evidence` 查看/验链。

典型边界：

```text
PREPARED
→ SUBMITTED
→ RESPONSE_COLLECTED
→ CHECKED
→ STATE_RECORDED
```

### B. PREPARED / ambiguous-send reconciliation ✅ code / ⏸ live selector validation

`LocalRecoveryController` 按 durable ordering 保守判断：

```text
PREPARED + no reservation → SAFE_RETRY
PREPARED + submitted      → RESUME
PREPARED + submitting + verified post-baseline activity → RESUME
PREPARED + submitting + no proof                        → AMBIGUOUS
```

`AMBIGUOUS` 不会自动 resend。selector/response source 不可用也不会被解释成“肯定没发”。

CLI：

```text
autodev-local recover --json
```

### C. Cross-crash-point idempotent recovery ✅

已覆盖：

- response file 已写、session metadata 尚未提交；
- Checker 已完成、session 尚未推进；
- workflow terminal state 已持久化、session 仍停在旧状态；
- 同一 `local_dispatch_id` 重放不会重复增加 attempts/failures/route history。

### D. Execution consistency audit ✅

`autodev-local audit --json` 交叉检查：

- evidence chain；
- response digest；
- session ↔ dispatch ledger；
- workflow `local_dispatch_id` ↔ session/evidence；
- terminal workflow state ↔ recoverable session state。

可恢复的 write lag 可以是 warning；digest/identity corruption 必须 fail closed。

### E. Independent Reviewer execution boundary ✅

同一个 canonical ChatGPT conversation 不能冒充独立 Reviewer。

自动 Review 只有在显式配置独立外部 reviewer executor 时才能通过 gate。默认 disabled。

语义：

```text
verified reviewer FAIL → genuine verification failure
reviewer transport/process/protocol failure → infrastructure failure
```

基础设施 reviewer failure 不增加新的实现 attempt。

### F. Repository execution evidence synchronization ✅

本地 PASS 不自动移动 `last_commit`。

`autodev-local sync-repository --json` 只有在以下事实同时成立时才推进 repository anchor：

```text
repo-context commit exists
CI == success
local HEAD == repo-context commit
business worktree clean
```

这样不会把未 commit/push 的本地修改误认为 GitHub 已验证事实。

### G. Recovery Skill / 0.9.0 packaging ✅ candidate

- Python package metadata → `0.9.0`；
- Plugin manifest → `0.9.0`；
- Skill：`recover-execution`；
- `docs/V0.9.md`；
- Plugin/package regressions 更新。

### H. 仍待 V1.0 readiness / 非 V0.9 自动回归阻塞项

- 用户机器真实 ChatGPT Windows selector drift/live calibration；
- LOW/MEDIUM/HIGH real-profile end-to-end switching；
- composer/Send/assistant-message live selectors；
- 更长期的 predicted difficulty → actual success/failure calibration；
- usage/token/time metrics 与减少无意义 HIGH；
- deterministic failure → 自动 materialize debug Task 的完整 UX。

V0.9 core branch 在 packaging/docs 收口前已经达到 **126 passed**；最终 branch + PR merge-ref 数量以最新 CI 为准。

API Provider 仍可作为可选执行层，不强绑 OpenAI；DeepSeek/其他 provider adapter 应保持 vendor-neutral，并且必须配合受控工具/patch/checker，而不是把“调用模型 API”误认为“代码已经修改”。

---

## V1.0 — 第一版正式发布

目标能力：

- 一个复杂项目对应一个 canonical conversation；
- Project / Stage / Step / Task；
- 自动内容级难度分类；
- Surface-aware routing；
- Windows 本地 exact mode switching；
- requested/actual profile 验证；
- GitHub 真实上下文；
- Rolling Project Context + Task Context Pack；
- safe submit / response resume；
- execution evidence / audit / crash recovery；
- Checker / independent Reviewer / failure reclassification；
- strict repository anchor sync；
- deterministic NONE；
- bounded local continuous execution；
- pause / resume / recovery。

不作为 V1.0 阻塞项：云端 exact mode switch、自建服务器、多用户、VS Code UI、Agent Swarm。

---

# 当前下一步

1. 对 V0.9 `0.9.0` packaging + recovery Skill 跑完整 branch CI。
2. 创建 stacked Draft PR #9，并跑 PR merge-ref CI。
3. 审查 V0.9 diff 与 regression logs；自动验收通过后保持 Draft，等待用户以后恢复 Windows 真机校准。
4. Windows live calibration 暂缓期间，不把 UIA 能力写成 live-verified。
