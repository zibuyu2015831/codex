---
title: Codex 构建与发布
summary: 描述 Cargo 与 Bazel 的真实分工（Bazel 是 PR 主校验路径，发布二进制由 Cargo 构建）与双锁同步义务、hermetic LLVM 工具链与补丁机制、由 blocking-ci/postmerge-ci 两个入口编排的 27 个 CI 工作流、repo-checks 的硬性仓库规则、rust-release.yml 的 15 个 job 与多平台发布产物矩阵、DotSlash/winget/npm 等安装通路，以及 compile_data 这类 Bazel 专属陷阱。
keywords: codex | build | release | bazel | cargo | ci | blocking-ci | repo-checks | module-bazel | hermetic-toolchain | compile-data | dotslash
scope: openai/codex 的构建系统、CI 工作流与发布流程
related_files: MODULE.bazel | justfile | package.json | scripts/format.py | .github/workflows | docs/install.md | README.md | AGENTS.md
dependencies: dev_docs/development_workflow.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 构建与发布

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 工作流内容、锁文件规模、MODULE.bazel 内容、发布 job 拓扑为 E2/E3（读取 yml 与配置）；文件计数为 E1

> [!NOTE]
> **第一版勘误（本次修订）**：初版把 Bazel 写成"发布构建系统"、把 `rust-release-prepare.yml` 当成发布打标入口、把 `rust-ci.yml` 当成 PR 上的测试通道——三条都是错的，本文已按工作流实际内容重写（见 §1、§4、§5）。

---

## 1. 双构建系统

| | **Cargo** | **Bazel** |
| ---- | ---- | ---- |
| 定位 | 日常开发主用；**发布二进制的实际构建者** | **PR 合并前的主校验路径**（test + clippy） |
| 清单 | `codex-rs/Cargo.toml` | `MODULE.bazel`（16,677 字节） |
| 锁文件 | `codex-rs/Cargo.lock`（367,304 字节） | `MODULE.bazel.lock`（**1,547,127 字节**） |
| 运行 | `just codex`、`just test` | `just bazel-codex`、`just bazel-test` |
| 发布 | `rust-release.yml` / `rust-release-windows.yml` 里的 `cargo build --target <t> --release` | 不参与发布产物构建；`bazel.yml` 的 `verify-release-build` job 只做**可构建性校验** |

> [!IMPORTANT]
> **纠正第一版的判断**：`grep -c bazel .github/workflows/rust-release.yml` 结果为 **0**——发布工作流完全不碰 Bazel。产物由 `cargo build --target "$target" --release --timings` 产出（`rust-release.yml` 的 build job；Windows 在 `rust-release-windows.yml` 里同款）。
>
> Bazel 的真实定位写在 `.github/workflows/README.md` 开头：**"`bazel.yml` is the main pre-merge verification path for Rust code."** 它由 `blocking-ci.yml` 作为第一个 reusable workflow 调用，跑 Bazel `test` 与 Bazel `clippy`（包括为 lint 内联 `#[cfg(test)]` 代码而生成的测试二进制）。
>
> `bazel.yml` 里确实有 `verify-release-build` job，但它只是"验证 release 配置能构建"，不产出发布资产。

> Bazel 锁文件是 Cargo 锁文件的 **4.2 倍大**，反映出 Bazel 侧管理的是包含 C++ 工具链在内的完整 hermetic 依赖树。

### 1.1 双锁同步义务（强制）

```
改了 Cargo.toml 或 Cargo.lock
        ↓
在仓库根跑 just bazel-lock-update      （= bazel mod deps --lockfile_mode=update）
        ↓
把更新后的 MODULE.bazel.lock 放进同一个 change
        ↓
CI 用 just bazel-lock-check 校验漂移
```

这是 `AGENTS.md` **顶部规则列表**中 "If you change Rust dependencies (`Cargo.toml` or `Cargo.lock`), run `just bazel-lock-update`" 一条的明文要求（grep 关键词：`bazel-lock-update`）。**CI 会验证锁文件漂移，忘了跑就会挂。**

### 1.2 `compile_data` 陷阱（`AGENTS.md` 顶部规则列表，grep `compile_data`）

> [!WARNING]
> **Bazel 不会自动把源码树里的文件提供给编译期 Rust 文件访问。**
>
> 如果你新增了 `include_str!`、`include_bytes!`、`sqlx::migrate!` 或类似的**构建期文件/目录读取**，必须更新该 crate 的 `BUILD.bazel`（`compile_data`、`build_script_data` 或 test data）。
>
> **否则 Cargo 能过，Bazel 会失败。** 这是本仓库最典型的"本地绿、CI 红"来源。

现实中的例子：`codex-rs/sandboxing/src/seatbelt.rs:21-24` 用 `include_str!` 内嵌三份 `.sbpl` 策略文件。

---

## 2. Bazel 侧的特殊性（E3）

`MODULE.bazel` 头部揭示了几件事：

```python
module(name = "codex")
bazel_dep(name = "bazel_skylib", version = "1.9.0")
bazel_dep(name = "platforms", version = "1.0.0")
bazel_dep(name = "llvm", version = "0.8.11")
```

### 2.1 hermetic LLVM + 上游补丁

`MODULE.bazel` 里共有 **6 处 `single_version_override`**（第一版只写了 2 处，漏了 4 处）：

| 被 override 的模块 | 说明 |
| ---- | ---- |
| `llvm` | hermetic LLVM 工具链，3 个补丁 |
| `abseil-cpp` | Windows gnullvm 线程标识 |
| `rules_cc` | rusty_v8 自定义 libc++ |
| `rules_rs` | build script 依赖注解；**同时把版本钉死在 `version = "0.0.96"`** |
| `bzip2` | Windows 栈参数 |
| `xz` | Windows 栈参数 |

此外 `rules_rust` 通过 `use_extension(...).patch(...)` 单独打了一批补丁（不算在 6 处 override 内）。

其中几条补丁的注释说明了原因：

| 补丁 | 原因（注释要点） |
| ---- | ---- |
| `llvm_rusty_v8_custom_libcxx.patch` | Codex 的自定义 libc++ 需求 |
| `llvm_windows_arm64_powl.patch` | Windows ARM64 |
| `llvm_windows_mingw_compat.patch` | Windows gnullvm 运行时需求，尚未进入上游 |
| `abseil_windows_gnullvm_thread_identity.patch` | Abseil 选的 MinGW pthread TLS 路径与 hermetic windows-gnullvm 工具链不匹配，强制走可移植的 C++11 thread-local 路径 |

补丁存放在仓库根的 `patches/` 目录：**19 个 `.patch` + 1 个 `BUILD.bazel`**（共 20 个条目——第一版写的"20 个文件"口径没区分补丁与 BUILD 文件）。19 个补丁里有 **10 个**文件名带 `windows` / `msvc` / `gnullvm` / `mingw`。

> **含义**：这套构建**不依赖开发机上的系统编译器**，而是自带 LLVM。这也解释了为什么 `MODULE.bazel.lock` 有 1.5 MB。**Windows 支持是补丁的主要来源。**

### 2.2 Bazel 目录结构

| 目录 | 内容 |
| ---- | ---- |
| `bazel/modules` | 模块定义 |
| `bazel/platforms` | 平台定义 |
| `bazel/rules` | 自定义规则 |
| `patches/` | 上游补丁（19 个 `.patch` + 1 个 `BUILD.bazel`，E1） |
| `third_party/` | 第三方（13 个受版本管理的文件，E1） |
| `rbe.bzl` | 远程构建执行配置 |
| `workspace_root_test_launcher.sh.tpl` / `.bat.tpl` | 测试启动器模板（Unix / Windows） |

---

## 3. Bazel 相关 just 任务

| 命令 | 作用 |
| ---- | ---- |
| `just bazel-lock-update` | 刷新 `MODULE.bazel.lock` |
| `just bazel-lock-check` | 校验漂移（Unix 走 `scripts/check-module-bazel-lock.sh`，Windows 走 `--lockfile_mode=error`） |
| `just bazel-codex <args>` | Bazel 构建并运行 codex |
| `just bazel-code-mode-host <args>` | Bazel 构建并运行 code-mode host |
| `just bazel-test` | `bazel test --test_tag_filters=-argument-comment-lint //... --keep_going` |
| `just bazel-clippy` | `bazel build --config=clippy`（目标由 `scripts/list-bazel-clippy-targets.sh` 生成）——**`[unix]` 专属，Windows 上没有这个任务** |
| `just bazel-argument-comment-lint` | 自定义 Dylint 检查——**同样是 `[unix]` 专属** |
| `just argument-comment-lint` | 走预构建 linter 的入口，也是 `[unix]` 专属 |
| `just argument-comment-lint-from-source` | 从源码构建 linter 再跑（`[no-cd]`，无平台限制）——第一版漏了这条 |
| `just build-for-release` | `bazel build //codex-rs/cli:release_binaries`（**本地/校验用途；CI 发布走 Cargo，见 §5**） |
| `just bench-e2e` | `bazel test --compilation_mode=opt //codex-rs:e2e-benchmarks` |
| `just bench-e2e-smoke` | 同上但用 fastbuild，只验证 benchmark 能跑起来 |

> `just bazel-test` 显式排除了 `argument-comment-lint` 标签的测试——它由独立任务跑。

> [!WARNING]
> **平台差异**：`bazel-clippy`、`bazel-argument-comment-lint`、`argument-comment-lint` 在 `justfile` 里都带 `[unix]` 属性，**Windows 开发机上这几条任务根本不存在**。`bazel-codex`、`bazel-code-mode-host`、`bazel-lock-check`、`test`、`install`、`log` 则各有 `[unix]` / `[windows]` 两个版本。
>
> 另外 `just install` 的 `[windows]` 分支会用 winget 安装 PowerShell 7（若 `pwsh.exe` 不存在），之后才走与 Unix 相同的 `rustup show active-toolchain` + `cargo fetch`。

---

## 4. CI 工作流（27 个 yml）

`.github/workflows/` 下共 **27 个 `.yml`**（E1），另有三个非 yml 条目：`README.md`、`Dockerfile.bazel`，以及 **`zstd`——它是一个文件，不是目录**（`#!/usr/bin/env dotslash` 脚本，用途写在它自己的注释里：为 Windows runner 包装 zstd，windows-aarch64 通过 x64 模拟复用 win64 产物）。第一版把它列成"未知用途的目录"，属于误判。

### 4.1 编排结构：两个**主编排器**，但不是仅有的两个事件入口

> [!CAUTION]
> **本节上一稿的两个数字都是错的，且与本文自己别处的叙述矛盾。**
>
> 上一稿写「约 20 个是 `workflow_call:` 专用」「真正的事件入口只有两个」。实测（E4）：
>
> ```bash
> ls .github/workflows/*.yml | wc -l                              # 27  总数
> grep -lE '^  workflow_call:' .github/workflows/*.yml | wc -l    # 14  声明了 workflow_call
> ```
>
> 再逐个解析顶层 `on:` 块可得：**只声明 `workflow_call` 的有 10 个**（真正的纯 reusable），而**声明了至少一个真实事件触发器的有 17 个**：`bazel`、`blocking-ci`、`cla`、`close-stale-contributor-prs`、`issue-deduplicator`、`issue-labeler`、`issue-translator`、`postmerge-ci`、`python-runtime-release`、`python-sdk-release`、`rust-ci-full`、`rust-ci`、`rust-release-prepare`、`rust-release-zsh`、`rust-release`、`rusty-v8-release`、`v8-canary`。
>
> 「只有两个事件入口」这句话**在本文内部就已被推翻**：§4.4 明写 `v8-canary.yml` 有 `pull_request` 触发器、**每个 PR 都会跑**；§4.4 还说 `close-stale-contributor-prs.yml` 有 `cron`。**同一篇文档里前后打架，是最容易被读者信以为真的那类错误。**

准确的说法是：**`blocking-ci.yml` 与 `postmerge-ci.yml` 是两个主编排器**（它们聚合了绝大多数校验、并各自带一个 `check_ci_results.py` 聚合 job），但**它们不是仅有的事件入口**——发布、社区自动化、定时任务等 15 个工作流各有自己的触发器。两个主编排器的结构如下：

```
blocking-ci.yml        （on: pull_request + push main）—— 唯一的合并阻断入口
├── bazel.yml                 Rust 的主 pre-merge 校验（test + clippy + verify-release-build）
├── blob-size-policy.yml      大文件入库策略
├── cargo-deny.yml            依赖许可证 / 安全审计
├── codespell.yml             拼写
├── repo-checks.yml           仓库硬规则（见 §4.3）
├── rust-ci.yml               Cargo 侧的"快检查"（见 §4.2）
├── sdk.yml                   SDK
└── required                  聚合 job，跑 .github/scripts/check_ci_results.py
                              （用 always() 防止依赖失败被 GitHub 跳过成"成功"）

postmerge-ci.yml       （on: push main）—— 不阻断合并
├── rust-ci-full.yml          完整 Cargo clippy 矩阵 + 完整 nextest 矩阵 + release-profile 构建
│   └── rust-ci-full-nextest-platform.yml   （被调 5 次，见 testing_guide.md）
├── v8-canary.yml
└── results                   同款 check_ci_results.py 聚合
```

> `blocking-ci.yml` 的注释直接点明：*"This is the single entrypoint for checks that block a PR merge"*；`required` job 是"版本控制的必需检查清单"，main 分支 ruleset 应当只要求这一个。
>
> **第一版把 `blocking-ci.yml` / `postmerge-ci.yml` 混在"Rust CI"一类里，掩盖了这个编排层次。**

### 4.2 `rust-ci.yml` 到底跑什么（重要纠正）

> [!IMPORTANT]
> **`rust-ci.yml` 不跑 codex-rs workspace 的测试，也不跑 clippy。** 第一版把它当成 PR 上的测试通道，是错的。
>
> 精确说法：它确实有一个 `cargo test`，但作用域是 workspace 之外的 `tools/argument-comment-lint`（另配一个 `python3 -m unittest discover`）。codex-rs 本体的 nextest 矩阵不在这里。
>
> 它的全部内容是：
>
> | job | 内容 |
> | ---- | ---- |
> | `changed` | 用 `git diff` 自行判断改动面（`codex`/`argument_comment_lint`/`workflows`），无关改动直接放行 |
> | `general` | `cargo fmt -- --config imports_granularity=Item --check` + `just bench-smoke` |
> | `cargo_shear` | `cargo shear --deny-warnings`（cargo-shear@1.11.2） |
> | `argument_comment_lint_package` | `tools/argument-comment-lint` 自身的 Python + Rust 测试（仅当该 lint 或其 workflow 接线被改动时） |
> | `argument_comment_lint_prebuilt` | Linux / macOS / Windows 三平台跑 argument-comment-lint |
> | results | 聚合，是唯一需要标为 required 的状态 |
>
> `.github/workflows/README.md` 的原话：*"`rust-ci.yml` keeps the Cargo-native PR checks intentionally small"*，且 *"Keep `rust-ci.yml` fast enough that it usually does not dominate PR latency."*
>
> **完整的 nextest 矩阵在 `rust-ci-full.yml`**，只由 `postmerge-ci.yml` 在 push main 时触发——**它不阻断 PR**。PR 上的 Rust 测试信号来自 `bazel.yml`。

### 4.3 `repo-checks.yml`：一批硬性仓库规则（第一版完全没覆盖）

它是 `blocking-ci.yml` 的成员，因此**下面每一条都是合并阻断的**：

| 检查 | 命令 |
| ---- | ---- |
| codex-rs 各 Cargo 清单必须继承 workspace 设置 | `python3 .github/scripts/verify_cargo_workspace_manifests.py` |
| **`codex-tui` 不得直接 import `codex-core`** | `python3 .github/scripts/verify_tui_core_boundary.py` |
| Bazel clippy flag 必须与 Cargo workspace lints 一致 | `python3 .github/scripts/verify_bazel_clippy_lints.py` |
| Codex 打包器单测 | `python3 -m unittest discover -s scripts/codex_package` |
| 独立安装器单测 | `python3 -m unittest discover -s scripts/install` |
| npm 包能否 stage 出来 | `scripts/stage_npm_packages.py` |
| 根 `README.md` 只能含 ASCII + 少量白名单 Unicode | `./scripts/asciicheck.py README.md` |
| 根 README 目录（ToC）与正文一致 | `python3 scripts/readme_toc.py README.md` |
| 全仓格式化 | `just fmt-check` |
| JS/MD/YAML 格式化 | `pnpm run format` |

> **`verify_tui_core_boundary.py` 值得单独记住**：TUI 与 core 的依赖边界是被 CI 机器强制的，不是口头约定。

> [!WARNING]
> **`.github/actions/check-clean-worktree` 是"改脏工作区就红"的机器约束**：所有生成物（schema、fixtures、`MODULE.bazel.lock`、格式化结果）必须已经提交在 change 里。见 §7。
>
> **但它的覆盖面远没有本文上一稿说的那么广，需要限定：**
>
> ```bash
> grep -lr "check-clean-worktree" .github/workflows/*.yml | wc -l   # 8（共 27 个工作流）
> ```
>
> **只有 8 个工作流引用它**：`bazel.yml`、`blob-size-policy.yml`、`cargo-deny.yml`、`codespell.yml`、`repo-checks.yml`、`rust-ci.yml`、`sdk.yml`、`v8-canary.yml`——**恰好就是 `blocking-ci.yml` 聚合的那批 pre-merge 校验**。其余 19 个工作流（含 `rust-ci-full.yml` 与全部 `rust-release*`）从不引用它。
>
> 上一稿还说"`rust-ci.yml` 的每个 job"都有——**也是 5/6，不是 6/6**。该文件 6 个 job（`changed`、`general`、`cargo_shear`、`argument_comment_lint_package`、`argument_comment_lint_prebuilt`、`results`）里只有 5 处 `uses: ./.github/actions/check-clean-worktree`（`:58`、`:85`、`:110`、`:166`、`:221`），**纯聚合 job `results` 没有**（它不产生任何文件，也就无从查起）。
>
> 准确表述：**pre-merge 校验类工作流的实质性 job 末尾都查工作区干净；postmerge 全量与发布链路不查。**

### 4.4 其余工作流

| 类别 | 工作流 | 备注 |
| ---- | ---- | ---- |
| **Bazel** | `bazel.yml` | PR 主校验路径；Windows gnullvm 按 4 片分 shard；含 `verify-release-build` |
| **Cargo 快检查** | `rust-ci.yml` | 见 §4.2 |
| **Cargo 全量（postmerge）** | `rust-ci-full.yml`、`rust-ci-full-nextest-platform.yml` | 见 §4.2、`testing_guide.md` §10 |
| **发布 — Rust** | `rust-release.yml`、`rust-release-windows.yml`、`rust-release-zsh.yml`、`rust-release-argument-comment-lint.yml` | 见 §5 |
| **发布 — 其他** | `r2-release.yml`、`rusty-v8-release.yml`、`python-runtime-release.yml`、`python-runtime-build.yml`、`python-sdk-release.yml` | |
| **SDK** | `sdk.yml` | |
| **仓库检查** | `repo-checks.yml`、`blob-size-policy.yml`、`cargo-deny.yml`、`codespell.yml` | 均由 `blocking-ci.yml` 调用 |
| **V8 覆盖 canary** | `v8-canary.yml` | **不是实验性工作流**，见下 |
| **models.json 定时刷新** | `rust-release-prepare.yml` | **与发布无关**，见 §5.1 |
| **社区自动化** | `cla.yml`、`close-stale-contributor-prs.yml`、`issue-deduplicator.yml`、`issue-labeler.yml`、`issue-translator.yml` | |

**三条纠正：**

1. **`v8-canary.yml` 不是"实验性"工作流。** 它的触发器是 `workflow_call` + `pull_request: {}` + `workflow_dispatch`——**每个 PR 都会跑**，同时被 `postmerge-ci.yml` 调用。它是 rusty-v8 的覆盖 canary，是否跑重活由 `.github/scripts/v8_canary_changes.py` 判断（yml 顶部注释说明：不能用触发器级 path filter，因为 `pull_request` 与 `workflow_call` 不能共享 path filter，所以脚本是唯一的判定来源）。
2. **`close-stale-contributor-prs.yml` 与受邀制规则无关。** 它是每天 `cron: "0 6 * * *"` 跑一次，把**超过 `DAYS_INACTIVE = 14` 天没有更新**（`:24-25`）的 PR 关掉。关闭评论的措辞也是 "no updates for more than 14 days...feel free to reopen"。**它是陈旧 PR 清理，不是未受邀 PR 的自动关闭。**

3. **`rust-release-prepare.yml` 与发布无关**，见 §5.1。

> [!CAUTION]
> **关于上面第 2 条：本文上一稿把权限过滤的方向写反了**，说"作者具有 `admin`/`maintain`/`write` 权限的 PR 会被跳过"。**恰恰相反：这类作者的 PR 正是被关掉的那一批。** 依据见下方代码（`.github/workflows/close-stale-contributor-prs.yml:69-73`，E3）。
>
> 被 `continue` 跳过的是**不具备**这三种权限的作者；具备的才 `push` 进 `stalePrs` 并在后续循环里关闭。完全没有协作者身份的作者，`getCollaboratorPermissionLevel` 会抛 404，在 `:62-64` 的 catch 分支里同样被跳过。
>
> 所以工作流名字里的 "contributor" 是字面意思：**它清理的是"有写权限的自己人"留下的陈旧 PR**，外部投稿反而不在它的射程内。判定条件是「作者是真人（`pr.user.type === "User"`，机器人 PR 一律跳过）」**且**「有 write/maintain/admin 权限」**且**「14 天无更新」三者同时成立；job 级还有 `if: github.repository == 'openai/codex'`，fork 上不会跑。

```js
for (const pr of prs) {                 // :41 起的主循环，此处省略前面的新鲜度与作者类型过滤
  // ... :53-67：getCollaboratorPermissionLevel，404 时 continue（非协作者被跳过）
  const hasContributorAccess = ["admin", "maintain", "write"].includes(permission);
  if (!hasContributorAccess) {
    core.info(`Author ${pr.user.login} has ${permission} access; skipping #${pr.number}`);
    continue;
  }
  stalePrs.push(pr);
}
```

其余仍然成立的观察：

- **Windows 有独立的发布工作流**（`rust-release-windows.yml`），与 §2.1 的补丁情况一致
- **`blob-size-policy.yml`** 说明仓库对大文件入库有策略约束
- **`cargo-deny.yml`** 做依赖许可证/安全审计
- 发布链路按产物拆分：Rust 二进制、R2（对象存储）、rusty-v8、Python runtime、Python SDK 各自独立

---

## 5. 发布链路与产物

### 5.1 触发方式：打标（E2）

发布**由 tag push 触发**，不存在"准备发布的工作流"。

| tag 形态 | 触发的工作流 |
| ---- | ---- |
| `rust-v*.*.*` | `rust-release.yml`（主发布链路） |
| `codex-zsh-v*.*.*` | `rust-release-zsh.yml` |
| `python-v*` | `python-sdk-release.yml` |
| `rusty-v8-v*.*.*` | `rusty-v8-release.yml` |

`rust-release.yml` 头部注释给出的标准动作就是：

```bash
git tag -a rust-v0.1.0 -m "Release 0.1.0"
git push origin rust-v0.1.0
```

**版本一致性由 `tag-check` job 强制**（`rust-release.yml` 第一个 job，步骤名 "Validate tag matches Cargo.toml version"）：必须是 tag ref、必须匹配 `^rust-v[0-9]+\.[0-9]+\.[0-9]+(-(alpha…|beta…))?$`、且 `rust-v` 之后的版本号必须等于 `codex-rs/Cargo.toml` 里的 version。该正则需与 `.github/scripts/publish_r2_release.py` 的 `VERSION_RE` 保持同步。

> [!IMPORTANT]
> **纠正第一版**：第一版把"发布版本号的确定与打标流程"指向了 `rust-release-prepare.yml`。**这个工作流和发布毫无关系。**
>
> 它只有 57 行，触发器是 `workflow_dispatch` + `cron: "0 */4 * * *"`（每 4 小时一次），做的事是：带鉴权头 curl `${OPENAI_BASE_URL}/models?client_version=99.99.99`，把结果写进 `codex-rs/models-manager/models.json`，然后用 `create-pull-request` 开一个标题为 "Update models.json" 的 PR。名字里的 "release-prepare" 有误导性。
>
> **真正的版本/打标逻辑在 `rust-release.yml` 的 `tag-check` job。**

### 5.2 `rust-release.yml` 的 15 个 job

| 顺序 | job | 作用 |
| ---- | ---- | ---- |
| 1 | `tag-check` | 校验 tag 与 `Cargo.toml` 版本一致 |
| 2 | `build` | **矩阵：4 个 target × 2 种 bundle（`primary` / `app-server`）**，跑 `cargo build --release`；timeout 90 分钟 |
| 3 | `sign-macos-binaries` | 走受保护的 `codesigning` environment + Azure Key Vault（PKCS11）签名 |
| 4 | `package-macos` | 打包 |
| 5 | `sign-macos-dmg` | DMG 签名 |
| 6 | `finalize-macos` | 公证（notarization）与最终校验 |
| 7 | `build-windows` | 调用 `rust-release-windows.yml` |
| 8 | `argument-comment-lint-release-assets` | 调用 `rust-release-argument-comment-lint.yml` |
| 9 | `release` | 汇总产物、生成 checksum manifest、创建 GitHub Release |
| 10 | `publish-r2` | 调用 `r2-release.yml`（`releases.openai.com`） |
| 11 | **`publish-dotslash`** | 发布 DotSlash 清单 |
| 12 | **`publish-npm`** | 发布 `@openai/codex` |
| 13 | `deploy-dev-website` | |
| 14 | **`winget`** | Windows 包管理器 |
| 15 | `update-branch` | |

`build` 矩阵的 bundle 划分值得注意：

| target | `primary` bundle 的 binaries | `app-server` bundle 的 binaries |
| ---- | ---- | ---- |
| `aarch64-apple-darwin` | `codex codex-code-mode-host codex-responses-api-proxy`（+ DMG） | `codex-app-server codex-code-mode-host` |
| `x86_64-apple-darwin` | 同上（+ DMG） | 同上 |
| `x86_64-unknown-linux-musl` | 同上 **+ `bwrap`** | 同上 |
| `aarch64-unknown-linux-musl` | 同上 **+ `bwrap`** | 同上 |

> 注释明确：*"Release artifacts intentionally ship MUSL-linked Linux binaries."*

### 5.3 平台矩阵与随行资产

`README.md` 的下载表只列了 4 个 tar.gz：

| 平台 | 产物 |
| ---- | ---- |
| macOS Apple Silicon | `codex-aarch64-apple-darwin.tar.gz` |
| macOS x86_64 | `codex-x86_64-apple-darwin.tar.gz` |
| Linux x86_64 | `codex-x86_64-unknown-linux-musl.tar.gz` |
| Linux arm64 | `codex-aarch64-unknown-linux-musl.tar.gz` |

但 `release` job 实际汇总的资产比这多。它的两个 download-artifact pattern 是：

```
{aarch64,x86_64}-{apple-darwin{,-app-server},unknown-linux-musl{,-app-server},pc-windows-msvc}
{*-symbols,argument-comment-lint-*,python-runtime-wheel-*}
```

于是**第一版的平台矩阵漏了**：

- **`pc-windows-msvc`**（Windows 产物，由 `build-windows` 产出，不在上面的 4 行表里）
- 每个 target 的 **`*-symbols` 符号归档**
- **Python runtime wheel**（`python-runtime-wheel-*`）
- **`codex-zsh` 清单**：`rust-release.yml` 用 `env.CODEX_ZSH_RELEASE_TAG`（基线上钉在 `codex-zsh-v0.1.0`）从对应 Release 下载 `codex-zsh`，再由 `codex_package.zsh.resolve_zsh_bin` 取出该 target 的 zsh 二进制放进包内 `codex-resources/zsh/`；`rg` 也是同类随行资源
- `release` job 另外产出 `codex-package_SHA256SUMS` 校验清单，并把 `codex-rs/core/config.schema.json` 作为 `config-schema.json` 一并发布

每个归档内的可执行文件**文件名带平台后缀**（如 `codex-x86_64-unknown-linux-musl`），解压后通常需要重命名为 `codex`。

> 这解释了为什么 `codex-rs/cli/src/main.rs:100-105` 要显式设置 `bin_name = "codex"`——保证帮助输出不受实际文件名影响。同时 `codex-arg0` 支持按 argv[0] 分发。

### 5.4 安装通路（E2，`README.md` + `docs/install.md`）

| 方式 | 命令 / 说明 |
| ---- | ---- |
| 官方安装脚本（Mac/Linux） | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` |
| 官方安装脚本（Windows） | `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 \| iex"` |
| npm | `npm install -g @openai/codex`（`publish-npm` job） |
| Homebrew | `brew install --cask codex` |
| **DotSlash** | Release 里附带名为 `codex` 的 DotSlash 文件（`publish-dotslash` job）。`docs/install.md`：把它提交进源码管理，即可让所有贡献者不分平台使用同一版本的可执行文件 |
| **winget** | `winget` job——Windows 包管理器通路 |
| GitHub Releases | 手动下载对应平台归档 |

> 第一版漏了 **DotSlash** 与 **winget** 两条通路。

**下载源与回退**（`README.md:28`）：安装器默认从 `https://releases.openai.com/codex` 下载，元数据或资产不可用时**回退到 GitHub Releases**。可用 `CODEX_INSTALLER_USE_RELEASES_OPENAI_COM=false`（也接受 `0`/`no`）强制走 GitHub Releases。

> 这与 `r2-release.yml` 工作流对应——`releases.openai.com` 很可能由对象存储承载。

### 5.5 npm 包

仓库根 `package.json` 的包名是 `codex-monorepo`，`private: true`，只提供仓库维护脚本：

```json
"scripts": {
  "format": "prettier --check *.json *.md docs/*.md .github/workflows/*.yml **/*.js",
  "format:fix": "prettier --write ...",
  "write-hooks-schema": "cargo run --manifest-path ./codex-rs/Cargo.toml -p codex-hooks --bin write_hooks_schema_fixtures"
}
```

**发布到 npm 的 `@openai/codex` 不是这个包**，而是 `codex-cli/` 目录下的产物（7 个文件）。

`package.json` 还有一大段 `resolutions` 锁定传递依赖版本（`@modelcontextprotocol/sdk`、`esbuild`、`rollup`、`semver` 等，**共 16 项**，第一版误记为 17）——典型的供应链版本收敛做法。另有独立的 `overrides` 一项（`punycode`）。

---

## 6. 格式化与 lint 流水线

| 层 | 命令 | 覆盖 | 阻断合并？ |
| ---- | ---- | ---- | ---- |
| 统一格式化 | just fmt → `scripts/format.py` | justfile / Rust / Bazel-Starlark / Python | 是（`repo-checks.yml` 跑 `just fmt-check`） |
| **Rust 导入粒度** | `cargo fmt -- --config imports_granularity=Item --check` | Rust | 是（`rust-ci.yml` 的 `general` job） |
| **未用依赖检测** | `cargo shear --deny-warnings`（cargo-shear@1.11.2） | Cargo 依赖 | 是（`rust-ci.yml` 的 `cargo_shear` job） |
| JS/MD/YAML 格式化 | `pnpm run format` → prettier | `*.json`、`*.md`、`docs/*.md`、`.github/workflows/*.yml`、`**/*.js` | 是（`repo-checks.yml`） |
| Rust lint | `just clippy` / `just fix -p <crate>` | Rust | PR 上由 `bazel.yml` 的 clippy job 阻断；完整 Cargo clippy 矩阵在 postmerge |
| 自定义 lint | `just argument-comment-lint` | Dylint，实现在 `tools/argument-comment-lint`（**workspace 之外的独立 crate**） | 是（`rust-ci.yml`，Linux/macOS/Windows 三平台） |
| 仓库硬规则 | `repo-checks.yml` 的一批 Python 校验脚本 | 见 §4.3 | 是 |
| 拼写 | CI `codespell.yml` | 全仓 | 是 |
| 依赖审计 | CI `cargo-deny.yml` | Cargo 依赖 | 是 |

> [!IMPORTANT]
> **`imports_granularity=Item`（第一版未提）**：本仓库的 rustfmt 检查带了非默认配置，要求 **每个 import 一行一个 item**。默认 `cargo fmt` 通过不代表 CI 通过——`just fmt` 会带上同样的配置，所以正常流程用 `just fmt` 即可。
>
> **`cargo shear`（第一版未提）**：会检测 `Cargo.toml` 中声明但未被使用的依赖，`--deny-warnings` 意味着**留下一个多余依赖就会挂**。删代码时尤其容易踩到。

> `tools/argument-comment-lint/` 有自己的 `Cargo.toml`，**不属于 `codex-rs` workspace**。它有两个驱动方式：Bazel（`--config=argument-comment-lint`）与预构建脚本（`run-prebuilt-linter.py`）。

### 6.1 `just fmt` 的真实工具依赖（第一版未提）

`scripts/format.py` 会分组调起外部工具，**这两个不装就跑不了 `just fmt` / `just fmt-check`**：

| 工具 | 用途 | 获取 |
| ---- | ---- | ---- |
| `dotslash` | 拉起 `tools/buildifier` 格式化 Bazel/Starlark | `cargo install --locked dotslash`（`docs/install.md` 有列） |
| `uv` | `uv run --frozen --project <root> ruff …`，分别作用于 `sdk/python` 与 `scripts` 两个独立工程 | CI 用 `astral-sh/setup-uv`（基线钉在 0.11.3）；`docs/install.md` 未列，需自行安装 |

> `sdk/python` 与 `scripts` 被有意拆成两个 `--project`，让 uv 与 Ruff 各自保留本工程的配置上下文。check 模式下 SDK 侧跑的是 `ruff check --diff`（只报告 lint 驱动的改写），不是完整 lint gate。

---

## 7. 代码生成物（必须与源码同 change 提交）

| 生成物 | 命令 | 触发条件 |
| ---- | ---- | ---- |
| `codex-rs/core/config.schema.json` | `just write-config-schema` | 改了 `ConfigToml` 或嵌套配置类型 |
| app-server TS 类型 + schema fixtures | `just write-app-server-schema` | 改了 app-server API 形状 |
| hooks schema fixtures | `just write-hooks-schema` | 改了 hooks 类型 |
| `MODULE.bazel.lock` | `just bazel-lock-update` | 改了 Cargo 依赖 |

四者都有**机器校验**：schema fixtures 有配套测试，Bazel 锁有 CI 检查。忘了跑就会失败。

> 兜底机制是 `.github/actions/check-clean-worktree`——它挂在 **`blocking-ci.yml` 聚合的那 8 个 pre-merge 校验工作流**的实质性 job 末尾（不是"每个 CI job"，口径与实测见 §4.3）。只要 CI 里跑一遍生成命令后工作区变脏，这一步就红。所以**生成物必须提交进同一个 change**（见 §4.3）。

---

## 8. 发布前检查清单

```
□ just fmt                                  已跑（需要 dotslash + uv，见 §6.1）
□ just test -p <crate> / just test          通过
□ just fix -p <crate>                       已跑（大改动）
□ 改了 Cargo 依赖 → just bazel-lock-update   已跑，锁文件入同一 change
□ 删了代码 → 顺手确认没留下未使用依赖（cargo shear 会挂）
□ 新增 include_str! 等 → BUILD.bazel compile_data 已补
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → just write-app-server-schema 已跑
□ 改了根 README → asciicheck / readme_toc 能过
□ 所有生成物已提交（pre-merge 校验工作流的 job 末尾会查工作区是否干净，见 §4.3）
□ just bazel-test                            通过（涉及构建改动时）
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500）
□ 若改动了 .github/**/*.yml → 需要临时的 workflow 上传审批，见 `$pushing-ci-changes` skill
```

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 各 reusable workflow 的逐 job 细节（除 §4 已展开的以外） | E1 | `.github/workflows/`（`README.md` 有编排说明） |
| `BUILD.bazel` 的编写规范 | E1 | 各 crate 的 `BUILD.bazel`、`bazel/rules/` |
| macOS 签名/公证链路的具体实现 | E1 | `.github/scripts/macos-signing/`、`rust-release.yml` 的 `sign-macos-*` job |
| npm 包 `@openai/codex` 的构建 | E1 | `codex-cli/` 目录、`scripts/stage_npm_packages.py` |
| Python SDK / runtime 的发布链路 | E1 | `python-sdk-release.yml`、`python-runtime-*.yml` |
| RBE（远程构建执行）配置 | E1 | `rbe.bzl` |
| `Dockerfile.bazel` 的用途 | E1 | `.github/workflows/Dockerfile.bazel` |
| `blob-size-policy` 的具体阈值 | E1 | `blob-size-policy.yml` |
| benchmark 的指标与基线 | E1 | `just bench`、`//codex-rs:e2e-benchmarks` |
| `.codex/skills/` 下的 14 个 skill | E1 | 见 `development_workflow.md` §2.6 与 `testing_guide.md` §8 |

> 第一版列在这里的 `zstd/`（其实是文件，见 §4）与"发布打标流程指向 `rust-release-prepare.yml`"两条已在本次修订中纠正并移除。

---

## 10. 相关文档

- [开发流程](./development_workflow.md) — 日常命令与提交前自检
- [测试指南](./testing_guide.md) — nextest 配置与 CI 测试
- [架构总览](./architecture_overview.md) §9 — 双构建系统概览
- [SDK 指南](./sdk_guide.md) — SDK 的构建与发布
- 仓库自带：[`docs/install.md`](../docs/install.md)、[`README.md`](../README.md)
