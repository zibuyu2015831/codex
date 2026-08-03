---
title: Codex CLI 开发文档体系生成方案
summary: 记录 openai/codex 仓库首次生成 dev_docs 开发文档体系的完整方案，包含项目检测结果、规模与复杂度评估、项目定位不可破坏约束、AI 与外部服务边界、17 份子文档清单、四批执行计划和证据验证记录；已含第 2 轮复查更正与用户确认结果，并追加第二轮独立审查推翻首版验收的记录，同步更正 CLI 子命令口径为 27 个变体、analytics 网络投递并非默认关闭、core/tests/suite 改用文件数口径、insta 快照流程在上游已有完整记载，且全文不再按行号引用 AGENTS.md。
keywords: codex | dev-docs | generation-plan | rust-monorepo | cli-agent | phase1 | acceptance-fail
scope: openai/codex 仓库 dev_docs 文档体系首次生成方案 (仓库根目录)
related_files: codex-rs/Cargo.toml | codex-rs/cli/src/main.rs | codex-rs/model-provider-info/src/lib.rs | codex-rs/analytics/src/client.rs | AGENTS.md | justfile | package.json
dependencies: dev_docs/_analysis/project_analysis_report.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-03
---

# Codex CLI - AI 文档生成方案

## 📋 方案元信息

- **项目名称**: Codex CLI（仓库 `openai/codex`，monorepo 包名 `codex-monorepo`）
- **项目类型**: CLI 工具项目（主）+ 库/SDK 项目（次）+ AI/LLM 应用（特征），分层混合 Monorepo
- **主要技术栈**: Rust 1.95.0 (edition 2024) / TypeScript / Python 3.10+ / Cargo + Bazel 双构建 / pnpm workspace
- **方案创建日期**: 2026-08-03
- **分析基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`（2026-08-03，`Capture rollout budget units from response usage (#36641)`）
- **当前分支**: `zibuyu`
- **文档语言**: 中文（zh-CN，用户明确指定）
- **预计执行耗时**: 18-26 小时（分 4 批，跨多个会话）

---

## 🎯 任务复杂度评估 (Complexity Assessment)

### 复杂度评级

**综合评级**: ⭐⭐⭐⭐⭐ (5 星 / 超大型项目策略)

### 原因分析

1. **代码规模**

   - Git 跟踪文件总数: 5913 个（基线 commit `bb5054fe47` 口径，`git ls-tree -r --name-only bb5054fe47 | wc -l`）。本体系自身产物落盘并提交后，`git ls-files | wc -l` 会随之增长（提交 `8224f7c034` 后为 5916），全部规模统计一律以基线 commit 口径为准
   - 扫描器统计: 5910 文件 / 809 目录 / 最大深度 9（`project_scanner.py --mode summary --exclude-standard`，`complexity_level: advanced`）
   - Rust: 2858 文件 / 1,270,789 行
   - TypeScript: 665 文件 / 9,865 行（其中 641 个为 `codex-rs/app-server-protocol/schema/typescript/` 下的自动生成协议类型）
   - Python: 137 文件 / 38,486 行
   - Markdown: 178 文件 / 17,419 行
   - 影响: **高** — 单会话不可能穷尽阅读，必须分批并显式记录未覆盖范围

2. **架构复杂度**

   - Cargo workspace 成员: **134 个 crate**（`cargo metadata --no-deps` 权威计数，E4）。其中 `codex-rs/Cargo.toml` 的 `[workspace] members` 显式列出 128 项；差额 6 个为 `chatgpt`、`message-history`、`windows-sandbox-rs`（仅以 `[workspace.dependencies]` path 依赖参与）与 `app-server/tests/common`、`core/tests/common`、`mcp-server/tests/common`（测试辅助 crate）。另有 workspace 之外的独立 crate `tools/argument-comment-lint`
   - 多前端单核心：`codex` 单一二进制通过 clap 子命令分发到 TUI / exec / app-server / mcp-server / responses-api-proxy / cloud 等入口。`codex-rs/cli/src/main.rs:124` 的 `Subcommand` 枚举共 **27 个变体**（3 个 `#[clap(hide = true)]`，1 个仅 macOS/Windows 条件编译）
   - 多进程协作：app-server、exec-server 可跨操作系统分离部署（AGENTS.md「## Platform Support」）
   - 四层扩展点：`ext/*` 内建扩展、`core-plugins`、`skills`、MCP 客户端/服务端
   - 三平台沙箱实现：Seatbelt(macOS) / Landlock+bwrap(Linux) / windows-sandbox-rs
   - 影响: **高**

3. **依赖复杂度**
   - 双构建系统：Cargo（`codex-rs/Cargo.lock`）与 Bazel（`MODULE.bazel` 16,677 字节 + `MODULE.bazel.lock` 1,547,127 字节），CI 校验锁文件漂移
   - 三套包管理：cargo / pnpm(10.33.0) / uv-pip（`sdk/python`）
   - `patches/` 目录含 20+ 个第三方补丁
   - 影响: **高**

### 复杂度因子计算

```
基础级别: 超大型 (3 级)  ← 5913 文件 > 500
+ Monorepo (+1)          ← pnpm-workspace.yaml + Cargo workspace + Bazel
+ 多进程/类微服务 (+1)    ← app-server / exec-server / mcp-server / responses-api-proxy 独立进程
+ 混合语言 (+0.5)        ← Rust / TypeScript / Python / Starlark / Shell / PowerShell (≥3 种)
= 5.5 级 → 已超出最高级别，采用超大型项目策略并额外收紧批次粒度
```

### 预计工作量

- **总计**: 18-26 小时
- **阶段一 (项目分析与方案)**: 2-3 小时（本方案，已完成）
- **阶段二 (第 1 批：主文档 + 架构 + crate 地图 + 开发流程)**: 5-7 小时
- **阶段三 (第 2 批：核心运行时 5 篇)**: 5-7 小时
- **阶段四 (第 3 批：集成与工程化 5 篇)**: 4-6 小时
- **阶段五 (第 4 批：实验性表面 + 可观测性 + SDK + AI Rules + 首版验收)**: 4-6 小时

### 风险点

- [x] **大文件**: 存在多个远超 800 行的文件，必须分段读取。实测 Top 5：`codex-rs/tui/src/bottom_pane/chat_composer.rs` 12,616 行、`codex-rs/core/src/config/config_tests.rs` 12,127 行、`codex-rs/core/src/session/tests.rs` 11,434 行、`codex-rs/tui/src/app/tests.rs` 7,520 行、`codex-rs/tui/src/resume_picker.rs` 6,681 行
- [x] **复杂依赖**: 134 个 crate 的依赖分层需通过 `codex-rs/Cargo.toml` 的 `[workspace.dependencies]` 路径映射反推，不得凭目录名臆测
- [ ] **文档不足**: 仓库自身产品文档托管在外部站点（`docs/config.md` 仅 15 行且指向 developers.openai.com），架构层面缺少仓库内说明，这正是本文档体系的价值点
- [x] **特殊架构**: 存在跨 OS 的 app-server/exec-server 分离、双构建系统、四层扩展点，均需代码级确认后再写入文档
- [x] **其他**: 上游高速迭代（单日多个 PR 合入），文档需标注基线 commit 并依赖路径 C 增量更新维持时效

---

## 🤝 交互策略 (Interaction Strategy)

### 1. 阶段性确认点

**何时请求用户审查**:

- [x] ✅ **完成阶段一后**: 请求用户审查项目检测结果、子文档清单与复杂度评估（当前所处位置）
- [ ] ✅ **完成第 1 批后**: 请求用户审查主文档 + `architecture_overview.md` + `crate_map.md` 质量，确认写作深度与颗粒度后再继续
- [ ] ✅ **发现重大架构理解偏差时**: 立即暂停并与用户沟通

### 2. 大文件处理策略

**处理原则**:

- 超过 800 行的文件先用 `grep -n "^pub fn\|^impl\|^pub struct\|^pub enum"` 获取结构概览，再按需分段读取
- Rust 大文件优先读取 `lib.rs` / `mod.rs` 的 `pub use` 导出清单来确定公开 API 边界
- 测试文件（`*_tests.rs`、`tests/suite/*`）仅在编写 `testing_guide.md` 时读取，不纳入架构分析

### 3. 不确定信息处理

**遇到以下情况时，必须询问用户**:

- 文档服务对象与深度定位（见"需要人工确认的项目特性"第 1 项）
- 实验性表面（cloud-tasks / desktop app / v8-poc / code-mode）的文档优先级（见第 3 项）

原第 2 项「`dev_docs/` 是否纳入版本管理」已由用户行动解决（提交至个人 fork），不再需要询问。

**不应该做的**:

- ❌ 臆测 crate 职责（必须以 `Cargo.toml` 依赖关系 + `lib.rs` 导出为准）
- ❌ 编造代码示例
- ❌ 使用占位符代替实际数据

### 4. 复杂模块处理

**策略**:

- 先用 mermaid 绘制 crate 依赖分层图（数据源：`codex-rs/Cargo.toml` 的 `[workspace.dependencies]` 路径映射 + 各 crate `Cargo.toml` 的 `[dependencies]`）
- 每批产出后先交付索引级内容，再回填细节
- `codex-core`（296,963 行）单独拆解为 `core_agent_loop.md` 与 `tools_and_sandbox.md` 两篇，不合并

---

## 📐 文档生成原则 (Documentation Principles)

### 1. 代码示例要求

**✅ 必须遵守**:

- 所有代码示例必须来自真实项目代码，注明 `文件路径:行号`
- Rust 示例保留原始 `format!` 内联变量、`match` 穷尽等仓库风格，不做改写
- 复杂示例附中文注释说明

**格式要求**:

```markdown
### 示例标题

**文件位置**: `codex-rs/model-provider-info/src/lib.rs:38`

\`\`\`rust
// 实际代码
\`\`\`
```

### 2. 链接格式规范

- **仓库内文件**: 使用相对仓库根的路径，如 `codex-rs/core/src/lib.rs`
- **跨文档引用**: 使用相对路径 `./crate_map.md`
- **外部资源**: 使用完整 URL（如 developers.openai.com 官方文档）

### 3. 可视化要求

**必须使用 mermaid 图表的场景**:

- 架构图：`codex` 二进制的子命令分发与多进程拓扑
- 依赖图：crate 分层依赖（protocol → core → 前端）
- 流程图：一次 turn 的完整生命周期、审批与沙箱决策链、登录流程
- 状态图：会话（thread）状态与 rollout 持久化

### 4. Markdown 格式要求

- 代码块指定语言类型（rust / typescript / python / toml / bash）
- 使用表格组织 crate 清单、配置项、子命令
- 使用 `> [!IMPORTANT]` 强调不可破坏约束
- 遵循仓库已有的 `.markdownlint-cli2.yaml` 与 `.prettierrc.toml` 约定

---

## 🎯 第一阶段：项目基础分析（已完成）

### 1.1 项目类型识别

**分析结果**:

```
项目类型: CLI 工具项目（主）+ 库/SDK 项目（次）+ AI/LLM 应用（特征）
形态:     分层混合 Monorepo（代码按 codex-rs/ · sdk/ · codex-cli/ 清晰分离）
主语言:   Rust 1.95.0，edition 2024
CLI 框架: clap + clap_complete（codex-rs/cli/Cargo.toml，codex-rs/cli/src/main.rs:1-5）
TUI 框架: ratatui（codex-rs/tui，样式约定见 codex-rs/tui/styles.md）
构建系统: Cargo（主） + Bazel（CI 校验，MODULE.bazel）+ just（任务入口，justfile）
包管理:   cargo / pnpm 10.33.0 / uv-pip
分发渠道: 独立安装脚本、npm @openai/codex、Homebrew cask、GitHub Releases
```

**验证方式**:

- [x] 检查 `codex-rs/Cargo.toml` 的 `[workspace]` 与 `[workspace.package]`
- [x] 检查 `package.json`、`pnpm-workspace.yaml`、`MODULE.bazel`、`justfile`
- [x] 检查 `codex-rs/cli/Cargo.toml` 的 `[[bin]] name = "codex"`
- [x] 扫描 `codex-rs/` 134 个 crate 目录

---

### 1.2 项目规模统计

**统计结果**:

```
Git 跟踪文件总数: 5913 个
├─ Rust  文件: 2858 个 (1,270,789 行)
├─ TypeScript: 665 个 (9,865 行，其中 641 个为生成的协议 schema)
├─ Python 文件: 137 个 (38,486 行)
├─ TOML   文件: 153 个 (6,107 行)
├─ Markdown  : 178 个 (17,419 行)
├─ Shell     : 36 个 (5,238 行)
├─ PowerShell: 6 个 (2,049 行)
├─ Starlark  : 8 个 (1,145 行)
└─ JavaScript: 3 个 (367 行)

Rust 代码量按 crate 排名（Top 10）:
├─ codex-rs/core/            296,963 行
├─ codex-rs/tui/             238,439 行
├─ codex-rs/app-server/      128,364 行
├─ codex-rs/exec-server/      39,311 行
├─ codex-rs/core-plugins/     37,038 行
├─ codex-rs/app-server-protocol/ 30,946 行
├─ codex-rs/cli/              26,629 行
├─ codex-rs/protocol/         23,132 行
├─ codex-rs/config/           21,034 行
└─ codex-rs/thread-store/     20,404 行

测试资产（全深度扫描口径，详见"测试资产扫描结果"章节）:
├─ 测试目录: 39 个，合计 631 个测试文件
├─ *_tests.rs 内联单元测试: 457 个
├─ insta 快照 (*.snap): 681 个
├─ 最大两处: codex-rs/core/tests/（174）、codex-rs/app-server/tests/（121）
├─ TypeScript SDK 测试: sdk/typescript/tests/（8 个文件，jest）
└─ Python SDK 测试: sdk/python/tests/（18 个文件，pytest）
```

**验证方式**:

- [x] `git ls-files | wc -l`
- [x] `git ls-files "*.rs" | xargs wc -l | awk '$2=="total"{s+=$1} END{print s}'`
- [x] `python3 AI-Coding-Context/tools/py/project_scanner.py . --mode summary --exclude-standard`
- [x] `git ls-files "*.snap" | wc -l`

**⚠️ 人工验证点**:

- Rust 行数含测试与快照断言，若需"生产代码行数"需另行扣除 457 个 `*_tests.rs`
- TypeScript 行数被生成代码稀释，`sdk/typescript/src` 实际仅 10 个手写文件

---

### 1.3 目录结构分析

**核心目录清单**（1-2 级）:

```
codex/（仓库根）
├── codex-rs/               - Rust workspace，134 个 crate，项目主体（2842 个 .rs；全仓 2858）
│   ├── core/               - 智能体核心：会话、turn、工具调用、上下文管理（296,963 行）
│   ├── tui/                - ratatui 交互式终端界面（238,439 行）
│   ├── app-server/         - JSON-RPC 应用服务端，供 IDE/桌面端接入（128,364 行）
│   ├── app-server-protocol/- 协议定义 + TypeScript schema 生成（30,946 行）
│   ├── exec-server/        - 命令执行服务端，可与 app-server 跨 OS 分离（39,311 行）
│   ├── cli/                - clap 子命令分发与 codex 二进制入口（26,629 行）
│   ├── exec/               - 非交互式 `codex exec` 执行器（9,621 行）
│   ├── protocol/           - 前后端共享协议类型（23,132 行）
│   ├── config/             - 配置加载、profile、config.toml 类型（21,034 行）
│   ├── sandboxing/         - Seatbelt / Landlock / bwrap / Windows 沙箱策略
│   ├── linux-sandbox/      - Linux 沙箱可执行入口
│   ├── windows-sandbox-rs/ - Windows 沙箱实现（19,173 行）
│   ├── login/              - ChatGPT OAuth / API key / device code 登录（13,798 行）
│   ├── ext/                - 内建扩展：agent/goal/guardian/mcp/memories/skills/web-search 等 12 个
│   ├── core-plugins/       - 插件运行时（37,038 行）
│   ├── skills/             - Skills 能力包与样例
│   ├── codex-mcp/ mcp-server/ rmcp-client/ - MCP 客户端与服务端
│   ├── rollout/ rollout-trace/ thread-store/ state/ - 会话持久化与回放
│   ├── otel/ analytics/    - 可观测性与埋点
│   ├── utils/              - 25 个通用工具 crate
│   └── vendor/ patches 相关 - 第三方定制
├── sdk/                    - 对外 SDK
│   ├── typescript/         - @openai/codex-sdk（10 个手写源文件，jest 测试）
│   ├── python/             - openai_codex（requires-python >=3.10，pytest）
│   └── python-runtime/     - Python 侧 codex 二进制分发
├── codex-cli/              - npm 包 @openai/codex 的启动器（bin/codex.js + 打包脚本）
├── docs/                   - 仓库文档（15 篇，多数为指向官方站点的短文）
├── scripts/                - 仓库级构建/发布/格式化脚本（Python 为主）
├── .github/workflows/      - 27 个 CI 工作流（yml；另有 README.md/Dockerfile.bazel/zstd 非 yml 条目）
├── bazel/ patches/ third_party/ - Bazel 规则、依赖补丁、第三方源
├── tools/                  - 仓库自有工具（argument-comment-lint 等）
├── AGENTS.md               - 仓库对 AI 代理的强制规范（22,519 字节）★ 核心事实源
├── justfile                - 统一任务入口（fmt/fix/test/bench/schema 等）
└── AI-Coding-Context -> <本地工作区>/AI-Coding-Context  （框架软链接，已排除）
```

**验证方式**:

- [x] `ls codex-rs/`、`ls docs/`、`find sdk -maxdepth 3 -type d`
- [x] `ls .github/workflows/`
- [x] 逐 crate 统计 `git ls-files "<dir>*.rs" | xargs wc -l`

**⚠️ 人工验证点**:

- `AI-Coding-Context` 是指向框架的软链接，**必须**在所有扫描与统计中排除（已在 `--exclude-standard` 下验证生效）
- `codex-rs/vendor/`、`third_party/`、`patches/` 为第三方内容，不纳入架构描述

---

### 1.3B 项目定位与不可破坏约束

| constraint | evidence | documentation_impact | ai_rules_impact | status |
| --- | --- | --- | --- | --- |
| 本地运行的编码智能体（"runs locally on your computer"） | `README.md:1` | `architecture_overview.md` 必须区分本地进程与远端 API 调用边界 | 不得把本地执行路径改造为默认云端执行 | confirmed |
| 沙箱 + 审批是核心安全边界 | `codex-rs/sandboxing/src/`（seatbelt.rs / landlock.rs / bwrap.rs / windows.rs + 3 个 .sbpl 策略文件）、`codex-rs/linux-sandbox/`、`codex-rs/windows-sandbox-rs/` | `tools_and_sandbox.md` 必须单独成文并说明三平台差异 | 不得绕过或削弱沙箱/审批链路 | confirmed |
| 禁止改动 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` / `CODEX_SANDBOX_ENV_VAR` 相关代码 | AGENTS.md 顶部规则列表（CODEX_SANDBOX 红线条目） | `tools_and_sandbox.md` + AI Rules 必须显式复述该红线 | 硬禁止：任何情况下不得新增或修改相关代码 | confirmed |
| 禁止向 docs 目录添加通用产品或用户文档（例外：app-server API 文档） | AGENTS.md 顶部规则列表（docs/ 条目） | 本体系产物落在仓库根 `dev_docs/`，禁止放入 `docs/` | 禁止把 dev_docs 内容迁移进 `docs/` | confirmed |
| 外部代码贡献仅限受邀（未受邀 PR 直接关闭） | `docs/contributing.md:3-17` | `development_workflow.md` 必须写明该治理前提；质量建议一律标注为"长期建议"而非待办修复 | AI 不得自行发起面向上游的 PR 流程建议 | confirmed |
| 禁止继续向 `codex-core` 堆叠新功能，应新建 crate | AGENTS.md「## The codex-core crate」 | `crate_map.md` + `core_agent_loop.md` 必须给出"新代码该放哪个 crate"的决策指引 | 新增功能前必须先评估是否可放入 core 之外的 crate | confirmed |
| Rust 模块目标 <500 LoC，>800 LoC 应新建模块；高触碰大文件点名清单 | AGENTS.md 顶部规则列表（Avoid large modules 条目） | `development_workflow.md` 必须列出点名文件并给出实测行数对照 | AI 不得继续在 `tui/src/chatwidget.rs`、`chat_composer.rs` 等文件堆叠新方法 | confirmed |
| 单次变更 ≤800 行（复杂逻辑 ≤500 行） | AGENTS.md「### Change size guidance (800 lines)」 | `development_workflow.md` 记录变更规模门槛与拆分策略 | AI 产出的改动需自检规模并主动提出分阶段方案 | confirmed |
| 必须同时支持 Linux / macOS / Windows（除非显式 OS 专属） | AGENTS.md「## Platform Support」 | 所有涉及路径、进程、沙箱的文档必须给出三平台差异说明 | 不得引入单平台方案而不标注 | confirmed |
| 依赖变更需同步刷新 `MODULE.bazel.lock`（CI 校验漂移） | AGENTS.md 顶部规则列表（Bazel 锁条目） | `build_and_release.md` 必须写明 Cargo/Bazel 双锁同步流程 | 改 `Cargo.toml`/`Cargo.lock` 必须同 PR 更新 Bazel 锁 | confirmed |
| Apache-2.0 开源许可 | `LICENSE`、`README.md` 末段、`sdk/typescript/package.json` `"license": "Apache-2.0"` | 文档中的代码引用需保持许可归属清晰 | 不得引入不兼容许可的依赖 | confirmed |

**说明**：上表所有约束均来自仓库内文件，证据等级 E2/E3，无需用户确认。其中 AGENTS.md 顶部规则列表（docs/ 条目） 直接决定了本文档体系的落盘位置，是本方案的硬性前置。

---

### 1.3C AI/外部服务边界

| boundary | evidence | data_sent_or_stored | user_authorization_or_config | documentation_impact | status |
| --- | --- | --- | --- | --- | --- |
| OpenAI Responses API（默认 provider 基址） | `codex-rs/model-provider-info/src/lib.rs:257`（`"https://api.openai.com/v1"`） | 用户 prompt、代码片段、文件内容、工具调用结果 | API key 登录（`codex login --api-key`），或环境变量 | `auth_and_providers.md` + `core_agent_loop.md` 必须说明发送内容边界 | confirmed |
| ChatGPT 后端 Codex 通道 | `codex-rs/model-provider-info/src/lib.rs:38`（`CHATGPT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"`） | 同上，走 ChatGPT 订阅额度 | `codex login` 选择 Sign in with ChatGPT | `auth_and_providers.md` 说明两条鉴权路径差异 | confirmed |
| OAuth 授权服务 | `codex-rs/login/src/server.rs:59`（`DEFAULT_ISSUER = "https://auth.openai.com"`）、`codex-rs/login/src/success_page.rs:7`（`https://chatgpt.com/codex/open-app`） | OAuth code、redirect_uri、JWT（含 `https://api.openai.com/auth` claim） | 用户浏览器交互授权，本地回调端口 1455 | `auth_and_providers.md` 绘制登录时序图 | confirmed |
| Personal Access Token 账户 API | `codex-rs/login/src/auth/personal_access_token.rs:11`（`PROD_AUTHAPI_BASE_URL = "https://auth.openai.com/api/accounts"`） | 访问令牌 | `codex login --with-access-token` / stdin 读取 | `auth_and_providers.md` 说明令牌来源与作用域 | confirmed |
| 凭证本地持久化 | `codex-rs/config/src/types.rs:109`（`Persist credentials in CODEX_HOME/auth.json`）、`:113`（keyring 优先，回退文件）、`:129`（`CODEX_HOME/.credentials.json`）、`codex-rs/keyring-store/` | OAuth token / API key | 由配置项选择 keyring 或文件 | `auth_and_providers.md` 必须写明存储位置与权限风险，**不得复述任何真实凭证值** | confirmed |
| 本地第三方模型运行时（Ollama / LM Studio） | `codex-rs/ollama/`、`codex-rs/lmstudio/` | prompt 与上下文发送至本机服务 | 用户配置 provider | `auth_and_providers.md` 区分默认在线路径与用户配置的本地路径 | confirmed |
| MCP 外部服务器 | `codex-rs/codex-mcp/`、`codex-rs/mcp-server/`、`codex-rs/rmcp-client/`、`codex-rs/ext/mcp/` | 由用户配置的 MCP server 决定，可能包含文件内容与工具参数 | `codex mcp` 子命令 + config.toml 显式配置 | `mcp_and_extensions.md` 必须说明"用户自带服务器"的数据外流边界 | confirmed |
| 遥测：OTLP 导出 + Statsig 指标 | `codex-rs/otel/src/otlp.rs`、`codex-rs/otel/src/config.rs:16`（注释："Keep the built-in Statsig default off in debug builds"）、`:90`（`Statsig metrics ingestion exporter using Codex-internal defaults`）、`:113`（测试 `statsig_default_metrics_exporter_is_disabled_in_debug_builds`） | 指标与追踪事件 | 由 `OtelSettings` / `StatsigMetricsSettings` 配置 | `observability.md` 必须完整核实 release 构建下的默认开关链路与可关闭方式 | needs_code_verification |
| 本地埋点采集（analytics） | `codex-rs/analytics/src/client.rs` 的 `queue: (analytics_enabled != Some(false))`（opt-out 语义）、`AnalyticsEventsDestination::from_base_url_and_capture_file`、`pub fn disabled()` | 事件入队后按目的地分派：仅当 debug 构建且捕获文件环境变量已设置且非空时写本地文件，否则走 HTTP 上报 | `analytics_enabled` 配置项 | `observability.md` 必须区分"采集开关"与"投递目的地"，**不得**把日志文案 `network delivery is disabled` 当成全局结论 | confirmed |
| Codex Cloud 任务 | `codex-rs/cloud-tasks/`、`codex-rs/cloud-tasks-client/`、`codex-rs/backend-client/`、CLI 子命令 `Cloud`（`codex-rs/cli/src/main.rs:195-197`，标注 `[EXPERIMENTAL]`） | 云端任务元数据与变更 diff | 用户显式执行 `codex cloud` | `auth_and_providers.md` 或 `observability.md` 说明该实验性通道 | confirmed |
| 安装器下载源 | `README.md`（`https://releases.openai.com/codex`，回退 GitHub Releases，可用 `CODEX_INSTALLER_USE_RELEASES_OPENAI_COM=false` 强制） | 无用户数据上行 | 环境变量可控 | `build_and_release.md` 记录分发链路 | confirmed |

**要求落实说明**：

- `needs_code_verification` 两项属于**代码可回答**的问题，按框架准入规则**不进入用户确认清单**，而是列为第 2/3 批的"下一步代码级核查"动作（见"下一步代码级核查"章节）。
- 本项目默认路径即为在线调用 OpenAI 服务，不属于"离线优先/无服务端"型项目；README 的 "runs locally" 指**智能体进程与代码操作在本地**，而非"不联网"。文档中必须写成这一双路径边界，禁止简化为"完全本地"。

---

### 1.4 业务模块识别

**模块清单**（按运行时职责划分）:

| 模块名称 | 目录位置 | 主要文件 | 实测代码量 | 关联技术 |
| -------- | -------- | -------- | ---------- | -------- |
| CLI 入口与子命令分发 | `codex-rs/cli` | `src/main.rs`、`src/lib.rs` | 26,629 行 | clap / clap_complete / arg0 dispatch |
| 智能体核心 | `codex-rs/core` | `src/lib.rs`、`src/codex_thread.rs`、`src/client.rs`、`src/compact.rs` | 296,963 行 | 会话、turn、上下文管理、compact |
| 工具与执行 | `codex-rs/core/src/tools`、`codex-rs/tools`、`codex-rs/core/src/unified_exec`、`codex-rs/shell-command` | `core/src/exec.rs`、`core/src/exec_policy.rs` | 见 core | 工具注册、命令规范化、执行策略 |
| 沙箱与审批 | `codex-rs/sandboxing`、`codex-rs/linux-sandbox`、`codex-rs/windows-sandbox-rs`、`codex-rs/execpolicy`、`codex-rs/shell-escalation` | `sandboxing/src/manager.rs`、`seatbelt_base_policy.sbpl`、`landlock.rs`、`bwrap.rs` | 19,173 行（仅 windows-sandbox-rs） | Seatbelt / Landlock / bubblewrap / Windows |
| 交互式 TUI | `codex-rs/tui` | `src/app.rs`、`src/chatwidget.rs`、`src/bottom_pane/chat_composer.rs`、`styles.md` | 238,439 行 | ratatui / insta 快照 |
| 非交互执行 | `codex-rs/exec`、`codex-rs/exec-server`、`codex-rs/exec-server-protocol` | `exec/src/lib.rs` | 9,621 + 39,311 行 | `codex exec`、跨 OS 执行服务 |
| 应用服务端 (App Server) | `codex-rs/app-server`、`app-server-protocol`、`app-server-daemon`、`app-server-client`、`app-server-transport` | `app-server/README.md`、`app-server-protocol/src/protocol/v2.rs` | 128,364 + 30,946 行 | JSON-RPC v2 / ts-rs schema 生成 |
| 配置系统 | `codex-rs/config`、`codex-rs/core/src/config` | `config/src/config_toml.rs`、`config/src/types.rs`、`config/src/state.rs`、`core/src/config/mod.rs` | 21,034 行 | config.toml / CODEX_HOME / profile 分层 |
| 鉴权与模型提供方 | `codex-rs/login`、`model-provider-info`、`model-provider`、`models-manager`、`chatgpt`、`keyring-store`、`aws-auth` | `login/src/server.rs`、`model-provider-info/src/lib.rs` | 13,798 行（login） | OAuth / API key / device code / keyring |
| 会话持久化与回放 | `codex-rs/rollout`、`rollout-trace`、`thread-store`、`state`、`message-history` | `rollout/src/`、`thread-store/src/` | 13,940 + 13,257 + 20,404 + 19,744 行 | SQLite / rollout 文件 / resume·fork·archive |
| MCP 集成 | `codex-rs/codex-mcp`、`mcp-server`、`rmcp-client`、`ext/mcp` | `codex-mcp/src/mcp_connection_manager.rs` | 14,560 + 19,361 行 | Model Context Protocol 双向 |
| 扩展与插件 | `codex-rs/ext/*`（12 个）、`core-plugins`、`plugin`、`skills`、`core-skills` | `core-plugins/src/manager.rs`、`skills/src/assets/samples/` | 37,038 行（core-plugins） | 扩展 API / 插件市场 / Skills |
| 可观测性 | `codex-rs/otel`、`analytics`、`feedback`、`response-debug-context` | `otel/src/config.rs`、`analytics/src/client.rs` | 12,116 行（analytics） | OTLP / Statsig / 本地埋点 |
| 网络与代理 | `codex-rs/http-client`、`websocket-client`、`network-proxy`、`responses-api-proxy`、`uds`、`stdio-to-uds` | `network-proxy/src/` | 17,064 行（network-proxy） | HTTP / WS / UDS / 反向代理 |
| SDK | `sdk/typescript`、`sdk/python`、`sdk/python-runtime` | `sdk/typescript/src/`、`sdk/python/src/openai_codex/` | 10 个 TS 手写文件 / 17 个 Python 文件 | jest / pytest / tsup |
| 打包与分发 | `codex-cli`、`scripts/codex_package`、`.github/workflows/*release*` | `codex-cli/bin/codex.js`、`codex-cli/scripts/build_npm_package.py` | 367 行 JS | npm / Homebrew / GitHub Releases |
| 通用工具库 | `codex-rs/utils/*`（25 个 crate） | `utils/cargo-bin`、`utils/path-utils`、`utils/fuzzy-match` 等 | — | 跨 crate 复用 |

**识别依据**:

```
模块划分基于 codex-rs/Cargo.toml [workspace.dependencies] 的 128 条 path 映射，
配合 codex-rs/cli/src/main.rs:1-90 的 use 语句（反映一级依赖关系）
以及 codex-rs/cli/src/main.rs:123-200 的 Subcommand 枚举（反映用户可见能力面）。
```

**验证方式**:

- [x] 每个模块均对应真实目录，路径已通过 `ls` / `git ls-files` 验证存在
- [x] 代码量为 `git ls-files "<dir>*.rs" | xargs wc -l` 实测值
- [ ] 打开各模块主文件验证职责描述（**留待正式生成阶段逐篇执行**）

**⚠️ 人工验证点**:

- 模块划分为运行时职责视角，与 Cargo crate 边界不是一一对应（如"工具与执行"横跨 core 内部模块与独立 crate）
- 尚未逐一打开各 crate 的 `lib.rs` 确认导出边界，正式生成时必须补齐

---

### 1.5 架构特点识别

1. **单二进制多前端（arg0 dispatch + clap 子命令）**

   - **识别依据**: `codex-rs/cli/Cargo.toml` 中 `[[bin]] name = "codex" path = "src/main.rs"`；`codex-rs/cli/src/main.rs:9-10` 引入 `codex_arg0::Arg0DispatchPaths` / `arg0_dispatch_or_else`；`:123-200` 的 `Subcommand` 枚举包含 Exec / Review / Login / Logout / Mcp / Plugin / McpServer / AppServer / RemoteControl / App / Completion / Update / Doctor / Sandbox / Debug / Execpolicy / Apply / Resume / Archive / Delete / Unarchive / Fork / Cloud 等
   - **影响范围**: 全部前端入口
   - **实现方式**: 单一 `codex` 可执行文件，通过 argv[0] 与子命令双重分发；无子命令时透传给交互式 TUI（`main.rs:93` 注释与 `:117` 的 `interactive: TuiCli` flatten）

2. **协议先行的分层：protocol → core → 前端**

   - **识别依据**: `codex-rs/protocol/src/protocol.rs`（6,349 行）为共享协议；`codex-rs/app-server-protocol/` 通过 ts-rs 生成 `schema/typescript/v2/` 下 550 个 TS 类型；AGENTS.md「## App-server API Development Best Practices」 规定了 app-server API 的命名、序列化与 schema 再生成流程（`just write-app-server-schema`）
   - **影响范围**: app-server、SDK、IDE/桌面端集成
   - **实现方式**: Rust 类型为单一事实源，TypeScript 类型由构建产出，wire 格式统一 camelCase（config RPC 例外，见 AGENTS.md「### Core Rules」）

3. **跨操作系统的进程分离（app-server ↔ exec-server）**

   - **识别依据**: AGENTS.md「## Platform Support」（"Codex supports running connected app-server and exec-server on different operating systems"）；`codex-rs/exec-server-protocol/`、`codex-rs/app-server-transport/`、`codex-rs/uds/`、`codex-rs/stdio-to-uds/` 的存在
   - **影响范围**: 远程/容器化执行场景、集成测试（`build_with_auto_env()`）
   - **实现方式**: 独立协议 crate + UDS/stdio 传输层

4. **三平台原生沙箱**

   - **识别依据**: `codex-rs/sandboxing/src/` 同时包含 `seatbelt.rs`、`landlock.rs`、`bwrap.rs`、`windows.rs`，以及 3 个策略文件 `seatbelt_base_policy.sbpl`、`seatbelt_network_policy.sbpl`、`restricted_read_only_platform_defaults.sbpl`；另有独立 crate `linux-sandbox`、`windows-sandbox-rs`、`bwrap`
   - **影响范围**: 所有命令执行路径
   - **实现方式**: 按平台选择沙箱后端，配合 `execpolicy` 与审批预设（`utils/approval-presets`）

5. **双构建系统（Cargo + Bazel）**

   - **识别依据**: `codex-rs/Cargo.toml` 与 `MODULE.bazel`（16,677 字节）/ `MODULE.bazel.lock`（1,547,127 字节）并存；AGENTS.md 顶部规则列表（Bazel 锁与 compile_data 条目） 要求依赖变更同步 `just bazel-lock-update`，并提醒 `include_str!`/`sqlx::migrate!` 需在 `BUILD.bazel` 补 `compile_data`；`.github/workflows/bazel.yml` 存在
   - **影响范围**: 全仓库构建与 CI
   - **实现方式**: Cargo 为本地主路径，Bazel 用于 CI 与部分 lint（`just argument-comment-lint`）

6. **四层可扩展性**

   - **识别依据**: `codex-rs/ext/`（agent / connectors / extension-api / goal / git-attribution / guardian / image-generation / items / memories / mcp / skills / web-search 共 12 个 crate）、`codex-rs/core-plugins/`（37,038 行）、`codex-rs/skills/`（含 `src/assets/samples/` 下 plugin-creator、skill-creator、skill-installer 样例）、MCP 客户端/服务端
   - **影响范围**: 功能扩展与第三方集成
   - **实现方式**: 内建扩展 crate、插件运行时、Skills 资产、MCP 协议四条并行路径

7. **会话可恢复性（rollout + thread-store）**

   - **识别依据**: CLI 子命令 `Resume` / `Fork` / `Archive` / `Unarchive` / `Delete`（`codex-rs/cli/src/main.rs:180-193`）；crate `rollout`、`rollout-trace`、`thread-store`、`state`；`codex-rs/cli/src/main.rs:27-29` 引入 `REDUCED_STATE_FILE_NAME`、`replay_bundle`、`StateRuntime`
   - **影响范围**: 会话生命周期、调试回放
   - **实现方式**: rollout 文件 + 状态库持久化，支持恢复与分叉

**验证方式**:

- [x] 每个特点均提供了具体文件路径，多数附行号
- [x] 未出现无代码依据的推断
- [ ] 特点 2/3/6 的实现细节需在正式生成阶段读取对应 `lib.rs` 深入确认

**⚠️ 人工验证点**:

- 特点 3（跨 OS 进程分离）目前证据为 `AGENTS.md` 陈述 + crate 存在性（E2+E1），正式文档中需补 E3 源码证据
- 特点 6 的四条扩展路径之间的关系（是否可组合、优先级）尚未验证，正式生成时必须核实

---

## ⚠️ 代码脱敏规范

> [!IMPORTANT]
> **第 2 轮复查升级**：本体系产物已提交并推送至**公开** fork `zibuyu2015831/codex`（`isPrivate: false`）。`dev_docs/` 下的每一个字节都是公开可检索内容，且 GitHub 会长期缓存，删除提交不保证内容立即消失。本节由"生成时的写作规范"升级为**每批提交前必须执行的硬性门禁**。

**适用性说明**：本项目为 Apache-2.0 开源仓库，源码中不含生产凭证。脱敏工作聚焦以下三类：

1. **公开的服务端点保留**：`https://api.openai.com/v1`、`https://chatgpt.com/backend-api/codex`、`https://auth.openai.com` 属于公开技术信息，按框架规范（"公开 API 端点"可保留）予以保留。
2. **凭证值一律不复述**：`auth.json`、`.credentials.json`、keyring 条目、JWT、OAuth code、API key 只写**变量名、配置项名与文件路径**，绝不写示例值或可复制的完整令牌。测试固件中的假 token（如 `codex-rs/login/src/token_data_tests.rs` 中的样例）不得引入文档。
3. **本地绝对路径脱敏**：分析环境的本地绝对路径（形如 `/Users/<用户名>/...`）禁止出现在 `dev_docs/` 的任何文件中（含 `_analysis` 过程文件）；框架软链接一律以 `AI-Coding-Context/`（相对路径）指代。此外禁止写入主机名、内网地址与个人邮箱。

### 脱敏检查清单

- [x] 已确认不复述任何 `auth.json` / keyring / JWT 实际值
- [x] 已确认保留公开服务端点（技术事实）
- [x] 已确认 `dev_docs/` 全部文件中不出现本机绝对路径（第 2 轮复查已修复 6 处）
- [x] 保留了完整技术实现细节

### 每批提交前的强制扫描命令

```bash
# 1) 本地绝对路径（期望无输出）
#    正则要求 /Users/ 后必须跟真实路径段，因此不会匹配本命令自身，
#    也不会匹配文档中 /Users/<用户名>/ 这类已脱敏的占位写法
grep -rnE "/Users/[A-Za-z0-9._-]+/" dev_docs/

# 2) 凭证样值（期望无输出）
grep -rniE "(api[_-]?key|token|secret|password|passwd|credential)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][A-Za-z0-9_-]{12,}" dev_docs/
```

两条命令的执行结果必须记入 `generation_progress.md`，任一有输出即为 blocker，禁止提交。

---

## 📝 第二阶段：核心代码模式提取（待正式生成阶段执行）

> 本阶段在 Phase 1 只锁定**提取目标与来源文件**，实际代码片段在用户确认后逐篇提取，避免方案文档本身膨胀。

### 2.1 CLI 子命令定义模式

- **来源文件**: `codex-rs/cli/src/main.rs:94-200`（`MultitoolCli` + `Subcommand`）
- **待提取要点**: clap derive 用法、`subcommand_negates_reqs`、`override_usage`、`#[clap(hide = true)]` 内部命令、`#[cfg(target_os = ...)]` 平台条件命令
- **落地文档**: `cli_usage.md`、`architecture_overview.md`

### 2.2 app-server v2 API 定义模式

- **来源文件**: `codex-rs/app-server-protocol/src/protocol/v2.rs`、`common.rs`、`codex-rs/app-server/README.md`
- **待提取要点**: `*Params`/`*Response`/`*Notification` 命名、`#[serde(rename_all = "camelCase")]`、`#[ts(export_to = "v2/")]`、`#[ts(optional = nullable)]`、游标分页（`cursor`/`limit` + `data`/`next_cursor`）、`#[experimental(...)]`
- **落地文档**: `app_server_protocol.md`
- **规范来源**: AGENTS.md「## App-server API Development Best Practices」（必须原样落实，不得改写）

### 2.3 沙箱策略模式

- **来源文件**: `codex-rs/sandboxing/src/manager.rs`、`seatbelt.rs`、`landlock.rs`、`bwrap.rs`、`windows.rs`、`policy_transforms.rs` 及 3 个 `.sbpl` 策略文件
- **待提取要点**: 平台分派、策略转换、违规检测（`violation.rs`、`denial.rs`）
- **落地文档**: `tools_and_sandbox.md`

### 2.4 集成测试模式

- **来源文件**: `codex-rs/core/tests/suite/`（**116 个 `.rs` 文件**，口径 `git ls-files "codex-rs/core/tests/suite/*.rs" | wc -l`；连同 `snapshots/` 等非 `.rs` 条目递归共 154 个跟踪文件）、`codex-rs/core/tests/common/`、AGENTS.md「#### codex_core integration testing」与「#### app-server integration testing」
- **口径说明**: 早期记录的「40+ 用例」是**用例数**的估读，与本体系其余位置使用的**文件数**口径不可比，已统一改为文件数并给出可复现命令。文件数 ≠ 用例数：单文件通常含多个 `#[tokio::test]`。
- **待提取要点**: `TestCodexBuilder::build_with_auto_env()`、`responses::mount_sse_once`、`ResponseMock::single_request()`、`wait_for_event`、`TestAppServer::builder().build()`、`pretty_assertions::assert_eq`
- **落地文档**: `testing_guide.md`

### 2.5 配置定义模式

- **来源文件**: `codex-rs/config/src/config_toml.rs`、`types.rs`、`state.rs`、`codex-rs/core/src/config/mod.rs:4578`（`find_codex_home`）、`codex-rs/utils/home-dir/src/lib.rs:13`
- **待提取要点**: `CODEX_HOME` 解析、config.toml 分层与 profile 覆盖、`just write-config-schema` 与 `codex-rs/core/config.schema.json` 的同步义务（AGENTS.md 顶部规则列表（config schema 条目））
- **落地文档**: `config_system.md`

### 2.6 TUI 样式与快照模式

- **来源文件**: `codex-rs/tui/styles.md`、`codex-rs/tui/src/wrapping.rs`、`line_utils.rs`、AGENTS.md「## TUI style conventions」至「### Snapshot tests」各节
- **待提取要点**: ratatui Stylize 助手优先、禁止使用 `.white()`、`textwrap::wrap`、`word_wrap_lines`、insta 快照工作流（`cargo insta pending-snapshots` / `show` / `accept`）
- **口径更正**: 本条一直把 insta 快照工作流列为「需从上游提取到 `tui_guide.md`」的既有事实，但首版交付的 `testing_guide.md` 却把它写成「上游无任何记载、做法未知」并登记为 accepted issue AI-004。两者矛盾，**以本条为准**：AGENTS.md 的「### Snapshot tests」一节已完整记载该流程，且额外给出一条硬要求——任何影响用户可见 UI（含新增 UI）的改动都必须附带对应的 insta 快照覆盖。AI-004 已撤销（见 `health_check_report.md` H13）。
- **落地文档**: `tui_guide.md`

---

## 📚 第三阶段：子文档规划（待审核）

> 分层依据：CLI 工具项目配置（`core/project_types/cli_tool.md` 推荐 `cli_usage.md` / `installation.md` / `plugin_system.md` / `configuration.md` / `contributing.md`）+ 超大型 Rust monorepo 的实际需要（新增 crate 地图、核心运行时、协议、沙箱等）。

### 3.1 必需子文档清单（P0，第 1 批）

- [ ] `dev_docs/AI_Coding_Context.md` — 主文档（索引 + 速查 + 场景导航）

  - **内容来源**: 本方案全文 + `README.md` + `AGENTS.md` + `justfile` + 各批子文档链接
  - **预计行数**: 400-550
  - **关键章节**: 项目概览 / 关键目录速查 / 场景快速导航 / 文档索引 / 核心代码模式 / 开发流程规范 / 命名规范 / 业务模块映射 / AI 编码禁忌 / 常见任务速查

- [ ] `dev_docs/architecture_overview.md` — 架构总览

  - **内容来源**: `codex-rs/cli/src/main.rs`、`codex-rs/Cargo.toml`、`codex-rs/protocol/`、`codex-rs/app-server/README.md`、1.5 节 7 个架构特点
  - **预计行数**: 450-600
  - **关键章节**: 运行时拓扑（mermaid）/ 单二进制多前端 / 协议分层 / 进程边界与跨 OS 部署 / 数据与凭证流向 / 外部服务边界

- [ ] `dev_docs/crate_map.md` — Cargo workspace crate 地图 ★ 本项目专属核心文档

  - **内容来源**: `cargo metadata --no-deps`（134 个包，权威计数）、`codex-rs/Cargo.toml` 的 `[workspace] members`（显式 128 项）与 `[workspace.dependencies]` 的 128 条 path 映射，各 crate `Cargo.toml`
  - **预计行数**: 500-700
  - **关键章节**: 分层总览（mermaid 依赖图）/ 按职责分组的 134 crate 速查表（crate 名 ↔ 目录 ↔ 职责 ↔ 代码量）/ "新代码该放哪个 crate"决策树 / `codex-core` 减负指引（对应 AGENTS.md「## The codex-core crate」）

- [ ] `dev_docs/development_workflow.md` — 开发流程与仓库硬规范

  - **内容来源**: `AGENTS.md` 全文、`justfile`、`docs/contributing.md`、`.github/workflows/`、`scripts/format.py`
  - **预计行数**: 400-550
  - **关键章节**: 环境准备（Rust 1.95.0 / Node ≥22 / pnpm ≥10.33.0 / Python ≥3.10）/ just 任务速查 / fmt·fix·test 三步法与 `-p` 作用域 / 变更规模门槛 / 大模块拆分规则与点名文件 / 贡献治理前提（受邀制 + CLA）/ CI 工作流地图

**第 1 批合计**: 4 篇，预计 1750-2400 行

---

### 3.2 推荐子文档清单

#### 第 2 批（P1，核心运行时，5 篇）

- [ ] `dev_docs/core_agent_loop.md` — 智能体核心循环

  - **推荐理由**: codex-core（296,963 行）是理解项目的最大障碍，且 AGENTS.md「### Model visible context」 对模型可见上下文有 6 条硬约束，必须成文
  - **内容来源**: `codex-rs/core/src/lib.rs`、`codex_thread.rs`、`client.rs`、`client_common.rs`、`compact*.rs`、`context/`、`context_manager/`、`session/`、`tasks/`
  - **预计行数**: 500-650

- [ ] `dev_docs/tools_and_sandbox.md` — 工具执行、审批与沙箱

  - **推荐理由**: 项目核心安全边界，三平台实现差异大，且含 `CODEX_SANDBOX_*` 绝对红线
  - **内容来源**: `codex-rs/sandboxing/`、`linux-sandbox/`、`windows-sandbox-rs/`、`execpolicy/`、`shell-escalation/`、`core/src/exec*.rs`、`core/src/tools/`、`utils/approval-presets/`
  - **预计行数**: 450-600

- [ ] `dev_docs/app_server_protocol.md` — App Server 协议与 API 开发规范

  - **推荐理由**: AGENTS.md「## App-server API Development Best Practices」 已给出完整硬规范；IDE/桌面端/SDK 均依赖此协议；TS 类型由此生成
  - **内容来源**: `codex-rs/app-server-protocol/src/protocol/{common,v2}.rs`、`codex-rs/app-server/README.md`、`schema/typescript/v2/`
  - **预计行数**: 400-550

- [ ] `dev_docs/config_system.md` — 配置系统

  - **推荐理由**: CLI 工具项目必备（`cli_tool.md` 推荐 `configuration.md`）；本项目配置分层复杂（CODEX_HOME / config.toml / profile / feature flags / CLI overrides）
  - **内容来源**: `codex-rs/config/`、`codex-rs/core/src/config/`、`codex-rs/features/`、`codex-rs/core/config.schema.json`、`docs/config.md`
  - **预计行数**: 400-550

- [ ] `dev_docs/tui_guide.md` — TUI 开发指南

  - **推荐理由**: 238,439 行第二大 crate，且 AGENTS.md「## TUI style conventions」至「### Snapshot tests」各节 有大量样式与快照硬约定，AGENTS.md 顶部规则列表（high-touch files 与 chatwidget 条目） 点名多个高触碰文件
  - **内容来源**: `codex-rs/tui/styles.md`、`codex-rs/tui/src/`（app / chatwidget / bottom_pane / wrapping / line_utils）
  - **预计行数**: 400-550

#### 第 3 批（P1，集成与工程化，5 篇）

- [ ] `dev_docs/testing_guide.md` — 测试指南

  - **推荐理由**: 457 个 `*_tests.rs` + 681 个快照 + 三语言测试栈，AGENTS.md「### Test authoring guidance」「### Change size guidance (800 lines)」与「## Tests」各节 规定详尽
  - **内容来源**: `codex-rs/core/tests/`、`codex-rs/app-server/tests/`、`sdk/typescript/tests/`、`sdk/python/tests/`、`justfile`、`AGENTS.md`
  - **预计行数**: 450-600

- [ ] `dev_docs/mcp_and_extensions.md` — MCP、扩展、插件与 Skills

  - **推荐理由**: `cli_tool.md` 推荐 `plugin_system.md`；本项目有四条并行扩展路径，需一篇统一说明
  - **内容来源**: `codex-rs/codex-mcp/`、`mcp-server/`、`rmcp-client/`、`ext/*`（12 个）、`core-plugins/`、`skills/`、`docs/skills.md`
  - **预计行数**: 450-600

- [ ] `dev_docs/auth_and_providers.md` — 鉴权与模型提供方

  - **推荐理由**: 1.3C 表中 10 条外部边界的集中落点；涉及凭证存储安全
  - **内容来源**: `codex-rs/login/`、`model-provider-info/`、`model-provider/`、`models-manager/`、`chatgpt/`、`keyring-store/`、`ollama/`、`lmstudio/`、`docs/authentication.md`
  - **预计行数**: 400-500

- [ ] `dev_docs/build_and_release.md` — 构建、双构建系统与发布

  - **推荐理由**: `cli_tool.md` 推荐 `installation.md`；本项目 Cargo/Bazel 双锁同步是高频踩坑点（AGENTS.md 顶部规则列表（Bazel 锁与 compile_data 条目））
  - **内容来源**: `MODULE.bazel`、`justfile`、`.github/workflows/`（27 个 yml）、`codex-cli/scripts/build_npm_package.py`、`scripts/`、`docs/install.md`
  - **预计行数**: 400-550

- [ ] `dev_docs/session_and_persistence.md` — 会话生命周期与持久化

  - **推荐理由**: `Resume`/`Fork`/`Archive`/`Delete`/`Unarchive` 五个用户可见子命令背后是 rollout + thread-store + state 三套机制，理解会话恢复是调试前提
  - **内容来源**: `codex-rs/rollout/`、`rollout-trace/`、`thread-store/`、`state/`、`message-history/`、`codex-rs/cli/src/state_db_recovery.rs`
  - **预计行数**: 350-450

#### 第 4 批（P2，3 篇 + 收尾）

> 用户已确认疑问 3 为「全部展开」，本批由原 2 篇增至 3 篇，新增 `experimental_surfaces.md`。

- [ ] `dev_docs/experimental_surfaces.md` — 实验性与低频表面 ★ 用户指定展开

  - **推荐理由**: 用户明确要求展开全部实验性表面。这些能力面在 `crate_map.md` 中只有条目，缺少"它是什么、当前成熟度、怎么用、代码在哪"的说明；且多数带 `[experimental]` / `#[clap(hide = true)]` 标记，误用风险高于稳定能力面
  - **覆盖对象（6 项）**: `Cloud`（`cloud-tasks` / `cloud-tasks-client` / `backend-client`）、桌面端 `codex app`、`remote-control`、`responses-api-proxy`、`v8-poc`、`code-mode`（4 个 crate）
  - **内容来源**: `codex-rs/cli/src/main.rs:147,150,154-155,173-174,195-200`、`codex-rs/cloud-tasks*/`、`codex-rs/v8-poc/`、`codex-rs/code-mode*/`、`codex-rs/app-server/` 的 remote-control 路径、各自 `Cargo.toml`
  - **强制写作约束**: 每节必须首行标注**当前成熟度与可见性**（experimental / hidden / PoC），并注明"上游可能随时变更或移除"；不得把 PoC 描述为稳定能力
  - **预计行数**: 500-700

- [ ] `dev_docs/observability.md` — 可观测性与遥测边界

  - **推荐理由**: 承接 1.3C 中两项 `needs_code_verification`，需明确 OTLP/Statsig/analytics 的默认开关与关闭方式
  - **内容来源**: `codex-rs/otel/`、`analytics/`、`feedback/`、`response-debug-context/`、`codex-rs/cli/src/exec_server_telemetry.rs`
  - **预计行数**: 300-400

- [ ] `dev_docs/sdk_guide.md` — TypeScript / Python SDK

  - **推荐理由**: 对外集成入口；两套 SDK 共享 app-server 协议
  - **内容来源**: `sdk/typescript/src/`、`sdk/python/src/openai_codex/`、`sdk/python-runtime/`、各 `package.json` / `pyproject.toml`
  - **预计行数**: 300-400

---

### 3.3 目录与规则产物

- [ ] `dev_docs/plans/README.md`（模板：`templates/plans_README_TEMPLATE.md`）
- [ ] `dev_docs/knowledge/README.md`（模板：`templates/knowledge_README_TEMPLATE.md`）
- [ ] `dev_docs/rules/combined/AI_RULES.md`（模板：`templates/AI_RULES_TEMPLATE.md`）

**AI_RULES.md 特别约定**：`AGENTS.md` 是仓库对 AI 的**既有事实源**，AI_RULES 不得复制其全文造成双份漂移，只做「指向 AGENTS.md 的索引 + 本文档体系导航 + dev_docs 特有约定」。

---

### 3.4 项目定位触发项覆盖

| 项目定位信号 | 证据文件 | 文档规划影响 | 覆盖方式 |
| ------------ | -------- | ------------ | -------- |
| 开源维护/贡献流程（受邀制 + CLA） | `docs/contributing.md`、`docs/CLA.md`、`LICENSE`、`.github/workflows/cla.yml` | 贡献治理前提必须前置说明，避免文档给出与维护者规则冲突的行动建议 | 合并到 `development_workflow.md` |
| AI 代理硬规范 | `AGENTS.md`（22,519 字节） | 决定 AI 编码禁忌章节与 AI_RULES 内容 | 拆分到 `development_workflow.md`（流程）+ `crate_map.md`（core 减负）+ `tui_guide.md`（TUI 约定）+ `app_server_protocol.md`（API 约定）+ 主文档「AI 编码禁忌」 |
| 用户手册/使用指南 | `docs/getting-started.md`、`docs/exec.md`、`docs/slash_commands.md`、`docs/skills.md`、外部站点 developers.openai.com | 面向用户的使用说明**不重复造轮子**，只做索引 | 主文档「文档索引」章节链接 `docs/` 与外部站点；不生成独立 `cli_usage.md`/`installation.md`，其开发者视角内容并入 `architecture_overview.md` 与 `build_and_release.md` |
| 自托管/部署运维 | `.devcontainer/`、`codex-cli/scripts/run_in_container.sh`、`init_firewall.sh`、`flake.nix` | 容器与 Nix 开发环境说明 | 合并到 `development_workflow.md` |
| 外部 API/数据授权 | `README.md`、`codex-rs/login/`、`codex-rs/model-provider-info/`、`docs/authentication.md` | Provider、授权、数据边界 | 单独文档 `auth_and_providers.md` |
| 沙箱与安全模型 | `docs/sandbox.md`、`docs/execpolicy.md`、`SECURITY.md`、`codex-rs/sandboxing/` | 安全边界必须独立成文 | 单独文档 `tools_and_sandbox.md` |
| 插件/扩展生态 | `docs/skills.md`、`codex-rs/ext/`、`core-plugins/`、`skills/` | 扩展开发说明 | 单独文档 `mcp_and_extensions.md` |

> [!IMPORTANT]
> AGENTS.md 顶部规则列表（docs/ 条目） 明确禁止向 `docs/` 添加通用产品或用户文档。本方案的全部产物落在仓库根 `dev_docs/`，**不得**移入 `docs/`。

---

## 🎯 第四阶段：主文档章节规划

### 4.1 必需章节检查清单

- [ ] **项目概览** — 数据来源：`README.md`、`codex-rs/Cargo.toml`、本方案 1.2 节统计命令输出
- [ ] **关键目录速查** — 数据来源：本方案 1.3 节目录树（`ls codex-rs/` 等实测）
- [ ] **场景快速导航** — 数据来源：本方案 1.4 节模块清单 + `codex-rs/cli/src/main.rs:123-200` 子命令枚举
- [ ] **文档索引** — 数据来源：本方案 3.1-3.3 节子文档清单 + `docs/` 15 篇既有文档
- [ ] **核心代码模式** — 数据来源：本方案第二阶段 6 类模式的实际提取结果
- [ ] **开发流程规范** — 数据来源：AGENTS.md 顶部规则列表（just fmt / just test / just fix 段）、`justfile`、`docs/contributing.md`
- [ ] **命名规范** — 数据来源：AGENTS.md 顶部规则列表（crate 前缀条目）（crate 前缀 `codex-`）、AGENTS.md「### Core Rules」（API 命名）、实际 crate 名验证
- [ ] **业务模块映射** — 数据来源：本方案 1.4 节 17 个模块清单
- [ ] **AI 编码禁忌** — 数据来源：`AGENTS.md` 全部禁止项（沙箱环境变量红线、core 膨胀、大文件堆叠、`#[async_trait]`、单次引用的小helper、`cargo test` 直用、docs/ 越界等）
- [ ] **常见任务速查** — 数据来源：`justfile` 任务列表 + `AGENTS.md` 中的 `just write-config-schema` / `just write-app-server-schema` / `just bazel-lock-update` / `just argument-comment-lint`

### 4.2 场景快速导航规划

| 场景描述 | 对应文档 | 数据来源 |
| -------- | -------- | -------- |
| 我要新增一个 CLI 子命令 | `architecture_overview.md` + `crate_map.md` | `codex-rs/cli/src/main.rs:123-200` |
| 我要改动智能体的上下文构造 | `core_agent_loop.md` | `codex-rs/core/src/context/`、AGENTS.md「### Model visible context」 |
| 我要新增/修改一个模型工具 | `tools_and_sandbox.md` + `core_agent_loop.md` | `codex-rs/core/src/tools/`、`codex-rs/tools/` |
| 我要新增 app-server API | `app_server_protocol.md` | AGENTS.md「## App-server API Development Best Practices」、`app-server-protocol/src/protocol/v2.rs` |
| 我要加一个配置项 | `config_system.md` | `codex-rs/config/src/config_toml.rs`、AGENTS.md 顶部规则列表（config schema 条目） |
| 我要改 TUI 界面 | `tui_guide.md` | `codex-rs/tui/styles.md`、AGENTS.md「## TUI style conventions」至「### Snapshot tests」各节 |
| 我要写/更新测试 | `testing_guide.md` | `codex-rs/core/tests/suite/`、AGENTS.md「### Test authoring guidance」与「## Tests」各节 |
| 我要接入一个 MCP server 或写扩展 | `mcp_and_extensions.md` | `codex-rs/codex-mcp/`、`codex-rs/ext/` |
| 我改了依赖，CI 报 Bazel 锁漂移 | `build_and_release.md` | AGENTS.md 顶部规则列表（Bazel 锁与 compile_data 条目） |
| 我要理解会话恢复/分叉行为 | `session_and_persistence.md` | `codex-rs/rollout/`、`thread-store/` |
| 我要确认某功能会向外发送什么数据 | `auth_and_providers.md` + `observability.md` | 本方案 1.3C 表 |
| 我不知道新代码该放哪个 crate | `crate_map.md` | `codex-rs/Cargo.toml`、AGENTS.md「## The codex-core crate」 |

**⚠️ 人工验证点**:

- 12 个场景是否覆盖用户在此仓库的主要工作模式
- 若用户的实际目的偏向"阅读理解上游代码"而非"参与开发"，场景清单需向"如何定位某功能实现"倾斜（对应待确认项 1）

---

## ⚠️ 风险点与注意事项

### 已识别的风险

1. **覆盖度风险（最高）**: 1,270,789 行 Rust 无法在文档体系中穷尽

   - **影响**: 文档可能给出局部正确但整体片面的架构描述
   - **缓解措施**: ①每篇文档 frontmatter 的 `related_files` 精确列出实际读过的文件；②主文档设「未覆盖范围」章节明确列出未深入的 crate；③优先覆盖代码量 Top 10 + 用户可见能力面

2. **上游高速迭代导致文档漂移**: 基线 commit `bb5054fe47` 当日即有多个 PR 合入

   - **影响**: 文档时效性衰减快
   - **缓解措施**: ①所有文档记录基线 commit；②`verified_at` 严格填写；③后续使用框架路径 C（`@commit` 增量更新）维护

3. **AGENTS.md 与实际代码的张力**: 规范要求 Rust 模块 <500 LoC，实测 `chat_composer.rs` 12,616 行

   - **影响**: 若文档只复述规范会误导；若只描述现状会削弱规范
   - **缓解措施**: 文档中同时给出「规范要求」与「实测现状」两栏，并明确标注这些是**历史遗留的高触碰文件，新代码不得继续堆入**

4. **双构建系统的验证成本**: 本地未验证 Bazel 构建可用性

   - **影响**: `build_and_release.md` 中的 Bazel 部分可能只有 E2 级证据
   - **缓解措施**: 该章节明确标注证据等级；不写"已验证"类措辞；提供 CI 工作流作为交叉参考

5. **本地 Python 版本低于 SDK 要求**: 本机 Python 3.9.6 < `sdk/python/pyproject.toml:10` 的 `requires-python = ">=3.10"`

   - **影响**: 无法在本机运行 Python SDK 测试来取得 E4 证据
   - **缓解措施**: `sdk_guide.md` 与 `testing_guide.md` 中 Python SDK 部分标注为 E2 级（基于配置文件），并写明本地验证前提

### 需要人工确认的项目特性

**准入规则说明**: 以下 3 项均已确认无法通过代码、配置、锁文件、README 或现有项目文档回答，属于用户意图与工作方式层面的决策。所有可代码核查的问题已移入下节"下一步代码级核查"。

> **第 2 轮复查状态**：第 2 项已由用户的实际操作解决，**当前仍需用户回答的为第 1、3 项**。已解决项保留原位并标注结论，不删除，以保持复查可追溯。

1. **文档体系的服务对象与深度定位**

   - **当前保守结论**: 按「双重定位」处理——既服务于**阅读理解 upstream 代码**（强化 crate 地图、架构导航、"某功能在哪实现"），也服务于**在本仓库做二次开发**（保留 AGENTS.md 规范落地、测试与构建指引）。第 1 批 4 篇文档在两种定位下均为必需，因此不阻塞方案通过。
   - **✅ 用户答复（2026-08-03）**: **兼顾**，与保守结论一致，批次顺序与权重维持方案原样，无需调整。
   - **已检查证据**: `README.md`（产品定位）、`docs/contributing.md:3`（外部贡献受邀制）、`git remote -v`（origin 为 `openai/codex` 本身而非 fork）、当前分支 `zibuyu`（本地 topic 分支，无本地提交差异证据表明开发意图）
   - **为什么代码或仓库文档无法回答**: 这是用户个人的使用目的，仓库本身不记录任何单个使用者的意图
   - **blocks_phase1**: false
   - **回写目标**: `generation_plan.md` 3.1-3.2 节子文档清单权重、`AI_Coding_Context.md` 场景快速导航
   - **建议做法**: 若答案是「主要为阅读理解」，第 2 批应把 `core_agent_loop.md` 提前并加大「功能定位索引」比重，`development_workflow.md` 可精简；若是「参与开发」，则维持当前批次顺序。

2. **`dev_docs/` 是否纳入版本管理** —— ✅ **已由用户行动解决（第 2 轮复查），不再需要用户回答**

   - **当前保守结论**: **提交全部内容（含 `_analysis`），推送至个人 fork `zibuyu2015831/codex`，禁止向上游 `origin` 推送任何内容。** 该结论已由用户的实际操作确立，取代第 1 轮的「不提交」。
   - **第 1 轮保守结论（已被推翻）**: 当时结论为"不提交、写入本地 exclude 文件"，依据是 `origin` 直连 `openai/codex` 且外部贡献受邀制。
   - **已检查证据（E4）**: commit `8224f7c034` 已包含三件套；`gh repo view zibuyu2015831/codex` → `isFork: true` / `parent: openai/codex` / `isPrivate: false`；`git remote -v` 新增 `fork  https://github.com/zibuyu2015831/codex.git`；`zibuyu` 分支 upstream 已指向 `fork/zibuyu`；上游 `origin` 未收到任何 push；框架软链接写入本地 exclude 文件后未提交；仓库根 gitignore 文件未被修改
   - **为什么代码或仓库文档无法回答**: 仓库不可能记录使用者对自己新增本地目录的版本管理偏好。第 2 轮中该项之所以能结案，是因为**用户用实际操作给出了答案**，而非代码提供了答案 —— 准入判定本身仍然成立。
   - **blocks_phase1**: false
   - **回写目标**: 本文执行计划、`project_analysis_report.md` 疑问 2、`development_workflow.md` 的「本地开发环境」章节
   - **对后续批次的约束**: ①正式文档同样提交至 `fork/zibuyu`；②push 目标必须显式写 `fork`，禁止 `git push origin`；③产物进入**公开**仓库，脱敏升级为硬性红线（见「代码脱敏规范」与报告 🟡 警告 6）

3. **实验性与低频表面的文档优先级**

   - **当前保守结论**（已被用户答复取代）: 上述表面在第 1-3 批中仅在 `crate_map.md` 中登记为条目，不单独展开。
   - **✅ 用户答复（2026-08-03）**: **全部展开。** 已据此在第 4 批新增 `experimental_surfaces.md`，覆盖 `Cloud`/`cloud-tasks`、桌面端 `codex app`、`remote-control`、`responses-api-proxy`、`v8-poc`、`code-mode` 共 6 项；正式文档总数由 16 篇增至 17 篇。第 1-3 批仍在 `crate_map.md` 中登记条目，展开内容集中在第 4 批。
   - **已检查证据**: `codex-rs/cli/src/main.rs:147`（`/// [experimental] Run the app server or related tooling.`）、`:150`（`[experimental]` RemoteControl）、`:195`（`[EXPERIMENTAL]` Cloud）、`:199-200`（`#[clap(hide = true)]` responses-api-proxy）、`codex-rs/v8-poc/` 目录名本身即 PoC
   - **为什么代码或仓库文档无法回答**: 代码可以告诉我们「哪些是实验性的」，但无法告诉我们「用户是否关心它们」——这是优先级偏好
   - **blocks_phase1**: false
   - **回写目标**: `generation_plan.md` 3.2 节第 4 批清单、`crate_map.md`
   - **建议做法**: 如用户主要关注稳定能力面，维持当前保守结论即可。

### 下一步代码级核查（不进入用户确认清单）

以下问题可由代码回答，将在对应批次执行，不占用用户确认：

| 待核查项 | 当前证据 | 核查动作 | 归属批次 | 落地文档 |
| -------- | -------- | -------- | -------- | -------- |
| OTLP / Statsig 遥测在 release 构建下的默认开关与关闭方式 | E3：`codex-rs/otel/src/config.rs:16,90,113` | 读取 `OtelSettings` / `StatsigMetricsSettings` 完整定义与 `provider.rs` 初始化链路，追溯 config.toml 键名 | 第 4 批 | `observability.md` |
| analytics 采集开关与投递目的地的分离边界 | E3：`codex-rs/analytics/src/client.rs` | 已完成：`CaptureFile` 分支同时受 `cfg(debug_assertions)` 与捕获文件环境变量约束，二者缺一即落到 `Self::Http`；"network delivery is disabled" 只是该分支内的日志文案，**不是**编译期全局常量 | 第 4 批（已闭合） | `observability.md` |
| 134 个 crate 的实际依赖分层（谁依赖 core，谁被 core 依赖） | E2：`codex-rs/Cargo.toml` `[workspace.dependencies]` | 逐 crate 读取 `Cargo.toml` 的 `[dependencies]` 并生成依赖图 | 第 1 批 | `crate_map.md` |
| 四层扩展机制（ext / core-plugins / skills / MCP）之间的关系与优先级 | E1：目录存在性 | 读取 `ext/extension-api/src/lib.rs`、`core-plugins/src/manager.rs`、`skills/src/lib.rs` 的公开 API | 第 3 批 | `mcp_and_extensions.md` |
| app-server ↔ exec-server 跨 OS 分离的实际传输实现 | E2：AGENTS.md「## Platform Support」 + crate 存在性 | 读取 `exec-server-protocol/src/`、`app-server-transport/src/`、`uds/src/` | 第 2 批 | `architecture_overview.md` |
| `CODEX_HOME` 的实际解析顺序 | E3：`codex-rs/core/src/config/mod.rs:4578`、`codex-rs/utils/home-dir/src/lib.rs:13` 两处同名函数 | 读取两处实现，确认调用关系与是否重复定义 | 第 2 批 | `config_system.md` |
| `docs/` 15 篇文档中哪些是实质内容、哪些仅为外链占位 | E4：`wc -l docs/config.md` = 15 行、`codex-rs/config.md` = 6 行、`docs/sandbox.md` 仅 3 行外链 | 逐篇 `wc -l` + 抽读 | 第 1 批 | `AI_Coding_Context.md` 文档索引 |

---

## 📊 质量保证措施

### 数据来源追溯

- [x] 项目规模 → `git ls-files` + `wc -l` + `project_scanner.py` 输出
- [x] 目录结构 → `ls` / `find` 实际输出
- [ ] 代码示例 → 实际文件路径 + 行号（正式生成阶段逐条落实）
- [x] 业务模块 → `codex-rs/Cargo.toml` workspace members + 目录实测
- [x] 架构特点 → 具体文件路径与行号（7 项中 5 项已达 E3）

### 验证检查点

生成正式文档前，必须验证:

- [x] 所有引用的文件路径已确认存在
- [x] 所有统计数据都有可复现命令
- [x] 架构特点有代码依据，未出现无依据推断
- [x] 业务模块清单与 workspace members 对齐
- [ ] 代码示例来自真实文件（正式生成阶段执行）

---

## 🧾 证据与验证记录

### 证据等级

| 等级 | 证据来源 | 允许措辞 |
| ---- | -------- | -------- |
| E1 | 目录结构、文件名、文件数量 | "疑似""风险假设""建议后续验证" |
| E2 | 配置文件、锁文件、README、项目文件 | "已从配置确认""技术栈事实" |
| E3 | 源码片段、协议、关键函数、调用链 | "代码显示""实现方式为" |
| E4 | 构建、测试、脚本运行、工具检查结果 | "已验证""检查通过/失败" |

### 关键事实记录

| 事实 | 证据等级 | 来源文件 | 验证方式 | 当前结论 |
| ---- | -------- | -------- | -------- | -------- |
| Rust workspace 含 134 个 crate | E4 | `codex-rs/Cargo.toml`（`cargo metadata --no-deps` 解析） | `cargo metadata --no-deps --format-version 1` 计数 `packages` | 已确认（第 2 轮复查更正，原记 130 有误） |
| `[workspace] members` 显式列出 128 项 | E2 | `codex-rs/Cargo.toml` `[workspace] members` | 读取 + 计数 | 已确认；与 134 的差额为 3 个仅以 path 依赖参与的 crate 与 3 个 `tests/common` 测试辅助 crate |
| 主二进制名为 `codex` | E2 | `codex-rs/cli/Cargo.toml` `[[bin]]` | 读取 | 已确认 |
| Rust 版本 1.95.0，edition 2024 | E2 | `codex-rs/rust-toolchain.toml`、`codex-rs/Cargo.toml` `[workspace.package]` | 读取 | 已确认 |
| Node ≥22、pnpm ≥10.33.0 | E2 | `package.json` `engines` / `packageManager` | 读取 | 已确认 |
| Python SDK 要求 ≥3.10 | E2 | `sdk/python/pyproject.toml:10`、`sdk/python-runtime/pyproject.toml:10` | grep | 已确认 |
| 本机 Python 为 3.9.6 | E4 | `python3 --version` | 命令执行 | 已确认（低于 SDK 要求） |
| 本机 Node 为 v24.13.0 | E4 | `node --version` | 命令执行 | 已确认（满足 ≥22） |
| 默认 API 基址 `https://api.openai.com/v1` | E3 | `codex-rs/model-provider-info/src/lib.rs:257` | grep + 读取 | 已确认 |
| ChatGPT 通道基址常量 | E3 | `codex-rs/model-provider-info/src/lib.rs:38` | grep | 已确认 |
| OAuth issuer `https://auth.openai.com` | E3 | `codex-rs/login/src/server.rs:59` | grep | 已确认 |
| 凭证存储于 `CODEX_HOME/auth.json` 或 keyring | E3 | `codex-rs/config/src/types.rs:109,113,129` | grep | 已确认 |
| 沙箱支持 Seatbelt/Landlock/bwrap/Windows | E3 | `codex-rs/sandboxing/src/{seatbelt,landlock,bwrap,windows}.rs` + 3 个 `.sbpl` | `ls` | 已确认 |
| CLI `Subcommand` 枚举 **27 个变体**（3 个 `#[clap(hide = true)]`，1 个仅 macOS/Windows 条件编译；因此 Linux 上可见 23 个、macOS 与 Windows 上可见 24 个） | E3 | `codex-rs/cli/src/main.rs` 的 `Subcommand` 枚举 | 读取 | **已更正**：原记「23 个」把「Linux 可见数」当成了「枚举变体数」，与全部正式文档的「27 个变体」冲突。该残留是第二轮独立审查推翻首版验收的直接证据之一（`health_check_report.md` H15 / X4） |
| 禁止向 `docs/` 添加通用文档 | E2 | AGENTS.md 顶部规则列表（docs/ 条目） | 读取 | 已确认 |
| 外部贡献受邀制 | E2 | `docs/contributing.md:3-17` | 读取 | 已确认 |
| 单次变更 ≤800 行 | E2 | AGENTS.md「### Change size guidance (800 lines)」 | 读取 | 已确认 |
| 三平台支持强制要求 | E2 | AGENTS.md「## Platform Support」 | 读取 | 已确认 |
| Cargo/Bazel 双锁需同步 | E2 | AGENTS.md 顶部规则列表（Bazel 锁条目） | 读取 | 已确认 |
| `chat_composer.rs` 12,616 行 | E4 | `git ls-files "*.rs" \| xargs wc -l \| sort -rn` | 命令执行 | 已确认 |
| insta 快照 681 个 | E4 | `git ls-files "*.snap" \| wc -l` | 命令执行 | 已确认 |
| `*_tests.rs` 457 个 | E4 | `git ls-files "*_tests.rs" \| wc -l` | 命令执行 | 已确认 |
| analytics 为 opt-out 语义；**网络投递并非「当前关闭」** | E3 | `codex-rs/analytics/src/client.rs` 的 `AnalyticsEventsDestination::from_base_url_and_capture_file` | 读取完整分支 | **已更正**：写本地文件的 `CaptureFile` 分支需同时满足「debug 构建」且「捕获文件环境变量已设置且非空」；环境变量未设时，debug 构建同样落到 `Self::Http` 走网络。原记「网络投递当前关闭」是只读了日志文案得出的错误结论（`health_check_report.md` H7） |
| Statsig 默认指标导出在 debug 构建下关闭 | E3 | `codex-rs/otel/src/config.rs:16,113` | grep | 待第 4 批完整核查 |
| 框架目录为软链接 `AI-Coding-Context` | E4 | `ls -la` 显示 `lrwxr-xr-x ... -> <本地工作区>/AI-Coding-Context` | 命令执行 | 已确认并已排除 |

### 量化声明来源

| 声明 | 数值 | 来源命令/文件 | 记录位置 |
| ---- | ---- | ------------- | -------- |
| Git 跟踪文件总数 | 5913 | `git ls-tree -r --name-only bb5054fe47 \| wc -l`（基线 commit 口径，不含本体系自身产物） | 本文 1.2 节 |
| 扫描器文件总数 | 5910 | `python3 AI-Coding-Context/tools/py/project_scanner.py . --mode summary --exclude-standard` | 本文 1.2 节 |
| 目录总数 | 809 | 同上（`total_dirs`） | 本文 1.2 节 |
| 最大目录深度 | 9 | 同上（`max_depth`） | 本文 1.2 节 |
| Rust 文件数 / 行数 | 2858 / 1,270,789 | `git ls-files "*.rs" \| wc -l`；`git ls-files "*.rs" \| tr '\n' '\0' \| xargs -0 cat \| wc -l` | 本文 1.2 节 |
| TypeScript 文件数 / 行数 | 665 / 9,865 | 同上（`*.ts`） | 本文 1.2 节 |
| Python 文件数 / 行数 | 137 / 38,486 | 同上（`*.py`） | 本文 1.2 节 |
| Markdown 文件数 / 行数 | 178 / 17,419 | 同上（`*.md`） | 本文 1.2 节 |
| Cargo workspace crate 数 | 134 | `cargo metadata --no-deps --format-version 1 --manifest-path codex-rs/Cargo.toml` 的 `packages` 计数 | 本文 1.1、1.3 节 |
| `[workspace] members` 显式项数 | 128 | `codex-rs/Cargo.toml` `[workspace] members` 计数 | 本文 1.1、3.2 节 |
| `[workspace.dependencies]` path 映射数 | 128 | `codex-rs/Cargo.toml` `[workspace.dependencies]` 中含 `path =` 的条目计数 | 本文 1.4 节 |
| `codex-rs/` 下子 crate 清单数 | 134 | `git ls-files "codex-rs/**/Cargo.toml" \| wc -l`（不含 workspace 根清单） | 本文 1.1 节 |
| CI 工作流数 | 27 | `git ls-files ".github/workflows/*.yml" ".github/workflows/*.yaml" \| wc -l`（`README.md`、`Dockerfile.bazel`、`zstd` 为非 yml 条目，不计入；第 3 批复核时由 29 更正为 27） | 本文 1.3 节 |
| 测试目录数 / 测试文件数 | 39 / 631 | `semantic_review_checker.scan_test_topology`（全深度递归，识别 `tests`/`test`/`__tests__`/`spec` 等目录名） | 本文"测试资产扫描结果"章节 |
| insta 快照数 | 681 | `git ls-files "*.snap" \| wc -l` | 本文 1.2 节 |
| `*_tests.rs` 数 | 457 | `git ls-files "*_tests.rs" \| wc -l` | 本文 1.2 节 |
| 各 crate Rust 行数 | 见 1.2 节 Top 10 | `for d in codex-rs/*/; do git ls-files "$d*.rs" \| xargs wc -l ...; done \| sort -rn` | 本文 1.2 节 |

### 测试资产扫描结果

- **扫描范围**: 全仓库递归扫描名为 `tests` / `test` / `integration_test` / `__tests__` / `spec` 的目录，外加 `codex-rs/**/*_tests.rs` 与 `codex-rs/**/*.snap`
- **扫描口径与命令**: `semantic_review_checker.scan_test_topology`（全深度）；交叉复核 `git ls-files "*_tests.rs" | wc -l`、`git ls-files "*.snap" | wc -l`
- **总量**: 39 个测试目录，631 个测试文件；另有 457 个内联 `*_tests.rs` 与 681 个 insta 快照

#### 完整测试目录清单（39 个）

| 测试目录 | 文件数 |
| -------- | -----: |
| `codex-rs/core/tests/` | 174 |
| `codex-rs/app-server/tests/` | 121 |
| `codex-rs/apply-patch/tests/` | 82 |
| `codex-rs/tui/src/chatwidget/tests/` | 35 |
| `codex-rs/exec-server/tests/` | 25 |
| `codex-rs/exec/tests/` | 19 |
| `codex-rs/cli/tests/` | 18 |
| `sdk/python/tests/` | 18 |
| `codex-rs/rmcp-client/tests/` | 17 |
| `codex-rs/vendor/bubblewrap/tests/` | 15 |
| `codex-rs/tui/src/app/tests/` | 12 |
| `codex-rs/otel/tests/` | 11 |
| `codex-rs/tui/tests/` | 10 |
| `codex-rs/mcp-server/tests/` | 9 |
| `sdk/typescript/tests/` | 8 |
| `codex-rs/tools/tests/` | 7 |
| `codex-rs/login/tests/` | 6 |
| `codex-rs/chatgpt/tests/` | 4 |
| `codex-rs/codex-api/tests/` | 4 |
| `codex-rs/http-client/tests/` | 4 |
| `codex-rs/linux-sandbox/tests/` | 4 |
| `codex-rs/ext/extension-api/tests/` | 3 |
| `codex-rs/app-server-transport/src/transport/remote_control/tests/` | 2 |
| `codex-rs/backend-client/tests/` | 2 |
| `codex-rs/code-mode-host/tests/` | 2 |
| `codex-rs/ext/goal/tests/` | 2 |
| `codex-rs/ext/mcp/tests/` | 2 |
| `codex-rs/ext/skills/tests/` | 2 |
| `codex-rs/rmcp-client/src/oauth/tests/` | 2 |
| `codex-rs/utils/rustls-provider/tests/` | 2 |
| `codex-rs/cloud-tasks/tests/` | 1 |
| `codex-rs/code-mode-runtime/tests/` | 1 |
| `codex-rs/core-skills/tests/` | 1 |
| `codex-rs/core/src/session/tests/` | 1 |
| `codex-rs/exec-server/src/client/tests/` | 1 |
| `codex-rs/execpolicy/tests/` | 1 |
| `codex-rs/ext/agent/tests/` | 1 |
| `codex-rs/network-proxy/tests/` | 1 |
| `codex-rs/stdio-to-uds/tests/` | 1 |

#### 分析结论

- **Rust 集成测试重心**: `codex-rs/core/tests/`（174 文件，其中 `suite/` 有 **116 个 `.rs`**、`common/` 支撑库、`remote_env_windows/` 远程环境用例、`all.rs` 聚合入口）与 `codex-rs/app-server/tests/`（121 文件），两者合计占测试文件近半。`suite/` 的数值口径为 `git ls-files "codex-rs/core/tests/suite/*.rs" | wc -l`（E1）。
- **单元测试形态**: 457 个内联 `*_tests.rs`，遵循 AGENTS.md「### Test module organization」 的 `#[path = "..._tests.rs"]` 独立文件约定。
- **快照测试**: 681 个 insta 快照，主要集中在 `codex-rs/tui`，对应 AGENTS.md「### Snapshot tests」 的 UI 变更必须附快照的硬要求。
- **SDK 测试**: `sdk/typescript/tests/`（8 文件，jest）与 `sdk/python/tests/`（18 文件，pytest），后者覆盖 app-server 生命周期、审批、流式、登录、契约生成与公开 API 签名。
- **第三方内容**: `codex-rs/vendor/bubblewrap/tests/`（15 文件）属 vendored 第三方测试，不纳入本项目测试规范描述。
- **未发现**: 独立的 `examples/**/tests/` 型样例工程测试。

- **已纳入 testing_guide / 主文档**: 是 — 第 3 批 `testing_guide.md` 以本清单为骨架（按"集成测试重心 → 单元测试形态 → 快照测试 → SDK 测试"组织）；主文档「常见任务速查」收录 `just test -p <crate>` 与 `cargo insta` 工作流。

### 推荐实践事实源

| 主题 | 事实源文件 | 证据位置 | 说明 |
| ---- | ---------- | -------- | ---- |
| 格式化与 lint 三步法 | `AGENTS.md` | AGENTS.md 顶部规则列表（just fmt / just test / just fix 段） | 明确 `just fmt` → `just test -p <crate>` → `just fix -p <crate>`，且禁止直接 `cargo test` |
| 抑制 core 膨胀 | `AGENTS.md` | AGENTS.md「## The codex-core crate」 | 维护者原话「resist adding code to codex-core」，可作为 crate 归属决策准则 |
| 模型上下文硬约束 | `AGENTS.md` | AGENTS.md「### Model visible context」 | 6 条：无历史重写、避免缓存失效、有界大小、单项 ≤10K token、>1k token 标 P0、片段须实现 `ContextualUserFragment` |
| app-server API 规范 | `AGENTS.md` | AGENTS.md「## App-server API Development Best Practices」 | v2 命名、camelCase、ts-rs 注解、游标分页、schema 再生成 |
| 集成测试写法 | `AGENTS.md` | AGENTS.md「#### codex_core integration testing」与「#### app-server integration testing」 | `TestCodexBuilder::build_with_auto_env()`、`mount_sse_once`、`ResponseMock` 断言 |
| TUI 样式约定 | AGENTS.md + `codex-rs/tui/styles.md` | AGENTS.md「## TUI style conventions」至「### Text wrapping」各节 | 约定 Stylize 助手、白色前景与 textwrap 换行的写法 |
| 贡献治理 | `docs/contributing.md` | `docs/contributing.md:3-17,31-42,72-88` | 受邀制、topic 分支、CLA 签署流程 |
| 变更规模控制 | `AGENTS.md` | AGENTS.md「### Change size guidance (800 lines)」 | ≤800 行（复杂逻辑 ≤500 行），超出需分阶段 |

### 最终验证命令

```bash
# 规模复核
git ls-files | wc -l
git ls-files "*.rs" | tr '\n' '\0' | xargs -0 cat | wc -l

# 框架边界复核（确认扫描结果不含框架文件）
python3 AI-Coding-Context/tools/py/project_scanner.py . --mode summary --exclude-standard

# Phase 1 hard gate
python3 AI-Coding-Context/tools/py/summary_validator.py --dir dev_docs/_analysis --recursive --strict

# 结构与语义检查（Python / JS 双套）
python3 AI-Coding-Context/tools/py/doc_health_checker.py --full-check --doc-dir dev_docs
node AI-Coding-Context/tools/js/doc_health_checker.js --full-check --doc-dir dev_docs
python3 AI-Coding-Context/tools/py/semantic_review_checker.py --full-check --doc-dir dev_docs --repo-root .
node AI-Coding-Context/tools/js/semantic_review_checker.js --full-check --doc-dir dev_docs --repo-root .
```

### 审核与确认留痕

- **方案生成完成时间**: 2026-08-03 12:45
- **等待人工审核状态**: 待审核
- **用户确认时间**: 未确认
- **进入正式生成时间**: 未开始

### 复查回写要求

当复查结论改变事实状态时，必须同步检查并更新本文档的摘要、正文、表格、待确认清单、行动计划、证据记录，以及 `project_analysis_report.md` 与 `generation_progress.md`。禁止只在文末追加"复查记录"而保留正文旧结论。

---

## 🔎 Phase 1 方案复查清单

- [x] 项目类型、技术栈、依赖、测试、部署方式均有 E2/E3/E4 证据；仅 E1 证据未写成强结论（四层扩展关系已标注为 E1 并列入代码级核查）
- [x] `证据与验证记录` 表包含 `证据等级` 列，25 条关键事实均可追溯来源文件或命令
- [x] 已建立关键事实清单与量化声明来源表；文件数、测试数、crate 数、大文件行数均记录了产出命令，后续修改需全文同步
- [x] 已填写 `1.3B 项目定位与不可破坏约束`（11 条），全部进入正式文档计划
- [x] 已填写 `1.3C AI/外部服务边界`（11 条），区分了默认在线路径、用户配置的本地模型路径与用户自带 MCP server，未混淆手动 Prompt 与外部服务
- [x] 子文档清单覆盖 3.4 节全部 7 类项目定位触发项；不单独成文的（用户手册、贡献流程、容器环境）已写明合并覆盖位置
- [x] 待用户确认项仅 3 项，均为使用意图与优先级偏好，已确认代码与仓库文档无法回答；7 项代码可答问题已移入"下一步代码级核查"
- [x] 每个待确认项均含 `当前保守结论`、`已检查证据`、`为什么代码或仓库文档无法回答`、`blocks_phase1`、`回写目标`
- [x] `docs/contributing.md` 受邀制、`AGENTS.md` 测试与格式化规则已纳入约束；本方案未提出任何与维护者规则冲突的修复待办
- [x] 风险与注意事项均有证据来源；无 E3 以下证据支撑的强结论
- [x] 质量保证措施与真实技术栈匹配，5 条检查命令均已在本机验证可执行
- [x] 复查结果已同步回写三件套
- [x] 下一步动作保持为"建议通过，等待用户确认"

---

## 🚀 执行计划

### 第 1 批（用户确认后执行）

1. `dev_docs/AI_Coding_Context.md` — 主文档（预计 2 小时）
2. `dev_docs/architecture_overview.md` — 架构总览（预计 1.5 小时）
3. `dev_docs/crate_map.md` — crate 地图（预计 2 小时，含逐 crate `Cargo.toml` 依赖采集）
4. `dev_docs/development_workflow.md` — 开发流程（预计 1.5 小时）
5. 目录结构：`dev_docs/plans/`、`dev_docs/knowledge/`（预计 0.5 小时）

**批次出口**: 执行脱敏强制扫描 → 提交 → `git push fork zibuyu`（禁止 `origin`）→ 向用户交付并请求审查写作深度与颗粒度，确认后再进入第 2 批。

### 第 2 批

`core_agent_loop.md`、`tools_and_sandbox.md`、`app_server_protocol.md`、`config_system.md`、`tui_guide.md`（预计 5-7 小时）

### 第 3 批

`testing_guide.md`、`mcp_and_extensions.md`、`auth_and_providers.md`、`build_and_release.md`、`session_and_persistence.md`（预计 4-6 小时）

### 第 4 批

`experimental_surfaces.md`、`observability.md`、`sdk_guide.md`、`dev_docs/rules/combined/AI_RULES.md`，随后执行首版质量验收并生成 `dev_docs/_analysis/health_check_report.md`（预计 4-6 小时；因用户要求展开全部实验性表面，较原估增加 2-3 小时）

---

## ✅ 审核清单（人工填写）

### 数据准确性审核

- [x] 项目规模数据已验证（5913 文件、1,270,789 行 Rust、134 crate）—— 第 2 轮复查已全部重跑复核
- [ ] 目录结构描述准确
- [ ] 17 个业务模块清单完整无遗漏
- [ ] 7 项架构特点识别准确

### 文档规划审核

- [x] 17 篇子文档清单合理（第 1 批 4 篇 + 第 2 批 5 篇 + 第 3 批 5 篇 + 第 4 批 3 篇）—— 用户已确认
- [ ] 主文档章节规划完整
- [ ] 12 个场景导航覆盖常见需求
- [ ] 未生成独立 `cli_usage.md` / `installation.md`（改为索引 `docs/` 与外部站点）的取舍可接受

### 待确认项决策

- [x] 待确认项 1：文档服务对象与深度定位 —— 用户答复：**兼顾**，维持方案原样
- [x] 待确认项 2：`dev_docs/` 是否纳入版本管理 —— 已解决：提交全部内容并推送个人 fork，不向上游推送
- [x] 待确认项 3：实验性表面的文档优先级 —— 用户答复：**全部展开**，第 4 批新增 `experimental_surfaces.md`

### 风险评估

- [ ] 覆盖度风险的缓解措施可接受
- [ ] 文档漂移的维护方案（路径 C 增量更新）可接受

---

## 📝 审核意见（人工填写）

### 需要修改的部分

_（待用户填写）_

### 需要补充的内容

_（待用户填写）_

### 批准意见

- [ ] **批准，可以开始生成文档**
- [ ] **需要修改后重新提交方案**
- [ ] **拒绝，原因如下**：_（待用户填写）_

---

**签名**: 待用户填写
**审核日期**: 待用户填写

---

## ⚠️ 风险应对预案 (Risk Mitigation Plan)

### 风险清单

| 风险 | 可能性 | 影响 | 应对措施 |
| :--- | :----: | :--: | :------- |
| 1.27M 行 Rust 无法全量覆盖 | 高 | 高 | 分 4 批 + 主文档显式声明「未覆盖范围」+ 优先覆盖 Top 10 crate |
| 超大文件（最大 12,616 行）无法一次读取 | 高 | 中 | 先 grep 结构概览（`^pub fn` / `^impl` / `^pub struct`），再分段读取关键部分 |
| 134 个 crate 依赖关系复杂 | 高 | 高 | 先从 `[workspace.dependencies]` 生成路径映射，再逐 crate 采集 `[dependencies]` 绘图 |
| 上游高速迭代导致文档漂移 | 高 | 中 | 记录基线 commit + `verified_at` + 后续走路径 C 增量更新 |
| AI token 限制导致会话中断 | 高 | 低 | 每批结束更新 `generation_progress.md`，支持断点续传 |
| Bazel 构建无法本地验证 | 中 | 中 | 相关结论降级为 E2，标注「未本机验证」，以 CI 工作流交叉参考 |
| Python 3.9.6 无法运行 SDK 测试 | 中 | 低 | Python SDK 章节标注 E2 级证据与本地验证前提 |
| 误将文档产物放入 `docs/` 违反 AGENTS.md 顶部规则列表（docs/ 条目） | 低 | 高 | 产物路径在方案中硬固定为 `dev_docs/`，并写入 AI_RULES |
| 文档质量不达标 | 低 | 高 | 每批结束执行质量检查清单；首版执行 5 项 checker 验收 |

### 应急处理流程

**遇到阻塞时**: 标记问题 → 跳过继续其他部分 → 汇总后统一向用户询问

**时间不足时**: 优先完成第 1、2 批（主文档 + 架构 + crate 地图 + 开发流程 + 核心运行时），第 3、4 批可后续补充

**质量不达标时**: 立即停止生成新文档 → 返工修复 → 重新评估剩余工作量

---

## ✅ 质量检查清单 (Quality Checklist)

### 准确性验证

- [ ] 所有代码示例路径可追溯（`文件:行号`）
- [ ] crate 地图与 `codex-rs/Cargo.toml` workspace members 完全一致
- [ ] 子命令清单与 `codex-rs/cli/src/main.rs` 的 `Subcommand` 枚举一致
- [ ] 配置项说明与 `codex-rs/core/config.schema.json` 一致
- [ ] AI Rules 与 `AGENTS.md` 无事实冲突

### 完整性验证

- [ ] 主文档包含全部子文档链接
- [ ] 架构总览含运行时拓扑 mermaid 图
- [ ] crate 地图含依赖分层 mermaid 图
- [ ] 至少 6 类核心代码模式有真实示例
- [ ] 「未覆盖范围」章节已明确列出

### 可用性验证

- [ ] 依据主文档能在 5 分钟内定位到 134 个 crate 中的目标 crate
- [ ] 「我要新增 X」类任务有 step-by-step 指引
- [ ] 所有 markdown 链接可跳转
- [ ] mermaid 图表可正确渲染

### 一致性验证

- [ ] 全部文档 frontmatter 符合 `SUMMARY_FORMAT_SPEC`（7 字段）
- [ ] `related_files` 路径均真实存在
- [ ] 文档间交叉引用有效
- [ ] 术语统一（crate 名一律使用 `codex-` 前缀全称）

---

## 🚨 首版验收被推翻的记录（第二轮独立审查）

> 本节是对本方案「执行计划」与「验证清单」的**事后修正记录**，写在这里是为了让后续任何按本方案续做的人第一时间看到：**首版验收的结论不成立**。

| 字段 | 值 |
| ---- | ---- |
| 首版验收结论 | `PASS_WITH_ACCEPTED_ISSUES`（7 项质量维度全部 ✅） |
| 复核方式 | 7 个独立代理从源码重新推导全部可核验断言 |
| 复核结果 | **15 项 HIGH 级事实错误**，分布在 12 篇文档中；另有约 45 项 MED、约 25 项 LOW |
| 改判后结论 | **FAIL** |
| 完整清单 | [`health_check_report.md`](./health_check_report.md) |

三条与本方案直接相关的教训：

1. **本方案的「关键事实记录」表本身留了错**。「CLI 子命令 23 个……已确认」在全部正式文档改用「27 个变体」之后仍未同步，导致首版验收报告中「四处全部已同步更正」的断言为假。**元文件也在验收范围内**，不能只查正式文档。
2. **「5 项 checker 全绿」被当成了「内容正确」**。这 5 个 checker 不做跨文档数值对账，也不校验「标题声明的计数」与「表格实际行数」是否相符；本轮 15 个 HIGH 全部落在其覆盖范围之外，其中 4 项属于 checker 的结构性盲区。
3. **证据等级越权是主要失误模式**：拿文件名列表下依赖结论（ext 依赖 8/12 被写成 12/12），拿类型定义与文件名下机制结论（Landlock 已废弃却被写成默认路径）。对应的硬规则已写入 `rules/combined/AI_RULES.md` §5.3。

---

## 📌 备注

- **框架边界**: 框架位于软链接 `AI-Coding-Context/ -> <本地工作区>/AI-Coding-Context`，已在所有扫描与统计中排除，扫描结果经验证不含框架文件。
- **产物路径**: 全部落在仓库根 `dev_docs/`，符合 AGENTS.md 顶部规则列表（docs/ 条目） 对 `docs/` 的限制。
- **既有文档关系**: 本体系不替代 `docs/` 与 developers.openai.com 的用户文档，定位为**面向开发者与 AI 代理的仓库内部导航与规范落地层**。
