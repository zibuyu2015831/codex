---
title: Codex 测试指南
summary: 描述 codex 仓库的测试拓扑与规模（91 个集成测试 target / 29 包、1448 处 #[cfg(test)]、仅 1 个 bench target）、nextest 配置中的重试与超时与串行化分组、本地 local profile 与 CI default profile 的实际差异、6 个测试支撑 crate、core 与 app-server 两大集成测试套件的组织方式（含 9 个 crate 共用的 all.rs 单聚合二进制模式与 suite/mod.rs 的 #[ctor] arg0 分派机制）、test_codex 测试夹具、insta 快照工作流与依赖事实（快照 92% 集中在 TUI，协议层走 schema fixture 对拍而非 insta）、跨 OS 与远程执行的四套机制（Bazel RBE / 构建远程测试本地 / Wine / Docker remote-env）、两条 Bazel 绿不等于 Cargo 绿的漏检机制，以及 CI 的 nextest archive 分片策略（五条平台通道中仅 macOS 用 GitHub 托管 runner）与 AGENTS.md 的测试编写强制约束。
keywords: codex | testing | nextest | insta | integration-test | test-codex | snapshot | test-group | remote-tests | nextest-archive | ctor-dispatch | self-hosted-runner | nextest-profile | bazel-rbe | wine-exec | skip-macros
scope: openai/codex 仓库的测试组织、运行与编写规范
related_files: codex-rs/.config/nextest.toml | codex-rs/Cargo.toml | codex-rs/core/tests/common/test_codex.rs | codex-rs/core/tests/common/lib.rs | codex-rs/core/tests/suite/mod.rs | codex-rs/app-server/tests/suite/mod.rs | codex-rs/app-server/tests/common/test_app_server.rs | justfile | .bazelrc | defs.bzl | AGENTS.md | .codex/skills/remote-tests/SKILL.md | .github/workflows/rust-ci-full.yml | .github/workflows/rust-ci-full-nextest-platform.yml
dependencies: dev_docs/development_workflow.md | dev_docs/core_agent_loop.md
verified_at: 2026-09-21
---

# 测试指南

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
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

换个口径看（同为 E1，均已实测）：

| 指标 | 数量 | 复核命令 |
| ---- | ---: | ---- |
| Cargo **集成测试 target** 数 | **91**（分布于 **29** 个包） | `cargo metadata --no-deps` 里 `kind == ["test"]` 计数 |
| `codex-rs` 下 `tests/` 里的 `.rs` 文件 | **436** | `find codex-rs -type f -path '*/tests/*.rs' -not -path '*/target/*' \| wc -l` |
| `#[cfg(test)]` 出现次数（内联单测入口） | **1,448** | `rg -c --no-filename '#\[cfg\(test\)\]' -g '*.rs' codex-rs \| awk '{s+=$1} END{print s}'` |
| Cargo **bench target** | **1** | `cargo metadata` 里 `kind == ["bench"]` |
| Python 测试文件 | **27** | `find . -name 'test_*.py'`（排除 `dev_docs/`、`node_modules/`） |
| TypeScript 测试文件 | **4**（jest） | `ls sdk/typescript/tests/*.test.ts` |

> [!IMPORTANT]
> **全仓只有 1 个 Cargo bench target**：`codex-utils-image` 的 `prompt_images`（`codex-rs/utils/image/Cargo.toml:25` 的 `[[bench]]`）。所以 `just bench` 的 `cargo bench --workspace --bench '*'` 实际只有这一个目标——**基准测试的覆盖面非常窄**，不要把它当成性能回归的安全网。重量级的性能验证在 Bazel 侧的 `//codex-rs:e2e-benchmarks`（`just bench-e2e`）。
>
> 另外注意 **91 个集成测试 target vs 29 个包**：平均每包 3 个，但分布极不均——§6.2 会讲到 9 个主要 crate 走的是"单一聚合二进制"模式，它们各自只贡献 1 个 target。

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
| `just bazel-test` | Bazel 侧测试。**PR 上的 Rust 测试信号来自 Bazel，不是 `.github/workflows/rust-ci.yml`**（见 §10） |

底层实现（`justfile`）：

```bash
RUST_MIN_STACK=8388608 NEXTEST_PROFILE=local cargo nextest run --no-fail-fast "$@"
```

三个要点：

- **`RUST_MIN_STACK` 设为 8 MiB** —— 默认栈不够用
- **`NEXTEST_PROFILE=local`** —— 本地显式指定 local profile；**CI 全程不设这个变量**，因此 CI 跑的是 nextest 的 **`default`** profile。两者不是同一套配置，差异见 §3.4
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

**`[profile.local] inherits = "default"`（第一版漏了）**：`just test` 用的 local profile **不是另起一套配置**，而是完整继承 default，只额外定义了自己的 override（把 app-server 集成测试放进 `app_server_integration_local` 分组）。所以本地和 CI 的**超时与重试**行为是一致的——但**并发度不一致**，见 §3.4。

> [!IMPORTANT]
> **`codex-rs/.config/nextest.toml` 里只有 `[profile.default]` 与 `[profile.local]` 两个 profile。** 别把它和 §10 里的 **`ci-test`** 搞混——那是 **Cargo profile**（`codex-rs/Cargo.toml:566-570`，`inherits = "test"` / `opt-level = 0` / `debug = "limited"`），由 `.github/workflows/rust-ci-full-nextest-platform.yml:182` 通过 `--cargo-profile` 传入，管的是**怎么编译**；nextest profile 管的是**怎么跑**（超时、重试、分组、JUnit）。两者名字都叫 "profile"，但分属不同工具、互不继承。

### 3.2 串行化分组（test-groups）

| 分组 | `max-threads` | 配置文件里的注释（多数挂在**引用该组的 `[[profile.default.overrides]]`** 上，而非组定义处） |
| ---- | ---: | ---- |
| `app_server_protocol_codegen` | 1 | **全文件唯一没有任何注释的分组**——组定义处与引用它的 override 处都没有说明，用途只能从 filter 反推：app-server-protocol 的 TS/JSON schema 生成一致性测试 |
| `app_server_integration` | 1 | 每个用例都会拉起一个全新的 app-server 子进程；库单测保持并行 |
| `app_server_integration_local` | 4 | 更高并发会在常见开发机的资源竞争下导致集成测试超时；全局 nextest 池仍受逻辑 CPU 数限制 |
| `core_apply_patch_cli_integration` | 1 | 跑完整 Codex turn + apply_patch，对 Windows runner 的进程启动停顿敏感 |
| `windows_sandbox_legacy_sessions` | 1 | 创建受限令牌子进程与私有桌面，串行以免耗尽 Windows 会话/桌面资源 |
| `windows_process_heavy` | 2 | 这些 Windows 重测试会拉子进程、写会话文件或起 JSON-RPC 客户端，是 30s 全量 CI 超时的主要来源 |

> **纠正**：第一版这张表声称"原因（配置文件注释要点）"，但 `app_server_protocol_codegen` 在 `codex-rs/.config/nextest.toml` 里**根本没有注释**，"代码生成类测试"是推断而非原文。
>
> **另一处订正**：表头原写"配置文件里的注释"，容易让人以为注释都挂在 `[test-groups.*]` 定义处。实际上 6 个分组里**只有 `app_server_integration_local` 的注释在定义处**（`codex-rs/.config/nextest.toml:20-21`）；`app_server_integration`（L48-49）、`core_apply_patch_cli_integration`（L60-61）、`windows_sandbox_legacy_sessions`（L66-67）、`windows_process_heavy`（L79-80）的注释都写在**引用它们的 `[[profile.default.overrides]]`** 块里。按注释找分组说明时要往 override 处看。

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

### 3.4 本地与 CI 跑的**不是同一个 nextest profile**

这条直接影响"本地绿 = CI 绿"的判断，值得单列：

| | 本地 `just test` | CI（`.github/workflows/rust-ci-full-nextest-platform.yml`） |
| ---- | ---- | ---- |
| nextest profile | **`local`**（`justfile:82` 显式 `NEXTEST_PROFILE=local`） | **`default`**——**该工作流全文不设 `NEXTEST_PROFILE`**，nextest 回落到默认 |
| app-server 集成测试并发 | `app_server_integration_local`，**`max-threads = 4`** | `app_server_integration`，**`max-threads = 1`** |
| 超时 / 重试 / 分组的其余部分 | 完全一致（`[profile.local] inherits = "default"`） | 同左 |

`[profile.local]` 的**唯一** override 就是把 app-server 集成测试改挂到 4 线程组。所以：

> [!WARNING]
> **本地跑得过、CI 挂掉的一类典型原因，就在这 4 vs 1 的差异里**——本地 4 路并发下暴露的竞态，CI 串行时可能测不出来；反过来，CI 串行下每个用例分到的资源更多、本地并发时更容易撞上 30s 超时。§10 的 JUnit 落盘路径 `target/nextest/default/junit.xml` 里那个 `default` 就是这件事的直接证据。

### 3.5 配置里**没有**的东西（同样值得知道）

- **不使用 `threads-required`**——并发控制全部通过 test-group 的 `max-threads` 表达。
- **`fail-fast` / `failure-output` 都不在 toml 里**：`--no-fail-fast` 是命令行给的，本地在 `justfile:82`、CI 在 `.github/workflows/rust-ci-full-nextest-platform.yml:377`。改这两项要改调用方，不是改配置文件。
- CI 另在环境层面加了 `RUST_BACKTRACE: 1` 与 `NEXTEST_STATUS_LEVEL: leak`（`.github/workflows/rust-ci-full-nextest-platform.yml:408-410`），本地默认没有——**本地复现 CI 失败时建议手工带上这两个**。

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
> **原文用的是 Prefer / avoid，而不是硬禁令**（"**Prefer** `codex_utils_cargo_bin::cargo_bin(...)` **over** ..."、"**avoid** `env!("CARGO_MANIFEST_DIR")`"，全节没有 must / never）。第一版把它硬化成禁令，并断言"不是风格偏好"——**措辞过强，但给出的理由是对的**：原文自己说明了这是正确性问题而非风格问题——Bazel 下二进制与资源位于 runfiles，`codex_utils_cargo_bin::cargo_bin` 解析出的绝对路径在 `chdir` 之后依然稳定，写死 Cargo 假设会在 Bazel 侧失败。

| 场景 | 优先用 | 避免用 |
| ---- | ---- | ---- |
| 在测试里拉起一方（first-party）二进制 | `codex_utils_cargo_bin::cargo_bin("...")` | `assert_cmd::Command::cargo_bin(...)`、`escargot` |
| 定位 fixture / 测试资源（原文限定 **"under Bazel"**） | `codex_utils_cargo_bin::find_resource!` | `env!("CARGO_MANIFEST_DIR")` |

> 第二条的作用域限定第一版也漏了：原文是 *"When locating fixture files or test resources **under Bazel**, avoid `env!("CARGO_MANIFEST_DIR")`. Prefer `codex_utils_cargo_bin::find_resource!` so paths resolve correctly under both Cargo and Bazel runfiles."*——`find_resource!` 的卖点是**两套构建系统下都能解析**，纯 Cargo 场景下 `CARGO_MANIFEST_DIR` 本身没有错。

### 4A.4 `### Integration tests` → `#### codex_core integration testing`：`core_test_support::responses` 的使用契约

> 下面两小节（4A.4 / 4A.5）都是 `AGENTS.md` 的 `## Tests` → **`### Integration tests`** 之下的 `####` 级子节。按 §0 立的"小节标题定位"规矩，父节标题在此给出，便于 grep 定位。

写 core 端到端测试时优先用 `core_test_support::responses`，并遵守：

- 默认用 `TestCodexBuilder::build_with_auto_env()`，保证新测试在异构 app/exec OS 下也能跑（细节见 §8）
- **所有 `mount_sse*` helper 都返回一个 `ResponseMock`——必须持有它**，才能对发出的 `/responses` POST body 做断言
- 只发一次 POST 用 `ResponseMock::single_request()`；要检查每一次请求用 `ResponseMock::requests()`（返回 `ResponsesRequest`）
- `ResponsesRequest` 提供结构化访问器：`body_json`、`input`、`function_call_output`、`custom_tool_call_output`、`call_output`、`header`、`path`、`query_param`——**用它们，而不是手工挖 JSON**
- 用 `ev_*` 构造器 + `sse(...)` 拼 SSE 载荷
- **优先 `wait_for_event`**，而不是 `wait_for_event_with_timeout`
- **优先 `mount_sse_once`**，而不是 `mount_sse_once_match` / `mount_sse_sequence`

原文给出的典型形态是：`mount_sse_once(&server, sse(vec![ev_response_created, ev_function_call, ev_completed]))` → `codex.submit(Op::UserTurn { .. })` → `mock.single_request()` 上断言。

### 4A.5 `### Integration tests` → `#### app-server integration testing`

- 测试应当针对 app-server 的**公开 JSON-RPC API**，mock 方式与 core 集成测试相同
- 默认用 **`TestAppServer::builder().build()`** 与 `TestAppServer::send_thread_start_request_with_auto_env()`

---

## 5. `test_codex` 测试夹具（E3）

集成测试的核心工具，位于 `codex-rs/core/tests/common/`（crate 名 `core_test_support`，6,752 行）。

| 类型 / 函数 | 位置 |
| ---- | ---- |
| `TestCodexBuilder` | `codex-rs/core/tests/common/test_codex.rs:294` |
| `TestCodex` | `codex-rs/core/tests/common/test_codex.rs:815` |
| `TestCodexHarness` | `codex-rs/core/tests/common/test_codex.rs:1036` |
| `TestCodexExecBuilder` | `codex-rs/core/tests/common/test_codex_exec.rs:6` |
| `pub fn test_codex_exec()` | `codex-rs/core/tests/common/test_codex_exec.rs:43` |

**builder 模式**：`TestCodexBuilder` → `TestCodex` → `TestCodexHarness`。另有 `test_codex_exec()` 专门用于 `codex exec` 路径。

测试支撑 crate 共 **6 个**。⚠️ **其中 3 个是 `[workspace] members`**（`app-server-test-client`、`test-binary-support`、`exec-server/tests/support`），另 3 个 `*/tests/common` 不是 member、仅靠 `[workspace.dependencies]` 的 path 依赖被 Cargo 纳入 workspace：

| crate | 位置 | workspace 声明处 | 作用 | 行数 |
| ---- | ---- | ---- | ---- | ---: |
| `core_test_support` | `codex-rs/core/tests/common/` | `codex-rs/Cargo.toml:271` | `test_codex` / `TestCodexBuilder` + skip 宏（见 §8.3） | 6,752 |
| `app_test_support` | `codex-rs/app-server/tests/common/` | `codex-rs/Cargo.toml:145` | `TestAppServer` JSON-RPC 客户端 | 3,878 |
| `mcp_test_support` | `codex-rs/mcp-server/tests/common/` | `codex-rs/Cargo.toml:272` | MCP server 测试助手 | 507 |
| `codex-exec-server-test-support` | `codex-rs/exec-server/tests/support/` | `codex-rs/Cargo.toml:189` | exec-server 脚手架 | — |
| `codex-test-binary-support` | `codex-rs/test-binary-support/` | `codex-rs/Cargo.toml:242` | 定位/启动已构建的测试二进制（§6.3 的 `#[ctor]` 分派就用它） | — |
| `codex-app-server-test-client` | `codex-rs/app-server-test-client/` | `codex-rs/Cargo.toml:158` | 对**真二进制**说话的客户端，由 `just app-server-test-client` 驱动（`justfile:39-41`：先 `cargo build -p codex-cli`，再 `cargo run -p codex-app-server-test-client -- --codex-bin ./target/debug/codex`） | — |

> [!NOTE]
> **第一版只列了前三个**，漏掉了后三个。其中两个不在 `tests/` 目录下而是**独立的顶层 crate**（`codex-rs/test-binary-support/`、`codex-rs/app-server-test-client/`）——按 `tests/` 目录找找不到，但它们是显式 member，`cargo metadata` 直接可见。
>
> 顺带纠正一个可能的误解：这些 crate **并没有**用 `publish = false` 屏蔽——全仓 `codex-rs/**/Cargo.toml` 里只有 `codex-rs/backend-client/Cargo.toml:6` 出现过 `publish` 键。它们不进生产依赖树，靠的是消费方把它们放在 `[dev-dependencies]` 里。

**HTTP mock** 统一用 `wiremock`（`codex-rs/Cargo.toml:485` 声明 `wiremock = "0.6"`），被 **20 个成员 crate 的 manifest** 引用（另加 `codex-rs/Cargo.toml` 的 workspace 声明本身）——§4A.4 讲的 `core_test_support::responses` 那一整套 `mount_sse*` / `ResponseMock` 就是架在它上面的。

---

## 6. 两大集成测试套件

### 6.1 `core/tests/suite/`（116 个 `.rs` 文件 + 一个 `snapshots/` 子目录）

按功能面组织，节选：

| 领域 | 文件 |
| ---- | ---- |
| 上下文压缩 | `codex-rs/core/tests/suite/compact.rs`（5,511 行）、`codex-rs/core/tests/suite/compact_remote.rs`、`codex-rs/core/tests/suite/compact_remote_trimming.rs`、`codex-rs/core/tests/suite/compact_resume_fork.rs` |
| 审批与策略 | `codex-rs/core/tests/suite/approvals.rs`、`codex-rs/core/tests/suite/exec_policy.rs`、`codex-rs/core/tests/suite/catalog_permission_messages.rs`、`codex-rs/core/tests/suite/guardian_review.rs` |
| 执行 | `codex-rs/core/tests/suite/exec.rs`、`codex-rs/core/tests/suite/apply_patch_cli.rs`、`codex-rs/core/tests/suite/extension_sandbox.rs` |
| 会话 | `codex-rs/core/tests/suite/fork_thread.rs`、`codex-rs/core/tests/suite/abort_tasks.rs`、`codex-rs/core/tests/suite/codex_delegate.rs` |
| 智能体 | `codex-rs/core/tests/suite/agent_execution.rs`、`codex-rs/core/tests/suite/agent_websocket.rs` |
| 客户端 | `codex-rs/core/tests/suite/client.rs`、`codex-rs/core/tests/suite/client_websockets.rs`、`codex-rs/core/tests/suite/cli_stream.rs` |
| 规范注入 | `codex-rs/core/tests/suite/agents_md.rs`、`codex-rs/core/tests/suite/additional_context.rs`、`codex-rs/core/tests/suite/collaboration_instructions.rs` |
| 其他 | `codex-rs/core/tests/suite/auto_review.rs`、`codex-rs/core/tests/suite/code_mode.rs`、`codex-rs/core/tests/suite/external_auth.rs`、`codex-rs/core/tests/suite/git_enrichment.rs`、`codex-rs/core/tests/suite/current_time_reminder.rs` |

> 表中一律写全路径，因为裸文件名有真实歧义：测试侧的 `codex-rs/core/tests/suite/compact.rs` 与实现侧的 `codex-rs/core/src/compact.rs` **同名且同 crate**，而本节的核心论点恰恰是二者的 parity；`codex-rs/core/tests/suite/agents_md.rs` 在 `codex-rs/exec/tests/suite/agents_md.rs` 下也有同名文件。

> [!CAUTION]
> **第 6 轮：`compact_remote_parity.rs` 已不存在**<!-- ref-exempt: 反例——正文说明该路径已不存在 -->，由它支撑的结论「本地与远程压缩之间有一致性（parity）测试」**失去证据**。
>
> 这与远程压缩 v1 整条路径被删除是同一件事：没有了两条远程实现，parity 测试自然也没有了对象。当前 `suite/` 下与压缩相关的是 `codex-rs/core/tests/suite/compact.rs`、`codex-rs/core/tests/suite/compact_remote.rs`、`codex-rs/core/tests/suite/compact_remote_trimming.rs`、`codex-rs/core/tests/suite/compact_resume_fork.rs` 与 `codex-rs/core/tests/suite/step_settings_compaction.rs`。
>
> **本轮未替该结论另寻证据**——是否仍存在等价的一致性覆盖需要读 `compact_remote.rs` 才能判定，留空比编一个替代来源诚实。详见 [`core_agent_loop.md`](./core_agent_loop.md) §6.2。

`codex-rs/core/tests/` 下除 `suite/` 与 `common/` 外还有两项本文未展开：`codex-rs/core/tests/responses_headers.rs`（独立文件）与 `codex-rs/core/tests/remote_env_windows/`（目录）。

### 6.2 `app-server/tests/suite/`

顶层共 8 项：`codex-rs/app-server/tests/suite/auth.rs`、`codex-rs/app-server/tests/suite/conversation_summary.rs`、`codex-rs/app-server/tests/suite/fuzzy_file_search.rs`、`codex-rs/app-server/tests/suite/logging.rs`、**`codex-rs/app-server/tests/suite/mod.rs`（挂载入口）**、`codex-rs/app-server/tests/suite/strict_config.rs`、`codex-rs/app-server/tests/suite/v2/`（97 个文件），以及 `codex-rs/app-server/tests/suite/zsh`。

> [!IMPORTANT]
> **`zsh` 不是测试子目录，是一个 DotSlash 清单文件。** 它是 2,661 字节、带可执行位的普通文件（`file` 报 `a /usr/bin/env dotslash script text executable`），同级的 `v2` 才是目录。它也**不是测试模块**——`codex-rs/app-server/tests/suite/mod.rs` 只声明了 `mod auth; mod conversation_summary; mod fuzzy_file_search; mod logging; mod strict_config; mod v2;`，**没有 `mod zsh;`**。
>
> 文件头注释自述用途：*"This is the patched zsh fork corresponding to `codex-rs/shell-escalation/patches/zsh-exec-wrapper.patch`. Fetching the prebuilt version via DotSlash makes it easier to write integration tests that exercise the zsh fork behavior in app-server tests."* —— 即通过 DotSlash 拉取预构建的 zsh fork 二进制，供集成测试验证 zsh fork 行为。消费方是 `codex-rs/app-server/tests/suite/v2/turn_start_zsh_fork.rs:793` 与 `codex-rs/core/tests/common/zsh_fork.rs`（131 行）。

#### 挂载链（也是 §2.1 里 `--test all` 的出处）

这两个 crate 的**聚合** target 都叫 `all`，所以 `--test all` 才是标准形式（注意 `codex-core` 另有 `responses_headers` 一个独立 target，见 §6.1）：

| crate | target 入口 | 聚合模块 |
| ---- | ---- | ---- |
| `codex-app-server` | `codex-rs/app-server/tests/all.rs`（一行 `mod suite;`） | `codex-rs/app-server/tests/suite/mod.rs`（6 条 `mod` 声明） |
| `codex-core` | `codex-rs/core/tests/all.rs`（`mod suite;`） | `codex-rs/core/tests/suite/mod.rs`（163 行） |

两个 target 入口文件里的注释都写着 *"Single integration test binary that aggregates all test modules."*（`codex-rs/core/tests/all.rs:3-7`）——**把所有集成测试编进同一个二进制**，这既是 `--test all` 的由来，也是下面 §6.3 那套 arg0 分派机制成立的前提。

**这不是 core / app-server 两家的特例，而是全仓 9 个 crate 共用的组织形态**（`git ls-files '*/tests/all.rs'`）：

```
codex-rs/core        codex-rs/app-server    codex-rs/mcp-server
codex-rs/login       codex-rs/tui           codex-rs/linux-sandbox
codex-rs/apply-patch codex-rs/exec          codex-rs/chatgpt
```

> 对上 §1 的规模数据：全仓 91 个集成测试 target 分布在 29 个包里，而这 9 个 crate 里有 **7 个只贡献 1 个 target**；例外是 `codex-core`（另有 `responses_headers`，共 2 个）与 `codex-tui`（另有 `manager_dependency_regression` / `test_backend`，共 3 个）——**测试代码量最大的几个 crate 恰恰是 target 数最少的**。所以 `--test all` 在这 9 个 crate 里都适用，其余包才需要按具体 target 名指定。

#### `v2/` 的组织方式

`v2/` 的 97 个文件**不按领域分子目录，而是一个方法/特性一个文件**，命名基本对齐 app-server 的 JSON-RPC 方法名，可直接从方法名反查测试：

下表所有文件的路径前缀统一为 `codex-rs/app-server/tests/suite/v2/`，为可读性只列文件名：

| 类别 | 例子（前缀同上） |
| ---- | ---- |
| thread 生命周期 | thread_start / thread_resume / thread_fork / thread_archive / thread_rollback / thread_list / thread_read |
| turn 生命周期 | turn_start / turn_steer / turn_interrupt / turn_start_zsh_fork |
| 插件 / 市场 | plugin_list / plugin_install / plugin_search / plugin_share / marketplace_add / marketplace_upgrade |
| 执行环境 | environment_add / environment_status / auto_env / exec_server_test_support / process_exec / command_exec |
| MCP / 工具 | mcp_tool / mcp_resource / mcp_server_status / dynamic_tools / code_mode_host |
| 协议与握手 | initialize / experimental_api / request_validation / client_metadata |

> 注意：这些文件名里有不少与实现侧同名（例如 `codex-rs/app-server/tests/suite/v2/command_exec.rs` 对 `codex-rs/app-server/src/command_exec.rs`，`codex-rs/app-server/tests/suite/v2/dynamic_tools.rs` 对 `codex-rs/app-server/src/dynamic_tools.rs`），引用时务必带全路径。

`codex-rs/app-server/tests/suite/v2/plugin_list.rs` 有 5,478 行，是仓库**第 8 大 Rust 源文件**（`git ls-files "*.rs"` 按行数排序）。放到**全部跟踪文件**里排序它只排第 16——比它大的 15 个多是非 `.rs` 生成物或数据文件（JSON schema 22,635 / 20,393 / 7,604 行、`codex-rs/Cargo.lock` 16,230 行、`sdk/python/src/openai_codex/generated/v2_all.py` 9,454 行、`codex-rs/tui/tests/fixtures/oss-story.jsonl` 8,041 行等）。

### 6.3 `codex-rs/core/tests/suite/mod.rs` 的 `#[ctor]` 二进制分派（串起 §3 / §6 / §10）

`codex-rs/core/tests/suite/mod.rs` 开头有一个 `#[ctor] pub static CODEX_ALIASES_TEMP_DIR`，在**任何测试运行之前**调用 `configure_test_binary_dispatch("codex-core-tests", ...)`。作用是：让**同一个测试二进制**根据 arg0 / argv1 伪装成不同的一方二进制，从而免去为测试单独构建 helper。

| 触发条件 | 分派到 | 常量来源 |
| ---- | ---- | ---- |
| `argv1 == CODEX_CORE_APPLY_PATCH_ARG1` | `apply_patch` | `codex_apply_patch` |
| `argv1 == CODEX_ARG0_EXEC_HELPER_ARG1`（仅 unix） | exec helper | `codex_exec_server` |
| `argv1 == CODEX_FS_HELPER_ARG1` | fs helper | `codex_exec_server` |
| `exe_name == CODEX_LINUX_SANDBOX_ARG0` | `codex-linux-sandbox` | `codex_sandboxing::landlock` |
| 其余 | `InstallAliases`（在临时目录里铺一组别名） | — |

文件里的原注释写得很直白：*"It allows the test binary to behave like codex and dispatch to apply_patch and codex-linux-sandbox based on the arg0."*，紧接着一句关键限制：**`NOTE: this doesn't work on ARM`**。

> [!TIP]
> **这条机制解释了本文另外两节的设计**：
> - **§3.2**：`core_apply_patch_cli_integration` 之所以要 `max-threads = 1`，正是因为这些用例会通过上面的分派拉起完整 Codex turn + `apply_patch` 子进程。
> - **§10**：分派在 ARM 上失效，所以 CI 必须**单独构建运行时 helper 并用环境变量注入**——`.github/workflows/rust-ci-full-nextest-platform.yml:386-404` 在 Linux 上注入 `CARGO_BIN_EXE_codex-linux-sandbox` / `CARGO_BIN_EXE_codex_linux_sandbox`，在 Windows 上注入 `CARGO_BIN_EXE_codex_windows_sandbox_setup` / `CARGO_BIN_EXE_codex_command_runner`。

---

## 7. insta 快照测试（`AGENTS.md` → `### Snapshot tests`）

全仓 **681 个 `.snap`**（E1：`git ls-files "*.snap" | wc -l`），分布极不均衡：

| crate | `.snap` 数 | 占比 |
| ---- | ---: | ---: |
| `codex-rs/tui` | **629** | 92.4% |
| `codex-rs/core` | **51** | 7.5% |
| `codex-rs/cli` | **1** | 0.1% |

`codex-rs/core` 的 51 个快照又分布在四处：`codex-rs/core/tests/suite/snapshots/`（**38**）、`codex-rs/core/src/context/world_state/snapshots/`（**9**）、`codex-rs/core/src/guardian/snapshots/`（**3**）、`codex-rs/core/src/session/snapshots/`（**1**）。

> [!NOTE]
> **勘误：协议层一个 insta 快照都没有。** 第一版写"主要集中在 TUI 与协议层（序列化结果）"是未经计数的推断——`git ls-files '*.snap' | grep -i protocol` 结果为空。
>
> 协议层的一致性校验走的是**另一条路：schema fixture 对拍**，不是 insta。见 `codex-rs/.config/nextest.toml:44` 的 `typescript_schema_fixtures_match_generated` / `json_schema_fixtures_match_generated`（它们和另外三个 codegen 测试一起被归入 `app_server_protocol_codegen` 串行组），对拍的 fixture 落在 `codex-rs/app-server-protocol/schema/json/*.json`。

> [!IMPORTANT]
> **本节是对第一版的整体订正。** 第一版写"`AGENTS.md` 未提及快照更新流程 / 两者如何调和需要确认 / 不要贸然用 `cargo insta`"——**这是本文档的调研失误（漏读了 `AGENTS.md` 的 `### Snapshot tests` 一节），不是上游的规范缺口。** 上游规范完整且明确，下面照录。

### 7.1 强制要求：UI 变更必须带快照覆盖

`AGENTS.md` 原文的 **Requirement**：

> 任何影响**用户可见 UI**（包括新增 UI）的改动，**必须**包含相应的 `insta` 快照覆盖——没有就新增快照测试，有就更新既有快照。快照更新要作为 PR 的一部分被 review 并 accept，这样 UI 影响易于评审、后续 diff 保持可视化。

**本文档第一版漏了这条强制要求**，这里补上：它和"智能体逻辑变更必须写集成测试"是同一层级的硬约束。（第一版写"三份文档都漏了"，但本轮只核验了本篇，另两份不在核验范围内，故收窄表述。）

### 7.2 更新快照的标准流程

当 UI 或文本输出是**有意**改变时，按下面四步走：

| 步骤 | 命令 |
| ---- | ---- |
| 1. 跑测试生成新快照 | `just test -p codex-tui` |
| 2. 查看待处理项 | `cargo insta pending-snapshots -p codex-tui` |
| 3. 审阅改动 | 直接读仓库里生成的 `*.snap.new` 文件，或 `cargo insta show -p codex-tui path/to/file.snap.new` |
| 4. **确认要接受本 crate 全部新快照后**才执行 | `cargo insta accept -p codex-tui` |

工具没装的话：`cargo install --locked cargo-insta`。（`AGENTS.md` 顶部规则列表也把 `cargo-insta` 与 `just`、`rg` 并列，要求"运行本文指令前先装好"。）

### 7.3 依赖事实（为什么上面那条命令链是通的）

| 事实 | 出处 |
| ---- | ---- |
| `insta = "1.46.3"`，声明在 `[workspace.dependencies]`，**不开任何 feature** | `codex-rs/Cargo.toml:339` |
| 消费者共 **4 个，全部在 `[dev-dependencies]`** | `codex-rs/core/Cargo.toml:150`、`codex-rs/tui/Cargo.toml:159`、`codex-rs/cli/Cargo.toml:114`、`codex-rs/cloud-tasks/Cargo.toml:44` |
| `cargo-insta` **不在 `codex-rs/Cargo.lock` 中** | 符合"全局 `cargo install`"的设计，不作为 crate 依赖 |
| `justfile` 里**没有**任何快照相关 recipe | `grep insta justfile` 只命中 `install` 段与注释 |
| 全仓**没有 `expect-test`** | `grep -rn expect-test --include=Cargo.toml codex-rs` 零命中——快照方案是单一的 |

> [!NOTE]
> 这几条合起来回答了一个自然的疑问：**既然 `insta` 没开 `cli` feature、`justfile` 也没有快照 recipe，`AGENTS.md` 给的那条 `cargo insta pending-snapshots / show / accept` 命令链靠什么成立？** 答案是 insta 1.x 的库与 CLI 本就分离——`cargo-insta` 是独立安装的**外部可执行文件**，不需要被依赖方开 feature。**所以规范里的命令链是通的，文档没有虚构**；`just` 里没有对应 recipe 也是有意为之，因为这三个子命令不跑测试（见 §7.2 末尾）。
>
> 同时也说明**为什么快照只可能出现在那 4 个 crate**——这正是 §7 开头实测分布（tui 629 / core 51 / cli 1）的直接解释；`cloud-tasks` 虽然声明了 `insta`，但目前一个 `.snap` 都没有。

> **"禁止 `cargo test`"与 `cargo insta` 的关系（第一版认为是未解决的张力，其实规范已经给了答案）**：
> **生成**快照走 `just test`（因此仍然遵循仓库默认的 nextest 配置），**审阅与接受**走 `cargo insta pending-snapshots` / `show` / `accept`——后面这三个子命令**不运行测试**，只是对已经落盘的 `.snap.new` 文件做查看和改名。两者不冲突。
>
> 注意规范给的是 `cargo insta accept`，**不是** `cargo insta review`，也不是 `INSTA_UPDATE=always`。

---

## 8. 跨操作系统测试与 `$remote-tests`

`AGENTS.md` → `## Platform Support`：

> "Tests and features must support Linux, macOS and Windows unless feature is explicitly OS-specific."

同节还指出，app-server 与 exec-server 可以跑在**不同操作系统**上，这类配置的集成测试细节见 **`$remote-tests` skill**。

平台专属测试的例子：`codex-rs/core/src/exec_policy_windows_tests.rs`、`windows-sandbox-rs` 的 `legacy_*` 测试。

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
| app-server 起服务 | 见下方警告：**用 `TestAppServer::builder().build()`**（除非该测试自定义 `$CODEX_HOME/environments.toml` 或运行时定义环境） |
| app-server 起 thread | `TestAppServer::send_thread_start_request_with_auto_env()`，并把 `ThreadStartParams.environments` 留为 `None` |

> [!WARNING]
> **skill 文本已落后于代码。** `.codex/skills/remote-tests/SKILL.md:25` 原文写的是 `TestAppServer::new_with_auto_env()`，**但该 API 在当前代码基线中已不存在**——`rg new_with_auto_env` 扫全仓 5,788 个文件，除本文档自身外**零命中**。
>
> 实际构造入口是 `pub fn builder() -> TestAppServerBuilder`（`codex-rs/app-server/tests/common/test_app_server.rs:176`），终结于 `build()`（`codex-rs/app-server/tests/common/test_app_server.rs:1891`）或 `build_initialized()`（`codex-rs/app-server/tests/common/test_app_server.rs:1874`）；**auto-env 是默认开启的**（`build()` 的文档注释：*"Builds a server with a temporary CODEX_HOME and automatic environment by default."*），需要关掉时用 `TestAppServerBuilder::without_auto_env()`（`codex-rs/app-server/tests/common/test_app_server.rs:1812`）。
>
> 所以：**写新测试以 `AGENTS.md` 的 `## Tests` → `### Integration tests` → `#### app-server integration testing` 为准**（即 §4A.5 给出的 `TestAppServer::builder().build()`），skill 里的旧签名照抄会编译不过。

### 8.3 skip 宏：skill 讲 5 个，`core_test_support` 实有 8 个

某个远程执行器配置下跑不过时，**只在该配置下跳过**。宏支持理由字符串的就写上，方便后来人：

| 宏 | 用于 |
| ---- | ---- |
| `skip_if_target_windows!` | Windows target 行为 |
| `skip_if_wine_exec!` | Wine-exec runner 的限制 |
| `skip_if_host_windows!` | Windows 宿主机限制 |
| `skip_if_remote!` | 仅本地有意义的测试行为 |
| `skip_if_no_remote_env!` | 仅远程有意义的测试行为 |

> skill 明确：**优先写在所有 host/target 组合下都能跑的测试**；让测试兼容各配置最常见的改动见 `$path-types` skill。

> [!NOTE]
> **口径说明：上表 5 个是 `$remote-tests` skill 明文列出的（`.codex/skills/remote-tests/SKILL.md:40-44`），但 `core_test_support` 实际定义了 8 个 `skip_if_*` 宏**（全在 `codex-rs/core/tests/common/lib.rs`）。另外 3 个与远程执行无关，所以 skill 没提，但写测试时同样用得上：
>
> | 宏 | 位置 | 用于 |
> | ---- | ---- | ---- |
> | `skip_if_sandbox!` | `codex-rs/core/tests/common/lib.rs:537` | 沙箱环境下跑不了的行为 |
> | `skip_if_no_network!` | `codex-rs/core/tests/common/lib.rs:563` | 需要真实网络的用例 |
> | `skip_if_test_condition!` | `codex-rs/core/tests/common/lib.rs:585` | 通用条件跳过（前三者的底座） |
>
> 五个远程相关宏的定义位置依次是 `:601`（`skip_if_remote`）、`:620`（`skip_if_no_remote_env`）、`:636`（`skip_if_wine_exec`）、`:655`（`skip_if_target_windows`）、`:710`（`skip_if_host_windows`）。同一文件里还有一个 `codex_linux_sandbox_exe_or_skip!`（`:674`）——它也有跳过语义，但不是 `skip_if_` 前缀，按"`skip_if_*` 宏"口径不计入 8 个。

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

### 8.5 全景：跨 OS / 远程执行实际有 **4 套**独立机制

`$remote-tests` 只覆盖了其中一套（下表第 4 条）。四者的目标、载体、开关各不相同，混在一起读会很困惑：

| # | 机制 | 解决什么 | 载体与开关 |
| ---- | ---- | ---- | ---- |
| 1 | **Bazel RBE（远程构建执行）** | 把**构建动作**扔到远端集群，拉高并发 | `rbe.bzl:39` 的 `rbe_platform_repository` 生成 platform，其 `exec_properties` 含 `"container-image": "docker://docker.io/mbolin491/codex-bazel@sha256:{image_sha}"`（`rbe.bzl:27`）；`.bazelrc:83-85` 配 `--strategy=remote`、`--extra_execution_platforms=//:rbe`、`--jobs=800`，endpoint 走 BuildBuddy 的 `grpcs://` |
| 2 | **"构建远程 / 测试本地"的拆分** | 平台专属测试必须在**真实平台**上跑 | `.bazelrc:168-200`。原注释：*"We have platform-specific tests, so we want to execute the tests on all platforms using the strongest sandboxing available on each platform."* → macOS 用 `common:ci-macos --strategy=TestRunner=darwin-sandbox,local`；Windows 用 `common:ci-windows-cross --host_platform=//:rbe` + `--strategy=TestRunner=local` + `--platforms=//:windows_x86_64_gnullvm`（构建在 Linux RBE，测试留在 Windows runner） |
| 3 | **Wine：在 Linux 上跑 Windows 二进制** | 免去真 Windows 机器，覆盖 Windows target 行为 | `defs.bzl:256-258` 的 `run_tests_with_wine_exec` 参数，实现在 `defs.bzl:579-584`。**全仓仅两个 crate 开启**：`codex-rs/core/BUILD.bazel:26` 与 `codex-rs/app-server/BUILD.bazel:15` |
| 4 | **Docker remote-env**（即 `$remote-tests`） | 验证 app-server / exec-server **拆分部署** | `scripts/test-remote-env.sh` 导出 `CODEX_TEST_REMOTE_ENV`（`:91`）与 `CODEX_TEST_REMOTE_EXEC_SERVER_URL`（`:88`）；CI 侧是 `.github/workflows/rust-ci-full-nextest-platform.yml:323-333` 的 "Set up remote test env (Docker)" 步骤，条件 `if: runner.os == 'Linux' && inputs.remote_env` |

> [!IMPORTANT]
> **四套机制里只有第 4 套会在 CI 上被打开，而且只有一条通道开**：`.github/workflows/rust-ci-full.yml:481` 的 `remote_env: true` 是全仓**唯一**的开启点（即 §10.2 表里的 "Linux x64（remote-env）"）。其余四条平台通道跑的都是普通 nextest。
>
> 而机制 1-3 全在 **Bazel 侧**——也就是 §10.1 说的"PR 上的 Rust 测试信号来自 Bazel"那条通道。**Cargo 侧完全看不到它们**，这也引出了下面 §8.6。

关于 Wine 这套（机制 3）还有两点值得知道：

- 专用测试目录是 `codex-rs/core/tests/remote_env_windows/`，其 `codex-rs/core/tests/remote_env_windows/README.md:15` 写着：*"No system Wine is required. Every process gets a fresh `WINEPREFIX` and isolated wineserver."*——**不依赖系统装的 Wine，每个进程一份干净前缀**，所以本地不需要预装任何东西。
- Wine 与 PowerShell 的版本由 `bazel/modules/wine.MODULE.bazel` 按 sha256 固定：**Wine 11.0**（`wine-11.0-amd64-wow64`）与 **PowerShell 7.2.24**。文件里的注释解释了为什么不升 PowerShell：*7.4.16 与 7.6.2 在固定的 Wine 11 运行时下 CLR 启动会失败，7.2.24 可以跑通*。

### 8.6 两条"Bazel 绿 ≠ Cargo 绿"的机制

> 这两条都是**单向漏检**：Bazel 通过不代表 Cargo 通过，反之亦然。因为 PR 的阻断信号来自 Bazel（§10.1），而本地 `just test` 走 Cargo，这个差异很容易咬人。

**1. Bazel CI 有一份独立的测试跳过清单，Cargo 侧没有对应物。**

`.bazelrc:166` 与 `.bazelrc:197` 通过 `--test_env=CODEX_BAZEL_TEST_SKIP_FILTERS=...` 在 Windows 通道上跳过若干用例（如 `suite::code_mode::code_mode_can_call_hidden_dynamic_tools`、`tests::windows_tests::conpty_ctrl_c_interrupts_powershell_foreground_child`、`command_safety::powershell_parser::tests::`）。**nextest 侧没有任何等价机制**——同样的用例在 Cargo 全量 CI（§10）的 Windows 通道上是照跑的。

`.bazelrc:194-196` 还自带一句给改动者的警告：*"Native Windows CI still covers the PowerShell parser-process tests. The cross-built gnullvm binaries currently hang in those tests when run on the Windows runner. **This replaces the Windows skip list, so retain its exclusions.**"*——`ci-windows-cross` 的清单是**整体替换**而非追加，改它时必须把 `ci-windows` 的排除项一并抄进去。

**2. Bazel 的 clippy 默认漏 lint 测试代码。**

`defs.bzl:350` 与 `defs.bzl:410`（以及分片集成测试的 `:535`、`:647`）给**单元测试的**底层 `rust_test` 打了 `tags = ["manual"]`（例外：`defs.bzl:575` 的直出集成测试不带该标签），因此 `bazel build --config=clippy //...` 根本不会展开到它们。必须走 `scripts/list-bazel-clippy-targets.sh`，它用 `bazel query 'kind("rust_test rule", attr(tags, "manual", //codex-rs/...))'`（`scripts/list-bazel-clippy-targets.sh:25-28`）把这些 manual target 显式列出来。脚本 `:48-51` 的注释说得很清楚：

> *"`--config=clippy` on the `workspace_root_test` wrappers does not lint the underlying `rust_test` binaries. Add the internal manual `*-unit-tests-bin` targets explicitly so inline `#[cfg(test)]` code is linted like `cargo clippy --tests`."*

⇒ **`bazel build --config=clippy //...` 跑绿了，不等于测试代码没有 clippy 问题**（§1 数过，仓库里有 1,448 处 `#[cfg(test)]`，全靠这条路径才被 lint 到）。

**附带：insta 快照路径在 Bazel 下是"伪造"出来的。** `defs.bzl:260-266` 给测试环境设 `INSTA_WORKSPACE_ROOT="."` 与 `INSTA_SNAPSHOT_PATH="src"`，`defs.bzl:340-347` 再用 `--remap-path-prefix=../codex-rs=` / `--remap-path-prefix=codex-rs=` 把 `file!()` 展开的路径改写成 Cargo 风格（如 `tui/src/...`）。这解释了**为什么同一批 `.snap` 文件在 Cargo 和 Bazel 两套系统下都能被找到**——不是 insta 自己适配的，是构建规则把路径对齐到了 Cargo 的形状。

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
| `.github/workflows/bazel.yml`（经 `.github/workflows/blocking-ci.yml`） | 每个 PR + push main | **PR 上的 Rust 测试信号来自这里**；Windows gnullvm 按 4 片分 shard。⚠️ 它跑的**不是** nextest，有独立的跳过清单与 clippy 覆盖缺口，见 §8.6 |
| `.github/workflows/rust-ci-full.yml`（经 `.github/workflows/postmerge-ci.yml`，或**分支名含 `full-ci` 时自触发**） | push main（经 postmerge-ci）+ `push: branches: ["**full-ci**"]` + `workflow_dispatch` | 完整 Cargo nextest 矩阵——**不阻断 PR** |

> [!NOTE]
> **勘误：`.github/workflows/rust-ci-full.yml` 不是"只在 push main"。** 它自己的 `on:` 块（`.github/workflows/rust-ci-full.yml:2-9`）有三个触发器：
>
> ```yaml
> on:
>   workflow_call:
>   push:
>     branches:
>       # Main pushes enter through postmerge-ci. Keep this opt-in branch trigger
>       # for developers who want the full suite before merging.
>       - "**full-ci**"
>   workflow_dispatch:
> ```
>
> **这是一个很有用的能力，值得记住**：把分支名起成包含 `full-ci` 的形式（例如 `<你的名字>/full-ci-sandbox-refactor`），**推上去就会在合并前跑完整矩阵**，不必等 postmerge 才发现平台相关的失败。yml 里的注释明说这就是它的设计意图。另外 `workflow_dispatch` 也允许手动对任意分支触发。
| `.github/workflows/rust-ci.yml`（经 `.github/workflows/blocking-ci.yml`） | 每个 PR | **不跑 codex-rs workspace 的测试**，只有 fmt / bench-smoke / cargo-shear / argument-comment-lint |

> [!NOTE]
> **一个容易让人自查时困惑的细节**：`.github/workflows/rust-ci.yml` 里的 `argument_comment_lint_package` job **内部确实跑了 `cargo test`**（`.github/workflows/rust-ci.yml:160`），旁边还有 `python3 -m py_compile`（`:155`）与 `python3 -m unittest discover`（`:157`）。但它的作用域是 `tools/argument-comment-lint` 这个**独立于 codex-rs workspace 的 package**（触发条件也只看 `tools/argument-comment-lint/*` 与两个 workflow 文件的改动，见 `:47`）。所以"PR 上不跑 codex-rs 测试"的结论**成立**。

### 10.2 archive + partition 的两段式

`.github/workflows/rust-ci-full.yml` 调用 `.github/workflows/rust-ci-full-nextest-platform.yml` **5 次**，每次一个平台通道。这个 reusable workflow 分两段：

1. **`archive` job**（`.github/workflows/rust-ci-full-nextest-platform.yml:180-184`）：

   ```bash
   cargo nextest archive \
     --target <target> \
     --cargo-profile <profile> \
     --timings \
     --archive-file "nextest-<artifact_id>.tar.zst"
   ```

   把编译好的测试二进制打包上传（Linux/Windows 还额外构建 sandbox / command-runner 等运行时 helper）。**`--target` 不能省**——Windows arm64 通道正是靠它在 windows-x64 上交叉编译出 `aarch64-pc-windows-msvc` 的归档。
2. **`shard` job**（`:373-381`）：`shard: [1, 2, 3, 4]` 矩阵，下载归档后回放：

   ```bash
   cargo nextest run --no-fail-fast \
     --archive-file "${archive_file}" \
     --workspace-remap "${workspace_root}" \
     --partition "hash:<shard>/4"
   ```

   **`--workspace-remap` 是归档回放能成立的另一半**：归档里记录的是 archive job 的源码路径，shard job 在另一台机器上解包后必须把 workspace 根重定位到本机路径。

固定参数：

- cargo profile **`ci-test`**
- **`NEXTEST_STATUS_LEVEL: leak`**
- JUnit 输出在 **`target/nextest/default/junit.xml`**——路径里的 `default` 印证了 §2.1 的说法：**CI 用 default profile，本地 `just test` 用 local**

五个平台通道：

| 通道 | runner 归属 | target | 备注 |
| ---- | ---- | ---- | ---- |
| macOS aarch64 | **GitHub 托管** `macos-15-xlarge` | `aarch64-apple-darwin` | 五条通道里唯一的 GitHub 托管 runner |
| Linux x64（remote-env） | **自托管 runner group** `<repo>-runners` / label `<repo>-linux-x64` | `x86_64-unknown-linux-gnu` | `remote_env: true`——即 §8 的远程执行器测试 |
| Linux arm64 | **自托管 runner group** `<repo>-runners` / label `<repo>-linux-arm64` | `aarch64-unknown-linux-gnu` | |
| Windows x64 | 自托管 windows-x64 | `x86_64-pc-windows-msvc` | `test_threads: 8` |
| Windows arm64 | 自托管 windows-arm64 | `aarch64-pc-windows-msvc` | **归档在 windows-x64 上交叉编译**，再到原生 arm64 上回放；`test_threads: 8` |

> **总结：五条通道里只有 macOS 用 GitHub 托管 runner，其余四条全部跑在自托管 runner group 上。**

> [!NOTE]
> **勘误：两条 Linux 通道不是 GitHub 托管的 `ubuntu-24.04` / `ubuntu-24.04-arm`。** 关键在 reusable workflow 的 `runs-on` 表达式（`.github/workflows/rust-ci-full-nextest-platform.yml:277`）——它**优先取 `runner_group`**，只在其为空时才回落到 `runner`：
>
> ```yaml
> runs-on: ${{ inputs.runner_group != '' && fromJSON(format('{{"group":"{0}","labels":"{1}"}}', inputs.runner_group, inputs.runner_labels)) || inputs.runner }}
> ```
>
> 而 `.github/workflows/rust-ci-full.yml:472-480`（`tests_linux_x64_remote`）与 `:486-495`（`tests_linux_arm64`）都传了 `runner_group: ${{ github.event.repository.name }}-runners` 加上对应的 `runner_labels`，所以 `runner: ubuntu-24.04` 在这两条通道里**从不生效为实际 runner**，仅用作缓存 key（`ARCHIVE_CACHE_RUNNER`）与回落值。
>
> 教训：读了 yml 不等于读懂了 `runs-on` 表达式——本节整体证据等级是 E2/E3（确实读了工作流），但**等级正确不代表解析正确**。

固定环境（archive 与 shard 两段共用）还有一条值得注意：

- **`RUST_MIN_STACK: "8388608" # 8 MiB`**（`.github/workflows/rust-ci-full-nextest-platform.yml:409`）——与本地 `justfile:7` 的 `rust_min_stack := "8388608"` **完全一致**。栈大小这一项本地与 CI 没有差异。
- **Cargo** profile **`ci-test`**（注意：不是 nextest profile，见 §3.1 的辨析）定义在 `codex-rs/Cargo.toml:566-570`：`inherits = "test"`、`opt-level = 0`、`debug = "limited"`，注释写着 *"Reduce binary size to reduce disk pressure."*——与 §2.1 那条"不要用 `--all-features` 做常规运行、会撑爆 `target/`"是同一个主题：**测试构建产物的磁盘压力是这个仓库的实际约束**。

> [!WARNING]
> **别把上面这条推广成"本地与 CI 完全一致"**：栈大小一致、超时与重试一致，但 **nextest profile 不同**（本地 `local` / CI `default`），app-server 集成测试的并发度是 4 vs 1；**Cargo profile 也不同**（本地默认 `test` / CI `ci-test`）；CI 还额外设了 `RUST_BACKTRACE=1` 与 `NEXTEST_STATUS_LEVEL=leak`。完整对照见 §3.4 与 §3.5。

> **含义**：单个平台通道的测试是 4 路并行的，所以 §3 里那句"30s slow-timeout 要与分片 CI 的超时预算对齐"是有出处的——分片压缩了单片墙钟时间，但没有放宽单测超时。

---

## 11. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `TestCodexBuilder` 的完整 builder 方法 | E1 | `codex-rs/core/tests/common/test_codex.rs`（分段读） |
| 基准测试的**历史基线数值与回归判据** | E1 | 组织方式已有明文（见下），基线数值本身未见于仓库 |
| `scripts/test-remote-env.sh` 的实现细节 | E1 | 该脚本 |
| `.codex/skills/` 下其余 skill 的内容 | E1 | 见 `development_workflow.md` §2.6 |

> **本轮从本表移除两项**：
> - **`zsh` 的用途**——它不是"测试子目录"而是一个 DotSlash 清单文件，用途由文件头注释明确自述，已写入 §6.2，不属未覆盖。
> - **基准测试的组织方式（降级为 E2，不再是空白）**——覆盖面已在 §1 实测：**全仓只有 1 个 Cargo bench target**（`codex-utils-image` 的 `prompt_images`）。`AGENTS.md` 的 `### Benchmarks` 已明文："*cargo benchmarks can be run with `just bench`, use the divan crate to write new ones. Use `just bench-smoke` to dry-run the benchmark for a single iteration to ensure it works.*"；`justfile:95-113` 进一步给出四个 recipe 的完整语义：`bench`（`cargo bench --workspace --bench '*'`）、`bench-smoke`（`just bench -- --test`）、`bench-e2e`（`bazel test --compilation_mode=opt ... //codex-rs:e2e-benchmarks`）、`bench-e2e-smoke`（fastbuild + `--test_arg=--test`）。**真正未覆盖的只剩基线数值与回归判据**，故收窄为上表那一行（E1）。

---

## 12. 相关文档

- [开发流程](./development_workflow.md) — 完整的改完代码后动作、`.codex/skills/` 清单
- [智能体核心循环](./core_agent_loop.md) — 什么算"智能体逻辑变更"
- [构建与发布](./build_and_release.md) — CI 编排结构（`blocking-ci` / `postmerge-ci`）与 Bazel
- [TUI 开发指南](./tui_guide.md) — TUI 测试的组织方式
