---
title: Codex 配置体系
summary: 描述 codex-config 的八层配置来源与精确优先级数值、93 个顶层配置键的规模、config.schema.json 的生成与防漂移机制、requirements.toml 的管理员约束能力，以及配置加载作为高风险改动面的注意事项。
keywords: codex | config | config-layer | precedence | config-toml | json-schema | requirements-toml
scope: codex-rs/config 与 codex-rs/core/src/config 的配置加载体系
related_files: codex-rs/config/src/config_layer_source.rs | codex-rs/config/src/lib.rs | codex-rs/core/src/config/mod.rs | codex-rs/core/src/config/schema.md | codex-rs/core/config.schema.json | docs/config.md | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/core_agent_loop.md
verified_at: 2026-08-03
---

# 配置体系

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-config`（21,034 行）+ `codex-rs/core/src/config/`
> **证据等级**: 层级优先级与配置键数量为 E3/E4（读取源码与生成的 schema）；各配置项语义未逐条解读

> [!NOTE]
> **面向用户的配置参考在外部站点**（`docs/config.md` 只有 15 行，正文指向 developers.openai.com）。本文只讲**配置体系的机制**——层级、优先级、生成链路——不复述配置项清单。

---

## 1. 八层配置来源与精确优先级（E3）

`codex-rs/config/src/config_layer_source.rs:6` 定义了 `ConfigLayerSource`，`:31-48` 给出了每层的数值优先级。**数值越大优先级越高，高优先级覆盖低优先级**（`:29-30` 的文档注释明文说明）。

| 优先级 | 层 | 变体 | 载体 |
| ---: | ---- | ---- | ---- |
| 0 | MDM 管理策略 | `Mdm { domain, key }` | 移动设备管理下发 |
| 10 | 主机级系统配置 | `System { file }` | 系统级文件 |
| 15 | 企业云配置包 | `EnterpriseManaged { id, name }` | 企业云下发 |
| 20 | 用户配置 | `User { file, profile: None }` | `~/.codex/config.toml` |
| **21** | 用户配置 + 选定 profile | `User { file, profile: Some(_) }` | 同上，附加 profile |
| 25 | 项目配置 | `Project { dot_codex_folder }` | 项目的 `.codex` 目录 |
| 30 | 会话覆盖 | `SessionFlags` | 本次会话的命令行覆盖 |
| 40 | 遗留管理配置（文件） | `LegacyManagedConfigTomlFromFile { file }` | 遗留路径 |
| 50 | 遗留管理配置（MDM） | `LegacyManagedConfigTomlFromMdm` | 遗留路径 |

### 三个容易踩的点

> [!WARNING]
> **① MDM 优先级最低（0），不是最高。**
> 直觉上"管理策略应该压倒一切"，但在这套模型里 `Mdm` 是**基线**，会被用户、项目、会话配置逐层覆盖。管理员要强制约束必须走 `requirements.toml`（见 §4），而不是靠配置层级。

> [!WARNING]
> **② 两个 legacy 层（40/50）优先级高于 SessionFlags（30）。**
> 这意味着遗留管理配置**会覆盖本次会话的命令行覆盖**。这很可能是有意为之的兼容行为，但对调试是个陷阱——"我明明在命令行指定了却不生效"的答案可能在这里。

> [!NOTE]
> **③ 带 profile 的用户配置是 21，比不带的 20 高 1。**
> 同一个文件因是否选中 profile 而产生两个相邻优先级，说明 profile 是在用户层**内部**叠加的，而不是独立一层。

### 排序语义

`config_layer_source.rs:52-57` 实现了 `PartialOrd`，注释明确：

> "Compares `ConfigLayerSource` by precedence, so `A < B` means settings from layer `A` will be overridden by settings from layer `B`."

配套类型：`ConfigLayerMetadata { name, version }`、`ConfigLayer { name, version, ... }` —— **每层都带版本号**，说明配置层有溯源能力。

---

## 2. 配置规模（E4）

| 指标 | 数量 |
| ---- | ---: |
| `config.toml` 顶层配置键 | **93** |
| `codex-config` crate 行数 | 21,034 |
| `core/src/config/config_tests.rs` 行数 | 12,127（全仓第 2 大文件） |

> 复核命令：
> ```bash
> python3 -c "import json;print(len(json.load(open('codex-rs/core/config.schema.json'))['properties']))"
> ```

顶层键的一部分（按字母序前 40 个）：`agents`、`allow_login_shell`、`analytics`、`approval_policy`、`approvals_reviewer`、`apps`、`audio`、`auto_review`、`chatgpt_base_url`、`compact_prompt`、`debug`、`default_permissions`、`desktop`、`developer_instructions`、`experimental_*`（7 个）、`features`、`feedback`、`file_opener`、`ghost_snapshot`、`hide_agent_reasoning`、`history`、`hooks` ……

> **完整清单请查 `codex-rs/core/config.schema.json`**，不要抄本文。

---

## 3. 模块版图

### `codex-config` crate（E4）

| 领域 | 文件 |
| ---- | ---- |
| **层级与合并** | `config_layer_source.rs`、`merge.rs`、`overrides.rs`、`loader/` |
| **TOML 结构** | `config_toml.rs`、`profile_toml.rs`、`permissions_toml.rs` |
| **约束与需求** | `config_requirements.rs`、`constraint.rs`、`requirements_exec_policy.rs`、`mcp_requirements.rs` |
| **MCP** | `mcp_types.rs`、`mcp_edit.rs`、`mcp_requirements.rs` |
| **编辑能力** | `plugin_edit.rs`、`marketplace_edit.rs`、`mcp_edit.rs` |
| **云配置** | `cloud_config_bundle.rs`、`cloud_config_layers.rs` |
| **钩子** | `hook_config.rs` |
| **诊断与溯源** | `diagnostics.rs`、`fingerprint.rs`、`key_aliases.rs` |
| **项目识别** | `project_root_markers.rs` |
| 其他 | `host_name.rs` |

`loader/` 下有 `layer_io.rs`、`macos.rs`（**平台专属加载逻辑**）、`README.md`。

> [!TIP]
> `codex-rs/config/src/loader/README.md` 是仓库内少有的模块级说明文档，读配置加载前值得先看。

### `core/src/config/`（E4）

| 文件 | 职责 |
| ---- | ---- |
| `mod.rs` | 配置主体（含 `find_codex_home`，见 §5） |
| `schema.rs` + `schema.md` | JSON Schema 生成 |
| `permissions.rs`、`resolved_permission_profile.rs`、`permission_profile_catalog.rs` | 权限档 |
| `auth_keyring.rs` | 钥匙串认证 |
| `otel.rs` | 遥测配置 |
| `network_proxy_spec.rs` | 网络代理 |
| `managed_features.rs` | 受管特性 |
| `agent_roles.rs` | 智能体角色 |
| `edit.rs` + `edit/` | 配置编辑 |
| `requirements.rs` | 需求约束 |

---

## 4. `requirements.toml`：管理员的强制约束

`docs/config.md:9-14` 给出了一个关键事实（E2）：

> Admins can set top-level `allow_managed_hooks_only = true` in `requirements.toml` to ignore user, project, and session hook configs while still allowing managed hooks from requirements and managed config layers.
>
> **This setting is only supported in `requirements.toml`; putting it in `config.toml` does not enable managed-hooks-only mode.**

**这印证了 §1 的推论**：config.toml 的层级模型里管理策略是最低优先级，所以真正的强制约束必须放在 requirements.toml 这个**独立机制**里。

相关实现：`config_requirements.rs`、`requirements_exec_policy.rs`、`mcp_requirements.rs`、`core/src/config/requirements.rs`。

> **未验证**（E1）：`requirements.toml` 支持的完整字段集与它与配置层的交互方式。

---

## 5. `CODEX_HOME` 解析（E3）

配置目录由 `CODEX_HOME` 环境变量决定，未设置时默认 `~/.codex`。**权威实现在 `codex-rs/utils/home-dir/src/lib.rs:13`**：

| 情况 | 行为 |
| ---- | ---- |
| CODEX_HOME 已设置且非空 | 路径**必须存在且是目录**，会被 canonicalize；不满足则返回错误（`lib.rs:20-40`） |
| `CODEX_HOME` 未设置或为空 | 回退到 `~/.codex`，**不校验目录是否存在** |

错误信息区分了两种失败：路径不存在时报 `CODEX_HOME points to {val:?}, but that path does not exist`，其他 IO 错误报 `failed to read CODEX_HOME {val:?}: {err}`。

> [!TIP]
> `codex-rs/core/src/config/mod.rs:4578` 也有一个 `pub fn find_codex_home`，但**它是薄委托**——函数体只有一行 `codex_utils_home_dir::find_codex_home()`。两处不是重复实现。

---

## 6. Schema 生成与防漂移

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

这是 `AGENTS.md:35` 的明文要求。schema 文件被提交进仓库的目的是**编辑器集成**（写 `config.toml` 时有补全与校验）。

---

## 7. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **配置加载是 `AGENTS.md:105-110` 点名的高风险改动面** | 与 app-server API、CLI 参数、rollout 恢复并列 |
| 改 `ConfigToml` 或嵌套类型必须跑 `just write-config-schema` | `AGENTS.md:35` |
| `config_tests.rs` 有 12,127 行，**必须分段读取** | 全仓第 2 大文件 |
| 新增配置层或改优先级会影响所有用户的既有配置，需极度谨慎 | §1 的优先级是行为契约 |
| 不要为静态定义的值写测试 | `AGENTS.md:30` |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 93 个配置键的逐个语义 | E4（仅键名） | `codex-rs/core/config.schema.json`、developers.openai.com |
| 层合并的具体算法（深合并还是浅覆盖） | E1 | `codex-rs/config/src/merge.rs` |
| profile 的作用范围与选择机制 | E1 | `config/src/profile_toml.rs` |
| `requirements.toml` 的完整字段集 | E1 | `config/src/config_requirements.rs` |
| 权限档（permission profile）的解析 | E1 | `core/src/config/resolved_permission_profile.rs` |
| 云配置包的下发链路 | E1 | `config/src/cloud_config_bundle.rs`、`codex-cloud-config` crate |
| MDM 在 macOS 上的读取方式 | E1 | `config/src/loader/macos.rs` |
| 配置指纹与诊断的用途 | E1 | `config/src/fingerprint.rs`、`diagnostics.rs` |

---

## 9. 相关文档

- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 与落盘内容
- [智能体核心循环](./core_agent_loop.md) §4 — 审批与沙箱策略类型
- [工具与沙箱](./tools_and_sandbox.md) — 沙箱策略的执行侧
- [认证与模型接入](./auth_and_providers.md) — 凭证存储配置
- [可观测性](./observability.md) — 遥测配置项
