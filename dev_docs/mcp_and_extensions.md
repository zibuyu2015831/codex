---
title: Codex MCP 与四条扩展路径
summary: 通过代码级核查确定 ext 扩展、插件、Skills、MCP 四条扩展路径的真实关系，说明 extension-api 的 13 个 Contributor trait 构成统一扩展点、Skills 与 MCP 通过包装 crate 接入该体系、插件是并行的独立机制，并给出各路径的选择依据。
keywords: codex | mcp | extensions | plugins | skills | extension-api | contributor
scope: codex-rs/ext、core-plugins、core-skills 与 MCP 相关 crate 的扩展体系
related_files: codex-rs/ext/extension-api/src/lib.rs | codex-rs/ext/extension-api/src/contributors.rs | codex-rs/ext/skills/Cargo.toml | codex-rs/ext/mcp/Cargo.toml | codex-rs/core-plugins/src/lib.rs | codex-rs/core/Cargo.toml
dependencies: dev_docs/crate_map.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-03
---

# MCP 与四条扩展路径

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 本文的核心结论（四条路径的关系）已由 **E3 代码级核查**确立，取代此前 `_analysis` 中标注的 E1 推断

> [!IMPORTANT]
> **这篇文档解决了一个长期挂账的问题。** 第 1 批的 `architecture_overview.md`、`crate_map.md`、`AI_Coding_Context.md` 都写着「四条扩展路径的相互关系尚未验证（E1），禁止凭目录名推断」。本文通过读取 `Cargo.toml` 依赖关系与 `extension-api` 公开 API 完成了核查，结论见 §1。
>
> 第 1 批文档中的 E1 声明**在本文发布后即失效**，以本文为准。

---

## 1. 核心结论：不是四条平行路径，是「一个统一扩展点 + 一个并行机制」

### 1.1 依赖关系实测（E3）

| 事实 | 证据 |
| ---- | ---- |
| 全部 12 个 `ext/*` crate 都依赖 `codex-extension-api` | `grep -rl "codex-extension-api" codex-rs --include=Cargo.toml` |
| `ext/skills`（`codex-skills-extension`）**同时依赖** `codex-core-skills` 与 `codex-skills` | `codex-rs/ext/skills/Cargo.toml:16,22` |
| `ext/mcp`（`codex-mcp-extension`）**依赖** `codex-mcp` | `codex-rs/ext/mcp/Cargo.toml:24` |
| `core-plugins` 依赖 `codex-plugin`，**不依赖 `codex-extension-api`** | `codex-rs/core-plugins/Cargo.toml:30` |
| `codex-core` 同时依赖 `codex-extension-api`、`codex-core-plugins`、`codex-core-skills`、`codex-mcp`、`codex-rmcp-client` | `codex-rs/core/Cargo.toml:36,37,39,46,64` |

### 1.2 由此确定的关系

```
                    ┌──────────────────────────────┐
                    │  codex-extension-api          │
                    │  13 个 Contributor trait      │
                    │  + ExtensionRegistry          │
                    │  ← 统一扩展点                  │
                    └──────────────┬───────────────┘
                                   │ 全部 12 个 ext/* 都实现它
        ┌──────────────┬───────────┼───────────┬──────────────┐
        │              │           │           │              │
   ext/skills      ext/mcp    ext/goal   ext/memories   ext/web-search
        │              │                                  等 12 个
        ↓ 包装          ↓ 包装
  codex-core-skills  codex-mcp
  codex-skills       （MCP 客户端）
   （Skills 运行时）


        ┌────────────────────────────────┐
        │  core-plugins + codex-plugin    │
        │  ← 并行的独立机制               │
        │  不依赖 extension-api           │
        └────────────────────────────────┘
                       ↑
              codex-core 直接依赖
```

**三句话总结**：

1. **`ext/extension-api` 是唯一的统一扩展点**，12 个 `ext/*` crate 全部构建在它之上
2. **Skills 与 MCP 不是独立路径，而是被包装成扩展**——`ext/skills` 包装 `core-skills`+`skills`，`ext/mcp` 包装 `codex-mcp`
3. **插件（plugins）是真正并行的独立机制**——`core-plugins` 不依赖 `extension-api`，由 `codex-core` 直接对接

> 所以此前"四条并行路径"的说法**不准确**。准确的说法是：**一个统一扩展点（覆盖 ext/skills/MCP）+ 一个并行的插件机制**。

---

## 2. extension-api：13 个 Contributor trait（E3）

`codex-rs/ext/extension-api/src/contributors.rs` 定义了扩展可以"贡献"的全部切入点：

| Trait | 位置 | 扩展能贡献什么 |
| ---- | ---- | ---- |
| `McpServerContributor<C>` | `:66` | MCP server 接入 |
| `ContextContributor` | `:81` | 上下文内容 |
| `ThreadLifecycleContributor<C>` | `:124` | 线程生命周期钩子（start / stop / resume / idle） |
| `TurnLifecycleContributor` | `:167` | turn 生命周期（start / stop / abort / error） |
| `TurnInputContributor` | `:208` | turn 输入 |
| `ConfigContributor<C>` | `:225` | 配置 |
| `TokenUsageContributor` | `:242` | token 用量统计 |
| `SkillInvocationContributor` | `:262` | Skill 调用 |
| `ToolContributor` | `:276` | 工具注册 |
| `ToolLifecycleContributor` | `:300` | 工具生命周期（start / finish） |
| `ApprovalReviewContributor` | `:313` | 审批评审 |
| `TurnItemContributor` | `:327` | turn 条目 |
| `UserInstructionsProvider` | `user_instructions.rs:38` | 用户指令加载 |

**所有 trait 都要求 `Send + Sync`**，说明扩展在多线程运行时环境中被调用。

### 注册机制

```rust
// lib.rs:76-78
pub use registry::ExtensionRegistry;
pub use registry::ExtensionRegistryBuilder;
pub use registry::empty_extension_registry;
```

`ExtensionRegistryBuilder` 的使用可在 `codex-rs/core/src/thread_manager_tests.rs:535,704` 看到实例——**扩展注册表在 thread manager 层构建**，说明扩展的生命周期与 thread 绑定。

### 能力接口（`capabilities.rs`）

| 类型 | 用途 |
| ---- | ---- |
| `AgentSpawner` / `AgentSpawnFuture` | 扩展可以派生子智能体 |
| `ExtensionEventSink` / `NoopExtensionEventSink` | 事件下沉 |
| `ResponseItemInjector` / `NoopResponseItemInjector` | **向模型响应流注入条目** |
| `ExtensionMetrics` | 指标 |
| `ExtensionWarning` | 警告 |

> `Noop*` 变体的存在说明这些能力是**可选注入**的——测试或轻量场景可以传空实现。

### 复用的核心类型

`extension-api` 大量 re-export `codex-tools` 与 `codex-protocol` 的类型（`lib.rs:16-35`）：`ToolCall`、`ToolSpec`、`ToolExecutor`、`ToolOutput`、`ResponsesApiTool`、`ConversationHistory`、`ResponseItem`、`FunctionCallError` 等。

> **含义**：扩展作者只需依赖 `codex-extension-api` 一个 crate，就能拿到全套工具类型，不必直接依赖 `codex-tools` 或 `codex-protocol`。这是有意设计的**收敛入口**。

---

## 3. 12 个内建扩展（E4）

| crate | 目录 | 行数 | 被 core 直接依赖 |
| ---- | ---- | ---: | :--: |
| `codex-skills-extension` | `ext/skills` | 11,114 | ✅（`core/Cargo.toml:144`） |
| `codex-goal-extension` | `ext/goal` | 4,384 | — |
| `codex-memories-extension` | `ext/memories` | 2,399 | — |
| `codex-extension-api` | `ext/extension-api` | 2,377 | ✅（`:39`） |
| `codex-mcp-extension` | `ext/mcp` | 1,504 | — |
| `codex-image-generation-extension` | `ext/image-generation` | 1,166 | ✅（`:141`） |
| `codex-web-search-extension` | `ext/web-search` | 874 | ✅（`:147`） |
| `codex-git-attribution` | `ext/git-attribution` | 439 | — |
| `codex-extension-items` | `ext/items` | 271 | ✅（`:40`） |
| `codex-agent-extension` | `ext/agent` | 161 | — |
| `codex-guardian` | `ext/guardian` | 77 | — |
| `codex-connectors-extension` | `ext/connectors` | 71 | — |

> [!NOTE]
> **`codex-core` 只直接依赖 5 个 ext crate**（skills / image-generation / web-search / extension-api / items）。其余 7 个由别处装配。
>
> **未验证**（E1）：其余 7 个扩展在哪一层被注册进 `ExtensionRegistry`。`cli`、`app-server`、`tui` 都依赖 `extension-api`，装配点可能在这些 crate 中。

---

## 4. 插件路径（并行机制）

### 4.1 模块版图（E4，`core-plugins/src/lib.rs`）

| 模块 | 职责 |
| ---- | ---- |
| `manifest` | 插件清单 |
| `loader` | 加载 |
| `store` | 存储 |
| `toggles` | 启用/禁用开关 |
| `startup_sync` | 启动时同步 |
| `installed_marketplaces` | 已安装的市场 |
| `marketplace` / `marketplace_add` / `marketplace_remove` / `marketplace_upgrade` | 市场的增删改查 |
| `remote` / `remote_bundle` / `remote_legacy` | 远程插件（含 legacy 兼容路径） |

`lib.rs:35` 有一个 `pub fn is_openai_curated_marketplace_name(marketplace_name: &str) -> bool`——**存在 OpenAI 官方精选市场的概念**。

### 4.2 依赖插件运行时的 crate（E3）

`core`、`tui`、`cli`、`app-server`、`external-agent-migration`、`ext/connectors`、`ext/mcp`

> `ext/connectors` 与 `ext/mcp` **同时依赖 extension-api 和 core-plugins**——两套机制在这两个扩展里交汇。这是唯一的交叉点。

### 4.3 用户入口

| 入口 | 说明 |
| ---- | ---- |
| `codex plugin add / list / remove / marketplace` | CLI 子命令（`cli/src/main.rs:1090-1110`） |
| `plugin/*` 协议方法（12 个） | app-server 协议 |
| `request_plugin_install` / `list_available_plugins_to_install` | 模型可调用的工具 |

**模型自己可以请求安装插件**——`core/src/tools/handlers/request_plugin_install.rs` 与 `list_available_plugins_to_install.rs`。这是一条值得注意的能力面。

---

## 5. Skills 路径

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-skills-extension`（`ext/skills`） | 11,114 | **扩展包装层**，实现 `SkillInvocationContributor` 等 trait |
| `codex-core-skills` | 9,083 | 运行时：`loader` / `injection` / `model` / `remote` / `service` / `system` / `config_rules` |
| `codex-skills` | 372 | 系统 skill 的安装与缓存 |

`codex-skills/src/lib.rs` 的公开 API（E3）：

```rust
pub fn system_cache_root_dir(codex_home: &AbsolutePathBuf) -> AbsolutePathBuf;  // :30
pub fn install_system_skills(codex_home: &AbsolutePathBuf) -> Result<(), SystemSkillsError>;  // :44
pub enum SystemSkillsError;  // :143
```

**系统 skill 缓存落在 `CODEX_HOME` 下**。仓库内自带的样例 skill 在 `codex-rs/skills/src/assets/samples/` —— 包括 `plugin-creator`、`skill-creator`、`skill-installer`。

`core-skills` 的 `injection` 模块说明 skill 内容会被**注入模型上下文**。

---

## 6. MCP 路径

### 6.1 四个 crate 的分工（E3/E4）

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-rmcp-client` | 19,361 | MCP 客户端底层实现 |
| `codex-mcp` | 14,560 | MCP 集成层，含 `mcp_connection_manager.rs` |
| `codex-mcp-extension`（`ext/mcp`） | 1,504 | **扩展包装层**，实现 `McpServerContributor` |
| `codex-mcp-server` | 4,128 | **把 Codex 自身暴露为 MCP server** |

**两个方向不要混淆**：

| 方向 | crate | 用户入口 |
| ---- | ---- | ---- |
| Codex **作为客户端**连接外部 MCP server | `rmcp-client`、`codex-mcp`、`ext/mcp` | `codex mcp` |
| Codex **作为服务端**被别的客户端连接 | `mcp-server` | `codex mcp-server`（stdio） |

### 6.2 强制约定

> [!IMPORTANT]
> `AGENTS.md:36`：处理 MCP 工具调用与工具变更时，**优先使用 codex-rs/codex-mcp/src/mcp_connection_manager.rs**，复用既有抽象，尽量缩小改动面，不要把逻辑层层透传。

### 6.3 会话侧接入

`codex-rs/core/src/session/` 下有 5 个 MCP 相关文件：`mcp.rs`、`mcp_runtime.rs`、`mcp_prewarm.rs`（**预热**）、`mcp_refresh.rs`、`mcp_tests.rs`。

预热与刷新的存在说明 MCP server 连接是**有状态且需要维护的长连接**，不是每次调用现连。

### 6.4 配置与协议

| 面 | 位置 |
| ---- | ---- |
| 配置类型 | `codex-rs/config/src/mcp_types.rs`、`mcp_edit.rs`、`mcp_requirements.rs` |
| 协议方法 | `mcpServer/*`（6 个）、`config/mcpServer/reload` |
| 工具处理器 | `core/src/tools/handlers/mcp.rs`、`mcp_resource.rs` |

---

## 7. 我该用哪条路径？

| 你要做的事 | 走哪条 | 理由 |
| ---- | ---- | ---- |
| 给模型加一个新工具 | **ext 扩展**，实现 `ToolContributor` | 统一扩展点，能拿到全套工具类型 |
| 在 turn 或 thread 生命周期插入逻辑 | **ext 扩展**，实现对应 `*LifecycleContributor` | 只有扩展体系有生命周期钩子 |
| 接入外部 MCP server | **配置 MCP**，不用写代码 | `codex mcp` + `config.toml` |
| 分发可安装的能力包给用户 | **插件** | 有市场、安装、开关、远程分发的完整基建 |
| 提供可复用的提示词/流程资产 | **Skill** | `core-skills` 的 injection 机制 |
| 把 Codex 接进别的 MCP 宿主 | **`codex mcp-server`** | 反方向，无需改代码 |

---

## 8. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| MCP 工具调用优先走 `mcp_connection_manager.rs` | `AGENTS.md:36` |
| 尽量复用既有抽象，不要多层透传 | `AGENTS.md:36` |
| 新扩展应实现 `extension-api` 的 trait，而不是直接改 `codex-core` | 见 [`crate_map.md`](./crate_map.md) §6 |
| 扩展 trait 都要求 `Send + Sync` | `contributors.rs` |
| trait 中的异步方法用 `impl Future + Send`，不要 `#[allow(async_fn_in_trait)]` | `AGENTS.md:25-28` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 7 个未被 core 直接依赖的 ext 在哪装配 | E1 | `cli`、`app-server`、`tui` 中搜 `ExtensionRegistryBuilder` |
| 各 Contributor trait 的方法签名与调用时机 | E1（仅知 trait 名） | `ext/extension-api/src/contributors.rs` |
| 插件清单（manifest）的格式 | E1 | `core-plugins/src/manifest.rs` |
| 插件市场的远程协议 | E1 | `core-plugins/src/remote*.rs` |
| Skill 注入模型上下文的具体形式 | E1 | `core-skills/src/injection.rs` |
| MCP 连接的握手与工具发现流程 | E1 | `codex-mcp/src/mcp_connection_manager.rs` |
| `ext/connectors` 与 `ext/mcp` 同时依赖两套机制的原因 | E1 | 两者的 `lib.rs` |
| `codex-connectors`（4,851 行）与 `ext/connectors`（71 行）的分工 | E1 | 两者的 `Cargo.toml` 与 `lib.rs` |

---

## 10. 相关文档

- [Crate 地图](./crate_map.md) §3.8 — 扩展相关 19 个 crate 清单
- [智能体核心循环](./core_agent_loop.md) §3 — 工具调用链路
- [配置体系](./config_system.md) — MCP 与插件的配置入口
- [app-server 协议](./app_server_protocol.md) — `plugin/*`、`mcpServer/*` 方法
- [实验性表面](./experimental_surfaces.md) — 其他能力面
