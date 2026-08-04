---
title: Codex 工具执行与沙箱隔离
summary: 描述 codex-sandboxing 的四种沙箱类型与平台选择逻辑、运行时权限类型 PermissionProfile 与兼容层 SandboxPolicy、macOS Seatbelt 的三份 sbpl 策略、Linux 默认的 bwrap 加 seccomp 加 no_new_privs 路径与已废弃的 legacy Landlock 分支、Windows 受限令牌沙箱、审批与沙箱的升级重试次序、沙箱违规记录机制，以及 CODEX_SANDBOX 环境变量的绝对红线。
keywords: codex | sandbox | seatbelt | bwrap | seccomp | landlock-legacy | permission-profile | windows-restricted-token | execpolicy
scope: codex-rs/sandboxing 及其平台实现 crate
related_files: codex-rs/sandboxing/src/manager.rs | codex-rs/sandboxing/src/lib.rs | codex-rs/sandboxing/src/policy_transforms.rs | codex-rs/linux-sandbox/src/landlock.rs | codex-rs/linux-sandbox/src/linux_run_main.rs | codex-rs/linux-sandbox/src/launcher.rs | codex-rs/features/src/lib.rs | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/shell-command/src/command_safety/is_safe_command.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 工具执行与沙箱隔离

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/sandboxing`（6,882 行）+ 平台实现 crate
> **证据等级**: 类型定义、平台选择逻辑、Linux 主/备路径分支、审批与沙箱次序为 E3；目录与文件清单为 E1；策略文件的具体规则内容未逐条解读

> [!WARNING]
> **本文第一版有四处事实性错误，已在本次修订中更正**，涉及 Linux 沙箱的主备关系、bwrap 与 Landlock 的切换开关位置、seccomp 过滤器的黑/白名单方向、以及 `is_safe_command()` 这个不存在的函数名。相关段落都保留了「原文写错了什么」的说明，便于对照旧版笔记。

---

## 0. 先读这一节：绝对红线

> [!CAUTION]
> **`AGENTS.md` 顶部规则列表规定：禁止新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码**（grep `Never add or modify any code related to`）。
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
| macOS | `MacosSeatbelt` | 在本函数内无条件 |
| Linux | `LinuxSeccomp` | 在本函数内无条件 |
| Windows | `WindowsRestrictedToken` **或 `None`** | **取决于 `windows_sandbox_enabled` 开关** |
| 其他 | `None` | 无沙箱 |

> [!WARNING]
> **不要把上表读成「macOS/Linux 一定有沙箱」。** `get_platform_sandbox` 只回答「本平台能提供哪种沙箱实现」，它不是入口。真正的入口是 `SandboxManager::select_initial`（`manager.rs:272`），它先调 `should_sandbox`（`manager.rs:289`），返回 false 时**直接给 `SandboxType::None`**，根本不问平台：
>
> ```rust
> // manager.rs:272-285（节选）
> pub fn select_initial(&self, permission_profile: &PermissionProfile, pref: SandboxablePreference, ...) -> SandboxType {
>     if self.should_sandbox(permission_profile, pref, has_managed_network_requirements) {
>         get_platform_sandbox(...).unwrap_or(SandboxType::None)
>     } else {
>         SandboxType::None
>     }
> }
> ```
>
> 所以准确的说法是：**三平台都先过 `should_sandbox` 这道闸**；`windows_sandbox_enabled` 是过闸之后 Windows 独有的**第二道**条件。本文第一版写的「这是三个平台中唯一有条件的分支」有误导性，已更正。

### 沙箱偏好（`manager.rs:54`）

```rust
pub enum SandboxablePreference { Auto, Require, Forbid }
```

`should_sandbox` 对这三者的处理（`manager.rs:296-306`，E3）：

- `Forbid` → 直接 false
- `Require` → 直接 true
- `Auto` → 取 `permission_profile.to_runtime_permissions()` 拆出的文件系统与网络策略，交给 `should_require_platform_sandbox` 判定

即调用方可以**强制要求**或**强制禁止**沙箱，而不只是"能用就用"。

---

## 1.5 运行时权限类型：`PermissionProfile`（E3）

> [!IMPORTANT]
> **`SandboxPolicy` 已经不是运行时的策略类型了。** 本文第一版与 [`core_agent_loop.md`](./core_agent_loop.md) §5.2 都只讲了 `SandboxPolicy`，这是不完整的。

运行时真正流转的是 `PermissionProfile`（`codex-rs/protocol/src/models.rs:316`）：

```rust
pub enum PermissionProfile {
    /// Codex owns sandbox construction for this profile.
    Managed { file_system: ManagedFileSystemPermissions, network: NetworkSandboxPolicy },
    /// Do not apply an outer sandbox.
    Disabled,
    /// Filesystem isolation is enforced by an external caller.
    External { network: NetworkSandboxPolicy },
}
```

关键点：

| 事实 | 证据 |
| ---- | ---- |
| 权限被**拆成两个正交维度**：文件系统与网络 | `PermissionProfile::to_runtime_permissions()` 返回 `(FileSystemSandboxPolicy, NetworkSandboxPolicy)` 二元组，调用点见 `manager.rs:85`、`:300` |

> [!IMPORTANT]
> **别把 `ManagedFileSystemPermissions` 和 `FileSystemSandboxPolicy` 当成同一个类型。** 本文与 [`core_agent_loop.md`](./core_agent_loop.md) 的上一稿都在这里把两者混为一谈了。它们是**两个不同的类型，处在链路的不同端**：
>
> | 类型 | 定义位置 | 角色 |
> | ---- | ---- | ---- |
> | `ManagedFileSystemPermissions` | `codex-rs/protocol/src/models.rs:258` | **`PermissionProfile::Managed` 的字段类型**。是个两变体枚举：`Restricted { entries, glob_scan_max_depth }` / `Unrestricted` |
> | `FileSystemSandboxPolicy` | `crate::permissions`（在 `models.rs:19` 被 `use` 进来） | **运行时的展开形态**，结构体，带 `kind` / `glob_scan_max_depth` / `entries` |
>
> 两者由 `ManagedFileSystemPermissions::to_sandbox_policy()`（`models.rs:288`）与 `::from_sandbox_policy()`（`:273`）互转。
>
> 换言之：**`PermissionProfile::Managed` 的字段签名是 `file_system: ManagedFileSystemPermissions, network: NetworkSandboxPolicy`**（`models.rs:320-322`）——只有 `network` 这一维是直接用 `*SandboxPolicy` 类型的，文件系统那一维隔了一层。上面代码块里的枚举定义是对的，是这张表的措辞把它抹平了。
| `SandboxManager` 的三个主方法都收 `&PermissionProfile`，不收 `SandboxPolicy` | `transform` / `select_initial` / `should_sandbox`（`manager.rs:272-311`） |
| `SandboxPolicy` 退化为**线上/兼容层类型** | `codex-rs/sandboxing/src/lib.rs:27` 导出 `compatibility_sandbox_policy_for_permission_profile`，被 `codex-rs/core/src/config/mod.rs:479`、`codex-rs/core/src/codex_thread.rs:139` 调用 |

### 策略的合成：`codex-rs/sandboxing/src/policy_transforms.rs`

这个模块负责把多来源的权限声明合成为一个 profile，公开函数（E3）：

| 函数 | 位置 | 用途 |
| ---- | ---- | ---- |
| `normalize_additional_permissions` | `:19` | 归一化附加权限声明 |
| `merge_permission_profiles` | `:72` | **并集**合成（放宽） |
| `intersect_permission_profiles` | `:126` | **交集**合成（收紧） |
| `effective_file_system_sandbox_policy` | `:459` | 求有效文件系统策略 |
| `effective_network_sandbox_policy` | `:492` | 求有效网络策略 |
| `effective_permission_profile` | `:507` | 求有效 profile |
| `should_require_platform_sandbox` | `:523` | `Auto` 偏好下是否需要平台沙箱 |

`codex-rs/core/src/tools/handlers/mod.rs:38-40`（上一稿误记为 `:52-54`，那三行其实是 `use crate::sandboxing::SandboxPermissions;` 等）同时导入了 `intersect_permission_profiles`、`merge_permission_profiles`、`normalize_additional_permissions`——说明工具侧的「附加权限」请求既有放宽也有收紧路径。

`SandboxPolicy` 四个变体的字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §5.2。

---

## 2. macOS：Seatbelt（E3）

### 三份 sbpl 策略文件

`codex-rs/sandboxing/src/seatbelt.rs:21-24` 通过 `include_str!` 内嵌三份策略：

| 常量 | 文件 |
| ---- | ---- |
| `MACOS_SEATBELT_BASE_POLICY` | `codex-rs/sandboxing/src/seatbelt_base_policy.sbpl` |
| `MACOS_SEATBELT_NETWORK_POLICY` | `codex-rs/sandboxing/src/seatbelt_network_policy.sbpl` |
| （受限只读平台默认） | `codex-rs/sandboxing/src/restricted_read_only_platform_defaults.sbpl` |

> [!IMPORTANT]
> 这三份 `.sbpl` 是通过 `include_str!` 在**编译期**读入的。按 AGENTS.md 顶部规则列表（grep `Bazel does not automatically make source-tree files available`），这类编译期文件读取必须在 `BUILD.bazel` 中配置 `compile_data`（或 `build_script_data` / test data），否则 **Cargo 能过而 Bazel 会失败**。改动这些文件或新增同类文件时务必注意。

### 命令构造入口

```rust
// seatbelt.rs:611
pub struct CreateSeatbeltCommandArgsParams<'a> { ... }

// seatbelt.rs:623
pub fn create_seatbelt_command_args(...);
```

**策略分为基础策略与网络策略两份**，说明网络访问是**叠加**上去的独立维度，与 `SandboxPolicy` 中 `network_access` 默认为 `false` 的设计一致。

---

## 3. Linux：bwrap（默认）+ seccomp + no_new_privs（E3）

> [!CAUTION]
> **本文第一版把主/备关系写反了。** 旧版称「Landlock + seccomp 双机制为主、bwrap 为回退路径」，这是错的。真实情况相反：
>
> - **文件系统隔离由 bubblewrap（bwrap）承担，是默认路径**
> - **Landlock 的文件系统强制已是遗留（legacy）分支，且对应开关已标记为 deprecated**
>
> `codex-rs/linux-sandbox/src/landlock.rs:1-4` 的模块文档就是这么写的：
> > "In-process Linux sandbox primitives: `no_new_privs` and seccomp.
> > **Filesystem restrictions are enforced by bubblewrap in `linux_run_main`.**
> > **Landlock helpers remain available here as legacy/backup utilities.**"
>
> 同文件 `:135` 对 `install_filesystem_landlock_rules_on_current_thread` 的注释：
> > "Note: this is **currently unused** because filesystem sandboxing is performed via bubblewrap. It is kept for reference and potential fallback use."

枚举名 `LinuxSeccomp`、指标标签 `seccomp` 只描述了三件套里的一件。实际组合：

| 机制 | 作用面 | 状态 | 依赖 |
| ---- | ---- | ---- | ---- |
| **bubblewrap（bwrap）** | 文件系统隔离（mount namespace） | **默认** | `bwrap.rs` / `codex-rs/linux-sandbox/src/bundled_bwrap.rs` / `codex-rs/linux-sandbox/src/bazel_bwrap.rs`、`codex-rs/bwrap/` crate |
| **seccomp** | 系统调用过滤（`BpfProgram`、`SeccompAction`） | **默认**，在 bwrap 内层生效 | `seccompiler` |
| **`no_new_privs`** | 阻止提权 | **默认** | 内核原语 |
| **Landlock（`AccessFs`、`Ruleset`）** | 文件系统访问控制 | **遗留/备份**，默认不启用 | `landlock` crate（仍在 `Cargo.toml` 中） |

### 3.1 主/备切换的真正开关（E3）

> [!NOTE]
> 本文第一版把这条标为「未验证（E1）」并让读者去看 `codex-rs/linux-sandbox/src/launcher.rs`——**指错了文件**。`codex-rs/linux-sandbox/src/launcher.rs` 只在「系统 bwrap」与「随产品分发的 bwrap」之间选（`preferred_bwrap_launcher()`，`codex-rs/linux-sandbox/src/launcher.rs:51`，被 `:37` 与 `:102` 调用），跟 Landlock 毫无关系。

真正的开关是 **`use_legacy_landlock`**：

| 层 | 形态 | 位置 |
| ---- | ---- | ---- |
| 配置 | `[features].use_legacy_landlock` | `codex-rs/features/src/lib.rs:404`（读取器）、`:1040`（键定义） |
| CLI | `--use-legacy-landlock`，`hide = true`，`default_value_t = false` | `codex-rs/linux-sandbox/src/linux_run_main.rs:110-111` |
| 分支 | `if !use_legacy_landlock { ... }` | `codex-rs/linux-sandbox/src/linux_run_main.rs:217` |
| 传递 | `turn_ctx.config.features.use_legacy_landlock()` | `codex-rs/core/src/tools/orchestrator.rs:254` |

`codex-rs/linux-sandbox/src/linux_run_main.rs:217-219` 的注释把语义写死了：

> "Outer stage: bubblewrap first, then re-enter this binary in the sandboxed environment to apply seccomp. **This path never falls back to legacy Landlock on failure.**"

而 `:251` 之后才是：

> "**Legacy path**: Landlock enforcement only, when bwrap sandboxing is not enabled."

**该开关已被标记废弃**：`codex-rs/features/src/lib.rs` 中它属于 `Stage::Deprecated`，`codex-rs/core/tests/suite/deprecation_notice.rs:104-135` 有专门的断言，期望的提示文案是

```
`[features].use_legacy_landlock` is deprecated and will be removed soon.
```

另外 `codex-rs/linux-sandbox/src/linux_run_main.rs:302-320` 有两条互斥校验：`--apply-seccomp-then-exec` 不能与 `--use-legacy-landlock` 同用；需要「直接运行时强制」的 permission profile 也与 legacy 分支不兼容。

### 3.2 bwrap 的三个文件与查找逻辑

| 文件 | 说明 |
| ---- | ---- |
| `bwrap.rs` | bubblewrap 封装 |
| `codex-rs/linux-sandbox/src/bundled_bwrap.rs` | 随产品分发的 bwrap |
| `codex-rs/linux-sandbox/src/bazel_bwrap.rs` | Bazel 构建下的 bwrap |
| `codex-rs/linux-sandbox/src/launcher.rs` | `preferred_bwrap_launcher()`：**系统 bwrap vs 随产品分发的 bwrap** 二选一 |

`sandboxing/src/lib.rs:14,16` 导出了 `find_system_bwrap_in_path` 与 `system_bwrap_warning`，说明**会尝试查找系统 bwrap 并在有问题时给出警告**。仓库内另有独立 crate `codex-rs/bwrap/`（含 `build.rs` 与 `config.h`），即随产品分发的那一份。

### 3.3 seccomp 过滤器是**黑名单**，不是白名单（E3）

> [!CAUTION]
> 本文第一版在「未覆盖」表里写的是「seccomp 过滤的系统调用**白名单**」——方向反了。`landlock.rs:252-253` 的 `SeccompFilter::new` 参数写得很清楚：
>
> ```rust
> SeccompAction::Allow,                     // default – allow
> SeccompAction::Errno(libc::EPERM as u32), // when rule matches – return EPERM
> ```
>
> 即**默认放行，命中规则才拒绝**（返回 `EPERM`）。规则全部通过 `deny_syscall()` 一类的加法添加，例如 `:250-251` 针对 `SYS_socket` / `SYS_socketpair` 的非 UNIX/非 IP 套接字拒绝规则。

### 3.4 其他 Linux 特有文件

- `codex-rs/linux-sandbox/src/proxy_routing.rs` — 代理路由；`codex-rs/linux-sandbox/src/linux_run_main.rs:220-230` 在启用代理时会 `prepare_host_proxy_route_spec()` 并把 socket 目录追加进可读根
- `allow_network_for_proxy(enforce_managed_network: bool) -> bool`（在 `sandboxing` crate 中）——网络代理场景下的放行判定
- `codex-rs/linux-sandbox/src/linux_run_main_tests.rs` 对 `use_legacy_landlock` 的 true/false 两条路径都有覆盖（`:611-659`）

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

`codex-rs/sandboxing/src/manager.rs` 提供的类型：

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

> [!IMPORTANT]
> **`SandboxExecRequest` 只应在「执行边界」构造。** `manager.rs:107-110` 的文档注释：
>
> > "A host-native launch request produced after [`SandboxManager::transform`] validates URI inputs. **Build this only at the execution boundary: in exec-server, or in its logical equivalent within app-server.** Orchestration and transport code should retain [`PathUri`] values and defer conversion to native paths until this request is created."
>
> 也就是说：编排层与传输层应一路携带 PathUri，**不要提前转成本机路径**。这条约束直接关联两个 crate：
>
> | crate | 角色 |
> | ---- | ---- |
> | `codex-rs/exec-server/` | 执行边界的服务端实现（含 `tests/`、`testing/`） |
> | `codex-rs/exec-server-protocol/` | 该边界的线上协议定义 |
>
> AGENTS.md 的 `## Platform Support` 一节说明了为什么需要这条边界：app-server 与 exec-server **可以跑在不同操作系统上**（grep `connected app-server and exec-server on different operating systems`）。路径的本机化因此必须推迟到真正执行的那一侧。

### MITM CA 支持

`manager.rs:76` 的 `with_managed_mitm_ca_readable_root(...)` 说明存在**受管 MITM CA 证书**场景——需要让沙箱内进程能读取企业 CA 包。这与 `codex-network-proxy`（17,064 行）相关。

---

## 6. 违规检测与记录（E3）

`codex-rs/sandboxing/src/violation.rs` 导出了一整套违规记录机制：

| 类型 / 函数 | 用途 |
| ---- | ---- |
| `SandboxViolationEvent` | 违规事件 |
| `SandboxViolationBackend` | 违规检测后端 |
| `FileSystemSandboxViolation` + `FileSystemSandboxViolationReason` | 文件系统违规及原因 |
| `NetworkSandboxViolation` | 网络违规 |
| `record_sandbox_violation` | 通用记录 |
| `record_filesystem_sandbox_violation` | 文件系统违规记录 |
| `record_network_sandbox_violation` | 网络违规记录 |

另有 `codex-rs/sandboxing/src/denial.rs` 的 `is_likely_sandbox_denied`——**启发式判断某次失败是否由沙箱拒绝导致**。这对错误信息的可读性很重要：命令失败时能区分"业务错误"与"被沙箱挡了"。

---

## 7. 策略与审批的关系（E3，次序已确认）

> [!NOTE]
> 本文第一版把这条次序标为「未验证（E1）、根据类型职责推断」。**其实源码里直接写了。** `codex-rs/core/src/tools/orchestrator.rs:1-8` 的模块头注释：
>
> > "Central place for approvals + sandbox selection + retry semantics. Drives a simple sequence for any ToolRuntime: **approval → select sandbox → attempt → retry with an escalated sandbox strategy on denial (no re-approval thanks to caching)**."

沙箱只解决"能做什么"，审批解决"要不要做"。**审批在前，沙箱选择在后，失败后还有一轮升级重试**：

```
模型发起工具调用
      ↓
【1) Approval】orchestrator.rs:151 `// 1) Approval`
   · exec_approval_requirement / default_exec_approval_requirement 定出 requirement
   · ExecApprovalRequirement::Skip 且开启严格自动评审时，仍会走一次 Guardian 评审
   · resolve_tool_apporval(..., ApprovalReviewer::Guardian | ApprovalReviewer::for_turn(..))
      ↓ 放行（already_approved = true）
【2) 选沙箱 + 第一次尝试】orchestrator.rs:226 `// 2) First attempt under the selected sandbox.`
   · sandbox_override_for_first_attempt(...) 决定是否 BypassSandboxFirstAttempt
   · SandboxManager::should_sandbox(&permissions, pref, managed_network_active)
   · SandboxManager::transform → SandboxType → spawn_process 执行
      ↓ 失败时
【3) 是否沙箱拒绝】orchestrator.rs:299 匹配 CodexErrorDetails::Sandbox(SandboxErr::Denied { .. })
   · is_likely_sandbox_denied（denial.rs）用于启发式判断
      ↓ 是
【4) 升级重试】orchestrator.rs:333-451
   · tool.escalate_on_failure() 为 false → 不重试（:333）
   · 审批策略为 Never / OnRequest 时不做「去沙箱」重试（:345）
   · 否则构造 retry_reason，按需二次审批（:392-404，严格自动评审下必须重新过 Guardian）
   · retry_sandbox / retry_sandbox_requested / retry_codex_linux_sandbox_exe → SandboxAttempt（:442）
      ↓
record_*_sandbox_violation 记录（violation.rs）
```

**「no re-approval thanks to caching」的边界**：普通情况下重试不再打扰用户（审批结果被缓存），但 `orchestrator.rs:391-395` 有例外注释——「retrying without the sandbox requires a fresh guardian review」，即**去掉沙箱的重试在严格自动评审模式下必须重新评审**。

### Guardian 自动评审后端

`core/src/guardian/` 是一个独立的审批评审后端。接入点：

| 位置 | 内容 |
| ---- | ---- |
| `codex-rs/core/src/tools/approvals.rs:133-135` | `enum ApprovalReviewer { Guardian, User }` |
| `orchestrator.rs:150` | `strict_auto_review_enabled_for_turn().await` 决定用哪个 reviewer |
| `orchestrator.rs:183`、`:215`、`:412` | **三处** `ApprovalReviewer::Guardian` 的选取（上一稿写作 `:172`、`:214-217`；`:172` 那一行其实是 `ApprovalCtx { turn: &tool_ctx.turn, .. }`，与 reviewer 无关。`:215` 与 `:412` 是同一形状的 `if strict_auto_review { Guardian } else { ApprovalReviewer::for_turn(turn_ctx) }`，分别位于首次审批与权限升级请求两条路径上） |
| `codex-rs/core/src/tools/approvals.rs:233`、`:264` | 消费侧：`ApprovalReviewer::Guardian` 分支与 `ApprovalResolutionSource::Guardian` 的映射 |
| `core/src/guardian/` 目录 | `review.rs`、`codex-rs/core/src/guardian/review_session.rs`、`codex-rs/core/src/guardian/approval_request.rs`、`prompt.rs`、`metrics.rs`、`codex-rs/core/src/guardian/policy.md`、`codex-rs/core/src/guardian/policy_template.md`、`snapshots/`（E1） |

`codex-rs/core/src/guardian/mod.rs:31-37` 导出 `GuardianReviewOptions`、`review_approval_request`、`guardian_timeout_message`、`new_guardian_review_id` 等——**有超时消息**这一点与 `ReviewDecision::TimedOut` 变体对应（见 [`core_agent_loop.md`](./core_agent_loop.md) §5.3）。

`SandboxPolicy` 的四个变体与字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §5.2；运行时的 `PermissionProfile` 见本文 §1.5。

---

## 8. 相关的执行安全 crate

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-execpolicy` | 2,937 | 执行策略；`codex execpolicy` 为 hidden 子命令 |
| `codex-shell-command` | 6,760 | shell 命令解析；**`is_known_safe_command()`** 在此 |
| `codex-shell-escalation` | 2,279 | 权限提升审批 |
| `codex-process-hardening` | 193 | 进程加固 |
| `codex-network-proxy` | 17,064 | 网络代理（与 MITM CA 相关） |
| `codex-rs/bwrap/` | — | 随产品分发的 bubblewrap |
| `codex-rs/exec-server/` + `codex-rs/exec-server-protocol/` | — | 执行边界服务与其协议，见本文 §5 |

> [!WARNING]
> **`is_safe_command()` 这个函数不存在。** 真实签名是
>
> ```rust
> // codex-rs/shell-command/src/command_safety/is_safe_command.rs:12
> pub fn is_known_safe_command(command: &[String]) -> bool
> ```
>
> **模块**名叫 `is_safe_command`，函数名叫 `is_known_safe_command`，两者不同名。本文第一版沿用了错的函数名，已更正。
>
> 需要注意的是，**上游源码注释里也还留着这个过时名字**——`codex-rs/protocol/src/protocol.rs:919`（`AskForApproval::UnlessTrusted` 的文档注释）与 `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs:362` 都写作 `is_safe_command()`。所以按这个名字 grep 会命中注释而找不到定义，容易误以为函数被删了。

`core/src/` 侧的对应文件：`exec.rs`、`codex-rs/core/src/exec_env.rs`、`exec_policy.rs`、`codex-rs/core/src/exec_policy_windows_tests.rs`（Windows 有独立测试文件，说明平台差异显著）。

---

## 9. 改动本区域的注意事项

| 事项 | 依据（AGENTS.md，按标题/关键词定位） |
| ---- | ---- |
| 🚫 **绝对禁止**触碰 `CODEX_SANDBOX_*` 相关代码 | 顶部规则列表，grep `Never add or modify any code related to` |
| 新增 `.sbpl` 或其他 `include_str!` 文件时必须补 `BUILD.bazel` 的 `compile_data` | 顶部规则列表，grep `Bazel does not automatically make source-tree files available` |
| 沙箱行为必须在 Linux / macOS / Windows 三平台都可用，除非是明确的 OS 专属特性 | `## Platform Support` |
| 改动沙箱逻辑属高风险，应补集成测试 | `### Test authoring guidance` |
| 单次改动尽量控制规模 | `### Change size guidance (800 lines)` |

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 三份 `.sbpl` 策略的具体规则 | E1（仅确认存在） | 直接读 `codex-rs/sandboxing/src/*.sbpl` |
| seccomp **拒绝规则**的完整清单（黑名单方向已确认，见 §3.3） | E1 | `codex-rs/linux-sandbox/src/landlock.rs` 中所有 `deny_syscall` 调用点 |
| bwrap 内外两层如何拼接（`build_inner_seccomp_command` / `run_bwrap_with_proc_fallback`） | E1 | `codex-rs/linux-sandbox/src/linux_run_main.rs:230-250` |
| Windows 两条后端路径的切换条件 | E1 | `codex-rs/windows-sandbox-rs/`（19,173 行） |
| `is_known_safe_command()` 的完整判定规则 | E1 | `codex-rs/shell-command/src/command_safety/` |
| execpolicy 的策略语言与规则格式 | E1 | `codex-rs/execpolicy/` |
| `codex-rs/sandboxing/src/policy_transforms.rs` 中 merge/intersect 的具体合成规则 | E1 | `codex-rs/sandboxing/src/policy_transforms.rs` |
| Guardian 评审的提示词与判定策略 | E1 | `codex-rs/core/src/guardian/policy.md`、`prompt.rs` |
| exec-server 协议的完整方法面 | E1 | `codex-rs/exec-server-protocol/src/` |
| MITM CA 与网络代理的完整链路 | E1 | `codex-rs/network-proxy/`（17,064 行） |

> **已从本表移除的两项**（第一版列为未验证，本次已在正文给出 E3 结论）：
> - 「Landlock/seccomp 与 bwrap 的选择条件」→ 见 §3.1，开关是 `use_legacy_landlock`
> - 「审批与沙箱在编排层的实际次序」→ 见 §7，源码注释直接写明

---

## 11. 相关文档

- [智能体核心循环](./core_agent_loop.md) — 审批与沙箱策略类型
- [架构总览](./architecture_overview.md) — 沙箱在整体架构中的位置
- [Crate 地图](./crate_map.md) §3.4 — 沙箱相关 8 个 crate
- [配置体系](./config_system.md) — 沙箱策略的配置入口
