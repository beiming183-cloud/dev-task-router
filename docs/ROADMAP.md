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

## V0.7 — Same-Conversation Foundation 🚧

目标：让一个复杂项目长期保持**同一个 canonical ChatGPT conversation**，同时解决两个问题：

```text
不同 Task 需要不同 reasoning profile
+
同一聊天窗口不可能无限承载全部历史细节
```

### A. Local Exact Mode Switch

当前 candidate 已实现：

- `RequestedProfile`
- `SwitchResult`
- `ModeSwitchController`
- `ModeSwitchBackend` 协议
- `DryRunModeSwitchBackend`
- `WindowsUIAModeSwitchBackend`
- `.autodev/local-switch.yaml`
- `autodev-mode probe`
- `autodev-mode switch LOW|MEDIUM|HIGH`
- `requested` / `actual` profile 分离
- Windows UI Automation/accessibility 驱动
- 禁止固定屏幕坐标
- selector / family / effort / verify labels 全部配置化
- 默认禁用，必须先校准
- UI 动作后无法验证则返回失败，不声称已经切换
- 模式切换失败属于 `MODE_SWITCH`/执行基础设施问题，不触发 Difficulty 上调
- Skill：`switch-local-mode`
- optional dependency：`pywinauto`

本地验收流程：

```text
打开 canonical ChatGPT conversation
↓
autodev-mode probe --json
↓
校准 .autodev/local-switch.yaml
↓
分别验证 LOW / MEDIUM / HIGH
↓
每次必须 verified: true
```

Windows 真机校准由用户暂缓，因此 PR #7 保持 Draft；其余自动可验证开发继续推进。

### B. Rolling Project Context / Task Context Pack

已实现：

- `.autodev/context.yaml`
- `RollingProjectContext`
- `ContextBudget`
- `TaskContextPack`
- `ContextPackBuilder`
- project goal / decisions / constraints / stage notes / task notes
- 字符串归一化去重
- commit-anchor stale detection
- repository files / facts / CI 的预算化选择
- recent failure evidence budget
- acceptance budget
- requested execution profile 写入 pack
- `autodev context`
- `autodev context --import`
- `autodev context-pack <task>`
- handoff 改成 **Next Task Context Pack first**
- PASSED 历史任务不反复占据 handoff
- unresolved ledger 最多展示 10 个 Task
- Skill：`build-context-pack`

核心链路：

```text
same canonical conversation
↓
rolling project context
+
current task-specific repository evidence
↓
Task Context Pack
↓
requested reasoning profile
↓
local exact switch
↓ verified
execute Task
```

Context Pack 的目的不是换窗口，而是让同一个长窗口在项目持续很久后仍有一个小而准确的工作集。

---

## V0.8 — 本地自动执行闭环

目标：把目前已经存在的“拆解 / 分类 / Context Pack / Mode Switch / Checker”串成自动状态机，而不是要求用户逐条手动执行 CLI。

计划：

- `LocalConversationExecutor` 抽象；
- Task Ready 时自动生成 Context Pack；
- 自动请求目标 profile；
- `verified: true` 后才允许发送 Task；
- 把 Task prompt + Context Pack 送入当前 canonical conversation；
- 等待执行结果；
- 收集 result / diff / test / CI；
- 更新 workflow state；
- 只把 durable information 写回 Rolling Context；
- Task 成功后自动进入下一 Task；
- 真正 Task failure 才做 `LOW → MEDIUM → HIGH`；
- Mode/UI/permission/network failure 不升级 Difficulty；
- pause / resume / recovery；
- 用户可设置最大连续 Task 数和人工确认边界。

```text
Task Ready
↓
Context Pack
↓
Difficulty / Route
↓
ModeSwitchController
↓ verified
Current ChatGPT Conversation
↓
Task execution
↓
Checker / Reviewer / GitHub evidence
↓
Rolling Context update
↓
Next Task
```

API Provider 仍可作为以后可选辅助层，但不是当前主路线；云端 exact switching 暂不作为 V0.8 阻塞项。

---

## V0.9 — 稳定性、恢复与成本校准

目标：让本地长时间运行更可靠，并逐步校准“哪些 Task 真正需要更高 reasoning”。

计划：

- mode-switch selector drift detection；
- ChatGPT UI change recovery；
- stuck-task timeout；
- duplicate-send protection；
- execution lease / idempotency；
- crash recovery；
- requested vs actual profile audit；
- predicted difficulty → actual success/failure 统计；
- 减少无意义 HIGH；
- usage / token / time 指标。

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
- Checker / Reviewer / failure reclassification；
- 本地自动执行闭环；
- pause / resume / recovery。

不作为 V1.0 阻塞项：云端 exact mode switch、自建服务器、多用户、VS Code UI、Agent Swarm。

---

# 当前下一步

V0.7 自动部分继续完成回归；Windows 真机校准暂缓。

随后进入 **V0.8 本地自动执行闭环**：先实现 `Task Ready → Context Pack → requested profile → switch gate` 的执行契约，再接真正的当前 ChatGPT conversation 驱动。
