---
title: Codex 认证与模型接入
summary: 描述 codex-login 的多种认证方式与凭证存储、ModelProviderInfo 的完整配置面、WireApi 仅剩 Responses 一个变体的现状与两条已移除路径的迁移提示、本地模型接入方式，以及凭证相关的安全约束。
keywords: codex | auth | login | oauth | pkce | model-provider | wire-api | keyring | credentials
scope: codex-rs/login、model-provider-info 与相关认证凭证存储
related_files: codex-rs/model-provider-info/src/lib.rs | codex-rs/login/src/lib.rs | codex-rs/login/src/auth/storage.rs | codex-rs/keyring-store/src/lib.rs | codex-rs/cli/src/main.rs | AGENTS.md
dependencies: dev_docs/config_system.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 认证与模型接入

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 类型定义与字段为 E3；端点为 E3（源码 grep）；认证流程时序为 E1

> [!CAUTION]
> **本文不复述任何凭证的实际值。** 只记录变量名、配置键名、文件路径与端点。测试夹具中的假 token（如 `codex-rs/login/src/token_data_tests.rs` 里的样例）也不引入文档。

---

## 1. 认证方式（E3）

`codex-rs/login/src/auth/` 下的实现文件揭示了支持的认证类型：

| 方式 | 实现文件 | CLI 入口 |
| ---- | ---- | ---- |
| ChatGPT 登录（OAuth） | `access_token.rs`、`../pkce.rs`、`../server.rs`、`../callback_params.rs` | `codex login` → Sign in with ChatGPT |
| API Key | — | `codex login --api-key`（`main.rs` 的 `run_login_with_api_key`） |
| Access Token（从 stdin 读） | `access_token.rs` | `run_login_with_access_token` |
| Device Code | `../device_code_auth.rs` | `run_login_with_device_code` |
| Personal Access Token | `personal_access_token.rs` | — |
| External Bearer | `external_bearer.rs` | 由 provider 配置驱动 |
| AWS Bedrock API Key | `bedrock_api_key.rs` | 配合 `codex-aws-auth` |
| Agent Identity | `agent_identity.rs` | 配合 `codex-agent-identity` |

CLI 侧对应函数（`codex-rs/cli/src/main.rs:13-20`）：`run_login_with_chatgpt`、`run_login_with_api_key`、`run_login_with_access_token`、`run_login_with_device_code`、`run_login_status`、`run_logout`、`read_api_key_from_stdin`、`read_access_token_from_stdin`。

### OAuth 流程要素（E3）

| 要素 | 文件 |
| ---- | ---- |
| PKCE | `login/src/pkce.rs` |
| 本地回调服务器 | `login/src/server.rs` |
| 回调参数解析 | `login/src/callback_params.rs` |
| 成功页面 | `login/src/success_page.rs`、`login/src/assets/` |
| 令牌数据 | `login/src/token_data.rs` |
| 撤销 | `login/src/auth/revoke.rs` |
| 出站代理 | `login/src/outbound_proxy.rs` |

**PKCE + 本地回调服务器 + 成功页面**是标准的 CLI OAuth 形态：起本地 HTTP 服务、浏览器授权后回调、渲染成功页。

> **未验证**（E1）：完整的时序与错误处理分支。入口是 `login/src/lib.rs` 与 `auth/manager.rs`。

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
| 存储抽象 | `login/src/auth/storage.rs` | 认证态落盘 |
| 系统钥匙串 | `codex-keyring-store`（226 行） | `DefaultKeyringStore`（`lib.rs:49`）、`CredentialStoreError`（`:9`） |
| 密钥抽象 | `codex-secrets`（786 行） | — |
| 配置侧 | `core/src/config/auth_keyring.rs` | 钥匙串相关配置 |
| 配置键 | `cli_auth_credentials_store` | `config.schema.json` 顶层键之一 |

**存储位置在 `CODEX_HOME`（默认 `~/.codex`）下**，以及系统钥匙串。

`ModelProviderInfo` 的字段注释（`model-provider-info/src/lib.rs:133-137`）提到 `auth.json`：

> "Does this provider require an OpenAI API Key or ChatGPT login token? If true, user is presented with login screen on first run, and login preference and token/key are stored in `auth.json`."

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

**存在 WebSocket 超时字段**，说明部分 provider 走 WebSocket 而非纯 HTTP 流（另见 `codex-websocket-client`、`core/tests/suite/client_websockets.rs`）。

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

## 6. 相关配置键（E4）

`config.schema.json` 中与本文相关的顶层键：`chatgpt_base_url`、`cli_auth_credentials_store`、`forced_chatgpt_workspace_id`、`forced_login_method`、`allow_login_shell`、`model_provider`、`oss_provider`（后两者见完整 schema）。

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
| 遥测中的认证环境信息见 `login/src/auth_env_telemetry.rs` | 与 [`observability.md`](./observability.md) 相关 |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| OAuth 完整时序与错误分支 | E1 | `login/src/lib.rs`、`auth/manager.rs` |
| 凭证在钥匙串中的具体命名与格式 | E1 | `keyring-store/src/lib.rs`、`auth/storage.rs` |
| `auth.json` 的结构 | E1 | `login/src/token_data.rs`、`auth/storage.rs` |
| Bedrock / AWS SigV4 的签名实现 | E1 | `codex-aws-auth`、`auth/bedrock_api_key.rs` |
| 令牌刷新与过期处理 | E1 | `auth/manager.rs`、`account/chatgptAuthTokens/refresh` |
| Ollama / LM Studio 的发现与探测 | E1 | `codex-ollama`、`codex-lmstudio` |
| `ModelProviderInfo` 剩余字段 | E3（部分） | `model-provider-info/src/lib.rs:89` 起 |
| Agent Identity 的用途 | E1 | `codex-agent-identity`、`auth/agent_identity.rs` |

---

## 10. 相关文档

- [配置体系](./config_system.md) — provider 配置的加载与层级
- [架构总览](./architecture_overview.md) §8 — 外部服务边界全景
- [可观测性](./observability.md) — 认证相关遥测
- [实验性表面](./experimental_surfaces.md) — 云任务的认证路径
