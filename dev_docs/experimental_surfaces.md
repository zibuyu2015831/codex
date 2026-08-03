---
title: Codex 实验性与低频表面
summary: 逐项展开 Codex Cloud 任务、桌面端、remote-control、responses-api-proxy、v8-poc、code-mode 六个实验性或隐藏能力面，并补上初版遗漏的 exec-server、app-server 子命令自身、realtime 语音/WebSocket 会话、codex-features 门控体系、协议层 #[experimental] 宏与一批隐藏子命令；说明 experimental_* 配置键并不门控这些表面、code-mode 的真实开关在 Feature 枚举。
keywords: codex | experimental | cloud-tasks | remote-control | code-mode | v8-poc | responses-api-proxy | desktop-app | realtime | codex-features
scope: codex 中标注 experimental / hidden / PoC 的能力面
related_files: codex-rs/cli/src/main.rs | codex-rs/cloud-tasks/Cargo.toml | codex-rs/cloud-config/src/lib.rs | codex-rs/v8-poc/src/lib.rs | codex-rs/code-mode-runtime/src/lib.rs | codex-rs/app-server-daemon/src/lib.rs | codex-rs/responses-api-proxy/src/lib.rs | codex-rs/responses-api-proxy/src/dump.rs | codex-rs/features/src/lib.rs | codex-rs/app-server-protocol/src/protocol/common.rs | codex-rs/core/src/config/mod.rs | codex-rs/core/config.schema.json
dependencies: dev_docs/crate_map.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 实验性与低频表面

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **本文由用户明确要求生成**：疑问 3 的答复为「全部展开」
> **证据等级**: 成熟度标记与代码位置为 E3；crate 构成与目录清单为 E1/E2；各表面的内部行为多为 E1

> [!CAUTION]
> **本文已修订。** 初版有三处事实错误、一处覆盖不全：
>
> 1. **`codex-cloud-config` 不属于 Cloud 任务**——`cloud-tasks/Cargo.toml` 根本不依赖它。这正是本体系明令禁止的"凭 crate 名推断"。见 §1.2。
> 2. **cloud-tasks 不是"独立 TUI 应用"**——它依赖 `codex-tui`。见 §1.3。
> 3. **`experimental_*` 配置键并不门控本文的六个表面**——真正的门控是 `codex-features` 的 `Feature` 枚举。见 §9.1。
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
| 桌面端 | 无实验标记，但**平台条件编译** | macOS / Windows 可见 | `cli/src/app_cmd.rs` |
| remote-control | `[experimental]` | 可见 | `app-server-daemon`、`app-server-transport` |
| responses-api-proxy | `#[clap(hide = true)]` | **隐藏** | `responses-api-proxy` |
| v8-poc | 目录名即 PoC | 无 CLI 入口 | `v8-poc`（92 行） |
| code-mode | 无 CLI 子命令，有 just 任务 | 半公开 | `code-mode` 系列 4 个 |

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

命令：`codex cloud`（别名 `codex cloud-tasks`），分发在 `main.rs:1450`。

### 1.2 crate 构成：**3 个，不是 4 个**（E2，逐项核对 `cloud-tasks/Cargo.toml`）

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-cloud-tasks` | 5,248 | 主体 |
| `codex-cloud-tasks-client` | 1,117 | 客户端 |
| `codex-cloud-tasks-mock-client` | 270 | **模拟客户端**（`Cargo.toml` 里留有一条上游待办注释，说明它本应挪进 `[dev-dependencies]`） |

> [!CAUTION]
> **修订说明（原文错误）**：初版把 **`codex-cloud-config`（2,433 行）** 列为 Cloud 任务的第 4 个 crate，职责写成"云配置"。
>
> **`cloud-tasks/Cargo.toml` 完全不依赖 `codex-cloud-config`。** 它的依赖方是 `app-server`、`cli`、`exec`、`tui`——与 cloud-tasks 无关。
>
> 该 crate 的模块文档（`cloud-config/src/lib.rs:1-4`）自述：
>
> > *"Cloud-hosted configuration data for Codex. This crate owns transport, caching, and refresh behavior for cloud-delivered config data. Parsing and composition remain in `codex-config`."*
>
> 即**服务端下发的配置数据**（属于配置体系，见 [`config_system.md`](./config_system.md)），与"云端任务"毫无关系。**这是典型的"看 crate 名前缀 `cloud-` 就归类"的推断错误**，正是本体系明令禁止的做法。

### 1.3 模块（`cloud-tasks/src/`，E1：目录清单）

| 文件 | 说明 |
| ---- | ---- |
| `app.rs` / `ui.rs` | TUI 层 |
| `cli.rs` | 命令行参数 |
| `new_task.rs` | 新建任务 |
| `scrollable_diff.rs` | **可滚动 diff 视图** |
| `env_detect.rs` | **环境探测** |
| `util.rs` / `lib.rs` | — |

> [!CAUTION]
> **修订说明（原文错误）**：初版写「**这是一个独立的 TUI 应用**，不复用 `codex-tui`」。
>
> `cloud-tasks/Cargo.toml:27` 明确写着 **`codex-tui = { workspace = true }`**，另有 `ratatui` 与 `crossterm`。它**复用 `codex-tui`**，`app.rs` / `ui.rs` 是在其之上的自有界面，而不是另起炉灶。

`scrollable_diff.rs` 与命令描述中的 "apply changes locally" 对应——浏览云端任务产生的变更并在本地应用。

`mock-client` 的存在说明这条链路**可以脱离真实云服务测试**。

其他值得注意的依赖：**`codex-login`**（`Cargo.toml` 中以 `path = "../login"` 引入）与 `codex-model-provider`、`codex-http-client`、`codex-git-utils`。

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

`main.rs:154-155` 定义，`:1260-1267` 分发。实现在 `codex-rs/cli/src/app_cmd.rs`。

### 2.2 行为要点

- **桌面 app 缺失时会打开安装器** —— 命令描述明文
- 分发时先调用 `reject_remote_mode_for_subcommand(...)`（`main.rs:1261-1265`），**拒绝在 remote 模式下使用该子命令**

`README.md:7` 提到桌面端体验也可通过 `chatgpt.com/codex?app-landing-page=true` 获取。

> **注意**：桌面 app 本身**不在这个仓库里**。CLI 只负责拉起或引导安装。相关协议方法：`app/list`、`app/read`、`app/installed`、`app/list/updated`。

> **未验证**（E1）：安装器的下载源与安装流程。入口是 `cli/src/app_cmd.rs`。

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

`main.rs:150` 定义，`:1245` 分发。另有两个守护进程子命令：

- `codex app-server daemon enable-remote-control`（`main.rs:1184`）
- `codex app-server daemon disable-remote-control`（`main.rs:1188`）

### 3.2 类型体系（`codex-app-server-daemon/src/lib.rs`，E3）

| 类型 | 位置 |
| ---- | ---- |
| `LifecycleCommand` | `:38` |
| `LifecycleStatus` | `:47` |
| `BootstrapStatus` | `:86` |
| `RemoteControlStartOutput` | `:106` |
| `RemoteControlMode` | `:126` |
| `RemoteControlStatus` | `:139` |
| `pub async fn set_remote_control(mode: RemoteControlMode)` | `:229` |

### 3.3 传输实现（`app-server-transport/src/transport/remote_control/`，**E1**：仅为目录/文件名清单，职责列是按文件名推断；初版标 E4 属评级过高，已下调）

| 文件 | 职责 |
| ---- | ---- |
| `auth.rs` | **鉴权** |
| `enroll.rs` | **注册/入网** |
| `websocket.rs` + `websocket_refresh_tests.rs` | WebSocket 连接与刷新 |
| `clients.rs` / `client_tracker.rs` | 客户端管理与追踪 |
| `desired_state.rs` | **期望状态**（声明式同步） |
| `protocol.rs` | 协议 |
| `server_api.rs` | 服务端 API |
| `segment.rs` | 分段 |

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

`main.rs:199-200`。

### 4.2 crate 构成（1,007 行）

| 文件 | 说明 |
| ---- | ---- |
| `lib.rs` | 主体，使用 `TcpListener`、`SocketAddr` —— **起本地 HTTP 服务** |
| `main.rs` | 独立二进制入口 |
| `read_api_key.rs` | **读取 API key** |
| `dump.rs` | 请求/响应转储 |

### 4.3 监听地址：**仅回环 + 随机端口**（E3）

初版把这一项列为 E1 未验证，实际上一行代码就能确定（`responses-api-proxy/src/lib.rs:139`）：

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

初版只说"`dump.rs` 的存在意味着它可能会转储请求内容"，漏掉了它自带的脱敏：

`dump.rs` 定义了一个认证头名常量与一个脱敏占位值常量（`:16-17`），并在写出请求头与响应头两处（`:160-161`、`:173-174`）都过一遍 `should_redact_header`。配套测试 `dump_request_writes_redacted_headers_and_json_body`（`:225` 起）锁定了这个行为。

> [!NOTE]
> **勘误：脱敏不止认证头一种。** 上一稿写"已知的脱敏只覆盖 Authorization 头"，并把"除此之外是否还有其他敏感头未脱敏"列为未验证项。实际的判定函数是两个条件的**或**（`responses-api-proxy/src/dump.rs:186-188`）：
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
- CI 工作流 `rusty-v8-release.yml`、`v8-canary.yml`

> **它与 code-mode 的关系**：`code-mode-runtime` 有 `v8_init.rs`——**V8 是 code-mode 的运行时基础**。v8-poc 可以理解为这条链路的最小验证件。

---

## 6. code-mode

> **成熟度**：无 CLI 子命令，但有 `just code-mode-host` / `just bazel-code-mode-host` 任务
> **可见性**：半公开 —— 不在 `codex --help` 中，但有构建任务与协议
> **稳定性风险**：**高** —— 4 个 crate、独立协议，且核心 crate 有告警机制

### 6.1 crate 构成

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-code-mode-runtime` | 6,749 | 运行时，含 `v8_init.rs`、`cell_actor/`、`session_runtime/` |
| `codex-code-mode` | 5,128 | 主体，含 `remote_session/` |
| `codex-code-mode-protocol` | 3,587 | 协议：`host/`、`runtime.rs`、`session.rs`、`response.rs`、`description.rs` |
| `codex-code-mode-host` | 3,517 | 宿主进程：`delegate.rs`、`peer.rs`、`transport.rs` |

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
| `core/src/session/code_mode_warning.rs` | **code-mode 告警** |
| `core/tests/suite/code_mode.rs`、`code_mode_elicitation.rs` | 集成测试 |
| `tools/router.rs:209` 的 `dispatch_tool_call_with_code_mode_result` | **工具分发直接感知 code-mode** |

> `code_mode_warning.rs` 的存在说明启用 code-mode 时会**向用户发出告警**——这本身就是"实验性"的信号。

### 6.4 运行方式

```bash
just code-mode-host          # cargo 路径
just bazel-code-mode-host    # Bazel 路径
```

> **未验证**（E1）：code-mode 的启用配置、JS 沙箱的隔离边界、`cell_actor` 的执行模型。

---

## 7. 初版遗漏的实验性表面（修订补入）

> [!CAUTION]
> 初版声称"六个表面全部展开"。逐条核对 `cli/src/main.rs` 的属性宏与文档注释后，**至少还有以下五类实验性表面未被覆盖**，其中两类（realtime、`codex-features`）的体量都超过初版已展开的 v8-poc。

### 7.1 `codex exec-server`——与 Cloud 同级的 `[EXPERIMENTAL]`（E3）

```rust
/// [EXPERIMENTAL] Run the standalone exec-server service.
ExecServer(ExecServerCommand),
```

`cli/src/main.rs:207-208`。**用的是大写 `[EXPERIMENTAL]`，与 Cloud 任务（`:195`）同一档**，并且**没有 `hide = true`，在 `codex --help` 中可见**。相关 crate：`codex-exec-server`；遥测装配见 `cli/src/exec_server_telemetry.rs`（其 `DEFAULT_ANALYTICS_ENABLED = false`，见 [`observability.md`](./observability.md) §1.2）。

> **未验证**（E1）：exec-server 的协议、与 `codex exec` 的关系、独立部署形态。

### 7.2 `codex app-server` **子命令自身**就是实验性的（E3）

```rust
/// [experimental] Run the app server or related tooling.
AppServer(AppServerCommand),
```

`cli/src/main.rs:147-148`。初版在 §3 只提到 `app-server daemon` 的两个 remote-control 子命令，**从未指出 `codex app-server` 这个子命令本身带 `[experimental]` 标记**。

这一点对读 [`app_server_protocol.md`](./app_server_protocol.md) 的人尤其重要：**app-server 协议虽然文档化程度最高，其 CLI 入口在上游仍标注为实验性。**

其下的子命令成熟度也不齐：

| 子命令 | 标记 | 位置 |
| ---- | ---- | ---- |
| `generate-ts` | `[experimental]` | `main.rs:610` |
| `generate-json-schema` | `[experimental]` | `main.rs:613` |
| `generate-internal-json-schema` | `[internal]` + `hide = true` | `main.rs:616-617` |
| `daemon pid-update-loop` | `[internal]` + `hide = true` | `main.rs:650-651` |

### 7.3 realtime 语音 / WebSocket 会话——**体量最大的未覆盖表面**（E3）

初版展开了 92 行的 v8-poc，却完全没提这条**合计约 7,500 行**的表面。（上一稿此处写"上万行"，与紧接着那张自己列出的、合计 7,512 行的表格自相矛盾——**同一节里的定性词与定量表要对得上**。）

**配置键（6 个，`core/src/config/mod.rs:987-1008`）**：`experimental_realtime_ws_base_url`、`experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_model`、`experimental_realtime_ws_backend_prompt`、`experimental_realtime_ws_startup_context`、`experimental_realtime_start_instructions`。

**代码规模**：

| 位置 | 行数 |
| ---- | ---: |
| `codex-rs/codex-api/src/endpoint/realtime_websocket/`（14 个文件，含 v1 / v2 / frameless-bidi 三套协议） | 4,393 |
| `codex-rs/core/src/realtime_conversation.rs` | 2,465 |
| `codex-rs/core/src/realtime_context.rs` | 580 |
| `codex-rs/core/src/context/realtime_start_instructions.rs` / `realtime_end_instructions.rs` | 28 / 46 |
| **合计** | **7,512** |

> 口径说明：4,393 行是 `realtime_websocket/` 下 14 个 `.rs` 的 `wc -l` 总和，其中含 **3 个 `*_tests.rs`、共 316 行**（`methods_common_tests.rs` 150、`methods_frameless_bidi_tests.rs` 102、`protocol_frameless_bidi_tests.rs` 64）。**扣掉测试后该目录的实现代码约 4,077 行。**

`webrtc_call_base_url` 这个键名指向**语音通话**方向。这也是全仓 `experimental_*` 配置键中占比最大的一组（10 个里有 6 个）。

> [!WARNING]
> 这条表面**同时涉及麦克风类输入、长连 WebSocket 与独立的后端地址**（三个 base-url 键都可被用户覆盖）。它的隐私与安全边界本文完全未审计。

> **未验证**（E1）：启用方式、默认是否关闭、音频数据流向、与主会话循环的关系。

### 7.4 `codex-features`——仓库里**最系统的**实验性标记机制（E3）

初版 §8（原 §7）的"标记方式不统一"列了四种方式，**唯独漏了这个专门为此设计的机制**。

`codex-rs/features/src/lib.rs`：

- `pub enum Stage`（**`:38` 起**）：`UnderDevelopment` / `Experimental { name, menu_description, announcement }` / `Stable` / `Deprecated` / `Removed`——**成熟度是一等公民，不是文档注释里的一句话**。
- `pub enum Feature`（`:85` 起）：**102 个变体**。
- `Stage::Experimental` 变体带 `name` 与 `menu_description`，供 **`/experimental` 菜单**向用户展示。
- CLI 入口：**`codex features`**（`cli/src/main.rs:211`），子命令含 `list`（列出各 feature 的 stage 与生效状态）。

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
| `Removed` | 32 | 保留为 no-op 的兼容开关，让旧配置仍能解析 |
| `UnderDevelopment` | 31 | 开发中，**不进 `/experimental` 菜单** |
| `Deprecated` | 3 | |
| `Experimental` | **1 或 2**（见下） | 只有这一档会出现在 `/experimental` 菜单里 |

> [!IMPORTANT]
> **上面这条 `grep` 只数到 101 条，比 102 个变体少一条**——差的那条恰恰是最有意思的一条。`Feature::PreventIdleSleep`（`features/src/lib.rs:1414-1431`）的 stage 是**平台条件表达式**，不是字面量：
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

> [!TIP]
> **这才是判断某项能力成熟度最系统的入口**——比逐个翻 `Subcommand` 的文档注释可靠得多。先跑 `codex features list`，再去看 `Feature` 枚举上的 `Stage`。

### 7.5 协议层的 `#[experimental("...")]` 属性宏——第五种标记方式（E3）

`codex-rs/app-server-protocol/src/protocol/common.rs` 里有一套宏，把 `#[experimental(reason)]` 编织进方法/类型的注册表。

> [!CAUTION]
> **勘误：上一稿点名的两个宏都是测试专用的，不是生产机制。**
>
> | 宏 | 位置 | 是否生产代码 |
> | ---- | ---- | ---- |
> | `experimental_reason_expr!` | `common.rs:81-93` | ✅ **这才是生产宏**——它把 `#[experimental(reason)]`、`inspect_params: true` 与"无标注"三种情况翻译成 `Option<&str>` 形式的实验性理由 |
> | `experimental_method_entry!` | `common.rs:96` | ❌ 紧邻其上的 `:95` 就是 `#[cfg(test)]` |
> | `experimental_type_entry!` | `common.rs:109` | ❌ 同理，`:108` 是 `#[cfg(test)]` |
>
> 上一稿给的展开位置 `:391-416` 起点也偏了：那三个消费上述测试宏的常量是 `EXPERIMENTAL_CLIENT_METHODS`、`EXPERIMENTAL_CLIENT_METHOD_PARAM_TYPES`、`EXPERIMENTAL_CLIENT_METHOD_RESPONSE_TYPES`，位于 **`:401-418`**，且**每一个都单独带 `#[cfg(test)]`**。
>
> 所以运行时真正读到"某个方法是不是实验性"的路径走的是 `experimental_reason_expr!`；那两个 `*_entry!` 宏只为测试期的清单断言服务。**引用 `macro_rules!` 时务必往上多看一行有没有 `#[cfg(test)]`。**

**全文件共 53 处 `#[experimental("...")]` 标注**，覆盖面远超初版的印象，例如：

| 方法 | 位置 |
| ---- | ---- |
| `plugin/search` | `:732` |
| `remoteControl/*` 的 7 个请求（`enable`、`disable`、`status/read`、`pairing/start`、`pairing/status`、`client/list`、`client/revoke`） | `:939-976` |
| `thread/increment_elicitation`、`thread/settings/update`、`thread/memoryMode/set`、`memory/reset`、`thread/backgroundTerminals/*`、`thread/search`、`thread/turns/list` 等 | `:517` 起散布 |

> 这也补正了 §3.3 的一处口径：`remoteControl/*` 的**请求**是 7 个（外加 1 个通知 `remoteControl/status/changed`，`:1741`），合计 8 个协议方法。

### 7.6 其余隐藏入口清单（E3，`grep -n "hide = true" codex-rs/cli/src/main.rs`）

| 入口 | 位置 | 说明 |
| ---- | ---- | ---- |
| `codex debug trace-reduce` | `main.rs:238-239` | *"Replay a rollout trace bundle and write reduced state JSON."*——对应 `codex-rollout-trace`（见 [`observability.md`](./observability.md) §6.3） |
| `codex debug clear-memories` | `main.rs:242-243` | *"Internal: reset local memory state for a fresh start."* |
| `codex app-server --remote-control` | `main.rs:541-542` | *"Enable remote control for this app-server process without changing persistence."*——**不是根级全局开关**，见下方勘误 |
| `codex login --api-key` 选项 | `main.rs:476-483` | 已废弃，现在只会退出并提示改用 `--with-api-key` |
| **`codex login --experimental_issuer <URL>`** | `main.rs:491` | **覆盖 OAuth issuer 基址**，`hide = true` |
| **`codex login --experimental_client-id <CLIENT_ID>`** | `main.rs:495` | **覆盖 OAuth client ID**，`hide = true` |

> [!CAUTION]
> **勘误：`--remote-control` 不是根级全局标志。** 上一稿把它写成"隐藏的全局开关，独立于子命令"。实际上它是 `struct AppServerCommand` 的字段（`cli/src/main.rs:514` 起，`--remote-control` 在 `:540-542`），因此**只能写成 `codex app-server --remote-control`**。根 CLI 结构体是 `MultitoolCli`（`main.rs:106`），里面没有这个字段。
>
> 同一个结构体里还有 `--strict-config`、`--listen`、`--stdio`、`--analytics-default-enabled` 等，全都是 app-server 子命令级的。**判断一个 clap 标志的作用域，要看它挂在哪个 `#[derive(Parser)]` 结构体上，不能只看 `hide = true`。**

> [!WARNING]
> 表中最后两项是**高风险认证覆盖面**：它们允许把 OAuth 流程指向任意 issuer。详见 [`auth_and_providers.md`](./auth_and_providers.md) §1.3。

---

## 8. 这些表面的共同特征

| 观察 | 说明 |
| ---- | ---- |
| **多数有独立协议或独立二进制** | code-mode 有 4 个 crate 与独立协议；responses-api-proxy、exec-server 有独立 main；realtime 有三套协议版本 |
| **都有测试覆盖** | 即便是 PoC 也进 CI（`v8-canary.yml`） |
| **部分与 Bazel 深度绑定** | v8-poc 明说是 "Bazel-wired"；code-mode 有专门的 bazel 任务 |
| **标记方式不统一——共 6 种** | ①`[EXPERIMENTAL]` / `[experimental]` 文档注释；②`#[clap(hide = true)]`；③平台 `cfg`；④目录名（v8-poc）；⑤**`codex-features` 的 `Stage` 枚举**（§7.4）；⑥**协议层 `#[experimental(...)]` 宏**（§7.5） |
| **大小写有含义（观察，非明文规则）** | `[EXPERIMENTAL]`（Cloud、exec-server）与 `[experimental]`（app-server、remote-control、generate-ts）并存；上游未说明二者是否有意区分，**不要据此推断成熟度差异** |

> [!TIP]
> **判断某个表面成熟度的可靠方法**（已修订，按可靠性排序）：
>
> 1. 先跑 **`codex features list`**，查 `Feature` 枚举上的 `Stage`（§7.4）——这是最系统的一处。
> 2. 协议方法查 `app-server-protocol/src/protocol/common.rs` 上的 `#[experimental(...)]`（§7.5）。
> 3. CLI 表面查 `codex-rs/cli/src/main.rs` 的 `Subcommand` 枚举定义处的文档注释与属性宏。
>
> **不要靠 crate 名或目录名猜测**——§1.2 的 `codex-cloud-config` 就是这么被归错类的。

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 建议入口 |
| ---- | ---- |
| Cloud 任务的云端 API 协议 | `codex-cloud-tasks-client`、`codex-backend-client` |
| 桌面 app 的安装器行为 | `cli/src/app_cmd.rs` |
| remote-control 的鉴权模型 | `app-server-transport/src/transport/remote_control/auth.rs`、`enroll.rs` |
| responses-api-proxy 的整体转发行为与 dump 落盘位置 | `responses-api-proxy/src/lib.rs`、`dump.rs` |
| code-mode 的 JS 沙箱隔离边界 | `code-mode-runtime/src/v8_init.rs`、`session_runtime/` |
| `cell_actor` 的执行模型 | `code-mode-runtime/src/cell_actor/` |
| realtime 会话的启用方式与音频数据流向 | `core/src/realtime_conversation.rs`、`codex-api/src/endpoint/realtime_websocket/` |
| exec-server 的协议与部署形态 | `codex-exec-server`、`cli/src/exec_server_telemetry.rs` |
| 102 个 `Feature` 各自的语义与默认状态 | `features/src/lib.rs`；或跑 `codex features list` |

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

**真正的门控在 `codex-rs/features/src/lib.rs` 的 `Feature` 枚举 `// Experimental` 段**。以 code-mode 为例，它有四个专属 feature：

| Feature | 位置 | 文档注释 |
| ---- | ---- | ---- |
| `CodeMode` | `:98` | *"Enable JavaScript code mode backed by the standalone host process."* |
| `CodeModeBufferedExec` | `:100` | *"Use a 30-second default yield timeout for code mode exec calls."* |
| `CodeModeHost` | `:102` | *"Run JavaScript code mode in the standalone host process."* |
| `CodeModeOnly` | `:104` | *"Restrict model-visible tools to code mode entrypoints (`exec`, `wait`)."* |

> [!TIP]
> 找某个实验性表面的开关，**先查 `Feature` 枚举，再查 `config.schema.json`**——多数表面走前者。二者的关系见 [`config_system.md`](./config_system.md)。

---

## 10. 相关文档

- [Crate 地图](./crate_map.md) §3.10 — 实验性 crate 清单
- [架构总览](./architecture_overview.md) §3 — 子命令口径与可见性
- [app-server 协议](./app_server_protocol.md) — `remoteControl/*` 方法
- [构建与发布](./build_and_release.md) §2 — V8 与 hermetic 工具链补丁
- [工具与沙箱](./tools_and_sandbox.md) — `execpolicy` 隐藏子命令
