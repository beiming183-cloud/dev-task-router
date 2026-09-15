# Dev Task Router

> 中文名：**项目拆解器**

一个轻量级、多模型、可恢复、可验证的 AI 开发任务编排工具。

它不试图重新做一个 AI IDE，也不自己承担所有编码工作，而是工作在 Codex、Claude Code、Gemini CLI、Aider 等现有 Coding Agent 之上：把一个大开发任务拆成可执行的小步骤，根据复杂度分配不同等级的模型，自动检查真实结果，并保存进度以便随时继续。

## 为什么做这个项目

长时间使用 AI 编程工具时，常见几个问题：

- 简单任务和复杂任务都使用同一个强模型，浪费额度和 Token；
- 一个大任务塞进单次对话，模型容易跑偏或遗漏步骤；
- AI 会说“已经完成”，但实际上可能没有代码修改、测试或构建产物；
- 中途中断、切换模型或重新打开项目后，需要重新解释大量上下文；
- 规划、实现、测试、审核混在一个上下文中，既浪费 Token，也不利于定位错误；
- 希望电脑和手机都能查看进度，但又不想先学习和维护复杂服务器。

Dev Task Router 的目标，就是在现有 AI 编程工具上增加一层轻量的 **Workflow Layer（工作流层）**。

## 核心流程

```text
用户目标
   ↓
Planner：拆分 Project / Stage / Step / Task
   ↓
Router：按任务复杂度选择 LOW / MEDIUM / HIGH
   ↓
Runner：调用 Codex / Claude Code / Gemini / Aider
   ↓
Checker：检查 Git diff / test / build / artifact
   ↓
Reviewer：独立审核结果
   ↓
State：保存状态和 HANDOFF
   ↓
下一任务
```

## 核心能力

- **任务拆分**：把大型开发需求拆成 Stage → Step → Task。
- **多模型路由**：简单任务使用低成本模型，复杂任务使用强模型。
- **Planner / Executor / Reviewer 分离**：避免一个模型既制定方案、又执行、又自己宣布通过。
- **真实完成验证**：以 Git diff、测试、构建、Commit、Artifact 为完成依据。
- **断点恢复**：关闭工具、切换模型后可以从上一次状态继续。
- **Handoff 压缩上下文**：模型切换时只读取必要状态，不重复消耗整个历史上下文。
- **可插拔执行器**：未来可以同时接入 Codex、Claude Code、Gemini CLI、Aider 等。
- **本地优先**：第一阶段不要求 VPS、数据库、Redis 或 Docker 集群。
- **GitHub Actions 补充云执行**：后续用 GitHub Actions 承担测试、构建、APK 等无需本机持续在线的任务。
- **手机 + 电脑协同**：电脑负责本地开发，手机通过 GitHub / 后续轻量界面查看和控制任务。

## 模型等级

第一版不做复杂 AI 分类，先采用稳定的规则路由：

| 等级 | 典型任务 |
| --- | --- |
| `LOW` | 文件搜索、文档、Handoff、Commit Message、小修改 |
| `MEDIUM` | 普通功能开发、普通 Bug、一般测试错误分析 |
| `HIGH` | 架构设计、复杂状态逻辑、疑难 Bug、最终 Review |
| `NONE` | 纯测试、构建等无需模型的步骤 |

实际模型与等级解耦，例如：

```yaml
models:
  low: gemini
  medium: gpt-medium
  high: gpt-high
```

以后更换模型时，只需要修改配置，不需要改工作流。

## 设计原则

1. **轻量优先**：插件负责调度，不重新实现完整 AI IDE。
2. **本地优先**：先让普通电脑直接使用，不要求服务器知识。
3. **Git 是事实来源**：AI 的文字回复不能代表任务完成。
4. **强模型只做值得做的事**：把昂贵推理集中在架构、复杂实现和审核。
5. **状态必须持久化**：每个任务都可以暂停、重试和恢复。
6. **先做闭环，再做智能**：先把 Plan → Run → Check → Review 跑通，再做自动复杂度判断。

## 计划中的项目结构

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

## 当前路线

- **V0.1**：状态机 + YAML 计划 + 单执行器 + CLI 最小闭环
- **V0.2**：LOW / MEDIUM / HIGH 多模型路由
- **V0.3**：Checker + Reviewer + Retry + 模型升级机制
- **V0.4**：VS Code 轻量面板
- **V0.5**：GitHub / Actions / Artifact / Build
- **V0.6**：手机控制与 GitHub 命令
- **V1.0**：完整的多模型、可恢复、可验证 AI 开发编排工具

详细设计见：

- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — 完整项目方案
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — 分阶段开发路线
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 架构与模块边界

## 当前状态

**Status: Planning / V0.1 not started**

第一阶段的唯一目标：

> 做出 `autodev start` 的最小闭环：读取计划 → 选择模型 → 调用执行器 → 检查结果 → 保存状态 → 进入下一任务。

---

Dev Task Router 的核心不是“再造一个会写代码的 AI”，而是回答五个问题：

> **做什么、谁来做、用哪个模型做、怎么证明做完、失败后从哪里继续。**
