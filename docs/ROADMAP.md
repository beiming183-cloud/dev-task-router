# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → 同会话精确切换 + Rolling Context → 本地自动执行闭环。**

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

当前自动回归：**89 passed**。这不是 Windows ChatGPT 真机验收，PR #8 仍保持 Draft。

---

## V0.9 — Execution Evidence / Recovery / Routing Calibration

下一阶段重点不再是把更多状态塞进同一个 loop，而是解决真实长期运行的证据闭环与恢复质量：

- Windows UI selector drift detection / build fingerprint；
- composer / response selector recovery；
- PREPARED ambiguous-send 手工/自动 reconciliation；
- response/session inspection commands；
- local worktree vs remote GitHub execution evidence synchronization；
- commit/PR/CI evidence refresh after Task execution；
- independent Reviewer execution channel；
- deterministic failure → explicit debug Task materialization；
- requested vs actual profile audit；
- predicted difficulty → actual success/failure calibration；
- usage / token / time metrics；
- 减少无意义 HIGH。

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
- Checker / independent Reviewer / failure reclassification；
- deterministic NONE；
- bounded local continuous execution；
- pause / resume / recovery。

不作为 V1.0 阻塞项：云端 exact mode switch、自建服务器、多用户、VS Code UI、Agent Swarm。

---

# 当前下一步

1. 保持 PR #7 / #8 Draft，不绕过用户暂缓的 Windows 真机校准。
2. 对 V0.8 最新 head 跑 branch + PR merge-ref 回归。
3. 进入 V0.9：优先做 **execution evidence refresh / PREPARED reconciliation / independent reviewer boundary**。
