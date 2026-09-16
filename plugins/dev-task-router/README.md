# 项目拆解器 Plugin

这是 Dev Task Router 的轻量 OpenAI Plugin 包。

V0.7 仍保持 **skill-only Plugin**，但增加一个可选的 Windows 本地 companion，用来在**同一个 ChatGPT 会话**里精确切换模型/推理档位。

## 核心链路

```text
开发目标
  ↓
GitHub 相关仓库事实
  ↓
Project → Stage → Step → Task
  ↓
NONE / LOW / MEDIUM / HIGH
  ↓
Surface route
  ↓
requested profile
  ↓
Windows local companion
  ↓ verified
同一个 ChatGPT conversation
```

核心原则：**拆 Task，不拆 conversation。**

## Skills

- `index`：共享难度、仓库证据、失败重分类、验证和 handoff 规则；
- `inspect-repository`：读取任务相关 repo / branch / commit / files / tests / PR / diff / CI；
- `decompose-project`：结合真实仓库范围拆 Stage / Step / Task；
- `classify-task`：输出 Difficulty / Reason / Confidence / Traits；
- `route-model`：把难度映射到 Chat / Codex / Work；
- `switch-local-mode`：把已解析 route 交给本地 companion，并要求 actual profile 验证；
- `create-handoff`：生成带 commit anchor 的最小上下文。

## Chat route

```text
LOW    → 5.6 Sol Low
MEDIUM → 5.6 Sol Medium
HIGH   → 5.6 Sol High
```

Codex / Work 当前只登记模型池；未配置时仍保持 `unresolved`，不猜 Lunar / Terra / Sol / Astra 强弱顺序。

## Local exact switch

本地 companion 的原则：

- Windows UI Automation / accessibility；
- 不使用固定屏幕坐标；
- 一次性 probe 当前 ChatGPT build；
- selector / model / effort / verify labels 配置化；
- `requested` 和 `actual` 分开；
- 只有 `verified: true` 才允许认为切换成功；
- selector 找不到、权限失败、UI 变化等属于 `MODE_SWITCH` 基础设施失败，不提升 Task Difficulty。

本地安装：

```powershell
pip install -e ".[local]"
```

Probe：

```powershell
autodev-mode probe --json
```

验收：

```powershell
autodev-mode switch LOW --surface chat --json
autodev-mode switch MEDIUM --surface chat --json
autodev-mode switch HIGH --surface chat --json
```

详细说明见 `docs/V0.7.md`。

## GitHub 上下文原则

用户要求描述目标状态；GitHub 证据描述当前实现状态。默认只携带 task-specific relevant files/tests/diff/CI，不把整个仓库塞进上下文。

## 失败后

真实实现/推理失败：

```text
LOW → MEDIUM
MEDIUM → HIGH
HIGH → HIGH retry / BLOCKED
```

模式切换失败、网络、凭据、权限、工具不可用等基础设施错误不触发上述升级。

## Plugin manifest

```text
plugins/dev-task-router/.codex-plugin/plugin.json
```

仓库级 marketplace：

```text
.agents/plugins/marketplace.json
```

当前云端 exact mode switch 暂不作为 V0.7 阻塞项；本阶段先把 Windows 本地同会话切换做实。
