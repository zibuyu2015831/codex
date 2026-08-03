---
title: Codex TypeScript 与 Python SDK
summary: 描述两套 SDK 的包名版本与运行时要求、共享 app-server 协议的架构含义、TypeScript 侧的 thread 与 turn 抽象、Python 侧同步与异步双客户端设计与捆绑 CLI 二进制的依赖策略，以及本地 Python 版本不足导致的证据等级上限。
keywords: codex | sdk | typescript | python | app-server | thread | async-client | packaging
scope: sdk/typescript、sdk/python、sdk/python-runtime 三套 SDK
related_files: sdk/typescript/package.json | sdk/typescript/src/index.ts | sdk/python/pyproject.toml | sdk/python/src | codex-rs/app-server-protocol/src/protocol/v2
dependencies: dev_docs/app_server_protocol.md | dev_docs/architecture_overview.md
verified_at: 2026-08-03
---

# TypeScript 与 Python SDK

> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **证据等级**: 包元数据与源码文件清单为 E2/E4；运行时行为为 E1

> [!WARNING]
> **本文的 Python 部分证据等级上限为 E2/E3。** 分析环境的 Python 是 3.9.6，低于 `sdk/python` 声明的 `requires-python = ">=3.10"`，**无法通过实际运行 pytest 取得 E4 验证**。相关结论基于配置文件与源码阅读，不能写成"已验证"。

---

## 1. 三个 SDK 包

| 目录 | 包名 | 版本 | 运行时要求 |
| ---- | ---- | ---- | ---- |
| `sdk/typescript` | `@openai/codex-sdk` | `0.0.0-dev` | Node ≥ 18 |
| `sdk/python` | `openai-codex` | `0.0.0-dev` | Python ≥ 3.10 |
| `sdk/python-runtime` | — | — | Python ≥ 3.10 |

两者都是 Apache-2.0。版本号 `0.0.0-dev` 是仓库内的占位值，**发布时由 CI 替换**（对应 `python-sdk-release.yml`、`sdk.yml` 工作流）。

> `sdk/` 目录下共 115 个 Git 跟踪文件。

---

## 2. 架构定位：SDK 是 app-server 的客户端

```
你的应用（TS / Python）
        ↓
  @openai/codex-sdk / openai-codex
        ↓  JSON-RPC
  codex app-server（同一个 codex 二进制）
        ↓
  codex-core
```

> [!IMPORTANT]
> **两套 SDK 共享同一份 app-server 协议**，而协议的**唯一事实源是 Rust 类型**（见 [`app_server_protocol.md`](./app_server_protocol.md) §0）。
>
> 这意味着：**协议变更会同时影响两套 SDK**，且 TS 类型是从 Rust 自动生成的（`schema/typescript/v2/` 下 550 个文件）。

---

## 3. TypeScript SDK

### 3.1 包配置（E2）

```json
{
  "name": "@openai/codex-sdk",
  "type": "module",
  "engines": { "node": ">=18" },
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts"
}
```

**纯 ESM**（`"type": "module"`），产物在 `dist/`，带类型声明。

### 3.2 源码模块（`sdk/typescript/src/`，E4）

| 文件 | 职责 |
| ---- | ---- |
| `index.ts` | 入口 |
| `codex.ts` | 主客户端 |
| `codexOptions.ts` | 客户端选项 |
| `thread.ts` / `threadOptions.ts` | **线程抽象** |
| `turnOptions.ts` | **turn 选项** |
| `items.ts` | 会话条目 |
| `events.ts` | 事件 |
| `exec.ts` | 执行 |
| `outputSchemaFile.ts` | 输出 schema 文件 |

**核心抽象是 thread 与 turn**，与 app-server 协议的 `thread/*`（57 个方法）、`turn/*`（8 个）、`item/*`（19 个）严格对应。这不是巧合——SDK 是协议的薄封装。

> `outputSchemaFile.ts` 说明 SDK 支持**结构化输出**：给定一个 JSON Schema 文件约束模型输出格式。

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
```

三个值得注意的点：

> [!IMPORTANT]
> **① 构建后端是 `uv_build`**，不是 setuptools/hatchling。构建这个包需要 uv。

> [!IMPORTANT]
> **② 依赖 `openai-codex-cli-bin==0.144.4`（精确版本锁定）。**
> 这是**捆绑的 CLI 二进制包**——Python SDK 不自己实现协议客户端，而是**拉起 codex 二进制**并与之通信。精确锁版本保证 SDK 与二进制的协议版本匹配。
>
> 这也解释了 `sdk/python-runtime` 的存在与 `python-runtime-build.yml` / `python-runtime-release.yml` 两个独立工作流——它们负责打包各平台的二进制。

> [!NOTE]
> **③ `Development Status :: 5 - Production/Stable`**
> 尽管仓库内版本号是 `0.0.0-dev`，包分类器声明的成熟度是 **Production/Stable**。这是三套 SDK 中唯一显式声明稳定性的。

### 4.2 源码模块（`sdk/python/src/openai_codex/`，E4）

| 文件 | 职责 |
| ---- | ---- |
| `__init__.py` | 入口 |
| `api.py` | API 层 |
| `async_client.py` | **异步客户端** |
| `_run.py` | 运行 |
| `_message_router.py` | **消息路由** |
| `_inputs.py` | 输入 |
| `_goal.py` | 目标（对应 `thread/goal/*` 协议方法） |
| `_login.py` | 登录 |
| `_approval_mode.py` | **审批模式**（对应 `AskForApproval`） |
| `_sandbox.py` | **沙箱**（对应 `SandboxPolicy`） |
| `_initialize_metadata.py` | 初始化元数据 |
| `_version.py` | 版本 |

**下划线前缀是 Python 的私有约定**——公开 API 面收敛在 `__init__.py` 与 `api.py`，其余是内部实现。

`async_client.py` 与 `api.py` 并存说明提供**同步与异步双接口**。

`_approval_mode.py` 与 `_sandbox.py` 直接对应 Rust 侧的 `AskForApproval` 与 `SandboxPolicy`（见 [`core_agent_loop.md`](./core_agent_loop.md) §4）——**SDK 使用者可以控制审批与沙箱策略**。

---

## 5. 两套 SDK 的对照

| | TypeScript | Python |
| ---- | ---- | ---- |
| 包名 | `@openai/codex-sdk` | `openai-codex` |
| 运行时 | Node ≥ 18 | Python ≥ 3.10 |
| 模块格式 | 纯 ESM | 标准包 |
| 构建 | tsc → `dist/` | uv_build |
| 与 codex 二进制的关系 | **未在包配置中声明依赖** | **精确锁定 `openai-codex-cli-bin==0.144.4`** |
| 同步/异步 | JS 天然异步 | 双客户端（`api.py` + `async_client.py`） |
| 类型来源 | ts-rs 从 Rust 生成 | pydantic 模型（手写或生成，未确认） |
| 声明的成熟度 | 未声明 | Production/Stable |

> **一个明显差异**：Python SDK 显式捆绑并锁定 CLI 二进制版本，TypeScript 侧没有对应声明。
>
> **未验证**（E1）：TS SDK 如何定位 codex 二进制——是要求用户预装，还是有其他机制。入口是 `sdk/typescript/src/exec.ts`。

---

## 6. 相关 CI 工作流

| 工作流 | 用途 |
| ---- | ---- |
| `sdk.yml` | SDK 通用 CI |
| `python-sdk-release.yml` | Python SDK 发布 |
| `python-runtime-build.yml` | Python runtime 构建 |
| `python-runtime-release.yml` | Python runtime 发布 |

见 [`build_and_release.md`](./build_and_release.md) §4。

---

## 7. 改动 SDK 的注意事项

| 事项 | 依据 |
| ---- | ---- |
| **协议变更会同时影响两套 SDK** | 共享 app-server 协议 |
| 改 app-server API 形状后必须跑 `just write-app-server-schema` | `AGENTS.md:300-304` |
| v2 类型必须标注 `#[ts(export_to = "v2/")]` | `AGENTS.md:277` |
| Python 侧的最低版本以最近的 `pyproject.toml` 的 `requires-python` 为准 | `AGENTS.md:313-315` |
| 格式化走 `just fmt`（覆盖 Python SDK 代码） | `justfile` |

---

## 8. 本文未覆盖的内容

| 未覆盖项 | 当前证据 | 建议入口 |
| ---- | ---- | ---- |
| 两套 SDK 的公开 API 签名 | E4（仅文件清单） | `sdk/typescript/src/index.ts`、`sdk/python/src/openai_codex/api.py` |
| SDK 的实际用法示例 | E1 | 各 SDK 的 `README.md` |
| TS SDK 如何定位 codex 二进制 | E1 | `sdk/typescript/src/exec.ts` |
| Python 侧类型是手写还是生成 | E1 | `sdk/python/src/openai_codex/` |
| `sdk/python-runtime` 的具体内容 | E1 | 该目录 |
| SDK 的测试组织与覆盖 | **E2 上限**（本机无法跑 Python 测试） | `sdk.yml` 工作流 |
| 版本号在发布时的替换机制 | E1 | `python-sdk-release.yml`、`sdk.yml` |

---

## 9. 相关文档

- [app-server 协议](./app_server_protocol.md) — SDK 依赖的协议面
- [架构总览](./architecture_overview.md) §4 — 协议先行的类型单一事实源
- [构建与发布](./build_and_release.md) — SDK 的 CI 与发布链路
- [智能体核心循环](./core_agent_loop.md) §4 — 审批与沙箱策略类型
