---
title: Codex 会话与持久化
summary: 描述 rollout 的 jsonl 落盘格式与文件命名规则、thread-store 的线程操作面与写锁机制、state crate 的 SQLite 与迁移体系、三层存储的分工，以及从既有 rollout 恢复会话这一高风险改动面的注意事项。
keywords: codex | session | rollout | thread-store | sqlite | jsonl | persistence | fork
scope: codex-rs/rollout、thread-store、state 与会话恢复相关实现
related_files: codex-rs/rollout/src/recorder.rs | codex-rs/rollout/src/lib.rs | codex-rs/thread-store/src/local | codex-rs/state/src/lib.rs | codex-rs/core/src/session/rollout_reconstruction.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 会话与持久化

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 落盘格式与命名规则为 E3（源码注释与代码）；模块结构为 E4；跨组件协作次序为 E1

---

## 1. 三层存储

| 层 | crate | 行数 | 载体 | 存什么 |
| ---- | ---- | ---: | ---- | ---- |
| **rollout** | `codex-rollout` | 13,940 | `.jsonl` 文件 | 会话的完整事件流，可回放可检查 |
| **thread-store** | `codex-thread-store` | 20,404 | 本地文件 + 索引 | 线程元数据、分组、归档状态 |
| **state** | `codex-state` | 19,744 | **SQLite** | 运行时状态、日志、审计 |

另有 `codex-rollout-trace`（13,257 行）负责 rollout 的追踪与回放（`codex debug trace-reduce`），`codex-message-history`（1,437 行）负责消息历史。

---

## 2. rollout：会话的事实记录（E3）

### 2.1 落盘格式与位置

`codex-rs/rollout/src/recorder.rs:1` 的模块文档：

> "Persist Codex session rollouts (.jsonl) so sessions can be replayed or inspected later."

同文件 `:81-82` 给出了真实的检查方式：

```bash
jq -C . ~/.codex/sessions/rollout-<日期>-<会话ID>.jsonl
fx ~/.codex/sessions/rollout-<日期>-<会话ID>.jsonl
```

**文件命名规则**（`recorder.rs:1570`，E3）：

```rust
let filename = format!("rollout-{date_str}-{conversation_id}.jsonl");
```

| 要素 | 说明 |
| ---- | ---- |
| 目录 | `$CODEX_HOME/sessions/`（默认 `~/.codex/sessions/`） |
| 前缀 | `rollout-` |
| 日期 | 形如 `2025-05-07T17-24-21`（冒号替换为连字符，可安全用作文件名） |
| 会话 ID | UUID |
| 扩展名 | `.jsonl`（每行一个 JSON 事件） |

> [!TIP]
> **调试会话问题时，直接 `jq` 这个文件是最快的路径。** 它是纯文本、逐行 JSON，不需要任何工具支持。

### 2.2 模块版图（E4）

| 文件 | 职责 |
| ---- | ---- |
| `recorder.rs` | 写入 |
| `reverse_jsonl_scanner.rs` | **反向扫描 jsonl**（`ReverseJsonlScanner`、`ScanOutcome`，`lib.rs:82-83`） |
| `compression.rs` | 压缩 |
| `metadata.rs` | 元数据 |
| `list.rs` / `search.rs` | 列举与搜索 |
| `session_index.rs` | 会话索引 |
| `rollout_reference_index.rs` | 引用索引 |
| `state_db.rs` / `sqlite_metrics.rs` | SQLite 侧 |
| `ordinal.rs` | 序号 |
| `policy.rs` / `config.rs` | 策略与配置 |
| `model_context.rs` | 模型上下文 |
| `persistence_metrics.rs` | 持久化指标 |

> **反向扫描器的存在很有信息量**：要"读最近 N 条"而不加载整个文件，就需要从文件尾部往前扫。这说明 rollout 文件可能很大，且常见需求是访问尾部。

---

## 3. thread-store：线程管理（E4）

### 3.1 操作面

`codex-rs/thread-store/src/local/` 下每个操作一个文件，一目了然：

| 操作 | 文件 |
| ---- | ---- |
| 创建 | `create_thread.rs` |
| 读取 | `read_thread.rs` |
| 列举 | `list_threads.rs` |
| 搜索 | `search_threads.rs` |
| 删除 | `delete_thread.rs` |
| 归档 / 取消归档 | `archive_thread.rs` / `unarchive_thread.rs` |
| 更新元数据 | `update_thread_metadata.rs` |
| 分组移动 | `move_thread_to_section.rs` |
| **分页 fork** | `paginated_fork.rs` |
| 历史 | `thread_history.rs` + `thread_history/` + `thread_history_materialization.rs` |
| 分组 | `thread_sections.rs` |
| **rollout 血缘** | `rollout_lineage.rs` |
| **写锁** | `writer_lock.rs` |
| 实时写入 | `live_writer.rs` |
| 模型上下文 | `model_context.rs` |

这套操作面与 app-server 协议的 `thread/*`（57 个方法）严格对应，见 [`app_server_protocol.md`](./app_server_protocol.md) §3。

### 3.2 两个值得注意的机制

> [!IMPORTANT]
> **① 写锁（`writer_lock.rs` + `writer_lock_tests.rs`）**
> 存在显式的写锁机制，说明**多个进程可能同时访问同一份线程存储**——TUI、app-server、exec 都可能在跑。改动写入路径时必须考虑并发。

> [!IMPORTANT]
> **② rollout 血缘（`rollout_lineage.rs`）**
> `codex fork` 会从既有会话派生新会话，两者之间存在**血缘关系**。这解释了为什么有 `paginated_fork.rs`——fork 一个长会话需要分页处理。

### 3.3 其他组成

| 文件 | 说明 |
| ---- | ---- |
| `in_memory.rs` | 内存实现（测试用途） |
| `store.rs` | 存储抽象 |
| `live_thread.rs` | 活跃线程 |
| `thread_metadata_sync.rs` | 元数据同步 |
| `types.rs` / `error.rs` | 类型与错误 |

---

## 4. state：SQLite 运行时状态（E4）

`codex-rs/state/src/`：

| 文件 | 职责 |
| ---- | ---- |
| `sqlite.rs` | SQLite 接入 |
| `migrations.rs` + `migrations_tests.rs` | **数据库迁移** |
| `log_db.rs` + `log_db_filter_tests.rs` | 日志库与过滤 |
| `audit.rs` | 审计 |
| `telemetry.rs` | 遥测 |
| `paths.rs` | 路径 |
| `extract.rs` | 提取 |
| `model/`、`runtime.rs` + `runtime/` | 模型与运行时 |

### 查看日志

```bash
just log        # 实时查看 state SQLite 中的日志
```

底层是 `cargo run -p codex-cli --bin logs_client`。

> [!WARNING]
> **迁移与 Bazel 的交互**：`AGENTS.md:40-43` 特别点名了 `sqlx::migrate!`——这类编译期读取目录的宏必须在 `BUILD.bazel` 配置 `compile_data`，否则 Cargo 过而 Bazel 挂。改动 `migrations.rs` 或迁移文件时务必检查。

---

## 5. 会话恢复与 fork

### 5.1 用户入口

| 命令 | 说明 |
| ---- | ---- |
| `codex resume` | 恢复会话（默认弹选择器，`--last` 直接续最近一个） |
| `codex fork` | 从既有会话派生（默认弹选择器，`--last` fork 最近一个） |
| `codex archive` / `unarchive` | 归档 / 取消归档 |
| `codex delete` | 永久删除 |

CLI 实现见 `codex-rs/cli/src/main.rs:1268-1362`。TUI 侧的选择器是 `codex-rs/tui/src/resume_picker.rs`（6,681 行）。

### 5.2 恢复链路

| 组件 | 位置 |
| ---- | ---- |
| 会话重建 | `core/src/session/rollout_reconstruction.rs`（+ 测试） |
| rollout 血缘 | `thread-store/src/local/rollout_lineage.rs` |
| 分页 fork | `thread-store/src/local/paginated_fork.rs` |
| 集成测试 | `core/tests/suite/fork_thread.rs`、`compact_resume_fork.rs` |

> [!CAUTION]
> **「从既有 rollout 恢复会话」是 `AGENTS.md:105-110` 明确点名的高风险改动面**，与 app-server API、CLI 参数、配置加载并列。
>
> 尤其注意 `compact_resume_fork.rs` 这个测试名——**上下文压缩、恢复、fork 三者交互**是最容易出问题的组合。

---

## 6. 与协议层的对应

| 存储侧 | 协议侧（`thread/*`，57 个方法） |
| ---- | ---- |
| `create_thread` / `read_thread` / `list_threads` | `thread/list`、`thread/loaded/list`、`thread/items/list` |
| `archive_thread` / `unarchive_thread` | `thread/archive`、`thread/archived` |
| `delete_thread` | `thread/delete`、`thread/deleted` |
| `paginated_fork` | `thread/fork` |
| `update_thread_metadata` | `thread/metadata/update`、`thread/name/set` |
| `move_thread_to_section` / `thread_sections` | `threadSection/*`（4 个） |
| （压缩） | `thread/compact/start`、`thread/compacted` |

---

## 7. 改动本区域的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **rollout 恢复是高风险改动面** | `AGENTS.md:105-110` |
| 改了 `sqlx::migrate!` 相关代码要补 `BUILD.bazel` 的 `compile_data` | `AGENTS.md:40-43` |
| 存储写入路径需考虑多进程并发（存在显式写锁） | `writer_lock.rs` |
| 改智能体逻辑必须补集成测试 | `AGENTS.md:112-118` |
| 落盘格式变更会影响既有用户的历史会话，需考虑兼容 | `.jsonl` 是持久化契约 |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `.jsonl` 每行事件的具体结构 | E1 | `rollout/src/recorder.rs`、直接 `jq` 一个真实文件 |
| SQLite 表结构与迁移历史 | E1 | `state/src/migrations.rs`、`model/` |
| 线程历史的物化（materialization）机制 | E1 | `thread-store/src/local/thread_history_materialization.rs` |
| 写锁的粒度与超时 | E1 | `thread-store/src/local/writer_lock.rs` |
| rollout 压缩的触发条件 | E1 | `rollout/src/compression.rs`、`policy.rs` |
| 会话搜索的索引方式 | E1 | `rollout/src/search.rs`、`session_index.rs` |
| `codex-rollout-trace` 的回放机制 | E1 | 该 crate + `codex debug trace-reduce` |
| 归档后数据的实际去向 | E1 | `archive_thread.rs` |

---

## 9. 相关文档

- [智能体核心循环](./core_agent_loop.md) — 会话与 turn 的内存态
- [app-server 协议](./app_server_protocol.md) §3 — `thread/*` 方法族
- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 落盘内容
- [测试指南](./testing_guide.md) — `fork_thread.rs`、`compact_resume_fork.rs`
- [构建与发布](./build_and_release.md) — `compile_data` 陷阱
