---
title: Codex 智能体核心循环
summary: 描述 codex-core 的会话与 turn 组织方式、工具调用的路由与分发链路、上下文管理与压缩机制、审批与沙箱决策的接入点，并标注各结论的证据等级与未验证边界。
keywords: codex | agent-loop | session | turn | tool-router | context-manager | compact
scope: codex-rs/core 的会话、turn、工具调用与上下文管理
related_files: codex-rs/core/src/session/turn.rs | codex-rs/core/src/tools/router.rs | codex-rs/core/src/tools/registry.rs | codex-rs/core/src/tools/handlers/mod.rs | codex-rs/core/src/context_manager/mod.rs | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-03
---

# 智能体核心循环

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/core`（296,963 行，67 个 workspace 依赖）的骨架结构
> **证据等级**: 目录与模块结构为 E4；类型与函数签名为 E3；模块间协作关系部分为 E1，已在文中逐处标注

> [!IMPORTANT]
> `codex-core` 是全仓最大的 crate。本文给出的是**可导航的骨架**，不是逐行讲解。遇到本文标注为 E1 的判断，请回去读代码，不要直接采信。

---

## 1. codex-core 的模块版图

`codex-rs/core/src/` 下的一级条目超过 100 个。按职责归类：

| 子系统 | 位置 | 说明 |
| ---- | ---- | ---- |
| **会话与 turn** | `session/`（28 个文件） | 会话生命周期、turn 组织、上下文窗口、token 预算 |
| **工具调用** | `tools/`（28 个文件 + 3 个子目录） | 路由、注册表、编排、审批、沙箱决策 |
| **上下文管理** | `context_manager/` | 历史、归一化、增量更新 |
| **上下文压缩** | `compact*.rs`（8 个文件） | 本地压缩、远程压缩 v1/v2、token 预算、模型回退 |
| **模型客户端** | `client.rs`、`client_common.rs` | 与模型服务通信 |
| **配置** | `config/` | 配置加载与校验（详见 [`config_system.md`](./config_system.md)） |
| **执行** | `exec.rs`、`exec_env.rs`、`exec_policy.rs` | 命令执行与策略 |
| **规范注入** | `agents_md.rs`、`agents_md_manager.rs` | 读取并注入仓库规范文件 |
| **补丁应用** | `apply_patch.rs` | 结构化补丁 |
| **扩展接入** | `apps/`、`agent/`、`connectors.rs` | 扩展与连接器 |

> [!NOTE]
> **未验证**（E1）：上表是按文件名与目录归类的**结构性描述**，各子系统之间的调用次序与依赖方向**未做完整追踪**。特别是 `compact*.rs` 的 8 个文件之间如何分工，本文不做推断。

---

## 2. 会话与 turn

### 2.1 `session/` 的组成

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

### 2.2 turn 的内部状态（E3）

`session/turn.rs` 中可见的状态类型：

| 类型 | 位置 | 用途 |
| ---- | ---- | ---- |
| `PlanModeStreamState` | `turn.rs:1593` | 计划模式的流式状态 |
| `AssistantMessageStreamParsers` | `turn.rs:1612` | 助手消息的流式解析器 |
| `ProposedPlanItemState` | `turn.rs:1654` | 提议的计划项状态 |

> 这三个类型都带 `impl` 块，说明 turn 内部至少存在**计划模式**与**流式消息解析**两条状态机。完整的 turn 状态流转**未追踪**（E1）。

> [!CAUTION]
> **从既有 rollout 恢复会话是 `AGENTS.md:105-110` 点名的高风险改动面之一。** 涉及 `rollout_reconstruction.rs` 的改动请格外谨慎。

---

## 3. 工具调用链路

这是本文证据最扎实的部分（E3）。

### 3.1 三个核心类型

| 类型 | 位置 | 角色 |
| ---- | ---- | ---- |
| `ToolCall` | `tools/router.rs:32` | 一次工具调用的载体 |
| `ToolRouter` | `tools/router.rs:68` | 路由与分发 |
| `ToolRegistry` | `tools/registry.rs:252` | 工具注册表 |

### 3.2 `ToolRouter` 的公开 API（E3）

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

### 3.3 调用链路上的其他环节

| 文件 | 职责 |
| ---- | ---- |
| `tools/orchestrator.rs` | 编排 |
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

> **未验证**（E1）：上述环节的**调用次序**。例如「审批发生在沙箱决策之前还是之后」需要读 `orchestrator.rs` 才能确认，本文不推断。

### 3.4 内置工具处理器（E4，来自 `tools/handlers/mod.rs`）

| 模块 | 工具用途 |
| ---- | ---- |
| `shell` | shell 命令执行 |
| `apply_patch` | 应用结构化补丁 |
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
| `extension_tools` | 扩展提供的工具 |
| `dynamic` | 动态工具 |
| `test_sync` | 测试同步（测试用途） |

**模式**：多数 handler 有配套的 `*_spec.rs`（工具规格）与 `*_tests.rs`（单元测试）。新增工具时应遵循这个三件套结构。

### 3.5 工具运行时（`tools/runtimes/`）

| 运行时 | 文件 |
| ---- | ---- |
| shell | `shell.rs` + `shell/` 子目录 |
| apply_patch | `apply_patch.rs` |
| unified_exec | `unified_exec.rs` |

`handlers/apply_patch.lark` 是一个 **Lark 语法文件**，说明补丁格式有形式化文法定义。

---

## 4. 审批与沙箱策略（E3）

工具调用要落到真实执行，必须先过两道决策：**审批**与**沙箱**。两者的策略类型都定义在 `codex-protocol` 中。

### 4.1 `AskForApproval`（`codex-rs/protocol/src/protocol.rs:917`）

| 变体 | 语义 |
| ---- | ---- |
| `UnlessTrusted`（序列化名 `untrusted`） | 只有 `is_safe_command()` 判定为"已知安全且只读"的命令自动放行，其余一律询问 |
| `OnRequest`（**默认**，兼容别名 `on-failure`） | 由模型决定何时请求用户批准 |
| `Granular(GranularApprovalConfig)` | 细粒度控制。字段为 `true` 表示放行该类，`false` 表示**自动拒绝**（而不是弹给用户） |
| `Never` | 永不询问。失败直接返回模型，不上升到用户 |

> [!WARNING]
> `Granular` 中字段为 `false` 的语义是**自动拒绝**，不是"询问用户"。这一点容易误读。

### 4.2 `SandboxPolicy`（`codex-rs/protocol/src/protocol.rs:1004`）

| 变体 | 磁盘 | 网络 |
| ---- | ---- | ---- |
| `DangerFullAccess`（`danger-full-access`） | 无限制 | 无限制 |
| `ReadOnly`（`read-only`） | 只读 | `network_access` 字段，**默认 false** |
| `WorkspaceWrite`（`workspace-write`） | 只读 + cwd 可写 | `network_access` 字段，**默认 false** |
| `ExternalSandbox`（`external-sandbox`） | 完整磁盘访问（表示进程已在外部沙箱内） | 由 `network_access` 决定 |

`WorkspaceWrite` 的可调字段：

- `writable_roots`：cwd 之外的额外可写目录
- `exclude_tmpdir_env_var`：为 `true` 时**不**把用户级 `TMPDIR` 计入默认可写根
- `exclude_slash_tmp`：为 `true` 时在 UNIX 上**不**把 `/tmp` 计入默认可写根

> **默认收紧**：`ReadOnly` 与 `WorkspaceWrite` 的 `network_access` 默认都是 `false`。放开网络是显式动作。

沙箱的平台实现见 [`tools_and_sandbox.md`](./tools_and_sandbox.md)。

---

## 5. 上下文管理与压缩

### 5.1 `context_manager/`（E4 结构）

| 文件 | 职责 |
| ---- | ---- |
| `history.rs` | 历史记录 |
| `normalize.rs` | 归一化 |
| `updates.rs` | 增量更新 |

### 5.2 压缩（compact）相关文件

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

> **未验证**（E1）：v1 与 v2 的选择条件、回退触发条件、本地与远程的分工。这需要完整读取上述 8 个文件。集成测试在 `codex-rs/core/tests/suite/compact.rs`（5,440 行），是理解压缩行为的最佳入口。

---

## 6. 仓库规范的注入

`core/src/agents_md.rs` 与 `agents_md_manager.rs` 负责读取仓库中的规范文件并注入模型上下文。

> 这解释了为什么仓库根的 `AGENTS.md` 对 Codex 自身有约束力——它不只是给人看的文档，也是运行时注入的内容。

---

## 7. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **改智能体逻辑必须补集成测试**，位于 `core/tests/suite/`，用 `test_codex` 搭建实例 | `AGENTS.md:112-118` |
| 需列出主要逻辑变更与用户可见行为清单 | `AGENTS.md:117-118` |
| 改了 core 后要跑 `just test`（全量），不只是 `-p codex-core` | `AGENTS.md:64` |
| 不要无必要地调用 `reset_client_session`，让增量检查逻辑决定是否复用上次请求 | `AGENTS.md:37` |
| MCP 工具调用优先走 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` | `AGENTS.md:36` |
| **默认不要往 core 加代码** | `AGENTS.md:74-83`，见 [`crate_map.md`](./crate_map.md) §6 |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| turn 的完整状态流转 | E1 | `session/turn.rs`（分段读）、`session/turn_tests.rs` |
| 工具调用各环节的次序 | E1 | `tools/orchestrator.rs`、`tools/lifecycle.rs` |
| 压缩的 v1/v2 选择与回退条件 | E1 | `core/tests/suite/compact.rs`（5,440 行） |
| 模型客户端的请求构造与流式解析 | E1 | `client.rs`、`client_common.rs` |
| 多智能体协作机制 | E1 | `session/multi_agents.rs`、`tools/handlers/multi_agents_v2/` |
| token 预算的具体算法 | E1 | `session/token_budget.rs`、`compact_token_budget.rs` |
| `is_safe_command()` 的判定规则 | E1 | `codex-shell-command` crate |

---

## 9. 相关文档

- [架构总览](./architecture_overview.md) — 进程边界与整体拓扑
- [Crate 地图](./crate_map.md) — core 的依赖热点与减负指引
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱的平台实现
- [配置体系](./config_system.md) — 审批与沙箱策略的配置入口
- [会话与持久化](./session_and_persistence.md) — rollout 与线程存储
