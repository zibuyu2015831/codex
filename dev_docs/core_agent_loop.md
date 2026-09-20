---
title: Codex 智能体核心循环
summary: 描述 codex-core 的提交-事件协议与三层循环（submission_loop → SessionTask → turn 循环）、会话与 turn 组织方式、工具调用的路由与分发链路、实时会话（realtime_conversation）子系统、上下文管理与压缩路径选择、审批与沙箱决策的接入点；给出 Op（28）与 EventMsg（83）的准确变体计数，并标注各结论的证据等级与未验证边界。第 6 轮上游同步修订：Op::UserInput 更名 TurnInput、known-safe 白名单退役致 AskForApproval 语义反转、独立 shell handler 与 runtime 并入 unified_exec/zsh_fork、压缩路径选择由特性开关改为 provider 能力枚举。
keywords: codex | agent-loop | submission-loop | session-task | turn | tool-router | permission-profile | context-manager | compact | realtime-conversation | turn-input | round6
scope: codex-rs/core 的提交循环、任务层、会话、turn、工具调用、实时会话与上下文管理
related_files: codex-rs/core/src/session/handlers.rs | codex-rs/core/src/session/mod.rs | codex-rs/core/src/session/turn.rs | codex-rs/core/src/tasks/mod.rs | codex-rs/core/src/tasks/regular.rs | codex-rs/core/src/tasks/compact.rs | codex-rs/core/src/tools/router.rs | codex-rs/core/src/tools/registry.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/core/src/tools/handlers/mod.rs | codex-rs/core/src/tools/approvals.rs | codex-rs/core/src/realtime_conversation.rs | codex-rs/core/src/exec_policy.rs | codex-rs/core/src/safety.rs | codex-rs/core/src/context_manager | codex-rs/core/Cargo.toml | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/tools/src/tool_spec.rs | codex-rs/shell-command/src/command_safety/is_dangerous_command.rs | codex-rs/model-provider/src/provider.rs | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-09-21
---

# 智能体核心循环

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **覆盖范围**: `codex-rs/core`（402,720 行）的骨架结构与三层循环
> **证据等级**: 循环链路、类型与函数签名为 E3；目录与文件计数为 E1；模块间部分协作关系为 E1，已在文中逐处标注

> [!IMPORTANT]
> `codex-core` 是全仓最大的 crate。本文给出的是**可导航的骨架**，不是逐行讲解。遇到本文标注为 E1 的判断，请回去读代码，不要直接采信。

> [!CAUTION]
> **第 6 轮上游同步（跨 2,230 个提交）后，本文的独立核验结果是 118 条断言 OK、174 条 WRONG，失效率约 59%。** 其中三节的叙事骨架已整体不成立，如果你读过旧版并记住了结论，请优先重读：
>
> | # | 旧版怎么说 | 现在的事实 | 见 |
> | ---: | ---- | ---- | ---- |
> | 1 | `UnlessTrusted` 档位下「被 `is_known_safe_command()` 判定为已知安全且未经复杂解析的命令自动放行」 | **白名单整体退役**，源码注释现在写的是相反的话：除非 execpolicy 有显式规则放行，否则**每条命令都要审批** | §5.1 |
> | 2 | `shell` 是与 `apply_patch`、`unified_exec` 并列的第一类工具，有自己的 handler 和 runtime 目录 | **独立 `shell` handler 与 runtime 都已不存在**，执行并入 `unified_exec`，进程侧实现在 `runtimes/zsh_fork*` | §4.4、§4.6 |
> | 3 | 压缩路径选择是「两个 feature 开关 + 一个判据函数」的三级判定，指标名有 `remote_v2` / `remote` / `local` | 远程压缩 v1 **整条删除**，判据函数删除，`Feature::RemoteCompactionV2` 降为 `Stage::Removed` 且不再被引用；改由 provider 能力枚举决定 | §6.2 |
>
> **另有一处最影响写代码的改名**：`Op::UserInput` 已更名为 **`Op::TurnInput`**，`Op::ThreadRollback` 已删除（§2.2）。
>
> **第 1 条的危险性最高**：它向读者传达「Codex 有一个命令白名单，满足条件即免审批」——一个**已被上游明确否决的安全模型**。

> [!NOTE]
> **更早几轮的修订史**（保留备查，不构成当前事实断言）：第一版标题写着「核心循环」却没有描述循环本身（后补 §2）；`codex-rs/core/src/safety.rs` 曾被误标为「命令安全判定入口」（实为 apply_patch 写入路径判定）；`realtime_conversation` 子系统曾被当成小子目录一笔带过（后补 §4.7）。

---

## 1. codex-core 的模块版图

`codex-rs/core/src/` 下有 **142 个一级条目，其中 19 个是子目录**（第 6 轮实测；基线为 17 个子目录，新增 `exec_policy/`、`realtime_history/`、`thread_manager/`，删除 `bin/`）。按职责归类：

| 子系统 | 位置 | 说明 |
| ---- | ---- | ---- |
| **提交循环** | `codex-rs/core/src/session/handlers.rs`、`codex-rs/core/src/session/mod.rs` | `submission_loop`：消费 `Submission`、按 `Op` 分派，见 §2.1 |
| **任务层** | `tasks/` | `SessionTask` 抽象与 4 种实现（regular / compact / review / user_shell），见 §2.2 |
| **会话与 turn** | `session/`（**51 个文件** + `snapshots/`、`tests/`） | 会话生命周期、turn 组织、上下文窗口、token 预算 |
| **线程编排** | `codex-rs/core/src/thread_manager.rs`、`codex-rs/core/src/codex_thread.rs` | 线程管理与线程实例 |
| **工具调用** | `tools/`（**30 个文件** + `code_mode/`、`executed_tool_calls/`、`handlers/`、`runtimes/`） | 路由、注册表、编排、审批、沙箱决策 |
| **审批评审** | `guardian/` | Guardian 自动评审后端，见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7 |
| **补丁写入安全判定** | `codex-rs/core/src/safety.rs` | `assess_patch_safety()`：判定 apply_patch 的写入路径是否越出可写根，唯一调用方 `codex-rs/core/src/apply_patch.rs:32`（函数定义在 `codex-rs/core/src/safety.rs:29`） |
| **命令安全判定** | `codex-rs/core/src/exec_policy.rs` | **第 6 轮变更**：接入的已不是白名单，而是 `codex-shell-command` 的 `dangerous_command_match_for_platform()` 黑名单（`codex-rs/core/src/exec_policy.rs:29`），见 §5.1 |
| **沙箱接入** | `sandboxing/` | core 侧对 `codex-sandboxing` 的封装 |
| **统一执行** | `unified_exec/` | 长驻进程式命令执行（对应 `ExecCommandHandler` / `WriteStdinHandler`） |
| **上下文历史** | `context_manager/` | 历史、归一化、增量更新（**4 个生产文件 + 一个模块根**，见 §6.1） |
| **上下文片段构造** | `context/` | 注入模型上下文的**文案/指令片段构造器**（**51 个条目**：`codex-rs/core/src/context/environment_context.rs`、`codex-rs/core/src/context/user_instructions.rs`、`codex-rs/core/src/context/turn_aborted.rs`、`codex-rs/core/src/context/realtime_start_instructions.rs`、`world_state/` 等。⚠️ 第 6 轮 `permissions_instructions.rs` 已迁出，现为 `codex-rs/prompts/src/permissions_instructions.rs`），与 `context_manager/` 不是一回事 |
| **上下文压缩** | `compact*.rs`（**10 个文件**） | 本地压缩、**远程压缩 v2**（v1 已整条删除）、token 预算、模型回退，路径选择见 §6.2 |
| **实时会话** | `codex-rs/core/src/realtime_conversation.rs`（**2,638 行**）+ `realtime_conversation/` | 语音/实时会话状态机与向常规 turn 的 handoff，见 §4.7 |
| **模型客户端** | `codex-rs/core/src/client.rs`、`codex-rs/core/src/client_common.rs` | 与模型服务通信 |
| **状态持久化** | `state/` | core 侧对 `codex-state` 的接入 |
| **配置** | `config/` | 配置加载与校验（详见 [`config_system.md`](./config_system.md)） |
| **执行** | `codex-rs/core/src/exec.rs`、`codex-rs/core/src/exec_env.rs`、`codex-rs/core/src/exec_policy.rs` | 命令执行与策略 |
| **规范注入** | `codex-rs/core/src/agents_md.rs`、`codex-rs/core/src/agents_md_manager.rs` | 读取并注入仓库规范文件 |
| **补丁应用** | `codex-rs/core/src/apply_patch.rs` | 结构化补丁 |
| **技能与钩子** | `codex-rs/core/src/skills.rs`、`codex-rs/core/src/hook_runtime.rs` | 技能定义、钩子运行时 |
| **插件** | `plugins/` | 插件装载（对应 `request_plugin_install` 等工具） |
| **扩展接入** | `apps/`、`agent/`、`codex-rs/core/src/connectors.rs` | 扩展与连接器 |
| **其他子目录** | `mcp_tool_call/`、`utils/`、`agent/`、`apps/`、`exec_policy/`、`realtime_history/`、`thread_manager/` | MCP 调用、工具函数与第 6 轮新增的三个子目录。**`bin/` 已不存在**（config schema 生成器迁至独立 crate `codex-rs/config-schema`） |

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

第一版写的「67 个 workspace 依赖」在当时**对不上任何一种口径**，已删除。第 6 轮实测（数字全部上涨）：

```bash
cd codex-rs/core
awk '/^\[dependencies\]/{f=1;next} /^\[/{f=0} f' Cargo.toml > /tmp/deps.txt
grep -c '^[a-zA-Z]'      /tmp/deps.txt   # 102 —— [dependencies] 条目总数
grep -c 'workspace = true' /tmp/deps.txt # 101 —— 其中走 workspace 继承的
grep -c '^codex'         /tmp/deps.txt   # 66  —— 其中仓内 codex-* crate
grep '^[a-zA-Z]' /tmp/deps.txt | grep -v 'workspace = true'
# → codex-windows-sandbox = { package = "codex-windows-sandbox", path = "../windows-sandbox-rs" }
```

| 口径 | 数量 |
| ---- | ---: |
| `[dependencies]` 条目总数 | **102** |
| 其中 `workspace = true` | **101** |
| 其中仓内 `codex-*` crate | **66**（唯一的非 workspace 依赖 `codex-windows-sandbox` 也在其中，走 `path`） |
| 第三方 crate | 36 |
| **上表之外**：target-gated 生产依赖 | 3 条，不在 `[dependencies]` 段内——`[target.x86_64-unknown-linux-musl.dependencies] openssl-sys`、`[target.aarch64-unknown-linux-musl.dependencies] openssl-sys`、`[target.'cfg(unix)'.dependencies] codex-shell-escalation` |
| **上表之外**：`[dev-dependencies]` | 28（测试依赖，不计入生产口径） |

> [!NOTE]
> `codex-shell-escalation` 是**仓内 crate**，因此「仓内 `codex-*` = 66」只在非 unix 平台成立；**在 unix 上实际为 67**。做依赖裁剪统计时不要漏掉这三个 target 段。这个 67 与 [`crate_map.md`](./crate_map.md) §4 用 `cargo metadata` 算出的「`codex-core` normal 出度 67」互相印证。

这个数字本身就是 `AGENTS.md:72` 中 ``## The `codex-core` crate`` 一节反复强调「resist adding code to codex-core」（`AGENTS.md:76`）的背景。**注意该标题含反引号**，按纯文本 `## The codex-core crate` grep 会零命中。

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

> **第 6 轮：`handlers.rs` 从约 900 行缩到 675 行，本节原有的 8 个行号引用全部越界，已整体刷新。**

```rust
// codex-rs/core/src/session/handlers.rs:411
pub(super) async fn submission_loop(
    sess: Arc<Session>,
    config: Arc<Config>,
    rx_sub: Receiver<Submission>,
) {
    // To break out of this loop, send Op::Shutdown.
    let mut shutdown_received = false;
    while let Ok(sub) = rx_sub.recv().await {
        // 第 6 轮新增：elicitation 单独走一条日志分支
        if matches!(sub.op, Op::ResolveElicitation { .. }) {
            debug!(submission_id = %sub.id, operation = sub.op.kind(), "Submission");
        } else {
            debug!(?sub, "Submission");
        }
        let dispatch_span = submission_dispatch_span(&sub);
        let should_exit = async {
            match sub.op {                      // 第 6 轮：已去掉 .clone()
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

要点（E3，行号为第 6 轮实测）：

| 事实 | 证据 |
| ---- | ---- |
| 循环体是 `while let Ok(sub) = rx_sub.recv().await`，从一个 channel 消费 `Submission` | `codex-rs/core/src/session/handlers.rs:418` |
| 分派方式是 `match sub.op`，即**按 `Op` 变体分支**（第 6 轮已去掉 `.clone()`） | `codex-rs/core/src/session/handlers.rs:426` |
| **正常**退出方式是 `Op::Shutdown` | `codex-rs/core/src/session/handlers.rs:416` 注释：「To break out of this loop, send `Op::Shutdown`」 |
| 每次提交都开一个 tracing span | `submission_dispatch_span(&sub)`，`codex-rs/core/src/session/handlers.rs:424` |
| 循环在会话创建时 `tokio::spawn` 起来 | `codex-rs/core/src/session/mod.rs:940`，span 名 `session_loop`，带 `thread_id` |
| join handle 被包成 `SessionIo { tx_sub, rx_event, agent_status, session_loop_termination }` | 构造在 `codex-rs/core/src/session/mod.rs:945-950`，类型定义在 `:408` |

> [!CAUTION]
> **勘误（结论）：「唯一的退出方式是 `Op::Shutdown`」不成立。**
>
> `codex-rs/core/src/session/handlers.rs:416` 那句注释确实这么写，但**注释描述的是意图，不是全部实现**。同一函数在循环之后还有一段（`codex-rs/core/src/session/handlers.rs:605-615`）：
>
> ```rust
> // If the submission loop exits because the channel closed without an
> // explicit shutdown op, still run session teardown.
> if !shutdown_received {
>     shutdown_session_runtime(&sess).await;
>     if let Some(live_thread) = sess.live_thread()
>         && let Err(err) = live_thread.shutdown().await
>     {
>         warn!("failed to shutdown thread persistence after submission channel closed: {err}");
>     }
> }
> ```
>
> **第 6 轮结构变化**：`emit_thread_stop_lifecycle` 已被挪进 `shutdown_session_runtime()` 内部（`codex-rs/core/src/session/handlers.rs:315`），不再出现在这段收尾代码里。结论本身不变。
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
| `Submission` | `:193` | 客户端 → core | 一次提交，含 `id` 与 `op` |
| `Op` | `:601`（枚举体 `:601-767`） | 客户端 → core | 提交的动作枚举，**28 个变体** |
| `Event` | `:1340` | core → 客户端 | 一次事件，含 `id` 与 `msg` |
| `EventMsg` | `:1358`（枚举体 `:1358-1575`） | core → 客户端 | 事件负载枚举，**83 个变体** |

这是一个**非对称的请求-流式响应模型**：一次 `Submission` 可能产生任意多个 `Event`，两者靠 `id` 关联。`codex-rs/core/src/session/handlers.rs` 中的 `sess.send_event(&turn_context, event.msg)`（1 处）与 `sess.send_event_raw(Event { id, msg })`（5 处）就是这条出向通道。

> **第 6 轮口径更正**：上一版写「handlers.rs 中**大量出现**」——实测合计只有 6 处。随着 handlers.rs 从约 900 行缩到 675 行，事件发送大多已下沉到各自的处理函数里。

> [!CAUTION]
> **`Op::UserInput` 已更名为 `Op::TurnInput`，`Op::ThreadRollback` 已删除。** 这是第 6 轮对写代码的人影响最直接的一处改动——`UserInput` 是描述「一句话如何进入内核」时的主角符号，凡按旧名 grep 或写代码的都会落空。
>
> 相对基线的 26 个变体：**新增** `TurnInput`（`codex-rs/protocol/src/protocol.rs:629`）、`RecoverTurn`（`:636`）、`SuspendTurnAndShutdown`（`:643`）、`TurnSettings`（`:658`）；**删除** `UserInput`、`ThreadRollback`。
>
> `ThreadRollback` 的删除是否意味着回滚能力被 `RecoverTurn` 接管，本轮未取证，**不要臆测**。

`Op` 的 **28 个变体**依次为（E3，`codex-rs/protocol/src/protocol.rs:601-767`）：

```
Interrupt, CleanBackgroundTerminals,
RealtimeConversationStart, RealtimeConversationAudio, RealtimeConversationText,
RealtimeConversationSpeech, RealtimeConversationClose, RealtimeConversationListVoices,
TurnInput, RecoverTurn, SuspendTurnAndShutdown,
ThreadSettings, TurnSettings, InterAgentCommunication,
ExecApproval, PatchApproval, ResolveElicitation, UserInputAnswer,
RequestPermissionsResponse, DynamicToolResponse,
RefreshMcpServers, ReloadUserConfig, Compact, SetThreadMemoryMode,
Review, ApproveGuardianDeniedAction, Shutdown, RunUserShellCommand
```

交叉印证：`codex-rs/core/src/session/handlers.rs` 中 `Op::` 的去重命中集合与上面这 28 个名字**完全相同**（`grep -o 'Op::[A-Za-z0-9_]*' … | sort -u | wc -l` → 28，逐字符比对无差异），即 `submission_loop` 显式覆盖了全部变体，没有遗漏也没有多余。**这条「全覆盖」的性质跨过 2,230 个提交仍然成立。**

> [!IMPORTANT]
> **`Op` 标了 `#[non_exhaustive]`**（`codex-rs/protocol/src/protocol.rs:600`）。因此 `submission_loop` 的 `match` 末尾那条 `_ => false`（`codex-rs/core/src/session/handlers.rs:596`，行内注释即 `// Ignore unknown ops; enum is non_exhaustive to allow extensions.`）**不是死代码**——它是给跨 crate 的外部扩展留的兜底分支，不要当成「漏了某个变体」去补。
>
> **数变体数时的陷阱**：带结构体字段的变体（如 `UserInput { .. }`、`ExecApproval { .. }`）跨多行。用逐行 brace-depth 脚本统计时，如果在**更新括号深度之后**才判定当前行是不是变体，这些变体会被整体跳过——第 5 轮核验中就有一次据此数出 16，与当时真实的 26 差了 10 个。判定必须在更新深度**之前**做。第 6 轮沿用同一方法得 28。

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
> 另外 `Op::RunUserShellCommand` 有**两条**路径（分派臂在 `codex-rs/core/src/session/handlers.rs:569`，实现在同文件 `run_user_shell_command()` `:95-127`）：若当前**已有活跃 turn**，则**不建 task**，直接 `tokio::spawn(execute_user_shell_command(..., UserShellCommandMode::ActiveTurnAuxiliary))` 挂在既有 turn 上；只有在没有活跃 turn 时才 `spawn_task(.., UserShellCommandTask::new(command))`。

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
| `codex-rs/core/src/session/turn_input.rs` | **第 6 轮补入**：`RegularTask` 的新构造点（`:362`、`:508`），§2.3 会引用 |
| `codex-rs/core/src/session/thread_settings.rs` | **第 6 轮补入**：`Op::ThreadSettings` / `Op::TurnSettings` 的落点 |
| `mcp*.rs`（4 个生产 + 1 个测试） | MCP 接入：`codex-rs/core/src/session/mcp.rs` / `codex-rs/core/src/session/mcp_runtime.rs` / `codex-rs/core/src/session/mcp_prewarm.rs` / `codex-rs/core/src/session/mcp_refresh.rs`（另有 `codex-rs/core/src/session/mcp_tests.rs`） |
| `codex-rs/core/src/session/rollout_reconstruction.rs` | 从既有 rollout 恢复会话 |
| `codex-rs/core/src/session/time_reminder.rs` | 时间提醒 |
| `codex-rs/core/src/session/extension_metrics.rs` | 扩展指标 |
| `codex-rs/core/src/session/code_mode_warning.rs` | code-mode 警告 |

> [!NOTE]
> **第 6 轮：`codex-rs/core/src/session/config_lock.rs` 已从本表删除——该文件已不存在，全仓亦无同名文件。** <!-- ref-exempt: 反例——正文说明该路径已不存在 -->「配置锁这个机制是否被别处承接」需要通读 `codex-rs/core/src/session/thread_settings.rs`、`codex-rs/core/src/session/step_settings.rs` 与 `config/` 才能下结论，本轮未做，**因此只删行、不臆测替代物**。
>
> **更早一轮补入**：`codex-rs/core/src/session/mod.rs`、`codex-rs/core/src/session/world_state.rs` 两个生产文件此前漏列。其中模块根的遗漏尤其要命——§2.1 自己就在引用它。
>
> **第 6 轮复算**：`session/` 现共 **51 个文件 = 36 个生产文件 + 15 个测试文件**（`*_tests.rs` 与 `tests.rs`），外加 `snapshots/`、`tests/` 两个目录。上表**只覆盖其中一部分**，本轮补入了 `turn_input.rs` 与 `thread_settings.rs` 两个 §2.3 会引用到的文件；其余未列的生产文件有 `daemon_recovery.rs`、`environment.rs`、`extension_interruption.rs`、`guardian_checkpoint.rs`、`plugin_selection.rs`、`realtime_history.rs`、`reasoning_effort.rs`、`retained_context.rs`、`startup.rs`、`step_activation.rs`、`step_settings.rs`、`turn_suspension.rs` 等。<!-- ref-exempt: 此处列举的是同目录内文件的裸文件名，前文已给出目录 -->
>
> 复算命令：
>
> ```bash
> ls -p codex-rs/core/src/session/ | grep -v / | wc -l                                  # 51
> ls -p codex-rs/core/src/session/ | grep -v / | grep -E '_tests\.rs$|^tests\.rs$' | wc -l  # 15
> ```。

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

> **第 6 轮：`ToolRouter` 的公开 API 从 4 个收敛为 3 个。**

```rust
// codex-rs/core/src/tools/router.rs:244 —— 从模型响应项构造工具调用
pub fn build_tool_call(item: ResponseItem)
    -> Result<Option<ToolCall>, FunctionCallError>;

// codex-rs/core/src/tools/router.rs:300 —— 分发（异步）
pub async fn dispatch_tool_call_with_code_mode_result(...);

// codex-rs/core/src/tools/router.rs:233 —— 该工具是否支持并行
pub fn tool_supports_parallel(&self, call: &ToolCall) -> bool;
```

**由此可确认的两件事**（E3）：

1. 工具调用是从模型的 `ResponseItem` **解析**出来的，而不是模型直接调用函数
2. 存在**并行执行**能力（`tool_supports_parallel` + `codex-rs/core/src/tools/parallel.rs`）

> [!CAUTION]
> **旧版的第三条结论已被删除，而不是改写。**
>
> 旧版据 `tool_waits_for_runtime_cancellation(&self, call: &ToolCall) -> bool` 推出「存在取消语义，且**不同工具的取消等待行为不同**」。该函数**全仓零命中**，且在 `codex-rs/core/src/tools/` 与 `codex-rs/tools/src/` 下 grep `runtime_cancellation` / `fn waits_for` / `cancellation_behavior` 均无替代符号。
>
> **唯一支撑证据消失后，正确的做法是删掉结论，而不是找个相近的符号把它圆回来。** 取消语义是否以别的形态存在（例如某个 trait 的方法）需要通读 `codex-rs/core/src/tools/sandboxing.rs` 起的 trait 体系，本轮未做——**留空比编一个替代证据诚实**。

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

> [!CAUTION]
> **第 6 轮：独立的 `shell` handler 已不存在。**
>
> `codex-rs/core/src/tools/handlers/` 下已无 `shell.rs`，`ShellHandler` 符号**全仓零命中**。只剩 `codex-rs/core/src/tools/handlers/shell_spec.rs` 作为**共享的规格构造模块**，被三个地方复用：`codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs:49`、`codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs:19`、`codex-rs/core/src/tools/handlers/request_permissions.rs:14`。
>
> 也就是说「shell 是一个独立工具，有自己的 handler 和 runtime」这个骨架已经不成立：**执行路径统一收敛到 `unified_exec`，进程侧实现在 `runtimes/zsh_fork*`（见 §4.6），`shell_spec.rs` 降格为规格构造工具库**。模型侧看到的工具名是 `exec_command` / `shell_command`。

| 模块 | 工具用途 |
| ---- | ---- |
| `apply_patch` | 应用结构化补丁 |
| `unified_exec` | **长驻进程式执行，第 6 轮起 shell 命令执行也并入此处**：导出 `ExecCommandHandler`（`codex-rs/core/src/tools/handlers/mod.rs:78`）与 `WriteStdinHandler`（`:80`），另有 `ExecCommandHandlerOptions`（`:79`）。对应 `core/src/unified_exec/` 与 `codex-rs/core/src/tools/runtimes/unified_exec.rs` |
| `request_user_input_async` | **第 6 轮补入**：异步请求用户输入 |
| `send_message_to_user_async` | **第 6 轮补入**：异步向用户发消息 |
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
| handler 模块总数 | **24** |
| 其中有 `*_spec.rs` | **12**（50%） |
| 其中有 `*_tests.rs` | **6**（25%）：`apply_patch` / `mcp_resource` / `multi_agents` / `request_plugin_install` / `request_user_input` / `unified_exec` |
| 同时具备 handler + spec + tests 三件套 | **5**（`unified_exec` 有 tests 但无 spec） |

复算命令（第 6 轮）：

```bash
cd codex-rs/core/src/tools/handlers
mods=$(grep -oE "^(pub\(crate\) )?mod [a-z_0-9]+;" mod.rs | sed "s/.*mod //;s/;//" \
       | grep -v "_spec$" | grep -v "_tests$")
echo "total: $(echo "$mods" | wc -l)"
for m in $mods; do [ -f "${m}_spec.rs" ]  && echo "$m"; done | wc -l
for m in $mods; do [ -f "${m}_tests.rs" ] && echo "$m"; done | wc -l
```

> [!WARNING]
> **「多数 handler 有配套的 `*_spec.rs` 与 `*_tests.rs`」不成立**，三件套只覆盖 24 个模块中的 5 个。
>
> **第 6 轮四项计数全变**（23/13/7/6 → 24/12/6/5）：`shell` 模块消失（见本节开头的 CAUTION），同时新增 `request_user_input_async` 与 `send_message_to_user_async` 两个模块。
>
> `*_spec.rs` **通常在工具需要向模型下发 JSON Schema 时出现**；规格在运行期动态构造的工具就没有这个文件。以下 **12 个**模块没有 `*_spec.rs`：`current_time`、`dynamic`、`extension_tools`、`mcp`、`multi_agents_common`、`multi_agents_v2`、`request_permissions`、`request_user_input_async`、`send_message_to_user_async`、`sleep`、`unified_exec`、`wait_for_environment`。新增工具时按需要决定是否配 spec，不要把三件套当作硬性规范。
>
> > 上一版这里写的是「**只在**…时出现」。该措辞是对无 spec 模块的**归纳解释**，逐个验证「它们确实在运行期动态构造规格」需要读 12 个模块的注册路径，本轮未做——因此降级为「**通常在**」。

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

> [!CAUTION]
> **第 6 轮：`runtimes/shell.rs` 与 `runtimes/shell/` 子目录都已不存在**<!-- ref-exempt: 反例——正文说明这两个路径已不存在 -->，重组为 `zsh_fork.rs` + `zsh_fork/`（`unix_escalation.rs` 搬进后者，875 行）。

| 运行时 | 文件 |
| ---- | ---- |
| **zsh_fork**（shell 执行） | `codex-rs/core/src/tools/runtimes/zsh_fork.rs` + `codex-rs/core/src/tools/runtimes/zsh_fork/unix_escalation.rs` |
| apply_patch | `codex-rs/core/src/tools/runtimes/apply_patch.rs` |
| unified_exec | `codex-rs/core/src/tools/runtimes/unified_exec.rs` |

`codex-rs/core/assets/tools/apply_patch.lark` 是一个 **Lark 语法文件**，说明补丁格式有形式化文法定义。**第 6 轮更正位置**：它不在 `handlers/` 下（`find codex-rs -name '*.lark'` 全仓只此一个）。

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

**接入点**（E3）：`submission_loop` 的六个分支中，五个转发给本模块的 `handle_*`——`codex-rs/core/src/session/handlers.rs:437` / `:452` / `:456` / `:460` / `:464` 分别对应 `handle_start` / `handle_audio` / `handle_text` / `handle_speech` / `handle_close`；`:468` 的 `ListVoices` 不进本模块，由 `codex-rs/core/src/session/handlers.rs:72` 的 `realtime_conversation_list_voices` 就地回一个事件。

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
> - **第 6 轮变更**：`symphonia` **已不再是 `codex-core` 的依赖**（`grep -n symphonia codex-rs/core/Cargo.toml` 零命中）。它随音频处理整体迁至新 crate `codex-rs/utils/audio/`；core 侧现在经 `codex_utils_audio::` 引用它的有 4 处：`codex-rs/core/src/context_manager/history.rs:58`、`codex-rs/core/src/session/mod.rs:177`、`codex-rs/core/src/tools/code_mode/mod.rs:46`、`codex-rs/core/src/tools/context.rs:18`。仍是**通用的音频输入处理**，不属于实时会话。
> - `tokio_tungstenite` 的使用者是 `codex-rs/core/src/client.rs`（模型客户端的 WebSocket 传输）与 `codex-rs/core/src/environment_selection.rs`（测试用的本地 WS 服务端）。
>
> 教训：**「Cargo.toml 里有某个依赖」不能反推「哪个模块在用它」**，必须 grep `use`。这与 [`AI_Coding_Context.md`](./AI_Coding_Context.md) 里记录的「按依赖名猜机制」致错模式是同一类。

> **未验证**（E1）：实时会话与常规 turn 在会话状态上的耦合程度、handoff 期间上下文历史如何合并，本文未追踪。入口见上表的 handoff 链与 `codex-rs/core/src/realtime_conversation_tests.rs`。

---

## 5. 审批与沙箱策略（E3）

工具调用要落到真实执行，必须先过两道决策：**审批**与**沙箱**。两者的策略类型都定义在 `codex-protocol` 中。

### 5.1 `AskForApproval`（`codex-rs/protocol/src/protocol.rs:986`）

> [!CAUTION]
> **本节是第 6 轮受损最重的一节：整套「命令白名单」安全模型已被上游否决，`UnlessTrusted` 的语义反转了。**
>
> 上游提交 `942af8447b`「Retire the untrusted approval policy (#39630)」删除了 `codex-rs/shell-command/src/command_safety/is_safe_command.rs` 整个模块<!-- ref-exempt: 反例——正文说明该路径已不存在 -->。复算：
>
> ```bash
> grep -rn "is_known_safe_command\|is_safe_command" codex-rs/ | wc -l   # 0
> grep -rn "used_complex_parsing" codex-rs/ --include='*.rs' | wc -l     # 0
> ```
>
> 旧版在这里给出的**四样东西同时失效**：`UnlessTrusted` 的变体语义、整块讲函数名考据的 WARNING、「自动放行的准确条件」代码块、以及基于它的三条要点。旧版向读者传达的是「Codex 有一个命令白名单，满足三个合取条件就免审批」——**一个已被上游明确否决的安全模型**。

| 变体 | 语义 |
| ---- | ---- |
| `UnlessTrusted`（序列化名 `untrusted`） | **除非 execpolicy 有显式规则放行，否则每条命令都要审批。** 源码注释原话：「Internal policy for projects marked untrusted. Commands require approval unless an explicit exec policy rule allows them.」（`codex-rs/protocol/src/protocol.rs:987-988`） |
| `OnRequest`（**默认**，兼容别名 `on-failure`） | 由模型决定何时请求用户批准 |
| `Granular(GranularApprovalConfig)` | 细粒度控制。字段为 `true` 表示放行该类，`false` 表示**自动拒绝**（而不是弹给用户） |
| `Never` | 永不询问。失败直接返回模型，不上升到用户 |

**判定骨架（E3，第 6 轮重推导）**：core 侧入口是 `codex-rs/core/src/exec_policy.rs` 的 `render_decision_for_unmatched_command_for_platform`（`:770` 起），**不是** `codex-rs/core/src/safety.rs`。现在是**先黑名单短路，再按审批档位分派**：

```rust
// codex-rs/core/src/exec_policy.rs:799-806 —— 第一步：危险命令短路
if dangerous_command_match.is_some() || windows_managed_fs_restrictions_without_sandbox_backend {
    return match approval_policy {
        AskForApproval::Never => Decision::Forbidden,
        AskForApproval::OnRequest
        | AskForApproval::UnlessTrusted
        | AskForApproval::Granular(_) => Decision::Prompt,
    };
}

// :809 起 —— 第二步：按档位分派
match approval_policy {
    AskForApproval::Never => Decision::Allow,        // :810-814，靠沙箱兜底
    AskForApproval::UnlessTrusted => {
        // Projects marked untrusted require approval for every command
        // that is not explicitly allowed by an exec policy rule.
        Decision::Prompt                              // :815-819
    }
    AskForApproval::OnRequest => { /* 再按 FileSystemSandboxKind 细分 */ }
    // ……
}
```

要点：

1. **判定极性翻转了。** 从「列举什么是安全的（白名单）」变成「列举什么是危险的（黑名单）」。`codex-rs/shell-command/src/command_safety/` 下现只剩 `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` 一条通路。
2. **`UnlessTrusted` 不再有任何自动放行分支。** 它在第二步里是一条光秃秃的 `Decision::Prompt`。
3. **`windows_managed_fs_restrictions_without_sandbox_backend` 的极性也反了。** 旧版说它是「放行路径的析取项」（Windows 保守场景也走同一条放行路径）；实际它现在是 `Prompt` / `Forbidden` 分支的析取项（`:799`）——它**触发审批**，不是放行。
4. **`dangerous_command_match` 命中时短路**（`:799-806`）：在任何审批策略下都不会自动放行——`Never` 下 `Forbidden`，其余一律 `Prompt`。这一条是旧版三条要点里唯一侥幸幸存的。

> 旧版还引用了两处「残留旧名的注释」作为佐证：`codex-rs/protocol/src/protocol.rs:919` 与 `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs:362`。<!-- ref-exempt: 反例——正文说明该旧路径已不存在 -->第 6 轮实测：前者的注释已按上面改写，后者的**路径本身都不存在了**（runtimes 重组见 §4.6），且新文件中对 `is_safe_command` 零命中。

`GranularApprovalConfig` 的 5 个字段（`codex-rs/protocol/src/protocol.rs:1012-1026`，E3；字段名与两个 `#[serde(default)]` 标注第 6 轮复核无变化）：

| 字段 | 控制的审批流 |
| ---- | ---- |
| `sandbox_approval` | shell 命令审批，含内联的 `with_additional_permissions` 与 `require_escalated` 请求 |
| `rules` | 由 execpolicy `prompt` 规则触发的提示 |
| `skill_approval` | 技能脚本执行触发的审批（`#[serde(default)]`） |
| `request_permissions` | 由 `request_permissions` 工具触发的提示（`#[serde(default)]`） |
| `mcp_elicitations` | MCP elicitation 提示 |

> [!WARNING]
> `Granular` 中字段为 `false` 的语义是**自动拒绝**，不是"询问用户"。枚举上方的文档注释原话：「When a field is `true`, commands in that category are allowed. When it is `false`, those requests are **automatically rejected instead of shown to the user**.」

### 5.2 `SandboxPolicy`（`codex-rs/protocol/src/protocol.rs:1072`）

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

### 5.3 `ReviewDecision`：审批的返回值（`codex-rs/protocol/src/protocol.rs:4145`，E3）

> 第一版两篇文档都没提这个类型，但它是审批链路的出口。

```rust
/// User's decision in response to an ExecApprovalRequest.
pub enum ReviewDecision { .. }
```

**8 个变体**（序列化为 snake_case）。**第 6 轮补入此前漏掉的 `ApprovedMcpPolicyAmendment`**：

| 变体 | 语义 |
| ---- | ---- |
| `Approved` | 批准本次执行 |
| `ApprovedExecpolicyAmendment { proposed_execpolicy_amendment }` | 批准并**落盘一条 execpolicy 修正**，后续同类命令自动放行 |
| `ApprovedForSession` | 批准，且**本会话内**同一审批缓存键的后续请求自动放行 |
| `ApprovedMcpPolicyAmendment` | **第 6 轮补入**：批准该 MCP 工具调用，并**跨会话**落盘一条 MCP 策略修正，后续匹配的调用自动放行 |
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

> [!CAUTION]
> **第 6 轮：本节描述的机制已被整体换掉。** 旧版写的是「两个 feature 开关 + 一个判据函数」的三级判定，三个指标名 `remote_v2` / `remote` / `local`。现在：
>
> - **远程压缩 v1 整条路径删除**——`compact_remote.rs` 与 `compact_remote_request.rs` 两个文件都不存在了<!-- ref-exempt: 反例——正文说明这两个路径已不存在 -->，`"remote"` 这个指标名随之消失。
> - **判据函数 `should_use_remote_compact_task()` 删除**（全仓零命中）。
> - **`Feature::RemoteCompactionV2` 降为 `Stage::Removed` + `default_enabled: false`**（`codex-rs/features/src/lib.rs:1800-1805`），且 `codex-rs/core/src/tasks/compact.rs` **不再引用它**。
> - 取而代之的是 provider 侧的三态能力枚举 `RemoteCompactionSupport`。
>
> **净行为大致不变**（OpenAI/Azure 走远程 v2，其余走本地），但机制描述全错，且结论有一处实质不完备——见下方 IMPORTANT。

`core/src/` 下与压缩相关的有 **10 个文件**：

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/core/src/compact.rs` | 本地压缩主体（`run_compact_task()` 在 `:146`）；`SUMMARIZATION_PROMPT` 现由 `codex-prompts` 定义，`:58` 只是再导出 |
| `codex-rs/core/src/compact_token_budget.rs` | token 预算路径，入口 `run_manual_compact_task()`（`:24`） |
| `codex-rs/core/src/compact_model_fallback.rs` | 模型回退：`should_retry_with_current_model()`（`:9`）/ `record_model_fallback()`（`:18`） |
| `codex-rs/core/src/compact_remote_v2.rs` | 远程压缩 v2 |
| `codex-rs/core/src/compact_remote_v2_attempt.rs` | v2 的内部辅助（无 `pub` 顶层函数） |
| `codex-rs/core/src/compact_remote_v2_images.rs` | **第 6 轮新增**：v2 的图片处理 |
| `codex-rs/core/src/compact_remote_history.rs` | **第 6 轮新增**：远程压缩的历史处理 |
| `codex-rs/core/src/compact_tests.rs` | 测试 |
| `codex-rs/core/src/compact_remote_history_tests.rs` | **第 6 轮新增**：测试 |
| `codex-rs/core/src/compact_remote_v2_image_budget_tests.rs` | **第 6 轮新增**：测试 |

**路径选择现在是两级判定，读一个 76 行的文件就能确定**（E3，`codex-rs/core/src/tasks/compact.rs:28-72` 的 `CompactTask::run`）：

```
① features.enabled(Feature::TokenBudget)
   → compact_token_budget::run_manual_compact_task(..)   【最高优先级，直接 return Ok(None)】
② 否则按 ctx.provider.capabilities().remote_compaction 分派
   RemoteCompactionSupport::V2          → compact_remote_v2::run_remote_compact_task(..)  【指标 "remote_v2"】
   RemoteCompactionSupport::Unsupported → compact::run_compact_task(..)                   【指标 "local"】
```

判据是**一个布尔开关加一个能力枚举**（旧版说的「两个布尔开关」已不成立）：

| 判据 | 取值 | 出处 |
| ---- | ---- | ---- |
| `Feature::TokenBudget` | `Stage::UnderDevelopment`，`default_enabled: false` | `codex-rs/features/src/lib.rs:1656-1660` |
| `ctx.provider.capabilities().remote_compaction` | `V2` 当且仅当 `is_openai() \|\| is_azure_responses_provider(..)` | `codex-rs/model-provider/src/provider.rs:410-417` |
| 同上，**Amazon Bedrock 另行硬编码 `V2`** | 不经上面那个条件判断 | `codex-rs/model-provider/src/amazon_bedrock/mod.rs:214-221` |

> [!IMPORTANT]
> **默认行为**（E3）：
>
> - provider 是 **OpenAI / Azure Responses / Amazon Bedrock** → 走**远程压缩 v2**。注意这由 **provider 能力直接决定，没有 feature 开关参与**——旧版写的「因为 `RemoteCompactionV2` 默认开启」这个理由已不成立。
> - **其余 provider** → 走本地压缩。
> - **token-budget 路径默认关闭**，一旦开启会**抢占**上面两条。
>
> **旧版「其他 provider → 走本地压缩」这个绝对化陈述不完备**：Amazon Bedrock 的 `capabilities()` 在生产实现里硬编码返回 `RemoteCompactionSupport::V2`（已确认不在 `#[cfg(test)]` 内），它既不是 OpenAI 也不是 Azure，却同样走远程 v2。**凡是「除了 X 就是 Y」这类穷举式陈述，都要把硬编码的特例翻出来。**

> **未验证**（E1）：模型回退的具体触发条件、本地与远程压缩在**产出内容**上的差异。集成测试在 `codex-rs/core/tests/suite/compact.rs`（5,511 行），是理解压缩行为的最佳入口。压缩本身是一种 `SessionTask`（`codex-rs/core/src/tasks/compact.rs`，见 §2.3）。

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
| Guardian 评审的具体策略 | E1 | `codex-rs/prompts/templates/guardian/policy.md`（第 6 轮已从 core 迁出）、`codex-rs/core/src/guardian/prompt.rs` |
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
