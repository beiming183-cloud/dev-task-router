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

完成从固定 `kind → level` 到内容级可解释分类的升级。

新增：

- `DifficultyClassifier`
- `DifficultyAssessment`
- `level / score / confidence / reason / factors / traits`
- 架构、状态、并发、风险、跨模块、歧义、验证成本等信号
- “伪简单高风险”识别
- Task 拆分停止条件
- `.autodev/surfaces.yaml`
- `SurfaceCatalog / SurfaceDecision`
- 新 Skill：`route-model`
- Chat 固定 Surface 映射
- Codex / Work 可配置模型池
- 不猜 Lunar / Terra / Sol / Astra 的 family 强弱顺序
- Plugin / Python package `0.5.0`
- `docs/V0.5.md`

当前 Chat 配置：

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

当前 Codex / Work 只登记可用池：

```text
families: lunar / terra / sol / astra
efforts: low / medium / high
```

如果未配置 family-to-difficulty 映射，保持 `unresolved`，不编造排序。

完整回归：**29 passed**。

---

## V0.6 — GitHub Plugin/App 联动与真实仓库上下文

目标：让分类和拆解不再只依赖用户描述，而是使用真实仓库事实。

计划：

- repo / branch / commit 上下文；
- 定位相关文件、模块、测试；
- 读取 PR / diff / CI；
- 根据真实影响范围修正 Difficulty；
- acceptance criteria 对应到真实测试/构建；
- GitHub 保持为事实来源；
- 不把整个仓库无差别塞进上下文。

V0.6 重点解决：

```text
用户需求
↓
读取真实仓库
↓
确定相关范围
↓
再拆 Task + 判断 Difficulty
```

---

## V0.7 — Context / Handoff 优化

目标：切模型、切对话时只携带必要上下文。

计划：

- relevant-files 最小集合；
- verified facts；
- 不可破坏约束；
- failure evidence；
- acceptance criteria；
- next action；
- Context Budget；
- 防止把完整聊天历史和完整仓库反复发送。

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

这一阶段才正式接 API / App / MCP 等执行集成。DeepSeek、OpenAI 或其他 Provider 都可以通过 Adapter 接入，不把 Core 锁死在单一厂商。

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

据此降低：

- 简单任务被判成 HIGH；
- 高风险任务被判成 LOW；
- 无意义重试；
- 不必要的高级模型使用。

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

V0.5 已完成。进入 **V0.6 GitHub 真实仓库上下文**：

1. 定义最小 Repo Context 数据结构。
2. 读取 branch / commit / changed files / tests / CI。
3. 用仓库事实辅助 Task 拆解和 Difficulty 判断。
4. 只提取相关文件，不扫描/发送整个仓库。
5. 把 GitHub evidence 写入 acceptance / handoff。
6. 为 Plugin 增加 repository-aware Skill。
7. 增加真实 diff / CI / missing-context 回归案例。
