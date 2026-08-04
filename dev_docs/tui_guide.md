---
title: Codex TUI 开发指南
summary: 描述 codex-tui 的模块版图与高触碰大文件实测规模、codex-tui 不「直接」依赖也不「直接」导入 codex-core 这条 CI 强制的架构不变量（core 仍会传递性链接进来，配置类型经 legacy_core 再导出）、AppServerTarget 的 Embedded / LocalDaemon / Remote 三态与其选择逻辑、styles.md 与 clippy.toml 的样式约定（含 #![deny(clippy::disallowed_methods)] 的编译期强制与机器强制的覆盖缺口）、AGENTS.md 中 TUI 与快照测试条款的落地要点，以及 app / chatwidget / bottom_pane 三层结构与在该 crate 内新增代码的硬性约束。注意「只走 app-server 协议」仅对线程/回合级会话 RPC 成立，本地 state DB 等数据面依赖由 TUI 直接持有。
keywords: codex | tui | ratatui | styles | chatwidget | bottom-pane | clippy | snapshot-test | app-server-client
scope: codex-rs/tui 的结构、样式规范、架构边界与改动约束
related_files: codex-rs/tui/styles.md | codex-rs/tui/Cargo.toml | codex-rs/clippy.toml | codex-rs/tui/src/lib.rs | codex-rs/tui/src/chatwidget.rs | codex-rs/tui/src/wrapping.rs | codex-rs/tui/src/render/line_utils.rs | codex-rs/tui/src/bottom_pane/AGENTS.md | .github/scripts/verify_tui_core_boundary.py | .github/workflows/repo-checks.yml | AGENTS.md
dependencies: dev_docs/development_workflow.md | dev_docs/crate_map.md
verified_at: 2026-08-05
---

# TUI 开发指南

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-tui`（**Rust 源码 238,439 行**，仅计 `.rs`；连同 629 个 `.snap` 等全部受控文件为 262,771 行。全仓第 2 大 crate，仅次于 `codex-core` 的 296,963 行 `.rs`）
> **证据等级**: 文件数量与行数清点为 E1（`git ls-files` / `wc -l` 口径见正文）；`codex-rs/tui/styles.md`、`codex-rs/clippy.toml`、AGENTS.md 的条款为 E2（明文）；架构边界为 E3（CI 脚本与 `codex-rs/tui/src/lib.rs` 导入）；**该边界的 CI 阻塞性为 E1**（`.github/workflows/blocking-ci.yml:33-36` 把 `.github/workflows/repo-checks.yml` 作为可复用 workflow 调起，`:58` 把 `repo-checks` 列入汇总作业的 `needs`）

> [!NOTE]
> **依赖数量的口径**（`codex-rs/tui/Cargo.toml`，E1）：
>
> | 口径 | 数量 |
> | ---- | ---: |
> | `[dependencies]` 段条目总数 | 87 |
> | 全部依赖段（含 `target.*` 与 `dev-dependencies`）去重后、标注 `workspace = true` 的条目 | 102 |
> | `[dependencies]` 段中的 `codex-*` crate | 42 |
> | 全文件去重后的 `codex-*` crate | 45 |
>
> 本文引用依赖数量时一律注明口径。此前版本写的「47 个 workspace 依赖」在任何口径下都不成立，已废弃。

---

## 0. 先读这一节：这里是全仓改动约束最严的地方

`codex-tui` 同时踩中四条约束：

| 约束 | 出处 |
| ---- | ---- |
| **不得「直接」依赖或 import `codex-core`**，且由 CI 机器强制（传递链接不受此限，见 §0.1） | `.github/scripts/verify_tui_core_boundary.py`（由 `.github/workflows/repo-checks.yml` 调起） |
| AGENTS.md **举例**点名了 5 个 TUI 高触碰文件（名单开放，见 §2） | AGENTS.md 顶部规则列表，grep `high-touch files` |
| `codex-rs/tui/src/chatwidget.rs` 有**额外**的单独约束 | AGENTS.md 顶部规则列表，grep `keep chatwidget.rs focused on orchestration` |
| 样式规则由 `codex-rs/clippy.toml` **机器强制** | `codex-rs/clippy.toml` 的 `disallowed-methods` |

在这个 crate 里写代码之前，先读完本文 §0.1、§2、§3 与 §4。

### 0.1 架构不变量：`codex-tui` 不「直接」依赖、不「直接」导入 `codex-core`（E3）

这是本文最容易被误判的一条；在 TUI 相关的架构约束里，只有这一条有专属的 CI 校验脚本（`.github/scripts/` 下另有其他校验脚本，`.github/workflows/repo-checks.yml` 也不止跑这一个，故不宜说成「全仓唯一」）。**注意"直接"这两个字——它是约束的全部内容。**

`.github/scripts/verify_tui_core_boundary.py` 的文件头写明：

> `"""Verify codex-tui does not depend on or import codex-core directly."""`

该脚本同时校验两件事：

1. `codex-rs/tui/Cargo.toml` 的依赖表中不出现 `codex-core`（实测：确无该条目）；
2. **`codex-rs/tui/` 整个 crate 目录下的任何 `.rs`**（含 `codex-rs/tui/tests/` 的 9 个集成测试 `.rs` 与 `codex-rs/tui/src/bin/md-events.rs`）不出现 `codex_core::` / `use codex_core` / `extern crate codex_core`。脚本用的是 `TUI_ROOT.glob("**/*.rs")`（`TUI_ROOT = ROOT / "codex-rs" / "tui"`，见 `.github/scripts/verify_tui_core_boundary.py:14`、`:76`），**不是**只扫 `src/`。匹配是**逐行正则**（`:18-20`），不做语法解析——注释与字符串字面量里出现同样会失败。

`.github/workflows/repo-checks.yml` 直接 `run: python3 .github/scripts/verify_tui_core_boundary.py`，而 `.github/workflows/blocking-ci.yml:33-36` 把 `.github/workflows/repo-checks.yml` 作为可复用 workflow 调起、`:58` 又把它列进汇总作业的 `needs`，因此这是 **PR 级别的硬门禁**，不是风格建议。

TUI 的会话 RPC 通路是 **app-server 客户端**：`codex-rs/tui/Cargo.toml:30` 依赖 `codex-app-server-client`，`codex-rs/tui/src/lib.rs` 导入并使用 `InProcessAppServerClient` 与 `RemoteAppServerClient` 两种客户端——前者在同进程内拉起 app-server，后者连接外部 app-server 进程（可以是本机 daemon，也可以是远端）。两条路径共用同一套协议，落点有三种，见 §6。

> [!CAUTION]
> **本文档体系上一稿把这条约束说过头了**，写成"TUI 不链接 `codex-core`"。**从链接期看，`codex-tui` 确实链接了 `codex-core`**——只是没有直接依赖边。E3 依据：
>
> - `codex-rs/cloud-config/Cargo.toml:16` 与 `codex-rs/utils/oss/Cargo.toml:11` 都有 `codex-core = { workspace = true }`（普通 `[dependencies]`，非 dev/build）；
> - `codex-rs/tui/src/lib.rs:41` `use codex_cloud_config::cloud_config_bundle_loader_for_storage;`，以及 `:66` `use codex_utils_oss::ensure_oss_provider_ready;` 与 `:67` `use codex_utils_oss::get_default_model_for_oss_provider;`（本仓 rustfmt 强制 one-import-per-line，不存在大括号合并写法）；
> - `codex-app-server-client` 自身也直接依赖 `codex-core`。
>
> 传递路径复核（**E1/E3，直读两份 manifest 的 `[dependencies]` 段**）：`codex-rs/tui/Cargo.toml:30` 有 `codex-app-server-client`，`codex-rs/app-server-client/Cargo.toml:20` 有 `codex-core`，两者都在普通 `[dependencies]` 段（非 dev/build）。因此 `codex-tui` 的直接普通依赖里没有 `codex-core`，但沿普通依赖可达，最短路径之一是 `codex-tui → codex-app-server-client → codex-core`。
>
> 这里刻意**不**用 `cargo metadata` 取证：本仓 workspace 含 git 依赖（`openai-oss-forks/tungstenite-rs`），`--offline` 直接失败（exit 101），联网又超出常规沙箱；而结论用成本更低的 manifest 直读就能确证，可复现性反而更高。
>
> **准确的表述**：**没有直接依赖边、没有直接导入（CI 强制）；`codex-core` 仍会经由若干中间 crate 传递性地链接进来，且 core 的配置类型通过 `codex_app_server_client::legacy_core` 被再导出（见 §0.2）。** 门禁管的是**代码耦合的可见面**，不是二进制里有没有这份代码。

### 0.2 但存在一个官方逃生舱：`legacy_core`（E3）

> [!IMPORTANT]
> **不要把上面的边界理解成「core 的一切都必须经协议方法抵达」。** `codex-app-server-client` 显式再导出了 core 的配置类型：
>
> ```rust
> // codex-rs/app-server-client/src/lib.rs
> /// module exists so clients can remove a direct `codex-core` dependency
> /// while legacy startup/config paths are migrated to RPCs.
> pub mod legacy_core {
>     pub mod config {
>         pub use codex_core::config::*;
>         pub mod edit { pub use codex_core::config::edit::*; }
>     }
> }
> ```
>
> TUI 用它的地方有 **93 处、分布在 40 个文件**（`grep -rn "legacy_core" codex-rs/tui/src/`），`codex-rs/tui/src/lib.rs` 开头就是 `use crate::legacy_core::config::Config;`。
>
> 校验脚本自己的报错文案也点名了它：`"...startup gaps belong behind codex_app_server_client::legacy_core."`——即这是**被认可的过渡通道**，不是绕过门禁的歪路。

因此边界的准确含义是：

| 被禁止的 | 被允许的 |
| ---- | ---- |
| `codex-rs/tui/Cargo.toml` 里出现 `codex-core`（含 dev / build / target 段） | 经 `codex_app_server_client::legacy_core` 使用 core 的**配置类型** |
| `tui/src/` 里出现 `codex_core::` / `use codex_core` / `extern crate codex_core` | 依赖 `codex-core-plugins`（**另一个 crate**，不在禁止名单内） |
| — | 依赖 `codex-cloud-config`、`codex-utils-oss`、`codex-app-server-client` 等**自身直接依赖 `codex-core` 的 crate**（传递链接不受门禁约束） |

> [!NOTE]
> `legacy_core` 的模块注释写明它的存在是为了让客户端**先摘掉直接依赖**，配置/启动路径迁到 RPC 是后续的事。所以它是**会缩小的**——新代码优先走协议方法，不要新增 `legacy_core` 用法。
>
> 本文档体系第一版把这条边界写反了（说所有前端都汇聚到 codex-core）；第二轮改成「必须先有协议方法」又矫枉过正，漏了这个逃生舱；第三轮补上了逃生舱，却把"不直接依赖"扩大成了"不链接"（见 §0.1 的 CAUTION）。**这个来回本身就说明：涉及依赖边界的断言，务必区分「直接依赖 / 直接导入 / 传递链接 / 再导出」四种关系，且传递关系必须沿依赖链逐跳核对中间 crate 的 manifest（`cargo metadata` 在本仓不可离线运行，见 §0.1 的 CAUTION），不能只看 TUI 自己那一份清单。** 以 §0.1 + 本节为准。

---

## 1. 模块版图

`codex-rs/tui/src/` 下有 **131 个一级条目**（E1，`ls` 口径）。三层主结构：

```
codex-rs/tui/src/
├── lib.rs (3,413 行)          ← crate 入口，含 app-server 客户端选择
├── cli.rs                     ← TUI 的 clap 参数
│
├── app_event.rs               ← 顶层：应用事件类型
├── app_event_sender.rs        ← 顶层：事件发送端
├── app_command.rs             ← 顶层：应用命令
├── app_backtrack.rs           ← 顶层：回溯
│
├── app.rs (1,424 行) / app/   ← 应用层：事件分发、会话生命周期、线程路由
│   ├── event_dispatch.rs / session_lifecycle.rs
│   ├── thread_events.rs / thread_routing.rs / thread_session_state.rs
│   ├── agent_status_feed.rs / agent_navigation.rs / agent_picker.rs
│   ├── safety_buffering.rs / resize_reflow.rs / plugin_mentions.rs / pets.rs
│   ├── app_server_events.rs / app_server_requests.rs / app_server_event_targets.rs
│   ├── …（共 33 个 .rs，另有 snapshots/ 与 tests/ 两个子目录 = 35 个一级条目）
│   ├── tests.rs (7,520 行)
│   └── tests/                 ← 10 个 .rs + snapshots/
│
├── chatwidget.rs (2,020 行) / chatwidget/  ← 会话主视图（编排层）
│   ├── chatwidget/            ← 60 个 .rs，另有 snapshots/ tests/ tokens/ = 63 个一级条目
│   └── chatwidget/tests/      ← 23 个 .rs + snapshots/
│
├── bottom_pane/               ← 输入区；`ls` 口径 50 个一级条目 = 43 个 .rs + AGENTS.md + 6 个子目录
│                                 递归口径 `git ls-files codex-rs/tui/src/bottom_pane | wc -l` = 264
│   ├── chat_composer.rs (12,616 行)  ← 全仓最大文件
│   ├── textarea.rs (4,016 行)
│   ├── mod.rs (3,114 行)
│   ├── footer.rs (2,075 行)
│   ├── request_user_input/mod.rs (3,899 行)
│   └── AGENTS.md              ← 本目录专属规则（改状态机须同步模块文档）
│
├── keymap.rs (3,203 行)        ← 键位映射
├── resume_picker.rs (6,681 行) ← 会话恢复选择器
├── app_server_session.rs (2,960 行) ← 与 app-server 的会话
├── wrapping.rs (1,948 行)      ← 换行助手：pub(crate) word_wrap_line（:856）/ word_wrap_lines（:1206）
├── render/line_utils.rs (76 行) ← 行前缀助手：pub prefix_lines（:57）
│
├── 渲染辅助
│   ├── color.rs / frames.rs / custom_terminal.rs
│   ├── diff_model.rs / diff_render.rs
│   ├── ascii_animation.rs / shimmer（见 styles.md）
│   └── exec_cell/
│
└── 功能模块
    ├── file_search.rs / external_editor.rs / clipboard_*.rs
    ├── get_git_diff.rs / git_action_directives.rs / branch_summary.rs
    ├── collaboration_modes.rs / goal_display.rs
    ├── approval_events.rs / auto_review_denials.rs
    ├── config_update.rs / debug_config.rs
    └── external_agent_config_migration/
```

> [!IMPORTANT]
> `codex-rs/tui/src/app_event.rs`、`codex-rs/tui/src/app_event_sender.rs`、`codex-rs/tui/src/app_command.rs`、`codex-rs/tui/src/app_backtrack.rs` 位于 `codex-rs/tui/src/` **顶层**，不在 `app/` 目录下。此前版本把它们画在 `app.rs / app/` 之下是错的，按错误路径去 grep 会找不到文件。

> **未验证**（E1）：`app` → `chatwidget` → `bottom_pane` 的**事件流方向与所有权关系**。上面的三层划分是按文件名与规模归纳的结构性描述。要确认实际数据流，读顶层的 `codex-rs/tui/src/app_event.rs` 与 `codex-rs/tui/src/app_event_sender.rs`，再看 `codex-rs/tui/src/app/event_dispatch.rs`。

> `codex-rs/tui/src/bottom_pane/` 目录自带一份 AGENTS.md：改动 paste-burst 与 chat-composer 状态机时，必须同步更新 `codex-rs/tui/src/bottom_pane/chat_composer.rs` / `codex-rs/tui/src/bottom_pane/paste_burst.rs` 的模块文档，并核对文档只描述代码中真实存在的 API 与行为。

---

## 2. 高触碰大文件：规范与实测

AGENTS.md 顶部规则列表（grep `Avoid large modules`）的目标是模块 **500 行以内**（不含测试）、文件超过约 **800 行**时新功能放新模块。

AGENTS.md **举例**点名了 5 个 TUI 高触碰文件（grep `high-touch files`），并以 `, and similarly central orchestration modules.` 收尾——**名单是开放的**，规则同样适用于其他中心编排模块，不要把它当封闭清单来做「不在名单上就不受约束」的推断。

这 5 个例子，以及本 crate 的实测 Top 12（E1，`wc -l`）：

| 文件 | 实测行数 | 被点名 |
| ---- | ---: | :--: |
| `codex-rs/tui/src/bottom_pane/chat_composer.rs` | **12,616** | ✅ |
| `codex-rs/tui/src/app/tests.rs` | 7,520 | — |
| `codex-rs/tui/src/resume_picker.rs` | 6,681 | — |
| `codex-rs/tui/src/chatwidget/tests/status_and_layout.rs` | 4,849 | — |
| `codex-rs/tui/src/bottom_pane/textarea.rs` | 4,016 | — |
| `codex-rs/tui/src/bottom_pane/request_user_input/mod.rs` | 3,899 | — |
| `codex-rs/tui/src/chatwidget/tests/popups_and_settings.rs` | 3,797 | — |
| `codex-rs/tui/src/lib.rs` | 3,413 | — |
| `codex-rs/tui/src/keymap.rs` | 3,203 | — |
| `codex-rs/tui/src/bottom_pane/mod.rs` | 3,114 | ✅ |
| `codex-rs/tui/src/app_server_session.rs` | 2,960 | — |
| `codex-rs/tui/src/chatwidget/tests/slash_commands.rs` | 2,958 | — |

另外三个被点名的文件：`codex-rs/tui/src/app.rs`（1,424 行）、`codex-rs/tui/src/bottom_pane/footer.rs`（2,075 行）、`codex-rs/tui/src/chatwidget.rs`（2,020 行）。它们都没进 Top 12——**被点名的理由是「吸引不相关改动」，不是「当前最大」**。

> [!IMPORTANT]
> **正确的理解方式**：500/800 行的目标约束的是**新增代码**。AGENTS.md 的原文是 "add new functionality in a new module instead of extending the existing file **unless there is a strong documented reason not to**"——存量文件不违反规范，但**新代码不得继续堆入**。
>
> 注意条款自带例外口：`unless there is a strong documented reason not to`。它比看上去有弹性，但 **"documented" 是硬要求**——理由必须落成文字（模块/函数注释或 PR 描述），口头「这次特殊」不算。
>
> 本表列出实测值是为了避免误判，**不是对上游的整改建议**。

### `codex-rs/tui/src/chatwidget.rs` 的额外约束

AGENTS.md 顶部规则列表（grep `keep chatwidget.rs focused on orchestration`）：

> "Avoid adding new standalone methods to `codex-rs/tui/src/chatwidget.rs` unless the change is trivial; prefer new modules/files and keep `chatwidget.rs` focused on orchestration."

（原文后半句只写文件名 `chatwidget.rs`；此处照录以保持可 grep，实际指的是 `codex-rs/tui/src/chatwidget.rs`。）

**翻译成操作**：`codex-rs/tui/src/chatwidget.rs`（2,020 行）只做编排。要加逻辑，新建模块，让它调用。`chatwidget/` 目录下已有 60 个 `.rs` 兄弟模块，绝大多数就是这样被拆出来的——加新文件是这里的常规动作，不是例外。

### 读取大文件的正确姿势

```bash
# 先拿结构
git grep -n "^pub fn\|^impl\|^pub struct\|^fn " codex-rs/tui/src/bottom_pane/chat_composer.rs | head -50
# 再定点读取
```

---

## 3. 样式约定（E2）

`codex-rs/tui/styles.md`（21 行）是 AGENTS.md 的 `## TUI style conventions` 一节指定的样式事实源（该节正文只有一句 "See `codex-rs/tui/styles.md`."）。

### 文本层级

| 用途 | 样式 |
| ---- | ---- |
| 标题 | `bold`。Markdown 多级标题**保留 `#` 号** |
| 正文 | 默认 |
| 次要文本 | `dim` |

### 前景色

| 语义 | 颜色 |
| ---- | ---- |
| 默认 | 大多数情况用默认前景色（`reset` 可以恢复） |
| 用户输入提示、选中、状态指示 | ANSI `cyan` |
| 成功与新增 | ANSI `green` |
| 错误、失败与删除 | ANSI `red` |
| Codex 自身 | ANSI `magenta` |

### `codex-rs/tui/styles.md` 的 Avoid 清单（三条，全文照录要点）

| # | 条目 | 是否被 clippy 机器强制 |
| ---: | ---- | ---- |
| 1 | 回避自定义颜色——无法保证在各种终端主题下对比度足够。`codex-rs/tui/src/shimmer.rs` 是可行的例外，因为它只取默认色并调整明度 | **是**。`Color::Rgb` / `Color::Indexed`（见 §3 的 clippy 表）都在 `disallowed-methods` 中 |
| 2 | 回避把 ANSI `black` 与 `white` 用作**前景色**，默认终端主题色效果更好（用 `reset` 可取回）。**例外**：在手工上色的背景上要拿到对比度时可用 | **部分**。`disallowed-methods` 只列了 `ratatui::style::Stylize::white` / `::black` **两个方法**；等价的 `Style::default().fg(Color::White)` / `Color::Black` **不在**名单内 |
| 3 | 回避 ANSI `blue` 与 `yellow`，当前样式指南不使用它们，改用上表列出的前景色 | **部分**。`yellow` 被 clippy 拦下；`blue` 只是文档约定 |

### `codex-rs/clippy.toml` 的 `disallowed-methods`（机器强制，E2）

`codex-rs/clippy.toml` 的 `disallowed-methods` 数组中与 TUI 样式相关的 5 条：

| 被禁路径 | 理由（原文要点） |
| ---- | ---- |
| `ratatui::style::Color::Rgb` | Use ANSI colors, which work better in various terminal themes. |
| `ratatui::style::Color::Indexed` | 同上 |
| `ratatui::style::Stylize::white` | 回避硬编码 white，优先默认前景色或 dim/bold。**例外**：在硬编码 ANSI 背景上渲染时可禁用该规则 |
| `ratatui::style::Stylize::black` | 同上（硬编码 black） |
| `ratatui::style::Stylize::yellow` | 回避 yellow，优先 `codex-rs/tui/styles.md` 中列出的颜色 |

> [!TIP]
> **在本 crate 里，这不是 lint 警告，是编译期错误。** `codex-rs/tui/src/lib.rs:5` 有 `#![deny(clippy::disallowed_methods)]`——违反 `disallowed-methods` 在 `codex-tui` 内直接 fail，**唯一合法出口是显式写 `#[allow(clippy::disallowed_methods)]`**。这也解释了 `codex-rs/tui/styles.md` 为什么把 `codex-rs/tui/src/shimmer.rs` 列为例外：该例外在代码里正是靠 `codex-rs/tui/src/shimmer.rs:57` 的 `#[allow(clippy::disallowed_methods)]` 加 `:60` 的 `Color::Rgb` 落地的。全 crate 共 18 处这类 `allow`（`grep -rn "allow(clippy::disallowed_methods)" codex-rs/tui/`）——加这种 `allow` 时应像 shimmer 那样在紧邻处写明理由。
>
> **自定义颜色是被机器拦下的，不只是文档劝阻。** `Color::Rgb` 与 `Color::Indexed` 是构造任意颜色的两条路，两条都在禁用列表里——这正是 `codex-rs/tui/styles.md` 第 1 条 Avoid 的执行手段。
>
> `codex-rs/tui/styles.md` 末尾写道 "(There are some rules to try to catch this in `clippy.toml`.)"（原文只写文件名，实际指 `codex-rs/clippy.toml`）——**文档约定与机器规则并不完全重合**。**机器强制只覆盖 Avoid 清单的一部分，且只覆盖到具体的方法/构造路径。** 落在文档一侧、clippy 不拦的至少有：ANSI `blue`；经 `Color::White` / `Color::Black` 而非 `Stylize::white` / `Stylize::black` 硬编码黑白；以及 `codex-rs/tui/styles.md` 的**全部正向条款**（标题用 `bold`、次要文本用 `dim`、cyan / green / red / magenta 的语义分配）——这些没有任何机器强制，只能靠 review。

同一个 `disallowed-methods` 数组里还有一批与样式无关的 sqlx 条目，共 **13 条**，跨 5 个路径前缀：`sqlx::Pool::connect{,_with,_lazy,_lazy_with}`、`sqlx::Pool::set_connect_options`、`sqlx::pool::PoolOptions::connect{,_with,_lazy,_lazy_with}`、`sqlx::Connection::connect{,_with}`、`sqlx::ConnectOptions::connect`、`sqlx::migrate::MigrateDatabase::create_database`。理由文案也不止「建池」一种：分别要求经 `codex-state` 的 sqlite shim **建池**、**建连接**、**建库**，外加一条「不得替换 shim 已建池的 options」（`set_connect_options`）。`codex-rs/clippy.toml:14` 的注释注明该名单是按 workspace sqlx 0.9.0 审计的——**升级 sqlx 时需要复查这份名单**。改 TUI 时通常不会碰到这一批。

---

## 4. AGENTS.md 中的 TUI 与测试条款（E2）

`codex-rs/tui/styles.md` 只管颜色与层级。**写法层面的约定在 AGENTS.md 里**，分散在下面几节。本节按章节标题归纳要点，不复制条款原文之外的解读；查原文请 grep 标题。

### `## TUI code conventions`

- 用 ratatui `Stylize` trait 的简洁助手。
- 普通 span：`"text".into()`。
- 带样式的 span：`"text".red()`、`"text".green()`、`"text".magenta()`、`"text".dim()` 等。
- 优先这些写法，而不是手工拼 `Span::styled` + `Style`。
- 原文给的示例（补丁摘要的文件行）：`vec!["  └ ".into(), "M".red(), " ".dim(), "tui/src/app.rs".dim()]`。

### `### TUI Styling (ratatui)`

| 要点 | 说明 |
| ---- | ---- |
| Stylize 助手优先 | `.dim()` / `.bold()` / `.cyan()` / `.italic()` / `.underlined()` 优于手写 `Style` |
| 简单转换优先 | span 用 `"text".into()`，line 用 `vec![…].into()`；类型推断有歧义时（如 `Paragraph::new` / `Cell::from`）才写 `Line::from(spans)` / `Span::from(text)` |
| **运行时计算的样式是例外** | Style 由运行时计算得出时，`Span::styled` 可以用；`Span::from(text).set_style(style)` 同样可接受 |
| 回避硬编码 white | 不用 `.white()`，默认前景色（不设色）即可 |
| 链式组合 | 如 `url.cyan().underlined()` |
| 单个元素 | 优先 `"text".into()`；只有目标类型不明或 `.into()` 会逼出额外类型标注时才用 `Line::from` / `Span::from` |
| 构造 line | 目标类型明确且无需额外标注时用 `vec![…].into()`，否则 `Line::from(vec![…])` |
| **回避无谓改写** | 在等价写法之间来回重构（`Span::styled` ↔ `set_style`、`Line::from` ↔ `.into()`）要有明确的可读性或功能收益；遵循文件内既有惯例，仅为满足 `.into()` 而加类型标注属于无谓改写 |
| 紧凑性 | 优先选 rustfmt 之后能留在一行的写法；都会折行时选折行数少的 |

### `### Text wrapping`

| 场景 | 用什么 |
| ---- | ---- |
| 换行纯字符串 | `textwrap::wrap` |
| 换行 ratatui `Line` | `codex-rs/tui/src/wrapping.rs` 中的 `word_wrap_lines` / `word_wrap_line` |
| 给换行结果加缩进 | `RtOptions` 的 `initial_indent` / `subsequent_indent`，而不是自写逻辑 |
| 给一组 line 统一加前缀（首行与后续行可不同） | `prefix_lines`（实现在 `codex-rs/tui/src/render/line_utils.rs`） |

### `### Snapshot tests`（**最容易漏掉的一条硬要求**）

> [!CAUTION]
> AGENTS.md 的原文是 **Requirement**：**任何影响用户可见 UI 的改动（含新增 UI）都必须附带对应的 `insta` 快照覆盖**——没有快照测试就新建一个，已有就更新，并把快照变更作为 PR 的一部分一起 review 和 accept。
>
> 这不是「建议补测试」，是 TUI 改动的准入条件。改了渲染却不带 `.snap` 变更的 PR 属于漏做。

有意变更 UI 或文本输出时的流程：

```bash
just test -p codex-tui                                   # 先跑出新快照
cargo insta pending-snapshots -p codex-tui               # 看有哪些待处理
cargo insta show -p codex-tui path/to/file.snap.new      # 预览单个（或直接读仓库里的 *.snap.new）
cargo insta accept -p codex-tui                          # 确认要全量接受本 crate 的新快照时才跑
```

没装工具：`cargo install --locked cargo-insta`。

### `### Test module organization`

新增测试模块时，内容写在**同级的独立文件**里，而不是内联在实现文件中，并用显式的 `#[path = "..._tests.rs"]`：

```rust
#[cfg(test)]
#[path = "parser_tests.rs"]
mod tests;
```

该约定**只适用于新增**测试模块；不要仅为了合规去搬动或重写已有的内联 `#[cfg(test)] mod tests { ... }`。TUI 里 `codex-rs/tui/src/config_update_tests.rs`、`codex-rs/tui/src/line_truncation_tests.rs`、`codex-rs/tui/src/markdown_render_tests.rs`、`codex-rs/tui/src/app/agent_status_feed_tests.rs` 等都是这一形态。

---

## 5. 测试组织（E1）

| 位置 | 规模 |
| ---- | ---- |
| `codex-rs/tui/src/app/tests.rs` | 7,520 行 |
| `codex-rs/tui/src/app/tests/` | 10 个 `.rs` + `snapshots/`，清单见下 |
| `codex-rs/tui/src/chatwidget/tests/` | 23 个 `.rs` + `snapshots/`，清单见下 |
| `codex-rs/tui/src/chatwidget/tests/status_and_layout.rs` | 4,849 行 |
| `codex-rs/tui/src/chatwidget/tests/popups_and_settings.rs` | 3,797 行 |
| `codex-rs/tui/src/chatwidget/tests/slash_commands.rs` | 2,958 行 |

> [!WARNING]
> 下面两份清单一律写全路径，因为**按短名 grep 会踩错**：`codex-rs/tui/src/app/safety_buffering.rs` 与 `codex-rs/tui/src/app/tests/safety_buffering.rs` 仅差一层目录；`codex-rs/tui/src/chatwidget/goal_menu.rs`、`codex-rs/tui/src/chatwidget/mcp_startup.rs`、`codex-rs/tui/src/chatwidget/side.rs`、`codex-rs/tui/src/chatwidget/usage.rs` 在 `codex-rs/tui/src/chatwidget/tests/` 下**各有一份同名文件**。

`codex-rs/tui/src/app/tests/` 的 10 个文件：`codex-rs/tui/src/app/tests/advanced_reasoning_tests.rs`、`codex-rs/tui/src/app/tests/key_chords.rs`、`codex-rs/tui/src/app/tests/model_catalog.rs`、`codex-rs/tui/src/app/tests/plugin_catalog.rs`、`codex-rs/tui/src/app/tests/rate_limits.rs`、`codex-rs/tui/src/app/tests/safety_buffering.rs`、`codex-rs/tui/src/app/tests/session_lifecycle_requests.rs`、`codex-rs/tui/src/app/tests/session_summary.rs`、`codex-rs/tui/src/app/tests/startup.rs`、`codex-rs/tui/src/app/tests/turn_submission.rs`。

`codex-rs/tui/src/chatwidget/tests/` 的 23 个文件按功能面切分，除上面三个大件外还有 `codex-rs/tui/src/chatwidget/tests/app_server.rs`、`codex-rs/tui/src/chatwidget/tests/approval_requests.rs`、`codex-rs/tui/src/chatwidget/tests/composer_submission.rs`、`codex-rs/tui/src/chatwidget/tests/config_errors_tests.rs`、`codex-rs/tui/src/chatwidget/tests/exec_flow.rs`、`codex-rs/tui/src/chatwidget/tests/goal_menu.rs`、`codex-rs/tui/src/chatwidget/tests/goal_validation.rs`、`codex-rs/tui/src/chatwidget/tests/guardian.rs`、`codex-rs/tui/src/chatwidget/tests/helpers.rs`、`codex-rs/tui/src/chatwidget/tests/history_replay.rs`、`codex-rs/tui/src/chatwidget/tests/mcp_startup.rs`、`codex-rs/tui/src/chatwidget/tests/permissions.rs`、`codex-rs/tui/src/chatwidget/tests/plan_mode.rs`、`codex-rs/tui/src/chatwidget/tests/plugin_catalog_tests.rs`、`codex-rs/tui/src/chatwidget/tests/review_mode.rs`、`codex-rs/tui/src/chatwidget/tests/side.rs`、`codex-rs/tui/src/chatwidget/tests/status_command_tests.rs`、`codex-rs/tui/src/chatwidget/tests/status_surface_previews.rs`、`codex-rs/tui/src/chatwidget/tests/terminal_title.rs`、`codex-rs/tui/src/chatwidget/tests/usage.rs`。

**测试按功能面拆分到子目录**，而不是塞进单个巨型 tests 文件——这符合 AGENTS.md「提取代码时把相关测试与模块文档一并迁移」的条目（grep `move the related tests`）。

快照规模（E1，`git ls-files "*.snap" | wc -l` 口径）：全仓 **681** 个 `.snap`，其中 **629** 个在 `codex-rs/tui/` 下。快照的强制要求与命令链见 §4「Snapshot tests」；更宽的测试栈见 [`testing_guide.md`](./testing_guide.md)。

---

## 6. 与 app-server 的关系（E3）

**线程/回合级的会话 RPC** 只走 app-server 协议这一条路（见 §0.1）。但这不等于「TUI 的一切数据都经协议」：配置类型走 `legacy_core`（§0.2，93 处 / 40 文件），本地 state DB 与 log DB 由 TUI 自己经 `codex_rollout::state_db`（`codex-rs/tui/src/lib.rs:61`）与 `codex_state::log_db`（`:62`）直接初始化、完全不经 RPC，另有 `codex-login`（6 文件）、`codex-models-manager`（7）、`codex-connectors`（9）、`codex-feedback`（13）、`codex-state`（7）、`codex-message-history`（7）、`codex-exec-server`（6）、`codex-rollout`（4）等直接依赖在用（文件数为 `grep -rl` 于 `codex-rs/tui/src/` 的口径）。**所以「唯一通路」的说法只在会话 RPC 这一面成立。**

「app-server」在 TUI 眼里有**三种落点**，由 `AppServerTarget` 枚举表达（`codex-rs/tui/src/lib.rs:264`）：

```rust
pub(crate) enum AppServerTarget {
    Embedded,                                          // 默认
    LocalDaemon { endpoint: RemoteAppServerEndpoint }, // 隐式自动切换
    Remote { endpoint: RemoteAppServerEndpoint },      // 显式 --remote
}
```

| target | 传输 | 客户端类型 | 触发条件 |
| ---- | ---- | ---- | ---- |
| **`Embedded`（默认）** | **同一 OS 进程内的 tokio 任务 + 有界 `mpsc` 通道**。不是子进程，不是 socket | `InProcessAppServerClient` | 无 `--remote`，且（无本地 daemon socket 在听 **或** 本次启动带了不可复现的覆盖项） |
| **`LocalDaemon`** | Unix domain socket，**跨进程** | `RemoteAppServerClient` | 无 `--remote`，且 `can_reuse_implicit_local_daemon` 为真，且探测到默认 daemon socket 正在监听。**这是隐式自动切换**——用户不会显式要求 |
| **`Remote`** | WebSocket（`ws://` / `wss://`）或 Unix socket | `RemoteAppServerClient` | CLI 传了 `--remote`（可选配 `--remote-auth-token-env`，后者仅对 `wss://` 或 loopback `ws://` 有效） |

**选择逻辑**（`codex-rs/tui/src/lib.rs:855-871` 的 `app_server_target_for_launch`，纯函数，有 3 个针对性单测在 `:2565` / `:2586` / `:2608`）：显式 remote → `Remote`；否则若 `can_reuse_implicit_local_daemon` 且探测到 socket → `LocalDaemon`；否则 `Embedded`。

**`can_reuse_implicit_local_daemon` 的四个与条件**（`codex-rs/tui/src/lib.rs:891-902`，注释原文 `A reused daemon cannot adopt this invocation's full launch config state.`）——任一不满足就退回 `Embedded`：① `cli_kv_overrides.is_empty()`（无 `-c` 覆盖）② `loader_overrides_are_default(...)`（无 `--profile` v2 / managed / system 配置路径覆盖等共 9 项，macOS 上多一项 `managed_preferences_base64`）③ `!strict_config` ④ `!has_non_replayable_launch_overrides`——实参就是 `cli.bypass_hook_trust`（`:968`）。

socket 探测是**带超时的连接尝试**且**仅 Unix**——`maybe_probe_default_daemon_socket` 在 `#[cfg(unix)]` 下走 `tokio::net::UnixStream::connect`（`:415`），在 `#[cfg(not(unix))]` 下是直接 `None` 的桩（`:440`），因此 **Windows 上 `LocalDaemon` 永不触发**。

**三态在下游的差异**（不只是传输差异）：

- **state DB 初始化**：`Embedded` 走 `state_db::try_init(config)`（TUI 自己建本地库，失败会走 `LocalStateDbStartupError` 的损坏恢复流程）；`LocalDaemon` / `Remote` 走 `state_db::get_state_db(config)`（不建库）。见 `codex-rs/tui/src/lib.rs:284-300` 的 `init_state_db_for_app_server_target`
- **workspace 语义**：只有 `Remote` 的 `uses_remote_workspace()` 为 `true`（`:271-273`），它决定 `ThreadParamsMode::Remote` vs `::Embedded`（`:275-281`）、`--cwd` 是否被当作远端 cwd override（`:980-983`）。**`LocalDaemon` 在这里与 `Embedded` 同侧**——虽跨进程，workspace 仍是本地的
- **环境加载**：`should_load_configured_environments(&loader_overrides, &app_server_target)`（`:831`）决定走 `EnvironmentManager::prepare_from_codex_home` 还是 `prepare_from_env`
- **会话恢复**：`:1781` 的 `is_persistent_resume` 判据是 `!matches!(&app_server_target, AppServerTarget::Embedded)`

> [!IMPORTANT]
> **最容易误判的一点**：`Embedded` 不意味着「没有 app-server」，也不意味着「跳过协议」。它是**同进程**的 app-server——`InProcessAppServerClient::start` 在 `tokio::spawn` 里跑一个 worker，两端各持一个有界 `mpsc::channel`（`codex-rs/app-server-client/src/lib.rs:466-469`）。响应仍是完整的 JSON-RPC 结果信封，原因写在源码注释里（`codex-rs/app-server-client/src/lib.rs:91-94`）："Even on the in-process path, successful responses still travel back through the same JSON-RPC result envelope used by socket/stdio transports because `MessageProcessor` continues to produce that shape internally."

**相关文件**：`codex-rs/tui/src/app_server_session.rs`（2,960 行）与 `codex-rs/tui/src/app_server_approval_conversions.rs` 负责会话与审批事件转换；`codex-rs/tui/src/app/app_server_events.rs` / `codex-rs/tui/src/app/app_server_requests.rs` / `codex-rs/tui/src/app/app_server_event_targets.rs` 负责事件路由。

> [!NOTE]
> `just tui-with-exec-server` **与本节三态无关**——它测的是远程**执行**后端（exec-server），TUI 的 app-server 仍是 `Embedded`。见 §8。

---

## 7. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **不得给 `codex-rs/tui/Cargo.toml` 加 `codex-core`；`codex-rs/tui/` 整个 crate 目录下的任何 `.rs`（含 `codex-rs/tui/tests/` 集成测试与 `src/bin/`）都不得出现 `codex_core::` / `use codex_core` / `extern crate codex_core`**——逐行正则匹配，注释与字符串里出现同样会失败（约束的是「直接」依赖与「直接」导入；传递链接不在其内，见 §0.1） | `.github/scripts/verify_tui_core_boundary.py`（CI 强制） |
| **改了用户可见 UI（含新增 UI）→ 必须附 insta 快照覆盖** | AGENTS.md `### Snapshot tests` |
| 改 TUI 后跑 `just test -p codex-tui` | AGENTS.md 顶部规则列表，grep `just test -p codex-tui` |
| 回避给 `codex-rs/tui/src/chatwidget.rs` 加新的独立方法（除非改动很小） | AGENTS.md 顶部规则列表，grep `keep chatwidget.rs focused on orchestration` |
| 新功能放新模块，不要扩写已超 800 行的文件 | AGENTS.md 顶部规则列表，grep `Avoid large modules` |
| 提取代码时把相关测试与模块文档一并迁移 | AGENTS.md 顶部规则列表，grep `move the related tests` |
| 新增测试模块用 `#[path = "..._tests.rs"]` 兄弟文件 | AGENTS.md `### Test module organization` |
| 颜色遵守 `codex-rs/tui/styles.md`；`white`/`black`/`yellow` 与 `Color::Rgb`/`Color::Indexed` 会被 clippy 拦下 | `codex-rs/clippy.toml` 的 `disallowed-methods` |
| 改 `bottom_pane/` 的 paste-burst / chat-composer 状态机 → 同步模块文档 | `codex-rs/tui/src/bottom_pane/AGENTS.md` |
| 大改动收尾跑 `just fix -p codex-tui` | AGENTS.md，grep `just fix -p <project>` |
| TUI 功能必须支持 Linux / macOS / Windows | AGENTS.md `## Platform Support` |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `app` → `chatwidget` → `bottom_pane` 的事件流 | E1 | 顶层的 `codex-rs/tui/src/app_event.rs`、`codex-rs/tui/src/app_event_sender.rs`，再看 `codex-rs/tui/src/app/event_dispatch.rs` |
| `app/` 下 33 个模块的职责划分 | E1 | 从 `codex-rs/tui/src/app/session_lifecycle.rs`、`codex-rs/tui/src/app/thread_routing.rs` 入手 |
| `chatwidget/` 下 60 个兄弟模块的职责划分 | E1 | 先 `ls` 再按功能名定点读 |
| `codex-rs/tui/src/bottom_pane/chat_composer.rs`（12,616 行）的内部结构 | E1 | 先读同目录 `AGENTS.md`，再 grep 结构分段读 |
| 键位映射体系 | E1 | `codex-rs/tui/src/keymap.rs`（3,203 行）与 `keymap/` 目录 |
| 斜杠命令的注册与分发 | E1 | `codex-rs/tui/src/chatwidget/tests/slash_commands.rs` 是最快的入口 |
| diff 渲染 | E1 | `codex-rs/tui/src/diff_model.rs`、`codex-rs/tui/src/diff_render.rs` |
| 会话恢复选择器 | E1 | `codex-rs/tui/src/resume_picker.rs`（6,681 行） |
| 快照测试的具体断言方式 | E1 | 见 [`testing_guide.md`](./testing_guide.md) |
| exec-server（远程**执行**后端）本身 | — | `codex-rs/cli` 的 `exec-server` 子命令与 `codex-rs/exec-server/` |

> [!NOTE]
> **`just tui-with-exec-server` 测的不是远程 app-server。** `justfile:25-28` 用 `[unix]` 属性把它标为 Unix 专属，实际执行 `scripts/run_tui_with_exec_server.sh`：脚本先 `cargo run -p codex-cli --bin codex -- exec-server --listen "$listen_url"` 起一个**远程执行后端**，再 `export CODEX_EXEC_SERVER_URL="$exec_server_url"`，最后 `cargo run -p codex-tui --bin codex-tui -- -c mcp_oauth_credentials_store=file "$@"` 起一个**普通 TUI**。
>
> 这个 TUI 的 app-server 仍走默认的 `AppServerTarget::Embedded`，**完全不经过 `RemoteAppServerClient`**（注意脚本传了 `-c`，按 §6 的 `can_reuse_implicit_local_daemon` 条件①，连 `LocalDaemon` 也被排除）。
>
> 真正切到 remote app-server 的开关是 CLI 的 `--remote` / `--remote-auth-token-env`。解析入口：`codex-rs/cli/src/main.rs:2427` 的 `resolve_remote_endpoint`。

---

## 9. 相关文档

- [开发流程](./development_workflow.md) — 规范、命令与提交前自检
- [Crate 地图](./crate_map.md) — TUI 在整体中的位置
- [app-server 协议](./app_server_protocol.md) — TUI 会话 RPC 的通路（三种落点见 §6）
- [测试指南](./testing_guide.md) — 快照测试
- 仓库自带：[`codex-rs/tui/styles.md`](../codex-rs/tui/styles.md)（**样式事实源**）、`codex-rs/tui/src/bottom_pane/AGENTS.md`（目录专属规则）
