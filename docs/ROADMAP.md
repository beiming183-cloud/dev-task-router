# Dev Task Router 开发路线图

## 总原则

按“先闭环、再智能、最后做界面”的顺序推进。

不要一开始做复杂 UI、服务器、多用户和 Agent Swarm。第一目标是让一个真实任务可以：

```text
读取计划 → 执行任务 → 检查结果 → 保存状态 → 继续下一步
```

---

## V0.1 — 最小可运行闭环 ✅

### 目标

先证明 Workflow Core 能稳定运行，不在第一版同时塞入模型路由、Git 验证和 UI。

### 已完成

- `autodev init`
- `autodev plan`
- `autodev start`
- `autodev status`
- `autodev pause`
- `autodev resume`
- `.autodev/project.yaml`
- `.autodev/plan.yaml`
- `.autodev/state.json`
- `READY / RUNNING / PAUSED / FAILED / PASSED` 工作流状态
- `PENDING / RUNNING / FAILED / PASSED` 任务状态
- 单一 `CommandExecutor`
- argv 命令执行，不使用 `shell=True`
- 每个 Task 可配置 `checks`
- attempts / last_error / started_at / finished_at 持久化
- plan/state 一致性保护
- 缺失命令可靠进入 FAILED
- FAILED 状态不会被 `autodev start` 静默重试
- pytest 测试集
- GitHub Actions 项目自身 CI

### 验证结果

```text
本地 pytest       → 6 passed
GitHub Actions    → success
init/start/status → PASSED
```

### V0.1 有意不做

- 真正的 LLM / Coding Agent 接入；
- LOW / MEDIUM / HIGH 实际模型路由；
- Project / Stage / Step 完整层级；
- 自动 retry；
- Reviewer；
- Git diff Checker；
- Handoff；
- VS Code UI；
- GitHub Actions 作为用户任务执行器。

这些功能不塞进 V0.1，避免第一版范围膨胀。

---

## V0.2 — 任务层级与真正的多模型路由

### 目标

从“任务能可靠跑”升级到“不同任务能交给不同等级的模型”，开始实际解决 Token / 强模型额度浪费问题。

### 功能

- Project → Stage → Step → Task 数据层级
- `models.yaml`
- `LOW / MEDIUM / HIGH / NONE` 明确枚举
- 规则 Router
- 不同等级映射不同模型 / Executor
- Executor 抽象接口
- Planner 与 Executor 分离
- Handoff 文件
- 每个 Task 记录计划模型等级与实际执行器
- 初步 usage 日志
- 保持 V0.1 flat task plan 的兼容读取或提供迁移工具

### 验收标准

同一项目中至少能表达并执行：

```text
Stage: architecture
  HIGH task

Stage: implementation
  MEDIUM task
  LOW task

Stage: test
  NONE task
```

并且切换执行器后状态不丢失，重新打开项目后能够继续。

---

## V0.3 — 验证、重试与模型升级闭环

### 目标

解决“AI 说完成但实际没完成”。

### 功能

- Checker
- Git diff 检查
- Reviewer
- acceptance criteria
- Retry
- 最大重试次数
- BLOCKED 状态
- 模型升级机制
- 失败原因结构化记录

默认升级示例：

```text
MEDIUM fail
→ MEDIUM retry
→ HIGH
```

### 验收标准

故意制造错误修改，系统能够识别 FAIL，而不是错误进入 PASSED；超过最大重试次数后进入 BLOCKED。

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

V0.1 已完成。下一阶段按下面顺序进入 V0.2：

1. 定义 Project / Stage / Step / Task 层级模型。
2. 定义 `ModelLevel = NONE / LOW / MEDIUM / HIGH`。
3. 实现兼容 flat task plan 的层级 Plan Loader。
4. 建立 `models.yaml`。
5. 实现 RuleRouter。
6. 抽象 Executor 接口，并让现有 CommandExecutor 实现它。
7. 加入 Handoff Writer。
8. 在 state 中记录 stage / step / requested model / executor。
9. 增加 Router 与恢复流程测试。
10. 再接第一个真实模型执行器。
