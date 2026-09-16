# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → 同会话精确切换 + Rolling Context → 本地自动执行闭环 → recovery / evidence / audit → V1.0 readiness。**

V1.0 继续保持轻量：不要求自建服务器、数据库集群、VS Code Extension 或 Agent Swarm。

核心产品约束：

```text
Task decomposition != conversation decomposition
```

复杂项目默认保持一个 canonical conversation；简单 Task 用较低 reasoning profile，复杂 Task 用较高 reasoning profile。Task 切换不要求用户开多个聊天窗口。

难度与执行面继续分层：

```text
Task / repo evidence
→ Difficulty: NONE / LOW / MEDIUM / HIGH
→ Surface / execution backend
→ concrete requested profile
→ actual profile verification
```

首次按预测难度直接分配，不做 weak-first。只有真正 implementation / reasoning / Checker / Reviewer failure 才允许：

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

网络、权限、selector、UI drift、response timeout、reviewer transport、GitHub sync 等基础设施失败不提升 Difficulty。

---

## V0.1 — 最小可运行闭环 ✅

完成 CLI、状态机、YAML plan、CommandExecutor、checks 和 CI。

## V0.2 — 任务层级与多模型路由 ✅

完成 Project → Stage → Step → Task、`NONE / LOW / MEDIUM / HIGH`、RuleRouter、Model Profile、Executor Registry、Handoff。

## V0.3 — 验证、重试与升级闭环 ✅

完成 Checker、Reviewer、Retry、Escalation、BLOCKED、失败历史和人工 retry。

## V0.4 — ChatGPT / Codex Plugin + Skill 化 ✅

完成 Skill-only Plugin、marketplace、Plugin package 回归测试和 Python package `0.4.0`。

验证：**23 passed**。

## V0.5 — 内容级复杂度判断 + Surface Router ✅

完成 `DifficultyClassifier / DifficultyAssessment`、Task 拆分停止条件、`SurfaceCatalog / SurfaceDecision`、`route-model` Skill，以及 Chat / Codex / Work 的分层路由配置。

完整回归：**29 passed**。

## V0.6 — GitHub 真实仓库上下文 ✅

完成 `RepositoryContext`、repo/branch/commit/PR/diff/test/CI evidence、repository-aware Difficulty、commit-anchored handoff、`inspect-repository` Skill，以及测试文件不计入业务 module_count 的误判修复。

核心原则：

```text
GitHub evidence = 当前实现事实
User request    = 目标状态
```

验证：branch CI + PR merge-ref CI 均通过，完整回归 **37 passed**。PR #6 已 squash merge 到 `main`。

---

## V0.7 — Same-Conversation Foundation 🚧 Draft PR #7

完成自动可验证部分：

### Local Exact Mode Switch

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

### Rolling Project Context / Task Context Pack

- `.autodev/context.yaml`
- `RollingProjectContext / ContextBudget`
- `TaskContextPack / ContextPackBuilder`
- project goal / decisions / constraints / stage notes / task notes
- normalized dedupe
- commit-anchor stale detection
- repository facts/files/CI budgets
- recent failures / acceptance budgets
- handoff 使用 **Next Task Context Pack first**
- PASSED 历史任务不反复展开

Windows 真机 LOW/MEDIUM/HIGH 校准由用户暂缓，因此 PR #7 保持 Draft。

---

## V0.8 — 本地同会话自动执行闭环 🚧 Draft PR #8

完成自动可验证部分：

```text
Task Ready
→ fresh Context Pack
→ Difficulty / requested profile
→ actual-profile verification
→ safe current-conversation submit
→ resumable response collection
→ Checker / Git evidence
→ bounded continuous loop
```

### 关键语义

- stale context / unresolved route / unverified profile 全部 fail closed；
- composer 写入必须 read-back 一致后才 Send；
- `.autodev/local-dispatch.json` 防重复提交；
- response baseline 只保存 message count + latest digest，不保存完整聊天；
- `WAITING_RESPONSE` 可 resume，不重新发送；
- response completed 不等于 PASS；
- Checker / require_diff 才能决定 Task；
- UI / response 基础设施失败不消耗模型 attempt；
- `REVIEW_REQUIRED` 保持独立 Review 边界；
- bounded `continue --max-cycles` 防无限执行。

### Deterministic NONE

```text
NONE command PASS → next Task
NONE command FAIL → DEBUG_TASK_REQUIRED → stop
```

失败的 NONE 不提升模型，也不自动重复执行。

V0.8 candidate 自动回归达到 **89 passed**；Windows live selectors 仍未验收。

---

## V0.9 — Execution Evidence / Recovery / Repository Sync 🚧 Draft PR #9

V0.9 让 V0.8 的本地执行状态机具备长期运行所需的可恢复、可审计和远端事实对齐能力。

### Append-only execution evidence

`.autodev/execution-evidence.jsonl` 使用 SHA-256 hash chain，compact 记录：

```text
PREPARED
→ SUBMITTED
→ RESPONSE_COLLECTED
→ CHECKED
→ STATE_RECORDED
```

记录幂等，不复制完整 chat history。

### Conservative recovery

```text
PREPARED + no reservation → SAFE_RETRY
PREPARED + submitted      → RESUME
PREPARED + submitting + verified post-baseline activity → RESUME
PREPARED + submitting + no proof                        → AMBIGUOUS
```

未知发送边界不猜测、不自动 resend。

### Audit / Reviewer / Repository sync

- `autodev-local audit` 交叉检查 evidence/session/dispatch/response digest/workflow；
- canonical ChatGPT conversation 不能冒充独立 Reviewer；
- reviewer infrastructure failure 不增加实现 attempt；
- 本地 PASS 不自动移动 `last_commit`；
- `sync-repository` 只有在 CI success + local HEAD match + clean business worktree 时推进仓库 anchor。

V0.9 自动验收：branch CI + real `refs/pull/9/merge` CI 均通过，**127 passed**。Windows UIA live validation 仍保留到 V1.0 release gate。

---

# V1.0 — 第一版正式发布 🚧 Readiness Draft

目标不是继续堆新功能，而是把 V0.7/V0.8/V0.9 收敛成明确的发布判定。

## A. Readiness 三层门禁 ✅ code

```text
automated_ready
live_windows_ready
release_ready = automated_ready && live_windows_ready
```

Linux CI 只能证明 automated readiness，不能冒充 Windows live readiness。

## B. UI Fingerprint / Selector Drift Guard ✅ code / ⏸ live baseline

已实现：

- privacy-safe `UIFingerprint`；
- 只跟踪项目真实依赖的 mode/effort/composer/Send/response selector；
- 不把聊天正文和动态消息控件纳入 fingerprint；
- baseline 存在后，真实 mode switch 前先 probe；
- MATCH 才继续，DRIFT / PROBE_FAILED fail closed；
- UI drift 属于 infrastructure failure，不增加 attempt。

CLI：

```text
autodev-readiness fingerprint --json
autodev-readiness fingerprint --record --json
```

## C. LOW / MEDIUM / HIGH Profile Calibration ✅ code / ⏸ live calibration

- 只有真实 `SwitchResult.verified=True` 才能写 calibration；
- profile calibration 与 UI fingerprint 绑定；
- UI drift 后旧 calibration 自动 stale；
- `autodev-mode calibrate-profile LOW|MEDIUM|HIGH` 没有 dry-run 伪成功路径。

## D. End-to-End Calibration Evidence ✅ code / ⏸ live runs

Registry 不能自证 `end_to_end_verified`。Readiness 会反查：

```text
SUBMITTED
RESPONSE_COLLECTED
CHECKED(ok=true)
STATE_RECORDED(PASSED)
```

并验证 evidence chain、session、response digest、profile identity；Review Task 还必须有 `REVIEWED: PASS`。

## E. Deterministic Failure → Debug Task 完整 UX ✅

已从“只生成 candidate”推进到完整闭环：

```text
NONE failure
→ materialize debug candidate
→ explicit activate-debug
→ independent classification
→ debug PASS
→ reopen original NONE source
→ rerun original deterministic command/check
```

约束：

- source NONE 不提升模型；
- debug Task 不允许预设 level/model；
- plan 只允许追加新 Task；
- 删除已有 durable Task state 仍 fail closed；
- debug Task 插到 source 前；
- source 原 attempts/failures/route history 保留；
- debug PASS 不能伪造 source PASS，必须再跑原命令。

CLI：

```text
autodev-local activate-debug [task_id] --json
```

## F. Usage / Time / Token / Outcome Calibration ✅

已实现真实、保守的描述性统计：

- deterministic command/check 使用 monotonic elapsed time；
- model Task 使用 durable session wall-clock window；
- `usage_id` 防 crash/replay 重复计量；
- UI backend 拿不到 provider token 时必须保持 `null`；
- 只有 provider/API 实际返回 usage 时才写 token；
- 按 initial level 统计 pass/fail/blocked、attempts、one-shot pass、duration coverage、token coverage；
- 统计 promotion、HIGH-first、promoted-to-HIGH；
- `HIGH-first + one-shot PASS` 只生成 `high_manual_review_candidates`，不自动降档，不表示 lower profile 一定成功；
- calibration report 为只读，不刷新 workflow timestamp、不自动初始化 Task state。

CLI：

```text
autodev-readiness calibration --json
```

## G. 自动验收 ✅

V1.0 readiness branch 当前自动回归：

```text
154 passed
```

这证明 state machine / evidence / debug activation / usage / calibration / readiness 逻辑通过自动测试，**不证明 Windows ChatGPT 客户端已经 live-verified**。

## H. Windows Live Release Gate ⏸ 用户机器

正式 V1.0 发布前仍需：

```text
[ ] record target Windows UI fingerprint
[ ] selector drift = MATCH
[ ] LOW exact switch verified
[ ] MEDIUM exact switch verified
[ ] HIGH exact switch verified
[ ] composer write/read-back verified
[ ] Send verified
[ ] assistant response completion verified
[ ] LOW end-to-end PASS evidence
[ ] MEDIUM end-to-end PASS evidence
[ ] HIGH end-to-end PASS evidence
[ ] autodev-readiness readiness --probe-ui => release_ready=true
```

在此之前：

- V1.0 PR 保持 Draft；
- package/plugin 不提前宣称正式 `1.0.0`；
- 文档使用 `V1.0 readiness candidate`；
- 不把 CI green 写成 live Windows complete。

---

# 当前下一步

1. 建立 `feature/v1.0-readiness` stacked Draft PR，base 指向 V0.9 branch。
2. 对 Draft PR 跑真实 merge-ref CI，确认 V1.0 自动可验证部分在 stacked base 上仍绿。
3. 用户恢复 Windows 真机校准时，依次完成 fingerprint → LOW/MEDIUM/HIGH switch → composer/Send/response → 三档 e2e calibration。
4. 只有 `release_ready=true` 后才进入正式 `1.0.0` package/plugin bump、Ready for Review 和最终 merge/release。
5. 真实运行积累足够样本后，再考虑受控 lower-profile A/B calibration；V1.0 不从少量 HIGH one-shot success 自动调低阈值。

不作为 V1.0 阻塞项：云端 exact mode switch、自建服务器、多用户、VS Code UI、Agent Swarm。
