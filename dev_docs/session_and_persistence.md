---
title: Codex 会话与持久化
summary: 描述 rollout 的 jsonl 落盘格式、YYYY/MM/DD 分层目录与文件命名规则、默认关闭的 zstd 压缩特性开关（默认路径下 rollout 仍是纯文本 jsonl）、rollout 同时写入的 SQLite 线程元数据、thread-store 的线程操作面与写锁机制、state crate 的 5 个 SQLite 迁移器、归档目录，以及从既有 rollout 恢复会话这一高风险改动面的注意事项。
keywords: codex | session | rollout | thread-store | sqlite | jsonl | zstd | archived-sessions | persistence | fork
scope: codex-rs/rollout、thread-store、state 与会话恢复相关实现
related_files: codex-rs/rollout/src/recorder.rs | codex-rs/rollout/src/lib.rs | codex-rs/rollout/src/compression.rs | codex-rs/rollout/src/state_db.rs | codex-rs/rollout/Cargo.toml | codex-rs/thread-store/Cargo.toml | codex-rs/thread-store/src/local | codex-rs/state/src/migrations.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# 会话与持久化

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 落盘路径、命名规则、压缩策略、迁移器清单为 E3（源码）；模块结构与目录清单为 E1；跨组件协作次序部分为 E1

> [!WARNING]
> **本文有两处修订史值得先读**：
>
> 1. **第一版把 rollout 的目录层级写错了**（漏了 `YYYY/MM/DD`）。按第一版给的路径 `ls`，一个文件都找不到。详见 §2.1。
> 2. **第二版（本文的上一稿）在压缩问题上矫枉过正**：它把「第一版说 rollout 是纯文本」判为错误，改写成「压缩不是可选功能、超过 7 天必然变成 `.jsonl.zst`」。**这个改写本身是错的。** `.zst` 机器确实存在，但它挂在一个 `default_enabled: false` 的特性开关后面，**默认配置下 rollout 不会被压缩**——在默认口径上，第一版反而更接近事实。详见 §2.2。

---

## 1. 三层存储

| 层 | crate | 行数 | 载体 | 存什么 |
| ---- | ---- | ---: | ---- | ---- |
| **rollout** | `codex-rollout` | 13,940 | `.jsonl` 文件（开启压缩特性后旧文件才转 `.jsonl.zst`，见 §2.2）**＋ SQLite 线程元数据** | 会话的完整事件流，可回放可检查 |
| **thread-store** | `codex-thread-store` | 20,404 | **无独立载体**：架在 `codex-rollout` + `codex-state` 之上，自身直接依赖 `sqlx` | 线程元数据、分组、归档状态的操作面 |
| **state** | `codex-state` | 19,744 | **SQLite**（5 个独立库，见 §4） | 运行时状态、日志、目标、记忆、线程历史、审计 |

> [!NOTE]
> **更正说明**：第一版的「载体」列写成 rollout=「`.jsonl` 文件」、thread-store=「本地文件 + 索引」，两者都不准确。依据（E2，`Cargo.toml` 的 `[dependencies]`）：
>
> ```
> rollout      → codex-state, zstd, ...            # 既写 jsonl，也写 SQLite，还做压缩
> thread-store → codex-rollout, codex-state, sqlx  # 自己不发明存储，全部借下层
> ```
>
> `rollout/src/state_db.rs` 直接 `use codex_state::SqliteConfig / ThreadMetadataBuilder / LogEntry`——**rollout 在写 jsonl 的同时也在往 SQLite 写线程元数据**。所以「rollout = 纯文件、state = 纯数据库」这个二分是错的。

另有 `codex-rollout-trace`（13,257 行）负责 rollout 的追踪与回放（`codex debug trace-reduce`），`codex-message-history`（1,437 行）负责消息历史。

---

## 2. rollout：会话的事实记录（E3）

### 2.1 落盘路径：`sessions/YYYY/MM/DD/`，不是 `sessions/`

> [!CAUTION]
> **本文第一版把目录写成了 `$CODEX_HOME/sessions/`——少了三层日期目录。** 按第一版给的命令 `ls ~/.codex/sessions/rollout-*.jsonl` **一个文件都匹配不到**。
>
> 错误来源可以确认：第一版直接抄了 `recorder.rs:81-82` 的**文档注释示例**，而那段注释本身是过时的（它写的是 `~/.codex/sessions/rollout-2025-05-07T17-24-21-<uuid>.jsonl`）。**真实路径由代码决定，不由注释决定。**

真正建目录的代码在 `codex-rs/rollout/src/recorder.rs:1553-1560`（E3）：

```rust
// Resolve ~/.codex/sessions/YYYY/MM/DD path.
let timestamp = OffsetDateTime::now_local()...;
let mut dir = config.codex_home().to_path_buf();
dir.push(SESSIONS_SUBDIR);                            // "sessions"
dir.push(timestamp.year().to_string());               // YYYY
dir.push(format!("{:02}", u8::from(timestamp.month()))); // MM
dir.push(format!("{:02}", timestamp.day()));          // DD
```

文件名在同函数 `:1570`：

```rust
let filename = format!("rollout-{date_str}-{conversation_id}.jsonl");
```

| 要素 | 说明 |
| ---- | ---- |
| 目录 | **`$CODEX_HOME/sessions/YYYY/MM/DD/`**（默认 `~/.codex/sessions/2026/08/03/`） |
| 前缀 | `rollout-` |
| 日期 | 形如 `2025-05-07T17-24-21`（`format_description!` 定义，冒号替换为连字符，可安全用作文件名） |
| 会话 ID | UUID |
| 扩展名 | `.jsonl`（每行一个 JSON 事件）。**默认就是这个形态**；只有显式开启压缩特性后，超过 7 天的文件才会变成 `.jsonl.zst`，见 §2.2 |

`SESSIONS_SUBDIR` 常量在 `rollout/src/lib.rs:25`。`rollout/src/recorder_tests.rs`、`tests.rs`、`compression_tests.rs`、`rollout_reference_index_tests.rs` 中的断言路径形如 `sessions/2025/01/03/rollout-<ts>-<uuid>.jsonl`，可作交叉验证。

**能用的查找命令**：

```bash
# 找最近的 rollout（注意用 -path 递归，别指望顶层通配）
find ~/.codex/sessions -name 'rollout-*.jsonl*' -type f | sort | tail -5
```

### 2.2 zstd 压缩存在，但挂在一个默认关闭的特性开关后面

> [!CAUTION]
> **这一节记录了一次矫枉过正。**
>
> - 第一版说 rollout「是纯文本、逐行 JSON，不需要任何工具支持」。
> - 第二版看到 `rollout/src/compression.rs` 里那套完整的 zstd 工作器，就断言「压缩不是可选功能」、「7 天后必然变成 `.jsonl.zst`」。
> - **第二版错了。** 压缩工作器只有一个生产调用点，而那个调用点被特性开关包着，开关默认关闭。**在默认配置下，rollout 就是纯 `.jsonl`，第一版的结论在默认口径上是对的。**
>
> 教训：看到一个功能完整的模块，不等于它在默认路径上被启用了。**要顺着调用链找到唯一的生产调用点，再看它的门禁条件。**

#### 唯一的生产调用点及其门禁（E3）

`codex-rs/core/src/thread_manager.rs:319-324`：

```rust
if config
    .features
    .enabled(Feature::LocalThreadStoreCompression)
{
    codex_rollout::spawn_rollout_compression_worker(config.codex_home.to_path_buf());
}
```

该开关的注册项在 `codex-rs/features/src/lib.rs:991-994`：

```rust
FeatureSpec {
    id: Feature::LocalThreadStoreCompression,
    key: "local_thread_store_compression",
    stage: Stage::UnderDevelopment,
    default_enabled: false,
},
```

可自行复核（E4）：

```bash
# 生产调用点只有一处（另两处命中是定义与 re-export）
grep -rn spawn_rollout_compression_worker codex-rs/ --include=*.rs
# codex-rs/core/src/thread_manager.rs:323      ← 唯一生产调用点
# codex-rs/rollout/src/compression.rs:29       ← 定义
# codex-rs/rollout/src/lib.rs:41               ← re-export
```

**结论**：`Stage::UnderDevelopment` + `default_enabled: false` ⇒ 除非用户在 config 里显式打开 `local_thread_store_compression`，压缩工作器根本不会被 spawn。

#### 开关打开之后，机器本身是这样的（E3）

下表的常量与函数都真实存在且如实描述——**它们只是不在默认路径上跑**：

| 事实 | 位置 |
| ---- | ---- |
| 压缩后缀 `.zst` | `compression.rs:18` `const COMPRESSED_SUFFIX: &str = ".zst"` |
| **超过 7 天的 rollout 才压缩** | `:258` `const MIN_ROLLOUT_AGE: Duration = Duration::from_secs(7 * 24 * 60 * 60)`，判定在 `:716` `if age < MIN_ROLLOUT_AGE { ... }` |
| 压缩算法与级别 | `:732` `fn encode_zstd_to_writer(...)`，`:257` `const COMPRESSION_LEVEL: i32 = 3` |
| 写入用临时文件再改名 | `:649` `encode_zstd_to_writer(path, temp_file.as_file_mut())`，`TEMP_SUFFIX = ".tmp"` |
| 有跨进程运行锁与陈旧清理 | `RUN_MARKER_FILE_NAME = "rollout-compression.lock"`、`RUN_MARKER_STALE_AFTER = 6h`、`WORKER_MAX_RUNTIME = 5h` |
| 依赖 | `rollout/Cargo.toml` 的 `zstd = { workspace = true }` |

所以调试命令应该这样用：

```bash
# 默认配置：直接 jq 就行，rollout 是纯文本 jsonl
jq -C . ~/.codex/sessions/2026/07/01/rollout-....jsonl

# 仅当开启了 local_thread_store_compression、且文件已超过 7 天时，
# 才会出现 .jsonl.zst，这时改用：
zstdcat ~/.codex/sessions/2026/07/01/rollout-....jsonl.zst | jq -C .
```

> [!TIP]
> **调试会话问题时 `jq` 是最快的路径，默认情况下也是够用的。** 只有在压缩开关被打开过的环境里才需要先确认扩展名。
>
> 代码侧不必自己判断形态，但**统一两种形态的不是反向扫描器**：`reverse_jsonl_scanner.rs` 里没有任何 `.zst` / `COMPRESSED_SUFFIX` 的引用，它的签名是 `ReverseJsonlScanner<R: Read + Seek>`（`:20`、`:30`），而 zstd 流本身不可 seek。真正屏蔽差异的入口是 `open_rollout_line_reader`（定义在 `rollout/src/compression.rs:47`，从 `rollout/src/lib.rs:37-41` 连同 `RolloutLineReader` / `existing_rollout_path` / `plain_rollout_path` 一起 re-export），它按路径选择 `RolloutLineReaderInner::Plain` 或阻塞式 zstd 解码分支。路径名层面的后缀剥离则在 `compression.rs:960` 的 `strip_suffix(COMPRESSED_SUFFIX)`。

### 2.3 模块版图（E1）

| 文件 | 职责 |
| ---- | ---- |
| `recorder.rs` | 写入 |
| `reverse_jsonl_scanner.rs` | **反向扫描 jsonl**（`ReverseJsonlScanner<R: Read + Seek>`、`ScanOutcome`，`lib.rs:82-83`）。**只处理可 seek 的明文流，不认识 `.zst`** |
| `compression.rs` | **zstd 压缩工作器**（7 天阈值、运行锁、原子改名）+ 统一读取入口 `open_rollout_line_reader`。压缩侧默认不启用，见 §2.2 |
| `metadata.rs` | 元数据 |
| `list.rs` / `search.rs` | 列举与搜索 |
| `session_index.rs` | 会话索引 |
| `rollout_reference_index.rs` | 引用索引 |
| `state_db.rs` / `sqlite_metrics.rs` | **SQLite 侧**：`state_db.rs` 借 `codex-state` 写线程元数据（`ThreadMetadataBuilder`、`SqliteConfig`），并重导出 `LogEntry` |
| `ordinal.rs` | 序号 |
| `policy.rs` / `config.rs` | 策略与配置 |
| `model_context.rs` | 模型上下文 |
| `persistence_metrics.rs` | 持久化指标 |

> **反向扫描器的存在很有信息量**：要"读最近 N 条"而不加载整个文件，就需要从文件尾部往前扫。这说明 rollout 文件可能很大，且常见需求是访问尾部。

### 2.4 两个目录常量（E3）

`rollout/src/lib.rs:25-26`：

```rust
pub const SESSIONS_SUBDIR: &str = "sessions";
pub const ARCHIVED_SESSIONS_SUBDIR: &str = "archived_sessions";
```

> 第一版在「未覆盖」表里把「归档后数据的实际去向」列为 E1 未知。**答案就在这两行**：归档的会话进 `$CODEX_HOME/archived_sessions/`，与 `sessions/` 平级。

同文件还定义了 `INTERACTIVE_SESSION_SOURCES`（`SessionSource::Cli` / `VSCode` / `Custom("atlas")` / `Custom("chatgpt")` 等），用于区分「交互式会话」与其他来源——列举与搜索会用到这个集合。

---

## 3. thread-store：线程管理（E1 结构）

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

## 4. state：SQLite 运行时状态（E1 结构 / E3 迁移器）

`codex-rs/state/src/`：

| 文件 | 职责 |
| ---- | ---- |
| `sqlite.rs` | SQLite 接入 |
| `migrations.rs` + `migrations_tests.rs` | **数据库迁移**，见下 |
| `log_db.rs` + `log_db_filter_tests.rs` | 日志库与过滤 |
| `audit.rs` | 审计 |
| `telemetry.rs` | 遥测 |
| `paths.rs` | 路径 |
| `extract.rs` | 提取 |
| `model/`、`runtime.rs` + `runtime/` | 模型与运行时 |

### 4.1 不是一个库，是 5 个（E3）

> 第一版只写了「`sqlx::migrate!`」单数，容易误以为只有一套 schema。

`state/src/migrations.rs:6-10`：

```rust
pub(crate) static STATE_MIGRATOR:          Migrator = sqlx::migrate!("./migrations");
pub(crate) static LOGS_MIGRATOR:           Migrator = sqlx::migrate!("./logs_migrations");
pub(crate) static GOALS_MIGRATOR:          Migrator = sqlx::migrate!("./goals_migrations");
pub(crate) static MEMORIES_MIGRATOR:       Migrator = sqlx::migrate!("./memory_migrations");
pub(crate) static THREAD_HISTORY_MIGRATOR: Migrator = sqlx::migrate!("./thread_history_migrations");
```

| 迁移器 | 迁移目录 | 覆盖内容 |
| ---- | ---- | ---- |
| `STATE_MIGRATOR` | `migrations/` | 主状态库 |
| `LOGS_MIGRATOR` | `logs_migrations/` | 日志（`just log` 读的就是它） |
| `GOALS_MIGRATOR` | `goals_migrations/` | 目标 |
| `MEMORIES_MIGRATOR` | `memory_migrations/` | 记忆 |
| `THREAD_HISTORY_MIGRATOR` | `thread_history_migrations/` | 线程历史 |

**这意味着新增一个 `.sql` 迁移文件时要先想清楚放进哪个目录**——五个目录互不相干，各自有独立的版本序列。

### 4.2 版本前向兼容策略（E3）

`migrations.rs:12-25` 的 `runtime_migrator` 有一段值得注意的设计：

> "Allow an older Codex binary to open a database that has already been migrated by a newer binary running in parallel. We intentionally **ignore applied migration versions that are newer than the embedded migration set**. Known migration versions are still validated by checksum, so this only relaxes the 'database is ahead of me' case."

即**旧二进制可以打开被新二进制迁移过的库**（多版本并存场景，比如同时装了 stable 与 nightly）。但已知版本仍要过 checksum 校验——**不能原地改历史迁移文件**。

### 查看日志

```bash
just log        # 实时查看 state SQLite 中的日志（LOGS_MIGRATOR 那一套）
```

底层是 `cargo run -p codex-cli --bin logs_client`。

> [!WARNING]
> **迁移与 Bazel 的交互**：AGENTS.md 顶部规则列表（grep `Bazel does not automatically make source-tree files available`）特别点名了 `sqlx::migrate!`——这类编译期读取目录的宏必须在 `BUILD.bazel` 配置 `compile_data`（或 `build_script_data` / test data），否则 Cargo 过而 Bazel 挂。**5 个迁移目录都要覆盖到。**

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
> **「从既有 rollout 恢复会话」是 `AGENTS.md` `### Breaking changes` 一节明确点名的高风险改动面**（grep `resuming sessions from existing rollouts`），与 app-server API、`rawResponseItem/*` 事件、CLI 参数、配置加载并列。
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

> 引用约定：`AGENTS.md` 的行号会漂移，下表一律按**标题 + 可 grep 的关键词**定位。

| 事项 | 依据 |
| ---- | ---- |
| **rollout 恢复是高风险改动面** | `AGENTS.md` `### Breaking changes`，grep `resuming sessions from existing rollouts` |
| 改了 `sqlx::migrate!` 相关代码要补 `BUILD.bazel` 的 `compile_data`（**5 个迁移目录**） | `AGENTS.md` 顶部规则列表，grep `Bazel does not automatically make source-tree files available` |
| 存储写入路径需考虑多进程并发（存在显式写锁） | `thread-store/src/local/writer_lock.rs` |
| 改智能体逻辑必须补集成测试 | AGENTS.md `### Test authoring guidance` |
| 落盘格式变更会影响既有用户的历史会话，需考虑兼容 | `.jsonl` 是持久化契约。默认路径下只有明文一种形态；但一旦用户开过 `local_thread_store_compression`，目录里就会同时存在 `.jsonl` 与 `.jsonl.zst`，**读路径应统一走 `open_rollout_line_reader`** |
| 不能原地修改已发布的迁移文件（checksum 校验） | `state/src/migrations.rs:12-25` |
| 改了 `Cargo.toml` / `Cargo.lock` 要跑 `just bazel-lock-update` | `AGENTS.md` 顶部规则列表，grep `just bazel-lock-update` |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `.jsonl` 每行事件的具体结构 | E1 | `rollout/src/recorder.rs`、按 §2.1 的 `find` 命令取一个真实文件再 `jq` |
| 5 个 SQLite 库的表结构与迁移历史 | E1 | `state/src/migrations/`、`logs_migrations/`、`goals_migrations/`、`memory_migrations/`、`thread_history_migrations/` |
| rollout 写 SQLite 元数据的完整字段 | E1 | `rollout/src/state_db.rs`（`ThreadMetadataBuilder` 的调用点） |
| 线程历史的物化（materialization）机制 | E1 | `thread-store/src/local/thread_history_materialization.rs` |
| 写锁的粒度与超时 | E1 | `thread-store/src/local/writer_lock.rs` |
| 会话搜索的索引方式 | E1 | `rollout/src/search.rs`、`session_index.rs` |
| `codex-rollout-trace` 的回放机制 | E1 | 该 crate + `codex debug trace-reduce` |
| `archive_thread.rs` 迁移文件的具体步骤 | E1 | `thread-store/src/local/archive_thread.rs` |

> **已从本表移除的两项**（第一版列为未知，本次已在正文给出 E3 结论）：
> - 「rollout 压缩的触发条件」→ 见 §2.2，**先是特性开关 `local_thread_store_compression`（默认关闭），开启后阈值才是 `MIN_ROLLOUT_AGE = 7 天`**
> - 「归档后数据的实际去向」→ 见 §2.4，目标目录是 `$CODEX_HOME/archived_sessions/`

---

## 9. 相关文档

- [智能体核心循环](./core_agent_loop.md) — 会话与 turn 的内存态
- [app-server 协议](./app_server_protocol.md) §3 — `thread/*` 方法族
- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 落盘内容
- [测试指南](./testing_guide.md) — `fork_thread.rs`、`compact_resume_fork.rs`
- [构建与发布](./build_and_release.md) — `compile_data` 陷阱
