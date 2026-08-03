---
title: Codex CLI 项目分析与问题报告
summary: 记录 openai/codex 仓库 Phase 1 分析阶段发现的风险、警告、疑问与建议，全部条目标注证据等级、当前状态、是否阻断 Phase 1 及回写目标，并前置说明维护者治理规则对建议边界的约束。
keywords: codex | analysis-report | risks | evidence-level | governance | phase1
scope: openai/codex 仓库首次文档生成前的问题与风险报告
related_files: AGENTS.md | docs/contributing.md | codex-rs/tui/src/bottom_pane/chat_composer.rs | codex-rs/otel/src/config.rs | codex-rs/analytics/src/client.rs | sdk/python/pyproject.toml
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-03
---

# Codex CLI - 分析与问题报告

## 📋 报告摘要

- **分析日期**: 2026-08-03
- **分析基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
- **项目规模**: 5913 个 Git 跟踪文件；Rust 2858 文件 / 1,270,789 行；130 个 Cargo crate
- **主要技术栈**: Rust 1.95.0 (edition 2024) / TypeScript / Python 3.10+ / Cargo + Bazel / pnpm
- **分析覆盖度**: 结构级 100%（全部目录与 workspace 成员已枚举）；源码级约 3%（已读取 `AGENTS.md`、`docs/contributing.md`、`codex-rs/Cargo.toml`、`codex-rs/cli/src/main.rs` 前 200 行，以及针对外部服务边界与遥测的定向 grep）

### 问题统计

| 严重程度 | 数量 | 状态 |
| -------- | ---- | -------- |
| 🔴 严重 | 0 | 无 |
| 🟡 警告 | 5 | 建议关注（均不阻断 Phase 1） |
| 🔵 疑问 | 3 | 需用户确认 |
| 💡 建议 | 4 | 可选优化 |

---

## ⚖️ 前置：维护者规则约束（阅读本报告前必读）

本仓库存在明确的治理约束，直接限定了本报告中"建议"的性质：

| 约束 | 证据 | 对本报告的影响 |
| ---- | ---- | -------------- |
| 外部代码贡献仅限受邀，未受邀 PR 直接关闭 | `docs/contributing.md:3-17`（"External contributions are by invitation only"、"Pull requests that have not been explicitly invited by a member of the Codex team will be closed without review"） | 本报告**不提出任何面向上游的修复待办**。所有代码层面的观察一律标注为"维护者规则约束下的长期观察"，不得作为 Phase 1 阻断项 |
| 测试策略由 `AGENTS.md` 规定 | `AGENTS.md:29-31`（"Do not add tests for values that are statically defined"、"Do not add negative tests for logic that was removed"）、`:112-124`（集成测试优先） | 本报告不建议新增测试；测试相关内容只做**现状记录**，落入 `testing_guide.md` |
| 格式化与 lint 流程固定 | `AGENTS.md:62-70`（`just fmt` / `just test -p` / `just fix -p`，禁止直接 `cargo test`） | 本报告不提出替代的格式化或测试命令 |
| 变更规模上限 800 行 | `AGENTS.md:125-131` | 任何"重构建议"若超出该规模，只能写为需分阶段的长期建议 |
| 禁止向 `docs/` 添加通用产品或用户文档 | `AGENTS.md:32` | 文档产物路径固定为仓库根 `dev_docs/` |

> [!IMPORTANT]
> 本报告的定位是**文档生成前的风险识别**，不是代码审计报告。未对上游代码执行安全或正确性审计，因此不产出 🔴 严重问题。

---

## 🔴 严重问题（必须修复）

**本次分析未发现 🔴 严重问题。**

原因说明（避免被误读为"已审计通过"）：

- Phase 1 的分析目标是**文档体系可行性与准确性风险**，而非代码缺陷。
- 已读取的源码占比约 3%，证据等级不足以支撑任何 P0 强结论。按框架证据等级规则（E3 以下不得写"必须修复"），此处不虚构严重问题。
- 本仓库为 Apache-2.0 上游仓库且外部贡献受邀制，即便发现代码缺陷也不属于本任务的可行动范围。

**blocks_phase1**: false

---

## 🟡 警告问题（建议关注）

### 警告 1: 文档产物落盘位置存在治理红线

- **问题类型**: 治理约束 / 文档体系设计
- **发现位置**: `AGENTS.md:32`
- **证据等级**: E2（仓库规范文件明文）
- **当前状态**: 已确认，已在方案中规避
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 1.3B 表 + 3.4 节 + `rules/combined/AI_RULES.md`

**问题描述**:

`AGENTS.md:32` 明文规定："Do not add general product or user-facing documentation to the `docs/` folder. The official Codex documentation lives elsewhere. The exception is app-server API documentation."

若本文档体系被放入 `docs/`，将直接违反仓库对 AI 代理的强制规范。

**影响评估**:

- 违反后果：与维护者规范正面冲突；若误提交将触发 review 拒绝
- 影响范围：全部 16 篇产物的落盘位置

**规避措施（已落实到方案）**:

- 全部产物固定在仓库根 `dev_docs/`，与 `docs/` 物理隔离
- `AI_RULES.md` 中显式写入"不得将 dev_docs 内容迁移进 docs/"
- 主文档「文档索引」章节只**链接** `docs/` 既有文档，不新增内容到 `docs/`

---

### 警告 2: 仓库自身规范与实测代码规模存在显著张力

- **问题类型**: 规范与现状不一致（历史遗留）
- **发现位置**: `AGENTS.md:49-61` vs 实测文件行数
- **证据等级**: E4（`git ls-files "*.rs" | xargs wc -l | sort -rn` 实测）+ E2（规范文本）
- **当前状态**: 已确认
- **blocks_phase1**: false
- **回写目标**: `development_workflow.md`、`tui_guide.md`、`AI_Coding_Context.md`「AI 编码禁忌」

**规范要求**（`AGENTS.md:49-61`）:

- "Target Rust modules under 500 LoC, excluding tests."
- "If a file exceeds roughly 800 LoC, add new functionality in a new module instead of extending the existing file"
- 点名高触碰文件：`codex-rs/tui/src/app.rs`、`codex-rs/tui/src/bottom_pane/chat_composer.rs`、`codex-rs/tui/src/bottom_pane/footer.rs`、`codex-rs/tui/src/chatwidget.rs`、`codex-rs/tui/src/bottom_pane/mod.rs`

**实测现状**（含测试代码，Top 10）:

| 文件 | 实测行数 |
| ---- | -------: |
| `codex-rs/tui/src/bottom_pane/chat_composer.rs` | 12,616 |
| `codex-rs/core/src/config/config_tests.rs` | 12,127 |
| `codex-rs/core/src/session/tests.rs` | 11,434 |
| `codex-rs/tui/src/app/tests.rs` | 7,520 |
| `codex-rs/tui/src/resume_picker.rs` | 6,681 |
| `codex-rs/core-plugins/src/manager_tests.rs` | 6,558 |
| `codex-rs/protocol/src/protocol.rs` | 6,349 |
| `codex-rs/app-server/tests/suite/v2/plugin_list.rs` | 5,478 |
| `codex-rs/app-server/src/request_processors/thread_processor.rs` | 5,442 |
| `codex-rs/core/tests/suite/compact.rs` | 5,440 |

**评价**:

- 规范中的 500/800 LoC 目标是**对新增代码的约束**，而非对存量文件的整改要求。`AGENTS.md:52-53` 的措辞是"add new functionality in a new module instead of extending the existing file"，与存量并不矛盾。
- 但若文档只复述规范而不给出实测现状，AI 与新人会在这些文件上产生误判。

**处理方式（非修复建议）**:

- `development_workflow.md` 与 `tui_guide.md` 中**并列呈现「规范要求」与「实测行数」两栏**
- 明确标注：这些是历史遗留的高触碰文件，**新代码不得继续堆入**，符合规范原意
- **不**提出对上游的拆分待办（受维护者规则约束）

---

### 警告 3: 本地 Python 版本低于 SDK 要求，无法取得 E4 级验证证据

- **问题类型**: 分析环境限制
- **发现位置**: `sdk/python/pyproject.toml:10`、`sdk/python-runtime/pyproject.toml:10` vs 本机运行时
- **证据等级**: E2（配置文件 `requires-python = ">=3.10"`）+ E4（`python3 --version` → `Python 3.9.6`）
- **当前状态**: 已确认
- **blocks_phase1**: false
- **回写目标**: `sdk_guide.md`、`testing_guide.md`、`generation_plan.md` 风险清单

**问题描述**:

本机 Python 为 3.9.6，低于 `sdk/python` 与 `sdk/python-runtime` 声明的 `requires-python = ">=3.10"`。因此本次分析无法通过实际运行 pytest 来验证 Python SDK 的测试拓扑与行为。

**影响评估**:

- `sdk_guide.md` 与 `testing_guide.md` 中 Python SDK 部分的证据等级上限为 E2/E3（配置 + 源码阅读），不能写"已验证"
- 不影响 Rust 主体（Rust 工具链未受影响）
- AICC 框架自身的 5 个 checker 已在 Python 3.9.6 下验证可运行（E4），不受此影响

**处理方式**:

- 相关章节显式标注"未在本机运行验证，结论基于配置与源码"
- 若用户后续升级 Python ≥3.10，可补跑测试将证据提升至 E4

---

### 警告 4: 文档覆盖度天然受限，存在"局部正确但整体片面"风险

- **问题类型**: 文档体系固有风险
- **发现位置**: 全仓库
- **证据等级**: E4（1,270,789 行 Rust 为实测值）
- **当前状态**: 已确认，方案已设缓解措施
- **blocks_phase1**: false
- **回写目标**: `AI_Coding_Context.md`「未覆盖范围」章节、`generation_plan.md` 风险清单

**问题描述**:

Rust 主体 1,270,789 行、130 个 crate。即便分 4 批生成 16 篇文档，源码级覆盖率也远低于 100%。若文档不声明边界，读者（尤其是 AI 代理）会误以为文档已完整描述系统。

**影响评估**:

- 风险：AI 依据不完整的架构描述做出错误改动
- 尤其在扩展机制（`ext/` 12 个 crate + `core-plugins` + `skills` + MCP 四条路径）上，关系尚未验证（当前仅 E1 级证据）

**缓解措施（已写入方案）**:

1. 每篇文档 frontmatter 的 `related_files` 精确列出**实际读过**的文件，不列未读文件
2. 主文档设「未覆盖范围」章节，逐条列出未深入的 crate
3. 优先覆盖代码量 Top 10 crate 与全部用户可见能力面（23 个 CLI 子命令）
4. 四层扩展机制的关系列为第 3 批的强制代码级核查项

---

### 警告 5: 遥测与埋点的默认行为尚未完整核实

- **问题类型**: 外部数据边界描述准确性
- **发现位置**: `codex-rs/otel/src/config.rs`、`codex-rs/analytics/src/client.rs`
- **证据等级**: E3（源码 grep 命中，但未读取完整初始化链路）
- **当前状态**: 待验证（已列入第 4 批代码级核查，**不进入用户确认清单**）
- **blocks_phase1**: false
- **回写目标**: `observability.md`、`generation_plan.md` 1.3C 表

**当前已知证据**:

| 事实 | 证据位置 | 原文要点 |
| ---- | -------- | -------- |
| 存在 Statsig 默认指标导出器 | `codex-rs/otel/src/config.rs:90` | 注释 `Statsig metrics ingestion exporter using Codex-internal defaults` |
| debug 构建下该默认导出器关闭 | `codex-rs/otel/src/config.rs:16`、测试 `:113` | 注释 `Keep the built-in Statsig default off in debug builds`；测试名 `statsig_default_metrics_exporter_is_disabled_in_debug_builds` |
| analytics 采用 opt-out 语义 | `codex-rs/analytics/src/client.rs:221` | `queue: (analytics_enabled != Some(false))` — 未显式设为 false 即启用入队 |
| analytics 网络投递当前关闭 | `codex-rs/analytics/src/client.rs:108` | 日志文案 `analytics event capture enabled; network delivery is disabled` |
| 存在显式禁用构造 | `codex-rs/analytics/src/client.rs:226` | `pub fn disabled()` |

**为何不写成强结论**:

上述证据来自定向 grep，未读取 `OtelSettings` / `StatsigMetricsSettings` 的完整字段定义、`provider.rs` 的初始化链路，也未确认 `analytics_enabled` 对应的 config.toml 键名。按证据等级规则，"release 构建默认开启遥测"这类结论需要完整调用链（E3 完整读取）才能成立。

**下一步动作**:

第 4 批 `observability.md` 生成时，完整读取 `codex-rs/otel/src/{config,provider,otlp,targets}.rs` 与 `codex-rs/analytics/src/{client,analytics_capture,events}.rs`，确认：

1. release 构建下 Statsig 导出器的实际默认值
2. `analytics_enabled` 的配置入口与默认值
3. "network delivery is disabled" 是编译期常量还是运行期条件

**注意**: 本项属**代码可回答**问题，按框架准入规则不得放入用户确认清单。

---

## 🔵 疑问事项（需用户确认）

> 以下 3 项已确认无法通过代码、配置、锁文件、README 或现有项目文档回答，属于用户使用意图与优先级偏好。完整字段见 `generation_plan.md` 的"需要人工确认的项目特性"章节。

### 疑问 1: 文档体系的服务对象与深度定位

- **疑问类型**: 使用意图
- **证据等级**: 不适用（非事实性问题）
- **当前状态**: 需用户确认
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 3.1-3.2 节、`AI_Coding_Context.md` 场景快速导航
- **为什么需要用户确认**: 仓库不记录任何单个使用者的意图；`git remote -v` 显示 origin 直指 `openai/codex`，当前分支 `zibuyu` 无法区分"阅读研究"与"二次开发"

**问题**:

本文档体系主要用于——

- **A. 阅读理解 upstream 代码**（关注"某功能在哪实现""这个 crate 干什么"）
- **B. 在本仓库做二次开发**（关注规范落地、测试、构建、提交流程）
- **C. 两者兼顾**

**当前保守结论**: 按 C（兼顾）处理。第 1 批 4 篇文档在三种定位下均为必需，故不阻塞。

**影响**:

- 选 A → 第 2 批应把 `core_agent_loop.md` 提前，加大「功能定位索引」比重，`development_workflow.md` 可精简
- 选 B → 维持当前批次顺序，强化 `testing_guide.md` 与 `build_and_release.md`
- 选 C → 维持方案原样

---

### 疑问 2: `dev_docs/` 是否纳入版本管理

- **疑问类型**: 工作流偏好
- **证据等级**: 不适用（非事实性问题）
- **当前状态**: 需用户确认
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 执行计划、`development_workflow.md`「本地开发环境」
- **为什么需要用户确认**: 仓库不可能记录使用者对自己新增本地目录的版本管理偏好

**已检查证据**:

- `git remote -v` → `origin  org-14957082@github.com:openai/codex.git`（直连上游，非 fork）
- `.gitignore`（931 字节）未包含 `dev_docs` 相关规则
- `docs/contributing.md:3-17` 外部贡献受邀制
- `git status` 显示当前 `AI-Coding-Context` 软链接为未跟踪状态

**当前保守结论**: **不提交**。第 1 批结束时建议写入 `.git/info/exclude`（仅本地生效，不修改仓库根的 gitignore 文件），避免误提交非受邀内容。

**需要用户确认**:

- [ ] 保持本地私有（写入 `.git/info/exclude`）
- [ ] 提交到版本库，并在 `.gitignore` 中排除 `dev_docs/_analysis/`（过程文件）
- [ ] 提交全部内容（含 `_analysis`）

---

### 疑问 3: 实验性与低频表面的文档优先级

- **疑问类型**: 优先级偏好
- **证据等级**: E3（实验性标记本身已由代码确认）
- **当前状态**: 需用户确认
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 3.2 节第 4 批清单、`crate_map.md`
- **为什么需要用户确认**: 代码能告诉我们"哪些是实验性的"，但无法告诉我们"用户是否关心它们"

**代码已确认的实验性标记**（`codex-rs/cli/src/main.rs`）:

| 子命令 | 行号 | 标记 |
| ------ | ---- | ---- |
| `AppServer` | 147 | `/// [experimental] Run the app server or related tooling.` |
| `RemoteControl` | 150 | `/// [experimental] Manage the app-server daemon with remote control enabled.` |
| `Cloud` | 195 | `/// [EXPERIMENTAL] Browse tasks from Codex Cloud and apply changes locally.` |
| responses-api-proxy | 199-200 | `#[clap(hide = true)]` `/// Internal: run the responses API proxy.` |
| `Execpolicy` | 173-174 | `#[clap(hide = true)]` |

另有 `codex-rs/v8-poc/`（目录名即 PoC）、`codex-rs/code-mode*`（4 个 crate）、`codex app` 桌面端（仅 macOS/Windows 条件编译，`main.rs:154-155`）。

**当前保守结论**: 上述表面在第 1-3 批中**仅在 `crate_map.md` 中登记为条目**，不单独展开；如需展开则进入第 4 批。

**需要用户确认**:

- [ ] 维持保守结论（仅登记）
- [ ] 需要展开某几项（请指明）
- [ ] 全部展开（第 4 批工作量将增加 2-3 小时）

---

## 💡 优化建议（可选）

### 建议 1: `crate_map.md` 采用可复现的生成方式而非纯手写

- **建议类型**: 文档可维护性
- **证据等级**: E4（130 个 crate 为 `codex-rs/Cargo.toml` 实测计数）
- **当前状态**: 待用户决策
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 第 1 批执行计划

**当前状态**: 130 个 crate 的清单若纯手写，上游每次新增 crate 都会造成漂移。

**建议**: 在 `dev_docs/` 下附一段可复现的采集命令（读取 `codex-rs/Cargo.toml` 的 `[workspace] members` 与各 crate `Cargo.toml`），把 crate 表格的"数据来源"固化为命令而非记忆。文档中同时保留生成时间与基线 commit。

**收益**: 后续走框架路径 C（`@commit` 增量更新）时可快速重跑比对，降低漂移检测成本。

**成本**: 第 1 批增加约 0.5 小时。

**优先级**: 💡 P2

---

### 建议 2: AI_RULES.md 只做索引，不复制 AGENTS.md 全文

- **建议类型**: 避免双份事实源漂移
- **证据等级**: E2（`AGENTS.md` 22,519 字节，是仓库对 AI 的既有强制规范）
- **当前状态**: 已采纳并写入方案
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 3.3 节（已写入）

**理由**: `AGENTS.md` 是仓库自带的 AI 规范事实源，且随上游持续更新。若 `AI_RULES.md` 复制其内容，会立即产生两份可能冲突的规范。

**建议内容结构**:

1. 指向 `AGENTS.md` 的强制引用（"以 AGENTS.md 为准，本文件不覆盖其任何条款"）
2. dev_docs 文档体系导航
3. dev_docs 特有约定（产物路径固定 `dev_docs/`、`related_files` 精确性要求、基线 commit 记录）

**优先级**: 💡 P1（已采纳）

---

### 建议 3: 为文档体系建立基线 commit 与漂移检查节奏

- **建议类型**: 文档时效性
- **证据等级**: E4（`git log -1` 显示基线 commit 当日合入，上游迭代频繁）
- **当前状态**: 待用户决策
- **blocks_phase1**: false
- **回写目标**: `AI_Coding_Context.md`、`development_workflow.md`

**建议**:

- 每篇文档 frontmatter 记录 `verified_at`，正文记录基线 commit
- 后续使用框架路径 C（`@commit` 增量更新）在拉取上游后触发局部更新
- 关注高漂移区：`codex-rs/Cargo.toml`（crate 增减）、`AGENTS.md`（规范变更）、`codex-rs/cli/src/main.rs`（子命令增减）、`codex-rs/app-server-protocol/`（协议变更）

**优先级**: 💡 P1

---

### 建议 4: 将「未覆盖范围」做成显式清单而非免责声明

- **建议类型**: 文档诚实性
- **证据等级**: E4（覆盖度限制为实测规模推导）
- **当前状态**: 已采纳并写入方案
- **blocks_phase1**: false
- **回写目标**: `AI_Coding_Context.md`

**建议**: 主文档中不写"本文档可能不完整"这类空泛免责，而是列出**具体未深入的 crate 名单**（例如 `v8-poc`、`bwrap`、`network-proxy`、`aws-auth`、`agent-graph-store` 等），让读者与 AI 能准确判断"哪里必须回去读代码"。

**优先级**: 💡 P1（已采纳）

---

## 🔍 架构观察

> 以下为分析过程中的中立观察，非问题。已确认证据等级，将作为正式文档的骨架输入。

### 观察 1: 单二进制多前端的收敛式架构

- **证据等级**: E3
- **发现**: `codex-rs/cli/Cargo.toml` 定义唯一主二进制 `codex`；`codex-rs/cli/src/main.rs:123-215` 的 `Subcommand` 枚举分发到 TUI / exec / app-server / mcp-server / cloud / responses-api-proxy 等入口；`main.rs:9-10` 使用 `codex_arg0::arg0_dispatch_or_else` 支持通过 argv[0] 分发
- **评价**: 这是理解整个项目的第一把钥匙 —— 所有前端共享同一份 codex-core crate。文档必须以此为主线组织。

### 观察 2: 协议先行的类型单一事实源

- **证据等级**: E2 + E3
- **发现**: `codex-rs/app-server-protocol/schema/typescript/v2/` 下有 550 个自动生成的 TS 类型文件；`AGENTS.md:277` 要求 v2 类型必须标注 `#[ts(export_to = "v2/")]`；`AGENTS.md:300-304` 规定 API 形状变更后需跑 `just write-app-server-schema` 并用 `just test -p codex-app-server-protocol` 验证
- **评价**: Rust 类型是唯一事实源，TS 类型为构建产物。文档中不得把生成的 TS 文件描述为"手写代码"。

### 观察 3: 三平台原生沙箱 + 独立执行服务

- **证据等级**: E3（沙箱实现）+ E2（跨 OS 分离）
- **发现**: `codex-rs/sandboxing/src/` 同时含 `seatbelt.rs` / `landlock.rs` / `bwrap.rs` / `windows.rs` 与 3 个 `.sbpl` 策略文件；另有独立 crate `linux-sandbox`、`windows-sandbox-rs`、`bwrap`、`execpolicy`、`shell-escalation`；`AGENTS.md:321-322` 声明 app-server 与 exec-server 可运行在不同操作系统
- **评价**: 沙箱是本项目的核心差异化能力，且与 `AGENTS.md:8-10` 的 `CODEX_SANDBOX_*` 红线直接相关，必须单独成文。

### 观察 4: 双构建系统带来的双锁同步义务

- **证据等级**: E2
- **发现**: `MODULE.bazel`（16,677 字节）+ `MODULE.bazel.lock`（1,547,127 字节）与 `codex-rs/Cargo.lock` 并存；`AGENTS.md:37-39` 要求依赖变更后跑 `just bazel-lock-update` 并同 PR 提交，CI 校验漂移；`AGENTS.md:40-43` 提醒 `include_str!` / `sqlx::migrate!` 等编译期文件读取需在 `BUILD.bazel` 补 `compile_data`
- **评价**: 高频踩坑点，`build_and_release.md` 必须给出明确流程。

### 观察 5: 四条并行的扩展路径

- **证据等级**: E1（目录存在性），关系待验证
- **发现**: `codex-rs/ext/`（12 个内建扩展 crate）、`codex-rs/core-plugins/`（37,038 行插件运行时）、`codex-rs/skills/`（含 plugin-creator / skill-creator / skill-installer 样例）、MCP 客户端与服务端（`codex-mcp` / `mcp-server` / `rmcp-client` / `ext/mcp`）
- **评价**: 四条路径并存但**相互关系尚未验证**。这是当前证据等级最薄弱的架构点，已列为第 3 批强制代码级核查项，正式文档中不得凭目录名推断其关系。

### 观察 6: 仓库内文档极薄，外部站点承载产品文档

- **证据等级**: E4
- **发现**: `docs/config.md` 仅 15 行、`codex-rs/config.md` 仅 6 行、`docs/sandbox.md` 仅 3 行且正文为指向 developers.openai.com 的外链；`codex-rs/README.md` 仅 3 行
- **评价**: 这正是本文档体系的价值空间 —— 仓库缺少**面向开发者的架构与规范落地层**。同时也解释了 `AGENTS.md:32` 的用意：产品文档在别处维护，`docs/` 不该被塞入通用文档。

---

## 📊 风险假设与证据等级

| 风险假设 | 证据等级 | 当前证据 | 验证状态 | 下一步验证动作 | 是否可定优先级 |
| -------- | -------- | -------- | -------- | -------------- | -------------- |
| 文档产物若落入 `docs/` 将违反仓库规范 | E2 | `AGENTS.md:32` | 已确认 | 无需进一步验证（方案已规避） | P1（已落实） |
| 高触碰大文件会持续吸引无关改动 | E2 + E4 | `AGENTS.md:54-57` 点名清单 + `wc -l` 实测 12,616 行 | 已确认 | 无需进一步验证 | 否（受维护者规则约束，仅记录） |
| Python SDK 章节无法取得 E4 证据 | E2 + E4 | `pyproject.toml:10` `>=3.10` + 本机 `Python 3.9.6` | 已确认 | 用户升级 Python 后可补跑 pytest | 否 |
| 四层扩展机制的关系可能被误述 | E1 | 仅目录存在性 | 待验证 | 第 3 批读取 `ext/extension-api/src/lib.rs`、`core-plugins/src/manager.rs`、`skills/src/lib.rs` 公开 API | P1 |
| release 构建下遥测默认开启 | E3（部分） | `otel/src/config.rs:16,90,113` grep 命中 | 待验证 | 第 4 批完整读取 `otel/src/{config,provider,otlp}.rs` 与 `analytics/src/client.rs` 投递链路 | P1 |
| app-server ↔ exec-server 跨 OS 分离的传输实现 | E2 | `AGENTS.md:321-322` + crate 存在性 | 待验证 | 第 2 批读取 `exec-server-protocol/src/`、`app-server-transport/src/`、`uds/src/` | P1 |
| `find_codex_home` 存在两处同名实现可能造成描述冲突 | E3 | `codex-rs/core/src/config/mod.rs:4578` 与 `codex-rs/utils/home-dir/src/lib.rs:13` 均定义 `pub fn find_codex_home` | 待验证 | 第 2 批读取两处实现，确认调用关系（委托 or 重复） | P1 |
| 上游高速迭代导致文档快速过期 | E4 | `git log -1` 基线 commit 与分析同日；近 5 次提交均为当日/近日 PR | 已确认 | 建立路径 C 增量更新节奏 | P1 |
| 文档覆盖度不足导致 AI 误判 | E4 | 1,270,789 行 Rust vs 16 篇文档 | 已确认 | 主文档「未覆盖范围」显式清单 | P1（已落实缓解） |

**证据等级规则复述**:

- E1：目录结构、文件名、文件数量 → 只能写"疑似""风险假设""建议后续验证"
- E2：配置文件、锁文件、README、项目文件 → 可写"已从配置确认"
- E3：源码片段、协议、关键函数、调用链 → 可写"代码显示""实现方式为"
- E4：构建、测试、脚本运行、工具检查结果 → 可写"已验证""检查通过/失败"

本报告未出现任何缺乏 E3 证据支撑的 `P0` 或"必须修复"结论。

---

## ✅ 审核与行动计划

### 用户审核清单

**严重问题确认**:

- 无 🔴 严重问题需确认

**警告确认（知悉即可，不需要行动）**:

- [ ] 警告 1: 文档产物落在仓库根 `dev_docs/`，禁止放入 `docs/` — 已在方案中规避
- [ ] 警告 2: 规范目标与存量大文件的张力 — 文档将并列呈现规范与实测
- [ ] 警告 3: 本机 Python 3.9.6 < SDK 要求 3.10 — 相关章节降级为 E2 证据
- [ ] 警告 4: 覆盖度限制 — 主文档设「未覆盖范围」显式清单
- [ ] 警告 5: 遥测默认行为待核实 — 第 4 批代码级核查，不需用户回答

**疑问确认（需用户回答）**:

- [ ] 疑问 1: 文档服务对象与深度定位 —— 用户回答：_（待填写）_
- [ ] 疑问 2: `dev_docs/` 是否纳入版本管理 —— 用户回答：_（待填写）_
- [ ] 疑问 3: 实验性表面的文档优先级 —— 用户回答：_（待填写）_

**优化建议决策**:

- [ ] 建议 1（crate 地图可复现生成）: [ ] 采纳 [ ] 暂不采纳
- [ ] 建议 2（AI_RULES 只做索引）: 已在方案中采纳
- [ ] 建议 3（基线 commit 与漂移检查节奏）: [ ] 采纳 [ ] 暂不采纳
- [ ] 建议 4（未覆盖范围显式清单）: 已在方案中采纳

---

### 行动计划

**阶段 1: Phase 1 收尾（当前）**

- [x] 生成 `_analysis` 三件套
- [x] 执行 Phase 1 自检门（5 项 checker）
- [ ] 用户答复上述 3 项待确认事项并批准方案

**阶段 2: 正式生成（用户确认后）**

- [ ] 第 1 批：主文档 + `architecture_overview.md` + `crate_map.md` + `development_workflow.md`
- [ ] 第 1 批出口：请求用户审查写作深度与颗粒度
- [ ] 第 2-4 批：按 `generation_plan.md` 执行计划推进

**阶段 3: 长期观察（不作为待办）**

- 高触碰大文件的演进（受维护者规则约束，仅记录不建议整改）
- 上游 `AGENTS.md` 规范变更（触发文档同步）
- 四层扩展机制的架构演进

---

## 📝 后续行动

### 立即行动

1. **用户审核本报告** — 重点是 3 项疑问
2. **用户批准 `generation_plan.md`** — 确认 16 篇子文档清单与 4 批执行计划
3. **进入第 1 批正式生成**

### 文档生成建议

**本报告未发现阻断文档生成的问题，建议在用户确认 3 项疑问后即可进入正式生成。**

理由：

- 无 🔴 严重问题
- 5 项警告均已有缓解措施，且全部 `blocks_phase1 = false`
- 3 项疑问均有可执行的保守结论，不阻塞第 1 批的 4 篇文档

**建议流程**:

```
1. 生成 _analysis 三件套                    ✅ 已完成
2. 执行 Phase 1 自检门（5 项 checker）       ✅ 已完成
3. 用户审核并回答 3 项疑问                   ⏸️ 当前位置
4. 用户批准方案
5. 第 1 批正式生成 → 用户审查颗粒度
6. 第 2-4 批 → 首版质量验收
```

---

## 📅 报告元信息

- **生成者**: AI Assistant（AICC 框架路径 A / Step 6）
- **生成日期**: 2026-08-03
- **分析时长**: 约 2 小时
- **分析基线**: commit `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
- **下次审查**: 第 1 批文档生成完成后，或上游 `AGENTS.md` 发生变更时

---

## 🔗 相关文档

- [文档生成方案](./generation_plan.md)
- [生成进度记录](./generation_progress.md)

---

**重要提醒**:

1. 本报告包含 AI 的观察与建议，需要人工判断
2. 本仓库外部贡献受邀制（`docs/contributing.md:3-17`），报告中的所有代码层面观察均为**长期记录**而非行动待办
3. 本报告未执行代码安全或正确性审计，"0 个严重问题"不等于"代码无缺陷"
