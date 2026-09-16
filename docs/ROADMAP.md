# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → Context 优化 → 执行集成。**

V1.0 前继续保持轻量，不要求自建服务器、数据库集群、VS Code Extension 或 Agent Swarm。

---

## V0.1 — 最小可运行闭环 ✅

完成 CLI、状态机、YAML plan、CommandExecutor、checks 和 CI。

## V0.2 — 任务层级与多模型路由 ✅

完成 Project → Stage → Step → Task、`NONE / LOW / MEDIUM / HIGH`、RuleRouter、Model Profile、Executor Registry、Handoff。

## V0.3 — 验证、重试与升级闭环 ✅

完成 Checker、Reviewer、Retry、Escalation、BLOCKED、失败历史和人工 retry。

核心升级语义：

```text
LOW failure    → MEDIUM
MEDIUM failure → HIGH
HIGH failure   → HIGH retry / BLOCKED
```

首次仍按预测难度直接分配；这不是 weak-first。

---

## V0.4 — ChatGPT / Codex Plugin + Skill 化 ✅

完成：

- `.agents/plugins/marketplace.json`
- `plugins/dev-task-router/.codex-plugin/plugin.json`
- Skill-only Plugin
- `index / decompose-project / classify-task / create-handoff`
- Plugin package 回归测试
- Python package `0.4.0`

验证：**23 passed**。

---

## V0.5 — 内容级复杂度判断 + Surface Router ✅

完成：

- `DifficultyClassifier / DifficultyAssessment`
- 内容级 `level / score / confidence / reason / factors / traits`
- 架构、状态、并发、风险、跨模块、歧义、验证成本信号
- “伪简单高风险”识别
- Task 拆分停止条件
- `.autodev/surfaces.yaml`
- `SurfaceCatalog / SurfaceDecision`
- `route-model` Skill
- Chat 固定 Surface 映射
- Codex / Work 可配置模型池
- 不猜 Lunar / Terra / Sol / Astra 强弱顺序
- Plugin / Python package `0.5.0`

完整回归：**29 passed**。

---

## V0.6 — GitHub Plugin/App 联动与真实仓库上下文 ✅

完成：

- `RepositoryContext`
- `.autodev/repo-context.yaml`
- `autodev repo-context --import / --json`
- repo / branch / commit / PR / relevant files / changed files / tests / CI/checks 数据结构
- safe relative path validation
- compact repository context budget
- repository evidence → Difficulty score / confidence / traits
- broad-scope / cross-module 修正
- `auth / migration / core-state / public-api / compatibility / persistence / concurrency` 等 verified risk tags
- failing CI 只对 debugging/review uncertainty 做有限修正
- workflow / RuleRouter 自动读取 repo context
- handoff 写入 repository / branch / commit / PR / CI / relevant files / facts
- 新 Skill：`inspect-repository`
- `decompose-project / classify-task / create-handoff / index` repository-aware
- 测试文件不计入业务 module_count，避免虚假跨模块升级
- Plugin / Python package `0.6.0`
- `docs/V0.6.md`

核心原则：

```text
GitHub evidence = 当前实现事实
User request    = 目标状态
```

不扫描整个仓库；优先 commit-anchored、task-specific evidence。

验证：branch CI + PR merge-ref CI 均通过，完整回归 **37 passed**。PR #6 已 squash merge 到 `main`。

---

## V0.7 — Context / Handoff 优化 🚧

目标：切模型、切对话、切执行阶段时只携带必要上下文，同时避免证据过旧、重复发送或上下文越滚越大。

计划：

- relevant-files 最小集合进一步裁剪；
- verified facts 去重与 provenance；
- 不可破坏约束单独持久化；
- failure evidence 压缩；
- acceptance criteria 精简；
- exact next action；
- Context Budget；
- stale evidence detection；
- task-specific context packs；
- repository context 与 task context 分层；
- 防止完整聊天历史和完整仓库反复发送；
- handoff 可比较/可更新，不每次整份重建。

验收方向：在保留任务正确性和关键约束的前提下，同一项目跨任务传递的上下文明显小于“整段聊天 + 整个仓库摘要”。

---

## V0.8 — 真正的多模型执行

目标：在产品支持或独立执行层允许时，让 Surface Route 真正调用模型。

```text
Task
↓
Difficulty classifier
↓
Surface router
↓
具体模型 / reasoning effort
↓
Executor
↓
Checker
↓ fail
Difficulty upward reclassification
```

这一阶段正式接 API / App / MCP 等执行集成。DeepSeek、OpenAI 或其他 Provider 都可以通过 Adapter 接入，不把 Core 锁死在单一厂商。

---

## V0.9 — 成本与自适应校准

记录：

```text
Task traits
→ predicted difficulty
→ surface/model
→ success/fail
→ promotion
→ token/cost
```

据此降低简单任务被判成 HIGH、高风险任务被判成 LOW、无意义重试和不必要高级模型使用。

---

## V1.0 — 第一版正式发布

目标能力：

- ChatGPT / Codex Plugin；
- Project / Stage / Step / Task；
- 自动内容级难度分类；
- Surface-aware model routing；
- 失败后 upward reclassification；
- Checker / Reviewer；
- GitHub 真实上下文；
- Compact Handoff；
- 可选多 Provider 执行集成；
- Token / 成本统计。

不作为 V1.0 阻塞项：自建服务器、多用户、VS Code UI、Agent Swarm、企业协作平台。

---

# 当前下一步

进入 **V0.7 Context / Handoff 优化**：

1. 定义 Task Context Pack schema。
2. 对 relevant files / facts / constraints / failures 设置独立预算。
3. 增加 stale evidence 检测。
4. 增加 context 去重和增量更新。
5. 让 handoff 只携带下一 Task 真正需要的内容。
6. 增加跨多 Task 的 context-size 回归测试。
7. CI 通过后合并 V0.7。
