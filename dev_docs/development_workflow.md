---
title: Codex CLI 开发流程与仓库硬规范
summary: 汇总 openai/codex 的贡献准入前提、just 任务清单、格式化与测试的强制流程、Bazel 双锁同步义务、800 行变更规模上限、模块大小规范与实测现状对照，以及提交前自检清单。
keywords: codex | development-workflow | agents-md | justfile | testing | bazel-lock | change-size
scope: openai/codex 仓库的开发、构建、测试与提交流程
related_files: AGENTS.md | justfile | docs/contributing.md | codex-rs/rust-toolchain.toml | scripts/format.py
dependencies: dev_docs/crate_map.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 开发流程与仓库硬规范

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **本文与 AGENTS.md 的关系**: AGENTS.md（22,519 字节）是仓库自带的 AI 代理**强制规范**，**优先级高于本文档体系**。本文只做落地说明与实测对照，**不覆盖、不改写其任何条款**。条款有出入时以 AGENTS.md 为准。

---

## 0. 先读这一节：贡献准入前提

> [!IMPORTANT]
> **本仓库的外部代码贡献是受邀制。**
>
> `docs/contributing.md:3-17` 明文规定："External contributions are by invitation only"，且 "Pull requests that have not been explicitly invited by a member of the Codex team will be closed without review"。

这条规则决定了本文的定位：

| 本文**是** | 本文**不是** |
| ---- | ---- |
| 在本仓库（或个人 fork）内做修改时的操作手册 | 向上游提 PR 的指南 |
| 理解上游为何这样约束的说明 | 对上游代码的整改建议清单 |

如果你的目标是向上游贡献，请先取得 Codex 团队成员的明确邀请。

---

## 1. 环境准备

### 1.1 工具链

| 工具 | 版本要求 | 来源 |
| ---- | ---- | ---- |
| Rust | **1.95.0**，edition 2024 | `codex-rs/rust-toolchain.toml` |
| Node.js | ≥ 22 | `package.json` `engines` |
| pnpm | ≥ 10.33.0 | `package.json` `packageManager` |
| Python | ≥ 3.10（SDK 与部分脚本） | `sdk/python/pyproject.toml:10` |
| just | 任务运行器 | `justfile`（203 行） |
| cargo-nextest | 测试运行器 | `just test` 依赖，`cargo install --locked cargo-nextest` |
| Bazel | 发布构建与锁文件校验 | `MODULE.bazel` |

```bash
# 初始化（拉取工具链与依赖）
just install
```

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
| `just fmt` | 格式化 justfile / Rust / Bazel-Starlark / Python，底层是 `scripts/format.py` |
| `just fmt-check` | 只检查不改文件 |
| `just fix -p <crate>` | `cargo clippy --fix --tests --allow-dirty`，**建议始终带 -p 限定范围** |
| `just clippy` | `cargo clippy --tests` |
| `just argument-comment-lint` | 自定义 Dylint 检查（`tools/argument-comment-lint`） |

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
| `just bazel-clippy` | Bazel 侧 clippy |
| `just build-for-release` | 构建发布二进制 |

### 2.5 代码生成（改了对应类型就必须跑）

| 命令 | 触发条件 |
| ---- | ---- |
| `just write-config-schema` | 修改了 `ConfigToml` 或其嵌套配置类型（`AGENTS.md:35`） |
| `just write-app-server-schema` | 修改了 app-server API 形状（`AGENTS.md:300-304`） |
| `just write-hooks-schema` | 修改了 hooks 相关类型 |

---

## 3. 强制工作流

### 3.1 改完代码后的固定动作

`AGENTS.md:62-70` 规定的顺序：

```
1. just fmt                      # 在 codex-rs 目录下，改完代码自动执行，无需请示
2. just test -p <改动的 crate>    # 例如改了 codex-rs/tui → just test -p codex-tui
3. 若改动涉及 common / core / protocol → just test（全量）
   ⚠️ 跑全量测试前需要征询用户
4. 大改动收尾 → just fix -p <crate>
   ⚠️ 跑完 fix / fmt 后不要重跑测试
```

> [!WARNING]
> **禁止直接跑 `cargo test`**（`AGENTS.md:63`），必须用 `just test`，以保证走仓库默认配置。
>
> **禁止用 PID 杀掉 Rust 命令**（`AGENTS.md:60`）。Rust 的锁会让执行变慢，这是预期行为，要有耐心。
>
> **避免 `--all-features`** 做常规本地运行：它会扩大构建矩阵并显著增加 `target/` 磁盘占用。

### 3.2 依赖变更的双锁义务

```
改了 Cargo.toml 或 Cargo.lock
        ↓
必须在仓库根跑 just bazel-lock-update
        ↓
把更新后的 MODULE.bazel.lock 放进同一个 change
        ↓
CI 校验锁文件漂移（AGENTS.md:37-39）
```

额外注意（`AGENTS.md:40-43`）：新增 `include_str!`、`include_bytes!`、`sqlx::migrate!` 等**编译期文件读取**时，必须更新该 crate 的 `BUILD.bazel`（`compile_data` / `build_script_data` / test data），否则 **Cargo 通过但 Bazel 失败**。

---

## 4. 代码规范要点

### 4.1 模块与文件大小

| 规范（`AGENTS.md:49-61`） | 内容 |
| ---- | ---- |
| 目标 | Rust 模块控制在 **500 行以内**（不含测试） |
| 阈值 | 文件超过约 **800 行**时，新功能放**新模块**，不要继续扩写原文件 |
| 优先级 | 优先新增模块，而非扩大既有模块 |
| 提取时 | 把相关测试与文档一并迁移到新实现旁，让不变量贴近它所属的代码 |

**被点名的高触碰文件**（`AGENTS.md:54-57`）：`codex-rs/tui/src/app.rs`、`codex-rs/tui/src/bottom_pane/chat_composer.rs`、`codex-rs/tui/src/bottom_pane/footer.rs`、`codex-rs/tui/src/chatwidget.rs`、`codex-rs/tui/src/bottom_pane/mod.rs`。

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

| 条款 | 出处 |
| ---- | ---- |
| 🚫 **禁止**新增或修改 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` / `CODEX_SANDBOX_ENV_VAR` 相关代码 | `AGENTS.md:8-10` |
| 🚫 **禁止**向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | `AGENTS.md:32` |
| 优先私有模块 + 显式导出的 crate 公共 API | `AGENTS.md:33` |
| 不要创建只被引用一次的小助手方法 | `AGENTS.md:44` |
| trait 中的异步方法用 `fn foo(&self, ...) -> impl Future<Output = T> + Send`，**不要**用 `#[allow(async_fn_in_trait)]` 绕过 | `AGENTS.md:25-28` |
| 追踪异步任务用 `#[tracing::instrument(...)]` 标注定义处，**不要**在调用点 `.instrument(...)`；加之前先查是否已被标注 | `AGENTS.md:45-48` |
| MCP 工具调用优先走 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` | `AGENTS.md:36` |
| 不要无必要地调用 `reset_client_session` | `AGENTS.md:37` |
| TUI 样式约定见 `codex-rs/tui/styles.md` | `AGENTS.md:135` |

---

## 5. 测试规范

### 5.1 测试类型选择

`AGENTS.md:112-124`：

- **智能体逻辑变更优先写集成测试**，位于 `core/suite` 下，用 `test_codex` 搭建测试实例
- **改变智能体逻辑的功能必须补集成测试**，并列出需要覆盖的主要逻辑变更与用户可见行为
- 确需单元测试时，放进**专门的 `*_tests.rs` 文件**
- **避免在主实现中留测试专用函数**
- 先查有没有现成 helper

### 5.2 明确禁止的测试

| 禁止项 | 出处 |
| ---- | ---- |
| 为**静态定义的值**写测试 | `AGENTS.md:30` |
| 为**已被移除的逻辑**写负向测试 | `AGENTS.md:31` |

### 5.3 断言风格

比较**整个对象的相等性**，而不是逐字段比较（`AGENTS.md:29`）。

### 5.4 测试资产规模（E4 实测）

| 指标 | 数量 |
| ---- | ---: |
| 测试目录（全深度） | 39 |
| 测试目录下文件 | 631 |
| `*_tests.rs` 文件 | 457 |
| insta 快照 `.snap` | 681 |

> 详细的测试拓扑、快照更新流程与 `test_codex` 用法待第 3 批 [`testing_guide.md`](./testing_guide.md)。

---

## 6. 变更规模上限

`AGENTS.md:125-131`：

| 变更类型 | 行数上限 |
| ---- | ---: |
| 一般变更（非机械性） | **800 行** |
| 复杂逻辑变更 | **500 行** |
| 机械性变更 | 不受此限 |

超限时的要求：**拆分成可评审的阶段**，并**基于实际 diff、依赖关系与受影响调用点**给出拆分建议，找出最小的可独立落地的一段。

---

## 7. 需要格外谨慎的改动面

`AGENTS.md:105-110` 列出的高风险面（改动前请确认已理解影响）：

- app-server API
- 原始响应项事件（`rawResponseItem/*`），**即便仍是实验性的**
- CLI 参数
- 配置加载
- 从既有 rollout 恢复会话

---

## 8. 本地开发环境（本文档体系相关）

> 本节记录的是**本文档体系自身**的工作方式，不属于上游仓库规范。

| 项 | 约定 |
| ---- | ---- |
| 产物路径 | 仓库根 `dev_docs/`，**禁止迁入 `docs/`**（`AGENTS.md:32`） |
| 版本控制 | 已纳入版本管理 |
| push 目标 | **只推个人 fork**，禁止 `git push origin`（`origin` 直连上游 `openai/codex`） |
| 框架目录 | `AI-Coding-Context` 为指向仓库外部的软链接，已写入 `.git/info/exclude`，不提交 |
| 脱敏 | fork 为公开仓库，提交前必须跑脱敏扫描，见 `dev_docs/_analysis/generation_plan.md`「代码脱敏规范」 |

---

## 9. 提交前自检清单

```
□ just fmt                                   已跑（改完代码即跑，无需请示）
□ just test -p <改动的 crate>                 通过
□ 改了 common/core/protocol → just test       通过（跑前先问用户）
□ 大改动 → just fix -p <crate>                已跑（跑完不要重跑测试）
□ 改了 Cargo.toml/lock → just bazel-lock-update 已跑，锁文件已入同一 change
□ 改了 ConfigToml → just write-config-schema   已跑
□ 改了 app-server API 形状 → just write-app-server-schema 已跑
   └ v2 类型已标注 #[ts(export_to = "v2/")]
□ 新增 include_str!/sqlx::migrate! → BUILD.bazel 的 compile_data 已补
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500），否则已给出拆分方案
□ 未触碰 CODEX_SANDBOX_* 相关代码
□ 未向 docs/ 添加通用文档
□ 新代码未无谓地堆进 codex-core（见 crate_map.md §6）
```

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 何时补齐 |
| ---- | ---- |
| ~~CI 工作流的具体内容~~ | **已完成**，见 `build_and_release.md` |
| Bazel 构建规则细节与 `BUILD.bazel` 写法 | 第 3 批 `build_and_release.md` |
| 发布流程与产物矩阵 | 第 3 批 `build_and_release.md` |
| `test_codex` 的用法与 insta 快照更新 | 第 3 批 `testing_guide.md` |
| `scripts/format.py` 的实现细节 | 暂无计划 |
| `$remote-tests` skill（跨 OS 集成测试） | 第 3 批 `testing_guide.md` |

---

## 11. 相关文档

- [Crate 地图](./crate_map.md) — 新代码该放哪个 crate
- [架构总览](./architecture_overview.md) — 双构建系统与进程边界
- [AI 编码上下文主文档](./AI_Coding_Context.md) — 场景导航入口
- 仓库自带：[AGENTS.md](../AGENTS.md)（**强制规范，优先级最高**）、[`docs/contributing.md`](../docs/contributing.md)、[`justfile`](../justfile)
