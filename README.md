# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务编排工具。

它不重新做一个 AI IDE，而是在 Codex、Claude Code、Gemini CLI、Aider 等现有 Coding Agent 之上增加一层轻量 Workflow Layer：把大任务拆成可执行的小任务，根据复杂度选择不同模型和执行器，检查真实结果，并保存状态供后续继续。

## 为什么做这个项目

- 简单任务和复杂任务都使用强模型，会浪费 Token 和高级模型额度；
- 大任务全部塞进一个对话，容易跑偏、漏步骤；
- AI 说“完成”不等于真的改了代码或跑过测试；
- 中断或换模型后，经常需要重新解释大量上下文；
- 规划、执行、测试和审核混在一起，不利于定位错误；
- 希望手机和电脑都能参与，但不想先维护复杂服务器。

## 核心流程

```text
Project
  ↓
Stage
  ↓
Step
  ↓
Task
  ↓
RuleRouter → NONE / LOW / MEDIUM / HIGH
  ↓
Model Profile → provider / model / executor
  ↓
Executor → command / agent-cli / future adapters
  ↓
checks + state + handoff + usage
```

## 当前能力

- **Project → Stage → Step → Task** 层级计划；
- 兼容 V0.1 flat task plan；
- `NONE / LOW / MEDIUM / HIGH` 模型等级；
- `PLANNER / EXECUTOR` 任务角色；
- `models.yaml` 模型 Profile；
- 基于任务类型的 RuleRouter；
- Task 显式 level 覆盖默认路由；
- Executor 抽象接口与 Registry；
- 本地 `command` Executor；
- 通用 `agent-cli` Executor，可调用外部 Coding Agent CLI；
- `state.json` 持久化；
- `handoff.md` 自动生成；
- `usage.jsonl` 初步执行记录；
- `pause / resume`；
- GitHub Actions 项目自身 CI。

## 默认模型路由

| Task kind | Level |
| --- | --- |
| `repo_search` / `docs` / `handoff` / `simple_edit` | `LOW` |
| `normal_code` / `normal_debug` | `MEDIUM` |
| `architecture` / `planning` / `complex_code` / `hard_debug` / `review` | `HIGH` |
| `test` / `build` | `NONE` |
| 未知类型 | `MEDIUM` |

`models.yaml` 再把等级映射到实际 Provider、Model 和 Executor：

```yaml
profiles:
  NONE:
    provider: local
    model: none
    executor: command

  LOW:
    provider: local
    model: low
    executor: command

  MEDIUM:
    provider: local
    model: medium
    executor: command

  HIGH:
    provider: local
    model: high
    executor: command
```

要接外部 Coding Agent，可以把某个 Profile 改成 `agent-cli`，并配置 argv 模板。详见 [`docs/V0.2.md`](docs/V0.2.md)。

## CLI

```text
autodev init
autodev plan
autodev models
autodev start
autodev pause
autodev resume
autodev status
autodev handoff
```

## 设计原则

1. **轻量优先**：插件负责调度，不复制完整 AI IDE。
2. **本地优先**：不要求 VPS、Redis、PostgreSQL 或容器集群。
3. **Git / 测试结果才是事实**：AI 的文字回复不能代表工程完成。
4. **强模型只做值得做的事**：架构、复杂实现、疑难问题和最终审核。
5. **状态必须持久化**：可以暂停、恢复、换模型。
6. **先做可靠闭环，再加自动智能**。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + 单执行器 + CLI 最小闭环
- **V0.2 ✅**：任务层级 + 多模型路由 + Executor 抽象 + Handoff
- **V0.3**：Checker + Reviewer + Retry + 模型升级机制
- **V0.4**：VS Code 轻量面板
- **V0.5**：GitHub / Actions / Artifact / Build 工程闭环
- **V0.6**：手机控制与 GitHub 命令
- **V1.0**：完整的多模型、可恢复、可验证 AI 开发编排工具

## 文档

- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — 完整项目方案
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — 分阶段路线
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 架构与模块边界
- [`docs/REFERENCES.md`](docs/REFERENCES.md) — 设计借鉴
- [`docs/V0.1.md`](docs/V0.1.md) — V0.1
- [`docs/V0.2.md`](docs/V0.2.md) — V0.2

## 当前状态

**Status: V0.2 complete on `main`.**

V0.2 本地与 GitHub Actions：**14 passed**。

---

Dev Task Router 的核心不是“再造一个会写代码的 AI”，而是回答：

> **做什么、谁来做、用哪个模型做、怎么证明做完、失败后从哪里继续。**
