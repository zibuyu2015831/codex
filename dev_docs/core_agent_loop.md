---
title: Codex 智能体核心循环
summary: 描述 codex-core 的提交-事件协议与三层循环（submission_loop → SessionTask → turn 循环）、会话与 turn 组织方式、工具调用的路由与分发链路、上下文管理与压缩机制、审批与沙箱决策的接入点，并标注各结论的证据等级与未验证边界。
keywords: codex | agent-loop | submission-loop | session-task | turn | tool-router | permission-profile | context-manager | compact
scope: codex-rs/core 的提交循环、任务层、会话、turn、工具调用与上下文管理
related_files: codex-rs/core/src/session/handlers.rs | codex-rs/core/src/session/mod.rs | codex-rs/core/src/session/turn.rs | codex-rs/core/src/tasks/mod.rs | codex-rs/core/src/tasks/regular.rs | codex-rs/core/src/tools/router.rs | codex-rs/core/src/tools/registry.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/core/src/tools/handlers/mod.rs | codex-rs/core/src/tools/approvals.rs | codex-rs/core/src/context_manager | codex-rs/core/Cargo.toml | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/tools/src/tool_spec.rs | codex-rs/shell-command/src/command_safety/is_safe_command.rs | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-03
---

# 智能体核心循环

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/core`（296,963 行）的骨架结构与三层循环
> **证据等级**: 循环链路、类型与函数签名为 E3；目录与文件计数为 E1；模块间部分协作关系为 E1，已在文中逐处标注

> [!IMPORTANT]
> `codex-core` 是全仓最大的 crate。本文给出的是**可导航的骨架**，不是逐行讲解。遇到本文标注为 E1 的判断，请回去读代码，不要直接采信。

> [!WARNING]
> **本文第一版存在结构性缺失与若干计数/位置错误，已在本次修订中更正**：标题写着「核心循环」却完全没有描述循环本身（新增 §2）；依赖计数、`session/` 与 `tools/` 的文件数、`turn.rs` 的类型位置、`is_safe_command()` 的函数名均有误。相关段落保留了更正说明。

---

## 1. codex-core 的模块版图

`codex-rs/core/src/` 下的一级条目超过 100 个（其中 17 个是子目录）。按职责归类：

| 子系统 | 位置 | 说明 |
| ---- | ---- | ---- |
| **提交循环** | `session/handlers.rs`、`session/mod.rs` | `submission_loop`：消费 `Submission`、按 `Op` 分派，见 §2.1 |
| **任务层** | `tasks/` | `SessionTask` 抽象与 4 种实现（regular / compact / review / user_shell），见 §2.2 |
| **会话与 turn** | `session/`（29 个文件 + `snapshots/`、`tests/`） | 会话生命周期、turn 组织、上下文窗口、token 预算 |
| **线程编排** | `thread_manager.rs`、`codex_thread.rs` | 线程管理与线程实例 |
| **工具调用** | `tools/`（26 个文件 + `code_mode/`、`handlers/`、`runtimes/`） | 路由、注册表、编排、审批、沙箱决策 |
| **审批评审** | `guardian/` | Guardian 自动评审后端，见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7 |
| **安全判定** | `safety.rs` | 命令安全性判定的 core 侧入口 |
| **沙箱接入** | `sandboxing/` | core 侧对 `codex-sandboxing` 的封装 |
| **统一执行** | `unified_exec/` | 长驻进程式命令执行（对应 `ExecCommandHandler` / `WriteStdinHandler`） |
| **上下文管理** | `context_manager/`、`context/` | 历史、归一化、增量更新 |
| **上下文压缩** | `compact*.rs`（8 个文件） | 本地压缩、远程压缩 v1/v2、token 预算、模型回退 |
| **模型客户端** | `client.rs`、`client_common.rs` | 与模型服务通信 |
| **状态持久化** | `state/` | core 侧对 `codex-state` 的接入 |
| **配置** | `config/` | 配置加载与校验（详见 [`config_system.md`](./config_system.md)） |
| **执行** | `exec.rs`、`exec_env.rs`、`exec_policy.rs` | 命令执行与策略 |
| **规范注入** | `agents_md.rs`、`agents_md_manager.rs` | 读取并注入仓库规范文件 |
| **补丁应用** | `apply_patch.rs` | 结构化补丁 |
| **技能与钩子** | `skills.rs`、`hook_runtime.rs` | 技能定义、钩子运行时 |
| **插件** | `plugins/` | 插件装载（对应 `request_plugin_install` 等工具） |
| **扩展接入** | `apps/`、`agent/`、`connectors.rs` | 扩展与连接器 |
| **其他子目录** | `bin/`、`mcp_tool_call/`、`realtime_conversation/`、`utils/` | 二进制入口、MCP 调用、实时会话、工具函数 |

> [!NOTE]
> **更正说明**：第一版此表把 `session/` 记为 28 个文件、`tools/` 记为 28 个文件，且完全遗漏了 `tasks/`、`guardian/`、`safety.rs`、`thread_manager.rs`、`codex_thread.rs`、`sandboxing/`、`state/`、`context/`、`plugins/`、`skills.rs`、`hook_runtime.rs`、`unified_exec/`。计数与清单已按下述命令重新核对（E1）：
>
> ```bash
> # 在 codex-rs/core/src 下
> ls -p session/ | grep -v / | wc -l   # → 29（另有 snapshots/ tests/ 两个目录）
> ls -p tools/   | grep -v / | wc -l   # → 26（另有 code_mode/ handlers/ runtimes/ 三个目录）
> ls -p .        | grep /              # → 17 个一级子目录
> ```

> [!NOTE]
> **未验证**（E1）：上表仍是按文件名与目录归类的**结构性描述**，各子系统之间的调用次序与依赖方向未做完整追踪。特别是 `compact*.rs` 的 8 个文件之间如何分工，本文不做推断。

### 1.1 依赖计数（E2，附命令）

第一版写的「67 个 workspace 依赖」**对不上任何一种口径**，已删除。实测：

```bash
cd codex-rs/core
awk '/^\[dependencies\]/{f=1;next} /^\[/{f=0} f' Cargo.toml > /tmp/deps.txt
grep -c '^[a-zA-Z]'      /tmp/deps.txt   # 95  —— [dependencies] 条目总数
grep -c 'workspace = true' /tmp/deps.txt # 94  —— 其中走 workspace 继承的
grep -c '^codex'         /tmp/deps.txt   # 57  —— 其中仓内 codex-* crate
grep '^[a-zA-Z]' /tmp/deps.txt | grep -v 'workspace = true'
# → codex-windows-sandbox = { package = "codex-windows-sandbox", path = "../windows-sandbox-rs" }
```

| 口径 | 数量 |
| ---- | ---: |
| `[dependencies]` 条目总数 | **95** |
| 其中 `workspace = true` | **94** |
| 其中仓内 `codex-*` crate | **57**（唯一的非 workspace 依赖 `codex-windows-sandbox` 也在其中，走 `path`） |
| 第三方 crate | 38 |

这个数字本身就是 `AGENTS.md` 中 `## The codex-core crate` 一节反复强调「resist adding code to codex-core」的背景。

---

## 2. 核心循环：三层嵌套（E3）

> [!IMPORTANT]
> **这是第一版整个漏掉的部分。** 文档标题叫「核心循环」，但通篇只有模块清单，没有任何一处描述循环。本节补上。

Codex 的智能体循环由三层构成，从外到内：

```
┌─ 提交循环 submission_loop ──────────────────────────────────────┐
│  while let Ok(sub) = rx_sub.recv().await { match sub.op { .. } } │
│  session/handlers.rs:714                                        │
│                                                                 │
│   ┌─ 任务层 SessionTask::run ─────────────────────────────────┐  │
│   │  regular / compact / review / user_shell                 │  │
│   │  tasks/mod.rs:184                                        │  │
│   │                                                          │  │
│   │   ┌─ turn 循环 ────────────────────────────────────────┐  │  │
│   │   │  loop { run_turn(..); if !有排队输入 { return } }  │  │  │
│   │   │  tasks/regular.rs:75-89                            │  │  │
│   │   └────────────────────────────────────────────────────┘  │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 第一层：`submission_loop`

```rust
// core/src/session/handlers.rs:714
pub(super) async fn submission_loop(
    sess: Arc<Session>,
    config: Arc<Config>,
    rx_sub: Receiver<Submission>,
) {
    // To break out of this loop, send Op::Shutdown.
    let mut shutdown_received = false;
    while let Ok(sub) = rx_sub.recv().await {
        debug!(?sub, "Submission");
        let dispatch_span = submission_dispatch_span(&sub);
        let should_exit = async {
            match sub.op.clone() {
                Op::Interrupt => { interrupt(&sess).await; false }
                Op::CleanBackgroundTerminals => { .. }
                Op::RealtimeConversationStart(params) => { .. }
                // ……
            }
        }
        // ……
    }
}
```

要点（E3）：

| 事实 | 证据 |
| ---- | ---- |
| 循环体是 `while let Ok(sub) = rx_sub.recv().await`，从一个 channel 消费 `Submission` | `handlers.rs:721` |
| 分派方式是 `match sub.op.clone()`，即**按 `Op` 变体分支** | `handlers.rs:725` |
| **正常**退出方式是 `Op::Shutdown` | `handlers.rs:719` 注释：「To break out of this loop, send `Op::Shutdown`」 |
| 每次提交都开一个 tracing span | `submission_dispatch_span(&sub)`，`handlers.rs:723` |
| 循环在会话创建时 `tokio::spawn` 起来 | `session/mod.rs:769`，span 名 `session_loop`，带 `thread_id` |

> [!NOTE]
> **勘误（行号）**：上表前四行的行号上一稿分别写作 `:720` / `:724` / `:718` / `:722`，**各差一行**，已按 `sed -n '714,726p'` 的实际内容改为 `:721` / `:725` / `:719` / `:723`。`submission_loop` 函数签名本身在 `:714`，这一处是对的。

> [!CAUTION]
> **勘误（结论）：「唯一的退出方式是 `Op::Shutdown`」不成立。**
>
> `handlers.rs:719` 那句注释确实这么写，但**注释描述的是意图，不是全部实现**。同一函数在循环之后还有一段（`handlers.rs:872-875`）：
>
> ```rust
> // If the submission loop exits because the channel closed without an
> // explicit shutdown op, still run session teardown.
> if !shutdown_received {
>     shutdown_session_runtime(&sess).await;
>     emit_thread_stop_lifecycle(sess.as_ref()).await;
>     // ...
> }
> ```
>
> 即：**`while let Ok(sub) = rx_sub.recv().await` 在发送端全部被丢弃、channel 关闭时也会退出**，此时 `shutdown_received` 仍为 `false`，代码显式走一遍收尾（关闭运行时、发 thread stop 生命周期事件、关闭线程持久化）。
>
> 这个区别对调试很关键：**会话可能在没有任何 `Op::Shutdown` 的情况下结束**——比如客户端进程崩溃导致 `tx_sub` 被 drop。如果按"只有 Shutdown 能退出"去排查"会话莫名结束"，方向就错了。
>
> 教训：**源码注释是作者意图的证据（E3 的弱形式），但穷尽性结论必须从控制流本身读出来。**

`session/mod.rs:766-778` 还把这个 join handle 包成了 `SessionIo { tx_sub, rx_event, agent_status, session_loop_termination }`——**提交进 `tx_sub`、事件出 `rx_event`**，这就是会话的全部对外接口形状。

### 2.2 提交-事件协议：`Submission` / `Op` / `Event` / `EventMsg`

> 第一版完全没有提到这四个类型，但它们是理解整个 core 的前提。

全部定义在 `codex-rs/protocol/src/protocol.rs`：

| 类型 | 位置 | 方向 | 角色 |
| ---- | ---- | ---- | ---- |
| `Submission` | `:176` | 客户端 → core | 一次提交，含 `id` 与 `op` |
| `Op` | `:531` | 客户端 → core | 提交的动作枚举（`Interrupt` / `UserInput` / `ThreadSettings` / `Shutdown` / `RealtimeConversation*` / …） |
| `Event` | `:1270` | core → 客户端 | 一次事件，含 `id` 与 `msg` |
| `EventMsg` | `:1288` | core → 客户端 | 事件负载枚举（`Error` / `Warning` / …） |

这是一个**非对称的请求-流式响应模型**：一次 `Submission` 可能产生任意多个 `Event`，两者靠 `id` 关联。`handlers.rs` 中大量出现的 `sess.send_event(&turn_context, event.msg)` 与 `sess.send_event_raw(Event { id, msg })` 就是这条出向通道。

### 2.3 第二层：任务层 `core/src/tasks/`

> 第一版的子系统表**完全没有 `tasks/` 这个目录**。

```rust
// core/src/tasks/mod.rs:184
pub(crate) trait SessionTask: Send + Sync + 'static {
    fn kind(&self) -> TaskKind;
    fn span_name(&self) -> &'static str;

    // 注意：不是 `async fn`。真实签名（mod.rs:202-208）是——
    fn run(
        self: Arc<Self>,
        session: Arc<Session>,
        ctx: Arc<TurnContext>,
        input: Vec<TurnInput>,
        cancellation_token: CancellationToken,
    ) -> impl std::future::Future<Output = SessionTaskResult> + Send;

    // 另有 abort(...) 释放资源
}
```

> [!IMPORTANT]
> **不要把 `run` 读成 async fn。** 上一稿在这里写了 `async fn run(...) -> ...;`，会让读者以为这是 async-fn-in-trait。两处差别都有实际后果：
>
> 1. **返回类型是显式的 `impl Future<Output = SessionTaskResult> + Send`**。手写 RPN 而不用 `async fn` 的典型动机就是**要挂上 `+ Send` 约束**（async-fn-in-trait 默认不保证返回的 Future 是 `Send`，而这个任务要被 `tokio::spawn` 到多线程 runtime 上）。实现者若写出非 `Send` 的 future 会直接编译失败。
> 2. **接收者是 `self: Arc<Self>`**，不是 `&self`——任务持有自身的 `Arc`，可以在 future 内部跨 await 点存活。

目录内容（E1）与 trait 文档要点（E3）：

| 文件 | 角色 |
| ---- | ---- |
| `mod.rs` | `SessionTask` trait。**注意 `enum TaskKind` 并不定义在这里**——它的定义在 `core/src/state/turn.rs:67`，`tasks/mod.rs:35` 只是 `use crate::state::TaskKind;` 把它引进来 |
| `regular.rs` | 常规智能体任务（默认路径，含 turn 循环） |
| `compact.rs` | 上下文压缩任务 |
| `review.rs` | 评审任务 |
| `user_shell.rs` | 用户 shell 任务 |
| `lifecycle.rs` | 任务生命周期 |
| `mod_tests.rs` / `user_shell_tests.rs` | 测试 |

`mod.rs:180-200` 的 trait 文档写明：任务由 `Session` 在**后台 Tokio task** 上执行；实现者通过 `cancellation_token` 感知中止请求并**尽快终止**；`run` 返回 `Some(msg)` 时该消息会由 `Session::on_task_finished` 发给客户端；返回 `CodexErr::TurnAborted` 则走「已中止 turn」的完成路径。

### 2.4 第三层：turn 循环

```rust
// core/src/tasks/regular.rs:75-89
loop {
    let last_agent_message = run_turn(
        Arc::clone(&sess),
        Arc::clone(&ctx),
        next_input,
        prewarmed_client_session.take(),
        cancellation_token.child_token(),
    )
    .instrument(run_turn_span.clone())
    .await?;
    if !sess.input_queue.has_pending_input(&sess.active_turn).await {
        return Ok(last_agent_message);
    }
    next_input = Vec::new();
}
```

这段代码解释了两件第一版没讲清楚的事：

1. **`session/input_queue.rs` 为什么存在**——用户可以在模型还在跑的时候继续输入；一个 turn 结束后如果队列里还有排队输入，**不返回、直接再跑一个 turn**。
2. **`next_input = Vec::new()` 的含义**——后续 turn 的输入不是从这里传的，而是由 `run_turn` 内部从 `input_queue` 取。

> **未验证**（E1）：`run_turn` 内部的完整流程（构造请求 → 流式解析 → 工具调用 → 写回历史）本文未逐段追踪。入口见 `tasks/regular.rs` 与 `session/turn.rs`。

---

## 3. 会话与 turn

### 3.1 `session/` 的组成（E1）

| 文件 | 职责（依据文件名与公开类型） |
| ---- | ---- |
| `session.rs` | 会话主体 |
| `turn.rs` | 单轮交互 |
| `turn_context.rs` | turn 级上下文 |
| `step_context.rs` | 步级上下文 |
| `context_window.rs` | 上下文窗口 |
| `token_budget.rs` / `rollout_budget.rs` | token 与 rollout 预算 |
| `input_queue.rs` | 输入队列 |
| `handlers.rs` | 事件处理 |
| `inject.rs` | 注入 |
| `review.rs` | 评审模式 |
| `multi_agents.rs` | 多智能体 |
| `mcp*.rs`（5 个） | MCP 接入：运行时、预热、刷新 |
| `rollout_reconstruction.rs` | 从既有 rollout 恢复会话 |
| `time_reminder.rs` | 时间提醒 |
| `extension_metrics.rs` | 扩展指标 |
| `code_mode_warning.rs` | code-mode 警告 |

### 3.2 turn 的内部状态（E3）

`session/turn.rs` 中可见的状态类型。**用 grep 定位，不要依赖行号**（这些类型在文件后半段，行号随改动漂移很快）：

| 类型 | 定位方式 | 用途 |
| ---- | ---- | ---- |
| `ProposedPlanItemState` | `rg -n 'struct ProposedPlanItemState' core/src/session/turn.rs` | 提议的计划项状态 |
| `PlanModeStreamState` | `rg -n 'struct PlanModeStreamState' core/src/session/turn.rs` | 计划模式的流式状态（内含一个 `plan_item_state: ProposedPlanItemState` 字段） |
| `AssistantMessageStreamParsers` | `rg -n 'struct AssistantMessageStreamParsers' core/src/session/turn.rs` | 助手消息的流式解析器 |

> [!NOTE]
> **更正说明**：第一版给的三个行号（1593 / 1612 / 1654）指向的是 **`impl` 块**而不是类型定义，其中 `ProposedPlanItemState` 更是偏了 80 行。基线 commit 上的真实定义位置是 `ProposedPlanItemState` 1574、`PlanModeStreamState` 1582、`AssistantMessageStreamParsers` 1605；对应的 `impl` 块才在 1593 / 1654 / 1612。本文改为按符号名索引。

这三个类型都带 `impl` 块，说明 turn 内部至少存在**计划模式**与**流式消息解析**两条状态机。`PlanModeStreamState` 在 `turn.rs` 后半段被十几个函数以 `&mut` 形式穿透传递（`:1716` 起），`AssistantMessageStreamParsers::new(plan_mode)` 在 `:2212` 被构造——说明**计划模式是流式解析的一个输入参数**，两条状态机并非完全独立。完整的 turn 状态流转**未追踪**（E1）。

> [!CAUTION]
> **从既有 rollout 恢复会话是 `AGENTS.md` 点名的高风险改动面之一**（`### Breaking changes` 一节，grep `resuming sessions from existing rollouts`）。涉及 `rollout_reconstruction.rs` 的改动请格外谨慎。

---

## 4. 工具调用链路

这是本文证据最扎实的部分（E3）。

### 4.1 三个核心类型

| 类型 | 位置 | 角色 |
| ---- | ---- | ---- |
| `ToolCall` | `tools/router.rs:32` | 一次工具调用的载体 |
| `ToolRouter` | `tools/router.rs:68` | 路由与分发 |
| `ToolRegistry` | `tools/registry.rs:252` | 工具注册表 |

### 4.2 `ToolRouter` 的公开 API（E3）

```rust
// tools/router.rs:153 —— 从模型响应项构造工具调用
pub fn build_tool_call(item: ResponseItem)
    -> Result<Option<ToolCall>, FunctionCallError>;

// tools/router.rs:209 —— 分发（异步）
pub async fn dispatch_tool_call_with_code_mode_result(...);

// tools/router.rs:136 —— 该工具是否支持并行
pub fn tool_supports_parallel(&self, call: &ToolCall) -> bool;

// tools/router.rs:146 —— 该工具是否需要等待运行时取消
pub fn tool_waits_for_runtime_cancellation(&self, call: &ToolCall) -> bool;
```

**由此可确认的三件事**（E3）：

1. 工具调用是从模型的 `ResponseItem` **解析**出来的，而不是模型直接调用函数
2. 存在**并行执行**能力（`tool_supports_parallel` + `tools/parallel.rs`）
3. 存在**取消语义**，且不同工具的取消等待行为不同

### 4.3 调用链路上的其他环节

| 文件 | 职责 |
| ---- | ---- |
| `tools/orchestrator.rs` | 编排：**审批 → 选沙箱 → 尝试 → 升级重试**，见下 |
| `tools/lifecycle.rs` | 生命周期 |
| `tools/parallel.rs` | 并行执行 |
| `tools/approvals.rs` | 审批 |
| `tools/sandboxing.rs` | 沙箱决策 |
| `tools/network_approval.rs` | 网络访问审批 |
| `tools/executed_tool_calls.rs` | 已执行调用的记录 |
| `tools/tool_dispatch_trace.rs` | 分发追踪 |
| `tools/spec_plan.rs` | 工具规格计划 |
| `tools/hosted_spec.rs` | 托管工具规格 |
| `tools/events.rs` | 工具事件 |
| `tools/context.rs` | 工具上下文 |
| `tools/hook_names.rs` | 钩子名 |

> [!NOTE]
> **更正说明**：第一版把「审批发生在沙箱决策之前还是之后」标为未验证。**源码注释里就写着**。`tools/orchestrator.rs:1-8` 模块头：
>
> > "Central place for approvals + sandbox selection + retry semantics. Drives a simple sequence for any ToolRuntime: **approval → select sandbox → attempt → retry with an escalated sandbox strategy on denial (no re-approval thanks to caching)**."
>
> 代码里也有对应的编号注释：**`:151`** `// 1) Approval`（上一稿写作 `:148`，那一行其实是 `let otel_tn = ...`）、`:226` `// 2) First attempt under the selected sandbox.`，失败后在 `:299` 匹配 `SandboxErr::Denied` 并在 `:333` 起按 `tool.escalate_on_failure()` 决定是否升级重试。完整流程图见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7。

### 4.4 内置工具处理器（E1，来自 `tools/handlers/mod.rs` 的 `mod` 声明与 `pub use`）

| 模块 | 工具用途 |
| ---- | ---- |
| `shell` | shell 命令执行 |
| `apply_patch` | 应用结构化补丁 |
| `unified_exec` | **长驻进程式执行**：导出 `ExecCommandHandler`（`mod.rs:76`）与 `WriteStdinHandler`（`:78`），另有 `ExecCommandHandlerOptions`（`:77`）。对应 `core/src/unified_exec/` 与 `tools/runtimes/unified_exec.rs` |
| `view_image` | 查看图片 |
| `plan` | 计划 |
| `current_time` | 当前时间 |
| `sleep` | 休眠 |
| `mcp` / `mcp_resource` | MCP 工具与资源 |
| `tool_search` | 工具搜索 |
| `request_user_input` | 请求用户输入 |
| `request_permissions` | 请求权限 |
| `request_plugin_install` | 请求安装插件 |
| `list_available_plugins_to_install` | 列出可安装插件 |
| `get_context_remaining` | 查询剩余上下文 |
| `new_context_window` | 新建上下文窗口 |
| `wait_for_environment` | 等待环境就绪 |
| `multi_agents` / `multi_agents_v2` | 多智能体协作 |
| `multi_agents_common` | **两代多智能体的公共实现**（`mod.rs:14`），改任一代时都要看它 |
| `extension_tools` | 扩展提供的工具 |
| `dynamic` | 动态工具 |
| `test_sync` | 测试同步（测试用途） |

> **第一版遗漏**：`unified_exec` 与 `multi_agents_common` 两个模块。

`handlers/mod.rs` 还从**外部目录**重导出两个 handler（`:52-53`）：

```rust
pub(crate) use crate::tools::code_mode::CodeModeExecuteHandler;
pub(crate) use crate::tools::code_mode::CodeModeWaitHandler;
```

它们的实现在 `core/src/tools/code_mode/`（`execute_handler.rs` / `wait_handler.rs` / `execute_spec.rs` / `wait_spec.rs` / `delegate.rs` / `response_adapter.rs`，E1）。注册处见 `tools/spec_plan.rs:13-14`。

**模式**：多数 handler 有配套的 `*_spec.rs`（工具规格）与 `*_tests.rs`（单元测试）。新增工具时应遵循这个三件套结构。

### 4.5 托管（hosted）工具：有规格、无本地 handler

> 这个区分第一版没讲，容易让人以为「工具表 = 全部工具」。

工具规格枚举定义在 **`codex-rs/tools/src/tool_spec.rs:19`**（注意：不在 `codex-protocol`）：

```rust
pub enum ToolSpec {
    Function(ResponsesApiTool),      // 普通函数工具 —— 有本地 handler
    Namespace(ResponsesApiNamespace),
    ToolSearch { .. },
    WebSearch { external_web_access, indexed_web_access, filters,
                user_location, search_context_size, search_content_types },
    Freeform(FreeformTool),
}
```

`ToolSpec::WebSearch` 序列化为 `{"type": "web_search"}`，**由模型服务端执行**——`tools/handlers/` 下没有也不需要 `web_search` handler。core 侧只负责：

| 环节 | 位置 |
| ---- | ---- |
| 按配置决定是否下发该规格 | `tools/spec_plan.rs:373` `create_web_search_tool(WebSearchToolOptions { .. })`、`:1036` 检查 `web_search_mode != Disabled` |
| 规格构造选项 | `tools/hosted_spec.rs`（`WebSearchToolOptions`，`spec_plan.rs:56` 导入） |
| 结果回读 | 模型返回 `ResponseItem::WebSearchCall`（`protocol/src/models.rs:984`），在历史中标记为 `"ws"`（`:1111`） |

**图片生成走的是另一条路**：它不是 `ToolSpec` 的变体，而是通过**扩展**注入的——`codex-image-generation-extension` crate 的 `install` 函数（见 `core/tests/suite/extension_sandbox.rs:10`、`thread-manager-sample/src/main.rs:138`），响应项类型为 `image_generation_call`（`rollout-trace/src/reducer/conversation/normalize.rs:121`）。

**三类工具的判别方法**：在 `tools/handlers/mod.rs` 里 grep 得到的 → 本地 handler；在 `tool_spec.rs` 里但 handlers 里没有的 → 托管工具；两处都没有却出现在响应项里的 → 扩展或 MCP 提供。

### 4.6 工具运行时（`tools/runtimes/`）

| 运行时 | 文件 |
| ---- | ---- |
| shell | `shell.rs` + `shell/` 子目录 |
| apply_patch | `apply_patch.rs` |
| unified_exec | `unified_exec.rs` |

`handlers/apply_patch.lark` 是一个 **Lark 语法文件**，说明补丁格式有形式化文法定义。

---

## 5. 审批与沙箱策略（E3）

工具调用要落到真实执行，必须先过两道决策：**审批**与**沙箱**。两者的策略类型都定义在 `codex-protocol` 中。

### 5.1 `AskForApproval`（`codex-rs/protocol/src/protocol.rs:917`）

| 变体 | 语义 |
| ---- | ---- |
| `UnlessTrusted`（序列化名 `untrusted`） | 只有 **`is_known_safe_command()`** 判定为"已知安全且只读"的命令自动放行，其余一律询问 |
| `OnRequest`（**默认**，兼容别名 `on-failure`） | 由模型决定何时请求用户批准 |
| `Granular(GranularApprovalConfig)` | 细粒度控制。字段为 `true` 表示放行该类，`false` 表示**自动拒绝**（而不是弹给用户） |
| `Never` | 永不询问。失败直接返回模型，不上升到用户 |

> [!WARNING]
> **`is_safe_command()` 这个函数名不存在**，第一版沿用了错误的名字。真实定义是
> `pub fn is_known_safe_command(command: &[String]) -> bool`，位于
> `codex-rs/shell-command/src/command_safety/is_safe_command.rs:12`——**模块**叫 `is_safe_command`，**函数**叫 `is_known_safe_command`。
>
> 上游源码注释里也还留着旧名：`protocol.rs:919`（正是 `UnlessTrusted` 上方那段文档注释）与 `core/src/tools/runtimes/shell/unix_escalation.rs:362`。按旧名 grep 只会命中注释。

`GranularApprovalConfig` 的 5 个字段（`protocol.rs:943-955`，E3）：

| 字段 | 控制的审批流 |
| ---- | ---- |
| `sandbox_approval` | shell 命令审批，含内联的 `with_additional_permissions` 与 `require_escalated` 请求 |
| `rules` | 由 execpolicy `prompt` 规则触发的提示 |
| `skill_approval` | 技能脚本执行触发的审批（`#[serde(default)]`） |
| `request_permissions` | 由 `request_permissions` 工具触发的提示（`#[serde(default)]`） |
| `mcp_elicitations` | MCP elicitation 提示 |

> [!WARNING]
> `Granular` 中字段为 `false` 的语义是**自动拒绝**，不是"询问用户"。枚举上方的文档注释原话：「When a field is `true`, commands in that category are allowed. When it is `false`, those requests are **automatically rejected instead of shown to the user**.」

### 5.2 `SandboxPolicy`（`codex-rs/protocol/src/protocol.rs:1004`）

> [!IMPORTANT]
> **`SandboxPolicy` 已不是运行时策略类型。** 运行时流转的是 `PermissionProfile`（`protocol/src/models.rs:316`），拆成**文件系统**与**网络**两个正交维度；`SandboxPolicy` 退化为**线上/兼容层**类型（`compatibility_sandbox_policy_for_permission_profile`）。详见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §1.5。下表描述的是这个兼容层类型。
>
> **勘误**：上一稿把这两个维度写成"`FileSystemSandboxPolicy` + `NetworkSandboxPolicy`"，**文件系统那一半是错的**。`PermissionProfile::Managed` 的字段类型是 `file_system: ManagedFileSystemPermissions`（`models.rs:258` 定义的枚举）与 `network: NetworkSandboxPolicy`（`models.rs:320-322`）；`FileSystemSandboxPolicy` 是**另一个类型**，要经 `ManagedFileSystemPermissions::to_sandbox_policy()`（`models.rs:288`）转换后才出现。只有网络那一维是直接用 `*SandboxPolicy` 的。

| 变体 | 磁盘 | 网络 |
| ---- | ---- | ---- |
| `DangerFullAccess`（`danger-full-access`） | 无限制 | 无限制 |
| `ReadOnly`（`read-only`） | 只读 | `network_access: bool`，**默认 false** |
| `WorkspaceWrite`（`workspace-write`） | 只读 + cwd 可写 | `network_access: bool`，**默认 false** |
| `ExternalSandbox`（`external-sandbox`） | 完整磁盘访问（表示进程已在外部沙箱内） | `network_access: NetworkAccess`，**不是 bool** |

> [!WARNING]
> **`ExternalSandbox` 的 `network_access` 类型与另外两个变体不同。** 它是枚举而非布尔：
>
> ```rust
> // protocol.rs:988-992
> pub enum NetworkAccess {
>     #[default]
>     Restricted,
>     Enabled,
> }
> ```
>
> 默认值是 `Restricted`（等价于「不放开」），判定用 `NetworkAccess::is_enabled()`（`:995`）。写匹配代码时不能把四个变体的 `network_access` 当同一类型处理。

`WorkspaceWrite` 的可调字段：

- `writable_roots`：cwd 之外的额外可写目录
- `exclude_tmpdir_env_var`：为 `true` 时**不**把用户级 `TMPDIR` 计入默认可写根
- `exclude_slash_tmp`：为 `true` 时在 UNIX 上**不**把 `/tmp` 计入默认可写根

另有 `WritableRoot`（`protocol.rs:1060`）承载「可写根之下仍需只读的子路径」，其文档注释点名了 `.codex`、`.git`（尤其 `.git/hooks`）——**防止智能体通过改写这些目录自我提权**。

> **默认收紧**：三个带 `network_access` 的变体默认都不放开网络。放开网络是显式动作。

沙箱的平台实现见 [`tools_and_sandbox.md`](./tools_and_sandbox.md)。

### 5.3 `ReviewDecision`：审批的返回值（`protocol.rs:4120`，E3）

> 第一版两篇文档都没提这个类型，但它是审批链路的出口。

```rust
/// User's decision in response to an ExecApprovalRequest.
pub enum ReviewDecision { .. }
```

**7 个变体**（序列化为 snake_case）：

| 变体 | 语义 |
| ---- | ---- |
| `Approved` | 批准本次执行 |
| `ApprovedExecpolicyAmendment { proposed_execpolicy_amendment }` | 批准并**落盘一条 execpolicy 修正**，后续同类命令自动放行 |
| `ApprovedForSession` | 批准，且**本会话内**同一审批缓存键的后续请求自动放行 |
| `NetworkPolicyAmendment { network_policy_amendment }` | 对同一 host 的后续请求**持久化一条网络策略规则**（允许或拒绝） |
| `Denied { rejection: String }` | 拒绝本次，但**会话继续**，智能体应换个做法 |
| `TimedOut` | **自动评审超时**（对应 Guardian 后端，见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7） |
| `Abort` | 拒绝，且**在用户下一条指令前什么都不做** |

> [!IMPORTANT]
> **`Default` 是拒绝，不是批准**：
>
> ```rust
> impl Default for ReviewDecision {
>     fn default() -> Self {
>         Self::Denied { rejection: "denied".to_string() }
>     }
> }
> ```
>
> 即任何「没拿到明确决定」的路径都会 fail-closed。另有便捷构造 `ReviewDecision::denied(rejection)`。

注意区分三种「否」：`Denied` 让智能体继续尝试别的办法，`Abort` 让智能体停下等用户，`TimedOut` 表示自动评审没在时限内给出结论。三者不可互换。

---

## 6. 上下文管理与压缩

### 6.1 `context_manager/`（E1 结构）

| 文件 | 职责 |
| ---- | ---- |
| `history.rs` | 历史记录 |
| `normalize.rs` | 归一化 |
| `updates.rs` | 增量更新 |

### 6.2 压缩（compact）相关文件

`core/src/` 下与压缩相关的有 8 个文件：

| 文件 | 说明 |
| ---- | ---- |
| `compact.rs` | 压缩主体 |
| `compact_token_budget.rs` | token 预算 |
| `compact_model_fallback.rs` | 模型回退 |
| `compact_remote.rs` | 远程压缩 |
| `compact_remote_v2.rs` / `compact_remote_v2_attempt.rs` | 远程压缩 v2 |
| `compact_remote_request.rs` | 远程压缩请求 |
| `compact_tests.rs` | 测试 |

**可确认的事实**（E2/E3）：压缩存在**本地**与**远程**两条路径，远程路径有 v1/v2 两代，且带**模型回退**机制。

> **未验证**（E1）：v1 与 v2 的选择条件、回退触发条件、本地与远程的分工。这需要完整读取上述 8 个文件。集成测试在 `codex-rs/core/tests/suite/compact.rs`（5,440 行），是理解压缩行为的最佳入口。压缩本身是一种 `SessionTask`（`tasks/compact.rs`，见 §2.3）。

---

## 7. 仓库规范的注入

`core/src/agents_md.rs` 与 `agents_md_manager.rs` 负责读取仓库中的规范文件并注入模型上下文。

> 这解释了为什么仓库根的 `AGENTS.md` 对 Codex 自身有约束力——它不只是给人看的文档，也是运行时注入的内容。

---

## 8. 改动本区域的注意事项

> 引用约定：`AGENTS.md` 的行号会随改动漂移，下表一律按**标题 + 可 grep 的关键词**定位。

| 事项 | 依据（AGENTS.md） |
| ---- | ---- |
| **改智能体逻辑必须补集成测试**，位于 `core/tests/suite/`，用 `test_codex` 搭建实例 | `### Test authoring guidance`，grep `use `test_codex` to set up a test instance` |
| 需列出主要逻辑变更与用户可见行为清单 | `### Test authoring guidance`，grep `list of major logic changes and user-facing behaviors` |
| 单元测试要放进独立的 `*_tests.rs` | `### Test authoring guidance` 末句 / `### Test module organization` |
| 改了 core、common 或 protocol 后要跑全量 `just test`，且**跑全量前先问用户** | `## Tests` 上方的编号列表，grep `if any changes were made in common, core, or protocol` |
| 不要直接 `cargo test`，一律走 `just test` | 同上编号列表第 1 条 |
| 不要无必要地调用 `reset_client_session`，让增量检查逻辑决定是否复用上次请求 | 顶部规则列表，grep `Do not call `reset_client_session` unnecessarily` |
| 改了 `Cargo.toml` / `Cargo.lock` 要跑 `just bazel-lock-update` 并把 lockfile 一起提交 | 顶部规则列表，grep `just bazel-lock-update` |
| **默认不要往 core 加代码** | `## The codex-core crate`，grep `resist adding code to codex-core` |
| 单次改动尽量控制规模 | `### Change size guidance (800 lines)` |
| 外部集成面（app-server API、CLI 参数、配置加载、rollout 恢复）属破坏性改动高风险区 | `### Breaking changes` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `run_turn` 内部的完整流程 | E1 | `tasks/regular.rs`、`session/turn.rs`（分段读）、`session/turn_tests.rs` |
| `Op` / `EventMsg` 的完整变体清单 | E1 | `protocol/src/protocol.rs:531`、`:1288` |
| `SessionTask` 四种实现的差异 | E1 | `tasks/regular.rs`、`compact.rs`、`review.rs`、`user_shell.rs` |
| 压缩的 v1/v2 选择与回退条件 | E1 | `core/tests/suite/compact.rs`（5,440 行） |
| 模型客户端的请求构造与流式解析 | E1 | `client.rs`、`client_common.rs` |
| 多智能体协作机制 | E1 | `session/multi_agents.rs`、`tools/handlers/multi_agents_common`、`multi_agents_v2/` |
| token 预算的具体算法 | E1 | `session/token_budget.rs`、`compact_token_budget.rs` |
| `is_known_safe_command()` 的判定规则 | E1 | `codex-rs/shell-command/src/command_safety/` |
| Guardian 评审的具体策略 | E1 | `core/src/guardian/policy.md`、`prompt.rs` |
| code_mode 的委派机制 | E1 | `core/src/tools/code_mode/delegate.rs`、`response_adapter.rs` |

> **已从本表移除**：「工具调用各环节的次序」——见 §4.3，`orchestrator.rs` 模块头注释直接写明。

---

## 10. 相关文档

- [架构总览](./architecture_overview.md) — 进程边界与整体拓扑
- [Crate 地图](./crate_map.md) — core 的依赖热点与减负指引
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱的平台实现
- [配置体系](./config_system.md) — 审批与沙箱策略的配置入口
- [会话与持久化](./session_and_persistence.md) — rollout 与线程存储
