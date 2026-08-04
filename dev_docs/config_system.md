---
title: Codex 配置体系
summary: 描述 codex-config 的八个配置层来源与九个优先级档位（含 MDM 在 macOS 上实际走最高优先级 legacy 通道这一关键勘误）、配置文件发现顺序、项目层的两道闸门（键黑名单 + 目录信任门控）、93 个顶层配置键的规模、profile 作为独立文件的第二用户层机制、config.schema.json 的生成与自动化防漂移测试、requirements.toml 的管理员约束能力、sqlite_home 的三级解析与 requirements 覆盖、LoaderOverrides 逃生舱，以及配置加载作为高风险改动面的注意事项。
keywords: codex | config | config-layer | precedence | config-toml | json-schema | requirements-toml | trust-gating | profile | denylist | sqlite-home | loader-overrides
scope: codex-rs/config 与 codex-rs/core/src/config 的配置加载体系
related_files: codex-rs/config/src/config_layer_source.rs | codex-rs/config/src/state.rs | codex-rs/config/src/loader/mod.rs | codex-rs/config/src/loader/layer_io.rs | codex-rs/config/src/loader/macos.rs | codex-rs/config/src/loader/README.md | codex-rs/core/src/config/mod.rs | codex-rs/core/src/config/config_loader_tests.rs | codex-rs/core/src/config/schema_tests.rs | codex-rs/core/src/bin/config_schema.rs | codex-rs/core/config.schema.json | codex-rs/app-server-protocol/src/protocol/v2/config.rs | codex-rs/app-server/src/config_layer.rs | codex-rs/cli/src/lib.rs | codex-rs/utils/home-dir/src/lib.rs | docs/config.md | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-05
---

# 配置体系

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-config`（`src/` 下 21,167 行）+ `codex-rs/core/src/config/`
> **证据等级**: 层级优先级、加载顺序与信任门控为 E3（源码与调用链）；配置键数量为 E2（解析已提交的生成产物 `codex-rs/core/config.schema.json`）；行数统计为 E1（对已跟踪文件 `wc -l`）；文件/模块清单为 E1

> [!NOTE]
> **面向用户的配置参考在外部站点**（`docs/config.md` 只有 15 行，正文指向 developers.openai.com）。本文只讲**配置体系的机制**——层级、优先级、发现顺序、生成链路——不复述配置项清单。

> [!CAUTION]
> **本文第一版有一处严重错误，已在 §1 与 §5 更正。**
> 第一版称「MDM 优先级最低（0）」并把它当作 §5 的论据。这个结论只对**枚举里那个从未在生产路径上被构造的 `Mdm` 变体**成立；真实的 macOS MDM 托管配置走的是**优先级 50 的 legacy 通道，是全场最高**。
> 直接原因是：第一版虽然在 §3 推荐读者去看 `codex-rs/config/src/loader/README.md`，自己却**没有读那份 README 的「Layering model」小节**——那一节第 1 行就写着 `LegacyManagedConfigTomlFromMdm` 排在最上面。教训是：文档里推荐的入口，作者必须先自己走一遍。

---

## 1. 八个层来源变体、九个优先级档位（E3）

`codex-rs/config/src/config_layer_source.rs:6` 定义了 `ConfigLayerSource`，`:31-48` 给出了每层的数值优先级。**数值越大优先级越高，高优先级覆盖低优先级**（`:29-30` 的文档注释明文说明）。

> [!NOTE]
> **「八层」还是「九层」？** `ConfigLayerSource` 只有 **8 个变体**，但 `precedence()` 返回 **9 个不同数值**——`User` 按 `profile.is_some()` 分叉为 21 / 20（见下表与 ③）。本文统一说「八个层来源变体、九个优先级档位」。

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
| **50** | 遗留管理配置（MDM，**仅 macOS**） | `LegacyManagedConfigTomlFromMdm` | **macOS 托管偏好设置，即真正的 MDM 通道** |

### 三个容易踩的点

> [!WARNING]
> **① 在 macOS 上，MDM 在生产路径上是最高优先级（50），不是最低（0）。**
>
> **平台限定**：这一层**只在 macOS 上存在**。`codex-rs/config/src/loader/layer_io.rs:77-87` 里只有 `#[cfg(target_os = "macos")]` 分支才调用 `load_managed_admin_config_layer`；`#[cfg(not(target_os = "macos"))]` 分支直接 `let managed_preferences = None;`。因此在 **Linux / Windows 上，全场最高的实际是优先级 40 的那一层**（`LegacyManagedConfigTomlFromFile`，定义见 `codex-rs/config/src/config_layer_source.rs:6`），本节所有「全场最高」「压在所有层之上」的表述都应读作「在 macOS 上」。
>
> `ConfigLayerSource::Mdm`（precedence 0）**在生产代码里从未被构造过**：全仓所有出现处都是 `match` 分支（`codex-rs/config/src/diagnostics.rs:260`、`codex-rs/config/src/state.rs:212`、`codex-rs/tui/src/debug_config.rs:408`、`codex-rs/app-server/src/config_layer.rs:16`、`codex-rs/hooks/src/engine/discovery.rs:379`、`codex-rs/app-server/src/config_manager_service.rs:789`、`codex-rs/core-skills/src/loader.rs:372` 等），仅有的两处构造都在测试内（`codex-rs/hooks/src/engine/mod_tests.rs` 与 `codex-rs/hooks/src/engine/discovery.rs` 的 `#[cfg(test)]` 段）。
>
> 真实的 macOS MDM 托管偏好设置（`com.openai.codex` 域的 `config_toml_base64` 键，`codex-rs/config/src/loader/macos.rs`）走的是另一条链路：
>
> ```
> macos.rs::load_managed_admin_config_layer   （CFPreferencesCopyAppValue 读托管偏好 → base64 解码 → 解析 TOML）
>         ↓
> loader/layer_io.rs::map_managed_admin_layer  （:96 → ManagedConfigFromMdm）
>         ↓
> loader/mod.rs:408                            （ConfigLayerEntry::new_with_raw_toml(ConfigLayerSource::LegacyManagedConfigTomlFromMdm, ...)）
>         ↓
> precedence = 50 —— 在 macOS 上压在所有层之上
> ```
>
> ⚠️ **注意**：`load_config_layers_state` 自己的文档注释把 `admin: managed preferences` 排在**升序清单的第一位（最低）**——那描述的是 `Mdm`（precedence 0）的**设计意图**，而非实现。见 §2 的「本文件的注释不可信」。
>
> 三处旁证：
> - `codex-rs/config/src/loader/README.md`「Layering model」小节：「Precedence is **top overrides bottom**: 1. `LegacyManagedConfigTomlFromMdm` (MDM-delivered `managed_config.toml`, while it is being phased out) …」
> - `codex-rs/core/src/config/config_loader_tests.rs:996` 的测试直接叫 `managed_preferences_take_highest_precedence()`。
> - `codex-rs/config/src/loader/mod.rs:369-370` 的注释：「Make a best-effort to support the legacy `managed_config.toml` as a config layer **on top of everything else**.」
>
> 换句话说：**在 macOS 上**，管理员通过 MDM 下发的 `config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> **确实压倒用户、项目与命令行**；在非 macOS 平台上这条通道根本不存在。但这是「尽力而为」的遗留机制（见 ②），正在被 `requirements.toml` 取代——想要**可靠**的强制约束仍应走 `requirements.toml`（`codex-rs/config/src/loader/macos.rs` 里对应的键是 `requirements_toml_base64`，见 §5）。

> [!WARNING]
> **② 两个 legacy 层（40/50）优先级高于 SessionFlags（30）——这是有明文记录的历史遗留。**
>
> 第一版把它写成「很可能是有意为之的兼容行为，对调试是个陷阱」，属于臆测。实际上 `codex-rs/app-server-protocol/src/protocol/v2/config.rs:87-90` 的注释已经解释了：
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
> - 21 = `${CODEX_HOME}/<name>.config.toml`（选定 profile，后缀常量见 `codex-rs/core/src/config/mod.rs:274` `CONFIG_PROFILE_V2_SUFFIX = ".config.toml"`）
>
> `codex-rs/config/src/loader/mod.rs:245-247` 的注释说得很清楚：「Add the base user config layer. When profile-v2 is selected, add the **profile config as a second user layer on top** so the profile only needs to contain overrides.」实现在 `:282-293`（`if active_user_file != base_user_file { layers.push(load_user_config_layer(...)) }`；`:281` 是空行）。
>
> CLI 侧的帮助文本（`codex-rs/cli/src/lib.rs:64`）也是这么写的：「Layer `$CODEX_HOME/<name>.config.toml` on top of the base user config.」
>
> 推论：profile 文件**只需要写差异项**，不必复制整份配置。
>
> **名称是被校验的**：`--profile` 的值先要通过 `ProfileV2Name`（`codex-rs/protocol/src/config_types.rs:100-141`）的 `FromStr`——**非空、且每个字节只能是 ASCII 字母数字或 `_` / `-`**（`:129-136`）。这直接堵死了 `../foo` 这类路径穿越：profile 名会被拼进 `${CODEX_HOME}/<name>.config.toml`，如果不校验就等于让 `--profile` 变成任意文件读取原语。

### 死类型 ②：`ConfigToml::profiles` 与整个 `ConfigProfile`（E3）

> [!WARNING]
> **继 `ConfigLayerSource::Mdm` 之后，本体系的第二个「类型存在 ≠ 类型生效」实例。**
>
> `ConfigToml::profiles: HashMap<String, ConfigProfile>`（`codex-rs/config/src/config_toml.rs:311-313`）仍会被 serde 反序列化，`ConfigProfile`（`codex-rs/config/src/profile_toml.rs:24`）有 40+ 个字段——但排除测试后，`ConfigProfile` 这个名字在全仓**只有 3 处命中**：结构体定义、`codex-rs/config/src/config_toml.rs:9` 的 `use`、以及 `:313` 的字段声明。**没有任何生产代码读取 `cfg.profiles` 的内容。**
>
> 它唯一的实际作用是：让 `[profiles.*]` 能通过 strict-config 的未知字段校验，并出现在 `codex-rs/core/config.schema.json` 里。真正会去看 `profiles` 的地方（`codex-rs/config/src/loader/mod.rs:265-268`）读的是**原始 `TomlValue`**，而不是这个类型化字段——目的仅仅是**检测冲突并报错**，见下一小节。
>
> 教训与 MDM 相同：**「schema 里有」「struct 里有」都不能推出「运行时读它」**。要判断一个配置键是否生效，必须找到读取点，而不是定义点。

### 旧版 profile 已被硬性禁用（E3）

`--profile x` 与 config.toml 里的**遗留** profile 写法互斥，同时出现会直接 `Err`：

- `codex-rs/config/src/loader/mod.rs:259-279`：若基础 `config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 里 `profile = "x"`（`:261-264`）**或**存在 `[profiles.x]` 表（`:265-268`），而命令行又传了 `--profile x`，则 `:270-278` 返回 `io::ErrorKind::InvalidData`，错误信息要求把设置搬进 `x.config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 并删掉遗留选择器/表。注意判定针对的是**同名**冲突：`[profiles.other]` 配 `--profile work` 不会报错，只是被忽略。
- `codex-rs/core/src/config/mod.rs:3260-3267`：「legacy `profile = "{profile}"` config is no longer supported; use `--profile {profile}` with `{profile}.config.toml` instead」。

所以 `codex-rs/config/src/profile_toml.rs` 不是理解 profile 机制的入口——真正的入口是 `codex-rs/config/src/loader/mod.rs` 的用户层加载段。

### 排序语义

`codex-rs/config/src/config_layer_source.rs:51-57` 实现了 `PartialOrd`（注释 `:51-52`，`impl` 本体 `:53-57`），注释明确：

> "Compares `ConfigLayerSource` by precedence, so `A < B` means settings from layer `A` will be overridden by settings from layer `B`."

配套类型：`ConfigLayerMetadata { name, version }`、`ConfigLayer { name, version, config, disabled_reason }` —— **每层都带版本号**（稳定指纹，用于乐观并发/冲突检测），**并带一个可选的禁用原因**（见 §2）。

> [!CAUTION]
> **`ConfigLayerSource` 在仓库里有两份平行定义，需要手工保持同步。**
> - `codex-rs/config/src/config_layer_source.rs:6`（domain 类型）
> - `codex-rs/app-server-protocol/src/protocol/v2/config.rs:29-98`（对外 wire 类型），**precedence 数值与 `PartialOrd` 实现完全一致**（`precedence()` 在 `:100-121`，其中 `match` 体 `:104-119` 是逐字复制；`PartialOrd` 在 `:123-129`）
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
> 两者由 `codex-rs/app-server/src/config_layer.rs:14-33` 的手写 `config_layer_source_to_api()` 桥接——该函数头的注释（`:8-13`）说明：两个类型刻意分开，避免 app-server 协议的所有权渗进配置域 crate；因为该 crate 两个类型都不拥有，孤儿规则不允许写 `From`。
>
> **改优先级数值或增删变体时必须同时改这两处**，否则 wire 层与内部层会静默不一致。
>
> **而且没有任何测试会捕捉到不同步**——本次核查未发现任何跨 crate 的一致性测试。可用的检查手段都不到位：
> - `codex-rs/config/src/state.rs:569` 的 `verify_layer_ordering` **只校验层栈「已按 precedence 排好序」，不校验 precedence 的取值是否正确**（`:570` 用的是 `is_sorted()`）；把两份副本的数值同步改错，它照样通过。
> - `codex-rs/config/src/loader/tests.rs` 只有 12 个测试函数，且全部围绕 profile-v2，**没有一个断言完整的八变体优先级次序**。
>
> 这是**纯人工约定**，改动时格外小心。

---

## 2. 配置文件的发现顺序与信任门控（E3）

`codex-rs/config/src/loader/mod.rs:96-111` 的文档注释给出了加载顺序清单（注释自称按优先级从低到高）：

| 层 | 注释里的位置 | 修正 |
| ---- | ---- | ---- |
| admin | macOS 托管偏好设置（`(*)` 注明「Only available on macOS via managed device profiles」） | **排在最低是错的**，见下 |
| system | `/etc/codex/config.toml`（Unix）/ `%ProgramData%\OpenAI\Codex\config.toml`（Windows） | Windows 侧是动态解析，见「平台差异」 |
| cloud | 企业云配置包片段 | |
| user | `${CODEX_HOME}/config.toml` | |
| profile | `${CODEX_HOME}/<name>.config.toml`（被选中时） | |
| cwd | `${PWD}/config.toml` | **实际是 `${PWD}/.codex/config.toml`**，见下 |
| tree | 逐级父目录直到根，找 `./.codex/config.toml` | |
| repo | `$(git rev-parse --show-toplevel)/.codex/config.toml` | |
| runtime | 例如 `--config` 标志、UI 里的模型选择器 | |

同一文件 `:82-94` 是**另一段**注释，讲的是 requirements 层；其中 `:87` 给出了 `requirements.toml` 的系统路径：`/etc/codex/requirements.toml`（Unix）/ `%ProgramData%\OpenAI\Codex\requirements.toml`（Windows）。config 层的那份清单在 `:96-111`。

### 本文件的注释不可信（E3）

> [!CAUTION]
> **`codex-rs/config/src/loader/mod.rs` 的这两段文档注释至少有两处与实现不符，而且彼此打架。任何「读注释确认」式的复核都会在这里得到错误答案。**
>
> **① admin 层的位置：两段注释自相矛盾。**
> - `:82-94`（requirements 层）把 `admin: managed preferences` 排在**最后（最高）**——与实现一致。
> - `:96-111`（config 层）按升序列举，却把 `admin: managed preferences` 排在**第一位（最低）**。
>
> 后者描述的其实是 `ConfigLayerSource::Mdm`（precedence 0）的**设计意图**——而那个变体零生产构造点（§1 ①）。真实的 macOS MDM 走 `LegacyManagedConfigTomlFromMdm`，precedence **50**，是最高。**同一个文件里紧邻的两段注释给出了相反的结论。**
>
> **② cwd 层的路径写错了。**
> 注释 `:104` 写的是 `cwd  ${PWD}/config.toml`，**实际是 `${PWD}/.codex/config.toml`**。项目层扫描出的每一级目录都只看其下的 `.codex/` 子目录：`:1243` 是 `let dot_codex_abs = dir.join(".codex");`，`:1245-1251` 先要求 `.codex` 存在且**是目录**，否则 `continue`；配置文件路径在 `:1262` 由 `dot_codex_abs.join(CONFIG_TOML_FILE)` 拼出。这也与本文 §1 的优先级表（`Project { dot_codex_folder }` → 项目的 `.codex` 目录）一致。
>
> **怎样才能发现这些**：只有追踪 `layers.push(...)` 的**实际调用序列**、以及 `precedence()` 的返回值，才能得到正确的层序与路径。**注释、README、帮助文本都只是线索，不是结论**——本文 §1 第一版的 MDM 错误正是「只读了一半材料」的产物，而这一节说明「读全了注释」同样不够。

### 平台差异：三条路径的解析机制各不相同（E3）

结论层面的「Unix 用 `/etc/codex`，Windows 用 `%ProgramData%\OpenAI\Codex`」掩盖了机制上的差异：

| 通道 | Unix | Windows |
| ---- | ---- | ---- |
| system `config.toml` / `requirements.toml` | 硬编码常量 `SYSTEM_CONFIG_TOML_FILE_UNIX = "/etc/codex/config.toml"`（`codex-rs/config/src/loader/mod.rs:55`），由 `:652-655` 的 `system_config_toml_file()` 返回 | `:671-681` 的 `windows_codex_system_dir()`：`SHGetKnownFolderPath(FOLDERID_ProgramData)`（`:696-701` 的 `windows_program_data_dir_from_known_folder()`）**动态解析**，再 `.join("OpenAI").join("Codex")`；解析失败时 `tracing::warn!` 并回退到 `:58` 的 `DEFAULT_PROGRAM_DATA_DIR_WINDOWS = r"C:\ProgramData"` | <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->
| legacy `managed_config.toml`（precedence 40） | `codex-rs/config/src/loader/layer_io.rs:20` 的 `CODEX_MANAGED_CONFIG_SYSTEM_PATH = "/etc/codex/managed_config.toml"` | **`$CODEX_HOME\managed_config.toml`**（`codex-rs/config/src/loader/layer_io.rs:171-183` 的 `managed_config_default_path()`，`#[cfg(not(unix))]` 分支） |
| admin 托管偏好（precedence 50） | **不存在** | **不存在**（`codex-rs/config/src/loader/layer_io.rs:77-87` 只有 `#[cfg(target_os = "macos")]` 才加载；其余平台 `let managed_preferences = None;`） |

> [!WARNING]
> **Windows 上存在一处强制力不对称。**
> precedence **40** 的 legacy `managed_config.toml` 落在 `$CODEX_HOME`——**用户可写的目录**；而 precedence **10** 的 system `config.toml` 落在受保护的 `%ProgramData%`。也就是说：在 Windows 上，用户可以自己写一个高优先级的「管理配置」层，压过管理员下发的 system 层。这条通道正在被 `requirements.toml` 取代（§5），但在过渡期内，**不要把 Windows 上的 `managed_config.toml` 当作强制手段**。 <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->

### 项目层的键黑名单（与信任门控正交）

> [!IMPORTANT]
> **项目层有两道闸门，信任门控只是第二道。第一道是无条件的键黑名单。**

无论目录是否受信任，`.codex/config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 里的下列 11 个键（均为顶层）一律被 `remove()` 掉：

`openai_base_url`、`chatgpt_base_url`、`apps_mcp_product_sku`、`model_provider`、`model_providers`、`notify`、`profile`、`profiles`、`experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_base_url`、`otel`

外加一个嵌套键 `features.respect_system_proxy`。

清单定义在 `codex-rs/config/src/loader/mod.rs:60-76` 的 `const PROJECT_LOCAL_CONFIG_DENYLIST`，理由写在 `:60-63` 的注释里：

> "Project-local config comes from repository contents, so it should not get to choose where a user's credentials are sent or which local commands are run. These settings are still supported from user, system, managed, and runtime config layers."

即：这一层的输入来自**仓库内容**，而仓库内容可能来自不受你控制的第三方。被拉黑的键恰好覆盖三类攻击面——**凭证外泄**（base URL / model provider）、**任意命令执行**（`notify`）、**遥测重定向**（`otel`）、**代理绕过**（`features.respect_system_proxy`）。

执行点：

```
loader/mod.rs:1296   sanitize_project_config(&mut config)     ← 无条件调用，不看 disabled_reason
        ↓            （定义 :956-974；剥离黑名单键并返回被剥离的键名）
loader/mod.rs:1306   if disabled_reason.is_none() && !ignored_project_config_keys.is_empty()
        ↓            → startup_warnings.push(project_ignored_config_keys_warning(...))
                       （定义 :976-991）
```

> [!NOTE]
> **剥离是无条件的，警告是有条件的。** `sanitize_project_config` 在 `:1296` 被调用时完全不看 `disabled_reason`——这正是「两道闸门正交」的代码级证据。但 `:1306` 只在 `disabled_reason.is_none()`（即该层未被信任门控禁用）时才推送启动警告：对一个本来就整层禁用的项目层，再报「有几个键被忽略了」没有意义。

警告文案（`:983-990`）：「Ignored unsupported project-local config keys in {config_path}: {ignored_keys}. If you want these settings to apply, manually set them in your user-level config.toml.」——**只能搬到用户层，没有「信任这个目录就放行」的选项。**

### 项目层的发现算法（E3）

- **候选目录**由 `cwd.ancestors()` 向上收集到 `project_root` 为止（`codex-rs/config/src/loader/mod.rs:1226`），随后 `:1238` 执行 `dirs.reverse()`——因此层的入栈顺序是 **root → cwd，越靠近 cwd 优先级越高**。
- **`project_root` 由 marker 决定**：默认 `DEFAULT_PROJECT_ROOT_MARKERS = &[".git"]`（`codex-rs/config/src/project_root_markers.rs:5`），可用配置键 `project_root_markers` 覆盖；给空数组即禁用向上探测。
- **每级目录必须有 `.codex` 目录**：`:1243-1252`，不是目录就 `continue`。
- **`~/.codex` 被显式排除**：`:1259-1261` 在 `.codex` 路径（规范化后）等于 `codex_home` 时 `continue`，避免把用户配置目录误当成项目层重复加载。
- **顺序有后置校验**：`codex-rs/config/src/state.rs:583-612` 在 `verify_layer_ordering` 内额外确认多个 `Project` 层确实是 root→cwd 排列，否则报 `"project layers are not ordered from root to cwd"`。

### 信任门控：不受信目录的配置会被加载但禁用

> [!IMPORTANT]
> **cwd / tree / repo 这三层是「loaded but disabled when the directory is untrusted」**（`codex-rs/config/src/loader/mod.rs:104-106` 原文）。这是两条正交安全机制之一（另一条是上面的键黑名单），不是可选优化。

门控覆盖面在提示文案里写死为三项——`codex-rs/config/src/loader/mod.rs:912`：`let gated_features = "project-local config, hooks, and exec policies";`，对应 `:917` / `:920` 两条面向用户的提示。

链路（E3）：

```
loader/mod.rs:318       project_trust_context(...)         ← 结合 project_root_markers 判定目录信任状态（定义在 :993）
        ↓
loader/mod.rs:1254-1256 decision = trust_context.decision_for_dir(&dir)
                        disabled_reason = trust_context.disabled_reason_for_decision(&decision)
        ↓
loader/mod.rs:949       ConfigLayerEntry::new_disabled(source, config, reason)
        ↓
codex-rs/config/src/state.rs:111   ConfigLayerEntry.disabled_reason: Option<String>
codex-rs/config/src/state.rs:171-173   fn is_disabled(&self) -> bool { self.disabled_reason.is_some() }
        ↓
codex-rs/config/src/state.rs:542   .filter(|layer| include_disabled || !layer.is_disabled())
```

被禁用的层在 `effective_config()`（`codex-rs/config/src/state.rs:492-501`）、`origins()`（`:506-519`）、`layers_high_to_low()`（`:524-529`）里**全部以 `include_disabled = false` 过滤掉**，但仍通过 `get_layers(ordering, include_disabled = true)` 暴露给 UI。`codex-rs/config/src/loader/README.md` 的说法是：「Layers with a `disabled_reason` are still surfaced for UI, but are ignored when computing the effective config and origins metadata.」

`include_disabled = true` 的**生产调用点**（E1，非测试）：

| 调用点 | 用途 |
| ---- | ---- |
| `codex-rs/tui/src/debug_config.rs:134-136` | TUI 配置调试视图列出全部层（含禁用层） |
| `codex-rs/app-server/src/config_manager_service.rs:163-165` | app-server 的 `include_layers` 响应字段 |
| `codex-rs/cli/src/doctor/title.rs:174-176` | `codex doctor` 输出 |
| `codex-rs/app-server/src/lib.rs:358-360` | 收集被禁用的项目目录，供客户端提示「是否信任」 |
| `codex-rs/tui/src/app/startup_prompts.rs:72-74` | 同上，TUI 启动时的信任提示 |

实际后果：**克隆一个不受信任的仓库不会让它的 `.codex/config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 自动生效**，但你能在 TUI 的配置调试视图里看到「这一层存在但被禁用了，原因是 X」，并被提示是否信任该目录。

### 结论：项目层实际能设置什么

> [!IMPORTANT]
> 即使目录**受信任**，项目 `.codex/config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 也**无法**设置 base URL、model provider、`notify`、`profile(s)` 与 `otel`——这些键会被无条件剥离并转成启动警告；**不受信任**的目录则整层被 `disabled_reason` 屏蔽，一个键都不生效。两道闸门都要过，才轮到普通的优先级合并。

---

## 2.5 逃生舱：`LoaderOverrides`（E3）

上面把层栈描述成固定的，但整套加载有一组注入点——`codex-rs/config/src/state.rs:43-56` 的 `LoaderOverrides`：

| 字段 | 作用 |
| ---- | ---- |
| `user_config_path` / `user_config_profile` | 把「用户层」指向任意文件 |
| `managed_config_path` / `system_config_path` / `system_requirements_path` | 重定向托管、系统与系统 requirements 路径 |
| `ignore_managed_requirements` | 整体跳过托管 requirements |
| `ignore_user_config` | 整体跳过用户配置 |
| `ignore_user_and_project_exec_policy_rules` | 忽略用户/项目层的 exec policy 规则 |
| `managed_preferences_base64`（`#[cfg(target_os = "macos")]`）、`macos_managed_config_requirements_base64` | 直接注入 MDM 内容，绕过 `CFPreferences` |

`:59-77` 的 `without_managed_config_for_tests()` 把托管配置整体关掉（把三条系统路径指向临时目录里的不存在文件、并把 MDM base64 置为空串），用于「只加载仓库内 fixture」的测试。

> [!NOTE]
> **它不只是测试设施**：`LoaderOverrides` 正是 **profile-v2 得以工作的机制**。`codex-rs/cli/src/main.rs:1947-1959` 的 `loader_overrides_for_profile_at_codex_home()` 在 `--profile <name>` 存在时构造 `LoaderOverrides { user_config_path: Some(<name>.config.toml 的路径), user_config_profile: Some(name), ..Default::default() }`——即「第二用户层」（§1 ③）不是加载器里的一段特判，而是通过这个注入点把用户层重定向出来的。
>
> 调试推论：如果「我的 `config.toml` 明明写了却没生效」而层栈里根本看不到用户层，先查是不是有人塞了 `LoaderOverrides`。 <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->

### 仅 debug 构建生效的两个环境变量（E1）

`codex-rs/app-server/src/main.rs:17-18` 定义了两个测试钩子（注释原文：「Debug-only test hook: lets integration tests point the server at a temporary managed config file without writing to /etc.」）：

| 环境变量 | 作用 | 读取点 |
| ---- | ---- | ---- |
| `CODEX_APP_SERVER_MANAGED_CONFIG_PATH` | 把 `managed_config.toml` 指向临时文件 | `codex-rs/app-server/src/main.rs:131-143` |
| `CODEX_APP_SERVER_DISABLE_MANAGED_CONFIG` | 取值 `1`/`true`/`TRUE`/`yes`/`YES` 时关闭托管配置 | `codex-rs/app-server/src/main.rs:119-129` |

两者的读取都包在 `#[cfg(debug_assertions)]` 里，**release 构建中设置它们完全无效**（函数直接返回 `None` / `false`）。

---

## 3. 配置规模（E1/E2）

| 指标 | 数量 | 证据 |
| ---- | ---: | ---- |
| `config.toml` **可被 schema 校验的**顶层键 | **93** | E2：`codex-rs/core/config.schema.json` 的 `properties` | <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->
| `ConfigToml` **仍会被 serde 接受的**顶层字段 | **96** | E2：`codex-rs/config/src/config_toml.rs` 的 `pub` 字段 |
| 其中**刻意对 schema 隐藏**的废弃/移除键 | **3** | E2：带 `#[schemars(skip)]` |
| `codex-config` crate `src/` 行数 | 21,167 | E1：`find codex-rs/config/src -type f \| xargs wc -l`（**全部文件**口径） |
| 同上，**仅 `.rs`** 口径 | 21,034 | E1：`git ls-files 'codex-rs/config/**/*.rs' \| xargs wc -l`。[`crate_map.md`](./crate_map.md) §3 用的是这个口径，两处数字不同**不是矛盾**，差额 133 行来自 `src/` 下的非 `.rs` 文件 |
| `codex-rs/core/src/config/config_tests.rs` 行数 | 12,127 | E1：`wc -l` |

> [!IMPORTANT]
> **93 还是 96？两个数字都对，但单说哪一个都不完整。**
>
> - **93** = `codex-rs/core/config.schema.json` 顶层 `properties` 的键数，且 schema 声明了 `additionalProperties: false`——这是**编辑器与 strict-config 会校验的集合**。
> - **96** = `ConfigToml` 的 `pub` 字段数——这是 **serde 实际会接受的集合**。
> - **差集恰好是 3 个带 `#[schemars(skip)]` 的字段**，全部是废弃或已移除的键：
>   - `js_repl_node_path`、`js_repl_node_module_dirs`（`codex-rs/config/src/config_toml.rs:300-306`，注释均为 `/// Deprecated: ignored.`）
>   - `experimental_thread_store_endpoint`（`codex-rs/config/src/config_toml.rs:413-416`，注释：`/// Removed. Former remote thread-store endpoint setting kept only so we can fail fast instead of silently falling back to local persistence.`）
>
> 即：**保留字段是为了「快速失败」而不是「静默忽略」**，同时又不希望它们出现在给用户看的 schema 里。写「93 个配置键」时请注明这是 schema 口径。

> 复核命令：
> ```bash
> python3 -c "import json;print(len(json.load(open('codex-rs/core/config.schema.json'))['properties']))"
> ```

顶层键的**若干示例**：`agents`、`approval_policy`、`chatgpt_base_url`、`default_permissions`、`features`、`hooks`、`history`、`model_providers`、`notify`、`otel`、`sqlite_home`、`experimental_*`（共 **10** 个）……

> [!NOTE]
> **本文刻意不复制完整键清单。** 上一版列了「按字母序前 40 个」，既漏了键、又把 `experimental_*` 数错成 7（实为 10，与 [实验性表面](./experimental_surfaces.md) §「experimental_ 前缀实测」一致）。**维护一份易漂移的复制品没有价值——完整清单请查 `codex-rs/core/config.schema.json`。**

> [!NOTE]
> **勘误（E1）**：第一版称 `codex-rs/core/src/config/config_tests.rs` 是「全仓第 2 大文件」。按**跟踪文件的总行数**排（`git ls-files | xargs wc -l | sort -rn`），它是**第 5**：前四位是 `codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.schemas.json`（22,635）、同目录的 `codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json`（20,393）、`codex-rs/Cargo.lock`（16,230）、`codex-rs/tui/src/bottom_pane/chat_composer.rs`（12,616）。它确实是**最大的 `.rs` 文件之一**（仅次于 `codex-rs/tui/src/bottom_pane/chat_composer.rs`），但「全仓第 2」这个口径不成立。

---

## 4. 模块版图

### `codex-config` crate（E1，来自 `ls`）

| 领域 | 文件 |
| ---- | ---- |
| **层栈核心** | `codex-rs/config/src/state.rs`（`ConfigLayerEntry` / `ConfigLayerStack` / `LoaderOverrides`，含 `effective_config`、`origins`、`get_layers`）、`codex-rs/config/src/config_layer_source.rs`、`codex-rs/config/src/merge.rs`、`codex-rs/config/src/overrides.rs`、`loader/` |
| **加载器** | `codex-rs/config/src/loader/mod.rs`（`load_config_layers_state`，加载顺序与信任门控的实现）、`codex-rs/config/src/loader/layer_io.rs`、`codex-rs/config/src/loader/macos.rs`（**平台专属**）、`codex-rs/config/src/loader/README.md`、`codex-rs/config/src/loader/tests.rs` |
| **TOML 结构** | `codex-rs/config/src/config_toml.rs`、`codex-rs/config/src/profile_toml.rs`（**死类型**，见 §1）、`codex-rs/config/src/permissions_toml.rs`、`codex-rs/config/src/types.rs`、`codex-rs/config/src/schema.rs` |
| **严格模式** | `codex-rs/config/src/strict_config.rs`（未知字段拒绝） |
| **约束与需求** | `codex-rs/config/src/config_requirements.rs`、`codex-rs/config/src/constraint.rs`、`codex-rs/config/src/requirements_exec_policy.rs`、`codex-rs/config/src/mcp_requirements.rs`、`requirements_layers/`（`codex-rs/config/src/requirements_layers/layer.rs`、`codex-rs/config/src/requirements_layers/stack.rs`、`codex-rs/config/src/requirements_layers/hooks.rs`、`codex-rs/config/src/requirements_layers/permissions.rs`、`codex-rs/config/src/requirements_layers/rules.rs`） |
| **线程级配置** | `codex-rs/config/src/thread_config.rs` + `thread_config/`（`codex-rs/config/src/thread_config/remote.rs`、`proto/`） |
| **MCP** | `codex-rs/config/src/mcp_types.rs`、`codex-rs/config/src/mcp_edit.rs`、`codex-rs/config/src/mcp_requirements.rs` |
| **编辑能力** | `codex-rs/config/src/plugin_edit.rs`、`codex-rs/config/src/marketplace_edit.rs`、`codex-rs/config/src/mcp_edit.rs` |
| **云配置** | `codex-rs/config/src/cloud_config_bundle.rs`、`codex-rs/config/src/cloud_config_layers.rs` |
| **钩子与技能** | `codex-rs/config/src/hook_config.rs`、`codex-rs/config/src/skills_config.rs` |
| **执行环境** | `codex-rs/config/src/shell_environment_policy.rs` |
| **TUI** | `codex-rs/config/src/tui_keymap.rs` |
| **诊断与溯源** | `codex-rs/config/src/diagnostics.rs`、`codex-rs/config/src/fingerprint.rs`、`codex-rs/config/src/key_aliases.rs` |
| **项目识别** | `codex-rs/config/src/project_root_markers.rs` |
| **测试基建** | `codex-rs/config/src/test_support.rs` + 各 `*_tests.rs` |
| 其他 | `codex-rs/config/src/host_name.rs` |

> [!TIP]
> `codex-rs/config/src/loader/README.md` 是仓库内少有的模块级说明文档，读配置加载**必须**先看——它同时给出了公开 API 面、优先级模型、内部文件分工。本文第一版的 MDM 错误就是跳过它造成的。

### `core/src/config/`（E1）

| 文件 | 职责 |
| ---- | ---- |
| `codex-rs/core/src/config/mod.rs` | 配置主体（含 `find_codex_home`（见 §6）、`CONFIG_PROFILE_V2_SUFFIX`、`sqlite_home` 解析、遗留 profile 拒绝逻辑） |
| `codex-rs/core/src/config/schema.rs` + `codex-rs/core/src/config/schema.md`（**与 `codex-rs/config/src/schema.rs` 同名不同文件**） | JSON Schema 生成 |
| `codex-rs/core/src/config/schema_tests.rs` | schema 防漂移测试（见 §7） |
| `codex-rs/core/src/bin/config_schema.rs` | `codex-write-config-schema` 二进制入口（20 行） |
| `codex-rs/core/src/config/permissions.rs`（**与 `codex-rs/config/src/permissions_toml.rs` 无关**）、`codex-rs/core/src/config/resolved_permission_profile.rs`、`codex-rs/core/src/config/permission_profile_catalog.rs` | 权限档 |
| `codex-rs/core/src/config/auth_keyring.rs` | 钥匙串认证 |
| `codex-rs/core/src/config/otel.rs` | 遥测配置 |
| `codex-rs/core/src/config/network_proxy_spec.rs` | 网络代理 |
| `codex-rs/core/src/config/managed_features.rs` | 受管特性 |
| `codex-rs/core/src/config/agent_roles.rs` | 智能体角色 |
| `codex-rs/core/src/config/edit.rs` + `edit/` | 配置编辑 |
| `codex-rs/core/src/config/requirements.rs` | 需求约束 |
| `codex-rs/core/src/config/config_loader_tests.rs` | 加载器行为测试（含 `managed_preferences_take_highest_precedence`） |

---

## 5. `requirements.toml`：管理员的强制约束

`docs/config.md:11-15` 给出了一个关键事实（E2）：

> Admins can set top-level `allow_managed_hooks_only = true` in `requirements.toml` to ignore user, project, and session hook configs while still allowing managed hooks from requirements and managed config layers. This setting is only supported in `requirements.toml`; putting it in `config.toml` does not enable managed-hooks-only mode. <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->

> [!NOTE]
> **勘误**：第一版在此处写「这印证了 §1 的推论：config.toml 的层级模型里管理策略是最低优先级，所以真正的强制约束必须放在 requirements.toml」。这个「印证」建立在 §1 的错误结论上，**不成立**——MDM 下发的 config.toml 实际是最高优先级（50）。
>
> 正确的解释是：`requirements.toml` 与配置层是**两套并行机制**，不是「因为配置层管不住所以另起一套」。
> - 配置层给的是**默认值/覆盖值**，用户仍可在 TUI 与 VS Code 里按轮次覆盖（`codex-rs/config/src/loader/mod.rs:369-373` 的注释明说了这一点）。
> - `requirements.toml` 给的是**不可协商的约束**（`ConfigRequirements`），并且有自己的一条加载链（`codex-rs/config/src/loader/mod.rs:82-91`：system → cloud → legacy → admin managed preferences，`compose_requirements()` 合并）。
> - `allow_managed_hooks_only` 这类开关**只在 requirements 通道生效**，正是因为它约束的是「谁可以提供 hook」，而不是「hook 的默认值是什么」。
> - 遗留的 `managed_config.toml` 会被**同时**当作配置层（40/50）与 requirements 层使用（`codex-rs/config/src/loader/mod.rs:189` 调用 `requirements_layers_from_legacy_scheme`，定义在 `:744`），这是向后兼容的桥。

### 它不参与 0–50 的优先级体系（E3）

> [!IMPORTANT]
> **`requirements.toml` 不是「第 51 层」，它根本不在那套优先级里。**

- **字段集是独立的**：`ConfigRequirementsToml`（`codex-rs/config/src/config_requirements.rs:875-909`）有 **31 个顶层字段**，**不是 `ConfigToml` 的子集**。语义也不同——多数字段是 `allowed_*`（允许集合）或强制值，而不是「默认值」。
- **合成是独立的**：requirements 层按自己的升序合成——system → 企业云 bundle → legacy 翻译层 → macOS MDM（最高，`codex-rs/config/src/loader/mod.rs:82-91`），由 `compose_requirements()` 合并。
- **施加是后置的**：合成结果作为 `ConfigLayerStack::new(layers, requirements, requirements_toml)` 的第二/三参数传入（`codex-rs/config/src/loader/mod.rs:430-434`），再通过 `apply_requirement_constrained_value`（`codex-rs/core/src/config/mod.rs:2121`）/ `Constrained<T>` 施加在**已经合并完的**配置之上——**凌驾于整个配置栈之上**，而不是参与合并。

`codex-rs/config/src/requirements_layers/stack.rs:1-14` 的模块注释列出了 **4 个不走普通 TOML merge** 的字段（因为「raw TOML replacement would break」其语义）：

| 字段 | 特殊语义 |
| ---- | ---- |
| `remote_sandbox_config` | 在每层内部先求值再合并 |
| `rules.prefix_rules` | 高优先级规则**追加在前** |
| `hooks` | 高优先级事件组追加在前，遇到 active managed-dir 冲突时 **fail closed** |
| `permissions.filesystem.deny_read` | 跨层**并集**，高优先级在前 |

> [!WARNING]
> **legacy 翻译路径会隐式放宽约束。**
> `managed_config.toml` 被翻译成 requirements 时（`codex-rs/config/src/loader/mod.rs` 的 `legacy_requirements_to_toml_value`），有两处回填会让约束**比原样更宽**：
> - `:813-824`：回填 `allowed_sandbox_modes` 时**总会先塞入 `ReadOnly`**，再追加实际要求的模式。代码注释给了理由：「Allowing read-only is a requirement for Codex to function correctly.」
> - `:803-812`：`approvals_reviewer == ApprovalsReviewer::AutoReview` 时，`allowed_approvals_reviewers` 会额外追加 `ApprovalsReviewer::User`。
>
> 后果：**从 `managed_config.toml` 迁移过来的约束，未必等价于直接写在 `requirements.toml` 里的同名约束。** 管理员迁移时应显式重写 `allowed_*` 列表，不要依赖翻译层。

相关实现：`codex-rs/config/src/config_requirements.rs`、`codex-rs/config/src/requirements_exec_policy.rs`、`codex-rs/config/src/mcp_requirements.rs`、`requirements_layers/`、`codex-rs/core/src/config/requirements.rs`。macOS 侧的 requirements 键是 `com.openai.codex` 域的 `requirements_toml_base64`（`codex-rs/config/src/loader/macos.rs:22`）。

> **未验证**（无等级）：`requirements.toml` 各字段的**逐个语义**与取值范围（字段**数量与名称**已核实，见上）。

---

## 6. `CODEX_HOME` 解析（E3）

配置目录由 `CODEX_HOME` 环境变量决定，未设置时默认 `~/.codex`。**权威实现在 `codex-rs/utils/home-dir/src/lib.rs:13`**：

| 情况 | 行为 |
| ---- | ---- |
| CODEX_HOME 已设置且非空 | 路径**必须存在且是目录**，会被 canonicalize；不满足则返回错误（`codex-rs/utils/home-dir/src/lib.rs:20-49`，canonicalize 在 `:43-48`） |
| `CODEX_HOME` 未设置或为空 | 回退到 `~/.codex`，**不校验目录是否存在** |

错误信息区分了**四种**失败：

| 失败 | 信息 | 位置 |
| ---- | ---- | ---- |
| 路径不存在 | `CODEX_HOME points to {val:?}, but that path does not exist` | `codex-rs/utils/home-dir/src/lib.rs:29` |
| 其他读取 IO 错误 | `failed to read CODEX_HOME {val:?}: {err}` | `:33` |
| 路径存在但不是目录 | `CODEX_HOME points to {val:?}, but that path is not a directory` | `:40` |
| canonicalize 失败 | `failed to canonicalize CODEX_HOME {val:?}: {err}` | `:46` |

> [!TIP]
> `codex-rs/core/src/config/mod.rs:4578` 也有一个 `pub fn find_codex_home`，但**它是薄委托**——函数体只有一行 `codex_utils_home_dir::find_codex_home()`。两处不是重复实现。

### `sqlite_home` 的三级解析（E3）

`CODEX_HOME` 决定配置目录，但**数据库目录是单独解析的**，且规则与直觉相反。`codex-rs/core/src/config/mod.rs:3892-3897`：

```rust
let sqlite_home = cfg
    .sqlite_home            // ① config.toml 的 sqlite_home
    .as_ref()
    .cloned()
    .or(sqlite_home_env)    // ② $CODEX_SQLITE_HOME（:3885 resolve_sqlite_home_env）
    .unwrap_or_else(|| codex_home.clone());   // ③ 回退到 CODEX_HOME
```

| 优先级 | 来源 |
| ---: | ---- |
| 1（最高） | `config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 的 `sqlite_home` |
| 2 | 环境变量 `$CODEX_SQLITE_HOME`（相对路径按 `resolved_cwd` 解析，见 `:3885` 的 `resolve_sqlite_home_env`） |
| 3（回退） | `codex_home` 本身 |

> [!WARNING]
> **配置文件压过环境变量，与大多数工具相反。** 在绝大多数 CLI 里环境变量优先级更高；这里恰好倒过来。所以「我导出了 `CODEX_SQLITE_HOME` 但数据库还在老地方」的答案通常是：某一层 `config.toml` 里已经写了 `sqlite_home`。两者同时存在时会推送启动警告，注意看启动输出。 <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->

**而且它可以被 requirements 覆盖。** 这是 §5「requirements 是不可协商约束」的具体例证：`ConfigRequirementsToml::sqlite_home`（`codex-rs/config/src/config_requirements.rs:876`，该结构体的**第一个**字段）给出精确值时，会压过上面整条链。`codex-rs/core/src/config/mod.rs:3886-3891` 调用 `requirements::push_sqlite_home_env_override_warning(...)`，实现（`codex-rs/core/src/config/requirements.rs:126-133`）会同时发一条 `tracing::warn!` 和一条启动警告：

> "Environment value for `$CODEX_SQLITE_HOME` is overridden by the required `sqlite_home` value {value:?} from {source}."

即完整的四级链条：**requirements 的 `sqlite_home` > `config.toml` 的 `sqlite_home` > `$CODEX_SQLITE_HOME` > `CODEX_HOME`**。 <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 -->

---

## 7. Schema 生成与防漂移（E2）

`codex-rs/core/src/config/schema.md` 说明（E2）：

> We generate a JSON Schema for `~/.codex/config.toml` from the `ConfigToml` type and commit it at `codex-rs/core/config.schema.json` for editor integration.

```
改 ConfigToml 或任何嵌套配置类型
        ↓
just write-config-schema                       （justfile:171-172）
  = cargo run -p codex-core --bin codex-write-config-schema
                                               （bin 定义：codex-rs/core/src/bin/config_schema.rs）
        ↓
codex-rs/core/config.schema.json 更新
        ↓
与 Rust 改动放进同一个 change
```

这是 `AGENTS.md` **顶部规则列表**里的明文要求（关键词 `just write-config-schema` / `ConfigToml or nested config types`）。schema 文件被提交进仓库的目的是**编辑器集成**（写 `config.toml` <!-- ref-exempt: 运行时用户配置文件，非仓库内文件 --> 时有补全与校验）。

### 防漂移不只是人工约定：有自动化测试，而且校验两次

> [!IMPORTANT]
> **`codex-rs/core/src/config/schema_tests.rs:13-55` 的 `config_schema_matches_fixture()` 会在 CI 上拦住忘记跑 `just write-config-schema` 的改动。** 这与 §1 里那两份需要手工同步的层来源枚举形成对照——后者**没有**任何自动化保障。

该测试做**两道**校验：

1. **规范化 JSON 比较**（`:16-36`）：把仓库内的 `codex-rs/core/config.schema.json` 与当场从 `ConfigToml` 生成的 schema 都过一遍 `canonicalize()`（消除键序等无关差异）再比对。不一致时用 `similar::TextDiff` 打印 unified diff 并 `panic!`，提示语明确写着：「Run `just write-config-schema` to overwrite with your changes.」
2. **逐字节比较**（`:38-55`）：把生成结果写到临时目录，再与仓库内 fixture 做 `assert_eq!`（Windows 下先归一化 `\r\n`）。注释指明这是为了「Make sure the version in the repo matches exactly」。

第 1 道保证**语义**不漂移，第 2 道保证**格式**（缩进、键序、尾随换行）也不漂移——这样 `codex-rs/core/config.schema.json` 的 diff 才是可读的。

---

## 8. 改动本区域的注意事项（E2）

| 事项 | 依据 |
| ---- | ---- |
| **配置加载是 `AGENTS.md` `## Code Review Rules` → `### Breaking changes` 点名的高风险改动面** | 该清单：app-server APIs、`rawResponseItem/*`、CLI parameters、**configuration loading**、resuming sessions from existing rollouts |
| 改 `ConfigToml` 或嵌套类型必须跑 `just write-config-schema` | AGENTS.md 顶部规则列表，关键词 `just write-config-schema` |
| **改优先级数值或增删层要同时改两处 `ConfigLayerSource`，而且没有任何测试会捕捉到不同步** | `codex-rs/config/src/config_layer_source.rs` + `codex-rs/app-server-protocol/src/protocol/v2/config.rs`，桥接在 `codex-rs/app-server/src/config_layer.rs`；`verify_layer_ordering` 只查「已排序」不查「值正确」（§1） |
| 新增配置层或改优先级会影响所有用户的既有配置，需极度谨慎 | §1 的优先级是行为契约 |
| 动 cwd/tree/repo 层时要确认**两道闸门**都仍然生效 | §2；绕过 `disabled_reason` 等于让不受信目录的配置生效，动 `PROJECT_LOCAL_CONFIG_DENYLIST` 等于让仓库内容决定凭证去向 |
| 给项目层新增「敏感」配置键时，同步评估是否要加进黑名单 | `codex-rs/config/src/loader/mod.rs:60-76`；判据是注释里的那句「should not get to choose where a user's credentials are sent or which local commands are run」 |
| `codex-rs/core/src/config/config_tests.rs` 有 12,127 行，**必须分段读取** | 最大的 `.rs` 文件之一 |
| **不要靠读 `codex-rs/config/src/loader/mod.rs` 的文档注释确认层序或路径** | §2「本文件的注释不可信」：admin 层位置与 cwd 路径两处均与实现不符 |
| 不要为静态定义的值写测试 | `AGENTS.md` 顶部规则列表，关键词 `Do not add tests for values that are statically defined` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 93 个配置键的逐个语义 | E2（仅键名） | `codex-rs/core/config.schema.json`、developers.openai.com |
| 层合并的具体算法（深合并还是浅覆盖） | E2 | `codex-rs/config/src/merge.rs`（`codex-rs/config/src/loader/README.md` 称其为 "recursive TOML merge"） |
| 目录信任状态本身是怎么判定与持久化的 | E1 | `codex-rs/config/src/loader/mod.rs` 的 `project_trust_context`、`codex-rs/config/src/project_root_markers.rs` |
| `requirements.toml` 各字段的逐个语义（字段数量与名称已核实，见 §5） | E2（仅字段名） | `codex-rs/config/src/config_requirements.rs`、`requirements_layers/` |
| 线程级配置层（`thread_config`）的注入时机 | E1 | `codex-rs/config/src/thread_config.rs`、`codex-rs/config/src/loader/mod.rs` 的 `insert_layer_by_precedence` |
| 权限档（permission profile）的解析 | E1 | `codex-rs/core/src/config/resolved_permission_profile.rs` |
| 云配置包的下发链路 | E1 | `codex-rs/config/src/cloud_config_bundle.rs`、`codex-cloud-config` crate |
| 严格模式（`strict_config`）的完整校验规则 | E1 | `codex-rs/config/src/strict_config.rs` |
| 配置指纹与诊断的用途 | E1 | `codex-rs/config/src/fingerprint.rs`、`codex-rs/config/src/diagnostics.rs` |

---

## 10. 相关文档

- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 与落盘内容
- [智能体核心循环](./core_agent_loop.md) §5 — 审批与沙箱策略类型
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱策略的执行侧
- [认证与模型接入](./auth_and_providers.md) — 凭证存储配置
- [app-server 协议](./app_server_protocol.md) — `ConfigLayerSource` 的 wire 侧副本
- [可观测性](./observability.md) — 遥测配置项
