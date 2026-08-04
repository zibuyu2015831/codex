---
title: Codex CLI 开发文档体系主文档
summary: openai/codex 仓库 dev_docs 开发文档体系的入口，提供项目概览、关键目录速查、12 条场景快速导航、文档索引、开发流程规范、核心代码模式、命名规范、业务模块映射、AI 编码禁忌清单与常见任务速查。
keywords: codex | main-doc | navigation | ai-coding-context | taboos | uncovered-scope
scope: openai/codex 仓库 dev_docs 文档体系总入口
related_files: AGENTS.md | docs/contributing.md | codex-rs/cli/src/main.rs | codex-rs/Cargo.toml | justfile | README.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md | dev_docs/development_workflow.md
verified_at: 2026-08-03
---

# Codex CLI 开发文档体系

> **项目**: [openai/codex](https://github.com/openai/codex) — 运行在本机的 OpenAI 编码智能体
> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **文档定位**: 兼顾**阅读理解 upstream 代码**与**在本仓库做二次开发**
> **语言**: 简体中文

---

## ⚠️ 阅读前必读

> [!CAUTION]
> **仓库自带的 AGENTS.md 优先级高于本文档体系的任何内容。**
>
> 它是仓库对 AI 代理的强制规范（22,519 字节）。本体系只做落地说明与实测补充，禁止覆盖或改写其任何条款。两者有出入时，一律以仓库规范文件为准，并请修正本体系的对应内容。

> [!IMPORTANT]
> **本仓库外部代码贡献受邀制**（`docs/contributing.md:3-17`）。未受邀的 PR 会被直接关闭而不予评审。本体系中所有对代码的观察都是**长期记录**，不是面向上游的修复待办。

---

## 📊 项目概览

| 维度 | 事实 | 证据等级 |
| ---- | ---- | ---- |
| 是什么 | 运行在本机的编码智能体 CLI，同时提供 IDE 接入与桌面端 | E2 |
| 主语言 | Rust 1.95.0（edition 2024），另有 TypeScript / Python SDK | E2 |
| 规模 | 5,913 个 Git 跟踪文件；Rust 2,858 文件 / **1,270,789 行** | E4 |
| 结构 | Cargo workspace，**134 个 crate** | E4 |
| 核心特征 | **单主二进制、多前端**；`codex-core` 是执行内核，但**不是所有前端的直接依赖** | E3 |
| 构建 | Cargo（日常开发**与发布产出**）+ Bazel（PR 合并前主验证路径），**双锁必须同步** | E2 |
| 隔离 | 三平台原生沙箱：Seatbelt / **bwrap+seccomp** / Windows 受限令牌 | E3 |
| 入口 | `codex` 一个主二进制（另有 6 个随发布交付的辅助可执行文件，加 2 个仅本地/CI 产出的共 8 个），27 个子命令变体 | E3 |
| 测试资产 | 39 个测试目录 / 631 个测试文件 / 457 个 `*_tests.rs` / 681 个快照 | E1 |

**最重要的一句话**：所有前端都是同一个二进制的子命令，但**它们到达 `codex-core` 的路径不同**——`codex exec`、app-server、MCP server、cloud 直接依赖 `codex-core`；而 **TUI 没有指向 `codex-core` 的直接依赖边，也不直接 import 它**（CI 强制），它经 `codex-app-server-client` 接入。

> [!WARNING]
> **注意「直接」二字，它是这条边界的全部要害。** `codex-core` 仍会**传递性**链接进 TUI（最短路径 `codex-tui → codex-app-server-client → codex-core`，另经 `cloud-config`、`utils/oss` 两条 normal 依赖），且 core 的配置类型经 `codex_app_server_client::legacy_core` 再导出，TUI 有 93 处在用。
>
> 本体系在这一句上错过三次：首版写反（说所有前端汇聚到 core），第二轮改成「能力必须先有协议方法」漏了 `legacy_core`，第三轮改成「不链接 core」漏了传递依赖。**校验脚本的原文是 `does not depend on or import codex-core directly`**——限定词一直都在。详见 [`tui_guide.md`](./tui_guide.md) §0.1–§0.2。

> [!CAUTION]
> **`codex-tui` 不得直接依赖或 import `codex-core`，这是 CI 机器强制的架构不变量。**
>
> 校验脚本：`.github/scripts/verify_tui_core_boundary.py`，文件头写明 `"""Verify codex-tui does not depend on or import codex-core directly."""`，由 `.github/workflows/repo-checks.yml` 在每个 PR 上执行。
>
> TUI 经 `codex-app-server-client` 接入，有两种客户端实现：`InProcessAppServerClient`（同进程）与 `RemoteAppServerClient`（连远端 app-server）。详见 [`architecture_overview.md`](./architecture_overview.md) §5。
>
> **例外（同样重要）**：`codex-app-server-client` 显式再导出了 core 的配置类型——`pub mod legacy_core { pub mod config { pub use codex_core::config::*; } }`，TUI 在 93 处、40 个文件中用它。校验脚本的报错文案也点名这是被认可的过渡通道。所以边界约束的是**依赖边与 import**，不是「core 的一切都必须经协议方法抵达」。详见 [`tui_guide.md`](./tui_guide.md) §0.2。
>
> 本文档体系首版曾把「所有前端都汇聚到 `codex-core`」写成主干论断并画入依赖图——**方向恰好与这条被强制的边界相反**。若你在旧版本中读到该表述，以本节为准。

**复杂度评级**：超大型项目（5.5 级 = 超大型 3 + Monorepo 1 + 多进程架构 1 + 混合语言 0.5）。

---

## 📂 关键目录速查

| 目录 | 内容 | 文件数量级 |
| ---- | ---- | ---- |
| `codex-rs/` | **Rust workspace，项目主体**，134 个 crate | 5,501 |
| `codex-rs/core/` | 智能体核心：会话、turn、工具调用、上下文（296,963 行） | — |
| `codex-rs/tui/` | ratatui 交互式终端界面（238,439 行） | — |
| `codex-rs/app-server/` | JSON-RPC 应用服务端，供 IDE / 桌面端 / SDK 接入（128,364 行） | — |
| `codex-rs/cli/` | **主二进制** `codex` 的入口与子命令分发 | — |
| `codex-rs/ext/` | 12 个 `ext/*` crate（其中 8 个是 contributor 型扩展） | — |
| `codex-rs/utils/` | **23 个**通用工具 crate | — |
| `codex-rs/sandboxing/` | 三平台沙箱统一入口 + 3 个 `.sbpl` 策略 | — |
| `codex-rs/vendor/` | **vendored bubblewrap C 源码**，Linux 默认沙箱的实际载体 | 51 |
| `codex-rs/docs/` | 仓库自带开发者文档：`codex-rs/docs/protocol_v1.md` / `codex-rs/docs/bazel.md` / `codex-rs/docs/codex_mcp_interface.md` | 3 |
| `codex-cli/` | **npm 分发包 `@openai/codex`**（注意：与 Cargo 包名 `codex-cli`＝目录 `codex-rs/cli` 同名，容易搜错） | 7 |
| `sdk/` | TypeScript / Python / Python-runtime 三套 SDK | 115 |
| `.github/` | CI 工作流（27 个 yml）与脚本 | 89 |
| `scripts/` | 格式化与辅助脚本（`scripts/format.py` 等） | 38 |
| `tools/` | `argument-comment-lint`（workspace 之外的独立 crate） | 31 |
| `docs/` | 仓库内文档，**极薄**（`docs/config.md` 15 行、`docs/sandbox.md` 3 行） | 15 |
| `dev_docs/` | **本文档体系**（不属于上游） | — |

> [!WARNING]
> `AGENTS.md` 顶部规则列表（grep `product or user-facing documentation`）禁止向 `docs/` 添加通用产品或用户文档。本体系全部产物固定在 `dev_docs/`，**任何情况下都不得迁入 `docs/`**。

---

## 🎯 场景快速导航

### 阅读理解类

| 我想…… | 去看 | 起手式 |
| ---- | ---- | ---- |
| 1. 搞清楚整体架构 | [`architecture_overview.md`](./architecture_overview.md) | 从 §2 运行时拓扑图开始 |
| 2. 知道某个 crate 是干什么的 | [`crate_map.md`](./crate_map.md) §3 | 按职责分组速查表 |
| 3. 找到某个功能在哪实现 | [`crate_map.md`](./crate_map.md) §3 → 对应 crate 目录 | `git grep -n "<关键词>" codex-rs/<crate>/src` |
| 4. 理解某个 CLI 子命令做了什么 | [`architecture_overview.md`](./architecture_overview.md) §3 | `codex-rs/cli/src/main.rs:124`（枚举）→ `:1001` 的 `match subcommand`（分发；`:1002` 为 `None` 默认 TUI） |
| 5. 搞清楚数据往哪里发 | [`architecture_overview.md`](./architecture_overview.md) §8 | 外部服务边界表 |
| 6. 知道配置和凭证存在哪 | [`architecture_overview.md`](./architecture_overview.md) §7 | `CODEX_HOME`，默认 `~/.codex` |

### 二次开发类

| 我想…… | 去看 | 起手式 |
| ---- | ---- | ---- |
| 7. 搭好环境跑起来 | [`development_workflow.md`](./development_workflow.md) §1 | `just install` → `just codex` |
| 8. 知道新代码该放哪个 crate | [`crate_map.md`](./crate_map.md) §5 决策树 | 默认答案：**不要放进 `codex-core`** |
| 9. 改完代码后该做什么 | [`development_workflow.md`](./development_workflow.md) §3.1 | `just fmt` → `just test -p <crate>` |
| 10. 评估我的改动会波及谁 | [`crate_map.md`](./crate_map.md) §4 依赖热点 | 查被依赖数排名 |
| 11. 改了依赖 / 配置 / 协议后要补跑什么 | [`development_workflow.md`](./development_workflow.md) §2.5 | `just bazel-lock-update` 等 |
| 12. 提交前检查有没有漏项 | [`development_workflow.md`](./development_workflow.md) §9 | 自检清单 |

---

## 🚀 文档索引

### 本体系文档

| 批次 | 文档 | 状态 |
| ---- | ---- | ---- |
| 第 1 批 | `AI_Coding_Context.md`（本文） | ✅ |
| 第 1 批 | [`architecture_overview.md`](./architecture_overview.md) — 架构总览 | ✅ |
| 第 1 批 | [`crate_map.md`](./crate_map.md) — 134 个 crate 地图 | ✅ |
| 第 1 批 | [`development_workflow.md`](./development_workflow.md) — 开发流程与规范 | ✅ |
| 第 2 批 | [`core_agent_loop.md`](./core_agent_loop.md) — 智能体核心循环 | ✅ |
| 第 2 批 | [`tools_and_sandbox.md`](./tools_and_sandbox.md) — 工具调用与沙箱 | ✅ |
| 第 2 批 | [`app_server_protocol.md`](./app_server_protocol.md) — app-server 协议 | ✅ |
| 第 2 批 | [`config_system.md`](./config_system.md) — 配置体系 | ✅ |
| 第 2 批 | [`tui_guide.md`](./tui_guide.md) — TUI 开发 | ✅ |
| 第 3 批 | [`testing_guide.md`](./testing_guide.md) — 测试指南 | ✅ |
| 第 3 批 | [`mcp_and_extensions.md`](./mcp_and_extensions.md) — MCP 与扩展体系 | ✅ |
| 第 3 批 | [`auth_and_providers.md`](./auth_and_providers.md) — 认证与模型接入 | ✅ |
| 第 3 批 | [`build_and_release.md`](./build_and_release.md) — 构建与发布 | ✅ |
| 第 3 批 | [`session_and_persistence.md`](./session_and_persistence.md) — 会话与持久化 | ✅ |
| 第 4 批 | [`experimental_surfaces.md`](./experimental_surfaces.md) — 实验性表面 | ✅ |
| 第 4 批 | [`observability.md`](./observability.md) — 可观测性与遥测边界 | ✅ |
| 第 4 批 | [`sdk_guide.md`](./sdk_guide.md) — TypeScript / Python SDK | ✅ |
| 第 4 批 | [`dev_docs/rules/combined/AI_RULES.md`](./rules/combined/AI_RULES.md) — AI 规则索引 | ✅ |

**辅助目录**：[`plans/`](./plans/README.md)（变更计划）、[`knowledge/`](./knowledge/README.md)（知识沉淀）、`_analysis/`（生成过程记录，非阅读材料）

> **17 篇正式文档 + AI 规则索引已全部生成。** 每篇末尾都有「本文未覆盖的内容」表，列出该主题下仍需回去读代码的部分。

### 仓库自带文档（**只链接，不复制**）

| 文档 | 用途 |
| ---- | ---- |
| [AGENTS.md](../AGENTS.md) | **AI 代理强制规范，优先级最高** |
| [`README.md`](../README.md) | 安装与快速上手 |
| [`docs/contributing.md`](../docs/contributing.md) | 贡献规则（受邀制） |
| [`docs/install.md`](../docs/install.md) | 安装与构建 |
| [`codex-rs/tui/styles.md`](../codex-rs/tui/styles.md) | TUI 样式约定 |
| [developers.openai.com/codex](https://developers.openai.com/codex) | 官方产品文档 |

---

## 🛠️ 开发流程规范

完整内容见 [`development_workflow.md`](./development_workflow.md)，此处只列最常用的骨架。

### 改完代码后的固定动作

```
1. just fmt                       # 在 codex-rs 目录下，改完即跑，无需请示
2. just test -p <改动的 crate>     # 改了 codex-rs/tui → just test -p codex-tui
3. 若改动涉及 common/core/protocol → just test（全量，跑前先问用户）
4. 大改动收尾 → just fix -p <crate>（跑完不要重跑测试）
```

### 触发式补跑

| 你改了什么 | 必须补跑 |
| ---- | ---- |
| `codex-rs/Cargo.toml` / `codex-rs/Cargo.lock` | `just bazel-lock-update`，锁文件入同一 change |
| `ConfigToml` 或嵌套配置类型 | `just write-config-schema` |
| app-server API 形状 | ⚠️ `just write-app-server-schema` 当前跑不通，改用 `python3 codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`（见「模式 4」） |
| 新增 `include_str!` / `sqlx::migrate!` | 更新该 crate 的 `BUILD.bazel`（`compile_data`） |

### 变更规模上限

| 变更类型 | 上限 |
| ---- | ---: |
| 一般变更 | 800 行 |
| 复杂逻辑变更 | 500 行 |

超限时必须拆分成可评审的阶段，并基于实际 diff 与依赖关系给出拆分建议。

---

## 💻 核心代码模式

> 以下模式来自 AGENTS.md 明文规定与源码实测，是本仓库写代码时必须遵循的形状。

### 模式 1：CLI 子命令定义

新增用户可见能力时，在 `codex-rs/cli/src/main.rs:124` 的 `Subcommand` 枚举中添加变体：

```rust
/// 一句话描述，会成为 --help 输出
Exec(ExecCli),

/// 实验性能力必须显式标注
/// [experimental] Run the app server or related tooling.
AppServer(AppServerCommand),

/// 内部用途用 hide 隐藏
#[clap(hide = true)]
ResponsesApiProxy(ResponsesApiProxyArgs),

/// 平台专属能力用条件编译
#[cfg(any(target_os = "macos", target_os = "windows"))]
App(app_cmd::AppCommand),
```

随后在 `codex-rs/cli/src/main.rs` 的 `match subcommand`（:1001 起）中补分发分支。

### 模式 2：trait 中的异步方法（`AGENTS.md` 顶部规则列表，grep `async_fn_in_trait`）

```rust
// ✅ 推荐：显式写出 future 契约
fn foo(&self, ...) -> impl std::future::Future<Output = T> + Send;

// ✅ 实现侧满足该契约时可以用 async fn
async fn foo(&self, ...) -> T { ... }

// 🚫 禁止：用 allow 绕过
#[allow(async_fn_in_trait)]
```

### 模式 3：异步追踪（`AGENTS.md` 顶部规则列表，grep `tracing::instrument`）

```rust
// ✅ 在定义处标注
#[tracing::instrument(...)]
async fn handle_turn(...) { ... }

// 🚫 不要在调用点附加 span
handle_turn(...).instrument(span)
```

加之前先检查被调用方——或它立即委托到的实现方法——是否已被标注。

### 模式 4：协议类型导出（`AGENTS.md` → `App-server API Development Best Practices` → `Core Rules`）

app-server v2 协议类型必须标注导出目标，否则生成的 TS 类型会落错目录：

```rust
#[derive(TS)]
#[ts(export_to = "v2/")]
pub struct SomeRequest { ... }
```

改完按 `AGENTS.md` 的 `App-server API Development Best Practices → Development Workflow` 一节重新生成 schema，再用 `just test -p codex-app-server-protocol` 验证。

> [!WARNING]
> `AGENTS.md` 与 `justfile` 都写着用 `just write-app-server-schema` 重新生成，但 **该 recipe 当前跑不通**：它调用 `cargo run -p codex-app-server-protocol --bin write_schema_fixtures`，而 `codex-app-server-protocol` 没有任何 bin target（无 `[[bin]]`、无 `src/bin/`）。
>
> 可用的生成入口是 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`。详见 [`app_server_protocol.md`](./app_server_protocol.md) §0。

### 模式 5：测试组织（`AGENTS.md` → `Test authoring guidance` / `Test assertions`）

```
智能体逻辑变更 → 集成测试（core/tests/suite 下，用 test_codex 搭建实例）——必须写
确需单元测试 → 放进专门的 *_tests.rs 文件（用 #[path = "..._tests.rs"] 挂载）
断言          → 比较整个对象的相等性，不要逐字段比；用 pretty_assertions::assert_eq
🚫 不要在主实现里留测试专用函数
🚫 不要在测试中改动进程环境变量
```

> 「比较整个对象的相等性」这条出自 `AGENTS.md` 顶部的通用规则列表，不在 `Test authoring guidance` 一节内。

### 模式 6：MCP 工具调用（`AGENTS.md` 顶部规则列表）

处理工具与工具调用的变更时，优先走 MCP 连接管理器复用既有抽象，不要把逻辑层层透传。

> [!NOTE]
> <!-- ref-exempt: 本行正在说明 AGENTS.md 给的路径不存在，引用不可解析即为要表达的事实 --> `AGENTS.md` 原文给的路径是 `codex-rs/codex-mcp/src/mcp_connection_manager.rs`，**该文件不存在**——上游规则文件的路径已陈旧。实际文件是 `codex-rs/codex-mcp/src/connection_manager.rs`（另有 `connection_manager/` 目录与 `codex-rs/codex-mcp/src/connection_manager_tests.rs`）。

---

## 📋 命名规范

| 对象 | 规范 | 实例 |
| ---- | ---- | ---- |
| crate 包名 | `codex-` 前缀 + kebab-case | `codex-core`、`codex-app-server-protocol` |
| crate 目录 | kebab-case，通常与包名去掉 `codex-` 前缀后一致 | `codex-rs/app-server-protocol/` |
| 例外：目录与包名不一致 <!-- ref-exempt: Cargo.toml 此处泛指任意 crate 的清单文件 --> | 少数 crate 存在偏差，**以 `Cargo.toml` 的 `name` 为准** | `codex-rs/windows-sandbox-rs/` → `codex-windows-sandbox`；`codex-rs/utils/path-utils/` → `codex-utils-path` |
| 工具库 crate | 统一放 `codex-rs/utils/`，包名 `codex-utils-*` | `codex-utils-absolute-path` |
| `ext/` 下的 crate | 统一放 `codex-rs/ext/`，但**包名不统一** | 8 个用 `codex-*-extension`（如 `codex-skills-extension`）；4 个不符：`codex-extension-api`、`codex-extension-items`、`codex-git-attribution`、`codex-guardian` |
| 单元测试文件 <!-- ref-exempt: 此列是命名规范举例，非指定文件 --> | `*_tests.rs` | `config_tests.rs`、`manager_tests.rs` |
| 集成测试 | `<crate>/tests/suite/` 下 | `codex-rs/core/tests/suite/compact.rs` |
| 测试辅助 crate | `*_test_support`（下划线，非 kebab） | `core_test_support`、`app_test_support` |
| 快照文件 | insta 生成的 `.snap` | 全仓 681 个 |
| 沙箱策略文件 | `.sbpl` | `codex-rs/sandboxing/` 下 3 个 |
| 生成的 TS 类型 | `schema/typescript/v2/` 下，**构建产物不可手改** | 550 个文件 |

> [!NOTE]
> 命名规范是**从实测归纳的**（E3/E4），`AGENTS.md` 未逐条明文规定其中的目录约定。遇到与本表不符的既有命名，以代码为准，不要据此改名。

---

## 🏢 业务模块映射

| 业务能力 | 主要 crate | 用户入口 |
| ---- | ---- | ---- |
| 交互式编码会话 | `codex-tui` → `codex-app-server-client` → app-server → `codex-core`（TUI **不直接依赖** core） | `codex`（无子命令） |
| 非交互批量执行 | `codex-exec` + `codex-core` | `codex exec`（别名 `e`） |
| 代码评审 | `codex-exec` | `codex review` |
| IDE / 桌面端接入 | `codex-app-server` + `codex-app-server-protocol` | `codex app-server` ⚠️ |
| 把 Codex 作为 MCP server | `codex-mcp-server` | `codex mcp-server` |
| 接入外部 MCP server | `codex-rmcp-client`、`codex-mcp` | `codex mcp` |
| 插件管理 | `codex-core-plugins`、`codex-plugin` | `codex plugin` |
| 认证登录 | `codex-login`、`codex-keyring-store`、`codex-secrets` | `codex login` / `logout` |
| 会话管理 | `codex-thread-store`、`codex-rollout` | `codex resume` / `fork` / `archive` / `delete` |
| 命令执行隔离 | `codex-sandboxing` 系列 8 个 crate | `codex sandbox` |
| 执行策略 | `codex-execpolicy` | `codex execpolicy` 🔒 |
| 变更应用 | `codex-chatgpt`（`apply_command`） | `codex apply`（别名 `a`） |
| 独立执行服务 | `codex-exec-server` | `codex exec-server` ⚠️ |
| 云任务 | `codex-cloud-tasks` 系列 4 个 crate | `codex cloud` ⚠️ |
| 桌面端 | 由 CLI 拉起安装器 | `codex app`（仅 macOS/Windows） |
| 诊断 | — | `codex doctor` / `debug` / `features` |
| 配置体系 | `codex-config` | `~/.codex/config.toml` |
| 模型接入 | `codex-model-provider`、`codex-ollama`、`codex-lmstudio` | 配置文件 |
| 可观测性 | `codex-otel`、`codex-analytics`、`codex-hooks` | — |

⚠️ = 实验性　🔒 = 隐藏子命令。详见 [`crate_map.md`](./crate_map.md) §3。

---

## ⚠️ AI 编码禁忌

### 🚫 绝对禁止

> [!NOTE]
> **出处一律给章节标题与原文关键词，不给行号。** 首版曾用行号引用，独立审查发现 30+ 处已偏移（`AGENTS.md` 是活文档）。用关键词 `grep` 才是可靠的定位方式。

| # | 禁忌 | 出处（`AGENTS.md` 章节 / 可 grep 的关键词） |
| ---: | ---- | ---- |
| 1 | 新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码 | 顶部规则列表，grep `CODEX_SANDBOX` |
| 2 | 向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | 顶部规则列表，grep `product or user-facing documentation` |
| 3 | 直接跑 cargo test（必须用 just 的测试任务） | 顶部规则列表，grep `` Do not run `cargo test` `` |
| 4 | 用 PID 杀掉正在跑的 Rust 命令 | 顶部规则列表，grep `be patient` |
| 5 | 手改 `app-server-protocol/schema/typescript/` 下的生成文件 | **出处不是 `AGENTS.md`**——`AGENTS.md` 无此条款。依据是生成文件首行 `// GENERATED CODE! DO NOT MODIFY BY HAND!` |
| 6 | 改动可见 UI 却不配 insta 快照覆盖 | `### Snapshot tests`，原文为 `**Requirement:** ... must include corresponding insta snapshot coverage` |
| 7 | 向 app-server **v1** 新增 API 面 | `## App-server API Development Best Practices`，原文 `Do not add new API surface area to v1.` |

### ⚠️ 强烈不建议

| # | 禁忌 | 出处 / 理由 |
| ---: | ---- | ---- |
| 8 | 把新逻辑堆进 `codex-core` | `## The codex-core crate`；已 296,963 行、66 个 workspace 依赖 |
| 9 | 继续扩写超过 800 行的文件 | 顶部规则列表，grep `add new functionality in a new module` |
| 10 | 给 `codex-rs/tui/src/chatwidget.rs` 加新的独立方法（除非改动很小） | 顶部规则列表，grep `codex-rs/tui/src/chatwidget.rs` |
| 11 | 用 `#[allow(async_fn_in_trait)]` 绕过 future 契约 | 顶部规则列表，grep `async_fn_in_trait` |
| 12 | 在调用点用 `.instrument(...)` 而非在定义处标注 | 顶部规则列表，grep `tracing::instrument` |
| 13 | 创建只被引用一次的小助手方法 | 顶部规则列表，grep `helper method` |
| 14 | 为静态定义的值写测试 | 顶部规则列表，grep `statically defined` |
| 15 | 为已移除的逻辑写负向测试 | 顶部规则列表 |
| 16 | 在主实现里留测试专用函数 | `### Test authoring guidance`，grep `Avoid test-only functions` |
| 17 | 单次变更超过 800 行（复杂逻辑 500 行） | `### Change size guidance (800 lines)` |
| 18 | 常规本地运行加 `--all-features` | 顶部规则列表，grep `--all-features` |
| 19 | 改了依赖却不同步 Bazel 锁文件 | 顶部规则列表，grep `bazel-lock-update` |
| 20 | 加了 `include_str!` 却不补 `BUILD.bazel` 的 `compile_data` | 顶部规则列表，grep `include_str!` |
| 21 | 在测试里改动进程环境变量 | `### Test assertions` 附近，grep `environment variables` |
| 22 | 用 `assert_cmd::Command::cargo_bin` / `env!("CARGO_MANIFEST_DIR")` | `### Spawning workspace binaries in tests (Cargo vs Bazel)`——会破坏 Bazel runfiles |

### 📌 本文档体系自身的约束

| # | 约束 |
| ---: | ---- |
| 23 | 推送只能推个人 fork，**禁止推上游 `origin`** |
| 24 | fork 是公开仓库，提交前必须跑脱敏扫描；**禁止写入任何凭证的实际值** |
| 25 | 文档中的 `related_files` 只列**实际读过**的文件 |
| 26 | 未验证的结论必须标注证据等级，**禁止把 E1 目录名推断写成 E3 事实** |
| 27 | 依赖类断言必须区分 `[dependencies]` 与 `[dev-dependencies]`，并用 `cargo metadata` 而非 `grep` 验证 |
| 28 | 断言某机制"生效"前，必须找到它的**构造点与调用方**，只读类型定义不算 |
| 29 | 外部文件引用给章节标题与可 grep 的关键词，**不给行号** |

> [!CAUTION]
> 第 26–28 条都是**本体系自己违反过**的规则。第二轮独立审查查出 15 个 HIGH 级事实错误，其中 5 个源于第 27/28 条：
>
> - 把 `[dev-dependencies]` 里的条目当成架构依赖，据此推出「`codex-core` 直接依赖 5 个扩展」——实际生产依赖只有 2 个
> - 读 `SandboxType` 与 `ConfigLayerSource` 的枚举定义就下结论，而 `Landlock` 文件系统强制与 `Mdm` 变体在生产路径上**根本不被构造**
>
> 写下规则不等于遵守规则。详见 [`dev_docs/_analysis/health_check_report.md`](./_analysis/health_check_report.md)。

---

## 🔧 常见任务速查

| 任务 | 命令 / 位置 |
| ---- | ---- |
| 初始化环境 | `just install` |
| 从源码运行 | `just codex <args>`（别名 `just c`） |
| 从源码跑非交互 | `just exec <args>` |
| 列出全部任务 | `just` 或 `just help` |
| 格式化 | `just fmt` |
| 只检查格式 | `just fmt-check` |
| 跑单个 crate 测试 | `just test -p <crate>` |
| 跑全量测试 | `just test`（**跑前先问用户**） |
| 修 lint | `just fix -p <crate>` |
| 看实时日志 | `just log` |
| 重新生成配置 schema | `just write-config-schema` |
| 重新生成 app-server schema | ⚠️ `just write-app-server-schema` **当前跑不通**（bin 不存在），改用 `python3 codex-rs/app-server-protocol/scripts/write_schema_fixtures.py` |
| 同步 Bazel 锁文件 | `just bazel-lock-update` |
| 校验锁文件漂移 | `just bazel-lock-check` |
| 构建发布产物（Bazel 校验用） | `just build-for-release`；**注意正式发布产物由 Cargo 构建**，见 [`build_and_release.md`](./build_and_release.md) §1 |
| 接受 insta 快照 | `just test -p codex-tui` 生成 → `cargo insta pending-snapshots -p codex-tui` → `cargo insta accept -p codex-tui` |
| 查 crate 总数 | `cargo metadata --no-deps --format-version 1 --manifest-path codex-rs/Cargo.toml \| python3 -c "import json,sys;print(len(json.load(sys.stdin)['packages']))"` |
| 找某功能实现 | `git grep -n "<关键词>" codex-rs/<crate>/src` |
| 读超大文件 | 先 `git grep -n "^pub fn\|^impl\|^pub struct" <file>` 拿结构，再定点读 |

> [!TIP]
> `cargo` 可能不在默认 PATH 中，需要时先 `export PATH="$HOME/.cargo/bin:$PATH"`。
> `justfile` 第 1 行是 `set working-directory := "codex-rs"`，所以 just 任务默认在 `codex-rs/` 下执行（除非标注 `[no-cd]`）。

---

## 📐 证据等级约定

本体系的所有结论都标注证据等级。看到结论时请先确认它的等级：

| 等级 | 来源 | 允许的措辞 |
| ---- | ---- | ---- |
| **E1** | 目录结构、文件名、文件数量 | 只能写"疑似""风险假设""建议后续验证" |
| **E2** | 配置文件、锁文件、README、项目文件 | 可写"已从配置确认" |
| **E3** | 源码片段、协议、关键函数、调用链 | 可写"代码显示""实现方式为" |
| **E4** | 构建、测试、脚本运行、工具检查结果 | 可写"已验证""检查通过/失败" |

> [!WARNING]
> **文件数量、目录清单属于 E1，不是 E4。** 「跑了 `wc -l` / `ls`」不等于 E4——E4 指构建、测试、lint 等**验证性**工具的运行结果。首版有 13 处把文件清单标成 E4，已在第二轮统一降级。
>
> 例：「134 个 crate」是 E4（`cargo metadata` 解析 workspace 后的权威输出）；「`utils/` 下 23 个目录」是 E1（数目录）；「Rust 2,858 个文件」是 E1（数文件），只有其行数 1,270,789 因经 `wc` 统计可算 E2 口径。

> [!CAUTION]
> **最常见的错误是把 E1 的目录名/依赖名推断写成 E3 事实。** 本体系有两次实例可供警惕：
>
> 1. 「12 个 `ext/*` 全部依赖 `extension-api`」——用 `grep -rl` 数文件名得出，实际是 8/12，且把 `extension-api` 自身也数了进去
> 2. 「Linux 沙箱用 Landlock」——因为 `Cargo.toml` 里有 `landlock` 依赖、文件名叫 `landlock.rs`。实际该机制已废弃，默认走 bwrap <!-- ref-exempt: 复述致错线索，泛指依赖名与文件名本身 -->
>
> 依赖存在 ≠ 依赖生效；类型定义存在 ≠ 该分支被构造。

---

## 🚧 未覆盖范围（显式清单）

> [!IMPORTANT]
> 1,270,789 行 Rust、134 个 crate，17 篇文档不可能覆盖全部。**下面列出的内容目前没有可靠文档，遇到时必须回去读代码。**

### 完全未深入的 crate

`codex-network-proxy`(17,064) · `codex-external-agent-migration`(15,262) · `codex-rollout-trace`(13,257) · `codex-hooks`(11,795) · `codex-apply-patch`(5,056) · `codex-connectors`(4,851) · `codex-utils-pty`(4,114) · `codex-git-utils`(3,572) · `codex-agent-graph-store`(479) · `codex-aws-auth`(375) · `codex-bwrap`(151) · `codex-v8-poc`(92) · `codex-file-watcher` · `codex-file-search` · `codex-terminal-detection` · `codex-prompts` · `codex-install-context` · `codex-feedback` · `codex-exec-server-test-support` · 以及 `utils/` 下的 23 个工具 crate

### 系统级缺口（第二轮独立审查补录）

以下子系统体量可观但**全部 17 篇文档零覆盖**，且首版未登记为未覆盖项：

| 子系统 | 入口 | 说明 |
| ---- | ---- | ---- |
| **Realtime 语音 / WebSocket 会话面** | `codex-rs/core/src/realtime_conversation.rs`(2,465)、`codex-rs/core/src/realtime_context.rs`(580)、`codex-api/src/endpoint/realtime_websocket/`(4,393)、6 个 `experimental_realtime_*` 配置键 | 体量数千行，是最大的单一缺口 |
| **`codex-features` 门控机制** | `codex-rs/features/src/lib.rs` 的 `Feature` 枚举（102 个变体，显式分 `// Stable.` 与 `// Experimental`）、`codex features` 子命令 | 这是仓库内**最系统的实验性标记方式**，`experimental_surfaces.md` 首版一字未提 |
| **Nix 构建路径** | `flake.nix`、`flake.lock`、`codex-rs/default.nix` | 「双构建系统 = Cargo + Bazel」的表述因此不完整 |
| **容器 / devcontainer 开发环境** | `.devcontainer/`、`codex-cli/scripts/run_in_container.sh`、`codex-cli/scripts/init_firewall.sh` | 原方案计划收入 `development_workflow.md`，被静默丢弃 |
| **记忆（memories）子系统** | `codex-rs/memories/`、`ext/memories`、`thread/memoryMode/set` | 仅在 crate 表中占一行 |
| **协作模式（collaboration mode）** | `collaboration-mode-templates`、`codex-rs/app-server-protocol/src/protocol/v2/collaboration_mode.rs`、`codex-rs/tui/src/collaboration_modes.rs` | 4 处提及文件名，无一处解释是什么 |
| **guardian 安全子系统** | `ext/guardian`、`core/src/guardian/`、`ApprovalReviewContributor` | 是审批链路的自动审查后端 |
| **多智能体协作** | `codex-rs/core/src/session/multi_agents.rs`、`tools/handlers/multi_agents_v2/`、`ext/agent`、`agent-graph-store` | 跨 5 个 crate |

### 已知但未验证的架构点

> 下表是**第二轮独立审查后的状态**。已闭合的项保留划线记录；被审查推翻的结论单独标注。

| 事项 | 当前证据 | 状态 |
| ---- | ---- | ---- |
| ~~四条扩展路径的相互关系~~ | **E3** | ⚠️ 已闭合但**首版结论有错**：不是 12/12 依赖 `extension-api`，而是 8/12。见 [`mcp_and_extensions.md`](./mcp_and_extensions.md) §1 |
| ~~遥测的默认开关~~ | **E3** | ⚠️ 已闭合但**首版结论有错**：debug 构建默认仍发网络，且两条通路是耦合的。见 [`observability.md`](./observability.md) §1 |
| ~~`find_codex_home` 是否重复实现~~ | **E3** | ✅ 已闭合：是薄委托，见 [`config_system.md`](./config_system.md) §5 |
| ~~insta 快照的更新流程~~ | **E2** | ✅ 已闭合：`AGENTS.md` 的 `### Snapshot tests` 一节有完整流程。**首版记为「无任何记载」是漏读**，见 [`testing_guide.md`](./testing_guide.md) |
| ~~turn 完整状态流转~~ | **E3** | ✅ 已闭合：`submission_loop` → `SessionTask` → `codex-rs/core/src/tasks/regular.rs` 的 turn 循环，见 [`core_agent_loop.md`](./core_agent_loop.md) §2 |
| ~~审批与沙箱的先后次序~~ | **E3** | ✅ 已闭合：审批 → 选沙箱 → 尝试 → 拒绝后升级重试（不重新审批），见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) |
| app-server ↔ exec-server 的跨 OS 传输实现 | E2 | ⏳ **未闭合**，入口见 [`app_server_protocol.md`](./app_server_protocol.md) §7 |
| `codex-core` 66 个 workspace 依赖的具体用途 | E1 | ⏳ 未闭合，见 [`core_agent_loop.md`](./core_agent_loop.md) §9 |
| 配置项全集（93 个键）的逐个语义 | E2（schema 键名） | ⏳ 未闭合，查 `codex-rs/core/config.schema.json` |
| Realtime 会话面 | 未开始 | ⏳ 见上方「系统级缺口」表 |
| Python SDK 的运行时行为 | E2（本机 Python 3.9.6 低于要求的 3.10，无法实跑） | ⏳ 待环境升级 |

> **每篇文档末尾都有各自的「本文未覆盖的内容」表**，比上表更细。上表只列跨文档的关键缺口。

### 本体系不涉及的内容

- 上游代码的安全审计与正确性审计（**"0 个严重问题"不等于"代码无缺陷"**）
- 面向最终用户的产品使用手册（见 developers.openai.com）
- 向上游提交 PR 的流程（受邀制，非本体系范围）

---

## 🕒 时效性与维护

| 项 | 值 |
| ---- | ---- |
| 基线 commit | `bb5054fe47abe73ecbbd454751066a28c89f4bb9` |
| 生成日期 | 2026-08-03 |
| 上游迭代频率 | 高（基线 commit 与分析同日，近 5 次提交均为当日/近日 PR） |

**高漂移区**（上游一变，本体系就可能过期）：

| 位置 | 影响的文档 |
| ---- | ---- |
| `codex-rs/Cargo.toml` | `crate_map.md` 全文 |
| 仓库根的 AI 规范文件 | `development_workflow.md`、本文「AI 编码禁忌」 |
| `codex-rs/cli/src/main.rs` | `architecture_overview.md` §3 |
| `codex-rs/app-server-protocol/` | `app_server_protocol.md` |
| `justfile` | `development_workflow.md` §2 |

**核对办法**：每篇文档 frontmatter 记录 `verified_at`，正文记录基线 commit。拉取上游后，对照上表跑一次 diff，只更新受影响的文档。

---

## 📝 生成过程记录

`dev_docs/_analysis/` 下有**四份**过程文件，**不是阅读材料**，供追溯与断点续传：

| 文件 | 用途 |
| ---- | ---- |
| `generation_plan.md` | 生成方案、17 篇文档清单、证据记录、脱敏门禁 |
| `project_analysis_report.md` | 风险、警告、疑问与建议，全部带证据等级 |
| `generation_progress.md` | 进度、方案复查记录、机器检查结果、用户确认状态 |
| `health_check_report.md` | 质量验收报告（**当前 verdict = FAIL**，记录第二轮独立审查查出的 15 项 HIGH 级错误） |

> [!IMPORTANT]
> **本文档体系经历过一次失败的自验收。** 首版判定通过（5 项 checker 全绿、7 项质量维度全 ✅），随后由 7 个独立代理从源码重新推导，查出 15 个 HIGH 级事实错误。
>
> 教训写在 `health_check_report.md` 的「三个错误模式」一节。使用本体系时，对**架构定性类结论**（谁依赖谁、哪个机制默认生效、哪条是主路径）请保持警惕并回查源码——这类结论正是首版错得最集中的地方。
