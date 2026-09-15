# Dev Task Router 开发路线图

## 总原则

按“先闭环、再智能、最后做界面”的顺序推进。

不要一开始做复杂 UI、服务器、多用户和 Agent Swarm。第一目标是让一个真实任务可以：

```text
读取计划 → 选择模型 → 调用执行器 → 修改代码 → 检查结果 → 保存状态 → 继续下一步
```

---

## V0.1 — 最小可运行闭环

### 目标

证明 Workflow Core 能工作。

### 必做功能

- `autodev init`
- `autodev start`
- `autodev status`
- `autodev pause`
- `autodev resume`
- Project / Stage / Step / Task 数据模型
- `plan.yaml`
- `state.json`
- 基础状态机
- 基础 Router：LOW / MEDIUM / HIGH / NONE
- 单一 Runner
- Git diff 检查
- 基础测试命令执行
- Handoff 文件

### 限制

- 只支持一个执行器；
- LOW / MEDIUM / HIGH 可以暂时映射到同一个真实模型；
- 不做 VS Code UI；
- 不做自动复杂度分类；
- 不做 GitHub Actions。

### 验收标准

至少用一个测试仓库完成：

```text
Task 1 → 修改 → 检查 → PASS
Task 2 → 修改 → 测试 → PASS
中途退出 → resume → 正确继续
```

---

## V0.2 — 真正的多模型路由

### 目标

开始实际节省强模型额度。

### 功能

- `models.yaml`
- 不同等级映射不同模型 / Executor
- Planner 与 Executor 分离
- LOW / MEDIUM / HIGH 规则路由
- 每个 Task 记录实际使用模型
- 初步 Token / usage 日志

### 验收标准

同一项目中至少出现：

```text
LOW task → cheap model
MEDIUM task → medium model
HIGH task → strong model
```

且切换过程不丢失任务状态。

---

## V0.3 — 验证与重试闭环

### 目标

解决“AI 说完成但实际没完成”。

### 功能

- Checker
- Reviewer
- acceptance criteria
- Retry
- 最大重试次数
- BLOCKED 状态
- 模型升级机制

默认升级示例：

```text
MEDIUM fail
→ MEDIUM retry
→ HIGH
```

### 验收标准

故意制造错误修改，系统能够识别 FAIL，而不是错误进入 PASSED。

---

## V0.4 — VS Code 轻量插件

### 目标

让日常操作不必一直使用 CLI。

### 功能

侧栏显示：

- 当前 Project；
- 当前 Stage / Step；
- Task 状态；
- 模型等级；
- 当前 Executor；
- 日志；
- Diff；
- Tests。

按钮：

- Continue
- Pause
- Retry
- Stop

### 原则

VS Code 只做 UI，不复制 Core 逻辑。

---

## V0.5 — GitHub 工程闭环

### 目标

把 GitHub 作为远程事实来源和云端补充执行层。

### 功能

- Branch / Commit 管理
- Push
- GitHub Actions 状态读取
- Test / Build workflow
- Artifact
- Android APK 等构建产物支持
- 可选 Git worktree

### 验收标准

本地完成代码任务后，GitHub Actions 能自动测试 / 构建，并把结果同步回状态。

---

## V0.6 — 手机控制

### 目标

不自建服务器的情况下，让手机能查看和触发部分任务。

### 第一阶段

直接依赖 GitHub App：

- 查看 Commit；
- 查看 Actions；
- 查看 Artifact；
- 查看 PR。

### 第二阶段

支持 Issue Command：

```text
/autodev status
/autodev continue
/autodev retry <task>
/autodev pause
```

### 第三阶段（可选）

开发薄 PWA，只负责状态展示和控制，不承担开发环境。

---

## V0.7 — 自动复杂度判断

### 目标

从固定规则进一步升级为半自动模型路由。

### 特征

- 文件数量；
- 代码影响范围；
- 是否修改核心架构；
- 是否涉及状态系统；
- 历史失败次数；
- 是否涉及安全 / 数据迁移；
- 测试覆盖情况。

输出：

```text
LOW / MEDIUM / HIGH
```

必须显示路由原因。

---

## V0.8 — 成本优化

### 功能

- Token 统计
- 不同模型任务成功率
- Retry 成本
- High 使用比例
- 全 High 成本估算 vs 实际成本
- Context Budget
- 自动上下文裁剪

---

## V0.9 — 自适应路由

根据历史任务统计：

```text
Task type
→ Model
→ Success / Fail
→ Retry count
→ Cost
```

逐步调整默认 Router。

例如：

```text
某类任务 MEDIUM 90% 一次成功
→ 不再默认 HIGH
```

或：

```text
某类任务 MEDIUM 连续高失败率
→ 默认升级 HIGH
```

---

## V1.0 — 第一版正式发布

### 必备能力

- Project / Stage / Step / Task
- 持久化状态
- 多模型 Router
- Planner / Executor / Checker / Reviewer
- Retry / Blocked / Resume
- Git 验证
- 测试 / Build 验证
- Handoff
- Context Manager
- CLI
- VS Code UI
- GitHub Actions
- 手机查看 / 基础控制
- Token 使用统计

### 不作为 V1.0 阻塞项

- 云端服务器；
- 多用户；
- Agent Swarm；
- 企业权限；
- Jira / Slack；
- 自建 Sandbox 平台。

---

# 当前立即开发顺序

建议从以下 10 个任务开始：

1. 建立 Python 包骨架。
2. 定义 Project / Stage / Step / Task 数据模型。
3. 定义状态枚举和状态迁移规则。
4. 实现 `.autodev/` 初始化。
5. 实现 `plan.yaml` 读取。
6. 实现规则 Router。
7. 定义 Runner 抽象接口。
8. 实现一个 MockRunner。
9. 实现 Git diff Checker。
10. 实现 `autodev start / status / resume`。

完成这十步后，再接第一个真实 Coding Agent。
