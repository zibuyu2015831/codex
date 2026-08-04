---
title: Codex CLI 项目分析与问题报告
summary: 记录 openai/codex 仓库 Phase 1 分析阶段发现的风险、警告、疑问与建议，全部条目标注证据等级、当前状态、是否阻断 Phase 1 及回写目标，并前置说明维护者治理规则对建议边界的约束；已含第 2 轮复查结果（更正 Cargo crate 计数、解决版本管理疑问、新增公开发布脱敏红线警告），以及第二轮独立审查新增的警告 7——自验收流程本身不足以发现事实错误，首版验收在 15 项 HIGH 级事实错误存在的情况下判定通过，现已改判为 FAIL。
keywords: codex | analysis-report | risks | evidence-level | governance | phase1 | self-acceptance-gap
scope: openai/codex 仓库首次文档生成前的问题与风险报告
related_files: AGENTS.md | docs/contributing.md | codex-rs/tui/src/bottom_pane/chat_composer.rs | codex-rs/otel/src/config.rs | codex-rs/analytics/src/client.rs | sdk/python/pyproject.toml
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-03
---

# Codex CLI - 分析与问题报告

## 📋 报告摘要

- **分析日期**: 2026-08-03
- **分析基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
- **项目规模**: 5913 个 Git 跟踪文件（基线 commit 口径）；Rust 2858 文件 / 1,270,789 行；**134 个 Cargo workspace crate**（`cargo metadata --no-deps` 计数；`[workspace] members` 显式 128 项）
- **主要技术栈**: Rust 1.95.0 (edition 2024) / TypeScript / Python 3.10+ / Cargo + Bazel / pnpm
- **复查轮次**: 第 2 轮（2026-08-03，用户再次要求方案自审后触发；第 1 轮结论及本轮更正见 `generation_progress.md`）
- **分析覆盖度**: 结构级 100%（全部目录与 workspace 成员已枚举）；源码级约 3%（已读取 `AGENTS.md`、`docs/contributing.md`、`codex-rs/Cargo.toml`、`codex-rs/cli/src/main.rs` 前 200 行，以及针对外部服务边界与遥测的定向 grep）

### 问题统计

| 严重程度 | 数量 | 状态 |
| -------- | ---- | -------- |
| 🔴 严重 | 0 | 无 |
| 🟡 警告 | 7 | 建议关注（警告 1-5 不阻断 Phase 1；警告 6 为第 2 轮复查新增；警告 7 为第二轮独立审查新增） |
| 🔵 疑问 | 0 | **全部结案**（3 项：疑问 2 由用户行动解决，疑问 1、3 已获用户答复） |
| 💡 建议 | 4 | 可选优化 |

> 计数口径：🟡 一栏的数字等于下方 `### 警告 N` 小节的实际个数（当前 7 个），🔵 一栏为**仍待用户回答**的疑问数（当前 0；`### 疑问 N` 小节仍保留 3 个已结案条目，供追溯）。

> 第 2 轮复查的净变化：新增警告 1 项（公开发布脱敏红线）、解决疑问 1 项（版本管理）、更正事实 1 项（Cargo crate 数 130 → 134）。
>
> 第二轮独立审查的净变化：新增警告 1 项（警告 7，自验收流程不足以发现事实错误）；首版验收结论由 `PASS_WITH_ACCEPTED_ISSUES` 改判为 **FAIL**，15 项 HIGH 级事实错误清单见 [`health_check_report.md`](./health_check_report.md)。
>
> **用户确认（2026-08-03）**：方案审核通过。疑问 1 答复「兼顾」，与保守结论一致，方案不变；疑问 3 答复「全部展开」，第 4 批新增 `experimental_surfaces.md`，正式文档由 16 篇增至 **17 篇**。已授权进入正式文档生成。

---

## ⚖️ 前置：维护者规则约束（阅读本报告前必读）

本仓库存在明确的治理约束，直接限定了本报告中"建议"的性质：

| 约束 | 证据 | 对本报告的影响 |
| ---- | ---- | -------------- |
| 外部代码贡献仅限受邀，未受邀 PR 直接关闭 | `docs/contributing.md:3-17`（"External contributions are by invitation only"、"Pull requests that have not been explicitly invited by a member of the Codex team will be closed without review"） | 本报告**不提出任何面向上游的修复待办**。所有代码层面的观察一律标注为"维护者规则约束下的长期观察"，不得作为 Phase 1 阻断项 |
| 测试策略由 `AGENTS.md` 规定 | AGENTS.md 顶部规则列表（测试条目）（"Do not add tests for values that are statically defined"、"Do not add negative tests for logic that was removed"）、「### Test authoring guidance」（集成测试优先） | 本报告不建议新增测试；测试相关内容只做**现状记录**，落入 `testing_guide.md` |
| 格式化与 lint 流程固定 | AGENTS.md 顶部规则列表（just fmt / just test / just fix 段）（`just fmt` / `just test -p` / `just fix -p`，禁止直接 `cargo test`） | 本报告不提出替代的格式化或测试命令 |
| 变更规模上限 800 行 | AGENTS.md「### Change size guidance (800 lines)」 | 任何"重构建议"若超出该规模，只能写为需分阶段的长期建议 |
| 禁止向 `docs/` 添加通用产品或用户文档 | AGENTS.md 顶部规则列表（docs/ 条目） | 文档产物路径固定为仓库根 `dev_docs/` |

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
- **发现位置**: AGENTS.md 顶部规则列表（docs/ 条目）
- **证据等级**: E2（仓库规范文件明文）
- **当前状态**: 已确认，已在方案中规避
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 1.3B 表 + 3.4 节 + `dev_docs/rules/combined/AI_RULES.md`

**问题描述**:

AGENTS.md 顶部规则列表（docs/ 条目） 明文规定："Do not add general product or user-facing documentation to the `docs/` folder. The official Codex documentation lives elsewhere. The exception is app-server API documentation."

若本文档体系被放入 `docs/`，将直接违反仓库对 AI 代理的强制规范。

**影响评估**:

- 违反后果：与维护者规范正面冲突；若误提交将触发 review 拒绝
- 影响范围：全部 17 篇产物的落盘位置

**规避措施（已落实到方案）**:

- 全部产物固定在仓库根 `dev_docs/`，与 `docs/` 物理隔离
- `AI_RULES.md` 中显式写入"不得将 dev_docs 内容迁移进 docs/"
- 主文档「文档索引」章节只**链接** `docs/` 既有文档，不新增内容到 `docs/`

---

### 警告 2: 仓库自身规范与实测代码规模存在显著张力

- **问题类型**: 规范与现状不一致（历史遗留）
- **发现位置**: AGENTS.md 顶部规则列表（Avoid large modules 条目） vs 实测文件行数
- **证据等级**: E4（`git ls-files "*.rs" | xargs wc -l | sort -rn` 实测）+ E2（规范文本）
- **当前状态**: 已确认
- **blocks_phase1**: false
- **回写目标**: `development_workflow.md`、`tui_guide.md`、`AI_Coding_Context.md`「AI 编码禁忌」

**规范要求**（AGENTS.md 顶部规则列表（Avoid large modules 条目））:

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

- 规范中的 500/800 LoC 目标是**对新增代码的约束**，而非对存量文件的整改要求。AGENTS.md 顶部规则列表（Avoid large modules 条目） 的措辞是"add new functionality in a new module instead of extending the existing file"，与存量并不矛盾。
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

Rust 主体 1,270,789 行、134 个 crate。即便分 4 批生成 17 篇文档，源码级覆盖率也远低于 100%。若文档不声明边界，读者（尤其是 AI 代理）会误以为文档已完整描述系统。

**影响评估**:

- 风险：AI 依据不完整的架构描述做出错误改动
- 尤其在扩展机制（`ext/` 12 个 crate + `core-plugins` + `skills` + MCP 四条路径）上，关系尚未验证（当前仅 E1 级证据）

**缓解措施（已写入方案）**:

1. 每篇文档 frontmatter 的 `related_files` 精确列出**实际读过**的文件，不列未读文件
2. 主文档设「未覆盖范围」章节，逐条列出未深入的 crate
3. 优先覆盖代码量 Top 10 crate 与全部用户可见能力面（`Subcommand` 枚举共 27 个变体，其中 3 个 `#[clap(hide = true)]`、1 个仅 macOS/Windows 条件编译，故 Linux 上可见 23 个、macOS/Windows 上 24 个）
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

### 警告 6: 文档产物已进入公开仓库，脱敏要求升级为硬性红线

- **问题类型**: 信息披露边界
- **发现位置**: 个人 fork `zibuyu2015831/codex`（`isPrivate: false`）
- **证据等级**: E4（`gh repo view --json isPrivate` 实跑 + `git push` 结果确认）
- **当前状态**: 已确认，已执行首次脱敏；对后续批次持续生效
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 安全与脱敏章节、`dev_docs/rules/combined/AI_RULES.md`
- **新增轮次**: 第 2 轮复查（第 1 轮时产物尚为本地文件，无此风险面）

**问题描述**:

第 1 轮生成时，`_analysis` 三件套是纯本地文件，框架的脱敏规则主要约束"正式文档"。用户随后将其提交并推送至**公开** fork，风险面发生实质变化：**`dev_docs/` 下的每一个字节都成为公开可检索内容**，且 GitHub 会长期缓存，删除提交也不保证内容立即消失。

**已执行的处置（E4）**:

| 项 | 结果 |
| ---- | ---- |
| 本地绝对路径扫描 | 命中 6 处指向本机 home 的框架软链接绝对路径，已全部替换为 `<本地工作区>/AI-Coding-Context` |
| 凭证类值扫描 | `grep -niE "(api[_-]?key\|token\|secret\|password\|credential)...[\"'][A-Za-z0-9_-]{12,}"` 无命中 |
| 框架软链接 | 未提交（写入 `.git/info/exclude`） |
| 脱敏后回归 | 5 项 checker 复跑均 exit_code=0 |

**对后续 17 篇正式文档的硬性约束**:

1. 禁止写入真实 API key、token、私钥、`auth.json` / `.credentials.json` 的**值**；只允许出现变量名、配置键名与文件路径
2. 禁止写入本地绝对路径、主机名、内网地址、个人邮箱
3. 引用测试 fixture 中的凭证样本时，只写文件路径与字段名，不复制值
4. 每批提交前必须复跑本节的两条扫描命令，结果记入 `generation_progress.md`

> [!NOTE]
> 这是一条**流程约束**，不是对上游仓库的问题指控 —— 上游代码本身未发现凭证泄露。

---

### 警告 7: 自验收流程本身不足以发现事实错误

- **问题类型**: 流程缺陷（本文档体系自身）
- **发现位置**: 首版 `health_check_report.md` 与本体系的自检门设计
- **证据等级**: E4（5 项 checker 实跑结果）+ E3（7 个独立代理逐条回源码复核）
- **当前状态**: 已确认，修复计划见 `health_check_report.md`
- **blocks_phase1**: false（Phase 1 已结束；本条约束的是验收阶段）
- **回写目标**: `dev_docs/rules/combined/AI_RULES.md` §5.3 与 §6、`generation_plan.md` 的验证清单
- **新增轮次**: 第二轮独立审查

**问题描述**:

首版自验收判定 `PASS_WITH_ACCEPTED_ISSUES`，7 项质量维度全部标 ✅。第二轮由 7 个独立代理从源码重新推导全部可核验断言后，查出 **15 项 HIGH 级事实错误**，分布在 12 篇文档中；其中 6 项恰是首版验收里被宣称「已用代码级核查闭合」的结论。首版结论因此不成立，已改判为 **FAIL**。

**根因不是某个人写错了，而是验收方法本身有洞**:

| 洞 | 表现 |
| ---- | ---- |
| 把「门禁全绿」当成「内容正确」 | 5 项 checker 在 15 项 HIGH 存在期间始终 exit_code=0 |
| checker 不做跨文档数值对账 | 同一事实在不同文档写不同数值可以全绿通过（本轮 4 例） |
| checker 不校验「标题声明的计数」与「表格实际行数」是否相符 | 标题写 20，同页表格列 23 行，仍全绿 |
| 自验收由生成者本人执行 | 生成时的错误前提在验收时被原样继承，尤其是「读了类型定义没读使用方」这类错误 |

**改进方向**:

1. 事实类断言的验收改由**独立代理**执行，且不得读生成者的结论，只读源码；
2. 新增跨文档数值对账 checker，纳入提交前门禁；
3. 依赖类与机制类断言的取证方式写成硬规则（已落入 `dev_docs/rules/combined/AI_RULES.md` §5.3）；
4. 元文件（`_analysis` 四件套）与正式文档同等纳入事实核查范围——本轮的 H15 就出在元文件上。

> [!WARNING]
> 这条警告的价值在于**它推翻的是本体系自己的结论**。在读取本体系任何一篇文档时，请把 `health_check_report.md` 的 HIGH 清单一并当作阅读前提。

---

## 🔵 疑问事项（需用户确认）

> 第 1 轮提出 3 项，**当前全部结案**：疑问 2 由用户的实际操作解决，疑问 1、3 已于 2026-08-03 获用户明确答复。全部条目保留在下方并标注结论，不删除，以保持复查可追溯。完整字段见 `generation_plan.md` 的"需要人工确认的项目特性"章节。

### 疑问 1: 文档体系的服务对象与深度定位

- **疑问类型**: 使用意图
- **证据等级**: 不适用（非事实性问题）
- **当前状态**: **已获用户答复 —— 兼顾（选项 C）**，与保守结论一致，方案不做调整
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 3.1-3.2 节、`AI_Coding_Context.md` 场景快速导航
- **为什么需要用户确认**: 仓库不记录任何单个使用者的意图。第 2 轮复查新增的证据（用户已建立个人 fork `zibuyu2015831/codex` 并推送 `zibuyu` 分支）说明存在**长期留存**意图，但仍无法区分"阅读研究"与"二次开发"——两者都会这么做

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

### 疑问 2: `dev_docs/` 是否纳入版本管理 —— ✅ 已由用户行动解决（第 2 轮复查）

- **疑问类型**: 工作流偏好
- **证据等级**: E4（`git log`、`git remote -v`、`gh repo view` 实跑确认）
- **当前状态**: **已解决，不再需要用户回答**
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 执行计划、`development_workflow.md`「本地开发环境」

**第 1 轮时的保守结论（已被推翻）**: 当时依据 `git remote -v` 只有 `origin  <上游 SSH remote，已脱敏>`（直连上游、非 fork）、仓库根 gitignore 文件无 dev_docs 规则，给出的保守结论是**不提交**，并写入本地 exclude 文件。

**用户实际采取的行动（E4 证据）**:

| 事实 | 证据 |
| ---- | ---- |
| `_analysis` 三件套已提交 | commit `8224f7c034`（`docs: add dev_docs Phase 1 analysis artifacts`），分支 `zibuyu` |
| 已建立个人 fork | `gh repo view zibuyu2015831/codex` → `isFork: true`，`parent: openai/codex` |
| 新增 push 目标 | `git remote -v` 现含 `fork  https://github.com/zibuyu2015831/codex.git`；`zibuyu` 分支已 `--set-upstream` 到 `fork/zibuyu` |
| 上游仓库未被写入 | `origin` 始终只读，无任何 push 记录 |
| 框架软链接未入库 | `AI-Coding-Context` 已写入 `.git/info/exclude`，未提交 |

**最终结论**: **提交全部内容（含 `_analysis`），推送至个人 fork，不向上游 `origin` 推送任何内容。** 仓库根 `.gitignore` 未被修改，符合"不改动上游文件"的原则。

**对后续批次的约束（已生效）**:

1. 第 1–4 批的全部正式文档同样落在 `dev_docs/` 并提交至 `fork/zibuyu`
2. 任何 push 操作的目标必须显式写 `fork`，禁止 `git push origin`
3. 产物已进入**公开**仓库，脱敏要求升级为硬性红线 —— 见 🟡 警告 6

---

### 疑问 3: 实验性与低频表面的文档优先级

- **疑问类型**: 优先级偏好
- **证据等级**: E3（实验性标记本身已由代码确认）
- **当前状态**: **已获用户答复 —— 全部展开**，第 4 批新增 `experimental_surfaces.md`
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

**当前保守结论**（已被用户答复取代）: 上述表面在第 1-3 批中仅在 `crate_map.md` 中登记为条目，不单独展开。

**用户答复（2026-08-03）**:

- [ ] 维持保守结论（仅登记）
- [ ] 需要展开某几项
- [x] **全部展开** ✅

**落地方式**: 第 4 批新增 `dev_docs/experimental_surfaces.md`（预计 500-700 行），覆盖 `Cloud`/`cloud-tasks`、桌面端 `codex app`、`remote-control`、`responses-api-proxy`、`v8-poc`、`code-mode` 共 6 项。正式文档总数由 16 篇增至 17 篇，第 4 批工时由 2-3 小时调整为 4-6 小时。每节强制首行标注当前成熟度与可见性，并注明上游可能随时变更或移除。

---

## 💡 优化建议（可选）

### 建议 1: `crate_map.md` 采用可复现的生成方式而非纯手写

- **建议类型**: 文档可维护性
- **证据等级**: E4（134 个 crate 为 `cargo metadata --no-deps` 实跑计数）
- **当前状态**: 待用户决策
- **blocks_phase1**: false
- **回写目标**: `generation_plan.md` 第 1 批执行计划

**当前状态**: 134 个 crate 的清单若纯手写，上游每次新增 crate 都会造成漂移。第 2 轮复查中该数值本身即从错误的 130 更正为 134，正说明手写计数不可靠。

**建议**: 在 `dev_docs/` 下附一段可复现的采集命令（以 `cargo metadata --no-deps` 为权威来源，辅以各 crate `Cargo.toml`），把 crate 表格的"数据来源"固化为命令而非记忆。文档中同时保留生成时间与基线 commit。

> 提升为 P1：第 2 轮复查证实纯手写/近似计数会直接产生事实错误（130 vs 134），该建议不再是可选优化。

**收益**: 后续走框架路径 C（`@commit` 增量更新）时可快速重跑比对，降低漂移检测成本。

**成本**: 第 1 批增加约 0.5 小时。

**优先级**: 💡 P1（原 P2，第 2 轮复查后上调）

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
- **发现**: `codex-rs/app-server-protocol/schema/typescript/v2/` 下有 550 个自动生成的 TS 类型文件；AGENTS.md「### Core Rules」 要求 v2 类型必须标注 `#[ts(export_to = "v2/")]`；AGENTS.md「### Development Workflow」 规定 API 形状变更后需跑 `just write-app-server-schema` 并用 `just test -p codex-app-server-protocol` 验证
- **评价**: Rust 类型是唯一事实源，TS 类型为构建产物。文档中不得把生成的 TS 文件描述为"手写代码"。

### 观察 3: 三平台原生沙箱 + 独立执行服务

- **证据等级**: E3（沙箱实现）+ E2（跨 OS 分离）
- **发现**: `codex-rs/sandboxing/src/` 同时含 `seatbelt.rs` / `landlock.rs` / `bwrap.rs` / `windows.rs` 与 3 个 `.sbpl` 策略文件；另有独立 crate `linux-sandbox`、`windows-sandbox-rs`、`bwrap`、`execpolicy`、`shell-escalation`；AGENTS.md「## Platform Support」 声明 app-server 与 exec-server 可运行在不同操作系统
- **评价**: 沙箱是本项目的核心差异化能力，且与 AGENTS.md 顶部规则列表（CODEX_SANDBOX 红线条目） 的 `CODEX_SANDBOX_*` 红线直接相关，必须单独成文。

### 观察 4: 双构建系统带来的双锁同步义务

- **证据等级**: E2
- **发现**: `MODULE.bazel`（16,677 字节）+ `MODULE.bazel.lock`（1,547,127 字节）与 `codex-rs/Cargo.lock` 并存；AGENTS.md 顶部规则列表（Bazel 锁条目） 要求依赖变更后跑 `just bazel-lock-update` 并同 PR 提交，CI 校验漂移；AGENTS.md 顶部规则列表（compile_data 条目） 提醒 `include_str!` / `sqlx::migrate!` 等编译期文件读取需在 `BUILD.bazel` 补 `compile_data`
- **评价**: 高频踩坑点，`build_and_release.md` 必须给出明确流程。

### 观察 5: 四条并行的扩展路径

- **证据等级**: E1（目录存在性），关系待验证
- **发现**: `codex-rs/ext/`（12 个内建扩展 crate）、`codex-rs/core-plugins/`（37,038 行插件运行时）、`codex-rs/skills/`（含 plugin-creator / skill-creator / skill-installer 样例）、MCP 客户端与服务端（`codex-mcp` / `mcp-server` / `rmcp-client` / `ext/mcp`）
- **评价**: 四条路径并存但**相互关系尚未验证**。这是当前证据等级最薄弱的架构点，已列为第 3 批强制代码级核查项，正式文档中不得凭目录名推断其关系。

### 观察 6: 仓库内文档极薄，外部站点承载产品文档

- **证据等级**: E4
- **发现**: `docs/config.md` 仅 15 行、`codex-rs/config.md` 仅 6 行、`docs/sandbox.md` 仅 3 行且正文为指向 developers.openai.com 的外链；`codex-rs/README.md` 仅 3 行
- **评价**: 这正是本文档体系的价值空间 —— 仓库缺少**面向开发者的架构与规范落地层**。同时也解释了 AGENTS.md 顶部规则列表（docs/ 条目） 的用意：产品文档在别处维护，`docs/` 不该被塞入通用文档。

---

## 📊 风险假设与证据等级

| 风险假设 | 证据等级 | 当前证据 | 验证状态 | 下一步验证动作 | 是否可定优先级 |
| -------- | -------- | -------- | -------- | -------------- | -------------- |
| 文档产物若落入 `docs/` 将违反仓库规范 | E2 | AGENTS.md 顶部规则列表（docs/ 条目） | 已确认 | 无需进一步验证（方案已规避） | P1（已落实） |
| 高触碰大文件会持续吸引无关改动 | E2 + E4 | AGENTS.md 顶部规则列表（high-touch files 条目） 点名清单 + `wc -l` 实测 12,616 行 | 已确认 | 无需进一步验证 | 否（受维护者规则约束，仅记录） |
| Python SDK 章节无法取得 E4 证据 | E2 + E4 | `pyproject.toml:10` `>=3.10` + 本机 `Python 3.9.6` | 已确认 | 用户升级 Python 后可补跑 pytest | 否 |
| 四层扩展机制的关系可能被误述 | E1 | 仅目录存在性 | 待验证 | 第 3 批读取 `codex-rs/ext/extension-api/src/lib.rs`、`codex-rs/core-plugins/src/manager.rs`、`skills/src/lib.rs` 公开 API | P1 |
| release 构建下遥测默认开启 | E3（部分） | `otel/src/config.rs:16,90,113` grep 命中 | 待验证 | 第 4 批完整读取 `otel/src/{config,provider,otlp}.rs` 与 `codex-rs/analytics/src/client.rs` 投递链路 | P1 |
| app-server ↔ exec-server 跨 OS 分离的传输实现 | E2 | AGENTS.md「## Platform Support」 + crate 存在性 | 待验证 | 第 2 批读取 `exec-server-protocol/src/`、`app-server-transport/src/`、`uds/src/` | P1 |
| `find_codex_home` 存在两处同名实现可能造成描述冲突 | E3 | `codex-rs/core/src/config/mod.rs:4578` 与 `codex-rs/utils/home-dir/src/lib.rs:13` 均定义 `pub fn find_codex_home` | 待验证 | 第 2 批读取两处实现，确认调用关系（委托 or 重复） | P1 |
| 上游高速迭代导致文档快速过期 | E4 | `git log -1` 基线 commit 与分析同日；近 5 次提交均为当日/近日 PR | 已确认 | 建立路径 C 增量更新节奏 | P1 |
| 文档覆盖度不足导致 AI 误判 | E4 | 1,270,789 行 Rust vs 17 篇文档 | 已确认 | 主文档「未覆盖范围」显式清单 | P1（已落实缓解） |

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
- [ ] 警告 6: 产物已进入公开 fork，脱敏为硬性红线 — 首次脱敏已执行，后续每批复扫
- [ ] 警告 7: 自验收流程不足以发现事实错误 — 首版验收结论已改判为 FAIL，事实类验收改由独立代理执行

**疑问确认（需用户回答）**:

- [x] 疑问 1: 文档服务对象与深度定位 —— 用户回答：**兼顾**（阅读理解 upstream + 二次开发），方案维持原样
- [x] 疑问 2: `dev_docs/` 是否纳入版本管理 —— **已解决**：提交全部内容并推送个人 fork `zibuyu2015831/codex`，不向上游推送
- [x] 疑问 3: 实验性表面的文档优先级 —— 用户回答：**全部展开**，第 4 批新增 `experimental_surfaces.md`

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
- [x] 提交并推送至个人 fork（commit `8224f7c034` → `fork/zibuyu`）
- [x] 执行第 2 轮方案复查（更正 crate 计数、回写版本管理结论、新增脱敏红线）
- [ ] 用户答复剩余 2 项待确认事项并批准方案

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

1. **用户审核本报告** — ✅ 已完成，3 项疑问全部结案
2. **用户批准 `generation_plan.md`** — 已确认 17 篇子文档清单与 4 批执行计划 ✅
3. **进入第 1 批正式生成**

### 文档生成建议

**本报告未发现阻断文档生成的问题，建议在用户确认剩余 2 项疑问后即可进入正式生成。**

理由：

- 无 🔴 严重问题
- 6 项警告均已有缓解措施，且全部 `blocks_phase1 = false`
- 剩余 2 项疑问均有可执行的保守结论，不阻塞第 1 批的 4 篇文档

**建议流程**:

```
1. 生成 _analysis 三件套                    ✅ 已完成
2. 执行 Phase 1 自检门（5 项 checker）       ✅ 已完成
3. 提交并推送至个人 fork                    ✅ 已完成
4. 第 2 轮方案复查（用户要求）               ✅ 已完成
5. 用户审核并回答剩余 2 项疑问               ⏸️ 当前位置
6. 用户批准方案
7. 第 1 批正式生成 → 用户审查颗粒度
8. 第 2-4 批 → 首版质量验收
```

---

## 📅 报告元信息

- **生成者**: AI Assistant（AICC 框架路径 A / Step 6）
- **生成日期**: 2026-08-03
- **最近复查**: 2026-08-03，第二轮独立审查（7 个独立代理回源码复核全部可核验断言，首版验收结论改判为 FAIL）
- **上一次复查**: 2026-08-03，第 2 轮方案复查（回到 Step 7.4 自检门，未生成任何正式文档）
- **分析时长**: 约 2 小时（首轮）+ 第 2 轮复查
- **分析基线**: commit `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
- **产物提交**: commit `8224f7c034`，推送至 `fork/zibuyu`（`zibuyu2015831/codex`）
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
