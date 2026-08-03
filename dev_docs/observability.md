---
title: Codex 可观测性与遥测边界
summary: 通过代码级核查确定 OTEL 三类导出器的默认值——trace 与通用导出器默认关闭而 metrics 默认为 Statsig、debug 构建下 Statsig 会降级为 None、analytics 为 opt-out 且 debug 下网络投递关闭，并说明用户提示词默认不记录与相关配置键。
keywords: codex | observability | otel | telemetry | statsig | analytics | opt-out | privacy
scope: codex-rs/otel、analytics、hooks、feedback 的遥测与埋点边界
related_files: codex-rs/otel/src/config.rs | codex-rs/core/src/config/otel.rs | codex-rs/analytics/src/client.rs | codex-rs/otel/src/provider.rs | codex-rs/hooks | AGENTS.md
dependencies: dev_docs/config_system.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 可观测性与遥测边界

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 默认值判定为 **E3**（读取 `unwrap_or` 与 `resolve_exporter` 实现）；投递链路细节部分为 E1

> [!IMPORTANT]
> **这篇文档解决了第二个长期挂账问题。** 前两轮的 `_analysis` 与第 1 批文档都写着「遥测的默认开关尚未完整核实（E3 部分证据），不给出 release 构建是否默认上报的结论」。本文完成了核查，结论见 §1。

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
| `log_user_prompt` | **`false`** | **用户提示词默认不记录** |
| `exporter`（通用） | **`None`** | 默认不导出 |
| `trace_exporter` | **`None`** | **追踪默认不导出** |
| `metrics_exporter` | **`Statsig`** | **指标默认导出到 Statsig** |

> [!IMPORTANT]
> **准确的结论是：默认只有「指标」会外发，追踪与通用导出默认关闭，用户提示词默认不记录。**
>
> 此前把这个问题笼统表述为"release 构建是否默认开启遥测"是不够精确的——**三类导出器的默认值并不一致**。

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

配套测试 `statsig_default_metrics_exporter_is_disabled_in_debug_builds`（`config.rs:110-117`）锁定了这个行为。

### 端点与凭据

| 项 | 位置 | 说明 |
| ---- | ---- | ---- |
| 指标端点常量 | `otel/src/config.rs:9` | 指向 `https://ab.chatgpt.com/otlp/v1/metrics` |
| 鉴权请求头名常量 | `otel/src/config.rs:10` | 一个 Statsig 专用的自定义头 |
| 客户端凭据常量 | `otel/src/config.rs:11` | **值不在本文复述** |

> [!NOTE]
> 第三项是**编译进二进制的客户端可分发凭据**（`client-` 前缀），不是服务端密钥。**本文档按脱敏规范只记录位置与用途，不复制常量名与值。** 需要时直接看源码对应行。

### 四种导出器类型（`otel/src/config.rs:88`）

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

## 3. analytics：opt-out 语义 + debug 下不投递（E3）

`codex-rs/analytics/src/client.rs`：

### 3.1 启用条件（`:215-224`）

```rust
queue: (analytics_enabled != Some(false))
    .then(|| AnalyticsEventsQueue::new(...))
```

**这是 opt-out 语义**：只有显式配置为 `false` 才关闭；`None`（未配置）与 `Some(true)` 都会创建队列。

另有 `pub fn disabled()`（`:226`）提供显式关闭的构造方式。

### 3.2 debug 构建下网络投递关闭（`:100-111`）

debug 构建走 `CaptureFile` 分支，日志文案是：

> `analytics event capture enabled; network delivery is disabled`

以及初始化失败时的：

> `failed to initialize analytics event capture; network delivery remains disabled`

| 构建类型 | analytics 行为 |
| ---- | ---- |
| **debug** | 事件**写入本地捕获文件**，`network delivery is disabled` |
| **release** | 走 `AnalyticsEventsQueue`，投递到 `base_url` 派生的目的地 |

> [!IMPORTANT]
> **"network delivery is disabled" 是 debug 构建专属的**（该分支在 `#[cfg(not(debug_assertions))] let _ = capture_file;` 之前），不是全局常态。第 1 轮把这句日志当作"网络投递当前关闭"的证据是**读窄了**——它只适用于 debug 构建。

---

## 4. 两条遥测通路对照

| | **OTEL / Statsig** | **analytics** |
| ---- | ---- | ---- |
| crate | `codex-otel`（6,979 行） | `codex-analytics`（12,116 行） |
| 内容 | 指标、追踪、span | 产品埋点事件 |
| 默认（release） | **指标开**、追踪关 | **开**（opt-out） |
| 默认（debug） | **全关**（Statsig→None） | 写本地文件，不发网络 |
| 关闭方式 | `metrics_exporter = "none"` | `analytics_enabled = false` |
| 端点 | `ab.chatgpt.com/otlp/v1/metrics` | 由 `base_url` 派生 |

> **两者都遵循同一个设计原则**：本地开发（debug）不产生外发流量，正式构建才启用。

---

## 5. 相关配置键（E4）

`config.schema.json` 顶层键中与本文相关的：

| 键 | 说明 |
| ---- | ---- |
| `analytics` | analytics 配置块（含 `analytics_enabled`） |
| `otel` | OTEL 配置块 |
| `feedback` | 用户反馈 |
| `hooks` | 钩子 |
| `debug` | 调试 |

OTEL 配置块内的字段（由 `core/src/config/otel.rs` 消费）：`log_user_prompt`、`environment`、`exporter`、`trace_exporter`、`metrics_exporter`。

配置层级与优先级见 [`config_system.md`](./config_system.md) §1。

> [!TIP]
> **想彻底关闭外发遥测**：把 `metrics_exporter` 设为 `none`，并把 analytics 显式设为 `false`。仅设其一不够——两条通路是独立的。

---

## 6. 其他可观测性组件

| crate | 行数 | 职责 |
| ---- | ---: | ---- |
| `codex-otel` | 6,979 | OTEL：`provider.rs`、`otlp.rs`、`targets.rs`、`trace_context.rs`、`events/`、`metrics/` |
| `codex-analytics` | 12,116 | 埋点采集与投递 |
| `codex-hooks` | 11,795 | 钩子机制（`just write-hooks-schema` 生成 schema） |
| `codex-feedback` | 1,147 | 用户反馈（`feedback/upload` 协议方法） |
| `codex-response-debug-context` | 166 | 响应调试上下文 |
| `codex-state` | 19,744 | 含 `telemetry.rs`、`audit.rs`、`log_db.rs` |

### 追踪的编写规范

> `AGENTS.md:45-48`：为异步任务加追踪时，**在函数或方法定义处标注 `#[tracing::instrument(...)]`**，不要在调用点用 `.instrument(...)` 附加 span。加之前先检查被调用方——或它立即委托到的实现方法——是否已被标注。

### 日志查看

```bash
just log        # 实时查看 state SQLite 中的日志
```

---

## 7. 认证相关遥测

`codex-rs/login/src/auth_env_telemetry.rs` 会上报**认证环境信息**。

> **未验证**（E1）：具体上报哪些字段。改动认证链路时请一并检查此文件。

---

## 8. 数据边界小结

| 通路 | 默认（release） | 内容 | 用户可关闭 |
| ---- | ---- | ---- | ---- |
| 模型请求 | 开（这是产品本身） | 会话内容 | 换本地 provider |
| OTEL 指标 | **开** | 指标 | `metrics_exporter = "none"` |
| OTEL 追踪 | **关** | — | — |
| 用户提示词记录 | **关**（`log_user_prompt = false`） | — | — |
| analytics 埋点 | **开**（opt-out） | 产品事件 | `analytics_enabled = false` |
| 用户反馈 | 关（用户主动触发） | 用户填写内容 | 不用即可 |

完整的外部服务边界见 [`architecture_overview.md`](./architecture_overview.md) §8。

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 具体上报了哪些指标名与维度 | E1 | `otel/src/metrics/`、`otel/src/events/` |
| analytics 事件的字段结构 | E1 | `analytics/src/events.rs`、`analytics_capture.rs` |
| OTEL provider 的初始化与关闭时序 | E1 | `otel/src/provider.rs`、`provider_shutdown_tests.rs` |
| `targets.rs` 的过滤规则 | E1 | `otel/src/targets.rs` |
| 认证环境遥测的字段 | E1 | `login/src/auth_env_telemetry.rs` |
| hooks 的事件模型 | E1 | `codex-hooks`（11,795 行） |
| audit 记录的内容与保留策略 | E1 | `state/src/audit.rs` |
| debug 捕获文件的位置与格式 | E1 | `analytics/src/analytics_capture.rs` |

---

## 10. 相关文档

- [配置体系](./config_system.md) — 遥测配置的加载与层级
- [架构总览](./architecture_overview.md) §8 — 外部服务边界全景
- [认证与模型接入](./auth_and_providers.md) — 认证遥测
- [会话与持久化](./session_and_persistence.md) — state 的日志与审计
