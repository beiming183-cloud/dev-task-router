# 项目拆解器 Plugin

这是 Dev Task Router 的轻量 OpenAI Plugin 包。

V0.4 采用 **skill-only** 设计：不包含 MCP server、不要求自建服务器、不要求数据库，也不绑定 VS Code。

## 核心能力

- 把软件开发目标拆成 `Project → Stage → Step → Task`；
- 根据工程难度直接分类为 `NONE / LOW / MEDIUM / HIGH`；
- 初次任务直接使用匹配难度的模型档位，而不是统一从弱模型开始；
- 若模型任务因真实实现/推理问题失败，把失败视为难度低估证据：`LOW → MEDIUM → HIGH`；
- 基础设施、权限、限流、网络等失败不会触发错误的难度升级；
- 为每个任务生成可验证 acceptance criteria；
- 在模型/对话切换时生成最小 handoff。

## Skills

- `index`：共享难度、路由、失败升级、验证和 handoff 规则；
- `decompose-project`：把完整开发目标拆成分阶段计划；
- `classify-task`：单独判断任务真实难度与后续升级路径；
- `create-handoff`：生成下一模型所需的最小上下文。

## Plugin manifest

```text
plugins/dev-task-router/.codex-plugin/plugin.json
```

仓库级 marketplace：

```text
.agents/plugins/marketplace.json
```

结构参考 OpenAI 当前 role-specific plugin 模板，Skill-only 版本不声明 `.app.json` 或 `.mcp.json`。

## 设计边界

Skill 本身负责：拆解、分类、路由建议、失败重分类、验收定义和 handoff。

Skill 本身不会假装已经切换 ChatGPT 当前模型。真正自动切换/调用不同模型需要产品侧支持或后续独立执行集成。
