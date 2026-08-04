---
title: Codex 智能体核心循环
summary: 描述 codex-core 的提交-事件协议与三层循环（submission_loop → SessionTask → turn 循环）、会话与 turn 组织方式、工具调用的路由与分发链路、实时会话（realtime_conversation）子系统、上下文管理与压缩路径选择、审批与沙箱决策的接入点；给出 Op（26）与 EventMsg（80）的准确变体计数，并标注各结论的证据等级与未验证边界。
keywords: codex | agent-loop | submission-loop | session-task | turn | tool-router | permission-profile | context-manager | compact | realtime-conversation
scope: codex-rs/core 的提交循环、任务层、会话、turn、工具调用、实时会话与上下文管理
related_files: codex-rs/core/src/session/handlers.rs | codex-rs/core/src/session/mod.rs | codex-rs/core/src/session/turn.rs | codex-rs/core/src/tasks/mod.rs | codex-rs/core/src/tasks/regular.rs | codex-rs/core/src/tasks/compact.rs | codex-rs/core/src/tools/router.rs | codex-rs/core/src/tools/registry.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/core/src/tools/handlers/mod.rs | codex-rs/core/src/tools/approvals.rs | codex-rs/core/src/realtime_conversation.rs | codex-rs/core/src/exec_policy.rs | codex-rs/core/src/safety.rs | codex-rs/core/src/context_manager | codex-rs/core/Cargo.toml | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/tools/src/tool_spec.rs | codex-rs/shell-command/src/command_safety/is_safe_command.rs | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-05
---

# 智能体核心循环

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/core`（296,963 行）的骨架结构与三层循环
> **证据等级**: 循环链路、类型与函数签名为 E3；目录与文件计数为 E1；模块间部分协作关系为 E1，已在文中逐处标注

> [!IMPORTANT]
> `codex-core` 是全仓最大的 crate。本文给出的是**可导航的骨架**，不是逐行讲解。遇到本文标注为 E1 的判断，请回去读代码，不要直接采信。

> [!WARNING]
> **本文第一版存在结构性缺失与若干计数/位置错误，已在前一轮修订中更正**：标题写着「核心循环」却完全没有描述循环本身（新增 §2）；`codex-rs/core/Cargo.toml` 的依赖计数、`session/` 与 `tools/` 的文件数、`codex-rs/core/src/session/turn.rs` 的类型位置、`is_safe_command()` 的函数名均有误。相关段落保留了更正说明。
>
> **本轮（第三版）进一步更正**：`codex-rs/core/src/safety.rs` 被误标为「命令安全判定入口」（实际是 apply_patch 写入路径判定，见 §1 与 §5.1）；`codex-rs/core/src/realtime_conversation.rs` 子系统被当成小子目录一笔带过（实际 2,465 行、是 `submission_loop` 五个 `Op` 分支的直接被调方，新增 §4.7）；`Op` / `EventMsg` 的变体计数、`session/` 与 handler 配套文件清单、若干行号区间与绝对化措辞均已修正；原列为「未验证」的压缩路径选择、`SessionTask` 四种实现差异等已就地降为 E3。

---

## 1. codex-core 的模块版图

`codex-rs/core/src/` 下的一级条目超过 100 个（其中 17 个是子目录）。按职责归类：

| 子系统 | 位置 | 说明 |
| ---- | ---- | ---- |
| **提交循环** | `codex-rs/core/src/session/handlers.rs`、`codex-rs/core/src/session/mod.rs` | `submission_loop`：消费 `Submission`、按 `Op` 分派，见 §2.1 |
| **任务层** | `tasks/` | `SessionTask` 抽象与 4 种实现（regular / compact / review / user_shell），见 §2.2 |
| **会话与 turn** | `session/`（29 个文件 + `snapshots/`、`tests/`） | 会话生命周期、turn 组织、上下文窗口、token 预算 |
| **线程编排** | `codex-rs/core/src/thread_manager.rs`、`codex-rs/core/src/codex_thread.rs` | 线程管理与线程实例 |
| **工具调用** | `tools/`（26 个文件 + `code_mode/`、`handlers/`、`runtimes/`） | 路由、注册表、编排、审批、沙箱决策 |
| **审批评审** | `guardian/` | Guardian 自动评审后端，见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7 |
| **补丁写入安全判定** | `codex-rs/core/src/safety.rs` | `assess_patch_safety()`：判定 apply_patch 的写入路径是否越出可写根，唯一调用方 `codex-rs/core/src/apply_patch.rs:39` |
| **命令安全判定** | `codex-rs/core/src/exec_policy.rs` | 接入 `codex-shell-command` 的 `is_known_safe_command()`，见 §5.1 |
| **沙箱接入** | `sandboxing/` | core 侧对 `codex-sandboxing` 的封装 |
| **统一执行** | `unified_exec/` | 长驻进程式命令执行（对应 `ExecCommandHandler` / `WriteStdinHandler`） |
| **上下文历史** | `context_manager/` | 历史、归一化、增量更新（3 个生产文件，见 §6.1） |
| **上下文片段构造** | `context/` | 注入模型上下文的**文案/指令片段构造器**（34 个条目：`codex-rs/core/src/context/environment_context.rs`、`codex-rs/core/src/context/user_instructions.rs`、`codex-rs/core/src/context/permissions_instructions.rs`、`codex-rs/core/src/context/turn_aborted.rs`、`codex-rs/core/src/context/realtime_start_instructions.rs`、`world_state/` 等），与 `context_manager/` 不是一回事 |
| **上下文压缩** | `compact*.rs`（8 个文件） | 本地压缩、远程压缩 v1/v2、token 预算、模型回退，路径选择见 §6.2 |
| **实时会话** | `codex-rs/core/src/realtime_conversation.rs`（2,465 行）+ `realtime_conversation/` | 语音/实时会话状态机与向常规 turn 的 handoff，见 §4.7 |
| **模型客户端** | `codex-rs/core/src/client.rs`、`codex-rs/core/src/client_common.rs` | 与模型服务通信 |
| **状态持久化** | `state/` | core 侧对 `codex-state` 的接入 |
| **配置** | `config/` | 配置加载与校验（详见 [`config_system.md`](./config_system.md)） |
| **执行** | `codex-rs/core/src/exec.rs`、`codex-rs/core/src/exec_env.rs`、`codex-rs/core/src/exec_policy.rs` | 命令执行与策略 |
| **规范注入** | `codex-rs/core/src/agents_md.rs`、`codex-rs/core/src/agents_md_manager.rs` | 读取并注入仓库规范文件 |
| **补丁应用** | `codex-rs/core/src/apply_patch.rs` | 结构化补丁 |
| **技能与钩子** | `codex-rs/core/src/skills.rs`、`codex-rs/core/src/hook_runtime.rs` | 技能定义、钩子运行时 |
| **插件** | `plugins/` | 插件装载（对应 `request_plugin_install` 等工具） |
| **扩展接入** | `apps/`、`agent/`、`codex-rs/core/src/connectors.rs` | 扩展与连接器 |
| **其他子目录** | `bin/`、`mcp_tool_call/`、`utils/` | 二进制入口、MCP 调用、工具函数 |

> [!NOTE]
> **更正说明**：第一版此表把 `session/` 记为 28 个文件、`tools/` 记为 28 个文件，且完全遗漏了 `tasks/`、`guardian/`、`codex-rs/core/src/safety.rs`、`codex-rs/core/src/thread_manager.rs`、`codex-rs/core/src/codex_thread.rs`、`sandboxing/`、`state/`、`context/`、`plugins/`、`codex-rs/core/src/skills.rs`、`codex-rs/core/src/hook_runtime.rs`、`unified_exec/`。计数与清单已按下述命令重新核对（E1）：
>
> ```bash
> # 在 codex-rs/core/src 下
> ls -p session/ | grep -v / | wc -l   # → 29（另有 snapshots/ tests/ 两个目录）
> ls -p tools/   | grep -v / | wc -l   # → 26（另有 code_mode/ handlers/ runtimes/ 三个目录）
> ls -p .        | grep /              # → 17 个一级子目录
> ```

> [!NOTE]
> **未验证**（E1）：上表仍是按文件名与目录归类的**结构性描述**，各子系统之间的调用次序与依赖方向未做完整追踪。（`compact*.rs` 的分工与路径选择原本也列在这里，已在 §6.2 中降为 E3。）

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
| **上表之外**：target-gated 生产依赖 | 3 条，不在 `[dependencies]` 段内——`[target.x86_64-unknown-linux-musl.dependencies] openssl-sys`、`[target.aarch64-unknown-linux-musl.dependencies] openssl-sys`、`[target.'cfg(unix)'.dependencies] codex-shell-escalation` |
| **上表之外**：`[dev-dependencies]` | 28（测试依赖，不计入生产口径） |

> [!NOTE]
> `codex-shell-escalation` 是**仓内 crate**，因此「仓内 `codex-*` = 57」只在非 unix 平台成立；**在 unix 上实际为 58**。做依赖裁剪统计时不要漏掉这三个 target 段。

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
| 循环体是 `while let Ok(sub) = rx_sub.recv().await`，从一个 channel 消费 `Submission` | `codex-rs/core/src/session/handlers.rs:721` |
| 分派方式是 `match sub.op.clone()`，即**按 `Op` 变体分支** | `codex-rs/core/src/session/handlers.rs:725` |
| **正常**退出方式是 `Op::Shutdown` | `codex-rs/core/src/session/handlers.rs:719` 注释：「To break out of this loop, send `Op::Shutdown`」 |
| 每次提交都开一个 tracing span | `submission_dispatch_span(&sub)`，`codex-rs/core/src/session/handlers.rs:723` |
| 循环在会话创建时 `tokio::spawn` 起来 | `codex-rs/core/src/session/mod.rs:769`，span 名 `session_loop`，带 `thread_id` |

> [!NOTE]
> **勘误（行号）**：上表前四行的行号上一稿分别写作 `:720` / `:724` / `:718` / `:722`，**各差一行**，已按 `sed -n '714,726p'` 的实际内容改为 `:721` / `:725` / `:719` / `:723`。`submission_loop` 函数签名本身在 `:714`，这一处是对的。

> [!CAUTION]
> **勘误（结论）：「唯一的退出方式是 `Op::Shutdown`」不成立。**
>
> `codex-rs/core/src/session/handlers.rs:719` 那句注释确实这么写，但**注释描述的是意图，不是全部实现**。同一函数在循环之后还有一段（`codex-rs/core/src/session/handlers.rs:872-881`）：
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

`codex-rs/core/src/session/mod.rs:766-778` 还把这个 join handle 包成了 `SessionIo { tx_sub, rx_event, agent_status, session_loop_termination }`——**提交进 `tx_sub`、事件出 `rx_event`**，这就是会话的全部对外接口形状。

### 2.2 提交-事件协议：`Submission` / `Op` / `Event` / `EventMsg`

> 第一版完全没有提到这四个类型，但它们是理解整个 core 的前提。

全部定义在 `codex-rs/protocol/src/protocol.rs`：

| 类型 | 位置 | 方向 | 角色 |
| ---- | ---- | ---- | ---- |
| `Submission` | `:176` | 客户端 → core | 一次提交，含 `id` 与 `op` |
| `Op` | `:531`（枚举体 `:531-688`） | 客户端 → core | 提交的动作枚举，**26 个变体** |
| `Event` | `:1270` | core → 客户端 | 一次事件，含 `id` 与 `msg` |
| `EventMsg` | `:1288`（枚举体 `:1288-1495`） | core → 客户端 | 事件负载枚举，**80 个变体** |

这是一个**非对称的请求-流式响应模型**：一次 `Submission` 可能产生任意多个 `Event`，两者靠 `id` 关联。`codex-rs/core/src/session/handlers.rs` 中大量出现的 `sess.send_event(&turn_context, event.msg)` 与 `sess.send_event_raw(Event { id, msg })` 就是这条出向通道。

`Op` 的 **26 个变体**依次为（E3，`codex-rs/protocol/src/protocol.rs:531-688`）：

```
Interrupt, CleanBackgroundTerminals,
RealtimeConversationStart, RealtimeConversationAudio, RealtimeConversationText,
RealtimeConversationSpeech, RealtimeConversationClose, RealtimeConversationListVoices,
UserInput, ThreadSettings, InterAgentCommunication,
ExecApproval, PatchApproval, ResolveElicitation, UserInputAnswer,
RequestPermissionsResponse, DynamicToolResponse,
RefreshMcpServers, ReloadUserConfig, Compact, SetThreadMemoryMode, ThreadRollback,
Review, ApproveGuardianDeniedAction, Shutdown, RunUserShellCommand
```

交叉印证：`codex-rs/core/src/session/handlers.rs` 中 `Op::` 的去重命中集合与上面这 26 个名字**完全相同**（`grep -o 'Op::[A-Za-z0-9_]*' … | sort -u` 逐字符比对无差异），即 `submission_loop` 显式覆盖了全部变体，没有遗漏也没有多余。

> [!IMPORTANT]
> **`Op` 标了 `#[non_exhaustive]`**（`codex-rs/protocol/src/protocol.rs:530`）。因此 `submission_loop` 的 `match` 末尾那条 `_ => false`（`codex-rs/core/src/session/handlers.rs:862`，行内注释即 `// Ignore unknown ops; enum is non_exhaustive to allow extensions.`）**不是死代码**——它是给跨 crate 的外部扩展留的兜底分支，不要当成「漏了某个变体」去补。
>
> **数变体数时的陷阱**：带结构体字段的变体（如 `UserInput { .. }`、`ExecApproval { .. }`）跨多行。用逐行 brace-depth 脚本统计时，如果在**更新括号深度之后**才判定当前行是不是变体，这些变体会被整体跳过——本轮核验中就有一次据此数出 16，与真实的 26 差了 10 个。判定必须在更新深度**之前**做。

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
| `codex-rs/core/src/tasks/mod.rs` | `SessionTask` trait。**注意 `enum TaskKind` 并不定义在这里**——它的定义在 `codex-rs/core/src/state/turn.rs:67`，`codex-rs/core/src/tasks/mod.rs:35` 只是 `use crate::state::TaskKind;` 把它引进来 |
| `codex-rs/core/src/tasks/regular.rs` | 常规智能体任务（默认路径，含 turn 循环） |
| `codex-rs/core/src/tasks/compact.rs` | 上下文压缩任务 |
| `codex-rs/core/src/tasks/review.rs` | 评审任务 |
| `codex-rs/core/src/tasks/user_shell.rs` | 用户 shell 任务 |
| `codex-rs/core/src/tasks/lifecycle.rs` | 任务生命周期 |
| `codex-rs/core/src/tasks/mod_tests.rs` / `codex-rs/core/src/tasks/user_shell_tests.rs` | 测试 |

**四种实现的 `kind()` / `span_name()`**（E3）：

| 实现 | `kind()` | `span_name()` | 构造点 |
| ---- | ---- | ---- | ---- |
| `RegularTask` | `TaskKind::Regular` | `"session_task.turn"` | `codex-rs/core/src/session/handlers.rs:267`、`codex-rs/core/src/tasks/mod.rs:473`、`codex-rs/core/src/session/inject.rs:131` |
| `CompactTask` | `TaskKind::Compact` | `"session_task.compact"` | 仅 `codex-rs/core/src/session/handlers.rs:458` |
| `ReviewTask` | `TaskKind::Review` | `"session_task.review"` | 仅 `codex-rs/core/src/session/review.rs:173` |
| `UserShellCommandTask`（`codex-rs/core/src/tasks/user_shell.rs:70-75`） | **`TaskKind::Regular`** | `"session_task.user_shell"` | `codex-rs/core/src/session/handlers.rs:326` |

> [!IMPORTANT]
> **「4 种实现」对应的不是 4 个 `TaskKind`。** `enum TaskKind` 只有 **3 个变体**（`Regular` / `Review` / `Compact`，`codex-rs/core/src/state/turn.rs:67-71`），而 `codex-rs/core/src/tasks/user_shell.rs:71` 让 `UserShellCommandTask` 复用了 `TaskKind::Regular`，只能靠 `span_name()` 在 tracing 里区分。按 `TaskKind` 分支写逻辑时，**用户 shell 任务会落进常规分支**。
>
> 另外 `Op::RunUserShellCommand` 有**两条**路径（分派臂在 `codex-rs/core/src/session/handlers.rs:838`，实现在同文件 `run_user_shell_command()` `:304-329`）：若当前**已有活跃 turn**，则**不建 task**，直接 `tokio::spawn(execute_user_shell_command(..., UserShellCommandMode::ActiveTurnAuxiliary))` 挂在既有 turn 上；只有在没有活跃 turn 时才 `spawn_task(.., UserShellCommandTask::new(command))`。

`codex-rs/core/src/tasks/mod.rs:180-200` 的 trait 文档写明：任务由 `Session` 在**后台 Tokio task** 上执行；实现者通过 `cancellation_token` 感知中止请求并**尽快终止**；`run` 返回 `Some(msg)` 时该消息会由 `Session::on_task_finished` 发给客户端；返回 `CodexErr::TurnAborted` 则走「已中止 turn」的完成路径。

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

1. **`codex-rs/core/src/session/input_queue.rs` 为什么存在**——用户可以在模型还在跑的时候继续输入；一个 turn 结束后如果队列里还有排队输入，**不返回、直接再跑一个 turn**。
2. **`next_input = Vec::new()` 的含义**（E3）——后续 turn 的输入不是从这里传的，而是由 `run_turn` 内部从 `input_queue` 取。`run_turn` 的签名在 `codex-rs/core/src/session/turn.rs:149`，取队列的调用在 `codex-rs/core/src/session/turn.rs:273-274` 的 `sess.input_queue.get_pending_input(&sess.active_turn)`。这两条是 E3，不在下面的未验证范围内。

> **未验证**（E1）：`run_turn` 内部**其余**流程（构造请求 → 流式解析 → 工具调用 → 写回历史）本文未逐段追踪。入口见 `codex-rs/core/src/tasks/regular.rs` 与 `codex-rs/core/src/session/turn.rs:149`。

---

## 3. 会话与 turn

### 3.1 `session/` 的组成（E1）

| 文件 | 职责（依据文件名与公开类型） |
| ---- | ---- |
| `codex-rs/core/src/session/mod.rs` | 模块根：`Session` 构造、`SessionIo`（`:393`）、`send_event` / `send_event_raw`（`:1824` / `:2040`） |
| `codex-rs/core/src/session/session.rs` | 会话主体 |
| `codex-rs/core/src/session/turn.rs` | 单轮交互（`run_turn` 在 `:149`） |
| `codex-rs/core/src/session/turn_context.rs` | turn 级上下文 |
| `codex-rs/core/src/session/step_context.rs` | 步级上下文 |
| `codex-rs/core/src/session/context_window.rs` | 上下文窗口 |
| `codex-rs/core/src/session/token_budget.rs` / `codex-rs/core/src/session/rollout_budget.rs` | token 与 rollout 预算（**注意**仓内另有 `codex-rs/core/src/rollout_budget.rs` 与 `codex-rs/core/src/context/rollout_budget.rs`，是不同文件） |
| `codex-rs/core/src/session/input_queue.rs` | 输入队列 |
| `codex-rs/core/src/session/handlers.rs` | 提交循环与 `Op` 分派 |
| `codex-rs/core/src/session/inject.rs` | 注入 |
| `codex-rs/core/src/session/review.rs` | 评审模式 |
| `codex-rs/core/src/session/multi_agents.rs` | 多智能体 |
| `codex-rs/core/src/session/world_state.rs` | 世界状态 |
| `codex-rs/core/src/session/config_lock.rs` | 配置锁 |
| `mcp*.rs`（4 个生产 + 1 个测试） | MCP 接入：`codex-rs/core/src/session/mcp.rs` / `codex-rs/core/src/session/mcp_runtime.rs` / `codex-rs/core/src/session/mcp_prewarm.rs` / `codex-rs/core/src/session/mcp_refresh.rs`（另有 `codex-rs/core/src/session/mcp_tests.rs`） |
| `codex-rs/core/src/session/rollout_reconstruction.rs` | 从既有 rollout 恢复会话 |
| `codex-rs/core/src/session/time_reminder.rs` | 时间提醒 |
| `codex-rs/core/src/session/extension_metrics.rs` | 扩展指标 |
| `codex-rs/core/src/session/code_mode_warning.rs` | code-mode 警告 |

> [!NOTE]
> **本轮补入**：`codex-rs/core/src/session/mod.rs`、`codex-rs/core/src/session/world_state.rs`、`codex-rs/core/src/session/config_lock.rs` 三个生产文件此前漏列。其中模块根的遗漏尤其要命——§2.1 自己就在引用 `codex-rs/core/src/session/mod.rs:769` 与 `:766-778`，而本表却没有它。
>
> 上表 23 个生产文件之外，`session/` 还有 6 个 `*_tests.rs`（`tests.rs`、`turn_tests.rs`、`mcp_tests.rs`、`code_mode_warning_tests.rs`、`elicitation_holders_tests.rs`、`rollout_reconstruction_tests.rs`）<!-- ref-exempt: 此处列举的是同目录内测试文件的裸文件名，前文已给出目录 --> 与 `snapshots/`、`tests/` 两个目录，合计 29 个文件。

### 3.2 turn 的内部状态（E3）

`codex-rs/core/src/session/turn.rs` 中可见的状态类型。**用 grep 定位，不要依赖行号**（这些类型在文件后半段，行号随改动漂移很快）：

| 类型 | 定位方式 | 用途 |
| ---- | ---- | ---- |
| `ProposedPlanItemState` | `rg -n 'struct ProposedPlanItemState' core/src/session/turn.rs` | 提议的计划项状态 |
| `PlanModeStreamState` | `rg -n 'struct PlanModeStreamState' core/src/session/turn.rs` | 计划模式的流式状态（内含一个 `plan_item_state: ProposedPlanItemState` 字段） |
| `AssistantMessageStreamParsers` | `rg -n 'struct AssistantMessageStreamParsers' core/src/session/turn.rs` | 助手消息的流式解析器 |

> [!NOTE]
> **更正说明**：第一版给的三个行号指向的是 **`impl` 块**而不是类型定义——它给 `ProposedPlanItemState` 标了 **1654**，而真实定义在 **1574**，偏了整整 80 行。基线 commit 上的对应关系是：
>
> | 类型 | 定义 | `impl` 块 |
> | ---- | ---: | ---: |
> | `ProposedPlanItemState` | 1574 | **1654** |
> | `PlanModeStreamState` | 1582 | **1593** |
> | `AssistantMessageStreamParsers` | 1605 | **1612** |
>
> 注意 `impl` 块并不按定义顺序排列（`ProposedPlanItemState` 的 `impl` 在最后），这正是第一版把行号张冠李戴的原因。本文改为按符号名索引。

这三个类型都带 `impl` 块，说明 turn 内部至少存在**计划模式**与**流式消息解析**两条状态机。`PlanModeStreamState` 在 `codex-rs/core/src/session/turn.rs` 后半段被 **9 个**函数以 `&mut` 形式穿透传递（`:1716` / `:1834` / `:1897` / `:1932` / `:1944` / `:1963` / `:1993` / `:2037` / `:2058`，其中 `:1897` / `:1932` / `:1944` 三处是 `Option<&mut …>`），`AssistantMessageStreamParsers::new(plan_mode)` 在 `:2212` 被构造——说明**计划模式是流式解析的一个输入参数**，两条状态机并非完全独立。完整的 turn 状态流转**未追踪**（E1）。

> [!CAUTION]
> **从既有 rollout 恢复会话是 `AGENTS.md` 点名的高风险改动面之一**（`### Breaking changes` 一节，grep `resuming sessions from existing rollouts`）。涉及 `codex-rs/core/src/session/rollout_reconstruction.rs` 的改动请格外谨慎。

---

## 4. 工具调用链路

这是本文证据最扎实的部分（E3）。

### 4.1 三个核心类型

| 类型 | 位置 | 角色 |
| ---- | ---- | ---- |
| `ToolCall` | `codex-rs/core/src/tools/router.rs:32` | 一次工具调用的载体 |
| `ToolRouter` | `codex-rs/core/src/tools/router.rs:68` | 路由与分发 |
| `ToolRegistry` | `codex-rs/core/src/tools/registry.rs:252` | 工具注册表 |

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
2. 存在**并行执行**能力（`tool_supports_parallel` + `codex-rs/core/src/tools/parallel.rs`）
3. 存在**取消语义**，且不同工具的取消等待行为不同

### 4.3 调用链路上的其他环节

| 文件 | 职责 |
| ---- | ---- |
| `codex-rs/core/src/tools/orchestrator.rs` | 编排：**审批 → 选沙箱 → 尝试 → 升级重试**，见下 |
| `codex-rs/core/src/tools/lifecycle.rs` | 生命周期 |
| `codex-rs/core/src/tools/parallel.rs` | 并行执行 |
| `codex-rs/core/src/tools/approvals.rs` | 审批 |
| `codex-rs/core/src/tools/sandboxing.rs` | 沙箱决策 |
| `codex-rs/core/src/tools/network_approval.rs` | 网络访问审批 |
| `codex-rs/core/src/tools/executed_tool_calls.rs` | 已执行调用的记录 |
| `codex-rs/core/src/tools/tool_dispatch_trace.rs` | 分发追踪 |
| `codex-rs/core/src/tools/spec_plan.rs` | 工具规格计划 |
| `codex-rs/core/src/tools/hosted_spec.rs` | 托管工具规格 |
| `codex-rs/core/src/tools/events.rs` | 工具事件 |
| `codex-rs/core/src/tools/context.rs` | 工具上下文 |
| `codex-rs/core/src/tools/hook_names.rs` | 钩子名 |

> [!NOTE]
> **更正说明**：第一版把「审批发生在沙箱决策之前还是之后」标为未验证。**源码注释里就写着**。`codex-rs/core/src/tools/orchestrator.rs:1-8` 模块头：
>
> > "Central place for approvals + sandbox selection + retry semantics. Drives a simple sequence for any ToolRuntime: **approval → select sandbox → attempt → retry with an escalated sandbox strategy on denial (no re-approval thanks to caching)**."
>
> 代码里也有对应的编号注释：**`:151`** `// 1) Approval`（上一稿写作 `:148`，那一行其实是 `let otel_tn = ...`）、`:226` `// 2) First attempt under the selected sandbox.`，失败后在 `:299` 匹配 `SandboxErr::Denied` 并在 `:333` 起按 `tool.escalate_on_failure()` 决定是否升级重试。完整流程图见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7。

### 4.4 内置工具处理器（E3，来自 `codex-rs/core/src/tools/handlers/mod.rs` 的 `mod` 声明与 `pub use`）

| 模块 | 工具用途 |
| ---- | ---- |
| `shell` | shell 命令执行 |
| `apply_patch` | 应用结构化补丁 |
| `unified_exec` | **长驻进程式执行**：导出 `ExecCommandHandler`（`codex-rs/core/src/tools/handlers/mod.rs:76`）与 `WriteStdinHandler`（`:78`），另有 `ExecCommandHandlerOptions`（`:77`）。对应 `core/src/unified_exec/` 与 `codex-rs/core/src/tools/runtimes/unified_exec.rs` |
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
| `multi_agents_common` | **两代多智能体的公共实现**（`codex-rs/core/src/tools/handlers/mod.rs:14`），改任一代时都要看它 |
| `extension_tools` | 扩展提供的工具 |
| `dynamic` | 动态工具 |
| `test_sync` | 测试同步（测试用途） |

> **第一版遗漏**：`unified_exec` 与 `multi_agents_common` 两个模块。

`codex-rs/core/src/tools/handlers/mod.rs` 还从**外部目录**重导出两个 handler（`:53-54`）：

```rust
pub(crate) use crate::tools::code_mode::CodeModeExecuteHandler;
pub(crate) use crate::tools::code_mode::CodeModeWaitHandler;
```

它们的实现在 `core/src/tools/code_mode/`（`codex-rs/core/src/tools/code_mode/execute_handler.rs` / `codex-rs/core/src/tools/code_mode/wait_handler.rs` / `codex-rs/core/src/tools/code_mode/execute_spec.rs` / `codex-rs/core/src/tools/code_mode/wait_spec.rs` / `codex-rs/core/src/tools/code_mode/delegate.rs` / `codex-rs/core/src/tools/code_mode/response_adapter.rs`，E1）。注册处见 `codex-rs/core/src/tools/spec_plan.rs:13-14`。

**配套文件的真实比例**（E3，`codex-rs/core/src/tools/handlers/` 目录清单 + `codex-rs/core/src/tools/handlers/mod.rs` 的 `mod` 声明）：

| 口径 | 数量 |
| ---- | ---: |
| handler 模块总数 | 23 |
| 其中有 `*_spec.rs` | **13**（57%） |
| 其中有 `*_tests.rs` | **7**（30%）：`apply_patch` / `mcp_resource` / `multi_agents` / `request_plugin_install` / `request_user_input` / `shell` / `unified_exec` |
| 同时具备 handler + spec + tests 三件套 | **6**（`unified_exec` 有 tests 但无 spec） |

> [!WARNING]
> **上一稿写的「多数 handler 有配套的 `*_spec.rs` 与 `*_tests.rs`」不成立**，三件套只覆盖 23 个模块中的 6 个。
>
> `*_spec.rs` **只在工具需要向模型下发 JSON Schema 时出现**；规格在运行期动态构造的工具就没有这个文件。以下 10 个模块没有 `*_spec.rs`：`current_time`、`dynamic`、`extension_tools`、`mcp`、`multi_agents_common`、`multi_agents_v2`、`request_permissions`、`sleep`、`unified_exec`、`wait_for_environment`。新增工具时按需要决定是否配 spec，不要把三件套当作硬性规范。

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
| 按配置决定是否下发该规格 | `codex-rs/core/src/tools/spec_plan.rs:373` `create_web_search_tool(WebSearchToolOptions { .. })`、`:1036` 检查 `web_search_mode != Disabled` |
| 规格构造选项 | `codex-rs/core/src/tools/hosted_spec.rs`（`WebSearchToolOptions`，`codex-rs/core/src/tools/spec_plan.rs:56` 导入） |
| 结果回读 | 模型返回 `ResponseItem::WebSearchCall`（`codex-rs/protocol/src/models.rs:984`），在历史中标记为 `"ws"`（`:1111`） |

**图片生成走的是另一条路**：它不是 `ToolSpec` 的变体，而是通过**扩展**注入的——`codex-image-generation-extension` crate 的 `install` 函数（见 `codex-rs/core/tests/suite/extension_sandbox.rs:10`、`codex-rs/thread-manager-sample/src/main.rs:138`），响应项类型为 `image_generation_call`（`codex-rs/rollout-trace/src/reducer/conversation/normalize.rs:121`）。

**三类工具的判别方法**：在 `codex-rs/core/src/tools/handlers/mod.rs` 里 grep 得到的 → 本地 handler；在 `codex-rs/tools/src/tool_spec.rs` 里但 handlers 里没有的 → 托管工具；两处都没有却出现在响应项里的 → 扩展或 MCP 提供。**这是快速定位用的启发式，不是穷举分类**——动态工具（`dynamic` handler）与运行期注册的规格都可能落在三类之外，遇到对不上号的工具名请回到 `codex-rs/core/src/tools/registry.rs` 追注册路径。

### 4.6 工具运行时（`tools/runtimes/`）

| 运行时 | 文件 |
| ---- | ---- |
| shell | `codex-rs/core/src/tools/runtimes/shell.rs` + `shell/` 子目录 |
| apply_patch | `codex-rs/core/src/tools/runtimes/apply_patch.rs` |
| unified_exec | `codex-rs/core/src/tools/runtimes/unified_exec.rs` |

`handlers/apply_patch.lark` 是一个 **Lark 语法文件**，说明补丁格式有形式化文法定义。

### 4.7 实时会话子系统 `realtime_conversation`

> [!IMPORTANT]
> **这是前两版都漏掉的一条主干路径。** 第二版把 `realtime_conversation` 归进「其他子目录」一笔带过，但那个子目录只有 `codex-rs/core/src/realtime_conversation/bem.rs`(71 行) + `codex-rs/core/src/realtime_conversation/bem_tests.rs`(103 行)；真正的子系统是**同级文件** `codex-rs/core/src/realtime_conversation.rs`，**2,465 行**，且 `submission_loop` 处理 `Op::RealtimeConversation*` 的六个分支里有五个直接调进它——即 §2.1「按 `Op` 分派」表格之外未被描述的第二条主干。

**位置与体量**（E3）：

| 文件 | 行数 | 挂载方式 |
| ---- | ---: | ---- |
| `codex-rs/core/src/realtime_conversation.rs` | 2,465 | `codex-rs/core/src/lib.rs:14` `mod realtime_conversation;`（**非 `pub`**，纯 core 内部） |
| `codex-rs/core/src/realtime_conversation_tests.rs` | 300 | `#[cfg(test)] #[path = "realtime_conversation_tests.rs"] mod tests;`（`codex-rs/core/src/realtime_conversation.rs:2463-2465`） |
| `codex-rs/core/src/realtime_conversation/bem.rs` | 71 | `codex-rs/core/src/realtime_conversation.rs:82` 的 `mod bem;` |
| `codex-rs/core/src/realtime_conversation/bem_tests.rs` | 103 | 同上子模块的测试 |

**协议面**（E3，`codex-rs/protocol/src/protocol.rs`）：6 个入向 `Op` 与 5 个出向 `EventMsg`。

| 方向 | 变体 | 行 |
| ---- | ---- | ---: |
| `Op` | `RealtimeConversationStart` / `Audio` / `Text` / `Speech` / `Close` / `ListVoices` | `:541` / `:544` / `:547` / `:550` / `:553` / `:556` |
| `EventMsg` | `RealtimeConversationStarted` / `Realtime` / `Closed` / `Sdp` | `:1300` / `:1303` / `:1306` / `:1309` |
| `EventMsg` | `RealtimeConversationListVoicesResponse` | `:1444` |

版本枚举 `RealtimeConversationVersion`（`V1` / `V2` / `V3`，**默认 `V2`**）在 `codex-rs/protocol/src/protocol.rs:1627`。

**接入点**（E3）：`submission_loop` 的六个分支中，五个转发给本模块的 `handle_*`——`codex-rs/core/src/session/handlers.rs:736` / `:750` / `:754` / `:758` / `:762` 分别对应 `handle_start` / `handle_audio` / `handle_text` / `handle_speech` / `handle_close`；`:766` 的 `ListVoices` 不进本模块，由 `codex-rs/core/src/session/handlers.rs:72` 的 `realtime_conversation_list_voices` 就地回一个事件。

**内部结构**（E3，行号均在 `codex-rs/core/src/realtime_conversation.rs`）：

| 环节 | 符号与行号 |
| ---- | ---- |
| 核心状态机 | `RealtimeConversationManager`（`:124`，`impl` 在 `:491-1061`） |
| 输入/输出方法 | `audio_in()`（`:702`）、`text_in()`（`:726`）、`handoff_out()`（`:751`）、`append_speech()`（`:970`）、`handoff_complete()`（`:995`）、`shutdown()`（`:1050`） |
| handoff 状态类型 | `RealtimeHandoffState`（`:142`）、`RealtimeHandoffOutput`（`:156`）、`RealtimeHandoffStreamState`（`:162`）、`RealtimeStreamedItem`（`:168`） |
| 流式 handoff 链 | `register_handoff_stream_item()`（`:845`）→ `stream_handoff_delta()`（`:901`）→ `finish_handoff_stream_item()`（`:940`） |
| 会话启动链 | `handle_start()`（`:1081`）→ `prepare_realtime_start()`（`:1141`）→ `validate_avas_webrtc_start()`（`:1232`）→ `build_realtime_session_config()`（`:1249`）→ `handle_start_inner()`（`:1429`） |
| 传输输入任务 | `spawn_realtime_input_task()`（`:1721`）与 WebRTC sideband `spawn_webrtc_sideband_input_task()`（`:1741`）——**两条并行输入路径** |
| 服务端事件循环 | `handle_realtime_server_event()`（`:2175`） |
| 文本前缀常量 | `REALTIME_USER_TEXT_PREFIX = "[USER] "`（`:102`）、`REALTIME_BACKEND_TEXT_PREFIX = "[BACKEND] "`（`:103`） |

**最重的一块是 handoff**——实时会话向常规 agent turn 的交接。四个 handoff 状态类型加上三段式流式接口，说明交接是**增量**发生的：实时侧一边产出、一边把条目注册进流、逐 delta 推送、最后收尾。`register` / `stream` / `finish` 三段与四个状态类型是一体的，改动时要一起看。

**子模块 `bem`**（E3）：`message_phase(text, channel_prefixes)`（`codex-rs/core/src/realtime_conversation/bem.rs:5`）按 `[ANALYSIS]` / `[COMMENTARY]` / `[FINAL]` 前缀判定 BEM 消息阶段（前两者都映射到 `MessagePhase::Commentary`，后者映射到 `FinalAnswer`）；`ChannelParser`（`codex-rs/core/src/realtime_conversation/bem.rs:35`）缓冲流式文本直到频道头完整——其文档注释（同文件 `:30-33`）写明目的是**让前端模型能区分 BEM 的 `analysis` 与 `commentary`**。

> [!CAUTION]
> **不要把 `symphonia` / `tokio-tungstenite` 当成这个子系统的依赖印记。** 本轮核验中曾出现这一推断（「`codex-rs/core/Cargo.toml:106` 的 `symphonia` 与 `:117` 的 `tokio-tungstenite` 是专为实时会话而在」），**实测不成立**：
>
> - `codex-rs/core/src/realtime_conversation.rs` 的 `use` 列表里**两个都没有**——它的非仓内第三方依赖只有 `anyhow` / `async-channel` / `base64` / `http` / `serde_json` / `tokio` / `tokio-util` / `tracing`。
> - `symphonia` 的唯一使用者是 `codex-rs/core/src/audio_preparation.rs`，而后者被 `codex-rs/core/src/context_manager/history.rs`、`codex-rs/core/src/session/mod.rs`、`codex-rs/core/src/tools/code_mode/mod.rs` 引用——是**通用的音频输入处理**，不属于实时会话。
> - `tokio_tungstenite` 的使用者是 `codex-rs/core/src/client.rs`（模型客户端的 WebSocket 传输）与 `codex-rs/core/src/environment_selection.rs`（测试用的本地 WS 服务端）。
>
> 教训：**「Cargo.toml 里有某个依赖」不能反推「哪个模块在用它」**，必须 grep `use`。这与 [`AI_Coding_Context.md`](./AI_Coding_Context.md) 里记录的「按依赖名猜机制」致错模式是同一类。

> **未验证**（E1）：实时会话与常规 turn 在会话状态上的耦合程度、handoff 期间上下文历史如何合并，本文未追踪。入口见上表的 handoff 链与 `codex-rs/core/src/realtime_conversation_tests.rs`。

---

## 5. 审批与沙箱策略（E3）

工具调用要落到真实执行，必须先过两道决策：**审批**与**沙箱**。两者的策略类型都定义在 `codex-protocol` 中。

### 5.1 `AskForApproval`（`codex-rs/protocol/src/protocol.rs:917`）

| 变体 | 语义 |
| ---- | ---- |
| `UnlessTrusted`（序列化名 `untrusted`） | 被 **`is_known_safe_command()`** 判定为「已知安全」**且**未经复杂解析的命令自动放行，其余一律询问（准确条件见下方） |
| `OnRequest`（**默认**，兼容别名 `on-failure`） | 由模型决定何时请求用户批准 |
| `Granular(GranularApprovalConfig)` | 细粒度控制。字段为 `true` 表示放行该类，`false` 表示**自动拒绝**（而不是弹给用户） |
| `Never` | 永不询问。失败直接返回模型，不上升到用户 |

> [!WARNING]
> **`is_safe_command()` 这个函数名不存在**，第一版沿用了错误的名字。真实定义是
> `pub fn is_known_safe_command(command: &[String]) -> bool`，位于
> `codex-rs/shell-command/src/command_safety/is_safe_command.rs:12`——**模块**叫 `is_safe_command`，**函数**叫 `is_known_safe_command`。
>
> 上游源码注释里也还留着旧名：`codex-rs/protocol/src/protocol.rs:919`（正是 `UnlessTrusted` 上方那段文档注释）与 `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs:362`。按旧名 grep 只会命中注释。

**`UnlessTrusted` 自动放行的准确条件**（E3，core 侧入口是 `codex-rs/core/src/exec_policy.rs`，**不是** `codex-rs/core/src/safety.rs`）：

```rust
// codex-rs/core/src/exec_policy.rs:743-765
let is_known_safe = match command_origin {
    ExecPolicyCommandOrigin::Generic => is_known_safe_command(command),
    // #[cfg(windows)] PowerShell 分支走 is_safe_powershell_words
};
// ……
if is_known_safe
    && !used_complex_parsing
    && (approval_policy == AskForApproval::UnlessTrusted
        || windows_managed_fs_restrictions_without_sandbox_backend)
{
    return Decision::Allow;
}
```

要点：

1. **是三个合取项，不是一个。** 「已知安全」不足以放行，还必须 **`!used_complex_parsing`**——命令若需要复杂解析（管道、变量展开一类），即使外层命令在安全名单里也不放行。上一稿只写了「已知安全且只读 → 自动放行」，漏掉了这一项。
2. 第三个合取项是个**析取**：除 `UnlessTrusted` 外，「Windows 沙箱后端被禁用而 profile 又带托管文件系统限制」这一保守场景也走同一条放行路径。
3. **`dangerous_command_match` 命中时优先级更高**（`codex-rs/core/src/exec_policy.rs:772-780`）：即使命令已知安全，只要匹配到危险命令规则，就走 `Decision::Prompt`（`Never` 策略下则是 `Decision::Forbidden`），不会自动放行。

`GranularApprovalConfig` 的 5 个字段（`codex-rs/protocol/src/protocol.rs:944-958`，E3）：

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
> **`SandboxPolicy` 已不是运行时策略类型。** 运行时流转的是 `PermissionProfile`（`codex-rs/protocol/src/models.rs:316`），拆成**文件系统**与**网络**两个正交维度；`SandboxPolicy` 退化为**线上/兼容层**类型（`compatibility_sandbox_policy_for_permission_profile`）。详见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §1.5。下表描述的是这个兼容层类型。
>
> **勘误**：上一稿把这两个维度写成"`FileSystemSandboxPolicy` + `NetworkSandboxPolicy`"，**文件系统那一半是错的**。`PermissionProfile::Managed` 的字段类型是 `file_system: ManagedFileSystemPermissions`（`codex-rs/protocol/src/models.rs:258` 定义的枚举）与 `network: NetworkSandboxPolicy`（`codex-rs/protocol/src/models.rs:320-322`）；`FileSystemSandboxPolicy` 是**另一个类型**，要经 `ManagedFileSystemPermissions::to_sandbox_policy()`（`codex-rs/protocol/src/models.rs:288`）转换后才出现。只有网络那一维是直接用 `*SandboxPolicy` 的。

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
> // codex-rs/protocol/src/protocol.rs:988-992
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

另有 `WritableRoot`（`codex-rs/protocol/src/protocol.rs:1060`）承载「可写根之下仍需只读的子路径」，其文档注释点名了 `.codex`、`.git`（尤其 `.git/hooks`）——**防止智能体通过改写这些目录自我提权**。

> **默认收紧**：三个带 `network_access` 的变体默认都不放开网络。放开网络是显式动作。

沙箱的平台实现见 [`tools_and_sandbox.md`](./tools_and_sandbox.md)。

### 5.3 `ReviewDecision`：审批的返回值（`codex-rs/protocol/src/protocol.rs:4120`，E3）

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
> 即 `ReviewDecision::default()` 求值为 `Denied`，因此**所有依赖 `Default` 取值的路径**都会 fail-closed。另有便捷构造 `ReviewDecision::denied(rejection)`。
>
> **不要过度外推**：这里只证明了 `impl Default` 的返回值，不等于「任何没拿到明确决定的路径都会 fail-closed」——不走 `Default` 的路径（例如超时另有 `TimedOut`、审批缓存命中另有各自取值）需单独确认。

注意区分三种「否」：`Denied` 让智能体继续尝试别的办法，`Abort` 让智能体停下等用户，`TimedOut` 表示自动评审没在时限内给出结论。三者不可互换。

---

## 6. 上下文管理与压缩

### 6.1 `context_manager/`（E3）

`codex-rs/core/src/context_manager/mod.rs` 只有 8 行，全部是 `mod` 声明与再导出——导出 `ContextManager`（定义在 `codex-rs/core/src/context_manager/history.rs:41`）以及 `estimate_item_token_count` / `is_user_turn_boundary` / `truncate_function_output_payload` 三个自由函数。

| 文件 | 职责 | 规模 |
| ---- | ---- | ---- |
| `codex-rs/core/src/context_manager/history.rs` | 历史记录；`ContextManager` 本体在 `:41` | 主体（另有 `codex-rs/core/src/context_manager/history_tests.rs`） |
| `codex-rs/core/src/context_manager/normalize.rs` | 归一化 | 411 行 |
| `codex-rs/core/src/context_manager/updates.rs` | 增量更新；只有 3 个 `pub(crate) fn`——`build_developer_update_item`（`:11`）、`build_contextual_user_message`（`:15`）、`merge_contextual_fragments`（`:19`） | 小 |

也就是说，这个目录的入口面**非常窄**：一个 `ContextManager` 加四个自由函数，改动时的对外影响范围可控。

### 6.2 压缩（compact）：文件清单与路径选择

`core/src/` 下与压缩相关的有 8 个文件：

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/core/src/compact.rs` | 本地压缩主体；另提供路径判据 `should_use_remote_compact_task()`（`:108`）与 `SUMMARIZATION_PROMPT` |
| `codex-rs/core/src/compact_token_budget.rs` | token 预算路径，入口 `run_manual_compact_task()` |
| `codex-rs/core/src/compact_model_fallback.rs` | 模型回退：`should_retry_with_current_model()` / `record_model_fallback()` |
| `codex-rs/core/src/compact_remote.rs` | 远程压缩 v1 |
| `codex-rs/core/src/compact_remote_v2.rs` | 远程压缩 v2 |
| `codex-rs/core/src/compact_remote_v2_attempt.rs` | v2 的内部辅助（无 `pub` 顶层函数） |
| `codex-rs/core/src/compact_remote_request.rs` | v2 的请求构造辅助（无 `pub` 顶层函数） |
| `codex-rs/core/src/compact_tests.rs` | 测试 |

**路径选择是三级判定，只需读一个约 40 行的函数就能确定**（E3，`codex-rs/core/src/tasks/compact.rs:35-77` 的 `CompactTask::run`）：

```
① features.enabled(Feature::TokenBudget)
   → compact_token_budget::run_manual_compact_task(..)   【最高优先级，直接 return】
② 否则 compact::should_use_remote_compact_task(provider) 为真
   → features.enabled(Feature::RemoteCompactionV2)
        ? compact_remote_v2::run_remote_compact_task(..)   【指标名 "remote_v2"】
        : compact_remote::run_remote_compact_task(..)      【指标名 "remote"】
③ 否则
   → compact::run_compact_task(..)                        【指标名 "local"】
```

判据是**两个布尔开关**，不是「8 个文件之间怎么分工」的问题：

| 开关 | 取值 | 出处 |
| ---- | ---- | ---- |
| `Feature::TokenBudget` | `Stage::UnderDevelopment`，`default_enabled: false` | `codex-rs/features/src/lib.rs:1337` 起的 `FeatureSpec` |
| `Feature::RemoteCompactionV2` | **`Stage::Stable`，`default_enabled: true`** | `codex-rs/features/src/lib.rs:1451` 起的 `FeatureSpec` |
| `should_use_remote_compact_task(provider)` | 等价于 `provider.supports_remote_compaction()`，即 `is_openai() \|\| is_azure_responses_provider(..)` | `codex-rs/core/src/compact.rs:108-109`、`codex-rs/model-provider-info/src/lib.rs:422` |

> [!IMPORTANT]
> **默认行为**（E3，由上表三行直接推出）：
>
> - provider 是 **OpenAI 或 Azure Responses** → 走**远程压缩 v2**（因为 `RemoteCompactionV2` 默认开启）
> - **其他 provider** → 走**本地压缩**（远程压缩不可用）
> - **token-budget 路径默认关闭**（`TokenBudget` 尚在开发中），一旦开启会**抢占**上面两条路径
>
> 上一稿把这条列为「需要完整读取 8 个文件」的未验证项，属于对证据成本的高估。

> **未验证**（E1）：模型回退的具体触发条件、本地与远程压缩在**产出内容**上的差异。集成测试在 `codex-rs/core/tests/suite/compact.rs`（5,440 行），是理解压缩行为的最佳入口。压缩本身是一种 `SessionTask`（`codex-rs/core/src/tasks/compact.rs`，见 §2.3）。

---

## 7. 仓库规范的注入

`codex-rs/core/src/agents_md.rs` 与 `codex-rs/core/src/agents_md_manager.rs` 负责读取仓库中的规范文件并注入模型上下文。

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
| 改了 `Cargo.toml` / `Cargo.lock` 要跑 `just bazel-lock-update` 并把 lockfile 一起提交 <!-- ref-exempt: 转述 AGENTS.md 通用规则，泛指任意 crate 的清单与锁文件 --> | 顶部规则列表，grep `just bazel-lock-update` |
| **默认不要往 core 加代码** | `## The codex-core crate`，grep `resist adding code to codex-core` |
| 单次改动尽量控制规模 | `### Change size guidance (800 lines)` |
| 外部集成面（app-server API、CLI 参数、配置加载、rollout 恢复）属破坏性改动高风险区 | `### Breaking changes` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `run_turn` 内部**其余**流程（构造请求 → 流式解析 → 写回历史） | E1 | `codex-rs/core/src/tasks/regular.rs`、`codex-rs/core/src/session/turn.rs:149`（分段读）、`codex-rs/core/src/session/turn_tests.rs` |
| 模型客户端的请求构造与流式解析 | E1 | `codex-rs/core/src/client.rs`、`codex-rs/core/src/client_common.rs` |
| 多智能体协作机制 | E1 | `codex-rs/core/src/session/multi_agents.rs`、`tools/handlers/multi_agents_common`、`multi_agents_v2/` |
| token 预算的具体算法 | E1 | `codex-rs/core/src/session/token_budget.rs`、`codex-rs/core/src/compact_token_budget.rs` |
| 压缩的**模型回退**触发条件、本地/远程产出差异 | E1 | `codex-rs/core/src/compact_model_fallback.rs`、`codex-rs/core/tests/suite/compact.rs`（5,440 行） |
| `is_known_safe_command()` **内部**的判定规则（其接入条件已在 §5.1 降为 E3） | E1 | `codex-rs/shell-command/src/command_safety/` |
| Guardian 评审的具体策略 | E1 | `codex-rs/core/src/guardian/policy.md`、`codex-rs/core/src/guardian/prompt.rs` |
| code_mode 的委派机制 | E1 | `codex-rs/core/src/tools/code_mode/delegate.rs`、`codex-rs/core/src/tools/code_mode/response_adapter.rs` |
| 实时会话与常规 turn 的状态耦合、handoff 期间历史合并方式 | E1 | `codex-rs/core/src/realtime_conversation.rs` 的 handoff 链（§4.7）、`codex-rs/core/src/realtime_conversation_tests.rs` |

**本轮从本表移除并就地降为 E3 的条目**（原因：读一处源码即可确定，继续标 E1 属于边界不诚实）：

| 原条目 | 现在写在哪 | 结论摘要 |
| ---- | ---- | ---- |
| `Op` / `EventMsg` 的完整变体清单 | §2.2 | `Op` **26** 个变体（`codex-rs/protocol/src/protocol.rs:531-688`，与 `codex-rs/core/src/session/handlers.rs` 中 `Op::` 去重命中数一致）；`EventMsg` **80** 个（`:1288-1495`） |
| `SessionTask` 四种实现的差异 | §2.3 | 四种实现只对应 **3 个 `TaskKind`**——`UserShellCommandTask` 复用 `TaskKind::Regular` |
| 压缩的 v1/v2 选择条件 | §6.2 | 三级判定，判据是 `Feature::TokenBudget` 与 `Feature::RemoteCompactionV2` 两个开关加 provider 能力 |
| `context_manager/` 的结构 | §6.1 | `codex-rs/core/src/context_manager/mod.rs` 仅 8 行，对外只有 `ContextManager` + 3 个自由函数 |
| 内置工具处理器清单的证据等级 | §4.4 | `mod` 声明与 `pub use` 本身即源码，标 E3 |
| `run_turn` 的签名位置与后续 turn 输入来源 | §2.4 | `codex-rs/core/src/session/turn.rs:149`；输入取自 `:273-274` 的 `input_queue.get_pending_input(..)` |
| `is_known_safe_command()` 的**接入条件** | §5.1 | `is_known_safe && !used_complex_parsing && (UnlessTrusted \|\| windows 保守场景)` |

> **上一版已从本表移除**：「工具调用各环节的次序」——见 §4.3，`codex-rs/core/src/tools/orchestrator.rs` 模块头注释直接写明。

---

## 10. 相关文档

- [架构总览](./architecture_overview.md) — 进程边界与整体拓扑
- [Crate 地图](./crate_map.md) — core 的依赖热点与减负指引
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱的平台实现
- [配置体系](./config_system.md) — 审批与沙箱策略的配置入口
- [会话与持久化](./session_and_persistence.md) — rollout 与线程存储
