---
title: Codex CLI 架构总览
summary: 描述 openai/codex 的主二进制多前端架构、TUI 经 app-server-client 而非直连 codex-core 的 CI 强制边界（约束的是直接依赖与直接导入，core 仍会传递性链接进 TUI，且存在多条绕过 app-server-client 的直调路径）、协议先行的类型单一事实源、三平台沙箱（Linux 以 bubblewrap 为主、Landlock 已废弃）与跨操作系统进程分离、7 个随正式发布交付的辅助可执行文件、发布 bundle 的平台差异、配置与凭证的落盘位置，以及六类外部服务边界与按二进制而异的遥测默认值。第 6 轮上游同步修订：基线推进到 5c5308fc9a，子命令 27→30、mcp-server 前端整条移除、known-safe 白名单退役、新增语音实时与 Guardian 两个子系统。
keywords: codex | architecture | single-binary | app-server | app-server-client | sandbox | bubblewrap | process-boundary | external-service | round6
scope: openai/codex 仓库整体运行时架构与进程边界
related_files: codex-rs/cli/src/main.rs | codex-rs/core/src/config/mod.rs | codex-rs/utils/home-dir/src/lib.rs | codex-rs/tui/Cargo.toml | codex-rs/app-server-client/Cargo.toml | .github/scripts/verify_tui_core_boundary.py | codex-rs/linux-sandbox/src/landlock.rs | codex-rs/linux-sandbox/src/linux_run_main.rs | codex-rs/core/src/otel_init.rs | AGENTS.md | justfile | README.md
dependencies: dev_docs/crate_map.md | dev_docs/AI_Coding_Context.md | dev_docs/_analysis/upstream_sync_round6.md
verified_at: 2026-09-20
---

# Codex CLI 架构总览

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **阅读顺序建议**: 本文 → [`crate_map.md`](./crate_map.md) → 各专题文档

---

## 1. 一句话概括

**Codex 是一个以单个主二进制对外、多前端、收敛到同一份 codex-core 会话循环的本地编码智能体**：所有用户入口（TUI、非交互 exec、IDE 接入的 app-server、云任务、语音会话）**都能通过同一个 `codex` 可执行文件的子命令抵达**；其中 app-server 另有一份同名的独立二进制（`codex-app-server` crate 自己的 `[[bin]]`）随 `bundle: app-server` 发布，供 IDE 直接拉起（见 §3.4）。除 TUI 外的前端直接依赖 codex-core，**TUI 的会话/turn 能力则必须经由 `codex-app-server-client` 间接抵达 core**。

理解这一点是理解整个仓库的第一把钥匙 —— 它解释了为什么 `codex-core` 有 402,720 行、**67 个内部依赖**，也解释了为什么协议 crate `codex-protocol` 被 **77 个 crate** 依赖。

> **计数口径**（依赖类断言必须标口径）：上面两个数字是**仅 `[dependencies]` / `[build-dependencies]`（含 `[target.*]` 变体）**的口径。若把 `[dev-dependencies]` 一并计入并去重，`codex-core` 的出度是 **75**（多出的 8 个全是测试支撑 crate，如 `core_test_support`、`codex-test-binary-support`）；`codex-protocol` 的入度**两种口径都是 77**——没有任何 crate 只在测试里用它。两套口径的完整对照见 [`crate_map.md`](./crate_map.md) §4。
>
> **第 6 轮提示**：`codex-core` 的 402,720 行**已不再是全仓第一**，`codex-tui` 以 405,863 行反超。但 core 自身仍比基线涨了 36%，减负压力并未减轻——排名变化来自分母。详见 [`crate_map.md`](./crate_map.md) §6。

> [!CAUTION]
> **`codex-tui` 不得「直接」依赖、也不得「直接」import codex-core —— 这是 CI 强制的架构边界，不是风格建议。**
>
> - 校验脚本：`.github/scripts/verify_tui_core_boundary.py`，文件头注释即 `"""Verify codex-tui does not depend on or import codex-core directly."""`——**注意 `directly`**；脚本同时禁止 `codex-rs/tui/Cargo.toml` 出现 `codex-core` 依赖，以及源码出现 `codex_core::` / `use codex_core` / `extern crate codex_core`。
> - 由 `.github/workflows/repo-checks.yml` 执行（`run: python3 .github/scripts/verify_tui_core_boundary.py`）。
> - **例外一（再导出）**：`codex-app-server-client` 显式再导出 core 的配置类型（`pub mod legacy_core { pub mod config { pub use codex_core::config::*; } }`），TUI 在 165 处、82 个文件中使用（第 6 轮实测，基线为 93 处 / 40 文件——**两年半不到翻了近一倍，这条"过渡通道"正在变宽而不是收窄**）。校验脚本的报错文案也点名这是被认可的过渡通道，所以该边界约束的是**依赖边与 import**，而非「core 能力必须经协议方法抵达」。详见 [`tui_guide.md`](./tui_guide.md) §0.2。
> - **例外二（传递链接）**：门禁**不管**传递依赖。`codex-cloud-config`（`codex-rs/cloud-config/Cargo.toml:30`）与 `codex-utils-oss`（`codex-rs/utils/oss/Cargo.toml:11`）都直接依赖 `codex-core`，而 TUI 正在用这两个 crate；`codex-app-server-client` 本身也直接依赖 `codex-core`。所以**编译产物里 `codex-core` 是链进 TUI 的**。E2 复核（读取上述 3 个 crate 的 Cargo 清单依赖声明）见 §2 的 CAUTION。
> - **正确路径**：`codex-tui` → `codex-app-server-client` → `codex-app-server` + `codex-core`。同进程用 `InProcessAppServerClient`，连远端 app-server 用 `RemoteAppServerClient`（均导出自 `codex-rs/app-server-client/src/lib.rs`）。
> - 在 TUI 中"顺手加一行 `use codex_core::...`"会直接挂 CI，无论功能是否正确。

---

## 2. 运行时拓扑

```mermaid
graph TB
    USER(("用户 / IDE / SDK"))

    subgraph BIN["主二进制 codex（codex-rs/cli）<br/>另随附 7 个辅助可执行文件，见 §3.4"]
        ARG0["arg0_dispatch_or_else<br/>main.rs:1174<br/>支持按 argv[0] 分发"]
        CLAP["clap Subcommand 枚举<br/>main.rs:150，30 个变体"]
    end

    subgraph FRONTEND["前端 / 服务端"]
        TUI["codex-tui<br/>交互式 TUI<br/>🚫 禁止「直接」依赖 codex-core（CI 强制）<br/>（core 仍会传递性链接）"]
        EXEC["codex-exec<br/>codex exec 非交互"]
        APPSRV["codex-app-server<br/>JSON-RPC 服务端"]
        CLOUD["codex-cloud-tasks<br/>[EXPERIMENTAL]"]
        VOICE["codex-voice-host<br/>语音/实时辅助进程"]
    end

    ASCLIENT["codex-app-server-client<br/>InProcessAppServerClient（同进程）<br/>RemoteAppServerClient（远端）"]

    CORE["codex-core<br/>会话 / turn / 工具调用 / 上下文"]

    subgraph EXECUTION["执行与隔离"]
        SANDBOX["codex-sandboxing<br/>Seatbelt / bwrap+seccomp / Windows"]
        EXECSRV["codex-exec-server<br/>可部署在另一操作系统"]
    end

    subgraph EXTERNAL["外部服务（按配置分流）"]
        OPENAI["OpenAI Responses API<br/>ChatGPT 后端通道"]
        LOCAL["本地模型<br/>Ollama / LM Studio"]
        MCPEXT["用户自带 MCP server"]
    end

    STORE[("CODEX_HOME<br/>默认 ~/.codex<br/>配置 / 凭证 / 会话")]

    USER --> ARG0 --> CLAP
    CLAP --> TUI & EXEC & APPSRV & CLOUD & VOICE
    TUI -->|会话/turn 能力的约定通路| ASCLIENT
    ASCLIENT --> APPSRV
    ASCLIENT --> CORE
    EXEC & APPSRV --> CORE
    ASCLIENT -.WebSocket / UDS.-> REMOTE["远端 app-server 实例<br/>（可在另一台机器 / 另一操作系统）"]
    CORE --> SANDBOX
    CORE -.可跨 OS.-> EXECSRV
    CORE --> OPENAI & LOCAL & MCPEXT
    CORE <--> STORE
    APPSRV <-.JSON-RPC.-> USER
```

> [!NOTE]
> 图中 `TUI --> ASCLIENT` 是 TUI 抵达 core **会话 / turn 能力**的约定通路：`codex-rs/tui/Cargo.toml` 的依赖表里没有 `codex-core`（**E2**，读配置文件），`tui/src/` 里也没有 `codex_core::`（**E3**，读源码），这两点由 `.github/scripts/verify_tui_core_boundary.py` 在 CI 上强制。`codex-app-server-client` 自身同时依赖 `codex-app-server` 与 `codex-core`（`codex-rs/app-server-client/Cargo.toml`），由它承担"跨越边界"的职责。
>
> **"约定通路"不等于"唯一通路"**：CI 门禁只禁 `codex-core` 这一个包名，TUI 里存在多条绕过 `codex-app-server-client` 的生产代码路径，且它们承载的是货真价实的业务能力（E3）：
>
> | 绕行路径 | 说明 |
> | ---- | ---- |
> | `codex_utils_oss::` | 探测 / 拉起本地 Ollama、LM Studio；`codex-rs/utils/oss/Cargo.toml:11` 自身 `[dependencies]` 直接依赖 `codex-core` |
> | `codex_cloud_config::` | 加载云配置 bundle；`codex-rs/cloud-config/Cargo.toml:30` 直接依赖 `codex-core` |
> | `codex_core_plugins::` | 插件市场名称常量与判定函数 |
>
> 因此本文对该边界的准确表述是"**会话 / turn 能力走 app-server-client**"，而不是"TUI 的一切能力都走 app-server-client"。
>
> > [!CAUTION]
> > **两条容易写错的表述（保留，仍然成立）：**
> >
> > 1. **"`codex-rs/tui/Cargo.toml` 只声明 `codex-app-server-client`"是错的。** 该文件的 `[dependencies]` 段里有 **51 条 `codex-*` 依赖**（全文件含 `[dev-dependencies]` 共 53 条，`grep -cE '^codex-' codex-rs/tui/Cargo.toml`；均写作 `{ workspace = true }`）。`cargo metadata` 解析后 `codex-tui` 的直接普通依赖有 **107** 个包。真正成立的说法只是「其中不含 `codex-core`」。
> > 2. **"TUI 不链接 `codex-core`"也是过度解读。** CI 脚本的文档注释原文是 `does not depend on or import codex-core **directly**`。传递地看，`codex-core` 照样会被链进 TUI：`codex-rs/cloud-config/Cargo.toml:30` 和 `codex-rs/utils/oss/Cargo.toml:11` 都直接依赖 `codex-core`；`codex-app-server-client` 本身也直接依赖 `codex-core`。E4 复核：在 `cargo metadata` 的普通依赖图上 BFS，`codex-tui → codex-app-server-client → codex-core` 可达。
> >
> > **准确表述：无直接依赖边、无直接导入（CI 强制）；`codex-core` 仍经多条中间 crate 传递性链接，且其配置类型通过 `codex_app_server_client::legacy_core` 再导出。** 详见 [`tui_guide.md`](./tui_guide.md) §0.1-§0.2。
> >
> > **第 6 轮数值变动**：`[dependencies]` 段的 `codex-*` 条数 42→51，`cargo metadata` 直接普通依赖 92→107，`legacy_core` 使用点 93→165。**三项全部上涨，但「不含 `codex-core`」这一条仍然成立**——边界没破，只是边界内侧变重了。

---

## 3. 入口层：一个二进制，30 个子命令

### 3.1 分发机制

`codex-rs/cli/src/main.rs` 是唯一主二进制的入口，两级分发：

1. **argv[0] 分发**（`codex-rs/cli/src/main.rs:10`、`:1174`）：`codex_arg0::arg0_dispatch_or_else` 允许通过可执行文件名改变行为。发布产物带平台后缀（如 `codex-x86_64-unknown-linux-musl`），但 `bin_name = "codex"` 保证帮助输出始终显示通用命令名（`codex-rs/cli/src/main.rs:129`）。
2. **clap 子命令分发**（`codex-rs/cli/src/main.rs:150` 起的 `Subcommand` 枚举 → `codex-rs/cli/src/main.rs:1236` 的 `match subcommand`）。

> **第 6 轮口径变化（承重）**：`:1237` 的第一条分支已不再是单纯的 `None =>`，而是 **`None | Some(Subcommand::Agents(_)) =>`** —— 新增的 `agents` 子命令与「无子命令」共用同一条默认 TUI 分支。因此「`None` 即默认 TUI」这句话仍对，但**反过来说「默认 TUI 只由 `None` 触发」已经不对了**。

### 3.2 子命令口径

| 口径 | 数量 |
| ---- | ---: |
| `Subcommand` 枚举变体总数 | **30** |
| 其中 `#[clap(hide = true)]` 隐藏 | 4（`TcpTunnel`、`Execpolicy`、`ResponsesApiProxy`、`StdioToUds`） |
| 其中平台条件编译 | 1（`App`，`#[cfg(any(target_os = "macos", target_os = "windows"))]`） |
| **Linux 上可见** | **25** |
| **macOS / Windows 上可见** | **26** |

> **第 6 轮变动**：新增 `Agents`、`MigrateRollouts`、`Queue`、`TcpTunnel` 四个变体，删除 `McpServer` 一个。隐藏变体从 3 个增至 4 个（新增的 `TcpTunnel` 即为 hidden）。

### 3.3 按用途分组

| 用途 | 子命令 |
| ---- | ---- |
| **核心交互** | （无子命令，默认 TUI）、`agents`、`exec`、`review` |
| **会话管理** | `resume`、`fork`、`archive`、`unarchive`、`delete`、`queue`、`migrate-rollouts` |
| **认证** | `login`、`logout` |
| **扩展生态** | `mcp`、`plugin` |
| **服务化** | `app-server`、`remote-control`、`exec-server` ⚠️ |
| **诊断运维** | `doctor`、`debug`、`features`、`completion`、`update` |
| **执行隔离** | `sandbox`、`execpolicy` 🔒 |
| **变更应用** | `apply` |
| **实验性** | `cloud`（别名 `cloud-tasks`）⚠️、`app`（桌面端，仅 macOS/Windows） |
| **内部用途** | `responses-api-proxy` 🔒、`stdio-to-uds` 🔒、`tcp-tunnel` 🔒 |

⚠️ = 标注 `[EXPERIMENTAL]`（`codex-rs/cli/src/main.rs:230` 的 `cloud`、`:242` 的 `exec-server`）　🔒 = `#[clap(hide = true)]`

> **第 6 轮变动**：`mcp-server` 整条移除（crate 已删）；`agents` / `queue` / `migrate-rollouts` / `tcp-tunnel` 新入表。**`exec-server` 是本轮唯一新标 `[EXPERIMENTAL]` 的服务化入口**——注意 `codex-exec-server` crate 本身有 57,913 行、相当成熟，实验性的是「把它作为独立服务跑」这条入口，不是这个 crate。

### 3.4 "单二进制"需要限定：还有 9 个随行的辅助可执行文件

"单二进制"指的是**用户交互只有一个入口 `codex`**，不是"交付物只有一个文件"。workspace 里除 `codex` 之外还定义了多个 `[[bin]]` 目标（E4，`cargo metadata` 的 `targets` 中 `kind` 含 `bin`），其中会随发布 / CI 产物一起分发或被 `codex` 在运行时拉起的有 9 个：

> **两个数字别混**：下表 9 行 = **随发布交付的 7 个 + 仅运行时/CI 使用的 2 个**（`codex-linux-sandbox`、`codex-execve-wrapper`）。断言账本登记的 `shipped_aux_binaries = 7` 指的是前者。

| 辅助可执行文件 | 所属 crate | 作用 | 随发布分发 |
| ---- | ---- | ---- | ---- |
| `codex-code-mode-host` | `codex-code-mode-host` | JS code-mode 的独立宿主进程 | **是**，出现在所有平台的 `primary` 与 `app-server` 两种 bundle 里；Windows 另有一个只装沙箱 helper 的 `bundle: helpers`，不含它 |
| `codex-responses-api-proxy` | `codex-responses-api-proxy` | 对应 hidden 子命令 `responses-api-proxy` | 是（primary bundle + Windows） |
| `codex-app-server` | `codex-app-server` | app-server 独立进程；发布矩阵为它单独准备了 `bundle: app-server` | **是**（app-server bundle + Windows） |
| `bwrap` | `codex-bwrap` | vendored bubblewrap；`codex-rs/cli/BUILD.bazel` 以 `extra_binaries = ["//codex-rs/bwrap:bwrap"]` 与 `codex` 一同产出 | 是（两个 Linux musl primary bundle） |
| `codex-windows-sandbox-setup` | `codex-windows-sandbox` | Windows 沙箱环境准备 | 是（Windows `helpers` bundle） |
| `codex-windows-sandbox-service` | `codex-windows-sandbox-service` | **第 6 轮新增**：Windows 沙箱常驻服务端 | 是（Windows `helpers` bundle） |
| `codex-command-runner` | `codex-windows-sandbox` | Windows 受限命令执行器 | 是（Windows `helpers` bundle） |
| `codex-linux-sandbox` | `codex-linux-sandbox` | Linux 沙箱 helper，由 `codex` 以子进程方式拉起 | 否（不在 release `binaries` 列表中；由 CI 拷入 helper 目录供测试） |
| `codex-execve-wrapper` | `codex-shell-escalation` | 权限提升时的 execve 包装（`codex-rs/shell-escalation/Cargo.toml:8-9`） | 否（同上，运行时 helper） |

> [!IMPORTANT]
> **引用 CI 配置的字符串列表时要整行贴，截断等于制造事实错误**（这是本体系上一轮的实际教训）。完整原文是 `.github/workflows/rust-release-windows.yml:7`：
>
> ```yaml
> WINDOWS_BINARIES: "codex codex-code-mode-host codex-responses-api-proxy codex-windows-sandbox-setup codex-windows-sandbox-service codex-command-runner codex-app-server"
> ```
>
> **第 6 轮变化**：该行新增 `codex-windows-sandbox-service`，从 6 项变为 7 项；去掉主二进制 `codex` 后，两个发布工作流的并集由基线的六项增至 **7 个辅助可执行文件**。

发布矩阵佐证（E2，`.github/workflows/rust-release.yml:89-132`）：非 Windows 的每个 target 拆成 `bundle: primary` 与 `bundle: app-server` 两条，`binaries` 字段分别是——

```yaml
# primary（macOS 两 arch）
binaries: "codex codex-code-mode-host codex-responses-api-proxy"        # :89 :101
# primary（Linux musl 两 arch，多一个 bwrap）
binaries: "codex codex-code-mode-host codex-responses-api-proxy bwrap"  # :114 :126
# app-server（全部四个 target）
binaries: "codex-app-server codex-code-mode-host"                       # :95 :107 :120 :132
```

macOS 的两组值（`primary` / `app-server`）还出现在签名（`:622-634`）、产物汇总（`:869-884`）与发布（`:1243` 起）几个阶段，是签名 / 公证 / DMG 专用 job，**不含 Linux 与 Windows** —— 带 `bwrap` 的那组 `binaries` 在这些处一次都没出现。

Windows 走独立工作流 `.github/workflows/rust-release-windows.yml`，其矩阵是**三种** bundle（`:27-63`，两个 arch 各三条）：

```yaml
bundle: primary     binaries: "codex codex-code-mode-host codex-responses-api-proxy"                            # :28 :35
bundle: helpers     binaries: "codex-windows-sandbox-setup codex-windows-sandbox-service codex-command-runner"  # :42 :49
bundle: app-server  binaries: "codex-app-server codex-code-mode-host"                                           # :56 :63
```

> **不要反过来推断"其余 bin 目标都不重要"。** workspace 共 **34 个** bin 目标（第 6 轮实测，基线为 31），出现在发布清单里的只有 **8 个**（`codex` + 7 个辅助）。**剩下 26 个里既有开发/测试类**（`codex-write-config-schema`、`rmcp_test_server` 等），**也有本身就是产品能力、只是不单独打包的**（`codex-exec`、`codex-tui`、`codex-execpolicy`、`codex-file-search`、`codex-stdio-to-uds`、`exec-server`、`apply_patch`——它们都编进主 codex 二进制或经上表的其他方式交付）。
>
> 判据是"是否出现在某个发布工作流的 `binaries` / `WINDOWS_BINARIES` 列表里"：`grep -hoE 'binaries: "[^"]*"' .github/workflows/rust-release*.yml`。
>
> [!WARNING]
> **这条判据有一个已知盲区，第 10 轮独立复核查出：`codex-voice-host` 走的是另一条交付通道。** 它在 `rust-release.yml` 里出现 19 次，却**不出现在任何 `binaries:` 列表中**——它由 Bazel 构建，再经 `third_party/voice/assemble_package.py:102` 放进包内的 `codex-resources/voice/bin/`。也就是说「不在 `binaries` 列表 ⇒ 不随发布交付」这个反向推断**不成立**。
>
> 上表的 `shipped_aux_binaries = 7` 是**发布工作流 `binaries` 列表口径**下的数字，本文继续沿用它（口径单一、可复算）；若改用「最终是否出现在用户拿到的包里」口径，还要算上 `codex-voice-host`，以及两个非 `codex-rs` 产物的第三方可执行文件 `codex-path/rg`（ripgrep）与 `codex-resources/<zsh>`。**语音包是否是正式发布的默认产物尚未取证**（`build-codex-package-archive.sh` 里 voice 是可选的 `--voice-release-dir`），所以本轮不把它并入主口径。


---

## 4. 协议先行：类型的单一事实源

这是本仓库最重要的工程约定之一。

```
Rust 类型定义（唯一事实源）
        │
        │  ts-rs 导出
        ▼
codex-app-server-protocol/schema/typescript/v2/*.ts（550 个文件，构建产物）
        │
        ▼
IDE 扩展 / 桌面端 / TypeScript SDK
```

**硬性规则**（来自 `AGENTS.md`）：

| 规则 | 出处（按标题定位，勿用行号） |
| ---- | ---- |
| v2 类型必须标注 `#[ts(export_to = "v2/")]` | `## App-server API Development Best Practices` → `### Core Rules`，搜 `export_to` |
| API 形状变更后须跑 `just write-app-server-schema` | 同章 `### Development Workflow`，搜 `write-app-server-schema` |
| 变更须用 `just test -p codex-app-server-protocol` 验证 | 同上，搜 `codex-app-server-protocol` |

> [!NOTE]
> 本文引用 `AGENTS.md` 一律给**章节标题 + 可 grep 的关键词**，不给行号 —— `AGENTS.md` 是高频改动文件，行号会静默失效。

> [!WARNING]
> 生成的 `.ts` 文件是**构建产物**，不是手写代码。文档与代码审查中都不得把它们描述为可直接编辑的源文件。

同类的"生成物"还有：

| 生成物 | 生成命令 |
| ---- | ---- |
| `config.toml` 的 JSON Schema | `just write-config-schema` <!-- ref-exempt: 指 CODEX_HOME 下的运行时用户配置文件，非仓库内文件 --> |
| hooks schema fixtures | `just write-hooks-schema` |
| app-server 协议 schema | `just write-app-server-schema` |

---

## 5. 进程边界与跨操作系统部署

### 5.1 五种进程形态

> [!NOTE]
> **本节标题上一稿写作"四种进程形态"，但表格是 5 行。** 这正是本文档体系反复批评的「标题计数与表格行数不符」，此处按实际行数改为 5。下表逐行可数：exec 单进程、TUI 同进程、TUI 连远端、客户端-服务端、守护进程。

| 形态 | 说明 | 相关 crate |
| ---- | ---- | ---- |
| **单进程（exec）** | `codex exec` 在本进程内直接跑 core | `codex-exec`、`codex-core` |
| **单进程（TUI，同进程 app-server）** | TUI 在**同一进程**内启动 `InProcessAppServerClient`，由该客户端持有 app-server 与 core；TUI 自身**不直接依赖、不直接导入 `codex-core`**（但 core 仍随中间 crate 传递性链接进同一个二进制，见 §2 的 CAUTION） | `codex-tui`、`codex-app-server-client`、`codex-app-server`、`codex-core` |
| **TUI ↔ 远端 app-server** | TUI 用 `RemoteAppServerClient` 连接一个**独立进程 / 独立机器**上的 app-server；core 完全跑在远端 | `codex-tui`、`codex-app-server-client`（`codex-rs/app-server-client/src/remote.rs`）、`codex-uds`；WebSocket 直接用第三方 crate `tokio-tungstenite` |
| **客户端-服务端** | app-server 以 JSON-RPC 对外服务，IDE / 桌面端 / SDK 作为客户端 | `codex-app-server`、`codex-app-server-transport`、`codex-app-server-client` |
| **守护进程** | `codex app-server daemon` 管理长驻生命周期，可启用 remote control | `codex-app-server-daemon`（`codex-rs/cli/src/main.rs:1169-1210`，注意该行号属 **CLI 的入口文件**，不是 daemon crate 自己的同名文件） |

> **勘误**：第一版此表只有三行，且把"单进程"写成"TUI / exec 直接在本进程内跑 core"。TUI 那一半是错的（见 §1 CAUTION），且遗漏了"TUI 连远端 app-server"这一形态。
>
> **勘误二（crate 存在 ≠ 在这条路径上生效）**：上一稿把 `codex-websocket-client` 列进了"TUI ↔ 远端 app-server"的相关 crate。**它不在这条路径上**：`codex-rs/app-server-client/Cargo.toml` 的 `[dependencies]` 里根本没有它；该 crate 的 WebSocket 走第三方 `tokio-tungstenite`（`codex-rs/app-server-client/src/remote.rs:51-53` 的 `use tokio_tungstenite::...`），UDS 走 `codex-uds`（同文件 `:39`）。`codex-websocket-client` 真正服务的是 `codex-api`、`code-mode` 与 `exec-server`（E2，`grep -rl codex-websocket-client codex-rs --include=Cargo.toml`）。**"仓库里存在一个名字对得上的 crate"从来不是"它在这条链路上被用到"的证据**，必须回到具体 crate 的 Cargo 清单依赖表和源码 `use` 语句去确认。

### 5.2 跨 OS 分离

`AGENTS.md` 的 `## Platform Support` 一节明确声明（搜 `different operating systems`）：

> "Codex supports running connected app-server and exec-server on different operating systems."

这意味着 `codex-exec-server`（39,311 行）可以运行在与 app-server 不同的操作系统上。相关传输设施包括 `codex-uds`（Unix domain socket）、`codex-stdio-to-uds`（stdio↔UDS 中继，hidden 子命令）、`codex-websocket-client`。

> [!NOTE]
> **传输实现细节仍未做代码级验证**（当前仅 `AGENTS.md` `## Platform Support` 的 E2 声明 + crate 存在性）。第 2 批 [`app_server_protocol.md`](./app_server_protocol.md) §7 复核后确认：**该缺口未能闭合**，`codex-exec-server-protocol`（1,723 行）是最佳切入点，跨 OS 集成测试见 `$remote-tests` skill。本节不推断实现方式。

---

## 6. 沙箱：三平台原生实现

沙箱是本项目的核心差异化能力，也是安全边界所在。

| 平台 | 机制 | 实现位置 |
| ---- | ---- | ---- |
| macOS | Seatbelt | `codex-rs/sandboxing/src/seatbelt.rs` + 3 个 `.sbpl` 策略文件 |
| **Linux（默认路径）** | **bubblewrap（文件系统）+ seccomp（系统调用）+ `no_new_privs`**；legacy Landlock 仅在显式开启 `[features].use_legacy_landlock` 时才走，且该 feature 已标 `Stage::Deprecated`、`default_enabled: false` | 调用侧 `codex-rs/sandboxing/src/bwrap.rs`；执行侧 `codex-linux-sandbox`（8,224 行）的 `codex-rs/linux-sandbox/src/linux_run_main.rs` / `codex-rs/linux-sandbox/src/landlock.rs`；bwrap 二进制来自 `codex-bwrap` crate（`codex-rs/bwrap`，151 行 Rust 壳）与**仓库内 vendored 的 bubblewrap C 源码 `codex-rs/vendor/bubblewrap/`（`git ls-files` 口径 50 个跟踪条目，`find -type f` 口径 49——差的一个是符号链接 `LICENSE` → `COPYING`；含 `codex-rs/vendor/BUILD.bazel` 则为 51 / 50）** |
| Linux（已废弃回退） | Landlock | 仅在显式打开 `[features].use_legacy_landlock` 时启用。CLI 开关 `--use-legacy-landlock` 为 `hide = true, default_value_t = false`（`codex-rs/linux-sandbox/src/linux_run_main.rs:110`）；`codex-features` 将其标为 `Stage::Deprecated`，`codex-rs/core/tests/suite/deprecation_notice.rs` 断言提示语"`[features].use_legacy_landlock` is deprecated and will be removed soon." |
| Windows | 原生沙箱 | `codex-rs/sandboxing/src/windows.rs`、`codex-windows-sandbox`（19,173 行） |

> [!CAUTION]
> **本节第一版严重写反了，此处保留勘误。** 第一版称 Linux 的机制是"**Landlock + seccomp**，bubblewrap 为备选"，并把实现指向 `codex-rs/sandboxing/src/landlock.rs`。三处都错：
>
> 1. **主次颠倒**。`codex-rs/linux-sandbox/src/landlock.rs` 的模块文档开宗明义：
>    > `//! In-process Linux sandbox primitives: no_new_privs and seccomp.`
>    > `//! Filesystem restrictions are enforced by bubblewrap in linux_run_main.`
>    > `//! Landlock helpers remain available here as legacy/backup utilities.`
>
>    同文件里的 `install_filesystem_landlock_rules_on_current_thread` 明确注明 "**currently unused** because filesystem sandboxing is performed via bubblewrap"。
> 2. **不存在"失败回退到 Landlock"**。`codex-rs/linux-sandbox/src/linux_run_main.rs:217` 的 `if !use_legacy_landlock { ... }` 分支注释写着 "This path **never falls back** to legacy Landlock on failure."；默认路径调用 `apply_permission_profile_to_current_thread(..., /*apply_landlock_fs*/ false, ...)`。
> 3. **文件指错**。`codex-rs/sandboxing/src/landlock.rs` 里**没有任何 landlock 调用**，它只是拼装 `codex-linux-sandbox` 子进程命令行（含在 legacy 模式下追加 `--use-legacy-landlock`）。真正的 `landlock` crate 依赖只出现在两处：`codex-rs/linux-sandbox/Cargo.toml:28`（普通 `[dependencies]`）与 `codex-rs/protocol/Cargo.toml:53`（在 `[target.'cfg(target_os = "linux")'.dependencies]` 段下，供类型定义使用）；版本声明源是 `codex-rs/Cargo.toml:345` 的 `[workspace.dependencies]`（`landlock = "0.4.4"`）。
>
> **正确心智模型：Linux = bwrap 管文件系统 + seccomp 管系统调用 + `no_new_privs`；Landlock 是待删除的 legacy 开关。**

配套能力：`codex-execpolicy`（执行策略）、`codex-shell-command`（命令解析）、`codex-shell-escalation`（权限提升审批）、`codex-process-hardening`（进程加固）。

> [!CAUTION]
> **绝对红线**：禁止新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码。这条规则没有例外。出处：`AGENTS.md` 顶部规则列表（无标题的一级列表），grep 关键词 `Never add or modify any code related to`。

---

## 7. 配置与凭证：CODEX_HOME

### 7.1 解析规则（E3，已读取实现）

配置目录由 `CODEX_HOME` 环境变量决定，未设置时默认 `~/.codex`。权威实现在 `codex-rs/utils/home-dir/src/lib.rs:13`：

- CODEX_HOME **已设置**：该路径必须存在且为目录，会被 canonicalize；否则返回错误（`codex-rs/utils/home-dir/src/lib.rs:20-50` 的 `find_codex_home_from_env`，其中 `:26` 做存在性检查、`:37` 做目录判定、`:43` 做 canonicalize）
- `CODEX_HOME` **未设置**：回退到 `~/.codex`，**不校验目录是否存在**

> [!TIP]
> **一个容易误判的点已澄清**：`codex-rs/core/src/config/mod.rs:4814` 也有一个 `pub fn find_codex_home`，但它是**薄委托**——函数体只有一行 `codex_utils_home_dir::find_codex_home()`。两处**不是重复实现**，`codex-utils-home-dir` 是唯一事实源。

### 7.2 落盘内容

| 内容 | 说明 |
| ---- | ---- |
| 配置 | `config.toml`（JSON Schema 由 `just write-config-schema` 生成） <!-- ref-exempt: 指 CODEX_HOME 下的运行时用户配置文件，非仓库内文件 --> |
| 凭证 | 认证态文件与系统钥匙串条目（`codex-login`、`codex-keyring-store`、`codex-secrets`） |
| 会话 | 线程与 rollout 记录（`codex-thread-store`、`codex-rollout`） |
| 状态与日志 | SQLite，可用 `just log` 实时查看（`codex-state`） |

> [!IMPORTANT]
> 本文档体系**不复述任何凭证的实际值**，只记录变量名、配置键名与文件路径。

---

## 8. 外部服务边界

README 描述 Codex "runs locally on your computer"，指的是**智能体进程在本地运行**，不等于"完全离线"或"不出网"。实际存在**六类**外部通路（第一版此处误写"三类"，与下表 6 行自相矛盾，已修正）：

| 类别 | 触发条件 | 端点 / 位置 | 证据 |
| ---- | ---- | ---- | ---- |
| **① 默认在线模型通路** | 默认路径 | `https://api.openai.com/v1`、`https://chatgpt.com/backend-api/codex` | E3，`codex-rs/model-provider-info/src/` |
| **② 认证通路** | 登录时 | `https://auth.openai.com`（含 `/oauth/token`、`/oauth/revoke`） | E3，`codex-rs/login/src/` |
| **③ 本地模型通路** | 用户显式配置 | Ollama（`codex-ollama`）、LM Studio（`codex-lmstudio`） | crate 存在 = **E1**；"有实现"= **E3**（已读 `codex-rs/ollama/src/`、`codex-rs/lmstudio/src/`） |
| **④ 用户自带 MCP server** | 用户显式配置 | 任意，由用户决定 | E3，`codex-rmcp-client`、`codex-mcp` |
| **⑤ 云任务** | `codex cloud`（实验性） | Codex Cloud 后端 | E3，`codex-rs/cli/src/main.rs:195-197` |
| **⑥ 遥测** | **随二进制而异**：前台型（TUI / exec / mcp-server）默认开指标，服务端型（app-server / remote-control / exec-server）默认关 | Statsig / OTLP | E3，`codex-rs/core/src/otel_init.rs`、`codex-rs/tui/src/lib.rs`、`codex-rs/app-server/src/main.rs` |

> [!IMPORTANT]
> **⑥ 遥测默认行为已完成代码级核查（E3），结论已定，不再是"待核实"**。三类导出器默认值**并不一致**：
>
> | 项 | 默认值 |
> | ---- | ---- |
> | `metrics_exporter` | **`Statsig`（开）** —— 但见下方两条前置条件 |
> | `trace_exporter` | `None`（关） |
> | `exporter`（通用） | `None`（关） |
> | `log_user_prompt` | **`false`（用户提示词不记录）** |
>
> **两条容易被漏掉的前置条件（对上一版结论的重要修正）**：
>
> 1. **analytics 关掉时，指标导出器被强制置为 `None`**。`codex-rs/core/src/otel_init.rs:70-77`（下为便于阅读的合并写法，源码把 `if config` / `.analytics_enabled` / `.unwrap_or(...)` 拆成了三行）：
>    ```rust
>    let metrics_exporter = if config.analytics_enabled.unwrap_or(default_analytics_enabled) {
>        to_otel_exporter(&config.otel.metrics_exporter)
>    } else {
>        OtelExporter::None
>    };
>    ```
>    也就是说 `metrics_exporter = Statsig` 只在 analytics 开启时才生效。
> 2. **`default_analytics_enabled` 的取值按二进制不同**，而且**不止 TUI 传 `true`**：
>
>    | 调用方 | 传入值 | 位置 |
>    | ---- | ---- | ---- |
>    | TUI 启动编排 | `true` | `codex-rs/tui/src/startup_orchestration.rs:558` |
>    | TUI 守护进程遥测 | `true` | `codex-rs/tui/src/daemon_telemetry.rs:47` |
>    | `codex exec` | `true` | `codex-rs/exec/src/lib.rs:173` |
>    | `codex migrate-rollouts` | `true` | `codex-rs/cli/src/migrate_rollouts.rs:63` |
>    | app-server | `false` | `codex-rs/app-server/src/main.rs:124` |
>    | remote-control | `false` | `codex-rs/cli/src/remote_control_cmd.rs:137` |
>    | exec-server 遥测 | `false` | `codex-rs/cli/src/exec_server_telemetry.rs:6` |
>
> **所以正确的说法是：交互式/一次性执行类前台二进制默认开，被集成的服务端形态（app-server、remote-control、exec-server 遥测）默认关。**
>
> > [!IMPORTANT]
> > **第 6 轮全部调用点位置改变，无一幸免**：TUI 的传入点从 `codex-rs/tui/src/lib.rs` 拆到 `codex-rs/tui/src/startup_orchestration.rs` 与 `codex-rs/tui/src/daemon_telemetry.rs` 两处；`codex mcp-server` 一行随 crate 删除；新增 `codex migrate-rollouts`。**分野本身（前台开 / 服务端关）没变，但每一行的位置都变了**——这是"结论对、证据全错"的典型样本。
> >
> > **复核需要两条 grep，一条是不够的**（各调用方写法不统一）：
> >
> > ```bash
> > # ① 具名常量式：命中 exec / cli-exec-server-telemetry（外加 app-server-test-client）
> > grep -rn "DEFAULT_ANALYTICS_ENABLED" codex-rs/ --include=*.rs
> > # ② 内联字面量 + argument-comment 式：命中 tui 两处 / app-server / remote-control / migrate-rollouts
> > grep -rn 'default_analytics_enabled\*/' codex-rs/ --include=*.rs
> > ```
> >
> > 两条 grep 各自都会多命中一些**不随发布交付的**目标，读结果时要剔除：① 会命中 `codex-rs/app-server-test-client/src/lib.rs:108`（测试客户端 bin，不在任何发布 `binaries` 列表里，见 §3.4）；② 会命中 app-server 与 tui 的测试。
>
> 另外 `Statsig` 在 **debug 构建下会降级为 `None`**，不发任何数据。完整证据与配置键见 [`observability.md`](./observability.md) §1-§3。

上述公开服务端点属于技术事实，按框架脱敏规范予以保留。

---

## 9. 双构建系统

仓库同时维护 Cargo 与 Bazel 两套构建：

| | Cargo | Bazel |
| ---- | ---- | ---- |
| 锁文件 | `codex-rs/Cargo.lock` | `MODULE.bazel.lock`（1,547,127 字节） |
| 日常开发 | ✅ 主用 | 发布与 CI 校验 |
| 发布构建 | — | `just build-for-release` → `//codex-rs/cli:release_binaries` |

> [!IMPORTANT]
> **依赖变更后必须同步双锁**：跑 `just bazel-lock-update` 并在同一个 PR 提交更新后的 `MODULE.bazel.lock`，CI 会校验漂移（AGENTS.md 顶部规则列表，grep `bazel-lock-update`）。
>
> 使用 `include_str!`、`sqlx::migrate!` 等**编译期读取文件**的宏时，还需在 `BUILD.bazel` 补 `compile_data`（`AGENTS.md` 顶部规则列表，grep `compile_data`）。

详见 [`development_workflow.md`](./development_workflow.md)。

---

## 10. 扩展面：四条路径，一个主扩展点

| 路径 | 入口 crate |
| ---- | ---- |
| ① 内建扩展 | `codex-rs/ext/`（15 个 crate，公共 API 在 `ext/extension-api`） |
| ② 插件 | `codex-core-plugins`（47,587 行）、`codex-plugin` |
| ③ Skills | `codex-rs/ext/skills`（22,219 行）、`codex-skills`（样例资产） |
| ④ MCP | 客户端 `codex-rmcp-client` / `codex-mcp`；扩展 `ext/mcp` |

> [!IMPORTANT]
> **关系已完成 `[dependencies]` 分段核查（E2）。第 6 轮实测为 11 / 15**（上一版 8 / 12）：
>
> | 依赖 `codex-extension-api` 的 11 个 | 不依赖的 3 个 | 第 15 个 |
> | ---- | ---- | ---- |
> | `ext/skills`、`ext/goal`、`ext/memories`、`ext/mcp`、`ext/image-generation`、`ext/web-search`、`ext/git-attribution`、`ext/guardian-v2`、`ext/guardian-reviewer`、`ext/history-notes`、`ext/queue` | `ext/agent`（只依赖 `codex-core` + `codex-protocol`）、`ext/connectors`（依赖 `codex-connectors` + `codex-core-plugins` + `codex-plugin` + `codex-utils-path-uri`）、`ext/items`（只依赖 `codex-utils-absolute-path`） | `ext/extension-api` 自身 —— 不要把它算成自己的"依赖方" |
>
> 结论：
>
> - `ext/extension-api` 仍是**主扩展点**（第 6 轮实测 **16 个**扩展 trait，见 [`crate_map.md`](./crate_map.md) §3.8），但**不是 `ext/` 目录的准入条件**。`ext/` 是一个**目录约定**，不是"必须实现 extension-api"的契约。
> - 不依赖它的**仍是原来那三个**，各有原因：**`ext/items` 是纯数据 / schema crate**（无行为，自然无 contributor）；**`ext/agent` 是子智能体辅助层**；二者都不是"贡献者型扩展"。
> - **`ext/connectors` 建立在插件机制之上**（依赖 `core-plugins` + `plugin`）。这一点削弱了"插件是完全平行的第二条赛道"的说法 —— 插件机制已经反向被 `ext/` 内的成员复用，两者是**交叉**而非平行。
> - `core-plugins` 自身确实**不**依赖 `extension-api`，由 `codex-core` 直接对接。
>
> **第 6 轮的三处结构变动**：
>
> 1. **③ Skills 路径改写**：`codex-core-skills` crate 被删（上游 `33e365b19e`「Remove the legacy core skill loader」），技能加载整体迁入 `ext/skills`——**Skills 从「被包装成扩展」变成「就是一个扩展」**，不再有独立的 core 侧 skills 运行时。
> 2. **④ MCP 路径失去服务端**：`codex-mcp-server` crate 被删（上游 `531f3836a1`），`codex mcp-server` 子命令一并移除。第四条路径现在只有客户端与扩展两截。
> 3. **Guardian 从 ext 的一个 77 行小成员膨胀为三 crate 子系统**（14,647 行在 `ext/` 内，另有 `guardian-context` 6,101 行在 ext 外）。
>
> 完整证据与选择依据见 [`mcp_and_extensions.md`](./mcp_and_extensions.md)。

---

## 11. 根 `docs/` 很薄，但"仓库没有开发者文档"是错的

> **勘误**：第一版本节标题为"仓库内文档极薄"，只列了 4 个 3–15 行的文件就得出"仓库缺少面向开发者的文档"的结论。这是**挑样本得结论**，并不成立 —— 分层看才准确。同时第一版把行数统计标为 E4，也是错的：文件行数属于 **E1（文件级事实）**，E4 应保留给实际跑构建 / 测试 / lint 工具的结论。

**第一层：根 `docs/` 与几处顶层 `*.md` 确实是薄的**（E1，`wc -l` 实测）：

| 文件 | 行数 |
| ---- | ---: |
| `docs/config.md` | 15 |
| `codex-rs/config.md` | 6 |
| `docs/sandbox.md` | 3（正文为指向 developers.openai.com 的外链） |
| `codex-rs/README.md` | 3 |

**第二层：per-crate 与规范文档一点都不薄**（E1，同批 `wc -l`，第 6 轮重测）：

| 文件 | 行数 | 内容 |
| ---- | ---: | ---- |
| `codex-rs/exec-server/README.md` | **517** | exec-server 协议与部署（基线 444，本轮增长） |
| AGENTS.md | **320** | AI 代理强制规范，本仓最高优先级文档 |
| `codex-rs/app-server/README.md` | **316** | **基线为 2,469 行，本轮缩至 1/8**，见下方 CAUTION |
| `codex-rs/docs/protocol_v1.md` | 191 | v1 协议 |
| `codex-rs/docs/bazel.md` | 180 | Bazel 构建 |

> [!CAUTION]
> **第 6 轮框架级变更：`codex-rs/app-server/README.md` 已不再是 app-server API 的权威文档。**
>
> 两项实测（E1/E2）：
>
> 1. **体量从 2,469 行缩到 316 行**，内容形态也变了——现在是「MCP App UI」「Initial Daybreak choice (experimental)」这类**逐特性的增量说明**，不是完整 API 参考。
> 2. **`AGENTS.md` 已不再提及它**：`grep -n 'README.md' AGENTS.md` **零命中**。基线时 `### Development Workflow` 要求「API 行为变更时同步更新 README」，该条已消失；现在 `## App-server API Development Best Practices`（`AGENTS.md:260`）指向的是 `codex-rs/app-server-protocol/src/protocol/common.rs` 与 `app-server-protocol/src/protocol/v2.rs` 两个**源码**位置。 <!-- ref-exempt: 反例——正文正在说明 AGENTS.md 给出的 v2.rs 这个路径不可解析 -->
>
>    ⚠️ **其中第二条是 `AGENTS.md` 自身的陈旧记载**：该文件**不存在**，v2 协议现在是**目录形态** `codex-rs/app-server-protocol/src/protocol/v2/`（内含 `codex-rs/app-server-protocol/src/protocol/v2/mod.rs` 与 `codex-rs/app-server-protocol/src/protocol/v2/shared.rs` 等）。按 `AGENTS.md` 的字面路径去找会扑空——这是本体系登记的第四条「AGENTS.md 陈旧记载」，见 [`AI_RULES.md`](./rules/combined/AI_RULES.md)。
>
> **对读者的实际影响**：找 app-server API 形状请以 **Rust 类型 + 生成的 schema** 为准（`codex-rs/app-server-protocol/`，631 个 TS 类型文件），不要再把该 README 当接口手册。详见 [`app_server_protocol.md`](./app_server_protocol.md)。
>
> 另：`codex-rs/docs/codex_mcp_interface.md`（基线 144 行）**已被整体删除**<!-- ref-exempt: 反例——正文说明该路径已不存在 -->，`codex-rs/docs/` 现只剩 `bazel.md` 与 `protocol_v1.md` 两个文件。

**修正后的判断**：面向**终端用户的产品文档**托管在 developers.openai.com、根 `docs/` 只留外链；面向开发者的接口文档**曾经**就近放在 crate 目录（`codex-rs/*/README.md`、`codex-rs/docs/`），但第 6 轮观察到这条路径正在**向源码与生成物收缩**——app-server README 瘦身、MCP 接口文档删除、AGENTS.md 改为直接指源码文件。**当前最可靠的接口事实源是 Rust 类型本身。**

本文档体系的价值空间因此要重新定位：不是"填补文档空白"，而是**提供跨 crate 的横向视角与归属决策** —— 这是 per-crate README 天然覆盖不到的部分。

> [!IMPORTANT]
> `AGENTS.md` 顶部规则列表（grep `Do not add general product or user-facing documentation`）禁止向 `docs/` 添加通用产品或用户文档（例外是 app-server API 文档）。**本文档体系全部产物固定在仓库根 `dev_docs/`，任何情况下都不得迁入 `docs/`。**

---

## 12. 本文未覆盖的内容

| 未覆盖项 | 当前证据等级 | 何时补齐 |
| ---- | ---- | ---- |
| `codex-core` 内部的 turn 循环与工具调度实现 | E1 | 第 2 批 `core_agent_loop.md` |
| app-server JSON-RPC 的方法清单与握手 | E2 | 第 2 批 `app_server_protocol.md` |
| 沙箱策略文件的具体规则 | E1（只确认了存在 3 个 `.sbpl` 文件，未读其内容） | 第 2 批 `tools_and_sandbox.md` |
| 配置项全集与优先级 | E2 | 第 2 批 `config_system.md` |
| ~~四条扩展路径的关系~~ | **E3，已完成**（并已修正为 8/12） | 见 `mcp_and_extensions.md` §1、本文 §10 |
| 认证流程的完整时序 | E3（端点已确认，流程未读） | 第 3 批 `auth_and_providers.md` |
| ~~遥测默认行为~~ | **E3，已完成**（含"按二进制而异"的修正） | 见 `observability.md`、本文 §8 |
| ~~实验性表面的展开~~ | **已完成** | 见 `experimental_surfaces.md` |
| exec-server ↔ app-server 的传输实现 | E2（仅 `AGENTS.md` `## Platform Support` 声明） | 未闭合，见 §5.2 |

---

## 13. 相关文档

- [Crate 地图](./crate_map.md) — 134 个 crate 的分层与归属决策
- [开发流程](./development_workflow.md) — 规范落地、构建与测试
- [AI 编码上下文主文档](./AI_Coding_Context.md) — 场景导航入口
- 仓库自带：[AGENTS.md](../AGENTS.md)（**优先级高于本体系**）、[`docs/contributing.md`](../docs/contributing.md)
