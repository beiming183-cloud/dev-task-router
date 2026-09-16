# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → 本地同会话精确切换 → Context 优化 → 自动执行。**

V1.0 前继续保持轻量，不要求自建服务器、数据库集群、VS Code Extension 或 Agent Swarm。

核心产品约束：**Task decomposition 不等于 conversation decomposition。** 复杂项目默认保持一个 canonical conversation；简单 Task 用低推理，复杂 Task 用高推理，优先在同一会话原地切换执行 profile。

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

## V0.7 — 本地同会话 Exact Mode Switch 🚧

目标：在 Windows 本地保持**同一个 ChatGPT 项目会话**，根据下一 Task 的 Difficulty / Surface route 自动切换模型与 reasoning profile，并且只有验证切换成功后才允许继续执行 Task。

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
- 新 Skill：`switch-local-mode`
- optional dependency：`pywinauto`
- Python / Plugin candidate `0.7.0`

本地验收流程：

```text
打开 canonical ChatGPT conversation
↓
autodev-mode probe --json
↓
用真实 accessibility 标签校准 .autodev/local-switch.yaml
↓
分别验证 LOW / MEDIUM / HIGH
↓
每次必须 verified: true
```

当前自动回归覆盖逻辑层和 dry-run；Windows ChatGPT 真机 UIA 仍必须在用户电脑完成一次校准和验收，不能用 Linux CI 冒充真机测试。

---

## V0.8 — Rolling Project Context / Handoff

目标：即使长期坚持一个 canonical conversation，也不把正确性寄托在无限聊天历史上。

计划：

- Project / Stage / Task Context 分层；
- Decision Registry；
- protected constraints；
- relevant-files 最小集合；
- verified facts provenance；
- failure evidence；
- Context Budget；
- stale evidence detection；
- task-specific Context Pack；
- 增量 handoff；
- 防止完整聊天历史和完整仓库反复发送。

---

## V0.9 — 本地自动执行闭环

目标：把“拆 Task → 判难度 → 本地精确切 profile → 发送当前 Task → 验证 → 下一 Task”连成同一会话的自动闭环。

```text
Task
↓
Difficulty classifier
↓
Surface router
↓
ModeSwitchController
↓ verified
canonical ChatGPT conversation
↓
Task execution
↓
Checker / GitHub / CI
↓
next Task
```

API Provider 仍可作为以后可选辅助层，但不是当前主路线；云端 exact switching 暂不作为 V0.7/V0.8 阻塞项。

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
- Rolling Project Context；
- Checker / Reviewer / failure reclassification；
- 本地自动执行闭环。

不作为 V1.0 阻塞项：云端 exact mode switch、自建服务器、多用户、VS Code UI、Agent Swarm。

---

# 当前下一步

完成 **V0.7 Windows 真机校准**：

1. 保持 ChatGPT 桌面端打开在同一个项目会话。
2. 安装 local extra。
3. 运行 `autodev-mode probe --json`。
4. 根据真实 UIA 控件填充 `.autodev/local-switch.yaml`。
5. 实测 `LOW / MEDIUM / HIGH` 三档。
6. 三档均返回 `verified: true` 后，再开 PR/合并 V0.7。
