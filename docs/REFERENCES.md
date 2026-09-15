# 设计参考

Dev Task Router 不复制下面项目的完整实现，只借鉴已经被验证过的设计思想，并保持自身的“轻量、本地优先、编排层”定位。

## Aider

GitHub: https://github.com/Aider-AI/aider

主要借鉴：

- Architect / Editor 的职责分离；
- 强模型负责思考，较便宜模型承担机械性工作；
- Weak Model 可承担摘要、Commit Message 等低价值任务。

在 Dev Task Router 中对应：

```text
Planner / HIGH
        ↓
Executor / MEDIUM or LOW
        ↓
Reviewer / HIGH
```

---

## LiteLLM

GitHub: https://github.com/BerriAI/litellm

主要借鉴：

- Complexity Routing；
- 根据任务复杂度，把简单请求发送给便宜模型，把复杂请求发送给强模型。

Dev Task Router 第一版不会直接依赖 LiteLLM，而是先实现简单的规则路由：

```text
LOW / MEDIUM / HIGH / NONE
```

后续再加入 AUTO Complexity Router。

---

## OpenHands

GitHub: https://github.com/OpenHands/OpenHands

主要借鉴：

- Task → Code → Test → Git / PR 的工程闭环；
- AI Coding Agent 的结果应该落到真实代码和 Git 状态；
- GitHub 可以作为远程任务与工程状态的一部分。

Dev Task Router 更强调：

> 模型的文字结论不是完成证明，Git / Test / Build 才是。

---

## Roomote

GitHub: https://github.com/RooCodeInc/Roomote

主要借鉴：

- Task / Model / Status / Logs 的任务控制面板；
- 不同工作可使用不同模型；
- 远程执行和手机查看任务的产品思路。

明确不在早期复制：

- 完整服务端平台；
- Redis；
- PostgreSQL；
- 多租户；
- 企业权限；
- 云 Sandbox 平台。

---

## GitHub Actions

Docs: https://docs.github.com/actions

主要借鉴和使用：

- CI Gate；
- Test / Build；
- Artifact；
- 无需自建服务器的远程执行能力。

在本项目中，GitHub Actions 是早期“电脑关机以后仍能执行测试和构建”的主要补充方案。

---

## Temporal（仅理念参考）

GitHub: https://github.com/temporalio/temporal

主要借鉴：

- Durable Execution；
- 工作流状态不应该只存在于进程内存中；
- 失败、重启后应能恢复执行。

第一版不会引入 Temporal。本项目使用本地 JSON/YAML + Git 状态完成轻量恢复。
