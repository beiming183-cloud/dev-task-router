# Dev Task Router 开发路线图

## 总原则

项目主线：**ChatGPT / Codex Plugin + Skills → 内容级难度判断 → Surface 路由 → GitHub 真实上下文 → 执行集成。**

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

## V0.6 — GitHub Plugin/App 联动与真实仓库上下文 🚧

目标：让分类和拆解不再只依赖用户描述，而是使用真实仓库事实。

当前 candidate 已实现：

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
- Plugin / Python package `0.6.0`
- `docs/V0.6.md`

核心原则：

```text
GitHub evidence = 当前实现事实
User request    = 目标状态
```

不扫描整个仓库；优先 commit-anchored、task-specific evidence。

最新 branch CI：**36 passed**。

V0.6 合并验收：PR CI 继续通过，合并后 main 回归通过，再标记 ✅。

---

## V0.7 — Context / Handoff 优化

目标：切模型、切对话时只携带必要上下文，同时避免证据过旧或重复传输。

计划：

- relevant-files 最小集合进一步裁剪；
- verified facts 去重；
- 不可破坏约束；
- failure evidence；
- acceptance criteria；
- next action；
- Context Budget；
- stale evidence detection；
- task-specific context packs；
- 防止完整聊天历史和完整仓库反复发送。

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

完成 V0.6 合并验收：

1. PR CI 通过。
2. 检查 repository-aware diff 是否只携带必要上下文。
3. squash merge 到 `main`。
4. main CI 通过后标记 V0.6 ✅。
5. 然后进入 V0.7 Context / Handoff 优化。
