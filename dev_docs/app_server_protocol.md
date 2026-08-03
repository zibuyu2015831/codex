---
title: Codex app-server JSON-RPC 协议
summary: 描述 codex-app-server-protocol 的 v1/v2 分版结构、221 个方法按命名空间的分布、Rust 类型作为唯一事实源与 ts-rs 导出 550 个 TypeScript 类型的生成链路、schema fixtures 校验机制，以及协议变更的强制流程与高风险提示。
keywords: codex | app-server | json-rpc | protocol | ts-rs | schema | api-versioning
scope: codex-rs/app-server-protocol 与 codex-rs/app-server 的对外协议
related_files: codex-rs/app-server-protocol/src/lib.rs | codex-rs/app-server-protocol/src/rpc.rs | codex-rs/app-server-protocol/src/protocol/mod.rs | codex-rs/app-server-protocol/src/export.rs | codex-rs/app-server-protocol/src/schema_fixtures.rs | AGENTS.md | justfile
dependencies: dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-03
---

# app-server JSON-RPC 协议

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **覆盖范围**: `codex-app-server-protocol`（30,946 行）+ `codex-app-server`（128,364 行）的协议面
> **证据等级**: 方法清单与目录结构为 E4（实测统计）；生成链路为 E2（规范明文）+ E3（源码）

---

## 0. 先读这一节：唯一事实源规则

> [!CAUTION]
> **Rust 类型是协议的唯一事实源。TypeScript 类型是构建产物。**
>
> `codex-rs/app-server-protocol/schema/typescript/v2/` 下的 **550 个 `.ts` 文件全部由 ts-rs 自动生成**，禁止手改。文档、代码审查、AI 改动中都不得把它们当作可编辑的源文件。

改协议的强制流程（`AGENTS.md:277,300-304`）：

```
1. 改 Rust 类型
2. v2 类型必须标注 #[ts(export_to = "v2/")]     ← 漏了会导出到错误目录
3. just write-app-server-schema                  ← 重新生成 TS 与 schema fixtures
4. just test -p codex-app-server-protocol        ← 验证
5. 生成的文件与 Rust 改动放进同一个 change
```

---

## 1. 协议规模（E4 实测）

| 指标 | 数量 |
| ---- | ---: |
| 协议方法/通知名（去重） | **221** |
| 生成的 v2 TypeScript 类型文件 | 550 |
| `protocol/v2/` 下的 Rust 模块 | 27（不含测试） |

> 复核命令：
> ```bash
> grep -rhoE '"[a-zA-Z]+/[a-zA-Z/]+"' codex-rs/app-server-protocol/src/ | sort -u | wc -l
> git ls-files "codex-rs/app-server-protocol/schema/typescript/v2/*" | wc -l
> ```
> 注：221 是对源码中形如 `"命名空间/方法"` 字面量的去重统计，其中包含少量测试夹具用的示例名（如 `enum/named`、`field/optionalCollection`、`custom/unstableField`）。真实对外方法数略低于此值。

---

## 2. 版本分层

```
codex-rs/app-server-protocol/src/
├── lib.rs
├── rpc.rs                  ← JSON-RPC 载体
├── export.rs               ← ts-rs 导出入口
├── precomputed_exports.rs  ← 预计算导出
├── schema_fixtures.rs      ← schema 夹具校验
├── experimental_api.rs     ← 实验性 API 标注
└── protocol/
    ├── mod.rs
    ├── common.rs           ← 版本共用类型
    ├── v1.rs               ← v1（单文件）
    ├── v2/                 ← v2（27 个模块）
    ├── mappers.rs          ← 版本间映射
    ├── event_mapping.rs    ← 事件映射
    ├── item_builders.rs    ← item 构造器
    ├── thread_history.rs
    ├── thread_history_projection.rs
    └── serde_helpers.rs
```

**关键观察**：

- **v1 是单个文件，v2 是 27 个模块的目录** —— v2 是当前主力版本，v1 处于维持状态
- `mappers.rs` 的存在说明**两版之间有显式映射**，而非各自独立
- `thread_history_projection.rs` 说明线程历史对外暴露的是**投影**而非原始结构

---

## 3. 方法按命名空间分布（E4）

| 命名空间 | 方法数 | 领域 |
| ---- | ---: | ---- |
| `thread` | **57** | 会话线程：生命周期、item、目标、压缩、后台终端、环境 |
| `item` | 19 | 会话条目 |
| `account` | 13 | 账号、登录、额度、用量 |
| `plugin` | 12 | 插件 |
| `fs` | 10 | 文件系统 |
| `turn` | 8 | 单轮交互 |
| `remoteControl` | 8 | 远程控制（实验性） |
| `process` | 6 | 进程 |
| `mcpServer` | 6 | MCP 服务端管理 |
| `externalAgentConfig` | 6 | 外部智能体配置导入 |
| `fuzzyFileSearch` | 5 | 模糊文件搜索 |
| `command` | 5 | 命令执行 |
| `threadSection` / `skills` / `model` / `config` / `app` / `tmp` | 各 4 | — |
| `windowsSandbox` / `marketplace` / `environment` | 各 3 | — |
| `plugins` / `openai` / `hook` / `experimentalFeature` | 各 2 | — |
| 其余（`ui`、`serverRequest`、`windows` 等） | 各 1 | — |

**`thread` 占 57 个方法，是协议的绝对重心。** 这与架构一致：app-server 对外提供的核心能力就是"管理会话线程"。

### `thread` 命名空间的方法族（节选，E4）

| 方法族 | 方法 |
| ---- | ---- |
| 生命周期 | `thread/list`、`thread/fork`、`thread/archive`、`thread/archived`、`thread/delete`、`thread/deleted`、`thread/closed`、`thread/loaded/list` |
| 内容 | `thread/items/list`、`thread/metadata/update`、`thread/name/set` |
| 上下文压缩 | `thread/compact/start`、`thread/compacted` |
| 目标 | `thread/goal/set`、`thread/goal/get`、`thread/goal/clear`、`thread/goal/cleared`、`thread/goal/updated` |
| 后台终端 | `thread/backgroundTerminals/list`、`.../clean`、`.../terminate` |
| 环境 | `thread/environment/connected`、`thread/environment/disconnected` |
| 记忆 | `thread/memoryMode/set` |
| 审批 | `thread/approveGuardianDeniedAction` |

> **命名约定**：动词式为**请求**（`set`、`list`、`start`），过去式为**通知**（`archived`、`deleted`、`compacted`、`updated`）。这是从方法名归纳的（E3），未在代码中找到明文规定。

---

## 4. v2 模块版图（E4）

`protocol/v2/` 下的 27 个模块，按领域归类：

| 领域 | 模块 |
| ---- | ---- |
| 会话 | `thread.rs`、`thread_data.rs`、`turn.rs`、`item.rs`、`review.rs` |
| 账号与权限 | `account.rs`、`permissions.rs`、`attestation.rs` |
| 执行 | `command_exec.rs`、`process.rs`、`environment.rs` |
| 扩展生态 | `plugin.rs`、`plugin_search.rs`、`apps.rs`、`mcp.rs`、`hook.rs`、`skills`（见 `thread`） |
| 配置与能力 | `config.rs`、`model.rs`、`experimental_feature.rs`、`collaboration_mode.rs` |
| 系统 | `fs.rs`、`notification.rs`、`realtime.rs`、`current_time.rs`、`feedback.rs` |
| 实验性 | `remote_control.rs`（+ `remote_control_tests.rs`） |
| 共用 | `shared.rs`、`mod.rs` |

`permissions.rs:529` 中另有一份 `SandboxPolicy` 定义——**与 `codex-protocol` 中 `protocol.rs:1004` 的同名类型并存**。

> [!WARNING]
> **两个 `SandboxPolicy` 的关系未验证**（E1）。可能是协议层的独立表示 + 映射，也可能是重复定义。改动任一处前请先确认另一处，并检查 `protocol/mappers.rs`。

---

## 5. 生成与校验链路

| 环节 | 文件 / 命令 |
| ---- | ---- |
| 导出入口 | `src/export.rs` |
| 预计算导出 | `src/precomputed_exports.rs`（+ 测试） |
| schema 夹具 | `src/schema_fixtures.rs`（+ 测试） |
| 生成命令 | `just write-app-server-schema` → `cargo run -p codex-app-server-protocol --bin write_schema_fixtures` |
| 验证命令 | `just test -p codex-app-server-protocol` |

**`schema_fixtures_tests.rs` 与 `precomputed_exports_tests.rs` 的存在意味着**：如果你改了 Rust 类型却没跑生成命令，**测试会失败**。这是防漂移的机器保障，不要试图绕过。

### 其他相关生成命令

| 命令 | 产物 |
| ---- | ---- |
| `just write-config-schema` | `codex-rs/core/config.schema.json` |
| `just write-hooks-schema` | hooks schema fixtures |
| `codex app-server generate-ts` | TS 类型（CLI 路径，`main.rs:1223`） |
| `codex app-server generate-json-schema` | JSON Schema（`main.rs:1234`） |
| `codex app-server generate-internal-json-schema` | 内部 JSON Schema（`main.rs:1240`） |

---

## 6. 服务端与传输

| crate | 行数 | 角色 |
| ---- | ---: | ---- |
| `codex-app-server` | 128,364 | 服务端实现（58 个 workspace 依赖，全仓第 2） |
| `codex-app-server-transport` | 16,180 | 传输层 |
| `codex-app-server-daemon` | 3,552 | 守护进程生命周期 |
| `codex-app-server-client` | 3,435 | 客户端 |
| `codex-app-server-test-client` | 4,077 | 测试客户端 |
| `codex-app-server-protocol-noop-macros` | 20 | 空实现宏 |

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

服务端的集成测试在 `codex-rs/app-server/tests/suite/v2/`，其中 `plugin_list.rs` 有 5,478 行——是仓库第 8 大文件。

---

## 7. 跨操作系统部署

`AGENTS.md:321-322`：

> "Codex supports running connected app-server and exec-server on different operating systems. See the `$remote-tests` skill for details about integration testing these configurations."

相关传输设施：`codex-uds`（Unix domain socket）、`codex-stdio-to-uds`（stdio↔UDS 中继，hidden 子命令 `codex stdio-to-uds`）、`codex-websocket-client`。

> **未验证**（E1）：app-server 与 exec-server 之间的**具体传输协议与握手流程**。`codex-exec-server-protocol` 只有 1,723 行，是较好的切入点。跨 OS 集成测试要看 `$remote-tests` skill。

---

## 8. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **app-server API 是 `AGENTS.md:105-110` 点名的高风险改动面** | 与之并列的还有 `rawResponseItem/*` 事件、CLI 参数、配置加载、rollout 恢复 |
| `rawResponseItem/*` **即使仍是实验性的**也要谨慎改动 | `AGENTS.md:107` |
| v2 类型必须标注 `#[ts(export_to = "v2/")]` | `AGENTS.md:277` |
| API 形状变更后必须跑生成命令并验证 | `AGENTS.md:300-304` |
| **例外**：app-server API 文档**可以**放进 `docs/`——这是 `AGENTS.md:32` 唯一的例外 | `AGENTS.md:32` |

> [!NOTE]
> 上一条值得注意：全仓禁止向 `docs/` 添加通用文档，但 **app-server API 文档是明文例外**。本文档体系仍固定在 `dev_docs/`，不使用这个例外。

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 221 个方法的逐个签名与语义 | E4（仅方法名） | `protocol/v2/` 各模块 |
| v1 与 v2 的映射规则 | E1 | `protocol/mappers.rs` |
| 两个 `SandboxPolicy` 定义的关系 | E1 | `v2/permissions.rs:529` vs `codex-protocol/src/protocol.rs:1004` |
| JSON-RPC 载体格式与错误码 | E1 | `src/rpc.rs` |
| 服务端请求处理器结构 | E1 | `codex-rs/app-server/src/request_processors/` |
| 跨 OS 传输的握手流程 | E1 | `codex-exec-server-protocol`、`codex-uds` |
| `experimental_api.rs` 的标注机制 | E1 | 该文件 + `codex-experimental-api-macros` |

---

## 10. 相关文档

- [架构总览](./architecture_overview.md) — 协议先行的类型单一事实源
- [Crate 地图](./crate_map.md) §3.3、§3.5 — 协议与传输 crate
- [智能体核心循环](./core_agent_loop.md) — 会话与 turn 的内部结构
- [会话与持久化](./session_and_persistence.md) — thread 的存储侧
- [构建与发布](./build_and_release.md) — 生成物与 CI 校验
