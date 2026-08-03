---
title: Codex MCP 与四条扩展路径
summary: 通过代码级核查确定 ext 扩展、插件、Skills、MCP 四条扩展路径的真实关系，说明 extension-api 的 13 个扩展点 trait（12 个 *Contributor 加上不带该后缀的 UserInstructionsProvider）构成主扩展点、ext/* 下 12 个 crate 中有 8 个构建在它之上而 items/agent/connectors 三个是例外、11 个具体扩展全部在 core 之上的 app-server / cli / mcp-server 层装配，并指出 ext/connectors 建在插件机制上因而插件并非完全平行的独立轨道。
keywords: codex | mcp | extensions | plugins | skills | extension-api | contributor | thread_extensions
scope: codex-rs/ext、core-plugins、core-skills 与 MCP 相关 crate 的扩展体系
related_files: codex-rs/ext/extension-api/src/lib.rs | codex-rs/ext/extension-api/src/contributors.rs | codex-rs/ext/skills/Cargo.toml | codex-rs/ext/mcp/Cargo.toml | codex-rs/ext/agent/Cargo.toml | codex-rs/ext/items/Cargo.toml | codex-rs/ext/connectors/Cargo.toml | codex-rs/core-plugins/src/lib.rs | codex-rs/core/Cargo.toml | codex-rs/app-server/src/extensions.rs | codex-rs/mcp-server/src/message_processor.rs | AGENTS.md
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

> [!CAUTION]
> **本文已修订，修正了初版的多处事实错误**（各处均有「修订说明」）：
>
> 1. **不是"全部 12 个 ext/\* 都依赖 extension-api"**——12 个目录里 1 个就是 `extension-api` 本身（crate 不能依赖自己），剩下 11 个里有 **3 个不依赖它**。真实比例是 **8 / 11**。
> 2. **`codex-core` 并不直接依赖那 5 个 ext crate**——初版引用的 `core/Cargo.toml:141/144/147` 全部落在 `[dev-dependencies]`（该段从 `:137` 开始）。**11 个具体扩展一个都不在 core 的生产依赖里。**
> 3. **装配点不是未知的**——主装配点是 `app-server/src/extensions.rs` 的 `thread_extensions()`。
> 4. `codex-rs/codex-mcp/src/mcp_connection_manager.rs` **这个文件不存在**，真实文件名是 `connection_manager.rs`。
> 5. `ext/connectors` **不依赖** extension-api，所以它不是"两套机制的交叉点"；`tui` **不依赖** extension-api。

---

## 1. 核心结论：一个主扩展点 + 一个并行机制，但边界比初版描述的更松

### 1.1 依赖关系实测（E3，逐个 `Cargo.toml` 核对）

`ext/` 下共 12 个目录，其中 `ext/extension-api` 是扩展点本身，**具体扩展是 11 个**。逐个核对 `codex-extension-api` 依赖：

| `ext/*` | 依赖 `codex-extension-api` | 备注 |
| ---- | :--: | ---- |
| `git-attribution` / `goal` / `guardian` / `image-generation` / `mcp` / `memories` / `skills` / `web-search` | ✅（8 个） | 常规扩展 |
| `items` | ❌ | 只依赖 `codex-utils-absolute-path` + `schemars`/`serde`/`ts-rs` |
| `agent` | ❌ | 只依赖 `codex-core`、`codex-protocol` |
| `connectors` | ❌ | 依赖 `codex-connectors`、`codex-core-plugins`、`codex-plugin`、`codex-utils-path-uri` |

> [!CAUTION]
> **修订说明（原文错误）**：初版写「全部 12 个 `ext/*` crate 都依赖 `codex-extension-api`」，并给了 `grep -rl` 作为证据。那条 grep 的命中里**包含 `ext/extension-api/Cargo.toml` 自己**（`[package] name` 行就含这个字符串）——**crate 不可能依赖自己**。逐文件核对后的真实数字是 **11 个具体扩展中的 8 个**。

其余实测结论：

| 事实 | 证据 |
| ---- | ---- |
| `ext/skills`（`codex-skills-extension`）**同时依赖** `codex-core-skills` 与 `codex-skills` | `codex-rs/ext/skills/Cargo.toml:16,22` |
| `ext/mcp`（`codex-mcp-extension`）**依赖** `codex-mcp`，**也依赖 `codex-core`** | `codex-rs/ext/mcp/Cargo.toml`（`codex-core`、`codex-mcp` 均在 `[dependencies]`） |
| `core-plugins` 依赖 `codex-plugin`，**不依赖 `codex-extension-api`** | `codex-rs/core-plugins/Cargo.toml:30` |
| `codex-core` 的**生产**依赖中只有两个 ext crate：`codex-extension-api`(`:39`)、`codex-extension-items`(`:40`) | `codex-rs/core/Cargo.toml`；`grep -n "^\[" codex-rs/core/Cargo.toml` 显示 `[dev-dependencies]` 从 `:137` 开始 |

### 1.2 三个"例外" crate 各自是什么（E3）

它们不依赖 `extension-api`，但各有明确定位——不能因为目录在 `ext/` 下就当成同类：

| crate | 定位 | 依据 |
| ---- | ---- | ---- |
| `ext/items`（`codex-extension-items`） | **纯类型 crate**，不是扩展。模块文档自述：*"Typed display items owned by Codex extensions. This crate intentionally sits below `codex-protocol` so core can carry extension items without owning each extension's display schema."* | `ext/items/src/lib.rs:1-4` |
| `ext/agent`（`codex-agent-extension`） | **子智能体派生的辅助层**，位于 `ThreadManager` **之上**：定义 `AgentInvocation` / `AgentRun` / `AgentRunner`，直接使用 `codex_core::ThreadManager`、`StartThreadOptions`、`NewThread` | `ext/agent/src/lib.rs:1-25`；被 `app-server/src/request_processors/turn_processor.rs:2-4` 使用 |
| `ext/connectors`（`codex-connectors-extension`） | **建在插件机制之上**。模块文档只有一行：*"Executor-backed connector declaration loading."*；公开 `ExecutorPluginConnectorProvider` | `ext/connectors/src/lib.rs:1-6` |

> [!IMPORTANT]
> **`ext/connectors` 是"插件是完全平行的独立轨道"这一说法的反例。** 它位于 `ext/` 目录下、名字带 `-extension`，却完全不碰 `extension-api`，而是构建在 `codex-core-plugins` + `codex-plugin` 上。两套机制在目录层面并不是干净分开的。

### 1.3 由此确定的关系

```
     ┌─────────────────────────────────────────────────────┐
     │  codex-extension-api  ── 主扩展点                    │
     │  13 个扩展点 trait（12 个 *Contributor + 1）         │
     │  + ExtensionRegistry                                 │
     └───────────────────────┬─────────────────────────────┘
                             │ 11 个具体扩展中的 8 个实现它
   ┌────────┬────────┬───────┼────────┬──────────┬─────────────┐
   │        │        │       │        │          │             │
ext/skills ext/mcp ext/goal ext/  ext/web-  ext/image-  ext/git-
   │        │              memories  search    generation  attribution
   │        │                                              + ext/guardian
   ↓ 包装    ↓ 包装（且依赖 codex-core → 位于 core 之上）
core-skills  codex-mcp
+ skills     （MCP 客户端）

   —— 不接 extension-api 的三个例外 ——
   ext/items      纯类型 crate，「刻意位于 codex-protocol 之下」
   ext/agent      ThreadManager 之上的子智能体派生辅助层
   ext/connectors 建在插件机制上（core-plugins + plugin）

     ┌────────────────────────────────┐
     │  core-plugins + codex-plugin    │
     │  ← 并行机制（但见 ext/connectors）│
     │  不依赖 extension-api            │
     └────────────────────────────────┘
                    ↑
        codex-core 直接依赖 core-plugins

  装配层（core 之上）：app-server / cli / mcp-server
        ↑ 11 个具体扩展**全部**在这一层注册，core 生产依赖里一个都没有
```

**三句话总结（已修订）**：

1. **`ext/extension-api` 是主扩展点**，但**不是所有 `ext/*` 都构建在它之上**——11 个具体扩展里 8 个是，`items`/`agent`/`connectors` 三个不是。
2. **Skills 与 MCP 不是独立路径，而是被包装成扩展**——`ext/skills` 包装 `core-skills`+`skills`，`ext/mcp` 包装 `codex-mcp`；注意 **`ext/mcp` 依赖 `codex-core`，位于 core 之上**，不是 core 的下游。
3. **插件（plugins）大体是并行机制**——`core-plugins` 不依赖 `extension-api`、由 `codex-core` 直接对接；但 **`ext/connectors` 与 `ext/mcp` 说明两条轨道会在扩展内部合流**。

> 所以此前"四条并行路径"的说法**不准确**。准确的说法是：**一个主扩展点（覆盖多数 ext + skills + MCP）+ 一个大体并行、但在个别扩展里合流的插件机制**，另加若干不属于任何一条的支撑 crate。

---

## 2. extension-api：13 个扩展点 trait = 12 个 `*Contributor` + 1（E3）

> [!NOTE]
> **勘误：不要写成"13 个 Contributor trait"。** 上一稿全文（含摘要与 §1.3 的示意图）都用了这个说法，但 `contributors.rs` 里以 `Contributor` 结尾的 trait 只有 **12** 个；第 13 个是 `UserInstructionsProvider`，定义在**另一个文件** `ext/extension-api/src/user_instructions.rs:38`，**名字里没有 "Contributor"**。
>
> 复核：`grep -cE "pub trait [A-Za-z]*Contributor" codex-rs/ext/extension-api/src/contributors.rs` → `12`。按 `Contributor` 关键词 grep 只会得到 12，这是最常见的对不上账原因。
>
> 本节改用 [`crate_map.md`](./crate_map.md) §3.8 已经采用的正确口径 **"12 + 1"**。下表的 13 个行号本身全部准确，只是标题的措辞错了。

`codex-rs/ext/extension-api/src/contributors.rs` 定义了扩展可以"贡献"的绝大部分切入点（前 12 行），第 13 行来自 `user_instructions.rs`：

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
| **`UserInstructionsProvider`** | **`user_instructions.rs:38`**（不在 `contributors.rs`，也不叫 `*Contributor`） | 用户指令加载 |

**所有 trait 都要求 `Send + Sync`**，说明扩展在多线程运行时环境中被调用。

### 注册机制

```rust
// lib.rs:76-78
pub use registry::ExtensionRegistry;
pub use registry::ExtensionRegistryBuilder;
pub use registry::empty_extension_registry;
```

`ExtensionRegistryBuilder` 在 `codex-rs/core/src/thread_manager_tests.rs:535,704` 等测试里有最小用例；**生产装配点见 §3.1**。注册表建好后作为 `Arc<ExtensionRegistry<Config>>` 传给 `ThreadManager::new`（可在 `thread-manager-sample/src/main.rs:137-152` 看到完整流程），说明**扩展的生命周期与 thread 绑定**。

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

## 3. `ext/` 下的 12 个 crate（E1：目录清单与行数；依赖列为 E2）

> [!NOTE]
> **口径修订**：初版标题写「12 个内建扩展」。准确说是 **`ext/` 下 12 个 crate**——其中 `extension-api` 是扩展点本身、`items` 是纯类型 crate，**真正的"内建扩展"是 11 个（`items` 若不计则更少）**。行数为目录统计，属 **E1**（初版标 E4 属于评级过高，已下调）。

| crate | 目录 | 行数 | 依赖 `extension-api` | 在 core 的**生产**依赖中 |
| ---- | ---- | ---: | :--: | :--: |
| `codex-skills-extension` | `ext/skills` | 11,114 | ✅ | ❌（仅 `[dev-dependencies]:144`） |
| `codex-goal-extension` | `ext/goal` | 4,384 | ✅ | ❌ |
| `codex-memories-extension` | `ext/memories` | 2,399 | ✅ | ❌ |
| `codex-extension-api` | `ext/extension-api` | 2,377 | —（自身） | ✅（`core/Cargo.toml:39`） |
| `codex-mcp-extension` | `ext/mcp` | 1,504 | ✅ | ❌ |
| `codex-image-generation-extension` | `ext/image-generation` | 1,166 | ✅ | ❌（仅 `[dev-dependencies]:141`） |
| `codex-web-search-extension` | `ext/web-search` | 874 | ✅ | ❌（仅 `[dev-dependencies]:147`） |
| `codex-git-attribution` | `ext/git-attribution` | 439 | ✅ | ❌ |
| `codex-extension-items` | `ext/items` | 271 | ❌ | ✅（`:40`） |
| `codex-agent-extension` | `ext/agent` | 161 | ❌ | ❌ |
| `codex-guardian` | `ext/guardian` | 77 | ✅ | ❌ |
| `codex-connectors-extension` | `ext/connectors` | 71 | ❌ | ❌ |

> [!CAUTION]
> **修订说明（原文错误）**：初版写「**`codex-core` 只直接依赖 5 个 ext crate**（skills / image-generation / web-search / extension-api / items），其余 7 个由别处装配」，并引用了 `core/Cargo.toml:141/144/147`。
>
> **那三行全部位于 `[dev-dependencies]` 段内。** 用 `grep -n "^\[" codex-rs/core/Cargo.toml` 可见：`[dependencies]` 是 `:18`，`[dev-dependencies]` 从 **`:137`** 开始。
>
> 正确结论：**`codex-core` 的生产依赖里只有 `codex-extension-api`(`:39`) 与 `codex-extension-items`(`:40`) 两个 ext crate，而这两个都不是具体扩展。11 个具体扩展一个也不由 core 装配，全部在更高层装配。**

### 3.1 装配点在哪（E3）

> [!IMPORTANT]
> **修订说明**：初版把这一条标为 E1 未验证，并建议去 `cli`、`app-server`、`tui` 搜 `ExtensionRegistryBuilder`（其中 `tui` 是错的方向，见 §4.2）。装配点是明确的，如下。

**主装配点：`codex-rs/app-server/src/extensions.rs:51-117` 的 `fn thread_extensions()`**

它用 `ExtensionRegistryBuilder::<Config>::with_event_sink(...)` 起手，然后依次安装 8 个扩展：

| 安装调用 | 备注 |
| ---- | ---- |
| `codex_goal_extension::install_with_backend(...)` | 需要 `state_db`；受 `Feature::Goals` 门控 |
| `codex_git_attribution::install(...)` | — |
| `codex_guardian::install(&mut builder, guardian_agent_spawner)` | 传入 `AgentSpawner` |
| `codex_memories_extension::install(...)` | — |
| `codex_mcp_extension::install(...)` + `install_executor_plugins(...)` | **第二个调用把插件机制接进 MCP 扩展** |
| `codex_web_search_extension::install(...)` | — |
| `codex_image_generation_extension::install(...)` | — |
| `codex_skills_extension::install_with_providers_and_metrics(...)` | 组装 executor / orchestrator / host 三种 `SkillProvider` |

**其他装配点**：

| 位置 | 装了什么 |
| ---- | ---- |
| `codex-rs/cli/src/main.rs:2057,2063` | `codex_git_attribution::install`、`codex_skills_extension::install` |
| `codex-rs/mcp-server/src/message_processor.rs:69` 起 | `ExtensionRegistryBuilder::with_event_sink` + `git_attribution`、`image_generation` 等 |
| `codex-rs/thread-manager-sample/src/main.rs:137` | 最小示例：只装 image-generation，随后传给 `ThreadManager::new` |

> `codex-agent-extension` 与 `codex-connectors-extension` **不走 `ExtensionRegistry`**：前者被 `app-server/src/request_processors/turn_processor.rs` 当作普通库调用，后者被 `ext/mcp` 作为插件 provider 依赖。这再次印证 §1.2 的判断。

---

## 4. 插件路径（并行机制）

### 4.1 模块版图（**E1**：`core-plugins/src/lib.rs` 的模块声明清单，职责列按模块名推断；初版标 E4 已下调）

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

### 4.2 依赖插件运行时的 crate（E2，`grep -rl "codex-core-plugins" --include=Cargo.toml`）

`core`、`tui`、`cli`、`app-server`、`external-agent-migration`、`ext/connectors`、`ext/mcp`

> [!CAUTION]
> **修订说明（原文错误）**：初版写「`ext/connectors` 与 `ext/mcp` **同时依赖 extension-api 和 core-plugins**……这是唯一的交叉点」。
>
> **`ext/connectors` 并不依赖 `extension-api`**（它的 `[dependencies]` 只有 `codex-connectors`、`codex-core-plugins`、`codex-plugin`、`codex-utils-path-uri` 加三个第三方 crate）。**同时持有两套机制的只有 `ext/mcp` 一个。**

修正后的分类：

| crate | `extension-api` | `core-plugins` | 含义 |
| ---- | :--: | :--: | ---- |
| `ext/mcp` | ✅ | ✅ | **唯一的真正交叉点**——`extensions.rs` 里 `codex_mcp_extension::install_executor_plugins(...)` 就是这条合流的落地 |
| `ext/connectors` | ❌ | ✅ | **纯插件侧**：`ExecutorPluginConnectorProvider`，被 `ext/mcp` 依赖 |

### 4.3 对比：谁依赖 `extension-api`（E2）

`grep -rl "codex-extension-api" codex-rs --include=Cargo.toml`，剔除工作区根 `Cargo.toml` 与 `ext/extension-api` 自身后：

`core`、`core-api`、`codex-home`、`cli`、`app-server`、`mcp-server`、`core/tests/common`，加上 §1.1 表中的 8 个 `ext/*`。

> [!CAUTION]
> **修订说明（原文错误）**：初版在 §3 与 §9 写「`cli`、`app-server`、`tui` 都依赖 `extension-api`」。**`tui` 不依赖**——`grep -n extension codex-rs/tui/Cargo.toml` 无任何输出。在 `tui` 里找扩展装配点是白费力气。

### 4.4 用户入口

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

### 6.1 四个 crate 的分工（E2 依赖关系 + **E1** 行数统计；初版的 E4 已下调）

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-rmcp-client` | 19,361 | MCP 客户端底层实现 |
| `codex-mcp` | 14,560 | MCP 集成层，含 `connection_manager.rs`（另有 `connection_manager/` 目录与 `connection_manager_tests.rs`） |
| `codex-mcp-extension`（`ext/mcp`） | 1,504 | **扩展包装层**，实现 `McpServerContributor`；**依赖 `codex-core`，位于 core 之上** |
| `codex-mcp-server` | 4,128 | **把 Codex 自身暴露为 MCP server** |

**两个方向不要混淆**：

| 方向 | crate | 用户入口 |
| ---- | ---- | ---- |
| Codex **作为客户端**连接外部 MCP server | `rmcp-client`、`codex-mcp`、`ext/mcp` | `codex mcp` |
| Codex **作为服务端**被别的客户端连接 | `mcp-server` | `codex mcp-server`（stdio） |

### 6.2 强制约定（含一处上游笔误）

> [!IMPORTANT]
> AGENTS.md「顶部规则列表」（关键词 `mcp_connection_manager`）：处理 MCP 工具调用与工具变更时，**优先复用 `codex-mcp` 的连接管理器**，复用既有抽象，尽量缩小改动面，不要把逻辑层层透传。

> [!CAUTION]
> **修订说明（路径不存在）**：初版照抄了 AGENTS.md 里的路径 `codex-rs/codex-mcp/src/mcp_connection_manager.rs`，并把它列为"建议入口"。
>
> **这个文件在仓库里不存在。** 真实文件是：
>
> - `codex-rs/codex-mcp/src/connection_manager.rs`
> - `codex-rs/codex-mcp/src/connection_manager/`（子模块目录）
> - `codex-rs/codex-mcp/src/connection_manager_tests.rs`
>
> **这处笔误来自 `AGENTS.md` 本身**（大概是文件重命名后规则文本没跟着改）。规则的**意图**依然有效，只是路径要按上面的真实文件名理解；**不要把这条陈旧路径当作可以直接打开的入口**。

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
| MCP 工具调用优先走 `codex-mcp/src/connection_manager.rs`（注意 AGENTS.md 里的路径已过时，见 §6.2） | AGENTS.md 顶部规则列表，关键词 `mcp_connection_manager` |
| 尽量复用既有抽象，不要多层透传 | 同上 |
| 新扩展应实现 `extension-api` 的 trait，而不是直接改 `codex-core` | 见 [`crate_map.md`](./crate_map.md) §6 |
| **新扩展的注册要加到 `app-server/src/extensions.rs` 的 `thread_extensions()`**，而不是往 `core/Cargo.toml` 里加依赖 | §3.1 |
| 扩展 trait 都要求 `Send + Sync` | `contributors.rs` |
| trait 中的异步方法用 `impl Future + Send`，不要 `#[allow(async_fn_in_trait)]` | `AGENTS.md` 顶部规则列表，关键词 `async_fn_in_trait` / RPITIT |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| ~~7 个未被 core 直接依赖的 ext 在哪装配~~ | **已在 §3.1 解决**（前提也是错的：不是 7 个而是 11 个全部） | — |
| 各 Contributor trait 的方法签名与调用时机 | E1（仅知 trait 名） | `ext/extension-api/src/contributors.rs` |
| 8 个装配调用各自的门控条件（哪些受 feature / 配置控制） | E1 | `app-server/src/extensions.rs:51-117` |
| 插件清单（manifest）的格式 | E1 | `core-plugins/src/manifest.rs` |
| 插件市场的远程协议 | E1 | `core-plugins/src/remote*.rs` |
| Skill 注入模型上下文的具体形式 | E1 | `core-skills/src/injection.rs` |
| MCP 连接的握手与工具发现流程 | E1 | `codex-mcp/src/connection_manager.rs` 与 `connection_manager/` |
| `ext/mcp` 里 `install_executor_plugins` 把插件接进 MCP 的具体语义 | E1 | `ext/mcp/src/lib.rs`、`ext/connectors/src/executor_plugin.rs` |
| `codex-connectors`（4,851 行）与 `ext/connectors`（71 行）的分工 | E1 | 两者的 `Cargo.toml` 与 `lib.rs` |
| `ext/agent` 派生子智能体时的隔离边界 | E1 | `ext/agent/src/lib.rs`、`app-server/src/request_processors/turn_processor.rs` |

---

## 10. 相关文档

- [Crate 地图](./crate_map.md) §3.8 — 扩展相关 19 个 crate 清单
- [智能体核心循环](./core_agent_loop.md) §4 — 工具调用链路
- [配置体系](./config_system.md) — MCP 与插件的配置入口
- [app-server 协议](./app_server_protocol.md) — `plugin/*`、`mcpServer/*` 方法
- [实验性表面](./experimental_surfaces.md) — 其他能力面
