---
title: Codex 仓库 AI 规则索引
summary: 作为 AI 代理在本仓库工作的规则入口，明确以仓库自带 AGENTS.md 为唯一强制事实源、本文件只做索引与定位，并给出 dev_docs 文档体系特有的落盘路径、推送目标与脱敏约定。
keywords: codex | ai-rules | agents-md | index | dev-docs | constraints
scope: AI 代理在 openai/codex 仓库及本文档体系中的行为约束索引
related_files: AGENTS.md | docs/contributing.md | codex-rs/tui/styles.md | codex-rs/clippy.toml | justfile
dependencies: dev_docs/AI_Coding_Context.md | dev_docs/development_workflow.md
verified_at: 2026-08-03
---

# AI 规则索引

> [!CAUTION]
> **本文件不是规范，是索引。**
>
> 仓库自带的 AGENTS.md（22,519 字节）是**唯一的强制规范事实源**，优先级高于本文档体系的任何内容。本文件**不覆盖、不改写、不复制**其任何条款。
>
> 本文件存在的唯一理由是：帮你**快速定位**该去读哪一条，以及补充 `dev_docs` 体系自身的约定。

---

## 1. 事实源优先级

```
1. AGENTS.md                      ← 强制规范，最高优先级
2. docs/contributing.md           ← 贡献准入规则
3. codex-rs/tui/styles.md         ← TUI 样式（AGENTS.md:135 指定）
4. codex-rs/clippy.toml           ← 机器强制的 lint 规则
5. justfile                       ← 命令的事实源
6. dev_docs/（本体系）             ← 落地说明与实测补充，最低优先级
```

**冲突时一律以上层为准**，并请修正 `dev_docs` 中的对应内容。

---

## 2. 开工前必读三条

| # | 事项 | 出处 |
| ---: | ---- | ---- |
| 1 | 外部代码贡献**受邀制**，未受邀 PR 直接关闭 | `docs/contributing.md:3-17` |
| 2 | 禁止触碰 `CODEX_SANDBOX_*` 相关代码 | `AGENTS.md:8-10` |
| 3 | 禁止向 `docs/` 添加通用产品或用户文档（例外：app-server API 文档） | `AGENTS.md:32` |

---

## 3. 规则定位索引

按你要做的事查 `AGENTS.md` 的对应行号：

| 我要…… | 去看 |
| ---- | ---- |
| 写异步 trait 方法 | `AGENTS.md:25-28` |
| 写测试 | `AGENTS.md:29-31`、`:112-124` |
| 加文档 | `AGENTS.md:32` |
| 设计模块可见性 | `AGENTS.md:33` |
| 改配置类型 | `AGENTS.md:35` |
| 改 MCP 工具调用 | `AGENTS.md:36` |
| 改 Cargo 依赖 | `AGENTS.md:37-39` |
| 用 `include_str!` / `sqlx::migrate!` | `AGENTS.md:40-43` |
| 写辅助方法 | `AGENTS.md:44` |
| 加追踪 | `AGENTS.md:45-48` |
| 拆分/新增模块 | `AGENTS.md:49-61` |
| 跑测试与 lint | `AGENTS.md:62-72` |
| 往 `codex-core` 加东西 | `AGENTS.md:74-83` |
| 改高风险面 | `AGENTS.md:105-110` |
| 估算变更规模 | `AGENTS.md:125-131` |
| 写 TUI 样式 | `AGENTS.md:135` → `codex-rs/tui/styles.md` |
| 改 app-server 协议 | `AGENTS.md:277`、`:300-304` |
| 考虑平台支持 | `AGENTS.md:318`、`:321-322` |
| 判断 Python 版本要求 | `AGENTS.md:313-315` |

---

## 4. 文档体系导航

| 我想…… | 去看 |
| ---- | ---- |
| 总入口与场景导航 | [`AI_Coding_Context.md`](../../AI_Coding_Context.md) |
| 理解整体架构 | [`architecture_overview.md`](../../architecture_overview.md) |
| 找 crate / 决定新代码放哪 | [`crate_map.md`](../../crate_map.md) |
| 开发流程与命令 | [`development_workflow.md`](../../development_workflow.md) |
| 智能体核心循环 | [`core_agent_loop.md`](../../core_agent_loop.md) |
| 工具执行与沙箱 | [`tools_and_sandbox.md`](../../tools_and_sandbox.md) |
| app-server 协议 | [`app_server_protocol.md`](../../app_server_protocol.md) |
| 配置体系 | [`config_system.md`](../../config_system.md) |
| TUI 开发 | [`tui_guide.md`](../../tui_guide.md) |
| 测试 | [`testing_guide.md`](../../testing_guide.md) |
| 扩展 / 插件 / Skills / MCP | [`mcp_and_extensions.md`](../../mcp_and_extensions.md) |
| 认证与模型接入 | [`auth_and_providers.md`](../../auth_and_providers.md) |
| 构建与发布 | [`build_and_release.md`](../../build_and_release.md) |
| 会话与持久化 | [`session_and_persistence.md`](../../session_and_persistence.md) |
| 实验性能力面 | [`experimental_surfaces.md`](../../experimental_surfaces.md) |
| 遥测与数据边界 | [`observability.md`](../../observability.md) |
| SDK | [`sdk_guide.md`](../../sdk_guide.md) |

---

## 5. dev_docs 体系特有约定

以下不属于上游规范，是本文档体系自身的规则。

### 5.1 落盘与版本控制

| 约定 | 说明 |
| ---- | ---- |
| **产物路径固定 `dev_docs/`** | 禁止迁入 `docs/`（`AGENTS.md:32`） |
| **推送只推个人 fork** | 禁止 `git push origin`（`origin` 直连上游 `openai/codex`） |
| 框架软链接不入库 | `AI-Coding-Context` 已写入 `.git/info/exclude` |
| 不修改仓库根的 gitignore 文件 | 用本地 exclude 代替 |

### 5.2 脱敏（fork 为公开仓库，硬性门禁）

每批提交前必须跑，任一有输出即为 blocker：

```bash
# 1) 本地绝对路径（期望无输出）
grep -rnE "/Users/[A-Za-z0-9._-]+/" dev_docs/

# 2) 凭证样值（期望无输出）
grep -rniE "(api[_-]?key|token|secret|password|passwd|credential)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][A-Za-z0-9_-]{12,}" dev_docs/
```

| 禁止写入 | 允许写入 |
| ---- | ---- |
| 真实 API key、token、私钥的**值** | 变量名、配置键名、常量名、文件路径 |
| 本地绝对路径、主机名、内网地址、个人邮箱 | 公开服务端点（技术事实） |
| 测试夹具中的假 token | 夹具文件路径与字段名 |

### 5.3 证据等级（写文档时必须标注）

| 等级 | 来源 | 允许的措辞 |
| ---- | ---- | ---- |
| E1 | 目录结构、文件名、数量 | 只能写"疑似""待验证" |
| E2 | 配置、锁文件、README | 可写"已从配置确认" |
| E3 | 源码片段、调用链 | 可写"代码显示" |
| E4 | 实跑构建/测试/工具 | 可写"已验证" |

> [!WARNING]
> **最常见的错误是把 E1 的目录名推断写成 E3 的事实。** 本体系已有先例：四条扩展路径的关系曾被标为 E1 留白，直到第 3 批读了 `Cargo.toml` 才得出结论——**结果与最初的直觉推断并不一致**（见 `mcp_and_extensions.md` §1）。

### 5.4 其他

| 约定 | 说明 |
| ---- | ---- |
| `related_files` 只列**实际读过**的文件 | 不列未读文件 |
| 每篇文档记录基线 commit 与 `verified_at` | 便于漂移检测 |
| 数值类事实必须给可复现命令 | 不抄历史数字 |
| 未覆盖范围要显式列清单 | 不写空泛免责声明 |

---

## 6. 质量门禁

本体系的产物由 5 项 checker 校验：

```bash
P=AI-Coding-Context/tools
python3 $P/py/summary_validator.py --dir dev_docs --recursive --strict
python3 $P/py/doc_health_checker.py --full-check --doc-dir dev_docs
node    $P/js/doc_health_checker.js --full-check --doc-dir dev_docs
python3 $P/py/semantic_review_checker.py --full-check --doc-dir dev_docs --repo-root .
node    $P/js/semantic_review_checker.js --full-check --doc-dir dev_docs --repo-root .
```

全部要求 `exit_code = 0`。Python 与 JS 两套实现结果不一致时，**必须先修正或记录为 blocker**，不得豁免。

---

## 7. 提交前自检

```
□ just fmt                                   已跑
□ just test -p <crate>                       通过
□ 改了 common/core/protocol → just test       通过（先问用户）
□ 大改动 → just fix -p <crate>                已跑
□ 改了 Cargo 依赖 → just bazel-lock-update    已跑
□ 改了 ConfigToml → just write-config-schema  已跑
□ 改了 app-server API → just write-app-server-schema 已跑
□ 新增 include_str! → BUILD.bazel compile_data 已补
□ 变更行数 ≤ 800（复杂逻辑 ≤ 500）
□ 未触碰 CODEX_SANDBOX_*
□ 未向 docs/ 添加通用文档
□ 改了 dev_docs → 5 项 checker + 2 项脱敏扫描全绿
□ push 目标是 fork，不是 origin
```
