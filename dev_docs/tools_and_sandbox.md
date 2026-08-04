---
title: Codex 工具执行与沙箱隔离
summary: 描述 codex-sandboxing 的四种沙箱类型与平台选择逻辑、运行时权限类型 PermissionProfile 与兼容层 SandboxPolicy、macOS Seatbelt 的三段式 sbpl 策略拼接、Linux 沙箱的两道判据（全盘写权限早退与 use_legacy_landlock）与 bwrap 加网络门控 seccomp 的默认路径、vendored bubblewrap 源码与随发布捆绑链路、Windows 默认无沙箱及 direct-spawn 包装的实际落点、审批与沙箱的升级重试次序、沙箱违规检测在执行层的归属，以及 CODEX_SANDBOX 环境变量的绝对红线。
keywords: codex | sandbox | seatbelt | bwrap | bubblewrap-vendor | seccomp | landlock-legacy | permission-profile | windows-restricted-token | wsl1 | execpolicy
scope: codex-rs/sandboxing 及其平台实现 crate
related_files: codex-rs/sandboxing/src/manager.rs | codex-rs/sandboxing/src/lib.rs | codex-rs/sandboxing/src/policy_transforms.rs | codex-rs/sandboxing/src/windows.rs | codex-rs/linux-sandbox/src/landlock.rs | codex-rs/linux-sandbox/src/linux_run_main.rs | codex-rs/linux-sandbox/src/launcher.rs | codex-rs/linux-sandbox/src/bundled_bwrap.rs | codex-rs/linux-sandbox/README.md | codex-rs/bwrap/build.rs | codex-rs/features/src/lib.rs | codex-rs/protocol/src/protocol.rs | codex-rs/protocol/src/models.rs | codex-rs/core/src/tools/orchestrator.rs | codex-rs/shell-command/src/command_safety/is_safe_command.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-05
---

# 工具执行与沙箱隔离

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-rs/sandboxing`（6,882 行）+ 平台实现 crate
> **证据等级**: 类型定义、平台选择逻辑、Linux 三条出口分支（全盘写权限早退 / bwrap 默认 / legacy Landlock）、seccomp 与 `no_new_privs` 的网络门控、Windows direct-spawn 包装链、审批与沙箱次序为 E3；目录与文件清单、vendor 树的「未见 Codex 侧改动」判断为 E1/E2；`.sbpl` 策略文件的具体规则内容未逐条解读；Bazel 相关结论未做构建级验证

> [!WARNING]
> **本文经过两轮更正，相关段落都保留了「原稿写错了什么」的说明，便于对照旧版笔记。**
>
> 第一版的四处事实性错误：Linux 沙箱的主备关系、bwrap 与 Landlock 的切换开关位置、seccomp 过滤器的黑/白名单方向、以及 `is_safe_command()` 这个不存在的函数名。
>
> 本次（2026-08-05）更正的重点：Linux 主/备切换实际有**两道**判据而非一道（§3.1）；seccomp 与 `no_new_privs` 都被**网络策略门控**，不是无条件默认（§3）；socket 规则的行号与**两种 seccomp 模式**（§3.3）；Seatbelt 三段策略的**各自入场条件**（§2）；**Windows 默认无沙箱**及 direct-spawn 包装链（§4、§4.1）；沙箱违规判定与记录在**执行层**而非 orchestrator（§7）；补齐了此前完全缺失的 `codex-rs/vendor/bubblewrap/`（§3.2）与 WSL1 行为（§3.5）。

---

## 0. 先读这一节：绝对红线

> [!CAUTION]
> **`AGENTS.md` 顶部规则列表规定：禁止新增或修改任何与 `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR`、`CODEX_SANDBOX_ENV_VAR` 相关的代码**（grep `Never add or modify any code related to`）。
>
> **AGENTS.md 原文**（`AGENTS.md:8`）限定的对象是 *code*：不要新增或修改任何与这两个环境变量相关的**代码**，原文本身未写出「无例外」这样的例外条款。
>
> **本文的建议**（比原文更保守，安全上是对的）：把它当成没有例外的红线——即使你认为改动是安全的、即使是重构、即使只是改注释，都不要碰。本文档也不复述这两个环境变量的取值与判定逻辑。

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

对应的指标标签（`codex-rs/sandboxing/src/manager.rs:42-52`）：`none` / `seatbelt` / `seccomp` / `windows_sandbox`。

### 平台选择逻辑（E3，`codex-rs/sandboxing/src/manager.rs:60-75`）

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
| Windows | `WindowsRestrictedToken` **或 `None`** | **默认 `None`**（三层默认全指向关）。要拿到 `WindowsRestrictedToken` 必须显式配置，见下方说明 |
| 其他 | `None` | 无沙箱 |

> [!IMPORTANT]
> **Windows 的默认值就是「无沙箱」。** 三层默认互相印证：
>
> 1. `WindowsSandboxLevel` 的 `#[default]` 变体是 `Disabled`（`codex-rs/protocol/src/config_types.rs:279-284`）；
> 2. 未配置 `windows_sandbox_mode` 时，配置装载走 `None => WindowsSandboxLevel::Disabled`（`codex-rs/core/src/config/mod.rs:3381-3385`）；
> 3. `codex-rs/sandboxing/src/manager.rs:280` 传给 `get_platform_sandbox` 的实参是 `windows_sandbox_level != WindowsSandboxLevel::Disabled`——`Disabled` 直接落到 `None` 分支。
>
> 另外两个相关 feature（`experimental_windows_sandbox` / `elevated_windows_sandbox`）在 `codex-rs/features/src/lib.rs:1050-1061` 都是 `Stage::Removed` + `default_enabled: false`。

> [!WARNING]
> **不要把上表读成「macOS/Linux 一定有沙箱」。** `get_platform_sandbox` 只回答「本平台能提供哪种沙箱实现」，它不是入口。真正的入口是 `SandboxManager::select_initial`（`codex-rs/sandboxing/src/manager.rs:272`），它先调 `should_sandbox`（`codex-rs/sandboxing/src/manager.rs:289`），返回 false 时**直接给 `SandboxType::None`**，根本不问平台：
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

### 沙箱偏好（`codex-rs/sandboxing/src/manager.rs:54`）

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
| `normalize_additional_permissions` | `:19` | 归一化附加权限声明 |
| `merge_permission_profiles` | `:72` | **并集**合成（放宽） |
| `intersect_permission_profiles` | `:126` | **交集**合成（收紧） |
| `effective_file_system_sandbox_policy` | `:459` | 求有效文件系统策略 |
| `effective_network_sandbox_policy` | `:492` | 求有效网络策略 |
| `effective_permission_profile` | `:507` | 求有效 profile |
| `should_require_platform_sandbox` | `:523` | `Auto` 偏好下是否需要平台沙箱 |

`codex-rs/core/src/tools/handlers/mod.rs:38-40` 同时导入了 `intersect_permission_profiles`、`merge_permission_profiles`、`normalize_additional_permissions`——说明工具侧的「附加权限」请求既有放宽也有收紧路径。

`SandboxPolicy` 四个变体的字段语义见 [`core_agent_loop.md`](./core_agent_loop.md) §5.2。

---

## 2. macOS：Seatbelt（E3）

### 三份 sbpl 策略文件

`codex-rs/sandboxing/src/seatbelt.rs:21-24` 通过 `include_str!` 内嵌三份策略：

| 常量 | 文件 | 何时选用 |
| ---- | ---- | ---- |
| `MACOS_SEATBELT_BASE_POLICY` | `codex-rs/sandboxing/src/seatbelt_base_policy.sbpl` | **恒含**——永远是拼接结果的第一段 |
| `MACOS_SEATBELT_NETWORK_POLICY` | `codex-rs/sandboxing/src/seatbelt_network_policy.sbpl` | **条件叠加**：只在网络被放行（回环代理或全网）时进入拼接。该常量只出现在 `codex-rs/sandboxing/src/seatbelt.rs:309` 与 `:332` 两个放行分支；网络被拒时 `dynamic_network_policy_for_network` 返回 `String::new()`（`:333-334`），这一段等于空 |
| （受限只读平台默认）`MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS` | `codex-rs/sandboxing/src/restricted_read_only_platform_defaults.sbpl` | **条件追加**：仅当 `file_system_sandbox_policy.include_platform_defaults()` 为真时 `push` 到末尾（`codex-rs/sandboxing/src/seatbelt.rs:749-751`）。该判定 = 非全盘可读 **且** `kind == Restricted` **且** entries 中存在可读的 `Special{Minimal}` 条目（`codex-rs/protocol/src/permissions.rs:688-699`） |

> [!IMPORTANT]
> 这三份 `.sbpl` 是通过 `include_str!` 在**编译期**读入的。按 AGENTS.md 顶部规则列表（grep `Bazel does not automatically make source-tree files available`），这类编译期文件读取必须在 `BUILD.bazel` 中配置 `compile_data`（或 `build_script_data` / test data），否则 **Cargo 能过而 Bazel 会失败**。改动这些文件或新增同类文件时务必注意。
>
> **注意**：「Cargo 能过而 Bazel 会失败」这句是 AGENTS.md 规则的转述，**本文未做构建级验证**（没有跑过 Bazel），仅为 E2。

### 命令构造入口

```rust
// seatbelt.rs:611
pub struct CreateSeatbeltCommandArgsParams<'a> { ... }

// seatbelt.rs:623
pub fn create_seatbelt_command_args(...);
```

最终交给 `sandbox-exec` 的策略由 `codex-rs/sandboxing/src/seatbelt.rs:741-750` 拼成：**基础段恒含 + 网络段条件叠加 + 平台默认段条件追加**（中间还夹着按权限档动态生成的 read / write / deny-read 段）。三段各有各的入场条件，见上表——不要读成「固定两份拼在一起」。

网络访问因此是**叠加**上去的独立维度，与 `SandboxPolicy` 中 `network_access` 默认为 `false` 的设计一致。

---

## 3. Linux：bwrap（需要文件系统隔离时的默认）+ 网络门控的 seccomp / no_new_privs（E3）

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
| **bubblewrap（bwrap）** | 文件系统隔离（mount namespace） | **需要文件系统隔离时的默认路径**（全盘写权限档会整体跳过，见 §3.1） | `codex-rs/linux-sandbox/src/bwrap.rs`（helper 侧 argv 构造与执行）+ `codex-rs/sandboxing/src/bwrap.rs`（系统 bwrap 查找与启动告警，职责不同，别混）/ `codex-rs/linux-sandbox/src/bundled_bwrap.rs` / `codex-rs/linux-sandbox/src/bazel_bwrap.rs`、`codex-rs/bwrap/` crate |
| **seccomp** | 系统调用过滤 | **网络受限或受管代理时**安装，在 bwrap 内层生效——**不是无条件默认**；门控逻辑见 `codex-rs/linux-sandbox/src/landlock.rs:96-117` | seccompiler crate（过滤器构造用到 BpfProgram、SeccompAction） |
| **`no_new_privs`** | 阻止提权 | **仅当需要 seccomp 或走 legacy Landlock 时**设置；默认路径上因网络受限而连带生效 | 内核原语（`codex-rs/linux-sandbox/src/landlock.rs:57-65`） |
| **Landlock（`AccessFs`、`Ruleset`）** | 文件系统访问控制 | **遗留/备份**，默认不启用 | `landlock` crate（`codex-rs/linux-sandbox/Cargo.toml:28`，位于 `[target.'cfg(target_os = "linux")'.dependencies]`，是**生产依赖而非 dev 依赖**） |

> [!IMPORTANT]
> **seccomp 与 `no_new_privs` 都被网络策略门控，不要读成无条件三件套。**
>
> - seccomp 在这里是一个**网络导向**的过滤器。是否安装由 `should_install_network_seccomp`（`codex-rs/linux-sandbox/src/landlock.rs:96-103`）决定：`!network_sandbox_policy.is_enabled() || allow_network_for_proxy`——即**只在网络被限制、或存在受管代理时**才装。反证测试 `codex-rs/linux-sandbox/src/landlock.rs:336-346` 的 `full_network_without_managed_proxy_skips_network_seccomp_mode` 断言这种情况下返回 `None`。
> - `no_new_privs` 的条件更严：`if network_seccomp_mode.is_some() || (apply_landlock_fs && !file_system_sandbox_policy.has_full_disk_write_access())`（`codex-rs/linux-sandbox/src/landlock.rs:61-64`）。上方注释解释了为什么不无条件设置——`PR_SET_NO_NEW_PRIVS` 会阻断 setuid 提权，而**很多 bwrap 部署依赖 setuid**。
>
> 结论：在最常见的「网络受限」权限档上两者确实都生效，但那是网络策略带来的**连带效果**，不是路径本身的固定组成。

### 3.1 主/备切换：两道判据，不止 `use_legacy_landlock`（E3）

> [!NOTE]
> 本文第一版把这条标为「未验证（E1）」并让读者去看 `codex-rs/linux-sandbox/src/launcher.rs`——**指错了文件**。`codex-rs/linux-sandbox/src/launcher.rs` 只在「系统 bwrap」与「随产品分发的 bwrap」之间选（`preferred_bwrap_launcher()`，`codex-rs/linux-sandbox/src/launcher.rs:51`，被 `:37` 与 `:102` 调用），跟 Landlock 毫无关系。
>
> 第二版把开关简化成「真正的开关是 `use_legacy_landlock`」，**也不完整**——它漏掉了在此之前的一条无条件早退。

`run_main()` 里决定走哪条路，实际有**两道判据**：

**判据 (a)：全盘写权限 + 无受管代理 → bwrap 被整体跳过。**
在到达 `use_legacy_landlock` 判断之前，`codex-rs/linux-sandbox/src/linux_run_main.rs:204-215` 有一条无条件早退：

```rust
if file_system_sandbox_policy.has_full_disk_write_access() && !allow_network_for_proxy {
    // 只做进程内约束（不套 Landlock 文件系统规则），然后直接 exec
    apply_permission_profile_to_current_thread(..., /*apply_landlock_fs*/ false, ...);
    exec_or_panic(command);   // 在 :217 的分支之前 return
}
```

也就是说，`danger-full-access` 一类权限档**根本不进 bwrap**，这与 `use_legacy_landlock` 的取值无关。

**判据 (b)：确实需要文件系统隔离时，才轮到 `use_legacy_landlock` 选路。**
`codex-rs/linux-sandbox/src/linux_run_main.rs:217` 的 `if !use_legacy_landlock { ... }` 决定走 bwrap 默认路径，还是落到其后的 legacy Landlock 路径。

**两条判据在编排侧被合成一个表达式**：`codex-rs/sandboxing/src/manager.rs:663-664`

```rust
let requires_bubblewrap = allow_network_for_proxy
    || (!use_legacy_landlock && !file_system_sandbox_policy.has_full_disk_write_access());
```

判据 (b) 的开关是 **`use_legacy_landlock`**：

| 层 | 形态 | 位置 |
| ---- | ---- | ---- |
| 配置 | `[features].use_legacy_landlock` | `codex-rs/features/src/lib.rs:404`（读取器）、`:1040`（键定义） |
| CLI | `--use-legacy-landlock`，`hide = true`，`default_value_t = false` | `codex-rs/linux-sandbox/src/linux_run_main.rs:110-111` |
| 早退（判据 a，**先于开关**） | `if has_full_disk_write_access() && !allow_network_for_proxy { ... exec_or_panic }` | `codex-rs/linux-sandbox/src/linux_run_main.rs:204-215` |
| 分支（判据 b） | `if !use_legacy_landlock { ... }` | `codex-rs/linux-sandbox/src/linux_run_main.rs:217` |
| 合成表达式 | `requires_bubblewrap` | `codex-rs/sandboxing/src/manager.rs:663-664` |
| 传递 | `turn_ctx.config.features.use_legacy_landlock()` | `codex-rs/core/src/tools/orchestrator.rs:254` |

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
> 本文第一版在「未覆盖」表里写的是「seccomp 过滤的系统调用**白名单**」——方向反了。`codex-rs/linux-sandbox/src/landlock.rs:250-253` 的 `SeccompFilter::new` 参数写得很清楚：
>
> ```rust
> SeccompAction::Allow,                     // default – allow
> SeccompAction::Errno(libc::EPERM as u32), // when rule matches – return EPERM
> ```
>
> 即**默认放行，命中规则才拒绝**（返回 `EPERM`）。

规则以**加法**添加，但写法有两种，不要说成「全部走 `deny_syscall()`」：

- **无条件拒绝**走 `deny_syscall()`（`codex-rs/linux-sandbox/src/landlock.rs:172-174`）——它做的就是 `rules.insert(nr, vec![])`，空规则向量表示无条件命中。`ptrace` / `process_vm_readv` / `io_uring_*` 以及 `Restricted` 模式下的一大批套接字调用都走这条。
- **带参数条件的规则**直接 `rules.insert(...)` 配合 `SeccompCondition`，不经过 `deny_syscall`（`codex-rs/linux-sandbox/src/landlock.rs:208-216`、`:225-246`）。全文件共 23 处生效的规则写入：19 处走 `deny_syscall`（另有 1 处 `SYS_recvfrom` 被注释掉，注释说明放行它是为了让 `cargo clippy` 这类工具的 socketpair + 子进程管理能正常工作），4 处是直接 `rules.insert` —— `:215`、`:216`、`:245`、`:246`。

#### seccomp 有两种模式

由 `network_seccomp_mode()`（`codex-rs/linux-sandbox/src/landlock.rs:105-117`）按是否代理路由选择：

| 模式 | 何时选用 | 套接字规则 |
| ---- | ---- | ---- |
| `NetworkSeccompMode::Restricted` | 网络受限、且未走代理路由 | `socket` / `socketpair` **仅放行 `AF_UNIX`**（`codex-rs/linux-sandbox/src/landlock.rs:208-216`），另外无条件拒绝 `connect` / `bind` / `listen` / `sendto` 等一整组 |
| `NetworkSeccompMode::ProxyRouted` | 存在受管代理、走代理路由 | `socket` **仅放行 `AF_INET` / `AF_INET6`**（用于连本地 TCP 网桥，连 `AF_UNIX` 也一并拒掉），`socketpair` **仅放行 `AF_UNIX`**（进程内 IPC，无法穿出沙箱）（`codex-rs/linux-sandbox/src/landlock.rs:225-246`） |

> [!NOTE]
> 本文上一稿把这两处规则统一标成 `codex-rs/linux-sandbox/src/landlock.rs:250-251`——**那两行其实是 `let filter = SeccompFilter::new(` 与 `rules,`**，跟套接字规则无关。正确位置是上表的 `:215-216` 与 `:245-246`。

### 3.4 其他 Linux 特有文件

- `codex-rs/linux-sandbox/src/proxy_routing.rs` — 代理路由；`codex-rs/linux-sandbox/src/linux_run_main.rs:221-231` 在启用代理时会 `prepare_host_proxy_route_spec()` 并把 socket 目录追加进可读根
- `allow_network_for_proxy(enforce_managed_network: bool) -> bool`（在 `sandboxing` crate 中）——网络代理场景下的放行判定
- `codex-rs/linux-sandbox/src/linux_run_main_tests.rs` 对 `use_legacy_landlock` 的 true/false 两条路径都有覆盖（`:611-659`）

### 3.5 WSL 行为（E2/E3）

`codex-rs/linux-sandbox/README.md:26-51` 的「Current Behavior」额外覆盖了一条本文之前完全没提的平台差异：

- **WSL2**：走正常的 Linux bubblewrap 路径，无特殊处理。
- **WSL1**：**不支持 bubblewrap 沙箱**——它无法创建所需的 user namespace。Codex 的做法不是降级，而是**在调用 bwrap 之前就拒绝**那些会进入 bwrap 路径的沙箱化 shell 命令。落点是 `codex-rs/sandboxing/src/manager.rs:656-670` 的 `ensure_linux_bubblewrap_is_supported`：`is_wsl1 && requires_bubblewrap` 时返回 `SandboxTransformError::Wsl1UnsupportedForBubblewrap`。注意这里用的正是 §3.1 那个合成表达式——**判据 (a) 命中（全盘写权限档）的命令在 WSL1 上仍能运行**，因为它们本来就不需要 bwrap。

---

## 4. Windows：默认无沙箱，显式开启后走受限令牌 / 提权两条后端（E3）

> [!IMPORTANT]
> 先记住 §1 的结论：**Windows 上默认没有沙箱**（`WindowsSandboxLevel` 默认 `Disabled`）。本节描述的一切都要显式配置 `windows_sandbox_mode` 才会发生。

`codex-rs/sandboxing/src/windows.rs` 的公开函数（函数体已读，E3）：

| 函数 | 位置 | 语义 |
| ---- | ---- | ---- |
| `WindowsSandboxFilesystemOverrides`（struct） | `:24-30` | 覆盖项载体：read/write roots override、是否含平台默认可读根、额外的 deny-read / deny-write 路径 |
| `windows_sandbox_uses_elevated_backend` | `:32-40` | `proxy_enforced \|\| matches!(sandbox_level, WindowsSandboxLevel::Elevated)`——**受管代理会强制走提权后端**，即使配置的是受限令牌 |
| `permission_profile_supports_windows_restricted_token_sandbox` | `:42-51` | 只有 `Managed` 且**非全盘写权限**的档位支持受限令牌；`Disabled` / `External` 一律 false |
| `unsupported_windows_restricted_token_sandbox_reason` | `:53-76` | 按 level 分派到两个 `resolve_*_overrides`，取其 `Err` 作为「不支持的原因」——即原因就是覆盖解析失败的错误 |
| `resolve_windows_restricted_token_filesystem_overrides` | `:78` | 受限令牌模式的文件系统覆盖解析 |
| `resolve_windows_elevated_filesystem_overrides` | `:219` | 提权模式的文件系统覆盖解析 |

**两条后端路径**：受限令牌（restricted token）与提权（elevated），各有独立的文件系统覆盖解析。切换条件就是上表 `:32-40` 那一行布尔表达式，入口在 `codex-rs/sandboxing/src/manager.rs:527-528`。

独立 crate `codex-windows-sandbox`（19,173 行）承载主要实现；`codex-rs/sandboxing/src/lib.rs:17` 的 `pub use codex_windows_sandbox::WindowsSandboxProxySettingsMode;` 是一条**再导出**（把下游 crate 的类型转挂到 `codex-sandboxing` 的公开面上），不是本 crate 的定义。

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
2. **选后端**：`windows_sandbox_uses_elevated_backend(request.windows_sandbox_level, proxy_enforced)`（`codex-rs/sandboxing/src/manager.rs:527-528`），据此选 elevated 还是 restricted-token 的覆盖解析。
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
> | `codex-rs/core/src/exec.rs:817-818` | 通用命令执行（`:817-822` 是完整的判定 + 记录段） |
> | `codex-rs/core/src/unified_exec/process.rs:319-321` | unified exec 进程 |
> | `codex-rs/core/src/tools/runtimes/apply_patch.rs:262-263` | apply_patch |
> | `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs:1064-1065` | Unix 权限提升路径 |
> | `codex-rs/core/src/tools/network_approval.rs:1051` | 网络违规（`record_network_sandbox_violation`） |
> | `codex-rs/exec-server/src/local_process.rs:950` | **exec-server 本地进程**——只做判定并写进 `process.sandbox_denied`，记录在别处 |

**「no re-approval thanks to caching」的边界**：普通情况下重试不再打扰用户（审批结果被缓存），但 `codex-rs/core/src/tools/orchestrator.rs:391-395` 有例外注释——「retrying without the sandbox requires a fresh guardian review」，即**去掉沙箱的重试在严格自动评审模式下必须重新评审**。

### Guardian 自动评审后端

`codex-rs/core/src/guardian/` 是一个独立的审批评审后端。接入点：

| 位置 | 内容 |
| ---- | ---- |
| `codex-rs/core/src/tools/approvals.rs:133-135` | `enum ApprovalReviewer { Guardian, User }` |
| `codex-rs/core/src/tools/orchestrator.rs:150` | `strict_auto_review_enabled_for_turn().await` 决定用哪个 reviewer |
| `codex-rs/core/src/tools/orchestrator.rs:183`、`:215`、`:412` | **三处** `ApprovalReviewer::Guardian` 的选取（上一稿写作 `:172`、`:214-217`；`:172` 那一行其实是 `ApprovalCtx { turn: &tool_ctx.turn, .. }`，与 reviewer 无关。`:215` 与 `:412` 是同一形状的 `if strict_auto_review { Guardian } else { ApprovalReviewer::for_turn(turn_ctx) }`，分别位于首次审批与权限升级请求两条路径上） |
| `codex-rs/core/src/tools/approvals.rs:233`、`:264` | 消费侧：`ApprovalReviewer::Guardian` 分支与 `ApprovalResolutionSource::Guardian` 的映射 |
| `codex-rs/core/src/guardian/` 目录 | `codex-rs/core/src/guardian/review.rs`、`codex-rs/core/src/guardian/review_session.rs`、`codex-rs/core/src/guardian/approval_request.rs`、`codex-rs/core/src/guardian/prompt.rs`、`codex-rs/core/src/guardian/metrics.rs`、`codex-rs/core/src/guardian/policy.md`、`codex-rs/core/src/guardian/policy_template.md`、`snapshots/`（E1） |

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
| `is_known_safe_command()` 的完整判定规则 | E1 | `codex-rs/shell-command/src/command_safety/` |
| execpolicy 的策略语言与规则格式 | E1 | `codex-rs/execpolicy/` |
| `codex-rs/sandboxing/src/policy_transforms.rs` 中 merge/intersect 的具体合成规则 | E1 | `codex-rs/sandboxing/src/policy_transforms.rs` |
| Guardian 评审的提示词与判定策略 | E1 | `codex-rs/core/src/guardian/policy.md`、`codex-rs/core/src/guardian/prompt.rs` |
| exec-server 协议的完整方法面 | E1 | `codex-rs/exec-server-protocol/src/` |
| MITM CA 与网络代理的完整链路 | E1 | `codex-rs/network-proxy/`（17,064 行） |

> **已从本表移除的三项**（早先列为未验证，现已在正文给出 E3 结论）：
> - 「Landlock/seccomp 与 bwrap 的选择条件」→ 见 §3.1，是**两道**判据：全盘写权限早退 + `use_legacy_landlock`
> - 「审批与沙箱在编排层的实际次序」→ 见 §7，源码注释直接写明
> - 「Windows 两条后端路径的切换条件」→ 见 §4，答案就是一行布尔表达式 `windows_sandbox_uses_elevated_backend`（`codex-rs/sandboxing/src/windows.rs:32-40`）= `proxy_enforced || matches!(sandbox_level, WindowsSandboxLevel::Elevated)`，入口在 `codex-rs/sandboxing/src/manager.rs:527-528`。**受管代理会强制走提权后端**，即使配置的是受限令牌。

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
