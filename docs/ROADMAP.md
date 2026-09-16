# Dev Task Router 开发路线图

## 总原则

按“先闭环、再路由、再验证、最后做界面和远程控制”的顺序推进。

项目保持轻量：V1.0 前不要求自建服务器、数据库集群或 Agent Swarm。

---

## V0.1 — 最小可运行闭环 ✅

已完成：

- `autodev init / plan / start / status / pause / resume`
- `.autodev/project.yaml / plan.yaml / state.json`
- READY / RUNNING / PAUSED / FAILED / PASSED
- 单一安全 `CommandExecutor`
- Task checks
- 失败状态、attempts、时间持久化
- plan/state 一致性保护
- pytest + GitHub Actions CI

---

## V0.2 — 任务层级与多模型路由 ✅

已完成：

- Project → Stage → Step → Task
- V0.1 flat `tasks:` 兼容读取
- `ModelLevel = NONE / LOW / MEDIUM / HIGH`
- `TaskRole = PLANNER / EXECUTOR`
- `.autodev/models.yaml`
- RuleRouter
- Task 显式 level 覆盖默认路由
- Model Profile：provider / model / executor
- Executor Protocol + Registry
- `command` / `agent-cli` Executor
- `handoff.md`
- `usage.jsonl`
- state 记录实际 route
- `autodev models / handoff`

验证：V0.1 + V0.2 共 **14 passed**。

详细说明见 [`V0.2.md`](V0.2.md)。

---

## V0.3 — 验证、重试与模型升级闭环 ✅

目标：解决“AI 说完成但实际没完成”，并在便宜模型处理不了时自动升级。

已实现：

- 独立 `TaskChecker`
- Task `checks` Gate
- `require_diff` Git working-tree Gate
- `acceptance` criteria
- 独立 Reviewer Gate
- `TaskRole.REVIEWER`
- `max_attempts`
- `escalate_after`
- `LOW → MEDIUM → HIGH` 升级策略
- `BLOCKED` Workflow / Task 状态
- 结构化 `failures[]`
- `route_history[]`
- `last_failure_type`
- `retry_cycles`
- `autodev retry <task>`
- `autodev retry <task> --run`
- Handoff 显示 attempts / route / last failure
- usage 日志扩展 retry 元数据字段
- V0.1 / V0.2 状态文件继续可迁移读取

默认升级示例：

```text
MEDIUM fail
→ MEDIUM retry
→ HIGH
```

兼容原则：旧任务未配置 `max_attempts` 时仍默认一次尝试，因此原 V0.1/V0.2 失败语义不被静默改变。

验收已覆盖：

- 第 2 次尝试成功；
- 第 3 次从 MEDIUM 升到 HIGH；
- 重试耗尽进入 BLOCKED；
- require_diff 拒绝“实际没有代码变化”的任务；
- Reviewer PASS 才能完成；
- Reviewer FAIL 会重试并最终 BLOCKED；
- 人工 retry 重置本轮预算但保留失败历史。

当前完整测试集：**21 tests**。

详细说明见 [`V0.3.md`](V0.3.md)。

---

## V0.4 — VS Code 轻量插件

目标：让日常使用不需要一直操作 CLI，同时保持插件本身很轻。

计划功能：

- VS Code Activity Bar / Side Bar 入口
- Project / Stage / Step / Task 树
- 当前 Workflow 状态
- Task 模型等级与实际 Profile
- Executor / Attempts / Last failure
- Logs / Handoff / Tests 快捷入口
- Continue / Pause / Retry / Stop
- 调用现有 AutoDev Core / CLI，不在插件中复制工作流逻辑
- 自动刷新 `.autodev/state.json`
- Windows / macOS / Linux 基础兼容

验收标准：用户安装插件后，不打开终端也能完成 `status → start/pause/retry → 查看任务状态` 基础流程。

---

## V0.5 — GitHub 工程闭环

目标：把 GitHub 作为远程事实来源和无需自建服务器的云端补充执行层。

计划功能：

- Branch / Commit / Push
- GitHub Actions 状态
- Test / Build workflow
- Artifact
- Android APK 等构建产物
- 可选 git worktree

---

## V0.6 — 手机控制

目标：电脑不在身边时，通过 GitHub 完成查看和基础控制。

第一阶段直接使用 GitHub App 查看 Commit、PR、Actions、Artifact。

第二阶段加入 Issue Command：

```text
/autodev status
/autodev continue
/autodev retry <task>
/autodev pause
```

第三阶段再考虑薄 PWA；PWA 只做状态展示与控制，不承担开发环境。

---

## V0.7 — 自动复杂度判断

从固定 RuleRouter 升级为半自动分类。

可能特征：

- 文件数量
- 代码影响范围
- 是否涉及核心架构 / 状态系统
- 历史失败次数
- 测试覆盖情况
- 安全 / 数据迁移风险

输出 `LOW / MEDIUM / HIGH`，并必须显示路由原因。

---

## V0.8 — 成本优化

- Provider Token usage
- 不同模型任务成功率
- Retry 成本
- HIGH 使用比例
- 全 HIGH 成本 vs 实际成本
- Context Budget
- 自动上下文裁剪

---

## V0.9 — 自适应路由

基于历史：

```text
Task type → Model → Success / Fail → Retry → Cost
```

逐步调整默认 Router，而不是永久依赖手写规则。

---

## V1.0 — 第一版正式发布

目标能力：

- Project / Stage / Step / Task
- 持久化状态
- 多模型 Router
- Planner / Executor / Checker / Reviewer
- Retry / Blocked / Resume
- Git 验证
- Test / Build 验证
- Handoff / Context Manager
- CLI + VS Code UI
- GitHub Actions
- 手机查看 / 基础控制
- Token 使用统计

不作为 V1.0 阻塞项：自建服务器、多用户、Agent Swarm、企业权限、Jira / Slack、自建 Sandbox 平台。

---

# 当前下一步

V0.1、V0.2、V0.3 已完成。下一阶段进入 **V0.4 VS Code 轻量插件**：

1. 建立 `vscode/` Extension 骨架。
2. 调用 `autodev status --json` 获取状态，不复制 Python Core。
3. 实现 Project / Stage / Step / Task TreeView。
4. 加入 Start / Pause / Retry 命令。
5. 显示 Attempts / Model / Executor / Last failure。
6. 监听 `.autodev/state.json` 自动刷新。
7. 提供打开 `handoff.md` / `plan.yaml` / `models.yaml` 快捷入口。
8. 保持无 WebView 的第一版，减少内存与复杂度。
9. 增加 Extension 单元测试与打包检查。
10. V0.4 稳定后再进入 GitHub 工程闭环。
