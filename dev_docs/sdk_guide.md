---
title: Codex TypeScript 与 Python SDK
summary: 描述两套 SDK 的包名版本与运行时要求、两者走完全不同传输通道这一关键事实（TS 走 codex exec --experimental-json，Python 走 codex app-server JSON-RPC）、TypeScript 侧的二进制定位链路与 thread/turn 抽象、Python 侧的同步异步双层结构，以及类型生成流水线的真实起点——不是仓库内的 schema 文件而是被 pin 住的运行时二进制（因此改仓库 schema 不会触发漂移测试，且 Rust 发布只走 stage-runtime、不重生成 SDK 类型），另含 python-runtime 的 wheel-only 构建钩子与捆绑 CLI 二进制的依赖锁定策略。
keywords: codex | sdk | typescript | python | exec-json | app-server | thread | async-client | packaging | datamodel-codegen
scope: sdk/typescript、sdk/python、sdk/python-runtime 三套 SDK
related_files: sdk/typescript/package.json | sdk/typescript/src/exec.ts | sdk/typescript/src/events.ts | sdk/typescript/src/codex.ts | sdk/typescript/src/codexOptions.ts | sdk/typescript/src/index.ts | sdk/python/pyproject.toml | sdk/python/src/openai_codex/api.py | sdk/python/src/openai_codex/client.py | sdk/python/src/openai_codex/errors.py | sdk/python/src/openai_codex/generated/v2_all.py | sdk/python/src/openai_codex/generated/notification_registry.py | sdk/python/scripts/update_sdk_artifacts.py | sdk/python/tests/test_contract_generation.py | sdk/python-runtime/pyproject.toml | codex-rs/exec/src/exec_events.rs | AGENTS.md
dependencies: dev_docs/app_server_protocol.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# TypeScript 与 Python SDK

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 包元数据为 E2；文件/目录清单为 E1；传输通道与生成链路为 E3（源码与调用链）

> [!CAUTION]
> **本文第一版的整体框架是错的，本版已重写 §2 / §3 / §5 / §8。**
>
> 第一版声称「两套 SDK 共享同一份 app-server 协议」，并据此推导出「协议变更会同时影响两套 SDK」「TS 类型是 ts-rs 从 Rust 生成的」「SDK 是协议的薄封装」，还在注意事项里让读者改 TS SDK 时去跑 `just write-app-server-schema`、加 `#[ts(export_to = "v2/")]`。
>
> **这些全部不成立。** `grep -rn "app-server" sdk/typescript/` 返回 **0 行**。TypeScript SDK 根本不接 app-server——它拉起 `codex exec --experimental-json` 并消费 exec 的事件流。只有 Python SDK 用 app-server。
>
> 错误的根源是：第一版看到 `sdk/typescript/src/thread.ts` / `sdk/typescript/src/turnOptions.ts` 与协议里的 `thread/*`、`turn/*` 命名空间同名，就直接假定了对应关系，**没有打开 `sdk/typescript/src/exec.ts` 看它到底 spawn 了什么**。同名不等于同源。

> [!WARNING]
> **本文的 Python 部分证据等级上限为 E2/E3。** 分析环境的 Python 是 3.9.6，低于 `sdk/python` 声明的 `requires-python = ">=3.10"`，**无法通过实际运行 pytest 取得 E4 验证**。相关结论基于配置文件与源码阅读，不能写成「已验证」。

---

## 1. 三个 SDK 包

| 目录 | 包名 | 版本 | 构建后端 | 运行时要求 |
| ---- | ---- | ---- | ---- | ---- |
| `sdk/typescript` | `@openai/codex-sdk` | `0.0.0-dev` | tsup | Node ≥ 18 |
| `sdk/python` | `openai-codex` | `0.0.0-dev` | `uv_build` | Python ≥ 3.10 |
| `sdk/python-runtime` | **`openai-codex-cli-bin`** | `0.0.0-dev` | `hatchling` | Python ≥ 3.10 |

> [!NOTE]
> **勘误（两轮）**：第一版把 `sdk/python-runtime` 的包名与版本写成「—」。它有完整的 `pyproject.toml`：`name = "openai-codex-cli-bin"`、`version = "0.0.0-dev"`、`description = "Pinned Codex CLI runtime for the Python SDK"`，构建后端是 **hatchling**（不是 uv_build）。
>
> 上一稿又说是「自定义构建钩子把 `bin/`、`codex-resources/`、`codex-path/` 打进 wheel」——**这三项其实来自静态配置，不是钩子干的**。`sdk/python-runtime/pyproject.toml:36-43`（E2）：
>
> ```toml
> [tool.hatch.build.targets.wheel]
> packages = ["src/codex_cli_bin"]
> include = [
>   "src/codex_cli_bin/codex-package.json",
>   "src/codex_cli_bin/bin/**",
>   "src/codex_cli_bin/codex-resources/**",
>   "src/codex_cli_bin/codex-path/**",
> ]
> ```
>
> 钩子（`sdk/python-runtime/hatch_build.py` 的 `RuntimeBuildHook.initialize`）做的是**另外三件事**（E3，本次一并把 §9「钩子做了什么」这一 E1 未知项结掉）：
>
> 1. `target_name == "sdist"` 时直接 `raise RuntimeError`——**该包只允许构建 wheel**，不发源码包；
> 2. 解析平台标签：优先取 hatch 配置里的 `platform-tag`，其次取对应环境变量，再退回 `packaging.tags.sys_tags()` 的第一个；
> 3. 设置 `build_data`：`pure_python = False`、`infer_tag = False`、`tag = f"py3-none-{platform_tag}"`——即**强制产出平台相关 wheel 并自己指定 tag**，这正是"每个平台一个 wheel"的实现方式。
>
> **它就是 `sdk/python` 里那条 `openai-codex-cli-bin==0.144.4` 依赖所指的包**——本仓库既是 SDK 的源，也是它捆绑二进制的源。第一版把这两件事分开写，没有连起来。

两个面向用户的包都是 Apache-2.0。版本号 `0.0.0-dev` 是仓库内的占位值，**发布时由 CI 替换**（见 §7；`sdk/python/release_version.py` 提供 `normalize_codex_version`）。

> `sdk/` 目录下共 115 个 Git 跟踪文件。

---

## 2. 架构定位：两套 SDK，两条不同的传输通道（E3）

```
        你的 TS 应用                          你的 Python 应用
             ↓                                      ↓
      @openai/codex-sdk                        openai-codex
             ↓                                      ↓
   spawn: codex exec --experimental-json    spawn: codex app-server --listen stdio://
             ↓  行分隔 JSON 事件流                  ↓  JSON-RPC（非标准 2.0）over stdio
        codex-exec                              codex-app-server
             ↓                                      ↓
                            codex-core
```

### 2.1 TypeScript SDK → `codex exec --experimental-json`

- `sdk/typescript/src/exec.ts:87`：
  ```ts
  const commandArgs: string[] = ["exec", "--experimental-json"];
  ```
  后续按需追加 `--config`、`--model`、`--sandbox`、`--cd`、`--add-dir`、`--skip-git-repo-check`、`--output-schema` 等 CLI 标志（`:89-130`），然后 `spawn` 并把 stdout 按行 yield 出去（`run()` 是 `AsyncGenerator<string>`）。
- `sdk/typescript/src/events.ts:1` 的第一行注释坐实了事件来源：
  ```ts
  // based on event types from codex-rs/exec/src/exec_events.rs
  ```
  对应的 Rust 类型是 `codex-rs/exec/src/exec_events.rs:11` 的 `pub enum ThreadEvent`。
- `grep -rn "app-server" sdk/typescript/` → **0 行**。

### 2.2 Python SDK → `codex app-server`

- `sdk/python/src/openai_codex/client.py:213` 的类文档字符串：
  > "Synchronous typed JSON-RPC client for `codex app-server` over stdio."
- `sdk/python/src/openai_codex/client.py:252`：
  ```text
  args.extend(["app-server", "--listen", "stdio://"])
  ```

### 2.3 这个差异的实际后果

| | TypeScript SDK | Python SDK |
| ---- | ---- | ---- |
| 契约面 | `codex-rs/exec/src/exec_events.rs` 的 `ThreadEvent` 及 CLI 标志 | app-server v2 JSON-RPC 方法与通知 |
| 改 app-server 协议会不会影响它 | **不会**（除非同时改了 exec 事件） | **会** |
| 改 `codex-rs/exec/src/exec_events.rs` 或 `codex exec` 标志会不会影响它 | **会** | 基本不会 |
| 类型来源 | **手写** TS（`sdk/typescript/src/events.ts` / `sdk/typescript/src/items.ts` 参照 Rust 类型人工同步，无生成器） | **生成**（见 §5.3） |
| 有无漂移检测 | 无（注释靠人维护） | 有（`sdk/python/tests/test_contract_generation.py`） |

> [!IMPORTANT]
> **`schema/typescript/v2/` 下那 550 个 ts-rs 生成的 `.ts` 文件不是给 `@openai/codex-sdk` 用的。** 它们是 app-server 协议的对外类型产物，服务于直接对接 app-server 的客户端（例如 VS Code 扩展）。TypeScript SDK 不引用它们。

---

## 3. TypeScript SDK

### 3.1 包配置（E2）

```json
{
  "name": "@openai/codex-sdk",
  "type": "module",
  "engines": { "node": ">=18" },
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "scripts": { "build": "tsup", "test": "jest", "lint": "pnpm eslint ..." }
}
```

**纯 ESM**（`"type": "module"`），产物在 `dist/`，带类型声明。

> [!NOTE]
> **勘误**：第一版在 §5 对照表里写「构建 = tsc → `dist/`」。实际的构建脚本是 **`tsup`**（`"build": "tsup"`，配置在 `sdk/typescript/tsup.config.ts`，devDependency `tsup@^8.5.0`）。`typescript` 只作为 devDependency 存在，用于类型检查与 ts-jest。测试跑 **jest**（`ts-jest`），格式化用 prettier，lint 用 eslint。

### 3.2 源码模块（`sdk/typescript/src/`，E1）

| 文件 | 职责 |
| ---- | ---- |
| `index.ts` | 入口，重导出类型 |
| `sdk/typescript/src/codex.ts` | 主客户端 `class Codex`，提供 `startThread()` / `resumeThread()` |
| `sdk/typescript/src/codexOptions.ts` | 客户端选项：`codexPathOverride`、`baseUrl`、`apiKey`、`config`、`env` |
| `sdk/typescript/src/thread.ts` / `sdk/typescript/src/threadOptions.ts` | 线程抽象 |
| `sdk/typescript/src/turnOptions.ts` | turn 选项 |
| `sdk/typescript/src/items.ts` | 会话条目类型 |
| `sdk/typescript/src/events.ts` | 事件类型（对应 `exec_events.rs::ThreadEvent`） |
| `sdk/typescript/src/exec.ts` | **进程编排层**：定位二进制、拼装 `codex exec` 参数、spawn、逐行产出 |
| `sdk/typescript/src/outputSchemaFile.ts` | 结构化输出的 schema 文件处理 |

> [!NOTE]
> **勘误**：第一版说「核心抽象是 thread 与 turn，与 app-server 协议的 `thread/*`（57 个方法）、`turn/*`（8 个）、`item/*`（19 个）严格对应……SDK 是协议的薄封装」。**不对应，也不是薄封装。** thread/turn/item 是 codex 全栈通用的领域概念，exec 事件流里同样有 `ThreadStartedEvent` / `TurnCompletedEvent` / `ItemCompletedEvent`（见 `index.ts` 的重导出列表）。TS SDK 对接的是**那一套**。

### 3.3 codex 二进制怎么找到（E3）

第一版把这条标为「未验证（E1）」，现已查清（`sdk/typescript/src/exec.ts`）：

1. **显式覆盖优先**：`CodexOptions.codexPathOverride`（`sdk/typescript/src/codexOptions.ts:6`）。
2. **否则从 npm 包解析**（`sdk/typescript/src/exec.ts:391-410`）：
   ```ts
   const codexPackageJsonPath = moduleRequire.resolve(`${CODEX_NPM_NAME}/package.json`);   // "@openai/codex"
   const codexRequire = createRequire(codexPackageJsonPath);
   const platformPackageJsonPath = codexRequire.resolve(`${platformPackage}/package.json`);
   vendorRoot = path.join(path.dirname(platformPackageJsonPath), "vendor");
   ```
   平台包按 target triple 映射（`sdk/typescript/src/exec.ts:47-54`）：

   | target triple | npm 平台包 |
   | ---- | ---- |
   | `x86_64-unknown-linux-musl` | `@openai/codex-linux-x64` |
   | `aarch64-unknown-linux-musl` | `@openai/codex-linux-arm64` |
   | `x86_64-apple-darwin` | `@openai/codex-darwin-x64` |
   | `aarch64-apple-darwin` | `@openai/codex-darwin-arm64` |
   | `x86_64-pc-windows-msvc` | `@openai/codex-win32-x64` |
   | `aarch64-pc-windows-msvc` | `@openai/codex-win32-arm64` |

3. **在 vendor 目录里定位可执行文件**（`resolveNativePackage`，`sdk/typescript/src/exec.ts:412-435`）：
   - 首选 `vendor/<triple>/bin/codex`（Windows 为 `codex.exe`），且要求同目录存在 `codex-package.json`；`PATH` 补充目录取自 `vendor/<triple>/codex-path/`。
   - 回退到**遗留布局** `vendor/<triple>/codex/codex[.exe]`，`PATH` 补充目录取自 `vendor/<triple>/path/`。
4. 都找不到就抛错：`Unable to locate Codex CLI binaries. Ensure @openai/codex is installed with optional dependencies.`

> **结论**：TS SDK **不在 `package.json` 里声明对 `@openai/codex` 的依赖**，而是在运行时 `require.resolve` 它。使用者必须自己装 `@openai/codex`（并保留 optionalDependencies），或者用 `codexPathOverride` 指一个现成的二进制。这与 Python 侧「硬锁一个二进制包版本」是两种截然不同的策略。

### 3.4 示例与测试（E1）

第一版把「SDK 的实际用法示例」标成 E1 未知并指向 README。实际上仓库里就有：

- `sdk/typescript/samples/`（4 个）：`sdk/typescript/samples/basic_streaming.ts`、`sdk/typescript/samples/structured_output.ts`、`sdk/typescript/samples/structured_output_zod.ts`、`sdk/typescript/samples/helpers.ts`
- `sdk/typescript/tests/`（8 个）：`sdk/typescript/tests/run.test.ts`、`sdk/typescript/tests/runStreamed.test.ts`、`sdk/typescript/tests/exec.test.ts`、`sdk/typescript/tests/abort.test.ts`，以及夹具 `sdk/typescript/tests/codexExecSpy.ts`、`sdk/typescript/tests/responsesProxy.ts`、`sdk/typescript/tests/setupCodexHome.ts`、`sdk/typescript/tests/testCodex.ts`

`sdk/typescript/tests/responsesProxy.ts` + `sdk/typescript/tests/setupCodexHome.ts` 说明测试是**起一个假的 Responses 代理并搭一个临时 `CODEX_HOME`**，端到端跑真二进制，而不是纯 mock。

---

## 4. Python SDK

### 4.1 包配置（E2，`sdk/python/pyproject.toml`）

```toml
[build-system]
requires = ["uv_build>=0.11.19,<0.12"]
build-backend = "uv_build"

[project]
name = "openai-codex"
requires-python = ">=3.10"
dependencies = ["pydantic>=2.12", "openai-codex-cli-bin==0.144.4"]
classifiers = ["Development Status :: 5 - Production/Stable", ...]

[dependency-groups]
test = ["pytest>=8.0", "datamodel-code-generator==0.31.2", { include-group = "format" }]

[tool.uv]
exclude-newer = "7 days"
exclude-newer-package = { openai-codex-cli-bin = "2026-07-15T01:00:00Z" }
index-strategy = "first-index"
```

四个值得注意的点：

> [!IMPORTANT]
> **① 构建后端是 `uv_build`**，不是 setuptools/hatchling。构建这个包需要 uv。（对比：`sdk/python-runtime` 用的是 hatchling。）

> [!IMPORTANT]
> **② 依赖 `openai-codex-cli-bin==0.144.4`（精确版本锁定）+ 时间戳锁定。**
> 除了 `==` 版本锁，`[tool.uv]` 与 `[tool.uv.pip]` 里还有 `exclude-newer-package = { openai-codex-cli-bin = "2026-07-15T01:00:00Z" }` —— **双保险**：即便版本号被放宽，解析器也不会取到该时刻之后发布的构件。全局还有 `exclude-newer = "7 days"` 与 `index-strategy = "first-index"`（防依赖混淆攻击）。
>
> 这也解释了 `sdk/python-runtime` 的存在与 `.github/workflows/python-runtime-build.yml` / `.github/workflows/python-runtime-release.yml` 两个独立工作流——它们负责打包各平台的二进制并发布成 `openai-codex-cli-bin`。

> [!WARNING]
> **③ 勘误：「Python SDK 不自己实现协议客户端」是错的。**
> 第一版写「Python SDK 不自己实现协议客户端，而是拉起 codex 二进制并与之通信」。这是把两件事对立起来了——**它两件事都做**：拉起二进制**作为服务端**，并在 Python 侧实现了一个完整的**带类型的 JSON-RPC 客户端**：
> - `sdk/python/src/openai_codex/client.py` / `sdk/python/src/openai_codex/async_client.py`：`CodexClient` / `AsyncCodexClient`，负责 spawn、握手、请求-响应配对
> - `sdk/python/src/openai_codex/_message_router.py:17`：`class MessageRouter`，负责把 stdout 上的帧分发给等待方
> - `sdk/python/src/openai_codex/errors.py`：完整的错误层级 `CodexError` → `JsonRpcError` → `CodexRpcError` → `ParseError` / `InvalidRequestError` / `MethodNotFoundError` / `InvalidParamsError` / `InternalRpcError` / `ServerBusyError`，另有 `TransportClosedError`。**注意 `RetryLimitExceededError` 不是 `CodexRpcError` 的直接子类**——`sdk/python/src/openai_codex/errors.py:52` 是 `class RetryLimitExceededError(ServerBusyError)`，即它比 `ServerBusyError` **更深一层**。这个区别有实际后果：`except ServerBusyError` 会连带捕获 `RetryLimitExceededError`。（上一稿把它与 `ServerBusyError` 并列，错了。）
> - `sdk/python/src/openai_codex/retry.py:12`：`retry_on_overload(...)`，过载重试策略
>
> 一句话：**二进制是服务端，协议客户端是 Python 自己写的。**

> [!NOTE]
> **④ `Development Status :: 5 - Production/Stable`**
> 尽管仓库内版本号是 `0.0.0-dev`，包分类器声明的成熟度是 **Production/Stable**。这是三套 SDK 中唯一显式声明稳定性的。

### 4.2 源码模块（`sdk/python/src/openai_codex/`，E1）

> [!NOTE]
> **勘误**：第一版这张表标为 E4 且只列了 12 项，实际目录下有 **19 项**（漏了 7 项，其中包括最关键的 `sdk/python/src/openai_codex/client.py`）。同时按本文档体系的证据分级，**目录清单属于 E1，不是 E4**。

| 文件 / 目录 | 职责 | 层 |
| ---- | ---- | ---- |
| `__init__.py` | 公开导出面 | 公开 |
| `sdk/python/src/openai_codex/api.py` | 公开 API 的**主体**：`Codex` / `AsyncCodex` / `Thread` / `AsyncThread` / `TurnHandle` / `AsyncTurnHandle`。**注意它不是"全部公开 API"**——见下方勘误 | 公开 |
| `sdk/python/src/openai_codex/models.py` | 公开数据模型（103 行） | 公开 |
| `sdk/python/src/openai_codex/types.py` | 公开类型别名（81 行） | 公开 |
| `sdk/python/src/openai_codex/errors.py` | 异常层级（见 §4.1 ③） | 公开 |
| `py.typed` | PEP 561 标记，声明包自带类型信息 | 公开 |
| **`sdk/python/src/openai_codex/client.py`** | **`CodexClient`：同步 JSON-RPC 传输客户端**，另含 `CodexConfig`、`CodexBinResolverOps`、`_ThreadStartLock` | 传输 |
| **`sdk/python/src/openai_codex/async_client.py`** | **`AsyncCodexClient`：异步对偶** | 传输 |
| `sdk/python/src/openai_codex/_message_router.py` | 帧路由 | 传输 |
| `sdk/python/src/openai_codex/retry.py` | 过载重试 | 传输 |
| `generated/` | **生成的类型**：`sdk/python/src/openai_codex/generated/v2_all.py`（9,454 行 pydantic 模型）、`sdk/python/src/openai_codex/generated/notification_registry.py`、`__init__.py` | 生成 |
| `sdk/python/src/openai_codex/_run.py` | turn 结果收集（`TurnResult`） | 内部 |
| `sdk/python/src/openai_codex/_inputs.py` | 输入构造与 wire 转换 | 内部 |
| `sdk/python/src/openai_codex/_goal.py` | 目标（对应 `thread/goal/*` 协议方法） | 内部 |
| `sdk/python/src/openai_codex/_login.py` | 登录（ChatGPT / device code，同步与异步各一套 handle） | 内部 |
| `sdk/python/src/openai_codex/_approval_mode.py` | 审批模式（对应 `AskForApproval`） | 内部 |
| `sdk/python/src/openai_codex/_sandbox.py` | 沙箱（对应 `SandboxPolicy`） | 内部 |
| `sdk/python/src/openai_codex/_initialize_metadata.py` | 初始化元数据校验 | 内部 |
| `sdk/python/src/openai_codex/_version.py` | 版本 | 内部 |

**下划线前缀是 Python 的私有约定**——但注意：`sdk/python/src/openai_codex/client.py` / `sdk/python/src/openai_codex/async_client.py` / `sdk/python/src/openai_codex/retry.py` **没有**下划线前缀，却也不是主要面向用户的入口，它们是传输层。

> [!NOTE]
> **勘误：`sdk/python/src/openai_codex/api.py` 不是"全部公开 API"。** 包的公开面由 `__init__.py:56` 的 `__all__` 定义，共 **36 项**；其中只有 6 项（`Codex` / `AsyncCodex` / `Thread` / `AsyncThread` / `TurnHandle` / `AsyncTurnHandle`）定义在 `sdk/python/src/openai_codex/api.py`，其余分散在 `sdk/python/src/openai_codex/errors.py`（11 项，异常层级与 `is_retryable_error`）、`sdk/python/src/openai_codex/_inputs.py`（8 项）、`sdk/python/src/openai_codex/_login.py`（4 项）、`sdk/python/src/openai_codex/client.py`（`CodexConfig`）、`sdk/python/src/openai_codex/retry.py`（`retry_on_overload`）、`sdk/python/src/openai_codex/_run.py`（`TurnResult`）、`sdk/python/src/openai_codex/_approval_mode.py`、`sdk/python/src/openai_codex/_sandbox.py`、`sdk/python/src/openai_codex/_version.py`。
>
> 复核方式：读 `sdk/python/src/openai_codex/__init__.py` 的 `__all__`，再对每个名字在包内 grep 其 `class` / `def` / 赋值定义位置。

### 4.3 同步/异步是两层各一对（E3）

> [!NOTE]
> **勘误**：第一版说「`sdk/python/src/openai_codex/async_client.py` 与 `sdk/python/src/openai_codex/api.py` 并存说明提供同步与异步双接口」，把**公开层**和**传输层**混成了一对。正确的对应是**两层各有一对**：

| 层 | 同步 | 异步 |
| ---- | ---- | ---- |
| **公开 API**（都在 `sdk/python/src/openai_codex/api.py`） | `Codex`（`:75`）、`Thread`（`:534`）、`TurnHandle`（`:718`） | `AsyncCodex`（`:287`）、`AsyncThread`（`:622`）、`AsyncTurnHandle`（`:763`） |
| **传输客户端** | `sdk/python/src/openai_codex/client.py:212` `CodexClient` | `sdk/python/src/openai_codex/async_client.py:52` `AsyncCodexClient` |

`sdk/python/src/openai_codex/api.py:41-42` 直接 import 了两者，并在 `Codex.__init__`（`:83`）里 `self._client = CodexClient(config=config)`、在 `AsyncCodex.__init__`（`:296`）里 `self._client = AsyncCodexClient(config=config)`。**公开层是薄的，传输层才是重的。**

---

## 5. Python 类型生成流水线（E3）

第一版把「Python 侧类型是手写还是生成」标为未验证（E1）。答案是**生成**，而且有完整的防漂移机制。

### 5.1 证据

- `sdk/python/src/openai_codex/generated/v2_all.py:1-2`：
  ```text
  # generated by datamodel-codegen:
  #   filename:  codex_app_server_protocol.v2.schemas.json
  ```
- `sdk/python/src/openai_codex/generated/notification_registry.py:1-2`：
  ```text
  # Auto-generated by scripts/update_sdk_artifacts.py
  # DO NOT EDIT MANUALLY.
  ```
- 生成器版本被**精确锁定**：`pyproject.toml` 的 `test` 依赖组里 `datamodel-code-generator==0.31.2`（`uv.lock` 同步锁定）。生成器版本漂移会导致产物漂移，所以必须锁死。
- `[tool.ruff] extend-exclude` 里排除了 `src/openai_codex/generated/**`——生成物不受 lint 约束。

### 5.2 链路：输入不是仓库里的 schema 文件，而是**被锁定的运行时二进制**

> [!CAUTION]
> **本文上一稿把这条链路的起点写错了。** 它画成「仓库里的 `codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json` → 生成脚本」，并说脚本的 `:51` 在定位那个文件。**两点都不成立：**
>
> - `sdk/python/scripts/update_sdk_artifacts.py:49-51` 的 `schema_bundle_path()` 只是拼一个**文件名**，它接受的 `schema_dir` 是参数传进来的临时目录，与仓库内的 `schema/json/` 无关。脚本全文没有引用 `app-server-protocol` 这个 crate 路径，`codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json` 在这里只是运行时导出的产物文件名。
> - 真正的输入是**被 pin 住的运行时二进制自己吐出来的 schema**。

真实链路（E3）：

```
sdk/python 的依赖 openai-codex-cli-bin==0.144.4（已安装的 wheel 里捆绑的 codex 二进制）
        ↓  update_sdk_artifacts.py:108 pinned_runtime_codex_path() 定位它，并校验版本号一致
        ↓  :530-546 generate_schema_from_pinned_runtime()
        ↓     run([codex_path, "app-server", "generate-json-schema", "--out", schema_dir])
临时目录（:1360 tempfile.TemporaryDirectory(prefix="codex-python-schema-")）
        ↓  :1350-1355 generate_types_from_schema_dir()：v2_all → notification_registry → api.py 扁平方法
        ↓  datamodel-code-generator==0.31.2
sdk/python/src/openai_codex/generated/v2_all.py            （9,454 行 pydantic 模型）
sdk/python/src/openai_codex/generated/notification_registry.py
sdk/python/src/openai_codex/api.py                          （扁平公开方法部分）
        ↓  漂移检测
sdk/python/tests/test_contract_generation.py
```

关键含义：**Python SDK 的生成产物跟踪的是"那个被 pin 的已发布版本"，不是你工作区里的 Rust 源码。**

`sdk/python/tests/test_contract_generation.py:10-14` 声明的受检产物是三项——注意 **`sdk/python/src/openai_codex/api.py` 也在列**：

```python
GENERATED_TARGETS = [
    Path("src/openai_codex/generated/notification_registry.py"),
    Path("src/openai_codex/generated/v2_all.py"),
    Path("src/openai_codex/api.py"),
]
```

测试的做法是先快照这三项、重跑生成脚本、再比对字节。

> [!CAUTION]
> **上一稿说"改了 schema 却没重新生成就会红"——这是错的。** 该测试在重跑生成前先断言运行时版本，见下方代码。
>
> 所以：**在仓库里改 codex-rs 的 app-server schema，并不会让这个测试变红**——它比对的两端都来自同一个被 pin 的 wheel。只有当**运行时 pin 被升到新版本**时，产物才需要（也才会）跟着变。

`sdk/python/tests/test_contract_generation.py:43-45`：

```python
assert importlib.metadata.version("openai-codex-cli-bin") == "0.144.4"
env = os.environ.copy()
env.pop("CODEX_EXEC_PATH", None)  # 注释明说：不用 checkout 或 CI 环境里的 app-server 二进制
```

### 5.3 谁在跑这个脚本，以及跑的是哪个子命令

`sdk/python/scripts/update_sdk_artifacts.py` 确实在四个工作流里被调用（E1，`grep -rln`），但**子命令不同，后果完全不同**（E3，`:1435-1450` 的 `run_command`）：

| 子命令 | 是否调用 `ops.generate_types()` |
| ---- | ---- |
| `generate-types` | ✅ |
| `stage-sdk` | ✅（先 `generate_types()` 再 `stage_python_sdk_package()`） |
| `stage-runtime` | ❌ **只做 runtime 包打包** |

各工作流实际用的子命令（E2）：

| 工作流 | 子命令 | 是否重生成 SDK 类型 |
| ---- | ---- | ---- |
| `.github/workflows/python-sdk-release.yml:196` | `stage-sdk` | ✅ |
| `.github/workflows/python-runtime-build.yml:77` | `stage-runtime` | ❌ |
| `.github/workflows/rust-release.yml:414`、`:838` | `stage-runtime` | ❌ |
| `.github/workflows/rust-release-windows.yml:326` | `stage-runtime` | ❌ |

> [!CAUTION]
> **上一稿写的"Rust 发布流程会连带重跑 SDK 产物生成"是错的**，并据此得出「这正是『协议是事实源、Python SDK 是下游』的机制体现」——**这个漂亮的因果链并不存在**。Rust 发布只走 `stage-runtime`，即把新构建出的 codex 二进制打进 `openai-codex-cli-bin` wheel；**只有 Python SDK 自己的发布流程（`stage-sdk`）才会重新生成类型**。
>
> 教训：看到脚本名出现在某个工作流里，不等于该工作流触发了脚本的全部能力——**要看它传的是哪个子命令**。可用 `grep -n 'update_sdk_artifacts' -A 3 .github/workflows/*.yml` 自查。

### 5.4 Python 测试组织（E1）

`sdk/python/tests/` 下 18 个文件，按对象分三类：

- **app-server 行为**：`sdk/python/tests/test_app_server_lifecycle.py`、`sdk/python/tests/test_app_server_run.py`、`sdk/python/tests/test_app_server_streaming.py`、`sdk/python/tests/test_app_server_approvals.py`、`sdk/python/tests/test_app_server_goal_operations.py`、`sdk/python/tests/test_app_server_inputs.py`、`sdk/python/tests/test_app_server_login.py`、`sdk/python/tests/test_app_server_turn_controls.py`，夹具 `sdk/python/tests/app_server_harness.py` / `sdk/python/tests/app_server_helpers.py` / `sdk/python/tests/conftest.py`
- **客户端与公开面**：`sdk/python/tests/test_client_rpc_methods.py`、`sdk/python/tests/test_async_client_behavior.py`、`sdk/python/tests/test_public_api_signatures.py`、`sdk/python/tests/test_public_api_runtime_behavior.py`
- **产物与集成**：`sdk/python/tests/test_contract_generation.py`、`sdk/python/tests/test_artifact_workflow_and_binaries.py`、`sdk/python/tests/test_real_app_server_integration.py`

---

## 6. 两套 SDK 的对照

| | TypeScript | Python |
| ---- | ---- | ---- |
| 包名 | `@openai/codex-sdk` | `openai-codex` |
| 运行时 | Node ≥ 18 | Python ≥ 3.10 |
| **与 codex 的通道** | **`codex exec --experimental-json`（行分隔 JSON 事件流）** | **`codex app-server --listen stdio://`（JSON-RPC）** |
| **契约面** | `codex-rs/exec/src/exec_events.rs` + CLI 标志 | app-server v2 方法/通知 |
| 模块格式 | 纯 ESM | 标准包（带 `py.typed`） |
| 构建 | **tsup** → `dist/` | `uv_build` |
| 测试 | jest（起假 Responses 代理跑真二进制） | pytest（18 个文件） |
| 与 codex 二进制的关系 | **不在包配置里声明**，运行时 `require.resolve("@openai/codex")` + 平台包，或 `codexPathOverride` | **精确锁 `openai-codex-cli-bin==0.144.4` + `exclude-newer-package` 时间戳锁** |
| 同步/异步 | JS 天然异步 | **两层各一对**：`Codex`/`AsyncCodex`（公开）、`CodexClient`/`AsyncCodexClient`（传输） |
| 类型来源 | **手写**（`sdk/typescript/src/events.ts` 顶部注释标注人工对照 Rust） | **生成**（datamodel-codegen 0.31.2 ← v2 JSON Schema） |
| 漂移检测 | 无 | `sdk/python/tests/test_contract_generation.py` |
| 声明的成熟度 | 未声明 | Production/Stable |

> **两个最重要的差异**：
> 1. **传输通道不同**——这决定了「改哪一层会影响哪个 SDK」。
> 2. **类型策略不同**——Python 侧有生成器 + 漂移测试兜底；TS 侧靠人工与注释，**改 `codex-rs/exec/src/exec_events.rs` 时没有任何机器保障会提醒你去同步 `sdk/typescript/src/events.ts`**。这是一个真实的风险点。

---

## 7. 相关 CI 工作流

| 工作流 | 用途 |
| ---- | ---- |
| `.github/workflows/sdk.yml` | SDK 通用 CI |
| `.github/workflows/python-sdk-release.yml` | Python SDK 发布；`update_sdk_artifacts.py stage-sdk` —— **唯一会重新生成 SDK 类型的工作流** |
| `.github/workflows/python-runtime-build.yml` | `openai-codex-cli-bin` 构建；`update_sdk_artifacts.py stage-runtime`（不生成类型） |
| `.github/workflows/python-runtime-release.yml` | `openai-codex-cli-bin` 发布 |
| `.github/workflows/rust-release.yml` / `.github/workflows/rust-release-windows.yml` | Rust 发布；同样只调 `stage-runtime`，**不重跑类型生成**（见 §5.3 的 CAUTION） |

见 [`build_and_release.md`](./build_and_release.md) §4。

---

## 8. 改动 SDK 的注意事项

> [!CAUTION]
> **勘误**：第一版这张表里有三条是基于「两套 SDK 共享 app-server 协议」的错误前提写的——「协议变更会同时影响两套 SDK」「改 app-server API 形状后必须跑 `just write-app-server-schema`」「v2 类型必须标注 `#[ts(export_to = "v2/")]`」。后两条是 **app-server 协议侧**的规则（属于 [`app_server_protocol.md`](./app_server_protocol.md) §9，且那条 just recipe 本身已失效），**与改 TypeScript SDK 无关**。

| 事项 | 依据 |
| ---- | ---- |
| **先确认你改的是哪条通道**：exec 事件流影响 TS SDK，app-server 协议影响 Python SDK | §2 |
| 改 `codex-rs/exec/src/exec_events.rs` 或 `codex exec` 的 CLI 标志 → **手工同步** `sdk/typescript/src/events.ts` / `sdk/typescript/src/items.ts` / `sdk/typescript/src/exec.ts` | 无生成器、无漂移测试，只有 `sdk/typescript/src/events.ts:1` 的一行注释 |
| 改 app-server v2 schema **不会**让 `sdk/python/tests/test_contract_generation.py` 变红（它比对的是被 pin 的运行时 wheel）。Python SDK 类型的更新时机是**运行时 pin 升版**，届时跑 `update_sdk_artifacts.py generate-types` | §5.2 / §5.3 |
| 不要手改 `sdk/python/src/openai_codex/generated/**`，也不要随手改 `sdk/python/src/openai_codex/api.py` | 两者都是 `GENERATED_TARGETS` |
| 升 `datamodel-code-generator` 版本会改变生成产物，必须连带重生成并核对 diff | `pyproject.toml` 锁 `==0.31.2` |
| 换捆绑二进制版本时，`==` 版本号与 `exclude-newer-package` 时间戳**要一起改** | `sdk/python/pyproject.toml` `[tool.uv]` / `[tool.uv.pip]` |
| Python 侧的最低版本以最近的 `pyproject.toml` 的 `requires-python` 为准；**不要用 `__future__` 做 Python 2 兼容** | `AGENTS.md` `## Python Development Best Practices` → `### Ignore Python 2 compatibility` |
| 三套包必须同时支持 Linux / macOS / Windows | AGENTS.md `## Platform Support` |
| 格式化走 `just fmt`（覆盖 Python SDK 代码）；Python 侧另有 ruff（`required-version = ">=0.15.8"`，`line-length = 100`，`target-version = "py310"`） | 仓库根 `justfile`、`sdk/python/pyproject.toml` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 两套 SDK 的公开 API 逐个签名 | E1（仅类名与文件清单） | `sdk/typescript/src/index.ts`、`sdk/python/src/openai_codex/api.py` |
| `codex exec --experimental-json` 事件流的完整事件表 | E1 | `codex-rs/exec/src/exec_events.rs` |
| `sdk/python/scripts/update_sdk_artifacts.py` 对 schema 的预处理规则（它有大量 normalize 逻辑，如 `:351`、`:558`） | E1 | 该脚本 |
| SDK 测试的实际通过情况 | **E2 上限**（本机 Python 3.9.6，跑不了） | `.github/workflows/sdk.yml` 工作流 |
| 版本号在发布时的替换机制 | E1（只确认了 `release_version.normalize_codex_version` 的存在） | `sdk/python/release_version.py`、`.github/workflows/python-sdk-release.yml`、`.github/workflows/sdk.yml` |

---

## 10. 相关文档

- [app-server 协议](./app_server_protocol.md) — **只有 Python SDK 依赖的协议面**
- [架构总览](./architecture_overview.md) §4 — 协议先行的类型单一事实源
- [构建与发布](./build_and_release.md) — SDK 的 CI 与发布链路
- [智能体核心循环](./core_agent_loop.md) §5 — 审批与沙箱策略类型
