# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务拆解与路由插件。

从 V0.4 开始，项目的主要产品形态改为 **ChatGPT / Codex Plugin + Skills**，而不是 VS Code 插件。它的核心不是“再造一个 AI IDE”，而是把一个开发目标拆成不同难度的任务，让不同任务从一开始就使用匹配的模型档位。

## 核心思想

```text
开发目标
  ↓
Project → Stage → Step → Task
  ↓
判断真实难度
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
直接匹配对应模型档位
```

不是把所有任务先交给弱模型。

第一次就按预测难度分配：

```text
简单任务 → LOW
普通任务 → MEDIUM
复杂任务 → HIGH
确定性测试/构建 → NONE
```

如果模型任务因为真正的推理/实现问题失败，说明初始难度可能低估，下一次向上重新分类：

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

权限、凭据、限流、网络、工具不可用等基础设施失败不会被误判成“任务太难”。

## 当前 Plugin 结构

```text
.agents/plugins/marketplace.json

plugins/dev-task-router/
├── .codex-plugin/plugin.json
├── README.md
└── skills/
    ├── index/SKILL.md
    ├── decompose-project/SKILL.md
    ├── classify-task/SKILL.md
    └── create-handoff/SKILL.md
```

V0.4 使用 **skill-only** 方案，不要求自建服务器、数据库、MCP server 或 VS Code Extension。

## 四个核心 Skills

- **index**：统一难度、路由、失败重分类、验证与 handoff 规则；
- **decompose-project**：把开发目标拆成 `Project → Stage → Step → Task`；
- **classify-task**：单独判断任务难度并检查是否分配过高/过低；
- **create-handoff**：为下一模型/下一对话生成最小必要上下文。

## 难度定义

| Level | 典型任务 |
| --- | --- |
| `NONE` | test / build / formatter / artifact collection |
| `LOW` | 搜索文件、文档、小改动、机械整理 |
| `MEDIUM` | 普通功能、常规 Bug、多文件但边界明确的修改 |
| `HIGH` | 架构、核心状态语义、跨模块、高风险或强歧义任务 |

LOW / MEDIUM / HIGH 是**任务难度等级**，不是价格等级。

## V0.1–V0.3 Python Core

早期 Core 继续保留，作为可执行参考和后续执行集成基础，目前已经支持：

- Project / Stage / Step / Task；
- RuleRouter；
- `command` / `agent-cli` Executor；
- Checker / `require_diff`；
- Reviewer；
- Retry / Escalation / BLOCKED；
- state / handoff / usage 持久化；
- GitHub Actions CI。

V0.4 以后，产品入口优先发展 Plugin / Skills；Python Core 不删除。

## Plugin 能做什么

用户可以让项目拆解器：

```text
把这个开发目标拆成阶段和任务，并按难度分配模型档位。
```

它会输出：

- Stage / Step / Task；
- 每个 Task 的 `NONE / LOW / MEDIUM / HIGH`；
- 为什么这样分类；
- 验收条件；
- handoff 边界；
- 失败后应该升级到哪个档位。

## 当前边界

Skill-only Plugin 可以规划和推荐模型档位，但不会假装已经替 ChatGPT 切换当前模型。真正的自动模型切换/调用需要产品原生支持或后续独立执行集成。

## 路线图

- **V0.1 ✅**：状态机 + YAML 计划 + CLI 最小闭环
- **V0.2 ✅**：任务层级 + 多模型路由 + Executor + Handoff
- **V0.3 ✅**：Checker + Reviewer + Retry + Escalation + BLOCKED
- **V0.4 🚧**：ChatGPT / Codex Plugin + Skill 化
- **V0.5**：更强的自动任务拆解与复杂度判断
- **V0.6**：GitHub Plugin/App 联动与仓库上下文
- **V0.7**：Context / Handoff 优化
- **V0.8**：执行集成与真正的多模型自动调用
- **V1.0**：完整的轻量多模型开发编排插件

## 文档

- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/REFERENCES.md`](docs/REFERENCES.md)
- [`docs/V0.1.md`](docs/V0.1.md)
- [`docs/V0.2.md`](docs/V0.2.md)
- [`docs/V0.3.md`](docs/V0.3.md)
- [`docs/V0.4.md`](docs/V0.4.md)

## 当前状态

**V0.4 GPT Plugin 改造进行中：Skill-only plugin skeleton 已建立。**

---

Dev Task Router 最终回答的是：

> **大项目应该拆成什么任务、每个任务到底有多难、应该直接交给哪个模型，以及失败后应该如何重新判断难度。**
