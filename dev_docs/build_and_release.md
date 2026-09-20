---
title: Codex 构建与发布
summary: 描述 Cargo 与 Bazel 的真实分工（Bazel 是 PR 主校验路径，发布二进制由 Cargo 构建）、双锁同步义务、两套系统编译源码不同导致的 7 类分歧陷阱、hermetic LLVM 工具链与补丁机制及其逃逸口、Nix 这条不钉版本且不参与交付的开发环境入口（devcontainer 第 6 轮已被上游删除）、由 blocking-ci/postmerge-ci 编排的 30 个 CI 工作流与 repo-checks 的三处失效项、rust-release.yml 的 20 个 job 与多平台发布产物矩阵、三类外部拉取产物、DotSlash/winget/npm 安装通路，以及 write-app-server-schema 等上游文档陈旧点。
keywords: codex | build | release | bazel | cargo | ci | blocking-ci | repo-checks | module-bazel | hermetic-toolchain | compile-data | dotslash | nix | patches | toolchain-pinning | round6
scope: openai/codex 的构建系统、CI 工作流与发布流程
related_files: MODULE.bazel | justfile | defs.bzl | .bazelrc | package.json | scripts/format.py | .github/workflows | docs/install.md | README.md | AGENTS.md | flake.nix | .github/dependabot.yaml
dependencies: dev_docs/development_workflow.md | dev_docs/architecture_overview.md
verified_at: 2026-09-21
---

# 构建与发布

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **证据等级**: 工作流内容、锁文件规模、MODULE.bazel 内容、发布 job 拓扑为 E2/E3（读取 yml 与配置）；文中所有「N 个文件 / N 个工作流 / N 处引用」类计数均为实跑 `ls` / `grep -c` / `git ls-files` 得来，按本体系约定统一归 **E1**（§4.1 上一稿把同类测量标成 E4，本次已统一）。`just write-app-server-schema` 相关内容的证据等级见 §7 的降级说明。

> [!NOTE]
> **第一版勘误（本次修订）**：初版把 Bazel 写成"发布构建系统"、把 `.github/workflows/rust-release-prepare.yml` 当成发布打标入口、把 `.github/workflows/rust-ci.yml` 当成 PR 上的测试通道——三条都是错的，本文已按工作流实际内容重写（见 §1、§4、§5）。

---

## 1. 双构建系统

| | **Cargo** | **Bazel** |
| ---- | ---- | ---- |
| 定位 | 日常开发主用；**发布二进制的实际构建者** | **PR 合并前的主校验路径**（test + clippy） |
| 清单 | `codex-rs/Cargo.toml` | `MODULE.bazel`（16,677 字节） |
| 锁文件 | `codex-rs/Cargo.lock`（367,304 字节） | `MODULE.bazel.lock`（**1,547,127 字节**） |
| 运行 | `just codex`、`just test` | `just bazel-codex`、`just bazel-test` |
| 发布 | `.github/workflows/rust-release.yml` / `.github/workflows/rust-release-windows.yml` 里的 `cargo build --target <t> --release` | 不参与发布产物构建；`.github/workflows/bazel.yml` 的 `verify-release-build` job 只做 **`cfg(not(debug_assertions))` 编译面回归**，见下方注解 |
| 源码替换 | `codex-rs/Cargo.toml:572-583` 的 `[patch.crates-io]`（3 个 git fork） | `patches/` 下 19 个 `.patch`（见 §2.1）——**两套互不相干，见 §1.3** |

> [!IMPORTANT]
> **纠正第一版的判断**：`grep -c bazel .github/workflows/rust-release.yml` 结果为 **0**——发布工作流完全不碰 Bazel。产物由 `cargo build --target "$target" --release --timings` 产出（`.github/workflows/rust-release.yml` 的 build job；Windows 在 `.github/workflows/rust-release-windows.yml` 里同款）。
>
> Bazel 的真实定位写在 `.github/workflows/README.md` 开头：**"`.github/workflows/bazel.yml` is the main pre-merge verification path for Rust code."** 它由 `.github/workflows/blocking-ci.yml` 作为第一个 reusable workflow 调用，跑 Bazel `test` 与 Bazel `clippy`（包括为 lint 内联 `#[cfg(test)]` 代码而生成的测试二进制）。
>
> [!WARNING]
> **`verify-release-build` 这个 job 名极易被误读成"验证发布构建"。** 它既不产出发布资产，也不做 release 优化。`.github/workflows/bazel.yml:483-488` 的步骤内注释原文：
>
> > *"This job exists to compile Rust code behind `cfg(not(debug_assertions))` so PR CI catches failures that would otherwise show up only in a release build. We do not need the full optimizer and debug-info work that normally comes with a release build to get that signal, so keep Bazel in `fastbuild` and disable Rust debug assertions explicitly."*
>
> 即：**它的唯一目的是把 `cfg(not(debug_assertions))` 后面的代码编译一遍**，让 PR CI 抓到只在 release 编译面下才暴露的错误；Bazel 仍跑在 `fastbuild`。目标清单由 `scripts/list-bazel-release-targets.sh` 给出（`//codex-rs/...` 减去 2 个排除项）。

> Bazel 锁文件是 Cargo 锁文件的 **4.2 倍大**，反映出 Bazel 侧管理的是包含 C++ 工具链在内的完整 hermetic 依赖树。

### 1.1 双锁同步义务（强制）

```
改了 Cargo.toml 或 Cargo.lock
        ↓
在仓库根跑 just bazel-lock-update      （= bazel mod deps --lockfile_mode=update）
        ↓
把更新后的 MODULE.bazel.lock 放进同一个 change
        ↓
CI 直接跑 scripts/check-module-bazel-lock.sh 校验漂移
（本地等价命令为 just bazel-lock-check）
```

`.github/workflows/bazel.yml:74-77` 的步骤 "Check MODULE.bazel.lock is up to date" 是 `run: ./scripts/check-module-bazel-lock.sh`，并不经过 just——全仓 `.github/` 下 `grep -rn "bazel-lock-check"` 零命中。Unix 下两者跑的是同一个脚本（见 §3）；**Windows 版 recipe 则不调脚本**，直接 `bazel mod deps --lockfile_mode=error` 加一段 PowerShell 错误处理（`justfile:147-148`）——等价但不共用实现。无论哪个平台，表述上都不要写成"CI 用 just …"。

这是 `AGENTS.md` **顶部规则列表**中 "If you change Rust dependencies (`Cargo.toml` or `Cargo.lock`), run `just bazel-lock-update`" 一条的明文要求（grep 关键词：`bazel-lock-update`）。<!-- ref-exempt: 本行的 Cargo.toml / Cargo.lock 位于 AGENTS.md 顶部规则的逐字引文内，加路径前缀会破坏引文保真度；限定口径见下一句 -->

引文里的「清单」指 `codex-rs/` 下任一 crate 的清单，或 workspace 清单 `codex-rs/Cargo.toml` 与其锁文件 `codex-rs/Cargo.lock`。**CI 会验证锁文件漂移，忘了跑就会挂。**

### 1.2 `compile_data` 陷阱（`AGENTS.md` 顶部规则列表，grep `compile_data`）

> [!WARNING]
> **Bazel 不会自动把源码树里的文件提供给编译期 Rust 文件访问。**
>
> 如果你新增了 `include_str!`、`include_bytes!`、`sqlx::migrate!` 或类似的**构建期文件/目录读取**，必须更新该 crate 的 `BUILD.bazel`（`compile_data`、`build_script_data` 或 test data）。
>
> **否则会出现 Cargo 能过、Bazel 失败的情况**（`AGENTS.md:40-43` 原文用词是 "or Bazel **may** fail even when Cargo passes"——是否真的失败取决于该文件是否已通过其他 `compile_data` 条目或依赖传递进入了 Bazel 沙箱，并非必然）。这是本仓库最典型的"本地绿、CI 红"来源。

现实中的例子：`codex-rs/sandboxing/src/seatbelt.rs:21-24` 用 `include_str!` 内嵌三份 `.sbpl` 策略文件。

`compile_data` 只是"两套系统行为不同"的**其中一类**。完整清单见下节。

### 1.3 两套系统编译的不是同一份东西（最重要的一节）

> [!CAUTION]
> **`patches/` 下的 19 个补丁全部只作用于 Bazel，Cargo 完全看不到。** 逐个补丁文件名做全仓 grep（排除锁文件），**每个都恰好命中两处**：`MODULE.bazel` 里的引用与 `patches/BUILD.bazel` 里的登记，此外无第三处。
>
> | 被打补丁的对象 | 补丁数 | `MODULE.bazel` 行 |
> | ---- | ---- | ---- |
> | `llvm` | 3 | `:13`、`:14`、`:15` |
> | `v8` | 3 | `:480`、`:481`、`:482` |
> | `rules_rust` | 3 | `:108`、`:111`、`:114` |
> | `rules_rs` | 1 | `:98` |
> | `rules_cc` | 1 | `:87` |
> | `abseil-cpp` / `bzip2` / `xz` | 各 1 | `:25`、`:302`、`:328` |
> | crate 级 annotation | 5 | `zstd-sys :261`、`ring :268`、`rusty_v8 :409`、`webrtc-sys :451`、`windows-link :460`（**这 5 个就是全部，无"等"**） |
>
> **Cargo 侧用的是另一套完全不相干的源替换**：`codex-rs/Cargo.toml:572-583` 的 `[patch.crates-io]`，指向 `openai-oss-forks` 组织下的 `crossterm` / `tokio-tungstenite` / `tungstenite` 三个 git fork（另有一段 `[patch."ssh://…/tungstenite-rs.git"]`）。
>
> **结论：`ring`、`zstd-sys`、`webrtc-sys`、`v8`、`windows-link` 这些 crate，在 Cargo 下和在 Bazel 下编译的是不同源码。** 因此"Cargo 能过"与"Bazel 能过"之间没有蕴含关系——这是本文所有"双系统陷阱"的根因。

在此基础上，**只在其中一套系统里才会踩到的坑共 7 类**（`compile_data` 是第 4 类）：

| # | 分歧点 | 证据 | 后果 |
| ---- | ---- | ---- | ---- |
| 1 | **feature 语义相反** | `codex-rs/v8-poc/BUILD.bazel:5-8` 用 `crate_features = select({…, "//conditions:default": ["sandbox"]})` 把 `sandbox` 写死为**开**；`codex-rs/v8-poc/Cargo.toml:12-13` 的 `[features] sandbox` 没有 `default`，Cargo 默认**关** | 同一份源码在两套系统下 feature 状态相反 |
| 2 | **`BAZEL_PACKAGE` 是 Bazel 独有的编译期环境变量** | `defs.bzl:282-283` 的 `rustc_env = {"BAZEL_PACKAGE": native.package_name()}`；消费点在 `codex-rs/linux-sandbox/src/bazel_bwrap.rs:12`、`codex-rs/exec-server/src/fs_sandbox.rs:290`、`codex-rs/utils/cargo-bin/src/lib.rs:132,151` | 真实运行逻辑按它分叉。全仓**没有** `#[cfg(bazel)]`，机制是 `option_env!` |
| 3 | **build script 在 Bazel 下看到假版本号 / 被整个删掉** | `defs.bzl:299-305` 的 `cargo_build_script(..., version = "0.0.0")` 硬编码；另有 **6 处** `crate.annotation(..., gen_build_script = "off")`（`MODULE.bazel:275,282,288,308,334,468`）在 Bazel 下直接不跑 build script，Cargo 照跑 | 依赖 `CARGO_PKG_VERSION` 或 build script 产物的代码行为不同 |
| 4 | **编译期读文件**（即 §1.2 的 `compile_data`） | 实例：`patches/windows-link.patch` 把 `#![doc = include_str!("../readme.md")]` 换成字面量，就是为了绕开 Bazel 沙箱看不到该文件 | Cargo 过、Bazel 挂 |
| 5 | **测试在 Bazel CI 下被静默跳过** | `.bazelrc:166` 与 `:197` 的 `--test_env=CODEX_BAZEL_TEST_SKIP_FILTERS=…`（由 `workspace_root_test_launcher.sh.tpl:124,161` / `.bat.tpl:30,83` 消费），**Cargo 侧无对应物** | **Bazel 绿 ≠ Cargo 绿** |
| 6 | **clippy 覆盖面不等** | `defs.bzl:350` 与 `:410` 给**每个**底层 `rust_test` 打了 `tags = ["manual"]`，于是 `bazel build --config=clippy //...` 会漏掉它们 | 必须走 `scripts/list-bazel-clippy-targets.sh` 补齐（见下方引文） |
| 7 | **insta 快照路径在 Bazel 下是模拟出来的** | `defs.bzl:260-266` 设 `INSTA_WORKSPACE_ROOT="."` / `INSTA_SNAPSHOT_PATH="src"`；`defs.bzl:340-347` 与 `:405-407` 用 `--remap-path-prefix=../codex-rs=` 和 `--remap-path-prefix=codex-rs=` 伪造 `file!()` | 快照落盘位置靠这层伪装才与 Cargo 一致 |

> 关于第 5 条的一个细节：`.bazelrc:194-196` 自带警告 —— *"This **replaces** the Windows skip list, so retain its exclusions."* 即 `ci-windows-cross` 的 skip 列表会**覆盖**而非叠加 `ci-windows` 的，改动时必须把原有排除项一并抄进去。
>
> 关于第 6 条，`scripts/list-bazel-clippy-targets.sh:25-52` 的注释解释得很清楚：*"`--config=clippy` on the `workspace_root_test` wrappers does not lint the underlying `rust_test` binaries. Add the internal manual `*-unit-tests-bin` targets explicitly so inline `#[cfg(test)]` code is linted like `cargo clippy --tests`."*

> [!IMPORTANT]
> **`BUILD.bazel` 是手写的，不是生成的**（全仓 `gazelle` 零命中；`codex-rs/**/BUILD.bazel` 共 **138** 个，无一含 `DO NOT EDIT` 或 `@generated` 标记）。
>
> `codex-rs/docs/bazel.md:160-167` 明写新增 crate 的流程：*"1. Add it to the Cargo workspace as usual. 2. Create a `BUILD.bazel` that calls `codex_rust_crate`…"*
>
> **含义：只往 `codex-rs/Cargo.toml` 加 crate 而不写 `BUILD.bazel`，Bazel 侧既没有对应目标、也不会报错**——它只是悄悄不存在。这是"新建 crate"流程里最容易漏、且最难通过报错发现的一步。

### 1.4 其他开发环境入口（不参与交付，第 6 轮由两套减为一套）

除 Cargo / Bazel 外，仓库**曾**提供 Nix flake 与 devcontainer 两套开发环境入口；**第 6 轮起只剩 Nix 一套**（devcontainer 已被上游删除，见下）。Nix 仍只是开发便利设施：**不产出任何发布产物，也不被任何 CI 工作流引用**——`grep -rn "flake.nix\|nix develop\|devcontainer" .github/ docs/ README.md AGENTS.md` 的唯一命中是 `.github/dependabot.yaml:19` 的 `package-ecosystem: devcontainers`，即只有 Dependabot 会自动更新 devcontainer feature 的版本。

#### Nix（`flake.nix` + `flake.lock` + `codex-rs/default.nix`）

`flake.nix` 自述 *"Development Nix flake for OpenAI Codex CLI"*，覆盖 4 个 system（`x86_64-linux` / `aarch64-linux` / `x86_64-darwin` / `aarch64-darwin`），依赖 nixos-unstable 与 `rust-overlay`（`github:oxalica/rust-overlay`）。两类 output：

| output | 内容 |
| ---- | ---- |
| `packages.<system>.codex-rs`（同时是 `default`） | `pkgs.callPackage ./codex-rs` 调用 `codex-rs/default.nix`，后者用 `rustPlatform.buildRustPackage`、`cargoLock.lockFile = ./Cargo.lock`，且 **`doCheck = false`（不跑测试）** |
| `devShells.<system>.default` | `mkShell`，装 `rust-bin.stable.latest.default`（含 `rust-src`、`rust-analyzer`）、`pkg-config`、`openssl`、`cmake`、`llvmPackages.clang` / `libclang`；`shellHook` 里 `export CC=clang; export CXX=clang++`，注释说明是为 BoringSSL 规避 GCC 15 的 warnings-as-errors |

用法：`nix develop`（进开发 shell）/ `nix build`（构建包）。

> [!IMPORTANT]
> **版本号逻辑与发布链路存在一条隐式耦合**：`flake.nix` 直接 `builtins.fromTOML` 读取 `codex-rs/Cargo.toml` 的 `workspace.package.version`，注释明写这是 *"the single source of truth used by the release workflow"*；若读到占位值 `0.0.0`（main 分支的常态），则退化为 `0.0.0-dev+${self.shortRev or "dirty"}`。`codex-rs/default.nix` 的 `postPatch` 再用 `sed` 把 `version = "0.0.0"` 就地替换，以保证二进制里 `env!("CARGO_PKG_VERSION")` 正确。
>
> **这与 §5.1 `tag-check` job 读的是同一个字段**——改动 `codex-rs/Cargo.toml` 的 workspace 版本会同时影响发布打标校验与 Nix 构建产出的版本号。

> [!CAUTION]
> **第 6 轮：`.devcontainer/` 目录已被上游整体删除，本小节原有的两条容器路径全部不存在了。**
>
> 上游提交 `f419c3214a`「Remove the repository devcontainer configurations (#43915)」，提交信息原文：
>
> > Remove the contributor and secure devcontainer profiles, Dockerfiles, setup and firewall scripts, installation lockfiles, and documentation under `.devcontainer/`.
> > Remove the Dependabot devcontainers entry and redundant container-specific target directory rules from `codex-rs/.gitignore`.
>
> 即：**两个 profile、两个 Dockerfile、防火墙脚本、安装锁文件与该目录下的文档一并删除**，Dependabot 的 `package-ecosystem: devcontainers` 条目也同步移除（`grep -n 'devcontainer' .github/dependabot.yaml` 现已零命中）。
>
> **连带失效的一条论证**：本节开头原本用「`grep -rn "flake.nix\|nix develop\|devcontainer" .github/ docs/ README.md AGENTS.md` 的唯一命中是 `.github/dependabot.yaml:19`」来论证「两套环境都不被 CI 引用」。该命中已消失，结论方向不变但证据要重取。
>
> 原小节记录的那套安全 profile 细节（setuid bwrap、关闭外层 seccomp/AppArmor、防火墙脚本的白名单出网、屏蔽 IPv6、`NET_ADMIN`+`NET_RAW`）**在当前仓库已无对应物**。若你是从旧文档得知这套配置并打算复现，请注意它已随上游一并移除，不再有维护。

#### 工具链固定：Cargo 与 Bazel 一致，Nix 不一致

比"不参与交付"更值得记的一点是：**四条链路里只有前两条把 Rust 版本钉死了。**

| 链路 | Rust 版本 | 证据 |
| ---- | ---- | ---- |
| Cargo | **1.95.0**（钉死） | `codex-rs/rust-toolchain.toml` 的 `channel = "1.95.0"` |
| Bazel | **1.95.0**（钉死，与 Cargo 一致） | `MODULE.bazel:190-194` 的 `toolchains.toolchain(edition = "2024", version = "1.95.0")` |
| CI（GitHub Actions） | **1.95.0**（钉死，18 处 SHA 全部一致） | `.github/workflows/` 下 18 处 `dtolnay/rust-toolchain@e081816240890017053eacbb1bdf337761dc5582 # 1.95.0` |
| **Nix** | **`latest`（不钉）** | `flake.nix` 的 `pkgs.rust-bin.stable.latest.minimal` / `…latest.default` |
| **devcontainer** | **无版本（不钉）** | `.devcontainer/Dockerfile:21` 的 `curl -sSf https://sh.rustup.rs \| sh -s -- -y --profile minimal` |

nightly 侧同样是 Cargo/Bazel 对齐的：`tools/argument-comment-lint/rust-toolchain`（**注意无 `.toml` 后缀**）为 `nightly-2025-09-18`，`MODULE.bazel:123-131` 的 `versions = ["nightly/2025-09-18"]` 与之相同。Bazel 自身版本由 `.bazelversion` 钉在 `9.0.0`。

> **含义**：**只有 Nix 那条链路会随时间漂移。** `rust-bin.stable.latest` 绕开 rustup，**不读 `codex-rs/rust-toolchain.toml`**，所以 Nix shell 里编译成功不能推断 CI 的 1.95.0 也能过。
>
> **devcontainer 不漂移。** `.devcontainer/Dockerfile` 装的是 rustup（`curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal`），而 rustup 会沿 cwd 及其祖先目录查找 toolchain 文件；根 `justfile:1` 的 `set working-directory := "codex-rs"` 使所有非 `[no-cd]` recipe 都在 `codex-rs/` 下执行，于是被 `codex-rs/rust-toolchain.toml` 拉回 **1.95.0**（仓库根没有 `rust-toolchain*` 文件，不存在被截胡的情况）。Dockerfile 那条不钉版本的安装**只影响镜像内的 default toolchain**，不影响实际构建。
>
> 两者都适合快速上手；把 Nix 当作发版前的最终验证是不安全的。

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

> **含义**：这套构建自带 hermetic LLVM 工具链（`MODULE.bazel:29` 的 `register_toolchains("@llvm//toolchain:all")`），**目标是不依赖开发机上的系统编译器**。这也解释了为什么 `MODULE.bazel.lock` 有 1.5 MB。（未做构建级验证——确证"完全不依赖"需实跑 bazel，属本体系禁止项。）**Windows 支持是补丁的主要来源**，如上所述占 19 个补丁中的 10 个（53%，相对多数而非压倒性）。

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

### 2.3 hermetic 化只有 Bazel 侧做了，而且有一个显式逃逸口

**Bazel 侧做了什么：**

| 手段 | 位置 |
| ---- | ---- |
| 禁止探测宿主 C++ / Apple 工具链 | `.bazelrc:1-4` 的 `BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=1`、`BAZEL_NO_APPLE_CPP_TOOLCHAIN=1`、`--xcode_version_config=//:disable_xcode` |
| 严格 action 环境 | `.bazelrc:26` 的 `--incompatible_strict_action_env`（该文件唯一的 `--incompatible_*`） |
| hermetic macOS SDK | `MODULE.bazel:31-39` 的 `osx.from_archive(sha256 = …, urls = ["https://swcdn.apple.com/…/CLTools_macOSNMOS_SDK.pkg"])`——直接下 SDK，不用宿主 Xcode |
| hermetic LLVM 工具链 | `MODULE.bazel:29` 的 `register_toolchains("@llvm//toolchain:all")` |

> [!WARNING]
> **逃逸口**：`.bazelrc:27-29` 把宿主 `PATH` 注入了 `--test_env`，注释直言 *"Not ideal, but We need to allow dotslash to be found"*（Linux/macOS 各一行）。**测试执行环境因此不是完全封闭的**——测试能看到宿主 `/usr/bin`、`/opt/homebrew/bin` 等目录下的东西。

**Cargo 侧基本没做 hermetic 化**：唯一一处是 `.github/workflows/rust-release.yml:179-187`，只对两个 musl 目标设 `CARGO_HOME=${GITHUB_WORKSPACE}/.cargo-home` 并用 `: > "${cargo_home}/config.toml"` 清空配置。

**Python 也不 hermetic**：`MODULE.bazel` 里**没有** `rules_python`，CI 各处直接用宿主 `python3`（§4.3 的 repo-checks 全部如此）。

**Cargo → Bazel 的依赖桥**是 `crate.from_cargo`（`MODULE.bazel:209-228`），以 `cargo_lock = "//codex-rs:Cargo.lock"` 为输入、展开 10 个 `platform_triples`；用的是新式模块扩展，**没有** legacy 的 `crates_repository`。这也正是 §1.1 双锁同步义务的机制来源。

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
| `just build-for-release` | `bazel build //codex-rs/cli:release_binaries`（**本地用途；CI 发布走 Cargo，且该目标零 CI 覆盖——见下方警告**） |
| `just bench-e2e` | `bazel test --compilation_mode=opt //codex-rs:e2e-benchmarks` |
| `just bench-e2e-smoke` | 同上但用 fastbuild，只验证 benchmark 能跑起来 |

> `just bazel-test` 显式排除了 `argument-comment-lint` 标签的测试——它由独立任务跑。

> [!CAUTION]
> **`//codex-rs/cli:release_binaries` 是一个完全没有 CI 覆盖的目标。** 三条证据：
>
> 1. `bazel/platforms/release_binaries.bzl:20` 的 `platform_data(...)` 与 `:26` 的 `native.filegroup(...)` **都带 `tags = ["manual"]`**——因此 `bazel build //...` 这类通配构建**永不**触及它；
> 2. `verify-release-build` 用的 `scripts/list-bazel-release-targets.sh` 全文只 `printf` 三行（`//codex-rs/...` 加两条 `-//` 排除），**不含 `release_binaries`**；
> 3. 全仓 grep `release_binaries` 只有 3 处非文档命中：`justfile:164`（本 recipe）、`codex-rs/cli/BUILD.bazel:2`（load 宏）、`bazel/platforms/release_binaries.bzl:24`（定义处）。
>
> 该规则会为 `PLATFORMS` 里的 **6 个平台**（`linux_arm64_musl`、`linux_amd64_musl`、`macos_amd64`、`macos_arm64`、`windows_amd64`、`windows_arm64`）各生成一个 `platform_data` 目标。**这套交叉发布 fan-out 一旦坏掉，不会被任何 CI 发现**——只有手动跑 `just build-for-release` 才会暴露。改动平台约束、LLVM 工具链或 `codex-rs/cli/BUILD.bazel` 时需特别注意。

> [!WARNING]
> **平台差异**：`bazel-clippy`、`bazel-argument-comment-lint`、`argument-comment-lint` 在 `justfile` 里都带 `[unix]` 属性，**Windows 开发机上这几条任务根本不存在**。`bazel-codex`、`bazel-code-mode-host`、`bazel-lock-check`、`test`、`install`、`log` 则各有 `[unix]` / `[windows]` 两个版本。
>
> 另外 `just install` 的 `[windows]` 分支会用 winget 安装 PowerShell 7（若 `pwsh.exe` 不存在），之后才走与 Unix 相同的 `rustup show active-toolchain` + `cargo fetch`。

---

## 4. CI 工作流（30 个 yml）

`.github/workflows/` 下共 **30 个 `.yml`**（E1，第 6 轮实测），另有三个非 yml 条目：`README.md`、`.github/workflows/Dockerfile.bazel`，以及 **`zstd`——它是一个文件，不是目录**（`#!/usr/bin/env dotslash` 脚本，用途写在它自己的注释里：为 Windows runner 包装 zstd，windows-aarch64 通过 x64 模拟复用 win64 产物）。第一版把它列成"未知用途的目录"，属于误判。

> **`.github/workflows/Dockerfile.bazel` 是一个死文件**：它自带注释 `# TODO(mbolin): Published to docker.io/mbolin491/codex-bazel:latest for initial debugging, but we should publish to a more proper location.`，且**没有任何工作流或脚本引用它**（全仓在 `*.yml` / `*.sh` 中 grep 该文件名零命中）。它是一次性调试遗留，读工作流时可以忽略。

### 4.1 编排结构：两个**主编排器**，但不是仅有的两个事件入口

> [!CAUTION]
> **本节上一稿的两个数字都是错的，且与本文自己别处的叙述矛盾。**
>
> 上一稿写「约 20 个是 `workflow_call:` 专用」「真正的事件入口只有两个」。实测（E1）：
>
> ```bash
> ls .github/workflows/*.yml | wc -l                              # 27  总数
> grep -lE '^  workflow_call:' .github/workflows/*.yml | wc -l    # 14  声明了 workflow_call
> ```
>
> 再逐个解析顶层 `on:` 块可得：**只声明 `workflow_call` 的有 10 个**（真正的纯 reusable），而**声明了至少一个真实事件触发器的有 17 个**：`bazel`、`blocking-ci`、`cla`、`close-stale-contributor-prs`、`issue-deduplicator`、`issue-labeler`、`issue-translator`、`postmerge-ci`、`python-runtime-release`、`python-sdk-release`、`rust-ci-full`、`rust-ci`、`rust-release-prepare`、`rust-release-zsh`、`rust-release`、`rusty-v8-release`、`v8-canary`。
>
> 「只有两个事件入口」这句话**在本文内部就已被推翻**：§4.4 明写 `.github/workflows/v8-canary.yml` 有 `pull_request` 触发器、**每个 PR 都会跑**；§4.4 还说 `.github/workflows/close-stale-contributor-prs.yml` 有 `cron`。**同一篇文档里前后打架，是最容易被读者信以为真的那类错误。**

准确的说法是：**`.github/workflows/blocking-ci.yml` 与 `.github/workflows/postmerge-ci.yml` 是两个主编排器**（它们聚合了绝大多数校验、并各自带一个 `.github/scripts/check_ci_results.py` 聚合 job），但**它们不是仅有的事件入口**——发布、社区自动化、定时任务等 15 个工作流各有自己的触发器。两个主编排器的结构如下：

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

> `.github/workflows/blocking-ci.yml` 的注释直接点明：*"This is the single entrypoint for checks that block a PR merge"*；`required` job 是"版本控制的必需检查清单"，main 分支 ruleset 应当只要求这一个。
>
> **第一版把 `.github/workflows/blocking-ci.yml` / `.github/workflows/postmerge-ci.yml` 混在"Rust CI"一类里，掩盖了这个编排层次。**

### 4.2 `.github/workflows/rust-ci.yml` 到底跑什么（重要纠正）

> [!IMPORTANT]
> **`.github/workflows/rust-ci.yml` 不跑 codex-rs workspace 的测试，也不跑 clippy。** 第一版把它当成 PR 上的测试通道，是错的。
>
> 精确说法：它确实有一个 `cargo test`，但作用域是 workspace 之外的 `tools/argument-comment-lint`（另配一个 `python3 -m unittest discover`）。codex-rs 本体的 nextest 矩阵不在这里。
>
> 它的全部内容是：
>
> | job | 内容 |
> | ---- | ---- |
> | `changed` | 用 `git diff` 自行判断改动面，输出 **4 个** 维度（`.github/workflows/rust-ci.yml:11-15`）：`argument_comment_lint`、`argument_comment_lint_package`、`codex`、`workflows`；无关改动直接放行。其中 `argument_comment_lint_package` 正是下一行同名 job 的门控条件 |
> | `general` | `cargo fmt -- --config imports_granularity=Item --check` + `just bench-smoke` |
> | `cargo_shear` | `cargo shear --deny-warnings`（cargo-shear@1.11.2） |
> | `argument_comment_lint_package` | `tools/argument-comment-lint` 自身的 Python + Rust 测试（仅当该 lint 或其 workflow 接线被改动时） |
> | `argument_comment_lint_prebuilt` | Linux / macOS / Windows 三平台跑 argument-comment-lint |
> | results | 聚合，是唯一需要标为 required 的状态 |
>
> `.github/workflows/README.md` 的原话：*"`.github/workflows/rust-ci.yml` keeps the Cargo-native PR checks intentionally small"*，且 *"Keep `.github/workflows/rust-ci.yml` fast enough that it usually does not dominate PR latency."*
>
> **完整的 nextest 矩阵在 `.github/workflows/rust-ci-full.yml`**，只由 `.github/workflows/postmerge-ci.yml` 在 push main 时触发——**它不阻断 PR**。PR 上的 Rust 测试信号来自 `.github/workflows/bazel.yml`。

### 4.3 `.github/workflows/repo-checks.yml`：一批硬性仓库规则（第一版完全没覆盖）

它是 `.github/workflows/blocking-ci.yml` 的成员，因此**下面每一条都是合并阻断的**：

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

> **`.github/scripts/verify_tui_core_boundary.py` 值得单独记住**：TUI 与 core 的依赖边界是被 CI 机器强制的，不是口头约定。

> [!CAUTION]
> **"上表每一条都在真正校验"这个印象是错的——基线 checkout 上有三处需要限定（"机器强制 ≠ 真的在校验"）：**
>
> 1. **README ToC 检查在当前 README 上是 no-op。** 实跑 `python3 scripts/readme_toc.py README.md` 输出 `Note: Skipping ToC check; no markers found in README.md.` 并 **exit 0**——根 `README.md` 里没有 ToC 标记，这一步什么都没查。
> 2. **`.github/scripts/verify_cargo_workspace_manifests.py` 在基线 checkout 上直接 exit 1。** 报错是 `codex-rs/code-mode/Cargo.toml: - remove the stale [features] exception from MANIFEST_FEATURE_EXCEPTIONS`：脚本 `:28-31` 的 `MANIFEST_FEATURE_EXCEPTIONS` 仍为该清单登记了 `[features] sandbox` 例外，但该清单现已没有 `[features]` 段（`codex-rs/code-mode/Cargo.toml` 的段落只有 `[package]` `[lib]` `[lints]` `[dependencies]` `[dev-dependencies]`）。这**不是本地改动造成的**——`git log` 显示该清单最后一次变更是 `97576b1794 (#36217)`。
> 3. **npm 打包那一步依赖一个写死的历史 run。** `.github/workflows/repo-checks.yml:55-72` 把 `CODEX_VERSION=0.133.0-alpha.4` 与 `WORKFLOW_URL="https://github.com/openai/codex/actions/runs/26201494185"` 硬编码进 `scripts/stage_npm_packages.py` 的参数。一旦那个 run 的 artifact 过期，这一步就会失败，**且与被测代码毫无关系**。
>
> 顺带一提，脚本本身解释了为什么 workspace crate features 被禁：*"Workspace crate features are disallowed because our Bazel build setup does not honor them today, which can let issues hidden behind feature gates go unnoticed"*——正对应 §1.3 第 1 类分歧。

> [!WARNING]
> **`.github/actions/check-clean-worktree` 是"改脏工作区就红"的机器约束**：所有生成物（schema、fixtures、`MODULE.bazel.lock`、格式化结果）必须已经提交在 change 里。见 §7。
>
> **但它的覆盖面远没有本文上一稿说的那么广，需要限定：**
>
> ```bash
> grep -lr "check-clean-worktree" .github/workflows/*.yml | wc -l   # 8（共 30 个工作流）
> ```
>
> **只有 8 个工作流引用它**：`.github/workflows/bazel.yml`、`.github/workflows/blob-size-policy.yml`、`.github/workflows/cargo-deny.yml`、`.github/workflows/codespell.yml`、`.github/workflows/repo-checks.yml`、`.github/workflows/rust-ci.yml`、`.github/workflows/sdk.yml`、`.github/workflows/v8-canary.yml`。其余 19 个工作流（含 `.github/workflows/rust-ci-full.yml` 与全部 `rust-release*`）从不引用它。
>
> **但这 8 个不等于 `.github/workflows/blocking-ci.yml` 的成员**（本文上一稿写成"恰好就是"，与 §4.1 的编排图自相矛盾）：`.github/workflows/blocking-ci.yml` 只 `uses:` **7 个** reusable workflow（`:15`、`:20`、`:25`、`:30`、`:35`、`:40`、`:45`，即上表前 7 个）。第 8 个 `.github/workflows/v8-canary.yml` **不由 blocking-ci 调用**——它由 `.github/workflows/postmerge-ci.yml` 调用，另外自带 `pull_request: {}` 触发器，因此仍会在每个 PR 上跑（见 §4.4 第 1 条）。
>
> 上一稿还说"`.github/workflows/rust-ci.yml` 的每个 job"都有——**也是 5/6，不是 6/6**。该文件 6 个 job（`changed`、`general`、`cargo_shear`、`argument_comment_lint_package`、`argument_comment_lint_prebuilt`、`results`）里只有 5 处 `uses: ./.github/actions/check-clean-worktree`（`:58`、`:85`、`:110`、`:166`、`:221`），**纯聚合 job `results` 没有**（它不产生任何文件，也就无从查起）。
>
> 准确表述：**pre-merge 校验类工作流的实质性 job 末尾都查工作区干净；postmerge 全量与发布链路不查。**

### 4.4 其余工作流

| 类别 | 工作流 | 备注 |
| ---- | ---- | ---- |
| **Bazel** | `.github/workflows/bazel.yml` | PR 主校验路径；Windows gnullvm 按 4 片分 shard；含 `verify-release-build` |
| **Cargo 快检查** | `.github/workflows/rust-ci.yml` | 见 §4.2 |
| **Cargo 全量（postmerge）** | `.github/workflows/rust-ci-full.yml`、`.github/workflows/rust-ci-full-nextest-platform.yml` | 见 §4.2、`testing_guide.md` §10 |
| **发布 — Rust** | `.github/workflows/rust-release.yml`、`.github/workflows/rust-release-windows.yml`、`.github/workflows/rust-release-zsh.yml`、`.github/workflows/rust-release-argument-comment-lint.yml` | 见 §5 |
| **发布 — 其他** | `.github/workflows/r2-release.yml`、`.github/workflows/rusty-v8-release.yml`、`.github/workflows/python-runtime-release.yml`、`.github/workflows/python-runtime-build.yml`、`.github/workflows/python-sdk-release.yml` | |
| **SDK** | `.github/workflows/sdk.yml` | |
| **仓库检查** | `.github/workflows/repo-checks.yml`、`.github/workflows/blob-size-policy.yml`、`.github/workflows/cargo-deny.yml`、`.github/workflows/codespell.yml` | 均由 `.github/workflows/blocking-ci.yml` 调用 |
| **V8 覆盖 canary** | `.github/workflows/v8-canary.yml` | **不是实验性工作流**，见下 |
| **models.json 定时刷新** | `.github/workflows/rust-release-prepare.yml` | **与发布无关**，见 §5.1 |
| **社区自动化** | `.github/workflows/cla.yml`、`.github/workflows/close-stale-contributor-prs.yml`、`.github/workflows/issue-deduplicator.yml`、`.github/workflows/issue-labeler.yml`、`.github/workflows/issue-translator.yml` | |

**三条纠正：**

1. **`.github/workflows/v8-canary.yml` 不是"实验性"工作流。** 它的触发器是 `workflow_call` + `pull_request: {}` + `workflow_dispatch`——**每个 PR 都会跑**，同时被 `.github/workflows/postmerge-ci.yml` 调用。它是 rusty-v8 的覆盖 canary，是否跑重活由 `.github/scripts/v8_canary_changes.py` 判断（yml 顶部注释说明：不能用触发器级 path filter，因为 `pull_request` 与 `workflow_call` 不能共享 path filter，所以脚本是唯一的判定来源）。
2. **`.github/workflows/close-stale-contributor-prs.yml` 与受邀制规则无关。** 它是每天 `cron: "0 6 * * *"` 跑一次，把**超过 `DAYS_INACTIVE = 14` 天没有更新**（`:24-25`）的 PR 关掉。关闭评论的措辞也是 "no updates for more than 14 days...feel free to reopen"。**它是陈旧 PR 清理，不是未受邀 PR 的自动关闭。**

3. **`.github/workflows/rust-release-prepare.yml` 与发布无关**，见 §5.1。

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

- **Windows 有独立的发布工作流**（`.github/workflows/rust-release-windows.yml`），与 §2.1 的补丁情况一致
- **`.github/workflows/blob-size-policy.yml`** 说明仓库对大文件入库有策略约束
- **`.github/workflows/cargo-deny.yml`** 做依赖许可证/安全审计
- 发布链路按产物拆分：Rust 二进制、R2（对象存储）、rusty-v8、Python runtime、Python SDK 各自独立

---

## 5. 发布链路与产物

### 5.1 触发方式：打标（E2）

发布**由 tag push 触发**。**仓库内没有任何工作流承担"确定版本号并打标"的职责**；唯一名字像的 `.github/workflows/rust-release-prepare.yml` 与发布无关（它是 cron 定时更新 `codex-rs/models-manager/models.json` 的 PR 机器人，见本节末的说明）。

| tag 形态 | 触发的工作流 |
| ---- | ---- |
| `rust-v*.*.*` | `.github/workflows/rust-release.yml`（主发布链路） |
| `codex-zsh-v*.*.*` | `.github/workflows/rust-release-zsh.yml` |
| `python-v*` | `.github/workflows/python-sdk-release.yml` |
| `rusty-v8-v*.*.*` | `.github/workflows/rusty-v8-release.yml` |

`.github/workflows/rust-release.yml` 头部注释给出的标准动作就是：

```bash
git tag -a rust-v0.1.0 -m "Release 0.1.0"
git push origin rust-v0.1.0
```

**版本一致性由 `tag-check` job 强制**（`.github/workflows/rust-release.yml` 第一个 job，步骤名 "Validate tag matches Cargo.toml version"）：必须是 tag ref、必须匹配 `^rust-v[0-9]+\.[0-9]+\.[0-9]+(-(alpha…|beta…))?$`、且 `rust-v` 之后的版本号必须等于 `codex-rs/Cargo.toml` 里的 version。正则全文（`.github/workflows/rust-release.yml:45`）：

```
^rust-v[0-9]+\.[0-9]+\.[0-9]+(-(alpha(\.[0-9]+){0,2}|beta(\.[0-9]+)?))?$
```

> [!WARNING]
> **这条正则有一份跨文件同步义务，而且没有任何自动校验。** `.github/workflows/rust-release.yml:43-44` 的注释写着 *"Keep this pattern in sync with `VERSION_RE` in `.github/scripts/publish_r2_release.py`"*——两处各写一遍、靠人记住。改一处忘另一处，症状会推迟到 `publish-r2` job 才出现。

**另一处易错点：npm 的发布判定比 GitHub Release 的严。** 两者用的是不同条件：

| 判定 | 位置 | 条件 |
| ---- | ---- | ---- |
| Release 是否标 prerelease | `.github/workflows/rust-release.yml:1287` | 版本号里只要含 `-` 就算 prerelease（`[[ "${version}" == *-* ]]`） |
| **是否发 npm** | `.github/workflows/rust-release.yml:1303-1311` | 只有 `^x.y.z$`（tag 为空）或 `^x.y.z-alpha.N(.M)?$`（tag 为 `alpha`）才发 |

⇒ **`beta` 版本会创建 GitHub Release，但不会发布到 npm。** tag-check 的正则允许 `beta`，npm 判定不允许，两者不是同一套规则。

发布链路末尾的 `update-branch` job 还会用 `gh api repos/${GITHUB_REPOSITORY}/git/refs/heads/latest-alpha-cli -X PATCH -f sha="${GITHUB_SHA}" -F force=true`（`:1642-1652`）**强推** `latest-alpha-cli` 分支到发布 commit。

> [!IMPORTANT]
> **纠正第一版**：第一版把"发布版本号的确定与打标流程"指向了 `.github/workflows/rust-release-prepare.yml`。**这个工作流和发布毫无关系。**
>
> 它只有 57 行，触发器是 `workflow_dispatch` + `cron: "0 */4 * * *"`（每 4 小时一次），做的事是：带鉴权头 curl `${OPENAI_BASE_URL}/models?client_version=99.99.99`，把结果写进 `codex-rs/models-manager/models.json`，然后用 `create-pull-request` 开一个标题为 "Update models.json" 的 PR。名字里的 "release-prepare" 有误导性。
>
> **真正的版本/打标逻辑在 `.github/workflows/rust-release.yml` 的 `tag-check` job。**

### 5.2 `.github/workflows/rust-release.yml` 的 20 个 job

> **第 6 轮：job 从 15 个增至 20 个**，新增 `push`、`build-macos-voice`（对应新的语音子系统）、`provisioned-macos-candidate`、`stage-npm-packages`、`publish-r2-assets` 五个。复算：`grep -cE '^  [a-z0-9-]+:$' .github/workflows/rust-release.yml`

| 顺序 | job | 作用 |
| ---- | ---- | ---- |
| 0 | `push` | **第 6 轮新增**：触发链的起点 |
| 1 | `tag-check` | 校验 tag 与 `codex-rs/Cargo.toml` 版本一致（`.github/workflows/rust-release.yml:48-49` 的 `cargo_ver="$(grep -m1 '^version' codex-rs/Cargo.toml …)"`，校验的是 workspace 根清单） |
| 2 | `build` | **矩阵：4 个 target × 2 种 bundle（`primary` / `app-server`）**，跑 `cargo build --release`；timeout 90 分钟 |
| 3 | `build-macos-voice` | **第 6 轮新增**：macOS 语音子系统构建，对应 `codex-rs/voice-host` 与 `third_party/voice/` |
| 4 | `sign-macos-binaries` | 走受保护的 `codesigning` environment + Azure Key Vault（PKCS11）签名 |
| 5 | `package-macos` | 打包 |
| 6 | `sign-macos-dmg` | DMG 签名 |
| 7 | `finalize-macos` | 公证（notarization）与最终校验 |
| 8 | `provisioned-macos-candidate` | **第 6 轮新增** |
| 9 | `build-windows` | 调用 `.github/workflows/rust-release-windows.yml` |
| 10 | `argument-comment-lint-release-assets` | 调用 `.github/workflows/rust-release-argument-comment-lint.yml` |
| 11 | `stage-npm-packages` | **第 6 轮新增**：npm 包暂存 |
| 12 | `release` | 汇总产物、生成 checksum manifest、创建 GitHub Release |
| 13 | `publish-r2-assets` | **第 6 轮新增**：R2 资产发布 |
| 14 | `publish-r2` | 调用 `.github/workflows/r2-release.yml`（`releases.openai.com`） |
| 15 | **`publish-dotslash`** | 发布 DotSlash 清单 |
| 16 | **`publish-npm`** | 发布 `@openai/codex` |
| 17 | `deploy-dev-website` | |
| 18 | **`winget`** | Windows 包管理器 |
| 19 | `update-branch` | |

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
- **`codex-zsh` 清单**：`.github/workflows/rust-release.yml` 用 `env.CODEX_ZSH_RELEASE_TAG`（基线上钉在 `codex-zsh-v0.1.0`）从对应 Release 下载 `codex-zsh`，再由 `codex_package.zsh.resolve_zsh_bin` 取出该 target 的 zsh 二进制放进包内 `codex-resources/zsh/`；`rg` 也是同类随行资源
- `release` job 另外产出 `codex-package_SHA256SUMS` 校验清单，并把 `codex-rs/core/config.schema.json` 作为名为 config-schema.json 的资产一并发布（`cp codex-rs/core/config.schema.json dist/config-schema.json`；这是 Release 资产名，不是仓库内路径）

每个归档内的可执行文件**文件名带平台后缀**（如 `codex-x86_64-unknown-linux-musl`），解压后通常需要重命名为 `codex`。

> 这解释了为什么 `codex-rs/cli/src/main.rs:100-105` 要显式设置 `bin_name = "codex"`——保证帮助输出不受实际文件名影响。同时 `codex-arg0` 支持按 argv[0] 分发。

#### 三类从仓库外拉取的产物

发布包里并非所有可执行文件都由本次构建产出，有三类是拉进来的：

| 产物 | 来源 | 机制 |
| ---- | ---- | ---- |
| **ripgrep（`rg`）** | 纯第三方 | `scripts/codex_package/rg` 是 DotSlash manifest，`providers[0].url` 指向 `https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/…`，每平台带 `sha256` digest |
| **`codex-zsh`** | 本仓构建，但走独立 tag 线 | 由 `.github/workflows/rust-release-zsh.yml` 从 upstream zsh commit `77045ef899e53b9598bebc5a41db93a548a40ca6`（`:9` 的 `ZSH_COMMIT`）加本仓补丁 `codex-rs/shell-escalation/patches/zsh-exec-wrapper.patch` 构建，发布到 `codex-zsh-v*.*.*` tag |
| **rusty_v8 静态库** | 本仓构建，独立 tag 线 | `.github/actions/setup-rusty-v8/action.yml:20,38-48` 从 `https://github.com/openai/codex/releases/download/rusty-v8-v${version}/` 下载 `librusty_v8_*.a.gz`、`src_binding_*.rs` 与 `.sha256`，并做校验；由 `.github/workflows/rusty-v8-release.yml` 生产 |

> [!WARNING]
> **`codex-zsh` 这条有个坑**：主发布工作流并不构建 zsh，而是从一个**写死的旧 tag** curl 下来的——`.github/workflows/rust-release.yml:18` 的 `env: CODEX_ZSH_RELEASE_TAG: codex-zsh-v0.1.0`。也就是说，改了 `codex-rs/shell-escalation/patches/zsh-exec-wrapper.patch` 或 `ZSH_COMMIT` 之后，**必须先发一个新的 `codex-zsh-v*` tag，再手动把这个 env 改过来**，否则主发布仍然打包旧的 zsh 二进制，且不会有任何报错。

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

> 这与 `.github/workflows/r2-release.yml` 工作流对应——`releases.openai.com` 很可能由对象存储承载。

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
| 统一格式化 | just fmt → `scripts/format.py` | justfile / Rust / Bazel-Starlark / Python | 是（`.github/workflows/repo-checks.yml` 跑 `just fmt-check`） |
| **Rust 导入粒度** | `cargo fmt -- --config imports_granularity=Item --check` | Rust | 是（`.github/workflows/rust-ci.yml` 的 `general` job） |
| **未用依赖检测** | `cargo shear --deny-warnings`（cargo-shear@1.11.2） | Cargo 依赖 | 是（`.github/workflows/rust-ci.yml` 的 `cargo_shear` job） |
| JS/MD/YAML 格式化 | `pnpm run format` → prettier | `*.json`、`*.md`、`docs/*.md`、`.github/workflows/*.yml`、`**/*.js` | 是（`.github/workflows/repo-checks.yml`） |
| Rust lint | `just clippy` / `just fix -p <crate>` | Rust | PR 上由 `.github/workflows/bazel.yml` 的 clippy job 阻断；完整 Cargo clippy 矩阵在 postmerge |
| 自定义 lint | `just argument-comment-lint` | Dylint，实现在 `tools/argument-comment-lint`（**workspace 之外的独立 crate**） | 是（`.github/workflows/rust-ci.yml`，Linux/macOS/Windows 三平台） |
| 仓库硬规则 | `.github/workflows/repo-checks.yml` 的一批 Python 校验脚本 | 见 §4.3 | 是 |
| 拼写 | CI `.github/workflows/codespell.yml` | 全仓 | 是 |
| 依赖审计 | CI `.github/workflows/cargo-deny.yml` | Cargo 依赖 | 是 |

> [!IMPORTANT]
> **`imports_granularity=Item`（第一版未提）**：本仓库的 rustfmt 检查带了非默认配置，要求 **每个 import 一行一个 item**。默认 `cargo fmt` 通过不代表 CI 通过——`just fmt` 会带上同样的配置，所以正常流程用 `just fmt` 即可。
>
> **`cargo shear`（第一版未提）**：会检测 `Cargo.toml` <!-- ref-exempt: 此处泛指任意 crate 的清单文件，非特定路径 --> 中声明但未被使用的依赖，`--deny-warnings` 意味着**留下一个多余依赖就会挂**。删代码时尤其容易踩到。

> `tools/argument-comment-lint/` 有自己的 `Cargo.toml` <!-- ref-exempt: 泛指该目录下的 crate 清单，前文已给出目录路径 -->，**不属于 `codex-rs` workspace**。它有两个驱动方式：Bazel（`--config=argument-comment-lint`）与预构建脚本（`tools/argument-comment-lint/run-prebuilt-linter.py`）。

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
| app-server TS 类型 + schema fixtures | `just write-app-server-schema` ⚠️ **当前跑不通，见下方警告** | 改了 app-server API 形状 |
| hooks schema fixtures | `just write-hooks-schema` | 改了 hooks 类型 |
| `MODULE.bazel.lock` | `just bazel-lock-update` | 改了 Cargo 依赖 |

> [!NOTE]
> **第 6 轮：这里原有的一条「必然失败」警告已经过期——上游把它修好了。**
>
> 旧版（基线 `bb5054fe47`）记载：`just write-app-server-schema` 的 recipe 体是 `cargo run -p codex-app-server-protocol --bin write_schema_fixtures -- {args}`，而该 crate 没有任何 `[[bin]]` 段，因此这条命令**跑不通**；当时给出的可用替代是 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`。
>
> **现在 recipe 直接调用的就是那个 Python 脚本**（`justfile:177-178`）：
>
> ```
> write-app-server-schema *args:
>     {{ python }} app-server-protocol/scripts/write_schema_fixtures.py {args}
> ```
>
> 即：**这条命令现在可以正常执行**，旧版的警告与替代方案说明都已不再适用。
>
> 连带地，下面那条「上游自身存在一处循环陈旧」（测试失败文案推荐一条跑不通的命令）**也随之解除**——文案推荐的命令现在是通的。该条已从 §7.1 的陈旧点清单移除。

四者都有**机器校验**：schema fixtures 有配套测试，Bazel 锁有 CI 检查。忘了跑就会失败。

### 7.1 上游文档的已知陈旧点

读 `AGENTS.md` 与工具报错文案时，以下几处已确认与当前代码不符。

> **第 6 轮变动**：原第一条（`just write-app-server-schema` 跑不通）**已被上游修复**，从本表移除，见本节上方的 NOTE。同时**新增一条**（AGENTS.md 指向的 v2 协议单文件路径已失效）。

| 陈旧点 | 陈旧内容 | 实际情况 |
| ---- | ---- | ---- |
| **`AGENTS.md:265`、`:275`** | 两处都指向 v2 协议的单文件路径 `app-server-protocol/src/protocol/v2.rs`<!-- ref-exempt: 反例——正文说明 AGENTS.md 给的这个路径不可解析 --> | **该文件不存在**。v2 协议已改为**目录形态** `codex-rs/app-server-protocol/src/protocol/v2/`（含 `mod.rs`、`shared.rs`、`account.rs` 等）。按字面路径去找会扑空 |
| **`AGENTS.md:68`** | *"Avoid `--all-features` for routine local runs… use it only when you specifically need full feature coverage"*，把 `--all-features` 说成"偶尔要用" | **workspace crate features 已被制度性禁止**（`.github/scripts/verify_cargo_workspace_manifests.py`，见 §4.3），`justfile:78-79` 的注释也写着 *"Workspace crate features are banned, so there should be no need to add `--all-features`."* 这条建议已无适用场景 |
| **`AGENTS.md:35`** 里的 `codex-rs/codex-mcp/src/mcp_connection_manager.rs` <!-- ref-exempt: 本行正在说明 AGENTS.md 给的这个路径不存在，引用不可解析恰是要表达的事实 --> | 该路径不存在 | 实际是 `codex-rs/codex-mcp/src/connection_manager.rs`；详见 [`AI_Coding_Context.md`](./AI_Coding_Context.md) |

> 兜底机制是 `.github/actions/check-clean-worktree`——它挂在 **8 个 pre-merge 校验工作流**的实质性 job 末尾（`.github/workflows/blocking-ci.yml` 调用的那 7 个，加上带自身 `pull_request` 触发器的 `.github/workflows/v8-canary.yml`；不是"每个 CI job"，口径与实测见 §4.3）。只要 CI 里跑一遍生成命令后工作区变脏，这一步就红。所以**生成物必须提交进同一个 change**（见 §4.3）。

---

## 8. 发布前检查清单

```
□ just fmt                                  已跑（需要 dotslash + uv，见 §6.1）
□ just test -p <crate> / just test          通过
□ just fix -p <crate>                       已跑（大改动）
□ 改了 Cargo 依赖 → just bazel-lock-update   已跑，锁文件入同一 change
□ 删了代码 → 顺手确认没留下未使用依赖（cargo shear 会挂）
□ 新增 include_str! 等 → BUILD.bazel compile_data 已补（见 §1.2）
□ 新建了 crate → 除加进 Cargo workspace 外，还手写了 BUILD.bazel
   （Bazel 侧不自动生成，漏了不会报错，见 §1.3）
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → fixtures 已重新生成
   （⚠️ just write-app-server-schema 当前跑不通，改用
     codex-rs/app-server-protocol/scripts/write_schema_fixtures.py，见 §7）
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
| `BUILD.bazel` 的编写规范（`codex_rust_crate` 的完整参数） | E1 | `codex-rs/docs/bazel.md`、`defs.bzl`、各 crate 的 `BUILD.bazel` |
| macOS 签名/公证链路的具体实现 | E1 | `.github/scripts/macos-signing/`、`.github/workflows/rust-release.yml` 的 `sign-macos-*` job |
| npm 包 `@openai/codex` 的构建 | E1 | `codex-cli/` 目录、`scripts/stage_npm_packages.py` |
| Python SDK / runtime 的发布链路 | E1 | `.github/workflows/python-sdk-release.yml`、`python-runtime-*.yml` |
| RBE（远程构建执行）配置 | E1 | `rbe.bzl` |
| `blob-size-policy` 的具体阈值 | E1 | `.github/workflows/blob-size-policy.yml` |
| benchmark 的指标与基线 | E1 | `just bench`、`//codex-rs:e2e-benchmarks` |
| `.codex/skills/` 下的 14 个 skill | E1 | 见 `development_workflow.md` §2.6 与 `testing_guide.md` §8 |

> 第一版列在这里的 `zstd/`（其实是文件，见 §4）与"发布打标流程指向 `.github/workflows/rust-release-prepare.yml`"两条已在本次修订中纠正并移除。

---

## 10. 相关文档

- [开发流程](./development_workflow.md) — 日常命令与提交前自检
- [测试指南](./testing_guide.md) — nextest 配置与 CI 测试
- [架构总览](./architecture_overview.md) §9 — 双构建系统概览
- [SDK 指南](./sdk_guide.md) — SDK 的构建与发布
- 仓库自带：[`docs/install.md`](../docs/install.md)、[`README.md`](../README.md)
