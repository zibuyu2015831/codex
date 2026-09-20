---
title: Codex MCP 与扩展体系
summary: 通过代码级核查确定扩展、插件、Skills、MCP 与 hooks 各路径的真实关系，说明 extension-api 的 16 个扩展点 trait 构成主扩展点、ext/* 下 15 个 crate 中有 11 个实现它、其中 10 个被装配层注册；给出 MCP 客户端侧三层 crate 分工与从 contributor 收集到统一工具注册表的完整链路、Skills 路径在第 6 轮的层级反转（ext/skills 同时被 core 生产依赖又被 registry 装配）、插件与其余三条路径的深度耦合，以及 hooks 的 11 种用户可配置事件。第 6 轮上游同步：Codex 作为 MCP 服务端的整个方向已被上游删除，core-skills crate 已删除。
keywords: codex | mcp | extensions | plugins | skills | hooks | extension-api | contributor | thread_extensions | elicitation | round6
scope: codex-rs/ext、core-plugins、codex-mcp、hooks 与 MCP 客户端相关 crate 的扩展体系
related_files: codex-rs/ext/extension-api/src/lib.rs | codex-rs/ext/extension-api/src/contributors.rs | codex-rs/ext/extension-api/src/capabilities/mod.rs | codex-rs/app-server/src/extensions.rs | codex-rs/core/src/mcp.rs | codex-rs/codex-mcp/src/runtime.rs | codex-rs/codex-mcp/src/connection_manager.rs | codex-rs/codex-mcp/src/elicitation.rs | codex-rs/ext/mcp/src/plugin_contributor.rs | codex-rs/ext/skills/src/loader/mod.rs | codex-rs/hooks/src/schema.rs | codex-rs/core/Cargo.toml | AGENTS.md
dependencies: dev_docs/crate_map.md | dev_docs/core_agent_loop.md | dev_docs/_analysis/upstream_sync_round6.md
verified_at: 2026-09-21
---

# MCP 与扩展体系

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **证据等级**: 路径关系、装配点、MCP 链路为 E3（源码与调用链）；crate 清单与行数为 E1；依赖关系为 E2

> [!CAUTION]
> **第 6 轮：本篇是全体系受损最重的一篇，核验轨判定 81 条原子断言中 47 条 WRONG（58%），另有 10 条「叙事对象已不存在、无从判对错」。** 若你读过旧版，以下五条请优先重读：
>
> | # | 旧版怎么说 | 现在的事实 |
> | ---: | ---- | ---- |
> | 1 | 四条路径之一是「MCP」，含 Codex 作为服务端与客户端**两个方向** | **服务端方向被整体删除**。`codex-rs/mcp-server` crate、`codex mcp-server` 子命令、`codex_tool_runner` / `codex_tool_config` / `CodexToolCallParam` 全部不存在 |
> | 2 | 「Skills 被包装成扩展」，`ext/skills` 包装 core 之下的 `core-skills` 运行时 | **层级反转了**。`core-skills` crate 已删除；`ext/skills` 既被 registry 装配，**又被 `codex-core` 当普通库生产依赖** |
> | 3 | 「core 的生产依赖里没有任何一个被注册进 `ExtensionRegistry` 的扩展」 | **已被证伪**。`codex-rs/core/Cargo.toml:68` 的 `codex-skills-extension` 就是 |
> | 4 | 插件是「大体并行、个别处合流」的第二条赛道 | **合流是常态**。`core-plugins` 在 crate 层面同时依赖 `codex-mcp` / `codex-skills` / `codex-hooks` |
> | 5 | `extension-api` 是纯粹的扩展点、不碰具体机制 | **松动了**。它的 `[dependencies]` 现含 `codex-mcp`（`codex-rs/ext/extension-api/Cargo.toml:22`） |
>
> **标题口径也随之改了**：旧版叫「四条扩展路径」，但 Skills 已不再是独立一条。现在更准确的说法是**三条 crate 作者侧路径（扩展 / 插件 / MCP 客户端）+ 一条用户配置路径（hooks）**。

> [!NOTE]
> **更早几轮的修订史**（保留备查）：初版曾称「12 个 `ext/*` 全部依赖 extension-api」（实为 8/11）、把 `codex-rs/core/Cargo.toml` 的 dev 依赖当成生产依赖、声称装配点未知。这些在第 5 轮已更正；第 6 轮的数字与结论在此基础上再次全面刷新。

## 1. 核心结论：一个主扩展点，但边界比旧版描述的松得多

### 1.1 依赖关系实测（E2，逐个 `Cargo.toml` 的 `[dependencies]` 段核对）<!-- ref-exempt: 泛指各 crate 的清单文件，不指某一个 -->

`ext/` 下共 **15 个**目录，其中 `ext/extension-api` 是扩展点本身，**具体扩展是 14 个**，其中 **11 个**实现 `codex-extension-api`。

```bash
ls -1 codex-rs/ext | wc -l                                                      # 15
grep -l "codex-extension-api" codex-rs/ext/*/Cargo.toml | grep -v "ext/extension-api/" | wc -l   # 11
```

| `ext/*` | 依赖 `codex-extension-api` | 备注 |
| ---- | :--: | ---- |
| `git-attribution` / `goal` / `guardian-v2` / `guardian-reviewer` / `history-notes` / `image-generation` / `mcp` / `memories` / `queue` / `skills` / `web-search` | ✅（11 个） | 常规扩展。**第 6 轮新增 4 个**：`guardian-v2`、`guardian-reviewer`、`history-notes`、`queue`（前两个由原单体 `ext/guardian` 拆分而来） |
| `items` | ❌ | 纯数据 / schema crate，`[dependencies]` 里 workspace 内只有 `codex-utils-absolute-path` |
| `agent` | ❌ | 只依赖 `codex-core`、`codex-protocol`；持有 `Weak<ThreadManager>`（`codex-rs/ext/agent/src/lib.rs:35`） |
| `connectors` | ❌ | **第 6 轮改名换职责**：模块文档现为 *"Plugin app declaration loading."*（`codex-rs/ext/connectors/src/lib.rs:1`），导出 `PluginAppProvider` / `PluginAppProviderError`，不再是旧版记录的 `ExecutorPluginConnectorProvider` |

> [!IMPORTANT]
> **「实现 extension-api」不等于「被注册进 `ExtensionRegistry`」——第 6 轮这两个集合首次出现差异。**
>
> 11 个实现者里有 **10 个**被装配层注册，唯一的例外是 **`guardian-reviewer`**：它依赖 `extension-api`，但不出现在任何装配点，而是被 `codex-core` 当**普通库**用（`codex-rs/core/Cargo.toml:51`）。
>
> 穷举命令：
>
> ```bash
> # 不含 ExtensionRegistryBuilder 的 ext crate（即不自我注册的）
> for d in codex-rs/ext/*/; do grep -rqs "ExtensionRegistryBuilder" "$d/src" || echo "$(basename $d)"; done
> # → agent connectors guardian-reviewer items
> ```

其余实测结论（第 6 轮刷新）：

| 事实 | 证据 |
| ---- | ---- |
| `ext/skills` **不再依赖任何 `core-skills`**（该 crate 已删除），现依赖 `codex-skills` 与 `codex-mcp` | `codex-rs/ext/skills/Cargo.toml` |
| `ext/mcp` 依赖 `codex-mcp`，**也依赖 `codex-core`** | `codex-rs/ext/mcp/Cargo.toml` |
| `core-plugins` 依赖 `codex-plugin`(`:29`)、`codex-mcp`(`:26`)、`codex-skills`(`:31`)、`codex-hooks`(`:23`)，**不依赖 `codex-extension-api`** | `codex-rs/core-plugins/Cargo.toml` |
| **`extension-api` 自身依赖 `codex-mcp`** | `codex-rs/ext/extension-api/Cargo.toml:22`，并在 `codex-rs/ext/extension-api/src/lib.rs:20-21` 再导出 `McpProtocolMode` / `ToolInfo as McpToolInfo` |

> [!CAUTION]
> **旧版的一条核心结论已被证伪：「`codex-core` 的生产依赖里没有任何一个被注册进 `ExtensionRegistry` 的扩展」。**
>
> ```
> codex-rs/core/Cargo.toml:51:codex-guardian-reviewer = { workspace = true }
> codex-rs/core/Cargo.toml:68:codex-skills-extension = { workspace = true }
> ```
>
> 两行都落在 `[dependencies]` 段内（`[dev-dependencies]` 从 `:140` 才开始）。其中 **`codex-skills-extension` 同时是被注册的扩展**（`codex-rs/app-server/src/extensions.rs:109`）**和 core 的生产库依赖**——core 直接用它的 `HostSkillsService`，不经过任何 contributor 契约。
>
> `grep -rn 'codex_skills_extension' codex-rs/core/src --include='*.rs' | grep -v _tests` 命中 **13 处**，横跨 `codex-rs/core/src/thread_manager.rs`、`codex-rs/core/src/session/mod.rs`、`codex-rs/core/src/session/turn.rs`、`codex-rs/core/src/state/service.rs`、`codex-rs/core/src/plugins/mod.rs`、`codex-rs/core/src/skills.rs` 等。
>
> **这是整个 `ext/` 目录里唯一被 core 反向依赖的「注册型」扩展**，详见 §5 的层级反转说明。

### 1.2 四个"例外" crate 各自是什么（E3）

> **第 6 轮：例外从三个增至四个**（新增 `guardian-reviewer`，见上方 IMPORTANT）。

### 1.3 由此确定的关系

```
     ┌─────────────────────────────────────────────────────┐
     │  codex-extension-api  ── 主扩展点                    │
     │  16 个扩展点 trait（12 个 *Contributor + 1）         │
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
        ↑ 进入 ExtensionRegistry 的是 8 个具体扩展，全部在这一层注册；
          core 的生产依赖里没有任何一个被注册的扩展
          （但 ext/items 是 core 的生产依赖——它不是扩展，是纯类型 crate）
```

**三句话总结（已修订）**：

1. **`ext/extension-api` 是主扩展点**，但**不是所有 `ext/*` 都构建在它之上**——11 个具体扩展里 8 个是，`items`/`agent`/`connectors` 三个不是。
2. **Skills 与 MCP 不是独立路径，而是被包装成扩展**——`ext/skills` 包装 `core-skills`+`skills`，`ext/mcp` 包装 `codex-mcp`；注意 **`ext/mcp` 依赖 `codex-core`，位于 core 之上**，不是 core 的下游。
3. **插件（plugins）大体是并行机制**——`core-plugins` 不依赖 `extension-api`、由 `codex-core` 直接对接；但 **`ext/connectors` 与 `ext/mcp` 说明两条轨道会在扩展内部合流**。

> 所以此前"四条并行路径"的说法**不准确**。准确的说法是：**一个主扩展点（覆盖多数 ext + skills + MCP）+ 一个大体并行、但在个别扩展里合流的插件机制**，另加若干不属于任何一条的支撑 crate。
>
> **另有第五条、面向用户而非 crate 作者的路径：`codex-hooks`**（11 种生命周期钩子事件，`codex-core` 的生产依赖）。它不经过 `extension-api`，见 **§7**。

---

## 2. extension-api：16 个扩展点 trait = 12 个 `*Contributor` + 4（E3）

> **第 6 轮：从 13 个增至 16 个。** 旧版记的 13 = 12 + 1，漏掉了 3 个同样不以 `Contributor` 结尾的 trait。复算：
>
> ```bash
> grep -rh "^pub trait " codex-rs/ext/extension-api/src/ | wc -l              # 20
> grep -rh "^pub trait " codex-rs/ext/extension-api/src/capabilities/ | wc -l  # 4（能力 trait，不计入扩展点）
> # 20 - 4 = 16
> ```
>
> 4 个不以 `Contributor` 结尾的扩展点：`UserInstructionsProvider`（`codex-rs/ext/extension-api/src/user_instructions.rs:67`）、`ThreadInstructionsProvider`（同文件 `:44`）、`SynchronousApprovalReviewer`（`codex-rs/ext/extension-api/src/contributors/approval_review.rs:24`）、`TurnStartAdmission`（`codex-rs/ext/extension-api/src/turn_admission.rs:10`）。**按 `Contributor` 关键词 grep 只会得到 12**，这是反复对不上账的原因。

> [!NOTE]
> **勘误：不要写成"13 个 Contributor trait"。** 上一稿全文（含摘要与 §1.3 的示意图）都用了这个说法，但 `codex-rs/ext/extension-api/src/contributors.rs` 里以 `Contributor` 结尾的 trait 只有 **12** 个；第 13 个是 `UserInstructionsProvider`，定义在**另一个文件** `codex-rs/ext/extension-api/src/user_instructions.rs:38`（注意仓库里还有一个同名文件 `codex-rs/core/src/context/user_instructions.rs`，不要混淆），**名字里没有 "Contributor"**。
>
> 复核：`grep -cE "pub trait [A-Za-z]*Contributor" codex-rs/ext/extension-api/src/contributors.rs` → `12`。按 `Contributor` 关键词 grep 只会得到 12，这是最常见的对不上账原因。
>
> 本节改用 [`crate_map.md`](./crate_map.md) §3.8 已经采用的正确口径 **"12 + 1"**。下表的 13 个行号本身全部准确，只是标题的措辞错了。

`codex-rs/ext/extension-api/src/contributors.rs` 定义了扩展可以"贡献"的绝大部分切入点（前 12 行），第 13 行来自 `codex-rs/ext/extension-api/src/user_instructions.rs`：

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
| **`UserInstructionsProvider`** | **`codex-rs/ext/extension-api/src/user_instructions.rs:38`**（不在 `codex-rs/ext/extension-api/src/contributors.rs`，也不叫 `*Contributor`） | 用户指令加载 |

**所有 trait 都要求 `Send + Sync`**，说明扩展在多线程运行时环境中被调用。

### 注册机制

```rust
// codex-rs/ext/extension-api/src/lib.rs:76-78
pub use registry::ExtensionRegistry;
pub use registry::ExtensionRegistryBuilder;
pub use registry::empty_extension_registry;
```

**注册是显式调用式的，不是 inventory / 链接期自动注册。** 每个扩展都要由装配层显式调一次 `builder.<xxx>_contributor(Arc::new(...))`——例如 `codex-rs/ext/mcp/src/lib.rs:43` 与 `:51` 各有一次 `builder.mcp_server_contributor(...)`。**这正是"类型存在 ≠ 扩展生效"的分界**：一个实现了 trait 的 crate，只要没人在装配层调它的 `install`，它就完全不参与运行时。

`ExtensionRegistryBuilder` 在 `codex-rs/core/src/thread_manager_tests.rs:535,704` 等测试里有最小用例；**生产装配点见 §3.1**。注册表建好后作为 `Arc<ExtensionRegistry<Config>>` 传给 `ThreadManager::new`（可在 `codex-rs/thread-manager-sample/src/main.rs:137-152` 看到完整流程），说明**扩展的生命周期与 thread 绑定**。

### 能力接口（`codex-rs/ext/extension-api/src/capabilities/`）

> [!IMPORTANT]
> **这不是一个 `capabilities.rs` 文件，而是一个目录**，含 `mod.rs`、`codex-rs/ext/extension-api/src/capabilities/agent.rs`、`events.rs`、`metrics.rs`、`codex-rs/ext/extension-api/src/capabilities/response_items.rs` 五个文件（全路径见下表；`codex-rs/ext/extension-api/src/lib.rs:1` 是 `mod capabilities;`）。<!-- ref-exempt: 此处列的是目录内的裸文件名，全路径在紧随的表格中给出 -->
>
> **更要紧的区分：这 4 个 capability trait 的方向与 §2 开头那 16 个扩展点 trait 相反。** capability 由**宿主实现、注入给扩展使用**；16 个扩展点 trait 则由**扩展实现、由宿主调用**。

| 类型 | 定义位置 | 用途 |
| ---- | ---- | ---- |
| ~~`AgentSpawner` / `AgentSpawnFuture`~~ | **第 6 轮删除**：`capabilities/agent.rs` 整个文件已不存在<!-- ref-exempt: 反例——正文说明该路径已不存在 --> | 取而代之的是 `ConversationHistorySnapshot`（`codex-rs/ext/extension-api/src/capabilities/conversation_history.rs`）。**能力 trait 仍是 4 个，但成员换了一个**——只对数字的检查抓不到这类变化 |
| `ExtensionEventSink` / `NoopExtensionEventSink` | `codex-rs/ext/extension-api/src/capabilities/events.rs:19` | 事件下沉 |
| `ResponseItemInjector` / `NoopResponseItemInjector` | `codex-rs/ext/extension-api/src/capabilities/response_items.rs:15` | **向模型响应流注入条目** |
| `ExtensionMetrics` | `codex-rs/ext/extension-api/src/capabilities/metrics.rs:5` | 指标 |
| `ExtensionWarning` | `codex-rs/ext/extension-api/src/capabilities/mod.rs` | 警告 |

> `Noop*` 变体的存在说明这些能力是**可选注入**的——测试或轻量场景可以传空实现。

### 复用的核心类型

`extension-api` 大量 re-export **三个** crate 的类型，不是两个（`codex-rs/ext/extension-api/src/lib.rs:16-35`）：

| 来源 crate | 行号 | re-export 的类型 |
| ---- | ---- | ---- |
| `codex-context-fragments` | `:16` | `ContextualUserFragment` |
| `codex-protocol` | `:17` | `ResponseItem`（`codex_protocol::models::ResponseItem`） |
| `codex-tools` | `:18`–`:35` | `ToolCall`、`ToolSpec`、`ToolExecutor`、`ToolOutput`、`ResponsesApiTool`、`ConversationHistory`、`FunctionCallError` 等 18 条 |

> **含义**：扩展作者只需依赖 `codex-extension-api` 一个 crate，就能拿到全套工具类型，不必直接依赖 `codex-tools` 或 `codex-protocol`。这是有意设计的**收敛入口**。

---

## 3. `ext/` 下的 15 个 crate（E1：目录清单与行数；依赖列为 E2）

> **第 6 轮行数全面刷新**（旧值 → 新值）：`ext/skills` 11,114 → **22,219**；`ext/goal` 4,384 → **5,725**；`ext/memories` 2,399 → **2,585**；`ext/extension-api` 2,377 → **2,912**；`ext/mcp` 1,504 → **3,843**；`ext/image-generation` 1,166 → **1,446**；`ext/web-search` 874 → **885**；`ext/git-attribution` 439 → **441**；`ext/items` 271 → **380**；`ext/agent` 161 → **170**；`ext/connectors` 71 → **74**。原 `ext/guardian`（77 行）已拆成 `ext/guardian-v2`（**11,545**）+ `ext/guardian-reviewer`（**3,102**）；另新增 `ext/history-notes`（**1,529**）与 `ext/queue`（**1,689**）。

> [!NOTE]
> **口径修订**：初版标题写「12 个内建扩展」。准确说是 **`ext/` 下 12 个 crate**——其中 `extension-api` 是扩展点本身、`items` 是纯类型 crate，**真正的"内建扩展"是 11 个（`items` 若不计则更少）**。行数为目录统计，属 **E1**（初版标 E4 属于评级过高，已下调）。

| crate | 目录 | 行数 | 依赖 `extension-api` | 在 core 的**生产**依赖中 |
| ---- | ---- | ---: | :--: | :--: |
| `codex-skills-extension` | `ext/skills` | 11,114 | ✅ | ❌（仅 `[dev-dependencies]:144`） |
| `codex-goal-extension` | `ext/goal` | 4,384 | ✅ | ❌ |
| `codex-memories-extension` | `ext/memories` | 2,399 | ✅ | ❌ |
| `codex-extension-api` | `ext/extension-api` | 2,377 | —（自身） | ✅（`codex-rs/core/Cargo.toml:39`） |
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
> **那三行全部位于 `[dev-dependencies]` 段内。** 用 `grep -n "^\[" codex-rs/core/Cargo.toml` 可见：`[dependencies]` 是 `:18`–`:126`，`[dev-dependencies]` 从 **`:137`** 开始。
>
> 正确结论：**`codex-core` 的生产依赖里只有 `codex-extension-api`(`:39`) 与 `codex-extension-items`(`:40`) 两个 `ext/*` crate，而这两个都不是具体扩展。**
>
> **不要写成"core 生产依赖里一个 ext crate 都没有"**——上表就写着 `codex-extension-items` 在 `:40`，两处会自相矛盾。准确表述是：**core 的生产依赖里没有任何一个被注册进 `ExtensionRegistry` 的扩展**；被注册的扩展共 **8 个**，全部在更高层装配（见 §3.1）。

### 3.1 装配点在哪（E3）

> [!IMPORTANT]
> **修订说明**：初版把这一条标为 E1 未验证，并建议去 `cli`、`app-server`、`tui` 搜 `ExtensionRegistryBuilder`（其中 `tui` 是错的方向，见 §4.2）。装配点是明确的，如下。

**主装配点：`codex-rs/app-server/src/extensions.rs:51-117` 的 `fn thread_extensions()`**

它用 `ExtensionRegistryBuilder::<Config>::with_event_sink(...)` 起手（`codex-rs/app-server/src/extensions.rs:72`），然后依次安装 8 个扩展（`:71-115`）：

| 安装调用 | 门控条件（E3，直接读代码） |
| ---- | ---- |
| `codex_goal_extension::install_with_backend(...)` | **双重门控**：`state_db.is_some()` 才进入分支，且传入 `\|config\| config.features.enabled(Feature::Goals)`（`codex-rs/app-server/src/extensions.rs:72-80`） |
| `codex_git_attribution::install(...)` | 无门控 |
| `codex_guardian::install(&mut builder, guardian_agent_spawner)` | 无门控；传入 `AgentSpawner` |
| `codex_memories_extension::install(...)` | 无门控 |
| `codex_mcp_extension::install(...)` + `install_executor_plugins(...)` | 无门控；**第二个调用把插件机制接进 MCP 扩展** |
| `codex_web_search_extension::install(...)` | 无门控 |
| `codex_image_generation_extension::install(...)` | 无门控 |
| `codex_skills_extension::install_with_providers_and_metrics(...)` | **4 个开关**：`include_skill_instructions` / `bundled_skills_enabled()` / `orchestrator_skills_enabled` / `Feature::SkillSearch`（`codex-rs/app-server/src/extensions.rs:103-113`）；`SkillProviders` 装齐 executor / orchestrator / host 三种 |

**其他装配点**：

| 位置 | 装了什么 |
| ---- | ---- |
| `codex-rs/cli/src/main.rs:2057,2063` | **共 2 个**：`codex_git_attribution::install`、`codex_skills_extension::install`；且用 `ExtensionRegistryBuilder::new()` 而非 `with_event_sink`（`codex-rs/cli/src/main.rs:2056`）——`new()` 走 `Default`，事件下沉是 `NoopExtensionEventSink`（`codex-rs/ext/extension-api/src/registry.rs:38-41,60-62`），**cli 装的扩展发不出扩展事件** |<!-- ref-exempt: with_event_sink 在此是被否定的对象，正文说的正是 cli 没有用它 --><!-- ref-exempt: with_event_sink 在此是被否定的对象，正文说的正是 cli 没有用它 -->
| ~~`codex-rs/mcp-server/src/message_processor.rs`~~ | **第 6 轮删除**：该 crate 已被上游整体移除<!-- ref-exempt: 反例——正文说明该路径已不存在 -->，这条装配点随之消失。剩余装配点见本表其余行。原内容（供对照）：曾装 3 个扩展 —— git-attribution / image-generation / skillsiders_and_metrics`(`:85`)。注意这里 `SkillProviders::new().with_host_provider(...)` **只装 host provider**，比 app-server 少 executor / orchestrator 两种 |
| `codex-rs/thread-manager-sample/src/main.rs:137` | 最小示例：只装 image-generation，随后传给 `ThreadManager::new` |

> **三处装配点的并集恰好是 8 个具体扩展**：goal / git-attribution / guardian / memories / mcp / web-search / image-generation / skills。`ext/` 下另外 3 个 crate（`items` / `agent` / `connectors`）**根本不进 `ExtensionRegistry`**——所以「11 个具体扩展全部在装配层注册」是错的，正确数字是 **8**。

> `codex-agent-extension` 与 `codex-connectors-extension` **不走 `ExtensionRegistry`**：前者被 `codex-rs/app-server/src/request_processors/turn_processor.rs` 当作普通库调用，后者被 `ext/mcp` 作为插件 provider 依赖。这再次印证 §1.2 的判断。<!-- ref-exempt: ExtensionRegistry 在此是被否定的对象，不应期望出现在 turn_processor.rs 中 -->

### 3.2 `thread_extensions()` 的调用侧（E3）

注册表不是进程级单例，而是**每次需要时重新构建**。全仓只有两处调用：

| 调用点 | 时机与含义 |
| ---- | ---- |
| `codex-rs/app-server/src/message_processor.rs:266` | 常规路径：处理消息时构建 thread 的扩展注册表 |
| `codex-rs/app-server/src/mcp_refresh.rs:329` | **MCP 配置 reload 会重建整个扩展注册表**——不只是 MCP 扩展，8 个扩展全部重装 |

> **对 §2「扩展的生命周期与 thread 绑定」的补充**：绑定 thread 只说了一半。`mcp_refresh` 这条路径说明注册表**也随 MCP 配置重载而重建**。
>
> 另注意 `codex-rs/app-server/src/mcp_refresh.rs` 与 `codex-rs/core/src/session/mcp_refresh.rs` 是**两个不同文件**，前者调 `thread_extensions`，后者是会话侧刷新（见 §6.3），极易混淆。

---

## 4. 插件路径（并行机制）

### 4.1 模块版图：`codex-rs/core-plugins/src/lib.rs` 的 13 个 `pub mod`（另有 26 个私有 mod，共 39 条声明）

> **第 6 轮**：`pub mod` 仍是 13 个（结论未变），但总声明数 27 → **39**，私有 mod 14 → **26**。复算：`grep -cE "^(pub )?mod " codex-rs/core-plugins/src/lib.rs`。

> [!NOTE]
> **证据等级 E1，且清单本身不完整——这是有意的裁剪。** `codex-rs/core-plugins/src/lib.rs:1-27` 共 **27** 条 `mod` 声明，下表只列其中 **13 条 `pub mod`**（对外 API 面）。职责列按模块名推断，故为 E1。初版把这里叫作"模块声明清单"是错的——"清单"暗示穷举，而实际漏了 14 条。
>
> 未列出的 14 个**私有** mod：`app_mcp_routing`(`:1`)、`command_migration`、`discoverable`、`http_client_selector`、`manager`、`marketplace_policy`、`npm_source`、`plugin_bundle_archive`、`provider`、`remote_plugin_id_resolver`、`script_attribution`、`test_support`（`#[cfg(test)]`）、`tool_suggest_metadata`。

| `pub mod` | 职责 |
| ---- | ---- |
| `manifest` | 插件清单 |
| `loader` | 加载 |
| `store` | 存储 |
| `toggles` | 启用/禁用开关 |
| `startup_sync` | 启动时同步 |
| `installed_marketplaces` | 已安装的市场 |
| `marketplace` / `marketplace_add` / `marketplace_remove` / `marketplace_upgrade` | 市场的增删改查 |
| `remote` / `remote_bundle` / `remote_legacy` | 远程插件（含 legacy 兼容路径） |

`codex-rs/core-plugins/src/lib.rs:35` 有一个 `pub fn is_openai_curated_marketplace_name(marketplace_name: &str) -> bool`——**存在 OpenAI 官方精选市场的概念**。

> [!IMPORTANT]
> **比 `ext/connectors` 更硬的"两条轨道已合流"证据，在 `core-plugins` 自己的清单里**：`codex-rs/core-plugins/Cargo.toml` 的 `[dependencies]` **同时包含 `codex-mcp`(`:27`) 与 `codex-skills`(`:32`)**，私有模块 `app_mcp_routing`(`codex-rs/core-plugins/src/lib.rs:1`) 也直接指向"插件 → MCP"的路由。
>
> 也就是说：**插件轨道与 MCP / Skills 在 crate 依赖层面就已经耦合**，不是只在 `ext/connectors` 这一个边角上碰头。「插件是完全平行的独立轨道」这个说法要打折扣。

### 4.2 依赖插件运行时的 crate（E2，`grep -rl "codex-core-plugins" --include=Cargo.toml`）

`core`、`tui`、`cli`、`app-server`、`external-agent-migration`、`ext/connectors`、`ext/mcp`

> [!CAUTION]
> **修订说明（原文错误）**：初版写「`ext/connectors` 与 `ext/mcp` **同时依赖 extension-api 和 core-plugins**……这是唯一的交叉点」。
>
> **`ext/connectors` 并不依赖 `extension-api`**（它的 `[dependencies]` 只有 `codex-connectors`、`codex-core-plugins`、`codex-plugin`、`codex-utils-path-uri` 加三个第三方 crate）。**在 `ext/` 内，同时持有两套机制的只有 `ext/mcp` 一个**——注意这个"唯一"限定在 `ext/` 目录内；`ext/` 之外还有 `core`、`cli`、`app-server` 三个 crate 同时依赖 `codex-extension-api` 与 `codex-core-plugins`。

修正后的分类：

| crate | `extension-api` | `core-plugins` | 含义 |
| ---- | :--: | :--: | ---- |
| `ext/mcp` | ✅ | ✅ | **在 `ext/` 内唯一的真正交叉点**——`codex-rs/app-server/src/extensions.rs` 里 `codex_mcp_extension::install_executor_plugins(...)` 就是这条合流的落地 |
| `ext/connectors` | ❌ | ✅ | **纯插件侧**：`ExecutorPluginConnectorProvider`，被 `ext/mcp` 依赖 |

**`ext/mcp` 注册的是两个不同的 contributor，别混为一谈**（E3）：

| 函数 | 注册的 contributor | 作用 |
| ---- | ---- | ---- |
| `install(...)`（`codex-rs/ext/mcp/src/lib.rs:42-44`） | `HostedPluginRuntimeExtension` | 托管插件运行时声明的 MCP server |
| `install_plugins(...)`（`codex-rs/ext/mcp/src/lib.rs:26` 导出 → `codex-rs/ext/mcp/src/plugin_contributor.rs:32`） | `PluginContributor` | **第 6 轮重构**：旧版的 `install_executor_plugins` / `executor_plugin.rs` / `SelectedExecutorPluginMcpContributor` 三者**全仓零命中**<!-- ref-exempt: 反例——正文说明这些符号已不存在 -->。现在是**一个 `PluginContributor` 对象同时占 4 个注册槽**（`codex-rs/ext/mcp/src/plugin_contributor.rs:25-28`：thread_lifecycle / config / turn_lifecycle / mcp_server）。旧版「两者都通过同一个 `builder.mcp_server_contributor(...)` 入口注册」已不成立onnectors_extension::ExecutorPluginConnectorProvider;` |

两者都通过同一个 `builder.mcp_server_contributor(...)` 入口注册（`:43`、`:51`）。

### 4.3 对比：谁依赖 `extension-api`（E2）

`grep -rl "codex-extension-api" codex-rs --include=Cargo.toml`，剔除工作区根 `Cargo.toml` 与 `ext/extension-api` 自身后：<!-- ref-exempt: 泛指 grep 参数与工作区根清单，不指某一个具体文件 -->

`core`、`core-api`、`codex-home`、`cli`、`app-server`、`mcp-server`、`core/tests/common`，加上 §1.1 表中的 8 个 `ext/*`。

> [!CAUTION]
> **修订说明（原文错误）**：初版在 §3 与"未覆盖内容"一节写「`cli`、`app-server`、`tui` 都依赖 `extension-api`」。**`tui` 不依赖**——`grep -n extension codex-rs/tui/Cargo.toml` 无任何输出。在 `tui` 里找**扩展**装配点是白费力气。
>
> **但这句话不要外溢到插件**：`tui` **确实**依赖 `codex-core-plugins`（见 §4.2 的清单）。「`tui` 与扩展体系无关」成立，「`tui` 与插件体系无关」不成立。

### 4.4 用户入口

| 入口 | 说明 |
| ---- | ---- |
| `codex plugin add / list / remove / marketplace` | CLI 子命令（`codex-rs/cli/src/main.rs:1090-1110`） |
| `plugin/*` 协议方法（12 个） | app-server 协议 |
| `request_plugin_install` / `list_available_plugins_to_install` | 模型可调用的工具 |

**模型自己可以请求安装插件**——`codex-rs/core/src/tools/handlers/request_plugin_install.rs` 与 `codex-rs/core/src/tools/handlers/list_available_plugins_to_install.rs`。这是一条值得注意的能力面。

---

## 5. Skills 路径：第 6 轮发生层级反转

> [!CAUTION]
> **旧版的骨架是「`ext/skills` 包装 core 之下的 `core-skills` 运行时」。这个方向反了。**
>
> 上游 `33e365b19e`「Remove the legacy core skill loader」删除了 `codex-rs/core-skills` crate<!-- ref-exempt: 反例——正文说明该 crate 已不存在 -->，加载器、检索器与注入全部搬进 `codex-rs/ext/skills/`。今天的层级是：
>
> ```
> codex-core  ──依赖──▶  ext/skills（codex-skills-extension）──依赖──▶  codex-skills（纯解析/模型层）
>      ▲                        │
>      └────── 同时经 ExtensionRegistry 被装配进来 ──┘
> ```
>
> **`ext/skills` 同时在 core 之下与 core 之上**：既是 `codex-rs/core/Cargo.toml:68` 的生产依赖（core 直接调它的 `HostSkillsService`，不经 contributor 契约），又在 `codex-rs/app-server/src/extensions.rs:109` 被注册进 registry。这是整个 `ext/` 目录里唯一有此双重身份的 crate，也是本轮最值得记住的结构性发现。
>
> **推论**：「Skills 是一条独立的扩展路径」这个说法应当撤回——它现在就是**扩展本体**，只是额外被 core 直接引用。

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-skills-extension`（`codex-rs/ext/skills`） | 22,219 | **Skills 的实现主体**：`loader/`（发现与装载）、`dynamic_skill_selector/`（一整套检索器，含 BM25、字符 n-gram、LRU 等）、`host_service.rs`、`host_prompt.rs`、`host_roots.rs` |
| `codex-skills`（目录 `codex-rs/skills`） | 2,594 | **纯解析 / 模型层**：`parser` / `model` / `selection` / `mentions` / `interface` / `invocation` / `loading` 七个模块的再导出（`codex-rs/skills/src/lib.rs:10-44`）。另含样例 skill 资产 |

> **crate 名 ≠ 目录名**：crate `codex-skills` 的目录是 `codex-rs/skills/`。不存在 `codex-skills/src/` 这个目录。

仓库自带的样例 skill 在 `codex-rs/skills/src/assets/samples/`，第 6 轮共 **6 个**（旧版记 3 个）：`imagegen`、`openai-docs`、`plugin-creator`、`review-agent`、`skill-creator`、`skill-installer`。

### 5.1 Skill 的发现与装载（E3，第 6 轮全部迁址）

> **旧版本节的 6 条证据全部指向已删除的 `codex-rs/core-skills/src/loader.rs`**<!-- ref-exempt: 反例——正文说明该路径已不存在 -->（本篇 18 个引用错误里有 12 个出自这里）。现按新位置重建。

扫描根的解析在 `codex-rs/ext/skills/src/host_roots.rs`，入口 `resolve_skill_roots`（`:28`）→ `resolve_skill_roots_with_home_dir`（`:48`）→ `roots_from_layer_stack`（`:73`）沿**配置层栈**逐层拼出，按 `SkillScope` 分类：

| `SkillScope` | 根目录 | 位置 |
| ---- | ---- | ---- |
| `Repo` | 项目配置目录下的 `skills/`（即 `.codex/skills`） | `codex-rs/ext/skills/src/host_roots.rs:90` |
| `User` | `$CODEX_HOME/skills` | `codex-rs/ext/skills/src/host_roots.rs:100` |
| `User` | `$HOME/.agents/skills`（用户安装的 skill） | `codex-rs/ext/skills/src/host_roots.rs:106` |
| `System` | 内置 skill 缓存 | `codex-rs/ext/skills/src/host_roots.rs:112` |
| `Admin` | 系统配置层下的 `skills/` | `codex-rs/ext/skills/src/host_roots.rs:118` |
| `Repo` | 从项目根到 cwd 之间每一级目录的 `.agents/skills` | `codex-rs/ext/skills/src/host_roots.rs:137` 的 `repo_agents_skill_roots`，分类在 `:171` |

目录名常量 `SKILLS_DIR_NAME = "skills"` 在 `codex-rs/ext/skills/src/host_roots.rs:25`；扫描上限常量 `MAX_SCAN_DEPTH` 与 `MAX_SKILLS_DIRS_PER_ROOT` 定义在 `codex-rs/ext/skills/src/loader/mod.rs`，消费点在 `codex-rs/ext/skills/src/loader/discovery.rs:70` 与 `:73`。去重在 `codex-rs/ext/skills/src/host_roots.rs:271` 的 `dedupe_skill_roots_by_path`。

> **仍未覆盖（E1）**：skill 内容注入模型上下文的**具体形式**本轮同样未读实现，与 §10 的未覆盖项口径一致。

---

## 6. MCP 路径

### 6.1 四个 crate 的分工（E2 依赖关系 + **E1** 行数统计；初版的 E4 已下调）

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-rmcp-client` | 19,361 | MCP 客户端底层实现 |
| `codex-mcp` | 14,560 | MCP 集成层，含 `codex-rs/codex-mcp/src/connection_manager.rs`（另有 `connection_manager/` 目录与 `codex-rs/codex-mcp/src/connection_manager_tests.rs`） |
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
> **修订说明（路径不存在）**：初版照抄了 AGENTS.md 里的路径 `codex-rs/codex-mcp/src/mcp_connection_manager.rs`（`AGENTS.md:35` 原文即 `prefer using codex-rs/codex-mcp/src/mcp_connection_manager.rs`），并把它列为"建议入口"。<!-- ref-exempt: 反例——正文正在声明 AGENTS.md 给的这个路径不存在 -->
>
> **这个文件在仓库里不存在。** 真实文件是：
>
> - `codex-rs/codex-mcp/src/connection_manager.rs`
> - `codex-rs/codex-mcp/src/connection_manager/`（子模块目录）
> - `codex-rs/codex-mcp/src/connection_manager_tests.rs`
>
> **这处笔误来自 `AGENTS.md` 本身**（大概是文件重命名后规则文本没跟着改）。规则的**意图**依然有效，只是路径要按上面的真实文件名理解；**不要把这条陈旧路径当作可以直接打开的入口**。

### 6.3 会话侧接入

`codex-rs/core/src/session/` 下有 5 个 MCP 相关文件：`codex-rs/core/src/session/mcp.rs`、`codex-rs/core/src/session/mcp_runtime.rs`、`codex-rs/core/src/session/mcp_prewarm.rs`（**预热**）、`codex-rs/core/src/session/mcp_refresh.rs`、`codex-rs/core/src/session/mcp_tests.rs`。

> **名为 `mcp_refresh` 的文件有两个**：`codex-rs/core/src/session/mcp_refresh.rs`（会话侧刷新）与 `codex-rs/app-server/src/mcp_refresh.rs`（app-server 侧，会调 `thread_extensions`，见 §3.2）。两者职责不同，引用时务必带全路径。

**MCP server 连接是有状态且需要维护的长连接，不是每次调用现连**（E3）。三类证据，按强度排列：

| 强度 | 证据 |
| ---- | ---- |
| **E3** | 协议侧存在 `mcpServer/startupStatus/updated` 通知（`codex-rs/app-server-protocol/src/protocol/common.rs:1737`）——有"启动状态"可播报，说明连接有独立于单次调用的生命周期 |
| E2 | 连接管理器是独立子系统：`codex-rs/codex-mcp/src/connection_manager.rs` 与 `codex-rs/codex-mcp/src/connection_manager/` 目录 |
| E2 | 会话侧同时存在预热与刷新两条通道：`codex-rs/core/src/session/mcp_prewarm.rs` + `codex-rs/core/src/session/mcp_runtime.rs` + `codex-rs/core/src/session/mcp_refresh.rs` |

（初版此处只凭文件名断言，属 E1；现已补到 E3。）

### 6.4 配置与协议

| 面 | 位置 |
| ---- | ---- |
| 配置类型 | `codex-rs/config/src/mcp_types.rs`、`codex-rs/config/src/mcp_edit.rs`、`codex-rs/config/src/mcp_requirements.rs` |
| 协议方法 | `mcpServer/*`（6 个）、`config/mcpServer/reload` |
| 工具处理器 | `codex-rs/core/src/tools/handlers/mcp.rs`、`codex-rs/core/src/tools/handlers/mcp_resource.rs` |

**传输形态只有两种，二选一，由用户填 `command` 还是填 `url` 决定**（E3，`codex-rs/config/src/mcp_types.rs`）：

| 变体 | 位置 | 关键字段 |
| ---- | ---- | ---- |
| `McpServerTransportConfig::Stdio` | `codex-rs/config/src/mcp_types.rs:455`（`:454` 的文档注释直接链到 MCP 规范的 stdio 章节） | `command`、`args`、`env`、`env_vars`、`cwd` |
| `McpServerTransportConfig::StreamableHttp` | `codex-rs/config/src/mcp_types.rs:467` | `url`、`bearer_token_env_var`、`http_headers`、`env_http_headers` |

判定逻辑在 `codex-rs/config/src/mcp_types.rs:372-409`：给了 `command` 就走 stdio，并逐个 `throw_if_set("stdio", "url", ...)` 拒绝 HTTP 侧字段；给了 `url` 就走 `StreamableHttp`，同样拒绝 stdio 侧字段；两个都没给则报 `"invalid transport"`。**所以 stdio 与 HTTP 的字段不能混填。**

同文件另有 4 类配套类型，本文未展开：

| 类型 | 位置 | 用途 |
| ---- | ---- | ---- |
| `AppToolApproval` | `codex-rs/config/src/mcp_types.rs:24` | 单个工具的审批模式（`Auto` / `Prompt` / `Writes` / `Approve`） |
| `McpServerDisabledReason` | `codex-rs/config/src/mcp_types.rs:39` | server 被 requirements 禁用后的用户可读原因 |
| `McpServerEnvVar` | `codex-rs/config/src/mcp_types.rs:68` | 环境变量声明（裸名或带 `source` 的对象） |
| `McpServerAuth` | `codex-rs/config/src/mcp_types.rs:140` | 认证模式：`oauth`（存储凭据）/ `chatgpt`（复用 ChatGPT 会话） |

> **第 6 轮：这里原有一句「客户端 / 服务端两个方向的划分经核实无误」的括注已删除。** 服务端方向整体不存在了，它引用的文件也不存在。

---

## 7. 第五条路径：`codex-hooks`（用户侧生命周期钩子）

> [!CAUTION]
> **本文标题的"四条扩展路径"是不完整的口径。** `codex-rs/hooks`（crate `codex-hooks`）提供一套**用户可配置**的生命周期钩子，既不经过 `extension-api`，也不经过插件市场，却同样是 `codex-core` 的**生产**依赖。把它算作第五条路径，比把它塞进"扩展"更诚实。
>
> 初版「我该用哪条路径？」表格里写「**只有**扩展体系有生命周期钩子」——**这是错的**，已在 §8 更正。

### 7.1 它凭什么算一条路径（E3）

| 事实 | 证据 |
| ---- | ---- |
| 是 `codex-core` 的**生产**依赖（不是 dev） | `codex-rs/core/Cargo.toml:52`（`[dependencies]` 段为 `:18`–`:126`） |
| 另被 app-server 与插件运行时依赖 | `codex-rs/app-server/Cargo.toml:55`、`codex-rs/core-plugins/Cargo.toml:24` |
| 有完整机制，不是一个类型别名 | `codex-rs/hooks/src/registry.rs`、`codex-rs/hooks/src/engine/`、`codex-rs/hooks/src/declarations.rs`、`codex-rs/hooks/src/config_rules.rs`、`codex-rs/hooks/src/schema.rs` |

### 7.2 11 种钩子事件（E3）

> **第 6 轮新增 `Interrupt`**（`codex-rs/hooks/src/schema.rs:123-124`）。复算：`sed -n '102,125p' codex-rs/hooks/src/schema.rs | grep -c 'rename ='` → 11。

`codex-rs/hooks/src/schema.rs:100-120` 的 `enum HookEventNameWire` 穷举了全部事件名（wire 格式即 `config.toml` 里写的字符串）：<!-- ref-exempt: 指用户机器上生成的 $CODEX_HOME/config.toml -->

| 事件 | 触发点（按名称） |
| ---- | ---- |
| `PreToolUse` | 工具调用前 |
| `PermissionRequest` | 权限请求时 |
| `PostToolUse` | 工具调用后 |
| `PreCompact` | 上下文压缩前 |
| `PostCompact` | 上下文压缩后 |
| `SessionStart` | 会话开始 |
| `UserPromptSubmit` | 用户提交 prompt |
| `SubagentStart` | 子智能体启动 |
| `SubagentStop` | 子智能体结束 |
| `Stop` | 主循环停止 |

### 7.3 与扩展体系的分工

| | ext 扩展（`*LifecycleContributor`） | `codex-hooks` |
| ---- | ---- | ---- |
| 面向谁 | **crate 作者**——要写 Rust、要在装配层注册 | **用户**——写配置即可，不改代码 |
| 入口 | `codex-rs/ext/extension-api/src/contributors.rs` 的 trait | `$CODEX_HOME/config.toml` 中的 hook 声明<!-- ref-exempt: 指用户机器上生成的配置文件 --> |
| 覆盖面 | thread / turn / tool / approval 等 16 个扩展点 | 10 种固定事件 |
| 生效方式 | 显式 `install(...)` 注册进 `ExtensionRegistry`（见 §2） | 由 `codex-rs/hooks/src/registry.rs` 按配置规则装载 |<!-- ref-exempt: ExtensionRegistry 属于左列的扩展体系，不应期望出现在 hooks/registry.rs 中 -->

**两套机制并存，不是替代关系。** 需要在生命周期插入逻辑时，先问"这段逻辑要不要用户能开关"——要，走 hooks；不要且需要 Rust 级能力，走扩展。

---

## 8. 我该用哪条路径？

| 你要做的事 | 走哪条 | 理由 |
| ---- | ---- | ---- |
| 给模型加一个新工具 | **ext 扩展**，实现 `ToolContributor` | 统一扩展点，能拿到全套工具类型 |
| 在 turn 或 thread 生命周期插入逻辑 | **写代码** → ext 扩展的对应 `*LifecycleContributor`；**不写代码 / 用户侧配置** → `codex-hooks`（10 种事件） | 两套并存：扩展面向 crate 作者，hooks 面向用户配置（见 §7） |
| 接入外部 MCP server | **配置 MCP**，不用写代码 | `codex mcp` + `config.toml`<!-- ref-exempt: 指用户机器上生成的配置文件 -->；传输二选一见 §6.4 |
| 分发可安装的能力包给用户 | **插件** | 有市场、安装、开关、远程分发的完整基建 |
| 提供可复用的提示词/流程资产 | **Skill** | `core-skills` 的 injection 机制；发现规则见 §5.1 |
| 把 Codex 接进别的 MCP 宿主 | **`codex mcp-server`** | 反方向，无需改代码 |

---

## 9. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| MCP 工具调用优先走 `codex-rs/codex-mcp/src/connection_manager.rs`（注意 AGENTS.md 里的路径已过时，见 §6.2） | AGENTS.md 顶部规则列表，关键词 `mcp_connection_manager`<!-- ref-exempt: mcp_connection_manager 是 AGENTS.md 里的检索关键词，不是 connection_manager.rs 内的符号 --> |
| **生命周期钩子有两条路**：写代码走扩展 trait，用户配置走 `codex-hooks` | §7；`codex-rs/hooks/src/schema.rs:100-120` |
| 尽量复用既有抽象，不要多层透传 | 同上 |
| 新扩展应实现 `extension-api` 的 trait，而不是直接改 `codex-core` | 见 [`crate_map.md`](./crate_map.md) §6 |
| **新扩展的注册要加到 `codex-rs/app-server/src/extensions.rs` 的 `thread_extensions()`**，而不是往 `codex-rs/core/Cargo.toml` 里加依赖 | §3.1 |
| 扩展 trait 都要求 `Send + Sync` | `codex-rs/ext/extension-api/src/contributors.rs` |
| trait 中的异步方法用 `impl Future + Send`，不要 `#[allow(async_fn_in_trait)]` | `AGENTS.md` 顶部规则列表，关键词 `async_fn_in_trait` / RPITIT |

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| ~~7 个未被 core 直接依赖的 ext 在哪装配~~ | **已在 §3.1 解决**（前提也是错的：不是 7 个，进入 `ExtensionRegistry` 的是 8 个） | — |
| ~~8 个装配调用各自的门控条件~~ | **已在 §3.1 解决**（E3）：goal 受 `state_db.is_some()` + `Feature::Goals` 双重门控，skills 受 4 个开关，其余 6 个无门控 | — |
| ~~`ext/mcp` 里 `install_executor_plugins` 的具体语义~~ | **已在 §4.2 解决**（E3）：注册 `SelectedExecutorPluginMcpContributor`，经 `ExecutorPluginConnectorProvider` 接 `ext/connectors` | — |
| ~~Skill 的发现与装载~~ | **已在 §5.1 解决**（E3） | — |
| 各 Contributor trait 的方法签名与调用时机 | E1（仅知 trait 名） | `codex-rs/ext/extension-api/src/contributors.rs` |
| 插件清单（manifest）的格式 | E1 | `codex-rs/core-plugins/src/manifest.rs` |
| 插件市场的远程协议 | E1 | `codex-rs/core-plugins/src/remote.rs`、`codex-rs/core-plugins/src/remote_bundle.rs`、`codex-rs/core-plugins/src/remote_legacy.rs` |
| Skill **注入模型上下文**的具体形式（发现与装载已覆盖，注入未覆盖） | E1 | 第 6 轮随 `core-skills` 删除而迁址，相关实现现分散在 `codex-rs/ext/skills/src/host_prompt.rs` 与 `codex-rs/core/src/plugins/injection.rs`，**本轮未读实现，不确认分工** |
| MCP 连接的握手与工具发现流程 | E1 | `codex-rs/codex-mcp/src/connection_manager.rs` 与 `codex-rs/codex-mcp/src/connection_manager/` |
| `codex-hooks` 的执行引擎与配置规则（本文只覆盖了 10 种事件名与依赖关系） | E1 | `codex-rs/hooks/src/engine/`、`codex-rs/hooks/src/config_rules.rs`、`codex-rs/hooks/src/declarations.rs` |
| `codex-connectors`（4,851 行）与 `ext/connectors`（71 行）的分工 | E1 | 两者的 `Cargo.toml` 与 `lib.rs`<!-- ref-exempt: 语境已限定为这两个 crate 各自的清单与入口文件 --> |
| `ext/agent` 派生子智能体时的隔离边界 | E1 | `codex-rs/ext/agent/src/lib.rs`、`codex-rs/app-server/src/request_processors/turn_processor.rs` |

---

## 11. 相关文档

- [Crate 地图](./crate_map.md) §3.8 — 扩展相关 19 个 crate 清单
- [智能体核心循环](./core_agent_loop.md) §4 — 工具调用链路
- [配置体系](./config_system.md) — MCP 与插件的配置入口
- [app-server 协议](./app_server_protocol.md) — `plugin/*`、`mcpServer/*` 方法
- [实验性表面](./experimental_surfaces.md) — 其他能力面
