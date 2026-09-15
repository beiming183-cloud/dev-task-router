# Dev Task Router（项目拆解器）完整项目方案

## 1. 项目定位

Dev Task Router 是一个**轻量级、多模型、可恢复、可验证的 AI 开发任务编排工具**。

它不重新实现完整 AI IDE，也不自己承担所有编码工作，而是位于现有 Coding Agent 之上，负责：

```text
规划任务 → 判断复杂度 → 选择模型 → 调用执行器 → 检查结果 → 保存进度 → 进入下一步
```

目标用户是已经在使用 Codex、Claude Code、Gemini CLI、Aider 等工具，但希望：

- 复杂任务使用强模型；
- 简单任务使用便宜模型；
- 降低 Token / 额度浪费；
- 一个大项目能够连续执行而不是依赖单次对话；
- 中断后可以恢复；
- AI 必须用真实工程结果证明任务完成；
- 手机和电脑可以共同查看项目状态；
- 初期不需要学习服务器、Docker 集群、数据库运维。

---

## 2. 主要问题

### 2.1 单模型贯穿整个开发流程

传统方式往往是：

```text
高性能模型
  ↓
读仓库
  ↓
规划
  ↓
写代码
  ↓
改格式
  ↓
跑测试
  ↓
看日志
  ↓
写文档
  ↓
写 commit message
```

大量低难度操作也消耗高价值模型额度。

Dev Task Router 将其拆为：

```text
强模型：架构 / 复杂决策 / 疑难问题 / 最终审核
中模型：普通实现 / 普通修复
低成本模型：搜索 / 文档 / Handoff / 简单修改
无模型：纯测试 / 构建
```

### 2.2 AI 的“完成”缺乏工程证明

任务不能因为模型输出“已完成”就进入下一阶段。

至少需要根据任务类型检查：

- Git diff 是否存在；
- 测试是否真实执行；
- exit code 是否为 0；
- 构建产物是否存在；
- Commit 是否真实产生；
- CI 是否通过。

### 2.3 长任务依赖聊天上下文

聊天窗口不应充当状态机。

状态必须写入项目目录：

```text
.autodev/
├─ project.yaml
├─ plan.yaml
├─ state.json
├─ models.yaml
├─ rules.yaml
├─ handoff.md
├─ logs/
└─ runs/
```

### 2.4 切换模型需要重新读大量内容

每个阶段结束生成 Handoff，只保存：

- 当前项目目标；
- 已完成事项；
- 当前任务；
- 不可破坏的约束；
- 最新 Commit；
- 测试状态；
- 下一步所需文件。

新模型接手时优先读取 Handoff + 相关文件，而不是完整聊天历史。

---

## 3. 核心原则

### 3.1 插件必须轻

Dev Task Router 不内置大型运行环境。

它只负责：

- 任务调度；
- 状态保存；
- 模型选择；
- 调用外部 Agent；
- Git 状态读取；
- 测试结果判断；
- 日志记录；
- UI 展示。

### 3.2 本地优先

V1.0 之前不要求：

- VPS；
- Redis；
- PostgreSQL；
- Kubernetes；
- 多用户后端；
- 云端容器平台。

### 3.3 Git 是工程事实来源

插件状态只是缓存，Git / Test / Build 才是真实结果。

### 3.4 强模型只解决高价值问题

模型能力与任务难度对应，而不是整个项目固定使用一个模型。

### 3.5 Planner / Executor / Checker / Reviewer 分离

禁止把规划、执行、验证全部交给同一个角色。

### 3.6 状态必须可恢复

退出程序、关闭电脑或切换执行器后，能够根据 state.json 和 Git 状态继续。

---

## 4. 总体架构

```text
┌─────────────────────────┐
│       VS Code / CLI     │
│ 项目 / Stage / Step     │
│ 日志 / Diff / Tests     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      AutoDev Core       │
│                         │
│ Planner                 │
│ Router                  │
│ Workflow Engine         │
│ Runner                  │
│ Checker                 │
│ Reviewer                │
│ State Manager           │
│ Context Manager         │
└───────┬─────────┬───────┘
        │         │
        │         └──────── Git
        │
        ▼
┌─────────────────────────┐
│       Executors         │
│ Codex                   │
│ Claude Code             │
│ Gemini CLI              │
│ Aider                   │
└─────────────────────────┘
        │
        ▼
   当前项目工作区
```

后期增加：

```text
GitHub Actions
   ↑
   │
GitHub 仓库
   ↑
   │
手机查看 / 触发
```

---

## 5. 核心模块

## 5.1 Planner

职责：把用户目标拆成可执行计划。

输入：

- 用户需求；
- 项目结构；
- 关键约束；
- 当前 Git 状态；
- 可用测试命令。

输出：

```text
Project
  ↓
Stage
  ↓
Step
  ↓
Task
```

Planner 应为每个任务生成：

- id；
- title；
- type；
- dependencies；
- acceptance criteria；
- suggested model level；
- relevant files；
- risk level。

默认使用 HIGH，但只在项目开始、重大架构变化或重新规划时调用。

---

## 5.2 Router

第一版采用规则路由，不依赖额外 AI 判断。

建议默认映射：

| Task Type | Level |
| --- | --- |
| repo_scan | LOW |
| file_search | LOW |
| docs | LOW |
| handoff | LOW |
| commit_message | LOW |
| simple_edit | LOW |
| normal_code | MEDIUM |
| normal_debug | MEDIUM |
| test_analysis | MEDIUM |
| architecture | HIGH |
| planning | HIGH |
| complex_code | HIGH |
| hard_debug | HIGH |
| final_review | HIGH |
| test_run | NONE |
| build | NONE |

用户通过配置把抽象等级映射到真实模型：

```yaml
models:
  low:
    executor: gemini
    model: fast-model
  medium:
    executor: codex
    model: medium-model
  high:
    executor: codex
    model: high-model
```

第二阶段加入 AUTO：

```text
Task → Complexity Classifier → LOW / MEDIUM / HIGH
```

复杂度判断可参考：

- 涉及文件数量；
- 是否修改核心架构；
- 是否涉及状态管理；
- 历史失败次数；
- 是否为回归问题；
- 修改影响范围。

---

## 5.3 Runner

统一执行器接口：

```python
run_task(project, task, model, context) -> RunResult
```

具体实现：

- CodexRunner
- ClaudeRunner
- GeminiRunner
- AiderRunner

Core 不依赖具体模型和供应商。

Runner 需要记录：

- 实际命令；
- 开始 / 结束时间；
- exit code；
- stdout / stderr；
- 输入上下文；
- 模型信息；
- Token / 成本（若可获得）。

---

## 5.4 Checker

Checker 不听模型自己的结论，只读取实际工程结果。

### 代码任务

检查：

```text
git diff
```

是否有合理修改。

### 测试任务

检查：

```text
exit_code == 0
```

以及测试报告。

### 构建任务

检查：

- 构建命令退出码；
- 目标 Artifact 是否存在；
- 可选 SHA256。

### Commit

检查：

```text
HEAD != previous_HEAD
```

只有通过 Checker 才能进入 REVIEWING / PASSED。

---

## 5.5 Reviewer

Reviewer 输入：

- 原始 Task；
- Planner 方案；
- Git diff；
- 测试结果；
- 关键约束。

输出：

```text
PASS
```

或：

```text
FAIL
reason: ...
required_fix: ...
```

FAIL 后创建 Fix Task，重新进入 Executor → Checker → Reviewer。

建议最大自动重试次数：3。

超过上限进入 BLOCKED。

---

## 5.6 Workflow Engine

标准状态：

```text
CREATED
  ↓
PLANNING
  ↓
READY
  ↓
RUNNING
  ↓
CHECKING
  ↓
REVIEWING
  ↓
PASSED
```

异常状态：

```text
FAILED
BLOCKED
PAUSED
CANCELLED
```

每次状态改变立即写盘。

---

## 5.7 State Manager

建议目录：

```text
.autodev/
├─ project.yaml
├─ plan.yaml
├─ state.json
├─ models.yaml
├─ rules.yaml
├─ handoff.md
├─ logs/
└─ runs/
```

### project.yaml

```yaml
name: example-project

repo:
  branch: main

commands:
  test:
    - pytest
  build:
    - python -m build
```

### state.json

```json
{
  "project": "example-project",
  "current_stage": "core",
  "current_step": 2,
  "status": "RUNNING",
  "executor": "codex",
  "model_level": "MEDIUM",
  "attempt": 1,
  "last_commit": "abc123"
}
```

---

## 5.8 Context Manager

禁止默认把整个仓库交给模型。

上下文优先级：

1. 当前 Task；
2. acceptance criteria；
3. handoff.md；
4. 相关文件；
5. 相关测试；
6. 最近 Git diff；
7. 必要时才扩展到其他文件。

HIGH 模型也必须接受上下文预算限制。

---

## 5.9 Handoff

每个 Stage 完成后更新：

```text
.autodev/handoff.md
```

建议内容：

```text
项目：
当前 Stage：

已完成：
- ...

当前任务：
- ...

必须保持：
- ...

最新 Commit：
测试：
下一步建议读取文件：
```

目标：让不同模型之间的交接成本远低于重新读取完整历史。

---

## 6. 模型升级与降级

### 6.1 升级

例如普通任务默认 MEDIUM：

```text
MEDIUM
  ↓ FAIL
MEDIUM retry
  ↓ FAIL
HIGH
```

升级原因必须写入日志。

### 6.2 降级

如果 Planner 标记 HIGH，但执行前检测到只是安全的小改动，可以建议降为 MEDIUM / LOW。

第一版只提示，不自动降级。

---

## 7. Git 集成

每个 Task 开始前记录 HEAD。

流程：

```text
记录 checkpoint
  ↓
执行修改
  ↓
测试
  ↓
Checker
  ↓
Reviewer
  ↓
Commit
```

Commit 规范建议：

```text
autodev(<stage>): <task summary>
```

失败任务不自动提交到主开发分支。

后期支持 git worktree，把复杂 Stage 隔离到独立工作目录。

---

## 8. CLI

第一版必须先有 CLI，UI 只是它的壳。

```bash
autodev init
autodev plan
autodev start
autodev status
autodev pause
autodev resume
autodev retry
autodev review
```

### autodev init

创建 `.autodev/` 和基础配置。

### autodev plan

读取用户目标并生成计划。

### autodev start

开始当前 Task。

### autodev status

输出当前阶段、任务、模型、重试次数、Git 状态。

### autodev resume

从 state.json + Git 状态恢复。

---

## 9. VS Code 插件

V0.4 再做。

插件只展示 Core 状态，不复制核心逻辑。

侧栏示例：

```text
DEV TASK ROUTER

Project: example

✓ Architecture
✓ Base implementation
▶ Semantic selection      HIGH
○ Regression             MEDIUM
○ Build                  NONE
○ Final review           HIGH

[Continue] [Pause] [Retry]
```

详情页 Tabs：

- PLAN
- LOG
- DIFF
- TESTS

---

## 10. GitHub Actions 与手机协同

不自建服务器。

GitHub Actions 先承担：

- test；
- build；
- APK；
- Artifact；
- CI Gate。

电脑关机后这些工作仍然可以执行。

手机第一阶段直接通过 GitHub App 查看：

- Commit；
- PR；
- Actions；
- Artifact；
- 测试状态。

后续支持 Issue Command：

```text
/autodev continue
/autodev retry stage3
/autodev status
```

再后期可做薄 PWA，但 PWA 只负责控制和显示，不直接跑开发环境。

---

## 11. 安全设计

命令分级：

### 可自动执行

```text
git status
pytest
gradlew test
npm test
```

### 需要人工确认

```text
rm -rf
git reset --hard
force push
大规模删除
修改密钥或认证配置
```

默认保护：

```text
.git/
.env
.autodev/rules.yaml
用户配置的 protected paths
```

---

## 12. 回滚

每个任务开始记录 checkpoint。

失败后允许：

- 保留现场；
- 恢复到 checkpoint；
- 创建新 Fix Task。

V0.5 后优先使用 worktree 隔离复杂修改。

---

## 13. 日志与审计

每次运行：

```text
.autodev/runs/<run-id>/
├─ task.json
├─ prompt.md
├─ result.md
├─ commands.log
├─ tests.log
├─ diff.patch
└─ review.md
```

目标是能回答：

- 哪个任务用了哪个模型；
- 输入了哪些上下文；
- 执行了什么命令；
- 为什么失败；
- 为什么升级模型；
- 为什么最终判定 PASS。

---

## 14. Token 与成本统计

若执行器提供 usage，则记录：

```text
Task
Model
Input Tokens
Output Tokens
Result
Retry Count
```

未来展示：

```text
若全部使用 HIGH：估算 X
实际使用：Y
节省：Z%
```

这也是项目的重要核心价值之一。

---

## 15. 借鉴来源

### Aider

借鉴 Architect / Editor / Weak Model 的角色分离思想。

### LiteLLM

借鉴 Complexity Routing，即简单任务给便宜模型，复杂任务给强模型。

### OpenHands

借鉴 Task → Code → Test → Git → PR 的工程闭环，以及任务必须产生真实工程结果的理念。

### Roomote

借鉴 Task / Model / Status / Logs 的任务控制面板和远程任务思路，但不复制其完整服务端体系。

### GitHub Actions

作为早期无需自建服务器的云端 CI / Build / Artifact 执行层。

---

## 16. 技术栈

### Core

Python：

- Typer：CLI；
- Pydantic：数据模型；
- PyYAML：配置；
- subprocess / GitPython：Git 和外部命令。

### VS Code

TypeScript。

VS Code 插件不重新实现 Core，通过 CLI 或本地 IPC 与 Core 通信。

---

## 17. 计划目录

```text
dev-task-router/
├─ src/
│  ├─ planner/
│  ├─ router/
│  ├─ runner/
│  ├─ checker/
│  ├─ reviewer/
│  ├─ state/
│  ├─ context/
│  └─ git/
├─ executors/
│  ├─ codex.py
│  ├─ claude.py
│  ├─ gemini.py
│  └─ aider.py
├─ cli/
├─ vscode/
├─ workflows/
├─ tests/
└─ docs/
```

---

## 18. 明确不做的事情（V1.0 前）

- 自己训练模型；
- 自己托管大模型；
- VPS 必选；
- Redis / PostgreSQL；
- Kubernetes；
- 多用户权限系统；
- Slack / Discord / Jira；
- 完整 IDE；
- 多 Agent 同时改同一个 Branch；
- Agent Swarm；
- 自建云端 Sandbox 平台。

---

## 19. 最小成功标准

第一阶段只验证一个闭环：

```text
autodev start
  ↓
读取 plan.yaml
  ↓
获得当前 Task
  ↓
Router 选择模型等级
  ↓
Runner 调用一个 Coding Agent
  ↓
产生真实文件修改
  ↓
Checker 检查 Git diff / test
  ↓
保存 state.json
  ↓
进入下一 Task
```

这个闭环一旦稳定，后面的 VS Code、GitHub、手机控制都只是不同入口。

---

## 20. 最终产品定义

Dev Task Router 不是“另一个会写代码的 AI”。

它是：

> **AI 编程工具之上的 Workflow Layer。**

真正解决的问题是：

```text
做什么？
谁来做？
用哪个模型做？
做到什么标准？
怎么证明真的做完？
失败以后从哪里继续？
怎样减少昂贵模型消耗？
```
