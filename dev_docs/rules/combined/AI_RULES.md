---
title: Codex 仓库 AI 规则索引
summary: 作为 AI 代理在本仓库工作的规则入口，明确以仓库自带 AGENTS.md 为唯一强制事实源、本文件只做索引与定位；规则索引全部改用章节标题加逐条实测过的可 grep 关键词而非易漂移的行号，登记 AGENTS.md 自身已知的三处陈旧记载（mcp_connection_manager.rs 路径不存在、--all-features 建议与 features 禁令矛盾、write-app-server-schema 循环失效），并给出 dev_docs 文档体系特有的落盘路径、推送目标、证据等级硬规则、取证方式禁忌与脱敏约定。
keywords: codex | ai-rules | agents-md | index | dev-docs | constraints | evidence-level | stale-upstream-docs
scope: AI 代理在 openai/codex 仓库及本文档体系中的行为约束索引
related_files: AGENTS.md | docs/contributing.md | codex-rs/tui/styles.md | codex-rs/clippy.toml | codex-rs/app-server-protocol/Cargo.toml | codex-rs/app-server-protocol/scripts/write_schema_fixtures.py | AGENTS.md | justfile | .github/scripts/verify_cargo_workspace_manifests.py | .github/scripts/verify_tui_core_boundary.py | .github/scripts/verify_bazel_clippy_lints.py | codex-rs/codex-mcp/src/connection_manager.rs
dependencies: dev_docs/AI_Coding_Context.md | dev_docs/development_workflow.md
verified_at: 2026-08-05
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

| # | 事项 | 出处（章节标题 + 可 grep 的关键词，**不给行号**） |
| ---: | ---- | ---- |
| 1 | 外部代码贡献**受邀制**，未受邀 PR 直接关闭 | `docs/contributing.md` 的 `## Contributing` 一节，grep `External contributions are by invitation only` 与 `will be closed without review` |
| 2 | 禁止触碰 `CODEX_SANDBOX_*` 相关代码 | AGENTS.md 顶部规则列表，grep `CODEX_SANDBOX_ENV_VAR` 或 `Never add or modify any code related to` |
| 3 | 禁止向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | AGENTS.md 顶部规则列表，grep `general product or user-facing documentation` |

> [!CAUTION]
> **第 0 条（本文件新增）：AGENTS.md 自身也会陈旧，照抄之前先验证。**
>
> 它仍是**唯一强制规范**——本条不是让你忽略它，而是提醒你**规则的意图**与**规则里写的路径/命令**可能已经脱节。已确认的三处见下方 **§3.5**。判据永远是：**引用命令前先跑一遍，引用路径前先 `ls` 一下。**

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
>
> **本表的每一条关键词都在 2026-08-05 逐条实测过 `grep -n`，全部命中。** 复核脚本形状：
>
> ```bash
> while IFS= read -r k; do grep -qF -- "$k" AGENTS.md || echo "MISS: $k"; done < <(关键词列表)
> ```
>
> ⚠️ **关键词必须落在 AGENTS.md 的同一行内。** AGENTS.md 是硬折行的（约 100 列），跨行短语用 `grep` 找不到。本轮就修掉一条这样的：上一版用的那条 chatwidget 长短语 **零命中**——原文既带反引号，又在 `unless the change is` / `trivial;` 之间折了行 <!-- ref-exempt: 本句在说明该长短语作为 grep 关键词不可用，不是文件引用 -->。可用的关键词是 `focused on orchestration`。

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
| 改 MCP 工具调用 | 顶部规则列表 | `mcp_connection_manager` ⚠️ **该路径在上游规则中已陈旧**，实际文件是 `codex-rs/codex-mcp/src/connection_manager.rs`（另有 `connection_manager/` 目录与 `codex-rs/codex-mcp/src/connection_manager_tests.rs`）。关键词仍用陈旧串才能命中原文，见 §3.5 <!-- ref-exempt: 左侧为 AGENTS.md 原文关键词，其不可解析正是本行要指出的问题 --> |
| 改 Cargo 依赖 | 顶部规则列表 | `just bazel-lock-update` |
| 用 `include_str!` / `sqlx::migrate!` | 顶部规则列表 | `compile_data` |
| 写辅助方法 | 顶部规则列表 | `referenced only once` |
| 加追踪 | 顶部规则列表 | `#[tracing::instrument` |
| 拆分/新增模块 | 顶部规则列表 | `Avoid large modules`、`high-touch files` |
| 改 `codex-rs/tui/src/chatwidget.rs` | 顶部规则列表 | `focused on orchestration`（**不要用 `keep chatwidget.rs focused on orchestration`——原文带反引号且折了行，零命中**） |
| 跑测试与 lint | 顶部规则列表 | `just fmt`、`just test -p`、`just fix -p <project>` |
| 往 `codex-core` 加东西 | `## The codex-core crate` | `resist adding code to codex-core` |
| 往模型上下文里塞内容 | `### Model visible context` | `ContextualUserFragment`、`No unbounded items` |
| 改外部集成面（破坏性变更） | `### Breaking changes` | `rawResponseItem/*` |
| 估算变更规模 | `### Change size guidance (800 lines)` | `should not exceed 800 lines` |
| 写 TUI 样式 | `## TUI style conventions` → `codex-rs/tui/styles.md` | `See ` + `codex-rs/tui/styles.md` |
| 写 TUI 代码 | `## TUI code conventions` / `### TUI Styling (ratatui)` | `Stylize`、`Avoid hardcoded white` |
| 在 TUI 里做文本换行 | `### Text wrapping` | `word_wrap_lines`、`prefix_lines` |
| 改 app-server 协议（整体） | `## App-server API Development Best Practices` 及其 `### Core Rules` / `### Client->server request payloads (*Params)` / `### Development Workflow` | `app-server v2`、`ts(export_to = "v2/")`、`ts(optional = nullable)` |
| 判断改动是否属高风险面 | `## Code Review Rules` → `### Breaking changes` | `rawResponseItem/*`、`even while experimental`（该清单点名：app-server API、`rawResponseItem/*`、CLI 参数、**配置加载**、从既有 rollout 恢复会话） |
| 加 `include_str!` / `.sbpl` 等编译期读文件 | 顶部规则列表 | `Bazel does not automatically make source-tree files available`、`compile_data` |
| 判断 app-server 与 exec-server 能否跨 OS | `## Platform Support` | `connected app-server and exec-server on different operating systems` |
| 考虑平台支持 | `## Platform Support` | `Linux, macOS and Windows` |
| 判断 Python 版本要求 | `## Python Development Best Practices` / `### Ignore Python 2 compatibility` | `requires-python` |

### 3.5 AGENTS.md 自身的已知陈旧点（必读）

> [!CAUTION]
> **规则的意图有效，规则里写的路径与命令未必有效。** 以下三处已在 2026-08-05 实测确认与当前代码/构建不符。**它们不构成豁免**——按意图执行，但别照抄字面。

| # | 陈旧点 | 上游怎么写的 | 实际情况 |
| ---: | ---- | ---- | ---- |
| S1 | MCP 连接管理器路径 | 顶部规则列表 grep `mcp_connection_manager` 处写作 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` <!-- ref-exempt: 本行正在声明该路径不存在，引用不可解析恰是要表达的事实 --> | **该文件不存在。** 真实文件是 `codex-rs/codex-mcp/src/connection_manager.rs`，另有同名子模块目录与 `codex-rs/codex-mcp/src/connection_manager_tests.rs`。大概是重命名后规则文本没跟着改 |
| S2 | `--all-features` 建议 | 顶部规则列表，grep `--all-features`：*"Avoid `--all-features` for routine local runs… use it only when you specifically need full feature coverage"*，把它说成「偶尔要用」 | **workspace crate features 已被制度性禁止**——`.github/scripts/verify_cargo_workspace_manifests.py` 直接拒绝任何 `[features]`（白名单只有 `codex-rs/code-mode/Cargo.toml` 与 `codex-rs/v8-poc/Cargo.toml` 的 `sandbox`），也拒绝 `optional = true`。`justfile:78-79` 的注释写着 *"Workspace crate features are banned, so there should be no need to add `--all-features`."* **这条建议已无适用场景** |
| S3 | app-server schema 再生成命令 | `AGENTS.md` 的 `## App-server API Development Best Practices` → `### Development Workflow`（grep `write-app-server-schema`）、`justfile` 的 `write-app-server-schema` recipe，**以及那条校验测试自己的 `panic!` 文案**（`codex-rs/app-server-protocol/src/schema_fixtures_tests.rs`，grep `Run \`just write-app-server-schema\` to overwrite`，两处）都推荐 `just write-app-server-schema` | **该 recipe 必然失败**：它调 `cargo run -p codex-app-server-protocol --bin write_schema_fixtures`，而 `codex-app-server-protocol` **没有任何 bin target**（根因是 `ts-rs` / `schemars` 只在 `[dev-dependencies]` 里，生产构建下 derive 宏被换成空实现，所以生成器只能以 `cfg(test)` 编译）。**这是一处循环陈旧——测试挂了以后照它说的做只会再挂一次。** 可用入口：`python3 codex-rs/app-server-protocol/scripts/write_schema_fixtures.py` |

---

## 4. 文档体系导航

| 我想…… | 去看 |
| ---- | ---- |
| 总入口与场景导航 | [`AI_Coding_Context.md`](../../AI_Coding_Context.md) |
| **看「取证方式本身的禁忌」（T1–T6）** | [`AI_Coding_Context.md`](../../AI_Coding_Context.md) 的「AI 编码禁忌」一节 |
| 理解整体架构 | [`architecture_overview.md`](../../architecture_overview.md) |
| 找 crate / 决定新代码放哪 | [`crate_map.md`](../../crate_map.md) |
| 开发流程与命令 | [`development_workflow.md`](../../development_workflow.md) |
| 智能体核心循环 | [`core_agent_loop.md`](../../core_agent_loop.md) |
| 工具执行与沙箱 | [`tools_and_sandbox.md`](../../tools_and_sandbox.md) |
| app-server 协议 | [`app_server_protocol.md`](../../app_server_protocol.md) |
| 配置体系 | [`config_system.md`](../../config_system.md) |
| TUI 开发（含 CI 强制的 core 边界） | [`tui_guide.md`](../../tui_guide.md) |
| 测试 | [`testing_guide.md`](../../testing_guide.md) |
| 扩展 / 插件 / Skills / MCP / hooks | [`mcp_and_extensions.md`](../../mcp_and_extensions.md) |
| 认证与模型接入 | [`auth_and_providers.md`](../../auth_and_providers.md) |
| 构建与发布（含 Nix / devcontainer） | [`build_and_release.md`](../../build_and_release.md) |
| 会话与持久化 | [`session_and_persistence.md`](../../session_and_persistence.md) |
| 实验性能力面（含 `codex-features` 门控） | [`experimental_surfaces.md`](../../experimental_surfaces.md) |
| 遥测与数据边界 | [`observability.md`](../../observability.md) |
| SDK | [`sdk_guide.md`](../../sdk_guide.md) |

---

## 5. dev_docs 体系特有约定

以下不属于上游规范，是本文档体系自身的规则。

### 5.1 落盘与版本控制

| 约定 | 说明 |
| ---- | ---- |
| **产物路径固定 `dev_docs/`** | 禁止迁入 `docs/`（AGENTS.md 顶部规则列表，grep `general product or user-facing documentation`） |
| **推送只推个人 fork** | **2026-08-05 已按规则意图重整 remote，当前状态如下（实测 `git remote -v`）：**<br>· `origin` → 个人 fork（fetch/push 均可）<br>· `upstream` → `openai/codex`，**push URL 已置为 `DISABLED_DO_NOT_PUSH_TO_UPSTREAM`**，误推立即 `fatal` 失败<br>· 已设 `remote.pushDefault = origin`，**任何裸 `git push` 一律走 fork**，不受分支跟踪影响<br>⚠️ 注意 `main` 分支跟踪的是 `upstream/main`（便于同步），**它的推送安全完全依赖上面那条被禁用的 push URL**，不要恢复它。<br>规则意图不变——**绝不向上游推送**。口径与 [`development_workflow.md`](../../development_workflow.md) §8 一致<br>📌 **历史**：本条曾两次记载失准——先写「`origin` 直连上游」，后改成「`origin` 已指向 fork 且未配置上游 remote」，而 2026-08-05 实测时 `origin` 确实直连上游、个人 fork 挂在名为 `fork` 的 remote 上。**引用本条前先跑一次 `git remote -v`。** |
| 框架软链接不入库 | ⚠️ **上一版写的「`AI-Coding-Context` 已写入 `.git/info/exclude`」不成立。** 实测：该软链接**当前不存在**，`.git/info/exclude` 仍是默认内容（全为注释，无自定义条目）。规则改为**条件式**：**若**在本地创建了指向框架仓库的软链接 `AI-Coding-Context`，**则**必须自行把它加入 `.git/info/exclude` |
| 不修改仓库根的 gitignore 文件 | 用本地 exclude 代替 |

### 5.2 脱敏（fork 为公开仓库，硬性门禁）

每批提交前必须跑，任一有输出即为 blocker。**首选统一入口**（覆盖下面两条以及 JWT 形状串、私钥块、SSH 组织身份串、内网 IP、个人邮箱共 7 项）：

```bash
bash dev_docs/_analysis/redact_scan.sh
```

手工兜底（与上面脚本前两项等价）：

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
> | ext 依赖 | 「12 个 `ext/*` **全部**依赖 `extension-api`」 | **未取证的归纳**：把「`ext/` 下共有 12 个 crate」直接当成了「12 个都依赖它」 | **8/12**。⚠️ **连这条勘误的错因也曾被写错**——早先说错因是「`grep -rl` 把 `extension-api` 自己数进去了」，但那样只会得到 **9**；`agent`/`connectors`/`items` 三份清单里该串出现 **0** 次，grep 口径解释不了差额 |
> | Linux 沙箱 | 「Linux 沙箱用 Landlock」 | `Cargo.toml` 里的**依赖名** + 一个叫 `landlock.rs` 的**文件名** | 该机制已废弃（`Stage::Deprecated`），默认路径是 bwrap；默认分支注释明写 "never falls back to legacy Landlock on failure" | <!-- ref-exempt: 复述致错线索，泛指依赖名与文件名本身 -->
>
> 由此定两条硬规则：
>
> 1. **依赖类断言**：必须区分 `[dependencies]` 与 `[dev-dependencies]`（以及 `target.*` 段），并以 `cargo metadata` 或**逐份清单直读**为准，**不得用 `grep` 数文件名**。写结论时注明取自哪个 section。
>    ⚠️ 本仓 workspace 含 git 依赖（`openai-oss-forks/tungstenite-rs`），`cargo metadata --offline` 直接失败（exit 101），联网又常超出沙箱。**拿不到 `cargo metadata` 时，逐跳直读 manifest 的 `[dependencies]` 段是可接受的替代**，但要在文中写明用的是哪种口径。
> 2. **机制类断言**：要说某机制「正在生效」，必须找到它的**构造点与调用方**，只找到类型定义、常量或同名文件不够。类型存在 ≠ 类型被构造 ≠ 该路径是默认路径。
>
> 另一先例：四条扩展路径的关系曾被标为 E1 留白，直到第 3 批读了各 crate 的 `Cargo.toml` 才得出结论 <!-- ref-exempt: 泛指多个 crate 的清单文件 -->——**结果与最初的直觉推断并不一致**（见 `mcp_and_extensions.md` §1）。

### 5.4 取证方式的六条禁忌（T1–T6）

> [!IMPORTANT]
> 上面两条硬规则管的是「依赖」与「机制」。**本轮双轨审查暴露的错误已经溢出这两类**，完整清单写在 [`AI_Coding_Context.md`](../../AI_Coding_Context.md) 的「🧨 取证方式本身的禁忌」表里，此处只留索引，避免两处各写一份、各自漂移：
>
> | 编号 | 一句话 |
> | ---- | ---- |
> | **T1** | 读注释 / README / 帮助文本就下结论——`codex-rs/config/src/loader/mod.rs` 的两段紧邻注释对配置层优先级给出**相反**答案，且都与实现不符 |
> | **T2** | 信任自己临时写的计数脚本而不先自证——`Op` 数错成 16（真值 26）、`thread/*` 数错成 57（真值 60），两次都是脚本自身的口径缺陷 |
> | **T3** | 把 `Stage::Removed` 读成「不可用」——`Stage` 只影响 `emit_metrics` 的指标过滤，`apply_map` 全程不看它 |
> | **T4** | 把上游文档 / `justfile` / AGENTS.md 的记载当成当前可执行——三处已确认陈旧，见 §3.5 |
> | **T5** | 符号 `pub` + 名字贴切 + 位置显眼 ⇒ 认定它生效（即上面的硬规则 2，本轮又新增两个反例：`ConfigLayerSource::Mdm`、`ConfigToml::profiles`） |
> | **T6** | 引用行号前不看文件总行数 |

### 5.5 其他

| 约定 | 说明 |
| ---- | ---- |
| `related_files` 只列**实际读过**的文件 | 不列未读文件 |
| 每篇文档记录基线 commit 与 `verified_at` | 便于漂移检测 |
| 数值类事实必须给可复现命令 | 不抄历史数字；命令登记在 `dev_docs/_analysis/claim_ledger.jsonl`，由 `--verify-repo` 对账 |
| 跨文档引用写「`<文档名>.md` §N — 章节标题」 | 只写 `§N` 不带标题的引用不会被漂移检查覆盖（见 §6） |
| 未覆盖范围要显式列清单 | 不写空泛免责声明；已闭合的项要注明**去哪读**，不要只划掉 |

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
> 实证：第二轮独立审查查出的多项 HIGH 级不一致，**全部是在 5 项 checker 通体绿灯的状态下漏过去的**（见 `dev_docs/_analysis/health_check_report.md` 的「跨文档矛盾」小节）。

> [!TIP]
> 上述两个盲区已由 `dev_docs/_analysis/cross_doc_consistency_checker.py` 补上，它还多做两件事：
>
> - **对账仓库真值**（`--verify-repo`）——每项已登记事实（见 `dev_docs/_analysis/claim_ledger.jsonl`）带一条可复现命令，用命令输出校验文档数字。跨文档一致性检查只能发现「两处写得不一样」，**发现不了「各处都抄成同一个错值」**，这一项才能。
> - **跨文档 `§N` 引用漂移**——章节号会因插入新章节而整体顺延，旧引用仍指向一个「存在但内容已换」的章节。判据是引用后跟的标题文字若明确匹配到了另一个章节号，即判漂移（匹配不上则视为作者的描述性文字，不报；匹配到被引章节的子节视为合法精度差异，不报）。
>
> **写跨文档引用时请用「`<文档名>.md` §N — 章节标题」这个形式**，只写 `§N` 不带标题的引用**不会被检查**——本轮就在主文档里发现一处这样的静默漂移（`find_codex_home` 的引用仍指向 `config_system.md` §5，而该文插入新章节后正确编号已是 §6）。

另有两项独立门禁：`dev_docs/_analysis/ref_checker.py`（仓库路径引用是否可解析，ERROR 必须为 0）与 `bash dev_docs/_analysis/redact_scan.sh`（脱敏）。

**仍然没有被任何 checker 覆盖的**：断言与源码是否相符。这只能靠独立复核，也正是 §5.4 那六条禁忌要防的东西。

---

## 7. 提交前自检

```
□ just fmt                                   已跑
□ just test -p <crate>                       通过
□ 改了 common/core/protocol → just test       通过（先问用户）
□ 大改动 → just fix -p <crate>                已跑
□ 改了 Cargo 依赖 → just bazel-lock-update    已跑
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → 重生成 schema 夹具（见下方注记 1）已跑
□ 改了用户可见 UI（含新增 UI）→ insta 快照覆盖已补/已更新
□ 新增 include_str! / sqlx::migrate! → BUILD.bazel compile_data 已补
□ 新建 crate 或改了任意 codex-rs/**/Cargo.toml → 过 verify_cargo_workspace_manifests.py 六条门禁
□ 改了 clippy lint 配置 → Cargo workspace lints 与 Bazel clippy flags 已双边同步
□ 改了 codex-rs/tui → 没有直接 import codex_core（含注释与字符串字面量）
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500）
□ 未触碰 CODEX_SANDBOX_*
□ 未向 docs/ 添加通用文档
□ 改了 .github/**/*.yml → 已确认拿到临时的工作流推送批准
□ 改了 dev_docs → 5 项框架 checker + 跨文档对账 + ref_checker + 2 项脱敏扫描全绿
□ push 目标是 fork，不是 origin
```

### 五条容易踩空的说明

1. **`just write-app-server-schema` 当前是坏的。** 该 recipe 执行 `cargo run -p codex-app-server-protocol --bin write_schema_fixtures`，但 `codex-app-server-protocol` **没有任何 bin target**（无 `[[bin]]`、无 `src/bin/`），命令必然失败。可用的入口是 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`。**注意这是循环陈旧**：校验测试自己的失败文案也在推荐这条坏命令（见 §3.5 S3）。该脚本内部用 `cargo test` 驱动一个 `#[ignore]` 的生成函数，是把测试当「代码生成宿主」用，**与「禁止直接跑 `cargo test`」不冲突**；但该 workaround 本身未实测，产物请自行核对。
2. **UI 改动必须配快照。** AGENTS.md 的 `### Snapshot tests` 一节写的是 Requirement：任何影响用户可见 UI 的改动（含新增 UI）都必须附带对应的 `insta` 快照覆盖。这条最常被漏。命令链见 `tui_guide.md` §4 与 `testing_guide.md` §7。
3. **动 CI 配置的推送可能被拒。** ⚠️ **第 6 轮：本条的原始依据已消失。** 上一版引用的 `.codex/skills/pushing-ci-changes/SKILL.md` 已不存在<!-- ref-exempt: 反例——正文说明该路径已不存在 -->；`.codex/skills/` 现有 11 个技能，其中没有等价物，`AGENTS.md` 中亦未检索到「推送 CI 配置需临时角色」的条款。

   **该限制是否仍然生效，本轮未能取证**——可能是规约移出了仓库，也可能是已取消。在拿到新依据之前，**按仍然生效对待**（这是更保守的一侧），但不要再把上述路径当作出处引用。
4. **`.github/workflows/repo-checks.yml` 有四条阻塞性机检脚本**，任何一条失败都挡合并：`.github/scripts/verify_cargo_workspace_manifests.py`（各 crate 清单必须继承 workspace 设置、**禁止任何 `[features]`**、禁止 `optional = true`）、`.github/scripts/verify_tui_core_boundary.py`、`.github/scripts/verify_bazel_clippy_lints.py`、`scripts/asciicheck.py` + `scripts/readme_toc.py`。同 job 还跑 `just fmt-check` 与 `pnpm run format`，末尾挂 `check-clean-worktree`。
5. **`codex-tui` 的 core 边界是字面量级检查。** `.github/scripts/verify_tui_core_boundary.py` 只做四件事：manifest 里不出现键名 `codex-core`，加上三条**逐行正则** `\bcodex_core::` / `\buse\s+codex_core\b` / `\bextern\s+crate\s+codex_core\b`；扫描范围是 `codex-rs/tui/**/*.rs` 全目录（含 `tests/` 与 `src/bin/`），**不做语法解析——注释与字符串字面量里出现同样会挂**。反过来，**传递依赖与 `codex_app_server_client::legacy_core` 再导出是被明确允许的**（脚本报错文案自己点名了后者）。详见 `tui_guide.md` §0.1–§0.2。
