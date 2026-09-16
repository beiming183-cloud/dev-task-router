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

验证：本地与 GitHub Actions 均通过。

---

## V0.2 — 任务层级与多模型路由 ✅

目标：让不同类型的任务真正能够被路由到不同等级的 Model Profile / Executor。

已实现：

- Project → Stage → Step → Task
- V0.1 flat `tasks:` 兼容读取
- `ModelLevel = NONE / LOW / MEDIUM / HIGH`
- `TaskRole = PLANNER / EXECUTOR`
- `.autodev/models.yaml`
- RuleRouter
- task.kind 默认路由
- Task 显式 level 覆盖默认路由
- Model Profile：provider / model / executor
- Executor Protocol + Registry
- `command` Executor
- 通用 `agent-cli` Executor
- `handoff.md`
- `usage.jsonl`
- state 记录 stage / step / role / kind / 实际 route
- V0.1 项目缺失 models.yaml 时自动补默认配置
- `autodev models`
- `autodev handoff`
- `autodev plan` 显示最终路由

验证：V0.1 回归测试 + V0.2 新测试共 **14 passed**，并用 fake Agent CLI 验证模型名和 prompt 确实传递给被路由的外部执行器。

详细说明见 [`V0.2.md`](V0.2.md)。

---

## V0.3 — 验证、重试与模型升级闭环

目标：解决“AI 说完成但实际没完成”，并在便宜模型处理不了时自动升级。

计划功能：

- Checker 抽象
- Git diff 检查
- acceptance criteria
- Reviewer
- Retry
- 最大重试次数
- BLOCKED 状态
- 失败原因结构化
- 模型升级策略

默认升级示例：

```text
MEDIUM fail
→ MEDIUM retry
→ HIGH
```

验收标准：故意制造错误修改，系统必须识别 FAIL；超过重试上限进入 BLOCKED，而不是错误进入 PASSED。

---

## V0.4 — VS Code 轻量插件

目标：让日常使用不需要一直操作 CLI。

侧栏计划显示：

- Project / Stage / Step / Task
- 状态
- 模型等级与实际 Profile
- Executor
- Logs / Diff / Tests

按钮：Continue / Pause / Retry / Stop。

原则：VS Code 只做 UI，不复制 Core 逻辑。

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

V0.1 与 V0.2 已完成。进入 V0.3 时优先顺序：

1. 定义 Checker 接口和 acceptance criteria。
2. 实现 Git diff / 文件存在 / 命令退出码等基础 Checker。
3. 增加 `BLOCKED` 状态。
4. 增加显式 `retry`。
5. 增加 max attempts。
6. 实现模型升级策略。
7. 加入独立 Reviewer 接口。
8. 让失败、重试、升级全部写入 usage / handoff。
9. 增加故意失败的端到端测试。
10. V0.3 稳定后再做 VS Code UI。
