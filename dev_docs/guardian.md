---
title: Codex Guardian 自动评审
summary: 描述第 6 轮上游由单体 ext/guardian 拆分而成的 Guardian 子系统：三个 crate（ext/guardian-v2 装配入口、ext/guardian-reviewer 同步复审策略、guardian-context 共享上下文）加宿主侧 core/src/guardian/ 模块与 prompts/templates/guardian/ 提示词模板的分工；说明一个 install 同时装同步复审与异步打分两套 contributor、guardian-reviewer 实现 extension-api 却不被注册而是被 core 当普通库依赖这一结构例外、input/request 双预算机制，以及审批编排侧从枚举选 reviewer 重构为 strict_auto_review 布尔加 ApprovalContext 的变化。
keywords: codex | guardian | auto-review | approval | sync-reviewer | async-scorer | guardian-context | extension-api | round6
scope: codex-rs/ext/guardian-v2、codex-rs/ext/guardian-reviewer、codex-rs/guardian-context、codex-rs/core/src/guardian 与相关提示词模板
related_files: codex-rs/ext/guardian-v2/src/lib.rs | codex-rs/ext/guardian-reviewer/src/lib.rs | codex-rs/guardian-context/src/lib.rs | codex-rs/core/src/guardian/mod.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/core/src/tools/approvals.rs | codex-rs/app-server/src/extensions.rs | codex-rs/protocol/src/config_types.rs | codex-rs/prompts/templates/guardian/policy.md | codex-rs/core/Cargo.toml
dependencies: dev_docs/tools_and_sandbox.md | dev_docs/mcp_and_extensions.md | dev_docs/_analysis/upstream_sync_round6.md
verified_at: 2026-09-21
---

# Guardian 自动评审

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **本文是第 6 轮上游同步新开的专题**：基线 `bb5054fe47` 上 Guardian 只是 `codex-rs/ext/guardian` 一个 **77 行**的小 crate，本轮拆成三个 crate、共 **20,748 行**，量级差 270 倍。此前本体系只在 `tools_and_sandbox.md` 里有一小节，且那一节的 7 个锚点第 6 轮全部失效。
> **证据等级**: crate 分工、装配链路、trait 实现为 E3（源码）；行数与文件清单为 E1；依赖关系为 E2

> [!IMPORTANT]
> **本文只回答结构问题：它由什么构成、谁装配它、它挂在哪些扩展点上。** 评审策略本身（提示词内容、判定规则、模型如何被调用）**未展开**——见 §6。

---

## 1. 三个 crate 加两处宿主侧代码

| 位置 | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-rs/ext/guardian-v2` | 11,545 | **装配入口**。内分 `async_scorer/` 与 `sync_reviewer/` 两条通路 |
| `codex-rs/ext/guardian-reviewer` | 3,102 | **同步复审策略与会话簿记**，独立于宿主会话运行时 |
| `codex-rs/guardian-context` | 6,101 | 同步复审与异步打分**共用**的上下文分段 |
| `codex-rs/core/src/guardian/` | — | 宿主侧：审批请求构造、决策、预算、复审会话 |
| `codex-rs/prompts/templates/guardian/` | — | 提示词模板 4 个：`codex-rs/prompts/templates/guardian/policy.md`、同目录的 policy_template、classifier_instructions、node_repl_policy |

> **第 6 轮迁移提示**：后两项都换过位置。`core/src/guardian/metrics.rs` **已删除且无同名替代**；`policy.md` 与 `policy_template.md` **从 `core/src/guardian/` 迁到了 `codex-rs/prompts/templates/guardian/`**<!-- ref-exempt: 反例——正文说明旧路径已不存在 -->。旧文档按 core 路径去找这两个 md 会扑空。

---

## 2. 一个 `install` 装两套 contributor

这是本子系统最值得先知道的结构事实。`codex-rs/ext/guardian-v2/src/lib.rs:15-22`：

```rust
/// Installs the guardian contributors into the extension registry.
pub fn install(
    registry: &mut ExtensionRegistryBuilder<Config>,
    auth_manager: Arc<AuthManager>,
    thread_manager: Weak<ThreadManager>,
) {
    async_scorer::install(registry, auth_manager, thread_manager.clone());
    install_reviewer(registry, thread_manager);
}
```

即**一次 `install` 调用同时装了异步打分与同步复审两套 contributor**。装配点在 `codex-rs/app-server/src/extensions.rs:95`：

```rust
codex_guardian_v2::install(&mut builder, auth_manager.clone(), thread_manager);
```

> [!CAUTION]
> **旧文档记的参数是 `guardian_agent_spawner`，那个类型已经不存在了。**
>
> 基线时的调用形如 `codex_guardian::install(..., guardian_agent_spawner)`，依赖 `AgentSpawner` 能力 trait。第 6 轮 `codex-rs/ext/extension-api/src/capabilities/agent.rs` **整个文件被删除**<!-- ref-exempt: 反例——正文说明该路径已不存在 -->，`AgentSpawner` 随之消失，参数换成了 `Weak<ThreadManager>`。
>
> 注意 `Weak` 这个选择：Guardian **不持有** `ThreadManager` 的所有权，避免与宿主形成引用环。

---

## 3. 一处结构例外：实现了 extension-api，却不被注册

`codex-rs/ext/` 下有 11 个 crate 实现 `codex-extension-api`，其中 **10 个**被装配层注册进 `ExtensionRegistry`。**唯一的例外就是 `guardian-reviewer`**。

它的去向是：被 `codex-core` 当**普通库**依赖（`codex-rs/core/Cargo.toml:51` 的 `codex-guardian-reviewer`，该行落在 `[dependencies]` 段内——`[dev-dependencies]` 从 `:140` 才开始）。

穷举命令：

```bash
# 不含 ExtensionRegistryBuilder 的 ext crate（即不自我注册的）
for d in codex-rs/ext/*/; do grep -rqs "ExtensionRegistryBuilder" "$d/src" || echo "$(basename $d)"; done
# → agent connectors guardian-reviewer items
```

其中 `agent` / `connectors` / `items` 本就不实现 extension-api，所以「实现了但不注册」的**只有 guardian-reviewer 一个**。

> **为什么要注意这条**：`ext/` 目录一直被当作「扩展都在这儿、都走 registry」的约定。guardian-reviewer 打破了这个约定——它既在 `ext/` 下、又实现了扩展点 trait、**却是通过 crate 依赖被直接调用的**。按「在 ext/ 下 ⇒ 经 registry 装配」去推断它的接入方式会推错。
>
> 顺带一提，`ext/skills` 是另一种双重身份（**既被注册、又被 core 生产依赖**），见 [`mcp_and_extensions.md`](./mcp_and_extensions.md) §5。两者合起来说明：**`ext/` 现在只是目录约定，接入方式必须逐个确认。**

---

## 4. 各 crate 的公开面

### 4.1 `ext/guardian-reviewer`

模块注释（`codex-rs/ext/guardian-reviewer/src/lib.rs:1-3`）划清了职责边界：

> *"Owns Guardian conversation bookkeeping and synchronous review policy **independently of the host session runtime**. The host supplies review attempts and enforces the resulting decision on the bound action."*

**即它自己不执行任何裁定——宿主提供复审尝试，并负责把裁定施加到被绑定的动作上。** 这条分工写得很明确，改动时不要把执行逻辑挪进来。

公开面包括：`ConversationCheckpoint` / `ConversationState`（`:9-10`，会话簿记）、`GuardianAssessment` / `guardian_output_contract_prompt` / `guardian_output_schema`（`:24-26`，评审产出契约）、`ReviewModel` / `select_review_model`（`:32-33`，评审模型选择）、`GuardianReviewError`（`:34`）。内部另有 `assessment`、`circuit_breaker` 等模块——**存在熔断器**这一点值得注意。

### 4.2 `guardian-context`

模块注释（`codex-rs/guardian-context/src/lib.rs`）给了两条硬语义：

> *"Shared context sections for synchronous Guardian review and asynchronous scoring. Transcript collection and bounded host-owned history are also available directly, without section composition."*
> *"**Contributor failures abort collection without returning partial context.**"*
> *"Sections preserve source-specific evidence and share prompt framing."*

**贡献者失败会中止整次采集，不返回部分上下文**——这是「宁可没有，也不要半份」的取舍，与很多系统的「尽力而为」相反。做容错改动时容易误把它改成部分返回。

公开面：`ActionPresentation` / `PlannedAction` / `PlannedActionKind` / `action_for_review`（`:24-27`）、`GuardianRootMessage`（`:28`）、`ContextSection`（`:29`）、`ConversationTranscriptEntry` / `ConversationTranscriptEntryKind`（`:31-32`）。

### 4.3 宿主侧 `core/src/guardian/`

目录现有 14 个 `.rs` 加 `snapshots/`：`review`、`review_session`、`review_session_context`、`review_session_setup`、`review_request`、`approval_request`、`prompt`、`decision`、`coverage`、`feedback`、`input_budget`、`request_budget`、`reviewer_config`、`runtime`。

`codex-rs/core/src/guardian/mod.rs` 的主要导出：

| 导出 | 位置 | 说明 |
| ---- | ---- | ---- |
| `decide_approval` / `spawn_approval_decision` | `:48-49` | 决策入口 |
| `check_pending_guardian_input` / `finalize_guardian_input` | `:12-13` | **输入预算** |
| `check_guardian_prompt_budget` / `ExhaustedReviewBudget` / `observe_guardian_request` | `:15-17` | **请求预算** |
| `resolve_review_model` | `:21` | 评审模型解析 |
| `GuardianApprovalRequest` / `GuardianMcpAnnotations` / `GuardianNetworkAccessTrigger` | `:43-45` | 审批请求类型 |

> **双预算机制（第 6 轮新增）**：`input_budget` 与 `request_budget` 是两套独立的预算，分别约束「送进评审的输入量」与「发起评审请求的次数」。`ExhaustedReviewBudget` 是后者耗尽时的显式类型。**这是旧文档完全没有的机制。**

---

## 5. 审批编排侧：从「枚举选 reviewer」改成「布尔 + 上下文」

Guardian 如何被审批链路调用，第 6 轮整体重构了。

> [!CAUTION]
> **以下三个符号全仓零命中，按它们 grep 只会白费力气**：`ApprovalReviewer`（枚举）、`resolve_tool_apporval()`、`strict_auto_review_enabled_for_turn()`。旧版 `tools_and_sandbox.md` 列举的 7 个锚点全部失效。

现在的形态：

| 位置 | 内容 |
| ---- | ---- |
| `codex-rs/core/src/tools/orchestrator.rs:136-140` | `strict_auto_review` 由 `session.active_turn_context_and_strict_auto_review()` 取出，**折叠成一个 `bool`** |
| `codex-rs/core/src/tools/orchestrator.rs:176-186`、`:203-213` | 该 bool 随 `ApprovalContext { .., strict_auto_review, .. }` 传给 `session.request_approval(action, approval_ctx)`（调用在 `:187-191`、`:214-218`） |
| `codex-rs/core/src/tools/approvals.rs:426-430` | 消费侧 `enum ApprovalResolutionSource { Hook, Guardian, User }`——**三变体，`Hook` 是第 6 轮新增的** |
| `codex-rs/protocol/src/config_types.rs:183-190` | 配置面 `enum ApprovalsReviewer { User, AutoReview }`（`guardian_subagent` 是 `AutoReview` 的 serde alias） |

> [!WARNING]
> **`ApprovalResolutionSource` 与 `ApprovalsReviewer` 是两个不同层次的类型，别混。** 前者在**编排面**，描述「这次审批的裁定是谁给的」；后者在**配置面**，描述「用户配置了用哪种 reviewer」。名字相近但不是一回事。

另：`codex-rs/ext/extension-api/src/contributors/approval_review.rs:24` 新增了 `SynchronousApprovalReviewer` trait——这是第 6 轮新增的 4 个「不以 `Contributor` 结尾」的扩展点之一（见 [`mcp_and_extensions.md`](./mcp_and_extensions.md) §2）。

协议侧对应 `Op::ApproveGuardianDeniedAction`（`codex-rs/protocol/src/protocol.rs` 的 `Op` 枚举）。

---

## 6. 本文未覆盖的内容

**以下均为「找过但本轮未展开」，不是「没找过」**：

| 未覆盖项 | 证据等级 | 卡点 |
| ---- | ---- | ---- |
| 评审策略本身（`codex-rs/prompts/templates/guardian/policy.md` 及同目录模板的内容与生效方式） | E1 | 只确认了文件位置，未读内容 |
| `async_scorer` 与 `sync_reviewer` 的分工细节 | E1 | 两个子目录合计逾万行，本轮只确认了「一个 install 装两套」 |
| 熔断器（`circuit_breaker`）的触发条件与恢复策略 | E1 | 仅确认模块存在 |
| 双预算的具体阈值与耗尽后的行为 | E1 | 仅确认 `ExhaustedReviewBudget` 类型存在 |
| `coverage` 与 `feedback` 两个模块的作用 | E1 | 仅确认文件存在 |
| Guardian 与 MCP elicitation 的关系 | E3（已知存在） | `GuardianMcpElicitationReviewer`（`codex-rs/core/src/session/mcp.rs:77`）是 `ElicitationReviewer` 的**全仓唯一生产实现**，即 MCP elicitation 被路由进 Guardian 审批体系。**机制已确认，链路未展开** |
| `ReviewDecision::TimedOut` 与 Guardian 的连接点 | E1 | 旧文档曾据 `guardian_timeout_message` 建立这条关联，该符号已零命中，**连接点需重新取证** |

---

## 7. 相关文档

- [工具执行与沙箱隔离](./tools_and_sandbox.md) §7 — 审批链路的完整次序与 Guardian 接入点
- [MCP 与扩展体系](./mcp_and_extensions.md) — `ext/` 目录的装配规则与结构例外
- [Crate 地图](./crate_map.md) §3.14 — Guardian 三个 crate 的定位
- [智能体核心循环](./core_agent_loop.md) §5.3 — `ReviewDecision` 的 8 个变体
