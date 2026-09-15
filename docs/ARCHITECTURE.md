# Dev Task Router 架构说明

## 1. 核心定位

Dev Task Router 是 Coding Agent 之上的轻量编排层。

```text
User / VS Code / CLI
        │
        ▼
Dev Task Router Core
        │
        ├─ Planner
        ├─ Router
        ├─ Workflow Engine
        ├─ Runner
        ├─ Checker
        ├─ Reviewer
        ├─ State Manager
        └─ Context Manager
        │
        ▼
Codex / Claude Code / Gemini CLI / Aider
        │
        ▼
Git Repository
```

---

## 2. 模块边界

### Planner

只负责把目标拆成结构化任务，不直接修改代码。

### Router

只负责根据 Task Type / Complexity 选择抽象模型等级，不关心实际供应商。

### Runner

负责调用具体 Coding Agent。

### Checker

负责读取真实工程结果，不进行主观审查。

### Reviewer

负责基于 Task、Diff、Tests 做独立审核。

### State Manager

负责状态持久化和恢复。

### Context Manager

负责控制每个模型实际读取多少上下文。

---

## 3. 数据层级

```text
Project
└─ Stage
   └─ Step
      └─ Task
```

### Project

代表完整仓库或完整开发目标。

### Stage

代表一个相对独立的大阶段，例如：

- Architecture
- Cursor System
- Regression
- Build

### Step

Stage 内的功能步骤。

### Task

最小可执行、可验证、可重试单元。

一个 Task 应尽量在一次 Runner 调用中完成。

---

## 4. Task 建议字段

```yaml
id: semantic_cursor_move
title: 实现语义光标移动
type: complex_code
status: ready
model_level: high
executor: auto
attempt: 0
max_attempts: 3

depends_on:
  - cursor_core

relevant_files:
  - src/CursorController.kt
  - src/SelectionState.kt

acceptance:
  - 左右移动遵守语义边界
  - 不破坏 AC
  - 不破坏 DEL
  - 相关测试通过
```

---

## 5. 状态迁移

允许的主路径：

```text
CREATED
→ PLANNING
→ READY
→ RUNNING
→ CHECKING
→ REVIEWING
→ PASSED
```

允许中断到：

```text
PAUSED
FAILED
BLOCKED
CANCELLED
```

恢复原则：

- PAUSED → READY / RUNNING
- FAILED → READY（retry）
- BLOCKED → READY（人工处理后）

禁止直接：

```text
RUNNING → PASSED
```

必须经过 Checker，必要时经过 Reviewer。

---

## 6. Runner 抽象

```python
class Runner:
    def run(self, task, context, model) -> RunResult:
        ...
```

RunResult 至少包含：

```text
success
exit_code
stdout
stderr
started_at
finished_at
model
executor
usage
```

Runner 不负责判断代码是否正确。

---

## 7. Checker 抽象

```python
class Checker:
    def check(self, task, before_state, after_state) -> CheckResult:
        ...
```

可组合多个检查器：

```text
GitDiffChecker
CommandExitChecker
TestChecker
ArtifactChecker
CommitChecker
```

---

## 8. Reviewer 抽象

Reviewer 应尽量只读。

输入：

```text
Task
Acceptance Criteria
Diff
Tests
Handoff
```

输出：

```text
PASS
```

或：

```text
FAIL
issues[]
fix_scope
```

---

## 9. Router 抽象

第一版：

```python
TASK_LEVEL = {
    "repo_scan": "LOW",
    "simple_edit": "LOW",
    "normal_code": "MEDIUM",
    "architecture": "HIGH",
    "complex_code": "HIGH",
    "test_run": "NONE",
}
```

实际模型映射单独配置。

这样 Workflow 不绑定 GPT、Claude 或 Gemini。

---

## 10. Context Manager

目标不是“给模型越多内容越好”，而是提供足够完成当前 Task 的最小上下文。

默认顺序：

```text
Task
→ Acceptance
→ Handoff
→ Relevant Files
→ Relevant Tests
→ Recent Diff
→ 必要时扩展搜索
```

上下文扩大必须有理由并记录到日志。

---

## 11. 事实优先级

当不同状态冲突时，优先级建议：

```text
Git / Filesystem / Test Result
        >
Checker Result
        >
state.json
        >
模型文字输出
```

例如 state.json 显示 PASSED，但对应 Commit 不存在，应标记状态冲突，而不是继续执行。

---

## 12. 本地与 GitHub 的职责

### 本地

主要负责：

- Coding Agent；
- 本地代码修改；
- 快速测试；
- AutoDev Core。

### GitHub

主要负责：

- 持久 Git 历史；
- CI；
- Build；
- Artifact；
- 手机查看；
- 后期远程触发。

因此不需要先搭独立服务器。

---

## 13. 未来兼容性

Core 的长期目标是保持以下接口稳定：

```text
Planner API
Router API
Runner API
Checker API
Reviewer API
State API
```

只要这些边界稳定，未来可以新增：

- 新模型；
- 新 Agent；
- VS Code；
- JetBrains；
- MCP；
- GitHub Actions；
- PWA；

而不需要推倒 Core。
