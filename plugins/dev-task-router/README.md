# 项目拆解器 Plugin

这是 Dev Task Router 的轻量 OpenAI Plugin 包。

V0.6 继续保持 **skill-only**：不要求 MCP server、自建服务器、数据库或 VS Code。

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实（需要时）
  ↓
Project → Stage → Step → Task
  ↓
任务内容 + 真实影响范围
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
当前 Surface
  ↓
Chat / Codex / Work 的具体模型路由
```

难度与具体模型分开：`HIGH` 说明任务复杂，不代表某个固定模型家族。

## Skills

- `index`：共享难度、仓库证据、失败重分类、验证和 handoff 规则；
- `inspect-repository`：读取与任务相关的 repo / branch / commit / files / tests / PR / diff / CI，输出紧凑证据；
- `decompose-project`：结合已验证仓库范围自动拆 Stage / Step / Task；
- `classify-task`：输出 Difficulty / Reason / Confidence / Traits；
- `route-model`：把难度映射到 Chat / Codex / Work；
- `create-handoff`：生成带 commit anchor 的最小上下文。

## GitHub 上下文原则

不扫描整个仓库再塞给下一模型。默认只保留：

```text
repository / branch / commit
相关实现文件
相关测试
已有 PR/diff 中真正相关的 changed files
当前 CI/check 状态
少量 verified facts
```

如果 branch head 变化，应该刷新依赖旧 commit 的 diff / CI / scope 判断。

用户要求描述目标状态；GitHub 证据描述当前实现状态。两者冲突时保留两者，不把目标要求误写成“当前代码事实”。

## 当前 Surface 规则

Chat 当前配置：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前暴露：

```text
families: lunar / terra / sol / astra
efforts: low / medium / high
```

项目不会擅自假设这些 family 的强弱顺序。没有配置路由时返回 `unresolved` + candidate pool。

## 失败后

真实实现/推理失败：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

这表示第一次分类可能低估，不是故意从弱模型开始试。

权限、网络、限流、凭据、工具不可用等基础设施失败不应该提升难度。

## Plugin manifest

```text
plugins/dev-task-router/.codex-plugin/plugin.json
```

仓库级 marketplace：

```text
.agents/plugins/marketplace.json
```

Skill 本身不会声称已经替 ChatGPT 切换当前模型；真正自动调用不同模型需要后续执行集成。
