---
title: Codex 配置体系
summary: 描述 codex-config 的八层配置来源与精确优先级数值（含 MDM 实际走最高优先级的 legacy 通道这一关键勘误）、配置文件发现顺序与目录信任门控、93 个顶层配置键的规模、profile 作为独立文件的第二用户层机制、config.schema.json 的生成与防漂移机制、requirements.toml 的管理员约束能力，以及配置加载作为高风险改动面的注意事项。
keywords: codex | config | config-layer | precedence | config-toml | json-schema | requirements-toml | trust-gating | profile
scope: codex-rs/config 与 codex-rs/core/src/config 的配置加载体系
related_files: codex-rs/config/src/config_layer_source.rs | codex-rs/config/src/state.rs | codex-rs/config/src/loader/mod.rs | codex-rs/config/src/loader/layer_io.rs | codex-rs/config/src/loader/macos.rs | codex-rs/config/src/loader/README.md | codex-rs/core/src/config/mod.rs | codex-rs/core/src/config/config_loader_tests.rs | codex-rs/core/config.schema.json | codex-rs/app-server-protocol/src/protocol/v2/config.rs | codex-rs/app-server/src/config_layer.rs | codex-rs/cli/src/lib.rs | docs/config.md | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-03
---

# 配置体系

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-config`（`src/` 下 21,167 行）+ `codex-rs/core/src/config/`
> **证据等级**: 层级优先级、加载顺序与信任门控为 E3（源码与调用链）；配置键数量为 E4（实跑脚本）；文件/模块清单为 E1

> [!NOTE]
> **面向用户的配置参考在外部站点**（`docs/config.md` 只有 15 行，正文指向 developers.openai.com）。本文只讲**配置体系的机制**——层级、优先级、发现顺序、生成链路——不复述配置项清单。

> [!CAUTION]
> **本文第一版有一处严重错误，已在 §1 与 §4 更正。**
> 第一版称「MDM 优先级最低（0）」并把它当作 §4 的论据。这个结论只对**枚举里那个从未在生产路径上被构造的 `Mdm` 变体**成立；真实的 macOS MDM 托管配置走的是**优先级 50 的 legacy 通道，是全场最高**。
> 直接原因是：第一版虽然在 §3 推荐读者去看 `config/src/loader/README.md`，自己却**没有读那份 README 的「Layering model」小节**——那一节第 1 行就写着 `LegacyManagedConfigTomlFromMdm` 排在最上面。教训是：文档里推荐的入口，作者必须先自己走一遍。

---

## 1. 八层配置来源与精确优先级（E3）

`codex-rs/config/src/config_layer_source.rs:6` 定义了 `ConfigLayerSource`，`:31-48` 给出了每层的数值优先级。**数值越大优先级越高，高优先级覆盖低优先级**（`:29-30` 的文档注释明文说明）。

| 优先级 | 层 | 变体 | 载体 |
| ---: | ---- | ---- | ---- |
| 0 | MDM 管理策略（**生产路径未使用**） | `Mdm { domain, key }` | 见下方 ① |
| 10 | 主机级系统配置 | `System { file }` | `/etc/codex/config.toml`（Unix）/ `%ProgramData%\OpenAI\Codex\config.toml`（Windows） |
| 15 | 企业云配置包 | `EnterpriseManaged { id, name }` | 企业云下发 |
| 20 | 用户配置 | `User { file, profile: None }` | `${CODEX_HOME}/config.toml` |
| **21** | 用户配置 + 选定 profile | `User { file, profile: Some(_) }` | `${CODEX_HOME}/<name>.config.toml`（**另一个文件**，见 ③） |
| 25 | 项目配置 | `Project { dot_codex_folder }` | 项目的 `.codex` 目录（cwd / 逐级父目录 / 仓库根） |
| 30 | 会话覆盖 | `SessionFlags` | 本次会话的 `-c` / `--config` |
| 40 | 遗留管理配置（文件） | `LegacyManagedConfigTomlFromFile { file }` | `managed_config.toml` |
| **50** | 遗留管理配置（MDM） | `LegacyManagedConfigTomlFromMdm` | **macOS 托管偏好设置，即真正的 MDM 通道** |

### 三个容易踩的点

> [!WARNING]
> **① MDM 在生产路径上是最高优先级（50），不是最低（0）。**
>
> `ConfigLayerSource::Mdm`（precedence 0）**在生产代码里从未被构造过**：全仓所有出现处都是 `match` 分支（`diagnostics.rs:260`、`state.rs:212`、`tui/src/debug_config.rs:408`、`app-server/src/config_layer.rs:16`、`hooks/src/engine/discovery.rs:379` 等），仅有的两处构造都在测试内（`hooks/src/engine/mod_tests.rs` 与 `hooks/src/engine/discovery.rs` 的 `#[cfg(test)]` 段）。
>
> 真实的 macOS MDM 托管偏好设置（`com.openai.codex` 域的 `config_toml_base64` 键，`config/src/loader/macos.rs`）走的是另一条链路：
>
> ```
> macos.rs::load_managed_admin_config_layer   （CFPreferencesCopyAppValue 读托管偏好 → base64 解码 → 解析 TOML）
>         ↓
> loader/layer_io.rs::map_managed_admin_layer  （:96 → ManagedConfigFromMdm）
>         ↓
> loader/mod.rs:408                            （ConfigLayerEntry::new_with_raw_toml(ConfigLayerSource::LegacyManagedConfigTomlFromMdm, ...)）
>         ↓
> precedence = 50 —— 压在所有层之上
> ```
>
> 三处旁证：
> - `config/src/loader/README.md`「Layering model」小节：「Precedence is **top overrides bottom**: 1. `LegacyManagedConfigTomlFromMdm` (MDM-delivered `managed_config.toml`, while it is being phased out) …」
> - `core/src/config/config_loader_tests.rs:996` 的测试直接叫 `managed_preferences_take_highest_precedence()`。
> - `loader/mod.rs:369-370` 的注释：「Make a best-effort to support the legacy `managed_config.toml` as a config layer **on top of everything else**.」
>
> 换句话说：管理员通过 MDM 下发的 `config.toml` **确实压倒用户、项目与命令行**。但这是「尽力而为」的遗留机制（见 ②），正在被 `requirements.toml` 取代——想要**可靠**的强制约束仍应走 `requirements.toml`（`macos.rs` 里对应的键是 `requirements_toml_base64`，见 §4）。

> [!WARNING]
> **② 两个 legacy 层（40/50）优先级高于 SessionFlags（30）——这是有明文记录的历史遗留。**
>
> 第一版把它写成「很可能是有意为之的兼容行为，对调试是个陷阱」，属于臆测。实际上 `app-server-protocol/src/protocol/v2/config.rs:87-90` 的注释已经解释了：
>
> > "`managed_config.toml` was designed to be a config that was loaded as the last layer on top of everything else. This scheme did not quite work out as intended, but we keep this variant as a 'best effort' while we phase out `managed_config.toml` in favor of `requirements.toml`."
>
> 即：这个层级**是按设计放在最顶上的**，但「这套方案并未完全达到预期」，所以它以「尽力而为」的形式保留，直到 `managed_config.toml` 被 `requirements.toml` 完全替代。
>
> 调试价值不变：「我明明在命令行 `-c` 指定了却不生效」，答案可能就在这两层。

> [!NOTE]
> **③ 带 profile 的用户配置是 21，比不带的 20 高 1——因为它是另一个文件。**
>
> 第一版写「profile 是在用户层**内部**叠加的」，错了。20 与 21 是**两个独立的层，读两个不同的文件**：
>
> - 20 = `${CODEX_HOME}/config.toml`（基础用户配置）
> - 21 = `${CODEX_HOME}/<name>.config.toml`（选定 profile，后缀常量见 `core/src/config/mod.rs:274` `CONFIG_PROFILE_V2_SUFFIX = ".config.toml"`）
>
> `loader/mod.rs:245-247` 的注释说得很清楚：「Add the base user config layer. When profile-v2 is selected, add the **profile config as a second user layer on top** so the profile only needs to contain overrides.」实现在 `:281-292`（`if active_user_file != base_user_file { layers.push(load_user_config_layer(...)) }`）。
>
> CLI 侧的帮助文本（`cli/src/lib.rs:64`）也是这么写的：「Layer `$CODEX_HOME/<name>.config.toml` on top of the base user config.」
>
> 推论：profile 文件**只需要写差异项**，不必复制整份配置。

### 旧版 profile 已被硬性禁用（E3）

`--profile x` 与 config.toml 里的**遗留** profile 写法互斥，同时出现会直接 `Err`：

- `loader/mod.rs:258-279`：若 `config.toml` 里 `profile = "x"` 或存在 `[profiles.x]` 表，而命令行又传了 `--profile x`，返回 `io::ErrorKind::InvalidData`，错误信息要求把设置搬进 `x.config.toml` 并删掉遗留选择器/表。
- `core/src/config/mod.rs:3264`：「legacy `profile = "{profile}"` config is no longer supported; use `--profile {profile}` with `{profile}.config.toml` instead」。

所以 `config/src/profile_toml.rs` 不是理解 profile 机制的入口——真正的入口是 `loader/mod.rs` 的用户层加载段。

### 排序语义

`config_layer_source.rs:52-57` 实现了 `PartialOrd`，注释明确：

> "Compares `ConfigLayerSource` by precedence, so `A < B` means settings from layer `A` will be overridden by settings from layer `B`."

配套类型：`ConfigLayerMetadata { name, version }`、`ConfigLayer { name, version, config, disabled_reason }` —— **每层都带版本号**（稳定指纹，用于乐观并发/冲突检测），**并带一个可选的禁用原因**（见 §2）。

> [!CAUTION]
> **`ConfigLayerSource` 在仓库里有两份平行定义，需要手工保持同步。**
> - `codex-rs/config/src/config_layer_source.rs:6`（domain 类型）
> - `codex-rs/app-server-protocol/src/protocol/v2/config.rs:29-98`（对外 wire 类型），**precedence 数值与 `PartialOrd` 实现完全一致**（`:100-128`）
>
> **措辞更正**：上一稿说这两份是"逐字重复"，不够准确。**逐字一致的是语义部分**——变体集合、各变体的字段名与类型、`precedence()` 的返回值、`PartialOrd` 的实现。**不一致的是包裹在外面的东西**：
>
> | 差异项 | domain 类型 | wire 类型 |
> | ---- | ---- | ---- |
> | derive | `#[derive(Debug, Clone, PartialEq, Eq)]` | 另加 `Serialize, Deserialize, JsonSchema, TS` |
> | 容器属性 | 无 | `#[serde(tag = "type", rename_all = "camelCase")]`、`#[ts(tag = "type")]`、`#[ts(export_to = "v2/")]` |
> | 变体属性 | 无 | 每个带字段的变体都有 `#[serde(rename_all = "camelCase")]` + `#[ts(rename_all = "camelCase")]` |
> | 文档注释 | 较简短 | 更详细，面向 API 使用方（例如 `System` 变体额外说明"路径不保证存在"） |
>
> 这个区别有实际意义：**直接把一份复制粘贴到另一份会破坏各自的约束**（domain crate 不该背上 `TS` / `JsonSchema` 依赖，wire 类型不能少了 serde 标签）。同步时要改的是**变体与 precedence**，不是整段替换。
>
> 两者由 `codex-rs/app-server/src/config_layer.rs:16-26` 的手写 `config_layer_source_to_api()` 桥接——该文件注释说明：两个类型刻意分开，避免 app-server 协议的所有权渗进配置域 crate；因为本 crate 两个类型都不拥有，孤儿规则不允许写 `From`。
>
> **改优先级数值或增删变体时必须同时改这两处**，否则 wire 层与内部层会静默不一致。

---

## 2. 配置文件的发现顺序与信任门控（E3）

`config/src/loader/mod.rs:96-109` 的文档注释是**权威的加载顺序清单**（按优先级从低到高）：

| 层 | 位置 |
| ---- | ---- |
| admin | macOS 托管偏好设置（`(*)` 注明「Only available on macOS via managed device profiles」） |
| system | `/etc/codex/config.toml`（Unix）/ `%ProgramData%\OpenAI\Codex\config.toml`（Windows） |
| cloud | 企业云配置包片段 |
| user | `${CODEX_HOME}/config.toml` |
| profile | `${CODEX_HOME}/<name>.config.toml`（被选中时） |
| cwd | `${PWD}/config.toml` |
| tree | 逐级父目录直到根，找 `./.codex/config.toml` |
| repo | `$(git rev-parse --show-toplevel)/.codex/config.toml` |
| runtime | 例如 `--config` 标志、UI 里的模型选择器 |

同一段注释的 `:88` 还给出了 `requirements.toml` 的对应系统路径：`/etc/codex/requirements.toml` / `%ProgramData%\OpenAI\Codex\requirements.toml`。

### 信任门控：不受信目录的配置会被加载但禁用

> [!IMPORTANT]
> **cwd / tree / repo 这三层是「loaded but disabled when the directory is untrusted」**（`loader/mod.rs:104-106` 原文）。这是一条完整的安全机制，不是可选优化。

链路（E3）：

```
loader/mod.rs:318       project_trust_context(...)         ← 结合 project_root_markers 判定目录信任状态（定义在 :993）
        ↓
loader/mod.rs:1254-1256 decision = trust_context.decision_for_dir(&dir)
                        disabled_reason = trust_context.disabled_reason_for_decision(&decision)
        ↓
loader/mod.rs:949       ConfigLayerEntry::new_disabled(source, config, reason)
        ↓
state.rs:111            ConfigLayerEntry.disabled_reason: Option<String>
state.rs:172            fn is_disabled(&self) -> bool { self.disabled_reason.is_some() }
        ↓
state.rs:542            .filter(|layer| include_disabled || !layer.is_disabled())
```

被禁用的层在 `effective_config()`（`state.rs:492-501`）、`origins()`（`:506-519`）、`layers_high_to_low()`（`:524-529`）里**全部以 `include_disabled = false` 过滤掉**，但仍通过 `get_layers(ordering, include_disabled = true)` 暴露给 UI。`loader/README.md` 的说法是：「Layers with a `disabled_reason` are still surfaced for UI, but are ignored when computing the effective config and origins metadata.」

实际后果：**克隆一个不受信任的仓库不会让它的 `.codex/config.toml` 自动生效**，但你能在 TUI 的配置调试视图里看到「这一层存在但被禁用了，原因是 X」。

---

## 3. 配置规模（E4）

| 指标 | 数量 |
| ---- | ---: |
| `config.toml` 顶层配置键 | **93** |
| `codex-config` crate `src/` 行数 | 21,167 |
| `core/src/config/config_tests.rs` 行数 | 12,127 |

> 复核命令：
> ```bash
> python3 -c "import json;print(len(json.load(open('codex-rs/core/config.schema.json'))['properties']))"
> ```

顶层键的一部分（按字母序前 40 个）：`agents`、`allow_login_shell`、`analytics`、`approval_policy`、`approvals_reviewer`、`apps`、`audio`、`auto_review`、`chatgpt_base_url`、`compact_prompt`、`debug`、`default_permissions`、`desktop`、`developer_instructions`、`experimental_*`（7 个）、`features`、`feedback`、`file_opener`、`ghost_snapshot`、`hide_agent_reasoning`、`history`、`hooks` ……

> **完整清单请查 `codex-rs/core/config.schema.json`**，不要抄本文。

> [!NOTE]
> **勘误**：第一版称 `config_tests.rs` 是「全仓第 2 大文件」。按**跟踪文件的总行数**排，它是**第 5**：前四位是 `app-server-protocol/schema/json/codex_app_server_protocol.schemas.json`（22,635）、同目录的 `codex_app_server_protocol.v2.schemas.json`（20,393）、`codex-rs/Cargo.lock`（16,230）、`tui/src/bottom_pane/chat_composer.rs`（12,616）。它确实是**最大的 `.rs` 文件之一**（仅次于 `chat_composer.rs`），但「全仓第 2」这个口径不成立。

---

## 4. 模块版图

### `codex-config` crate（E1，来自 `ls`）

| 领域 | 文件 |
| ---- | ---- |
| **层栈核心** | `state.rs`（`ConfigLayerEntry` / `ConfigLayerStack`，含 `effective_config`、`origins`、`get_layers`）、`config_layer_source.rs`、`merge.rs`、`overrides.rs`、`loader/` |
| **加载器** | `loader/mod.rs`（`load_config_layers_state`，加载顺序与信任门控的实现）、`loader/layer_io.rs`、`loader/macos.rs`（**平台专属**）、`loader/README.md`、`loader/tests.rs` |
| **TOML 结构** | `config_toml.rs`、`profile_toml.rs`、`permissions_toml.rs`、`types.rs`、`schema.rs` |
| **严格模式** | `strict_config.rs`（未知字段拒绝） |
| **约束与需求** | `config_requirements.rs`、`constraint.rs`、`requirements_exec_policy.rs`、`mcp_requirements.rs`、`requirements_layers/`（`layer.rs`、`stack.rs`、`hooks.rs`、`permissions.rs`、`rules.rs`） |
| **线程级配置** | `thread_config.rs` + `thread_config/`（`remote.rs`、`proto/`） |
| **MCP** | `mcp_types.rs`、`mcp_edit.rs`、`mcp_requirements.rs` |
| **编辑能力** | `plugin_edit.rs`、`marketplace_edit.rs`、`mcp_edit.rs` |
| **云配置** | `cloud_config_bundle.rs`、`cloud_config_layers.rs` |
| **钩子与技能** | `hook_config.rs`、`skills_config.rs` |
| **执行环境** | `shell_environment_policy.rs` |
| **TUI** | `tui_keymap.rs` |
| **诊断与溯源** | `diagnostics.rs`、`fingerprint.rs`、`key_aliases.rs` |
| **项目识别** | `project_root_markers.rs` |
| **测试基建** | `test_support.rs` + 各 `*_tests.rs` |
| 其他 | `host_name.rs` |

> [!TIP]
> `codex-rs/config/src/loader/README.md` 是仓库内少有的模块级说明文档，读配置加载**必须**先看——它同时给出了公开 API 面、优先级模型、内部文件分工。本文第一版的 MDM 错误就是跳过它造成的。

### `core/src/config/`（E1）

| 文件 | 职责 |
| ---- | ---- |
| `mod.rs` | 配置主体（含 `find_codex_home`（见 §6）、`CONFIG_PROFILE_V2_SUFFIX`、遗留 profile 拒绝逻辑） |
| `schema.rs` + `schema.md` | JSON Schema 生成 |
| `permissions.rs`、`resolved_permission_profile.rs`、`permission_profile_catalog.rs` | 权限档 |
| `auth_keyring.rs` | 钥匙串认证 |
| `otel.rs` | 遥测配置 |
| `network_proxy_spec.rs` | 网络代理 |
| `managed_features.rs` | 受管特性 |
| `agent_roles.rs` | 智能体角色 |
| `edit.rs` + `edit/` | 配置编辑 |
| `requirements.rs` | 需求约束 |
| `config_loader_tests.rs` | 加载器行为测试（含 `managed_preferences_take_highest_precedence`） |

---

## 5. `requirements.toml`：管理员的强制约束

`docs/config.md:11-15` 给出了一个关键事实（E2）：

> Admins can set top-level `allow_managed_hooks_only = true` in `requirements.toml` to ignore user, project, and session hook configs while still allowing managed hooks from requirements and managed config layers. This setting is only supported in `requirements.toml`; putting it in `config.toml` does not enable managed-hooks-only mode.

> [!NOTE]
> **勘误**：第一版在此处写「这印证了 §1 的推论：config.toml 的层级模型里管理策略是最低优先级，所以真正的强制约束必须放在 requirements.toml」。这个「印证」建立在 §1 的错误结论上，**不成立**——MDM 下发的 config.toml 实际是最高优先级（50）。
>
> 正确的解释是：`requirements.toml` 与配置层是**两套并行机制**，不是「因为配置层管不住所以另起一套」。
> - 配置层给的是**默认值/覆盖值**，用户仍可在 TUI 与 VS Code 里按轮次覆盖（`loader/mod.rs:369-373` 的注释明说了这一点）。
> - `requirements.toml` 给的是**不可协商的约束**（`ConfigRequirements`），并且有自己的一条加载链（`loader/mod.rs:82-91`：system → cloud → legacy → admin managed preferences，`compose_requirements()` 合并）。
> - `allow_managed_hooks_only` 这类开关**只在 requirements 通道生效**，正是因为它约束的是「谁可以提供 hook」，而不是「hook 的默认值是什么」。
> - 遗留的 `managed_config.toml` 会被**同时**当作配置层（40/50）与 requirements 层使用（`loader/mod.rs:189` 调用 `requirements_layers_from_legacy_scheme`，定义在 `:744`），这是向后兼容的桥。

相关实现：`config_requirements.rs`、`requirements_exec_policy.rs`、`mcp_requirements.rs`、`requirements_layers/`、`core/src/config/requirements.rs`。macOS 侧的 requirements 键是 `com.openai.codex` 域的 `requirements_toml_base64`（`loader/macos.rs:22`）。

> **未验证**（E1）：`requirements.toml` 支持的完整字段集。

---

## 6. `CODEX_HOME` 解析（E3）

配置目录由 `CODEX_HOME` 环境变量决定，未设置时默认 `~/.codex`。**权威实现在 `codex-rs/utils/home-dir/src/lib.rs:13`**：

| 情况 | 行为 |
| ---- | ---- |
| CODEX_HOME 已设置且非空 | 路径**必须存在且是目录**，会被 canonicalize；不满足则返回错误（`lib.rs:20-40`） |
| `CODEX_HOME` 未设置或为空 | 回退到 `~/.codex`，**不校验目录是否存在** |

错误信息区分了两种失败：路径不存在时报 `CODEX_HOME points to {val:?}, but that path does not exist`，其他 IO 错误报 `failed to read CODEX_HOME {val:?}: {err}`。

> [!TIP]
> `codex-rs/core/src/config/mod.rs:4578` 也有一个 `pub fn find_codex_home`，但**它是薄委托**——函数体只有一行 `codex_utils_home_dir::find_codex_home()`。两处不是重复实现。

---

## 7. Schema 生成与防漂移

`codex-rs/core/src/config/schema.md` 说明（E2）：

> We generate a JSON Schema for `~/.codex/config.toml` from the `ConfigToml` type and commit it at `codex-rs/core/config.schema.json` for editor integration.

```
改 ConfigToml 或任何嵌套配置类型
        ↓
just write-config-schema
  （= cargo run -p codex-core --bin codex-write-config-schema）
        ↓
codex-rs/core/config.schema.json 更新
        ↓
与 Rust 改动放进同一个 change
```

这是 `AGENTS.md` **顶部规则列表**里的明文要求（关键词 `just write-config-schema` / `ConfigToml or nested config types`）。schema 文件被提交进仓库的目的是**编辑器集成**（写 `config.toml` 时有补全与校验）。

---

## 8. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **配置加载是 `AGENTS.md` `## Code Review Rules` → `### Breaking changes` 点名的高风险改动面** | 该清单：app-server APIs、`rawResponseItem/*`、CLI parameters、**configuration loading**、resuming sessions from existing rollouts |
| 改 `ConfigToml` 或嵌套类型必须跑 `just write-config-schema` | AGENTS.md 顶部规则列表，关键词 `just write-config-schema` |
| **改优先级数值或增删层要同时改两处 `ConfigLayerSource`** | `config/src/config_layer_source.rs` + `app-server-protocol/src/protocol/v2/config.rs`，桥接在 `app-server/src/config_layer.rs` |
| 新增配置层或改优先级会影响所有用户的既有配置，需极度谨慎 | §1 的优先级是行为契约 |
| 动 cwd/tree/repo 层时要确认信任门控仍然生效 | §2；绕过 `disabled_reason` 等于让不受信目录的配置生效 |
| `config_tests.rs` 有 12,127 行，**必须分段读取** | 最大的 `.rs` 文件之一 |
| 不要为静态定义的值写测试 | `AGENTS.md` 顶部规则列表，关键词 `Do not add tests for values that are statically defined` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 93 个配置键的逐个语义 | E4（仅键名） | `codex-rs/core/config.schema.json`、developers.openai.com |
| 层合并的具体算法（深合并还是浅覆盖） | E1 | `codex-rs/config/src/merge.rs`（README 称其为 "recursive TOML merge"） |
| 目录信任状态本身是怎么判定与持久化的 | E1 | `loader/mod.rs` 的 `project_trust_context`、`project_root_markers.rs` |
| `requirements.toml` 的完整字段集 | E1 | `config/src/config_requirements.rs`、`requirements_layers/` |
| 线程级配置层（`thread_config`）的注入时机 | E1 | `config/src/thread_config.rs`、`loader/mod.rs` 的 `insert_layer_by_precedence` |
| 权限档（permission profile）的解析 | E1 | `core/src/config/resolved_permission_profile.rs` |
| 云配置包的下发链路 | E1 | `config/src/cloud_config_bundle.rs`、`codex-cloud-config` crate |
| 严格模式（`strict_config`）的完整校验规则 | E1 | `config/src/strict_config.rs` |
| 配置指纹与诊断的用途 | E1 | `config/src/fingerprint.rs`、`diagnostics.rs` |

---

## 10. 相关文档

- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 与落盘内容
- [智能体核心循环](./core_agent_loop.md) §5 — 审批与沙箱策略类型
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱策略的执行侧
- [认证与模型接入](./auth_and_providers.md) — 凭证存储配置
- [app-server 协议](./app_server_protocol.md) — `ConfigLayerSource` 的 wire 侧副本
- [可观测性](./observability.md) — 遥测配置项
