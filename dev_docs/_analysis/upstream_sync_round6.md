---
title: 第 6 轮上游同步作业单（基线 bb5054fe47 → 5c5308fc9a）
summary: 记录 2026-09-20 将 upstream/main 合入 zibuyu 分支后的文档同步作业：上游改动规模、事实基座重建结果（断言账本 29→33 条，26 条数值失效）、三项框架级语义变更（untrusted 审批白名单退役、Op::UserInput 更名为 TurnInput、mcp-server 与 core-skills crate 删除）、33 条死引用的逐条去向裁定，以及由此推导的十一个批次作业计划与受影响文档映射。
keywords: codex | upstream-sync | round6 | claim-ledger | broken-refs | framework-change | batch-plan
scope: dev_docs 文档体系第 6 轮上游同步的作业依据与进度基准
related_files: codex-rs/Cargo.toml | codex-rs/protocol/src/protocol.rs | codex-rs/cli/src/main.rs | codex-rs/shell-command/src/command_safety/is_dangerous_command.rs | codex-rs/ext/skills/src/loader/mod.rs | codex-rs/codex-mcp/src/lib.rs
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/claim_ledger.jsonl | dev_docs/_analysis/generation_progress.md
verified_at: 2026-09-20
---

# 第 6 轮上游同步作业单

> **本文件是作业依据，不是对外文档。** 它记录「上游变了什么」与「哪篇文档因此失效」，供第 6 轮逐批修订时逐条销账。

---

## 1. 本轮范围

| 项 | 值 |
| ---- | ---- |
| 合并动作 | `git merge main` → 合并提交 `67e6921373` |
| 旧基线 | `bb5054fe47`（2026-08-03） |
| 新基线 | `5c5308fc9a`（2026-09-20） |
| 跨越提交 | 2,230 个 |
| 文件改动 | 6,091 个，+817,079 / −152,246 行 |
| 合并冲突 | 无 |
| 分支纯净性 | 复核通过（`dev_docs/` 以外改动数 = 0） |

> [!NOTE]
> 合并的是 `upstream/main`（openai/codex，即本地 `main`）。`origin/main`（fork 镜像 `zibuyu2015831/codex`）当时仍停在旧基线 `bb5054fe47`，落后 2,230 个提交——**不要**把 fork 镜像当成上游真值。

### 规模漂移

| 维度 | 旧基线 | 新基线 | 变化 |
| ---- | ---- | ---- | ---- |
| Git 跟踪文件（不含 `dev_docs/`） | 5,913 | 8,297 | +40% |
| `.rs` 文件 | 2,858 | 4,631 | +62% |
| Rust 行数 | 1,270,789 | 1,858,112 | +46% |
| `cargo metadata` crate 数 | 134 | 154 | +20 |
| `[workspace] members` | 128 | 149 | +21 |
| `ext/*` crate | 12 | 15 | +3 |
| `utils/*` crate | 23 | 26 | +3 |
| CLI `Subcommand` 变体 | 27 | 30 | +3 |
| `Op` 枚举变体 | 26 | 28 | +2 |
| insta 快照 | 681 | 1,359 | +99% |
| `*_tests.rs` | 457 | 1,148 | +151% |

---

## 2. 方法论：批次 0–1 降级，批次 2 起恢复

`generation_plan.md`「审查方法：双轨交叉 + 修后复核」要求每篇文档同时派**核验轨 / 重推导轨 / 修订轨**三类独立代理，靠互相不可见来暴露「文档与源码都自洽但不同构」的框架性错误。

本轮的执行强度**分两段，不可一概而论**：

| 批次 | 方法 | 强度 |
| ---- | ---- | ---- |
| 0–1 | **单人分轨**：同一执行者串行承担三轨（先仅读源码重推导 → 再与文档差分 → 再落笔修订） | **降级** |
| 2 起 | **恢复双轨交叉**：每篇派独立的核验轨 + 重推导轨代理，重推导轨被明令禁止读取 `dev_docs/`；修订轨由主控承担，裁定与源码冲突时拒改并记录反证 | 符合原方法论 |

### 批次 0–1 的折价必须记住

降级的原因是当时的执行环境禁止派生子代理。**弱在同一执行者无法对自己隐藏文档内容**，「重推导」不可避免地被已读过的文档锚定——而这恰恰是**漏写类**与**叙事骨架类**问题唯一能被抓到的机制。

已采取的补偿：对每一处框架级判断强制给出可复现命令并写进断言账本（见 §3）。

**补偿是不充分的。** 实证依据就在本轮自己身上：批次 1 在逐篇回源时才发现四项门禁查不出的问题（见 §6 末尾），其中「app-server README 从 2,469 行缩到 316 行且 AGENTS.md 不再提及它」属于典型的叙事骨架失效——**账本与门禁对它完全无感**，它是被人读出来的。既然单人分轨下仍漏了这类问题多久无从得知，批次 0–1 的产物应在批次 10 的复核轮中**重新过一遍重推导轨**，不可因「当时已核验过」而跳过。

---

## 3. 事实基座重建结果

断言账本 `dev_docs/_analysis/claim_ledger.jsonl` 从 29 条扩到 **33 条**，其中 **26 条数值失效已更新**、**1 条断言语义重写**、**4 条新登记**。全部 33 条已复验通过。

### 3.1 工装缺陷（本轮修复）

| 缺陷 | 表现 | 修复 |
| ---- | ---- | ---- |
| `workspace_crates` 的 verify 用裸 `cargo` 且 `2>/dev/null` | cargo 不在 PATH 的环境下**静默失败**，checker 只报「命令执行失败」而非「数值错误」 | 改为 `PATH="$PATH:$HOME/.cargo/bin" cargo ... --offline`，不再吞 stderr |
| `sqlite_migration_files` 的 verify **硬编码 5 个目录名** | 上游新增 `queue_migrations` 后，新目录被静默漏计，实测值 67 看着"只是漂移"，实际口径已错 | 改为通配 `codex-rs/state/*migrations*/` |
| `realtime_op_variants`（新登记）首版 verify 用裸 grep | 协议文件中 `EventMsg` 另有 5 个 RealtimeConversation 前缀变体，与 `Op` 的 6 个混计为 11 | 改为限定在 `Op` 枚举体内计数 |

这三条都属于同一类：**verify 命令自身会随上游结构变化而失去原口径**。账本的价值依赖 verify 的口径稳定性，此后新增条目应优先用通配与结构化解析，避免硬编码清单。

### 3.2 数值更新一览

| id | 旧值 | 新值 |
| ---- | ---- | ---- |
| `workspace_crates` | 134 | 154 |
| `workspace_members_listed` | 128 | 149 |
| `utils_crates` | 23 | 26 |
| `ext_crates` | 12 | 15 |
| `ext_with_extension_api` | 8 / 12 | 11 / 15 |
| `ci_workflows` | 27 | 30 |
| `insta_snapshots` | 681 | 1,359 |
| `tests_rs_files` | 457 | 1,148 |
| `config_schema_keys` | 93 | 100 |
| `ts_v2_schema_files` | 550 | 631 |
| `agents_md_bytes` | 22,519 | 22,397 |
| `rust_files` | 2,858 | 4,631 |
| `rust_loc` | 1,270,789 | 1,858,112 |
| `tracked_files_upstream` | 5,913 | 8,297 |
| `shipped_aux_binaries` | 6 | 7 |
| `cli_subcommand_variants` | 27（Linux 23 / mac·win 24） | 30（Linux 25 / mac·win 26） |
| `op_variants` | 26 | 28 |
| `op_variants_matched_in_submission_loop` | 26 | 28 |
| `core_total_lines` | 296,963 | 402,720 |
| `sqlite_migration_files` | 55（5 目录） | 69（6 目录） |
| `sqlx_migrate_call_sites` | 5 | 6 |
| `compression_worker_call_sites` | 7 命中 / 1 生产调用点 | 7 命中 / **3 生产调用点** |
| `tui_legacy_core_usages` | 93 处 / 40 文件 | 165 处 / 82 文件 |
| `codex_config_lines_rs_only` | 21,034 | 29,374 |
| `codex_config_lines_src_all` | 21,167 | 29,515 |
| `tokio_spawn_sites_core_tui` | 131 | 166 |

未变：`submission_channel_capacity`（512）、`session_io_async_channel_pair`（2）。

### 3.3 新登记条目

| id | 断言 |
| ---- | ---- |
| `realtime_op_variants` | `Op` 枚举中 `RealtimeConversation*` 变体共 6 个 |
| `guardian_crates` | Guardian 子系统由 3 个 crate 组成 |
| `mcp_server_crate_absent` | `codex-rs/mcp-server` crate 已不存在 |
| `core_skills_crate_absent` | `codex-rs/core-skills` crate 已不存在 |

---

## 4. 框架级变更（不是数值漂移）

以下三项**推翻了现有文档的叙事骨架**，逐条核验每句话都可能「单看没错」，必须整段重写。

### 4.1 untrusted 审批策略的白名单已整体退役

**上游提交**：`942af8447b` — *Retire the untrusted approval policy (#39630)*

- `codex-rs/shell-command/src/command_safety/is_safe_command.rs` 整个模块被删除 <!-- ref-exempt: 反例——正文说明的正是该路径已不存在 -->
- 函数 `is_safe_command()` 与 `is_known_safe_command()` 全仓归零
- `AskForApproval::UnlessTrusted` 变体**仍在**，但文档注释已改写：

| | 旧基线语义 | 新基线语义 |
| ---- | ---- | ---- |
| 判定机制 | **白名单**：只自动批准 `is_safe_command()` 认定的只读安全命令 | **规则制**：除非 execpolicy 有显式规则允许，否则一律需要审批 |
| 定位 | 面向用户的审批档位 | 「Internal policy for projects marked untrusted」——内部策略 |

`command_safety/` 目录下现只剩 `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` 这条**黑名单**通路。**极性翻转了**：从「列举什么是安全的」变成「列举什么是危险的」。

> 陷阱：`is_safe_command` 这个**模块名**在旧文档里被当成函数名写过（账本 `is_safe_command_absent` 原本就是为纠这个错而登记的）。本轮它从「名字写错」升级成「整个概念不存在」，旧账本条目的 expected 仍是 0，**数值没变但断言含义完全不同**——这正是门禁全绿仍不充分的典型例子。

**受影响**：`dev_docs/tools_and_sandbox.md`、`dev_docs/learn/07-security.md`、`dev_docs/learn/13-patch-and-exec-policy.md`、`dev_docs/architecture_overview.md` 的安全章节。

### 4.2 `Op::UserInput` 更名为 `Op::TurnInput`

`Op` 枚举 26 → 28：

- 新增：`TurnInput`、`TurnSettings`、`RecoverTurn`、`SuspendTurnAndShutdown`
- 删除：`UserInput`、`ThreadRollback`

`UserInput` → `TurnInput` 是**重命名**，而 `UserInput` 是现有文档描述「一句话如何进入内核」时的主角符号。凡写 `Op::UserInput` 的段落全部失效。

**受影响**：`dev_docs/core_agent_loop.md`、`dev_docs/learn/03-protocol.md`、`dev_docs/learn/32-rust-for-python-readers.md`（三篇经 grep 确认命中）。

`ThreadRollback` 的删除另需确认回滚能力是改由 `RecoverTurn` 承担还是整体移除——留待批次 2 回源判定。

### 4.3 `mcp-server` 与 `core-skills` 两个 crate 被删除

| crate | 上游提交 | 去向 |
| ---- | ---- | ---- |
| `codex-rs/mcp-server` <!-- ref-exempt: 反例——正文说明该 crate 已不存在 --> | `531f3836a1` *Remove the deprecated `codex mcp-server` command (#42993)* | **能力整体删除，非迁移**（见下方更正）；CLI 的 `McpServer` 子命令一并删除，`Mcp` 保留但方向相反（管理外部服务器） |
| `codex-rs/core-skills` <!-- ref-exempt: 反例——正文说明该 crate 已不存在 --> | `33e365b19e` *Remove the legacy core skill loader (#37457)* | 技能加载迁至 `codex-rs/ext/skills/src/loader/`（新结构含 `dynamic_skill_selector` 一整套检索器）；样例技能资产在 `codex-rs/skills/src/assets/` |

`mcp_and_extensions.md` 全篇以 `mcp-server` crate 为叙事骨架（18 个 ERROR 中 8 个指向它），属于**整篇重写**而非修补。

> [!CAUTION]
> **本节的 `mcp-server` 去向判定曾经写错，错误出自本作业单自身，已于批次 3 期间更正。**
>
> 批次 0 最初把去向记为「服务端能力归入 `codex-rs/codex-mcp`」，批次 1 的 `crate_map.md` 沿用了它。**实测证伪**：
>
> ```bash
> grep -rn 'codex_tool_runner\|codex_tool_config\|CodexToolCallParam' --include='*.rs' codex-rs/   # 0
> grep -n '^pub ' codex-rs/codex-mcp/src/lib.rs   # 导出全是客户端侧：McpBinding / McpResourceClient / connection_manager …
> ```
>
> 上游提交信息原文也写明是删除而非迁移：「Remove the `codex mcp-server` subcommand and the standalone `codex-mcp-server` crate, including its tests, interface documentation, build dependencies, and run recipe」。这同时解释了 `codex-rs/docs/codex_mcp_interface.md` 为什么消失——它就是那句「interface documentation」。 <!-- ref-exempt: 反例——正文说明该路径已被同一提交删除 -->
>
> 保留的 `Mcp` 子命令方向**相反**：`codex-rs/cli/src/main.rs:170` 写的是「Manage **external** MCP servers for Codex」。
>
> **教训**：错误的根源是一个未经检验的隐含假设——「crate 被删 ⇒ 它的能力必然迁去了某处」。**能力可以就这么没了。** 裁定死引用去向时，「无对应」必须是一个和「迁移到 X」同等正当的结论，否则就会被迫编出一个去处。本作业单 §5 的裁定原则里已写了「禁止顺手改路径蒙混过关」，但这一条当时仍然没挡住——因为它防的是路径级的敷衍，防不住**能力级的想当然**。
>
> 另注：这两个批次正是在 §2 所述**单人分轨降级**条件下完成的，本条是该折价的又一个实证样本。

---

## 5. 死引用去向裁定（33 条去重 / 73 次引用）

裁定原则：能在新树中找到**同名同责**的文件才记「迁移」；仅文件名相同但职责不同的记「无对应」，禁止顺手改路径蒙混过关。

| 失效路径 | 引用次数 | 裁定 |
| ---- | ---- | ---- |
| `codex-rs/core-skills/src/loader.rs` <!-- ref-exempt: 已失效路径清单 --> | 12 | 迁移 → `codex-rs/ext/skills/src/loader/mod.rs`（结构已重组，非一对一） |
| `codex-rs/thread-store/src/local/writer_lock.rs` <!-- ref-exempt: 已失效路径清单 --> | 8 | 迁移 → `codex-rs/rollout/src/writer_lock.rs` |
| `codex-rs/mcp-server/src/lib.rs` <!-- ref-exempt: 已失效路径清单 --> | 6 | crate 删除，**能力整体消失，无任何对应**（见 §4.3 的更正） |
| `codex-rs/core/src/session/config_lock.rs` <!-- ref-exempt: 已失效路径清单 --> | 4 | **无对应**，全仓无同名文件，需回源确认机制是否还在 |
| `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs` <!-- ref-exempt: 已失效路径清单 --> | 3 | 迁移 → `codex-rs/core/src/tools/runtimes/zsh_fork/unix_escalation.rs` |
| `codex-rs/core/src/guardian/policy.md` <!-- ref-exempt: 已失效路径清单 --> | 3 | 迁移 → `codex-rs/prompts/templates/guardian/policy.md` |
| `codex-rs/docs/codex_mcp_interface.md` <!-- ref-exempt: 已失效路径清单 --> | 2 | 删除；`codex-rs/docs/` 现只剩 `bazel.md` 与 `protocol_v1.md` |
| `codex-rs/sandboxing/src/restricted_read_only_platform_defaults.sbpl` <!-- ref-exempt: 已失效路径清单 --> | 2 | 更名 → `codex-rs/sandboxing/src/seatbelt_read_only_platform_defaults.sbpl` |
| `codex-rs/core/src/audio_preparation.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | 迁移 → 新 crate `codex-rs/utils/audio/` |
| `codex-rs/mcp-server/src/message_processor.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | crate 删除；`codex-rs/app-server/src/message_processor.rs` 是**另一条通路**，不可直接改指 |
| `codex-rs/core/src/context/permissions_instructions.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | 迁移 → `codex-rs/prompts/src/permissions_instructions.rs` |
| `codex-rs/core/src/tools/runtimes/shell.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | 重组 → `runtimes/` 下现为 `zsh_fork.rs` / `unified_exec.rs` / `apply_patch.rs`，需回源判定职责对应 |
| `codex-rs/core/src/compact_remote.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | 重组 → `compact_remote_v2.rs` / `compact_remote_history.rs` 等 6 个文件 |
| `codex-rs/core/src/compact_remote_request.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | **无对应** |
| `codex-rs/mcp-server/Cargo.toml` <!-- ref-exempt: 已失效路径清单 --> | 2 | crate 删除 |
| `codex-rs/core/tests/suite/compact_remote_parity.rs` <!-- ref-exempt: 已失效路径清单 --> | 2 | **无对应**；同目录现有 `compact_remote.rs` / `compact_remote_trimming.rs` |
| `.devcontainer/*`（6 个文件） <!-- ref-exempt: 已失效路径清单 --> | 6 | **目录整体删除**，devcontainer 这条开发环境入口已不存在 |
| `codex-rs/core/src/bin/config_schema.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → 新 crate `codex-rs/config-schema/src/main.rs`（产物 `codex-rs/core/config.schema.json` 路径不变） |
| `codex-rs/core/src/config/agent_roles.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → 新 crate `codex-rs/agent-roles/` |
| `codex-rs/shell-command/src/command_safety/is_safe_command.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | **删除，概念退役**（见 §4.1） |
| `codex-rs/ext/extension-api/src/capabilities/agent.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | **无对应**；capabilities 现为 `conversation_history` / `events` / `metrics` / `response_items` |
| `codex-rs/ext/mcp/src/executor_plugin.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 重组 → `plugin.rs` / `plugin_contributor.rs` / `plugin_providers.rs` |
| `codex-rs/core-skills/src/loader/discovery.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → `codex-rs/ext/skills/src/loader/discovery.rs` |
| `codex-rs/core-skills/src/injection.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → `codex-rs/core/src/plugins/injection.rs`（需确认职责是否等同） |
| `.codex/skills/pushing-ci-changes/SKILL.md` <!-- ref-exempt: 已失效路径清单 --> | 1 | 删除；`.codex/skills/` 现为 `babysit-pr` / `code-review*` / `codex-pr-body` 等 10 项 |
| `codex-rs/thread-store/src/local/writer_lock_tests.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → `codex-rs/rollout/src/writer_lock_tests.rs` |
| `codex-rs/core/src/guardian/metrics.rs` <!-- ref-exempt: 已失效路径清单 --> | 1 | **无对应**；`core/src/guardian/` 目录仍在但文件集已全换 |
| `codex-rs/core/src/guardian/policy_template.md` <!-- ref-exempt: 已失效路径清单 --> | 1 | 迁移 → `codex-rs/prompts/templates/guardian/policy_template.md` |

**统计**：迁移可改指 12 条 / 重组需回源 4 条 / 无对应需重写 6 条 / 整体删除 11 条（含 `.devcontainer` 6 个）。

---

## 6. 受影响文档与批次计划

ERROR 集中度（合并后首测，共 97 ERROR / 207 WARN）：

| 文档 | ERROR | 主要成因 |
| ---- | ---- | ---- |
| `core_agent_loop.md` | 20 | `Op::UserInput` 更名 + runtimes 重组 |
| `mcp_and_extensions.md` | 18 | `mcp-server` crate 删除（叙事骨架失效） |
| `session_and_persistence.md` | 10 | `writer_lock` 迁移 + compaction 通路改动 |
| `tools_and_sandbox.md` | 9 | 白名单退役 + sbpl 更名 |
| `build_and_release.md` | 7 | `.devcontainer` 删除 + 交付二进制 +1 |
| `config_system.md` / `crate_map.md` | 各 5 | schema 生成器迁 crate / crate 数大变 |
| 其余 16 篇 | 1–3 | 零散 |

| 批次 | 内容 | 状态 |
| ---- | ---- | ---- |
| 0 | 事实基座重建与工装修复（本文件 + 账本） | ✅ 完成 |
| 1 | `crate_map.md` / `architecture_overview.md`（其余各篇的事实基础，须先定稿） | ✅ 完成（两篇引用类 ERROR 归零） |
| 2 | `core_agent_loop.md` / `tools_and_sandbox.md` / `session_and_persistence.md` | ✅ 完成（三篇引用类 ERROR 归零；后两篇恢复双轨交叉，核验轨分别判定 79 / 174 条 WRONG） |
| 3 | `config_system.md` / `auth_and_providers.md` | ⬜ |
| 4 | `app_server_protocol.md` / `mcp_and_extensions.md`（重写） / `sdk_guide.md` | ⬜ |
| 5 | `build_and_release.md` / `development_workflow.md` / `testing_guide.md` / `observability.md` | ⬜ |
| 6 | `tui_guide.md` / `experimental_surfaces.md` | ⬜ |
| 7 | 新专题：语音/实时子系统、Guardian v2 | ⬜ |
| 8 | `learn/` 20 篇 | ⬜ |
| 9 | 主文档 / `AI_RULES.md` / `_analysis/` / `diagrams/` | ⬜ |
| 10 | 门禁全绿 + 重推导复核轮 | ⬜ |

### 新子系统落位（用户已定：重点子系统新开专题）

| 子系统 | 组成 | 处置 |
| ---- | ---- | ---- |
| 语音 / 实时 | `voice-host`、`realtime-webrtc`、`utils/audio`、`third_party/voice`、`Op::RealtimeConversation*` 6 变体 | **新开专题**（批次 7） |
| Guardian v2 | `guardian-context`、`ext/guardian-v2`、`ext/guardian-reviewer`、`core/src/guardian/`、`prompts/templates/guardian/` | **新开专题**（批次 7） |
| 其余 18 个新 crate | `agent-roles`、`attachment-store`、`build-info`、`config-schema`、`diagnostics`、`history`、`mermaid`、`mxc-sandbox`、`otel-trace-websocket`、`tcp-tunnel`、`user-verification`、`windows-sandbox-service`、`workload-identity`、`worktree`、`utils/git-discovery`、`utils/redacted-string`、`ext/history-notes`、`ext/queue` | 在 `crate_map.md` 登记定位（批次 1），相关机制并入对应专题 |

> 这 18 个 crate 的 `Cargo.toml` **均无 `description` 字段**，职责只能从 `lib.rs` 文档注释与调用方回源推导——批次 1 的主要工作量在此，不可凭 crate 名猜测。 <!-- ref-exempt: 泛指任意 crate 的清单文件与入口文件，不指某一个具体路径 -->

---

## 7. 门禁状态基线

批次 0 结束时的门禁实测（供后续批次对照收敛）：

| 检查 | 合并后首测 | 批次 0 结束 | 批次 1 结束 | 批次 2 结束 |
| ---- | ---- | ---- | ---- | ---- |
| 脱敏 | 7 类全通过 | 7 类全通过 | 7 类全通过 | 7 类全通过 |
| 引用可解析性 | 97 ERROR / 207 WARN | 未变（正文尚未修订） | 89 ERROR / 202 WARN | **50 ERROR / 179 WARN** |
| 跨文档对账与账本 | 35 个问题 | 33 条账本全部复验通过 | 10 个问题 | 无不一致（已定稿 5 篇无一命中） |

引用类 ERROR 将随批次 2–9 逐步归零；**门禁全绿仍是必要非充分条件**，§2 的方法论折价在本轮尤其需要记住。

### 批次 1 的额外发现（不在合并时的失效清单里）

以下四项**门禁查不出**，是逐篇回源时才浮现的，全部已写入对应文档：

| 发现 | 性质 | 落点 |
| ---- | ---- | ---- |
| `codex-tui` 行数（405,863）**首次超过** `codex-core`（402,720） | 「代码量第一」易主，但 core 自身仍涨 36%，减负压力未减 —— **排名变化来自分母** | `crate_map.md` §6、`architecture_overview.md` §1 |
| `codex-rs/app-server/README.md` 从 2,469 行缩到 **316 行**，且 `AGENTS.md` 已完全不再提及它（`grep 'README.md' AGENTS.md` 零命中） | 它**不再是 app-server API 的权威文档**，形态已变为逐特性增量说明 | `architecture_overview.md` §11 |
| `extension-api` 的能力 trait **数量不变（4 个）但成员换了一个**：`AgentSpawner` 删除、`ConversationHistorySnapshot` 新增 | 「数字没变但集合变了」，只核对计数的检查抓不到 | `crate_map.md` §3.8 |
| `AGENTS.md:264-265` 指向的 `app-server-protocol/src/protocol/v2.rs` **不存在**（v2 已改为目录形态） <!-- ref-exempt: 反例——正文说明 AGENTS.md 给出的该路径不可解析 --> | 第四条「AGENTS.md 自身陈旧记载」 | `dev_docs/architecture_overview.md` §11，待批次 9 登记进 `AI_RULES.md` |

另有三处口径级修正：扩展 trait 数 13→**16**（此前漏掉 4 个不以 `Contributor` 结尾的）；`codex-rs/cli/src/main.rs` 的默认 TUI 分支已从 `None =>` 变为 `None | Some(Subcommand::Agents(_)) =>`（「默认 TUI 只由 `None` 触发」不再成立）；`[workspace.dependencies]` 的 path 条目数用 `grep -c 'path\s*='` 会因 `..._path =` 子串命中而虚高 2。

### 批次 2 的额外发现

本批恢复双轨交叉后，核验轨对两篇给出的失效率分别是 **79/197** 与 **174/295（59%）**，共六 + 三处叙事骨架失效。除各文已就地记载外，有四条跨篇的方法论教训值得单列：

| 教训 | 出处 | 说明 |
| ---- | ---- | ---- |
| **只核验被引用的函数、不追调用方，会漏掉整类错误** | `tools_and_sandbox.md` §3 | 「seccomp 被网络策略门控」在函数级至今为真，门控函数与反证测试都还能通过；但调用点加了一条 `.or_else()` 兜底，实际语义翻转为「除全盘写档外恒装」。**这是最容易「看着还对、实则已错」的形态。** |
| **「我找到了唯一的调用点」这个结论本身会过期** | `session_and_persistence.md` §2.2 | 压缩工作器从 1 个生产调用点增至 3 个，且新增的 RPC 入口**门禁与老入口完全不同**（不看那个特性开关）。绝对化措辞必须配穷举命令，并每轮重跑。 |
| **在已消失的机制上做精细考据，考据越细误导越深** | `tools_and_sandbox.md` §8、`core_agent_loop.md` §5.1 | 旧版整块在教读者「`is_safe_command()` 不存在，真名是 `is_known_safe_command()`，grep 不到定义是因为你名字写错了，**别以为函数被删了**」——而真相恰恰是函数真的被删了，连它引用的两处「旧名残留注释」也一处已改写、一处路径都不存在。 |
| **唯一证据消失时应删结论，而不是找个相近符号圆回来** | `core_agent_loop.md` §4.2 | `tool_waits_for_runtime_cancellation` 全仓零命中，由它推出的「不同工具取消等待行为不同」已整条删除并注明未取证。**留空比编一个替代证据诚实。** |

另有两处「数字没变但集合变了」，与批次 1 的 `AgentSpawner` 那条同类：`codex-rs/linux-sandbox/src/landlock.rs` 的 `deny_syscall` 仍是 19 处但新增了 `process_vm_writev` 与 3 条 `io_uring_*`；`extension-api` 能力 trait 仍是 4 个但换了一个成员。**只对数字的检查对这一类完全无感。**
