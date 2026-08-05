---
title: 32 Python 程序员读 codex 的 Rust 地图
summary: 面向熟悉 Python 但不熟悉 Rust 的读者，把散落在前面各篇的 Rust 小注收拢成一张对照表，覆盖读 codex 源码必须认识的十来个语法与惯用法（Arc 与引用计数、Option 与 Result 与问号、trait 与 impl、async fn in trait 的 Send 约束、self Arc Self、模块默认私有与 pub crate、non_exhaustive、include_str 编译期内嵌、channel 拆成两半的所有权动因），以及 codex 用机器强制的四条工程规约（禁止 crate features、禁止 unwrap 与 expect、禁止跨 await 持锁、禁用方法清单）及其对自建 Rust 项目的可迁移建议。
keywords: rust | python | arc | option | result | trait | async-trait | send | ownership | channel | non-exhaustive | clippy | workspace-lints | features-ban
scope: 读懂 codex 源码所需的 Rust 语法与该仓库机器强制的工程规约
related_files: codex-rs/Cargo.toml | codex-rs/clippy.toml | .github/scripts/verify_cargo_workspace_manifests.py | codex-rs/core/src/session/mod.rs | codex-rs/core/src/tasks/mod.rs | codex-rs/protocol/src/protocol.rs | codex-rs/core/src/context_manager/mod.rs
dependencies: 无（本目录文档自包含，不依赖 dev_docs 其余文档）
verified_at: 2026-08-05
---

# 32 Python 程序员读 codex 的 Rust 地图

> **前置**：无。可以在任何时候查阅
> **定位**：**这不是 Rust 教程**，是"读 codex 源码时会绊住你的那些东西"的对照表

---

## 0. 怎么用这一篇

前面各篇里散着十几处「Rust 小注」。这一篇把它们收拢，并补上前面没地方放的。

**建议用法**：读源码遇到看不懂的符号，回来查表；不要通读。

**一个总的心态**：

> **Rust 里绝大部分"多出来的东西"，都是在回答同一个问题："这块内存归谁，什么时候释放，谁能同时碰它。"**
>
> Python 有 GC 和 GIL 帮你回答了，所以你从来不用写。Rust 没有，所以要写出来。**看到陌生符号时先问"它在回答所有权问题吗"**，八成是。

---

## 1. 最高频的十个符号

| 你会看到 | Python 里的对应 | 一句话 |
| ---- | ---- | ---- |
| `Arc<T>` | 普通对象引用 | 引用计数指针，**可跨线程共享** |
| `Arc::clone(&x)` | `y = x` | **计数 +1，不复制数据**。看到 `clone` 别以为在深拷贝 |
| `Option<T>` | `Optional[T]` | 有值 / 没值。**强制你处理没值的情况** |
| `Result<T, E>` | 返回值 or 抛异常 | 成功 / 失败。**Rust 没有异常** |
| `?` | `raise` 向上冒泡 | "出错就提前返回这个错误" |
| `&x` / `&mut x` | 传引用（默认行为） | 借用 / 可变借用 |
| `impl Trait for Type` | `class Type(Trait):` | 给类型实现一个接口 |
| `match x { ... }` | `match` / `if-elif` 链 | **但它强制穷尽**，漏一个分支编译不过 |
| `mod foo;` | `import foo` | 但**默认私有**，见 §5 |
| `pub(crate)` | 无对应 | "只对本 crate 公开"，比 `pub` 收敛 |

### 再补四个：不是符号，但同样高频

| 你会看到 | 一句话 | Python 里 |
| ---- | ---- | ---- |
| **`panic`** | **程序遇到不该出现的状态，当场终止**（数组越界、`unwrap()` 到了空值）。**和 `Result` 不是一回事**——`Result` 是预期内的失败，`panic` 是 bug | 未捕获的异常把进程带走 |
| **`drop`** | **一个值的最后一个持有者消失，值被自动销毁**。时刻是确定的、可预测的 | 引用计数归零被回收（但时刻你管不着） |
| **`Send`** | 这个类型**可以被搬到另一个线程上去** | 无对应（有 GIL） |
| **`Sync`** | 这个类型**可以被多个线程同时读** | 无对应 |

> **`Send` / `Sync` 出现在哪**：`SessionTask: Send + Sync + 'static` 这类**约束列表**里（[04](./04-three-loops.md) §4），意思是"想实现这个 trait，你的类型必须先满足这几条"。`'static` 是第三条，表示"不借用任何有期限的外部数据，因此能活任意久"。
>
> **实际影响**：你在一个要被 `tokio::spawn` 的 future 里持有了非 `Send` 的东西跨越 `.await`，**编译报错，而且报错信息很长**。看到 "future is not `Send`" 就是撞上这个了。

---

## 2. `Arc`：满屏的 `Arc<Session>` 是什么

[02](./02-startup.md) §4 出现过：

```rust
let session_for_loop = Arc::clone(&session);
tokio::spawn(async move {
    submission_loop(session_for_loop, config, rx_sub).await;
});
```

**Python 里这段是隐形的**：

```python
task = asyncio.create_task(submission_loop(session, config, rx_sub))
#                                          ^^^^^^^ 直接用，引用计数 CPython 帮你加
```

Rust 要你显式写出"我要多一个指向它的指针"。

| 类型 | 含义 | 什么时候用 |
| ---- | ---- | ---- |
| `Rc<T>` | 引用计数，**单线程** | codex 里基本不用 |
| `Arc<T>` | 引用计数，**跨线程安全**（Atomic） | 到处都是 |
| `Arc<Mutex<T>>` | 共享 + 可变 | 需要多处改同一个东西 |

> **`Arc::clone` 很便宜**（一次原子加法），不要看到 `clone` 就担心性能。真正贵的是 `x.clone()` 在一个大结构体上。

### `Arc<Mutex<T>>` vs channel：codex 两个都用

这是自建项目要做的一个真实选择：

| 手法 | codex 用在哪 | 什么时候选它 |
| ---- | ---- | ---- |
| **channel** | 前端 ↔ 内核（[02](./02-startup.md) §5） | **跨边界**通信。想让边界在类型层面守住 |
| **`Arc<Mutex<T>>`** | `Session` 内部状态、`TurnDiffTracker` | **同一个组件内部**的共享可变状态 |

> **不要非此即彼。** 常见误区是"用了消息驱动就不能有共享状态"。codex 的做法是：**跨边界用消息，边界内部用共享状态**。

---

## 3. `Option` / `Result` / `?`：Rust 没有异常

### `Option<T>`：可能没有

[11](./11-model-client.md) §5 那个例子：

```rust
Completed { end_turn: Option<bool> }    // 三态：Some(true) / Some(false) / None
```

**Python 里最容易出的 bug 在这**：

```python
if end_turn:          # ❌ None 和 False 被混成一类了
    ...
if end_turn is True:  # ✅ 但你得记得这么写
    ...
```

Rust 强制你区分：

```rust
match end_turn {
    Some(true)  => { /* 模型明确说结束了 */ }
    Some(false) => { /* 模型明确说没结束 */ }
    None        => { /* 这个 provider 没告诉我们，走兜底逻辑 */ }
}
```

**漏掉 `None` 分支编译不过。**

### `Result<T, E>` 和 `?`

```rust
let step_context = sess.capture_step_context(...).await?;
//                                                     ^ 出错就直接 return 这个错误
```

约等于 Python：

```python
try:
    step_context = await sess.capture_step_context(...)
except Exception:
    raise            # 原样往上抛
```

区别是**Rust 在函数签名里就写明了会失败**（返回 `Result`），而 Python 的异常是不可见的。

> **这就是为什么 codex 到处是 `-> CodexResult<...>`。** 它是 `Result<T, CodexErr>` 的别名。

### `anyhow` vs `thiserror`

codex 两个都依赖。区别：

| crate | 用途 | Python 类比 |
| ---- | ---- | ---- |
| `thiserror` | **定义**结构化错误类型（库用） | 自定义 `Exception` 子类 |
| `anyhow` | **传播**任意错误，带上下文（应用用） | `raise ... from e` + 堆栈 |

> **给自建项目**：**库里用 `thiserror`（调用方要能 `match` 你的错误），应用入口用 `anyhow`（只需要打日志）。**
>
> [11](./11-model-client.md) §6 那个 `is_retryable()` 之所以能实现，就是因为错误是结构化的——`anyhow` 一把梭的话，你没法判断"这个错该不该重试"。

---

## 4. trait 与两个让人卡住的签名

### `trait` 就是接口

```rust
pub(crate) trait SessionTask: Send + Sync + 'static {
    fn kind(&self) -> TaskKind;
    fn run(self: Arc<Self>, ...) -> impl Future<Output = SessionTaskResult> + Send;
}
```

Python：

```python
class SessionTask(Protocol):
    def kind(self) -> TaskKind: ...
    async def run(self, ...) -> SessionTaskResult: ...
```

**但有两个 Rust 特有的东西**（[04](./04-three-loops.md) §4 提过）：

### ① `-> impl Future<...> + Send` 而不是 `async fn`

**为什么不直接写 `async fn run(...)`？**

因为 trait 里的 `async fn` **不保证返回的 Future 是 `Send`**，而这个任务要被 `tokio::spawn` 到多线程运行时上——**不是 `Send` 就 spawn 不了**。

手写成 `impl Future + Send` 就是为了**把这个约束写进契约**：谁实现这个 trait，谁就必须保证自己的 future 能跨线程。

> **`Send` 是什么**：一个类型能安全地在线程间转移。Python 里没有对应概念（GIL 让你不用想）。
>
> **实际影响**：如果你在 `run` 里持有一个非 `Send` 的东西跨越 `.await`，**编译报错**，而且报错信息会很长。看到"future is not Send"就是这个。

AGENTS.md 对此有专门规则（grep `async_fn_in_trait`）。

### ② `self: Arc<Self>` 而不是 `&self`

```rust
fn run(self: Arc<Self>, ...) -> impl Future<...>
//     ^^^^^^^^^^^^^^^ 接收者是 Arc，不是引用
```

**因为返回的 future 要活得比这次调用长**（被 spawn 出去了）。如果接收者是 `&self`，那个引用在函数返回后就悬空了。

拿 `Arc<Self>` 意味着**任务持有自己的一份所有权**，可以安心跨 `.await` 存活。

> **Python 里不用想这个**——对象只要还有引用就不会被回收。这一条纯粹是所有权系统的税。

---

## 5. 模块系统：默认全私有

[05](./05-inside-a-turn.md) §5 那个 8 行的 `codex-rs/core/src/context_manager/mod.rs`：

```rust
mod history;                    // 挂进来，但外面看不见
mod normalize;
pub(crate) mod updates;         // 挂进来，本 crate 内可见

pub(crate) use history::ContextManager;              // 单独放行这几个
pub(crate) use history::estimate_item_token_count;
pub(crate) use history::is_user_turn_boundary;
pub(crate) use history::truncate_function_output_payload;
```

**和 Python 完全相反：**

| | Python | Rust |
| ---- | ---- | ---- |
| 默认可见性 | **全部公开**（`_foo` 只是约定） | **全部私有** |
| 要暴露什么 | 无需声明（或写 `__all__`） | **必须逐个 `pub use`** |

### 三档可见性

| 写法 | 谁能看见 |
| ---- | ---- |
| （不写） | 只有当前模块及其子模块 |
| `pub(crate)` | **本 crate 内**任何地方 |
| `pub` | 全世界（其他 crate 也能用） |

> **这是 codex 能精确控制"入口面"的机制。** AGENTS.md 有两条相关规则：`Prefer private modules`、`Keep crate API surfaces as small as possible`。
>
> **对自建项目**：Python 里没有等价机制，但可以用 `__all__` + linter 规则近似。**关键是养成"默认不导出"的习惯**——你导出的每个符号都是未来的维护负担。

---

## 6. `#[non_exhaustive]`：为什么会有 `_ => {}` 兜底

[03](./03-protocol.md) §7 那个坑：

```rust
#[non_exhaustive]
pub enum Op { /* 26 个变体 */ }

// 别处的 match：
match sub.op {
    Op::UserInput(..) => { /* … */ }
    // …
    _ => false,     // ← 这不是漏写
}
```

**含义**：标了 `#[non_exhaustive]` 的枚举，**其他 crate 匹配它时必须写兜底分支**。这样上游加新变体不算破坏性变更。

> ⚠️ **对 fork 的实际影响**（[22](./22-load-bearing-and-cuts.md) §1）：这条兜底分支会**吃掉你本该看到的编译错误**。删变体时它不报错，运行时才发现漏了。
>
> **削减期间临时注释掉它**，让编译器帮你找全。

---

## 7. `include_str!`：编译期把文件塞进二进制

```rust
const APPLY_PATCH_LARK_GRAMMAR: &str = include_str!("apply_patch.lark");
```

**编译时**读取文件内容，变成一个字符串常量塞进二进制。运行时没有文件读取。

Python 里没有直接对应——最接近的是 `importlib.resources`，但那是运行时读的。

> ⚠️ **codex 特有的坑**：本仓库同时用 Cargo 和 Bazel 构建。**Bazel 不会自动让源码树里的文件对编译可见**，所以新增 `include_str!` 必须同步往 `BUILD.bazel` 的 `compile_data` 里加一条（AGENTS.md grep 关键词 `compile_data`）。忘了就是 Bazel 构建挂而 Cargo 构建正常。

---

## 8. channel 为什么被拆成两半

[02](./02-startup.md) §5 讲过，这里补充**为什么**：

```rust
let (tx, rx) = async_channel::bounded(512);   // 一次拿到两头
```

> **注意 crate 名**：codex 用的是 `async_channel`（第三方、MPMC、不绑运行时），**不是** `tokio::sync::mpsc`（MPSC、绑 tokio）。整个项目跑在 tokio 上，但 channel 不是 tokio 的——这两件事不冲突，因为 `async_channel` 只依赖 `Future`，任何运行时都能驱动。

Python 的 `asyncio.Queue` 是**一个对象**，谁拿到都能又发又收。Rust 拆成两个值，是因为：

> **所有权系统能保证"发送端在这里、接收端在那里"，编译期就锁死了数据流向。**

这直接支撑了 [02](./02-startup.md) §5 那个"最妙的地方"——前端手里只有 `tx_sub` 和 `rx_event`，**它在类型层面就不可能调用内核函数**。

> **给自建项目（Python）**：拿不到编译期保证，但可以近似——**把 `Queue` 包一层，只暴露 `send` 或只暴露 `recv`**：
>
> ```python
> class Sender:
>     def __init__(self, q): self._q = q
>     async def send(self, msg): await self._q.put(msg)
>     # 故意没有 recv
> ```
>
> 挡不住存心绕过的人，但能挡住手滑。

### 顺带：有界与无界的 Python 对照

[02](./02-startup.md) §5 讲的那个不对称，Python 里是同一个类的两种构造：

| codex | Python 等价 | 满了的行为 |
| ---- | ---- | ---- |
| `async_channel::bounded(512)` | `asyncio.Queue(maxsize=512)` | `await q.put()` 挂起——**这就是背压** |
| `async_channel::unbounded()` | `asyncio.Queue()`（默认无上限） | 不会满，只会吃内存 |

**Python 版本一样能做出这个设计**，唯一区别是 Rust 用两个不同的构造函数、Python 用一个参数。**别因为它只是个参数就不当回事**——这一个参数决定了"谁能卡住谁"。

---

## 9. `FuturesOrdered` 与 tokio 的心智模型

> **先对齐一个前提**：Python 的 `asyncio` 是标准库，`import` 就有；**Rust 的 `async`/`await` 只是语法，运行时要自己选、自己写进依赖**。tokio 是这个位置上的事实标准。所以下表左边不是"Rust 的标准做法"，是"tokio 的做法"——换成 `async-std` 名字就变了。完整说明见 [01](./01-coordinates.md) §2 补课。

[05](./05-inside-a-turn.md) §3 出现过：

```rust
let mut in_flight: FuturesOrdered<BoxFuture<'static, CodexResult<ResponseInputItem>>>
    = FuturesOrdered::new();
```

| Rust | Python |
| ---- | ---- |
| `tokio::spawn(fut)` | `asyncio.create_task(coro)` |
| `FuturesOrdered` | `asyncio.gather(*tasks)`（**保序**） |
| `FuturesUnordered` | `asyncio.as_completed(tasks)`（先完成先出） |
| `CancellationToken` | `task.cancel()`，但**可以建子 token** |
| `watch::Receiver` | 无直接对应——只保留**最新值**的广播 |

### 一个 Python 没有的东西：取消令牌树

[04](./04-three-loops.md) §6：

```rust
cancellation_token.child_token()
```

**父取消 → 子跟着取消；子取消 → 父不受影响。**

Python 里 `task.cancel()` 是平的，你得自己维护"哪些任务属于这一组"。

> **这个模式值得在 Python 里手动实现**——"中断一个 turn"和"中断整个任务"必须能分开表达，否则用户按一次 Ctrl+C 就把整个会话杀了。

---

## 10. codex 用机器强制的四条规约

这些不是 Rust 语言特性，是**这个仓库自己加的门禁**。对自建 Rust 项目直接可抄。

### ① 禁止 crate features

`.github/scripts/verify_cargo_workspace_manifests.py` 拒绝任何 `[features]` 段和 `optional = true`。脚本自己的报错文案说明了原因：

> "Workspace crate features are disallowed because our Bazel build setup does not honor them today, which can let issues hidden behind feature gates go unnoticed, and because they add extra crate build permutations we want to avoid."

**两条理由**：Bazel 不认它（会造成两套构建行为不一致）；每加一个 feature 就多一倍构建组合。

> **对自建项目**：feature flag 在 Rust 里是**测试矩阵的乘法**。一个 crate 3 个 feature = 8 种组合，你的 CI 大概率只测了 1 种。**能不用就不用**，用运行时配置（[12](./12-config-and-features.md)）代替。

### ② 禁止 `unwrap` / `expect`

`codex-rs/Cargo.toml` 的 `[workspace.lints.clippy]`：

```toml
unwrap_used = "deny"
expect_used = "deny"
```

`codex-rs/clippy.toml` 里放开测试：

```toml
allow-expect-in-tests = true
allow-unwrap-in-tests = true
```

> `unwrap()` 相当于 Python 的"我确定这里不会是 None，出错就崩"。**生产代码里禁掉它，等于强制你处理每一个失败分支。**
>
> **这条最值得抄**，而且几乎零成本——加两行配置。

### ③ 禁止跨 `.await` 持锁

```toml
await_holding_lock = "deny"
await_holding_invalid_type = "deny"
```

配合 `codex-rs/clippy.toml`：

```toml
await-holding-invalid-types = [
    "tokio::sync::MutexGuard",
    "tokio::sync::RwLockReadGuard",
    "tokio::sync::RwLockWriteGuard",
]
```

**为什么危险**：拿着锁 `.await`，这段时间锁一直被占着，别的任务全在等 —— **异步死锁的头号来源**。

> **Python 里同样的坑**：`async with lock: await something_slow()`。没有 linter 帮你，只能靠 review。**Rust 这条能机器强制，是实打实的优势。**

### ④ 禁用方法清单

`codex-rs/clippy.toml` 的 `disallowed-methods` 把具体 API 拉黑并写明理由，例如：

```toml
{ path = "sqlx::Pool::connect", reason = "Create SQLite pools through codex-state's sqlite shim." }
{ path = "ratatui::style::Color::Rgb", reason = "Use ANSI colors, which work better in various terminal themes." }
```

> **这是"架构约束落到机器上"的最细粒度形态**（呼应 [20](./20-design-decisions.md) 决策 10）。
>
> "所有 SQLite 连接必须走我们的封装"——写在文档里三个月后必被绕过；写成 `disallowed-methods`，**绕过就是 CI 红灯，而且报错信息里直接告诉你该用什么**。
>
> **Python 里可以用 `flake8` 自定义规则或 `ruff` 的 `flake8-tidy-imports` 近似。**

---

## 11. 读源码时的三个实用建议

### ① 按符号名找，不要按行号找

本教程给的 `文件:行号` 会漂。**行号对不上时用 `rg` 按符号名重新定位**：

```bash
rg 'fn run_turn' codex-rs/core/src/session/turn.rs
rg 'struct ToolRouter' codex-rs/core/src/tools/
```

### ② 先读每个目录的模块根文件，它就是这个目录的目录

因为 Rust 默认全私有，**模块根文件里的 `pub use` 清单就是"这个模块对外提供什么"的完整答案**（[05](./05-inside-a-turn.md) §5 那 8 行是最好的例子）。

比在目录里挨个点开文件快十倍。

### ③ 读测试比读实现快

[31](./31-testing-an-agent.md) §7 说过：**测试写的是"它应该怎么表现"，实现写的是"它怎么做到"。**

想搞懂压缩到底干了什么？`codex-rs/core/tests/suite/compact.rs`（5,440 行）比读 8 个 `compact_*.rs` 快得多。

---

## 本篇小结

| 你现在应该能回答 | 答案 |
| ---- | ---- |
| 满屏的 `Arc` 是什么？ | 引用计数指针。Python 里这是隐形的，Rust 要显式写 |
| `Arc::clone` 贵吗？ | **不贵**，一次原子加法。不是深拷贝 |
| Rust 怎么抛异常？ | **不抛**。用 `Result` + `?` |
| `thiserror` 和 `anyhow` 怎么选？ | 库用 `thiserror`（调用方要能 match），应用用 `anyhow` |
| 为什么 trait 里写 `impl Future + Send`？ | 要 spawn 到多线程运行时，必须约束 `Send` |
| 为什么是 `self: Arc<Self>`？ | future 要活得比调用长，引用会悬空 |
| 模块默认可见吗？ | **默认全私有**，和 Python 相反。要逐个 `pub use` |
| `_ => {}` 是漏写吗？ | 不是，`#[non_exhaustive]` 要求的。**但 fork 削减时要临时注释掉** |
| channel 为什么拆两半？ | 所有权系统能锁死数据流向，边界靠类型守 |
| 最该抄的规约是哪条？ | **`unwrap_used = "deny"`**，两行配置，收益极大 |

---

**回到** [README 目录](./README.md)，或从 [01 坐标系](./01-coordinates.md) 再读一遍——第二遍会看到第一遍漏掉的东西。
