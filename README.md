# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务编排工具。

它不重新做一个 AI IDE，而是在 Codex、Claude Code、Gemini CLI、Aider 等现有 Coding Agent 之上增加一层轻量 Workflow Layer：把大任务拆成可执行的小任务，根据复杂度选择不同模型和执行器，用确定性检查与独立 Reviewer 验证结果，并保存状态供后续继续。

## 为什么做这个项目

- 简单任务和复杂任务都使用强模型，会浪费 Token 和高级模型额度；
- 大任务全部塞进一个对话，容易跑偏、漏步骤；
- AI 说“完成”不等于真的改了代码或跑过测试；
- 中断或换模型后，经常需要重新解释大量上下文；
- 便宜模型失败后，希望自动升级，而不是一开始所有任务都用最强模型；
- 希望手机和电脑都能参与，但不想先维护复杂服务器。

## 当前核心流程

```text
Project → Stage → Step → Task
                 ↓
        RuleRouter / Model Profile
                 ↓
              Executor
                 ↓
              Checker
                 ↓
          fail? → Retry
                    ↓
                 Escalate
                    ↓
                 BLOCKED
                 ↓ pass
             Reviewer（可选）
                 ↓
                PASS
```

## 当前能力

- **Project → Stage → Step → Task** 层级计划；
- 兼容 V0.1 flat task plan；
- `NONE / LOW / MEDIUM / HIGH` 模型等级；
- `PLANNER / EXECUTOR / REVIEWER` 角色；
- `models.yaml` 模型 Profile；
- 基于任务类型的 RuleRouter；
- Executor 抽象接口与 Registry；
- 本地 `command` Executor；
- 通用 `agent-cli` Executor；
- `checks` 确定性检查；
- `require_diff` Git 工作区变化 Gate；
- `max_attempts` 自动 Retry；
- `LOW → MEDIUM → HIGH` 模型升级；
- `BLOCKED` 状态；
- 独立 Reviewer Gate；
- acceptance criteria；
- `autodev retry <task>` 人工重开任务；
- `state.json` / `handoff.md` / `usage.jsonl` 持久化；
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

`models.yaml` 再把等级映射到具体 Provider、Model 和 Executor。

## Retry / Escalation 示例

```yaml
- id: implement-feature
  title: Implement feature
  kind: normal_code
  max_attempts: 3
  escalate_after: 2
  prompt: Implement the feature.
```

若 `normal_code` 默认是 `MEDIUM`：

```text
attempt 1 → MEDIUM
attempt 2 → MEDIUM
attempt 3 → HIGH
```

重试预算耗尽后进入 `BLOCKED`，不会无限循环。

## Reviewer 示例

```yaml
- id: semantic-selection
  title: Implement semantic selection
  kind: complex_code
  prompt: Implement semantic selection.
  review: true
  review_level: HIGH
  acceptance:
    - Existing delete behavior is unchanged
    - History behavior is unchanged
    - New tests pass
```

Reviewer 是一次独立调用，最终必须输出机器可解析的 `PASS` 或 `FAIL`。Reviewer FAIL 会重新进入 Retry / Escalation。

## CLI

```text
autodev init
autodev plan
autodev models
autodev start
autodev pause
autodev resume
autodev retry <task> [--run]
autodev status
autodev handoff
```

## 设计原则

1. **轻量优先**：插件负责调度，不复制完整 AI IDE。
2. **本地优先**：不要求 VPS、Redis、PostgreSQL 或容器集群。
3. **真实结果优先**：测试、Git 状态和 Reviewer Gate 高于 AI 的口头完成声明。
4. **强模型按需使用**：先让合适的便宜模型尝试，失败后再升级。
5. **状态必须持久化**：可以暂停、恢复、重试、换模型。
6. **先做可靠闭环，再做复杂 UI 和自动智能**。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + 单执行器 + CLI 最小闭环
- **V0.2 ✅**：任务层级 + 多模型路由 + Executor 抽象 + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + 模型升级 + BLOCKED
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
- [`docs/V0.3.md`](docs/V0.3.md) — V0.3

## 当前状态

**Status: V0.3 implemented on `feature/v0.3-verification`, pending final CI / merge.**

当前完整测试集：**21 tests**。

---

Dev Task Router 的核心不是“再造一个会写代码的 AI”，而是回答：

> **做什么、谁来做、用哪个模型做、怎么证明做完、失败后怎么恢复与升级。**
