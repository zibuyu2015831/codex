---
title: Codex 会话与持久化
summary: 描述 rollout 的 jsonl 落盘格式、YYYY/MM/DD 分层目录与文件命名规则、写入用本地时区而解析用 UTC 的时区不一致、默认关闭的 zstd 压缩特性开关及其完整触发链（两道门禁、一次性 spawn、6 小时运行锁、5 道逐文件跳过判定）、jsonl 为事实源而 SQLite 为可重建派生索引的自愈机制、thread-store 的操作面与跨进程写锁、state crate 的 5 个 SQLite 迁移器与 55 个迁移文件、扁平归档目录，以及会话恢复与两种 fork 持久化策略这一高风险改动面的注意事项。
keywords: codex | session | rollout | thread-store | sqlite | jsonl | zstd | archived-sessions | persistence | fork | writer-lock | backfill
scope: codex-rs/rollout、thread-store、state 与会话恢复相关实现
related_files: codex-rs/rollout/src/recorder.rs | codex-rs/rollout/src/lib.rs | codex-rs/rollout/src/compression.rs | codex-rs/rollout/src/state_db.rs | codex-rs/rollout/src/metadata.rs | codex-rs/rollout/src/session_index.rs | codex-rs/rollout/Cargo.toml | codex-rs/thread-store/Cargo.toml | codex-rs/thread-store/src/local | codex-rs/thread-store/src/local/writer_lock.rs | codex-rs/thread-store/src/local/archive_thread.rs | codex-rs/state/src/migrations.rs | codex-rs/state/src/sqlite.rs | codex-rs/utils/home-dir/src/lib.rs | AGENTS.md
dependencies: dev_docs/core_agent_loop.md | dev_docs/architecture_overview.md
verified_at: 2026-08-05
---

# 会话与持久化

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 落盘路径、命名规则、压缩触发链、迁移器清单、写锁语义、恢复链路均为 E3（源码）；模块结构与目录清单为 E1

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
| **thread-store** | `codex-thread-store` | 20,404 | **无独立数据载体**：数据全部借 `codex-rollout`（jsonl）与 `codex-state`（SQLite），自身直接依赖 `sqlx`；但自己会落一个锁目录 `$CODEX_HOME/thread-writer-locks/`，见 §3.2 | 线程元数据、分组、归档状态的操作面 |
| **state** | `codex-state` | 19,744 | **SQLite**（5 个独立库，见 §4；默认落在 `$CODEX_HOME/`，可被 `sqlite_home` 配置键或 `CODEX_SQLITE_HOME` 环境变量挪走） | 运行时状态、日志、目标、记忆、线程历史、审计 |

> [!NOTE]
> **更正说明**：第一版的「载体」列写成 rollout=「`.jsonl` 文件」、thread-store=「本地文件 + 索引」，两者都不准确。依据（E2，两个 crate 的 `Cargo.toml` `[dependencies]` 段）：<!-- ref-exempt: Cargo.toml 泛指下方两个 crate 的清单 -->
>
> ```
> rollout      → codex-state, zstd, ...            # 既写 jsonl，也写 SQLite，还做压缩
> thread-store → codex-rollout, codex-state, sqlx  # 数据不自己发明，全部借下层
> ```
>
> `codex-rs/rollout/src/state_db.rs` 直接 `use codex_state::SqliteConfig / ThreadMetadataBuilder / LogEntry`——**rollout 在写 jsonl 的同时也在往 SQLite 写线程元数据**。所以「rollout = 纯文件、state = 纯数据库」这个二分是错的。

另有 `codex-rollout-trace`（13,257 行）负责 rollout 的追踪与回放（`codex debug trace-reduce`），`codex-message-history`（1,437 行）负责消息历史。

---

## 2. rollout：会话的事实记录（E3）

### 2.1 落盘路径：`sessions/YYYY/MM/DD/`，不是 `sessions/`

> [!CAUTION]
> **本文第一版把目录写成了 `$CODEX_HOME/sessions/`——少了三层日期目录。** 按第一版给的命令 `ls ~/.codex/sessions/rollout-*.jsonl` **一个文件都匹配不到**。
>
> 错误来源可以确认：第一版直接抄了 `codex-rs/rollout/src/recorder.rs:81-82` 的**文档注释示例**，而那段注释本身是过时的（它写的是 `~/.codex/sessions/rollout-2025-05-07T17-24-21-<uuid>.jsonl`）。**真实路径由代码决定，不由注释决定。**

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
| 目录 | **`$CODEX_HOME/sessions/YYYY/MM/DD/`**（默认 `~/.codex/sessions/2026/08/03/`）。日期取自 `OffsetDateTime::now_local()`——**本地时区，不是 UTC**；MM/DD 补零两位，年份不补零 |
| 前缀 | `rollout-` |
| 日期 | 形如 `2025-05-07T17-24-21`（`format_description!` 定义，冒号替换为连字符，可安全用作文件名） |
| 会话 ID | UUID |
| 扩展名 | `.jsonl`（每行一个 JSON 事件）。**默认就是这个形态**；只有显式开启压缩特性后，冷文件才可能变成 `.jsonl.zst`，见 §2.2 |

> [!WARNING]
> **写入与解析的时区不一致（E3，改动此处务必先读）**
>
> | 侧 | 代码 | 时区 |
> | ---- | ---- | ---- |
> | 文件名/目录生成 | `codex-rs/rollout/src/recorder.rs:1554` `OffsetDateTime::now_local()` | **本地时区** |
> | 文件名反向解析 | `codex-rs/rollout/src/list.rs:981` `PrimitiveDateTime::parse(..).assume_utc()` | **UTC** |
> | 每行 `timestamp` 字段 | `codex-rs/rollout/src/recorder.rs:1908-1913` `OffsetDateTime::now_utc()` | UTC |
>
> 非 UTC 时区下，按文件名排序与游标分页会带上本地偏移量的系统性偏差。**单独"修正"任何一侧都会破坏既有文件的排序、分页游标或反归档路径重建三者之一**——三处是耦合的。

---

### 2.1.1 一次会话还会落下这些（E3）

除 rollout 本身，默认配置下同一个 `$CODEX_HOME` 还会出现：

| 产物 | 路径 | 来源 |
| ---- | ---- | ---- |
| 线程名索引 | `$CODEX_HOME/session_index.jsonl` | `codex-rs/rollout/src/session_index.rs:19` |
| 全局消息历史 | `$CODEX_HOME/history.jsonl` | `codex-rs/message-history/src/lib.rs:52` |
| 写者锁目录 | `$CODEX_HOME/thread-writer-locks/` | `codex-rs/thread-store/src/local/writer_lock.rs:17-18` |
| 压缩运行标记 | `$CODEX_HOME/.tmp/rollout-compression.lock` | `codex-rs/rollout/src/compression.rs:262` |
| 5 个 SQLite 库 | `$SQLITE_HOME/*.sqlite`（默认即 `$CODEX_HOME`） | `codex-rs/state/src/sqlite.rs:29-33` |

> [!CAUTION]
> **两个 append-only jsonl 的并发策略不一致。** `history.jsonl` 有跨进程文件锁（`try_lock` + 10 次重试，`codex-rs/message-history/src/lib.rs:160-179`）；`session_index.jsonl` **只有进程内 `Mutex`**（`codex-rs/rollout/src/session_index.rs:20` 的 `LazyLock<Mutex<()>>`）。后者的 `remove_thread_name_entries` 是「读全文 → 写临时文件 → rename」，同一个 `CODEX_HOME` 下多进程并发重命名/删除线程会丢条目。改这块时应向 `history.jsonl` 的模式对齐。

`SESSIONS_SUBDIR` 常量在 `codex-rs/rollout/src/lib.rs:25`。`codex-rs/rollout/src/recorder_tests.rs`、`codex-rs/rollout/src/tests.rs`、`codex-rs/rollout/src/compression_tests.rs`、`codex-rs/rollout/src/rollout_reference_index_tests.rs` 中的断言路径形如 `sessions/2025/01/03/rollout-<ts>-<uuid>.jsonl`，可作交叉验证。

**能用的查找命令**：

```bash
# 找最近的 rollout（注意用 -path 递归，别指望顶层通配）
find ~/.codex/sessions -name 'rollout-*.jsonl*' -type f | sort | tail -5
```

#### `$CODEX_HOME` 的解析规则（E3）

`codex-rs/utils/home-dir/src/lib.rs:13-63` 的 `find_codex_home()`：

| 情形 | 行为 |
| ---- | ---- |
| `CODEX_HOME` 未设或为空 | 回落到 `dirs::home_dir()/.codex`，**不校验该目录是否存在** |
| `CODEX_HOME` 非空 | 覆盖默认值，但**要求该路径已存在且是目录**，否则直接返回 `Err`；命中后会 `canonicalize()` |

全平台走同一套逻辑，平台差异只来自 `dirs::home_dir()` 的取值。

> [!NOTE]
> **SQLite 侧可以和 rollout 分家。** 5 个 `.sqlite` 默认与 rollout 同处 `$CODEX_HOME/`，但配置键 `sqlite_home` 或环境变量 `CODEX_SQLITE_HOME` 能把它们整体挪走（配置优先于环境变量）。此时 jsonl 与 SQLite 元数据**分处两个目录**，排查落盘问题时要分别去看。见 `codex-rs/core/src/config/mod.rs:3892-3897` 与 `codex-rs/state/src/sqlite.rs:90-141`。

### 2.2 zstd 压缩存在，但挂在一个默认关闭的特性开关后面

> [!CAUTION]
> **这一节记录了一次矫枉过正。**
>
> - 第一版说 rollout「是纯文本、逐行 JSON，不需要任何工具支持」。
> - 第二版看到 `codex-rs/rollout/src/compression.rs` 里那套完整的 zstd 工作器，就断言「压缩不是可选功能」、「7 天后必然变成 `.jsonl.zst`」。
> - **第二版错了。** 压缩工作器只有一个生产调用点，而那个调用点被特性开关包着，开关默认关闭。**在默认配置下，rollout 就是纯 `.jsonl`，第一版的结论在默认口径上是对的。**
>
> 教训：看到一个功能完整的模块，不等于它在默认路径上被启用了。**要顺着调用链找到唯一的生产调用点，再看它的门禁条件。**

#### 唯一的生产调用点及其门禁（E3）

`codex-rs/core/src/thread_manager.rs:317-324`。注意**有两道门禁**，不是一道：

```rust
match &config.experimental_thread_store {
    ThreadStoreConfig::Local => {                      // 门禁一：存储形态必须是 Local
        if config
            .features
            .enabled(Feature::LocalThreadStoreCompression)  // 门禁二：特性开关
        {
            codex_rollout::spawn_rollout_compression_worker(config.codex_home.to_path_buf());
        }
```

`ThreadStoreConfig::Local` 带 `#[default]`（`codex-rs/core/src/config/mod.rs:600-603`），所以门禁一默认满足；但把 `experimental_thread_store` 设为 `InMemory` 时同样不会 spawn。

该开关的注册项在 `codex-rs/features/src/lib.rs:990-995`：

```rust
FeatureSpec {
    id: Feature::LocalThreadStoreCompression,
    key: "local_thread_store_compression",
    stage: Stage::UnderDevelopment,
    default_enabled: false,
},
```

可自行复核（E3，源码检索）：

```bash
# 生产调用点只有一处（另两处命中是定义与 re-export）
grep -rn spawn_rollout_compression_worker codex-rs/ --include='*.rs'
# codex-rs/core/src/thread_manager.rs:323      ← 唯一生产调用点
# codex-rs/rollout/src/compression.rs:29       ← 定义
# codex-rs/rollout/src/lib.rs:41               ← re-export
```

**结论**：`Stage::UnderDevelopment` + `default_enabled: false` ⇒ 除非用户在 config 里显式打开 `local_thread_store_compression`，压缩工作器根本不会被 spawn。开关的判定路径没有任何灰度旁路：`Features::with_defaults()`（`codex-rs/features/src/lib.rs:382-393`）只把 `default_enabled` 为真的 spec 收进集合，`enabled()` 就是对该集合的查表，`Stage` 不参与运行时判定。

#### 开关打开之后，机器本身是这样的（E3）

下表的常量与函数都真实存在且如实描述——**它们只是不在默认路径上跑**：

| 事实 | 位置 |
| ---- | ---- |
| 压缩后缀 `.zst` | `codex-rs/rollout/src/compression.rs:18` `const COMPRESSED_SUFFIX: &str = ".zst"` |
| **mtime 距今 ≥ 7 天的 rollout 才压缩** | `:258` `const MIN_ROLLOUT_AGE: Duration = Duration::from_secs(7 * 24 * 60 * 60)`，判定在 `:716` `if age < MIN_ROLLOUT_AGE { ... }` |
| 压缩算法与级别 | `:732` `fn encode_zstd_to_writer(...)`，`:257` `const COMPRESSION_LEVEL: i32 = 3` |
| 写入用临时文件再改名 | `:649` `encode_zstd_to_writer(path, temp_file.as_file_mut())`，`TEMP_SUFFIX = ".tmp"`；改名前后各做一次 `same_file_state` 复核，变了就回滚 |
| 有跨进程运行锁与陈旧清理 | `RUN_MARKER_FILE_NAME = "rollout-compression.lock"`（落在 `$CODEX_HOME/.tmp/`）、`RUN_MARKER_STALE_AFTER = 6h`、`WORKER_MAX_RUNTIME = 5h` |
| 扫描范围 | `sessions/` **与** `archived_sessions/` 两个根（`:380-388`、`:760`） |
| 依赖 | `codex-rs/rollout/Cargo.toml` 的 `zstd = { workspace = true }` |

> [!WARNING]
> **开关打开 ≠ 7 天后必然被压缩。** 7 天只是逐文件条件之一，完整链路是：
>
> 1. `experimental_thread_store` 为 `Local` **且** 特性开关已开；
> 2. worker 在**本地 thread store 构造时一次性 spawn**——它不是定时任务，进程不重启就不会再跑第二轮；
> 3. 需成功领取 `$CODEX_HOME/.tmp/rollout-compression.lock`（`create_new`）。锁已存在且未满 6h 则**整轮跳过**，即每个 `CODEX_HOME` 6 小时内至多跑一轮；
> 4. 单轮受 `WORKER_MAX_RUNTIME = 5h` 截断，没扫完就停；
> 5. 逐文件还要过 5 道跳过判定：已是 `.zst`、meta 行不可读（`skipped_unreadable_meta`）、**被 `RolloutReferenceIndex` 引用**（`skipped_referenced`）、**`SessionMeta.history_base` 非空即 fork 指针**（`skipped_fork_pointer`）、目标 `.zst` 已存在。
>
> 所以一个 7 天前的 rollout 完全可能永远不被压缩。判定代码见 `codex-rs/rollout/src/compression.rs` 的 `worker::run`（`:348-408`）与 `compress_rollouts_in_root`（`:424-513`）。
>
> 第 5 条里的两项跳过把本节与 §3.2 ②（rollout 血缘）、§5（fork）串成了一条线：**压缩会主动避开与 fork 血缘相关的 rollout**。

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
> 代码侧不必自己判断形态，但**统一两种形态的不是反向扫描器**：`codex-rs/rollout/src/reverse_jsonl_scanner.rs` 里没有任何 `.zst` / `COMPRESSED_SUFFIX` 的引用，它的签名是 `ReverseJsonlScanner<R: Read + Seek>`（`:20`、`:30`），而 zstd 流本身不可 seek。真正屏蔽差异的入口是 `open_rollout_line_reader`（定义在 `codex-rs/rollout/src/compression.rs:47`，从 `codex-rs/rollout/src/lib.rs:37-41` 连同 `RolloutLineReader` / `existing_rollout_path` / `plain_rollout_path` 一起 re-export），它按路径选择 `RolloutLineReaderInner::Plain` 或阻塞式 zstd 解码分支。路径名层面的后缀剥离则在 `codex-rs/rollout/src/compression.rs:960` 的 `strip_suffix(COMPRESSED_SUFFIX)`。

### 2.3 模块版图（E1）

| 文件 | 职责 |
| ---- | ---- |
| `codex-rs/rollout/src/recorder.rs` | 写入 |
| `codex-rs/rollout/src/reverse_jsonl_scanner.rs` | **反向扫描 jsonl**（`ReverseJsonlScanner<R: Read + Seek>`、`ScanOutcome`，`codex-rs/rollout/src/lib.rs:82-83`）。**只处理可 seek 的明文流，不认识 `.zst`** |
| `codex-rs/rollout/src/compression.rs` | **zstd 压缩工作器**（7 天阈值、运行锁、原子改名）+ 统一读取入口 `open_rollout_line_reader`。压缩侧默认不启用，见 §2.2 |
| `codex-rs/rollout/src/metadata.rs` | 元数据；并含启动时的 SQLite backfill（见 §4.3） |
| `codex-rs/rollout/src/list.rs` / `codex-rs/rollout/src/search.rs` | 列举与搜索 |
| `codex-rs/rollout/src/session_index.rs` | 会话索引 |
| `codex-rs/rollout/src/rollout_reference_index.rs` | 引用索引 |
| `codex-rs/rollout/src/state_db.rs` / `codex-rs/rollout/src/sqlite_metrics.rs` | **SQLite 侧**：`codex-rs/rollout/src/state_db.rs` 借 `codex-state` 写线程元数据（`ThreadMetadataBuilder`、`SqliteConfig`），并重导出 `LogEntry` |
| `codex-rs/rollout/src/ordinal.rs` | 序号 |
| `codex-rs/rollout/src/policy.rs` / `codex-rs/rollout/src/config.rs` | 策略与配置 |
| `codex-rs/rollout/src/model_context.rs` | 模型上下文（注意与 `codex-rs/thread-store/src/local/model_context.rs` 同名不同物） |
| `codex-rs/rollout/src/persistence_metrics.rs` | 持久化指标 |

> **反向扫描器的存在很有信息量**：要"读最近 N 条"而不加载整个文件，就需要从文件尾部往前扫。这说明 rollout 文件可能很大，且常见需求是访问尾部。

### 2.4 两个目录常量（E3）

`codex-rs/rollout/src/lib.rs:25-26`：

```rust
pub const SESSIONS_SUBDIR: &str = "sessions";
pub const ARCHIVED_SESSIONS_SUBDIR: &str = "archived_sessions";
```

> 第一版在「未覆盖」表里把「归档后数据的实际去向」列为 E1 未知。**答案就在这两行**：归档的会话进 `$CODEX_HOME/archived_sessions/`，与 `sessions/` 平级。

同文件（`codex-rs/rollout/src/lib.rs:27-34`）还定义了 `INTERACTIVE_SESSION_SOURCES`，用于区分「交互式会话」与其他来源——列举与搜索会用到这个集合。该集合是 `vec![]` 字面量穷举，**恰好 4 个来源**：`SessionSource::Cli`、`VSCode`、`Custom("atlas")`、`Custom("chatgpt")`。

---

## 3. thread-store：线程管理（E1 结构 / E3 机制）

### 3.1 操作面

`codex-rs/thread-store/src/local/` 下主要操作各占一个文件（该目录另有 `mod.rs`、`helpers.rs`、`test_support.rs` 与 7 个 `*_tests.rs`）：<!-- ref-exempt: 括号内是同目录下的辅助文件名枚举，路径已由句首给出 -->

| 操作 | 文件 |
| ---- | ---- |
| 创建 | `codex-rs/thread-store/src/local/create_thread.rs` |
| 读取 | `codex-rs/thread-store/src/local/read_thread.rs` |
| 列举 | `codex-rs/thread-store/src/local/list_threads.rs` |
| 搜索 | `codex-rs/thread-store/src/local/search_threads.rs` |
| 删除 | `codex-rs/thread-store/src/local/delete_thread.rs` |
| 归档 / 取消归档 | `codex-rs/thread-store/src/local/archive_thread.rs` / `codex-rs/thread-store/src/local/unarchive_thread.rs` |
| 更新元数据 | `codex-rs/thread-store/src/local/update_thread_metadata.rs` |
| 分组移动 | `codex-rs/thread-store/src/local/move_thread_to_section.rs` |
| **分页 fork** | `codex-rs/thread-store/src/local/paginated_fork.rs` |
| 历史 | `codex-rs/thread-store/src/local/thread_history.rs` + `codex-rs/thread-store/src/local/thread_history/` + `codex-rs/thread-store/src/local/thread_history_materialization.rs` |
| 分组 | `codex-rs/thread-store/src/local/thread_sections.rs`（⚠️ 该 crate 内 `codex-rs/thread-store/src/thread_sections.rs` 与 `codex-rs/thread-store/src/local/thread_sections.rs` **同时存在**，勿混） |
| **rollout 血缘** | `codex-rs/thread-store/src/local/rollout_lineage.rs` |
| **写锁** | `codex-rs/thread-store/src/local/writer_lock.rs` |
| 实时写入 | `codex-rs/thread-store/src/local/live_writer.rs` |
| 模型上下文 | `codex-rs/thread-store/src/local/model_context.rs` |

这套操作面覆盖了 app-server 协议 `thread/*`（共 57 个方法）中的**持久化子集**，并非一一对应：协议侧的 `thread/realtime/*`（11 个）、`thread/goal/*`（5 个）、`thread/backgroundTerminals/*`（3 个）等运行时方法族在 thread-store 没有对应文件；反向地，`codex-rs/thread-store/src/local/thread_history_materialization.rs`、`codex-rs/thread-store/src/local/rollout_lineage.rs`、`codex-rs/thread-store/src/local/writer_lock.rs`、`codex-rs/thread-store/src/local/live_writer.rs` 也没有对应的协议方法。部分映射见 §6，完整方法表见 [`app_server_protocol.md`](./app_server_protocol.md) §3。

### 3.2 两个值得注意的机制

> [!IMPORTANT]
> **① 写锁（`codex-rs/thread-store/src/local/writer_lock.rs` + `codex-rs/thread-store/src/local/writer_lock_tests.rs`，E3）**
>
> 这是**真正的跨进程 OS 建议锁**，不是进程内 `Mutex`——`codex-rs/thread-store/src/local/writer_lock.rs:38-84` 的 `acquire` 用的是 `File::try_lock()`。落盘位置在 `$CODEX_HOME/thread-writer-locks/`：每个线程一把 `<thread_id>.lock`，外加一把全局 `.coordination.lock`（`codex-rs/thread-store/src/local/writer_lock.rs:17-18`）。
>
> | 性质 | 实际行为 |
> | ---- | ---- |
> | 粒度 | 每线程一把 |
> | 获取方式 | `try_lock()` **非阻塞**；拿不到直接返回 `ThreadStoreError::Conflict`，**无超时、无重试** |
> | 协调锁 | 取线程锁前先拿 `.coordination.lock`，这把是**阻塞** `lock()`，并顺带做一次陈旧锁清理（`:86-113`） |
> | 生产调用点 | `LocalThreadStore::acquire_writer_locks`（`codex-rs/thread-store/src/local/mod.rs:267-276`），被 `delete_thread.rs:38,87` 与 `codex-rs/thread-store/src/local/archive_thread.rs:38` 调用 |
>
> TUI、app-server、exec 走的是同一套本地存储，任意两者并存即可能争锁。改动写入路径时必须考虑这一点。

> [!IMPORTANT]
> **② rollout 血缘（`codex-rs/thread-store/src/local/rollout_lineage.rs`）**
> `codex fork` 会从既有会话派生新会话，两者之间存在**血缘关系**。这解释了为什么有 `codex-rs/thread-store/src/local/paginated_fork.rs`——fork 一个长会话需要分页处理。

### 3.3 其他组成

| 文件 | 说明 |
| ---- | ---- |
| `codex-rs/thread-store/src/in_memory.rs` | 内存实现（测试用途） |
| `codex-rs/thread-store/src/store.rs` | 存储抽象 |
| `codex-rs/thread-store/src/live_thread.rs` | 活跃线程 |
| `codex-rs/thread-store/src/thread_metadata_sync.rs` | 元数据同步 |
| `codex-rs/thread-store/src/types.rs` / `codex-rs/thread-store/src/error.rs` | 类型与错误 |

### 3.4 归档做了什么（E3）

归档与 SQL migration 无关，是一次文件搬迁加一次元数据更新。`codex-rs/thread-store/src/local/archive_thread.rs` 的 `archive_thread`：

1. `find_thread_path_by_id_str` 定位 rollout 文件；
2. `scoped_rollout_path` 校验它确实位于 `sessions/` 子树内（防越界）；
3. `std::fs::rename` 把该文件从 `sessions/YYYY/MM/DD/` 搬到 **`$CODEX_HOME/archived_sessions/<原文件名>`**——注意归档区是**扁平的**，不保留日期分层；
4. `ctx.mark_archived(thread_id, archived_path, now)` 更新 SQLite。

扁平性的旁证：列举归档会话走 `ThreadListLayout::Flat`，而列举 `sessions/` 走日期分层路径（`codex-rs/rollout/src/recorder.rs:1359-1372`）。

**触发条件只有显式用户动作**（`codex archive` / `codex delete` / app-server 的 `thread/archive`），**没有**任何时间或容量阈值。

---

## 4. state：SQLite 运行时状态（E1 结构 / E3 迁移器）

`codex-rs/state/src/`：

| 文件 | 职责 |
| ---- | ---- |
| `codex-rs/state/src/sqlite.rs` | SQLite 接入 |
| `codex-rs/state/src/migrations.rs` + `codex-rs/state/src/migrations_tests.rs` | **数据库迁移**，见下 |
| `codex-rs/state/src/log_db.rs` + `codex-rs/state/src/log_db_filter_tests.rs` | 日志库与过滤 |
| `codex-rs/state/src/audit.rs` | 审计 |
| `codex-rs/state/src/telemetry.rs` | 遥测 |
| `codex-rs/state/src/paths.rs` | **仅 9 行**，只有一个 `file_modified_time_utc()` 文件 mtime 辅助函数。**不是路径解析**——DB 路径解析在 `codex-rs/state/src/sqlite.rs` 的 `SqliteConfig::state_db_path()` 等方法 |
| `codex-rs/state/src/extract.rs` | 提取 |
| `codex-rs/state/src/model/`、`codex-rs/state/src/runtime.rs` + `codex-rs/state/src/runtime/` | 模型与运行时 |

### 4.1 不是一个库，是 5 个（E3）

> 第一版只写了「`sqlx::migrate!`」单数，容易误以为只有一套 schema。

`codex-rs/state/src/migrations.rs:6-10`：

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

`codex-rs/state/src/migrations.rs:12-25` 的 `runtime_migrator` 有一段值得注意的设计：

> "Allow an older Codex binary to open a database that has already been migrated by a newer binary running in parallel. We intentionally **ignore applied migration versions that are newer than the embedded migration set**. Known migration versions are still validated by checksum, so this only relaxes the 'database is ahead of me' case."

即**旧二进制可以打开被新二进制迁移过的库**（多版本并存场景，比如同时装了 stable 与 nightly）。但已知版本仍要过 checksum 校验——**不能原地改历史迁移文件**。

### 4.3 jsonl 与 SQLite 的一致性：jsonl 是事实源，SQLite 是可重建的派生索引（E3）

这是本区域最容易改坏的一点。二者**不是**每条 rollout item 同步双写，而是「jsonl 权威 + SQLite 自愈」：

| 同步路径 | 时机 | 位置 |
| ---- | ---- | ---- |
| **启动 backfill** | 进程启动，全量扫 `sessions/` 与 `archived_sessions/`，按 watermark 增量 upsert；`init()` 前有 `wait_for_backfill_gate` 挡着（超时 30s） | `codex-rs/rollout/src/metadata.rs:200-305` |
| **惰性 read-repair** | 列举/读取时发现元数据对不上就地修复 | `codex-rs/rollout/src/state_db.rs` 的 `reconcile_rollout` / `read_repair_rollout_path`（调用点 `codex-rs/rollout/src/recorder.rs:552,563,592,632`） |
| **live 写入同步** | 仅当 `rollout_path` 发生变化时 upsert | `codex-rs/thread-store/src/local/live_writer.rs:210-243` |

推论：**删掉 SQLite 库不会丢会话数据**（会被 backfill 重建），但删掉 jsonl 就真的丢了。

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
| 会话重建 | `codex-rs/core/src/session/rollout_reconstruction.rs`（+ 测试） |
| rollout 血缘 | `codex-rs/thread-store/src/local/rollout_lineage.rs` |
| 分页 fork | `codex-rs/thread-store/src/local/paginated_fork.rs` |
| 集成测试 | `codex-rs/core/tests/suite/fork_thread.rs`、`codex-rs/core/tests/suite/compact_resume_fork.rs` |

### 5.3 fork 有两种持久化策略，默认走的是「整份复制」（E3）

`codex-rs/core/src/session/mod.rs:412-418`：

```rust
pub(crate) enum ForkPersistence {
    Copied,
    Referenced { history_base: Option<HistoryPosition>, inherited_item_count: usize },
}
```

| 策略 | 做什么 | 何时启用 |
| ---- | ---- | ---- |
| **`Copied`（默认）** | 新线程有全新 `ThreadId` 与全新 rollout 文件，源历史**整份复制**进去，不写 `history_base` | `ThreadManager::fork_thread` / `fork_thread_from_history` 一律用它 |
| `Referenced` | 新 rollout 的 `SessionMeta.history_base` 指向父线程的 `HistoryPosition{ thread_id, end_ordinal_exclusive, end_byte_offset }`，**不复制历史字节** | 仅 `ThreadManager::fork_prepared_thread`，唯一调用方是 app-server 的 `thread/fork`，且**要求源线程 `history_mode == Paginated` 且存在 state DB** |

为什么默认是 `Copied`：`LocalThreadStore` **没有 override** `default_history_mode()`，回落到 `ThreadHistoryMode::Legacy`（`codex-rs/protocol/src/protocol.rs:701-702` 的 `#[default]`）；而 `StartThreadOptions.history_mode` 生产代码中从不被设为 `Some(Paginated)`（唯一例外是 subagent 继承父线程模式）。

> [!CAUTION]
> **`Referenced` fork 依赖父文件的绝对字节偏移，与压缩/追加天然冲突。** 现有防线是三重的：压缩跳过被引用的 rollout、压缩跳过带 `history_base` 的 rollout、`materialize_rollout_for_reference` 在血缘解析时强制解压成明文。**削弱其中任何一条都是静默数据损坏。** 另注意 `codex-rs/thread-store/src/local/thread_history_materialization.rs` 直接 `File::open(...).seek(start_offset)`，完全不走压缩 reader——投影链假定明文文件。
>
> 被引用的父线程受删除保护：`RolloutReferenceIndex` 计数大于 0 时拒绝删除（`codex-rs/thread-store/src/local/delete_thread.rs:35-37`）。

> [!CAUTION]
> **「从既有 rollout 恢复会话」是 `AGENTS.md` `### Breaking changes` 一节明确点名的高风险改动面**（grep `resuming sessions from existing rollouts`），与 app-server API、`rawResponseItem/*` 事件、CLI 参数、配置加载并列。
>
> 尤其注意 `codex-rs/core/tests/suite/compact_resume_fork.rs` 这个测试名——**上下文压缩、恢复、fork 三者交互**是最容易出问题的组合。

---

## 6. 与协议层的对应

下表是**部分映射**（E3），不是全集——协议侧 57 个 `thread/*` 方法中的运行时族在 thread-store 没有对应实现，见 §3.1 的说明。

| 存储侧 | 协议侧（`thread/*`，共 57 个方法） |
| ---- | ---- |
| `create_thread` / `read_thread` / `list_threads` | `thread/list`、`thread/loaded/list`、`thread/items/list` |
| `archive_thread` | `thread/archive`（请求）、`thread/archived`（完成通知） |
| `unarchive_thread` | `thread/unarchive`（请求）、`thread/unarchived`（完成通知） |
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
| 存储写入路径需考虑多进程并发（存在显式写锁） | `codex-rs/thread-store/src/local/writer_lock.rs` |
| 改智能体逻辑必须补集成测试 | AGENTS.md `### Test authoring guidance` |
| 落盘格式变更会影响既有用户的历史会话，需考虑兼容 | `.jsonl` 是持久化契约。默认路径下只有明文一种形态；但一旦用户开过 `local_thread_store_compression`，目录里就会同时存在 `.jsonl` 与 `.jsonl.zst`，**读路径应统一走 `open_rollout_line_reader`** |
| **写路径对 `.zst` 的处理与读路径不同** | 追加不走 `open_rollout_line_reader`：`open_log_file` 会先调 `materialize_rollout_for_append_blocking`（`codex-rs/rollout/src/compression.rs:66-80`）把 `.zst` **还原成明文 `.jsonl`** 再追加。见 `codex-rs/rollout/src/recorder.rs:1580-1582` |
| SQLite 可重建，jsonl 不可 | 见 §4.3。改动写入路径时，破坏 jsonl 是不可逆的，破坏 SQLite 会被 backfill 自愈 |
| 不能原地修改已发布的迁移文件（checksum 校验） | `codex-rs/state/src/migrations.rs:12-25` |
| 改了 Rust 依赖清单要跑 `just bazel-lock-update` <!-- ref-exempt: 转述 AGENTS.md 通用规则，泛指任意 crate 的清单与锁文件 --> | `AGENTS.md` 顶部规则列表，grep `just bazel-lock-update` |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| `.jsonl` 每行事件的具体结构 | E1 | `codex-rs/rollout/src/recorder.rs`、按 §2.1 的 `find` 命令取一个真实文件再 `jq` |
| 5 个 SQLite 库的表结构与迁移历史 | E1 | `codex-rs/state/migrations/`（46 个 `.sql`）、`codex-rs/state/logs_migrations/`（2）、`codex-rs/state/goals_migrations/`（2）、`codex-rs/state/memory_migrations/`（1）、`codex-rs/state/thread_history_migrations/`（4）。**注意这 5 个目录在 crate 根、与 `src/` 平级**，不在 `src/` 下面——`sqlx::migrate!("./migrations")` 的相对路径是相对 crate 根的 |
| rollout 写 SQLite 元数据的完整字段 | E1 | `codex-rs/rollout/src/state_db.rs`（`ThreadMetadataBuilder` 的调用点） |
| 线程历史的物化（materialization）机制 | E1 | `codex-rs/thread-store/src/local/thread_history_materialization.rs` |
| 写锁的粒度与超时 | E1 | `codex-rs/thread-store/src/local/writer_lock.rs` |
| 会话搜索的索引方式 | E1 | `codex-rs/rollout/src/search.rs`、`codex-rs/rollout/src/session_index.rs` |
| `codex-rollout-trace` 的回放机制 | E1 | 该 crate + `codex debug trace-reduce` |
| 线程历史物化后的数据结构 | E1 | `codex-rs/thread-store/src/local/thread_history_materialization.rs` |

> **已从本表移除的三项**（曾列为未知，现已在正文给出 E3 结论）：
> - 「rollout 压缩的触发条件」→ 见 §2.2。**先是两道门禁（`ThreadStoreConfig::Local` + 默认关闭的特性开关），开启后还有一次性 spawn、6h 运行锁、5h 单轮上限与 5 道逐文件跳过判定**，7 天只是其中一条
> - 「归档后数据的实际去向」→ 见 §2.4 与 §3.4，目标目录是 `$CODEX_HOME/archived_sessions/`，**扁平存放**，不保留日期分层
> - 「归档的具体步骤」→ 见 §3.4，是 `rename` + `mark_archived`，与 SQL migration 无关

---

## 9. 相关文档

- [智能体核心循环](./core_agent_loop.md) — 会话与 turn 的内存态
- [app-server 协议](./app_server_protocol.md) §3 — `thread/*` 方法族
- [架构总览](./architecture_overview.md) §7 — `CODEX_HOME` 落盘内容
- [测试指南](./testing_guide.md) — `codex-rs/core/tests/suite/fork_thread.rs`、`codex-rs/core/tests/suite/compact_resume_fork.rs`
- [构建与发布](./build_and_release.md) — `compile_data` 陷阱
