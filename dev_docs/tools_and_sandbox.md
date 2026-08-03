---
title: Codex 工具执行与沙箱隔离
summary: 描述 codex-sandboxing 的四种沙箱类型与平台选择逻辑、macOS Seatbelt 的三份 sbpl 策略、Linux 的 Landlock 加 seccomp 双机制与 bwrap 回退、Windows 受限令牌沙箱、沙箱违规记录机制，以及 CODEX_SANDBOX 环境变量的绝对红线。
keywords: codex | sandbox | seatbelt | landlock | seccomp | bwrap | windows-restricted-token | execpolicy
scope: codex-rs/sandboxing 及其平台实现 crate
related_files: codex-rs/sandboxing/src/manager.rs | codex-rs/sandboxing/src/seatbelt.rs | codex-rs/sandboxing/src/landlock.rs | codex-rs/sandboxing/src/windows.rs | codex-rs/linux-sandbox/src/landlock.rs | codex-rs/protocol/src/protocol.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 工具执行与沙箱隔离

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/sandboxing`（6,882 行）+ 平台实现 crate
> **证据等级**: 类型定义、平台选择逻辑、策略文件为 E3；策略文件的具体规则内容未逐条解读

---

## 0. 先读这一节：绝对红线

> [!CAUTION]
> **`AGENTS.md:8-10` 规定：禁止新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码。**
>
> 这条规则**没有例外**。即使你认为改动是安全的、即使是重构、即使只是改注释——都不要碰。本文档也不复述这两个环境变量的取值与判定逻辑。

---

## 1. 四种沙箱类型（E3）

`codex-rs/sandboxing/src/manager.rs:35`：

```rust
pub enum SandboxType {
    None,
    MacosSeatbelt,
    LinuxSeccomp,
    WindowsRestrictedToken,
}
```

对应的指标标签（`manager.rs:42-52`）：`none` / `seatbelt` / `seccomp` / `windows_sandbox`。

### 平台选择逻辑（E3，`manager.rs:60-75`）

```rust
pub fn get_platform_sandbox(windows_sandbox_enabled: bool) -> Option<SandboxType> {
    if cfg!(target_os = "macos")   { Some(SandboxType::MacosSeatbelt) }
    else if cfg!(target_os = "linux") { Some(SandboxType::LinuxSeccomp) }
    else if cfg!(target_os = "windows") {
        if windows_sandbox_enabled { Some(SandboxType::WindowsRestrictedToken) }
        else { None }
    }
    else { None }
}
```

| 平台 | 结果 | 备注 |
| ---- | ---- | ---- |
| macOS | `MacosSeatbelt` | 无条件 |
| Linux | `LinuxSeccomp` | 无条件 |
| Windows | `WindowsRestrictedToken` **或 `None`** | **取决于 `windows_sandbox_enabled` 开关** |
| 其他 | `None` | 无沙箱 |

> [!WARNING]
> **Windows 上沙箱不是无条件启用的。** 当 `windows_sandbox_enabled` 为 false 时返回 `None`，即无沙箱。这是三个平台中唯一有条件的分支。

### 沙箱偏好（`manager.rs:54`）

```rust
pub enum SandboxablePreference { Auto, Require, Forbid }
```

`Require` 与 `Forbid` 的存在说明调用方可以**强制要求**或**强制禁止**沙箱，而不只是"能用就用"。

---

## 2. macOS：Seatbelt（E3）

### 三份 sbpl 策略文件

`codex-rs/sandboxing/src/seatbelt.rs:21-24` 通过 `include_str!` 内嵌三份策略：

| 常量 | 文件 |
| ---- | ---- |
| `MACOS_SEATBELT_BASE_POLICY` | `seatbelt_base_policy.sbpl` |
| `MACOS_SEATBELT_NETWORK_POLICY` | `seatbelt_network_policy.sbpl` |
| （受限只读平台默认） | `restricted_read_only_platform_defaults.sbpl` |

> [!IMPORTANT]
> 这三份 `.sbpl` 是通过 `include_str!` 在**编译期**读入的。按 `AGENTS.md:40-43`，这类编译期文件读取必须在 `BUILD.bazel` 中配置 `compile_data`，否则 **Cargo 能过而 Bazel 会失败**。改动这些文件或新增同类文件时务必注意。

### 命令构造入口

```rust
// seatbelt.rs:611
pub struct CreateSeatbeltCommandArgsParams<'a> { ... }

// seatbelt.rs:623
pub fn create_seatbelt_command_args(...);
```

**策略分为基础策略与网络策略两份**，说明网络访问是**叠加**上去的独立维度，与 `SandboxPolicy` 中 `network_access` 默认为 `false` 的设计一致。

---

## 3. Linux：Landlock + seccomp（E3）

> [!NOTE]
> **这是一个容易写错的点。** 枚举名是 `LinuxSeccomp`、指标标签是 `seccomp`，但实现文件叫 `landlock.rs`——实际上**两种机制同时使用**。
>
> `codex-rs/linux-sandbox/src/landlock.rs:1` 的模块文档写得很清楚：
> > "In-process Linux sandbox primitives: `no_new_privs` and seccomp."
>
> 而同一文件 `:15-23` 又导入了 `landlock` crate 的 `ABI` / `Access` / `AccessFs` / `Ruleset` 等类型。`codex-rs/linux-sandbox/Cargo.toml:28,30` 同时声明了 `landlock` 与 `seccompiler` 两个依赖。

| 机制 | 作用面 | 依赖 crate |
| ---- | ---- | ---- |
| **Landlock** | 文件系统访问控制（`AccessFs`、`Ruleset`） | `landlock` |
| **seccomp** | 系统调用过滤（`BpfProgram`、`SeccompAction`） | `seccompiler` |
| **`no_new_privs`** | 阻止提权 | 内核原语 |

### bwrap 回退路径

`codex-rs/linux-sandbox/src/` 下另有三个 bwrap 相关文件：

| 文件 | 说明 |
| ---- | ---- |
| `bwrap.rs` | bubblewrap 封装 |
| `bundled_bwrap.rs` | 随产品分发的 bwrap |
| `bazel_bwrap.rs` | Bazel 构建下的 bwrap |

`sandboxing/src/lib.rs:14,16` 导出了 `find_system_bwrap_in_path` 与 `system_bwrap_warning`，说明**会尝试查找系统 bwrap 并在有问题时给出警告**。

> **未验证**（E1）：Landlock/seccomp 与 bwrap 的**选择条件**——什么情况下走哪条路径。需读 `linux-sandbox/src/launcher.rs`。

### 其他 Linux 特有文件

- `proxy_routing.rs` — 代理路由
- `landlock.rs:8` 的 `allow_network_for_proxy(enforce_managed_network: bool) -> bool`（在 `sandboxing` crate 中）——网络代理场景下的放行判定

---

## 4. Windows：受限令牌沙箱（E3）

`codex-rs/sandboxing/src/windows.rs` 的公开函数揭示了这条路径的复杂度：

| 函数 | 位置 | 用途 |
| ---- | ---- | ---- |
| `windows_sandbox_uses_elevated_backend` | `:32` | 是否使用提权后端 |
| `permission_profile_supports_windows_restricted_token_sandbox` | `:42` | 权限档是否支持受限令牌沙箱 |
| `unsupported_windows_restricted_token_sandbox_reason` | `:53` | **不支持时的原因** |
| `resolve_windows_restricted_token_filesystem_overrides` | `:78` | 受限令牌模式的文件系统覆盖 |
| `resolve_windows_elevated_filesystem_overrides` | `:219` | 提权模式的文件系统覆盖 |
| `WindowsSandboxFilesystemOverrides`（struct） | `:24` | 覆盖项载体 |

**两条后端路径**：受限令牌（restricted token）与提权（elevated），各有独立的文件系统覆盖解析。

`unsupported_..._reason` 的存在说明**存在权限档不被 Windows 沙箱支持的情况**，且代码会给出具体原因。

独立 crate `codex-windows-sandbox`（19,173 行）承载主要实现；`lib.rs:17` 还导出了 `WindowsSandboxProxySettingsMode`。

---

## 5. 沙箱管理器与执行请求（E3）

`sandboxing/src/manager.rs` 提供的类型：

| 类型 | 位置 | 用途 |
| ---- | ---- | ---- |
| `SandboxManager` | `:265` | 管理器主体 |
| `SandboxCommand` | `:98` | 沙箱化后的命令 |
| `SandboxExecRequest` | `:112` | 执行请求 |
| `SandboxTransformRequest<'a>` | `:129` | 变换请求（借用） |
| `SandboxDirectSpawnTransformRequest<'a>` | `:150` | 直接 spawn 的变换请求 |
| `SandboxTransformError` | `:197` | 变换错误（实现了 `Display` 与 `Error`） |

**核心抽象是"变换"（transform）**：把一个普通命令变换成受沙箱约束的命令，而不是在执行时拦截。这解释了 `create_seatbelt_command_args` 这类"构造命令参数"的 API 形状。

进程启动在 `spawn.rs`：`SpawnRequest`、`WindowsSandboxSpawnRequest`、`spawn_process`。

### MITM CA 支持

`manager.rs:76` 的 `with_managed_mitm_ca_readable_root(...)` 说明存在**受管 MITM CA 证书**场景——需要让沙箱内进程能读取企业 CA 包。这与 `codex-network-proxy`（17,064 行）相关。

---

## 6. 违规检测与记录（E3）

`sandboxing/src/violation.rs` 导出了一整套违规记录机制：

| 类型 / 函数 | 用途 |
| ---- | ---- |
| `SandboxViolationEvent` | 违规事件 |
| `SandboxViolationBackend` | 违规检测后端 |
| `FileSystemSandboxViolation` + `FileSystemSandboxViolationReason` | 文件系统违规及原因 |
| `NetworkSandboxViolation` | 网络违规 |
| `record_sandbox_violation` | 通用记录 |
| `record_filesystem_sandbox_violation` | 文件系统违规记录 |
| `record_network_sandbox_violation` | 网络违规记录 |

另有 `denial.rs` 的 `is_likely_sandbox_denied`——**启发式判断某次失败是否由沙箱拒绝导致**。这对错误信息的可读性很重要：命令失败时能区分"业务错误"与"被沙箱挡了"。

---

## 7. 策略与审批的关系

沙箱只解决"能做什么"，审批解决"要不要做"。两者是正交的：

```
模型发起工具调用
      ↓
审批决策（AskForApproval）—— 见 core_agent_loop.md §4.1
      ↓ 放行
沙箱变换（SandboxPolicy → SandboxType）—— 本文 §1
      ↓
spawn_process 执行
      ↓ 失败时
is_likely_sandbox_denied 判断是否沙箱拒绝
      ↓
record_*_sandbox_violation 记录
```

> **未验证**（E1）：上图的**次序**是根据类型职责推断的合理链路，未通过读 `core/src/tools/orchestrator.rs` 完整确认。实际实现可能存在交错。

`SandboxPolicy` 的四个变体与字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §4.2。

---

## 8. 相关的执行安全 crate

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-execpolicy` | 2,937 | 执行策略；`codex execpolicy` 为 hidden 子命令 |
| `codex-shell-command` | 6,760 | shell 命令解析；`is_safe_command()` 的判定逻辑应在此 |
| `codex-shell-escalation` | 2,279 | 权限提升审批 |
| `codex-process-hardening` | 193 | 进程加固 |
| `codex-network-proxy` | 17,064 | 网络代理（与 MITM CA 相关） |

`core/src/` 侧的对应文件：`exec.rs`、`exec_env.rs`、`exec_policy.rs`、`exec_policy_windows_tests.rs`（Windows 有独立测试文件，说明平台差异显著）。

---

## 9. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| 🚫 **绝对禁止**触碰 `CODEX_SANDBOX_*` 相关代码 | `AGENTS.md:8-10` |
| 新增 `.sbpl` 或其他 `include_str!` 文件时必须补 `BUILD.bazel` 的 `compile_data` | `AGENTS.md:40-43` |
| 沙箱行为必须在 Linux / macOS / Windows 三平台都可用，除非是明确的 OS 专属特性 | `AGENTS.md:318` |
| 改动沙箱逻辑属高风险，应补集成测试 | `AGENTS.md:112-118` |

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 三份 `.sbpl` 策略的具体规则 | E1（仅确认存在） | 直接读 `codex-rs/sandboxing/src/*.sbpl` |
| Landlock/seccomp 与 bwrap 的选择条件 | E1 | `codex-rs/linux-sandbox/src/launcher.rs` |
| seccomp 过滤的系统调用白名单 | E1 | `codex-rs/linux-sandbox/src/landlock.rs` |
| Windows 两条后端路径的切换条件 | E1 | `codex-rs/windows-sandbox-rs/`（19,173 行） |
| `is_safe_command()` 的完整判定规则 | E1 | `codex-shell-command` crate |
| execpolicy 的策略语言与规则格式 | E1 | `codex-rs/execpolicy/` |
| 审批与沙箱在编排层的实际次序 | E1 | `codex-rs/core/src/tools/orchestrator.rs` |
| MITM CA 与网络代理的完整链路 | E1 | `codex-rs/network-proxy/`（17,064 行） |

---

## 11. 相关文档

- [智能体核心循环](./core_agent_loop.md) — 审批与沙箱策略类型
- [架构总览](./architecture_overview.md) — 沙箱在整体架构中的位置
- [Crate 地图](./crate_map.md) §3.4 — 沙箱相关 8 个 crate
- [配置体系](./config_system.md) — 沙箱策略的配置入口
