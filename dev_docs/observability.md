---
title: Codex 可观测性与遥测边界
summary: 通过代码级核查确定 OTEL 三类导出器的默认值——trace 与日志（logs）导出器默认关闭、metrics 默认为 Statsig 但实际是否生效取决于各二进制传入的 default_analytics_enabled、debug 构建下 Statsig 会降级为 None；`[otel] exporter` 是唯一会外发 user.email / user.account_id 与用户提示词的通道；analytics 为 opt-out 且 debug 构建默认仍走网络（只有显式设置捕获文件环境变量才转为落盘），因此 app-server / remote-control 上不写配置时「指标不发但埋点仍发」；关闭 analytics 会连带把 OTEL metrics 导出器强制为 None；配置键是 `[analytics] enabled` 而非 `analytics_enabled`；codex-feedback 的上传目的地是第三方 Sentry，但崩溃不会自动上报。
keywords: codex | observability | otel | telemetry | statsig | analytics | sentry | opt-out | privacy | pii | otel_init
scope: codex-rs/otel、analytics、otel_init、rollout-trace、hooks、feedback 的遥测与埋点边界
related_files: codex-rs/otel/src/config.rs | codex-rs/otel/src/provider.rs | codex-rs/otel/src/events/shared.rs | codex-rs/otel/src/events/session_telemetry.rs | codex-rs/core/src/config/otel.rs | codex-rs/core/src/otel_init.rs | codex-rs/analytics/src/client.rs | codex-rs/config/src/types.rs | codex-rs/core/config.schema.json | codex-rs/state/src/telemetry.rs | codex-rs/features/src/lib.rs | codex-rs/rollout-trace/src | codex-rs/feedback/src/lib.rs | AGENTS.md
dependencies: dev_docs/config_system.md | dev_docs/architecture_overview.md
verified_at: 2026-08-05
---

# 可观测性与遥测边界

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 默认值判定为 **E3**（读取 `unwrap_or`、`resolve_exporter`、`build_provider` 实现）；配置键判定为 E2（`codex-rs/config/src/types.rs` + 生成的 `codex-rs/core/config.schema.json`）；投递链路（`build_provider` → `OtelProvider::from` → `build_logger` / `build_tracer_provider` / `MetricsClient`）亦为 **E3**（逐行读取 `codex-rs/otel/src/provider.rs:84-130`）。仍为 E1 的只剩「具体上报了哪些字段名与标签维度」一类，见 §9

> [!IMPORTANT]
> **这篇文档解决了第二个长期挂账问题。** 前两轮的 `_analysis` 与第 1 批文档都写着「遥测的默认开关尚未完整核实（E3 部分证据），不给出 release 构建是否默认上报的结论」。本文完成了核查，结论见 §1。

> [!CAUTION]
> **本文已修订，修正了初版的四处事实错误**（详见对应小节的「修订说明」）：
>
> 1. §3.2 原写「debug 构建下网络投递关闭」——**错误**。debug 构建默认仍然走 HTTP 投递，只有显式设置捕获文件环境变量才落盘。
> 2. §5 原写「两条通路是独立的」——**方向反了**。关闭 analytics 会连带把 OTEL metrics 导出器强制为 `None`。
> 3. 全文原用 `analytics_enabled` 作为配置键——**它不是配置键**，真实键是 `[analytics] enabled`。（后续修订又更正了此处的**机制**描述：写错的键默认是被**静默忽略**，不是"被拒绝"；只有加 `--strict-config` 才会报错。见 §5。）
> 4. §1/§8 原写「metrics 默认外发」——**默认值由各二进制自行传入**：TUI / exec / mcp-server 传 `true`，app-server / remote-control / exec-server 遥测传 `false`。（注意：后续修订发现 `crate_map.md` 与 `architecture_overview.md` 一度把这条收窄成"只有 TUI"，那同样是错的；以 §1.2 的六行表为准。）

---

## 1. 核心结论：三类导出器，默认值各不相同（E3）

`codex-rs/core/src/config/otel.rs:13-21` 是默认值的权威位置：

```rust
let log_user_prompt  = config.log_user_prompt.unwrap_or(false);
let exporter         = config.exporter.unwrap_or(OtelExporterKind::None);
let trace_exporter   = config.trace_exporter.unwrap_or(OtelExporterKind::None);
let metrics_exporter = config.metrics_exporter.unwrap_or(OtelExporterKind::Statsig);
```

| 项 | 默认值 | 含义 |
| ---- | ---- | ---- |
| `log_user_prompt` | **`false`** | **用户提示词默认不记录**；未开启时字段被替换为 `"[REDACTED]"`（见下方 CAUTION） |
| `exporter`（**日志 / logs 导出器**） | **`None`** | 默认不导出。**这是唯一会外发 `user.email`、`user.account_id` 与用户提示词的通道**——`log_user_prompt` 只在此通道生效；`trace_exporter` 走的 `trace_event!` 刻意剔除了这三项。故即使误设 `log_user_prompt = true`，只要 `exporter` 保持 `None`，提示词仍不会外发 |
| `trace_exporter` | **`None`** | **追踪默认不导出**；即使打开也不含邮箱、账号 ID 与提示词原文 |
| `metrics_exporter` | **`Statsig`** | 指标**配置层**默认指向 Statsig（是否真的生效见下） |

> [!IMPORTANT]
> **准确的结论是：追踪与日志导出默认关闭，用户提示词默认不记录；指标在配置层默认指向 Statsig，但最终是否外发还要过两道关。**
>
> 此前把这个问题笼统表述为"release 构建是否默认开启遥测"是不够精确的——**三类导出器的默认值并不一致**。

> [!CAUTION]
> **`exporter` 不是"通用导出器"，它是日志（logs）导出器——而且是三类里隐私敏感度最高的一类。**（初版把它标成"通用"，读者据此无法判断"打开哪个键会导致邮箱与提示词外发"。）
>
> 证据链：
>
> 1. `codex-rs/otel/src/provider.rs:85` —— `let log_enabled = !matches!(settings.exporter, OtelExporter::None);`；`:124-126` 用它去 `build_logger(&log_resource, &settings.exporter)`。即 `exporter` 只喂 logger 一条线。
> 2. `codex-rs/core/config.schema.json` 中该键的 description 原文就是 `"Optional log exporter"`（对照 `trace_exporter` 的 `"Optional trace exporter"`、`metrics_exporter` 的 `"Optional metrics exporter"`）。`codex-rs/core/src/config/otel.rs:18-19` 的注释亦印证："enabling log export must not implicitly send spans to a /v1/logs endpoint"。
> 3. **PII 的分界线在两个宏上**：`codex-rs/otel/src/events/shared.rs:4-20` 的 `log_event!` 注入 `user.account_id = $self.metadata.account_id, user.email = $self.metadata.account_email`；而 `:24-38` 的 `trace_event!` **刻意不含**这两项。
> 4. **提示词同理**：`codex-rs/otel/src/events/session_telemetry.rs:968-972` 的
>    ```rust
>    let prompt_to_log = if self.metadata.log_user_prompts { prompt.as_str() } else { "[REDACTED]" };
>    ```
>    随后只进 `log_event!`（`:974-979`）；紧邻的 `trace_event!`（`:980-987`）根本没有 `prompt` 字段。
> 5. 邮箱的来源是 session metadata 自身的字段：`codex-rs/otel/src/events/session_telemetry.rs:93` 的 `pub(crate) account_email: Option<String>`，经 `log_event!` 以 `user.email` 上报。
>
> **另有一条容易被忽略的残留**：`log_user_prompt = false` 时被替换的只有 `prompt` 字段本身，**`prompt_length` 字段始终上报**（`log_event!` 与 `trace_event!` 都带 `prompt_length = %prompt.chars().count()`）。即在 REDACTED 模式下，**提示词的字符长度信息仍会外发**。

### 1.1 指标还要过的两道关（E3）

`codex-rs/core/src/config/otel.rs` 只决定"配置解析后的值"。真正的装配点是 **`codex-rs/core/src/otel_init.rs` 的 `build_provider`**（`:16`），指标要额外过两道关：

**第一道：analytics 开关（`codex-rs/core/src/otel_init.rs:70-77`）**

```rust
let metrics_exporter = if config
    .analytics_enabled
    .unwrap_or(default_analytics_enabled)
{
    to_otel_exporter(&config.otel.metrics_exporter)
} else {
    OtelExporter::None
};
```

**第二道：`resolve_exporter` 的 debug 降级**，见 §2。

### 1.2 `default_analytics_enabled` 是**每个二进制自己传的**（E3）

`build_provider` 的第四个参数由调用方给定，各二进制并不一致：

| 调用方 | 传入值 | 位置 |
| ---- | ---- | ---- |
| TUI | **`true`** | `codex-rs/tui/src/lib.rs:1157` |
| `codex exec` | **`true`** | `codex-rs/exec/src/lib.rs:163`（`DEFAULT_ANALYTICS_ENABLED`）→ `:501` |
| `codex mcp-server` | **`true`** | `codex-rs/mcp-server/src/lib.rs:57` → `:88` |
| **app-server** | **`false`** | `codex-rs/app-server/src/main.rs:108`（注释：*"Analytics are disabled by default for app-server. Users have to explicitly opt in"*，见 `codex-rs/cli/src/main.rs:544` 附近的同名参数说明） |
| **remote-control** | **`false`** | `codex-rs/cli/src/remote_control_cmd.rs:137` |
| **exec-server 遥测** | **`false`** | `codex-rs/cli/src/exec_server_telemetry.rs:6` → `:31` |

> [!NOTE]
> **表的边界**：上表只收**随正式发布交付的二进制**。另有 `codex-rs/app-server-test-client/src/lib.rs:2364` 传 `true`（`DEFAULT_ANALYTICS_ENABLED`），但它属测试客户端 bin，不随发布交付，故不入表。
>
> 另注意 **TUI 是经转发而非直接调用**：`codex-rs/tui/src/lib.rs:1153` 调的是 `codex_app_server_client::build_otel_provider`，而后者是 `codex-rs/app-server-client/src/lib.rs:53` 的再导出（`pub use codex_core::otel_init::build_provider as build_otel_provider;`）。搜索 `build_provider` 时若只搜 `otel_init::build_provider` 会漏掉 TUI 这一条。

> [!IMPORTANT]
> **修订说明（原文错误）**：初版把"指标默认外发"写成了全局结论。实际上这是 **TUI / exec / mcp-server 的行为**；在 **app-server 与 remote-control 路径下，用户不显式写 `[analytics] enabled = true` 就不会有 OTEL 指标外发**（metrics exporter 被置为 `None`）。

> [!CAUTION]
> **`[analytics] enabled` 一个键喂两条通路，但两侧的缺省语义完全相反——这是全文最容易被误判的隐私事实。**
>
> | 消费方 | 判定表达式 | 位置 | `enabled` 未配置（`None`）时 |
> | ---- | ---- | ---- | ---- |
> | **OTEL metrics** | `config.analytics_enabled.unwrap_or(default_analytics_enabled)` | `codex-rs/core/src/otel_init.rs:70-77` | 回落到该二进制传入的默认值；app-server 传 `false` ⇒ metrics exporter = `None` |
> | **analytics 埋点** | `(analytics_enabled != Some(false))` | `codex-rs/analytics/src/client.rs:221-222` | **队列照建、事件照发** |
>
> 关键在于 **`default_analytics_enabled` 只被 OTEL 那一侧消费**。在 app-server 内它唯一的去处是 `build_provider`（`codex-rs/app-server/src/lib.rs:581`）；analytics 客户端**完全不读它**——`codex-rs/app-server/src/analytics_utils.rs:11-15` 直传 `config.analytics_enabled`（即那个 `Option<bool>` 原值），且 `codex-rs/app-server/src/lib.rs:877` 对 `analytics_events_client_from_config` 是**无条件调用**。
>
> **净效果：在 `codex-app-server`（以及 VSCode 扩展所走的 remote-control）上不写任何配置时，Statsig 指标不发，但 analytics 埋点事件仍在外发。** "app-server 默认关遥测"这句话只对了一半。要让埋点也停下，必须**显式**写 `[analytics] enabled = false`（`None` 不等于 `false`）。

---

## 2. Statsig 默认导出器的 debug 降级（E3）

`codex-rs/otel/src/config.rs:13-35` 的 `resolve_exporter`：

```rust
OtelExporter::Statsig => {
    // Keep the built-in Statsig default off in debug builds so
    // incremental local development and test runs do not emit
    // best-effort OTEL traffic unless a test or binary opts into an
    // explicit exporter configuration.
    if cfg!(debug_assertions) {
        return OtelExporter::None;
    }
    OtelExporter::OtlpHttp { endpoint: <指标端点常量>, headers: <鉴权头常量>, protocol: Json, tls: None }
}
```

| 构建类型 | `metrics_exporter = Statsig` 的实际行为 |
| ---- | ---- |
| **debug**（`debug_assertions` 开） | **降级为 `None`，不发任何数据** |
| **release** | 解析为 OTLP/HTTP，向 Statsig 端点发送指标 |

配套测试 `statsig_default_metrics_exporter_is_disabled_in_debug_builds`（`codex-rs/otel/src/config.rs:112-118`）锁定了这个行为。

> 注意这里是**无条件的** `if cfg!(debug_assertions) { return OtelExporter::None; }`——与 §3.2 的 analytics 分支形成对比，后者是**有条件的**。

### 端点与凭据

| 项 | 位置 | 说明 |
| ---- | ---- | ---- |
| 指标端点常量 | `codex-rs/otel/src/config.rs:9` | 指向 `https://ab.chatgpt.com/otlp/v1/metrics` |
| 鉴权请求头名常量 | `codex-rs/otel/src/config.rs:10` | 一个 Statsig 专用的自定义头 |
| 客户端凭据常量 | `codex-rs/otel/src/config.rs:11` | **值不在本文复述** |

> [!NOTE]
> 第三项是**编译进二进制的客户端可分发凭据**，不是服务端密钥。**本文档按脱敏规范只记录位置与用途，不复制常量名、请求头名与值。** 需要时直接看源码对应行。

### 四种导出器类型（`codex-rs/otel/src/config.rs:88`）

```rust
pub enum OtelExporter {
    None,
    Statsig,                                    // 仅用于 metrics
    OtlpGrpc { endpoint, headers, tls },
    OtlpHttp { endpoint, headers, protocol, tls },
}
```

`Statsig` 变体的文档注释写明 "This is intended for **metrics only**"。

---

## 3. analytics：opt-out 语义；debug 构建**默认仍走网络**（E3）

`codex-rs/analytics/src/client.rs`：

### 3.1 启用条件（`:213-224`）

```rust
queue: (analytics_enabled != Some(false))
    .then(|| AnalyticsEventsQueue::new(...))
```

**这是 opt-out 语义**：只有显式配置为 `false` 才关闭；`None`（未配置）与 `Some(true)` 都会创建队列。

另有 `pub fn disabled()`（`:226`）提供显式关闭的构造方式。

### 3.2 捕获文件分支是**有条件的**，不是 debug 构建的常态（`:97-133`）

> [!CAUTION]
> **修订说明（原文错误，本节是初版最严重的一处错误）**
>
> 初版写「debug 构建下网络投递关闭 / debug 构建走 `CaptureFile` 分支」。**这是错的。** 该分支只有在**捕获文件环境变量被设置且非空**时才走到；**未设置时 debug 构建会一路落到 `Self::Http { .. }`，照常走网络**。

关键在于两段代码的组合：

```rust
// client.rs:98-99 —— cfg 之外还有一层 if let
#[cfg(debug_assertions)]
if let Some(path) = capture_file {
    // ... tracing::warn!("analytics event capture enabled; network delivery is disabled")
    return Self::CaptureFile { path };
}

#[cfg(not(debug_assertions))]
let _ = capture_file;

// 未提前 return 时的兜底（含未设置捕获文件的 debug 构建）
Self::Http { url: format!("{base_url}/codex/analytics-events/events") }
```

而 `capture_file` 的来源（`codex-rs/analytics/src/client.rs:123-133`）：

```rust
fn analytics_capture_file_from_env() -> Option<PathBuf> {
    #[cfg(debug_assertions)]
    { std::env::var_os(/* 捕获文件环境变量 */)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from) }

    #[cfg(not(debug_assertions))]
    None
}
```

修正后的真值表：

| 构建类型 | 捕获文件环境变量 | analytics 目的地 |
| ---- | ---- | ---- |
| **debug** | **未设置 / 为空**（默认） | **`Http`——照常投递到 `base_url` 派生的 URL** |
| **debug** | 已设置为非空路径 | `CaptureFile`——写本地文件，日志打印 `network delivery is disabled` |
| **release** | 恒为 `None` | `Http` |

> [!IMPORTANT]
> 两条日志文案（`analytics event capture enabled; network delivery is disabled` 与 `failed to initialize analytics event capture; network delivery remains disabled`）**只在捕获文件被显式启用时才打印**。它们描述的是"捕获模式"而不是"debug 构建"。
>
> 也就是说，第 1 轮把这句日志当作"网络投递当前关闭"的证据是**读窄了**；初版把它修正成"debug 专属"，则是**修偏了**——正确的限定条件是**捕获文件模式专属**。

> [!TIP]
> **本地开发时如果不希望 analytics 出网**，靠"跑 debug 构建"是不够的。要么显式设置捕获文件环境变量（见 `codex-rs/analytics/src/analytics_capture.rs` 中的环境变量常量），要么在 config.toml 里写 `[analytics] enabled = false`（见 §5）。

---

## 4. OTEL 与 analytics 两条通路对照

| | **OTEL / Statsig** | **analytics** |
| ---- | ---- | ---- |
| crate | `codex-otel`（6,979 行） | `codex-analytics`（12,116 行） |
| 内容 | 指标、追踪、span | 产品埋点事件 |
| 默认（release） | 指标**视二进制而定**（TUI/exec/mcp-server 开，app-server/remote-control 关）、追踪关 | **开**（opt-out） |
| 默认（debug） | **全关**（`resolve_exporter` 无条件把 Statsig→None） | **照常发网络**；只有显式设置捕获文件环境变量才写本地文件 |
| 未配置（`enabled` 为 `None`）时 | metrics 回落到二进制传入的 `default_analytics_enabled`（app-server ⇒ **关**） | **开**（`!= Some(false)`，见 §1.2 CAUTION） |
| 关闭方式 | `[otel] metrics_exporter = "none"` | `[analytics] enabled = false` |
| **PII 处理** | **分通道**：logs 通道（`[otel] exporter`）经 `log_event!` 携带 `user.email`、`user.account_id`、提示词原文（受 `log_user_prompt` 门控）；traces 通道（`trace_exporter`）经 `trace_event!` **刻意剔除**这三项；metrics 通道不带这些字段 | 事件字段结构本文**未覆盖**（E1，见 §9），因此**不能断言其不含 PII** |
| 端点 | `ab.chatgpt.com/otlp/v1/metrics` | 由 `base_url` 派生 |

> [!CAUTION]
> **修订说明（原文错误）**：初版在此处写「两者都遵循同一个设计原则：本地开发（debug）不产生外发流量，正式构建才启用」。**这句话不成立。**
>
> 两条通路对 debug 构建的处理**并不一致**：
>
> - **OTEL/Statsig 是无条件降级**——`cfg!(debug_assertions)` 直接 `return OtelExporter::None`（`codex-rs/otel/src/config.rs:19-21`）。
> - **analytics 是有条件降级**——只有设置了捕获文件环境变量才转本地；**默认情况下 debug 构建照样发网络**（`codex-rs/analytics/src/client.rs:98-99` + `:123-133`）。
>
> 所以「debug 不产生外发流量」只对 OTEL 成立，对 analytics **不成立**。

---

## 5. 相关配置键（E2：读 `codex-rs/config/src/types.rs` 与生成的 `codex-rs/core/config.schema.json`）

> [!CAUTION]
> **修订说明（原文错误）**：初版多处把 **`analytics_enabled` 当成配置键**。**它不是配置键**，只是 `Config` 结构体的内部字段名（`codex-rs/core/src/config/mod.rs:1082`）。
>
> 真实的 config.toml 键是 **`[analytics]` 配置块下的 `enabled`**：
>
> ```rust
> // codex-rs/config/src/types.rs:218-222
> #[schemars(deny_unknown_fields)]
> pub struct AnalyticsConfigToml {
>     pub enabled: Option<bool>,
> }
> ```
>
> 生成的 `codex-rs/core/config.schema.json` 顶层只有 `analytics`（93 个顶层键中**没有** `analytics_enabled`），且顶层 `additionalProperties: false`。
>
> `[feedback] enabled` 同理（`codex-rs/config/src/types.rs:226-229`）。

> [!CAUTION]
> **结论不变，但机制说错了，这里更正。**
>
> 上一稿写「在 config.toml 里写 `analytics_enabled = false` 会被当作未知键**拒绝**」。**"不生效"是对的，"被拒绝"是错的**——默认情况下它是被**静默忽略**的。
>
> 关键在于属性的**命名空间**（`codex-rs/config/src/config_toml.rs:148-150`、`codex-rs/config/src/types.rs:217-218`）：
>
> ```rust
> #[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, JsonSchema)]
> #[schemars(deny_unknown_fields)]     // ← schemars，不是 serde
> pub struct ConfigToml { ... }
> ```
>
> `#[schemars(...)]` **只影响生成的 JSON Schema**（让 `codex-rs/core/config.schema.json` 带上 `additionalProperties: false`），**对 serde 的反序列化没有任何约束**。这里**没有** `#[serde(deny_unknown_fields)]`，所以 `toml::from_str` 遇到不认识的键会照常成功，把它丢掉。
>
> 真正会报错的是**另一条可选路径**：`codex-rs/config/src/strict_config.rs` 基于 `serde_ignored` 收集被忽略的字段并转成 `ConfigError`，而它只在 `strict_config == true` 时启用。该开关来自 CLI 的 `--strict-config`，**声明处即写明默认关闭**（如 `codex-rs/cli/src/main.rs:286-287` 的 `#[arg(long = "strict-config", default_value_t = false)]`，各子命令同款）；`codex-rs/config/src/state.rs:35` 的默认值也是 `false`。
>
> **所以对绝大多数用户而言：写错配置键既不会生效、也不会有任何提示。** 想要拼写错误变成硬错误，得自己带上 `--strict-config`。
>
> 这个区别很实用——它解释了为什么"我明明写了配置却没生效，也没报错"是常见现象。**读 `deny_unknown_fields` 时务必看清前缀是 `serde` 还是 `schemars`。**

### 5.1 顶层键

`codex-rs/core/config.schema.json` 顶层键中与本文相关的：

| 键 | 说明 |
| ---- | ---- |
| `analytics` | analytics 配置块；唯一字段是 `enabled: Option<bool>` |
| `feedback` | 用户反馈配置块；唯一字段是 `enabled: Option<bool>` |
| `otel` | OTEL 配置块 |
| `hooks` | 钩子 |
| `debug` | 调试 |

正确写法：

```toml
[analytics]
enabled = false

[feedback]
enabled = false

[otel]
metrics_exporter = "none"
```

OTEL 配置块内的字段（由 `codex-rs/core/src/config/otel.rs` 消费）：`log_user_prompt`、`environment`、`exporter`、`trace_exporter`、`metrics_exporter`、`span_attributes`、`tracestate`。

配置层级与优先级见 [`config_system.md`](./config_system.md) §1。

### 5.2 两条通路是**耦合**的，不是独立的

> [!CAUTION]
> **修订说明（原文方向反了）**：初版的 TIP 写「仅设其一不够——两条通路是独立的」。**实际方向相反**：`codex-rs/core/src/otel_init.rs:70-77` 显示 **analytics 开关是 OTEL metrics 的上游门禁**——`[analytics] enabled = false` 会**连带**把 `metrics_exporter` 强制为 `OtelExporter::None`，无论 `[otel] metrics_exporter` 配成什么。

耦合关系表：

| 配置 | analytics 埋点 | OTEL metrics | OTEL traces |
| ---- | ---- | ---- | ---- |
| `[analytics] enabled = false` | 关 | **也被强制关** | 不受影响（本来默认就关） |
| `[otel] metrics_exporter = "none"` | **不受影响，照常上报** | 关 | 不受影响 |
| 两者都设 | 关 | 关 | 关 |

> [!TIP]
> **想彻底关闭外发遥测**：**`[analytics] enabled = false` 单独一项就能同时关掉 analytics 埋点与 OTEL 指标**。稳妥起见仍建议同时写上 `[otel] metrics_exporter = "none"`（防止上游改动这条耦合），但要清楚：**只设 `metrics_exporter = "none"` 是不够的，analytics 埋点仍会照常上报。**
>
> **反之亦然，且更容易踩**：`default_analytics_enabled = false`（app-server / remote-control / exec-server 的出厂行为）**只关掉 OTEL 指标那一半**——analytics 埋点走的是 `!= Some(false)`，`None` 不满足，埋点照发（见 §1.2 CAUTION）。**"默认关"与"显式关"在这里不等价。**

---

## 6. 其他可观测性组件

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-otel` | 6,979 | OTEL：`codex-rs/otel/src/provider.rs`、`codex-rs/otel/src/otlp.rs`、`codex-rs/otel/src/targets.rs`、`codex-rs/otel/src/trace_context.rs`、`events/`、`metrics/` |
| `codex-analytics` | 12,116 | 埋点采集与投递 |
| `codex-hooks` | 11,795 | 钩子机制（`just write-hooks-schema` 生成 schema） |
| `codex-feedback` | 1,147 | 用户反馈（`feedback/upload` 协议方法）；**上传目的地是第三方 Sentry**，见 §6.6 |
| `codex-response-debug-context` | 166 | 响应调试上下文 |
| `codex-state` | 19,744 | 含 `codex-rs/state/src/telemetry.rs`、`codex-rs/state/src/audit.rs`、`codex-rs/state/src/log_db.rs` |
| `codex-rollout-trace` | 13,257 | **会话追踪落盘**，见 §6.3 |

### 6.1 遥测的装配点：`codex-rs/core/src/otel_init.rs`（E3）

这个文件是**主线**上把配置变成实际导出器的入口，初版完全没有提及（§1.1 与 §5.2 两处错误都源于它）。它导出三个函数：

> [!NOTE]
> **勘误：不要写成"唯一入口"。** `OtelProvider::from(&OtelSettings { .. })` 在生产代码里有**两个**调用点：`codex-rs/core/src/otel_init.rs:83`（本节讲的这个）和 **`codex-rs/windows-sandbox-rs/src/wfp_setup.rs:49`**（其余命中都在 `otel/tests/` 下）。后者的代码注释解释了为什么必须绕开 core 的构造器：
>
> > *"The setup helper cannot call codex-core's OTEL builder because core depends on this crate, so the parent process passes only the resolved Statsig environment in the elevation payload. Other exporters are intentionally omitted from this helper path."*
>
> 即**依赖方向反了**（core 依赖 windows-sandbox，不能反向调用），所以该 helper 只接收父进程传下来的已解析 Statsig 环境，并**刻意只保留这一种导出器**。复核：`grep -rn "OtelProvider::from" codex-rs/ --include=*.rs`。

| 函数 | 作用 |
| ---- | ---- |
| `build_provider(config, service_version, service_name_override, default_analytics_enabled)`（`:16`） | 把 `Config` 翻译成 `OtelSettings` 并构造 `OtelProvider`；analytics 与 metrics 的耦合就在这里（`:70-77`） |
| `record_process_start(otel, originator)`（**`:97`**） | 进程启动打点，转调 `codex_otel::record_process_start_once`（`:101`） |
| `install_sqlite_telemetry(otel, originator)`（**`:104`**） | 安装 SQLite→OTEL 指标通道，见 §6.2 |

> [!NOTE]
> **勘误：上面两个行号原写作 `:112` / `:119`，都超出了文件范围。** `codex-rs/core/src/otel_init.rs` 全文只有 **110 行**（`wc -l`），根本不存在第 112、119 行。已按 `grep -n` 结果改为 `:97` 与 `:104`。**引用行号前先看一眼文件总行数，是最省事的一道自检。**

`build_provider` 还读一个 feature 开关：

```rust
let runtime_metrics = config.features.enabled(Feature::RuntimeMetrics);
```

**`Feature::RuntimeMetrics`（`codex-rs/features/src/lib.rs:140`）是第三个影响"发什么"的开关**，与 `[analytics] enabled`、`[otel] metrics_exporter` 并列。它打开后，`codex-rs/otel/src/provider.rs:116-118` 会给 `MetricsConfig` 追加 `with_runtime_reader()`（进程运行时指标）。

规格（`codex-rs/features/src/lib.rs:966-971`）：

```rust
FeatureSpec {
    id: Feature::RuntimeMetrics,
    key: "runtime_metrics",
    stage: Stage::UnderDevelopment,
    default_enabled: false,
},
```

> [!NOTE]
> **勘误：上一稿写「它走 feature flag 体系而不是普通配置键，因此不在 `codex-rs/core/config.schema.json` 顶层键里」——错。**
>
> `features` **本身就是那 93 个顶层键之一**（schema 中的 description 是 `"Centralized feature flags (new). Prefer this over individual toggles."`），其 `properties` 里确有 `"runtime_metrics": {"type": "boolean"}`，且该块同样是 `additionalProperties: false`。**用户完全可以在 config.toml 里写：**
>
> ```toml
> [features]
> runtime_metrics = true
> ```
>
> 原措辞会让读者误以为无法通过 config.toml 设置。正确说法是：**它不是一个独立的顶层键，而是 `features` 这个顶层键下的子键**——默认 `false`，阶段为 `Stage::UnderDevelopment`。

### 6.2 SQLite → OTEL 指标通道（E3）

一条初版零覆盖的遥测路径：

```
otel_init::install_sqlite_telemetry
  → codex_rollout::sqlite_telemetry_recorder(metrics, originator)   // codex-rs/rollout/src/state_db.rs:238
  → codex_state::install_process_db_telemetry(telemetry)            // state/src/telemetry.rs:29
```

接口定义在 `codex-rs/state/src/telemetry.rs:15-20`：

```rust
pub trait DbTelemetry: Send + Sync + 'static {
    fn counter(&self, name: &str, inc: i64, tags: &[(&str, &str)]);
    fn record_duration(&self, name: &str, duration: Duration, tags: &[(&str, &str)]);
}
pub type DbTelemetryHandle = Arc<dyn DbTelemetry>;
```

进程级单例（`OnceLock`），**首次安装生效，重复安装被忽略**。含义：**本地 SQLite 的操作计数与耗时会作为 OTEL 指标外发**，其外发与否跟随 §1.1 的 metrics 开关。

> **部分未验证**（标签维度仍为 E1）：**计数器名已可直接列出**——`codex-rs/state/src/telemetry.rs:6-8` 导入了三个常量 `DB_FALLBACK_METRIC`、`DB_INIT_DURATION_METRIC`、`DB_INIT_METRIC`（定义在 `codex-rs/state/src/lib.rs:99-103`）。仍未核实的是**每次上报附带的标签维度**。入口改指 `codex-rs/state/src/telemetry.rs:6-8` 与 `codex-rs/rollout/src/sqlite_metrics.rs`（而非原写的 `codex-rs/rollout/src/state_db.rs:238`，那只是注册点）。

### 6.3 `codex-rollout-trace`：会话追踪落盘（**E3**）

`codex-rs/rollout-trace/`（13,257 行）把会话过程还原成可回放的 trace，**落盘到本地而非外发**，初版连"未覆盖"清单里都没有它。

> [!NOTE]
> **勘误：本节上一稿标 E1（"仅按目录与模块名"）——**证据等级被低估了**，反而削弱了"不外发"这条重要判定。**"落盘本地而非外发"现已可硬证**：
>
> 1. `codex-rs/rollout-trace/Cargo.toml` 的 `[dependencies]` **不含任何 HTTP 客户端**——全部依赖只有 `anyhow`、`codex-code-mode`、`codex-protocol`、`http`（纯类型库）、`serde`、`serde_json`、`tracing`、`uuid`。**没有 `reqwest`，也没有任何传输层 crate。**
> 2. `codex-rs/rollout-trace/src/writer.rs:3-4` 只 `use std::fs::File; use std::fs::OpenOptions;`——出口就是本地文件。
>
> 即这个 crate **在编译期就不具备出网能力**。

**开关与落盘位置（E3）：**

| 项 | 结论 | 证据 |
| ---- | ---- | ---- |
| 是否受开关控制 | **是**——由环境变量 `CODEX_ROLLOUT_TRACE_ROOT` 控制 | `codex-rs/rollout-trace/src/thread.rs:44` 的 `pub const CODEX_ROLLOUT_TRACE_ROOT_ENV: &str = "CODEX_ROLLOUT_TRACE_ROOT";` |
| 未设置时 | **直接 `disabled()`，不产生任何文件** | `codex-rs/rollout-trace/src/thread.rs:106-109`：`let Some(root) = std::env::var_os(CODEX_ROLLOUT_TRACE_ROOT_ENV) else { return Self::disabled(); };` |
| 落盘位置 | `$CODEX_ROLLOUT_TRACE_ROOT/trace-{uuid}-{thread_id}/` | `codex-rs/rollout-trace/src/thread.rs:426`：`root.join(format!("trace-{trace_id}-{thread_id}"))` |
| 是否含用户提示词 | **是——承载完整提示词与模型响应原文** | `codex-rs/rollout-trace/src/payload.rs:30-49` 的 `RawPayloadKind` 含 `InferenceRequest`、`InferenceResponse`、`SessionMetadata`、`ToolInvocation`、`ToolResult` 等 |

> [!CAUTION]
> **这是全仓库最完整地承载会话原文的一条本地路径。** 它默认不启用（未设环境变量即 `disabled()`），但**一旦启用，`$CODEX_ROLLOUT_TRACE_ROOT` 下的 bundle 目录会包含推理请求与响应的原文**。分享调试 bundle 前必须自行脱敏——**crate 本身不做任何 PII 过滤**。

顶层模块：

| 模块 | 名字暗示的职责 |
| ---- | ---- |
| `codex-rs/rollout-trace/src/payload.rs` / `codex-rs/rollout-trace/src/raw_event.rs` / `codex-rs/rollout-trace/src/protocol_event.rs` | 事件载荷与原始事件 |
| `codex-rs/rollout-trace/src/writer.rs` | 写出 |
| `codex-rs/rollout-trace/src/bundle.rs` | trace bundle（与 `codex debug trace-reduce` 子命令对应，见 [`experimental_surfaces.md`](./experimental_surfaces.md)） |
| `codex-rs/rollout-trace/src/inference.rs` / `codex-rs/rollout-trace/src/mcp.rs` / `codex-rs/rollout-trace/src/tool_dispatch.rs` / `codex-rs/rollout-trace/src/code_cell.rs` / `codex-rs/rollout-trace/src/compaction.rs` / `codex-rs/rollout-trace/src/thread.rs` | 各类事件的记录 |
| `model/`（4 个文件） | `codex-rs/rollout-trace/src/model/conversation.rs`、`codex-rs/rollout-trace/src/model/runtime.rs`、`codex-rs/rollout-trace/src/model/session.rs` |
| `reducer/` | 把事件流归约成状态 |

> [!WARNING]
> **引用这些模块时务必写全路径。** 上表中的 `codex-rs/rollout-trace/src/inference.rs`、`codex-rs/rollout-trace/src/code_cell.rs`、`codex-rs/rollout-trace/src/compaction.rs`、`codex-rs/rollout-trace/src/thread.rs` 以及 `codex-rs/rollout-trace/src/model/conversation.rs`，在 **`codex-rs/rollout-trace/src/reducer/` 下各有一个同名文件**（记录端 vs 归约端），只写裸文件名会真歧义。

> **仍未验证**（E1）：bundle 内各文件的**具体序列化格式**（`codex-rs/rollout-trace/src/writer.rs` 与 `codex-rs/rollout-trace/src/bundle.rs`）。开关、落盘位置与内容边界已在上表核实为 E3。**改动遥测边界时务必核查此处**——它确实是承载会话原文最完整的一条路径。

### 6.4 追踪的编写规范

> `AGENTS.md`「顶部规则列表」（关键词 `tracing::instrument`）：为异步任务加追踪时，**在函数或方法定义处标注 `#[tracing::instrument(...)]`**，不要在调用点用 `.instrument(...)` 附加 span。加之前先检查被调用方——或它立即委托到的实现方法——是否已被标注。

### 6.5 日志查看

```bash
just log        # 实时查看 state SQLite 中的日志
```

### 6.6 `codex-feedback`：上传目的地是**第三方 Sentry**（E3）

> [!CAUTION]
> **这是与 Statsig、ChatGPT 后端并列的第三条外发通路，而且是唯一一条走 Anthropic/OpenAI 之外第三方服务的通路。** 本文前几稿全文零次出现 "Sentry"，§8 的「用户反馈」行只写了"用户填写内容"而不写去向——对一篇隐私边界文档，这是最该补的一格。

`codex-rs/feedback/src/lib.rs:417` 的 `pub fn upload_feedback(&self, options: FeedbackUploadOptions<'_>)`，其文档注释原文就是 *"Upload feedback to **Sentry** with optional attachments."*。实现（`:421-435`）在函数内部临时构造一个 Sentry 客户端：

```rust
use sentry::Client;
use sentry::ClientOptions;
use sentry::protocol::Envelope;   // 以及 EnvelopeItem / Event / Level
use sentry::transports::DefaultTransportFactory;
use sentry::types::Dsn;

let client = Client::from_config(ClientOptions {
    dsn: Some(Dsn::from_str(SENTRY_DSN).map_err(|e| anyhow!("invalid DSN: {e}"))?),
    transport: Some(Arc::new(DefaultTransportFactory {})),
    ..Default::default()
});
```

> [!NOTE]
> DSN 来自同文件内的常量 `SENTRY_DSN`。**本文按脱敏规范只记录常量名与所在文件（`codex-rs/feedback/src/lib.rs`），不复述其字面量**——本 fork 是公开仓库。需要时直接看源码。

**同样重要的是反面结论——崩溃不会自动上报：**

| 事实 | 证据 |
| ---- | ---- |
| 全工作区 **`sentry::init` 零命中** | `grep -rn "sentry::init" codex-rs/` 无结果 |
| `sentry` 依赖只出现在 **一个 crate** | `codex-rs/feedback/Cargo.toml:15` 的 `sentry = { version = "0.46" }`；workspace 根 `codex-rs/Cargo.toml:399` 只是版本声明，不构成实际链接 |
| TUI 的两个 panic hook **不接 Sentry** | `codex-rs/tui/src/tui.rs:542`（只 `restore_after_exit()` 后转调前一个 hook）、`codex-rs/tui/src/lib.rs:1347`（只 `tracing::error!("panic: {info}")` 后转调前一个 hook） |

即 Sentry **只在用户主动触发 `feedback/upload` 时**才建立连接并发送一次 envelope；**没有全局 hub、没有自动 panic/错误捕获、进程崩溃不会产生任何 Sentry 流量**。

### 6.7 windows-sandbox 的 WFP setup 也走 Statsig（E3）

`codex-rs/windows-sandbox-rs/src/wfp_setup.rs:38-62` 的 `build_wfp_metrics_provider` 是 §6.1 勘误里提到的**第二个** `OtelProvider::from` 调用点。它的导出器组合是**硬编码**的：

```rust
exporter:         OtelExporter::None,     // logs 关
trace_exporter:   OtelExporter::None,     // traces 关
metrics_exporter: OtelExporter::Statsig,  // 仅指标
runtime_metrics:  false,
```

因此它同样要过 §2 的 `resolve_exporter` debug 降级（debug 构建下 Statsig→`None`）。是否启用由**父进程在提权 payload 里传下来的 `Option<&StatsigMetricsSettings>`** 决定——`:42-44` 的 `let Some(otel) = otel else { return Ok(None); };` 意味着父进程不传就完全不构造 provider。

> [!NOTE]
> 这条通路**不读 config.toml，也不看 `[analytics] enabled`**——它拿到的已经是父进程解析好的 Statsig 环境。换言之，**关闭它的正确做法是在父进程侧关闭指标**（§5.2），而不是指望 helper 自己判断。

### 6.8 反面事实：**没有任何遥测 opt-out 环境变量**（E3）

实测 `codex-rs/` 全树：

| 查找项 | 结果 |
| ---- | ---- |
| `DO_NOT_TRACK` | **零命中** |
| `*_DISABLE_TELEMETRY` | **零命中** |
| 遥测相关的 `*_OPT_OUT` | **零命中**（仅有的 `opt_out` 命中是 `notices.fast_default_opt_out` 与 TUI 的 `model_migration.can_opt_out`，与遥测无关） |
| 门控遥测的 cargo feature | **不存在**——`codex-otel` / `codex-analytics` 都不是可选依赖，也没有 `telemetry` 之类的 feature gate |

**结论：关闭遥测只能改 config.toml**（`[analytics] enabled = false` + `[otel] metrics_exporter = "none"`）。设置任何业界通行的环境变量（含 `DO_NOT_TRACK=1`）**不会产生任何效果**。唯一与遥测相关的环境变量是 §3.2 的 analytics 捕获文件变量（仅 debug 构建生效，且是"改目的地"而非"关闭"）与 §6.3 的 `CODEX_ROLLOUT_TRACE_ROOT`（是"打开"而非"关闭"）。

---

## 7. 认证相关遥测

`codex-rs/login/src/auth_env_telemetry.rs` 会上报**认证环境信息**。

> **未验证**（E1）：具体上报哪些字段。改动认证链路时请一并检查此文件。

---

## 8. 数据边界小结

下表 10 行穷举本文核实过的全部数据出口。

| 通路 | 目的地 | 默认（release） | 内容 | 用户可关闭 |
| ---- | ---- | ---- | ---- | ---- |
| 模型请求 | 模型 provider | 开（这是产品本身） | 会话内容 | 换本地 provider |
| OTEL 指标 | Statsig（`ab.chatgpt.com`） | **视二进制而定**：TUI / `codex exec` / `codex mcp-server` **开**；app-server / remote-control / exec-server **关** | 指标；**不含邮箱、账号 ID、提示词** | `[analytics] enabled = false`（连带关闭）或 `[otel] metrics_exporter = "none"` |
| OTEL 追踪（`trace_exporter`） | 用户自配 OTLP | **关** | span；`trace_event!` **刻意剔除** `user.email` / `user.account_id` / 提示词 | 保持默认即可 |
| **OTEL 日志（`exporter`）** | 用户自配 OTLP | **关** | **唯一携带 `user.email`、`user.account_id` 的通道**；`log_user_prompt = true` 时还携带**提示词原文**（§1） | 保持默认即可 |
| 用户提示词记录 | 随 OTEL 日志通道 | **关**（`[otel] log_user_prompt = false`） | 关闭时字段为 `"[REDACTED]"`，但 **`prompt_length` 始终上报** | 保持默认；且 `exporter = none` 时该开关无出口 |
| analytics 埋点 | ChatGPT 后端（`base_url` 派生） | **开**（opt-out）；**debug 构建同样默认外发**；**app-server 不写配置时也照发**（§1.2） | 产品事件（字段结构未覆盖，E1） | **只能显式** `[analytics] enabled = false` |
| SQLite 指标（§6.2） | 随 OTEL 指标 | 跟随 OTEL 指标 | DB 计数与耗时（`codex.sqlite.*`） | 同 OTEL 指标 |
| windows-sandbox WFP setup（§6.7） | Statsig | 由父进程传入的 `StatsigMetricsSettings` 决定；debug 构建降级为 `None` | 仅指标 | 在父进程侧关闭指标 |
| 用户反馈（§6.6） | **第三方 Sentry** | 关（用户主动触发） | 用户填写内容 + 附件 | 不用即可；或 `[feedback] enabled = false` |
| rollout-trace（§6.3） | **本地磁盘，不出网** | **关**（未设 `CODEX_ROLLOUT_TRACE_ROOT` 即 `disabled()`） | **完整提示词与模型响应原文**（`InferenceRequest` / `InferenceResponse` / `SessionMetadata`） | 不设该环境变量即可 |

> [!IMPORTANT]
> 本表相对初版的关键修正：
>
> 1. **OTEL 指标不是全局默认开**——默认值由各二进制调用 `build_provider` 时传入（§1.2）。
> 2. **关闭键是 `[analytics] enabled`，不是 `analytics_enabled`**（§5）。
> 3. 新增「目的地」列，并把 **Sentry**（§6.6）与 **windows-sandbox WFP**（§6.7）两条此前完全缺失的通路补入。
> 4. `exporter` 从原表缺失的"通用导出"提升为**独立一行**——它是唯一携带 PII 与提示词的通道（§1）。
> 5. rollout-trace 从「未验证（E1）」升级为已核实（§6.3）。

> [!CAUTION]
> **三条最容易被误判的事实，集中在这里：**
>
> 1. **`DO_NOT_TRACK` 等环境变量一概无效**——关闭遥测只能改 config.toml（§6.8）。
> 2. **"app-server 默认关遥测"只对了一半**——指标确实关，但 analytics 埋点仍在发（§1.2）。
> 3. **反馈上传去的是第三方 Sentry**，不是 ChatGPT 后端（§6.6）。但**崩溃不会自动上报**，全仓库无 `sentry::init`。

完整的外部服务边界见 [`architecture_overview.md`](./architecture_overview.md) §8。

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 具体上报了哪些指标名与维度 | E1 | `otel/src/metrics/`、`otel/src/events/` |
| analytics 事件的字段结构 | E1 | `codex-rs/analytics/src/events.rs`、`codex-rs/analytics/src/analytics_capture.rs` |
| OTEL provider 的初始化与关闭时序 | E1 | `codex-rs/otel/src/provider.rs`、`codex-rs/otel/src/provider_shutdown_tests.rs` |
| `codex-rs/otel/src/targets.rs` 的过滤规则 | E1 | `codex-rs/otel/src/targets.rs` |
| 认证环境遥测的字段 | E1 | `codex-rs/login/src/auth_env_telemetry.rs` |
| hooks 的事件模型 | E1 | `codex-hooks`（11,795 行） |
| audit 记录的内容与保留策略 | E1 | `codex-rs/state/src/audit.rs` |
| analytics 捕获文件的环境变量名、位置与格式 | E1 | `codex-rs/analytics/src/analytics_capture.rs` |
| SQLite 遥测的**标签维度**（计数器名已核实，见 §6.2） | E1 | `codex-rs/state/src/telemetry.rs:6-8`、`codex-rs/rollout/src/sqlite_metrics.rs` |
| rollout-trace bundle 内各文件的**序列化格式**（开关、落盘位置、内容边界已核实为 E3，见 §6.3） | E1 | `codex-rs/rollout-trace/src/writer.rs`、`codex-rs/rollout-trace/src/bundle.rs`、`codex-rs/rollout-trace/src/payload.rs` |
| `Feature::RuntimeMetrics` 打开后额外发什么 | E1 | `otel/src/metrics/`、`codex-rs/features/src/lib.rs:140` |
| `[feedback] enabled` 关闭后影响哪些表面 | E1 | `codex-feedback`、`codex-rs/config/src/types.rs:226` |
| 反馈上传时随附件一并发往 Sentry 的**诊断内容**（`feedback_diagnostics.attachment_text()`）与 tag 维度 | E1 | `codex-rs/feedback/src/lib.rs:413`、`:437` 起 |

---

## 10. 相关文档

- [配置体系](./config_system.md) — 遥测配置的加载与层级
- [架构总览](./architecture_overview.md) §8 — 外部服务边界全景
- [认证与模型接入](./auth_and_providers.md) — 认证遥测
- [会话与持久化](./session_and_persistence.md) — state 的日志与审计
