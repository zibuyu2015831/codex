---
title: Codex CLI 开发流程与仓库硬规范
summary: 汇总 openai/codex 的贡献准入前提、just 任务清单与其真实工具前置条件、格式化与测试的强制流程、Bazel 双锁同步义务、800 行变更规模上限、模块大小规范与实测现状对照、AGENTS.md 的模型可见上下文评审规则与 app-server API 硬规则、.codex/skills 下 14 个 skill 的用途，以及提交前自检清单。
keywords: codex | development-workflow | agents-md | justfile | testing | bazel-lock | change-size | skills | app-server-api | model-visible-context
scope: openai/codex 仓库的开发、构建、测试与提交流程
related_files: AGENTS.md | justfile | docs/contributing.md | codex-rs/rust-toolchain.toml | scripts/format.py | docs/install.md | .codex/skills
dependencies: dev_docs/crate_map.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 开发流程与仓库硬规范

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **本文与 AGENTS.md 的关系**: AGENTS.md（22,519 字节）是仓库自带的 AI 代理**强制规范**，**优先级高于本文档体系**。本文只做落地说明与实测对照，**不覆盖、不改写其任何条款**。条款有出入时以 AGENTS.md 为准。

> [!IMPORTANT]
> **引用约定（本次修订变更）**：本文第一版按**行号**引用 `AGENTS.md`，事后核对发现这些行号存在系统性偏差。本次修订把全部引用改为 **小节标题 + 可 grep 的关键词**，不再给行号。
>
> `AGENTS.md` 可用的小节标题：`## The codex-core crate`、`## Code Review Rules`（含 `### Crate API surface`、`### Model visible context`、`### Breaking changes`、`### Test authoring guidance`、`### Change size guidance (800 lines)`）、`## TUI style conventions`、`## TUI code conventions`（含 `### TUI Styling (ratatui)`、`### Text wrapping`）、`## Tests`（含 `### Test module organization`、`### Snapshot tests`、`### Benchmarks`、`### Test assertions`、`### Spawning workspace binaries in tests (Cargo vs Bazel)`、`### Integration tests` → `#### codex_core integration testing`、`#### app-server integration testing`）、`## App-server API Development Best Practices`（含 `### Core Rules`、`` ### Client->server request payloads (`*Params`) ``、`### Development Workflow`）、`## Python Development Best Practices`、`## Platform Support`。
>
> `## The codex-core crate` 之前是一段没有标题的顶层条目列表，本文统称**"顶部规则列表"**。

---

## 0. 先读这一节：贡献准入前提

> [!IMPORTANT]
> **本仓库的外部代码贡献是受邀制。**
>
> `docs/contributing.md:3-17` 明文规定："External contributions are by invitation only"，且 "Pull requests that have not been explicitly invited by a member of the Codex team will be closed without review"。

> [!NOTE]
> **勘误（两轮）**：
>
> - `build_and_release.md` 第一版曾把 `.github/workflows/close-stale-contributor-prs.yml` 说成"受邀制规则的自动执行"。**并非如此**——那个工作流是每天关闭 **14 天无更新**的陈旧 PR（`DAYS_INACTIVE = 14`，`.github/workflows/close-stale-contributor-prs.yml:24-25`）。受邀制规则是**人工执行**的，没有对应的自动化。
> - 本文与 `build_and_release.md` 的上一稿又把权限过滤**写反了**，称它"跳过具有 write/maintain/admin 权限作者的 PR"。**方向恰好相反。** `:69-73` 里 `hasContributorAccess = ["admin","maintain","write"].includes(permission)`，`if (!hasContributorAccess) { ...; continue; }`——**不具备**这三种权限的才被跳过，具备的会进入 `stalePrs` 被关闭；完全不是协作者的作者会在 `:62-64` 命中 404 分支，同样跳过。换句话说，它清理的是**有写权限的自己人**留下的、且已 14 天无更新的 PR。

这条规则决定了本文的定位：

| 本文**是** | 本文**不是** |
| ---- | ---- |
| 在本仓库（或个人 fork）内做修改时的操作手册 | 向上游提 PR 的指南 |
| 理解上游为何这样约束的说明 | 对上游代码的整改建议清单 |

如果你的目标是向上游贡献，请先取得 Codex 团队成员的明确邀请。

---

## 1. 环境准备

### 1.1 工具链

| 工具 | 版本要求 | 来源 / 装法 | 谁需要它 |
| ---- | ---- | ---- | ---- |
| Rust | **1.95.0**，edition 2024 | `codex-rs/rust-toolchain.toml` | 一切 |
| Node.js | ≥ 22 | `package.json` `engines` | `pnpm run format` |
| pnpm | ≥ 10.33.0 | `package.json` `packageManager` | 同上 |
| Python | ≥ 3.10（SDK 与部分脚本） | `sdk/python/pyproject.toml:10` | `justfile` 自身（`set shell` 用 python3 跑 `scripts/just-shell.py`） |
| **just** | 任务运行器 | `cargo install --locked just` | **所有"强制"命令的前提** |
| **cargo-nextest** | 测试运行器 | `cargo install --locked cargo-nextest` | `just test` |
| **dotslash** | 拉起钉版的开发工具 | `cargo install --locked dotslash` | **`just fmt` / `just fmt-check`**（`scripts/format.py` 用它跑 `tools/buildifier` 格式化 Bazel/Starlark） |
| **uv** | Python 工程运行器 | `astral-sh/setup-uv`（CI 钉在 0.11.3）或自行安装 | **`just fmt` / `just fmt-check`**（`scripts/format.py` 用 `uv run --frozen --project …` 跑 ruff，分别作用于 `sdk/python` 与 `scripts`） |
| cargo-insta | 快照工具 | `cargo install --locked cargo-insta` | 接受 insta 快照（见 §5.5） |
| Bazel | PR 主校验路径、锁文件校验 | `MODULE.bazel` | `just bazel-*` |

```bash
just install
```

> [!WARNING]
> **`just install` 并不安装工具链**（第一版的注释"拉取工具链与依赖"有误导性）。它在 `justfile` 里的 Unix 实现只有两行：
>
> ```
> rustup show active-toolchain
> cargo fetch
> ```
>
> 也就是：**打印**当前激活的 toolchain（触发 rustup 按 `codex-rs/rust-toolchain.toml` 拉取），然后**预取 Cargo 依赖**。它不会装 `just` 本身（鸡生蛋问题）、不会装 `cargo-nextest`、`dotslash`、`uv`——而上面表格里标粗的这几项，正是"强制流程"里那几条命令（`just fmt`、`just test`）的硬前提。
>
> `[windows]` 分支多一步：若找不到 `pwsh.exe`，先用 winget 装 PowerShell 7。
>
> `docs/install.md` 给的手动清单是：rustup + `rustfmt`/`clippy` 组件 → `cargo install --locked just` → `cargo install --locked dotslash` → `cargo install --locked cargo-nextest`。**`uv` 不在这份清单里，但 just fmt 需要它**——这是文档与实际的一处缺口。

> [!TIP]
> `cargo` 可能不在默认 PATH 中，需要时先 `export PATH="$HOME/.cargo/bin:$PATH"`。

### 1.2 justfile 的一个关键特性

`justfile` 第 1 行是 `set working-directory := "codex-rs"`。**所有 just 任务默认在 `codex-rs/` 下执行**，除非该任务标注了 `[no-cd]`。这解释了为什么 `AGENTS.md` 反复强调"in the `codex-rs` directory"。

---

## 2. just 任务清单

### 2.1 日常开发

| 命令 | 作用 |
| ---- | ---- |
| `just` / `just help` | 列出全部任务 |
| `just codex <args>`（别名 `just c`） | 从源码运行 `codex` |
| `just exec <args>` | 从源码运行 `codex exec` |
| `just tui-with-exec-server` | 同时起 exec-server 与 TUI（Unix） |
| `just mcp-server-run` | 运行 MCP server |
| `just code-mode-host` | 运行 code-mode host |
| `just app-server-test-client` | 构建 CLI 并运行 app-server 测试客户端 |
| `just file-search <args>` | 运行 file-search CLI |
| `just log` | 实时查看 state SQLite 中的日志 |

### 2.2 格式化与 lint（**强制**）

| 命令 | 作用 |
| ---- | ---- |
| just fmt | 格式化 justfile / Rust / Bazel-Starlark / Python，底层是 `scripts/format.py`（**需要 dotslash + uv**） |
| `just fmt-check` | 只检查不改文件（`.github/workflows/repo-checks.yml` 在 CI 上跑的就是它） |
| `just fix -p <crate>` | `cargo clippy --fix --tests --allow-dirty`，**建议始终带 -p 限定范围** |
| `just clippy` | `cargo clippy --tests` |
| `just argument-comment-lint` | 自定义 Dylint 检查（`tools/argument-comment-lint`）——**`[unix]` 专属** |
| `just argument-comment-lint-from-source` | 同上但从源码构建 linter（`[no-cd]`，无平台限制） |

> [!NOTE]
> **CI 上另有两条本地 just 任务覆盖不到的强制检查**（详见 `build_and_release.md` §6）：
>
> - `cargo fmt -- --config imports_granularity=Item --check` —— **一行一个 import**，比默认 rustfmt 更严；`just fmt` 会带上同样配置，所以走 `just fmt` 就没问题，但直接 `cargo fmt` 会漏。
> - `cargo shear --deny-warnings` —— **未使用的依赖会挂 CI**。删代码后记得清理 `Cargo.toml`。

### 2.3 测试

| 命令 | 作用 |
| ---- | ---- |
| `just test -p <crate>` | 跑单个 crate 的测试（**日常首选**） |
| `just test` | 跑全量测试（`cargo nextest run --no-fail-fast`，`RUST_MIN_STACK=8 MiB`） |
| `just test-github-scripts` | 跑 `.github/scripts` 下的 Python 单测 |
| `just bench` / `bench-smoke` | 基准测试 |
| `just bazel-test` | Bazel 测试 |

### 2.4 Bazel 与发布

| 命令 | 作用 |
| ---- | ---- |
| `just bazel-lock-update` | **依赖变更后必跑**，刷新 `MODULE.bazel.lock` |
| `just bazel-lock-check` | 校验锁文件是否漂移（CI 同款检查） |
| `just bazel-codex <args>` | 用 Bazel 构建并运行 codex |
| `just bazel-clippy` | Bazel 侧 clippy——**`[unix]` 专属** |
| `just bazel-argument-comment-lint` | **`[unix]` 专属** |
| `just build-for-release` | `bazel build //codex-rs/cli:release_binaries`（本地校验用；**CI 的发布二进制由 Cargo 构建**，见 `build_and_release.md` §5） |

> Windows 开发机上 `bazel-clippy` / `bazel-argument-comment-lint` / `argument-comment-lint` 这三条任务**根本不存在**（`justfile` 里带 `[unix]`）。

### 2.5 代码生成（改了对应类型就必须跑）

| 命令 | 触发条件 |
| ---- | ---- |
| `just write-config-schema` | 修改了 `ConfigToml` 或其嵌套配置类型（`AGENTS.md` 顶部规则列表，grep `write-config-schema`） |
| `just write-app-server-schema` ⚠️**当前跑不通，见下方警告** | 修改了 app-server API 形状（`AGENTS.md` → `## App-server API Development Best Practices` → `### Development Workflow`；实验性 fixture 受影响时还要加 `--experimental`） |
| `just write-hooks-schema` | 修改了 hooks 相关类型 |

> **pre-merge 校验工作流**的 job 末尾挂着 `.github/actions/check-clean-worktree`——**生成物没提交，CI 就红**。
>
> 需要限定口径：`grep -lr "check-clean-worktree" .github/workflows/*.yml | wc -l` 得 **8**，即 27 个工作流里只有 8 个引用它（`bazel`、`blob-size-policy`、`cargo-deny`、`codespell`、`repo-checks`、`rust-ci`、`sdk`、`v8-canary`——正好是 `.github/workflows/blocking-ci.yml` 聚合的那批）。`.github/workflows/rust-ci-full.yml` 与全部 `rust-release*` **不查**。本文与 `build_and_release.md` 早前写的"每个 job 末尾都查"是夸大表述，已更正；详见 [`build_and_release.md`](./build_and_release.md) §4.3。

### 2.6 `.codex/skills/`：仓库自带的 14 个 skill（第一版完全未覆盖）

这些是给 Codex 自身用的可调用 skill（`$<name>` 形式），也是**理解仓库规范的一手资料**——`AGENTS.md` 有多处直接把细节甩给它们。

| skill | 用途 | 与本文档体系的关系 |
| ---- | ---- | ---- |
| **`remote-tests`** | 跨 OS（Docker Linux exec-server / Wine Windows exec-server）集成测试的完整方法 | `AGENTS.md` 的 `## Platform Support` 与两处集成测试小节都引它。**内容已整理进 `testing_guide.md` §8** |
| **`pushing-ci-changes`** | 推 `.github/**/*.yml` 改动被拒时怎么办 | **直接影响 §9 的提交清单**，见下方警告 |
| `path-types` | 为操作系统路径挑选 Rust 类型（**只用于新定义的类型**，除非被明确要求否则不改既有代码） | `remote-tests` 指向它来解决跨平台测试兼容问题 |
| `test-tui` | 交互式启动并验证 TUI 改动 | `tui_guide.md` |
| `code-review` | 编排器：用 subagent 跑其余全部 `code-review-*` skill，每个 skill 一个 subagent | — |
| `code-review-breaking-changes` | 对应 `AGENTS.md` 的 `### Breaking changes` | 见 §7 |
| `code-review-change-size` | 对应 `### Change size guidance (800 lines)` | 见 §6 |
| `code-review-context` | 对应 `### Model visible context` | 见 §4.4 |
| `code-review-testing` | 对应 `### Test authoring guidance` | `testing_guide.md` §4 |
| `babysit-pr` | PR 创建后持续轮询 review 评论、CI 状态与可合并性；重试疑似 flaky 失败最多 3 次 | — |
| `codex-pr-body` | 更新 PR 标题与正文 | — |
| `codex-bug` | 诊断 `openai/codex` 的 GitHub bug 报告 | — |
| `codex-issue-digest` | 按 feature-area 标签做 issue 摘要 | — |
| `update-v8-version` | 更新钉住的 `v8` / `rusty_v8` 版本，排查 v8-canary 失败 | `build_and_release.md` §4.4 |

> [!NOTE]
> **勘误：四个 `code-review-*` 内容 skill 与 `## Code Review Rules` 的各小节并非一一对应。**
>
> 上一稿写的"一一对应"不成立，有两处偏差：
>
> 1. **数量不等：5 个小节 vs 4 个 skill。** `## Code Review Rules` 下有 `### Crate API surface`、`### Model visible context`、`### Breaking changes`、`### Test authoring guidance`、`### Change size guidance (800 lines)` 五节，而 `.codex/skills/` 下只有四个 `code-review-*`。**`### Crate API surface` 没有对应的 skill**——跑完全部 code-review skill 也不会覆盖它。
> 2. **即便对得上的那四对，内容也未必逐字相同。** 至少 `code-review-breaking-changes` 就比 `AGENTS.md` 少一条，详见 §7。
>
> 所以准确的说法是：**四个 skill 覆盖了五个小节中的四个，且是"派生"而非"复制"。** 自查时仍应回读 `AGENTS.md` 原文。

> [!WARNING]
> **`$pushing-ci-changes`：改 CI 配置会被拒推。**
>
> 仓库禁止任何人上传 CI 配置改动，除非已被授予**临时角色**。要推 `.github/**/*.yml` 及相关文件，需要由**用户本人**走内部的 workflow 审批流程申请批准——**代理无法自行申请豁免**。
>
> skill 给的操作建议：明知会被拒也**先试着推一次**，以确认账号是否已有批准；真被拒了就把审批链接给用户，等批准同步到 GitHub 后再继续。

## 3. 强制工作流

### 3.1 改完代码后的固定动作

`AGENTS.md` 顶部规则列表末尾那三段（grep `Run \`just fmt\``、`Do not run \`cargo test\` directly`、`Before finalizing a large change`）规定的顺序：

```
1. just fmt                      # 在 codex-rs 目录下，改完代码自动执行，无需请示
2. just test -p <改动的 crate>    # 例如改了 codex-rs/tui → just test -p codex-tui
3. 若改动涉及 common / core / protocol → just test（全量）
   ⚠️ 跑全量测试前需要征询用户
4. 大改动收尾 → just fix -p <crate>
   ⚠️ 跑完 fix / fmt 后不要重跑测试
```

> [!WARNING]
> **禁止直接跑 `cargo test`**（顶部规则列表，grep `Do not run \`cargo test\` directly`），必须用 `just test`，以保证走仓库默认配置。
>
> **禁止用 PID 杀掉 Rust 命令**（顶部规则列表，grep `never try to kill them using the PID`）。Rust 的锁会让执行变慢，这是预期行为，要有耐心。
>
> **避免 `--all-features`** 做常规本地运行：它会扩大构建矩阵并显著增加 `target/` 磁盘占用。

> [!NOTE]
> **一个例外**：`AGENTS.md` 的 `### Snapshot tests` 明确允许（并要求）用 `cargo insta pending-snapshots` / `cargo insta show` / `cargo insta accept` 来审阅和接受快照——这三个子命令**不运行测试**。快照的**生成**仍然走 `just test -p <crate>`。详见 §5.5 与 `testing_guide.md` §7。

### 3.2 依赖变更的双锁义务

```
改了 Cargo.toml 或 Cargo.lock
        ↓
必须在仓库根跑 just bazel-lock-update
        ↓
把更新后的 MODULE.bazel.lock 放进同一个 change
        ↓
CI 校验锁文件漂移
```

出处：`AGENTS.md` 顶部规则列表，grep `bazel-lock-update`。

额外注意（顶部规则列表，grep `compile_data`）：新增 `include_str!`、`include_bytes!`、`sqlx::migrate!` 等**编译期文件读取**时，必须更新该 crate 的 `BUILD.bazel`（`compile_data` / `build_script_data` / test data），否则 **Cargo 通过但 Bazel 失败**。

---

## 4. 代码规范要点

### 4.1 模块与文件大小

| 规范（`AGENTS.md` 顶部规则列表，grep `Avoid large modules`） | 内容 |
| ---- | ---- |
| 目标 | Rust 模块控制在 **500 行以内**（不含测试） |
| 阈值 | 文件超过约 **800 行**时，新功能放**新模块**，不要继续扩写原文件 |
| 优先级 | 优先新增模块，而非扩大既有模块 |
| 提取时 | 把相关测试与文档一并迁移到新实现旁，让不变量贴近它所属的代码 |

**被点名的高触碰文件**（同一条目下，grep `high-touch files`）：`codex-rs/tui/src/app.rs`、`codex-rs/tui/src/bottom_pane/chat_composer.rs`、`codex-rs/tui/src/bottom_pane/footer.rs`、`codex-rs/tui/src/chatwidget.rs`、`codex-rs/tui/src/bottom_pane/mod.rs`。

其中 chatwidget.rs 有额外约束：**除非改动很小，否则不要给它加新的独立方法**，应新建模块，保持它专注于编排。

### 4.2 规范与实测现状对照

> [!IMPORTANT]
> 下面的实测数据是为了**避免误判**而列出的，**不是对上游的整改建议**。规范中的 500/800 行目标约束的是**新增代码**，措辞是"add new functionality in a new module instead of extending the existing file"，与存量文件并不矛盾。

| 文件 | 规范目标 | 实测行数（含测试） |
| ---- | ---: | ---: |
| `codex-rs/tui/src/bottom_pane/chat_composer.rs` | < 800 | **12,616** |
| `codex-rs/core/src/config/config_tests.rs` | 不适用（纯测试） | 12,127 |
| `codex-rs/core/src/session/tests.rs` | 不适用（纯测试） | 11,434 |
| `codex-rs/tui/src/app/tests.rs` | 不适用（纯测试） | 7,520 |
| `codex-rs/tui/src/resume_picker.rs` | < 800 | 6,681 |
| `codex-rs/core-plugins/src/manager_tests.rs` | 不适用（纯测试） | 6,558 |
| `codex-rs/protocol/src/protocol.rs` | < 800 | 6,349 |
| `codex-rs/app-server/src/request_processors/thread_processor.rs` | < 800 | 5,442 |

**正确的理解方式**：这些是历史遗留的高触碰文件。**新代码不得继续堆入**——这正是规范的原意。读取它们时必须分段（先 grep `^pub fn` / `^impl` / `^pub struct` 拿结构，再定点读取）。

### 4.3 其他硬性条款

出处一律为 `AGENTS.md` **顶部规则列表**（除末行外），给出 grep 关键词：

| 条款 | grep 关键词 |
| ---- | ---- |
| 🚫 **禁止**新增或修改 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` / `CODEX_SANDBOX_ENV_VAR` 相关代码 | `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` |
| 🚫 **禁止**向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | `general product or user-facing documentation` |
| 优先私有模块 + 显式导出的 crate 公共 API | `Prefer private modules` |
| 不要创建只被引用一次的小助手方法 | `referenced only once` |
| trait 中的异步方法用 `fn foo(&self, ...) -> impl Future<Output = T> + Send`，**不要**用 `#[allow(async_fn_in_trait)]` 绕过 | `async_fn_in_trait` |
| 追踪异步任务用 `#[tracing::instrument(...)]` 标注定义处，**不要**在调用点 `.instrument(...)`；加之前先查是否已被标注 | `tracing::instrument` |
| MCP 工具调用优先走 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` | `mcp_connection_manager` |
| 不要无必要地调用 `reset_client_session` | `reset_client_session` |
| 尽量让 `match` 穷尽，避免通配分支 | `avoid wildcard arms` |
| 新增 trait 要写文档注释，说明其角色与实现方的预期用法 | `Newly added traits should include doc comments` |
| 位置传参的不透明字面量（`None`/bool/数字）要加精确的 `/*param_name*/` 注释 | `argument_comment_lint` |
| TUI 样式约定见 `codex-rs/tui/styles.md` | `## TUI style conventions` 一节 |

### 4.4 `### Model visible context`：模型可见上下文的评审规则（第一版未覆盖）

`AGENTS.md` → `## Code Review Rules` → `### Model visible context`（同时也是 `$code-review-context` skill 的全文）。Codex 维护一份发给模型的消息历史，**对它的任何改动都受这 6 条约束**：

1. **不得重写历史**——上下文只能增量构建
2. **避免频繁改动上下文**，那会导致 prompt 缓存失效
3. **不得有无界项**——凡注入模型上下文的东西都必须有**有界的大小和硬上限**
4. **单项不得超过 10K token**
5. 新增的**可能超过 1k token 的单项要标记为 P0**，需要额外的人工评审
6. **所有注入的片段都必须定义在 `core/context` 里的 struct 中，并实现 `ContextualUserFragment` trait**

> 第 6 条是可机检的结构性约束：找注入点就去 `core/context` 看 `ContextualUserFragment` 的实现方。

### 4.5 `## App-server API Development Best Practices`（第一版只捕获了 1 条）

第一版的 §4.3 只记了 `#[ts(export_to = "v2/")]` 一条。实际上 `AGENTS.md` 有整整一节（约 47 行）的硬规则，适用范围是 `codex-rs/app-server-protocol/src/protocol/common.rs`、`app-server-protocol/src/protocol/v2.rs`、`codex-rs/app-server/README.md`。

**`### Core Rules`：**

| 规则 | 要点 |
| ---- | ---- |
| **只在 v2 开发** | 所有活跃 API 开发都在 app-server v2，**不要给 v1 加新的 API 面** |
| 命名 | `*Params`（请求）/ `*Response`（响应）/ `*Notification`（通知） |
| RPC 方法名 | `<resource>/<method>`，**resource 用单数**（如 `thread/read`、`app/list`） |
| 线上字段 | 一律 camelCase，用 `#[serde(rename_all = "camelCase")]`；**例外**：config 类 RPC 载荷用 snake_case 以对齐 `config.toml` 的键 |
| 字符串枚举值 | 同样 camelCase，serde 与 TS 的 `rename_all` 要一致 |
| **v2 类型** | 必须 `#[ts(export_to = "v2/")]`，生成的 TS 才会落到正确的命名空间 |
| **禁止 `skip_serializing_if = "Option::is_none"`** | v2 API 载荷字段一律不许用。唯一例外：故意无参的 client→server 请求可写 `params: #[ts(type = "undefined")] #[serde(skip_serializing_if = "Option::is_none")] Option<()>` |
| Rust / TS 重命名保持对齐 | 有 `#[serde(rename = "...")]` 就要有对应的 `#[ts(rename = "...")]` |
| 判别联合 | 两个序列化器都要显式打标：`#[serde(tag = "type", ...)]` + `#[ts(tag = "type", ...)]` |
| ID | API 边界上用朴素 `String`，UUID 解析放在内部 |
| 时间戳 | 整数 Unix 秒（`i64`），命名 `*_at`（`created_at` / `updated_at` / `resets_at`） |
| 实验性面 | `#[experimental("method/or/field")]`；需要字段级 gating 时 derive `ExperimentalApi`；只有部分字段实验性时在 `common.rs` 用 `inspect_params: true` |

**`### Client->server request payloads (*Params)`：**

- 每个可选字段**必须**标 #[ts(optional = nullable)]；**这个标注不得用在 *Params 之外的地方**
- 可选集合字段（`Vec`、`HashMap` 等）**必须**用 `Option<...>` + `#[ts(optional = nullable)]`；**不要**用 `#[serde(default)]` 来表达可选集合
- 布尔字段若希望"省略即 false"，用 `#[serde(default, skip_serializing_if = "std::ops::Not::not")] pub field: bool`，**不要**用 `Option<bool>`
- 新的 list 方法**默认要实现游标分页**：请求侧 `cursor: Option<String>` + `limit: Option<u32>`，响应侧 `data: Vec<...>` + `next_cursor: Option<String>`

**`### Development Workflow`：**

- API 行为变了就更新 app-server 的文档/示例（**至少** `codex-rs/app-server/README.md`）
- API 形状变了就跑 `just write-app-server-schema`（实验性 fixture 受影响时加 `--experimental`）
- 用 `just test -p codex-app-server-protocol` 验证
- **避免只断言实验性字段标记的样板测试**，靠 schema 生成/测试与行为覆盖即可

---

## 5. 测试规范

### 5.1 测试类型选择

`AGENTS.md` → `### Test authoring guidance`：

- **智能体逻辑变更优先写集成测试**，位于 `core/suite` 下，用 `test_codex` 搭建测试实例
- **改变智能体逻辑的功能必须补集成测试**，并列出需要覆盖的主要逻辑变更与用户可见行为
- 确需单元测试时，放进**专门的 `*_tests.rs` 文件**
- **避免在主实现中留测试专用函数**
- 先查有没有现成 helper

### 5.2 明确禁止的测试

| 禁止项 | 出处（顶部规则列表 grep 关键词） |
| ---- | ---- |
| 为**静态定义的值**写测试 | `statically defined` |
| 为**已被移除的逻辑**写负向测试 | `negative tests for logic that was removed` |

### 5.3 断言风格

- 比较**整个对象的相等性**，而不是逐字段比较（顶部规则列表，grep `entire objects`）
- `### Test assertions`：**必须用 `pretty_assertions::assert_eq`**；**不要在测试里修改进程环境变量**

### 5.4 测试模块组织（`### Test module organization`）

新增测试模块时用独立同级文件 + 显式 `#[path]`：

```rust
#[cfg(test)]
#[path = "parser_tests.rs"]
mod tests;
```

> **只适用于新增模块**——原文明确说不要为了符合这个约定而搬动/重写既有的内联 `#[cfg(test)] mod tests { ... }`。

### 5.5 快照测试是硬性要求（`### Snapshot tests`，第一版未覆盖）

> [!IMPORTANT]
> **任何影响用户可见 UI（含新增 UI）的改动，必须包含相应的 `insta` 快照覆盖**——没有就新增快照测试，有就更新既有快照，并把 accept 结果作为 PR 的一部分提交，以便 UI 影响可评审、后续 diff 保持可视化。
>
> 流程：`just test -p codex-tui`（生成）→ `cargo insta pending-snapshots -p codex-tui`（查看待处理）→ 读 `*.snap.new` 或 `cargo insta show -p codex-tui <file>`（审阅）→ 确认要接受本 crate 全部新快照后才 `cargo insta accept -p codex-tui`。
>
> 详见 [`testing_guide.md`](./testing_guide.md) §7。

### 5.6 Bazel 兼容的测试写法（`### Spawning workspace binaries in tests`）

- 拉一方二进制用 codex_utils_cargo_bin::cargo_bin("...")，**不要**用 `assert_cmd::Command::cargo_bin` 或 escargot
- 找 fixture / 资源用 `codex_utils_cargo_bin::find_resource!`，**不要**用 `env!("CARGO_MANIFEST_DIR")`

这不是风格问题：Bazel 下二进制与资源位于 runfiles，写死 Cargo 假设会在 Bazel 侧失败。

### 5.7 测试资产规模（E1：文件计数）

| 指标 | 数量 |
| ---- | ---: |
| 测试目录（全深度） | 39 |
| 测试目录下文件 | 631 |
| `*_tests.rs` 文件 | 457 |
| insta 快照 `.snap` | 681 |

> 证据等级由第一版的 E4 下调为 **E1**——这些只是文件计数，不是构建/测试的实际运行结果。
>
> 详细的测试拓扑、快照流程、`test_codex` 用法、`$remote-tests` 与 CI 分片见 [`testing_guide.md`](./testing_guide.md)。

---

## 6. 变更规模上限

`AGENTS.md` → `### Change size guidance (800 lines)`（也是 `$code-review-change-size` skill 的全文）：

| 变更类型 | 行数上限 |
| ---- | ---: |
| 一般变更（非机械性） | **800 行** |
| 复杂逻辑变更 | **500 行** |
| 机械性变更 | 不受此限 |

超限时的要求：**拆分成可评审的阶段**，并**基于实际 diff、依赖关系与受影响调用点**给出拆分建议，找出最小的可独立落地的一段。

---

## 7. 需要格外谨慎的改动面

`AGENTS.md` → `### Breaking changes` 列出的外部集成面（改动前请确认已理解影响），共 **5** 项：

- app-server API
- 原始响应项事件（`rawResponseItem/*`），**即便仍是实验性的**
- CLI 参数
- 配置加载
- 从既有 rollout 恢复会话

> [!WARNING]
> **勘误：`$code-review-breaking-changes` skill 不是这一节的"全文"，它少一条。**
>
> `.codex/skills/code-review-breaking-changes/SKILL.md` 正文只列了 **4** 项——**独独漏掉了「原始响应项事件（`rawResponseItem/*`）」**。它另有一句 `AGENTS.md` 里没有的收尾：*"Do not stop after finding one issue; analyze all possible ways breaking changes can happen."*
>
> 实际后果：**只跑 `$code-review-breaking-changes` 做自查，`rawResponseItem/*` 的破坏性变更不会被提醒。** 涉及原始响应项事件时，请以 `AGENTS.md` 的 `### Breaking changes` 一节为准（grep `rawResponseItem`）。
>
> 更一般的教训：**"skill 是 AGENTS.md 某节的机器化投放"是个好用的近似，但不能假设两者逐字一致**——本文档体系此前多处基于这个假设写作，需要逐条核对。

---

## 8. 本地开发环境（本文档体系相关）

> 本节记录的是**本文档体系自身**的工作方式，不属于上游仓库规范。

| 项 | 约定 |
| ---- | ---- |
| 产物路径 | 仓库根 `dev_docs/`，**禁止迁入 `docs/`**（`AGENTS.md` 顶部规则列表，grep `general product or user-facing documentation`） |
| 版本控制 | 已纳入版本管理 |
| push 目标 | **只推个人 fork**，禁止 `git push origin`（`origin` 直连上游 `openai/codex`） |
| 框架目录 | `AI-Coding-Context` 为指向仓库外部的软链接，已写入 `.git/info/exclude`，不提交 |
| 脱敏 | fork 为公开仓库，提交前必须跑脱敏扫描，见 `dev_docs/_analysis/generation_plan.md`「代码脱敏规范」 |

---

## 9. 提交前自检清单

```
□ just fmt                                   已跑（改完代码即跑，无需请示；需 dotslash + uv）
□ just test -p <改动的 crate>                 通过
□ 改了 common/core/protocol → just test       通过（跑前先问用户）
□ 大改动 → just fix -p <crate>                已跑（跑完不要重跑测试）
□ 改了 Cargo.toml/lock → just bazel-lock-update 已跑，锁文件已入同一 change
□ 删了代码 → 没留下未使用依赖（CI 的 cargo shear --deny-warnings 会挂）
□ 改了 ConfigToml → just write-config-schema   已跑
□ 改了 app-server API 形状 → 重新生成 schema 已跑（⚠️ `just write-app-server-schema` 当前失败，改用 `python3 codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`）
   ├ 只动 v2，没给 v1 加新 API 面
   ├ v2 类型已标注 #[ts(export_to = "v2/")]
   ├ 可选字段已标 #[ts(optional = nullable)]，且没用 skip_serializing_if
   ├ 新 list 方法带了 cursor/limit + data/next_cursor 分页
   └ app-server/README.md 已同步；just test -p codex-app-server-protocol 通过
□ 改了用户可见 UI → insta 快照覆盖已新增/更新并 accept
□ 动了模型可见上下文 → 无历史重写、有硬上限、单项 ≤10K token、
   片段定义在 core/context 且实现 ContextualUserFragment；>1k token 的新项已标 P0
□ 新增 include_str!/sqlx::migrate! → BUILD.bazel 的 compile_data 已补
□ 新增测试模块用了独立 *_tests.rs + #[path]（既有内联 mod tests 不迁移）
□ 测试里没改进程环境变量；断言用 pretty_assertions::assert_eq
□ 改了根 README → asciicheck / readme_toc 能过
□ 所有生成物已提交（pre-merge 校验工作流的 job 末尾会查工作区是否干净，见 §2.5）
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500），否则已给出拆分方案
□ 未触碰 CODEX_SANDBOX_* 相关代码
□ 未向 docs/ 添加通用文档
□ 新代码未无谓地堆进 codex-core（见 crate_map.md §6）
□ codex-tui 没有直接 import codex-core（repo-checks 会机检）
□ 若改动了 .github/**/*.yml → 已知会被拒推，需用户走 workflow 审批（见 §2.6）
```

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| ~~CI 工作流的具体内容~~ | — | **已完成**，见 `build_and_release.md` §4 |
| ~~发布流程与产物矩阵~~ | — | **已完成**，见 `build_and_release.md` §5 |
| ~~`test_codex` 用法与 insta 快照更新~~ | — | **已完成**，见 `testing_guide.md` §5、§7 |
| ~~`$remote-tests` skill（跨 OS 集成测试）~~ | — | **已完成**，见 `testing_guide.md` §8 |
| Bazel 构建规则细节与 `BUILD.bazel` 写法 | E1 | 各 crate 的 `BUILD.bazel`、`bazel/rules/` |
| `scripts/format.py` 的实现细节 | E1 | 该脚本 |
| `## TUI style conventions` / `## TUI code conventions` / `### Text wrapping` 的逐条内容 | E1 | `AGENTS.md` 对应小节、`codex-rs/tui/styles.md`、`tui_guide.md` |
| `## The codex-core crate` 一节的内容 | E1 | `AGENTS.md` 该小节、`crate_map.md` |
| `.codex/skills/` 中 `babysit-pr` / `codex-bug` / `codex-issue-digest` / `update-v8-version` 的详细流程 | E1 | 对应 `SKILL.md` |

---

## 11. 相关文档

- [Crate 地图](./crate_map.md) — 新代码该放哪个 crate
- [架构总览](./architecture_overview.md) — 双构建系统与进程边界
- [构建与发布](./build_and_release.md) — CI 编排、repo-checks 硬规则、lint 流水线、发布链路
- [测试指南](./testing_guide.md) — nextest 配置、快照流程、`$remote-tests`、CI 分片
- [AI 编码上下文主文档](./AI_Coding_Context.md) — 场景导航入口
- 仓库自带：[AGENTS.md](../AGENTS.md)（**强制规范，优先级最高**）、[`docs/contributing.md`](../docs/contributing.md)、[`justfile`](../justfile)、[`docs/install.md`](../docs/install.md)、`.codex/skills/`
