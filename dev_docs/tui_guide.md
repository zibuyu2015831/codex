---
title: Codex TUI 开发指南
summary: 描述 codex-tui 的模块版图与高触碰大文件实测规模、styles.md 的样式约定及其在 clippy.toml 中的机器强制、app 与 chatwidget 与 bottom_pane 三层结构、快照测试的组织方式，以及在该 crate 内新增代码的硬性约束。
keywords: codex | tui | ratatui | styles | chatwidget | bottom-pane | clippy | snapshot-test
scope: codex-rs/tui 的结构、样式规范与改动约束
related_files: codex-rs/tui/styles.md | codex-rs/clippy.toml | codex-rs/tui/src/lib.rs | codex-rs/tui/src/bottom_pane/chat_composer.rs | codex-rs/tui/src/chatwidget.rs | AGENTS.md
dependencies: dev_docs/development_workflow.md | dev_docs/crate_map.md
verified_at: 2026-08-03
---

# TUI 开发指南

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-tui`（238,439 行，全仓第 2 大 crate，47 个 workspace 依赖）
> **证据等级**: 文件规模与 lint 规则为 E4；样式约定为 E2（`styles.md` 明文）；模块协作关系为 E1

---

## 0. 先读这一节：这里是全仓改动约束最严的地方

`codex-tui` 同时踩中三条规范：

| 约束 | 出处 |
| ---- | ---- |
| 5 个高触碰文件被 `AGENTS.md` **点名** | `AGENTS.md:54-57` |
| `chatwidget.rs` 有**额外**的单独约束 | `AGENTS.md:59-61` |
| 样式规则由 `clippy.toml` **机器强制** | `codex-rs/clippy.toml:8-13` |

在这个 crate 里写代码之前，先读完本文 §2 和 §3。

---

## 1. 模块版图

`codex-rs/tui/src/` 下有 **131 个一级条目**。三层主结构：

```
codex-rs/tui/src/
├── lib.rs (3,413 行)          ← crate 入口
├── cli.rs                     ← TUI 的 clap 参数
│
├── app.rs / app/              ← 应用层：事件循环、命令、回溯
│   ├── app_event.rs / app_event_sender.rs / app_command.rs
│   ├── app_backtrack.rs
│   └── app/tests.rs (7,520 行)
│
├── chatwidget.rs / chatwidget/  ← 会话主视图（编排层）
│   └── chatwidget/tests/        ← 大量快照与行为测试
│
├── bottom_pane/ (50 个文件)     ← 输入区
│   ├── chat_composer.rs (12,616 行)  ← 全仓最大文件
│   ├── textarea.rs (4,016 行)
│   ├── mod.rs (3,114 行)
│   └── request_user_input/mod.rs (3,899 行)
│
├── keymap.rs (3,203 行)        ← 键位映射
├── resume_picker.rs (6,681 行) ← 会话恢复选择器
├── app_server_session.rs (2,960 行) ← 与 app-server 的会话
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

> **未验证**（E1）：`app` → `chatwidget` → `bottom_pane` 的**事件流方向与所有权关系**。上面的三层划分是按文件名与规模归纳的结构性描述。要确认实际数据流，读 `app_event.rs` 与 `app_event_sender.rs`。

---

## 2. 高触碰大文件：规范与实测（E4）

`AGENTS.md:49-53` 的目标是模块 **500 行以内**（不含测试）、文件超过约 **800 行**时新功能放新模块。

`AGENTS.md:54-57` 点名的 5 个高触碰文件，以及本 crate 的实测 Top 12：

| 文件 | 实测行数 | 被点名 |
| ---- | ---: | :--: |
| `bottom_pane/chat_composer.rs` | **12,616** | ✅ |
| `app/tests.rs` | 7,520 | — |
| `resume_picker.rs` | 6,681 | — |
| `chatwidget/tests/status_and_layout.rs` | 4,849 | — |
| `bottom_pane/textarea.rs` | 4,016 | — |
| `bottom_pane/request_user_input/mod.rs` | 3,899 | — |
| `chatwidget/tests/popups_and_settings.rs` | 3,797 | — |
| `lib.rs` | 3,413 | — |
| `keymap.rs` | 3,203 | — |
| `bottom_pane/mod.rs` | 3,114 | ✅ |
| `app_server_session.rs` | 2,960 | — |
| `chatwidget/tests/slash_commands.rs` | 2,958 | — |

另外三个被点名的文件：`app.rs`、`bottom_pane/footer.rs`、`chatwidget.rs`。

> [!IMPORTANT]
> **正确的理解方式**：500/800 行的目标约束的是**新增代码**。`AGENTS.md:52-53` 的原文是 "add new functionality in a new module instead of extending the existing file"——存量文件不违反规范，但**新代码不得继续堆入**。
>
> 本表列出实测值是为了避免误判，**不是对上游的整改建议**。

### `chatwidget.rs` 的额外约束（`AGENTS.md:59-61`）

> "Avoid adding new standalone methods to `codex-rs/tui/src/chatwidget.rs` unless the change is trivial; prefer new modules/files and keep `chatwidget.rs` focused on orchestration."

**翻译成操作**：`chatwidget.rs` 只做编排。要加逻辑，新建模块，让 `chatwidget.rs` 调用它。

### 读取大文件的正确姿势

```bash
# 先拿结构
git grep -n "^pub fn\|^impl\|^pub struct\|^fn " codex-rs/tui/src/bottom_pane/chat_composer.rs | head -50
# 再定点读取
```

---

## 3. 样式约定（E2 + E4）

`codex-rs/tui/styles.md`（21 行）是 `AGENTS.md:135` 指定的样式事实源。

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

### 禁止使用（E4：由 clippy 机器强制）

`codex-rs/clippy.toml:8-13` 的 `disallowed-methods`：

| 被禁方法 | 理由（clippy.toml 原文要点） |
| ---- | ---- |
| `ratatui::style::Stylize::white` | 避免硬编码 white，优先默认前景色或 dim/bold。**例外**：在硬编码 ANSI 背景上渲染时可禁用该规则 |
| `ratatui::style::Stylize::black` | 同上 |
| `ratatui::style::Stylize::yellow` | 避免 yellow，优先 `tui/styles.md` 中列出的颜色 |

`styles.md` 还建议：

- **避免自定义颜色** —— 无法保证在各种终端主题下对比度足够。`shimmer.rs` 是个可行的例外，因为它只是取默认色并调整明度
- **避免 ANSI `blue`** —— 目前样式指南不使用（注：`blue` 未进 clippy 禁用列表，是文档约定而非机器强制）

> [!TIP]
> `styles.md` 末尾写道 "(There are some rules to try to catch this in `clippy.toml`.)"——**文档约定与机器规则并不完全重合**。`blue` 只在文档中被劝阻，`yellow`/`white`/`black` 则会被 clippy 拦下。

---

## 4. 测试组织

| 位置 | 规模 |
| ---- | ---- |
| `app/tests.rs` | 7,520 行 |
| `chatwidget/tests/status_and_layout.rs` | 4,849 行 |
| `chatwidget/tests/popups_and_settings.rs` | 3,797 行 |
| `chatwidget/tests/slash_commands.rs` | 2,958 行 |

**测试按功能面拆分到 `chatwidget/tests/` 子目录**，而不是塞进单个 `tests.rs`——这是符合 `AGENTS.md:56-58`「提取代码时把相关测试一并迁移」的做法。

TUI 大量使用 insta 快照测试（全仓 681 个 `.snap`）。快照更新流程见 [`testing_guide.md`](./testing_guide.md)。

---

## 5. 与 app-server 的关系

`app_server_session.rs`（2,960 行）与 `app_server_approval_conversions.rs` 说明：**TUI 也可以作为 app-server 的客户端**，而不只是直接内嵌 core。

`just tui-with-exec-server` 任务（`justfile`，Unix 专属）会同时起 exec-server 与 TUI，用于测试这条路径。

> **未验证**（E1）：TUI 何时走内嵌 core、何时走 app-server 会话。读 `app_server_session.rs` 与 `lib.rs` 的启动分支可确认。

---

## 6. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| 改 TUI 后跑 `just test -p codex-tui` | `AGENTS.md:63-64` |
| **不要**给 chatwidget.rs 加新的独立方法（除非改动很小） | `AGENTS.md:59-61` |
| 新功能放新模块，不要扩写已超 800 行的文件 | `AGENTS.md:52-53` |
| 提取代码时把相关测试与文档一并迁移 | `AGENTS.md:56-58` |
| 颜色遵守 `styles.md`；`white`/`black`/`yellow` 会被 clippy 拦下 | `codex-rs/clippy.toml:8-13` |
| 大改动收尾跑 `just fix -p codex-tui` | `AGENTS.md:70` |
| TUI 功能必须支持 Linux / macOS / Windows | `AGENTS.md:318` |

---

## 7. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `app` → `chatwidget` → `bottom_pane` 的事件流 | E1 | `app_event.rs`、`app_event_sender.rs` |
| `chat_composer.rs`（12,616 行）的内部结构 | E1 | 先 grep 结构再分段读 |
| 键位映射体系 | E1 | `keymap.rs`（3,203 行） |
| 斜杠命令的注册与分发 | E1 | `chatwidget/tests/slash_commands.rs` 是最快的入口 |
| diff 渲染 | E1 | `diff_model.rs`、`diff_render.rs` |
| 会话恢复选择器 | E1 | `resume_picker.rs`（6,681 行） |
| TUI 走内嵌 core 还是 app-server 的判定 | E1 | `app_server_session.rs`、`lib.rs` |
| 快照测试的具体断言方式 | E1 | 见 [`testing_guide.md`](./testing_guide.md) |

---

## 8. 相关文档

- [开发流程](./development_workflow.md) — 规范、命令与提交前自检
- [Crate 地图](./crate_map.md) — TUI 在整体中的位置
- [app-server 协议](./app_server_protocol.md) — TUI 作为客户端的那条路径
- [测试指南](./testing_guide.md) — 快照测试
- 仓库自带：[`codex-rs/tui/styles.md`](../codex-rs/tui/styles.md)（**样式事实源**）
