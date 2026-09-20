---
title: Codex 工具执行与沙箱隔离
summary: 描述 codex-sandboxing 的五种沙箱类型与平台选择逻辑、运行时权限类型 PermissionProfile 与兼容层 SandboxPolicy、macOS Seatbelt 的十余段 sbpl 拼接与本轮新增的四项安全加固、Linux 沙箱的三道判据（前置 panic 使 legacy Landlock 与受限文件系统策略互斥、全盘写早退、bwrap 默认路径）与因 VmSocketRestricted 兜底而在非全盘写档位上恒装的 seccomp、vendored bubblewrap 源码与随发布捆绑链路、Windows 默认无沙箱及受限令牌/提权/MXC 三条后端、审批与沙箱的升级重试次序、沙箱违规检测在执行层的归属，以及 CODEX_SANDBOX 环境变量的绝对红线。第 6 轮上游同步修订：known-safe 白名单整体退役、Guardian 审批后端重构、Windows 新增 MXC 后端。
keywords: codex | sandbox | seatbelt | bwrap | bubblewrap-vendor | seccomp | landlock-legacy | permission-profile | windows-restricted-token | windows-mxc | vm-socket-restricted | wsl1 | execpolicy | round6
scope: codex-rs/sandboxing 及其平台实现 crate
related_files: codex-rs/sandboxing/src/manager.rs | codex-rs/sandboxing/src/lib.rs | codex-rs/sandboxing/src/policy_transforms.rs | codex-rs/sandboxing/src/windows.rs | codex-rs/linux-sandbox/src/landlock.rs | codex-rs/linux-sandbox/src/linux_run_main.rs | codex-rs/linux-sandbox/src/launcher.rs | codex-rs/linux-sandbox/src/bundled_bwrap.rs | codex-rs/linux-sandbox/README.md | codex-rs/bwrap/build.rs | codex-rs/features/src/lib.rs | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/shell-command/src/command_safety/is_dangerous_command.rs | codex-rs/protocol/src/sandbox.rs | codex-rs/sandboxing/src/windows_mxc.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-09-21
---

# 工具执行与沙箱隔离

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **覆盖范围**: `codex-rs/sandboxing`（10,097 行）+ 平台实现 crate
> **证据等级**: 类型定义、平台选择逻辑、Linux 三条出口分支（全盘写权限早退 / bwrap 默认 / legacy Landlock）、seccomp 与 `no_new_privs` 的网络门控、Windows direct-spawn 包装链、审批与沙箱次序为 E3；目录与文件清单、vendor 树的「未见 Codex 侧改动」判断为 E1/E2；`.sbpl` 策略文件的具体规则内容未逐条解读；Bazel 相关结论未做构建级验证

> [!CAUTION]
> **第 6 轮上游同步（基线跨越 2,230 个提交）推翻了本文六处叙事骨架。** 如果你读过旧版并记住了结论，以下六条请优先重读：
>
> | # | 旧版怎么说 | 现在的事实 | 见 |
> | ---: | ---- | ---- | ---- |
> | 1 | 「`is_safe_command()` 这个函数不存在，真名是 `is_known_safe_command()`，别以为函数被删了」 | **整个 known-safe 白名单被删了。** 两个名字全仓归零，判定极性翻转为黑名单 | §8 |
> | 2 | seccomp「只在网络受限或有受管代理时安装，不是无条件默认」 | 新增 `VmSocketRestricted` 兜底，**除全盘写档外恒装** | §3、§3.3 |
> | 3 | Windows「受限令牌 / 提权两条后端」，且「受管代理会强制走提权后端」 | **三条后端**（新增 MXC）；`proxy_enforced` 参数**已被删除**，后端选择只看 `WindowsSandboxLevel` | §4 |
> | 4 | Linux 主/备切换「两道判据」 | **三道**：新增无条件前置 panic，legacy Landlock 与任何受限文件系统策略互斥 | §3.1 |
> | 5 | Seatbelt「三段式拼接」 | **四份 `.sbpl`、十余段拼接**，含 4 项本轮新增的安全加固 | §2 |
> | 6 | Guardian 审批走 `ApprovalReviewer` 枚举选 reviewer | 该枚举与配套的 7 个锚点**全部不存在**，重构为 `strict_auto_review: bool` + `ApprovalContext` | §7 |
>
> **第 1 条尤其危险**：旧版在告诫读者「grep 不到定义是因为你名字写错了」，而真相恰恰相反——函数真的被删了。旧版的这条「更正记录」会二次误导，已整体重写。

> [!NOTE]
> **更早几轮的修订史**（保留备查，不构成当前事实断言）：第一版曾写错 Linux 沙箱的主备关系、bwrap 与 Landlock 的切换开关位置、seccomp 过滤器的黑/白名单方向；第 5 轮补齐了 `codex-rs/vendor/bubblewrap/`（§3.2）与 WSL1 行为（§3.5），并更正了沙箱违规判定与记录的归属（在执行层而非 orchestrator，§7）。

---

## 0. 先读这一节：绝对红线

> [!CAUTION]
> **`AGENTS.md` 顶部规则列表规定：禁止新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码**（grep `Never add or modify any code related to`）。
>
> **AGENTS.md 原文**（`AGENTS.md:8`）限定的对象是 *code*：不要新增或修改任何与这两个环境变量相关的**代码**，原文本身未写出「无例外」这样的例外条款。
>
> **本文的建议**（比原文更保守，安全上是对的）：把它当成没有例外的红线——即使你认为改动是安全的、即使是重构、即使只是改注释，都不要碰。本文档也不复述这两个环境变量的取值与判定逻辑。

---

## 1. 五种沙箱类型（E3）

> **第 6 轮变更**：从四种增至五种（新增 `WindowsMxc`），且**枚举已从 `codex-sandboxing` 搬到 `codex-protocol`**——`codex-rs/sandboxing/src/manager.rs:25` 现在只是一行 `pub use codex_protocol::sandbox::SandboxType;`。按旧路径找定义会扑空。

`codex-rs/protocol/src/sandbox.rs:10-16`：

```rust
pub enum SandboxType {
    None,
    MacosSeatbelt,
    LinuxSeccomp,
    WindowsRestrictedToken,
    WindowsMxc,
}
```

对应的指标标签（`codex-rs/protocol/src/sandbox.rs:19-27` 的 `as_metric_tag()`）：`none` / `seatbelt` / `seccomp` / `windows_sandbox` / `windows_mxc`。同文件 `:31-42` 另有本文未展开的 `effective_windows_sandbox_type`。

### 平台选择逻辑（E3，`codex-rs/sandboxing/src/manager.rs:47-61`）

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
| Windows | `WindowsRestrictedToken` / `WindowsMxc` **或 `None`** | **默认 `None`**。要拿到前两者必须显式配置，见下方说明 |
| 其他 | `None` | 无沙箱 |

> [!IMPORTANT]
> **Windows 的默认值仍然是「无沙箱」，但第 6 轮的证据链已整体换掉。** 结论没变，三层证据里有两层要重写：
>
> 1. `WindowsSandboxLevel` 的 `#[default]` 变体仍是 `Disabled`（`codex-rs/protocol/src/config_types.rs:297-302`）；
> 2. **配置键已从 `windows_sandbox_mode` 换成 TOML 的 `[windows].sandbox`**（解析见 `codex-rs/core/src/windows_sandbox.rs:83` 的 `resolve_windows_sandbox_mode`），取值为三态枚举 `WindowsSandboxModeToml::{Elevated, Unelevated, Mxc}`；未配置时**不再直接落到 `Disabled`**，而是回落到 feature（`codex-rs/core/src/windows_sandbox.rs:61-67` 的 `None => Self::from_features(&config.features)`），feature 也关时才在 `codex-rs/core/src/config/windows_sandbox_config.rs:51` 得到 `(SandboxType::None, WindowsSandboxLevel::Disabled)`；
> 3. `select_initial` 的第三个参数**已从 `WindowsSandboxLevel` 换成 `SandboxType`**（`codex-rs/sandboxing/src/manager.rs:301-318`），传给 `get_platform_sandbox` 的实参现在是 `windows_sandbox_type != SandboxType::None`。
>
> 旧的两个 feature（`experimental_windows_sandbox` / `elevated_windows_sandbox`）在 `codex-rs/features/src/lib.rs:1232-1243` 仍是 `Stage::Removed` + `default_enabled: false`，现降级为 legacy 兼容读取（`codex-rs/core/src/windows_sandbox.rs:97-119`）。

> [!CAUTION]
> **「`WindowsSandboxLevel == Disabled` ⇒ 没有沙箱」这条推断在 MXC 模式下不成立。**
>
> 配置为 `mxc` 时得到的是 `(SandboxType::WindowsMxc, WindowsSandboxLevel::Disabled)`（`codex-rs/core/src/config/windows_sandbox_config.rs:48-50`）——**level 是 `Disabled`，但沙箱是开着的**。`select_initial` 在 `codex-rs/sandboxing/src/manager.rs:314-316` 对 `WindowsMxc` 做了短路，根本不走 `get_platform_sandbox`。
>
> 真正的判据是 `SandboxType`，不是 `WindowsSandboxLevel`。上游为此专门留了一个适配器 `windows_sandbox_level_for_legacy_checks`（`codex-rs/core/src/windows_sandbox.rs:43-53`），其注释明写「Backend selection must continue to use `SandboxType` directly.」

> [!WARNING]
> **不要把上表读成「macOS/Linux 一定有沙箱」。** `get_platform_sandbox` 只回答「本平台能提供哪种沙箱实现」，它不是入口。真正的入口是 `SandboxManager::select_initial`（`codex-rs/sandboxing/src/manager.rs:301`），它先调 `should_sandbox`（`codex-rs/sandboxing/src/manager.rs:322`），返回 false 时**直接给 `SandboxType::None`**，根本不问平台：
>
> ```rust
> // manager.rs:301-318（节选，第 6 轮实测）
> pub fn select_initial(
>     &self,
>     permission_profile: &PermissionProfile,
>     pref: SandboxablePreference,
>     windows_sandbox_type: SandboxType,        // ← 第 6 轮参数类型由 WindowsSandboxLevel 改为 SandboxType
>     has_managed_network_requirements: bool,
> ) -> SandboxType {
>     #[cfg(windows)]
>     crate::windows_mxc::record_availability_once();
>     if !self.should_sandbox(...) { return SandboxType::None; }
>     if cfg!(windows) && windows_sandbox_type == SandboxType::WindowsMxc {
>         return SandboxType::WindowsMxc;       // ← MXC 短路，不经 get_platform_sandbox
>     }
>     get_platform_sandbox(windows_sandbox_type != SandboxType::None).unwrap_or(SandboxType::None)
> }
> ```
>
> 所以准确的说法是：**三平台都先过 `should_sandbox` 这道闸**；`windows_sandbox_enabled` 是过闸之后 Windows 独有的**第二道**条件。本文第一版写的「这是三个平台中唯一有条件的分支」有误导性，已更正。

### 沙箱偏好（`codex-rs/sandboxing/src/manager.rs:41`）

```rust
pub enum SandboxablePreference { Auto, Require, Forbid }
```

`should_sandbox` 对这三者的处理（`codex-rs/sandboxing/src/manager.rs:296-306`，E3）：

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
| 权限被**拆成两个正交维度**：文件系统与网络 | `PermissionProfile::to_runtime_permissions()` 返回 `(FileSystemSandboxPolicy, NetworkSandboxPolicy)` 二元组，调用点见 `codex-rs/sandboxing/src/manager.rs:85`、`:300` |

> [!IMPORTANT]
> **别把 `ManagedFileSystemPermissions` 和 `FileSystemSandboxPolicy` 当成同一个类型。** 本文与 [`core_agent_loop.md`](./core_agent_loop.md) 的上一稿都在这里把两者混为一谈了。它们是**两个不同的类型，处在链路的不同端**：
>
> | 类型 | 定义位置 | 角色 |
> | ---- | ---- | ---- |
> | `ManagedFileSystemPermissions` | `codex-rs/protocol/src/models.rs:258` | **`PermissionProfile::Managed` 的字段类型**。是个两变体枚举：`Restricted { entries, glob_scan_max_depth }` / `Unrestricted` |
> | `FileSystemSandboxPolicy` | 定义在 `codex-rs/protocol/src/permissions.rs:223`，经 `codex-rs/protocol/src/models.rs:19` 的 `use crate::permissions::...` 引入 | **运行时的展开形态**，结构体，带 `kind` / `glob_scan_max_depth` / `entries` 三个字段 |
>
> 两者由 `ManagedFileSystemPermissions::to_sandbox_policy()`（`codex-rs/protocol/src/models.rs:288`）与 `::from_sandbox_policy()`（`:273`）互转。
>
> 换言之：**`PermissionProfile::Managed` 的字段签名是 `file_system: ManagedFileSystemPermissions, network: NetworkSandboxPolicy`**（`codex-rs/protocol/src/models.rs:320-322`）——只有 `network` 这一维是直接用 `*SandboxPolicy` 类型的，文件系统那一维隔了一层。上面代码块里的枚举定义是对的，是这张表的措辞把它抹平了。
| **没有任何一个 `SandboxManager` 方法接受 `SandboxPolicy`** ——这才是结论。签名并不整齐：`select_initial`（`codex-rs/sandboxing/src/manager.rs:272`）与 `should_sandbox`（`:289`）**直接**收 `&PermissionProfile`；`transform`（`:310`）收的是 `SandboxTransformRequest<'_>`（`:310-313`），`PermissionProfile` 只是它的 `permissions` 字段（结构体定义在 `:129`，该字段在 `:131`）。此外还有第四个公开方法 `transform_for_direct_spawn`（`:443`），收 `SandboxDirectSpawnTransformRequest<'_>` | `codex-rs/sandboxing/src/manager.rs:272`、`:289`、`:310-313`、`:443` |
| `SandboxPolicy` 退化为**线上/兼容层类型** | `codex-rs/sandboxing/src/lib.rs:27` 导出 `compatibility_sandbox_policy_for_permission_profile`，被 `codex-rs/core/src/config/mod.rs:479`、`codex-rs/core/src/codex_thread.rs:139` 调用 |

### 策略的合成：`codex-rs/sandboxing/src/policy_transforms.rs`

这个模块负责把多来源的权限声明合成为一个 profile，公开函数（E3）：

| 函数 | 位置 | 用途 |
| ---- | ---- | ---- |
| `normalize_additional_permissions` | `:19` | 归一化附加权限声明（第 6 轮唯一行号未漂的一条） |
| `merge_permission_profiles` | `:93` | **并集**合成（放宽） |
| `intersect_permission_profiles_with_context` | `:147` | **交集**合成（收紧）。⚠️ 第 6 轮改名，旧名 `intersect_permission_profiles` 已不存在 |
| `effective_file_system_sandbox_policy` | `:582` | 求有效文件系统策略 |
| `effective_network_sandbox_policy` | `:615` | 求有效网络策略 |
| `effective_permission_profile` | `:630` | 求有效 profile |
| `should_require_platform_sandbox` | `:646` | `Auto` 偏好下是否需要平台沙箱 |

> [!WARNING]
> **上一版在这里犯了「拿测试导入当生产证据」的错。** 旧文写「`handlers/mod.rs:38-40` 同时导入了 `intersect_permission_profiles`、`merge_permission_profiles`、`normalize_additional_permissions`——说明工具侧既有放宽也有收紧路径」。实测 `codex-rs/core/src/tools/handlers/mod.rs:39-42` 的生产导入是 `materialize_additional_permissions_with_context`、`merge_permission_profiles`、`normalize_additional_permissions_with_context`；**`intersect_*` 的唯一导入在 `:399`，位于起自 `:383` 的 `#[cfg(test)] mod tests` 之内**——是测试专用。
>
> 「工具侧确实存在收紧路径」这个结论**侥幸仍然成立**，但证据要换成生产调用点 `codex-rs/core/src/session/mod.rs:3245`（`request_permissions` 的响应与请求求交）。这正是本体系反复强调的「类型/导入存在 ≠ 生产路径生效」。

`SandboxPolicy` 四个变体的字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §5.2。

---

## 2. macOS：Seatbelt（E3）

### 四份 sbpl 策略文件

> **第 6 轮变更**：从三份增至四份（新增 `seatbelt_preferences_policy.sbpl`），且旧文件 `restricted_read_only_platform_defaults.sbpl` 更名为 `seatbelt_read_only_platform_defaults.sbpl`。 <!-- ref-exempt: 反例——正文说明旧文件名已不存在 -->

`codex-rs/sandboxing/src/seatbelt.rs:21-25` 通过 `include_str!` 内嵌四份策略：

| 常量 | 文件 | 何时选用 |
| ---- | ---- | ---- |
| `MACOS_SEATBELT_BASE_POLICY` | `codex-rs/sandboxing/src/seatbelt_base_policy.sbpl` | **恒含**——永远是拼接结果的第一段 |
| `MACOS_SEATBELT_NETWORK_POLICY` | `codex-rs/sandboxing/src/seatbelt_network_policy.sbpl` | **条件叠加**：只在网络被放行（回环代理或全网）时进入拼接。该常量只出现在 `codex-rs/sandboxing/src/seatbelt.rs:351` 与 `:374` 两个放行分支；网络被拒时 `dynamic_network_policy_for_network` 返回 `String::new()`（`:357` / `:363` / `:376`），这一段等于空 |
| `MACOS_SEATBELT_PREFERENCES_POLICY` | `codex-rs/sandboxing/src/seatbelt_preferences_policy.sbpl` | **第 6 轮新增**，条件为 `file_system_sandbox_policy.has_full_disk_read_access()`（`codex-rs/sandboxing/src/seatbelt.rs:1054-1056`） |
| `MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS` | `codex-rs/sandboxing/src/seatbelt_read_only_platform_defaults.sbpl` | **条件追加**：仅当 `file_system_sandbox_policy.include_platform_defaults()` 为真时 `push`（`codex-rs/sandboxing/src/seatbelt.rs:1057-1058`）。该判定 = 非全盘可读 **且** `kind == Restricted` **且** entries 中存在可读的 `Special{Minimal}` 条目（`codex-rs/protocol/src/permissions.rs:949-960`） |

> [!IMPORTANT]
> 这四份 `.sbpl` 是通过 `include_str!` 在**编译期**读入的。按 AGENTS.md 顶部规则列表（grep `Bazel does not automatically make source-tree files available`），这类编译期文件读取必须在 `BUILD.bazel` 中配置 `compile_data`（或 `build_script_data` / test data），否则 **Cargo 能过而 Bazel 会失败**。改动这些文件或新增同类文件时务必注意。
>
> **注意**：「Cargo 能过而 Bazel 会失败」这句是 AGENTS.md 规则的转述，**本文未做构建级验证**（没有跑过 Bazel），仅为 E2。第 6 轮已复核：四份 `.sbpl` 均已登记在 `codex-rs/sandboxing/BUILD.bazel:5-10` 的 `compile_data` 中。

### 命令构造入口

```rust
// seatbelt.rs:860
pub struct CreateSeatbeltCommandArgsParams<'a> { ... }

// seatbelt.rs:872
pub fn create_seatbelt_command_args(...);
```

> [!CAUTION]
> **第 6 轮：「三段式拼接」这个骨架已经不成立了。** 实测 `codex-rs/sandboxing/src/seatbelt.rs:1048-1088` 按顺序 push **十二段**，其中至少四段是本轮新增的安全加固，旧版完全没有记载。

最终交给 `sandbox-exec` 的策略按下列顺序拼成（E3，`codex-rs/sandboxing/src/seatbelt.rs:1048-1088`）：

| # | 段 | 条件 |
| ---: | ---- | ---- |
| 1 | `MACOS_SEATBELT_BASE_POLICY` | 恒含 |
| 2 | `file_read_policy` | 动态生成 |
| 3 | `file_write_policy` | 动态生成 |
| 4 | `network_policy` | 动态生成，网络被拒时为空串 |
| 5 | `MACOS_SEATBELT_PREFERENCES_POLICY` | **新增**，`has_full_disk_read_access()`（`:1054-1056`） |
| 6 | `MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS` | `include_platform_defaults`（`:1057-1058`） |
| 7 | `(allow file-read* (subpath "/Applications"))` | **新增**，且额外要求 `profile == MacosSeatbeltProfile::Process`（`:1059-1061`） |
| 8 | `daemon::protection_policy(&shared_daemon_socket_directory())` | **新增**，`!has_full_disk_write_access()`（`:1063-1069`） |
| 9 | `(deny mach-lookup (xpc-service-name-prefix ""))` | **新增，无条件**（`:1069`） |
| 10 | `deny_read_policy` | 动态生成 |
| 11 | protected-ancestor 的 `deny file-write-unlink` 批量段 | **新增**（`:1075-1081`） |
| 12 | `(deny system-fcntl (fcntl-command 80 110))` | **新增**，`!has_full_disk_write_access()`（`:1083-1088`） |

第 8、9、11、12 项是本轮 macOS 侧最实质的语义增量，各自的动机都写在源码注释里：

- **第 8 项（daemon socket 保护）**：「Network grants and Unix-socket allowlists must never reopen the privileged app-server RPC transport to filesystem-restricted commands」。**这与 §3.1 里 Linux 侧新增的那条前置 panic 是同一条上游治理主线**——两个平台同时在堵「受限命令经由 app-server socket 逃逸」这条路。
- **第 11 项**：注释说明必须放在最后，否则 rename 可以绕过。
- **第 12 项**：「These fcntls mutate files through read-only descriptors, bypassing file-write* and file-ioctl」——即用只读 fd 改写文件的绕过手法。

网络访问仍是**叠加**上去的独立维度，与 `SandboxPolicy` 中 `network_access` 默认为 `false` 的设计一致。

---

## 3. Linux：bwrap（需要文件系统隔离时的默认）+ 非全盘写档位恒装的 seccomp / no_new_privs（E3）

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
> 同文件 `:144-146` 对 `install_filesystem_landlock_rules_on_current_thread` 的注释：
> > "Note: this is **currently unused** because filesystem sandboxing is performed via bubblewrap. It is kept for reference and potential fallback use."

枚举名 `LinuxSeccomp`、指标标签 `seccomp` 只描述了三件套里的一件。实际组合：

| 机制 | 作用面 | 状态 | 依赖 |
| ---- | ---- | ---- | ---- |
| **bubblewrap（bwrap）** | 文件系统隔离（mount namespace） | **需要文件系统隔离时的默认路径**（全盘写权限档会整体跳过，见 §3.1） | `codex-rs/linux-sandbox/src/bwrap.rs`（helper 侧 argv 构造与执行）+ `codex-rs/sandboxing/src/bwrap.rs`（系统 bwrap 查找与启动告警，职责不同，别混）/ `codex-rs/linux-sandbox/src/bundled_bwrap.rs` / `codex-rs/linux-sandbox/src/bazel_bwrap.rs`、`codex-rs/bwrap/` crate |
| **seccomp** | 系统调用过滤 | **除全盘写权限档外恒装**（第 6 轮变更，见下方 CAUTION），在 bwrap 内层生效；共三种模式，由网络策略与代理路由共同选择 | seccompiler crate（过滤器构造用到 BpfProgram、SeccompAction） |
| **`no_new_privs`** | 阻止提权 | **非全盘写权限档上恒设**（因 seccomp 恒装而连带）；只有 `danger-full-access` 且无受管代理时才跳过 | 内核原语（`codex-rs/linux-sandbox/src/landlock.rs:68-72` 为判定表达式，`:127` 起为函数） |
| **Landlock（`AccessFs`、`Ruleset`）** | 文件系统访问控制 | **遗留/备份，且第 6 轮起在受限文件系统策略下被前置 panic 拒绝**，见 §3.1 | `landlock` crate（`codex-rs/linux-sandbox/Cargo.toml:29`，位于 `[target.'cfg(target_os = "linux")'.dependencies]`，是**生产依赖而非 dev 依赖**） |

> [!CAUTION]
> **第 6 轮推翻了本文上一版的核心论点。** 旧版说「seccomp 与 `no_new_privs` 都被网络策略门控，不是无条件三件套」——这在**函数级**仍然为真，但在**调用级**已经不成立，因为调用方加了一条兜底。
>
> `codex-rs/linux-sandbox/src/landlock.rs:52-64`：
>
> ```rust
> let network_seccomp_mode = network_seccomp_mode(
>     network_sandbox_policy, managed_network.is_some(), proxy_routing_active,
> )
> .or_else(|| {
>     // VM sockets can reach host services outside the filesystem sandbox.
>     // In WSL2 they also allow Windows process launch through an alias of
>     // the interop socket, even when /run/WSL is masked. Keep ordinary
>     // network access while denying that host bridge.
>     (!file_system_sandbox_policy.has_full_disk_write_access())
>         .then_some(NetworkSeccompMode::VmSocketRestricted)
> });
> ```
>
> **实际语义**：只要权限档**不是全盘写**，`network_seccomp_mode` 就一定是 `Some`，seccomp 就一定会装（最低档 `VmSocketRestricted`，只拒 `AF_VSOCK`）。旧版据此得出的「全网放行 + 无代理的 workspace-write 档没有 seccomp」是**错误的安全结论**。
>
> 连带地，`no_new_privs` 的判定表达式没变（`:68-72` 仍是 `network_seccomp_mode.is_some() || (apply_landlock_fs && !has_full_disk_write_access())`），但因为左操作数在所有非全盘写档位上恒为真，它也从「偶发连带」变成了「恒设」。注释解释的动机不变——`PR_SET_NO_NEW_PRIVS` 会阻断 setuid 提权，而很多 bwrap 部署依赖 setuid，所以全盘写档位要留口子。
>
> **这是最容易「看着还对、实则已错」的一处**：门控函数 `should_install_network_seccomp`（`:104-111`）与那条反证测试（`:368-377`）在函数级都还在、都还能通过，只有调用点多了一层 `.or_else()`。只核验被引用的函数、不追调用方，就会漏掉。

### 3.1 主/备切换：三道判据（第 6 轮新增第 0 道）（E3）

> [!NOTE]
> **历次修订**：第一版把这条标为「未验证（E1）」并让读者去看 `codex-rs/linux-sandbox/src/launcher.rs`——**指错了文件**（那里只在「系统 bwrap」与「随产品分发的 bwrap」之间选，跟 Landlock 无关）。第二版把开关简化成「真正的开关是 `use_legacy_landlock`」，漏掉了在此之前的无条件早退。第三版补上了早退，定为「两道判据」。

> [!CAUTION]
> **第 6 轮：上游新增了一道无条件前置 panic，使「legacy Landlock 仍是一条可用的文件系统隔离后备」这个前提不再成立。**
>
> `codex-rs/linux-sandbox/src/linux_run_main.rs:405-411`：
>
> ```rust
> fn ensure_legacy_landlock_mode_supports_policy(
>     use_legacy_landlock: bool,
>     file_system_sandbox_policy: &FileSystemSandboxPolicy,
> ) {
>     if use_legacy_landlock && !file_system_sandbox_policy.has_full_disk_write_access() {
>         panic!("filesystem-restricted execution requires bubblewrap to isolate app-server sockets");
>     }
> }
> ```
>
> 它在 `run_main()` 的 `:189` **无条件调用**，早于所有分支。配套测试 `codex-rs/linux-sandbox/src/linux_run_main_tests.rs` 的 `legacy_landlock_cannot_bypass_daemon_socket_isolation` 带 `#[should_panic(expected = "filesystem-restricted execution requires bubblewrap")]`。`codex-rs/linux-sandbox/README.md` 也已写明：「Filesystem-restricted execution requires bubblewrap. The legacy Landlock option is rejected for these policies because it cannot isolate app-server Unix sockets.」
>
> **推论（承重）**：通过前置校验后，`use_legacy_landlock` 为真的情况下必然 `has_full_disk_write_access() == true`；而「全盘写 + 无代理」又被判据 (a) 早退吃掉。**legacy Landlock 分支的唯一可达条件是「全盘写 + 有受管代理」——而在该条件下 `apply_landlock_fs && !has_full_disk_write_access()` 恒假，Landlock 规则根本不会安装。**
>
> 也就是说：**legacy Landlock 已经不能提供任何文件系统隔离，只剩一个空壳分支。**
>
> 注意这条 panic 的理由（隔离 app-server Unix socket）与 §2 里 macOS Seatbelt 新增的第 8 段（daemon socket 保护）**动机完全相同**——这是一条跨平台的上游安全治理主线。

`run_main()` 里决定走哪条路，实际有**三道判据**：

**判据 (0)：无条件前置 panic——legacy Landlock 与任何受限文件系统策略互斥。** 见上方 CAUTION，位置 `codex-rs/linux-sandbox/src/linux_run_main.rs:189`（调用）/ `:405-411`（定义）。

**判据 (a)：全盘写权限 + 无受管代理 → bwrap 被整体跳过。**
在到达 `use_legacy_landlock` 判断之前，`codex-rs/linux-sandbox/src/linux_run_main.rs:276-287` 有一条无条件早退：

```rust
if file_system_sandbox_policy.has_full_disk_write_access() && !allow_network_for_proxy {
    // 只做进程内约束（不套 Landlock 文件系统规则），然后直接 exec
    apply_permission_profile_to_current_thread(..., /*apply_landlock_fs*/ false, ...);
    exec_or_panic(command);   // 在 :289 的分支之前 return
}
```

也就是说，`danger-full-access` 一类权限档**根本不进 bwrap**，这与 `use_legacy_landlock` 的取值无关。

**判据 (b)：残余的 `use_legacy_landlock` 选路。**
`codex-rs/linux-sandbox/src/linux_run_main.rs:289` 的 `if !use_legacy_landlock { ... }` 决定走 bwrap 默认路径，还是落到其后的 legacy Landlock 路径（`:343` 之后）。**经判据 (0) 与 (a) 夹逼后，后者已无实际隔离能力**，见上方 CAUTION。

**判据在编排侧被合成一个表达式**：`codex-rs/sandboxing/src/manager.rs:777-778`

```rust
let requires_bubblewrap = allow_network_for_proxy
    || (!use_legacy_landlock && !file_system_sandbox_policy.has_full_disk_write_access());
```

判据 (b) 的开关是 **`use_legacy_landlock`**：

| 层 | 形态 | 位置 |
| ---- | ---- | ---- |
| 配置 | `[features].use_legacy_landlock` | `codex-rs/features/src/lib.rs:518`（读取器）、`:1222`（键定义） |
| 前置 panic（判据 0，**最先执行**） | `ensure_legacy_landlock_mode_supports_policy` | `codex-rs/linux-sandbox/src/linux_run_main.rs:189` / `:405-411` |
| CLI | `--use-legacy-landlock`，`hide = true`，`default_value_t = false` | `codex-rs/linux-sandbox/src/linux_run_main.rs:114-118` |
| 早退（判据 a） | `if has_full_disk_write_access() && !allow_network_for_proxy { ... exec_or_panic }` | `codex-rs/linux-sandbox/src/linux_run_main.rs:276-287` |
| 分支（判据 b） | `if !use_legacy_landlock { ... }` | `codex-rs/linux-sandbox/src/linux_run_main.rs:289` |
| 合成表达式 | `requires_bubblewrap` | `codex-rs/sandboxing/src/manager.rs:777-778` |
| 传递 | 生产路径已改为 `sandbox_config.use_legacy_landlock`（`codex-rs/core/src/tools/orchestrator.rs:307`、`:481`）；`features.use_legacy_landlock()` 的唯一生产调用点上移至 `codex-rs/core/src/session/mod.rs:854`，其余全在测试 |

`codex-rs/linux-sandbox/src/linux_run_main.rs:218-220` 的注释把 bwrap 分支的语义写死了：

> "Outer stage: bubblewrap first, then re-enter this binary in the sandboxed environment to apply seccomp. **This path never falls back to legacy Landlock on failure.**"

而 `:251` 之后才是：

> "**Legacy path**: Landlock enforcement only, when bwrap sandboxing is not enabled."

**该开关已被标记废弃**：`codex-rs/features/src/lib.rs` 中它属于 `Stage::Deprecated`，`codex-rs/core/tests/suite/deprecation_notice.rs:104-135` 有专门的断言，期望的提示文案是

```
`[features].use_legacy_landlock` is deprecated and will be removed soon.
```

另外 `codex-rs/linux-sandbox/src/linux_run_main.rs:302-320` 有两条互斥校验：`--apply-seccomp-then-exec` 不能与 `--use-legacy-landlock` 同用；需要「直接运行时强制」的 permission profile 也与 legacy 分支不兼容。

### 3.2 bwrap 从哪来：查找、编译、捆绑（E3）

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/linux-sandbox/src/bwrap.rs` | helper 侧的 bubblewrap 封装（argv 构造与执行） |
| `codex-rs/sandboxing/src/bwrap.rs` | **另一个同名文件，职责不同**：系统 bwrap 的 PATH 查找与启动期告警 |
| `codex-rs/linux-sandbox/src/bundled_bwrap.rs` | 定位并 exec 随产品分发的 bwrap（316 行） |
| `codex-rs/linux-sandbox/src/bazel_bwrap.rs` | Bazel runfiles 下的候选解析（68 行，**dev/test-only**） |
| `codex-rs/linux-sandbox/src/launcher.rs` | `preferred_bwrap_launcher()`：三态选择，见下 |

#### `preferred_bwrap_launcher()` 是三态，不是二选一

`codex-rs/linux-sandbox/src/launcher.rs:51-67` 返回的 `BubblewrapLauncher` 有 **三个** 变体，且**系统 bwrap 优先**：

1. **`System`** —— 先试 `find_system_bwrap_in_path()`；找到还不算数，还要过一道**能力探测**：`system_bwrap_launcher_for_path_with_probe`（`codex-rs/linux-sandbox/src/launcher.rs:81-87`）跑 `bwrap --help`（`:108-124`），要求输出里含 `--perms` 才接受（`supports_perms: true`），同时顺带记下是否支持 `--argv0`——老版本（Ubuntu 20.04/22.04 一类）不支持 `--argv0`，会切到内层 re-exec 的兼容路径。
2. **`Bundled`** —— 系统 bwrap 不可用时退到 `bundled_bwrap::launcher()`。
3. **`Unavailable`** —— 两者都拿不到。此时 `exec_bwrap`（`codex-rs/linux-sandbox/src/launcher.rs:42-47`）**直接 panic**，提示「no system bwrap was found on PATH and no bundled codex-resources/bwrap binary was found」。

结果被 `OnceLock` 缓存（`codex-rs/linux-sandbox/src/launcher.rs:52`），整个进程只探测一次。

#### 系统 bwrap 的查找与告警（E3）

`codex-rs/sandboxing/src/lib.rs:14,16` 导出了 `find_system_bwrap_in_path` 与 `system_bwrap_warning`——但**光看导出名只是 E1 推断**。真正的实现证据：

- `system_bwrap_warning`（`codex-rs/sandboxing/src/bwrap.rs:40`）：在权限档需要 bwrap 时，若系统 bwrap 缺失或无法创建 user namespace，产出启动期告警文案。
- `find_system_bwrap_in_path`（`codex-rs/sandboxing/src/bwrap.rs:168`）：用 `which::which_in_all` 遍历 `PATH`，并**刻意跳过落在当前工作目录下的命中**（`:174-191`，`path.starts_with(&cwd)` 时丢弃，除非 cwd 就是根）——防止仓库里放一个假的 `bwrap` 劫持沙箱。

#### vendored bubblewrap：`codex-rs/vendor/bubblewrap/`

> [!IMPORTANT]
> **这是 Linux 默认沙箱所依赖二进制的真实源头，路径容易记错。** `vendor/` **不在仓库根**——仓库根下的 `third_party/` 与 `patches/` 与沙箱无关；bubblewrap 的 C 源码在 **`codex-rs/vendor/bubblewrap/`**。

**是什么。** 上游 `containers/bubblewrap` **v0.11.2** 的完整源码 drop，约 508 KB / 49 个文件（`git ls-files` 数为 50，多出的一条是 `LICENSE -> COPYING` 符号链接），未见 Codex 侧改动（E2：目录比对，未做逐字节 diff）。版本证据：`codex-rs/vendor/bubblewrap/meson.build:4` 的 `version : '0.11.2'`，以及 `codex-rs/vendor/bubblewrap/NEWS.md:1-18`（0.11.2 条目；CVE-2026-41163 的 setuid 修复在 `:10`）。上游的 `meson.build` / `tests/` / `demos/` 一并带入，但 **Codex 的构建不使用它们**。

**怎么编。** `codex-rs/bwrap` 是个薄壳 crate（Rust 侧仅 151 行 = `codex-rs/bwrap/build.rs` 106 行 + `codex-rs/bwrap/src/main.rs` 45 行；后者的三个 `#[cfg]` 分支各只有几行，第一个 `fn main()` 结束于 `:29`——**别把它当成文件总行数**），产出**独立二进制 `bwrap`**，无 lib target（`codex-rs/bwrap/Cargo.toml:7-9` 只有 `[[bin]]`）：

- `codex-rs/bwrap/build.rs:14` 指向 `../vendor/bubblewrap`（也可用 `CODEX_BWRAP_SOURCE_DIR` 覆盖，`:84-99`）；
- `codex-rs/bwrap/build.rs:53-56` 用 `cc` 把 4 个 C 文件（`bubblewrap.c` / `bind-mount.c` / `network.c` / `utils.c`）编成静态库；
- **关键在 `codex-rs/bwrap/build.rs:59-61` 的 `.define("main", Some("bwrap_main"))`**——把上游的 `main` 改名成一个可调用符号，再由 Rust 的 `main` 转发 argv 去调 `extern "C" bwrap_main`；
- libcap 经 `pkg-config` 定位（`codex-rs/bwrap/build.rs:37-40`、`:69-74`），成功后发出 `cargo:rustc-cfg=bwrap_available`（`:75`）；
- 设了 `CODEX_SKIP_BWRAP_BUILD` 或目标不是 Linux 时直接跳过编译（`codex-rs/bwrap/build.rs:22-25`）。

> [!NOTE]
> **C 源码进的是独立的 `bwrap` 可执行文件，不是 `codex` 主二进制。** `codex-bwrap` 也**不是** `codex-core` 的依赖，只是同一 workspace 的成员。

**`codex-rs/linux-sandbox/src/bundled_bwrap.rs` 做什么：定位磁盘上的 bwrap 文件并 exec，二进制既不内嵌也不解压。**
`launcher()`（`codex-rs/linux-sandbox/src/bundled_bwrap.rs:28-33`）依次尝试：

1. `InstallContext::bundled_resource("bwrap")` → `<package>/codex-resources/bwrap`（`codex-rs/linux-sandbox/src/bundled_bwrap.rs:72-76`）；
2. `legacy_candidates_for_exe`（`:92-107`）：`<exe_dir>/codex-resources/bwrap` → `<exe_dir>/../codex-resources/bwrap`（npm 的 `vendor/<target>/` 布局）→ `<exe_dir>/bwrap` → `bazel_bwrap::candidate()`。

`exec()`（`codex-rs/linux-sandbox/src/bundled_bwrap.rs:36-69`）有一处值得记住的安全设计：**先打开文件拿到 fd，用编译期内嵌的 `option_env!("CODEX_BWRAP_SHA256")` 校验 SHA-256（`:116-124`、`:126-160`），然后 `execv` 的目标是 `/proc/self/fd/<fd>` 而不是路径**——校验的字节与执行的字节是同一个 inode，规避 TOCTOU。注意：**该环境变量未设置、或摘要为全零时，校验被跳过**（`:118-123` 的 `(digest != NULL_SHA256_DIGEST).then_some(digest)`）。

**`codex-rs/linux-sandbox/src/bazel_bwrap.rs` 做什么：dev/test-only 的 runfiles 解析器，不是生产路径。**
只有一个 `pub(crate) fn candidate()`。`#[cfg(debug_assertions)]` 的版本要求 `option_env!("BAZEL_PACKAGE").is_some()` **且**至少存在一个 runfiles 环境变量（`codex-rs/linux-sandbox/src/bazel_bwrap.rs:12`、`:29-33`）；`#[cfg(not(debug_assertions))]` 的版本**硬返回 `None`**（`:23-26`）——**release 构建永远不会走这条路**。它与 bundled 路径不是互斥关系，而是后者候选链的最后一环。

**是否随发布捆绑：是。**

| 环节 | 证据 |
| ---- | ---- |
| 发布矩阵把 `bwrap` 列为产物（仅两个 Linux target） | `.github/workflows/rust-release.yml:113`、`:125` 的 `binaries: "codex codex-code-mode-host codex-responses-api-proxy bwrap"` |
| 单独构建并计算摘要 | `.github/workflows/rust-release.yml:224` 的 `cargo build --bin bwrap`；`:235-236` 先 `strip` 再取 sha256，写入 `CODEX_BWRAP_SHA256`（正对应上面的编译期校验） |
| DotSlash 产物条目 | `.github/dotslash-config.json:87-98` |
| 打包落位 | `scripts/codex_package/layout.py:68-69` 复制到 `<package>/codex-resources/bwrap`；`:148-150` 把它列为 Linux 包的**必需文件 + 可执行文件** |
| 安装器 | `scripts/install/install.sh:948-949`、`:975-977` 复制并 `chmod 0755`；`:1017` 校验 `codex-resources/bwrap` 可执行 |

Bazel 侧只做 smoke build，不产出发布物。

### 3.3 seccomp 过滤器是**黑名单**，不是白名单（E3）

> [!CAUTION]
> 本文第一版在「未覆盖」表里写的是「seccomp 过滤的系统调用**白名单**」——方向反了。`codex-rs/linux-sandbox/src/landlock.rs:282-285` 的 `SeccompFilter::new` 参数写得很清楚：
>
> ```rust
> SeccompAction::Allow,                     // default – allow
> SeccompAction::Errno(libc::EPERM as u32), // when rule matches – return EPERM
> ```
>
> 即**默认放行，命中规则才拒绝**（返回 `EPERM`）。

规则以**加法**添加，但写法有两种，不要说成「全部走 `deny_syscall()`」：

- **无条件拒绝**走 `deny_syscall()`（`codex-rs/linux-sandbox/src/landlock.rs:183-185`）——它做的就是 `rules.insert(nr, vec![])`，空规则向量表示无条件命中。`ptrace` / `process_vm_readv` / `io_uring_*` 以及 `Restricted` 模式下的一大批套接字调用都走这条。
- **带参数条件的规则**直接 `rules.insert(...)` 配合 `SeccompCondition`，不经过 `deny_syscall`（`codex-rs/linux-sandbox/src/landlock.rs:222-231`、`:232-268`、`:270-279`）。

**第 6 轮复算：全文件共 25 处生效的规则写入 = 19 处 `deny_syscall` + 6 处直接 `rules.insert`**（`:230`、`:231`、`:267`、`:268`、`:277`、`:278`）。复算命令：

```bash
grep -c "deny_syscall(&mut rules" codex-rs/linux-sandbox/src/landlock.rs   # 20，减去 :216 被注释的 SYS_recvfrom = 19
grep -c "rules.insert(libc::" codex-rs/linux-sandbox/src/landlock.rs      # 6
```

> **「19 处 `deny_syscall`」这个数字碰巧没变，但构成变了**——这是只对数字、不对集合的检查抓不到的典型。新增了 `SYS_process_vm_writev`（`:193`）与 3 条 `io_uring_*`（`:197-199`）。`io_uring` 那三条的注释说明了动机：它可以绕过 `socket()` 直接创建 `AF_VSOCK`，因此**在所有三种模式下都拒**。

被注释掉的那条 `SYS_recvfrom`（`:216`）仍在，注释说明放行它是为了让 `cargo clippy` 这类工具的 socketpair + 子进程管理能正常工作。

#### seccomp 有三种模式（第 6 轮从两种增至三种）

枚举定义在 `codex-rs/linux-sandbox/src/landlock.rs:100-104`；前两种由 `network_seccomp_mode()`（`:112-125`）按是否代理路由选择，第三种由调用点 `:56-64` 的 `.or_else()` 兜底产生：

| 模式 | 何时选用 | 套接字规则 |
| ---- | ---- | ---- |
| `NetworkSeccompMode::Restricted` | 网络受限、且未走代理路由 | `socket` / `socketpair` **仅放行 `AF_UNIX`**（`codex-rs/linux-sandbox/src/landlock.rs:222-231`），另外无条件拒绝 `connect` / `bind` / `listen` / `sendto` 等一整组 |
| `NetworkSeccompMode::ProxyRouted` | 存在受管代理、走代理路由 | `socket` **仅放行 `AF_INET` / `AF_INET6`**（用于连本地 TCP 网桥），`socketpair` **仅放行 `AF_UNIX`**（`codex-rs/linux-sandbox/src/landlock.rs:232-268`） |
| `NetworkSeccompMode::VmSocketRestricted` | **第 6 轮新增**：网络本可全开、但权限档非全盘写（`:56-64` 的兜底） | `socket` / `socketpair` **仅拒 `AF_VSOCK`**（`:270-279`）；其余一律放行 |

> [!CAUTION]
> **`VmSocketRestricted` 与另两种模式有一条实质差异，安全上必须知道：它不拒 `ptrace` / `process_vm_readv` / `process_vm_writev`。**
>
> `codex-rs/linux-sandbox/src/landlock.rs:190` 的 `if mode != VmSocketRestricted` 把这三条 deny 规则整体跳过了。也就是说，最低档 seccomp 只堵住 VM socket 这条「逃到宿主」的路，**不阻止同机进程间内存读写**。
>
> 该模式的存在理由写在 `:57-60` 的注释里：VM socket 能触达文件系统沙箱之外的宿主服务；在 WSL2 下它还能通过 interop socket 的别名启动 Windows 进程，**即使 `/run/WSL` 已被遮蔽**。

> [!NOTE]
> **`ProxyRouted` 对 `AF_UNIX` 的处理有一条反直觉的极性**：只有当 `managed_network.is_some_and(|c| c.dangerously_allow_all_unix_sockets)` 为真时，`AF_UNIX` 才被加进 deny 条件（`:243-250`）。即**该开关打开时 `socket(AF_UNIX)` 被拒，关闭时放行**——与名字给人的直觉相反。引用此处请直接照抄源码行，不要转述。

> [!NOTE]
> **历史修订**：本文更早一稿把两处套接字规则统一标成 `codex-rs/linux-sandbox/src/landlock.rs:250-251`——那两行其实是 `let filter = SeccompFilter::new(` 与 `rules,`，跟套接字规则无关（该构造现位于 `:282-285`）。

### 3.4 其他 Linux 特有文件

- `codex-rs/linux-sandbox/src/proxy_routing.rs` — 代理路由；`codex-rs/linux-sandbox/src/linux_run_main.rs:221-231` 在启用代理时会 `prepare_host_proxy_route_spec()` 并把 socket 目录追加进可读根
- `allow_network_for_proxy(enforce_managed_network: bool) -> bool`（在 `sandboxing` crate 中）——网络代理场景下的放行判定
- `codex-rs/linux-sandbox/src/linux_run_main_tests.rs` 对 `use_legacy_landlock` 的 true/false 两条路径都有覆盖（`:611-659`）

### 3.5 WSL 行为（E2/E3）

`codex-rs/linux-sandbox/README.md:26-51` 的「Current Behavior」额外覆盖了一条本文之前完全没提的平台差异：

- **WSL2**：走正常的 Linux bubblewrap 路径，无特殊处理。
- **WSL1**：**不支持 bubblewrap 沙箱**——它无法创建所需的 user namespace。Codex 的做法不是降级，而是**在调用 bwrap 之前就拒绝**那些会进入 bwrap 路径的沙箱化 shell 命令。落点是 `codex-rs/sandboxing/src/manager.rs:656-670` 的 `ensure_linux_bubblewrap_is_supported`：`is_wsl1 && requires_bubblewrap` 时返回 `SandboxTransformError::Wsl1UnsupportedForBubblewrap`。注意这里用的正是 §3.1 那个合成表达式——**判据 (a) 命中（全盘写权限档）的命令在 WSL1 上仍能运行**，因为它们本来就不需要 bwrap。

---

## 4. Windows：默认无沙箱，显式开启后走受限令牌 / 提权 / MXC 三条后端（E3）

> [!CAUTION]
> **本节上一版有一条高风险的安全语义错误，务必先读这一条。**
>
> 旧版写：「`windows_sandbox_uses_elevated_backend` = `proxy_enforced || matches!(sandbox_level, WindowsSandboxLevel::Elevated)`——**受管代理会强制走提权后端**，即使配置的是受限令牌」。该断言在 §4 与 §10 各复述了一遍。
>
> **`proxy_enforced` 这个参数已被整个删除。** `codex-rs/sandboxing/src/windows.rs:32-34` 现在的全部函数体是：
>
> ```rust
> pub fn windows_sandbox_uses_elevated_backend(sandbox_level: WindowsSandboxLevel) -> bool {
>     matches!(sandbox_level, WindowsSandboxLevel::Elevated)
> }
> ```
>
> 全部 7 个调用点（`codex-rs/core/src/exec.rs:679`、`codex-rs/core/src/sandboxing/mod.rs:145`、`codex-rs/exec-server/src/process_sandbox.rs:287`、`codex-rs/sandboxing/src/manager.rs:630`、`codex-rs/cli/src/doctor/sandbox.rs:130` 及 2 处测试）均只传 1 个参数。
>
> **正确表述：后端选择只看 `WindowsSandboxLevel`。** `proxy_enforced` 现在只作为独立参数传给 `create_windows_sandbox_command_args_for_permission_profile`（`codex-rs/sandboxing/src/manager.rs:673`），不再影响后端选择。

> [!IMPORTANT]
> 先记住 §1 的结论：**Windows 上默认没有沙箱**。但注意 §1 那条 CAUTION——**判据是 `SandboxType` 而非 `WindowsSandboxLevel`**，MXC 模式下 level 反而是 `Disabled`。本节描述的一切都要显式配置 `[windows].sandbox` 才会发生。

`codex-rs/sandboxing/src/windows.rs` 的公开函数（函数体已读，E3，行号为第 6 轮实测）：

| 函数 | 位置 | 语义 |
| ---- | ---- | ---- |
| `WindowsSandboxFilesystemOverrides`（struct） | `:24-30` | 覆盖项载体：read/write roots override、是否含平台默认可读根、额外的 deny-read / deny-write 路径（**第 6 轮行号未漂的唯一一条**） |
| `windows_sandbox_uses_elevated_backend` | `:32-34` | `matches!(sandbox_level, WindowsSandboxLevel::Elevated)`——见上方 CAUTION |
| `permission_profile_supports_windows_restricted_token_sandbox` | `:36-45` | 只有 `Managed` 且**非全盘写权限**的档位支持受限令牌；`Disabled` / `External` 一律 false |
| `unsupported_windows_restricted_token_sandbox_reason` | `:47-70` | 按 level 分派到两个 `resolve_*_overrides`，取其 `Err` 作为「不支持的原因」——即原因就是覆盖解析失败的错误 |
| `resolve_windows_restricted_token_filesystem_overrides` | `:72` | 受限令牌模式的文件系统覆盖解析 |
| `resolve_windows_elevated_filesystem_overrides` | `:213` | 提权模式的文件系统覆盖解析 |

**三条后端路径**（第 6 轮由两条增至三条）：

| 后端 | `SandboxType` | 选择条件 |
| ---- | ---- | ---- |
| 受限令牌（restricted token） | `WindowsRestrictedToken` | `[windows].sandbox = "unelevated"` |
| 提权（elevated） | `WindowsRestrictedToken` + `WindowsSandboxLevel::Elevated` | `[windows].sandbox = "elevated"`，由上表 `:32-34` 判定 |
| **MXC（第 6 轮新增）** | `WindowsMxc` | `[windows].sandbox = "mxc"`（`codex-rs/core/src/config/windows_sandbox_config.rs:48-50`）。在 `codex-rs/sandboxing/src/manager.rs:314-316` **短路返回**，不经 `get_platform_sandbox`；transform 走 `codex-rs/sandboxing/src/manager.rs:378-420` 的独立分支 |

MXC 的实现分布在新 crate `codex-rs/mxc-sandbox`（1,851 行，模块注释：「Native Windows MXC helper. Policy conversion is portable; execution requires a usable process security environment and never enters MXC's ACL fallbacks.」）与 `codex-rs/sandboxing/src/windows_mxc.rs`；另有随发布交付的常驻服务 `codex-rs/windows-sandbox-service`（5,261 行）。

独立 crate `codex-windows-sandbox`（28,227 行，目录名是 `codex-rs/windows-sandbox-rs`）承载主要实现；`codex-rs/sandboxing/src/lib.rs:23` 的 `pub use codex_windows_sandbox::WindowsSandboxProxySettingsMode;` 是一条**再导出**（把下游 crate 的类型转挂到 `codex-sandboxing` 的公开面上），不是本 crate 的定义。

### 4.1 Windows 的实际落点：direct-spawn 包装链（E3）

上表那些函数（`codex-rs/sandboxing/src/windows.rs`）全是「解析覆盖项」的纯函数。

**真正的沙箱化不在 `transform` 里完成**，而在 `transform_for_direct_spawn` 之后的包装步骤。调用链：

```
SandboxManager::transform_for_direct_spawn        codex-rs/sandboxing/src/manager.rs:443
   └─(cfg(windows))→ transform_for_direct_spawn_with_codex_home   :461（:460 是 #[cfg] 属性行）
          └─→ wrap_windows_sandbox_exec_request_for_direct_spawn  :482
```

（非 Windows 目标上 `transform_for_direct_spawn` 直接转调 `self.transform(request.transform)`，`codex-rs/sandboxing/src/manager.rs:454-457`。）

`wrap_windows_sandbox_exec_request_for_direct_spawn` 做四件事：

1. **换程序**：把原 program 交给 `codex_windows_sandbox::resolve_exe_for_launch`，得到 helper exe 并替换掉（`codex-rs/sandboxing/src/manager.rs:509-510`）。
2. **选后端**：`windows_sandbox_uses_elevated_backend(request.windows_sandbox_level)`（`codex-rs/sandboxing/src/manager.rs:630`，**第 6 轮已去掉 `proxy_enforced` 参数**），据此选 elevated 还是 restricted-token 的覆盖解析。
3. **重组命令**：把原命令整体塞进 helper 的参数里（`codex-rs/sandboxing/src/manager.rs:581-583`）。
4. **改回 `None` 并补环境**：`request.sandbox = SandboxType::None;` `request.arg0 = None;` 然后 `add_windows_sandbox_wrapper_setup_env(&mut request.env)`（`codex-rs/sandboxing/src/manager.rs:584-586`）。

> [!WARNING]
> **包装完成后 `request.sandbox` 被置回 `SandboxType::None`——这一点很反直觉。**
> 它不表示「不沙箱了」，而是表示**外层沙箱的职责已经交给 helper exe 承担**，spawn 侧不应再叠加一层。读 `SandboxExecRequest` 时看到 Windows 路径上 `sandbox == None`，不要据此断定命令未被沙箱化。

环境变量做了白名单收窄：`WINDOWS_SANDBOX_WRAPPER_SETUP_ENV_ALLOWLIST` = `&["USERNAME", "USERPROFILE"]`（`codex-rs/sandboxing/src/manager.rs:32`），只注入这两个。

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

**核心抽象是"变换"（transform）**：把一个普通命令变换成受沙箱约束的命令，而不是在执行时拦截（**Windows 的 direct-spawn 路径是例外——它在 `transform` 之后另有一层包装步骤，见 §4.1**）。这解释了 `create_seatbelt_command_args` 这类"构造命令参数"的 API 形状。

进程启动在 `codex-rs/sandboxing/src/spawn.rs`：`SpawnRequest`、`WindowsSandboxSpawnRequest`、`spawn_process`。

> [!IMPORTANT]
> **`SandboxExecRequest` 只应在「执行边界」构造。** `codex-rs/sandboxing/src/manager.rs:107-110` 的文档注释：
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

`codex-rs/sandboxing/src/manager.rs:76` 的 `with_managed_mitm_ca_readable_root(...)` 说明存在**受管 MITM CA 证书**场景——需要让沙箱内进程能读取企业 CA 包。这与 `codex-network-proxy`（17,064 行）相关。

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
      ↓ 失败时（旁注：以下两步都在【执行层】那次失败尝试的内部完成，不在 orchestrator）
      · is_likely_sandbox_denied(...) 启发式判定失败是否由沙箱拒绝导致
      · 判定为是 → 就地 record_*_sandbox_violation 记录，并产出 SandboxErr::Denied
      ↓ 错误冒泡回 orchestrator
【3) 解构已分类好的错误】orchestrator.rs:299 匹配 CodexErrorDetails::Sandbox(SandboxErr::Denied { .. })
      ↓ 是
【4) 升级重试】orchestrator.rs:333-451
   · tool.escalate_on_failure() 为 false → 不重试（:333）
   · 审批策略为 Never / OnRequest 时不做「去沙箱」重试（:345）
   · 否则构造 retry_reason，按需二次审批（:392-404，严格自动评审下必须重新过 Guardian）
   · retry_sandbox / retry_sandbox_requested / retry_codex_linux_sandbox_exe → SandboxAttempt（:442）
```

> [!IMPORTANT]
> **`is_likely_sandbox_denied` 与 `record_*_sandbox_violation` 都不在 orchestrator 里；本文上一稿把它们画进了 orchestrator 步骤，且次序颠倒。**
> `rg 'is_likely_sandbox_denied|record_.*sandbox_violation' codex-rs/core/src/tools/orchestrator.rs` **零命中**。两者都在**执行层**调用，发生在失败的那一次尝试**内部**，作用是*生产*出 `SandboxErr::Denied`；记录发生在重试**之前**，不是流程末尾。`codex-rs/core/src/tools/orchestrator.rs:299` 只是把已经分类好的错误解构出来。
>
> `codex-rs/sandboxing/src/denial.rs:11-12` 的文档注释把这个分工写死了：
> > "This predicate is intentionally side-effect free. **Callers that handle a denial should record it where the relevant audit context is available.**"
>
> 即判定是纯函数，记录由各自持有审计上下文的调用方完成。`codex-core` 与 `codex-exec-server` 中的全部调用点：
>
> | 调用点 | 场景 |
> | ---- | ---- |
> | `codex-rs/core/src/exec.rs:827` | 通用命令执行（`:829` 为记录） |
> | `codex-rs/core/src/unified_exec/process.rs:324` | unified exec 进程（`:326` 为记录） |
> | `codex-rs/core/src/tools/runtimes/apply_patch.rs:220` | apply_patch（`:226` 为记录） |
> | `codex-rs/core/src/tools/network_approval.rs:1078` | 网络违规（`record_network_sandbox_violation`） |
> | `codex-rs/exec-server/src/local_process.rs:1096` | **exec-server 本地进程**——只做判定并写进 `process.sandbox_denied`，记录在别处 |
>
> **第 6 轮变更**：穷举结果由 6 处降为 **5 处**。原表中的 `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs` 一行**两重失效**——该路径随 runtimes 目录重组已不存在 <!-- ref-exempt: 反例——正文说明该路径已不存在 -->（现为 `codex-rs/core/src/tools/runtimes/zsh_fork/unix_escalation.rs`，875 行），且新文件中对 `is_likely_sandbox_denied` / `record_*_sandbox_violation` **零命中**，即这条调用点被整体移除了。
>
> 另：`codex-rs/sandboxing/src/denial.rs` 新增了 `is_likely_executor_managed_sandbox_denied`（经 `codex-rs/sandboxing/src/lib.rs:24` 导出），本文未展开。

**「no re-approval thanks to caching」的边界**：普通情况下重试不再打扰用户（审批结果被缓存），但 `codex-rs/core/src/tools/orchestrator.rs:391-395` 有例外注释——「retrying without the sandbox requires a fresh guardian review」，即**去掉沙箱的重试在严格自动评审模式下必须重新评审**。

### Guardian 自动评审后端

> [!CAUTION]
> **第 6 轮：本小节上一版列举的 7 个锚点全部失效**，审批评审后端已被整体重构。以下三个符号**全仓零命中**，按它们 grep 只会白费力气：`ApprovalReviewer`（枚举）、`resolve_tool_apporval()`、`strict_auto_review_enabled_for_turn()`。

`codex-rs/core/src/guardian/` 是一个独立的审批评审后端。**重构后的形态是「一个 bool + 一个上下文结构体」，不再是「枚举选 reviewer」**：

| 位置 | 内容 |
| ---- | ---- |
| `codex-rs/core/src/tools/orchestrator.rs:136-140` | `strict_auto_review` 由 `session.active_turn_context_and_strict_auto_review()` 取出，**折叠成一个 `bool`** |
| `codex-rs/core/src/tools/orchestrator.rs:176-186`、`:203-213` | 该 bool 随 `ApprovalContext { .., strict_auto_review, .. }` 传给 `session.request_approval(action, approval_ctx)`（调用在 `:187-191`、`:214-218`） |
| `codex-rs/core/src/tools/approvals.rs:426-430` | 消费侧的 `enum ApprovalResolutionSource { Hook, Guardian, User }`——**三变体，且 `Hook` 是第 6 轮新增的** |
| `codex-rs/protocol/src/config_types.rs:183-190` | 配置面的 `enum ApprovalsReviewer { User, AutoReview }`（`guardian_subagent` 是 `AutoReview` 的 serde alias）。**这是配置面类型，不是编排面类型，两者别混** |
| `codex-rs/core/src/guardian/` 目录 | review、review_session、approval_request、prompt、decision、coverage、feedback、input_budget、request_budget、reviewer_config、review_session_context、review_session_setup、review_request、runtime 共 14 个 `.rs` + `snapshots/`（E1） |

**目录层的三处变化**（E1）：原有的 `codex-rs/core/src/guardian/metrics.rs` **已删除且无同名替代**<!-- ref-exempt: 反例——正文说明该路径已不存在 -->；原有的 `codex-rs/core/src/guardian/policy.md` 与 `policy_template.md` **迁至 `codex-rs/prompts/templates/guardian/policy.md` 与 `codex-rs/prompts/templates/guardian/policy_template.md`**<!-- ref-exempt: 反例——正文说明旧路径已不存在 -->（该目录另含 `classifier_instructions.md`、`node_repl_policy.md`）；新增 decision、coverage、feedback、input_budget、request_budget、reviewer_config、runtime 等一批本文未展开的子系统，其中 input_budget 与 request_budget 构成一套**双预算**机制。

`codex-rs/core/src/guardian/mod.rs` 现在导出的是 `decide_approval`、`spawn_approval_decision`（`:48-49`）、`check_pending_guardian_input` / `finalize_guardian_input`（`:12-13`）、`check_guardian_prompt_budget` / `ExhaustedReviewBudget`（`:15-16`）、`resolve_review_model`（`:21`）等。**上一版列举的 `review_approval_request` 与 `guardian_timeout_message` 都不是 mod.rs 的导出**——前者只是 `codex-rs/core/src/guardian/tests.rs` 里的测试辅助函数，后者全仓零命中。

> 这意味着上一版据此推出的「**有超时消息**，与 `ReviewDecision::TimedOut` 对应」这条关联**失去了证据**。`ReviewDecision::TimedOut` 变体本身仍在（见 [`core_agent_loop.md`](./core_agent_loop.md) §5.3），但它与 Guardian 的连接点需要重新取证，本轮未做。

`SandboxPolicy` 的四个变体与字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §5.2；运行时的 `PermissionProfile` 见本文 §1.5。

---

## 8. 相关的执行安全 crate

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-execpolicy` | 2,975 | 执行策略；`codex execpolicy` 为 hidden 子命令 |
| `codex-shell-command` | 10,155 | shell 命令解析与**危险命令判定**（黑名单，见下方 CAUTION） |
| `codex-shell-escalation` | 2,282 | 权限提升审批 |
| `codex-process-hardening` | 193 | 进程加固 |
| `codex-network-proxy` | 29,510 | 网络代理（与 MITM CA 相关） |
| `codex-mxc-sandbox` | 1,851 | **第 6 轮新增**：原生 Windows MXC 辅助，见 §4 |
| `codex-windows-sandbox-service` | 5,261 | **第 6 轮新增**：Windows 沙箱常驻服务端，随发布交付 |
| `codex-linux-sandbox` | 11,817 | Linux 沙箱 helper |
| `codex-rs/bwrap/` | — | 随产品分发的 bubblewrap |
| `codex-rs/exec-server/` + `codex-rs/exec-server-protocol/` | — | 执行边界服务与其协议，见本文 §5 |

> [!CAUTION]
> **known-safe 命令白名单已整体退役——这是本轮最需要重读的一条。**
>
> 上游提交 `942af8447b`「Retire the untrusted approval policy (#39630)」删除了整个 `codex-rs/shell-command/src/command_safety/is_safe_command.rs` 模块<!-- ref-exempt: 反例——正文说明该路径已不存在 -->。复算：
>
> ```bash
> grep -rn "is_known_safe_command\|is_safe_command" codex-rs/ | wc -l   # 0
> ls codex-rs/shell-command/src/command_safety/
> # fixtures  is_dangerous_command.rs  mod.rs  powershell_parser.ps1
> # powershell_parser.rs  powershell_tree_sitter.rs  powershell_tree_sitter_tests.rs
> # windows_dangerous_commands.rs
> ```
>
> **判定极性翻转了**：从「列举什么是安全的」变成「列举什么是危险的」，现只剩 `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` 一条黑名单通路（`dangerous_command_match` / `dangerous_command_match_for_platform` / `dangerous_powershell_words_match`），外加 Windows 专用的 `windows_dangerous_commands.rs`。
>
> `AskForApproval::UnlessTrusted` 变体**仍在** `codex-rs/protocol/src/protocol.rs:991`，但其文档注释已重写为：
>
> ```rust
> /// Internal policy for projects marked untrusted. Commands require
> /// approval unless an explicit exec policy rule allows them.
> ```
>
> 即由白名单改判为 **execpolicy 规则制**。
>
> > **本文上一版在这里犯了一个会二次误导的错。** 旧版整块 WARNING 是在教读者「`is_safe_command()` 这个函数不存在，真名是 `is_known_safe_command()`，按错名字 grep 会命中注释而找不到定义，**容易误以为函数被删了**」——而真相恰恰是**函数真的被删了**。旧版还引用了两处「残留旧名的注释」（`codex-rs/protocol/src/protocol.rs:919` 与 `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs:362`），第 6 轮实测：前者的注释已按上面改写，后者的**路径本身都不存在了** <!-- ref-exempt: 反例——正文说明该旧路径已不存在 -->（runtimes 重组为 `codex-rs/core/src/tools/runtimes/zsh_fork/unix_escalation.rs`，且其中对 `is_safe_command` 零命中）。
> >
> > 这是「文档在一个已消失的机制上继续做精细考据」的典型形态——考据越细，误导越深。

`codex-rs/core/src/` 侧的对应文件：`codex-rs/core/src/exec.rs`、`codex-rs/core/src/exec_env.rs`、`codex-rs/core/src/exec_policy.rs`、`codex-rs/core/src/exec_policy_windows_tests.rs`（Windows 有独立测试文件，说明平台差异显著）。

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
| bwrap 内外两层拼接的**具体 argv 内容**（外层 `run_bwrap_with_proc_fallback` 的 bind 参数、内层 `build_inner_seccomp_command` 的 re-exec 参数） | E3（调用位置与拼接次序已确认：`build_inner_seccomp_command` 在 `codex-rs/linux-sandbox/src/linux_run_main.rs:232` 调用，`run_bwrap_with_proc_fallback` 在 `:240`；未展开的是两个函数各自构造的 argv 明细） | `codex-rs/linux-sandbox/src/linux_run_main.rs:230-250` |
| `dangerous_command_match_for_platform()` 内部的黑名单规则（第 6 轮：旧的 known-safe 白名单已整体退役，见 §8） | E1 | `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` |
| execpolicy 的策略语言与规则格式 | E1 | `codex-rs/execpolicy/` |
| `codex-rs/sandboxing/src/policy_transforms.rs` 中 merge/intersect 的具体合成规则 | E1 | `codex-rs/sandboxing/src/policy_transforms.rs`（注意 intersect 第 6 轮已改名为 `intersect_permission_profiles_with_context`） |
| Guardian 评审的提示词与判定策略 | E1 | `codex-rs/prompts/templates/guardian/policy.md`、`codex-rs/core/src/guardian/prompt.rs` |
| exec-server 协议的完整方法面 | E1 | `codex-rs/exec-server-protocol/src/` |
| MITM CA 与网络代理的完整链路 | E1 | `codex-rs/network-proxy/`（29,510 行） |

> **已从本表移除的三项**（早先列为未验证，现已在正文给出 E3 结论）：
> - 「Landlock/seccomp 与 bwrap 的选择条件」→ 见 §3.1，是**两道**判据：全盘写权限早退 + `use_legacy_landlock`
> - 「审批与沙箱在编排层的实际次序」→ 见 §7，源码注释直接写明
> - 「Windows 后端路径的切换条件」→ 见 §4。第 6 轮后端由两条增至**三条**（新增 MXC）；受限令牌与提权之间的切换是一行布尔表达式 `windows_sandbox_uses_elevated_backend`（`codex-rs/sandboxing/src/windows.rs:32-34`）= `matches!(sandbox_level, WindowsSandboxLevel::Elevated)`，入口在 `codex-rs/sandboxing/src/manager.rs:630`。**`proxy_enforced` 参数已被删除，「受管代理强制走提权后端」这条旧结论不再成立。** MXC 则在 `codex-rs/sandboxing/src/manager.rs:314-316` 更早地短路。

---

## 11. 相关文档

### 仓库内的一手材料

- **`codex-rs/linux-sandbox/README.md`（E2，权威）** —— 本文 §3 的结论在 `:26-51` 的「Current Behavior」里被逐条写明，另外还覆盖了本文之外的两点：**WSL1/WSL2 行为**（已补入 §3.5）与 **`--argv0` 老版本兼容路径**（见 §3.2）。改动 Linux 沙箱行为时应同步更新这份 README。
- `codex-rs/vendor/bubblewrap/NEWS.md` —— 上游 bubblewrap 的变更记录，判断 vendored 版本是否需要跟进 CVE 时看这里。

> [!WARNING]
> **有一条死链要提防。** `codex-rs/sandboxing/src/landlock.rs:21` 的注释把读者引向一份不存在的文档：
>
> > "See `docs/linux_sandbox.md` for the Linux semantics." <!-- ref-exempt: 这条路径是反例，本就不存在于仓库中 -->
>
> 该文件在仓库中**不存在**（全库无 `linux_sandbox*.md`；`docs/sandbox.md` 只有 3 行且仅做外链）。顺着这条注释找文档会扑空，正确的替代入口是上面的 `codex-rs/linux-sandbox/README.md`。

### 本体系其他文档

- [智能体核心循环](./core_agent_loop.md) — 审批与沙箱策略类型
- [架构总览](./architecture_overview.md) — 沙箱在整体架构中的位置
- [Crate 地图](./crate_map.md) §3.4 — 沙箱相关 8 个 crate
- [配置体系](./config_system.md) — 沙箱策略的配置入口
