---
title: Codex TypeScript 与 Python SDK
summary: 描述两套 SDK 的包名版本与运行时要求、两者走完全不同传输通道这一关键事实（TS 走 codex exec --experimental-json，Python 走 codex app-server JSON-RPC）、TypeScript 侧的二进制定位链路与 thread/turn 抽象、Python 侧的同步异步双层结构，以及类型生成流水线的真实起点——不是仓库内的 schema 文件而是被 pin 住的运行时二进制（因此改仓库 schema 不会触发漂移测试，且 Rust 发布对 update_sdk_artifacts.py 只走 stage-runtime、不重生成 SDK 类型，但它仍在另一条支线上经 stage_npm_packages.py 发布 TS SDK 的 npm 包），另含 python-runtime 的 wheel-only 构建钩子（sdist target 注册同一 hook 以主动报错）与捆绑 CLI 二进制的依赖锁定策略、sdk.yml 两条流水线的实际内容与两侧发布版本号替换机制。
keywords: codex | sdk | typescript | python | exec-json | app-server | thread | async-client | packaging | datamodel-codegen
scope: sdk/typescript、sdk/python、sdk/python-runtime 三套 SDK
related_files: sdk/typescript/package.json | sdk/typescript/src/exec.ts | sdk/typescript/src/events.ts | sdk/typescript/src/codex.ts | sdk/typescript/src/codexOptions.ts | sdk/typescript/src/index.ts | sdk/python/pyproject.toml | sdk/python/src/openai_codex/api.py | sdk/python/src/openai_codex/client.py | sdk/python/src/openai_codex/errors.py | sdk/python/src/openai_codex/generated/v2_all.py | sdk/python/src/openai_codex/generated/notification_registry.py | sdk/python/scripts/update_sdk_artifacts.py | sdk/python/tests/test_contract_generation.py | sdk/python-runtime/pyproject.toml | sdk/python-runtime/hatch_build.py | sdk/python/src/openai_codex/_goal.py | sdk/typescript/tests/testCodex.ts | scripts/stage_npm_packages.py | .github/workflows/sdk.yml | .github/workflows/rust-release.yml | codex-rs/exec/src/exec_events.rs | AGENTS.md
dependencies: dev_docs/app_server_protocol.md | dev_docs/architecture_overview.md
verified_at: 2026-09-21
---

# TypeScript 与 Python SDK

> **基线 commit**: `5c5308fc9a9ee789049d646ef11e5400384b9c6f`
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
> **本文的 Python 部分证据等级上限为 E2/E3。** 分析环境 Python 为 3.14.6（满足 `sdk/python` 声明的 `requires-python = ">=3.10"`），但未安装 `pytest` / `pydantic` / `openai-codex-cli-bin`（`sdk/python` 下无 `.venv`），且核验期禁止联网安装依赖，**因此仍无法取得 E4 验证**。相关结论基于配置文件与源码阅读，不能写成「已验证」。
>
> 卡住的确切步骤：`cd sdk/python && python3 -m pytest --collect-only` → `No module named pytest`，连收集阶段都进不去。即使跨过这一步，`sdk/python/tests/test_contract_generation.py:43` 还硬断言 `importlib.metadata.version("openai-codex-cli-bin") == "0.153.4"`，而该包是**平台专属 wheel、只发 PyPI**——`sdk/python-runtime/hatch_build.py:17-20` 对 sdist 构建直接 `raise RuntimeError("openai-codex-cli-bin is wheel-only; ...")`，仓库内无法本地构建替代品，这是不可绕过的硬墙。官方 CI 的做法印证了这点：`.github/workflows/sdk.yml:36-39` 第一步就是 `uv sync --group dev --frozen`，必须联网。

---

## 1. 三个 SDK 包

| 目录 | 包名 | 版本 | 构建后端 | 运行时要求 |
| ---- | ---- | ---- | ---- | ---- |
| `sdk/typescript` | `@openai/codex-sdk` | `0.0.0-dev` | tsup | Node ≥ 18 |
| `sdk/python` | `openai-codex` | `0.0.0-dev` | `uv_build` | Python ≥ 3.10 |
| `sdk/python-runtime` | **`openai-codex-cli-bin`** | `0.0.0-dev` | `hatchling` | Python ≥ 3.10 |

> [!NOTE]
> **勘误（两轮）**：第一版把 `sdk/python-runtime` 的包名与版本写成「—」。它有完整的 `sdk/python-runtime/pyproject.toml`：`name = "openai-codex-cli-bin"`、`version = "0.0.0-dev"`、`description = "Pinned Codex CLI runtime for the Python SDK"`，构建后端是 **hatchling**（不是 uv_build）。
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
> 1. `target_name == "sdist"` 时直接 `raise RuntimeError`——**该包只允许构建 wheel**，不发源码包。这个 raise 之所以有机会执行，是因为 `sdk/python-runtime/pyproject.toml:47-48` 除了 wheel target 之外还注册了 sdist target 与**同一个** custom hook：
>
>    ```toml
>    [tool.hatch.build.targets.sdist]
>
>    [tool.hatch.build.targets.sdist.hooks.custom]
>    ```
>
>    也就是说 wheel-only 策略不是靠「不配置 sdist」被动实现的，而是靠「配置了 sdist 但让 hook 主动炸掉」——任何人尝试 `hatch build --target sdist` 都会立刻拿到明确报错，而不是一个静默产出的残缺源码包；
> 2. 解析平台标签：优先取 hatch 配置里的 `platform-tag`，其次取对应环境变量，再退回 `packaging.tags.sys_tags()` 的第一个；
> 3. 设置 `build_data`：`pure_python = False`、`infer_tag = False`、`tag = f"py3-none-{platform_tag}"`——即**强制产出平台相关 wheel 并自己指定 tag**，这正是"每个平台一个 wheel"的实现方式。
>
> **它就是 `sdk/python` 里那条 `openai-codex-cli-bin==0.153.4` 依赖所指的包**——本仓库既是 SDK 的源，也是它捆绑二进制的源。第一版把这两件事分开写，没有连起来。

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
- **想看完整的「SDK 选项 → CLI 标志」映射，直接读 `sdk/typescript/src/exec.ts:17-39`**：该文件顶部的选项类型定义里，逐字段用注释标注了对应标志，是 TS 侧「契约面 = CLI 标志」最直接的文档。除上面列出的几个之外还包括 `--config model_reasoning_effort`、`--config sandbox_workspace_write.network_access`、`--config web_search`、legacy `--config features.web_search_request`、`--config approval_policy`。
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
> **`codex-rs/app-server-protocol/schema/typescript/v2/` 下那 631 个 ts-rs 生成的 `.ts` 文件不是给 `@openai/codex-sdk` 用的。**（注意仓库根下没有 `schema/` 目录，完整路径在 `codex-rs/app-server-protocol/` 下；每个文件首行都是 `// GENERATED CODE! DO NOT MODIFY BY HAND!`。） 它们是 app-server 协议的对外类型产物，服务于直接对接 app-server 的客户端（例如 VS Code 扩展）。TypeScript SDK 不引用它们。

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
> **勘误**：第一版在 §5 对照表里写「构建 = tsc → `dist/`」。实际的构建脚本是 **`tsup`**（`"build": "tsup"`，配置在 `sdk/typescript/tsup.config.ts`，devDependency `tsup@^8.5.0`）。`typescript` 只作为 devDependency 存在，用于类型检查与 ts-jest。测试跑 **jest**（`ts-jest`），格式化用 prettier，lint 用 eslint。 <!-- ref-exempt: 此处 `typescript` 是 npm 包名（devDependency），不是前一处文件引用里的符号 -->

### 3.2 源码模块（`sdk/typescript/src/`，E1）

| 文件 | 职责 |
| ---- | ---- |
| `sdk/typescript/src/index.ts` | 入口：值导出 `Codex`（`:29`）/ `Thread`（`:26`），其余全部为 `export type` 重导出。这两行是整个包**唯一的值导出面**，也正是用户拿到的入口 API |
| `sdk/typescript/src/codex.ts` | 主客户端 `class Codex`，提供 `startThread()` / `resumeThread()` |
| `sdk/typescript/src/codexOptions.ts` | 客户端选项：`codexPathOverride`、`baseUrl`、`apiKey`、`config`、`env` |
| `sdk/typescript/src/thread.ts` / `sdk/typescript/src/threadOptions.ts` | 线程抽象 |
| `sdk/typescript/src/turnOptions.ts` | turn 选项 |
| `sdk/typescript/src/items.ts` | 会话条目类型 |
| `sdk/typescript/src/events.ts` | 事件类型（对应 `exec_events.rs::ThreadEvent`） |
| `sdk/typescript/src/exec.ts` | **进程编排层**：定位二进制、拼装 `codex exec` 参数、spawn、逐行产出 |
| `sdk/typescript/src/outputSchemaFile.ts` | 结构化输出的 schema 文件处理 |

> [!NOTE]
> **勘误**：第一版说「核心抽象是 thread 与 turn，与 app-server 协议的 `thread/*`（57 个方法）、`turn/*`（8 个）、`item/*`（19 个）严格对应……SDK 是协议的薄封装」。**不对应，也不是薄封装。** thread/turn/item 是 codex 全栈通用的领域概念，exec 事件流里同样有 `ThreadStartedEvent` / `TurnCompletedEvent` / `ItemCompletedEvent`（见 `sdk/typescript/src/index.ts` 的重导出列表）。TS SDK 对接的是**那一套**。

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
   - 首选 `vendor/<triple>/bin/codex`（Windows 为 `codex.exe`），且要求同目录存在 `codex-package.json`（运行时由打包流水线写入 vendor 目录，仓库内不存在该文件）；`PATH` 补充目录取自 `vendor/<triple>/codex-path/`。 <!-- ref-exempt: codex-package.json 是 npm 平台包 vendor 目录内的运行时元数据文件名，仓库内不存在；见 sdk/typescript/src/exec.ts:419 与 sdk/python/scripts/update_sdk_artifacts.py:29 -->
   - 回退到**遗留布局** `vendor/<triple>/codex/codex[.exe]`，`PATH` 补充目录取自 `vendor/<triple>/path/`。
4. 都找不到就抛错：`Unable to locate Codex CLI binaries. Ensure @openai/codex is installed with optional dependencies.`

> **结论**：TS SDK **不在 `package.json` 里声明对 `@openai/codex` 的依赖**——穷举锚点：`sdk/typescript/package.json` 根本没有 `dependencies` 键，只有 `devDependencies`——而是在运行时 `require.resolve` 它。使用者必须自己装 `@openai/codex`（并保留 optionalDependencies），或者用 `codexPathOverride` 指一个现成的二进制。这与 Python 侧「硬锁一个二进制包版本」是两种截然不同的策略。

### 3.4 示例与测试（E1 + E3）

第一版把「SDK 的实际用法示例」标成 E1 未知并指向 README。实际上仓库里就有：

- `sdk/typescript/samples/`（4 个）：`sdk/typescript/samples/basic_streaming.ts`、`sdk/typescript/samples/structured_output.ts`、`sdk/typescript/samples/structured_output_zod.ts`、`sdk/typescript/samples/helpers.ts`
- `sdk/typescript/tests/`（8 个）：`sdk/typescript/tests/run.test.ts`、`sdk/typescript/tests/runStreamed.test.ts`、`sdk/typescript/tests/exec.test.ts`、`sdk/typescript/tests/abort.test.ts`，以及夹具 `sdk/typescript/tests/codexExecSpy.ts`、`sdk/typescript/tests/responsesProxy.ts`、`sdk/typescript/tests/setupCodexHome.ts`、`sdk/typescript/tests/testCodex.ts`

测试是**起一个假的 Responses 代理并搭一个临时 `CODEX_HOME`**，端到端跑真二进制，而不是纯 mock（E3）：

- `sdk/typescript/tests/testCodex.ts:6-9` 决定用哪个二进制——`process.env.CODEX_EXEC_PATH ?? path.join(process.cwd(), "..", "..", "codex-rs", "target", "debug", "codex")`，即默认直接指向工作区里 `cargo build` 出来的 debug 二进制。
- `sdk/typescript/tests/responsesProxy.ts` 起一个 `node:http` 服务冒充 Responses API，`sdk/typescript/tests/setupCodexHome.ts` 造临时 `CODEX_HOME`。

CI 侧闭环印证了这一点：`.github/workflows/sdk.yml:85-142` 先用 Bazel 构建 `//codex-rs/cli:codex`、把产物 install 到 `.tmp/sdk-ci/codex`、写进 `CODEX_EXEC_PATH` 并跑一次 `--version` 预热，之后才 `pnpm install --frozen-lockfile` → build → lint → test（`:146-156`）。**如果 TS 测试是纯 mock，就不需要先构建一个真二进制。**

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
dependencies = ["pydantic>=2.12", "openai-codex-cli-bin==0.153.4"]
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
> **② 依赖 `openai-codex-cli-bin==0.153.4`（精确版本锁定）+ 时间戳锁定。**
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
| `sdk/python/src/openai_codex/__init__.py` | 公开导出面 | 公开 |
| `sdk/python/src/openai_codex/api.py` | 公开 API 的**主体**：`Codex` / `AsyncCodex` / `Thread` / `AsyncThread` / `TurnHandle` / `AsyncTurnHandle`。**注意它不是"全部公开 API"**——见下方勘误 | 公开 |
| `sdk/python/src/openai_codex/models.py` | 公开数据模型（103 行） | 公开 |
| `sdk/python/src/openai_codex/types.py` | 公开类型别名（81 行） | 公开 |
| `sdk/python/src/openai_codex/errors.py` | 异常层级（见 §4.1 ③） | 公开 |
| `py.typed` | PEP 561 标记，声明包自带类型信息 | 公开 |
| **`sdk/python/src/openai_codex/client.py`** | **`CodexClient`：同步 JSON-RPC 传输客户端**，另含 `CodexConfig`、`CodexBinResolverOps`、`_ThreadStartLock` | 传输 |
| **`sdk/python/src/openai_codex/async_client.py`** | **`AsyncCodexClient`：异步对偶** | 传输 |
| `sdk/python/src/openai_codex/_message_router.py` | 帧路由 | 传输 |
| `sdk/python/src/openai_codex/retry.py` | 过载重试 | 传输 |
| `generated/` | **生成的类型**：`sdk/python/src/openai_codex/generated/v2_all.py`（12,811 行 pydantic 模型）、`sdk/python/src/openai_codex/generated/notification_registry.py`、`sdk/python/src/openai_codex/generated/__init__.py` | 生成 |
| `sdk/python/src/openai_codex/_run.py` | turn 结果收集（`TurnResult`） | 内部 |
| `sdk/python/src/openai_codex/_inputs.py` | 输入构造与 wire 转换 | 内部 |
| `sdk/python/src/openai_codex/_goal.py` | **goal 生命周期状态机与通知路由**（448 行，包内第三大文件）：`observe()`（`:55`）、`activate_turn_routing()`（`:89`）、`wait_for_start()`（`:94`）、`begin_interrupt()`/`confirm_interrupt()`/`cancel_interrupt()`（`:130`/`:137`/`:143`）、`active_turn()`（`:154`），并与 `sdk/python/src/openai_codex/_message_router.py:197` 的 `notification.method.startswith("thread/goal/")` 路由联动。**协议调用本身不在这里**——`thread/goal/clear` / `thread/goal/set` 发在 `sdk/python/src/openai_codex/client.py:496` / `:515` | 内部 |
| `sdk/python/src/openai_codex/_login.py` | 登录（ChatGPT / device code，同步与异步各一套 handle） | 内部 |
| `sdk/python/src/openai_codex/_approval_mode.py` | 审批模式（对应 `AskForApproval`） | 内部 |
| `sdk/python/src/openai_codex/_sandbox.py` | 沙箱（对应 `SandboxPolicy`） | 内部 |
| `sdk/python/src/openai_codex/_initialize_metadata.py` | 初始化元数据校验 | 内部 |
| `sdk/python/src/openai_codex/_version.py` | 版本 | 内部 |

**下划线前缀是 Python 的私有约定**——但注意：`sdk/python/src/openai_codex/client.py` / `sdk/python/src/openai_codex/async_client.py` / `sdk/python/src/openai_codex/retry.py` **没有**下划线前缀，却也不是主要面向用户的入口，它们是传输层。

> [!NOTE]
> **勘误：`sdk/python/src/openai_codex/api.py` 不是"全部公开 API"。** 包的公开面由 `sdk/python/src/openai_codex/__init__.py:56` 的 `__all__` 定义，共 **36 项**；其中只有 6 项（`Codex` / `AsyncCodex` / `Thread` / `AsyncThread` / `TurnHandle` / `AsyncTurnHandle`）定义在 `sdk/python/src/openai_codex/api.py`，其余分散在 `sdk/python/src/openai_codex/errors.py`（**12 项** = 11 个异常类 + `is_retryable_error`）、`sdk/python/src/openai_codex/_inputs.py`（8 项）、`sdk/python/src/openai_codex/_login.py`（4 项）、`sdk/python/src/openai_codex/client.py`（`CodexConfig`）、`sdk/python/src/openai_codex/retry.py`（`retry_on_overload`）、`sdk/python/src/openai_codex/_run.py`（`TurnResult`）、`sdk/python/src/openai_codex/_approval_mode.py`、`sdk/python/src/openai_codex/_sandbox.py`、`sdk/python/src/openai_codex/_version.py`。
>
> 复核方式：读 `sdk/python/src/openai_codex/__init__.py` 的 `__all__`，再对每个名字在包内 grep 其 `class` / `def` / 赋值定义位置。

### 4.3 同步/异步是两层各一对（E3）

> [!NOTE]
> **勘误**：第一版说「`sdk/python/src/openai_codex/async_client.py` 与 `sdk/python/src/openai_codex/api.py` 并存说明提供同步与异步双接口」，把**公开层**和**传输层**混成了一对。正确的对应是**两层各有一对**：

| 层 | 同步 | 异步 |
| ---- | ---- | ---- |
| **公开 API**（都在 `sdk/python/src/openai_codex/api.py`） | `Codex`（`:75`）、`Thread`（`:534`）、`TurnHandle`（`:718`） | `AsyncCodex`（`:287`）、`AsyncThread`（`:622`）、`AsyncTurnHandle`（`:763`） |
| **传输客户端** | `sdk/python/src/openai_codex/client.py:212` `CodexClient` | `sdk/python/src/openai_codex/async_client.py:52` `AsyncCodexClient` |

`sdk/python/src/openai_codex/api.py:41-42` 直接 import 了两者，并在 `Codex.__init__`（`:83`）里 `self._client = CodexClient(config=config)`、在 `AsyncCodex.__init__`（`:296`）里 `self._client = AsyncCodexClient(config=config)`。

体量上，**传输层合计约为公开层的两倍**：`sdk/python/src/openai_codex/client.py` 864 行 + `sdk/python/src/openai_codex/async_client.py` 378 行 + `sdk/python/src/openai_codex/_message_router.py` 278 行 = **1,520 行**，而公开层 `sdk/python/src/openai_codex/api.py` 是 **807 行**。不过要注意 `sdk/python/src/openai_codex/api.py` 仍是包内**单文件最大者**，且其中相当一部分是生成出来的扁平方法（见 §5），并非全部手写的胶水代码——所以这里说的是「传输层承担了更多真实复杂度」，不是「公开层没有代码量」。

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
- 生成器版本被**精确锁定**：`sdk/python/pyproject.toml` 的 `test` 依赖组里 `datamodel-code-generator==0.31.2`（`sdk/python/uv.lock:96-98` 同步锁定）。生成器版本漂移会导致产物漂移，所以必须锁死。
- `[tool.ruff] extend-exclude` 里排除了 `src/openai_codex/generated/**`——生成物不受 lint 约束。

### 5.2 链路：输入就是仓库里的 schema 文件

> [!CAUTION]
> **这一节经历了两次反转，第二次把第一次推翻了回去。请连着读完再采信任何一版。**
>
> | 版本 | 结论 |
> | ---- | ---- |
> | 第一版 | 仓库里的 `schema/json/` → 生成脚本 |
> | 第 5 轮 | **推翻**：真正的输入是被 pin 住的运行时二进制现场导出的 schema，经临时目录中转；「改仓库 schema 不会让漂移测试变红」 |
> | **第 6 轮（当前）** | **再次推翻，链路改回了第一版的样子**：输入就是仓库内 `codex-rs/app-server-protocol/schema/json/` |
>
> **当前事实**（E3）：
>
> - `pinned_runtime_codex_path()` 与 `generate_schema_from_pinned_runtime()` **两个函数都已不存在**（`grep -c` → 0），临时目录中转也没了。
> - 路径改为**外置在配置里**（`sdk/python/pyproject.toml` 第 39-40 行）：
>
>   ```toml
>   [tool.codex.codegen]
>   schema-dir = "../../codex-rs/app-server-protocol/schema/json"
>   ```
>
>   `sdk/python/scripts/update_sdk_artifacts.py` 的 `generate-types` 在未传 `--schema-dir` 时读该配置键。
> - `codex-rs/app-server-protocol/scripts/write_schema_fixtures.py` 在重生成夹具后**紧接着**调用 `update_sdk_artifacts.py generate-types --schema-dir <仓库内 schema 目录>`。
>
> > [!IMPORTANT]
> > **第 5 轮那次「纠正」错在方法上，值得单独记住。**
> >
> > 它的核心证据是 `grep -c 'app-server-protocol' sdk/python/scripts/update_sdk_artifacts.py` → **0**，由此断定「脚本与仓库内 schema 没有任何引用关系」。
> >
> > **这条命令今天仍然返回 0，但结论完全相反**——因为路径被外置到了 `sdk/python/pyproject.toml` 的 `[tool.codex.codegen]` 段。
> >
> > **纪律：否定性 grep 不能证否一个机制。** 证否必须追到**调用点或配置键**，不能停在字面量搜索。本轮 [`app_server_protocol.md`](./app_server_protocol.md) §3 的「只有 `Initialized` 抓不到」是同一种失败模式，两篇各犯了一次。
> >
> > 另一层教训：当文档发现自己「纠正」了一个看似朴素的说法时要额外警惕——**朴素说法往往是上游的稳态，精致机制反而可能是短暂的中间形态**。

真实链路（E3，第 6 轮）：

```
改 Rust 协议类型
        ↓  just write-app-server-schema        （justfile:177-178 → write_schema_fixtures.py）
        ↓  ① cargo test … write_schema_fixtures_from_env --ignored   （真跑 ts-rs / schemars）
codex-rs/app-server-protocol/schema/json/      （仓库内 vendored 产物，被 git 跟踪）
        ↓  ② 同一个脚本接着 uv run update_sdk_artifacts.py generate-types --schema-dir <上面那个目录>
        ↓     datamodel-code-generator==0.31.2
sdk/python/src/openai_codex/generated/v2_all.py                （12,811 行 pydantic 模型）
sdk/python/src/openai_codex/generated/notification_registry.py （302 行）
sdk/python/src/openai_codex/api.py                             （扁平公开方法部分）
        ↓  漂移检测
sdk/python/tests/test_contract_generation.py + sdk.yml 末尾的 check-clean-worktree
```

关键含义（**与上一版相反**）：**Python SDK 的生成产物跟踪的正是你工作区里的 Rust 源码**（经由 vendored schema）。改了 app-server 协议类型而不重新生成，漂移测试**就会红**。

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
> **第 6 轮：这里原有的「改了 schema 也不会红」已被推翻，而且它引用的代码整块不存在了。**
>
> 上一版断言该测试会先校验 `importlib.metadata.version("openai-codex-cli-bin") == "0.153.4"` 并 `env.pop("CODEX_EXEC_PATH")`，据此推出「改仓库 schema 不会让测试变红」。
>
> 实测（`grep -n 'importlib\|openai-codex-cli-bin\|CODEX_EXEC_PATH' sdk/python/tests/test_contract_generation.py` → **零命中**）：版本断言与 `env.pop` 都已删除。该测试现在的文档字符串是：
>
> > *"Regenerating from **repository schemas** should leave reviewed artifacts unchanged."*
>
> **所以：改了仓库里的 app-server schema 而不重新生成，这个测试就会红**——这正是它现在唯一的作用。
>
> **一个连带的好消息**：那堵「必须装平台专属 wheel 才能跑测试」的硬墙已经拆了。该测试现在只需要 `datamodel-code-generator` 与仓库内 schema 即可运行。

### 5.3 谁在跑这个脚本，以及跑的是哪个子命令

> [!CAUTION]
> **第 6 轮：`stage-sdk` 已不再生成类型，因此「有哪个发布流程会重新生成 SDK 类型」这个问题的答案现在是——没有。**
>
> 该子命令的 help 文本逐字写着 *"Stage a releasable SDK package **from the checked-in generated code**"*，`run_command` 里它只调 `stage_python_sdk_package`。
>
> 生成现在**只发生在开发者本地**跑 `just write-app-server-schema`（或直接跑 `update_sdk_artifacts.py generate-types`）时，由 `sdk/python/tests/test_contract_generation.py` 与 `.github/workflows/sdk.yml` 末尾的 `check-clean-worktree` 双重兜底。
>
> 上一版在这里总结的方法论——「看到脚本名出现在某个工作流里，不等于该工作流触发了脚本的全部能力」——**不仅仍然成立，而且更成立了**。

`sdk/python/scripts/update_sdk_artifacts.py` 确实在四个工作流里被调用（E2——计的是 YAML 文件**内容**匹配，不是目录/文件名清点），但**子命令不同，后果完全不同**（E3，`:1435-1450` 的 `run_command`）：

| 子命令 | 是否调用 `ops.generate_types()` |
| ---- | ---- |
| `generate-types` | ✅ |
| `stage-sdk` | ✅（先 `generate_types()` 再 `stage_python_sdk_package()`） |
| `stage-runtime` | ❌ **只做 runtime 包打包** |

各工作流实际用的子命令（E2）：

| 工作流 | 子命令 | 是否重生成 SDK 类型 |
| ---- | ---- | ---- |
| `.github/workflows/python-sdk-release.yml` | `stage-sdk` | ⚠️ **第 6 轮：该工作流已缩至 172 行，原 `:196` 行号越界，且文件中已无 `stage-sdk` job**。本轮未重新推导 Python SDK 的发布 job 清单 |
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
| 与 codex 二进制的关系 | **不在包配置里声明**，运行时 `require.resolve("@openai/codex")` + 平台包，或 `codexPathOverride` | **精确锁 `openai-codex-cli-bin==0.153.4` + `exclude-newer-package` 时间戳锁** |
| 同步/异步 | JS 天然异步 | **两层各一对**：`Codex`/`AsyncCodex`（公开）、`CodexClient`/`AsyncCodexClient`（传输） |
| 类型来源 | **手写**（`sdk/typescript/src/events.ts` 顶部注释标注人工对照 Rust） | **生成**（datamodel-codegen 0.31.2 ← v2 JSON Schema） |
| 漂移检测 | 无 | `sdk/python/tests/test_contract_generation.py` |
| 声明的成熟度 | 未声明 | Production/Stable |

> **两个最重要的差异**：
> 1. **传输通道不同**——这决定了「改哪一层会影响哪个 SDK」。
> 2. **类型策略不同**——Python 侧有生成器 + 漂移测试兜底；TS 侧靠人工与注释，**改 `codex-rs/exec/src/exec_events.rs` 时没有任何「类型级」的机器保障会提醒你去同步 `sdk/typescript/src/events.ts`**（TS 侧既无生成器也无漂移测试）。唯一的间接兜底是 §3.4 那套端到端 jest：它跑的是真二进制，所以事件形状不兼容**可能**让 `sdk/typescript/tests/run.test.ts` / `sdk/typescript/tests/runStreamed.test.ts` 失败——但那是运行时症状，不是类型检查，纯新增字段之类的漂移照样静默通过。这仍是一个真实的风险点。

---

## 7. 相关 CI 工作流

| 工作流 | 用途 |
| ---- | ---- |
| `.github/workflows/sdk.yml` | SDK 通用 CI，两套 SDK 各一条流水线（详见下方） |
| `.github/workflows/python-sdk-release.yml` | Python SDK 发布。**第 6 轮：它已不再调用 `update_sdk_artifacts.py`**——该文件缩至 172 行，现在是编排器（`:74` 调 `python-runtime-build.yml`、`:83` 调 `python-sdk-build.yml`），自己只做 PyPI 发布与校验 |
| `.github/workflows/python-sdk-build.yml` | **第 6 轮新增**：`stage-sdk` 的唯一调用点（`:49-52`） |
| `.github/workflows/python-sdk-cli-release.yml` | **第 6 轮新增**，本文未展开 |
| `.github/workflows/python-runtime-build.yml` | `openai-codex-cli-bin` 构建；`update_sdk_artifacts.py stage-runtime`（不生成类型） |
| `.github/workflows/python-runtime-release.yml` | `openai-codex-cli-bin` 发布 |
| `.github/workflows/rust-release.yml` / `.github/workflows/rust-release-windows.yml` | Rust 发布；对 `sdk/python/scripts/update_sdk_artifacts.py` 同样只调 `stage-runtime`，**不重跑类型生成**（见 §5.3 的 CAUTION）。**但 `.github/workflows/rust-release.yml` 另外还发布 TS SDK 的 npm 包**——见 §7.2 |

### 7.1 `.github/workflows/sdk.yml` 实际跑了什么（E2）

- **Python SDK**（`.github/workflows/sdk.yml:36-39`）：在 `python:3.12-slim` 容器里 `uv sync --group dev --frozen` → `ruff check` → `ruff format --check` → `pytest`。第一步就必须联网拉依赖（含 `openai-codex-cli-bin` wheel），这正是本文顶部「本地拿不到 E4」的原因。
- **TypeScript SDK**（`.github/workflows/sdk.yml:85-156`）：先用 Bazel 构建 `//codex-rs/cli:codex`、把二进制 install 到 `.tmp/sdk-ci/codex` 并写入 `CODEX_EXEC_PATH`、跑 `--version` 预热，然后 `pnpm install --frozen-lockfile` → `run build` → `run lint` → `run test`。

### 7.2 `.github/workflows/rust-release.yml` 也发布 `@openai/codex-sdk`（E2）

**§7 的表格容易让人以为 Rust 发布流程与 TS SDK 无关——不对。** 它与 `sdk/python/scripts/update_sdk_artifacts.py` 的关系确实只有 `stage-runtime`，但它在另一条支线上打包并发布 TypeScript SDK 的 npm tarball：

- `.github/workflows/rust-release.yml:1333-1339`：
  ```bash
  ./scripts/stage_npm_packages.py \
    --release-version "$RELEASE_VERSION" \
    ... \
    --package codex \
    --package codex-responses-api-proxy \
    --package codex-sdk
  ```
- 随后 `:1440` 把 `codex-sdk-npm-${version}.tgz` 一并从 release 下载，`:1462`、`:1527` 走 npm 发布与打 tag。

所以准确的分工是：**TS SDK 的 npm 发布挂在 Rust 发布流程上（与 CLI 同版本同批次），Python SDK 的发布走自己的 `.github/workflows/python-sdk-release.yml`。** 这也解释了为什么 TS SDK 不用锁二进制版本——它和 `@openai/codex` 本来就是同一次发布出去的。

**版本号替换机制**（E3，本次把 §9 的这条 E1 未知项结掉）：

| 侧 | 替换者 |
| ---- | ---- |
| TypeScript | `scripts/stage_npm_packages.py` 的 `--release-version` 参数（由 `.github/workflows/rust-release.yml:1333-1339` 传入） |
| Python | `sdk/python/scripts/update_sdk_artifacts.py:213-225` 的 `stage_python_sdk_package()`，内部先 `normalize_codex_version(sdk_version)` 再 `_rewrite_project_version(pyproject_text, package_version)` 改写 staging 目录里那份 `sdk/python/pyproject.toml` 的副本 |

两侧都是**在 staging 副本上改写**，仓库工作区里的 `0.0.0-dev` 始终不动。

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
| 不要手改 `sdk/python/src/openai_codex/generated/**`，也不要随手改 `sdk/python/src/openai_codex/api.py` | 两者都在 `sdk/python/tests/test_contract_generation.py:10-14` 的 `GENERATED_TARGETS` 里 |
| 升 `datamodel-code-generator` 版本会改变生成产物，必须连带重生成并核对 diff | `sdk/python/pyproject.toml` 锁 `==0.31.2` |
| 换捆绑二进制版本时，`==` 版本号与 `exclude-newer-package` 时间戳**要一起改** | `sdk/python/pyproject.toml` `[tool.uv]` / `[tool.uv.pip]` |
| Python 侧的最低版本以最近的 `pyproject.toml` 的 `requires-python` 为准；**不要用 `__future__` 做 Python 2 兼容** | `AGENTS.md` `## Python Development Best Practices` → `### Ignore Python 2 compatibility` <!-- ref-exempt: 原文 "check the closest pyproject.toml's requires-python field"，「最近的」是泛指，不绑定单一文件 --> |
| 三套包必须同时支持 Linux / macOS / Windows | AGENTS.md `## Platform Support` |
| 格式化走 `just fmt`（覆盖 Python SDK 代码）；Python 侧另有 ruff（`required-version = ">=0.15.8"`，`line-length = 100`，`target-version = "py310"`） | 仓库根 `justfile`、`sdk/python/pyproject.toml` |

---

## 9. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 两套 SDK 的公开 API 逐个签名 | E1（仅类名与文件清单） | `sdk/typescript/src/index.ts`、`sdk/python/src/openai_codex/api.py` |
| `codex exec --experimental-json` 事件流的完整事件表 | E1 | `codex-rs/exec/src/exec_events.rs` |
| `sdk/python/scripts/update_sdk_artifacts.py` 对 schema 的预处理规则（它有大量 normalize 逻辑，如 `:351`、`:558`） | E1 | 该脚本 |
| SDK 测试的实际通过情况 | **E2/E3 上限**（缺 `pytest` / `pydantic` / `openai-codex-cli-bin` 依赖，需 `uv sync --group dev` 联网；见本文顶部 WARNING） | `.github/workflows/sdk.yml` 工作流（见 §7.1） |

---

## 10. 相关文档

- [app-server 协议](./app_server_protocol.md) — **只有 Python SDK 依赖的协议面**
- [架构总览](./architecture_overview.md) §4 — 协议先行的类型单一事实源
- [构建与发布](./build_and_release.md) — SDK 的 CI 与发布链路
- [智能体核心循环](./core_agent_loop.md) §5 — 审批与沙箱策略类型
