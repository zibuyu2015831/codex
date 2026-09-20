---
title: Codex CLI 开发文档体系主文档
summary: openai/codex 仓库 dev_docs 开发文档体系的入口，提供项目概览、关键目录速查、12 条场景快速导航、文档索引、开发流程规范、核心代码模式、命名规范、业务模块映射、AI 编码禁忌清单与常见任务速查；本轮随 16 篇下游文档定稿对齐，修正 TUI 边界为「字面量级语法边界而非语义边界」、ext 进入 ExtensionRegistry 的是 8 个、Windows 默认无沙箱、Linux 沙箱的全盘写权限早退分支、遥测两条通路的缺省语义相反，并补入「读注释不读实现」「正则口径陷阱」「Stage::Removed ≠ 不可用」「上游记载 ≠ 当前可执行」四条新禁忌。
keywords: codex | main-doc | navigation | ai-coding-context | taboos | uncovered-scope | branch-policy | docs-only | merge-sync
scope: openai/codex 仓库 dev_docs 文档体系总入口
related_files: AGENTS.md | docs/contributing.md | codex-rs/cli/src/main.rs | codex-rs/Cargo.toml | justfile | README.md | .github/scripts/verify_tui_core_boundary.py | codex-rs/config/src/loader/mod.rs | codex-rs/features/src/lib.rs | codex-rs/protocol/src/protocol.rs
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md | dev_docs/development_workflow.md
verified_at: 2026-08-05
---

# Codex CLI 开发文档体系

> **项目**: [openai/codex](https://github.com/openai/codex) — 运行在本机的 OpenAI 编码智能体
> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **文档定位**: 兼顾**阅读理解 upstream 代码**与**在本仓库做二次开发**
> **语言**: 简体中文

---

## ⚠️ 阅读前必读

> [!CAUTION]
> **`zibuyu` 分支是纯文档分支：只增删改 `dev_docs/`，不得改动 codex 的任何源码。**
>
> 该分支的唯一目的是**学习与查验 codex 的架构和源码**，与上游代码演进解耦。`codex-rs/`、`sdk/`、`.github/`、`justfile`、根 `docs/` 等一律不动。
>
> 复核命令（应输出 `0`）：
>
> ```bash
> git diff --name-only "$(git merge-base HEAD origin/main)" HEAD -- . ':(exclude)dev_docs' | wc -l
> ```
>
> **需要改源码时，不要在本分支动手**——切回主分支并基于主分支新建分支再实现：
>
> ```bash
> git switch main && git pull && git switch -c <你的分支名>
> ```
>
> 这条规则对**人和 AI 代理同时生效**，且跨设备生效：换一台机器 clone 本仓库、切到 `zibuyu` 分支后，仍以本节为准。

> [!IMPORTANT]
> **每次 merge 主分支之后，必须同步修订 `dev_docs/`。**
>
> 本分支需要不定时 merge 主分支（`origin/main`）以跟上上游。**merge 不是终点，同步文档才是**——本体系大量引用 `path:line`、crate 数、字段数、枚举变体数这类易漂移的事实，上游代码一动，这些断言就会**静默失效**（不报错、不冲突，只是变成假的）。
>
> merge 后的标准动作：
>
> 1. 取出上游改动范围：`git diff --stat <merge 前的 origin/main> origin/main`
> 2. 映射到受影响的文档：16 篇专题 + 本文 + [`dev_docs/rules/combined/AI_RULES.md`](./rules/combined/AI_RULES.md)（映射关系见下方「🚀 文档索引」与「🏢 业务模块映射」）
> 3. 逐篇回源核验并修订，同步更新各文的 `verified_at` 与本文的**基线 commit**
> 4. 过门禁：`bash dev_docs/_analysis/gate.sh`（脱敏 / 引用可解析性 / 跨文档对账与断言账本）
>
> > 门禁全绿是**必要条件，不是充分条件**。`dev_docs/_analysis/gate.sh` 自己写明了这一点：它只覆盖结构、引用与已登记数值，断言是否与源码相符只能靠独立复核。实测基准是每轮修复会引入 6~7 个新的 HIGH 级事实错误，而它们全部是在门禁全绿状态下被独立代理发现的。方法论见 [`dev_docs/_analysis/generation_plan.md`](./_analysis/generation_plan.md)。
>
> 当前状态：基线 commit 与 `origin/main` 顶端**一致**（`bb5054fe47`，`git rev-list --count bb5054fe47..origin/main` = 0），即尚无待同步的上游改动。

> [!CAUTION]
> **仓库自带的 AGENTS.md 优先级高于本文档体系的任何内容。**
>
> 它是仓库对 AI 代理的强制规范（22,519 字节）。本体系只做落地说明与实测补充，禁止覆盖或改写其任何条款。两者有出入时，一律以仓库规范文件为准，并请修正本体系的对应内容。

> [!IMPORTANT]
> **本仓库外部代码贡献受邀制**（`docs/contributing.md` 的 `## Contributing` 一节，grep `External contributions are by invitation only`）。未受邀的 PR 会被直接关闭而不予评审。本体系中所有对代码的观察都是**长期记录**，不是面向上游的修复待办。

---

## 📊 项目概览

| 维度 | 事实 | 证据等级 |
| ---- | ---- | ---- |
| 是什么 | 运行在本机的编码智能体 CLI，同时提供 IDE 接入与桌面端 | E2 |
| 主语言 | Rust 1.95.0（edition 2024），另有 TypeScript / Python SDK | E2 |
| 规模 | 8,297 个 Git 跟踪文件（**口径：`git ls-files` 全量减去本体系自身的 `dev_docs/`**，复核 `git ls-files \| grep -vc '^dev_docs/'`）；Rust 4,631 文件 / **1,858,112 行** | E4 |
| 结构 | Cargo workspace，**154 个 crate** | E4 |
| 核心特征 | **单主二进制、多前端**；`codex-core` 是执行内核，但**不是所有前端的直接依赖** | E3 |
| 构建 | Cargo（日常开发**与发布产出**）+ Bazel（PR 合并前主验证路径），**双锁必须同步**；另有 Nix flake 与 devcontainer 两条**不参与交付**的开发环境入口 | E2 |
| 隔离 | macOS Seatbelt / Linux **bwrap + 条件安装的 seccomp** / **Windows 默认无沙箱**（`WindowsSandboxLevel` 的 `#[default]` 是 `Disabled`，显式开启后才走受限令牌或提权后端） | E3 |
| 入口 | `codex` 一个主二进制（另有 7 个随发布交付的辅助可执行文件，加 2 个仅本地/CI 产出的共 9 个），30 个子命令变体（Linux 可见 25、macOS/Windows 可见 26） | E3 |
| 测试资产 | 1148 个 `*_tests.rs` / 1359 个 insta 快照 | E1 |

**最重要的一句话**：所有前端都是同一个二进制的子命令，但**它们到达 `codex-core` 的路径不同**——`codex exec`、app-server、MCP server、cloud 直接依赖 `codex-core`；而 **TUI 没有指向 `codex-core` 的直接依赖边，也不直接 import 它**（CI 强制），会话/turn 能力经 `codex-app-server-client` 接入。

> [!WARNING]
> **这是一条语法边界，不是语义边界。** CI 强制的全部内容就是四条字面量级判定：`codex-rs/tui/Cargo.toml` 的依赖表里不出现键名 `codex-core`，加上三条逐行正则 `\bcodex_core::` / `\buse\s+codex_core\b` / `\bextern\s+crate\s+codex_core\b`（`.github/scripts/verify_tui_core_boundary.py` 的 `FORBIDDEN_PACKAGE` 与 `FORBIDDEN_SOURCE_PATTERNS`）。逐行正则不做语法解析——**注释与字符串字面量里出现同样会挂**。
>
> 由此推出三条**被明确允许**的现实：
>
> 1. **传递依赖不受限，且是官方逃生舱。** 脚本的报错文案自己指定了替代通道：`"...startup gaps belong behind codex_app_server_client::legacy_core."` 该模块直接 `pub use codex_core::config::*;`，TUI 中有 **93 处 / 40 个文件**在用。
> 2. **`codex-core` 照样链接进 TUI**。最短路径 `codex-tui → codex-app-server-client → codex-core`，另有 `codex-cloud-config`、`codex-utils-oss` 两条 normal 依赖。
> 3. **禁令只针对 `codex-core` 这一个包名**。TUI 直接依赖 `codex-core-plugins`（另一个 crate，不在禁令字符串内），并有绕过 app-server-client 的生产路径：`codex_utils_oss::ensure_oss_provider_ready`、`codex_cloud_config::cloud_config_bundle_loader_for_storage`。
>
> 本体系在这一句上错过三次：首版写反（说所有前端汇聚到 core），第二轮改成「能力必须先有协议方法」漏了 `legacy_core`，第三轮改成「不链接 core」漏了传递依赖。**校验脚本的原文是 `does not depend on or import codex-core directly`**——限定词一直都在。详见 [`tui_guide.md`](./tui_guide.md) §0.1–§0.2。

> [!CAUTION]
> **`codex-tui` 不得直接依赖或 import `codex-core`，这是 CI 机器强制的架构不变量。**
>
> 校验脚本：`.github/scripts/verify_tui_core_boundary.py`，文件头写明 `"""Verify codex-tui does not depend on or import codex-core directly."""`，由 `.github/workflows/repo-checks.yml` 在每个 PR 上执行；扫描范围是 `codex-rs/tui/**/*.rs` 全目录（含 `tests/` 与 `src/bin/`），不只是 `src/`。
>
> TUI 经 `codex-app-server-client` 接入，有两种客户端实现：`InProcessAppServerClient`（同进程）与 `RemoteAppServerClient`（连远端 app-server）；在 TUI 眼里落点有三态 `Embedded` / `LocalDaemon` / `Remote`。详见 [`architecture_overview.md`](./architecture_overview.md) §5 — 进程边界与跨操作系统部署、[`tui_guide.md`](./tui_guide.md) §6 — 与 app-server 的关系。
>
> **例外（同样重要）**：见上方 WARNING 的三条。所以边界约束的是**依赖边与 import 的字面量**，不是「core 的一切都必须经协议方法抵达」。详见 [`tui_guide.md`](./tui_guide.md) §0.2 — 但存在一个官方逃生舱。
>
> 本文档体系首版曾把「所有前端都汇聚到 `codex-core`」写成主干论断并画入依赖图——**方向恰好与这条被强制的边界相反**。若你在旧版本中读到该表述，以本节为准。

**复杂度评级**：超大型项目（5.5 级 = 超大型 3 + Monorepo 1 + 多进程架构 1 + 混合语言 0.5）。

---

## 📂 关键目录速查

| 目录 | 内容 | 文件数量级 |
| ---- | ---- | ---- |
| `codex-rs/` | **Rust workspace，项目主体**，154 个 crate | 5,501 |
| `codex-rs/core/` | 智能体核心：会话、turn、工具调用、上下文（296,963 行） | — |
| `codex-rs/tui/` | ratatui 交互式终端界面（238,439 行） | — |
| `codex-rs/app-server/` | JSON-RPC 应用服务端，供 IDE / 桌面端 / SDK 接入（128,364 行） | — |
| `codex-rs/cli/` | **主二进制** `codex` 的入口与子命令分发 | — |
| `codex-rs/ext/` | 12 个 `ext/*` crate。其中 **8 个依赖 `extension-api`，且恰好就是被注册进 `ExtensionRegistry` 的 8 个**；另 3 个（`items` / `agent` / `connectors`）各走各的机制，`ext/items` 反而是 `codex-core` 的**生产依赖** | — |
| `codex-rs/utils/` | **23 个**通用工具 crate | — |
| `codex-rs/sandboxing/` | 三平台沙箱统一入口 + 3 个 `.sbpl` 策略 | — |
| `codex-rs/vendor/` | **vendored bubblewrap C 源码**（上游 v0.11.2 完整 drop），Linux 默认沙箱的实际载体 | 51（其中 `bubblewrap/` 占 50，`git ls-files` 口径） |
| `codex-rs/docs/` | 仓库自带开发者文档：`codex-rs/docs/protocol_v1.md` / `codex-rs/docs/bazel.md` / `codex-rs/docs/codex_mcp_interface.md` | 3 |
| `codex-cli/` | **npm 分发包 `@openai/codex`**（注意：与 Cargo 包名 `codex-cli`＝目录 `codex-rs/cli` 同名，容易搜错） | 7 |
| `sdk/` | TypeScript / Python / Python-runtime 三套 SDK | 115 |
| `.github/` | CI 工作流（30 个 yml）与脚本 | 89 |
| `scripts/` | 格式化与辅助脚本（`scripts/format.py` 等） | 38 |
| `tools/` | `argument-comment-lint`（workspace 之外的独立 crate） | 31 |
| `docs/` | 仓库内文档，**极薄**（`docs/config.md` 15 行、`docs/sandbox.md` 3 行） | 15 |
| `dev_docs/` | **本文档体系**（不属于上游） | — |

> [!WARNING]
> `AGENTS.md` 顶部规则列表（grep `product or user-facing documentation`）禁止向 `docs/` 添加通用产品或用户文档。本体系全部产物固定在 `dev_docs/`，**任何情况下都不得迁入 `docs/`**。

---

## 🎯 场景快速导航

### 阅读理解类

> 下表每条都写成「文档 §章节号 — 章节标题」，`dev_docs/_analysis/cross_doc_consistency_checker.py` 会校验章节号与标题是否仍然对得上，下游插入新章节导致编号顺延时会报 `section_ref_drifted`。

| 我想…… | 去看 | 起手式 |
| ---- | ---- | ---- |
| 1. 搞清楚整体架构 | [`architecture_overview.md`](./architecture_overview.md) §2 — 运行时拓扑 | 先看拓扑图，再读 §3.4 的 8 个随行可执行文件 |
| 2. 知道某个 crate 是干什么的 | [`crate_map.md`](./crate_map.md) §3 — 按职责分组速查表 | 12 个分组表，先定分组再定 crate |
| 3. 找到某个功能在哪实现 | [`crate_map.md`](./crate_map.md) §3 — 按职责分组速查表 | `git grep -n "<关键词>" codex-rs/<crate>/src` |
| 4. 理解某个 CLI 子命令做了什么 | [`architecture_overview.md`](./architecture_overview.md) §3 — 入口层：一个二进制 | `codex-rs/cli/src/main.rs:124`（枚举）→ `:1001` 的 `match subcommand`（分发；`:1002` 为 `None` 默认 TUI） |
| 5. 搞清楚数据往哪里发 | [`architecture_overview.md`](./architecture_overview.md) §8 — 外部服务边界 | 六类通路表；隐私细节再转 [`observability.md`](./observability.md) §8 — 数据边界小结 |
| 6. 知道配置和凭证存在哪 | [`architecture_overview.md`](./architecture_overview.md) §7 — 配置与凭证：CODEX_HOME | `CODEX_HOME`，默认 `~/.codex`；数据库目录另有一条链，见 [`config_system.md`](./config_system.md) §6 — CODEX_HOME 解析 |

### 二次开发类

| 我想…… | 去看 | 起手式 |
| ---- | ---- | ---- |
| 7. 搭好环境跑起来 | [`development_workflow.md`](./development_workflow.md) §1 — 环境准备 | `just install` → `just codex` |
| 8. 知道新代码该放哪个 crate | [`crate_map.md`](./crate_map.md) §5 — 新代码归属决策树 | 默认答案：**不要放进 `codex-core`**；新建 crate 还要过 `.github/scripts/verify_cargo_workspace_manifests.py` 六条门禁 |
| 9. 改完代码后该做什么 | [`development_workflow.md`](./development_workflow.md) §3.1 — 改完代码后的固定动作 | `just fmt` → `just test -p <crate>` |
| 10. 评估我的改动会波及谁 | [`crate_map.md`](./crate_map.md) §4 — 依赖热点与影响面 | 查被依赖数排名；注意该表是**含 dev-deps** 的影响面口径 |
| 11. 改了依赖 / 配置 / 协议后要补跑什么 | [`development_workflow.md`](./development_workflow.md) §2.5 — 代码生成 | `just bazel-lock-update` 等 |
| 12. 提交前检查有没有漏项 | [`development_workflow.md`](./development_workflow.md) §9 — 提交前自检清单 | 自检清单 |

---

## 🚀 文档索引

### 本体系文档

| 批次 | 文档 | 状态 |
| ---- | ---- | ---- |
| 第 1 批 | `AI_Coding_Context.md`（本文） | ✅ |
| 第 1 批 | [`architecture_overview.md`](./architecture_overview.md) — 架构总览 | ✅ |
| 第 1 批 | [`crate_map.md`](./crate_map.md) — 154 个 crate 地图 | ✅ |
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

> **17 篇正式文档 + AI 规则索引已全部生成，并于 2026-08-05 完成一轮双轨交叉审查 + 修后复核 + 主文档对齐定稿。** 每篇末尾都有「本文未覆盖的内容」表，列出该主题下仍需回去读代码的部分。
>
> **本文是最后定稿的一篇**——它汇总下游结论，因此**任何冲突一律以下游专题文档为准**，并请回来修正本文。

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
| 新建 crate / 改任意 `codex-rs/**/Cargo.toml` | `.github/scripts/verify_cargo_workspace_manifests.py` 的六条门禁（含**禁止任何 `[features]`**、禁止 `optional = true`），见 [`crate_map.md`](./crate_map.md) §5 — 新代码归属决策树 |
| 改 clippy lint 配置 | Cargo workspace lints 与 Bazel clippy flags 须双边同步（`.github/scripts/verify_bazel_clippy_lints.py` 机检） |

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
> **根因**：`ts-rs` 与 `schemars` 只在该 crate 的 `[dev-dependencies]` 里，生产构建下 `#[derive(TS, JsonSchema)]` 被 `codex-app-server-protocol-noop-macros` 换成空实现——所以真正跑 ts-rs 的路径**必须以 `cfg(test)` 编译**，生成器只能是 `#[ignore]` 测试而不可能是 `[[bin]]`。
>
> **而且这是一处循环陈旧**：那条校验测试自己的 `panic!` 文案（`codex-rs/app-server-protocol/src/schema_fixtures_tests.rs`，两处）也写着 "Run `just write-app-server-schema` to overwrite with your changes."——**测试挂了以后照它说的做只会再挂一次**。
>
> 可用的生成入口是 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`（它内部用 `cargo test` 作为「代码生成宿主」驱动那个 `#[ignore]` 函数，**不是在跑测试**，与禁忌 3 不冲突；该 workaround 本身未实测，产物请自行核对）。详见 [`app_server_protocol.md`](./app_server_protocol.md) §0 与 §6。

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
| 云任务 | `codex-cloud-tasks` 系列 **3 个** crate（`cloud-tasks` / `cloud-tasks-client` / `cloud-tasks-mock-client`；`codex-cloud-config` **不属于**这条能力，它是配置加载层） | `codex cloud` ⚠️ |
| 桌面端 | 由 CLI 拉起安装器 | `codex app`（仅 macOS/Windows） |
| 诊断 | `codex-features`（102 个 `Feature` 变体的开关体系） | `codex doctor` / `debug` / `features` |
| 配置体系 | `codex-config` | `~/.codex/config.toml`（93 个 schema 顶层键） |
| 模型接入 | `codex-model-provider`、`codex-ollama`、`codex-lmstudio` | 配置文件 |
| 可观测性 | `codex-otel`、`codex-analytics`、`codex-rollout-trace`、`codex-feedback` | — |
| 用户侧生命周期钩子 | `codex-hooks`（10 种事件，`codex-core` 的生产依赖，**扩展体系之外的第五条路径**） | `config.toml` 的 hook 声明 <!-- ref-exempt: 指 CODEX_HOME 下的运行时用户配置文件，非仓库内文件 --> |

⚠️ = 实验性　🔒 = 隐藏子命令。详见 [`crate_map.md`](./crate_map.md) §3 — 按职责分组速查表。

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
| 8 | 把新逻辑堆进 `codex-core` | `## The codex-core crate`（标题含反引号，直接按纯文本 grep 会 0 命中，改 grep `resist adding code to codex-core`）；已 296,963 行、**66 个 workspace 依赖（含 dev 去重口径；仅 normal 为 58）** |
| 9 | 继续扩写超过 800 行的文件 | 顶部规则列表，grep `add new functionality in a new module` |
| 10 | 给 `codex-rs/tui/src/chatwidget.rs` 加新的独立方法（除非改动很小） | 顶部规则列表，grep `codex-rs/tui/src/chatwidget.rs` |
| 11 | 用 `#[allow(async_fn_in_trait)]` 绕过 future 契约 | 顶部规则列表，grep `async_fn_in_trait` |
| 12 | 在调用点用 `.instrument(...)` 而非在定义处标注 | 顶部规则列表，grep `tracing::instrument` |
| 13 | 创建只被引用一次的小助手方法 | 顶部规则列表，grep `helper method` |
| 14 | 为静态定义的值写测试 | 顶部规则列表，grep `statically defined` |
| 15 | 为已移除的逻辑写负向测试 | 顶部规则列表 |
| 16 | 在主实现里留测试专用函数 | `### Test authoring guidance`，grep `Avoid test-only functions` |
| 17 | 单次变更超过 800 行（复杂逻辑 500 行） | `### Change size guidance (800 lines)` |
| 18 | 常规本地运行加 `--all-features` | 顶部规则列表，grep `--all-features`。⚠️ **这条规则本身已经过时**：workspace crate features 被 `.github/scripts/verify_cargo_workspace_manifests.py` **制度性禁止**（白名单只有 `code-mode` 与 `v8-poc` 的 `sandbox` feature），`justfile:78-79` 的注释直接写着 "Workspace crate features are banned, so there should be no need to add `--all-features`."。**`AGENTS.md` 把它写成「偶尔要用」，与仓库现状矛盾——不要照抄** |
| 19 | 改了依赖却不同步 Bazel 锁文件 | 顶部规则列表，grep `bazel-lock-update` |
| 20 | 加了 `include_str!` 却不补 `BUILD.bazel` 的 `compile_data` | 顶部规则列表，grep `include_str!` |
| 21 | 在测试里改动进程环境变量 | `### Test assertions` 附近，grep `environment variables` |
| 22 | 用 `assert_cmd::Command::cargo_bin` / `env!("CARGO_MANIFEST_DIR")` | `### Spawning workspace binaries in tests (Cargo vs Bazel)`——会破坏 Bazel runfiles |

### 🧨 取证方式本身的禁忌（本轮双轨审查新增）

> 上面两张表管的是「不要写什么代码」。这张表管的是「**不要用什么方式确认事实**」——本轮暴露的错误几乎全部出在取证方式上，而不是出在读得不够多。

| # | 禁忌 | 具体案例与判据 |
| ---: | ---- | ---- |
| **T1** | **读注释、README、帮助文本就下结论** | `codex-rs/config/src/loader/mod.rs` 的函数文档注释把配置层优先级**排反了**：`:96-111` 那段按升序把 `admin: managed preferences` 列在第一位（最低），而**同一文件紧邻的** `:82-94` 又把它列在最后（最高）。真实实现是 macOS MDM 走 `LegacyManagedConfigTomlFromMdm`，precedence **50，全场最高**。同段注释还把 cwd 层路径写成 `${PWD}/config.toml`，实际是 `${PWD}/.codex/config.toml`。**在这里「读注释确认」必然得到错误答案**——唯一可靠的判据是追踪 `layers.push(...)` 的实际调用序列与 `precedence()` 的返回值。见 [`config_system.md`](./config_system.md) §2 — 配置文件的发现顺序与信任门控 |
| **T2** | **信任自己临时写的计数脚本，不先自证** | 两次实例：① `Op` 枚举数错成 **16**（真值 26）——括号深度脚本在**更新深度之后**才判定变体，带结构体字段的变体（如 `UserInput { .. }`）被整体跳过；② `thread/*` 方法数错成 **57**（真值 60）——正则字符类写成 `[A-Za-z/]` 漏了下划线，恰好漏掉 `thread/inject_items`、`thread/increment_elicitation`、`thread/decrement_elicitation` 三条。**计数脚本必须先在已知答案的小样本上自证，或换一条独立口径交叉验证**（`Op` 的交叉口径是 `grep -oE 'Op::[A-Za-z]+' codex-rs/core/src/session/handlers.rs \| sort -u \| wc -l`，同为 26） |
| **T3** | **把 `Stage::Removed` 读成「不可用」** | `Stage` 在 `codex-rs/features/src/lib.rs` 中**唯一的行为性使用**是 `emit_metrics`（`:447-451`）里的过滤——**只影响指标上报**。真正把用户配置落到开关上的 `apply_map`（`:466`）经 `feature_for_key`（`:637`）分支，**全程不检查 `stage`**。所以 `Stage::Removed` 的 feature **照样能被用户在 `[features]` 里开启**，也照样出现在 `codex features list` 里。判断「死开关」的**唯一可靠判据**是穷举 `grep -rn --include='*.rs' 'Feature::Xxx' codex-rs/`，看它是否只出现在「枚举定义 + `FeatureSpec` + 测试」里（`Feature::RemoteControl` 就是这样一个：2 处命中，生产读取点为 0）。见 [`experimental_surfaces.md`](./experimental_surfaces.md) §7.4 — codex-features |
| **T4** | **把上游文档 / `justfile` / `AGENTS.md` 的记载当成当前可执行** | 已确认的三处陈旧：① `just write-app-server-schema` 跑不通（`codex-app-server-protocol` 无 bin target），而 `AGENTS.md`（grep `write-app-server-schema`）、`justfile` 的同名 recipe **以及那条校验测试自己的 `panic!` 文案**（`codex-rs/app-server-protocol/src/schema_fixtures_tests.rs`）都在推荐它——**循环陈旧，照它说的做只会再挂一次**；② `AGENTS.md`（grep `--all-features`）的建议与「workspace crate features 被制度禁止」矛盾（见禁忌 18）；③ `AGENTS.md` 指的 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` <!-- ref-exempt: 本行正在说明该路径不存在，引用不可解析即为要表达的事实 --> 不存在，实为 `codex-rs/codex-mcp/src/connection_manager.rs`。**引用任何命令前先跑一遍；引用任何路径前先 `ls` 一下** |
| **T5** | **符号 `pub` + 名字贴切 + 位置显眼 ⇒ 它生效了** | 三条独立的反例：`ConfigLayerSource::Mdm`（precedence 0，全仓生产构造点为 0，只有 `match` 分支与测试）；`ConfigToml::profiles` 与整个 `ConfigProfile`（40+ 字段，排除测试后全仓只有 3 处命中，无任何生产代码读它）；`install_filesystem_landlock_rules_on_current_thread`（注释自述 "currently unused"）。**判据永远是「谁在构造它 / 谁在调用它」，不是「它长什么样」** |
| **T6** | **引用行号前不看文件总行数** | 实例：`codex-rs/core/src/otel_init.rs` 全文 110 行，上一稿却引了 `:112` 与 `:119`。**`wc -l` 一下是成本最低的一道自检** |

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
> 例：「154 个 crate」是 E4（`cargo metadata` 解析 workspace 后的权威输出）；「`utils/` 下 26 个目录」是 E1（数目录）；「Rust 4,631 个文件」是 E1（数文件），只有其行数 1,858,112 因经 `wc` 统计可算 E2 口径。

> [!CAUTION]
> **最常见的错误是把 E1 的目录名/依赖名推断写成 E3 事实。** 本体系有两次实例可供警惕：
>
> 1. 「12 个 `ext/*` 全部依赖 `extension-api`」——实测是 **8/12**。⚠️ **连这条勘误本身也曾被写错**：早先说错因是「`grep -rl` 把 `extension-api` 自己数了进去」，但那样只会得到 **9** 而不是 12；`ext/agent` / `ext/connectors` / `ext/items` 三份清单里 `codex-extension-api` 出现次数均为 **0**，grep 口径解释不了差额。**真实错因是把「`ext/` 下共有 12 个 crate」直接归纳成「12 个都依赖它」——一次完全未取证的推断。** 见 [`crate_map.md`](./crate_map.md) §3.8 — 扩展面
> 2. 「Linux 沙箱用 Landlock」——因为 `Cargo.toml` 里有 `landlock` 依赖、文件名叫 `landlock.rs`。实际该机制已废弃（`Stage::Deprecated`），默认走 bwrap，且默认分支的注释明写 "This path **never falls back** to legacy Landlock on failure." <!-- ref-exempt: 复述致错线索，泛指依赖名与文件名本身 -->
>
> 依赖存在 ≠ 依赖生效；类型定义存在 ≠ 该分支被构造；**而「解释错因」本身也需要取证**。

---

## 🚧 未覆盖范围（显式清单）

> [!IMPORTANT]
> 1,270,789 行 Rust、134 个 crate，17 篇文档不可能覆盖全部。**下面列出的内容目前没有可靠文档，遇到时必须回去读代码。**

### 完全未深入的 crate

`codex-network-proxy`(17,064) · `codex-external-agent-migration`(15,262) · `codex-apply-patch`(5,056) · `codex-connectors`(4,851) · `codex-utils-pty`(4,114) · `codex-git-utils`(3,572) · `codex-agent-graph-store`(479) · `codex-aws-auth`(375) · `codex-v8-poc`(92) · `codex-file-watcher` · `codex-file-search` · `codex-terminal-detection` · `codex-prompts` · `codex-install-context` · `codex-exec-server-test-support` · 以及 `utils/` 下的 23 个工具 crate

> **本轮已从上表移除四项**（不再是「零覆盖」，但仍未逐模块展开）：`codex-rollout-trace`(13,257) → [`observability.md`](./observability.md) §6.3；`codex-hooks`(11,795) → [`mcp_and_extensions.md`](./mcp_and_extensions.md) §7 与 [`observability.md`](./observability.md) §6；`codex-bwrap`(151) 与 `codex-rs/vendor/bubblewrap/` → [`tools_and_sandbox.md`](./tools_and_sandbox.md) §3.2；`codex-feedback` → [`observability.md`](./observability.md) §6.6。

### 曾登记为「零覆盖」、本轮已补写的系统级缺口

> 下表**不再是待办**，保留是为了让读过旧版的人知道去哪找。中间一列是本轮补写的落点。

| 子系统 | 现在去哪读 | 补写后的关键结论 |
| ---- | ---- | ---- |
| **Realtime 语音 / WebSocket 会话面** | [`experimental_surfaces.md`](./experimental_surfaces.md) §7.3、[`core_agent_loop.md`](./core_agent_loop.md) §4.7 | 合计约 **7,512 行**（不是「上万行」）；6 个 `experimental_realtime_*` 配置键（占全仓 10 个 `experimental_*` 键的 6 个）；门控是 `Feature::RealtimeConversation`，**默认关闭且有生产读取点** |
| **`codex-features` 门控机制** | [`experimental_surfaces.md`](./experimental_surfaces.md) §7.4 | `Feature` 枚举 **102 个变体**。⚠️ **成熟度必须按 `FeatureSpec` 的 `stage:` 字段数，不能按源码注释分段数**——两者大面积不一致；且 `Stage` 只影响指标上报（见禁忌 T3） |
| **Nix 构建路径** | [`build_and_release.md`](./build_and_release.md) §1.4 | 只是开发便利设施，**不产出发布产物、不被任何 CI 引用**；且 Rust 版本**不钉死**（Cargo/Bazel/CI 三处都钉在 1.95.0，Nix 与 devcontainer 不钉） |
| **容器 / devcontainer 开发环境** | [`build_and_release.md`](./build_and_release.md) §1.4 | 两条 profile：贡献者用与「安全客户」用；后者以 setuid 装 bubblewrap、关掉 Docker 外层 seccomp/AppArmor 以便 bwrap 能建内层沙箱 |
| **guardian 安全子系统** | [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7 | 审批链路的自动评审后端；`ApprovalReviewer::{Guardian, User}` 二选一由 `strict_auto_review_enabled_for_turn()` 决定；**去掉沙箱的重试在严格模式下必须重新过 Guardian** |
| **项目层配置的键黑名单** | [`config_system.md`](./config_system.md) §2 | 项目层有**两道正交闸门**：11 个顶层配置键 + 1 个嵌套键**无条件剥离**（不看信任状态），信任门控只是第二道 |
| **`sqlite_home` 解析** | [`config_system.md`](./config_system.md) §6 | 四级链条 `requirements > config.toml > $CODEX_SQLITE_HOME > CODEX_HOME`——**配置文件压过环境变量，与多数 CLI 相反** |
| **MCP 传输配置** | [`mcp_and_extensions.md`](./mcp_and_extensions.md) §6 | 只有 `Stdio` 与 `StreamableHttp` 两种，由填 `command` 还是填 `url` 二选一决定，字段不能混填 |
| **Skills 的发现机制** | [`mcp_and_extensions.md`](./mcp_and_extensions.md) §5 | 扫描根沿**配置层栈**拼出，分 `Repo`/`User`/`System`/`Admin` 四种 scope；每根最多 2000 个 skill 目录、深度上限 6 层 |
| **`experimental_api` 标注机制** | [`app_server_protocol.md`](./app_server_protocol.md) §4 | 协议层的第五种实验性标记方式，走 inventory 链接期注册 |

### 仍然未覆盖的系统级缺口

| 子系统 | 入口 | 说明 |
| ---- | ---- | ---- |
| **记忆（memories）子系统** | `codex-rs/memories/`、`ext/memories`、`thread/memoryMode/set` | 仅在 crate 表与扩展清单中占一行 |
| **协作模式（collaboration mode）** | `codex-collaboration-mode-templates`、`codex-rs/app-server-protocol/src/protocol/v2/collaboration_mode.rs`、`codex-rs/tui/src/collaboration_modes.rs` | 多处提及文件名，无一处解释是什么 |
| **多智能体协作** | `codex-rs/core/src/session/multi_agents.rs`、`codex-rs/core/src/tools/handlers/multi_agents_v2/`、`ext/agent`、`codex-agent-graph-store` | 跨 5 个 crate；[`core_agent_loop.md`](./core_agent_loop.md) §9 亦登记为未覆盖 |
| **网络代理与 MITM CA 的完整链路** | `codex-rs/network-proxy/`(17,064) | [`tools_and_sandbox.md`](./tools_and_sandbox.md) §10 亦登记为未覆盖 |

### 已知但未验证的架构点

> 下表是**本轮定稿后的状态**。已闭合的项保留划线记录；被审查推翻的结论单独标注。

| 事项 | 当前证据 | 状态 |
| ---- | ---- | ---- |
| ~~四条扩展路径的相互关系~~ | **E2/E3** | ⚠️ 已闭合但**首版结论有错**：不是 12/12 依赖 `extension-api`，而是 8/12；**进入 `ExtensionRegistry` 的是 8 个**，另 3 个各走各的机制。见 [`mcp_and_extensions.md`](./mcp_and_extensions.md) §1 |
| ~~遥测的默认开关~~ | **E3** | ⚠️ 已闭合但**首版结论有错**：debug 构建下 analytics 默认仍发网络，两条通路是耦合的，且**缺省语义相反**（见下方 CAUTION）。见 [`observability.md`](./observability.md) §1 |
| ~~`find_codex_home` 是否重复实现~~ | **E3** | ✅ 已闭合：是薄委托，见 [`config_system.md`](./config_system.md) §6 — CODEX_HOME 解析 |
| ~~insta 快照的更新流程~~ | **E2** | ✅ 已闭合：`AGENTS.md` 的 `### Snapshot tests` 一节有完整流程。**首版记为「无任何记载」是漏读**，见 [`testing_guide.md`](./testing_guide.md) §7 |
| ~~turn 完整状态流转~~ | **E3** | ✅ 已闭合：`submission_loop` → `SessionTask` → `codex-rs/core/src/tasks/regular.rs` 的 turn 循环，见 [`core_agent_loop.md`](./core_agent_loop.md) §2 |
| ~~审批与沙箱的先后次序~~ | **E3** | ✅ 已闭合：审批 → 选沙箱 → 尝试 → 拒绝后升级重试（不重新审批）；**违规判定与记录在执行层而非 orchestrator**。见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §7 |
| ~~Linux 沙箱的主备切换条件~~ | **E3** | ✅ 已闭合：**两道**判据——全盘写权限且无受管代理时**整体跳过 bwrap** 的早退分支，之后才轮到 `use_legacy_landlock` 选路。见 [`tools_and_sandbox.md`](./tools_and_sandbox.md) §3.1 |
| app-server ↔ exec-server 的跨 OS 传输实现 | E2 | ⏳ **未闭合**，入口见 [`app_server_protocol.md`](./app_server_protocol.md) §8 |
| `codex-core` 依赖的**具体用途**（含 dev 去重 66 / 仅 normal 58） | E1 | ⏳ 未闭合；口径已核实，见 [`core_agent_loop.md`](./core_agent_loop.md) §1.1 与 [`crate_map.md`](./crate_map.md) §4 |
| 配置项全集（93 个 schema 顶层键）的逐个语义 | E2（schema 键名） | ⏳ 未闭合，查 `codex-rs/core/config.schema.json`；注意 serde 实际接受 96 个字段，差额 3 个带 `#[schemars(skip)]` |
| Realtime 会话面的音频数据流向 | E1 | ⏳ 未闭合（表面本身已覆盖，见上表） |
| Python SDK 的运行时行为 | E2（本机 Python 3.9.6 低于要求的 3.10，无法实跑） | ⏳ 待环境升级，见 [`sdk_guide.md`](./sdk_guide.md) §9 |

> [!CAUTION]
> **遥测这条最容易被误读，主文档在此给出定论**（完整证据见 [`observability.md`](./observability.md) §1 与 §5）：
>
> 1. **`[otel] exporter` 是日志导出器，不是「通用导出器」**——它是**唯一**会外发 `user.email`、`user.account_id` 与用户提示词的通道；`trace_exporter` 走的 `trace_event!` 刻意剔除了这三项。默认 `None`。
> 2. **`[analytics] enabled` 一个键喂两条通路，但缺省语义相反**：OTEL metrics 侧是 `unwrap_or(default_analytics_enabled)`，analytics 埋点侧是 `!= Some(false)`。**净效果——app-server / remote-control 上不写配置时，Statsig 指标关闭，但 analytics 埋点仍在外发。** 「app-server 默认关遥测」只对了一半，要让埋点停下必须**显式**写 `[analytics] enabled = false`（`None` ≠ `false`）。
> 3. **没有任何遥测 opt-out 环境变量**——`DO_NOT_TRACK` 等一概零命中，关闭只能改 `config.toml` <!-- ref-exempt: 指 CODEX_HOME 下的运行时用户配置文件，非仓库内文件 -->。

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
| 定稿日期 | 2026-08-05（16 篇下游文档双轨交叉审查 + 修后复核完成后，本文与 `AI_RULES.md` 最后对齐） |
| 上游迭代频率 | 高（基线 commit 与分析同日，近 5 次提交均为当日/近日 PR） |

**高漂移区**（上游一变，本体系就可能过期）：

| 位置 | 影响的文档 |
| ---- | ---- |
| `codex-rs/Cargo.toml` | `crate_map.md` 全文 |
| 仓库根的 AI 规范文件 | `development_workflow.md`、`dev_docs/rules/combined/AI_RULES.md`、本文「AI 编码禁忌」 |
| `codex-rs/cli/src/main.rs` | `architecture_overview.md` §3 |
| `codex-rs/app-server-protocol/` | `app_server_protocol.md` |
| `codex-rs/features/src/lib.rs` | `experimental_surfaces.md` §7.4、本文禁忌 T3 |
| `codex-rs/protocol/src/protocol.rs` | `core_agent_loop.md` §2.2（`Op` 26 / `EventMsg` 80） |
| `justfile` | `development_workflow.md` §2、`build_and_release.md` §3 |

**核对办法**：每篇文档 frontmatter 记录 `verified_at`，正文记录基线 commit。拉取上游后，对照上表跑一次 diff，只更新受影响的文档。

---

## 📝 生成过程记录

`dev_docs/_analysis/` 下有过程文件与自建工具，**不是阅读材料**，供追溯、断点续传与机器校验：

| 文件 | 用途 |
| ---- | ---- |
| `generation_plan.md` | 生成方案、17 篇文档清单、证据记录、脱敏门禁 |
| `project_analysis_report.md` | 风险、警告、疑问与建议，全部带证据等级 |
| `generation_progress.md` | 进度、方案复查记录、机器检查结果、用户确认状态 |
| `health_check_report.md` | 质量验收报告，记录历轮独立审查查出的事实错误与复核结论 |
| `dev_docs/_analysis/claim_ledger.jsonl` | **断言账本**：每条可复验事实带一条可复现命令，供跨文档对账与仓库真值对账 |
| `dev_docs/_analysis/cross_doc_consistency_checker.py` | 跨文档数值一致性 + `§N` 引用漂移 + 标题计数 vs 表格行数 + `--verify-repo` 真值对账 |
| `dev_docs/_analysis/ref_checker.py` / `dev_docs/_analysis/redact_scan.sh` / `dev_docs/_analysis/normalize_refs.py` / `dev_docs/_analysis/gate.sh` | 引用可解析性、脱敏扫描、引用规范化、门禁聚合 |

> [!IMPORTANT]
> **本文档体系经历过一次失败的自验收。** 首版判定通过（5 项框架 checker 全绿、7 项质量维度全 ✅），随后由独立代理从源码重新推导，查出成批的 HIGH 级事实错误；本轮又用双轨交叉审查在**已经修过一遍**的文稿里查出新一批。
>
> **两轮的共同教训不是「读得不够」，而是「取证方式不对」**——具体清单见上方「🧨 取证方式本身的禁忌」六条（T1–T6）。使用本体系时，对**架构定性类结论**（谁依赖谁、哪个机制默认生效、哪条是主路径、某个数字怎么数出来的）请保持警惕并回查源码。
>
> **所有数值类断言以 `dev_docs/_analysis/claim_ledger.jsonl` 的可复现命令为准，不要抄本文的历史数字。**
