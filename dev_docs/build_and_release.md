---
title: Codex 构建与发布
summary: 描述 Cargo 与 Bazel 双构建系统的分工与双锁同步义务、hermetic LLVM 工具链与补丁机制、27 个 CI 工作流的分类、多平台发布产物矩阵与安装通路、npm 与 Python SDK 的独立发布链路，以及 compile_data 这类 Bazel 专属陷阱。
keywords: codex | build | release | bazel | cargo | ci | module-bazel | hermetic-toolchain | compile-data
scope: openai/codex 的构建系统、CI 工作流与发布流程
related_files: MODULE.bazel | justfile | package.json | .github/workflows | docs/install.md | README.md | AGENTS.md
dependencies: dev_docs/development_workflow.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 构建与发布

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 工作流清单、锁文件规模、MODULE.bazel 内容为 E4/E3；发布链路细节部分为 E1

---

## 1. 双构建系统

| | **Cargo** | **Bazel** |
| ---- | ---- | ---- |
| 定位 | 日常开发主用 | 发布构建与 CI 校验 |
| 清单 | `codex-rs/Cargo.toml` | `MODULE.bazel`（16,677 字节） |
| 锁文件 | `codex-rs/Cargo.lock`（367,304 字节） | `MODULE.bazel.lock`（**1,547,127 字节**） |
| 运行 | `just codex`、`just test` | `just bazel-codex`、`just bazel-test` |
| 发布 | — | `just build-for-release` → `//codex-rs/cli:release_binaries` |

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

这是 `AGENTS.md:37-39` 的明文要求。**CI 会验证锁文件漂移，忘了跑就会挂。**

### 1.2 `compile_data` 陷阱（`AGENTS.md:40-43`）

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

`MODULE.bazel` 对 `llvm` 与 `abseil-cpp` 打了 `single_version_override` 补丁，注释说明了原因：

| 补丁 | 原因（注释要点） |
| ---- | ---- |
| `llvm_rusty_v8_custom_libcxx.patch` | Codex 的自定义 libc++ 需求 |
| `llvm_windows_arm64_powl.patch` | Windows ARM64 |
| `llvm_windows_mingw_compat.patch` | Windows gnullvm 运行时需求，尚未进入上游 |
| `abseil_windows_gnullvm_thread_identity.patch` | Abseil 选的 MinGW pthread TLS 路径与 hermetic windows-gnullvm 工具链不匹配，强制走可移植的 C++11 thread-local 路径 |

补丁存放在 `patches/` 目录（仓库根，20 个文件）。

> **含义**：这套构建**不依赖开发机上的系统编译器**，而是自带 LLVM。这也解释了为什么 `MODULE.bazel.lock` 有 1.5 MB。**Windows 支持是补丁的主要来源。**

### 2.2 Bazel 目录结构

| 目录 | 内容 |
| ---- | ---- |
| `bazel/modules` | 模块定义 |
| `bazel/platforms` | 平台定义 |
| `bazel/rules` | 自定义规则 |
| `patches/` | 上游补丁（20 个文件） |
| `third_party/` | 第三方（13 个文件） |
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
| `just bazel-clippy` | `bazel build --config=clippy`（目标由 `scripts/list-bazel-clippy-targets.sh` 生成） |
| `just bazel-argument-comment-lint` | 自定义 Dylint 检查 |
| `just build-for-release` | `bazel build //codex-rs/cli:release_binaries` |
| `just bench-e2e` | `bazel test --compilation_mode=opt //codex-rs:e2e-benchmarks` |
| `just bench-e2e-smoke` | 同上但用 fastbuild，只验证 benchmark 能跑起来 |

> `just bazel-test` 显式排除了 `argument-comment-lint` 标签的测试——它由独立任务跑。

---

## 4. CI 工作流（E4：27 个 yml）

`.github/workflows/` 下共 **27 个 `.yml`**（另有 `README.md`、`Dockerfile.bazel`、`zstd/` 三个非 yml 条目）。

### 按用途分类

| 类别 | 工作流 |
| ---- | ---- |
| **Rust CI** | `rust-ci.yml`、`rust-ci-full.yml`、`rust-ci-full-nextest-platform.yml`、`blocking-ci.yml`、`postmerge-ci.yml` |
| **Bazel** | `bazel.yml` |
| **发布 — Rust** | `rust-release.yml`、`rust-release-prepare.yml`、`rust-release-windows.yml`、`rust-release-zsh.yml`、`rust-release-argument-comment-lint.yml` |
| **发布 — 其他** | `r2-release.yml`、`rusty-v8-release.yml`、`python-runtime-release.yml`、`python-runtime-build.yml`、`python-sdk-release.yml` |
| **SDK** | `sdk.yml` |
| **仓库检查** | `repo-checks.yml`、`blob-size-policy.yml`、`cargo-deny.yml`、`codespell.yml` |
| **社区自动化** | `cla.yml`、`close-stale-contributor-prs.yml`、`issue-deduplicator.yml`、`issue-labeler.yml`、`issue-translator.yml` |
| **实验性** | `v8-canary.yml` |

### 可读出的信息

- **`close-stale-contributor-prs.yml` 直接对应受邀制贡献规则**（`docs/contributing.md:3-17`）——未受邀的 PR 会被自动关闭
- **Windows 有独立的发布工作流**（`rust-release-windows.yml`），与 §2.1 的补丁情况一致
- **`blob-size-policy.yml`** 说明仓库对大文件入库有策略约束
- **`cargo-deny.yml`** 做依赖许可证/安全审计
- 发布链路按产物拆分：Rust 二进制、R2（对象存储）、rusty-v8、Python runtime、Python SDK 各自独立

---

## 5. 发布产物

### 5.1 平台矩阵（E2，`README.md:55-65`）

| 平台 | 产物 |
| ---- | ---- |
| macOS Apple Silicon | `codex-aarch64-apple-darwin.tar.gz` |
| macOS x86_64 | `codex-x86_64-apple-darwin.tar.gz` |
| Linux x86_64 | `codex-x86_64-unknown-linux-musl.tar.gz` |
| Linux arm64 | `codex-aarch64-unknown-linux-musl.tar.gz` |

每个归档内只有一个可执行文件，**文件名带平台后缀**（如 `codex-x86_64-unknown-linux-musl`），解压后通常需要重命名为 `codex`。

> 这解释了为什么 `codex-rs/cli/src/main.rs:100-105` 要显式设置 `bin_name = "codex"`——保证帮助输出不受实际文件名影响。同时 `codex-arg0` 支持按 argv[0] 分发。

### 5.2 安装通路（E2，`README.md`）

| 方式 | 命令 |
| ---- | ---- |
| 官方安装脚本（Mac/Linux） | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` |
| 官方安装脚本（Windows） | `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 \| iex"` |
| npm | `npm install -g @openai/codex` |
| Homebrew | `brew install --cask codex` |
| GitHub Releases | 手动下载对应平台归档 |

**下载源与回退**（`README.md:28`）：安装器默认从 `https://releases.openai.com/codex` 下载，元数据或资产不可用时**回退到 GitHub Releases**。可用 `CODEX_INSTALLER_USE_RELEASES_OPENAI_COM=false`（也接受 `0`/`no`）强制走 GitHub Releases。

> 这与 `r2-release.yml` 工作流对应——`releases.openai.com` 很可能由对象存储承载。

### 5.3 npm 包

仓库根 `package.json` 的包名是 `codex-monorepo`，`private: true`，只提供仓库维护脚本：

```json
"scripts": {
  "format": "prettier --check *.json *.md docs/*.md .github/workflows/*.yml **/*.js",
  "format:fix": "prettier --write ...",
  "write-hooks-schema": "cargo run --manifest-path ./codex-rs/Cargo.toml -p codex-hooks --bin write_hooks_schema_fixtures"
}
```

**发布到 npm 的 `@openai/codex` 不是这个包**，而是 `codex-cli/` 目录下的产物（7 个文件）。

`package.json` 还有一大段 `resolutions` 锁定传递依赖版本（`@modelcontextprotocol/sdk`、`esbuild`、`rollup`、`semver` 等 17 项）——典型的供应链版本收敛做法。

---

## 6. 格式化与 lint 流水线

| 层 | 命令 | 覆盖 |
| ---- | ---- | ---- |
| 统一格式化 | just fmt → `scripts/format.py` | justfile / Rust / Bazel-Starlark / Python |
| JS/MD/YAML 格式化 | `pnpm format` → prettier | `*.json`、`*.md`、`docs/*.md`、`.github/workflows/*.yml`、`**/*.js` |
| Rust lint | `just clippy` / `just fix -p <crate>` | Rust |
| 自定义 lint | `just argument-comment-lint` | Dylint，实现在 `tools/argument-comment-lint`（**workspace 之外的独立 crate**） |
| 拼写 | CI `codespell.yml` | 全仓 |
| 依赖审计 | CI `cargo-deny.yml` | Cargo 依赖 |

> `tools/argument-comment-lint/` 有自己的 `Cargo.toml`，**不属于 `codex-rs` workspace**。它有两个驱动方式：Bazel（`--config=argument-comment-lint`）与预构建脚本（`run-prebuilt-linter.py`）。

---

## 7. 代码生成物（必须与源码同 change 提交）

| 生成物 | 命令 | 触发条件 |
| ---- | ---- | ---- |
| `codex-rs/core/config.schema.json` | `just write-config-schema` | 改了 `ConfigToml` 或嵌套配置类型 |
| app-server TS 类型 + schema fixtures | `just write-app-server-schema` | 改了 app-server API 形状 |
| hooks schema fixtures | `just write-hooks-schema` | 改了 hooks 类型 |
| `MODULE.bazel.lock` | `just bazel-lock-update` | 改了 Cargo 依赖 |

四者都有**机器校验**：schema fixtures 有配套测试，Bazel 锁有 CI 检查。忘了跑就会失败。

---

## 8. 发布前检查清单

```
□ just fmt                                  已跑
□ just test -p <crate> / just test          通过
□ just fix -p <crate>                       已跑（大改动）
□ 改了 Cargo 依赖 → just bazel-lock-update   已跑，锁文件入同一 change
□ 新增 include_str! 等 → BUILD.bazel compile_data 已补
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → just write-app-server-schema 已跑
□ just bazel-test                            通过（涉及构建改动时）
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500）
```

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 27 个工作流的逐个内容 | E4（仅文件名） | `.github/workflows/`（`README.md` 有说明） |
| `BUILD.bazel` 的编写规范 | E1 | 各 crate 的 `BUILD.bazel`、`bazel/rules/` |
| 发布版本号的确定与打标流程 | E1 | `rust-release-prepare.yml` |
| npm 包 `@openai/codex` 的构建 | E1 | `codex-cli/` 目录 |
| Python SDK / runtime 的发布链路 | E1 | `python-sdk-release.yml`、`python-runtime-*.yml` |
| RBE（远程构建执行）配置 | E1 | `rbe.bzl` |
| `zstd/` 与 `Dockerfile.bazel` 的用途 | E1 | `.github/workflows/` |
| `blob-size-policy` 的具体阈值 | E1 | `blob-size-policy.yml` |
| benchmark 的指标与基线 | E1 | `//codex-rs:e2e-benchmarks` |

---

## 10. 相关文档

- [开发流程](./development_workflow.md) — 日常命令与提交前自检
- [测试指南](./testing_guide.md) — nextest 配置与 CI 测试
- [架构总览](./architecture_overview.md) §9 — 双构建系统概览
- [SDK 指南](./sdk_guide.md) — SDK 的构建与发布
- 仓库自带：[`docs/install.md`](../docs/install.md)、[`README.md`](../README.md)
