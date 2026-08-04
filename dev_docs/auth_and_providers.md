---
title: Codex 认证与模型接入
summary: 以 codex-protocol 的 AuthMode 枚举（7 个变体）为准描述认证方式，说明 auth.json 的实际结构与路径、cli_auth_credentials_store 的四个取值与 Feature::SecretAuthStorage 的关系、ModelProviderInfo 的完整配置面、WireApi 仅剩 Responses 一个变体的现状、本地模型接入方式，以及两个隐藏的 OAuth 覆盖参数带来的风险。
keywords: codex | auth | login | oauth | pkce | model-provider | wire-api | keyring | credentials | auth-mode
scope: codex-rs/login、protocol/src/auth.rs、model-provider-info 与相关认证凭证存储
related_files: codex-rs/protocol/src/auth.rs | codex-rs/model-provider-info/src/lib.rs | codex-rs/login/src/lib.rs | codex-rs/login/src/auth/storage.rs | codex-rs/keyring-store/src/lib.rs | codex-rs/config/src/types.rs | codex-rs/core/src/config/auth_keyring.rs | codex-rs/features/src/lib.rs | codex-rs/cli/src/main.rs | AGENTS.md
dependencies: dev_docs/config_system.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 认证与模型接入

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 类型定义与字段为 E3；端点为 E3（源码 grep）；认证流程时序为 E1

> [!CAUTION]
> **本文不复述任何凭证的实际值。** 只记录变量名、配置键名、文件路径与端点。测试夹具中的假 token（如 `codex-rs/login/src/token_data_tests.rs` 里的样例）也不引入文档。

> [!IMPORTANT]
> **本文已修订：**
>
> 1. **§1 重建**——初版的认证方式表是**按 `login/src/auth/` 的文件名推导**的，因此漏了两种模式、又把实现文件当成了并列的认证模式。现改为以**权威枚举 `AuthMode`** 为准。
> 2. **§2 补全**——`auth.json` 的结构初版标为 E1 未验证，实际有明确的类型定义。
> 3. **§2 补全**——`cli_auth_credentials_store` 的取值初版完全未说明。
> 4. **§1.3 新增**——两个隐藏的 OAuth 覆盖参数。

---

## 1. 认证方式：以 `AuthMode` 枚举为准（E3）

> [!CAUTION]
> **修订说明（原文方法有误）**：初版的表格是从 `codex-rs/login/src/auth/` **目录下的文件名**推导出来的。这导致两类问题：
>
> - **漏掉了两个变体**：`ChatgptAuthTokens` 与 `Headers`（它们没有同名实现文件）。
> - **把实现文件当成了并列的认证模式**：例如 "External Bearer"（`codex-rs/login/src/auth/external_bearer.rs`）是一个实现文件，不是 `AuthMode` 的一个变体。
>
> 权威定义是 **`codex-rs/protocol/src/auth.rs:9-34` 的 `pub enum AuthMode`**，共 **7 个变体**。以下表格按该枚举重建。

| `AuthMode` 变体 | serde 线格式 | strum `Display` | 文档注释（原文） | 典型入口 |
| ---- | ---- | ---- | ---- | ---- |
| `ApiKey` | `apikey` | **`ApiKey`** ⚠️ | *"OpenAI API key provided by the caller and stored by Codex."* | `codex login --with-api-key`（`run_login_with_api_key`） |
| `Chatgpt` | `chatgpt` | **`Chatgpt`** ⚠️ | *"ChatGPT OAuth managed by Codex (tokens persisted and refreshed by Codex)."* | `codex login` → Sign in with ChatGPT |
| **`ChatgptAuthTokens`** | `chatgptAuthTokens` | `chatgptAuthTokens` | *"ChatGPT auth tokens supplied by an external host application."* | **宿主应用注入**（非 CLI 交互）；协议方法 `account/chatgptAuthTokens/refresh` |
| **`Headers`** | `headers` | `headers` | *"Codex backend auth supplied as request headers."* | **由请求头承载的后端认证**，不经本地登录流程 |
| `AgentIdentity` | `agentIdentity` | `agentIdentity` | *"Programmatic Codex auth backed by a registered Agent Identity."* | 配合 `codex-agent-identity` |
| `PersonalAccessToken` | `personalAccessToken` | `personalAccessToken` | *"Programmatic Codex auth backed by a personal access token."* | 程序化接入 |
| `BedrockApiKey` | `bedrockApiKey` | `bedrockApiKey` | *"Amazon Bedrock bearer token managed by Codex."* | 配合 `codex-aws-auth` |

> [!IMPORTANT]
> **勘误：上一稿把 serde 与 strum 合并成一列"线格式（serde/strum）"，掩盖了两者不一致的两行。** 两套属性是**各自独立**的（`codex-rs/protocol/src/auth.rs:7-33`）：
>
> - 枚举级只有 `#[serde(rename_all = "lowercase")]`，**没有** strum 的 `serialize_all`；
> - 变体级上，后 5 个变体**同时**带 `#[serde(rename = "...")]` 与 `#[strum(serialize = "...")]` 且取值相同；
> - **`ApiKey` 与 `Chatgpt` 两个变体没有任何变体级属性**。于是 serde 走 `rename_all = "lowercase"` 得到 `apikey` / `chatgpt`，而 strum 的 `Display` 因为拿不到任何重写指示，**直接输出变体名 `ApiKey` / `Chatgpt`**（strum 不读 serde 属性）。
>
> 也就是说：**同一个值经 `serde_json` 序列化和经 `to_string()` 打印，前两行会得到不同的字符串。** 日志/错误信息里出现 `ApiKey` 而配置或协议里是 `apikey`，两者指同一个东西——排查时别当成两种模式。

`AuthMode` 上还有辅助方法，例如 `has_chatgpt_account()`（`:37` 起）——**`Chatgpt`、`ChatgptAuthTokens`、`PersonalAccessToken` 三者被视为"有 ChatGPT 账号"**。

> [!NOTE]
> **两个补回的变体值得特别注意**：`ChatgptAuthTokens` 与 `Headers` 都是**由外部注入凭证**的模式，不走 `codex login` 交互流程。做认证相关改动时，只测 CLI 登录路径会漏掉它们。

### 1.1 `login/src/auth/` 下的实现文件（E1：目录清单）

这些是**实现**，与上面的模式**不是一一对应**：

| 文件 | 承载的能力 |
| ---- | ---- |
| `codex-rs/login/src/auth/access_token.rs` | access token 处理（含从 stdin 读入） |
| `codex-rs/login/src/auth/personal_access_token.rs` | `PersonalAccessToken` |
| `codex-rs/login/src/auth/external_bearer.rs` | 外部 bearer token 的取用（由 provider 配置驱动，**不是独立的 `AuthMode`**） |
| `codex-rs/login/src/auth/bedrock_api_key.rs` | `BedrockApiKey` |
| `codex-rs/login/src/auth/agent_identity.rs` | `AgentIdentity` |
| `storage.rs` | 凭证落盘，见 §2 |
| `codex-rs/login/src/auth/revoke.rs` | 撤销 |
| `manager.rs` | 认证管理器（`AuthManager`） |

另有 `codex-rs/login/src/device_code_auth.rs`——**Device Code 是 OAuth 的一种授权流程，不是独立的 `AuthMode` 变体**（它最终仍落到 `Chatgpt`）。

### 1.2 CLI 侧入口函数

`codex-rs/cli/src/main.rs:13-20`：`run_login_with_chatgpt`、`run_login_with_api_key`、`run_login_with_access_token`、`run_login_with_device_code`、`run_login_status`、`run_logout`、`read_api_key_from_stdin`、`read_access_token_from_stdin`。

### 1.3 两个**隐藏的 OAuth 覆盖参数**（E3，修订补入）

`codex login` 有两个 `hide = true` 的参数，`codex login --help` 中**看不到**：

| 参数 | 位置 | 作用 |
| ---- | ---- | ---- |
| `--experimental_issuer <URL>` | `codex-rs/cli/src/main.rs:490-492` | *"EXPERIMENTAL: Use custom OAuth issuer base URL (advanced)"*——**覆盖 OAuth issuer 基址** |
| `--experimental_client-id <CLIENT_ID>` | `codex-rs/cli/src/main.rs:494-496` | *"EXPERIMENTAL: Use custom OAuth client ID (advanced)"*——**覆盖 OAuth client ID** |

> [!WARNING]
> **这是本文覆盖范围内风险最高的一处能力面。** 这两个参数允许把整个 OAuth 授权流程指向**任意 issuer**——包括把用户引向非 OpenAI 的授权端点。它们既隐藏又带 `experimental_` 前缀，说明只面向高级/内部场景。
>
> - **不要**在文档、脚本或教程中向普通用户推荐这两个参数。
> - 审计认证链路时**必须**把它们计入攻击面。
> - 相关的隐藏入口全景见 [`experimental_surfaces.md`](./experimental_surfaces.md) §7.6。

另有一个已废弃的隐藏参数：**`--api-key` 选项**（`main.rs:476-483`），现在只会退出并提示改用 `--with-api-key`。

> **勘误**：上一稿称它是"位置参数"。它不是——`main.rs:476` 起的属性是 `#[arg(long = "api-key", ...)]`，另带 `num_args = 0..=1`、一个空字符串的 `default_missing_value`、一个占位用的 `value_name`、`hide = true` 与标注 `(deprecated)` 的 `help`。也就是**一个带长名的可选值选项**（`num_args = 0..=1` 使 `--api-key` 后可以不跟值）。clap 里位置参数是不写 `long = ...` 的，这一点可以直接区分。

### OAuth 流程要素（E3）

| 要素 | 文件 |
| ---- | ---- |
| PKCE | `codex-rs/login/src/pkce.rs` |
| 本地回调服务器 | `codex-rs/login/src/server.rs` |
| 回调参数解析 | `codex-rs/login/src/callback_params.rs` |
| 成功页面 | `codex-rs/login/src/success_page.rs`、`login/src/assets/` |
| 令牌数据 | `codex-rs/login/src/token_data.rs` |
| 撤销 | `codex-rs/login/src/auth/revoke.rs` |
| 出站代理 | `codex-rs/login/src/outbound_proxy.rs` |

**PKCE + 本地回调服务器 + 成功页面**是标准的 CLI OAuth 形态：起本地 HTTP 服务、浏览器授权后回调、渲染成功页。

> **未验证**（E1）：完整的时序与错误处理分支。入口是 `codex-rs/login/src/lib.rs` 与 `codex-rs/login/src/auth/manager.rs`。

### 相关端点（E3，公开技术信息）

| 端点 | 用途 |
| ---- | ---- |
| `https://auth.openai.com` | 认证主域 |
| `https://auth.openai.com/oauth/token` | 令牌 |
| `https://auth.openai.com/oauth/revoke` | 撤销 |
| `https://auth.openai.com/api/accounts` | 账号 |
| `https://api.openai.com/auth`、`/profile`、`/v1` | API |
| `https://chatgpt.com/backend-api/codex` | ChatGPT 通道 |
| `https://chatgpt.com/codex-backend/agent-identity` | 智能体身份 |

---

## 2. 凭证存储

| 组件 | 位置 | 说明 |
| ---- | ---- | ---- |
| 存储抽象 | `codex-rs/login/src/auth/storage.rs` | 认证态落盘 |
| 系统钥匙串 | `codex-keyring-store`（226 行） | `DefaultKeyringStore`（`lib.rs:49`）、`CredentialStoreError`（`:9`） |
| 密钥抽象 | `codex-secrets`（786 行） | — |
| 配置侧 | `codex-rs/core/src/config/auth_keyring.rs` | 钥匙串后端的解析 |
| 配置键 | `cli_auth_credentials_store` | `codex-rs/core/config.schema.json` 顶层键之一，取值见 §2.2 |

**存储位置在 `CODEX_HOME`（默认 `~/.codex`）下**，以及系统钥匙串。

`ModelProviderInfo` 的 **`requires_openai_auth`** 字段（`codex-rs/model-provider-info/src/lib.rs`，字段本身在 `:137`，注释在 `:132-135`）提到 `auth.json`：

> "Does this provider require an OpenAI API Key or ChatGPT login token? If true, user is presented with login screen on first run, and login preference and token/key are stored in `auth.json`."

> [!NOTE]
> **引用方式修订**：初版把这段注释标为 `:133-137`，实际注释是 `:132-135`、字段声明在 `:137`。行号会随上游改动漂移——**优先按符号名（`requires_openai_auth`）引用**，行号只作辅助。

### 2.1 `auth.json` 的结构（E3，修订补入）

> [!IMPORTANT]
> **修订说明**：初版把 "`auth.json` 的结构" 列在 §9 的 E1 未验证清单里。**它是有明确类型定义的**，无需推断。

`codex-rs/login/src/auth/storage.rs:38` 起：

```rust
/// Expected structure for $CODEX_HOME/auth.json.
#[derive(Deserialize, Serialize, Clone, Debug, PartialEq)]
pub struct AuthDotJson {
    pub auth_mode: Option<AuthMode>,
    #[serde(rename = "OPENAI_API_KEY")]
    pub openai_api_key: Option<String>,
    pub tokens: Option<TokenData>,
    pub last_refresh: Option<DateTime<Utc>>,
    pub agent_identity: Option<AgentIdentityStorage>,
    pub personal_access_token: Option<String>,
    pub bedrock_api_key: Option<BedrockApiKeyAuth>,
    // ...
}
```

要点：

- **文件里显式记录 `auth_mode`**，与 §1 的枚举一一对应。
- **API key 字段的线名是全大写下划线形式**（由 `#[serde(rename = ...)]` 指定），与 Rust 字段名 `openai_api_key` 仅大小写风格不同。
- 每种程序化认证各有独立字段（`agent_identity` / `personal_access_token` / `bedrock_api_key`）。
- `last_refresh` 支撑令牌刷新判定。
- **大部分**字段带 `#[serde(default, skip_serializing_if = "Option::is_none")]`——未使用的模式不会在文件里留下空键。

> [!CAUTION]
> **勘误：上一稿写的"所有敏感字段都带 `skip_serializing_if`"不成立。** `codex-rs/login/src/auth/storage.rs` 里 **API key 那个字段是例外**——它只有一个 `#[serde(rename = ...)]` 属性，**既没有 `default` 也没有 `skip_serializing_if`**（`:44-45`）；相邻的 `auth_mode`（`:41-42`）才是带 `#[serde(default, skip_serializing_if = "Option::is_none")]` 的那种写法。
>
> 后果很具体：**即使没有配置 API key，序列化 `auth.json` 时也会写出一个值为 `null` 的该键**。所以"文件里出现这个键"并不代表"存了凭证"，排查时别据此下结论。
>
> 这类"逐字段属性不一致"是最容易被概括掉的细节——**看到"所有字段都……"这类全称判断，应逐字段核对而不是抽查一两个。**

路径构造（`storage.rs:150-151`）：

```rust
pub(super) fn get_auth_file(codex_home: &Path) -> PathBuf {
    codex_home.join("auth.json")
}
```

即 **`$CODEX_HOME/auth.json`**，无额外子目录。

> [!CAUTION]
> **这个文件承载明文凭证。** 本文只描述字段名与类型，**不复述任何值**。排查问题时不要把它整体粘贴到 issue、日志或对话里。

### 2.2 `cli_auth_credentials_store` 的取值（E3，修订补入）

初版只说它是"`codex-rs/core/config.schema.json` 顶层键之一"，未说明取值。类型是 `AuthCredentialsStoreMode`（`codex-rs/config/src/types.rs:107-117`），共 **4 个取值**：

| 取值 | 语义（文档注释原文） |
| ---- | ---- |
| **`file`**（`#[default]`） | *"Persist credentials in CODEX_HOME/auth.json."* |
| `keyring` | *"Persist credentials in the keyring. Fail if unavailable."*——**钥匙串不可用时直接失败，不降级** |
| `auto` | *"Use keyring when available; otherwise, fall back to a file in CODEX_HOME."* |
| `ephemeral` | *"Store credentials in memory only for the current process."*——**只存内存，进程退出即失** |

```toml
cli_auth_credentials_store = "keyring"
```

> 注意与 MCP 侧的 `mcp_oauth_credentials_store`（`OAuthCredentialsStoreMode`，`types.rs:122`）区分——那是**另一个键**，默认值与语义都不同（它默认偏好 keyring）。

### 2.3 与 `Feature::SecretAuthStorage` 的关系（E3）

选择钥匙串存储时，实际后端还要过一个 feature 开关。`codex-rs/core/src/config/auth_keyring.rs`：

```rust
impl Config {
    pub fn auth_keyring_backend_kind(&self) -> AuthKeyringBackendKind {
        auth_keyring_backend_kind_from_secret_auth_storage(
            self.features.enabled(Feature::SecretAuthStorage),
        )
    }
}
```

`Feature::SecretAuthStorage`（`codex-rs/features/src/lib.rs:92`）的文档注释：

> *"Store CLI auth in the encrypted local secrets backend when keyring storage is selected."*

**含义**：`cli_auth_credentials_store = "keyring"`（或 `auto` 命中钥匙串）时，开启该 feature 会把凭证路由到**加密的本地 secrets 后端**（`codex-secrets`），而不是直接用系统钥匙串。

它的注册项在 `codex-rs/features/src/lib.rs:853-857`：

```rust
FeatureSpec {
    id: Feature::SecretAuthStorage,
    key: "secret_auth_storage",
    stage: Stage::Stable,
    default_enabled: cfg!(windows),
},
```

> [!IMPORTANT]
> **两处需要留意，其中一处是对上一稿的更正：**
>
> 1. **`default_enabled: cfg!(windows)`——在 Windows 上它默认就是开的。** 不要把它当成纯粹的"选择性加固项"来描述；在 Windows 平台上，加密本地 secrets 后端是**默认路径**，反倒是关闭它需要显式配置。
> 2. **上一稿说它"是 `Feature` 枚举 `// Stable.` 注释段仅有的 3 个之一，在这个以实验性为主的枚举里已属稳定"——依据用错了。** 判定成熟度的权威字段是 `stage:`，不是源码里的注释分段。按 `stage:` 统计，102 个 feature 中 `Stage::Stable` 有 **34** 个，`Stage::Experimental` 只有 1~2 个（随 target 而变）——**这个枚举根本不是"以实验性为主"**。详见 [`experimental_surfaces.md`](./experimental_surfaces.md) §7.4。（"`// Stable.` 注释段只有 3 个变体"这句本身是对的，只是它不能用来推断成熟度。）

另有 `resolve_bootstrap_auth_keyring_backend_kind`（`codex-rs/core/src/config/auth_keyring.rs:22`），用于**在完整 `Config` 构建之前**就得读认证的启动路径。

---

## 3. `ModelProviderInfo`：provider 配置面（E3）

`codex-rs/model-provider-info/src/lib.rs:89` 定义，字段相当丰富：

### 3.1 基础

| 字段 | 说明 |
| ---- | ---- |
| `name` | 展示名 |
| `base_url` | provider 的 OpenAI 兼容 API 基址 |
| `wire_api` | 线协议（见 §4） |
| `query_params` | 追加到 base URL 的查询参数 |

### 3.2 认证（四选一或组合）

| 字段 | 说明 |
| ---- | ---- |
| `env_key` | **推荐**：存放 API key 的环境变量名 |
| `env_key_instructions` | 引导用户获取并设置该变量的说明 |
| `experimental_bearer_token` | 直接给 `Authorization: Bearer <token>` 的值 |
| `auth` (`ModelProviderAuthInfo`) | 命令驱动的 bearer token |
| `aws` (`ModelProviderAwsAuthInfo`) | AWS SigV4 |

> [!WARNING]
> `experimental_bearer_token` 的字段注释明确写道："Use of this config is **discouraged in favor of `env_key`** for security reasons, but this may be necessary when using this programmatically."
>
> **优先用 `env_key`，不要把 token 直接写进配置文件。**

### 3.3 HTTP 头

| 字段 | 说明 |
| ---- | ---- |
| `http_headers` | 键值对直接作为请求头 |
| `env_http_headers` | 键为头名，**值为环境变量名**；变量未设置或为空时该头不发送 |

`env_http_headers` 是另一个避免把敏感值写进配置的机制。

### 3.4 重试与超时

| 字段 | 说明 |
| ---- | ---- |
| `request_max_retries` | HTTP 请求最大重试次数 |
| `stream_max_retries` | 流式响应断开后的重连次数 |
| `stream_idle_timeout_ms` | 流空闲多久判定连接丢失 |
| `websocket_connect_timeout_ms` | WebSocket 连接超时 |

**存在 WebSocket 超时字段**，说明部分 provider 走 WebSocket 而非纯 HTTP 流（另见 `codex-websocket-client`、`codex-rs/core/tests/suite/client_websockets.rs`）。

---

## 4. `WireApi`：只剩一个变体（E3）

```rust
// model-provider-info/src/lib.rs:57
pub enum WireApi {
    /// The Responses API exposed by OpenAI at `/v1/responses`.
    #[default]
    Responses,
}
```

> [!IMPORTANT]
> **`WireApi` 现在只有 `Responses` 一个变体。** 曾经存在的 `chat` 已被移除。
>
> 源码中保留了两条迁移错误信息（`lib.rs:50-52`）：
>
> | 场景 | 错误提示要点 |
> | ---- | ---- |
> | `wire_api = "chat"` | 不再支持。改用 `wire_api = "responses"` |
> | provider id `ollama-chat` | 不再支持。在 `model_provider` / `oss_provider` / `--local-provider` 中把 `ollama-chat` 换成 `ollama` |
>
> 两条提示都指向同一个讨论帖：`github.com/openai/codex/discussions/7782`。
>
> `LEGACY_OLLAMA_CHAT_PROVIDER_ID` 常量（`lib.rs:51`）仍在，用于识别并给出上述提示。

**含义**：Codex 已完全转向 Responses API。写文档或做集成时不要再提 Chat Completions 路径。

---

## 5. 本地与第三方模型接入

| crate | 行数 | 目标 |
| ---- | ---: | ---- |
| `codex-ollama` | 1,107 | Ollama |
| `codex-lmstudio` | 470 | LM Studio |
| `codex-aws-auth` | 375 | AWS（Bedrock 场景） |
| `codex-model-provider` | 3,247 | provider 抽象 |
| `codex-models-manager` | 2,722 | 模型管理 |
| `codex-backend-client` | 2,258 | 后端客户端 |
| `codex-backend-openapi-models` | 1,017 | 后端 OpenAPI 模型 |

相关 CLI 参数：`--local-provider`；配置键：`model_provider`、`oss_provider`。

> [!NOTE]
> **README 说 Codex "runs locally on your computer"，指的是智能体进程在本地跑，不等于不出网。** 默认路径仍走 OpenAI/ChatGPT 服务；本地模型需要用户显式配置。完整的外部服务边界见 [`architecture_overview.md`](./architecture_overview.md) §8。

---

## 6. 相关配置键（**E2**：读生成的 `codex-rs/core/config.schema.json`；初版标 E4 已下调）

`codex-rs/core/config.schema.json` 中与本文相关的顶层键：`chatgpt_base_url`、`cli_auth_credentials_store`、`forced_chatgpt_workspace_id`、`forced_login_method`、`allow_login_shell`、`model_provider`、`oss_provider`（后两者见完整 schema）。

配置层级与优先级见 [`config_system.md`](./config_system.md) §1。

---

## 7. 相关的用户入口

| 入口 | 说明 |
| ---- | ---- |
| `codex login` / `codex logout` | CLI 登录登出 |
| `codex login status` | 查看登录态（`main.rs:1375`） |
| `codex doctor` | 诊断本地安装、配置、认证与运行时健康 |
| `account/*` 协议方法（13 个） | app-server：登录、额度、用量、工作区消息 |

`account` 命名空间的 13 个方法包括 `account/login/start`、`/cancel`、`/completed`、`account/logout`、`account/rateLimits/read`、`account/usage/read`、`account/chatgptAuthTokens/refresh` 等。

---

## 8. 安全约束

| 约束 | 说明 |
| ---- | ---- |
| 优先 `env_key`，避免 `experimental_bearer_token` | 字段注释明文建议 |
| 敏感请求头用 `env_http_headers` 而非 `http_headers` | 同上机制 |
| 文档中**只写变量名、键名、路径**，不写值 | 本体系脱敏规范 |
| 测试夹具中的假 token 不得引入文档 | 同上 |
| **不要向普通用户推荐 `--experimental_issuer` / `--experimental_client-id`** | §1.3——可把 OAuth 流程指向任意 issuer |
| **`$CODEX_HOME/auth.json` 承载明文凭证**，不要整体粘贴到 issue 或日志 | §2.1 |
| 需要更强的本地保护时用 `cli_auth_credentials_store = "keyring"` + `Feature::SecretAuthStorage` | §2.2 / §2.3 |
| 遥测中的认证环境信息见 `codex-rs/login/src/auth_env_telemetry.rs` | 与 [`observability.md`](./observability.md) 相关 |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| ~~`auth.json` 的结构~~ | **已在 §2.1 解决**（`AuthDotJson`） | — |
| OAuth 完整时序与错误分支 | E1 | `codex-rs/login/src/lib.rs`、`codex-rs/login/src/auth/manager.rs` |
| 凭证在钥匙串中的具体命名与格式 | E1 | `codex-rs/keyring-store/src/lib.rs`、`codex-rs/login/src/auth/storage.rs` |
| `TokenData` / `AgentIdentityStorage` / `BedrockApiKeyAuth` 的内部字段 | E1 | `codex-rs/login/src/token_data.rs`、`codex-rs/login/src/auth/storage.rs` |
| `ChatgptAuthTokens` 与 `Headers` 两种模式的实际注入路径 | E1 | `codex-rs/login/src/auth/manager.rs`；`account/chatgptAuthTokens/refresh` |
| `Feature::SecretAuthStorage` 开启后凭证的实际落点 | E1 | `codex-secrets`、`codex-rs/config/src/types.rs` 的 `AuthKeyringBackendKind` |
| `--experimental_issuer` / `--experimental_client-id` 的校验与约束 | E1 | `codex-rs/cli/src/main.rs:490-496`、`codex-rs/login/src/lib.rs` |
| Bedrock / AWS SigV4 的签名实现 | E1 | `codex-aws-auth`、`codex-rs/login/src/auth/bedrock_api_key.rs` |
| 令牌刷新与过期处理 | E1 | `codex-rs/login/src/auth/manager.rs`、`account/chatgptAuthTokens/refresh` |
| Ollama / LM Studio 的发现与探测 | E1 | `codex-ollama`、`codex-lmstudio` |
| `ModelProviderInfo` 剩余字段 | E3（部分） | `codex-rs/model-provider-info/src/lib.rs:89` 起 |
| Agent Identity 的用途 | E1 | `codex-agent-identity`、`codex-rs/login/src/auth/agent_identity.rs` |

---

## 10. 相关文档

- [配置体系](./config_system.md) — provider 配置的加载与层级
- [架构总览](./architecture_overview.md) §8 — 外部服务边界全景
- [可观测性](./observability.md) — 认证相关遥测
- [实验性表面](./experimental_surfaces.md) — 云任务的认证路径
