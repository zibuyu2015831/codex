---
title: Codex 实验性与低频表面
summary: 逐项展开 Codex Cloud 任务、桌面端、remote-control、responses-api-proxy、v8-poc、code-mode 六个实验性或隐藏能力面的成熟度标记、代码位置、模块构成与已知边界，每节首行标注可见性与稳定性风险。
keywords: codex | experimental | cloud-tasks | remote-control | code-mode | v8-poc | responses-api-proxy | desktop-app
scope: codex 中标注 experimental / hidden / PoC 的能力面
related_files: codex-rs/cli/src/main.rs | codex-rs/cloud-tasks/src/lib.rs | codex-rs/v8-poc/src/lib.rs | codex-rs/code-mode-runtime/src/lib.rs | codex-rs/app-server-daemon/src/lib.rs | codex-rs/responses-api-proxy/src/lib.rs
dependencies: dev_docs/crate_map.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 实验性与低频表面

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **本文由用户明确要求生成**：疑问 3 的答复为「全部展开」
> **证据等级**: 成熟度标记与代码位置为 E3；各表面的内部行为多为 E1

---

## 0. 通读警告

> [!CAUTION]
> **本文覆盖的六个能力面全部带有实验性、隐藏或 PoC 标记。上游可能随时变更或移除它们，恕不另行通知。**
>
> 不要基于本文的内容构建长期依赖。每一节的首行都标注了该表面的**可见性**与**稳定性风险**。

### 六个表面一览

| 表面 | 标记 | 可见性 | 主要 crate |
| ---- | ---- | ---- | ---- |
| Codex Cloud 任务 | `[EXPERIMENTAL]` | 可见 | `cloud-tasks` 系列 4 个 |
| 桌面端 | 无实验标记，但**平台条件编译** | macOS / Windows 可见 | `cli/src/app_cmd.rs` |
| remote-control | `[experimental]` | 可见 | `app-server-daemon`、`app-server-transport` |
| responses-api-proxy | `#[clap(hide = true)]` | **隐藏** | `responses-api-proxy` |
| v8-poc | 目录名即 PoC | 无 CLI 入口 | `v8-poc`（92 行） |
| code-mode | 无 CLI 子命令，有 just 任务 | 半公开 | `code-mode` 系列 4 个 |

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

### 1.2 crate 构成

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-cloud-tasks` | 5,248 | 主体，含 TUI |
| `codex-cloud-config` | 2,433 | 云配置 |
| `codex-cloud-tasks-client` | 1,117 | 客户端 |
| `codex-cloud-tasks-mock-client` | 270 | **模拟客户端**（测试用） |

### 1.3 模块（`cloud-tasks/src/`，E4）

| 文件 | 说明 |
| ---- | ---- |
| `app.rs` / `ui.rs` | 自带 TUI |
| `cli.rs` | 命令行参数 |
| `new_task.rs` | 新建任务 |
| `scrollable_diff.rs` | **可滚动 diff 视图** |
| `env_detect.rs` | **环境探测** |
| `util.rs` / `lib.rs` | — |

**这是一个独立的 TUI 应用**，不复用 `codex-tui`。`scrollable_diff.rs` 与命令描述中的 "apply changes locally" 对应——浏览云端任务产生的变更并在本地应用。

`mock-client` 的存在说明这条链路**可以脱离真实云服务测试**。

> **未验证**（E1）：云端 API 的协议、认证方式与 `codex-backend-client` 的关系。

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

### 3.3 传输实现（`app-server-transport/src/transport/remote_control/`，E4）

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
| `dump.rs` | 转储 |

> [!CAUTION]
> **这是内部工具，不要在生产中依赖。** 它会监听本地端口并处理 API key。`dump.rs` 的存在意味着它可能会转储请求内容——**在处理敏感数据时格外注意**。

> **未验证**（E1）：代理的具体行为、监听地址默认值、dump 的触发条件与落盘位置。

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

### 6.2 架构线索（E3/E4）

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

## 7. 这些表面的共同特征

| 观察 | 说明 |
| ---- | ---- |
| **都有独立协议或独立二进制** | cloud-tasks 自带 TUI；code-mode 有 4 个 crate 与独立协议；responses-api-proxy 有独立 main |
| **都有测试覆盖** | 即便是 PoC 也进 CI（`v8-canary.yml`） |
| **多数与 Bazel 深度绑定** | v8-poc 明说是 "Bazel-wired"；code-mode 有专门的 bazel 任务 |
| **标记方式不统一** | 有的用 `[experimental]`，有的用 `hide = true`，有的靠目录名，有的靠平台 cfg |

> [!TIP]
> **判断某个表面成熟度的可靠方法**：查 `codex-rs/cli/src/main.rs` 的 `Subcommand` 枚举定义处的文档注释与属性宏，而不是靠 crate 名或目录名猜测。

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 建议入口 |
| ---- | ---- |
| Cloud 任务的云端 API 协议 | `codex-cloud-tasks-client`、`codex-backend-client` |
| 桌面 app 的安装器行为 | `cli/src/app_cmd.rs` |
| remote-control 的鉴权模型 | `app-server-transport/src/transport/remote_control/auth.rs`、`enroll.rs` |
| responses-api-proxy 的代理行为与 dump | `responses-api-proxy/src/lib.rs`、`dump.rs` |
| code-mode 的 JS 沙箱隔离边界 | `code-mode-runtime/src/v8_init.rs`、`session_runtime/` |
| `cell_actor` 的执行模型 | `code-mode-runtime/src/cell_actor/` |
| 各表面的启用配置键 | `codex-rs/core/config.schema.json` 中的 `experimental_*` 键 |

---

## 9. 相关文档

- [Crate 地图](./crate_map.md) §3.10 — 实验性 crate 清单
- [架构总览](./architecture_overview.md) §3 — 子命令口径与可见性
- [app-server 协议](./app_server_protocol.md) — `remoteControl/*` 方法
- [构建与发布](./build_and_release.md) §2 — V8 与 hermetic 工具链补丁
- [工具与沙箱](./tools_and_sandbox.md) — `execpolicy` 隐藏子命令
