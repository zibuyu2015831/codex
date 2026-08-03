---
title: Codex 测试指南
summary: 描述 codex 仓库的测试拓扑与规模、nextest 配置中的重试与超时与串行化分组、core 与 app-server 两大集成测试套件的组织方式、test_codex 测试夹具、insta 快照测试，以及 AGENTS.md 对测试编写的强制约束与明确禁止项。
keywords: codex | testing | nextest | insta | integration-test | test-codex | snapshot | test-group
scope: openai/codex 仓库的测试组织、运行与编写规范
related_files: codex-rs/.config/nextest.toml | codex-rs/core/tests/common/test_codex.rs | codex-rs/core/tests/suite | codex-rs/app-server/tests/suite | justfile | AGENTS.md
dependencies: dev_docs/development_workflow.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-03
---

# 测试指南

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 测试拓扑与 nextest 配置为 E4（实测统计与读取配置）；测试夹具 API 为 E3

---

## 0. 先读这一节：三条不可违反的规则

| 规则 | 出处 |
| ---- | ---- |
| 🚫 **禁止直接跑 `cargo test`**，必须用 just 的测试任务 | `AGENTS.md:63` |
| 🚫 **禁止**为静态定义的值写测试 | `AGENTS.md:30` |
| 🚫 **禁止**为已被移除的逻辑写负向测试 | `AGENTS.md:31` |

另有一条易被忽视的：**跑完 `just fix` 或 `just fmt` 后不要重跑测试**（`AGENTS.md:72`）。

---

## 1. 测试资产规模（E4）

| 指标 | 数量 |
| ---- | ---: |
| 测试目录（全深度递归） | **39** |
| 测试目录下文件 | **631** |
| `*_tests.rs` 单元测试文件 | **457** |
| insta 快照 `.snap` | **681** |
| `core/tests/suite/` 集成测试文件 | **117** |
| `app-server/tests/suite/v2/` 文件 | **97** |

> 复核命令：
> ```bash
> git ls-files | grep -oE '(^|.*/)tests/' | sort -u | wc -l    # 39
> git ls-files | grep -E '(^|/)tests/' | wc -l                 # 631
> git ls-files "*_tests.rs" | wc -l                            # 457
> git ls-files "*.snap" | wc -l                                # 681
> ```

---

## 2. 运行测试

### 2.1 命令

| 命令 | 用途 |
| ---- | ---- |
| `just test -p <crate>` | **日常首选**，只跑单个 crate |
| `just test` | 全量。**跑前先征询用户**（`AGENTS.md:64`） |
| `just test-github-scripts` | `.github/scripts` 下的 Python 单测 |
| `just bazel-test` | Bazel 侧测试 |

底层实现（`justfile`）：

```bash
RUST_MIN_STACK=8388608 NEXTEST_PROFILE=local cargo nextest run --no-fail-fast "$@"
```

三个要点：

- **`RUST_MIN_STACK` 设为 8 MiB** —— 默认栈不够用
- **`NEXTEST_PROFILE=local`** —— 本地用 local profile，CI 用 default
- **`--no-fail-fast`** —— 全部跑完再报，不中途停

> [!TIP]
> 需要 `cargo install --locked cargo-nextest`。
> **不要用 `--all-features` 做常规运行**——会扩大构建矩阵并显著增加 `target/` 磁盘占用（`AGENTS.md:65`）。

### 2.2 耐心

> [!WARNING]
> `AGENTS.md:60`：跑 Rust 命令（`just fix` / `just test`）时**要有耐心，绝不要用 PID 杀掉它们**。Rust 的锁会让执行变慢，**这是预期行为**。

---

## 3. nextest 配置（E4，`codex-rs/.config/nextest.toml`）

### 3.1 默认 profile

```toml
[profile.default]
slow-timeout = { period = "30s", terminate-after = 2 }   # 30s × 2 = 60s 后终止
retries = 1                                              # 重试 1 次
[profile.default.junit]
path = "junit.xml"
```

**`retries = 1` 的理由写在注释里**：让单次偶发失败不至于直接判全量 CI 失败。

**`slow-timeout` 30 秒**是全仓的基准超时预算。超出这个值的测试必须显式豁免（见 §3.3）。

### 3.2 串行化分组（test-groups）

| 分组 | `max-threads` | 原因（配置文件注释要点） |
| ---- | ---: | ---- |
| `app_server_protocol_codegen` | 1 | 代码生成类测试 |
| `app_server_integration` | 1 | 每个用例都会拉起一个全新的 app-server 子进程 |
| `app_server_integration_local` | 4 | 本地放宽到 4 个子进程；全局 nextest 池仍受 CPU 数限制 |
| `core_apply_patch_cli_integration` | 1 | 跑完整 Codex turn + apply_patch，对 Windows 进程启动停顿敏感 |
| `windows_sandbox_legacy_sessions` | 1 | 创建受限令牌子进程与私有桌面，串行以免耗尽 Windows 会话/桌面资源 |
| `windows_process_heavy` | 2 | Windows 上的重进程测试 |

> **可读出的信息**：**Windows 是测试稳定性的主要痛点**——6 个分组里有 2 个是专门为 Windows 资源限制设的。app-server 集成测试的成本也很高（每用例一个子进程）。

### 3.3 超时豁免

配置里有若干 `[[profile.default.overrides]]` 给特定测试放宽超时，例如：

```toml
[[profile.default.overrides]]
# Do not add new tests here
filter = 'test(rmcp_client) | test(humanlike_typing_1000_chars_appears_live_no_placeholder)'
slow-timeout = { period = "1m", terminate-after = 4 }
```

> [!IMPORTANT]
> 注释 **"Do not add new tests here"** 是明确的约束：**不要往这个豁免列表里加新测试**。你的测试跑不进 30 秒，应该优化测试而不是申请豁免。

---

## 4. 测试类型选择（`AGENTS.md:112-124`）

```
改动智能体逻辑？
├── 是 → 必须写集成测试（core/tests/suite/ 下，用 test_codex）
│         并列出需要覆盖的主要逻辑变更与用户可见行为
└── 否 → 确需单元测试时，放进专门的 *_tests.rs 文件
```

三条附加要求：

1. **避免在主实现中留测试专用函数**（`AGENTS.md:119`）
2. **先查有没有现成 helper**（`AGENTS.md:121`）
3. **比较整个对象的相等性**，而不是逐字段比较（`AGENTS.md:29`）

---

## 5. `test_codex` 测试夹具（E3）

集成测试的核心工具，位于 `codex-rs/core/tests/common/`（crate 名 `core_test_support`，6,752 行）。

| 类型 / 函数 | 位置 |
| ---- | ---- |
| `TestCodexBuilder` | `test_codex.rs:294` |
| `TestCodex` | `test_codex.rs:815` |
| `TestCodexHarness` | `test_codex.rs:1036` |
| `TestCodexExecBuilder` | `test_codex_exec.rs:6` |
| `pub fn test_codex_exec()` | `test_codex_exec.rs:43` |

**builder 模式**：`TestCodexBuilder` → `TestCodex` → `TestCodexHarness`。另有 `test_codex_exec()` 专门用于 `codex exec` 路径。

三个测试辅助 crate（都不在 `[workspace] members` 中，通过 path 依赖纳入）：

| crate | 位置 | 行数 |
| ---- | ---- | ---: |
| `core_test_support` | `core/tests/common` | 6,752 |
| `app_test_support` | `app-server/tests/common` | 3,878 |
| `mcp_test_support` | `mcp-server/tests/common` | 507 |

---

## 6. 两大集成测试套件

### 6.1 `core/tests/suite/`（117 个文件）

按功能面组织，节选：

| 领域 | 文件 |
| ---- | ---- |
| 上下文压缩 | `compact.rs`（5,440 行）、`compact_remote.rs`、`compact_remote_parity.rs`、`compact_resume_fork.rs` |
| 审批与策略 | `approvals.rs`、`exec_policy.rs`、`catalog_permission_messages.rs`、`guardian_review.rs` |
| 执行 | `exec.rs`、`apply_patch_cli.rs`、`extension_sandbox.rs` |
| 会话 | `fork_thread.rs`、`abort_tasks.rs`、`codex_delegate.rs` |
| 智能体 | `agent_execution.rs`、`agent_websocket.rs` |
| 客户端 | `client.rs`、`client_websockets.rs`、`cli_stream.rs` |
| 规范注入 | `agents_md.rs`、`additional_context.rs`、`collaboration_instructions.rs` |
| 其他 | `auto_review.rs`、`code_mode.rs`、`external_auth.rs`、`git_enrichment.rs`、`current_time_reminder.rs` |

> `compact_remote_parity.rs` 的存在说明**本地与远程压缩之间有一致性（parity）测试**——这是理解压缩机制的好入口。

### 6.2 `app-server/tests/suite/`

顶层：`auth.rs`、`conversation_summary.rs`、`fuzzy_file_search.rs`、`logging.rs`、`strict_config.rs`、`zsh/`，以及 **`v2/`（97 个文件）**。

`v2/plugin_list.rs` 有 5,478 行，是仓库第 8 大文件。

---

## 7. insta 快照测试

全仓 **681 个 `.snap`**，主要集中在 TUI（渲染输出）与协议层（序列化结果）。

`codex-rs/core/src/session/snapshots/` 等目录存放快照。

> **未验证**（E1）：**快照更新的具体命令**。仓库 `justfile` 中没有 `insta` 相关任务，`AGENTS.md` 也未提及。标准 insta 流程是 `cargo insta review` / `INSTA_UPDATE=always`，但**本仓库禁止直接跑 cargo 测试命令**，两者如何调和需要确认。
>
> **建议**：更新快照前先在 `codex-rs/` 下搜索既有做法，或询问维护者。不要贸然用 `cargo insta` 绕过 `just test`。

---

## 8. 跨操作系统测试

`AGENTS.md:318`：

> "Tests and features must support Linux, macOS and Windows unless feature is explicitly OS-specific."

`AGENTS.md:321-322` 另外指出，app-server 与 exec-server 可以跑在**不同操作系统**上，这类配置的集成测试要看 **`$remote-tests` skill**。

> **未验证**（E1）：`$remote-tests` skill 的具体内容与调用方式。

平台专属测试的例子：`core/src/exec_policy_windows_tests.rs`、`windows-sandbox-rs` 的 `legacy_*` 测试。

---

## 9. 编写测试的检查清单

```
□ 这是智能体逻辑变更吗？→ 是则必须写集成测试（core/tests/suite/）
□ 用 test_codex / test_codex_exec 搭建实例，不要手搓
□ 先搜有没有现成 helper
□ 单元测试放进独立的 *_tests.rs，不要塞进实现文件
□ 主实现里没有留测试专用函数
□ 断言比较整个对象，而不是逐字段
□ 不是在为静态定义的值写测试
□ 不是在为已移除的逻辑写负向测试
□ 测试能在 30 秒内跑完（不要往 nextest 超时豁免列表里加）
□ Linux / macOS / Windows 都能过（除非是明确的 OS 专属特性）
□ 跑 just test -p <crate> 通过
□ 改了 common/core/protocol → 跑 just test（先问用户）
```

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| insta 快照的更新流程 | E1 | 搜 `codex-rs/` 下既有做法；询问维护者 |
| `$remote-tests` skill 的内容 | E1 | 仓库 skill 定义 |
| `TestCodexBuilder` 的完整 builder 方法 | E1 | `core/tests/common/test_codex.rs`（分段读） |
| CI 中测试的分片策略 | E1 | `.github/workflows/`（27 个 yml），见 `build_and_release.md` |
| `zsh/` 测试子目录的用途 | E1 | `app-server/tests/suite/zsh/` |
| 基准测试（bench）的组织 | E1 | `just bench`、`//codex-rs:e2e-benchmarks` |

---

## 11. 相关文档

- [开发流程](./development_workflow.md) — 完整的改完代码后动作
- [智能体核心循环](./core_agent_loop.md) — 什么算"智能体逻辑变更"
- [构建与发布](./build_and_release.md) — CI 与 Bazel 测试
- [TUI 开发指南](./tui_guide.md) — TUI 测试的组织方式
