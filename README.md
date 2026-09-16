# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由 Plugin。

项目主线是 **ChatGPT / Codex Plugin + Skills**。它不重新做 AI IDE，而是把开发目标拆成可执行 Task；在真实仓库可用时先读取相关 GitHub 事实，再判断工程难度，最后根据当前运行环境选择模型路线。

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实（需要时）
  ↓
Project → Stage → Step → Task
  ↓
内容 + 真实影响范围
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
Execution Surface
  ↓
Chat / Codex / Work 的具体模型路线
```

**难度和模型是两层概念。** `HIGH` 表示任务本身复杂，并不等于某个固定模型 family。

## V0.6 GitHub Repository Context

当仓库事实会改变拆解或难度判断时，Plugin 先用 `inspect-repository` 获取紧凑证据：

```text
repository / branch / commit
相关实现文件
相关测试
相关 PR / changed files / diff
当前 CI/check 状态
少量 verified facts / evidence tags
```

默认不会把整个仓库无差别塞进上下文。仓库证据尽量锚定到 commit SHA；如果 branch head 变化，应刷新依赖旧 commit 的 scope / diff / CI 判断。

用户要求描述**目标状态**，GitHub 证据描述**当前实现状态**。两者冲突时同时保留，不把目标要求误写成当前事实。

Python reference core 新增：

```text
RepositoryContext
.autodev/repo-context.yaml
autodev repo-context --import <yaml/json>
autodev repo-context [--json]
```

Repository evidence 可以修正 Difficulty，例如真实跨模块范围、`auth`、`migration`、`core-state`、`public-api`、`compatibility` 等已验证标签可以揭示“看起来只改一行、实际风险很高”的任务。

## Difficulty 分类

分类器综合：

- blast radius；
- architecture coupling；
- ambiguity / design burden；
- state / lifecycle / concurrency；
- reversibility；
- verification burden；
- cross-module / public interface；
- security / auth / migration / release / compatibility；
- 真实 relevant/changed files 与 module roots；
- 相关测试和 CI evidence。

输出：

```text
Difficulty
Score
Confidence
Reason
Factors
Traits
```

仓库很大本身不会让任务变 HIGH；只使用与当前目标相关的范围。

## Surface 路由

当前 Chat 映射：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记可用池：

```text
families: lunar / terra / sol / astra
efforts:  low / medium / high
```

项目**不会擅自猜**这些 family 的强弱顺序。未配置 family-to-difficulty 时返回 `unresolved` + candidate pool。

## 失败后重新分类

第一次直接按预测难度分配，不做 weak-first。

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

这表示原始复杂度估计可能偏低。权限、凭据、网络、限流、工具不可用等基础设施问题不应该被当成“任务更难”。

## Plugin 结构

```text
.agents/plugins/marketplace.json

plugins/dev-task-router/
├── .codex-plugin/plugin.json
├── README.md
└── skills/
    ├── index/SKILL.md
    ├── inspect-repository/SKILL.md
    ├── decompose-project/SKILL.md
    ├── classify-task/SKILL.md
    ├── route-model/SKILL.md
    └── create-handoff/SKILL.md
```

当前仍是 **skill-only Plugin**：不要求自建服务器、数据库、MCP server 或 VS Code Extension。

## 六个核心 Skills

- **index**：共享仓库证据、难度、失败重分类、验证与 handoff 规则；
- **inspect-repository**：定向读取 repo / branch / commit / files / tests / PR / diff / CI；
- **decompose-project**：结合真实范围拆 `Project → Stage → Step → Task`；
- **classify-task**：判断 Difficulty / Confidence / Traits；
- **route-model**：把难度映射到 Chat / Codex / Work；
- **create-handoff**：生成带 commit anchor 的最小必要上下文。

## Python Reference Core

Python Core 用于验证路由逻辑和以后接执行层，目前支持：

- Project / Stage / Step / Task；
- `RepositoryContext`；
- 内容级 `DifficultyClassifier` + repository evidence；
- `SurfaceCatalog / SurfaceDecision`；
- RuleRouter；
- `command` / `agent-cli` Executor；
- Checker / Reviewer；
- Retry / Escalation / BLOCKED；
- state / compact handoff / usage；
- GitHub Actions CI。

## 当前边界

Skill-only Plugin 可以读取已连接 GitHub 工具提供的事实、拆解、分类、给出 Surface 路由并生成 handoff，但不会假装已经替 ChatGPT 点击并切换模型。真正自动调用不同模型仍属于后续执行集成。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI 最小闭环
- **V0.2 ✅**：任务层级 + 多模型路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation + BLOCKED
- **V0.4 ✅**：ChatGPT / Codex Plugin + Skill 化
- **V0.5 ✅**：内容级复杂度判断 + Surface Router + 模型池配置
- **V0.6 🚧**：GitHub Plugin/App 联动与真实仓库上下文
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
- [`docs/V0.6.md`](docs/V0.6.md)

## 当前状态

**V0.6 candidate on `feature/v0.6-github-context`.**

最新 branch CI：**36 passed**。

---

Dev Task Router 最终回答的是：

> **真实仓库里这个目标会影响什么、应该拆成哪些任务、每个任务到底有多难、当前环境该怎样映射模型，以及失败后如何重新判断难度。**
