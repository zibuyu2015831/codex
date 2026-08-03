---
title: Codex 测试指南
summary: 描述 codex 仓库的测试拓扑与规模、nextest 配置中的重试与超时与串行化分组、core 与 app-server 两大集成测试套件的组织方式、test_codex 测试夹具、insta 快照工作流（AGENTS.md 已明文规定且要求 UI 变更必须带快照覆盖）、$remote-tests skill 描述的跨 OS 远程执行器测试，以及 CI 的 nextest archive 分片策略与 AGENTS.md 的测试编写强制约束。
keywords: codex | testing | nextest | insta | integration-test | test-codex | snapshot | test-group | remote-tests | nextest-archive
scope: openai/codex 仓库的测试组织、运行与编写规范
related_files: codex-rs/.config/nextest.toml | codex-rs/core/tests/common/test_codex.rs | codex-rs/core/tests/suite | codex-rs/app-server/tests/suite | justfile | AGENTS.md | .codex/skills/remote-tests/SKILL.md | .github/workflows/rust-ci-full-nextest-platform.yml
dependencies: dev_docs/development_workflow.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-03
---

# 测试指南

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: nextest 配置、AGENTS.md 条款、CI 工作流内容为 E2/E3（读取配置与源码）；文件计数为 E1；测试夹具 API 为 E3

> [!NOTE]
> **第一版勘误（本次修订）**：初版称"`AGENTS.md` 未提及 insta 快照更新流程"，并据此建议"不要贸然用 `cargo insta`"。**这是本文档的调研失误——`AGENTS.md` 有完整的 `### Snapshot tests` 一节**，明确规定了流程，还规定 UI 变更**必须**带快照覆盖。相关内容已按原文重写（见 §7），不再作为"未覆盖项"。
>
> 同期纠正的还有：`$remote-tests` 的内容（仓库内有 skill 定义，见 §8）、CI 分片策略（见 §10）、`core/tests/suite/` 文件数、nextest 配置的若干细节。

---

## 0. 先读这一节：三条不可违反的规则

| 规则 | 出处（`AGENTS.md`，按小节标题定位） |
| ---- | ---- |
| 🚫 **禁止直接跑 `cargo test`**，必须用 just 的测试任务 | 顶部规则列表，grep `Do not run \`cargo test\` directly` |
| 🚫 **禁止**为静态定义的值写测试 | 顶部规则列表，grep `statically defined` |
| 🚫 **禁止**为已被移除的逻辑写负向测试 | 顶部规则列表，grep `negative tests for logic that was removed` |

另有一条易被忽视的：**跑完 `just fix` 或 `just fmt` 后不要重跑测试**（顶部规则列表，grep `Do not re-run tests after running`）。

> 本文引用 `AGENTS.md` 一律给**小节标题 + 可 grep 的关键词**，不给行号——行号会随上游改动漂移（第一版正是因为按行号引用而出现了系统性偏差）。第 72 行 `## The codex-core crate` 之前的内容没有小标题，统称"顶部规则列表"。

---

## 1. 测试资产规模（E1：文件计数）

| 指标 | 数量 |
| ---- | ---: |
| 测试目录（全深度递归） | **39** |
| 测试目录下文件 | **631** |
| `*_tests.rs` 单元测试文件 | **457** |
| insta 快照 `.snap` | **681** |
| `core/tests/suite/` 集成测试 `.rs` 文件 | **116** |
| `app-server/tests/suite/v2/` 文件 | **97** |

> 复核命令：
> ```bash
> git ls-files | grep -oE '(^|.*/)tests/' | sort -u | wc -l    # 39
> git ls-files | grep -E '(^|/)tests/' | wc -l                 # 631
> git ls-files "*_tests.rs" | wc -l                            # 457
> git ls-files "*.snap" | wc -l                                # 681
> git ls-files "codex-rs/core/tests/suite/*.rs" | wc -l        # 116
> ```

> [!NOTE]
> 两处修订：
> 1. 证据等级从 E4 降为 **E1**——这些只是文件计数，不是构建/测试/lint 的实际运行结果。
> 2. `core/tests/suite/` 是 **116**，不是 117。第一版用 `ls` 统计，把子目录 `snapshots/` 也数进去了；`git ls-files "…/*.rs"` 的结果是 116。

---

## 2. 运行测试

### 2.1 命令

| 命令 | 用途 |
| ---- | ---- |
| `just test -p <crate>` | **日常首选**，只跑单个 crate |
| `just test` | 全量。**跑前先征询用户**（`AGENTS.md` 顶部规则列表，grep `do ask the user before running the complete test suite`） |
| `just test -p <crate> --test all` | 只跑该 crate 的集成测试 target（`$remote-tests` skill 里的标准形式，见 §8） |
| `just test-github-scripts` | `.github/scripts` 下的 Python 单测 |
| `just bazel-test` | Bazel 侧测试。**PR 上的 Rust 测试信号来自 Bazel，不是 `rust-ci.yml`**（见 §10） |

底层实现（`justfile`）：

```bash
RUST_MIN_STACK=8388608 NEXTEST_PROFILE=local cargo nextest run --no-fail-fast "$@"
```

三个要点：

- **`RUST_MIN_STACK` 设为 8 MiB** —— 默认栈不够用
- **`NEXTEST_PROFILE=local`** —— 本地用 local profile，CI 用 default（CI 侧已证实：JUnit 落在 `target/nextest/default/junit.xml`，见 §10）
- **`--no-fail-fast`** —— 全部跑完再报，不中途停

> [!TIP]
> 需要 `cargo install --locked cargo-nextest`。
> **不要用 `--all-features` 做常规运行**——会扩大构建矩阵并显著增加 `target/` 磁盘占用（`AGENTS.md` 顶部规则列表，grep `Avoid \`--all-features\` for routine local runs`）。

### 2.2 耐心

> [!WARNING]
> `AGENTS.md` 顶部规则列表（grep `never try to kill them using the PID`）：跑 Rust 命令（`just fix` / `just test`）时**要有耐心，绝不要用 PID 杀掉它们**。Rust 的锁会让执行变慢，**这是预期行为**。

---

## 3. nextest 配置（E2，`codex-rs/.config/nextest.toml`）

### 3.1 默认 profile

```toml
[profile.default]
slow-timeout = { period = "30s", terminate-after = 2 }   # 30s × 2 = 60s 后终止
retries = 1                                              # 重试 1 次
[profile.default.junit]
path = "junit.xml"

[profile.local]
inherits = "default"
```

**`retries = 1` 的理由写在注释里**：让单次偶发失败不至于直接判全量 CI 失败。

**`slow-timeout` 30 秒**是全仓的基准超时预算，注释里说明它要与"分片 CI 的超时预算"保持一致。

**`[profile.local] inherits = "default"`（第一版漏了）**：`just test` 用的 local profile **不是另起一套配置**，而是完整继承 default，只额外定义了自己的 override（把 app-server 集成测试放进 `app_server_integration_local` 分组）。所以本地和 CI 的超时、重试行为是一致的。

### 3.2 串行化分组（test-groups）

| 分组 | `max-threads` | 配置文件里的注释 |
| ---- | ---: | ---- |
| `app_server_protocol_codegen` | 1 | **无注释**（分组定义处没有说明，用途只能从引用它的 override filter 反推：app-server-protocol 的 TS/JSON schema 生成一致性测试） |
| `app_server_integration` | 1 | 每个用例都会拉起一个全新的 app-server 子进程；库单测保持并行 |
| `app_server_integration_local` | 4 | 更高并发会在常见开发机的资源竞争下导致集成测试超时；全局 nextest 池仍受逻辑 CPU 数限制 |
| `core_apply_patch_cli_integration` | 1 | 跑完整 Codex turn + apply_patch，对 Windows runner 的进程启动停顿敏感 |
| `windows_sandbox_legacy_sessions` | 1 | 创建受限令牌子进程与私有桌面，串行以免耗尽 Windows 会话/桌面资源 |
| `windows_process_heavy` | 2 | 这些 Windows 重测试会拉子进程、写会话文件或起 JSON-RPC 客户端，是 30s 全量 CI 超时的主要来源 |

> **纠正**：第一版这张表声称"原因（配置文件注释要点）"，但 `app_server_protocol_codegen` 在 `nextest.toml` 里**根本没有注释**，"代码生成类测试"是推断而非原文。

> **可读出的信息**：**Windows 是测试稳定性的主要痛点**——6 个分组里有 2 个是专门为 Windows 资源限制设的。app-server 集成测试的成本也很高（每用例一个子进程）。

### 3.3 超时豁免

配置里有若干 `[[profile.default.overrides]]` 会放宽超时。**共 3 处放宽**（第一版只写了 1 处）：

| filter 覆盖的测试 | 放宽后的 `slow-timeout` |
| ---- | ---- |
| `test(rmcp_client)` / `test(humanlike_typing_1000_chars_appears_live_no_placeholder)` | `1m` × 4 |
| `cfg(windows)` 上的 `start_thread_uses_all_default_environments_from_codex_home` | `1m` × 2 |
| `cfg(windows)` 上的 `windows_process_heavy` 一组（`suite::resume::`、`suite::cli_stream::`、`suite::auth_env::` 等） | `45s` × 2 |

只有第一条带着那句注释：

```toml
[[profile.default.overrides]]
# Do not add new tests here
filter = 'test(rmcp_client) | test(humanlike_typing_1000_chars_appears_live_no_placeholder)'
slow-timeout = { period = "1m", terminate-after = 4 }
```

> [!IMPORTANT]
> 注释 **"Do not add new tests here"** 是针对**这一条 filter** 的明确约束：不要往它的测试名列表里加新测试。跑不进 30 秒时优先优化测试。
>
> 但要理解准确：仓库**并非绝对禁止任何超时放宽**——另外两条 Windows 相关的放宽就没有这句注释，它们的注释说明的是"在两条 Windows 全量 CI 通道上，即使降低了竞争仍然超时"。也就是说：**平台级的系统性超时是被接受的例外，个别测试写得慢则不是**。第一版把这里写成了绝对的"不要申请豁免"，措辞过强。
>
> 还有一条 override 是把 `approval_matrix_covers_all_modes` **显式设回 30s × 2**（与默认相同），属于防漂移的固化，不是放宽。

---

## 4. 测试类型选择（`AGENTS.md` → `### Test authoring guidance`）

```
改动智能体逻辑？
├── 是 → 必须写集成测试（core/suite 下，用 test_codex）
│         并列出需要覆盖的主要逻辑变更与用户可见行为
└── 否 → 确需单元测试时，放进专门的 *_tests.rs 文件
```

三条附加要求：

1. **避免在主实现中留测试专用函数**（同节，grep `Avoid test-only functions`）
2. **先查有没有现成 helper**（同节，grep `existing helpers`）
3. **比较整个对象的相等性**，而不是逐字段比较（顶部规则列表，grep `comparing the equality of entire objects`）

> 相关的还有 `### Crate API surface`：*"Keep crate API surfaces as small as possible. Avoid proliferating test-only helpers."*——helper 也不宜无限膨胀。

---

## 4A. `AGENTS.md` 里其余的测试硬规则（第一版未覆盖）

这一批全部来自 `AGENTS.md` 的 `## Tests` 及其子节，第一版只捕获了其中一部分。

### 4A.1 `### Test module organization`

- 新增测试模块时，**内容必须写在同级的独立文件里**，不要内联在实现文件中。
- 必须用显式的 `#[path = "..._tests.rs"]`，让测试文件名可读、可定位：

  ```rust
  #[cfg(test)]
  #[path = "parser_tests.rs"]
  mod tests;
  ```

> [!WARNING]
> **这条只适用于新增测试模块。** 原文明确写着：不要仅仅为了符合这个约定，就去搬动或重写既有的内联 `#[cfg(test)] mod tests { ... }`。第一版把它写成了无条件规则。

### 4A.2 `### Test assertions`

| 规则 | 说明 |
| ---- | ---- |
| **必须用 `pretty_assertions::assert_eq`** | 为了更清晰的 diff；测试模块顶部若没有就补上 import |
| 尽量做深比较 | `assert_eq!()` 比整个对象，而不是逐字段 |
| **不要在测试里修改进程环境变量** | 应当把环境派生的开关/依赖从上层传入 |

### 4A.3 `### Spawning workspace binaries in tests (Cargo vs Bazel)`

> [!IMPORTANT]
> 这是**双构建系统的正确性问题**，不是风格偏好——Bazel 下二进制与资源位于 runfiles，写死 Cargo 假设会在 Bazel 侧失败。

| 场景 | 用 | 不要用 |
| ---- | ---- | ---- |
| 在测试里拉起一方（first-party）二进制 | `codex_utils_cargo_bin::cargo_bin("...")` | `assert_cmd::Command::cargo_bin(...)`、`escargot` |
| 定位 fixture / 测试资源 | `codex_utils_cargo_bin::find_resource!` | `env!("CARGO_MANIFEST_DIR")` |

`cargo_bin` 解析出的绝对路径在 `chdir` 之后依然有效，这是它相对其他方案的关键优势。

### 4A.4 `#### codex_core integration testing`：`core_test_support::responses` 的使用契约

写 core 端到端测试时优先用 `core_test_support::responses`，并遵守：

- 默认用 `TestCodexBuilder::build_with_auto_env()`，保证新测试在异构 app/exec OS 下也能跑（细节见 §8）
- **所有 `mount_sse*` helper 都返回一个 `ResponseMock`——必须持有它**，才能对发出的 `/responses` POST body 做断言
- 只发一次 POST 用 `ResponseMock::single_request()`；要检查每一次请求用 `ResponseMock::requests()`（返回 `ResponsesRequest`）
- `ResponsesRequest` 提供结构化访问器：`body_json`、`input`、`function_call_output`、`custom_tool_call_output`、`call_output`、`header`、`path`、`query_param`——**用它们，而不是手工挖 JSON**
- 用 `ev_*` 构造器 + `sse(...)` 拼 SSE 载荷
- **优先 `wait_for_event`**，而不是 `wait_for_event_with_timeout`
- **优先 `mount_sse_once`**，而不是 `mount_sse_once_match` / `mount_sse_sequence`

原文给出的典型形态是：`mount_sse_once(&server, sse(vec![ev_response_created, ev_function_call, ev_completed]))` → `codex.submit(Op::UserTurn { .. })` → `mock.single_request()` 上断言。

### 4A.5 `#### app-server integration testing`

- 测试应当针对 app-server 的**公开 JSON-RPC API**，mock 方式与 core 集成测试相同
- 默认用 **`TestAppServer::builder().build()`** 与 `TestAppServer::send_thread_start_request_with_auto_env()`

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

### 6.1 `core/tests/suite/`（116 个 `.rs` 文件 + 一个 `snapshots/` 子目录）

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

## 7. insta 快照测试（`AGENTS.md` → `### Snapshot tests`）

全仓 **681 个 `.snap`**，主要集中在 TUI（渲染输出）与协议层（序列化结果）。`codex-rs/core/src/session/snapshots/` 等目录存放快照。

> [!IMPORTANT]
> **本节是对第一版的整体订正。** 第一版写"`AGENTS.md` 未提及快照更新流程 / 两者如何调和需要确认 / 不要贸然用 `cargo insta`"——**这是本文档的调研失误（漏读了 `AGENTS.md` 的 `### Snapshot tests` 一节），不是上游的规范缺口。** 上游规范完整且明确，下面照录。

### 7.1 强制要求：UI 变更必须带快照覆盖

`AGENTS.md` 原文的 **Requirement**：

> 任何影响**用户可见 UI**（包括新增 UI）的改动，**必须**包含相应的 `insta` 快照覆盖——没有就新增快照测试，有就更新既有快照。快照更新要作为 PR 的一部分被 review 并 accept，这样 UI 影响易于评审、后续 diff 保持可视化。

**三份文档的第一版都漏了这条强制要求**，这里补上：它和"智能体逻辑变更必须写集成测试"是同一层级的硬约束。

### 7.2 更新快照的标准流程

当 UI 或文本输出是**有意**改变时，按下面四步走：

| 步骤 | 命令 |
| ---- | ---- |
| 1. 跑测试生成新快照 | `just test -p codex-tui` |
| 2. 查看待处理项 | `cargo insta pending-snapshots -p codex-tui` |
| 3. 审阅改动 | 直接读仓库里生成的 `*.snap.new` 文件，或 `cargo insta show -p codex-tui path/to/file.snap.new` |
| 4. **确认要接受本 crate 全部新快照后**才执行 | `cargo insta accept -p codex-tui` |

工具没装的话：`cargo install --locked cargo-insta`。（`AGENTS.md` 顶部规则列表也把 `cargo-insta` 与 `just`、`rg` 并列，要求"运行本文指令前先装好"。）

> **"禁止 `cargo test`"与 `cargo insta` 的关系（第一版认为是未解决的张力，其实规范已经给了答案）**：
> **生成**快照走 `just test`（因此仍然遵循仓库默认的 nextest 配置），**审阅与接受**走 `cargo insta pending-snapshots` / `show` / `accept`——后面这三个子命令**不运行测试**，只是对已经落盘的 `.snap.new` 文件做查看和改名。两者不冲突。
>
> 注意规范给的是 `cargo insta accept`，**不是** `cargo insta review`，也不是 `INSTA_UPDATE=always`。

---

## 8. 跨操作系统测试与 `$remote-tests`

`AGENTS.md` → `## Platform Support`：

> "Tests and features must support Linux, macOS and Windows unless feature is explicitly OS-specific."

同节还指出，app-server 与 exec-server 可以跑在**不同操作系统**上，这类配置的集成测试细节见 **`$remote-tests` skill**。

平台专属测试的例子：`core/src/exec_policy_windows_tests.rs`、`windows-sandbox-rs` 的 `legacy_*` 测试。

### 8.1 `$remote-tests` skill 的内容（`.codex/skills/remote-tests/SKILL.md`）

> 第一版把这条标为"未验证 E1"。它就在仓库里——`.codex/skills/` 下 14 个 skill 之一。

远程执行器测试验证的是 **app-server / exec-server 拆分**：确保智能体特性在本地与远程两种执行环境下都能工作。

**前提**：目前**需要 x86_64 Linux 宿主机**。有两种形态：

| 形态 | 说明 |
| ---- | ---- |
| **Docker** | Linux exec-server |
| **Wine** | Windows exec-server，app-server 仍留在 Linux 宿主上 |

### 8.2 测试夹具：如何 opt-in

单个用例必须**显式选择**跑在远程执行器上：

| 场景 | 用法 |
| ---- | ---- |
| `codex_core` 集成测试 | `TestCodexBuilder::build_with_auto_env()`（除非该测试需要更精细地控制 executor） |
| app-server 起服务 | `TestAppServer::new_with_auto_env()`（除非该测试自定义 `$CODEX_HOME/environments.toml` 或运行时定义环境） |
| app-server 起 thread | `TestAppServer::send_thread_start_request_with_auto_env()`，并把 `ThreadStartParams.environments` 留为 `None` |

### 8.3 五个 skip 宏

某个远程执行器配置下跑不过时，**只在该配置下跳过**。宏支持理由字符串的就写上，方便后来人：

| 宏 | 用于 |
| ---- | ---- |
| `skip_if_target_windows!` | Windows target 行为 |
| `skip_if_wine_exec!` | Wine-exec runner 的限制 |
| `skip_if_host_windows!` | Windows 宿主机限制 |
| `skip_if_remote!` | 仅本地有意义的测试行为 |
| `skip_if_no_remote_env!` | 仅远程有意义的测试行为 |

> skill 明确：**优先写在所有 host/target 组合下都能跑的测试**；让测试兼容各配置最常见的改动见 `$path-types` skill。

### 8.4 怎么跑

**Docker**：容器由 `./scripts/test-remote-env.sh` 构建与初始化；在 bash 里 `source` 这个脚本还会提供 `codex_remote_env_cleanup` 函数供测试后清理。

```bash
bash -c '
  set -euo pipefail
  unset CODEX_TEST_REMOTE_EXEC_SERVER_URL
  source scripts/test-remote-env.sh
  trap codex_remote_env_cleanup EXIT

  cd codex-rs
  just test -p codex-core --test all      # app-server 侧换成 -p codex-app-server
'
```

**Wine**：要为 Windows 构建 exec-server 再放到 Wine 下运行，**这个跨平台构建依赖决定了它只能走 Bazel**：

```sh
bazel test //codex-rs/core:core-all-wine-exec-test
bazel test //codex-rs/app-server:app-server-all-wine-exec-test
```

> macOS 开发机跑不了这些测试（需要 x86_64 Linux 宿主），skill 里给出的做法是连到远端开发机执行。

---

## 9. 编写测试的检查清单

```
□ 这是智能体逻辑变更吗？→ 是则必须写集成测试（core/suite）
□ 改动影响用户可见 UI？→ 必须有对应的 insta 快照覆盖（新增或更新），并已 accept
□ 用 test_codex / test_codex_exec 搭建实例，不要手搓
□ 默认用 build_with_auto_env() / TestAppServer::builder().build()（异构 OS 兼容）
□ 先搜有没有现成 helper；不要增殖 test-only helper
□ 新增测试模块 → 独立 *_tests.rs + #[cfg(test)] #[path = "..."] mod tests;
   （既有内联 mod tests 不要为此迁移）
□ 主实现里没有留测试专用函数
□ 断言用 pretty_assertions::assert_eq，比较整个对象而不是逐字段
□ 没有在测试里改进程环境变量
□ 拉二进制用 codex_utils_cargo_bin::cargo_bin；找资源用 find_resource!
□ 持有了 mount_sse* 返回的 ResponseMock；优先 wait_for_event / mount_sse_once
□ 不是在为静态定义的值写测试
□ 不是在为已移除的逻辑写负向测试
□ 测试能在 30 秒内跑完（不要往那条带 "Do not add new tests here" 的 filter 里加）
□ Linux / macOS / Windows 都能过（除非是明确的 OS 专属特性）
□ 跑 just test -p <crate> 通过
□ 改了 common/core/protocol → 跑 just test（先问用户）
```

---

## 10. CI 里的测试分片策略

> 第一版把这条标为"未覆盖 E1"，这里补齐。

### 10.1 什么时候跑

| 通道 | 触发 | 内容 |
| ---- | ---- | ---- |
| `bazel.yml`（经 `blocking-ci.yml`） | 每个 PR + push main | **PR 上的 Rust 测试信号来自这里**；Windows gnullvm 按 4 片分 shard |
| `rust-ci-full.yml`（经 `postmerge-ci.yml`，或**分支名含 `full-ci` 时自触发**） | push main（经 postmerge-ci）+ `push: branches: ["**full-ci**"]` + `workflow_dispatch` | 完整 Cargo nextest 矩阵——**不阻断 PR** |

> [!NOTE]
> **勘误：`rust-ci-full.yml` 不是"只在 push main"。** 它自己的 `on:` 块（`.github/workflows/rust-ci-full.yml:2-9`）有三个触发器：
>
> ```yaml
> on:
>   workflow_call:
>   push:
>     branches:
>       # Main pushes enter through postmerge-ci. Keep this opt-in branch
>       # trigger for developers who want the full suite before merging.
>       - "**full-ci**"
>   workflow_dispatch:
> ```
>
> **这是一个很有用的能力，值得记住**：把分支名起成包含 `full-ci` 的形式（例如 `<你的名字>/full-ci-sandbox-refactor`），**推上去就会在合并前跑完整矩阵**，不必等 postmerge 才发现平台相关的失败。yml 里的注释明说这就是它的设计意图。另外 `workflow_dispatch` 也允许手动对任意分支触发。
| `rust-ci.yml`（经 `blocking-ci.yml`） | 每个 PR | **不跑 codex-rs workspace 的测试**，只有 fmt / bench-smoke / cargo-shear / argument-comment-lint |

### 10.2 archive + partition 的两段式

`rust-ci-full.yml` 调用 `rust-ci-full-nextest-platform.yml` **5 次**，每次一个平台通道。这个 reusable workflow 分两段：

1. **`archive` job**：`cargo nextest archive --cargo-profile <profile> --archive-file nextest-<artifact_id>.tar.zst`，把编译好的测试二进制打包上传（Linux/Windows 还额外构建 sandbox / command-runner 等运行时 helper）。
2. **`shard` job**：`shard: [1, 2, 3, 4]` 矩阵，下载归档后用 **`--partition "hash:<shard>/4"`** 回放。

固定参数：

- cargo profile **`ci-test`**
- **`NEXTEST_STATUS_LEVEL: leak`**
- JUnit 输出在 **`target/nextest/default/junit.xml`**——路径里的 `default` 印证了 §2.1 的说法：**CI 用 default profile，本地 `just test` 用 local**

五个平台通道：

| 通道 | runner | target | 备注 |
| ---- | ---- | ---- | ---- |
| macOS aarch64 | `macos-15-xlarge` | `aarch64-apple-darwin` | |
| Linux x64（remote-env） | `ubuntu-24.04` | `x86_64-unknown-linux-gnu` | `remote_env: true`——即 §8 的远程执行器测试 |
| Linux arm64 | `ubuntu-24.04-arm` | `aarch64-unknown-linux-gnu` | |
| Windows x64 | 自托管 windows-x64 | `x86_64-pc-windows-msvc` | `test_threads: 8` |
| Windows arm64 | 自托管 windows-arm64 | `aarch64-pc-windows-msvc` | **归档在 windows-x64 上交叉编译**，再到原生 arm64 上回放；`test_threads: 8` |

> **含义**：单个平台通道的测试是 4 路并行的，所以 §3 里那句"30s slow-timeout 要与分片 CI 的超时预算对齐"是有出处的——分片压缩了单片墙钟时间，但没有放宽单测超时。

---

## 11. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `TestCodexBuilder` 的完整 builder 方法 | E1 | `core/tests/common/test_codex.rs`（分段读） |
| `zsh/` 测试子目录的用途 | E1 | `app-server/tests/suite/zsh/` |
| 基准测试（bench）的组织与基线 | E1 | `just bench`（divan）、`just bench-smoke`、`//codex-rs:e2e-benchmarks` |
| `scripts/test-remote-env.sh` 的实现细节 | E1 | 该脚本 |
| `.codex/skills/` 下其余 skill 的内容 | E1 | 见 `development_workflow.md` §2.6 |

> 第一版列在这里的三项——insta 快照更新流程、`$remote-tests` 内容、CI 分片策略——**都不是真正的空白**，本次已分别在 §7、§8、§10 补齐。

---

## 12. 相关文档

- [开发流程](./development_workflow.md) — 完整的改完代码后动作、`.codex/skills/` 清单
- [智能体核心循环](./core_agent_loop.md) — 什么算"智能体逻辑变更"
- [构建与发布](./build_and_release.md) — CI 编排结构（`blocking-ci` / `postmerge-ci`）与 Bazel
- [TUI 开发指南](./tui_guide.md) — TUI 测试的组织方式
