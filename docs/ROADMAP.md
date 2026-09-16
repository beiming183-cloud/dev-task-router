# Dev Task Router 开发路线图

## 总原则

项目主线改为：**先做 ChatGPT / Codex Plugin + Skills，再做自动拆解、仓库联动和真正的多模型执行。**

V1.0 前保持轻量，不要求自建服务器、数据库集群、VS Code Extension 或 Agent Swarm。

---

## V0.1 — 最小可运行闭环 ✅

完成 CLI、状态机、YAML plan、CommandExecutor、checks 和 CI。

## V0.2 — 任务层级与多模型路由 ✅

完成 Project → Stage → Step → Task、`NONE / LOW / MEDIUM / HIGH`、RuleRouter、Model Profile、Executor Registry、Handoff。

## V0.3 — 验证、重试与升级闭环 ✅

完成 Checker、Reviewer、Retry、Escalation、BLOCKED、失败历史和人工 retry。

V0.3 的升级语义从现在起明确为：**初始分类先直接匹配难度；如果真实执行失败，则把失败视为可能低估难度的证据并向上重新分类。**

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

基础设施失败不触发难度升级。

---

## V0.4 — ChatGPT / Codex Plugin + Skill 化 🚧

目标：把“项目拆解器”真正做成 OpenAI Plugin，而不是 VS Code 插件。

当前设计：Skill-only Plugin。

已建立：

- `.agents/plugins/marketplace.json`
- `plugins/dev-task-router/.codex-plugin/plugin.json`
- `skills/index/SKILL.md`
- `skills/decompose-project/SKILL.md`
- `skills/classify-task/SKILL.md`
- `skills/create-handoff/SKILL.md`

原则：

- 不要求自建服务器；
- 不要求 MCP server；
- 不要求 `.app.json`；
- 不绑定 VS Code；
- 初次按难度直接分配模型档位；
- 真失败后向上重新分类。

验收标准：Plugin manifest 和所有 Skill 文件结构合法，能被当前 OpenAI Plugin/Skill 体系识别；插件能稳定产出带难度、原因、验收和 handoff 的开发计划。

---

## V0.5 — 自动任务拆解与复杂度判断

目标：从固定 kind 规则升级成真正根据任务内容判断难度。

重点特征：

- blast radius；
- 架构耦合；
- 歧义程度；
- 状态/生命周期复杂度；
- 可逆性；
- 验证成本；
- 安全、迁移、认证等领域风险；
- 历史失败证据。

输出必须包括：

```text
Difficulty
Reason
Confidence
Initial route
Failure route
```

---

## V0.6 — GitHub Plugin/App 联动

目标：让项目拆解器可以读取真实仓库上下文，而不是只依赖用户口述。

计划：

- repo / branch / commit 上下文；
- 查找相关文件和模块；
- 读取 CI / PR / diff；
- 将 GitHub 事实用于任务拆解和验收；
- 保持 GitHub 为事实来源。

---

## V0.7 — Context / Handoff 优化

目标：让切模型、切对话时只携带必要上下文。

计划：

- 相关文件最小集合；
- 已验证事实；
- 不可破坏约束；
- 失败证据；
- acceptance criteria；
- next action；
- 防止把整个聊天历史塞给下一模型。

---

## V0.8 — 真正的多模型执行

目标：在产品支持或独立执行层允许时，让路由结果真正调用不同模型，而不只是给出推荐。

理想链路：

```text
Task
↓
Difficulty classifier
↓
LOW / MEDIUM / HIGH
↓
对应模型执行
↓
Checker
↓ fail
重新分类并上调
```

这里才考虑 App / MCP / API 等执行集成；在确定必要前不自建重型服务器。

---

## V0.9 — 成本与自适应路由

记录：

```text
Task type → predicted difficulty → model → success/fail → promoted tier → cost
```

据此校准分类器，降低“把简单任务判成 HIGH”和“把复杂任务判成 LOW”的概率。

---

## V1.0 — 第一版正式发布

目标能力：

- ChatGPT / Codex Plugin；
- Project / Stage / Step / Task；
- 自动难度分类；
- 不同难度对应不同模型档位；
- 失败后 upward reclassification；
- Checker / Reviewer；
- GitHub 上下文；
- Compact Handoff；
- 可选执行集成；
- Token / 成本统计。

不作为 V1.0 阻塞项：自建服务器、多用户、VS Code UI、Agent Swarm、企业协作平台。

---

# 当前下一步

先完成 V0.4：

1. 校验 Plugin manifest / marketplace JSON。
2. 校验所有 Skill frontmatter 和引用路径。
3. 增加插件包回归测试。
4. 修正 V0.3 文档中的升级语义。
5. CI 通过后合并 V0.4。
6. 然后进入 V0.5 自动任务拆解与复杂度判断。
