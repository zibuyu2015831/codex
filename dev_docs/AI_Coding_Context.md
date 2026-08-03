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
| 核心特征 | **单二进制、多前端、收敛到同一份 `codex-core`** | E3 |
| 构建 | Cargo（日常）+ Bazel（发布与 CI 校验），**双锁必须同步** | E2 |
| 隔离 | 三平台原生沙箱：Seatbelt / Landlock+seccomp / bwrap / Windows 受限令牌 | E3 |
| 入口 | `codex` 一个二进制，27 个子命令变体 | E3 |
| 测试资产 | 39 个测试目录 / 631 个测试文件 / 457 个 `*_tests.rs` / 681 个快照 | E4 |

**最重要的一句话**：所有前端（TUI、`codex exec`、app-server、MCP server、cloud）都是同一个二进制的子命令，最终都汇聚到 `codex-core`。抓住这条主线，整个仓库就有了骨架。

**复杂度评级**：超大型项目（5.5 级 = 超大型 3 + Monorepo 1 + 多进程架构 1 + 混合语言 0.5）。

---

## 📂 关键目录速查

| 目录 | 内容 | 文件数量级 |
| ---- | ---- | ---- |
| `codex-rs/` | **Rust workspace，项目主体**，134 个 crate | 5,501 |
| `codex-rs/core/` | 智能体核心：会话、turn、工具调用、上下文（296,963 行） | — |
| `codex-rs/tui/` | ratatui 交互式终端界面（238,439 行） | — |
| `codex-rs/app-server/` | JSON-RPC 应用服务端，供 IDE / 桌面端 / SDK 接入（128,364 行） | — |
| `codex-rs/cli/` | **唯一主二进制** `codex` 的入口与子命令分发 | — |
| `codex-rs/ext/` | 12 个内建扩展 crate | — |
| `codex-rs/utils/` | 20 个通用工具 crate | — |
| `codex-rs/sandboxing/` | 三平台沙箱统一入口 + 3 个 `.sbpl` 策略 | — |
| `sdk/` | TypeScript / Python / Python-runtime 三套 SDK | 115 |
| `.github/` | CI 工作流（27 个 yml）与脚本 | 89 |
| `scripts/` | 格式化与辅助脚本（`format.py` 等） | 38 |
| `tools/` | `argument-comment-lint`（workspace 之外的独立 crate） | 31 |
| `docs/` | 仓库内文档，**极薄**（`config.md` 15 行、`sandbox.md` 3 行） | 15 |
| `dev_docs/` | **本文档体系**（不属于上游） | — |

> [!WARNING]
> `AGENTS.md:32` 禁止向 `docs/` 添加通用产品或用户文档。本体系全部产物固定在 `dev_docs/`，**任何情况下都不得迁入 `docs/`**。

---

## 🎯 场景快速导航

### 阅读理解类

| 我想…… | 去看 | 起手式 |
| ---- | ---- | ---- |
| 1. 搞清楚整体架构 | [`architecture_overview.md`](./architecture_overview.md) | 从 §2 运行时拓扑图开始 |
| 2. 知道某个 crate 是干什么的 | [`crate_map.md`](./crate_map.md) §3 | 按职责分组速查表 |
| 3. 找到某个功能在哪实现 | [`crate_map.md`](./crate_map.md) §3 → 对应 crate 目录 | `git grep -n "<关键词>" codex-rs/<crate>/src` |
| 4. 理解某个 CLI 子命令做了什么 | [`architecture_overview.md`](./architecture_overview.md) §3 | `codex-rs/cli/src/main.rs:124`（枚举）→ `:1016`（分发） |
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
| 第 4 批 | [`rules/combined/AI_RULES.md`](./rules/combined/AI_RULES.md) — AI 规则索引 | ✅ |

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
| `Cargo.toml` / `Cargo.lock` | `just bazel-lock-update`，锁文件入同一 change |
| `ConfigToml` 或嵌套配置类型 | `just write-config-schema` |
| app-server API 形状 | `just write-app-server-schema` |
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

随后在 `main.rs:1016` 起的 match 中补分发分支。

### 模式 2：trait 中的异步方法（`AGENTS.md:25-28`）

```rust
// ✅ 推荐：显式写出 future 契约
fn foo(&self, ...) -> impl std::future::Future<Output = T> + Send;

// ✅ 实现侧满足该契约时可以用 async fn
async fn foo(&self, ...) -> T { ... }

// 🚫 禁止：用 allow 绕过
#[allow(async_fn_in_trait)]
```

### 模式 3：异步追踪（`AGENTS.md:45-48`）

```rust
// ✅ 在定义处标注
#[tracing::instrument(...)]
async fn handle_turn(...) { ... }

// 🚫 不要在调用点附加 span
handle_turn(...).instrument(span)
```

加之前先检查被调用方——或它立即委托到的实现方法——是否已被标注。

### 模式 4：协议类型导出（`AGENTS.md:277`）

app-server v2 协议类型必须标注导出目标，否则生成的 TS 类型会落错目录：

```rust
#[derive(TS)]
#[ts(export_to = "v2/")]
pub struct SomeRequest { ... }
```

改完跑 `just write-app-server-schema`，再用 `just test -p codex-app-server-protocol` 验证。

### 模式 5：测试组织（`AGENTS.md:112-124`）

```
智能体逻辑变更 → 集成测试（core/suite 下，用 test_codex 搭建实例）——必须写
确需单元测试 → 放进专门的 *_tests.rs 文件
断言          → 比较整个对象的相等性，不要逐字段比
🚫 不要在主实现里留测试专用函数
```

### 模式 6：MCP 工具调用（`AGENTS.md:36`）

处理工具与工具调用的变更时，优先走 codex-rs/codex-mcp/src/mcp_connection_manager.rs，复用既有抽象，不要把逻辑层层透传。

---

## 📋 命名规范

| 对象 | 规范 | 实例 |
| ---- | ---- | ---- |
| crate 包名 | `codex-` 前缀 + kebab-case | `codex-core`、`codex-app-server-protocol` |
| crate 目录 | kebab-case，通常与包名去掉 `codex-` 前缀后一致 | `codex-rs/app-server-protocol/` |
| 例外：目录与包名不一致 | 少数 crate 存在偏差，**以 `Cargo.toml` 的 `name` 为准** | `codex-rs/windows-sandbox-rs/` → `codex-windows-sandbox`；`codex-rs/utils/path-utils/` → `codex-utils-path` |
| 工具库 crate | 统一放 `codex-rs/utils/`，包名 `codex-utils-*` | `codex-utils-absolute-path` |
| 内建扩展 crate | 统一放 `codex-rs/ext/`，包名 `codex-*-extension` | `codex-skills-extension` |
| 单元测试文件 | `*_tests.rs` | `config_tests.rs`、`manager_tests.rs` |
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
| 交互式编码会话 | `codex-tui` + `codex-core` | `codex`（无子命令） |
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

| # | 禁忌 | 出处 |
| ---: | ---- | ---- |
| 1 | 新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码 | `AGENTS.md:8-10` |
| 2 | 向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | `AGENTS.md:32` |
| 3 | 直接跑 cargo test（必须用 just 的测试任务） | `AGENTS.md:63` |
| 4 | 用 PID 杀掉正在跑的 Rust 命令 | `AGENTS.md:60` |
| 5 | 手改 `app-server-protocol/schema/typescript/` 下的生成文件 | `AGENTS.md:277,300-304` |

### ⚠️ 强烈不建议

| # | 禁忌 | 出处 / 理由 |
| ---: | ---- | ---- |
| 6 | 把新逻辑堆进 `codex-core` | `AGENTS.md:74-83`；已 296,963 行、67 个依赖 |
| 7 | 继续扩写超过 800 行的文件 | `AGENTS.md:52-53` |
| 8 | 给 `chatwidget.rs` 加新的独立方法（除非改动很小） | `AGENTS.md:59-61` |
| 9 | 用 `#[allow(async_fn_in_trait)]` 绕过 future 契约 | `AGENTS.md:28` |
| 10 | 在调用点用 `.instrument(...)` 而非在定义处标注 | `AGENTS.md:45-48` |
| 11 | 创建只被引用一次的小助手方法 | `AGENTS.md:44` |
| 12 | 为静态定义的值写测试 | `AGENTS.md:30` |
| 13 | 为已移除的逻辑写负向测试 | `AGENTS.md:31` |
| 14 | 在主实现里留测试专用函数 | `AGENTS.md:119` |
| 15 | 单次变更超过 800 行（复杂逻辑 500 行） | `AGENTS.md:125-131` |
| 16 | 常规本地运行加 `--all-features` | `AGENTS.md:65` |
| 17 | 改了依赖却不同步 Bazel 锁文件 | `AGENTS.md:37-39` |
| 18 | 加了 `include_str!` 却不补 `BUILD.bazel` 的 `compile_data` | `AGENTS.md:40-43` |

### 📌 本文档体系自身的约束

| # | 约束 |
| ---: | ---- |
| 19 | 推送只能推个人 fork，**禁止推上游 `origin`** |
| 20 | fork 是公开仓库，提交前必须跑脱敏扫描；**禁止写入任何凭证的实际值** |
| 21 | 文档中的 `related_files` 只列**实际读过**的文件 |
| 22 | 未验证的结论必须标注证据等级，**禁止把 E1 目录名推断写成 E3 事实** |

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
| 重新生成 app-server schema | `just write-app-server-schema` |
| 同步 Bazel 锁文件 | `just bazel-lock-update` |
| 校验锁文件漂移 | `just bazel-lock-check` |
| 构建发布产物 | `just build-for-release` |
| 查 crate 总数 | `cargo metadata --no-deps --format-version 1 --manifest-path codex-rs/Cargo.toml` |
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

> 例：本文「134 个 crate」是 E4（`cargo metadata` 实跑）；「四条扩展路径」当前只有 E1（目录存在性），因此各文档中**都没有**描述它们的相互关系。

---

## 🚧 未覆盖范围（显式清单）

> [!IMPORTANT]
> 1,270,789 行 Rust、134 个 crate，17 篇文档不可能覆盖全部。**下面列出的内容目前没有可靠文档，遇到时必须回去读代码。**

### 完全未深入的 crate

`codex-network-proxy`(17,064) · `codex-external-agent-migration`(15,262) · `codex-rollout-trace`(13,257) · `codex-hooks`(11,795) · `codex-apply-patch`(5,056) · `codex-connectors`(4,851) · `codex-utils-pty`(4,114) · `codex-git-utils`(3,572) · `codex-agent-graph-store`(479) · `codex-aws-auth`(375) · `codex-bwrap`(151) · `codex-v8-poc`(92) · `codex-file-watcher` · `codex-file-search` · `codex-terminal-detection` · `codex-prompts` · `codex-features` · `codex-install-context` · `codex-feedback` · 以及 `utils/` 下的 20 个工具 crate

### 已知但未验证的架构点

> 下表是**首版全部 17 篇文档完成后的最终状态**。已闭合的项保留划线记录，便于追溯。

| 事项 | 当前证据 | 状态 |
| ---- | ---- | ---- |
| ~~四条扩展路径的相互关系~~ | **E3** | ✅ 已闭合，见 [`mcp_and_extensions.md`](./mcp_and_extensions.md) §1 |
| ~~遥测的默认开关~~ | **E3** | ✅ 已闭合，见 [`observability.md`](./observability.md) §1 |
| ~~`find_codex_home` 是否重复实现~~ | **E3** | ✅ 已闭合：是薄委托，见 [`config_system.md`](./config_system.md) §5 |
| app-server ↔ exec-server 的跨 OS 传输实现 | E2 | ⏳ **未闭合**，入口见 [`app_server_protocol.md`](./app_server_protocol.md) §7 |
| `codex-core` 67 个依赖的具体用途 | E1 | ⏳ 未闭合，见 [`core_agent_loop.md`](./core_agent_loop.md) §8 |
| 配置项全集（93 个键）的逐个语义 | E4（仅键名） | ⏳ 未闭合，查 `config.schema.json` |
| turn 完整状态流转、工具调用次序 | E1 | ⏳ 未闭合，见 [`core_agent_loop.md`](./core_agent_loop.md) §8 |
| insta 快照的更新流程 | E1 | ⏳ 未闭合，见 [`testing_guide.md`](./testing_guide.md) §7 |
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

`dev_docs/_analysis/` 下有三份过程文件，**不是阅读材料**，供追溯与断点续传：

| 文件 | 用途 |
| ---- | ---- |
| `generation_plan.md` | 生成方案、17 篇文档清单、证据记录、脱敏门禁 |
| `project_analysis_report.md` | 风险、警告、疑问与建议，全部带证据等级 |
| `generation_progress.md` | 进度、两轮方案复查记录、机器检查结果、用户确认状态 |
| `health_check_report.md` | 质量验收报告 |
