---
title: Codex 认证与模型接入
summary: 以 codex-protocol 的 AuthMode 枚举（7 个变体）为准描述认证方式，区分「类型存在」与「实际生效」——只有 4 个变体会写进 auth.json，Headers 被存储层拒绝、ChatgptAuthTokens 被强制 Ephemeral；说明 auth.json 的实际结构与 0600 权限、resolved_mode() 的推断顺序、cli_auth_credentials_store 的四个取值与 Feature::SecretAuthStorage / AuthKeyringBackendKind 的两处平台分叉、ModelProviderInfo 的完整配置面与 validate() 的互斥规则、WireApi 仅剩 Responses 一个变体的现状、CODEX_OSS_BASE_URL 驱动的本地模型接入（完全不走认证），以及若干隐藏的 OAuth / 端点覆盖参数带来的风险。
keywords: codex | auth | login | oauth | pkce | model-provider | wire-api | keyring | credentials | auth-mode | resolved-mode | oss-provider
scope: codex-rs/login、protocol/src/auth.rs、model-provider-info 与相关认证凭证存储
related_files: codex-rs/protocol/src/auth.rs | codex-rs/model-provider-info/src/lib.rs | codex-rs/login/src/lib.rs | codex-rs/login/src/auth/storage.rs | codex-rs/login/src/auth/manager.rs | codex-rs/login/src/auth/auth_headers.rs | codex-rs/keyring-store/src/lib.rs | codex-rs/secrets/src/local.rs | codex-rs/config/src/types.rs | codex-rs/core/src/config/auth_keyring.rs | codex-rs/features/src/lib.rs | codex-rs/cli/src/main.rs | codex-rs/rmcp-client/src/oauth.rs | AGENTS.md
dependencies: dev_docs/config_system.md | dev_docs/architecture_overview.md
verified_at: 2026-08-05
---

# 认证与模型接入

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 类型定义与字段为 E3；端点为 E3（**取证方式已修正为「常量名 + 被谁请求」，不再以 grep 到 URL 字面量为准**，见 §1.6）；§1.1 的文件清单为 E1、其「承载的能力」列为 E3；依赖宏展开与序列化语义的两处结论（§1 的 serde/strum 差异、§2.1 的 `null` 键）为 **E3（推断）**——静态证据完备且高置信度，但未跑运行期验证；OAuth 完整时序为 E1

> [!CAUTION]
> **本文不复述任何凭证的实际值。** 只记录变量名、配置键名、文件路径与端点。测试夹具中的假 token（如 `codex-rs/login/src/token_data_tests.rs` 里的样例）也不引入文档。

> [!IMPORTANT]
> **本文已修订：**
>
> 1. **§1 重建**——初版的认证方式表是**按 `login/src/auth/` 的文件名推导**的，因此漏了两种模式、又把实现文件当成了并列的认证模式。现改为以**权威枚举 `AuthMode`** 为准。
> 2. **§2 补全**——`auth.json` 的结构初版标为 E1 未验证，实际有明确的类型定义。
> 3. **§2 补全**——`cli_auth_credentials_store` 的取值初版完全未说明。
> 4. **§1.3 新增**——隐藏的 OAuth 覆盖参数与端点重定向环境变量。
> 5. **本轮（2026-08-05）**——纠正一整类「**类型存在 ≠ 该路径生效**」的错误：7 个 `AuthMode` 变体只有 4 个会写进 `auth.json`（§1.4）；`Headers` 在本仓库生产代码中零构造（§1）；新增 §1.5「认证加载的四级优先级」与 §2.1.1「`resolved_mode()` 的推断顺序」；补全 `CODEX_OSS_BASE_URL` 驱动的本地模型路径（§5）、`validate()` 的互斥规则（§3.6）、MCP OAuth 与 CLI 登录的对照（§2.5）。

> [!CAUTION]
> **本轮修订反复撞上同一个失败模式，先在这里点名：**
>
> 1. **按文件名推断文件内容**——初版 §1 的原始根因，本轮在 §1.1 又复发一次（把 18 行的 `codex-rs/login/src/auth/access_token.rs` 说成"含从 stdin 读入"、漏掉 5 个文件、进而误断 `Headers` "没有同名实现文件"）。**文件名只能证明文件存在（E1），断言它承载什么能力必须打开文件（E3）。**<!-- ref-exempt: 检查器误报——同行的 `Headers` 指 AuthMode::Headers，本句正是在说 access_token.rs 与它无关；该文件不含此符号是预期 -->
> 2. **grep 到 URL 字面量就当成端点**——初版"相关端点"表把 OIDC claim 命名空间与 JWT `iss` 值列成了可请求的 HTTP 端点（§1.6）。**E3 的取证方式必须是「找到这个字面量的用途：它的常量名是什么、被谁请求」，而不是「它长得像 URL」。**
> 3. **类型/字段存在就当成运行期生效**——`AuthMode` 有 7 个变体不等于 7 条路径都会落盘；`ModelProviderInfo` 有 5 个认证字段不等于可以组合使用。**枚举是能力面，运行期还有 `validate()`、存储层拒绝、强制降级三道闸。**

---

## 1. 认证方式：以 `AuthMode` 枚举为准（E3）

> [!CAUTION]
> **修订说明（原文方法有误）**：初版的表格是从 `codex-rs/login/src/auth/` **目录下的文件名**推导出来的。这导致两类问题：
>
> - **漏掉了两个变体**：`ChatgptAuthTokens` 与 `Headers`。（初版给的理由是"它们没有同名实现文件"——**这个理由本身也是错的**：`Headers` 的实现就是 `codex-rs/login/src/auth/auth_headers.rs`（`:10-12` 的 `pub struct AuthHeaders`，经 `codex-rs/login/src/auth/mod.rs:15` re-export）。初版按文件名推导时连这个文件都没读到。只有 `ChatgptAuthTokens` 确实没有同名实现文件。）
> - **把实现文件当成了并列的认证模式**：例如 "External Bearer"（`codex-rs/login/src/auth/external_bearer.rs`）是一个实现文件，不是 `AuthMode` 的一个变体。<!-- ref-exempt: 本行否定 external_bearer.rs 含 AuthMode（实测零命中），引用不可解析恰是要表达的事实 -->
>
> 权威定义是 **`codex-rs/protocol/src/auth.rs:9-34` 的 `pub enum AuthMode`**，共 **7 个变体**。以下表格按该枚举重建。
>
> 另有一份**用于生成 TypeScript 的重复定义**：`codex-rs/app-server-protocol/src/protocol/common.rs:24` 起的 `pub enum AuthMode`（带 `#[ts(...)]`）。它的 `ChatgptAuthTokens` 文档注释写着 `/// [UNSTABLE] FOR OPENAI INTERNAL USE ONLY - DO NOT USE.`（`:29`）——比 protocol 侧的注释更明确。改动认证模式时**两处都要改**。

| `AuthMode` 变体 | serde 线格式 | strum `Display` | 文档注释（原文） | 典型入口 |
| ---- | ---- | ---- | ---- | ---- |
| `ApiKey` | `apikey` | **`ApiKey`** ⚠️ | *"OpenAI API key provided by the caller and stored by Codex."* | `codex login --with-api-key`（`run_login_with_api_key`） |
| `Chatgpt` | `chatgpt` | **`Chatgpt`** ⚠️ | *"ChatGPT OAuth managed by Codex (tokens persisted and refreshed by Codex)."* | `codex login` → Sign in with ChatGPT |
| **`ChatgptAuthTokens`** | `chatgptAuthTokens` | `chatgptAuthTokens` | *"ChatGPT auth tokens supplied by an external host application."* | **宿主应用注入**：`account/login/start` 的 `ChatgptAuthTokens` 变体（见下方勘误） |
| **`Headers`** | `headers` | `headers` | *"Codex backend auth supplied as request headers."* | **下游兼容面**，非 CLI 路径：由嵌入 Codex 的宿主应用构造 `AuthHeaders` 后经 `ExternalAuth` 注入（见下方勘误） |
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
>
> **证据等级：E3（推断）。** 属性的存在与缺失是直接读源码确认的（`codex-rs/protocol/src/auth.rs:7-33`，逐变体核对），但"strum 拿不到重写指示就输出变体名"这一步依赖 **`Display` derive 的宏展开语义**，本轮未跑运行期验证。静态证据完备、结论高置信度，但等级应标 E3（推断）而非 E3（直证）。

> [!CAUTION]
> **勘误：上一稿把这两个变体的"典型入口"写错了。**
>
> **`ChatgptAuthTokens` 的入口不是 `account/chatgptAuthTokens/refresh`。** 那个方法是 **server→client 的 `ServerRequest`**——Codex **反向**向宿主应用要一份新 token（注册在 `codex-rs/app-server-protocol/src/protocol/common.rs:1569`，实现在 `codex-rs/app-server/src/external_auth.rs`）。它是**刷新回调**，不是注入入口。
> **真正的注入入口是 `account/login/start` 的 `LoginAccountParams::ChatgptAuthTokens` 变体**（`codex-rs/app-server-protocol/src/protocol/v2/account.rs:84-89`），带 `#[experimental("account/login/start.chatgptAuthTokens")]`，注释写明 *"[UNSTABLE] FOR OPENAI INTERNAL USE ONLY - DO NOT USE."*
>
> **`AuthMode::Headers` 在本仓库全部生产代码中零构造。** 对 `CodexAuth::Headers(..)` 的**构造**全部命中都在测试里（`codex-rs/core/tests/suite/external_auth.rs:27`、`codex-rs/model-provider/src/auth.rs:459`、`codex-rs/login/src/auth/auth_tests.rs:1117`、`codex-rs/codex-mcp/src/connection_manager_tests.rs`、`codex-rs/core-plugins/src/remote/catalog_cache_tests.rs`，以及 `codex-rs/app-server/src/request_processors/feedback_processor.rs:728`——该文件 `#[cfg(test)]` 从 `:432` 开始，故同属测试）；生产侧只有**模式匹配**（如 `codex-rs/model-provider/src/auth.rs:287`、`codex-rs/login/src/auth/manager.rs:1119`）。
> 它由**嵌入 Codex 的宿主应用**自行构造 `AuthHeaders` 后经 `ExternalAuth` 注入——因此它是一个**下游兼容面**，不是 CLI 路径。类型经 `codex-rs/login/src/lib.rs:32` 与 `codex-rs/core-api/src/lib.rs:78` 对外导出。仓库内唯一的行为覆盖是 `codex-rs/core/tests/suite/external_auth.rs`。

`AuthMode` 上还有两个辅助方法（`codex-rs/protocol/src/auth.rs:36-56`），**分组判据不同，不要混用**：

| 方法 | 位置 | 返回 `true` 的变体 | 返回 `false` 的变体 | 用途 |
| ---- | ---- | ---- | ---- | ---- |
| `has_chatgpt_account()` | `codex-rs/protocol/src/auth.rs:38-43` | `Chatgpt`、`ChatgptAuthTokens`、`PersonalAccessToken` | `ApiKey`、`Headers`、`AgentIdentity`、`BedrockApiKey` | 是否代表一个**已认证的人类 ChatGPT 账号** |
| **`uses_codex_backend()`** | `codex-rs/protocol/src/auth.rs:46-55` | `Chatgpt`、`ChatgptAuthTokens`、`Headers`、`AgentIdentity`、`PersonalAccessToken` | **`ApiKey`、`BedrockApiKey`** | 是否走 **Codex 后端**而非直连模型 API |

> [!IMPORTANT]
> **理解 §1 的模式分组，`uses_codex_backend()` 比 `has_chatgpt_account()` 更关键。** 它划出的是**流量去向**这条线：`ApiKey` 与 `BedrockApiKey` 直连模型 API，其余 5 个变体的请求都经过 Codex 后端。排查"为什么这个模式下某个后端特性不可用"，先看这个方法而不是 `has_chatgpt_account()`。
>
> 两者的差集正说明它们不可互换：`Headers` 与 `AgentIdentity` 走 Codex 后端，但**不**算"有 ChatGPT 账号"。

> [!NOTE]
> **两个补回的变体值得特别注意**：`ChatgptAuthTokens` 与 `Headers` 都是**由外部注入凭证**的模式，不走 `codex login` 交互流程。做认证相关改动时，只测 CLI 登录路径会漏掉它们。

### 1.1 `login/src/auth/` 下的实现文件（**文件名与清单为 E1；「承载的能力」列为 E3**）

> [!CAUTION]
> **证据等级勘误，同时是一次旧病复发。** 上一稿把本节整体标为 "E1（目录清单）"，但右列「承载的能力」是**文件内容断言**，只能靠打开文件取证，属 E3。挂着 E1 标签写 E3 结论，等于给「按文件名猜内容」发了通行证——**这正是本项目 28 个 HIGH 级错误的原始根因**，而 §1 开头刚刚为此重建过一次表格，本节又犯了同一个错。
>
> 直接后果有两条：
>
> - `codex-rs/login/src/auth/access_token.rs` 被写成"access token 处理（**含从 stdin 读入**）"。该文件**总共 18 行**，只有一个前缀常量、一个两变体枚举和一个分类函数，**没有任何 IO**。stdin 读入根本不在这里。
> - 表只列了 8 个文件，实际有 **13 个非测试文件**，漏掉的 `codex-rs/login/src/auth/auth_headers.rs` 恰恰是 `AuthMode::Headers` 的实现——于是又反过来支撑了 §1 那句错误的"它们没有同名实现文件"。**一个越权的证据等级，制造了两处下游错误。**

这些是**实现**，与上面的模式**不是一一对应**。`codex-rs/login/src/auth/` 下共 **13 个非测试文件**（另有 5 个 `*_tests.rs`，不计入）：

| 文件 | 承载的能力 |
| ---- | ---- |
| `codex-rs/login/src/auth/access_token.rs` | **仅 18 行**：`PERSONAL_ACCESS_TOKEN_PREFIX`（`:1`）、`enum CodexAccessToken { PersonalAccessToken, AgentIdentityJwt }`（`:3-6`）、`classify_codex_access_token()`（`:8-14`）。**按 token 前缀分流，不做 IO。** |
| `codex-rs/login/src/auth/auth_headers.rs` | **`AuthMode::Headers` 的实现**：`pub struct AuthHeaders { headers: HeaderMap }`（`:10-12`），经 `codex-rs/login/src/auth/mod.rs:15` re-export |
| `codex-rs/login/src/auth/personal_access_token.rs` | `PersonalAccessToken`：`PersonalAccessTokenAuth`（`:24`）、whoami 校验（`:40-52`） |
| `codex-rs/login/src/auth/external_bearer.rs` | 外部 bearer token 的取用（由 provider 配置驱动，**不是独立的 `AuthMode`**）；`run_provider_auth_command()`（`:102`）**执行用户配置的命令**取 token <!-- ref-exempt: 本行否定 external_bearer.rs 含 AuthMode（实测零命中），引用不可解析恰是要表达的事实 --> |
| `codex-rs/login/src/auth/bedrock_api_key.rs` | `BedrockApiKey`：`BedrockApiKeyAuth`（`:13-17`）、`login_with_bedrock_api_key()`（`:20`） |
| `codex-rs/login/src/auth/agent_identity.rs` | `AgentIdentity` |
| `codex-rs/login/src/auth/storage.rs` | 凭证落盘与 5 个存储后端，见 §2 |
| `codex-rs/login/src/auth/revoke.rs` | 撤销 |
| `codex-rs/login/src/auth/manager.rs` | 认证管理器（`AuthManager`）、`load_auth()` 优先级（§1.5）、令牌刷新 |
| `codex-rs/login/src/auth/default_client.rs` | 认证专用 HTTP 客户端构造（`create_default_auth_client`） |
| `codex-rs/login/src/auth/error.rs` | `RefreshTokenFailedError` / `RefreshTokenFailedReason` |
| `codex-rs/login/src/auth/util.rs` | 内部工具 |
| `codex-rs/login/src/auth/mod.rs` | 模块声明与 re-export（`:1-20`） |

另有 `codex-rs/login/src/device_code_auth.rs`——**Device Code 是 OAuth 的一种授权流程，不是独立的 `AuthMode` 变体**。<!-- ref-exempt: 本行否定 device_code_auth.rs 含 AuthMode/Chatgpt 符号（实测零命中），引用不可解析恰是要表达的事实；肯定部分的证据链见下一段 -->

**它最终仍落到 `Chatgpt`**——证据链（上一稿只给结论未给链路，此处补齐）：`codex-rs/login/src/device_code_auth.rs:222` 调用 `crate::server::persist_tokens_async(...)` → `codex-rs/login/src/server.rs:910-911` 构造 `AuthDotJson { auth_mode: Some(AuthMode::Chatgpt), ... }`。

### 1.2 CLI 侧入口函数

`codex-rs/cli/src/main.rs:13-20` 从 `codex-rs/cli/src/login.rs` 引入：`run_login_with_chatgpt`、`run_login_with_api_key`、`run_login_with_access_token`、`run_login_with_device_code`、`run_login_status`、`run_logout`、`read_api_key_from_stdin`、`read_access_token_from_stdin`。

**凭证的 stdin 读入在这里，不在 `codex-rs/login/src/auth/access_token.rs`**（见 §1.1 勘误）：

| 函数 | 位置 | 对应参数 |
| ---- | ---- | ---- |
| `read_api_key_from_stdin` | `codex-rs/cli/src/login.rs:264` | `codex login --with-api-key` |
| `read_access_token_from_stdin` | `codex-rs/cli/src/login.rs:272` | `codex login --with-access-token` |

两者都转调 `read_stdin_secret`（`codex-rs/cli/src/login.rs:281`）。**API key 与 access token 一律从 stdin 读，不接受命令行字面量**——这是一处刻意的设计（见 §1.3 末尾已废弃的 `--api-key`）。

### 1.3 两个**隐藏的 OAuth 覆盖参数**（E3，修订补入）

`codex login` 有两个 `hide = true` 的参数，`codex login --help` 中**看不到**：

| 参数 | 位置 | 作用 |
| ---- | ---- | ---- |
| `--experimental_issuer <URL>` | `codex-rs/cli/src/main.rs:489-492` | *"EXPERIMENTAL: Use custom OAuth issuer base URL (advanced)"*——**覆盖 OAuth issuer 基址**（默认 `DEFAULT_ISSUER`，`codex-rs/login/src/server.rs:59`） |
| `--experimental_client-id <CLIENT_ID>` | `codex-rs/cli/src/main.rs:494-496` | *"EXPERIMENTAL: Use custom OAuth client ID (advanced)"*——**覆盖 OAuth client ID** |

> **勘误（行号）**：上一稿把 `--experimental_issuer` 标为 `:490-492`，实际是 **`:489-492`**——该参数有**两行**文档注释（`:489` 与 `:490`），clap 取第一行作 `help`、两行合并作 `long_help`，漏掉 `:489` 会把 `help` 的来源指错。`--experimental_client-id` 的 `:494-496` **正确**。

> [!WARNING]
> **这是本文覆盖范围内最容易被忽视的一处认证端点改写面。** 这两个参数允许把整个 OAuth 授权流程指向**任意 issuer**——包括把用户引向非 OpenAI 的授权端点。它们既隐藏又带 `experimental_` 前缀，说明只面向高级/内部场景。
>
> - **不要**在文档、脚本或教程中向普通用户推荐这两个参数。
> - 审计认证链路时**必须**把它们计入攻击面。
> - 相关的隐藏入口全景见 [`experimental_surfaces.md`](./experimental_surfaces.md) §7.6。
>
> **上一稿写的是"风险最高的一处能力面"，这个说法要收回**：它既没有比较基准，又遗漏了同类项——**同类的端点改写面至少还有 4 个环境变量**（见下方 §1.3.1），其中 `CODEX_AUTHAPI_BASE_URL` 与 `CODEX_OSS_BASE_URL` **既不隐藏、也没有 `experimental_` 前缀**，反而更容易被误用。

另有一个已废弃的隐藏参数：**`--api-key` 选项**（`codex-rs/cli/src/main.rs:476-484`），现在只会退出并提示改用 `--with-api-key`。

> **勘误**：上一稿称它是"位置参数"。它不是——`codex-rs/cli/src/main.rs:476` 起的属性是 `#[arg(long = "api-key", ...)]`，另带 `num_args = 0..=1`、一个空字符串的 `default_missing_value`、一个占位用的 `value_name`、`hide = true` 与标注 `(deprecated)` 的 `help`。也就是**一个带长名的可选值选项**（`num_args = 0..=1` 使 `--api-key` 后可以不跟值）。clap 里位置参数是不写 `long = ...` 的，这一点可以直接区分。

#### 1.3.1 端点 / 客户端标识的重定向环境变量（E3，本轮补入）

除上面两个 CLI 参数外，还有**四个环境变量**可以改写认证链路的目标地址或客户端身份。**它们都没有签名校验或白名单**：

| 环境变量 | 覆盖的默认值（常量名） | 位置 | 空值处理 |
| ---- | ---- | ---- | ---- |
| `CODEX_REFRESH_TOKEN_URL_OVERRIDE` | `REFRESH_TOKEN_URL` | 常量 `codex-rs/login/src/auth/manager.rs:193`；使用 `:1457-1460` | ⚠️ **`unwrap_or_else` 无空值过滤——空字符串也会被采纳** |
| `CODEX_REVOKE_TOKEN_URL_OVERRIDE` | `REVOKE_TOKEN_URL` | 常量 `codex-rs/login/src/auth/manager.rs:194` | — |
| `CODEX_APP_SERVER_LOGIN_CLIENT_ID` | `CLIENT_ID`（`codex-rs/login/src/auth/manager.rs:1448`，**值不复述**） | 常量 `codex-rs/login/src/auth/manager.rs:195`；使用 `oauth_client_id()` `:1450-1455` | ✅ 带 `.filter(\|s\| !s.trim().is_empty())` |
| `CODEX_AUTHAPI_BASE_URL` | `PROD_AUTHAPI_BASE_URL` | 常量 `codex-rs/login/src/auth/personal_access_token.rs:12`；使用 `:44-48` | ✅ 带 trim + 空值过滤 |

> [!CAUTION]
> **两个函数对空值的处理不一致，这是一处真实的行为差异，不是笔误级细节。**
>
> - `oauth_client_id()`（`codex-rs/login/src/auth/manager.rs:1450-1455`）链式里有 `.filter(|client_id| !client_id.trim().is_empty())`，**设成空串会回落到默认常量**。
> - `refresh_token_endpoint()`（`codex-rs/login/src/auth/manager.rs:1457-1460`）只有 `.unwrap_or_else(|_| ...)`，**`env::var` 返回 `Ok("")` 时空串被原样采纳**，刷新请求会打到一个空 URL 上并以一个与配置无关的错误失败。
>
> 排查"令牌刷新莫名失败"时，`CODEX_REFRESH_TOKEN_URL_OVERRIDE=` 这种**看起来等于没设**的写法是需要排除的一项。

另外，`CODEX_OSS_BASE_URL` / `CODEX_OSS_PORT` 同属端点改写类别，但走的是 provider 构造而非认证链路，见 §5.1。

### 1.4 **7 个变体里只有 4 个会写进 `auth.json`**（E3，本轮补入）

> [!CAUTION]
> **这是本文最容易误导人的一处「类型存在 ≠ 路径生效」。** `AuthMode` 有 7 个变体，但**存储层只接受其中 4 个**。剩下 3 个各有各的原因，而且都不是"暂未实现"，是**代码里显式做掉的**。

| `AuthMode` 变体 | 会写进 `auth.json`？ | 依据 |
| ---- | ---- | ---- |
| `ApiKey` | ✅ | 落在 `openai_api_key` 字段 |
| `Chatgpt` | ✅ | `codex-rs/login/src/server.rs:910-911` 显式写 `auth_mode: Some(AuthMode::Chatgpt)` |
| `AgentIdentity` | ✅ | 落在 `agent_identity` 字段 |
| `BedrockApiKey` | ✅ | 落在 `bedrock_api_key` 字段 |
| **`PersonalAccessToken`** | ⚠️ **落盘，但 `auth_mode` 写成 `None`** | `codex-rs/login/src/auth/manager.rs:945-947`：注释 *"Infer PAT auth from the credential field so older Codex builds can still deserialize auth.json after a rollback."* + `auth_mode: None,` |
| **`Headers`** | ❌ **被存储层显式拒绝** | `codex-rs/login/src/auth/manager.rs:316-320`：`return Err(std::io::Error::other("externally provided auth cannot be loaded from auth storage."))` |
| **`ChatgptAuthTokens`** | ❌ **被强制降为 `Ephemeral`，只存内存** | `codex-rs/login/src/auth/manager.rs:1513-1517` 的 `storage_mode()` |

要点：

- **`PersonalAccessToken` 是刻意写 `None` 的**，不是遗漏。目的是让**回滚到旧版 Codex** 的用户仍能反序列化 `auth.json`——旧版不认识 `personalAccessToken` 这个 `auth_mode` 取值。实际模式由 `resolved_mode()` 从**凭证字段**反推（§2.1.1）。
- **`Headers` 的拒绝发生在加载路径上**（`from_auth_dot_json`），意味着即使有人手工把 `"auth_mode": "headers"` 写进 `auth.json`，Codex 也会报错而不是接受。
- **`ChatgptAuthTokens` 的降级会静默覆盖用户配置**——详见 §2.4。

> [!IMPORTANT]
> **排查时的两条硬约束：**
>
> 1. **不能假定 `auth_mode` 一定存在。** 它是 `Option<AuthMode>`，PAT 路径下就是 `None`，且该字段带 `skip_serializing_if`（§2.1），`None` 时**整个键都不会出现在文件里**。
> 2. **不能假定 `auth_mode` 等于实际生效的模式。** 生效的是 `resolved_mode()` 的结果；`auth_mode` 只是它的第一优先级输入。

### 1.5 认证加载的**四级优先级**（E3，本轮补入）

`codex-rs/login/src/auth/manager.rs:1217-1305` 的 `load_auth()` 按固定顺序取第一个命中的来源：

| 顺序 | 来源 | 位置 | 前提 |
| ---: | ---- | ---- | ---- |
| 1 | 环境变量 **`CODEX_API_KEY`** | `codex-rs/login/src/auth/manager.rs:1228-1230` | **需要 `enable_codex_api_key_env == true`** |
| 2 | **进程内 ephemeral 存储** | `codex-rs/login/src/auth/manager.rs:1232-1254` | 无条件 |
| 3 | 环境变量 **`CODEX_ACCESS_TOKEN`** | `codex-rs/login/src/auth/manager.rs:1256-1274` | 无条件 |
| 4 | 持久化存储（`file` / `keyring` / `auto`） | `codex-rs/login/src/auth/manager.rs:1282-1305` | 配置的存储模式不是 `ephemeral`（`:1277-1279` 提前返回 `None`） |

源码注释把前两级的意图说得很清楚：

> `:1227` *"API key via env var takes precedence over any other auth method."*
> `:1232-1233` *"External ChatGPT auth tokens live in the in-memory (ephemeral) store. Always check this first so external auth takes precedence over any persisted credentials."*

> [!IMPORTANT]
> **反直觉的一点：ephemeral 内存存储排在 `CODEX_ACCESS_TOKEN` 之前。**
>
> 直觉上"环境变量优先于内存态"，实际相反——**宿主应用注入的 `ChatgptAuthTokens` 会盖过 `CODEX_ACCESS_TOKEN`**。在 IDE 扩展这类宿主里设 `CODEX_ACCESS_TOKEN` 却发现不生效，原因通常在这里，而不是变量没读到。

> [!CAUTION]
> **`enable_codex_api_key_env` 是调用方传入的显式参数，不同入口取值不同——「设 `CODEX_API_KEY` 就能覆盖登录态」这句话在一半场景下是假的。**
>
> | 取值 | 调用点（生产） | 场景 |
> | ---- | ---- | ---- |
> | **`true`** | `codex-rs/cli/src/main.rs:1893`、`codex-rs/cli/src/main.rs:2101`、`codex-rs/cli/src/mcp_cmd.rs:574`、`codex-rs/cli/src/doctor.rs:354` | **CLI 主路径** |
> | **`false`** | `codex-rs/app-server/src/lib.rs:511`、`codex-rs/app-server/src/lib.rs:752`、`codex-rs/mcp-server/src/message_processor.rs:62`、`codex-rs/tui/src/lib.rs:561`、`codex-rs/core/src/prompt_debug.rs:36`、`codex-rs/core/src/connectors.rs:121`、`codex-rs/cli/src/main.rs:2055` | **app-server / MCP server / TUI / connectors** |
>
> ⇒ **在 IDE 扩展、app-server、MCP server 场景下 `CODEX_API_KEY` 根本不生效。** 这不是 bug，是宿主不希望环境变量悄悄改写会话身份。

> [!CAUTION]
> **`OPENAI_API_KEY` 不在 `load_auth()` 的任何一级里。**
>
> 把 `OPENAI_API_KEY` 说成"CLI 的 API key 认证入口"是**错的**。常量在 `codex-rs/login/src/auth/manager.rs:838`，读取函数 `read_openai_api_key_from_env()` 在 `:842-847`，但它的生产调用点只有两个：
>
> | 调用点 | 用途 |
> | ---- | ---- |
> | `codex-rs/tui/src/onboarding/auth.rs:780` | onboarding 里 API key 输入框的**预填值**——只是省一次粘贴，不构成认证 |
> | `codex-rs/core/src/realtime_conversation.rs:1637` | realtime 会话的**临时回退**，带 `TODO` 注释（`:1634-1635`）说明是待移除的过渡措施 |
>
> 另有 `codex-rs/cli/src/doctor.rs:1375`、`:2623` 的**存在性诊断**与 `codex-rs/login/src/auth_env_telemetry.rs:36` 的遥测——两者都只判断"变量在不在"，不拿它去认证。
>
> **CLI 的 API key 认证入口是 `codex login --with-api-key`（写入 `auth.json`）与环境变量 `CODEX_API_KEY`（第 1 级），不是 `OPENAI_API_KEY`。**
>
> 三个变量的常量定义相邻（`codex-rs/login/src/auth/manager.rs:838-840`），极易被一并当成等价物——但只有后两个进 `load_auth()`（`read_codex_api_key_from_env` `:849`、`read_codex_access_token_from_env` `:853`）。

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

### 1.6 相关端点与标识符（E3，公开技术信息）

> [!CAUTION]
> **证据等级勘误：上一稿这张表标了 E3（源码 grep），但取证方式与等级不匹配。**
>
> **grep 到一个 URL 字面量，只能证明"这个字符串出现在源码里"，不能证明"它是一个可请求的 HTTP 端点"。** 上一稿因此把三个东西错误地列成了端点：两个 **OIDC claim 命名空间**和一个 **JWT issuer**——它们都是**标识符**，向它们发请求没有任何意义。
>
> **E3 对 URL 的正确取证方式是：找到该字面量的用途——它的常量名叫什么、被哪段代码当作请求目标。** 下面按这个标准重做，并把两类分开。

#### 端点（可请求）

| 端点 | 常量名 / 位置 | 用途 |
| ---- | ---- | ---- |
| `https://auth.openai.com` | `DEFAULT_ISSUER`（`codex-rs/login/src/server.rs:59`） | OAuth issuer 基址；可被 `--experimental_issuer` 覆盖 |
| `https://auth.openai.com/oauth/token` | `REFRESH_TOKEN_URL`（`codex-rs/login/src/auth/manager.rs:191`） | 令牌刷新；可被 `CODEX_REFRESH_TOKEN_URL_OVERRIDE` 覆盖 |
| `https://auth.openai.com/oauth/revoke` | `REVOKE_TOKEN_URL`（`codex-rs/login/src/auth/manager.rs:192`） | 令牌撤销；可被 `CODEX_REVOKE_TOKEN_URL_OVERRIDE` 覆盖 |
| `https://auth.openai.com/api/accounts` | `PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL`（`codex-rs/agent-identity/src/lib.rs:43`）与 `PROD_AUTHAPI_BASE_URL`（`codex-rs/login/src/auth/personal_access_token.rs:11`） | 账号 API 基址：Agent Identity 注册、PAT 的 whoami 校验（`WHOAMI_PATH`，`codex-rs/login/src/auth/personal_access_token.rs:13`）；后者可被 `CODEX_AUTHAPI_BASE_URL` 覆盖 |
| `https://chatgpt.com/backend-api/codex` | `CHATGPT_CODEX_BASE_URL`（`codex-rs/model-provider-info/src/lib.rs:38`） | ChatGPT 通道；对应配置键 `chatgpt_base_url` |

#### JWT / OIDC 标识符（**不是端点**）

| 字面量 | 它到底是什么 | 位置 |
| ---- | ---- | ---- |
| `https://api.openai.com/auth` | **ID Token 自定义 claim 的 serde 重命名键**——`IdClaims.auth` 字段的线名 | `codex-rs/login/src/token_data.rs:77`（`struct IdClaims`，`:72-80`） |
| `https://api.openai.com/profile` | 同上——`IdClaims.profile` 字段的线名 | `codex-rs/login/src/token_data.rs:75` |
| `https://chatgpt.com/codex-backend/agent-identity` | **JWT `iss`（issuer）声明的期望值** | `AGENT_IDENTITY_JWT_ISSUER`（`codex-rs/agent-identity/src/lib.rs:41`） |

> [!WARNING]
> **这三个都不可请求。** 它们是 JWT / OIDC 规范里用 URI 形式充当**命名空间**的标识符（自定义 claim 必须用 URI 形式命名以避免撞名，`iss` 同理），背后没有对应的 HTTP 资源。
>
> **不要把它们写进网络白名单、代理规则或防火墙配置**——放行它们既不会让认证工作，也会平白扩大出网面。上一稿把 `https://api.openai.com/auth`、`/profile`、`/v1` 合并成一行标"API"，正是这种误读最容易造成的后果。
>
> 同理，`AGENT_IDENTITY_JWT_AUDIENCE`（`codex-rs/agent-identity/src/lib.rs:40`）是 `aud` 声明的期望值，也不是端点。

---

## 2. 凭证存储

| 组件 | 位置 | 说明 |
| ---- | ---- | ---- |
| 存储抽象 | `codex-rs/login/src/auth/storage.rs` | 认证态落盘；**5 个后端实现**，见 §2.3 |
| 系统钥匙串 | `codex-keyring-store`（226 行） | `KeyringStore` trait（`codex-rs/keyring-store/src/lib.rs:42-46`）、`DefaultKeyringStore`（`codex-rs/keyring-store/src/lib.rs:49`）、`CredentialStoreError`（`codex-rs/keyring-store/src/lib.rs:9`） |
| 密钥抽象 | `codex-secrets`（786 行） | 加密本地文件后端，落点见 §2.3 |
| 配置侧 | `codex-rs/core/src/config/auth_keyring.rs` | 钥匙串后端的解析 |
| 配置键 | `cli_auth_credentials_store` | `codex-rs/core/config.schema.json` 顶层键之一，取值见 §2.2 |

**存储位置在 `CODEX_HOME`（默认 `~/.codex`）下**，以及系统钥匙串。

> [!NOTE]
> **配置键名没有 `_mode` 后缀。** `config.toml` 里写 `cli_auth_credentials_store`，而 Rust 侧的 `Config` 字段叫 `cli_auth_credentials_store_mode`。这是**刻意**的，源码有注释说明（`codex-rs/core/src/config/mod.rs:4051-4052`）：<!-- ref-exempt: `config.toml` 泛指用户配置文件（$CODEX_HOME/config.toml 等各层），不指仓库内任一同名文件 -->
>
> > *"The config.toml omits `_mode` because it's a config file. However, `_mode` is important in code to differentiate the mode from the store implementation."*
>
> 也就是说，代码里 **mode（模式枚举）与 store（后端实现）是两个概念**——`AuthCredentialsStoreMode` 是用户表达的意图，`FileAuthStorage` 之类才是实现。写配置时用 `cli_auth_credentials_store_mode` 会被当成未知键。

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
}
```

> **勘误**：上一稿在代码块末尾留了一个 `// ...`，暗示还有未列出的字段。**没有了——以上即全部 7 个字段**（`codex-rs/login/src/auth/storage.rs:40-60`）。占位省略号会让读者以为文档做了裁剪，进而去猜"被省掉的是什么"，反而制造不确定性；确认穷举时就应明说穷举。

要点：

- ⚠️ **`auth_mode` 是 `Option<AuthMode>`，既不保证存在、也不保证等于实际生效的模式**——上一稿写的"文件里显式记录 `auth_mode`，与 §1 的枚举**一一对应**"，三重都不成立，详见 §1.4 与下面的 §2.1.1。
- **API key 字段的线名是全大写下划线形式**（由 `#[serde(rename = ...)]` 指定），与 Rust 字段名 `openai_api_key` 仅大小写风格不同。
- 每种程序化认证各有独立字段（`agent_identity` / `personal_access_token` / `bedrock_api_key`）。
- `last_refresh` 支撑令牌刷新判定。
- **大部分**字段带 `#[serde(default, skip_serializing_if = "Option::is_none")]`——未使用的模式不会在文件里留下空键。

> [!CAUTION]
> **勘误：上一稿写的"所有敏感字段都带 `skip_serializing_if`"不成立。** `codex-rs/login/src/auth/storage.rs` 里 **API key 那个字段是例外**——它只有一个 `#[serde(rename = ...)]` 属性，**既没有 `default` 也没有 `skip_serializing_if`**（`:44-45`）；相邻的 `auth_mode`（`:41-42`）才是带 `#[serde(default, skip_serializing_if = "Option::is_none")]` 的那种写法。
>
> 后果很具体：**即使没有配置 API key，序列化 `auth.json` 时也会写出一个值为 `null` 的该键**。所以"文件里出现这个键"并不代表"存了凭证"，排查时别据此下结论。
>
> **证据等级：E3（推断）。** 属性的有无是逐字段读源码确认的（`codex-rs/login/src/auth/storage.rs:40-60`），但"缺少 `skip_serializing_if` ⇒ `None` 会被写成 `null`"这一步依赖 **serde 的默认序列化语义**，本轮未跑运行期验证。静态证据完备、结论高置信度，等级标 E3（推断）。
>
> 这类"逐字段属性不一致"是最容易被概括掉的细节——**看到"所有字段都……"这类全称判断，应逐字段核对而不是抽查一两个。**

#### 2.1.1 `resolved_mode()`：`auth_mode` 缺失时的推断顺序（E3，本轮补入）

因为 PAT 路径刻意把 `auth_mode` 写成 `None`（§1.4），**实际生效的模式由 `resolved_mode()` 决定**，而不是直接读字段。`codex-rs/login/src/auth/manager.rs:1493-1507`：

| 顺序 | 判据 | 结果 |
| ---: | ---- | ---- |
| 1 | `auth_mode` 是 `Some(mode)` | 直接返回该 `mode` |
| 2 | `personal_access_token.is_some()` | `AuthMode::PersonalAccessToken` |
| 3 | `bedrock_api_key.is_some()` | `AuthMode::BedrockApiKey` |
| 4 | `openai_api_key.is_some()` | `AuthMode::ApiKey` |
| 5 | 以上皆不命中 | **兜底 `AuthMode::Chatgpt`** |

> [!IMPORTANT]
> **两条排查含义：**
>
> 1. **顺序即优先级。** 一个同时写了 `personal_access_token` 与 `openai_api_key` 且没有 `auth_mode` 的 `auth.json`，会被判定为 PAT——**先命中的赢**，不报冲突。
> 2. **第 5 条是无条件兜底，不是"检测到 ChatGPT 凭证"。** 一个字段全空的 `auth.json` 也会 `resolved_mode() == Chatgpt`。看到日志里报 `Chatgpt` **不能反推"存在 ChatGPT 令牌"**——这正是 §2.1 那条 `openai_api_key` 恒被序列化为 `null` 的勘误在另一个方向上的同类陷阱。

路径构造（`codex-rs/login/src/auth/storage.rs:150-152`）：

```rust
pub(super) fn get_auth_file(codex_home: &Path) -> PathBuf {
    codex_home.join("auth.json")
}
```

即 **`$CODEX_HOME/auth.json`**，无额外子目录。

> **勘误（行号）**：上一稿标 `:150-151`，实际函数体占 **`:150-152`**（含收尾的 `}`）。

#### 2.1.2 文件权限：Unix `0o600`（E3，本轮补入）

写入 `auth.json` 时显式设定权限位（`codex-rs/login/src/auth/storage.rs:210-214`）：

```rust
let mut options = OpenOptions::new();
options.truncate(true).write(true).create(true);
#[cfg(unix)]
{
    options.mode(0o600);
}
```

**权限在 `open` 时通过 `OpenOptions::mode()` 设定**（`codex-rs/login/src/auth/storage.rs:213`），而不是写完再 `chmod`——后者会留下一个短暂的宽权限窗口。

> [!IMPORTANT]
> **`#[cfg(unix)]` 这个门控是理解 §2.3 平台分叉的关键一环。**
>
> - **Unix 上**：`auth.json` 即使是明文，也只有当前用户可读（`0o600`），文件系统本身提供了一层保护。
> - **Windows 上**：这段代码**不编译进去**，没有等价的权限收紧。明文 `auth.json` 少了这层保护。
>
> ⇒ 这就是为什么 `Feature::SecretAuthStorage` 的 `default_enabled` 是 `cfg!(windows)`、`AuthKeyringBackendKind::default()` 在 Windows 返回 `Secrets`（§2.3）。**两处平台分叉不是巧合，是同一个缺口的补偿。** 把它们当成三条互不相干的事实记忆，就会漏掉"改动其中一处需要同时评估另外两处"。

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

> 注意与 MCP 侧的 `mcp_oauth_credentials_store`（`OAuthCredentialsStoreMode`，`codex-rs/config/src/types.rs:122`）区分——那是**另一个键**，默认值与语义都不同（它默认偏好 keyring）。完整对照见 §2.5。

> [!IMPORTANT]
> **本地开发构建会静默把 `keyring` / `auto` 降为 `file`。** `resolve_cli_auth_credentials_store_mode()`（`codex-rs/core/src/config/mod.rs:288-299`）在 `CARGO_PKG_VERSION` 等于 `LOCAL_DEV_BUILD_VERSION`（`"0.0.0"`，`codex-rs/core/src/config/mod.rs:271`）时，把 `Keyring` 和 `Auto` 一律改写成 `File`。
>
> ⇒ **从源码构建的 Codex 不会用钥匙串**，无论 `config.toml` 怎么配。"我配了 keyring，凭证却出现在 `auth.json` 里"最常见的原因就是这条——在发版二进制上复现不出来。这是**第三处**会静默改写 `cli_auth_credentials_store` 的逻辑（另外两处：§2.4 的 `ChatgptAuthTokens` 强制 `Ephemeral`、§2.3 的 feature 开关）。<!-- ref-exempt: `config.toml` 泛指用户配置文件，不指仓库内任一同名文件 -->

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

**含义**：`cli_auth_credentials_store = "keyring"`（或 `auto` 命中钥匙串）时，该 feature 决定用哪一种钥匙串后端。

> [!CAUTION]
> **勘误：上一稿写的"开启该 feature 会把凭证路由到加密的本地 secrets 后端，而不是<u>直接</u>用系统钥匙串"，把两者说成了互斥关系——不成立。**
>
> **`Secrets` 后端仍然用系统钥匙串**，只是钥匙串里存的东西换了：
>
> | 后端 | 凭证本体在哪 | 系统钥匙串里存什么 |
> | ---- | ---- | ---- |
> | **`Direct`**（feature 关闭） | 系统钥匙串 | **序列化后的凭证本身** |
> | **`Secrets`**（feature 开启） | `$CODEX_HOME/secrets/codex_auth.age`（加密文件） | **解密用的文件密钥** |
>
> 依据是 `AuthKeyringBackendKind` 两个变体的文档注释（`codex-rs/config/src/types.rs:140`、`:142`）：
>
> > `Direct`：*"Store the serialized auth payload directly in the OS keyring."*
> > `Secrets`：*"Store auth payloads in the local encrypted secrets file, **with the file key in the OS keyring**."*
>
> ⇒ **两种后端都依赖系统钥匙串可用**，`Secrets` 并没有绕开它。把 `Secrets` 理解成"不用钥匙串的方案"，会在钥匙串不可用的排查中判断错方向。

后端枚举与落点：

| 落点 | 位置 |
| ---- | ---- |
| `AuthKeyringBackendKind::{Direct, Secrets}` | `codex-rs/config/src/types.rs:136-144` |
| `Direct` 的钥匙串命名 | service `"Codex Auth"`（`KEYRING_SERVICE`，`codex-rs/login/src/auth/storage.rs:231`）；account 由 `compute_store_key()`（`codex-rs/login/src/auth/storage.rs:234-245`）算出，形如 `cli\|<canonical codex_home 的 sha256 前 16 个 hex 字符>` |
| `Secrets` 的加密文件 | `$CODEX_HOME/secrets/` 下，文件名常量见 `codex-rs/secrets/src/local.rs:37-39`：`LOCAL_SECRETS_FILENAME`、**`CODEX_AUTH_SECRETS_FILENAME`**（CLI 认证用）、`MCP_OAUTH_SECRETS_FILENAME` |
| `Secrets` 的密钥名 | `CODEX_AUTH_SECRET_NAME`（`codex-rs/login/src/auth/storage.rs:226-230`） |

> [!NOTE]
> **account key 里含 `CODEX_HOME` 的哈希，意味着不同 `CODEX_HOME` 的凭证在钥匙串里互不干扰**（`codex-rs/login/src/auth/storage.rs:234-245` 先 `canonicalize()` 再 sha256 取前 16 位）。副作用是**移动或改名 `CODEX_HOME` 会导致钥匙串里已存的凭证找不到**，表现为"突然要求重新登录"，但旧条目仍留在钥匙串里。

**5 个存储后端实现**（`codex-rs/login/src/auth/storage.rs`，均实现 `AuthStorageBackend`）：

| 实现 | 位置 | 对应模式 |
| ---- | ---- | ---- |
| `FileAuthStorage` | `codex-rs/login/src/auth/storage.rs:170` | `file` |
| `DirectKeyringAuthStorage` | `codex-rs/login/src/auth/storage.rs:248` | `keyring` + `AuthKeyringBackendKind::Direct` |
| `SecretsKeyringAuthStorage` | `codex-rs/login/src/auth/storage.rs:322` | `keyring` + `AuthKeyringBackendKind::Secrets` |
| `AutoAuthStorage` | `codex-rs/login/src/auth/storage.rs:405` | `auto` |
| `EphemeralAuthStorage` | `codex-rs/login/src/auth/storage.rs:460` | `ephemeral` |

由 `create_auth_storage()`（`codex-rs/login/src/auth/storage.rs:498`）按 `(mode, backend_kind)` 二元组选择。**mode 和 backend_kind 是两个正交的枚举**——这正是 §2 开头那条 `_mode` 命名注释想要区分的东西。

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
> 1. **`default_enabled: cfg!(windows)`——在 Windows 上它默认就是开的。** 不要把它当成纯粹的"选择性加固项"来描述；在 Windows 平台上，加密本地 secrets 后端是**默认路径**，反倒是关闭它需要显式配置。原因见 §2.1.2：Windows 上没有 `0o600` 那层文件权限保护。
> 2. **上一稿说它"是 `Feature` 枚举 `// Stable.` 注释段仅有的 3 个之一，在这个以实验性为主的枚举里已属稳定"——依据用错了。** 判定成熟度的权威字段是 `stage:`，不是源码里的注释分段。按 `stage:` 统计，`Stage::Experimental` 只有 **1~2 个**（随 target 而变）；真正的成熟度分布是 **Stable 34 / UnderDevelopment 31 / Deprecated 3 / Removed 32**（共 102 个 `FeatureSpec`）——**不能用"实验性为主"概括**。详见 [`experimental_surfaces.md`](./experimental_surfaces.md) §7.4。（"`// Stable.` 注释段只有 3 个变体"这句本身是对的，只是它不能用来推断成熟度。）

#### 两条平台判据：结果一致，**可覆盖性不同**

> [!CAUTION]
> **只说"Windows 默认用 `Secrets` 后端"会漏掉最要紧的一半。** 代码里有**两条**独立的平台判据，结论相同但性质不同：
>
> | 判据 | 位置 | 能否被用户覆盖 |
> | ---- | ---- | ---- |
> | `impl Default for AuthKeyringBackendKind`：`if cfg!(windows) { Secrets } else { Direct }` | `codex-rs/config/src/types.rs:146-154` | ❌ **不可配置**——编译期常量 |
> | feature `secret_auth_storage` 的 `default_enabled: cfg!(windows)` | `codex-rs/features/src/lib.rs:852-857`，经 `auth_keyring_backend_kind_from_secret_auth_storage()`（`codex-rs/core/src/config/auth_keyring.rs:47-54`）转换 | ✅ **可被 `[features] secret_auth_storage = false` 覆盖** |
>
> **生产 `Config` 走的是第二条**（`Config::auth_keyring_backend_kind()`，`codex-rs/core/src/config/auth_keyring.rs:11-15`）。第一条只在拿不到 `Config` 的场合兜底——例如 `load_auth()` 里构造 ephemeral 存储时直接用 `AuthKeyringBackendKind::default()`（`codex-rs/login/src/auth/manager.rs:1237`）。
>
> ⇒ **两条路径在代码里混用。** 这意味着：在 Windows 上把 `secret_auth_storage` 关掉，**只影响走 `Config` 的路径**，走 `Default::default()` 的兜底路径仍然是 `Secrets`。评估"关掉这个 feature 会发生什么"时，必须把两条路径分别过一遍。

另有 `resolve_bootstrap_auth_keyring_backend_kind`（`codex-rs/core/src/config/auth_keyring.rs:22-45`），用于**在完整 `Config` 构建之前**就得读认证的启动路径——它从 bootstrap 配置重建一份 `Features` 再走同一个转换函数，因此与第二条判据一致。

### 2.4 `ChatgptAuthTokens` 会**静默覆盖** `cli_auth_credentials_store`（E3，本轮补入）

`AuthDotJson::storage_mode()`（`codex-rs/login/src/auth/manager.rs:1509-1518`）：

```rust
fn storage_mode(
    &self,
    auth_credentials_store_mode: AuthCredentialsStoreMode,
) -> AuthCredentialsStoreMode {
    if self.resolved_mode() == AuthMode::ChatgptAuthTokens {
        AuthCredentialsStoreMode::Ephemeral
    } else {
        auth_credentials_store_mode
    }
}
```

> [!IMPORTANT]
> **`ChatgptAuthTokens` 模式下，用户配置的存储模式一律被丢弃并改为 `Ephemeral`——没有警告，没有日志。**
>
> 这对排查**"为什么配了 `cli_auth_credentials_store = "keyring"` 却什么都没存进钥匙串"**是决定性信息。三个候选原因按排查成本排序：
>
> 1. **当前是 `ChatgptAuthTokens` 模式**（本节）——宿主应用注入的凭证本就只允许留在内存里。
> 2. **本地开发构建**（§2.2）——`CARGO_PKG_VERSION == "0.0.0"` 时 `keyring`/`auto` 被降为 `file`。
> 3. 钥匙串本身不可用——只有 `auto` 会静默回落，`keyring` 会直接失败。
>
> 注意这条降级发生在 `resolved_mode()` 之上，因此**同样受 §2.1.1 推断顺序的影响**。

### 2.5 CLI 登录 vs MCP OAuth：**两套独立体系**（E3，本轮补入）

`$CODEX_HOME` 下有两套互不相干的凭证存储。它们的键名、枚举、默认值、落点全都不同，**极易互相套用**：

| 维度 | CLI 登录 | MCP OAuth |
| ---- | ---- | ---- |
| 配置键 | `cli_auth_credentials_store` | `mcp_oauth_credentials_store` |
| 枚举 | `AuthCredentialsStoreMode`（4 变体，`codex-rs/config/src/types.rs:107-117`） | `OAuthCredentialsStoreMode`（3 变体，`codex-rs/config/src/types.rs:119-134`） |
| **默认值** | **`File`**（`#[default]` 在 `codex-rs/config/src/types.rs:108`） | **`Auto`**（`#[default]` 在 `codex-rs/config/src/types.rs:127`） |
| 文件后端 | `$CODEX_HOME/auth.json` | `$CODEX_HOME/.credentials.json`（`FALLBACK_FILENAME`，`codex-rs/rmcp-client/src/oauth.rs:611`；路径构造 `:825-827`） |
| Keyring service | `"Codex Auth"`（`codex-rs/login/src/auth/storage.rs:231`） | `"Codex MCP Credentials"`（`codex-rs/rmcp-client/src/oauth.rs:76`） |
| Secrets 文件 | `CODEX_AUTH_SECRETS_FILENAME`（`codex-rs/secrets/src/local.rs:38`） | `MCP_OAUTH_SECRETS_FILENAME`（`codex-rs/secrets/src/local.rs:39`） |
| Unix 权限 | `0o600`，**`open` 时**经 `OpenOptions::mode()`（`codex-rs/login/src/auth/storage.rs:213`） | `0o600`，**写完后**经 `set_permissions()`（`codex-rs/rmcp-client/src/oauth.rs:868-873`） |

> [!IMPORTANT]
> **默认行为的差异比键名差异更值得记住：CLI 默认写明文 `auth.json`，MCP 默认优先写 keyring。**
>
> 也就是说，"Codex 默认把凭证存哪"这个问题**没有单一答案**——取决于问的是哪一套。回答"Codex 默认不用钥匙串"时若只看了 CLI 侧，对 MCP 侧就是错的。

> [!WARNING]
> **`.credentials.json` 带一条比 `auth.json` 更强的明文安全警示，却长期没被记录。** `OAuthCredentialsStoreMode::File` 变体的文档注释（`codex-rs/config/src/types.rs:129-131`）：<!-- ref-exempt: `.credentials.json` 是运行期产物（$CODEX_HOME 下），仓库中不存在该文件属预期 -->
>
> > *"CODEX_HOME/.credentials.json — **This file will be readable to Codex and other applications running as the same user.**"*
>
> 这句话说的是 `0o600` 保护不了的那一半威胁模型：**同用户运行的任何进程**（包括其他 CLI 工具、编辑器插件、被安装的恶意包）都能读它。相比之下 `auth.json` 那边只有"承载明文凭证"这一句泛泛的提醒。
>
> 模块头注释（`codex-rs/rmcp-client/src/oauth.rs:17`）说明了为何仍保留这个回退：*"If the keyring is not available or fails, we fall back to CODEX_HOME/.credentials.json which is consistent with other coding CLI agents."*——是**为了与其他编码 CLI 代理保持一致**，属有意识的取舍，不是疏漏。已补入 §8 安全约束表。

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
| `env_key_instructions` | `env_key` 未设置时展示给用户的**提示文案**（`codex-rs/model-provider-info/src/lib.rs:98-100`）——**不是认证机制**，见 §3.2 勘误 |

### 3.2 认证（**四选一，`validate()` 强制互斥**）

| 字段 | 说明 |
| ---- | ---- |
| `env_key` | **推荐**：存放 API key 的环境变量名 |
| `experimental_bearer_token` | 直接给 `Authorization: Bearer <token>` 的值 |
| `auth` (`ModelProviderAuthInfo`) | 命令驱动的 bearer token |
| `aws` (`ModelProviderAwsAuthInfo`) | AWS SigV4（`profile` / `region`，`codex-rs/model-provider-info/src/lib.rs:150-153`） |

> [!CAUTION]
> **勘误：上一稿标题写"四选一**或组合**"——"或组合"不成立。** `ModelProviderInfo::validate()`（`codex-rs/model-provider-info/src/lib.rs:157-214`）会在**配置加载期**显式拒绝组合，详见 §3.6。
>
> 另外，**`env_key_instructions` 不是认证机制**，上一稿把它列进这张表是分类错误。它只是 `env_key` 未设置时的**提示文案**（`codex-rs/model-provider-info/src/lib.rs:98-100`），会被塞进 `EnvVarError.instructions`（`codex-rs/model-provider-info/src/lib.rs:295`）显示给用户。它不参与任何认证判定，因此也不参与互斥校验——已从本表移出，见 §3.1。

> [!WARNING]
> `experimental_bearer_token` 的字段注释明确写道（`codex-rs/model-provider-info/src/lib.rs:101-104`）："Use of this config is **discouraged in favor of `env_key`** for security reasons, but this may be necessary when using this programmatically."
>
> **优先用 `env_key`，不要把 token 直接写进配置文件。**

> [!WARNING]
> **`auth` 字段是配置驱动的任意命令执行。** `ModelProviderAuthInfo` 携带一个 `command`，由 `run_provider_auth_command()`（`codex-rs/login/src/auth/external_bearer.rs:102`）通过 `Command::new()`（`:104`）拉起子进程取 bearer token。
>
> ⇒ **能写 `model_providers.<id>.auth` 的人，就能让 Codex 执行任意命令。** 唯一的结构性防护是 `model_providers` 在 `PROJECT_LOCAL_CONFIG_DENYLIST` 里（`codex-rs/config/src/loader/mod.rs:64-76`），因此**项目级配置文件无法引入 provider**——一个 clone 下来的仓库不能借此在你机器上执行命令。已补入 §8。

`env_key` 的取值由 `ModelProviderInfo::api_key()`（`codex-rs/model-provider-info/src/lib.rs:286-301`）直接 `std::env::var(env_key)` 读取，**变量名完全由配置指定、无白名单**；未设置或全空白时报 `EnvVarError` 并附上 `env_key_instructions`。

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

### 3.5 能力开关（本轮补入，上一稿漏列）

| 字段 | 位置 | 说明 |
| ---- | ---- | ---- |
| `requires_openai_auth` | `codex-rs/model-provider-info/src/lib.rs:139` | 是否需要 OpenAI API key / ChatGPT 登录；`true` 时首次运行弹登录界面 |
| **`supports_websockets`** | `codex-rs/model-provider-info/src/lib.rs:142` | *"Whether this provider supports the Responses API WebSocket transport."* |
| **`supports_standalone_web_search`** | `codex-rs/model-provider-info/src/lib.rs:145` | *"Whether this provider supports the standalone web-search endpoint."* |

三者都带 `#[serde(default)]`，即**默认 `false`**——省略等于关闭。

> **上一稿的推断可以升级为直证。** 原文写"**存在 WebSocket 超时字段**，说明部分 provider 走 WebSocket 而非纯 HTTP 流"——这是从超时字段反推能力，属推断。实际有一个**直接的布尔开关** `supports_websockets`（`codex-rs/model-provider-info/src/lib.rs:142`），且内置 `openai` provider 明确设为 `true`（`codex-rs/model-provider-info/src/lib.rs:365`）。结论不变，但依据从"存在某个超时字段"换成"存在一个名为 supports_websockets 的字段并被置为 true"。（另见 `codex-websocket-client`、`codex-rs/core/tests/suite/client_websockets.rs`。）

### 3.6 `validate()`：配置面唯一的运行期校验（E3，本轮补入）

`ModelProviderInfo::validate()`（`codex-rs/model-provider-info/src/lib.rs:157-214`）是 provider 配置**唯一**的运行期校验逻辑——用户看到的 provider 配置错误信息**全部**由这里产生。规则有三组：

| # | 规则 | 报错信息 | 位置 |
| ---: | ---- | ---- | ---- |
| 1 | `aws` **不能**与 `supports_websockets` 同时出现 | `provider aws cannot be combined with supports_websockets` | `codex-rs/model-provider-info/src/lib.rs:159-166` |
| 2 | `aws` **不能**与 `env_key` / `experimental_bearer_token` / `auth` / `requires_openai_auth` 同时出现 | `provider aws cannot be combined with <逗号分隔的冲突项>` | `codex-rs/model-provider-info/src/lib.rs:168-186` |
| 3 | `auth.command` **不得**为空白 | `provider auth.command must not be empty` | `codex-rs/model-provider-info/src/lib.rs:192-194` |
| 4 | `auth` **不能**与 `env_key` / `experimental_bearer_token` / `requires_openai_auth` 同时出现 | `provider auth cannot be combined with <逗号分隔的冲突项>` | `codex-rs/model-provider-info/src/lib.rs:196-213` |

要点：

- **冲突项是累加后一次报出的**（两处都先 `Vec::push` 再 `join(", ")`），所以一条错误信息里可能列出多个字段。看到 `cannot be combined with env_key, requires_openai_auth` 是**一次**校验的结果，不是两次。
- **规则 1 单独成条且带 `TODO` 注释**（`codex-rs/model-provider-info/src/lib.rs:160-162`）：AWS SigV4 尚不支持对 WebSocket 升级请求签名，因此这是**暂时**的限制而非设计约束——上游实现后可能取消。其余互斥是设计使然。
- **规则 3 先于规则 4 检查**：`auth` 存在但 `command` 为空时，先报 `must not be empty`，即使同时还有别的冲突。
- **`env_key` 与 `experimental_bearer_token` 之间不互斥**——两者可以同时配置，`validate()` 不拦。§3.2 的"四选一"指的是 `aws` / `auth` 与其余认证字段之间的关系。

### 3.7 内置 provider：4 个，且**只能扩展不能覆盖**（E3，本轮补入）

`built_in_model_providers()`（`codex-rs/model-provider-info/src/lib.rs:438-464`）：

| provider id | 常量 | 要点 |
| ---- | ---- | ---- |
| `openai` | `OPENAI_PROVIDER_ID`（`codex-rs/model-provider-info/src/lib.rs:37`） | `requires_openai_auth: true`、`supports_websockets: true`、`supports_standalone_web_search: true`（`codex-rs/model-provider-info/src/lib.rs:364-366`）；`env_http_headers` 预置 `OPENAI_ORGANIZATION` / `OPENAI_PROJECT`（`:348-358`） |
| `amazon-bedrock` | `AMAZON_BEDROCK_PROVIDER_ID`（`codex-rs/model-provider-info/src/lib.rs:40`） | `base_url: None` 时由运行期推导区域端点，**配了值就是明确的端点覆盖**（`:375-378`） |
| `ollama` | `OLLAMA_OSS_PROVIDER_ID`（`codex-rs/model-provider-info/src/lib.rs:435`） | 经 `create_oss_provider(DEFAULT_OLLAMA_PORT, ...)`，默认端口 **11434**（`codex-rs/model-provider-info/src/lib.rs:432`） |
| `lmstudio` | `LMSTUDIO_OSS_PROVIDER_ID`（`codex-rs/model-provider-info/src/lib.rs:434`） | 经 `create_oss_provider(DEFAULT_LMSTUDIO_PORT, ...)`，默认端口 **1234**（`codex-rs/model-provider-info/src/lib.rs:431`） |

源码注释说明了为什么只有这 4 个（`codex-rs/model-provider-info/src/lib.rs:445-448`）：

> *"We do not want to be in the business of adjucating which third-party providers are bundled with Codex CLI, so we only include the OpenAI and open source ("oss") providers by default. Users are encouraged to add to `model_providers` in config.toml to add their own providers."*

**`merge_configured_model_providers()`（`codex-rs/model-provider-info/src/lib.rs:471-507`）的合并语义**：

- 一般情况走 `model_providers.entry(key).or_insert(provider)`（`codex-rs/model-provider-info/src/lib.rs:503`）——**`or_insert` 意味着同名时保留内置项、丢弃用户配置**。用户 provider **只能扩展**内置集，**不能覆盖内置项**。
- **唯一例外是 `amazon-bedrock`**（`codex-rs/model-provider-info/src/lib.rs:476-501`）：允许改 `base_url` / `auth` / `http_headers` / `aws.profile` / `aws.region`；把这几项 `take()` 走之后若剩余部分 `!= ModelProviderInfo::default()`，直接报错——
  `model_providers.amazon-bedrock only supports changing base_url, auth, http_headers, aws.profile, and aws.region; other non-default provider fields are not supported`

> [!IMPORTANT]
> **"配了同名 provider 却不生效"是静默的。** 除 `amazon-bedrock` 外，试图覆盖 `openai` / `ollama` / `lmstudio` 不会报错，配置只是被 `or_insert` 无声丢弃。想改内置 provider 的行为，要么换个 id，要么用 §5.1 的 `CODEX_OSS_BASE_URL` 之类的专用入口。

---

## 4. `WireApi`：只剩一个变体（E3）

```rust
// codex-rs/model-provider-info/src/lib.rs:57
pub enum WireApi {
    /// The Responses API exposed by OpenAI at `/v1/responses`.
    #[default]
    Responses,
}
```

> [!IMPORTANT]
> **`WireApi` 现在只有 `Responses` 一个变体。** 曾经存在的 `chat` 已被移除。
>
> 源码中保留了两条迁移错误信息（`codex-rs/model-provider-info/src/lib.rs:51-52`）：
>
> | 场景 | 错误提示要点 |
> | ---- | ---- |
> | `wire_api = "chat"` | 不再支持。改用 `wire_api = "responses"` |
> | provider id `ollama-chat` | 不再支持。在 `model_provider` / `oss_provider` / `--local-provider` 中把 `ollama-chat` 换成 `ollama` |
>
> 两条提示都指向同一个讨论帖：`github.com/openai/codex/discussions/7782`。
>
> 常量分别是 `CHAT_WIRE_API_REMOVED_ERROR`（`codex-rs/model-provider-info/src/lib.rs:50`）与 `OLLAMA_CHAT_PROVIDER_REMOVED_ERROR`（`codex-rs/model-provider-info/src/lib.rs:52`）；`LEGACY_OLLAMA_CHAT_PROVIDER_ID`（`codex-rs/model-provider-info/src/lib.rs:51`）仍在，用于识别旧 id 并给出上述提示。
>
> **两条都是"定向报错"而非静默忽略**——与 §3.7 里覆盖内置 provider 时的静默丢弃形成对比。移除能力时给出可执行的迁移提示，是这个 crate 里一致的做法。

**含义**：Codex 已完全转向 Responses API。写文档或做集成时不要再提 Chat Completions 路径。

---

## 5. 本地与第三方模型接入

| crate | 目录 | 行数 | 目标 |
| ---- | ---- | ---: | ---- |
| `codex-ollama` | `codex-rs/ollama/` | 1,107 | Ollama |
| `codex-lmstudio` | `codex-rs/lmstudio/` | 470 | LM Studio |
| `codex-aws-auth` | `codex-rs/aws-auth/` | 375 | AWS（Bedrock 场景） |
| `codex-model-provider` | `codex-rs/model-provider/` | 3,247 | provider 抽象 |
| `codex-models-manager` | `codex-rs/models-manager/` | 2,722 | 模型管理 |
| `codex-backend-client` | `codex-rs/backend-client/` | 2,258 | 后端客户端 |
| `codex-backend-openapi-models` | ⚠️ **`codex-rs/codex-backend-openapi-models/`** | 1,017 | 后端 OpenAPI 模型 |

> [!NOTE]
> **最后一行的目录名有前缀重复，不符合其余 crate 的规律。** 其他 crate 都是 `codex-rs/<去掉 codex- 前缀的短名>/`（`codex-ollama` → `codex-rs/ollama/`），唯独 `codex-backend-openapi-models` 的目录是 **`codex-rs/codex-backend-openapi-models/`**——crate 名整体作为目录名，`codex` 出现了两次。
>
> ⇒ **按惯例推路径（`codex-rs/backend-openapi-models/`）会找不到。** 上一稿只给了 crate 名和行数，读者按规律去找必然扑空。行数 1,017 本身正确。

相关 CLI 参数：`--local-provider`（定义在 **`codex-rs/utils/cli/src/shared_options.rs:29-32`**，**不在** `codex-rs/cli/src/main.rs`）、`--oss`（`codex-rs/utils/cli/src/shared_options.rs:26`）；配置键：`model_provider`、`oss_provider`。

### 5.1 `CODEX_OSS_BASE_URL` / `CODEX_OSS_PORT`：本地模型接入的**真正入口**（E3，本轮补入）

> [!IMPORTANT]
> **上一稿的 §5 只有 crate 行数和三个配置键，完全没说 provider 是怎么被构造出来的**——而这正是"如何接入本地模型"这个问题的答案所在。

构造入口是 `create_oss_provider()`（`codex-rs/model-provider-info/src/lib.rs:510-527`）：

```rust
pub fn create_oss_provider(default_provider_port: u16, wire_api: WireApi) -> ModelProviderInfo {
    // These CODEX_OSS_ environment variables are experimental: we may
    // switch to reading values from config.toml instead.
    let default_codex_oss_base_url = format!(
        "http://localhost:{codex_oss_port}/v1",
        codex_oss_port = std::env::var("CODEX_OSS_PORT") /* ...解析失败则用 default_provider_port... */
    );
    let codex_oss_base_url = std::env::var("CODEX_OSS_BASE_URL") /* ...空值过滤... */ ;
    create_oss_provider_with_base_url(&codex_oss_base_url, wire_api)
}
```

| 环境变量 | 作用 | 位置 |
| ---- | ---- | ---- |
| **`CODEX_OSS_PORT`** | 覆盖 `http://localhost:<port>/v1` 里的端口；解析失败或为空则用调用方给的默认端口 | `codex-rs/model-provider-info/src/lib.rs:515-519` |
| **`CODEX_OSS_BASE_URL`** | **整体覆盖 base URL**，优先级高于 `CODEX_OSS_PORT`（后者只影响被覆盖掉的默认值） | `codex-rs/model-provider-info/src/lib.rs:522-525` |

**源码注释自称这两个变量是实验性的**（`codex-rs/model-provider-info/src/lib.rs:511-512`）：*"These CODEX_OSS_ environment variables are experimental: we may switch to reading values from config.toml instead."*——但**变量名里没有任何 `EXPERIMENTAL` / `experimental_` 标记**。

`create_oss_provider_with_base_url()`（`codex-rs/model-provider-info/src/lib.rs:529-550`）产出的 provider 各字段是**写死**的：

| 字段 | 值 | 位置 |
| ---- | ---- | ---- |
| `name` | `"gpt-oss"`（固定，**与 provider id 无关**） | `codex-rs/model-provider-info/src/lib.rs:531` |
| `env_key` | `None` | `codex-rs/model-provider-info/src/lib.rs:533` |
| `experimental_bearer_token` / `auth` / `aws` | 全 `None` | `codex-rs/model-provider-info/src/lib.rs:535-537` |
| **`requires_openai_auth`** | **`false`** | `codex-rs/model-provider-info/src/lib.rs:546` |
| `supports_websockets` / `supports_standalone_web_search` | 全 `false` | `codex-rs/model-provider-info/src/lib.rs:547-548` |

> [!IMPORTANT]
> **本地模型路径完全不走认证。** 四个认证字段全是 `None`，`requires_openai_auth` 是 `false`——`--oss` / `oss_provider` 选中的 provider 既不读环境变量、不发 `Authorization` 头，也不触发登录界面。
>
> 这是理解 §1 那七种 `AuthMode` 的边界所在：**它们描述的是 Codex 后端与 OpenAI 兼容 API 的认证，不覆盖本地 provider**。排查"本地模型为什么不要求登录"时，答案就是这几行常量，不在 `AuthMode` 那边。
>
> 注意 `ollama` 与 `lmstudio` 两个内置 provider 都由 `create_oss_provider()` 构造（§3.7），因此**同一组 `CODEX_OSS_*` 环境变量会同时影响两者**——它们只在 `default_provider_port` 上有区别，而 `CODEX_OSS_BASE_URL` 恰恰把这个区别抹平。

> [!WARNING]
> **`CODEX_OSS_BASE_URL` 与 `--experimental_issuer` 属同一风险类别：无校验地改写请求目标地址。** 差别在于**它更容易被误用**——既不隐藏、变量名也没有 `experimental_` 前缀，只有源码注释里提了一句"experimental"。设置它会把所有本地 provider 的流量导向指定地址，而该路径**不发送任何凭证**，因而也没有"凭证泄漏"这个显性信号提示配置被改写。已补入 §8 安全约束表。

配套常量：

| 常量 | 值 | 位置 |
| ---- | ---- | ---- |
| `DEFAULT_OLLAMA_PORT` | 11434 | `codex-rs/model-provider-info/src/lib.rs:432` |
| `DEFAULT_LMSTUDIO_PORT` | 1234 | `codex-rs/model-provider-info/src/lib.rs:431` |
| `OLLAMA_OSS_PROVIDER_ID` | `"ollama"` | `codex-rs/model-provider-info/src/lib.rs:435` |
| `LMSTUDIO_OSS_PROVIDER_ID` | `"lmstudio"` | `codex-rs/model-provider-info/src/lib.rs:434` |

未配置默认 OSS provider 时的报错信息在 `codex-rs/exec/src/lib.rs:396-398`，会把上面两个 id 列进提示。

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
| `codex login status` | 查看登录态（`codex-rs/cli/src/main.rs:1375-1377` 的 `LoginSubcommand::Status` 分支 → `run_login_status`） |
| `codex doctor` | 诊断本地安装、配置、认证与运行时健康；认证相关检查见 `codex-rs/cli/src/doctor.rs:1375`、`:2623` |
| `account/*` 协议方法（13 个） | app-server：登录、额度、用量、工作区消息 |

`account` 命名空间的 13 个方法包括 `account/login/start`、`/cancel`、`/completed`、`account/logout`、`account/rateLimits/read`、`account/usage/read`、`account/chatgptAuthTokens/refresh` 等。

> [!IMPORTANT]
> **`account/login/start` 与 `account/chatgptAuthTokens/refresh` 的方向相反，不要当成一对。**
>
> - `account/login/start` 是 **client→server 的 `ClientRequest`**，其 `LoginAccountParams::ChatgptAuthTokens` 变体（`codex-rs/app-server-protocol/src/protocol/v2/account.rs:84-89`）是**外部注入凭证的入口**。
> - `account/chatgptAuthTokens/refresh` 是 **server→client 的 `ServerRequest`**（`codex-rs/app-server-protocol/src/protocol/common.rs:1569`），是 Codex **反向**向宿主要新 token 的**刷新回调**，实现在 `codex-rs/app-server/src/external_auth.rs`。
>
> 上一稿在 §1 把后者写成了 `ChatgptAuthTokens` 的"典型入口"，方向恰好反了。

**远程 app-server 的 bearer token**：`--remote-auth-token-env <ENV_VAR>`（`codex-rs/cli/src/main.rs:906-909`）——注意它接受的是**环境变量的名字**，不是 token 本身；读取逻辑在 `read_remote_auth_token_from_env_var()`（`codex-rs/cli/src/main.rs:2344-2346`），变量不存在或为空都会报错。**没有硬编码的默认变量名**（`CODEX_REMOTE_AUTH_TOKEN` 只是测试里用的约定名，全部命中都在 `codex-rs/cli/src/main.rs` 的 `#[cfg(test)]` 段内，该段从 `:2614` 开始）。

---

## 8. 安全约束

| 约束 | 说明 |
| ---- | ---- |
| 优先 `env_key`，避免 `experimental_bearer_token` | 字段注释明文建议（`codex-rs/model-provider-info/src/lib.rs:101-104`）——**明文 token 落在 `config.toml` 里** <!-- ref-exempt: `config.toml` 泛指用户配置文件，不指仓库内任一同名文件 --> |
| **`model_providers.<id>.auth` 是配置驱动的任意命令执行** | §3.2——`run_provider_auth_command()`（`codex-rs/login/src/auth/external_bearer.rs:102`）拉起子进程 |
| 上面两项被 `PROJECT_LOCAL_CONFIG_DENYLIST` 挡在项目层之外 | `model_providers` 在denylist 里（`codex-rs/config/src/loader/mod.rs:64-76`），**clone 的仓库无法借此注入 provider** |
| 敏感请求头用 `env_http_headers` 而非 `http_headers` | 同上机制 |
| MCP server 用 `bearer_token_env_var`，不要用 `bearer_token` | `bearer_token` 被**双重封堵**：`#[schemars(skip)]` 使其不出现在 schema（`codex-rs/config/src/mcp_types.rs:283`），两种 transport 都 `throw_if_set(..., "bearer_token", ...)`（`codex-rs/config/src/mcp_types.rs:379`、`:401`） |
| 文档中**只写变量名、键名、路径**，不写值 | 本体系脱敏规范 |
| 测试夹具中的假 token 不得引入文档 | 同上 |
| **不要向普通用户推荐 `--experimental_issuer` / `--experimental_client-id`** | §1.3——可把 OAuth 流程指向任意 issuer |
| **四个端点/客户端标识重定向环境变量同样计入攻击面** | §1.3.1——`CODEX_REFRESH_TOKEN_URL_OVERRIDE`、`CODEX_REVOKE_TOKEN_URL_OVERRIDE`、`CODEX_APP_SERVER_LOGIN_CLIENT_ID`、**`CODEX_AUTHAPI_BASE_URL`**（后者既不隐藏也无 `experimental_` 前缀，最易误用） |
| **`CODEX_OSS_BASE_URL` / `CODEX_OSS_PORT` 无校验地改写本地 provider 基址** | §5.1——与 `--experimental_issuer` 同类；源码注释自称 experimental 但变量名无标记 |
| **`$CODEX_HOME/auth.json` 承载明文凭证**，不要整体粘贴到 issue 或日志 | §2.1；Unix 下有 `0o600`（§2.1.2），**Windows 下没有** |
| **`$CODEX_HOME/.credentials.json`（MCP OAuth 回退）明文，且注释警告"同用户的其他应用可读"** | §2.5——`codex-rs/config/src/types.rs:129-131`。这条警示比 `auth.json` 那条更强 |
| 需要更强的本地保护时用 `cli_auth_credentials_store = "keyring"` + `Feature::SecretAuthStorage` | §2.2 / §2.3；注意本地开发构建（`0.0.0`）会把 `keyring` 静默降为 `file` |
| ⚠️ **`forced_login_method` / `forced_chatgpt_workspace_id` 放在 `/etc/codex/config.toml` 里拦不住用户** | 见下方强制力边界 |
| 遥测中的认证环境信息见 `codex-rs/login/src/auth_env_telemetry.rs` | 与 [`observability.md`](./observability.md) 相关 |

### 8.1 强制力边界：`forced_*` 键**不是**管理员强制项（E3，本轮补入）

`forced_login_method` 与 `forced_chatgpt_workspace_id` 是**普通 `ConfigToml` 字段**（`codex-rs/config/src/config_toml.rs:243`、`:247`），不是 `requirements.toml` 字段。它们在 `codex-rs/core/config.schema.json` 的顶层键里，**用户在自己的 `$CODEX_HOME/config.toml` 里就能改写**。

配置层优先级（`ConfigLayerSource::precedence()`，`codex-rs/config/src/config_layer_source.rs:31-48`；**数值大者胜**）：

| 层 | 数值 |
| ---- | ---: |
| `Mdm` | **0** |
| `System`（`/etc/codex/config.toml`） | 10 |
| `EnterpriseManaged` | 15 |
| `User`（`$CODEX_HOME/config.toml`） | 20（带 profile 时 21） |
| `Project` | 25 |
| `SessionFlags` | 30 |
| `LegacyManagedConfigTomlFromFile` | 40 |
| `LegacyManagedConfigTomlFromMdm` | **50** |

> [!WARNING]
> **`System` 层是 10，会被 `User` 层（20）盖掉——管理员把 `forced_login_method` 写进 `/etc/codex/config.toml` 是拦不住用户的。**
>
> 要真正强制，得用优先级高于 `User` 的层：`LegacyManagedConfigTomlFromFile`（40）或 `LegacyManagedConfigTomlFromMdm`（50）。
>
> ⚠️ **额外的陷阱：`ConfigLayerSource::Mdm` 的优先级是 0，即最低。** 名字里有 "MDM" 不等于优先级高——高优先级的那个变体叫 `LegacyManagedConfigTomlFromMdm`（50）。这两个变体名相近而优先级相差 50，**是本表最容易读反的一处**。
>
> 判据可以直接从源码注释确认（`codex-rs/config/src/config_layer_source.rs:51-52`）：*"Compares [ConfigLayerSource] by precedence, so `A < B` means settings from layer `A` will be overridden by settings from layer `B`."*——**数值小的被覆盖**。

---

## 9. 本文未覆盖的内容

> [!IMPORTANT]
> **本轮把 5 项从"未覆盖 E1"升级为"已覆盖 E3"。** 它们并非真的缺证据，而是**上一稿没去找**——静态证据一直都在。写"未覆盖"之前应先确认是"找过而没有"，还是"没找过"；把后者记成前者，会让这张表变成掩盖工作量的地方，而不是暴露风险的地方。

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| ~~`auth.json` 的结构~~ | **已在 §2.1 解决**（`AuthDotJson`） | — |
| ~~凭证在钥匙串中的具体命名与格式~~ | **已升 E3，在 §2.3 解决**：service `"Codex Auth"`（`codex-rs/login/src/auth/storage.rs:231`）、account `cli\|<sha256 前16位>`（`codex-rs/login/src/auth/storage.rs:234-245`）、`KeyringStore` trait（`codex-rs/keyring-store/src/lib.rs:42-46`） | — |
| ~~`TokenData` / `AgentIdentityStorage` / `BedrockApiKeyAuth` 的内部字段~~ | **已升 E3**：`BedrockApiKeyAuth`（`codex-rs/login/src/auth/bedrock_api_key.rs:13-17`）、`AgentIdentityStorage`（`codex-rs/login/src/auth/storage.rs:63-68`，`#[serde(untagged)]` 的 `Jwt` / `Record` 两变体）、`TokenData` 与 `IdClaims`（`codex-rs/login/src/token_data.rs:72-80`） | — |
| ~~`ChatgptAuthTokens` 与 `Headers` 两种模式的实际注入路径~~ | **已升 E3，在 §1 与 §1.4 解决**：`LoginAccountParams::ChatgptAuthTokens`（`codex-rs/app-server-protocol/src/protocol/v2/account.rs:84-89`）、`Headers` 经 `ExternalAuth` 注入且存储层拒绝（`codex-rs/login/src/auth/manager.rs:316-320`） | — |
| ~~`Feature::SecretAuthStorage` 开启后凭证的实际落点~~ | **已升 E3，在 §2.3 解决**：`$CODEX_HOME/secrets/` 下，文件名常量 `codex-rs/secrets/src/local.rs:37-39`（CLI 认证用 `CODEX_AUTH_SECRETS_FILENAME`）；密钥仍在系统钥匙串 | — <!-- ref-exempt: 检查器误报——同行的 `SecretAuthStorage` 属 Feature 枚举（codex-rs/features/src/lib.rs:92），不是 local.rs / config/types.rs 里的符号；文档 §2.3 已正确归类，未混淆。types.rs 上与之相邻的符号是 AuthKeyringBackendKind（codex-rs/config/src/types.rs:139） --> |
| OAuth 完整时序与错误分支 | E1 | `codex-rs/login/src/lib.rs`、`codex-rs/login/src/auth/manager.rs` |
| `--experimental_issuer` / `--experimental_client-id` 的校验与约束 | E1 | `codex-rs/cli/src/main.rs:489-496`、`codex-rs/login/src/lib.rs` |
| Bedrock / AWS SigV4 的签名实现 | E1 | `codex-aws-auth`、`codex-rs/login/src/auth/bedrock_api_key.rs` |
| 令牌刷新的重试/退避与过期判定细节 | E1（**入口已在 §1.3.1 / §7 澄清**） | `codex-rs/login/src/auth/manager.rs`、`codex-rs/app-server/src/external_auth.rs` |
| Ollama / LM Studio 的**发现与探测**（provider 构造已在 §5.1 覆盖） | E1 | `codex-ollama`、`codex-lmstudio` |
| `ModelProviderInfo` 剩余字段 | E3（**本轮补齐 `supports_websockets` / `supports_standalone_web_search`，见 §3.5**） | `codex-rs/model-provider-info/src/lib.rs:89` 起 |
| Agent Identity 的用途与注册流程 | E1 | `codex-agent-identity`、`codex-rs/login/src/auth/agent_identity.rs` |
| `codex-secrets` 的加密方案（age 格式、密钥派生） | E1 | `codex-rs/secrets/src/local.rs` |

---

## 10. 相关文档

- [配置体系](./config_system.md) — provider 配置的加载与层级
- [架构总览](./architecture_overview.md) §8 — 外部服务边界全景
- [可观测性](./observability.md) — 认证相关遥测
- [实验性表面](./experimental_surfaces.md) — 云任务的认证路径
