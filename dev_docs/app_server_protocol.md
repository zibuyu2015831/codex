---
title: Codex app-server JSON-RPC 协议
summary: 描述 codex-app-server-protocol 的 v1/v2 分版结构、方法注册表所在的四个宏与按命名空间的真实方法分布（注册表 217 个 wire 名，加上宏派生的 initialized 通知共 218 个协议名）、Rust 类型作为唯一事实源与「ts-rs 仅是 dev-dependency、生产构建改用空实现宏」的生成链路（Rust 类型 → 预计算 .zst → CLI generate-ts / vendored TypeScript）、schema fixtures 的真实再生成入口（justfile 里的 recipe 已失效）、experimental_api 的 inventory 链接期注册机制、AGENTS.md 中的 API 设计硬性规则及其例外，以及协议变更的高风险提示。
keywords: codex | app-server | json-rpc | protocol | ts-rs | schema | api-versioning | method-registry | experimental-api
scope: codex-rs/app-server-protocol 与 codex-rs/app-server 的对外协议
related_files: codex-rs/app-server-protocol/src/lib.rs | codex-rs/app-server-protocol/src/rpc.rs | codex-rs/app-server-protocol/src/protocol/mod.rs | codex-rs/app-server-protocol/src/protocol/common.rs | codex-rs/app-server-protocol/src/protocol/v2/mod.rs | codex-rs/app-server-protocol/src/protocol/v2/permissions.rs | codex-rs/app-server-protocol/src/protocol/v2/config.rs | codex-rs/app-server-protocol/src/experimental_api.rs | codex-rs/app-server-protocol/src/precomputed_exports.rs | codex-rs/app-server-protocol/Cargo.toml | codex-rs/app-server-protocol/scripts/write_schema_fixtures.py | codex-rs/app-server/Cargo.toml | justfile | AGENTS.md
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-05
---

# app-server JSON-RPC 协议

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-app-server-protocol`（30,946 行）+ `codex-app-server`（128,364 行）的协议面
> **证据等级**: 方法清单为 E3（从注册表宏抽取）；纯文件计数为 E1；依赖统计为 E2（对 `codex-rs/*/Cargo.toml` 的文本统计，未触发构建）；生成链路、模块版图、实验性标注机制为 E3（读源码）
>
> 本文对证据等级**倾向于低标而非虚标**——多处标 E1 的其实已读到源码。若某条结论看起来比标注的等级更强，通常是标注保守了，而不是结论超出了证据。

---

## 0. 先读这一节：唯一事实源规则

> [!CAUTION]
> **Rust 类型是协议的唯一事实源。TypeScript 类型是构建产物。**
>
> `codex-rs/app-server-protocol/schema/typescript/v2/` 下的 **550 个 `.ts` 文件全部由 ts-rs 自动生成**，禁止手改。文档、代码审查、AI 改动中都不得把它们当作可编辑的源文件。

复核方式（每个文件首行都是生成标记，`grep -L` 列出**不含**该标记的文件，应为空）：

```bash
grep -rL 'GENERATED CODE! DO NOT MODIFY BY HAND' \
  codex-rs/app-server-protocol/schema/typescript/v2 --include='*.ts'   # 无输出
```

### ts-rs / schemars 是 `[dev-dependencies]`，不进生产构建（E3）

> [!IMPORTANT]
> **这是理解整条生成链路的前提，也是「为什么生成器是 `#[ignore]` 测试而不是二进制」的根因（见 §6）。**
>
> `codex-rs/app-server-protocol/Cargo.toml` 的 `[dependencies]` 段（`:15-37`）里**没有** `ts-rs` 和 `schemars`；它们只出现在 `[dev-dependencies]` 段（`:39` 起，`schemars` `:49`、`ts-rs` `:52`）。
>
> 生产构建下 `#[derive(TS, JsonSchema)]` 里的两个 derive 宏被替换成空实现（`codex-rs/app-server-protocol/src/lib.rs:64-71`）：
>
> ```rust
> #[cfg(not(test))] pub(crate) use codex_app_server_protocol_noop_macros::JsonSchema;
> #[cfg(not(test))] pub(crate) use codex_app_server_protocol_noop_macros::TS;
> #[cfg(test)]      pub(crate) use schemars::JsonSchema;
> #[cfg(test)]      pub(crate) use ts_rs::TS;
> ```
>
> 这正是 §7 表里那个只有 20 行的 `codex-app-server-protocol-noop-macros` crate 的用途：**让协议类型上的 `#[derive(TS, JsonSchema)]` 在非 test 构建下退化为零成本的空实现**，从而把 ts-rs / schemars 完全挡在发布产物之外。
>
> 推论：**任何真正跑 ts-rs 的路径都必须以 `cfg(test)` 编译**。所以 `codex-rs/app-server-protocol/src/export.rs`、`codex-rs/app-server-protocol/src/schema_fixtures.rs` 都是 `#[cfg(test)] mod`（`codex-rs/app-server-protocol/src/lib.rs:2-3`、`:10-11`），生成入口也只能是测试而不是 `[[bin]]`。

改协议的强制流程（`AGENTS.md` `## App-server API Development Best Practices` → `### Core Rules` / `### Development Workflow`）：

```
1. 改 Rust 类型
2. v2 类型必须标注 #[ts(export_to = "v2/")]     ← 漏了会导出到错误目录
3. 重新生成 TS 与 schema fixtures               ← 见 §6，AGENTS.md 里写的命令目前跑不通
4. just test -p codex-app-server-protocol        ← 验证
5. 生成的文件与 Rust 改动放进同一个 change
```

> [!WARNING]
> **勘误**：本文第一版把第 3 步写成「`just write-app-server-schema`」并当作必须执行的步骤，**没有实际验证它能跑**。它跑不通——见 §6。

---

## 1. 协议规模

| 指标 | 数量 | 证据 |
| ---- | ---: | ---- |
| 注册表里的协议方法/通知名（去重） | **217** | E3，见下方抽取命令 |
| 加上抽取命令抓不到的 `ClientNotification::Initialized`（wire 名 `initialized`） | **218** | E3 |
| 生成的 v2 TypeScript 类型文件 | 550 | E1（`git ls-files`） |
| `schema/typescript/` 全部文件 | 642 | E1 |
| `schema/json/` 文件 | 285（递归口径，见 §7） | E1 |
| `schema/precomputed/` 文件 | 2（整条 TS 生成链路的枢纽，见 §6） | E1 |
| `protocol/v2/` 下的 Rust 模块（不含测试） | **28** | E1（`ls` 数文件）+ E3（读 `codex-rs/app-server-protocol/src/protocol/v2/mod.rs` 的 28 条 `mod` / `pub use` 声明） |

> [!WARNING]
> **勘误**：第一版给的是 **221**，来自对**整个 `src/` 目录**做 `grep -rhoE '"[a-zA-Z]+/[a-zA-Z/]+"'` 的粗暴统计。那个口径会把测试夹具名、测试路径字面量、类型判别值一起算进来，同时又漏掉用 `#[serde(rename = "...")]` 而非 `=> "..."` 声明的方法。本文改用**从方法注册表宏直接抽取**的口径（见 §3）。

---

## 2. 版本分层

目录树（**略去 5 个 `*_tests.rs`**：`codex-rs/app-server-protocol/src/precomputed_exports_tests.rs`、`codex-rs/app-server-protocol/src/schema_fixtures_tests.rs`、`codex-rs/app-server-protocol/src/protocol/common_tests.rs`、`codex-rs/app-server-protocol/src/protocol/item_builders_tests.rs`、`codex-rs/app-server-protocol/src/protocol/thread_history_projection_tests.rs`）：

```
codex-rs/app-server-protocol/src/
├── lib.rs
├── rpc.rs                  ← JSON-RPC 载体
├── export.rs               ← ts-rs 导出入口（#[cfg(test)]，非测试构建不编译）
├── precomputed_exports.rs  ← 预计算导出（普通模块，进生产构建）
├── schema_fixtures.rs      ← schema 夹具校验（#[cfg(test)]，非测试构建不编译）
├── experimental_api.rs     ← 实验性 API 标注
└── protocol/
    ├── mod.rs
    ├── common.rs           ← ★ 方法注册表（四个宏）+ 版本共用类型（4,209 行）
    ├── v1.rs               ← v1（单文件，仅 237 行）
    ├── v2/                 ← v2（28 个模块）
    ├── mappers.rs          ← 私有 mod，24 行，无生产调用方（见下）
    ├── event_mapping.rs    ← core Event → v2 ServerNotification
    ├── item_builders.rs    ← item 构造器
    ├── thread_history.rs
    ├── thread_history_projection.rs
    └── serde_helpers.rs    ← 私有 mod
```

`codex-rs/app-server-protocol/src/export.rs` 与 `codex-rs/app-server-protocol/src/schema_fixtures.rs` 的 `#[cfg(test)]` 出自 `codex-rs/app-server-protocol/src/lib.rs:2-3` 与 `:10-11`；原因见 §0「ts-rs / schemars 是 `[dev-dependencies]`」。

**关键观察**：

- **v1 是单个文件（237 行），v2 是 28 个模块的目录** —— 对照 `codex-rs/app-server-protocol/src/protocol/common.rs` 的 4,209 行，v1 的体量已经小到可以忽略：v2 是当前主力版本，v1 处于维持状态
- `codex-rs/app-server-protocol/src/protocol/thread_history_projection.rs` 说明线程历史对外暴露的是**投影**而非原始结构
- `codex-rs/app-server-protocol/src/protocol/mod.rs:1-12` 有明确的**可见性分级**：`mappers` 与 `serde_helpers` 是私有 `mod`，其余 8 个是 `pub mod`。这是判定 `codex-rs/app-server-protocol/src/protocol/mappers.rs` 为死代码的第一个信号

> [!WARNING]
> **勘误：`codex-rs/app-server-protocol/src/protocol/mappers.rs` 不是「v1↔v2 的显式映射层」，它是死代码。**
> 上一稿从「存在一个叫 `codex-rs/app-server-protocol/src/protocol/mappers.rs` 的文件」推出「两版之间有显式映射机制」——这是从文件名推导机制，不成立。实际情况：
>
> - `codex-rs/app-server-protocol/src/protocol/mappers.rs` **全文 24 行**，只含一个 `impl From<v1::ExecOneOffCommandParams> for v2::CommandExecParams`
> - `ExecOneOffCommandParams` 全仓仅 3 处出现：定义（`codex-rs/app-server-protocol/src/protocol/v1.rs:187`）、`impl` 签名与 `fn from` 形参（`codex-rs/app-server-protocol/src/protocol/mappers.rs:3`、`:4`）。**没有任何生产调用方**，`ExecOneOffCommand` 也不在 217 条注册表里
> - `codex-rs/app-server-protocol/src/protocol/mod.rs:7` 把它声明为私有 `mod mappers;`，外部无法引用
>
> **`codex-rs/app-server-protocol/src/protocol/event_mapping.rs` 也不是 v1↔v2 映射**：全文 614 行，`v1::` 出现 **0** 次、`v2::` 出现 16 次——它做的是 **core `Event` → v2 `ServerNotification`** 的转换，与版本间映射无关。
>
> 真正的分版机制见 §3：**v1 与 v2 共用同一个 `ClientRequest` 枚举，靠 params 类型区分版本**，不存在集中式的版本映射层。
>
> 复核命令：
> ```bash
> wc -l codex-rs/app-server-protocol/src/protocol/mappers.rs                    # 24
> grep -rn 'ExecOneOffCommandParams' --include='*.rs' .                          # 3 处
> grep -c 'v1::' codex-rs/app-server-protocol/src/protocol/event_mapping.rs      # 0
> ```

### 「它不是真正的 JSON-RPC 2.0」

> [!IMPORTANT]
> `codex-rs/app-server-protocol/src/rpc.rs:1-2` 的模块文档第一句就是：
>
> > "We do not do true JSON-RPC 2.0, as we neither send nor expect the `\"jsonrpc\": \"2.0\"` field."
>
> 文件里确实定义了 `pub const JSONRPC_VERSION: &str = "2.0";`（`codex-rs/app-server-protocol/src/rpc.rs:11`），但那不代表线上帧里带这个字段。**写第三方客户端时不要按 JSON-RPC 2.0 规范去校验帧格式。** 本文其余部分沿用「JSON-RPC」这个说法，但请记住这个限定。

---

## 3. 方法注册表在哪里（E3）

> [!IMPORTANT]
> **协议方法的权威清单不在 `protocol/v2/` 下，而在 `codex-rs/app-server-protocol/src/protocol/common.rs` 的四个宏调用里。**
> 第一版把 `codex-rs/app-server-protocol/src/protocol/common.rs` 只标成「版本共用类型」，导致读者无从下手找方法表。

四个宏的**定义**与**调用**都在同一个文件 `codex-rs/app-server-protocol/src/protocol/common.rs` 内，**没有跨 crate 的过程宏参与**——想看展开结果，直接读这个文件的宏体即可。

| 宏 | 定义行 | 调用区段 | 主要生成物 | 条目数 |
| ---- | ---: | ---- | ---- | ---: |
| `client_request_definitions!` | `:203` | `:474-1259` | `enum ClientRequest` + `enum ClientResponse` / `ClientResponsePayload` + `method_name()`（`:241`）+ `TryFrom<JSONRPCRequest>`（`:261`）+ 3 个 `export_client_*` | 136 |
| `server_request_definitions!` | `:1265` | `:1529-1600` | `enum ServerRequest` + `enum ServerResponse` / `ServerRequestPayload` + 3 个 `export_server_*` | 9 |
| `server_notification_definitions!` | `:1436` | `:1684-1787` | `enum ServerNotification` + `TryFrom<JSONRPCNotification>`（`:1473`）+ `export_server_notification_schemas` | 72（其中 1 条不用 `=> "..."` 而用 rename/strum 属性声明，纯箭头抽取只得 71） |
| `client_notification_definitions!` | `:1493` | `:1808-1810` | `enum ClientNotification` + `export_client_notification_schemas` | 1（`Initialized`，wire 名 `initialized`，见下） |

（行号均相对 `codex-rs/app-server-protocol/src/protocol/common.rs`。）

> [!NOTE]
> **四个宏的生成物并不对称**，不要假设它们各生成同一套东西：
> - `method_name()` **只有** `client_request_definitions!` 生成（`:241`）
> - `TryFrom<JSONRPC*>` 只有前者与 `server_notification_definitions!` 在宏内生成；`impl TryFrom<JSONRPCRequest> for ServerRequest`（`:1521`）是**手写在文件顶层**、不在任何宏体内的
> - 所有 `export_*` 函数都带 `#[cfg(test)]`（例如 `:420`、`:436`、`:1480`、`:1510`），原因见 §0——它们要调用 ts-rs / schemars

> [!WARNING]
> **勘误：`ClientNotification::Initialized` 不是「无 wire 名」，它的 wire 名是 `"initialized"`。**
> 上一稿从「宏调用区段里没有 `=> "..."` 字面量」推出「这个通知没有 wire 名」——又一次从「字面量不存在」推导机制不存在。**第三方客户端作者按上一稿会以为不存在 `initialized` 帧，这是可执行层面的错误。**
>
> 宏定义（`codex-rs/app-server-protocol/src/protocol/common.rs:1500-1508`）在生成的枚举上加了：
>
> ```rust
> #[serde(tag = "method", content = "params", rename_all = "camelCase")]
> #[strum(serialize_all = "camelCase")]
> pub enum ClientNotification { ... }
> ```
>
> 所以 wire 名**由变体名 `Initialized` 派生**为 `"initialized"`，并已固化进生成的 schema：`codex-rs/app-server-protocol/schema/json/ClientNotification.json` 里是 `"method": { "enum": ["initialized"], "title": "InitializedNotificationMethod" }`。
>
> 生产收发两端都在：发送 `codex-rs/app-server/src/in_process.rs:381`（`client.notify(ClientNotification::Initialized)?;`），接收 `codex-rs/app-server/src/message_processor.rs:634`（`process_client_notification`）。
>
> 准确说法：它**只是没有显式字面量**（所以下面的抽取命令抓不到，217 这个数才要另外 +1），不是没有 wire 名。

抽取命令（本文所有方法统计的口径，E3）：

```bash
F=codex-rs/app-server-protocol/src/protocol/common.rs
extract() { awk -v a=$1 -v b=$2 'NR>=a&&NR<=b' $F \
  | grep -oE '(=>[[:space:]]*|strum\(serialize = )"[^"]+"' | sed 's/.*"\(.*\)"/\1/'; }
{ extract 474 1259; extract 1529 1600; extract 1684 1787; } | sort -u > /tmp/methods.txt
wc -l < /tmp/methods.txt                                    # 217
awk -F/ '{print (NF>1 ? $1 : "(无命名空间)")}' /tmp/methods.txt | sort | uniq -c | sort -rn
```

> [!NOTE]
> **为什么要匹配 `strum(serialize = ...)` 而不只是 `=> "..."`**：绝大多数条目写成 `Variant => "ns/method" { ... }`，但 `AccountLoginCompleted`（`codex-rs/app-server-protocol/src/protocol/common.rs:1782-1785`）改用 `#[serde(rename)]` + `#[ts(rename)]` + `#[strum(serialize)]` 三件套声明 wire 名。只抓 `=> "` 会把它漏掉，`account` 就会少算成 12。
>
> 而 `ClientNotification::Initialized` 连 `strum(serialize)` 都没有——它靠 `#[strum(serialize_all = "camelCase")]` 从变体名派生，**任何基于字面量的抽取口径都抓不到它**，只能人工 +1。这就是 217 与 218 两个数的来源。

### `ClientRequest` 是一个横跨 v1+v2 的枚举

`client_request_definitions!` 区段里：

- `params: v2::...` —— **116** 处
- `params: v1::...` —— **4** 处：`Initialize`（`:476`）、`GetConversationSummary`（`:1219`）、`GitDiffToRemote`（`:1224`）、`GetAuthStatus`（`:1230`）

也就是说 **v1 与 v2 的请求共用同一个 `ClientRequest` 枚举**，靠 params 类型区分版本，而不是两个独立的协议表面。

> [!NOTE]
> **勘误：举例举错了区段。** 上一稿把 `ExecCommandApproval` 当作 `client_request_definitions!` 里的 v1 例子——**它不在这个宏里**。`ExecCommandApproval { params: v1::ExecCommandApprovalParams }` 位于 **`server_request_definitions!`** 宏调用区段（`codex-rs/app-server-protocol/src/protocol/common.rs:1596-1597`），即**服务端发给客户端**的请求，方向与客户端请求枚举相反。
>
> **"4 处"这个计数是对的**，只是四个成员全部是上面列出的那些。`server_request_definitions!` 里另有 2 处 v1（`ApplyPatchApproval` `codex-rs/app-server-protocol/src/protocol/common.rs:1591`、`ExecCommandApproval` `:1597`）与 9 处 v2，属于另一张表。
>
> 复核方式：先用 `grep -n 'client_request_definitions!\|server_request_definitions!'` 拿到两个宏的起始行，再在各自行号区间内数 `params: v1::`——**跨宏统计会把两个方向的请求混成一堆。**

### 11 个无命名空间的遗留方法（217 口径下 10 条，另加 `initialized`）

不带 `<resource>/<method>` 形式的方法名（全部来自注册表，非测试夹具）：

```
initialize   getAuthStatus   getConversationSummary   gitDiffToRemote   fuzzyFileSearch
error        warning         configWarning            guardianWarning   deprecationNotice
initialized  ← 抽取命令抓不到，见上方勘误
```

前 5 个是请求，中间 5 个是服务端通知，最后 1 个是唯一的客户端通知。
**口径提醒**：§4 表格里 `(无命名空间)` 一行写的是 **10**，那是 217 口径（抽取命令的输出）；把 `initialized` 算进来是 **11**。两个数都对，看的是哪个口径。

它们早于 `<resource>/<method>` 约定，新代码不应仿照。

---

## 4. 方法按命名空间分布（E3，注册表口径）

| 命名空间 | 方法数 | 领域 |
| ---- | ---: | ---- |
| `thread` | **60** | 会话线程：生命周期、item、目标、压缩、后台终端、环境、实时语音 |
| `item` | 19 | 会话条目 |
| `account` | 13 | 账号、登录、额度、用量 |
| `plugin` | 12 | 插件 |
| `fs` | 10 | 文件系统 |
| *(无命名空间)* | 10 | 遗留方法，见 §3 |
| `turn` | 8 | 单轮交互 |
| `remoteControl` | 8 | 远程控制（实验性） |
| `process` | 6 | 进程 |
| `mcpServer` | 6 | MCP 服务端管理 |
| `externalAgentConfig` | 6 | 外部智能体配置导入 |
| `fuzzyFileSearch` | 5 | 模糊文件搜索（**另有 1 个同名无命名空间遗留方法**，合计 6 条以 `fuzzyFileSearch` 开头） |
| `command` | 5 | 命令执行 |
| `threadSection` / `skills` / `model` / `config` / `app` | 各 4 | — |
| `windowsSandbox` / `marketplace` / `environment` | 各 3 | — |
| `hook` / `experimentalFeature` | 各 2 | — |
| `windows`、`serverRequest`、`review`、`rawResponseItem`、`rawResponse`、`permissionProfile`、`modelProvider`、`mock`、`memory`、`mcpServerStatus`、`hooks`、`feedback`、`currentTime`、`configRequirements`、`collaborationMode`、`attestation` | 各 1 | — |

> [!WARNING]
> **勘误（相对第一版）**：
> - `thread` 57 → **60**
> - `account` 13 保持（第一版偶然正确；粗暴 grep 与 `=> "` 抽取都会算成 12，只有把 rename 属性算上才是 13）
> - `fuzzyFileSearch` 5 → 命名空间下 5 条 + 1 条同名遗留方法
> - `windowsSandbox` 从「各 3」一行中被单独确认存在（第一版 §5 的模块表却漏了对应的 v2 模块文件，前后矛盾——见 §5 勘误）
> - **删除三个不存在的命名空间**（第一版那条粗暴正则 `'"[a-zA-Z]+/[a-zA-Z/]+"'` 把下面这些带斜杠的字符串一起算成了命名空间）：
>   - `tmp` —— 来自测试里的路径字面量，如 `codex-rs/app-server-protocol/src/protocol/common.rs:2933` 的 `absolute_path_string("tmp/AGENTS.md")` <!-- ref-exempt: `tmp/AGENTS.md` 是被引述的测试字面量本身（论点正是「它是路径字面量、不是命名空间」），不指向仓库文件 -->
>   - `plugins` —— 来自 `codex-rs/app-server-protocol/src/protocol/v2/tests.rs:3423` 的 `path: Some("plugins/example")` 与 `:3480` 的 `sparse_paths: Some(vec!["plugins/foo"])`，是**字段取值**，不是测试函数名
>   - `openai` —— **上一稿的举证不可复现**：它说来源是 `model_provider: "openai"`，但那是个不含斜杠的普通 String 值，在上述正则下根本匹配不到。真实来源是两个**带斜杠**的字面量：`codex-rs/app-server-protocol/src/protocol/v2/mcp.rs:675-676` 的 MCP UI content-type 判别值 `openai/form`（`#[serde(rename)]` + `#[ts(rename)]`，**在生产代码里**，不是测试值），以及 `codex-rs/app-server-protocol/src/protocol/v2/tests.rs:2206` 测试 JSON 中的 `"openai/imagePicker"`。结论不变——`openai` 不是协议命名空间
> - `enum/unit`、`enum/tuple`、`enum/named`（`codex-rs/app-server-protocol/src/experimental_api.rs:69-73`）同理，是 `#[experimental(...)]` derive 宏的**单元测试夹具**，不是协议方法
> - 新增 `(无命名空间)` 一行（10 条遗留方法，第一版完全没提），并把「各 1」的 16 个命名空间逐一列出；第一版笼统写成「其余（`ui`、`serverRequest`、`windows` 等）」，而 `ui` 在注册表里**并不存在**

**`thread` 占 60 个方法，是协议的绝对重心。** 这与架构一致：app-server 对外提供的核心能力就是「管理会话线程」。

### `thread` 命名空间的方法族（节选，E3）

| 方法族 | 方法 |
| ---- | ---- |
| 生命周期 | `thread/start`、`thread/started`、`thread/read`、`thread/resume`、`thread/list`、`thread/fork`、`thread/archive`、`thread/archived`、`thread/unarchive`、`thread/unarchived`、`thread/delete`、`thread/deleted`、`thread/closed`、`thread/loaded/list`、`thread/unsubscribe` |
| 内容 | `thread/items/list`、`thread/turns/list`、`thread/metadata/update`、`thread/name/set`、`thread/name/updated`、`thread/inject_items`、`thread/rollback` |
| 搜索 | `thread/search`、`thread/searchOccurrences` |
| 上下文压缩 | `thread/compact/start`、`thread/compacted` |
| 目标 | `thread/goal/set`、`thread/goal/get`、`thread/goal/clear`、`thread/goal/cleared`、`thread/goal/updated` |
| 实时语音 | `thread/realtime/start`、`.../started`、`.../stop`、`.../closed`、`.../sdp`、`.../appendAudio`、`.../appendText`、`.../appendSpeech`、`.../listVoices`、`.../itemAdded`、`.../outputAudio/delta`、`.../transcript/delta`、`.../transcript/done`、`.../error` |
| 后台终端 | `thread/backgroundTerminals/list`、`.../clean`、`.../terminate` |
| 环境 | `thread/environment/connected`、`thread/environment/disconnected` |
| 设置与用量 | `thread/settings/update`、`thread/settings/updated`、`thread/status/changed`、`thread/tokenUsage/updated`、`thread/memoryMode/set` |
| 审批与推举 | `thread/approveGuardianDeniedAction`、`thread/increment_elicitation`、`thread/decrement_elicitation` |

### 命名约定：有明文规定，也有反例

> [!IMPORTANT]
> 第一版称命名约定「未在代码中找到明文规定」——**错了**。`AGENTS.md` 的 `## App-server API Development Best Practices` 下有一整套硬性规则，**但它们分散在两个不同的小节里，作用域也不同**（上一稿把这些规则**全部**记在 `### Core Rules` 名下，其中 **2 条**——`#[ts(optional = nullable)]` 与游标分页——实际属于 `### Client->server request payloads` 小节）：
>
> **来自 `### Core Rules`（适用于全部 v2 API 表面）：**
>
> | 规则 | AGENTS.md 关键词 |
> | ---- | ---- |
> | 所有新 API 只做 v2，**不得给 v1 增加表面积** | `Do not add new API surface area to v1` |
> | 载荷命名 `*Params` / `*Response` / `*Notification` | `Follow payload naming consistently` |
> | 方法名形如 `<resource>/<method>`，**resource 用单数** | `keep <resource> singular` |
> | wire 上一律 camelCase（字段与字符串枚举值），**除非 tagged union 或明确的兼容性要求需要定点 rename** | `Always expose fields as camelCase on the wire ... unless a tagged union or explicit compatibility requirement needs a targeted rename`（`AGENTS.md:274`） |
> | **例外**：config RPC 载荷用 snake_case，以对齐 config.toml 键名 | `Exception: config RPC payloads are expected to use snake_case` |
> | v2 载荷字段**禁止** `#[serde(skip_serializing_if = "Option::is_none")]`；**例外**：故意无 params 的 client→server 请求可写 `params: #[ts(type = "undefined")] #[serde(skip_serializing_if = "Option::is_none")] Option<()>` | `Never use #[serde(skip_serializing_if = ...)] for v2 API payload fields` + `Exception: client->server requests that intentionally have no params`（`AGENTS.md:278-281`） |
> | ID 在 API 边界用朴素 `String`；时间戳用 `i64` Unix 秒且命名 `*_at` | `Prefer plain String IDs` / `Timestamps should be integer Unix seconds` |
>
> **来自 `### Client->server request payloads (`*Params`)`（只适用于 client→server 的 `*Params` 类型）：**
>
> | 规则 | AGENTS.md 关键词 |
> | ---- | ---- |
> | `#[ts(optional = nullable)]` **只能**用在 client→server 的 `*Params` 上（`AGENTS.md:291` 逐字无例外从句） | `Do not use #[ts(optional = nullable)] outside client->server request payloads` |
> | 新的 list 方法**默认实现游标分页**（`cursor`/`limit` → `data`/`next_cursor`） | `For new list methods, implement cursor pagination by default` |
>
> **为什么这个区分重要**：把只约束 `*Params` 的规则当成通用规则，会导致给 `*Response` / `*Notification` 也加上 `#[ts(optional = nullable)]`——而那恰恰是该小节明令禁止的。
>
> **反向的错也一样危险**：上面两条带 `unless` / `Exception:` 从句的规则，如果转述时把例外丢掉，就会把「有例外的规则」当成「无例外的规则」，从而误判现有代码违规。上一稿正是这么丢的。
>
> 另外可从方法名归纳（E3，非明文）：动词式为**请求**（`set`、`list`、`start`），过去式为**通知**（`archived`、`deleted`、`compacted`、`updated`）。

> [!WARNING]
> **反例 1：三个方法用了 snake_case，违反 camelCase 规则。**
> `thread/decrement_elicitation`、`thread/increment_elicitation`、`thread/inject_items`。
> 复核：`grep '_' /tmp/methods.txt`（对上面抽取命令的输出）——只有这三条。
>
> **反例 2：五个方法用了复数 resource，违反 `keep <resource> singular`。**
> `skills/list`、`skills/changed`、`skills/config/write`、`skills/extraRoots/set`，以及 `hooks/list`。
> 尤其刺眼的是 **`hooks/list` 与单数的 `hook/started`、`hook/completed` 并存于同一协议**——同一个领域里单复数两种写法同时在线，是这条规则最直接的自相矛盾例证。
> 复核：`grep -E '^(skills|hooks|hook)/' /tmp/methods.txt`。
>
> 改协议时不要把这两类当成可以照抄的先例。

### 实验性 API 的标注机制（E3）

注册表里有 **53 处 `#[experimental(...)]`** 标注（分布：`client_request_definitions!` 区段 38 处、`server_request_definitions!` 1 处、`server_notification_definitions!` 14 处）。整套机制在 `codex-rs/app-server-protocol/src/experimental_api.rs`（全文 195 行，其中 `:1-56` 是实现，`:58` 起是 `#[cfg(test)] mod tests`）：

| 组成 | 位置 | 说明 |
| ---- | ---- | ---- |
| trait `ExperimentalApi` | `codex-rs/app-server-protocol/src/experimental_api.rs:5-9` | 唯一方法 `fn experimental_reason(&self) -> Option<&'static str>`；`None` 表示完全稳定 |
| struct `ExperimentalField` | `:13-20` | `{ type_name, field_name, reason }`；`reason` 的约定是 `<method>`（方法级）或 `<method>.<field>`（字段级） |
| **注册机制** | `:22` `inventory::collect!(ExperimentalField);` | 用 **`inventory` crate 的链接期分布式注册**——各处的 `#[experimental]` 宏各自提交一条记录，链接时汇总，无需中心清单 |
| 运行时查询 | `:25-27` `experimental_fields()` | `inventory::iter::<ExperimentalField>` 收集全部注册项 |
| 容器透传 | `:34-56` | 为 `Option<T>` / `Vec<T>` / `HashMap<K,V,S>` / `BTreeMap<K,V>` 各实现一份，递归找**第一个**实验性成员 |
| 错误信息 | `:30-32` `experimental_required_message(reason)` | 生成 `"{reason} requires experimentalApi capability"` |
| 注解入口 | `#[experimental("...")]` | 由 `codex-experimental-api-macros` 提供 |

> [!NOTE]
> **`inventory` 是生产依赖，不是 dev-dependency**（`codex-rs/app-server-protocol/Cargo.toml:34`），`codex-experimental-api-macros` 同样在 `[dependencies]` 里（`:17`）。这与 ts-rs / schemars 的处境正相反（§0）——实验性门禁必须在**运行时**生效，所以整套机制都进生产构建。

`AGENTS.md:286-287` 明文规定了用法：用 `#[experimental("method/or/field")]`；需要**字段级**门禁时 derive `ExperimentalApi`；**当一个方法只有部分字段是实验性的**，要在 `codex-rs/app-server-protocol/src/protocol/common.rs` 的注册表条目上写 `inspect_params: true`（让服务端逐字段检查而不是整个方法拒绝）。

规模上最集中的是 `remoteControl/*`——7 个方法全部带标注（`codex-rs/app-server-protocol/src/protocol/common.rs:939`、`:945`、`:951`、`:957`、`:963`、`:969`、`:975`），与 §4 表里 `remoteControl` 标注为「实验性」一致。

> [!WARNING]
> `AGENTS.md` 的 `### Development Workflow` 明令**不要**为「某个字段是否带实验标记」写样板测试（关键词 `Avoid boilerplate tests that only assert experimental field markers`）。`codex-rs/app-server-protocol/src/experimental_api.rs:58-78` 里那几个 `enum/unit`、`enum/tuple`、`enum/named` 是 **derive 宏自身的单元测试夹具**，不是协议方法，也不是这类样板测试。

---

## 5. v2 模块版图（E3 主 + E1 辅）

> **证据等级说明**：核心论据是读源码——`codex-rs/app-server-protocol/src/protocol/v2/mod.rs:1-58` 的声明结构（`mod shared;` + 27 条 `mod ...;`，对应 28 条 `pub use ...::*;`），以及 `codex-rs/app-server-protocol/src/protocol/v2/remote_control.rs:203` 的 `#[path = "remote_control_tests.rs"]` 属性（它说明 `codex-rs/app-server-protocol/src/protocol/v2/remote_control_tests.rs` 是被 `#[cfg(test)]` 挂进来的测试文件，不是独立模块）。只有「目录下共 31 个 `.rs` 文件」这一条是 E1（`ls`）。

`protocol/v2/` 下共 31 个 `.rs` 文件，其中 **28 个是非测试模块**；另外 3 个是 `codex-rs/app-server-protocol/src/protocol/v2/tests.rs`、`codex-rs/app-server-protocol/src/protocol/v2/remote_control_tests.rs` 与 `codex-rs/app-server-protocol/src/protocol/v2/mod.rs` 本身。

**下表中的模块名均位于 `codex-rs/app-server-protocol/src/protocol/v2/` 目录下**（为避免歧义，路径写全）：

| 领域 | 模块 |
| ---- | ---- |
| 会话 | `codex-rs/app-server-protocol/src/protocol/v2/thread.rs`、`codex-rs/app-server-protocol/src/protocol/v2/thread_data.rs`、`codex-rs/app-server-protocol/src/protocol/v2/turn.rs`、`codex-rs/app-server-protocol/src/protocol/v2/item.rs`、`codex-rs/app-server-protocol/src/protocol/v2/review.rs` |
| 账号与权限 | `codex-rs/app-server-protocol/src/protocol/v2/account.rs`、`codex-rs/app-server-protocol/src/protocol/v2/permissions.rs`、`codex-rs/app-server-protocol/src/protocol/v2/attestation.rs` |
| 执行与沙箱 | `codex-rs/app-server-protocol/src/protocol/v2/command_exec.rs`、`codex-rs/app-server-protocol/src/protocol/v2/process.rs`、`codex-rs/app-server-protocol/src/protocol/v2/environment.rs`、`codex-rs/app-server-protocol/src/protocol/v2/windows_sandbox.rs` |
| 扩展生态 | `codex-rs/app-server-protocol/src/protocol/v2/plugin.rs`、`codex-rs/app-server-protocol/src/protocol/v2/plugin_search.rs`、`codex-rs/app-server-protocol/src/protocol/v2/apps.rs`、`codex-rs/app-server-protocol/src/protocol/v2/mcp.rs`、`codex-rs/app-server-protocol/src/protocol/v2/hook.rs` |
| 配置与能力 | `codex-rs/app-server-protocol/src/protocol/v2/config.rs`、`codex-rs/app-server-protocol/src/protocol/v2/model.rs`、`codex-rs/app-server-protocol/src/protocol/v2/experimental_feature.rs`、`codex-rs/app-server-protocol/src/protocol/v2/collaboration_mode.rs` |
| 系统 | `codex-rs/app-server-protocol/src/protocol/v2/fs.rs`、`codex-rs/app-server-protocol/src/protocol/v2/notification.rs`、`codex-rs/app-server-protocol/src/protocol/v2/realtime.rs`、`codex-rs/app-server-protocol/src/protocol/v2/current_time.rs`、`codex-rs/app-server-protocol/src/protocol/v2/feedback.rs` |
| 实验性 | `codex-rs/app-server-protocol/src/protocol/v2/remote_control.rs` |
| 共用 | `codex-rs/app-server-protocol/src/protocol/v2/shared.rs` |

> [!NOTE]
> **勘误**：第一版说 27 个模块，且表里漏了 `codex-rs/app-server-protocol/src/protocol/v2/windows_sandbox.rs`、多列了一行不存在的文件 `skills（见 thread）`。`skills/*` 是 4 个协议方法（`skills/list`、`skills/changed`、`skills/config/write`、`skills/extraRoots/set`），但 v2 目录下**没有** `skills.rs`——`windowsSandbox/*` 的 3 个方法则**确实**有对应模块。用 `ls codex-rs/app-server-protocol/src/protocol/v2/` 可以一眼复核。 <!-- ref-exempt: `skills.rs` 是本条论点否定的对象，v2 目录下不存在该文件 -->

### 两个 `SandboxPolicy` 不是重复定义（E3）

`codex-rs/app-server-protocol/src/protocol/v2/permissions.rs:529` 有一份 `SandboxPolicy`，`codex-rs/protocol/src/protocol.rs:1004` 有一份同名类型（注意 crate 名叫 `codex-protocol`，但它在仓库里的目录是 `codex-rs/protocol/`，不是 `codex-protocol/`）。

> [!NOTE]
> **勘误**：第一版把两者关系标成「未验证（E1），可能是重复定义」，并让读者去查 `codex-rs/app-server-protocol/src/protocol/mappers.rs`——但 `codex-rs/app-server-protocol/src/protocol/mappers.rs` 里 `SandboxPolicy` 出现 **0 次**，那是个死胡同。

真实关系（`codex-rs/app-server-protocol/src/protocol/v2/permissions.rs:639-640`）：

```rust
impl SandboxPolicy {
    pub fn to_core(&self) -> codex_protocol::protocol::SandboxPolicy { ... }
}
```

- **v2 版是 wire 表示**：`#[serde(tag = "type", rename_all = "camelCase")]`，并且有一份**手写的 `Deserialize` 实现**（`:595`，经由中间类型 `SandboxPolicyDeserialize`，`:559`）来处理兼容性。
- **core 版是内部表示**：kebab-case 序列化。
- `to_core()` 做 wire→core 转换（`NetworkAccess` 也在此处映射到 `CoreNetworkAccess`）。

> [!NOTE]
> **勘误：转换不是单向的。** 上一稿称 `to_core()` 是"单向的 wire→core 转换点"。同一个文件里还有反向实现（`codex-rs/app-server-protocol/src/protocol/v2/permissions.rs:673-674`）：
>
> ```rust
> impl From<codex_protocol::protocol::SandboxPolicy> for SandboxPolicy {
>     fn from(value: codex_protocol::protocol::SandboxPolicy) -> Self { ... }
> }
> ```
>
> 即 **core→wire 方向由 `From` 实现承担**，两个方向都在。这很自然——服务端既要接收客户端传来的策略，也要把当前生效的策略回报给客户端。
>
> 所以下面这条"必须同步"的提醒，实际上**要同步的是两个 match，不是一个**。

改任一处时，`to_core()` 与那个 `From` 实现的 match 都必须同步——它们都是穷尽匹配，漏了会编译失败，这是机器保障。

---

## 6. 生成与校验链路

### 完整链路（两段，不要混成一段）

```
Rust 类型
  │  ① 只在 cfg(test) 下：ts-rs / schemars 真正参与（§0）
  ▼
schema/precomputed/app-server-exports-{stable,experimental}.json.zst   （2 个文件）
  │  ② include_bytes! 编译进二进制 + 运行时 zstd 解压回放
  ▼
CLI `codex app-server generate-ts`  /  vendored schema/typescript/（550 个 .ts）
```

**第 ① 段**由 `#[ignore]` 测试驱动（见下方 CAUTION），**第 ② 段完全不跑 ts-rs**：

- `codex-rs/app-server-protocol/src/precomputed_exports.rs:15-18` 用 `include_bytes!` 把两个 `.zst` **编译进发布二进制**
- `:123` 的 `zstd::stream::decode_all(...)` 在运行时解压后回放导出结果
- `:14` 的 `pub(crate) const GENERATED_TS_HEADER: &str = "// GENERATED CODE! DO NOT MODIFY BY HAND!\n\n";` 正是那 550 个 `.ts` 文件首行 header 的来源

这解释了 §1 表里那条不起眼的「`schema/precomputed/` 文件 = 2」：**它不是一个计数条目，而是整条链路的枢纽**——发布出去的 `codex` 二进制之所以能在用户机器上 `generate-ts`，靠的就是这两个预烤好的 `.zst`，而不是把 ts-rs 打包进去。

| 环节 | 文件 / 命令 |
| ---- | ---- |
| 导出入口（`#[cfg(test)]`） | `codex-rs/app-server-protocol/src/export.rs` |
| 预计算导出（生产模块） | `codex-rs/app-server-protocol/src/precomputed_exports.rs`（+ 测试） |
| schema 夹具（`#[cfg(test)]`） | `codex-rs/app-server-protocol/src/schema_fixtures.rs`（+ 测试） |
| **真实再生成入口** | `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py` |
| 验证命令 | `just test -p codex-app-server-protocol` |

> [!CAUTION]
> **`just write-app-server-schema` 目前跑不通——这是上游的陈旧，不是本文写错。**
>
> 仓库根 `justfile:175-176` 的 recipe 是：
>
> ```
> write-app-server-schema *args:
>     cargo run -p codex-app-server-protocol --bin write_schema_fixtures -- {args}
> ```
>
> 但 `codex-rs/app-server-protocol/Cargo.toml` **没有任何 `[[bin]]` 段**，`src/bin/` 目录也不存在，所以这条 `cargo run --bin write_schema_fixtures` 必然失败。
>
> `AGENTS.md` 的 `### Development Workflow` 小节仍然写着 `just write-app-server-schema`（以及 `--experimental` 变体），同样已经陈旧。
>
> **实际能用的入口是 Python 脚本** `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`：它设置 `CODEX_APP_SERVER_SCHEMA_ROOT`（以及 `CODEX_APP_SERVER_SCHEMA_EXPERIMENTAL`、可选的 `CODEX_APP_SERVER_SCHEMA_PRETTIER`）后运行
>
> ```
> cargo test -p codex-app-server-protocol --lib \
>   schema_fixtures_tests::write_schema_fixtures_from_env -- --exact --ignored
> ```
>
> 即：**生成器本身是一个被 `#[ignore]` 标记、靠环境变量驱动的测试**，不是二进制。脚本还接受 `--schema-root`、`-p/--prettier`、`--experimental` 三个参数。
>
> **根因**（上一稿只描述了现象）：ts-rs 与 schemars 是 `[dev-dependencies]`，非 test 构建下 `#[derive(TS, JsonSchema)]` 被换成空实现宏（见 §0）。所以**生成逻辑在物理上只能存在于 `cfg(test)` 里**——即便有人把 justfile 修好，也不可能改成 `[[bin]]`，除非把 ts-rs 提升为生产依赖。这条 recipe 大概率是在依赖关系调整前留下的。

> [!WARNING]
> **勘误**：第一版把 `just write-app-server-schema` 写进 §0 的强制流程当作必做步骤，却没有验证它是否可执行。改协议前请先确认当前 justfile 是否已修好；没修好就直接跑上面的 Python 脚本。

**`codex-rs/app-server-protocol/src/schema_fixtures_tests.rs` 与 `codex-rs/app-server-protocol/src/precomputed_exports_tests.rs` 的作用**：如果你改了 Rust 类型却没重新生成夹具与 `.zst`，这个漂移**会被这两个测试捕获**。关键在于 `codex-rs/app-server-protocol/src/schema_fixtures_tests.rs:1-5` 同时导入了两侧：`crate::export::generate_ts_with_options`（**真跑 ts-rs**）与 `crate::precomputed_exports::decode_precomputed_exports`（**回放 `.zst`**），然后把两者逐文件比对（`stable_precomputed_exports_match_schema_fixtures` `:47`、`experimental_precomputed_exports_match_generated` `:70`）。这是防漂移的机器保障，不要试图绕过。

> [!NOTE]
> **两个同名函数是个真实的坑**：`generate_ts_with_options` 在 `codex-rs/app-server-protocol/src/export.rs:110`（真 ts-rs，`#[cfg(test)]`）和 `codex-rs/app-server-protocol/src/precomputed_exports.rs:62`（读 `.zst` 回放，进生产构建）各有一份。看代码时务必确认用的是哪一个。

### schema 产物的三个目录（E1）

| 目录 | 文件数 | 内容 |
| ---- | ---: | ---- |
| `schema/typescript/` | 642（其中 `v2/` 550） | ts-rs 导出的 `.ts` 类型 |
| `schema/json/` | 285（递归） | JSON Schema。含两个巨型汇总文件：`codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.schemas.json`（22,635 行，全仓最大文件）与 `codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json`（20,393 行），以及 `codex-rs/app-server-protocol/schema/json/ClientRequest.json`、`codex-rs/app-server-protocol/schema/json/ServerNotification.json` 等按类型拆分的文件 |

> **口径说明**：285 是**递归计数**，包含 `v1/` 与 `v2/` 两个子目录里的文件。只看顶层是 39 项：
>
> ```bash
> ls codex-rs/app-server-protocol/schema/json | wc -l                    # 39（含 v1/ v2/ 两个目录项）
> find codex-rs/app-server-protocol/schema/json -type f | wc -l          # 285
> ```
>
> 两个数字都对，但**必须写明是哪一种**——否则读者按 `ls` 复核会以为差了一个数量级。
| `schema/precomputed/` | 2 | 预计算导出 |

> [!WARNING]
> **勘误：这份 vendored 的 `codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json` 不是 Python SDK 类型生成的输入。**
> 上一稿写「它同时是 Python SDK 类型生成的输入」，并引 [`sdk_guide.md`](./sdk_guide.md) §5 作背书——但 `sdk_guide.md:317-319` 恰恰是**推翻这个说法**的那段勘误。这是从「两边有同名文件」推出「存在引用关系」。
>
> 实际链路（`sdk/python/scripts/update_sdk_artifacts.py:1360-1362`）：
>
> ```python
> with tempfile.TemporaryDirectory(prefix="codex-python-schema-") as td:
>     schema_dir = generate_schema_from_pinned_runtime(Path(td) / "schema")
>     generate_types_from_schema_dir(schema_dir)
> ```
>
> 即：SDK 脚本从一个**临时目录**读取 schema，而那份 schema 是由**已发布的、被 pin 住的 runtime 二进制**现场导出的（走的正是上面 §6 的 `.zst` 回放路径），与仓库里 `codex-rs/app-server-protocol/schema/json/` 这份 vendored 产物**没有任何引用关系**。两者只是碰巧同名、内容相近。
>
> 复核：`grep -c 'app-server-protocol' sdk/python/scripts/update_sdk_artifacts.py` → **0**（脚本全文不提这个 crate 路径）。
>
> 详见 [`sdk_guide.md`](./sdk_guide.md) §5。

### 其他相关生成命令

| 命令 | 产物 |
| ---- | ---- |
| `just write-config-schema` | `codex-rs/core/config.schema.json` |
| `just write-hooks-schema` | hooks schema fixtures |
| `codex app-server generate-ts` | TS 类型（CLI 路径，`codex-rs/cli/src/main.rs:1223`） |
| `codex app-server generate-json-schema` | JSON Schema（`codex-rs/cli/src/main.rs:1234`） |
| `codex app-server generate-internal-json-schema` | 内部 JSON Schema（`codex-rs/cli/src/main.rs:1240`） |

> [!IMPORTANT]
> **这三个 CLI 子命令与本节上半部的 ts-rs 链路是两条不同的路。** 它们跑在**发布二进制**里，而发布二进制根本没有 ts-rs（§0）——走的是 `codex-rs/app-server-protocol/src/precomputed_exports.rs` 的 `include_bytes!` + zstd 回放路径。
> 换句话说：**改了 Rust 类型之后跑 `codex app-server generate-ts` 不会反映你的改动**，因为它读的是编译进当时那个二进制里的预计算快照。要重新生成，必须走 `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py`（它会重跑 `cfg(test)` 下的 ts-rs）。

---

## 7. 服务端与传输

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-app-server` | 128,364 | 服务端实现（依赖规模见下） |
| `codex-app-server-transport` | 16,180 | 传输层 |
| `codex-app-server-daemon` | 3,552 | 守护进程生命周期 |
| `codex-app-server-client` | 3,435 | 客户端 |
| `codex-app-server-test-client` | 4,077 | 测试客户端 |
| `codex-app-server-protocol-noop-macros` | 20 | 空实现宏：非 test 构建下顶替 `ts_rs::TS` 与 `schemars::JsonSchema`，把这两个 dev-dependency 挡在生产构建外（见 §0） |

> [!NOTE]
> **勘误**：第一版写「58 个 workspace 依赖，全仓第 2」，这个数字复现不出来。按明确口径重新统计每个 crate 清单文件的 `[dependencies]` 段（**E2**——只是对 `codex-rs/*/Cargo.toml` 跑 awk/grep 的文本统计，没有触发任何构建或测试）：
>
> | 口径 | `codex-app-server` | 排名 |
> | ---- | ---: | ---- |
> | `workspace = true` 条目 | **73** | 第 3（`codex-core` 94、`codex-tui` 85） |
> | 内部 `codex-*` 依赖 | **53** | 第 2（`codex-core` 57） |
>
> 复核命令：
> ```bash
> for f in codex-rs/*/Cargo.toml; do
>   n=$(awk '/^\[dependencies\]/{f=1;next}/^\[/{f=0}f' $f | grep -c "workspace = true")
>   echo "$n $f"
> done | sort -rn | head
> ```
> 结论不变：**app-server 是全仓耦合面最广的 crate 之一，改它的影响半径很大。**

### CLI 入口（E3，`codex-rs/cli/src/main.rs`）

| 子命令 | 位置 | 说明 |
| ---- | ---- | ---- |
| `codex app-server` | `:147`、`:1114` | 标注 `[experimental]` |
| `codex app-server daemon start/stop/restart/bootstrap/version` | `:1169-1210` | 守护进程管理 |
| `codex app-server daemon enable-remote-control` / `disable-remote-control` | `:1184`、`:1188` | 远程控制开关 |
| `codex app-server proxy` | `:1213` | 代理 |
| `codex remote-control` | `:150`、`:1245` | 标注 `[experimental]` |

### 测试客户端

```bash
just app-server-test-client    # 构建 CLI 并连上测试客户端
```

服务端的集成测试在 `codex-rs/app-server/tests/suite/v2/`，其中 `codex-rs/app-server/tests/suite/v2/plugin_list.rs` 有 5,478 行。

---

## 8. 跨操作系统部署

`AGENTS.md` `## Platform Support`：

> "Codex supports running connected app-server and exec-server on different operating systems. See the `$remote-tests` skill for details about integration testing these configurations."

同一节还要求：「Tests and features must support Linux, macOS and Windows unless feature is explicitly OS-specific.」

相关传输设施：`codex-uds`（Unix domain socket）、`codex-stdio-to-uds`（stdio↔UDS 中继，hidden 子命令 `codex stdio-to-uds`）、`codex-websocket-client`。

> **未验证**（E1）：app-server 与 exec-server 之间的**具体传输协议与握手流程**。`codex-exec-server-protocol` 只有 1,723 行，是较好的切入点。跨 OS 集成测试要看 `$remote-tests` skill。

---

## 9. 改动本区域的注意事项

| 事项 | 依据（`AGENTS.md` 章节 + 关键词） |
| ---- | ---- |
| **app-server API 是点名的高风险改动面** | `## Code Review Rules` → `### Breaking changes`；与之并列的还有 `rawResponseItem/*` 事件、CLI 参数、配置加载、rollout 恢复 |
| `rawResponseItem/*` **即使仍是实验性的**也要谨慎改动 | 同上，关键词 `even while experimental` |
| 新 API 一律做在 v2，不得扩大 v1 表面积 | `## App-server API Development Best Practices` → `### Core Rules`，关键词 `Do not add new API surface area to v1` |
| v2 类型必须标注 `#[ts(export_to = "v2/")]` | 同上，关键词 `Always set #[ts(export_to = "v2/")]` |
| API 形状变更后必须重新生成夹具并验证 | `### Development Workflow`，关键词 `Regenerate schema fixtures` / `just test -p codex-app-server-protocol`；**但生成命令本身已陈旧，见 §6** |
| 至少要同步更新 `codex-rs/app-server/README.md` | `### Development Workflow`，关键词 `Update app-server docs/examples` |
| **例外**：app-server API 文档**可以**放进 `docs/` | `AGENTS.md` 顶部规则列表，关键词 `Do not add general product or user-facing documentation to the docs/ folder` 那一条的后半句 |
| 别为「某个字段是否带实验标记」写样板测试 | `### Development Workflow`，关键词 `Avoid boilerplate tests that only assert experimental field markers` |

> [!NOTE]
> 倒数第二条值得注意：全仓禁止向 `docs/` 添加通用文档，但 **app-server API 文档是明文例外**。本文档体系仍固定在 `dev_docs/`，不使用这个例外。

> [!NOTE]
> `AGENTS.md:265` 该节的适用文件清单里逐字写的是 `app-server-protocol/src/protocol/v2.rs`（单文件），而实际早已是 `protocol/v2/` 目录——这是上游文档的又一处陈旧，不影响规则本身的效力。此处保留原文写法是为了让读者能在 `AGENTS.md` 里检索到。 <!-- ref-exempt: `app-server-protocol/src/protocol/v2.rs` 是对 AGENTS.md:265 的逐字引述，本条论点正是「这个路径在仓库里已不存在」 -->

---

## 10. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 217 个方法的逐个签名与语义 | E3（仅方法名） | `codex-rs/app-server-protocol/src/protocol/common.rs` 的四个宏 + `protocol/v2/` 各模块 |
| **v1 请求在服务端如何被处理**（已确认不存在集中式 v1↔v2 映射层，见 §2） | E3（只确认了 `codex-rs/app-server-protocol/src/protocol/mappers.rs` 是死代码、`codex-rs/app-server-protocol/src/protocol/event_mapping.rs` 与版本无关） | `codex-rs/app-server/src/request_processors/` 里那 4 个 `params: v1::` 请求的处理器 |
| JSON-RPC 载体的完整帧格式与错误码 | E1（只确认了「非标准 2.0」） | `codex-rs/app-server-protocol/src/rpc.rs` |
| 服务端请求处理器结构 | E1 | `codex-rs/app-server/src/request_processors/` |
| 游标分页在既有 list 方法上的落实程度 | E1 | 各 `*ListParams` / `*ListResponse` |
| 跨 OS 传输的握手流程 | E1 | `codex-exec-server-protocol`、`codex-uds` |
| `codex-experimental-api-macros` 与 `codex-app-server-protocol-noop-macros` 的宏展开细节 | E3（两者的**用途**已查明，见 §4、§0；未读展开代码） | `codex-rs/experimental-api-macros/` 与 `codex-rs/app-server-protocol-noop-macros/` 两个 crate 的 lib 根文件 |

---

## 11. 相关文档

- [架构总览](./architecture_overview.md) — 协议先行的类型单一事实源
- [Crate 地图](./crate_map.md) §3.3、§3.5 — 协议与传输 crate
- [配置体系](./config_system.md) §1 — `ConfigLayerSource` 在 `codex-rs/app-server-protocol/src/protocol/v2/config.rs` 的 wire 副本
- [SDK 指南](./sdk_guide.md) — 只有 Python SDK 用本协议；TypeScript SDK 走 `codex exec --experimental-json`
- [智能体核心循环](./core_agent_loop.md) — 会话与 turn 的内部结构
- [会话与持久化](./session_and_persistence.md) — thread 的存储侧
- [构建与发布](./build_and_release.md) — 生成物与 CI 校验
