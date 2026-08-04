---
title: Codex 实验性与低频表面
summary: 逐项展开 Codex Cloud 任务、桌面端、remote-control、responses-api-proxy、v8-poc、code-mode 六个实验性或隐藏能力面，并补上初版遗漏的 exec-server、app-server 子命令自身、realtime 语音/WebSocket 会话、codex-features 门控体系、协议层 #[experimental] 宏与一批隐藏子命令；说明 experimental_* 配置键并不门控这些表面，而各表面的门控机制彼此不同——只有 code-mode 与 realtime 真正走 Feature 枚举，remote-control 走 daemon 持久化设置，其余表面没有运行时门控。
keywords: codex | experimental | cloud-tasks | remote-control | code-mode | v8-poc | responses-api-proxy | desktop-app | realtime | codex-features
scope: codex 中标注 experimental / hidden / PoC 的能力面
related_files: codex-rs/cli/src/main.rs | codex-rs/cloud-tasks/Cargo.toml | codex-rs/cloud-config/src/lib.rs | codex-rs/v8-poc/src/lib.rs | codex-rs/code-mode-runtime/src/lib.rs | codex-rs/app-server-daemon/src/lib.rs | codex-rs/responses-api-proxy/src/lib.rs | codex-rs/responses-api-proxy/src/dump.rs | codex-rs/features/src/lib.rs | codex-rs/app-server-protocol/src/protocol/common.rs | codex-rs/core/src/config/mod.rs | codex-rs/core/config.schema.json
dependencies: dev_docs/crate_map.md | dev_docs/architecture_overview.md
verified_at: 2026-08-05
---

# 实验性与低频表面

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **本文由用户明确要求生成**：疑问 3 的答复为「全部展开」
> **证据等级**: 成熟度标记与代码位置为 E3；crate 构成与目录清单为 E1/E2；各表面的内部行为多为 E1

> [!CAUTION]
> **本文已修订。** 初版有三处事实错误、一处覆盖不全：
>
> 1. **`codex-cloud-config` 不属于 Cloud 任务**——`codex-rs/cloud-tasks/Cargo.toml` 根本不依赖它。这正是本体系明令禁止的"凭 crate 名推断"。见 §1.2。
> 2. **cloud-tasks 不是"独立 TUI 应用"**——它依赖 `codex-tui`。见 §1.3。
> 3. **`experimental_*` 配置键并不门控本文的六个表面**——但门控机制**因表面而异**，并非统一走 `codex-features` 的 `Feature` 枚举（第二稿的说法过度概括，本稿已改为分表述）。见 §9.1。
> 4. 初版自称"全部展开"，但**漏掉了至少五类实验性表面**，已补入 §7。

---

## 0. 通读警告

> [!CAUTION]
> **本文覆盖的能力面全部带有实验性、隐藏或 PoC 标记。上游可能随时变更或移除它们，恕不另行通知。**
>
> 不要基于本文的内容构建长期依赖。每一节的首行都标注了该表面的**可见性**与**稳定性风险**。

### 初版展开的六个表面

| 表面 | 标记 | 可见性 | 主要 crate |
| ---- | ---- | ---- | ---- |
| Codex Cloud 任务 | `[EXPERIMENTAL]` | 可见 | `cloud-tasks` 系列 **3 个**（修订，见 §1.2） |
| 桌面端 | 无实验标记，但**平台条件编译** | macOS / Windows 可见 | `codex-rs/cli/src/app_cmd.rs` |
| remote-control | `[experimental]` | 可见 | `app-server-daemon`、`app-server-transport` |
| responses-api-proxy | `#[clap(hide = true)]` | **隐藏** | `responses-api-proxy` |
| v8-poc | 目录名即 PoC | 无 CLI 入口 | `v8-poc`（92 行） |
| code-mode | 无 CLI 子命令，有 just 任务 | 半公开——但**宿主二进制随每个 release bundle 交付**（见 §6.4） | `code-mode` 系列 4 个 |

**§7 补入的表面**：`codex exec-server`、`codex app-server` 子命令自身、realtime 语音/WebSocket 会话、`codex-features` 门控体系、协议层 `#[experimental]` 宏、一批隐藏子命令与隐藏登录参数。

另有两个隐藏子命令不在本文展开：`execpolicy`（见 [`tools_and_sandbox.md`](./tools_and_sandbox.md)）、`stdio-to-uds`（见 [`app_server_protocol.md`](./app_server_protocol.md)）。

---

## 1. Codex Cloud 任务

> **成熟度**：`[EXPERIMENTAL]`（`codex-rs/cli/src/main.rs:195`）
> **可见性**：`codex --help` 中可见
> **稳定性风险**：**高** —— 依赖云端后端，接口可能随服务端变更

### 1.1 入口

```rust
/// [EXPERIMENTAL] Browse tasks from Codex Cloud and apply changes locally.
#[clap(name = "cloud", alias = "cloud-tasks")]
Cloud(CloudTasksCli),
```

命令：`codex cloud`（别名 `codex cloud-tasks`），分发在 `codex-rs/cli/src/main.rs:1450`。

### 1.2 crate 构成：**3 个，不是 4 个**（E2，逐项核对 `codex-rs/cloud-tasks/Cargo.toml`）

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-cloud-tasks` | 5,248 | 主体 |
| `codex-cloud-tasks-client` | 1,117 | 客户端 |
| `codex-cloud-tasks-mock-client` | 270 | **模拟客户端**（`codex-rs/cloud-tasks/Cargo.toml` 里留有一条上游待办注释，说明它本应挪进 `[dev-dependencies]`） |

> [!CAUTION]
> **修订说明（原文错误）**：初版把 **`codex-cloud-config`（2,433 行）** 列为 Cloud 任务的第 4 个 crate，职责写成"云配置"。
>
> **`codex-rs/cloud-tasks/Cargo.toml` 完全不依赖 `codex-cloud-config`。** 它的依赖方是 `app-server`、`cli`、`exec`、`tui`——与 cloud-tasks 无关。
>
> 该 crate 的模块文档（`codex-rs/cloud-config/src/lib.rs:1-4`）自述：
>
> > *"Cloud-hosted configuration data for Codex. This crate owns transport, caching, and refresh behavior for cloud-delivered config data. Parsing and composition remain in `codex-config`."*
>
> 即**服务端下发的配置数据**（属于配置体系，见 [`config_system.md`](./config_system.md)），与"云端任务"毫无关系。**这是典型的"看 crate 名前缀 `cloud-` 就归类"的推断错误**，正是本体系明令禁止的做法。

### 1.3 模块（`cloud-tasks/src/`，E1：目录清单）

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/cloud-tasks/src/app.rs` / `codex-rs/cloud-tasks/src/ui.rs` | TUI 层（**注意与 `codex-rs/tui/src/app.rs` 区分**——它们同名但分属两个 crate，正是本节要澄清的对象） |
| `codex-rs/cloud-tasks/src/cli.rs` | 命令行参数 |
| `codex-rs/cloud-tasks/src/new_task.rs` | 新建任务 |
| `codex-rs/cloud-tasks/src/scrollable_diff.rs` | **可滚动 diff 视图** |
| `codex-rs/cloud-tasks/src/env_detect.rs` | **环境探测** |
| `codex-rs/cloud-tasks/src/util.rs` / `codex-rs/cloud-tasks/src/lib.rs` | — |

> [!CAUTION]
> **修订说明（原文错误）**：初版写「**这是一个独立的 TUI 应用**，不复用 `codex-tui`」。
>
> `codex-rs/cloud-tasks/Cargo.toml:27` 明确写着 **`codex-tui = { workspace = true }`**，另有 `ratatui` 与 `crossterm`。它**复用 `codex-tui`**，`codex-rs/cloud-tasks/src/app.rs` / `codex-rs/cloud-tasks/src/ui.rs` 是在其之上的自有界面，而不是另起炉灶。

`codex-rs/cloud-tasks/src/scrollable_diff.rs` 与命令描述中的 "apply changes locally" 对应——浏览云端任务产生的变更并在本地应用。

`mock-client` 的存在说明这条链路**可以脱离真实云服务测试**。

其他值得注意的依赖：**`codex-login`**（`codex-rs/cloud-tasks/Cargo.toml` 中以 `path = "../login"` 引入）与 `codex-model-provider`、`codex-http-client`、`codex-git-utils`。

> **部分澄清**：初版把"云端认证方式"整体标为 E1。至少可以确定 **cloud-tasks 复用 `codex-login` 的认证体系**（见 [`auth_and_providers.md`](./auth_and_providers.md)），而不是另有一套。
>
> **未验证**（E1）：云端 API 的协议细节、具体使用哪种 `AuthMode`、与 `codex-backend-client` 的关系。

---

## 2. 桌面端（`codex app`）

> **成熟度**：无 `[experimental]` 标记
> **可见性**：**仅 macOS / Windows**（Linux 上该子命令不存在）
> **稳定性风险**：中 —— 平台条件编译，行为随平台差异

### 2.1 入口（E3）

```rust
/// Launch the Desktop app (opens the app installer if missing).
#[cfg(any(target_os = "macos", target_os = "windows"))]
App(app_cmd::AppCommand),
```

`codex-rs/cli/src/main.rs:154-155` 定义，`:1260-1267` 分发。实现在 `codex-rs/cli/src/app_cmd.rs`。

### 2.2 行为要点

- **桌面 app 缺失时会打开安装器** —— 命令描述明文
- 分发时先调用 `reject_remote_mode_for_subcommand(...)`（`codex-rs/cli/src/main.rs:1261-1265`），**拒绝在 remote 模式下使用该子命令**

`README.md:7` 提到桌面端体验也可通过 `chatgpt.com/codex?app-landing-page=true` 获取。

> **注意**：桌面 app 本身**不在这个仓库里**。CLI 只负责拉起或引导安装。相关协议方法：`app/list`、`app/read`、`app/installed`、`app/list/updated`。

### 2.3 `--download-url`：**可覆盖安装器下载源**（E3）

`codex-rs/cli/src/app_cmd.rs` 全文只有 25 行，`struct AppCommand`（`:5`）只有两个字段，第二个就是它（`:10-12`）：

```rust
/// Override the app installer download URL (advanced).
#[arg(long = "download-url")]
pub download_url_override: Option<String>,
```

它随后被原样传给 `crate::desktop_app::run_app_open_or_install(workspace, cmd.download_url_override)`（`codex-rs/cli/src/app_cmd.rs:19`、`:23`，macOS / Windows 各一支）。

> [!WARNING]
> **这是本文覆盖面里风险最高的一个覆盖开关，而且它没有 `hide = true`——`codex app --help` 中直接可见。**
>
> §7.6 把 `--experimental_issuer`（覆盖 OAuth issuer）标为「高风险认证覆盖面」。**同一逻辑下 `--download-url` 的风险更高**：issuer 覆盖影响的是令牌流向，而下载源覆盖**落地的是一个会被执行的安装器二进制**。不要从不可信来源接受带此参数的命令行。

> **未验证**（E1）：默认下载源的取值、安装流程与是否校验签名/校验和。入口是 `codex-rs/cli/src/desktop_app/mac.rs`、`codex-rs/cli/src/desktop_app/windows.rs`。

---

## 3. remote-control

> **成熟度**：`[experimental]`（`codex-rs/cli/src/main.rs:150`）
> **可见性**：可见
> **稳定性风险**：**高** —— 涉及远程控制与鉴权，接口面大

### 3.1 入口

```rust
/// [experimental] Manage the app-server daemon with remote control enabled.
RemoteControl(RemoteControlCommand),
```

`codex-rs/cli/src/main.rs:150` 定义，`:1245` 分发。另有两个守护进程子命令：

- `codex app-server daemon enable-remote-control`（`codex-rs/cli/src/main.rs:1184`）
- `codex app-server daemon disable-remote-control`（`codex-rs/cli/src/main.rs:1188`）

### 3.2 类型体系（`codex-rs/app-server-daemon/src/lib.rs`，E3）

> [!NOTE]
> **勘误：路径头写错。** 上一稿这里写的是 `codex-app-server-daemon/src/lib.rs`<!-- ref-exempt: 这是被勘误的错误路径本身（反例），故意保留原文以说明错在哪里；正确路径在同句后半 -->——那是 **crate 名**，不是目录名，该路径在仓库里不存在。正确路径是 **`codex-rs/app-server-daemon/src/lib.rs`**。表内 7 个行号经复核全部正确，错的只是路径前缀。**crate 名与目录名在本仓库普遍不同（`codex-` 前缀被去掉），引用时要用目录名。**

| 类型 | 位置 |
| ---- | ---- |
| `LifecycleCommand` | `:38` |
| `LifecycleStatus` | `:47` |
| `BootstrapStatus` | `:86` |
| `RemoteControlStartOutput` | `:106` |
| `RemoteControlMode` | `:126` |
| `RemoteControlStatus` | `:139` |
| `pub async fn set_remote_control(mode: RemoteControlMode) -> Result<RemoteControlOutput>` | `:229` |

`set_remote_control` 的实现体只有两行：先 `ensure_supported_platform()?`，再 `Daemon::from_environment()?.set_remote_control(mode).await`。**它是 remote-control 真正的开关写入点**——写的是 daemon 的持久化设置，不是 `Feature` 枚举，详见 §9.1。

### 3.3 传输实现（`app-server-transport/src/transport/remote_control/`，**E1**：仅为目录/文件名清单，职责列是按文件名推断；初版标 E4 属评级过高，已下调）

| 文件 | 职责 |
| ---- | ---- |
| `codex-rs/app-server-transport/src/transport/remote_control/auth.rs` | **鉴权** |
| `codex-rs/app-server-transport/src/transport/remote_control/enroll.rs` | **注册/入网** |
| `codex-rs/app-server-transport/src/transport/remote_control/websocket.rs` + `codex-rs/app-server-transport/src/transport/remote_control/websocket_refresh_tests.rs` | WebSocket 连接与刷新 |
| `codex-rs/app-server-transport/src/transport/remote_control/clients.rs` / `codex-rs/app-server-transport/src/transport/remote_control/client_tracker.rs` | 客户端管理与追踪 |
| `codex-rs/app-server-transport/src/transport/remote_control/desired_state.rs` | **期望状态**（声明式同步） |
| `codex-rs/app-server-transport/src/transport/remote_control/protocol.rs` | 协议 |
| `codex-rs/app-server-transport/src/transport/remote_control/server_api.rs` | 服务端 API |
| `codex-rs/app-server-transport/src/transport/remote_control/segment.rs` | 分段 |

**这是一套完整的远程接入体系**：注册 → 鉴权 → WebSocket 长连 → 期望状态同步。协议侧有 `remoteControl/*` 共 8 个方法。

> [!WARNING]
> 这条路径**打开了远程控制本地 app-server 的能力面**。启用前请确认你理解其鉴权模型。本文未审计其安全性。

> **未验证**（E1）：鉴权机制的具体实现、`desired_state` 的同步语义。

---

## 4. responses-api-proxy

> **成熟度**：`#[clap(hide = true)]` + 描述以 "Internal:" 开头
> **可见性**：**隐藏**，`--help` 中不显示
> **稳定性风险**：**极高** —— 明确标为内部用途

### 4.1 入口

```rust
/// Internal: run the responses API proxy.
#[clap(hide = true)]
ResponsesApiProxy(ResponsesApiProxyArgs),
```

`codex-rs/cli/src/main.rs:199-200`。

### 4.2 crate 构成（1,007 行）

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/responses-api-proxy/src/lib.rs` | 主体，使用 `TcpListener`、`SocketAddr` —— **起本地 HTTP 服务** |
| `codex-rs/responses-api-proxy/src/main.rs` | 独立二进制入口 |
| `codex-rs/responses-api-proxy/src/read_api_key.rs` | **读取 API key** |
| `codex-rs/responses-api-proxy/src/dump.rs` | 请求/响应转储 |

### 4.3 监听地址：**仅回环 + 随机端口**（E3）

初版把这一项列为 E1 未验证，实际上一行代码就能确定（`codex-rs/responses-api-proxy/src/lib.rs:139`）：

```rust
fn bind_listener(port: Option<u16>) -> Result<(TcpListener, SocketAddr)> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port.unwrap_or(0)));
    // 省略：绑定与错误处理
}
```

- **地址硬编码为 `127.0.0.1`**——不监听 `0.0.0.0`，局域网内其他机器连不上。
- **端口默认 `0`**，即由内核分配随机端口；随后通过 `write_server_info(path, port)` 把实际端口写给调用方。

> [!IMPORTANT]
> **修订说明**：初版的 CAUTION 写「它会监听本地端口并处理 API key」，语气上把暴露面说得比实际大。**监听面仅限本机回环 + 随机端口**，这是相当收敛的设计。风险主要在"本机上的其他进程"，而不是网络侧。

### 4.4 dump **会脱敏认证头与 Cookie 头**（E3）

初版只说"`codex-rs/responses-api-proxy/src/dump.rs` 的存在意味着它可能会转储请求内容"，漏掉了它自带的脱敏：

`codex-rs/responses-api-proxy/src/dump.rs` 定义了一个认证头名常量与一个脱敏占位值常量（`:16-17`），并在写出请求头与响应头两处（`:160-161`、`:173-174`）都过一遍 `should_redact_header`。配套测试 `dump_request_writes_redacted_headers_and_json_body`（`:225` 起）锁定了这个行为。

> [!NOTE]
> **勘误：脱敏不止认证头一种。** 上一稿写"已知的脱敏只覆盖 Authorization 头"，并把"除此之外是否还有其他敏感头未脱敏"列为未验证项。实际的判定函数是两个条件的**或**（`codex-rs/responses-api-proxy/src/dump.rs:186-188`）：
>
> ```rust
> fn should_redact_header(name: &str) -> bool {
>     name.eq_ignore_ascii_case(AUTHORIZATION_HEADER_NAME)
>         || name.to_ascii_lowercase().contains("cookie")
> }
> ```
>
> 即：认证头做大小写不敏感的**全名匹配**，另外**任何小写后含 `cookie` 子串的头名都会被脱敏**（因此 `Cookie` 与 `Set-Cookie` 都覆盖到了）。这个"未验证"项据此撤销。

> [!CAUTION]
> **仍然是内部工具，不要在生产中依赖。** 脱敏只作用于**请求头/响应头**；**请求体与响应体是照原样落盘的**。会话内容、提示词、模型输出都可能出现在 dump 文件里。

> **未验证**（E1）：代理的整体转发行为、dump 的触发条件与落盘位置。

---

## 5. v8-poc

> **成熟度**：**PoC**，模块文档自述 "Bazel-wired proof-of-concept crate **reserved for future V8 experiments**"
> **可见性**：**无 CLI 入口**
> **稳定性风险**：不适用 —— 它目前不提供任何产品功能

### 5.1 全部内容（92 行，E3）

`codex-rs/v8-poc/src/lib.rs` 只有三个函数：

```rust
pub fn bazel_target() -> &'static str;          // 返回自身的 Bazel label
pub fn embedded_v8_version() -> &'static str;   // 返回内嵌 V8 版本
pub fn linked_v8_has_sandbox() -> bool;         // 链接的 V8 是否启用了 in-process sandbox
```

第三个函数通过 `unsafe extern "C" { fn v8__V8__IsSandboxEnabled() -> bool; }` 直接调用 V8 的 C API。

### 5.2 它实际验证的是什么

**这个 crate 不实现功能，它验证的是构建链路**：能否在 Bazel 下正确链接 V8，以及链接进来的 V8 是否带 in-process sandbox。

对应的基建：

- `MODULE.bazel` 中的 `llvm_rusty_v8_custom_libcxx.patch`（自定义 libc++）
- CI 工作流 `.github/workflows/rusty-v8-release.yml`、`.github/workflows/v8-canary.yml`

> **它与 code-mode 的关系**：`code-mode-runtime` 有 `codex-rs/code-mode-runtime/src/v8_init.rs`——**V8 是 code-mode 的运行时基础**。v8-poc 可以理解为这条链路的最小验证件。

---

## 6. code-mode

> **成熟度**：无 CLI 子命令，但有 `just code-mode-host` / `just bazel-code-mode-host` 任务
> **可见性**：半公开 —— 不在 `codex --help` 中，但有构建任务与协议
> **稳定性风险**：**高** —— 4 个 crate、独立协议，且核心 crate 有告警机制

### 6.1 crate 构成

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-code-mode-runtime` | 6,749 | 运行时，含 `codex-rs/code-mode-runtime/src/v8_init.rs`、`cell_actor/`、`session_runtime/` |
| `codex-code-mode` | 5,128 | 主体，含 `remote_session/` |
| `codex-code-mode-protocol` | 3,587 | 协议：`host/`、`codex-rs/code-mode-protocol/src/runtime.rs`、`codex-rs/code-mode-protocol/src/session.rs`、`codex-rs/code-mode-protocol/src/response.rs`、`codex-rs/code-mode-protocol/src/description.rs` |
| `codex-code-mode-host` | 3,517 | 宿主进程：`codex-rs/code-mode-host/src/delegate.rs`、`codex-rs/code-mode-host/src/peer.rs`、`codex-rs/code-mode-host/src/transport.rs` |

### 6.2 架构线索（E3 依赖 + **E1** 目录清单；初版的 E4 已下调）

```
codex-code-mode-host (独立二进制)
    ↕ transport.rs / peer.rs
codex-code-mode-protocol (host/ + runtime.rs + session.rs)
    ↕
codex-code-mode-runtime (v8_init.rs → V8 运行时)
    └── cell_actor/ + session_runtime/
```

**"cell actor"** 的命名暗示这是一个**基于单元格的执行模型**（类似 notebook）。配合 V8，指向"在沙箱化的 JS 运行时中执行模型生成的代码"这一方向。

### 6.3 与 core 的接入点

| 位置 | 说明 |
| ---- | ---- |
| `core/src/tools/code_mode/` | 工具侧接入 |
| `codex-rs/core/src/session/code_mode_warning.rs` | **code-mode 告警** |
| `codex-rs/core/tests/suite/code_mode.rs`、`codex-rs/core/tests/suite/code_mode_elicitation.rs` | 集成测试 |
| `codex-rs/core/src/tools/router.rs:255` 的 `dispatch_tool_call_with_code_mode_result_inner` | **工具分发直接感知 code-mode**（生产入口是 `:230` 的 `dispatch_tool_call_with_terminal_outcome`，见下方勘误） |

> [!CAUTION]
> **勘误：上一稿点名的 `dispatch_tool_call_with_code_mode_result`（`codex-rs/core/src/tools/router.rs:209`）是 `#[allow(dead_code)]` 的测试专用包装，生产调用方为 0。**
>
> 该属性就写在紧邻其上的 `codex-rs/core/src/tools/router.rs:207`。穷举 `grep -rn --include='*.rs' 'dispatch_tool_call_with_code_mode_result' codex-rs/` 得 7 处命中，逐条分类：
>
> | 命中 | 性质 |
> | ---- | ---- |
> | `codex-rs/core/src/tools/router.rs:209` | 声明（`#[allow(dead_code)]` 包装） |
> | `codex-rs/core/src/tools/router.rs:218`、`:242` | 两个包装各自对 `_inner` 的调用 |
> | `codex-rs/core/src/tools/router.rs:255` | `_inner` 的声明 |
> | `codex-rs/core/src/tools/router_tests.rs:521` | **测试** |
> | `codex-rs/core/src/session/tests.rs:10914` | **测试** |
> | `codex-rs/core/src/tools/parallel.rs:137` | **不是调用**——它是 `trace_span!` 的名字字符串 |
>
> 生产路径是：`dispatch_tool_call_with_terminal_outcome`（`codex-rs/core/src/tools/router.rs:230`，`pub(crate)`，无 `dead_code` 豁免）→ `dispatch_tool_call_with_code_mode_result_inner`（`:255`）。
>
> **结论（"工具分发直接感知 code-mode"）成立，但引用的符号选错了。** 这是本体系硬约束「**函数存在 ≠ 函数生效**」的教科书案例：`pub` + 名字贴切 + 位置显眼，三者都不能替代「谁在调用它」这一步。判据是**穷举 grep 该符号并逐条分类为 声明 / 生产调用 / 测试 / 字符串**——`#[allow(dead_code)]` 本身就是编译器在提示「本 crate 内无人调用」。

> [!NOTE]
> **勘误：`code_mode_warning` 不是"实验性信号"，它是模型兼容性告警。** 上一稿写「启用 code-mode 时会向用户发出告警——这本身就是『实验性』的信号」，读起来像是「只要开 code-mode 就会被警告这是实验功能」。实际不是。
>
> `codex-rs/core/src/session/code_mode_warning.rs:5-16` 的 `unsupported_code_mode_warning` 有三重提前返回：
>
> ```rust
> if !code_mode_enabled
>     || model_info.tool_mode.is_some()
>     || model_info.used_fallback_model_metadata
> {
>     return None;
> }
> ```
>
> 即：**只有在 code-mode 已启用、且当前模型的元数据没有声明 `tool_mode` 时才会触发**。告警文案本身也印证了这一点——*"...but model `{model}` does not advertise Code Mode support. This may degrade model performance."*
>
> **在一个支持 code-mode 的模型上启用 code-mode，一条告警都不会出。** 它衡量的是「模型是否适配」，不能被读作成熟度标记。

### 6.4 交付形态：**`codex-code-mode-host` 随每一个 release bundle 发布**（E3）

§0 把 code-mode 的可见性写作「半公开——不在 `codex --help` 中，但有构建任务与协议」。这个说法**低估了它的实际公开度**：它的宿主二进制是**随发布交付的**，不是只能自行构建的开发件。

`.github/workflows/rust-release.yml` 里 **20 处 `binaries:` 字段全部含 `codex-code-mode-host`**，覆盖 primary 与 app-server 两类 bundle × 四个目标平台，并贯穿构建、macOS 签名（`:496-508`）、打包（`:685-700`）与校验（`:991-1006`；`:1114` 有一条 `verify_signed_binary` 专门验它）四个阶段：

| bundle | `binaries:` 内容 |
| ---- | ---- |
| primary（macOS / Linux） | `codex codex-code-mode-host codex-responses-api-proxy`（Linux 另加 `bwrap`） |
| app-server | `codex-app-server codex-code-mode-host` |

Windows 侧同理：`.github/workflows/rust-release-windows.yml:7` 的 `WINDOWS_BINARIES` 常量为 `codex codex-code-mode-host codex-responses-api-proxy codex-windows-sandbox-setup codex-command-runner codex-app-server`——**`codex-code-mode-host` 是其中 6 个随发布交付的辅助二进制之一**。

> [!IMPORTANT]
> 把这一点与 §9.1 的 feature 表合起来看：**`code_mode_host` 是 `Stage::Stable` 且 `default_enabled: true`**。
>
> 也就是说，code-mode 的**宿主进程既随发布安装、其开关又默认打开**；真正默认关闭的是主开关 `code_mode`（`Stage::UnderDevelopment`）。**code-mode 的实际"公开度"显著高于「无 CLI 子命令」这一表象给人的印象**——缺的只是最后一步启用，而不是整条链路。

### 6.5 运行方式

```bash
just code-mode-host          # cargo 路径
just bazel-code-mode-host    # Bazel 路径
```

> **未验证**（E1）：code-mode 的启用配置、JS 沙箱的隔离边界、`cell_actor` 的执行模型。

---

## 7. 初版遗漏的实验性表面（修订补入）

> [!CAUTION]
> 初版声称"六个表面全部展开"。逐条核对 `codex-rs/cli/src/main.rs` 的属性宏与文档注释后，**至少还有以下五类实验性表面未被覆盖**，其中两类（realtime、`codex-features`）的体量都超过初版已展开的 v8-poc。

### 7.1 `codex exec-server`——与 Cloud 同级的 `[EXPERIMENTAL]`（E3）

```rust
/// [EXPERIMENTAL] Run the standalone exec-server service.
ExecServer(ExecServerCommand),
```

`codex-rs/cli/src/main.rs:207-208`。**用的是大写 `[EXPERIMENTAL]`，与 Cloud 任务（`:195`）同一档**，并且**没有 `hide = true`，在 `codex --help` 中可见**。相关 crate：`codex-exec-server`；遥测装配见 `codex-rs/cli/src/exec_server_telemetry.rs`（其 `DEFAULT_ANALYTICS_ENABLED = false`，见 [`observability.md`](./observability.md) §1.2）。

#### 它不是一个薄封装（E1，目录清单）

> [!NOTE]
> **上一稿在这里只给了 4 行 + 3 项未验证，展开力度明显失衡。** 本文 §7.3 刚批评初版「展开了 92 行的 v8-poc，却完全没提 7,500 行的 realtime」——`exec-server` 是同型问题的轻量版：它与 Cloud 同为大写 `[EXPERIMENTAL]`、同样在 `--help` 中可见，模块数却比本文展开的多数表面都多。

`codex-rs/exec-server/src/` 下有 **50 余个 `.rs` 文件加 6 个子目录**（`client/`、`server/`、`remote/`、`proto/`、`noise_relay/`）。按文件名可分为四组：

| 组 | 代表文件 | 按文件名推断的方向 |
| ---- | ---- | ---- |
| **客户端侧** | `codex-rs/exec-server/src/client.rs`、`codex-rs/exec-server/src/client_api.rs`、`codex-rs/exec-server/src/client_transport.rs`、`codex-rs/exec-server/src/client_recovery.rs` | 连接、传输与**断连恢复** |
| **能力协商** | `codex-rs/exec-server/src/capability_discovery.rs`、`codex-rs/exec-server/src/capability_discovery_cache.rs`、`codex-rs/exec-server/src/resolved_capability.rs` | 探测对端能力并缓存 |
| **文件系统 / 进程抽象** | `codex-rs/exec-server/src/local_file_system.rs` / `codex-rs/exec-server/src/remote_file_system.rs` / `codex-rs/exec-server/src/sandboxed_file_system.rs`、`codex-rs/exec-server/src/local_process.rs` / `codex-rs/exec-server/src/remote_process.rs`、`codex-rs/exec-server/src/fs_sandbox.rs`、`codex-rs/exec-server/src/process_sandbox.rs` | **本地/远程/沙箱三套并列实现**同一组抽象 |
| **传输与安全** | `codex-rs/exec-server/src/noise_channel.rs`、`codex-rs/exec-server/src/relay.rs`、`codex-rs/exec-server/src/relay_noise_tests.rs`、`codex-rs/exec-server/src/websocket_pong_watchdog.rs`、`codex-rs/exec-server/src/network_policy_decisions.rs` | **Noise 协议加密信道** + 中继 + WebSocket 保活 + 网络策略 |

> **这里最值得注意的两点**（均为按文件名的 E1 推断，未读实现）：
>
> 1. **`local_*` 与 `remote_*` 成对出现**，说明 exec-server 的设计目标是让「在本机执行」与「在远端执行」走同一组抽象——这解释了它为什么需要独立子命令，而不是并进 `codex exec`。
> 2. **出现了 `codex-rs/exec-server/src/noise_channel.rs` 与 `codex-rs/exec-server/src/relay.rs`**。Noise 是一套加密握手框架，配合 relay 与 `remote/`，指向**跨主机的执行通道**。

> [!WARNING]
> 若上述推断成立，这条表面涉及**跨主机执行命令**。它同时带 `[EXPERIMENTAL]` 标记且在 `--help` 中可见，**其安全边界本文完全未审计**。

> **未验证**（E1）：exec-server 的协议、与 `codex exec` 的关系、独立部署形态；上表的分组是按**文件名**推断的，各模块的实际职责与 Noise 信道的信任模型均未读实现验证。

### 7.2 `codex app-server` **子命令自身**就是实验性的（E3）

```rust
/// [experimental] Run the app server or related tooling.
AppServer(AppServerCommand),
```

`codex-rs/cli/src/main.rs:147-148`。初版在 §3 只提到 `app-server daemon` 的两个 remote-control 子命令，**从未指出 `codex app-server` 这个子命令本身带 `[experimental]` 标记**。

这一点对读 [`app_server_protocol.md`](./app_server_protocol.md) 的人尤其重要：**app-server 协议虽然文档化程度最高，其 CLI 入口在上游仍标注为实验性。**

其下的子命令成熟度也不齐：

| 子命令 | 标记 | 位置 |
| ---- | ---- | ---- |
| `generate-ts` | `[experimental]` | `codex-rs/cli/src/main.rs:610` |
| `generate-json-schema` | `[experimental]` | `codex-rs/cli/src/main.rs:613` |
| `generate-internal-json-schema` | `[internal]` + `hide = true` | `codex-rs/cli/src/main.rs:616-617` |
| `daemon pid-update-loop` | `[internal]` + `hide = true` | `codex-rs/cli/src/main.rs:650-651` |

### 7.3 realtime 语音 / WebSocket 会话——**体量最大的未覆盖表面**（E3）

初版展开了 92 行的 v8-poc，却完全没提这条**合计约 7,500 行**的表面。（上一稿此处写"上万行"，与紧接着那张自己列出的、合计 7,512 行的表格自相矛盾——**同一节里的定性词与定量表要对得上**。）

**配置键（6 个，`codex-rs/core/src/config/mod.rs:987-1008`）**：`experimental_realtime_ws_base_url`、`experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_model`、`experimental_realtime_ws_backend_prompt`、`experimental_realtime_ws_startup_context`、`experimental_realtime_start_instructions`。

**代码规模**：

| 位置 | 行数 |
| ---- | ---: |
| `codex-rs/codex-api/src/endpoint/realtime_websocket/`（14 个文件，含 v1 / v2 / frameless-bidi 三套协议） | 4,393 |
| `codex-rs/core/src/realtime_conversation.rs` | 2,465 |
| `codex-rs/core/src/realtime_context.rs` | 580 |
| `codex-rs/core/src/context/realtime_start_instructions.rs` / `codex-rs/core/src/context/realtime_end_instructions.rs` | 28 / 46 |
| **合计** | **7,512** |

> 口径说明：4,393 行是 `realtime_websocket/` 下 14 个 `.rs` 的 `wc -l` 总和，其中含 **3 个 `*_tests.rs`、共 316 行**（`codex-rs/codex-api/src/endpoint/realtime_websocket/methods_common_tests.rs` 150、`codex-rs/codex-api/src/endpoint/realtime_websocket/methods_frameless_bidi_tests.rs` 102、`codex-rs/codex-api/src/endpoint/realtime_websocket/protocol_frameless_bidi_tests.rs` 64）。**扣掉测试后该目录的实现代码约 4,077 行。**

`webrtc_call_base_url` 这个键名指向**语音通话**方向。这也是全仓 `experimental_*` 配置键中占比最大的一组（10 个里有 6 个）。

> [!WARNING]
> 这条表面**同时涉及麦克风类输入、长连 WebSocket 与独立的后端地址**（三个 base-url 键都可被用户覆盖）。它的隐私与安全边界本文完全未审计。

#### 门控：`Feature::RealtimeConversation`，**默认关闭**（E3）

上一稿把「默认是否关闭」列为未验证项——实际一查即知，现予撤销。

`codex-rs/features/src/lib.rs:1390-1395`：

```rust
FeatureSpec {
    id: Feature::RealtimeConversation,
    key: "realtime_conversation",
    stage: Stage::UnderDevelopment,
    default_enabled: false,
},
```

而且它**有明确的生产读取点**——`codex-rs/app-server/src/request_processors/turn_processor.rs:1053`：

```rust
if !thread.enabled(Feature::RealtimeConversation) {
    return Err(invalid_request(...));
}
```

即：未开启时，realtime 相关请求被直接拒绝。穷举 `grep -rn --include='*.rs' 'Feature::RealtimeConversation' codex-rs/` 共 4 处——1 处声明、1 处生产读取（上述）、2 处测试（`codex-rs/app-server/tests/suite/v2/realtime_conversation.rs:3552`、`:3554`）。

> **这条恰好支撑 §9.1 的论点**：realtime 是**除 code-mode 外第二个真正走 `Feature` 门控的表面**（声明 + 默认值 + 生产读取点三件套齐备）。本文覆盖的其余表面都不是。

> **未验证**（E1）：音频数据流向、与主会话循环的关系、三个 base-url 键被覆盖后的实际生效路径。

### 7.4 `codex-features`——仓库里**最系统的**实验性标记机制（E3）

初版 §8（原 §7）的"标记方式不统一"列了四种方式，**唯独漏了这个专门为此设计的机制**。

`codex-rs/features/src/lib.rs`：

- `pub enum Stage`（**`:38` 起**）：`UnderDevelopment` / `Experimental { name, menu_description, announcement }` / `Stable` / `Deprecated` / `Removed`——**成熟度是一等公民，不是文档注释里的一句话**。
- `pub enum Feature`（`:85` 起）：**102 个变体**。
- `Stage::Experimental` 变体带 `name` 与 `menu_description`，供 **`/experimental` 菜单**向用户展示。
- CLI 入口：**`codex features`**（`codex-rs/cli/src/main.rs:211`），子命令含 `list`（列出各 feature 的 stage 与生效状态）。

#### 成熟度分布要按 `stage:` 字段数，不能按注释分段数（E3）

> [!CAUTION]
> **本文上一稿在这里自相矛盾。** 它前一句刚说完「成熟度是一等公民，不是文档注释里的一句话」，下一句就用源码里的注释分段来给 102 个变体分类，写成「`// Stable.`（`:86`）只有 3 个，`// Experimental`（`:94`）起其余全部」。**这既背离了自己刚立的原则，事实上也不对**：
>
> - 枚举里其实有**三个**注释分段，不是两个：`// Stable.`（`:86`，3 个变体）、`// Experimental`（`:94`，78 个变体）、`// Removed`（`:270`，21 个变体）。所以"其余全部是 Experimental"漏掉了整整一段。
> - 更重要的是，**注释分段与真实的 `stage:` 值大面积不一致**。权威来源是 `FEATURES` 注册表里每个 `FeatureSpec` 的 `stage:` 字段。

按 `stage:` 统计（E4）：

```bash
grep -oE 'stage: Stage::[A-Za-z]+' codex-rs/features/src/lib.rs | sort | uniq -c
#   3 stage: Stage::Deprecated
#   1 stage: Stage::Experimental
#  32 stage: Stage::Removed
#  34 stage: Stage::Stable
#  31 stage: Stage::UnderDevelopment
```

| Stage | 数量 | 说明 |
| ---- | ---: | ---- |
| `Stable` | 34 | |
| `Removed` | 32 | 惯例上是保留为 no-op 的兼容开关，让旧配置仍能解析——但**这是逐个 feature 的消费端决定的，不是 `Stage` 决定的**，见下 |
| `UnderDevelopment` | 31 | 开发中，**不进 `/experimental` 菜单** |
| `Deprecated` | 3 | |
| `Experimental` | **1 或 2**（见下） | 只有这一档会出现在 `/experimental` 菜单里 |

> [!IMPORTANT]
> **上面这条 `grep` 只数到 101 条，比 102 个变体少一条**——差的那条恰恰是最有意思的一条。`Feature::PreventIdleSleep`（`codex-rs/features/src/lib.rs:1414-1431`）的 stage 是**平台条件表达式**，不是字面量：<!-- ref-exempt: 句首的 `grep` 是行文中的行内代码（指上一段那条命令），不是紧随其后那个文件引用的符号名；引用检查器把二者误配。文件路径与行号 1414-1431 已实测正确。 -->
>
> ```rust
> stage: if cfg!(any(target_os = "macos", target_os = "linux", target_os = "windows")) {
>     Stage::Experimental { name: "Prevent sleep while running", .. }
> } else {
>     Stage::UnderDevelopment
> },
> ```
>
> 所以准确说法是：**在 macOS / Linux / Windows 上 `Experimental` 有 2 个（`NetworkProxy` + `PreventIdleSleep`），`UnderDevelopment` 31 个；在其他 target 上则是 1 个与 32 个。**
>
> 这也说明：**纯文本 `grep` 计数在遇到条件编译时会静默漏项。数目对不上（101 ≠ 102）本身就是应当追查的信号，不该四舍五入过去。**

综合结论：**「实验性」这个词在 `codex-features` 里是极窄的一档**——102 个 feature 里只有 1~2 个是 `Stage::Experimental`；数量最多的三档分别是 `Stable`(34)、`Removed`(32) 与 `UnderDevelopment`(31)。用注释分段读出来的"78 个 Experimental"是完全错误的量级。

#### `Stage` 是**描述性**的，不是**可开启性**的（E3）

> [!IMPORTANT]
> **上面这张表容易被误读成「能不能开」——它不是。** 实测 `Stage` 在 `codex-rs/features/src/lib.rs` 中**唯一的行为性使用**是 `emit_metrics`（`:447-451`）：
>
> ```rust
> pub fn emit_metrics(&self, otel: &SessionTelemetry) {
>     for feature in FEATURES {
>         if matches!(feature.stage, Stage::Removed) {
>             continue;
>         }
>         // 省略：与 default_enabled 不同才上报
> ```
>
> **它只影响指标上报。** 而真正把用户配置落到开关上的 `apply_map`（`:466`）经 `feature_for_key`（`:637`）分支，**全程不检查 `stage`**——`feature_for_key` 只做 `spec.key == key` 的线性匹配，匹配不上再落到 `legacy::feature_for_key`。
>
> ⇒ **`Stage::Removed` 的 feature 照样能被用户在 `[features]` 里开启。** `Removed` 表达的是「上游认为它已退场」，不是「运行时会拒绝它」。
>
> **反例就在仓库里**：`Feature::WindowsSandbox` 与 `Feature::WindowsSandboxElevated` 都标 `Removed`，却仍被 `codex-rs/core/src/windows_sandbox.rs:34`、`:37`（`features.enabled(...)`）与 `:70`、`:77`（按 `.key()` 读取）实际读取，用于向后兼容映射；`codex-rs/tui/src/windows_sandbox.rs:27`、`:30` 同样在读。**所以「`Removed` = no-op」不成立**——是否 no-op 取决于每个 feature 的消费端有没有被一并删掉。
>
> 结论：判断「这个开关还有没有用」，`Stage` 只是线索，**唯一可靠的判据是看它的消费端**。

#### 判断「死开关」：`Stage` 与 `codex features list` 都判不出来

> [!CAUTION]
> **本节推荐的方法有一个盲区：它判不出「有声明、有 key、能开启、却零生产读取点」的死变体。**
>
> `Feature::RemoteControl` 就是这样一个：它在 `codex-rs/features/src/lib.rs:1396-1400` 有完整的 `FeatureSpec`（`key: "remote_control"`、`Stage::Removed`、`default_enabled: false`），因此**会出现在 `codex features list` 的输出里、也能被用户写进配置**——但穷举 `grep -rn --include='*.rs' 'Feature::RemoteControl' codex-rs/` **只有 2 处命中**：`codex-rs/features/src/lib.rs:1397`（声明）与 `codex-rs/features/src/tests.rs:209`（测试断言）。**生产读取点为 0。** 开或不开，行为完全一致。
>
> remote-control 真正的门控在别处，见 §9.1。
>
> 同类死变体还有 **`Feature::UseLinuxSandboxBwrap`**——穷举同样只有 2 处：`codex-rs/features/src/lib.rs:282`（`enum Feature` 的变体定义）与 `codex-rs/features/src/lib.rs:1033`（注册表条目）。
>
> **可靠判据：穷举 grep 该变体，看它是否只出现在「枚举定义 + `FeatureSpec` + 测试」里。** 这与 §6.3 那条「函数存在 ≠ 函数生效」是同一条原则在配置开关上的投影。

> [!TIP]
> **这仍是判断某项能力成熟度最系统的入口**——比逐个翻 `Subcommand` 的文档注释可靠得多。但要按顺序走完三步，缺一步就会误判：
>
> 1. 先跑 **`codex features list`**，确认这个 key 存在。
> 2. 再看 `FEATURES` 注册表里该 `FeatureSpec` 的 **`stage:` 与 `default_enabled:`**（注意不是注释分段，也注意 `stage` 可能是条件表达式）。
> 3. **最后穷举 `grep 'Feature::Xxx'`，确认它有生产读取点**——只有声明和测试的是死开关，前两步查不出来。

### 7.5 协议层的 `#[experimental("...")]` 属性宏——第五种标记方式（E3）

`codex-rs/app-server-protocol/src/protocol/common.rs` 里有一套宏，把 `#[experimental(reason)]` 编织进方法/类型的注册表。

> [!CAUTION]
> **勘误：上一稿点名的两个宏都是测试专用的，不是生产机制。**
>
> | 宏 | 位置 | 是否生产代码 |
> | ---- | ---- | ---- |
> | `experimental_reason_expr!` | `codex-rs/app-server-protocol/src/protocol/common.rs:81-93` | ✅ **这才是生产宏**——它把 `#[experimental(reason)]`、`inspect_params: true` 与"无标注"三种情况翻译成 `Option<&str>` 形式的实验性理由 |
> | `experimental_method_entry!` | `codex-rs/app-server-protocol/src/protocol/common.rs:96` | ❌ 紧邻其上的 `:95` 就是 `#[cfg(test)]` |
> | `experimental_type_entry!` | `codex-rs/app-server-protocol/src/protocol/common.rs:109` | ❌ 同理，`:108` 是 `#[cfg(test)]` |
>
> 上一稿给的展开位置 `:391-416` 起点也偏了：那三个消费上述测试宏的常量是 `EXPERIMENTAL_CLIENT_METHODS`、`EXPERIMENTAL_CLIENT_METHOD_PARAM_TYPES`、`EXPERIMENTAL_CLIENT_METHOD_RESPONSE_TYPES`，位于 **`:401-418`**，且**每一个都单独带 `#[cfg(test)]`**。
>
> 所以运行时真正读到"某个方法是不是实验性"的路径走的是 `experimental_reason_expr!`；那两个 `*_entry!` 宏只为测试期的清单断言服务。**引用 `macro_rules!` 时务必往上多看一行有没有 `#[cfg(test)]`。**

**全文件共 53 处 `#[experimental("...")]` 标注**，覆盖面远超初版的印象，例如：

> **计数口径（53 vs 66）**：这里的模式**带了左引号**（`#[experimental("`），是刻意的。不带引号计（`#[experimental(`）为 **66 处**，多出的 13 处是上述 `macro_rules!` 骨架里的 `$reason` 等**元变量匹配臂**，而不是对真实方法/类型的标注。**统计属性宏用量时必须把宏定义自身排除掉**，否则会把"定义"当成"使用"重复计入——这与 §7.4 那条「注释分段 ≠ `stage:` 字段」是同一类口径陷阱。

| 方法 | 位置 |
| ---- | ---- |
| `plugin/search` | `:732` |
| `remoteControl/*` 的 7 个请求（`enable`、`disable`、`status/read`、`pairing/start`、`pairing/status`、`client/list`、`client/revoke`） | `:939-976` |
| `thread/increment_elicitation`、`thread/settings/update`、`thread/memoryMode/set`、`memory/reset`、`thread/backgroundTerminals/*`、`thread/search`、`thread/turns/list` 等 | `:517` 起散布 |

> 这也补正了 §3.3 的一处口径：`remoteControl/*` 的**请求**是 7 个（外加 1 个通知 `remoteControl/status/changed`，`:1741`），合计 8 个协议方法。

### 7.6 其余隐藏入口清单（E3，`grep -n "hide = true" codex-rs/cli/src/main.rs`）

| 入口 | 位置 | 说明 |
| ---- | ---- | ---- |
| `codex debug trace-reduce` | `codex-rs/cli/src/main.rs:238-239` | *"Replay a rollout trace bundle and write reduced state JSON."*——对应 `codex-rollout-trace`（见 [`observability.md`](./observability.md) §6.3） |
| `codex debug clear-memories` | `codex-rs/cli/src/main.rs:242-243` | *"Internal: reset local memory state for a fresh start."* |
| `codex app-server --remote-control` | `codex-rs/cli/src/main.rs:541-542` | *"Enable remote control for this app-server process without changing persistence."*——**不是根级全局开关**，见下方勘误 |
| `codex login --api-key` 选项 | `codex-rs/cli/src/main.rs:476-483` | 已废弃，现在只会退出并提示改用 `--with-api-key` |
| **`codex login --experimental_issuer <URL>`** | `codex-rs/cli/src/main.rs:491` | **覆盖 OAuth issuer 基址**，`hide = true` |
| **`codex login --experimental_client-id <CLIENT_ID>`** | `codex-rs/cli/src/main.rs:495` | **覆盖 OAuth client ID**，`hide = true` |
| **`codex app --download-url <URL>`** | `codex-rs/cli/src/app_cmd.rs:10-12` | **覆盖桌面 app 安装器下载源**；**注意它没有 `hide = true`，在 `codex app --help` 中可见**。详见 §2.3 |

> [!CAUTION]
> **勘误：`--remote-control` 不是根级全局标志。** 上一稿把它写成"隐藏的全局开关，独立于子命令"。实际上它是 `struct AppServerCommand` 的字段（**`codex-rs/cli/src/main.rs:515`**，`:514` 是其上的 `#[derive(Debug, Parser)]`；`--remote-control` 在 `:540-542`），因此**只能写成 `codex app-server --remote-control`**。根 CLI 结构体是 `MultitoolCli`（`codex-rs/cli/src/main.rs:106`），里面没有这个字段。
>
> 同一个结构体里还有 `--strict-config`、`--listen`、`--stdio`、`--analytics-default-enabled` 等，全都是 app-server 子命令级的。**判断一个 clap 标志的作用域，要看它挂在哪个 `#[derive(Parser)]` 结构体上，不能只看 `hide = true`。**

> [!WARNING]
> **表中最后三项是本文覆盖面里风险最高的一组"任意 URL 覆盖"开关**：
>
> - 两个 `--experimental_*` 登录参数允许**把 OAuth 流程指向任意 issuer / client ID**。详见 [`auth_and_providers.md`](./auth_and_providers.md) §1.3。
> - `codex app --download-url` 允许**把桌面 app 安装器指向任意 URL**。**按同一逻辑，它的风险比前两者更高**——issuer 覆盖影响的是凭据流向，而下载源覆盖**落地的是一个会被执行的二进制**；而且前两者至少是 `hide = true`，它**在 `--help` 中直接可见**。
>
> 三者的共同点：**都以命令行参数形式绕过配置文件**，因此不会出现在 `config.toml`<!-- ref-exempt: 泛指用户机器上的 Codex 配置文件，不是仓库内的某个 config.toml --> 的审计范围内。不要从不可信来源复制粘贴带这些参数的命令行。

---

## 8. 这些表面的共同特征

| 观察 | 说明 |
| ---- | ---- |
| **多数有独立协议或独立二进制** | code-mode 有 4 个 crate 与独立协议；responses-api-proxy、exec-server 有独立 main；realtime 有三套协议版本 |
| **绝大多数有测试覆盖** | 即便是 PoC 也进 CI（`.github/workflows/v8-canary.yml`）。**例外是桌面端**：`codex-rs/cli/src/app_cmd.rs`（全文 25 行）**零测试**，仅其下游 `codex-rs/cli/src/desktop_app/mac.rs:324` 与 `codex-rs/cli/src/desktop_app/windows.rs:87` 各有一个 `#[cfg(test)]` 块。上一稿的"都有"过度概括 |
| **部分与 Bazel 深度绑定** | v8-poc 明说是 "Bazel-wired"；code-mode 有专门的 bazel 任务 |
| **标记方式不统一——已知 6 种** | ①`[EXPERIMENTAL]` / `[experimental]` 文档注释；②`#[clap(hide = true)]`；③平台 `cfg`；④目录名（v8-poc）；⑤**`codex-rs/features/src/lib.rs` 的 `Stage` 枚举**（§7.4）；⑥**协议层 `#[experimental(...)]` 宏**（§7.5）。**另见 `codex-rs/features/src/legacy.rs` 的 `ALIASES` 表（`:11` 起），可视为第 7 种**——它把 `experimental_use_unified_exec_tool`、`enable_experimental_windows_sandbox` 等旧配置键映射到现行 `Feature`，同样承载成熟度语义（"这个键已经过时了"）。此处不写"共"，因为**穷举面本身就未必封闭** |
| **大小写有含义（观察，非明文规则）** | `[EXPERIMENTAL]`（Cloud、exec-server）与 `[experimental]`（app-server、remote-control、generate-ts）并存；上游未说明二者是否有意区分，**不要据此推断成熟度差异** |

> [!TIP]
> **判断某个表面成熟度的可靠方法**（已修订，按可靠性排序）：
>
> 1. 先跑 **`codex features list`**，查 `Feature` 枚举上的 `stage:` 与 `default_enabled:`（§7.4）——这是最系统的一处。**但要记得走完第 4 步**。
> 2. 协议方法查 `codex-rs/app-server-protocol/src/protocol/common.rs` 上的 `#[experimental(...)]`（§7.5）。
> 3. CLI 表面查 `codex-rs/cli/src/main.rs` 的 `Subcommand` 枚举定义处的文档注释与属性宏。
> 4. **最后一律穷举 grep 该符号，确认它有生产读取/调用点**——`Stage` 只描述上游意图，不决定运行时行为；有声明未必有效果（§7.4 的 `Feature::RemoteControl`、§6.3 的 `dispatch_tool_call_with_code_mode_result` 都是这样被误判的）。
>
> **不要靠 crate 名或目录名猜测**——§1.2 的 `codex-cloud-config` 就是这么被归错类的。

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 建议入口 |
| ---- | ---- |
| Cloud 任务的云端 API 协议 | `codex-cloud-tasks-client`、`codex-backend-client` |
| 桌面 app 的安装器行为 | `codex-rs/cli/src/app_cmd.rs` |
| remote-control 的鉴权模型 | `codex-rs/app-server-transport/src/transport/remote_control/auth.rs`、`codex-rs/app-server-transport/src/transport/remote_control/enroll.rs` |
| responses-api-proxy 的整体转发行为与 dump 落盘位置 | `codex-rs/responses-api-proxy/src/lib.rs`、`codex-rs/responses-api-proxy/src/dump.rs` |
| code-mode 的 JS 沙箱隔离边界 | `codex-rs/code-mode-runtime/src/v8_init.rs`、`session_runtime/` |
| `cell_actor` 的执行模型 | `code-mode-runtime/src/cell_actor/` |
| realtime 会话的启用方式与音频数据流向 | `codex-rs/core/src/realtime_conversation.rs`、`codex-api/src/endpoint/realtime_websocket/` |
| exec-server 的协议与部署形态 | `codex-exec-server`、`codex-rs/cli/src/exec_server_telemetry.rs` |
| 102 个 `Feature` 各自的语义与默认状态 | `codex-rs/features/src/lib.rs`；或跑 `codex features list` |

### 9.1 关于"各表面的启用配置键"（修订）

> [!CAUTION]
> **修订说明（原文错误）**：初版在此表最后一行写「各表面的启用配置键 → `codex-rs/core/config.schema.json` 中的 `experimental_*` 键」，等于把读者指向了一个**不成立的假设**。

实测（E2，解析生成的 `codex-rs/core/config.schema.json`）：**93 个顶层键中只有 10 个以 `experimental_` 开头**，且**没有一个对应本文展开的六个表面**：

| `experimental_*` 键 | 实际对应 |
| ---- | ---- |
| `experimental_realtime_ws_base_url`、`experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_model`、`experimental_realtime_ws_backend_prompt`、`experimental_realtime_ws_startup_context`、`experimental_realtime_start_instructions` | **realtime 表面**（§7.3），6 个 |
| `experimental_compact_prompt_file` | 上下文压缩提示词文件 |
| `experimental_thread_config_endpoint` | 线程配置端点 |
| `experimental_thread_store` | 线程存储 |
| `experimental_use_unified_exec_tool` | 统一 exec 工具（另有对应的 `Feature::UnifiedExec`） |

**Cloud、桌面端、remote-control、responses-api-proxy、v8-poc、code-mode 六个表面，一个都不在这份清单里。**

#### 但门控机制**因表面而异**——第二稿的"统一走 `Feature` 枚举"是过度概括（本稿勘误）

> [!CAUTION]
> **勘误：上一稿在这里写「真正的门控在 `codex-rs/features/src/lib.rs` 的 `Feature` 枚举 `// Experimental` 段」，对六个表面全称成立——实测只有 code-mode 一个成立。**
>
> 这一稿犯的是与 §1.2 同型的错误：**给出了一个机制，却没有对这个机制本身跑一遍「默认值 + 生产构造点 + 调用方」三件套**。逐个表面核对如下。
>
> 另外，`// Experimental` 段这个定位**与本文 §7.4 刚立下的原则直接冲突**——§7.4 已论证「注释分段与真实 `stage:` 值大面积不一致，权威来源是 `FeatureSpec` 的 `stage:` 字段」，下一节却又回头用注释分段定位。这与本文 `:418` 批评上一稿的问题是同一型。**本节一律按 `stage:` 字段陈述。**

| 表面 | 真正的门控 | 判据 |
| ---- | ---- | ---- |
| **code-mode** | ✅ **`Feature` 枚举**（4 个 feature，见下表） | 三件套齐备：有 `FeatureSpec`、有默认值、有生产读取点——**工具集选择**在 `codex-rs/core/src/tools/mod.rs:70`（`else if turn_context.config.features.enabled(Feature::CodeMode)`），另见 `codex-rs/core/src/session/config_lock.rs:335`、`codex-rs/core/src/session/code_mode_warning.rs:10` |
| **realtime** | ✅ **`Feature::RealtimeConversation`** | 同上，生产读取点在 `codex-rs/app-server/src/request_processors/turn_processor.rs:1053`（§7.3） |
| **remote-control** | ⚠️ **daemon 持久化设置**，**不是 `Feature`** | 见下方警告 |
| **Cloud 任务** | ❌ **无运行时门控** | `Feature` 枚举中无任何对应变体；仅靠子命令始终可见 + `[EXPERIMENTAL]` 文档注释 |
| **桌面端** | ❌ **无运行时门控** | 同上无变体；可见性由**平台条件编译**（`#[cfg(any(target_os = "macos", target_os = "windows"))]`）决定 |
| **responses-api-proxy** | ❌ **无运行时门控** | 同上无变体；仅靠 `#[clap(hide = true)]` 从 `--help` 中隐去——**隐藏不等于禁用，知道名字就能调用** |
| **v8-poc** | ❌ **无门控可言** | **零反向依赖，不链接进任何二进制**——`codex-v8-poc` 在 `codex-rs/Cargo.toml` 中只出现在 workspace 成员表（`:94`）与 `[workspace.dependencies]` 声明（`:269`），没有任何 crate 依赖它；佐证是 `:530-536` 的 `[workspace.metadata.cargo-shear] ignored` 里专门列了它（**未使用依赖检测器把它标为误报才需要豁免**）。它没有可被"开启"的产品行为 |

> [!WARNING]
> **`Feature::RemoteControl` 是一个死变体，读它会得出错误结论。**
>
> 它**确实存在**——`codex-rs/features/src/lib.rs:1396-1400` 有完整的 `FeatureSpec`（`key: "remote_control"`、`stage: Stage::Removed`、`default_enabled: false`），所以它会出现在 `codex features list` 里，也能被写进 `[features]` 表。**但它的生产读取点为 0**：穷举 `grep -rn --include='*.rs' 'Feature::RemoteControl' codex-rs/` 只有 2 处——`codex-rs/features/src/lib.rs:1397`（声明）与 `codex-rs/features/src/tests.rs:209`（测试断言）。
>
> **remote-control 真正的门控是 daemon 的持久化设置**：`codex-rs/app-server-daemon/src/settings.rs:12` 的 `DaemonSettings { remote_control_enabled: bool }`，由 `codex-rs/app-server-daemon/src/lib.rs:229` 的 `set_remote_control(mode)` 写入——也就是 `codex app-server daemon enable-remote-control` / `disable-remote-control` 这两个子命令（§3.1）背后的东西。另有一个**不改持久化**的进程级开关 `codex app-server --remote-control`（§7.6）。
>
> 这是 §7.4 那条「死开关」判据的实例：**`stage` 与 `codex features list` 都判不出它**，只有穷举 grep 能。

#### code-mode 的四个 feature：**`stage` 与 `default_enabled` 才是"能不能用"的决定因素**（E3，`codex-rs/features/src/lib.rs:900-923`）

| Feature | key | `stage` | `default_enabled` | 文档注释 |
| ---- | ---- | ---- | ---: | ---- |
| **`CodeMode`** | `code_mode` | `UnderDevelopment` | **`false`** | *"Enable JavaScript code mode backed by the standalone host process."* |
| `CodeModeBufferedExec` | `code_mode_buffered_exec` | `UnderDevelopment` | `false` | *"Use a 30-second default yield timeout for code mode exec calls."* |
| **`CodeModeHost`** | `code_mode_host` | **`Stable`** | **`true`** | *"Run JavaScript code mode in the standalone host process."* |
| `CodeModeOnly` | `code_mode_only` | `UnderDevelopment` | `false` | *"Restrict model-visible tools to code mode entrypoints (`exec`, `wait`)."* |

> [!IMPORTANT]
> **上一稿这张表只有位置和文档注释，漏掉了 `stage` 与 `default_enabled`——而这两列才是读者真正要问的"我能不能用"的答案。** 补齐后有两点必须点明：
>
> 1. **主开关是 `code_mode`，`UnderDevelopment` 且默认关闭。** 想启用 code-mode，要开的是它。
> 2. **`code_mode_host` 名字相近，却是 `Stable` 且默认开——它不开启 code-mode。** 它只决定「**若** code-mode 已经在运行，是否走独立的 host 进程」。把它当成 code-mode 的总开关，会得出"code-mode 默认就是开的"这一错误结论。（这也与 §6.4 对上了：宿主二进制随发布交付、其开关默认打开，但**主开关默认关闭**。）
>
> 另有一条**联动规则**（`codex-rs/features/src/lib.rs:576-578` 的 `normalize_dependencies`）：
>
> ```rust
> if self.enabled(Feature::CodeModeOnly) && !self.enabled(Feature::CodeMode) {
>     self.enable(Feature::CodeMode);
> }
> ```
>
> 即**只开 `code_mode_only` 会自动把 `code_mode` 一并带开**。这是本文覆盖的 feature 中唯一一条自动联动。

> [!TIP]
> 找某个实验性表面的开关，按下列顺序，**且不要假定一定找得到**：
>
> 1. 查 `Feature` 枚举（`codex-rs/features/src/lib.rs`）——**但只有 code-mode 与 realtime 走这条**，且要按 §7.4 第 3 步确认有生产读取点。
> 2. 查 `codex-rs/core/config.schema.json` 的配置键——realtime 的 6 个 `experimental_*` 键在这里。
> 3. 查该表面**自有的持久化设置**——remote-control 走的是 `codex-rs/app-server-daemon/src/settings.rs`，既不在 `Feature` 里也不在 `codex-rs/core/config.schema.json` 里。
> 4. **接受"没有开关"这个答案**——Cloud、桌面端、responses-api-proxy 就没有；它们的"实验性"只体现在文档注释与 `--help` 可见性上，**运行时不设任何拦截**。
>
> `Feature` 与 config 键二者的关系见 [`config_system.md`](./config_system.md)。

---

## 10. 相关文档

- [Crate 地图](./crate_map.md) §3.10 — 实验性 crate 清单
- [架构总览](./architecture_overview.md) §3 — 子命令口径与可见性
- [app-server 协议](./app_server_protocol.md) — `remoteControl/*` 方法
- [构建与发布](./build_and_release.md) §2 — V8 与 hermetic 工具链补丁
- [工具与沙箱](./tools_and_sandbox.md) — `execpolicy` 隐藏子命令
