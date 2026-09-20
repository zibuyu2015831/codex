---
title: Codex 语音与实时会话
summary: 描述第 6 轮上游新增的语音/实时子系统：它由两条互不相同的通路构成——core 侧经 Op::RealtimeConversation* 六个协议变体走的会话通路，与 TUI 侧经 codex-realtime-webrtc 拉起独立 codex-voice-host 辅助进程走的本地音频通路；说明三个新 crate 与 third_party/voice 私有 GStreamer 运行时的分工、voice-host 作为无人以库形式依赖的纯二进制这一结构特征、平台库名差异与能力探测入口，以及本专题尚未展开的边界。
keywords: codex | voice | realtime | webrtc | gstreamer | voice-host | realtime-conversation | opus | round6
scope: codex-rs/voice-host、codex-rs/realtime-webrtc、codex-rs/utils/audio、third_party/voice 与 core 侧实时会话通路
related_files: codex-rs/voice-host/src/main.rs | codex-rs/realtime-webrtc/src/lib.rs | codex-rs/realtime-webrtc/src/client.rs | codex-rs/realtime-webrtc/src/session.rs | codex-rs/utils/audio/src/lib.rs | codex-rs/core/src/realtime_conversation.rs | codex-rs/core/src/realtime_conversation/sideband.rs | codex-rs/protocol/src/protocol.rs | third_party/voice/README.md | third_party/voice/sources.json
dependencies: dev_docs/crate_map.md | dev_docs/core_agent_loop.md | dev_docs/_analysis/upstream_sync_round6.md
verified_at: 2026-09-21
---

# 语音与实时会话

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
> **本文是第 6 轮上游同步新开的专题**：语音/实时是基线 `bb5054fe47` 之后成建制出现的子系统，此前本体系完全没有覆盖。
> **证据等级**: crate 分工与依赖关系为 E2（`cargo metadata` + 清单）；协议变体、进程模型、平台差异为 E3（源码）；`third_party/voice` 的构成为 E1/E2（目录与 `sources.json`）

> [!IMPORTANT]
> **本文只回答「它由什么构成、怎么接起来」，不回答「它怎么跑起来、用户怎么用」。** 端到端的启用路径、配置键全集与故障排查均**未展开**——见 §6。写「未覆盖」而不是硬凑，是本体系的既定纪律。

---

## 1. 最该先知道的一件事：语音有**两条**通路

这是本子系统最容易被误读的地方。「语音」在 codex 里不是一个模块，而是**两条几乎不相交的链路**，它们的传输、进程模型、所在层次全都不同。

| | 通路 A：实时会话协议 | 通路 B：本地音频辅助进程 |
| ---- | ---- | ---- |
| **入口** | `Op::RealtimeConversation*` 六个协议变体 | TUI 直接调用 `codex-realtime-webrtc` |
| **所在层** | `codex-core`（`codex-rs/core/src/realtime_conversation.rs`，2,638 行） | `codex-tui` → `codex-realtime-webrtc` → 独立进程 |
| **进程模型** | 同进程，core 内的状态机 | **另起一个 `codex-voice-host` 子进程** |
| **传输** | WebSocket（`tokio-tungstenite`）+ WebRTC sideband | WebRTC + 本地音频设备 |
| **是否经 app-server 协议** | 是 | **否**——TUI 侧直连，不走 `Op` |

**两条通路在 crate 依赖图上几乎不相交**（E2，`cargo metadata`）：

```
codex-core        ──依赖──▶ codex-utils-audio          （只有它依赖 utils/audio）
codex-tui         ──依赖──▶ codex-realtime-webrtc
codex-voice-host  ──依赖──▶ codex-realtime-webrtc
```

> [!CAUTION]
> **`codex-voice-host` 没有任何 crate 以库的形式依赖它。**
>
> 用 `cargo metadata` 遍历所有包的 path 依赖，以 `codex-voice-host` 为目标的结果是**空集**。
>
> 它是一个**纯二进制**（`codex-rs/voice-host/Cargo.toml:7-9` 的 `[[bin]] name = "codex-voice-host"`），随发布交付（见 [`architecture_overview.md`](./architecture_overview.md) §3.4），由 `codex-realtime-webrtc` 在运行期**按文件名拉起**。
>
> 这意味着：**按「谁依赖它」去找调用方会一无所获**。正确的追法是在 `codex-rs/realtime-webrtc/src/` 里 grep 二进制文件名——命中在 `codex-rs/realtime-webrtc/src/session.rs:177-181` 与 `codex-rs/realtime-webrtc/src/client.rs:158`。这是本体系反复强调的「依赖图不等于调用图」的又一个实例。

---

## 2. 通路 A：`Op::RealtimeConversation*`（core 侧）

### 2.1 六个协议变体

`Op` 枚举中 `RealtimeConversation` 前缀的变体共 **6 个**（`codex-rs/protocol/src/protocol.rs:611-626`）：

| 变体 | 行 |
| ---- | ---: |
| `RealtimeConversationStart` | `:611` |
| `RealtimeConversationAudio` | `:614` |
| `RealtimeConversationText` | `:617` |
| `RealtimeConversationSpeech` | `:620` |
| `RealtimeConversationClose` | `:623` |
| `RealtimeConversationListVoices` | `:626` |

> [!WARNING]
> **计数时必须限定在 `Op` 枚举体内。** 同一个 `codex-rs/protocol/src/protocol.rs` 的 `EventMsg` 枚举里**另有 5 个** `RealtimeConversation` 前缀变体（`Started` / `Realtime` / `Closed` / `Sdp` / `ListVoicesResponse`，`:1376-1385` 与 `:1524`）。裸正则匹配会把两者混计成 **11**。
>
> 本体系的断言账本为此专门登记了一条 `realtime_op_variants`，其 verify 命令限定在 `Op` 枚举体内计数——首版就是用不限定枚举体的匹配写的，数出来是 11。

### 2.2 分派与实现

六个变体中**五个**转发给 `codex-rs/core/src/realtime_conversation.rs` 的 `handle_*`（`codex-rs/core/src/session/handlers.rs:437` / `:452` / `:456` / `:460` / `:464`）；第六个 `ListVoices` **不进该模块**，由 `codex-rs/core/src/session/handlers.rs:64` 的 `realtime_conversation_list_voices` 就地应答。

模块本体 `codex-rs/core/src/realtime_conversation.rs`（2,638 行）非 `pub`，纯 core 内部。子目录 `codex-rs/core/src/realtime_conversation/` 现有 5 个文件，合计 490 行：bem(71) + bem_tests(103) + existing_call(90) + sideband(190) + sideband_tests(36)。

### 2.3 两条并行输入路径

- `spawn_realtime_input_task()`（`codex-rs/core/src/realtime_conversation.rs:1873`）
- `spawn_webrtc_sideband_input_task()`（**第 6 轮迁出主文件**，现在 `codex-rs/core/src/realtime_conversation/sideband.rs:27`）

后者由 `codex-rs/core/src/realtime_conversation.rs:674` 调起，sideband 基址来自配置键 `experimental_realtime_webrtc_call_base_url`（`:1261`）。

> **`bem` 子模块**：`message_phase()`（`codex-rs/core/src/realtime_conversation/bem.rs:5`）把流式消息按 `analysis` / `commentary` / `final` 三个通道头分相；`ChannelParser`（`:35`）缓冲直到通道头完整，**原样释放信封**以便前端区分 BEM 的 `analysis` 与 `commentary`。

---

## 3. 通路 B：`codex-voice-host` 辅助进程

### 3.1 进程所有权语义

`codex-rs/realtime-webrtc/src/client.rs:55-62` 的文档注释把语义写得很清楚：

> *"Owns one helper. Dropping it terminates the process and leaves its waiter to reap it. A successful handshake establishes compatibility only, not an active audio session."*

两条都反直觉，值得单独记：

1. **`VoiceHost` 句柄一旦 drop，辅助进程就被终止**——它不是「连接」，是「所有权」。
2. **握手成功只证明兼容，不代表音频会话已建立**。把握手成功当作「语音已就绪」会误判。

`codex-rs/voice-host/src/main.rs:1-2` 的模块注释补了第三条：

> *"Same-build helper lifecycle with privately owned runtime, transport and opt-in local devices."*
> *"Queued privacy controls take priority over starting another capture batch."*

即**排队中的隐私控制优先于启动下一批采集**——这是隐私语义，不是性能优化。

### 3.2 平台差异

辅助进程的可执行文件名与配套的 GStreamer 库名逐平台不同（`codex-rs/realtime-webrtc/src/session.rs:177-181`）：

| 平台 | 可执行文件 | 配套库 |
| ---- | ---- | ---- |
| macOS | `bin/codex-voice-host` | `lib/libgstreamer-1.0.0.dylib` |
| Windows | `bin/codex-voice-host.exe` | `bin/gstreamer-1.0-0.dll` |
| Linux | `bin/codex-voice-host` | `lib/libgstreamer-1.0.so.0` |

**能力探测入口**是 `RealtimeWebrtcSession::is_supported()`，TUI 在两处调用它决定是否展示语音相关 UI：`codex-rs/tui/src/tooltips.rs:43` 与 `codex-rs/tui/src/bottom_pane/experimental_features_view.rs:87`。后者的上下文是「实验特性视图」，说明这条通路当前仍属实验面。

### 3.3 crate 构成

`codex-rs/voice-host`（5,843 行）按职责分文件：采集（capture_worker）、回放（playback / playout）、音轨（audio_sink / audio_track）、设备（device_buffers / devices / devices_unavailable）、处理（processing）、入站（incoming）。

`codex-rs/realtime-webrtc`（1,954 行）：`codex-rs/realtime-webrtc/src/client.rs`（`VoiceHost` / `ConnectionError`）、`codex-rs/realtime-webrtc/src/session.rs`（`RealtimeWebrtcSession`）、`codex-rs/realtime-webrtc/src/protocol.rs`（`AudioControls` / `AudioState`），另有 message_reader、helper_exit（`HelperExitStage`）、linux_alsa（Linux 音频后端）三个模块。

---

## 4. `third_party/voice`：私有 GStreamer 运行时

这是仓库根下的**非 Rust** 目录，负责为上述辅助进程准备一份**私有捆绑**的音频运行时。

`third_party/voice/README.md` 开宗明义地划了边界：

> *"This stage pins and prepares sources for a privately bundled, GStreamer-based audio runtime, including its native dependencies and build tools. **It does not compile native libraries, link them into Codex or enable voice.**"*

即这一层**只做「钉版本 + 取源码 + 校验摘要」**，不编译、不链接、不启用。

该目录的 `sources.json` 记录 **11 个归档**的版本、URL 与 SHA-256：

| 用途 | 来源 |
| ---- | ---- |
| GStreamer 框架与插件 | `gstreamer`、`gst-plugins-base`、`gst-plugins-good` |
| 支撑原生库 | `glib`、`libffi`、`pcre2`、`zlib`、`proxy-libintl` |
| 音频编解码 | `opus` |
| **构建工具（非运行时库）** | `meson`、`ninja` |

> README 特别说明：GLib 的归档里**捎带了 `gvdb`**，它被记录但没有独立的 fetch 条目——所以「11 个归档」与「涉及多少个上游项目」不是一回事。同时明确「这些输入**不包含**完整的平台原生工具链」。

Bazel 用标准 `http_archive` 规则抓取、校验、解包与缓存。该目录另有一批平台专用 Python 脚本（linux_runtime / macos_runtime / windows_runtime / windows_crt / build_native / prepare_sources / assemble_package 等）与 4 个 `.bzl`，以及 `licenses/` 目录和许可声明文件。

> [!IMPORTANT]
> **发布侧有一个对应的 job**：`.github/workflows/rust-release.yml` 的 `build-macos-voice`（第 6 轮新增，见 [`build_and_release.md`](./build_and_release.md) §5.2）。也就是说语音运行时的构建在发布矩阵里是**独立一环**，不混在常规 `build` job 里。

---

## 5. `codex-utils-audio`：与上述两条通路都不同的第三件事

`codex-rs/utils/audio`（428 行）容易被误当成语音子系统的一部分，**它不是**。

模块注释（`codex-rs/utils/audio/src/lib.rs`）：

> *"Audio preparation and duration-based token estimates for model inputs."*

它做的是**模型输入侧的音频预处理与按时长估算 token**，唯一的依赖方是 `codex-core`。core 侧经它引用的有 4 处：`codex-rs/core/src/context_manager/history.rs:58`、`codex-rs/core/src/session/mod.rs:177`、`codex-rs/core/src/tools/code_mode/mod.rs:46`、`codex-rs/core/src/tools/context.rs:18`。

> **它是第 6 轮从 core 拆出去的**：原为 `codex-rs/core/src/audio_preparation.rs`<!-- ref-exempt: 反例——正文说明该旧路径已不存在 -->，随之迁走的还有 `symphonia` 依赖——该 crate **已不再是 `codex-core` 的依赖**（`grep -n symphonia codex-rs/core/Cargo.toml` 零命中）。本体系 [`core_agent_loop.md`](./core_agent_loop.md) §4.7 此前把 `symphonia` 记为 core 的依赖，已在第 6 轮更正。

---

## 6. 本文未覆盖的内容

诚实声明，避免被当作完整事实源。**以下均为「找过但本轮未展开」，不是「没找过」**：

| 未覆盖项 | 当前证据等级 | 卡点 |
| ---- | ---- | ---- |
| 端到端启用路径（用户怎么开启语音） | E1 | 需通读 TUI 侧的实验特性视图与配置链路 |
| 实时会话的完整状态机（`handle_start` 之后的流转） | E1 | `codex-rs/core/src/realtime_conversation.rs` 2,638 行，本轮只确认了入口与两条输入路径 |
| `RealtimeConversationVersion`（V1/V2/V3，默认 V2）各版本差异 | E1 | 枚举在 `codex-rs/protocol/src/protocol.rs:1714`，语义未读 |
| 语音相关配置键全集 | E1 | 已知 `experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_base_url`、`experimental_realtime_ws_model` 等（见 [`config_system.md`](./config_system.md) §3 的 `experimental_*` 清单），未逐个读取点核实 |
| `third_party/voice` 的实际构建流程 | E1 | 该目录有 10 余个 Python 脚本与 4 个 `.bzl`，本轮只读了 README 与那份 `sources.json` 清单 |
| 隐私语义的完整边界（何时采集、何时停止、数据去向） | E1 | 模块注释提到「排队中的隐私控制优先」，但实现未读。**这是最应当优先补齐的一项** |
| `codex-mxc-sandbox` / Windows 沙箱与语音的交互 | E1 | 未评估 |

---

## 7. 相关文档

- [Crate 地图](./crate_map.md) §3.13 — 语音与实时三个 crate 的定位
- [架构总览](./architecture_overview.md) §3.4 — `codex-voice-host` 在发布交付清单中的位置
- [智能体核心循环](./core_agent_loop.md) §4.7 — core 侧实时会话子系统的内部结构
- [构建与发布](./build_and_release.md) §5.2 — `build-macos-voice` job
- [实验性表面](./experimental_surfaces.md) — 实验特性的统一视角
