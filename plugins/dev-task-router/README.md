# 项目拆解器 Plugin

Dev Task Router 的轻量 OpenAI Plugin 包。

当前仍保持 **skill-only + lightweight local companion**：不要求 MCP server、自建服务器、数据库或 VS Code Extension。

## 核心原则

```text
Task decomposition != conversation decomposition
```

复杂项目默认保持同一个 canonical conversation。不同 Task 可以使用不同 reasoning profile，但不为了 LOW / MEDIUM / HIGH 人为拆成多个聊天窗口。

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实
  ↓
Project → Stage → Step → Task
  ↓
Rolling Project Context + Task Context Pack
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
requested profile
  ↓
本地 exact mode switch
  ↓ verified
当前 canonical conversation
  ↓
response monitor
  ↓
Checker / Git evidence
  ↓
Execution Evidence / Recovery / Audit
  ↓
Rolling Context delta
  ↓
next Task
```

## Skills

- `index`：共享难度、上下文、仓库证据、失败重分类和验证规则；
- `inspect-repository`：读取 task-specific repo / branch / commit / files / tests / PR / diff / CI；
- `decompose-project`：结合真实仓库范围拆 Stage / Step / Task；
- `classify-task`：输出 Difficulty / Reason / Confidence / Traits；
- `route-model`：把难度映射到 Chat / Codex / Work；
- `build-context-pack`：从 rolling context + repository evidence 生成预算化当前 Task 工作集；
- `switch-local-mode`：Windows 本地同会话切换 requested model / effort，并验证 actual profile；
- `prepare-local-execution`：安全发送、response resume、Checker、NONE 与 continuous-loop 规则；
- `recover-execution`：处理 PREPARED/ambiguous-send、execution evidence、状态审计、独立 Reviewer 和 repository anchor 同步；
- `create-handoff`：生成 next-task-first compact handoff。

## Rolling context / Context Pack

`.autodev/context.yaml` 保存跨 Task 仍然有价值的信息，不是聊天记录副本。

正常 Task Context Pack 只携带：

```text
Project / Stage / Step / Task
project goal
applicable decisions
protected constraints
stage/task notes
acceptance
recent failure evidence
relevant files/facts/CI
requested execution profile
exact next action
```

不重复完整聊天历史，也不 dump 整个仓库。

PASS 后只自动写入 Checker 已验证的最小事实，不从 assistant prose 自动生成永久 decision/constraint。

## 当前 Chat Surface

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前登记模型池，但没有明确配置时不猜 family 强弱顺序。

## Local exact switch

Windows local companion 使用 UI Automation/accessibility，不使用固定屏幕坐标。

```text
autodev-mode probe --json
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

只有 `verified: true` 且 actual family/effort 与 requested 完全一致，才允许模型 Task 进入 conversation。

## Local execution loop

检查/运行命令：

```text
autodev-local prepare --json
autodev-local gate --dry-run --json
autodev-local probe-conversation --json

autodev-local run --json
autodev-local resume --json
autodev-local continue --max-cycles 10 --json
```

模型 Task：

```text
verified route
→ composer full read-back
→ duplicate guard
→ Send
→ stable response completion
→ Checker / Git evidence
```

`resume` 只恢复已存在的 active dispatch，没有 session 时禁止创建新发送。

真正 deterministic `NONE` command 可自动执行并继续；失败则 `DEBUG_TASK_REQUIRED`，不会把 NONE 直接提升成模型 Task。

## Recovery / Evidence / Audit

V0.9 增加：

```text
autodev-local recover --json
autodev-local evidence --json
autodev-local audit --json
autodev-local sync-repository --json
```

`.autodev/execution-evidence.jsonl` 是本地 append-only compact evidence ledger，并使用 SHA-256 hash chain 检查历史证据是否被修改。它不复制完整聊天历史。

恢复原则：

```text
PREPARED + 无 dispatch reservation → SAFE_RETRY
PREPARED + submitted              → RESUME
PREPARED + submitting + 已验证响应活动 → RESUME
PREPARED + submitting + 无法证明发送结果 → AMBIGUOUS / 停止
```

未知发送边界不猜测、不自动二次发送。response 文件已落盘、workflow state 已持久化等后续 crash point 也通过 durable state 做幂等恢复，不能重复增加 attempt。

`audit` 会核对 evidence chain、response digest、session↔dispatch、workflow `local_dispatch_id` 等状态关系。可恢复的写入延迟可以是 warning；数据损坏或身份冲突必须 fail closed。

## Independent Reviewer

同一个 canonical ChatGPT conversation 不能因为下一条提示词写了“独立审查”就被当成 independent Reviewer。

只有显式配置并通过 gate 的外部 reviewer executor 才能自动审查。Reviewer transport/process/protocol 故障属于基础设施失败，不应消耗新的实现 attempt；明确的 reviewer `FAIL` 才能成为真正的验证失败证据。

## Repository anchor sync

本地 Checker PASS 不等于 GitHub 上已经存在且通过 CI 的 commit。

只有以下条件同时成立，才允许 `sync-repository` 推进 rolling `last_commit`：

```text
repo-context commit 已知
CI == success
local HEAD == repo-context commit
业务 worktree 干净
```

这样不会把未 commit/push 的本地修改误写成远端事实。

## Failure reclassification

只有完成一次真实模型执行后，Checker/DIFF/有效 Reviewer 失败才能作为 Difficulty promotion 证据：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

UI selector、ChatGPT 窗口、mode switch、response timeout、恢复歧义、evidence audit、Reviewer 基础设施、GitHub 同步、权限/依赖/网络等基础设施问题都不提升 Difficulty。

## 当前边界

V0.9 自动回归覆盖 execution evidence、PREPARED reconciliation、跨 crash-point 幂等恢复、状态一致性 audit、独立 Reviewer gate、repository anchor sync，以及 V0.8 的 safe submit / response resume / Checker / rolling delta / deterministic NONE / bounded continuous loop。

Windows exact mode switch、composer、Send、assistant-message selectors 仍需要对用户实际 ChatGPT Windows build 做一次真机 UIA 校准。默认配置保持关闭；未验证前只称为**已实现、未 live-verified**。
