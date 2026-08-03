---
title: Codex 仓库 AI 规则索引
summary: 作为 AI 代理在本仓库工作的规则入口，明确以仓库自带 AGENTS.md 为唯一强制事实源、本文件只做索引与定位；规则索引改用章节标题加可 grep 关键词而非易漂移的行号，并给出 dev_docs 文档体系特有的落盘路径、推送目标、证据等级硬规则与脱敏约定。
keywords: codex | ai-rules | agents-md | index | dev-docs | constraints | evidence-level
scope: AI 代理在 openai/codex 仓库及本文档体系中的行为约束索引
related_files: AGENTS.md | docs/contributing.md | codex-rs/tui/styles.md | codex-rs/clippy.toml | codex-rs/app-server-protocol/Cargo.toml | codex-rs/app-server-protocol/scripts/write_schema_fixtures.py | .codex/skills/pushing-ci-changes/SKILL.md | justfile
dependencies: dev_docs/AI_Coding_Context.md | dev_docs/development_workflow.md
verified_at: 2026-08-03
---

# AI 规则索引

> [!CAUTION]
> **本文件不是规范，是索引。**
>
> 仓库自带的 AGENTS.md（22,519 字节）是**唯一的强制规范事实源**，优先级高于本文档体系的任何内容。本文件**不覆盖、不改写、不复制**其任何条款。
>
> 本文件存在的唯一理由是：帮你**快速定位**该去读哪一条，以及补充 `dev_docs` 体系自身的约定。

---

## 1. 事实源优先级

```
1. AGENTS.md                      ← 强制规范，最高优先级
2. docs/contributing.md           ← 贡献准入规则
3. codex-rs/tui/styles.md         ← TUI 样式（由 AGENTS.md「TUI style conventions」节指定）
4. codex-rs/clippy.toml           ← 机器强制的 lint 规则
5. justfile                       ← 命令的事实源
6. dev_docs/（本体系）             ← 落地说明与实测补充，最低优先级
```

**冲突时一律以上层为准**，并请修正 `dev_docs` 中的对应内容。

---

## 2. 开工前必读三条

| # | 事项 | 出处 |
| ---: | ---- | ---- |
| 1 | 外部代码贡献**受邀制**，未受邀 PR 直接关闭 | `docs/contributing.md:3-17` |
| 2 | 禁止触碰 `CODEX_SANDBOX_*` 相关代码 | AGENTS.md 顶部规则列表，grep `CODEX_SANDBOX_ENV_VAR` |
| 3 | 禁止向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | AGENTS.md 顶部规则列表，grep `general product or user-facing documentation` |

---

## 3. 规则定位索引

> [!IMPORTANT]
> **本表不再给行号。**
>
> 上一版按 `AGENTS.md:NN` 索引，第二轮独立审查发现其中多条已经漂移——有的指向空行，有的指向相邻的另一条规则（配置 schema、MCP、平台支持、测试与 lint 区段、async trait 区段、breaking changes 区段、Python 版本区段均已偏移）。行号随上游每次编辑失效，且失效时**无任何报错**，读者只会静默读到错的规则。
>
> 因此改为「**章节标题 + 可 grep 的关键词**」。章节标题是稳定锚点；关键词可直接 `grep -n "<关键词>" AGENTS.md` 定位到条款本身。行号漂移不会再导致误读。
>
> 表中「顶部规则列表」指 AGENTS.md 开头 `# Rust/codex-rs` 之下、第一个 `##` 标题之前的那段无标题条目列表。

| 我要…… | AGENTS.md 章节 | 可 grep 的关键词 |
| ---- | ---- | ---- |
| 写异步 trait 方法 | 顶部规则列表 | `async_fn_in_trait` |
| 写单元测试 | 顶部规则列表 | `comparing the equality of entire objects` |
| 写测试（评审口径） | `### Test authoring guidance` | `MUST add an integration test` |
| 写测试断言 | `### Test assertions` | `pretty_assertions::assert_eq` |
| 组织测试模块 | `### Test module organization` | `#[path = "parser_tests.rs"]` |
| **改了可见 UI → 补快照** | `### Snapshot tests` | `must include` / `cargo insta pending-snapshots` |
| 在测试里拉起本仓二进制 | `### Spawning workspace binaries in tests (Cargo vs Bazel)` | `codex_utils_cargo_bin::cargo_bin` |
| 写集成测试 | `### Integration tests` / `#### codex_core integration testing` / `#### app-server integration testing` | `core_test_support::responses`、`TestAppServer::builder` |
| 写 benchmark | `### Benchmarks` | `just bench-smoke` |
| 加文档 | 顶部规则列表 | `general product or user-facing documentation` |
| 设计模块可见性 | 顶部规则列表 | `Prefer private modules` |
| 控制 crate 对外 API | `### Crate API surface` | `Keep crate API surfaces as small as possible` |
| 改配置类型 | 顶部规则列表 | `just write-config-schema` |
| 改 MCP 工具调用 | 顶部规则列表 | `mcp_connection_manager.rs` |
| 改 Cargo 依赖 | 顶部规则列表 | `just bazel-lock-update` |
| 用 `include_str!` / `sqlx::migrate!` | 顶部规则列表 | `compile_data` |
| 写辅助方法 | 顶部规则列表 | `referenced only once` |
| 加追踪 | 顶部规则列表 | `#[tracing::instrument` |
| 拆分/新增模块 | 顶部规则列表 | `Avoid large modules`、`high-touch files` |
| 改 `chatwidget.rs` | 顶部规则列表 | `keep chatwidget.rs focused on orchestration` |
| 跑测试与 lint | 顶部规则列表 | `just fmt`、`just test -p`、`just fix -p <project>` |
| 往 `codex-core` 加东西 | `## The codex-core crate` | `resist adding code to codex-core` |
| 往模型上下文里塞内容 | `### Model visible context` | `ContextualUserFragment`、`No unbounded items` |
| 改外部集成面（破坏性变更） | `### Breaking changes` | `rawResponseItem/*` |
| 估算变更规模 | `### Change size guidance (800 lines)` | `should not exceed 800 lines` |
| 写 TUI 样式 | `## TUI style conventions` → `codex-rs/tui/styles.md` | `See ` + `styles.md` |
| 写 TUI 代码 | `## TUI code conventions` / `### TUI Styling (ratatui)` | `Stylize`、`Avoid hardcoded white` |
| 在 TUI 里做文本换行 | `### Text wrapping` | `word_wrap_lines`、`prefix_lines` |
| 改 app-server 协议（整体） | `## App-server API Development Best Practices` 及其 `### Core Rules` / `### Client->server request payloads (*Params)` / `### Development Workflow` | `app-server v2`、`ts(export_to = "v2/")`、`ts(optional = nullable)` |
| 考虑平台支持 | `## Platform Support` | `Linux, macOS and Windows` |
| 判断 Python 版本要求 | `## Python Development Best Practices` / `### Ignore Python 2 compatibility` | `requires-python` |

---

## 4. 文档体系导航

| 我想…… | 去看 |
| ---- | ---- |
| 总入口与场景导航 | [`AI_Coding_Context.md`](../../AI_Coding_Context.md) |
| 理解整体架构 | [`architecture_overview.md`](../../architecture_overview.md) |
| 找 crate / 决定新代码放哪 | [`crate_map.md`](../../crate_map.md) |
| 开发流程与命令 | [`development_workflow.md`](../../development_workflow.md) |
| 智能体核心循环 | [`core_agent_loop.md`](../../core_agent_loop.md) |
| 工具执行与沙箱 | [`tools_and_sandbox.md`](../../tools_and_sandbox.md) |
| app-server 协议 | [`app_server_protocol.md`](../../app_server_protocol.md) |
| 配置体系 | [`config_system.md`](../../config_system.md) |
| TUI 开发 | [`tui_guide.md`](../../tui_guide.md) |
| 测试 | [`testing_guide.md`](../../testing_guide.md) |
| 扩展 / 插件 / Skills / MCP | [`mcp_and_extensions.md`](../../mcp_and_extensions.md) |
| 认证与模型接入 | [`auth_and_providers.md`](../../auth_and_providers.md) |
| 构建与发布 | [`build_and_release.md`](../../build_and_release.md) |
| 会话与持久化 | [`session_and_persistence.md`](../../session_and_persistence.md) |
| 实验性能力面 | [`experimental_surfaces.md`](../../experimental_surfaces.md) |
| 遥测与数据边界 | [`observability.md`](../../observability.md) |
| SDK | [`sdk_guide.md`](../../sdk_guide.md) |

---

## 5. dev_docs 体系特有约定

以下不属于上游规范，是本文档体系自身的规则。

### 5.1 落盘与版本控制

| 约定 | 说明 |
| ---- | ---- |
| **产物路径固定 `dev_docs/`** | 禁止迁入 `docs/`（AGENTS.md 顶部规则列表，grep `general product or user-facing documentation`） |
| **推送只推个人 fork** | 禁止 `git push origin`（`origin` 直连上游 `openai/codex`） |
| 框架软链接不入库 | `AI-Coding-Context` 已写入 `.git/info/exclude` |
| 不修改仓库根的 gitignore 文件 | 用本地 exclude 代替 |

### 5.2 脱敏（fork 为公开仓库，硬性门禁）

每批提交前必须跑，任一有输出即为 blocker：

```bash
# 1) 本地绝对路径（期望无输出）
grep -rnE "/Users/[A-Za-z0-9._-]+/" dev_docs/

# 2) 凭证样值（期望无输出）
grep -rniE "(api[_-]?key|token|secret|password|passwd|credential)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][A-Za-z0-9_-]{12,}" dev_docs/
```

| 禁止写入 | 允许写入 |
| ---- | ---- |
| 真实 API key、token、私钥的**值** | 变量名、配置键名、常量名、文件路径 |
| 本地绝对路径、主机名、内网地址、个人邮箱 | 公开服务端点（技术事实） |
| 测试夹具中的假 token | 夹具文件路径与字段名 |

### 5.3 证据等级（写文档时必须标注）

| 等级 | 来源 | 允许的措辞 |
| ---- | ---- | ---- |
| E1 | 目录结构、文件名、**文件数量与行数清点** | 只能写"疑似""待验证" |
| E2 | 配置、锁文件、README | 可写"已从配置确认" |
| E3 | 源码片段、调用链 | 可写"代码显示" |
| E4 | 实跑构建/测试/lint 工具并取其结论 | 可写"已验证" |

> 注意：`git ls-files | wc -l`、`wc -l` 这类**清点**属于 E1，不是 E4。E4 指的是真的把构建、测试或 lint 跑起来并采信其结果。

> [!WARNING]
> **最常见的错误是把 E1/E2 的名字推断写成 E3 的事实。** 本体系已有两个实打实的翻车案例，都是「看到了名字就下了结论」：
>
> | 案例 | 当时的推断 | 推断依据 | 实际 |
> | ---- | ---- | ---- | ---- |
> | ext 依赖 | 「12 个 `ext/*` **全部**依赖 `extension-api`」 | `grep -rl` 出来的**文件名列表** | **8/12**。3 个不依赖，第 4 个是 `extension-api` 自身被误计入 |
> | Linux 沙箱 | 「Linux 沙箱用 Landlock」 | `Cargo.toml` 里的**依赖名** + 一个叫 `landlock.rs` 的**文件名** | 该机制已废弃，默认路径是 bwrap；Landlock 只作 legacy 回退 |
>
> 由此定两条硬规则：
>
> 1. **依赖类断言**：必须区分 `[dependencies]` 与 `[dev-dependencies]`（以及 `target.*` 段），并以 `cargo metadata` 为准，**不得用 `grep` 数文件名**。写结论时注明取自哪个 section。
> 2. **机制类断言**：要说某机制「正在生效」，必须找到它的**构造点与调用方**，只找到类型定义、常量或同名文件不够。类型存在 ≠ 类型被构造 ≠ 该路径是默认路径。
>
> 另一先例：四条扩展路径的关系曾被标为 E1 留白，直到第 3 批读了 `Cargo.toml` 才得出结论——**结果与最初的直觉推断并不一致**（见 `mcp_and_extensions.md` §1）。

### 5.4 其他

| 约定 | 说明 |
| ---- | ---- |
| `related_files` 只列**实际读过**的文件 | 不列未读文件 |
| 每篇文档记录基线 commit 与 `verified_at` | 便于漂移检测 |
| 数值类事实必须给可复现命令 | 不抄历史数字 |
| 未覆盖范围要显式列清单 | 不写空泛免责声明 |

---

## 6. 质量门禁

本体系的产物由 5 项框架 checker + 1 项本体系自建 checker 校验：

```bash
P=AI-Coding-Context/tools
python3 $P/py/summary_validator.py --dir dev_docs --recursive --strict
python3 $P/py/doc_health_checker.py --full-check --doc-dir dev_docs
node    $P/js/doc_health_checker.js --full-check --doc-dir dev_docs
python3 $P/py/semantic_review_checker.py --full-check --doc-dir dev_docs --repo-root .
node    $P/js/semantic_review_checker.js --full-check --doc-dir dev_docs --repo-root .

# 本体系自建，补 5 项框架 checker 的盲区
python3 dev_docs/_analysis/cross_doc_consistency_checker.py --verify-repo
```

全部要求 `exit_code = 0`。Python 与 JS 两套实现结果不一致时，**必须先修正或记录为 blocker**，不得豁免。

> [!CAUTION]
> **5 项全绿是必要条件，不是充分条件。** 这 5 个 checker 校验的是结构、frontmatter、模板残留、run record、锚点极性；它们**不做**下面两件事：
>
> - **跨文档数值对账**——同一个事实在 A 文档写 20、B 文档写 27，5 项照样全绿；
> - **同一文档内「标题声明的计数」与「表格实际行数」是否相符**——标题写「20 个 crate」而下面的表列了 23 行，5 项照样全绿。
>
> 实证：第二轮独立审查查出的 4 项 HIGH 级不一致，**全部是在 5 项 checker 通体绿灯的状态下漏过去的**（见 `_analysis/health_check_report.md` 的「跨文档矛盾」小节）。

> [!TIP]
> 上述两个盲区已由 `dev_docs/_analysis/cross_doc_consistency_checker.py` 补上，它还多做一件事：
>
> - **对账仓库真值**（`--verify-repo`）——每项已登记事实带一条可复现命令，用命令输出校验文档数字。跨文档一致性检查只能发现「两处写得不一样」，**发现不了「各处都抄成同一个错值」**，这一项才能。
> - **跨文档 `§N` 引用漂移**——章节号会因插入新章节而整体顺延，旧引用仍指向一个「存在但内容已换」的章节。判据是引用后跟的标题文字若明确匹配到了另一个章节号，即判漂移（匹配不上则视为作者的描述性文字，不报；匹配到被引章节的子节视为合法精度差异，不报）。

**仍然没有被任何 checker 覆盖的**：断言与源码是否相符。这只能靠独立复核——本轮 15 个 HIGH 里有 11 个属于此类。

---

## 7. 提交前自检

```
□ just fmt                                   已跑
□ just test -p <crate>                       通过
□ 改了 common/core/protocol → just test       通过（先问用户）
□ 大改动 → just fix -p <crate>                已跑
□ 改了 Cargo 依赖 → just bazel-lock-update    已跑
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → 重生成 schema 夹具（见下方注记）已跑
□ 改了用户可见 UI（含新增 UI）→ insta 快照覆盖已补/已更新
□ 新增 include_str! → BUILD.bazel compile_data 已补
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500）
□ 未触碰 CODEX_SANDBOX_*
□ 未向 docs/ 添加通用文档
□ 改了 .github/**/*.yml → 已确认拿到临时的工作流推送批准
□ 改了 dev_docs → 5 项框架 checker + 跨文档对账 + 2 项脱敏扫描全绿
□ push 目标是 fork，不是 origin
```

### 三条容易踩空的说明

1. **`just write-app-server-schema` 当前是坏的。** 该 recipe 执行 `cargo run -p codex-app-server-protocol --bin write_schema_fixtures`，但 `codex-app-server-protocol` **没有任何 bin target**（`src/bin/` 不存在），命令必然失败。可用的入口是 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`。这是上游 `justfile` 与 AGENTS.md 自身的陈旧记载，照抄之前请先验证可执行性。
2. **UI 改动必须配快照。** AGENTS.md 的 `### Snapshot tests` 一节写的是 Requirement：任何影响用户可见 UI 的改动（含新增 UI）都必须附带对应的 `insta` 快照覆盖。这条最常被漏。命令链见 `tui_guide.md` §4。
3. **动 CI 配置的推送会被拒。** 本仓库禁止在未获临时角色的情况下推送 `.github/**/*.yml` 及相关文件；被拒后需由用户走审批流程拿到临时批准，代理自身无法申请豁免。详见 `.codex/skills/pushing-ci-changes/SKILL.md`。
