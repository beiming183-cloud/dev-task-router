# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由 Plugin。

项目主线是 **ChatGPT / Codex Plugin + Skills**。它不重新做 AI IDE，而是把开发目标拆成可执行 Task，先判断真实工程难度，再根据当前运行环境选择合适的模型路线。

## 核心链路

```text
开发目标
  ↓
Project → Stage → Step → Task
  ↓
内容级难度判断
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
Execution Surface
  ↓
Chat / Codex / Work 的具体模型路线
```

**难度和模型是两层概念。**

`HIGH` 表示任务本身复杂，并不等于某个固定模型 family。

## V0.5 难度分类

分类器会综合：

- blast radius；
- architecture coupling；
- ambiguity / design burden；
- state / lifecycle / concurrency；
- reversibility；
- verification burden；
- cross-module / public interface；
- security / auth / migration / release / compatibility 等高风险信号。

输出包括：

```text
Difficulty
Score
Confidence
Reason
Factors
Traits
```

所以一个看起来只有“一行修改”的任务，如果涉及认证、核心状态或跨模块兼容，也可以被识别为 HIGH。

## Surface 路由

`autodev init` 会生成：

```text
.autodev/surfaces.yaml
```

当前 Chat 映射：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记的可用池：

```text
families: lunar / terra / sol / astra
efforts:  low / medium / high
```

项目**不会擅自猜**这些 family 的强弱顺序。未配置某个难度对应哪个 family 时，返回 `unresolved` + candidate pool；以后只需更新 Surface 配置，不需要改难度分类器。

## 失败后重新分类

第一次仍然直接按预测难度分配，不做 weak-first。

真实实现/推理失败时：

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

这表示原始复杂度估计可能偏低。

权限、凭据、网络、限流、工具不可用等基础设施问题不应该被当成“任务更难”。

## Plugin 结构

```text
.agents/plugins/marketplace.json

plugins/dev-task-router/
├── .codex-plugin/plugin.json
├── README.md
└── skills/
    ├── index/SKILL.md
    ├── decompose-project/SKILL.md
    ├── classify-task/SKILL.md
    ├── route-model/SKILL.md
    └── create-handoff/SKILL.md
```

当前仍然是 **skill-only Plugin**：不要求自建服务器、数据库、MCP server 或 VS Code Extension。

## 五个核心 Skills

- **index**：共享难度、路由、失败重分类、验证与 handoff 规则；
- **decompose-project**：自动拆 `Project → Stage → Step → Task`，并定义停止拆分条件；
- **classify-task**：判断 Difficulty / Confidence / Traits；
- **route-model**：把难度映射到 Chat / Codex / Work；
- **create-handoff**：为下一个模型/对话生成最小必要上下文。

## Python Reference Core

Python Core 继续保留，用于验证路由逻辑和以后接执行层。目前支持：

- Project / Stage / Step / Task；
- 内容级 `DifficultyClassifier`；
- `SurfaceCatalog / SurfaceDecision`；
- RuleRouter；
- `command` / `agent-cli` Executor；
- Checker / `require_diff`；
- Reviewer；
- Retry / Escalation / BLOCKED；
- state / handoff / usage 持久化；
- GitHub Actions CI。

## 当前边界

Skill-only Plugin 可以拆解、分类、给出 Surface 路由并生成 handoff，但不会假装已经替 ChatGPT 点击并切换模型。真正自动调用不同模型需要后续执行集成或产品原生能力。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI 最小闭环
- **V0.2 ✅**：任务层级 + 多模型路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation + BLOCKED
- **V0.4 ✅**：ChatGPT / Codex Plugin + Skill 化
- **V0.5 ✅**：内容级复杂度判断 + Surface Router + 模型池配置
- **V0.6**：GitHub Plugin/App 联动与真实仓库上下文
- **V0.7**：Context / Handoff 优化
- **V0.8**：API / 执行集成，实现真正的多模型自动调用
- **V1.0**：完整轻量多模型开发编排插件

## 文档

- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/REFERENCES.md`](docs/REFERENCES.md)
- [`docs/V0.1.md`](docs/V0.1.md)
- [`docs/V0.2.md`](docs/V0.2.md)
- [`docs/V0.3.md`](docs/V0.3.md)
- [`docs/V0.4.md`](docs/V0.4.md)
- [`docs/V0.5.md`](docs/V0.5.md)

## 当前状态

**V0.5 complete on `main`.**

完整回归：**29 passed**。

---

Dev Task Router 最终回答的是：

> **大项目应该拆成什么任务、任务到底有多难、当前环境应该怎样映射模型，以及失败后如何重新判断难度。**
