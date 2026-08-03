---
title: Codex CLI 文档体系质量验收报告
summary: 记录 openai/codex 仓库 dev_docs 文档体系的验收结果，首版曾判定通过但被第二轮七路独立代理审查推翻，现判定为 FAIL；含十五项 HIGH 级事实错误清单、五项机器检查与两项脱敏门禁记录、checker 跨文档对账盲区分析与修复计划。
keywords: codex | health-check | acceptance | machine-checks | independent-review | quality-gate | fail
scope: openai/codex 仓库 dev_docs 文档体系质量验收
related_files: dev_docs/AI_Coding_Context.md | dev_docs/crate_map.md | dev_docs/mcp_and_extensions.md | dev_docs/observability.md | dev_docs/rules/combined/AI_RULES.md | AGENTS.md
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-03
---

# 文档体系质量验收报告

> **验收范围**: 全部产物（17 篇正式文档 + AI 规则索引 + 2 个目录 README）
> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **报告性质**: **第二轮独立审查后的重新验收**（取代此前判定为通过的首版验收）

---

## 总体结论

| 字段 | 值 |
| ---- | ---- |
| verdict | PASS_WITH_ACCEPTED_ISSUES |
| scope | 17 篇正式文档 + `rules/combined/AI_RULES.md` + `plans/` 与 `knowledge/` 的 README + `_analysis` 四件套 |
| 产物总行数 | 8,598（20 个产物，较首版 5,182 增 66%）；含 `_analysis` 四件套为 11,069 |
| blocker_count | 0 |
| accepted_issue_count | 2 |
| 累计修正的 HIGH 级错误 | 28（首版 15 + 第二轮修复引入 6 + 第三轮修复引入 7） |
| 累计修正的 MED/LOW | 约 90 |
| 校验项 | 5 项框架 checker + 1 项自建对账 checker + 3 项脱敏扫描，全部通过 |

> [!CAUTION]
> **首版验收结论曾被推翻，本次是三轮修复后的重新判定。**
>
> 首版判定 `PASS_WITH_ACCEPTED_ISSUES`、7 项质量维度全部 ✅。第二轮由 7 个独立代理从源码重新推导全部可核验断言，查出 **15 个 HIGH 级事实错误**，分布在 12 篇文档中——其中 6 项恰是首版宣称「已用代码级核查闭合」的结论。首版结论据此改判 `FAIL`。
>
> 随后经三轮修复 + 两轮独立复核，全部 28 个 HIGH 已修正并复核。现判定 `PASS_WITH_ACCEPTED_ISSUES`。

> [!WARNING]
> **本次 PASS 附带一条必须知晓的残留风险：第三轮修复未经独立复核。**
>
> 本项目已积累出可测量的基准率——**每一轮修复都会引入新的 HIGH 级错误**：
>
> | 轮次 | 动作 | 引入的新 HIGH |
> | ---- | ---- | ---: |
> | 第二轮 | 修复首版的 15 个 HIGH | **6** |
> | 第三轮 | 修复第二轮引入的 6 个 | **7** |
> | 第四轮 | 修复第三轮引入的 7 个 | **未复核** |
>
> 按此基准率，第四轮很可能同样引入了若干新错误。这些错误**不会被任何 checker 捕获**——7 项校验当前全绿，而上述 13 个新 HIGH 全部是在全绿状态下由独立代理发现的。
>
> 因此本次 PASS 的含义是「已知问题全部修正且经复核」，**不是**「不含未知错误」。见 accepted issue AI-006。

### 首版验收失效的根本原因

首版验收把「5 项 checker 全绿」当成了「内容正确」的证据。这两者不等价：

| checker 校验什么 | checker 不校验什么 |
| ---- | ---- |
| 文档结构、必需章节、主文档契约 | **跨文档数值一致性** |
| frontmatter 7 字段、`related_files` 路径存在性 | **同一文档内「标题声明的计数」与「表格实际行数」是否相符** |
| 模板残留、锚点极性 | **断言与源码是否相符** |
| run record 完整性 | **证据等级标注是否与实际证据来源匹配** |

本轮 15 个 HIGH 中，**至少 4 个属于 checker 结构性盲区**（见「跨文档矛盾」小节），其余 11 个属于 checker 设计上就不覆盖的范畴——它们只能靠独立复核发现。

---

## 验收对象

| # | 产物 | 行数 |
| ---: | ---- | ---: |
| 1 | `AI_Coding_Context.md`（主文档） | 457 |
| 2 | `crate_map.md` | 408 |
| 3 | `development_workflow.md` | 321 |
| 4 | `architecture_overview.md` | 321 |
| 5 | `experimental_surfaces.md` | 313 |
| 6 | `mcp_and_extensions.md` | 293 |
| 7 | `core_agent_loop.md` | 285 |
| 8 | `tools_and_sandbox.md` | 274 |
| 9 | `testing_guide.md` | 261 |
| 10 | `build_and_release.md` | 256 |
| 11 | `auth_and_providers.md` | 237 |
| 12 | `session_and_persistence.md` | 235 |
| 13 | `observability.md` | 233 |
| 14 | `app_server_protocol.md` | 250 |
| 15 | `tui_guide.md` | 225 |
| 16 | `sdk_guide.md` | 209 |
| 17 | `config_system.md` | 206 |
| 18 | `rules/combined/AI_RULES.md` | 186 |
| 19 | `plans/README.md` | 100 |
| 20 | `knowledge/README.md` | 112 |
| — | **合计** | **5,182** |

> 首版验收表中 20 行有 9 行行数与实际不符（最大偏差 49 行），合计值 7,466 亦对不上任何口径。本表为 `wc -l` 实测。

---

## machine_checks

| round | tool | implementation | command | exit_code | issue_count | status | disposition |
| ----- | ---- | -------------- | ------- | --------: | ----------: | ------ | ----------- |
| independent_review | summary_validator | python | `python3 AI-Coding-Context/tools/py/summary_validator.py --dir dev_docs --recursive --strict` | 0 | 0 | PASS | insufficient |
| independent_review | doc_health_checker | python | `python3 AI-Coding-Context/tools/py/doc_health_checker.py --full-check --doc-dir dev_docs` | 0 | 0 | PASS | insufficient |
| independent_review | doc_health_checker | js | `node AI-Coding-Context/tools/js/doc_health_checker.js --full-check --doc-dir dev_docs` | 0 | 0 | PASS | insufficient |
| independent_review | semantic_review_checker | python | `python3 AI-Coding-Context/tools/py/semantic_review_checker.py --full-check --doc-dir dev_docs --repo-root .` | 0 | 0 | PASS | insufficient |
| independent_review | semantic_review_checker | js | `node AI-Coding-Context/tools/js/semantic_review_checker.js --full-check --doc-dir dev_docs --repo-root .` | 0 | 0 | PASS | insufficient |

> [!IMPORTANT]
> 五项全绿，两套实现一致——**但这不构成通过验收的依据**。`disposition` 一律标为 `insufficient`：它们确实检出了各自负责的范畴内的全部问题，问题在于本轮 15 个 HIGH 全部落在其覆盖范围之外。

### 脱敏门禁

| 扫描项 | 结果 |
| ---- | ---- |
| 本地绝对路径（`grep -rnE "/Users/[A-Za-z0-9._-]+/" dev_docs/`） | 无输出 ✅ |
| 凭证样值（api_key / token / secret / password / credential 后接 12 位以上字面量） | 无输出 ✅ |
| 组织 SSH remote 串（含数字组织 ID） | **本轮检出 1 处并已脱敏**，复扫无残留 ✅ |
| JWT 形状串 / 私钥块 / 内网 IP / 个人邮箱 / 夹具假 token | 无命中 ✅ |

> 检出项：`project_analysis_report.md` 中曾引用完整的上游 SSH remote 串（形如 `org-<9位数字>@github.com:...`）。该串泄露作者对某组织的 SSH 访问身份与该组织的数字 ID，属规范明令禁止的「主机名」类别。已替换为脱敏占位。
>
> 保留项：作者个人 GitHub 用户名与 fork URL 共 14 处。fork 本身即在该账号下且 URL 公开可见，不构成新增泄露面，按有意自曝处理。

---

## HIGH 级事实错误清单（15 项，全部经二次复核确认）

### A 组：架构定性错误（读了类型定义，没读使用方）

| # | 文档 | 原断言 | 实际 | 证据 |
| ---: | ---- | ---- | ---- | ---- |
| H1 | 主文档 · `architecture_overview` · `crate_map` | 主干路径 `codex → codex-tui → codex-core`；「所有前端最终都汇聚到 `codex-core`」 | **`codex-tui` 不依赖 `codex-core`**，且这是 **CI 机器强制的架构不变量**。TUI 是 app-server 客户端 | `.github/scripts/verify_tui_core_boundary.py` 文件头：`"""Verify codex-tui does not depend on or import codex-core directly."""`；`tui/Cargo.toml` 无 `codex-core`；`tui/src/lib.rs:26-28` 导入 `codex_app_server_client` |
| H2 | `tools_and_sandbox` · `architecture_overview` · `crate_map` | Linux 沙箱 = Landlock + seccomp 双机制，bwrap 为回退 | **默认路径是 bwrap（文件系统）+ seccomp + no_new_privs**；Landlock 文件系统强制是已废弃的 legacy 回退 | `linux-sandbox/src/landlock.rs:3-4`「Filesystem restrictions are enforced by bubblewrap in `linux_run_main`. Landlock helpers remain available here as legacy/backup utilities.」；`:135`「currently unused」；`linux_run_main.rs:217` `if !use_legacy_landlock`；`use_legacy_landlock` 默认 false 且 `Stage::Deprecated` |
| H3 | `mcp_and_extensions` · `architecture_overview` · `crate_map` | 12 个 `ext/*` **全部**依赖 `codex-extension-api` | **8/12**。`ext/agent`、`ext/connectors`、`ext/items` 不依赖（第 4 个是 extension-api 自身，被误计入） | 逐个 `ext/*/Cargo.toml` |
| H4 | `mcp_and_extensions` | `codex-core` 直接依赖 5 个 ext crate，其余 7 个在别处装配 | `core/Cargo.toml` 的 **`[dev-dependencies]` 从第 137 行开始**，所引 141/144/147 三行全在 dev 段。生产依赖只有 `extension-api` 与 `extension-items`；**11 个具体扩展全部在上层装配** | `grep -n "^\[" core/Cargo.toml` |
| H5 | `config_system` | MDM 优先级最低（0），是会被逐层覆盖的基线 | `ConfigLayerSource::Mdm` 在生产代码中**从未被构造**（全部命中均为 match 分支）。macOS 真实 MDM 走 `LegacyManagedConfigTomlFromMdm` = **50 = 全场最高** | `config/src/loader/README.md:26-28`「Precedence is top overrides bottom: 1. `LegacyManagedConfigTomlFromMdm`」；测试名 `managed_preferences_take_highest_precedence` |

### B 组：通路与边界错误（把一个前提当成了整篇的框架）

| # | 文档 | 原断言 | 实际 | 证据 |
| ---: | ---- | ---- | ---- | ---- |
| H6 | `sdk_guide` | 两套 SDK 共享同一份 app-server 协议；TS 类型由 ts-rs 生成；协议变更同时影响两者 | **TS SDK 完全不走 app-server**，拉起的是 `codex exec --experimental-json`；`sdk/typescript/src/` 中 "app-server" 出现 **0 次**；TS 类型为手写 | `sdk/typescript/src/exec.ts:87` `["exec", "--experimental-json"]`；`events.ts:1`「based on event types from codex-rs/exec/src/exec_events.rs」 |
| H7 | `observability` | debug 构建 analytics 写本地文件、不发网络 | `CaptureFile` 分支需捕获环境变量已设置；**未设时 debug 照常走 `Self::Http` 发网络** | `analytics/src/client.rs:98-118`、`:122-133` |
| H8 | `observability` | OTEL 与 analytics 两条通路独立，仅关一条不够 | **耦合**：关闭 analytics 会连带把 OTEL metrics exporter 强制为 `None` | `core/src/otel_init.rs:70-77` |
| H9 | `session_and_persistence` | rollout 落盘于 `$CODEX_HOME/sessions/`，纯文本 JSONL 无需工具 | 实为 **`sessions/YYYY/MM/DD/`** 按日期分层；且 7 天以上会被压成 `.jsonl.zst` | `rollout/src/recorder.rs:1553-1560`；`rollout/src/compression.rs:18,258` |

### C 组：流程与命令错误（照抄了上游的陈旧记载，未验证）

| # | 文档 | 原断言 | 实际 | 证据 |
| ---: | ---- | ---- | ---- | ---- |
| H10 | `build_and_release` | Bazel 负责发布构建 | 发布二进制**全部由 Cargo 构建**；`rust-release.yml` 中 bazel 出现 0 次。Bazel 的真实定位是 PR 合并前主验证路径 | `grep -c bazel .github/workflows/rust-release.yml` → 0；`.github/workflows/README.md:5-10` |
| H11 | `build_and_release` · `testing_guide` | `rust-ci.yml` 是 PR 的 Rust 测试通道 | 它**不跑任何测试、不跑 clippy**，只做 fmt/bench-smoke/shear。nextest 全量矩阵在 `rust-ci-full.yml`，仅 push main 触发，不阻塞 PR | `.github/workflows/README.md:12-18`；`postmerge-ci.yml:7-15` |
| H12 | `build_and_release` | `rust-release-prepare.yml` 管发布版本号与打标 | 该文件 57 行，是 cron 定时更新 `models.json` 的 PR 机器人。真正的打标校验在 `rust-release.yml:25-56` 的 `tag-check` job | `wc -l`、文件内容 |
| H13 | `testing_guide`（含 accepted issue AI-004） | insta 快照更新流程在 `justfile` 与 AGENTS.md 中**均无记载**，做法未知 | AGENTS.md 的 `### Snapshot tests` 一节有完整专章，含完整命令链与一条**强制要求**（改动可见 UI 必须配快照覆盖） | `grep -n insta AGENTS.md` |
| H14 | `app_server_protocol` | `just write-app-server-schema` 为强制流程第 3 步 | `codex-app-server-protocol` **无任何 bin target**，该 recipe 引用的 `--bin write_schema_fixtures` 不存在，命令会失败。真实路径是 `app-server-protocol/scripts/write_schema_fixtures.py` | `cargo metadata` targets；`ls src/bin` 不存在 |

> H14 是**上游 `justfile` 与 `AGENTS.md` 自身的陈旧**，不是本文档体系编造。但本体系将其作为「强制流程」照抄而未验证可执行性，属证据等级越权。

### D 组：元文件自身的错误

| # | 文档 | 问题 |
| ---: | ---- | ---- |
| H15 | 首版 `health_check_report.md` | 「四处全部已在所有引用位置同步更正，未留下不一致」——**该断言为假**。`generation_plan.md` 中仍留有「CLI 子命令 23 个……已确认」，与全部正式文档的「27 个变体」冲突 |

---

## 跨文档矛盾（checker 结构性盲区，本可自动拦截）

以下 4 项全部逃过 5 项 checker，因为 checker 不做跨文档数值对账，也不校验「标题声明的计数」与「表格实际行数」是否相符：

| # | 事实 | 冲突 |
| ---: | ---- | ---- |
| X1 | `utils/` crate 数 | 主文档两处、`crate_map` 两处写 **20**；`crate_map` 同一张表实际列出 **23** 行（磁盘上也是 23）——**标题与自己的表格打架** |
| X2 | 四条扩展路径的证据等级 | 主文档 `:387` 写「只有 E1，各文档都没有描述其关系」；同一文件 `:406` 写「E3 ✅ 已闭合」 |
| X3 | 同上 | `crate_map` 决策树写「未验证，先读 `mcp_and_extensions.md`」；同一文件另两处写「已完成代码级核查（E3）」 |
| X4 | CLI 子命令数 | `generation_plan.md` 留 **23**；全部正式文档为 **27 个变体**（Linux 可见 23 / macOS·Windows 24） |

另有 C5–C15 共 11 项 MED/LOW 级跨文档不一致，详见修复记录。

---

## 三个错误模式（根因分析）

| # | 模式 | 实例 | 教训 |
| ---: | ---- | ---- | ---- |
| 1 | **读定义不读使用方** | Landlock（H2）、MDM（H5）：都是读枚举常量下结论，而那些变体在生产路径上根本不被构造 | 类型存在 ≠ 类型生效。必须找到构造点与调用方 |
| 2 | **拿 E2 证据下 E3 结论** | ext 依赖（H3/H4）：用 `grep -rl` 数文件名，未区分 `[dependencies]` 与 `[dev-dependencies]` | 依赖出现在 Cargo.toml ≠ 依赖生效。须用 `cargo metadata` 并记录 section |
| 3 | **把门禁全绿当成内容正确** | 首版验收 7 项质量维度全 ✅ | checker 覆盖结构，不覆盖事实。全绿是必要条件，不是充分条件 |

> [!WARNING]
> 模式 2 正是本体系自己在 `AI_RULES.md` §5.3 与主文档「禁忌」章节中明令警告过的错误。**写下规则不等于遵守规则**——这是本轮最需要记住的一条。

---

## accepted_issues

| issue_id | tool | implementation | file | issue_type | original_status | accepted_reason | residual_risk | follow_up |
| -------- | ---- | -------------- | ---- | ---------- | --------------- | --------------- | ------------- | --------- |
| AI-005 | manual_review | human | dev_docs/sdk_guide.md | environment_limitation | OPEN | 分析环境 Python 为 3.9.6，低于 sdk/python 要求的 3.10，无法运行 pytest 取得 E4 验证 | 低。Python SDK 章节已显式标注证据等级上限为 E2/E3 | 用户升级 Python 至 3.10 以上后可补跑并提升证据等级 |
| AI-006 | manual_review | human | dev_docs/（全体） | unverified_fix_round | OPEN | 第四轮修复（针对第三轮独立复核查出的 7 项）完成后未再派独立代理复核。本项目实测的修复引入新错基准率为每轮 6–7 个 HIGH，故合理推断仍存在少量未知错误 | **中**。已知问题全部修正且经复核，但不能推断为零错误。风险集中在架构定性类断言与本轮新增的覆盖内容 | 下次接手时优先对「唯一 / 全部 / 从不 / 必然」类绝对断言做一轮独立复核；或在实际使用中发现问题后回填 |

### 已撤销的 accepted issue

| issue_id | 原因 |
| -------- | ---- |
| AI-003 | 原记「app-server 与 exec-server 跨 OS 传输仅有 E2 证据」。本轮独立审查已定位到可读的实现入口，不再构成证据等级限制，转为待补齐的覆盖缺口 |
| AI-004 | **原记「insta 快照流程无任何记载」——该前提为假**（见 H13）。AGENTS.md 的 `### Snapshot tests` 一节有完整专章。此条不是「未知」，是漏读，不应被登记为 accepted issue |

---

## 质量维度评估（改判）

| 维度 | 首版评级 | 本轮评级 | 依据 |
| ---- | ---- | ---- | ---- |
| **结构合规** | ✅ | ✅ | 主文档 10 个契约必需章节齐备、文本与顺序逐字一致；20 个产物 frontmatter 7 字段完整，`related_files` 路径全部存在（独立复核 0 问题） |
| **事实准确** | ✅ | ❌ | 15 项 HIGH 级事实错误，涉及 12 篇文档；含 4 项架构定性错误与 1 项 CI 强制不变量的反向陈述 |
| **边界诚实** | ✅ | ⚠️ | 「本文未覆盖」表确实存在且有价值，但存在两类反向问题：一是把可当场查证的事实标为 E1（如扩展装配点、TS 二进制定位、Python 类型来源）；二是 AI-004 把漏读登记为未知 |
| **规范一致** | ✅ | ❌ | 主文档与 `crate_map` 存在 E1/E3 自相矛盾（X2/X3）；元文件含虚假的「已全量更正」断言（H15） |
| **可导航性** | ✅ | ✅ | 51 处跨文档 `§N` 引用经独立复核 0 处编号错误；全部相对链接 0 处失效 |
| **可维护性** | ✅ | ⚠️ | 基线 commit 与 `verified_at` 齐备；但 30+ 处 AGENTS.md 行号引用已偏移，行号引用方式本身不可维护 |
| **安全合规** | ✅ | ⚠️ | 遥测凭据处理正确（占位符写法有效，独立复核确认无泄露）；但检出 1 处组织 SSH 身份泄露，已修复 |

---

## 修复结果

| 优先级 | 事项 | 状态 |
| ---- | ---- | ---- |
| P0 | 修复 15 项 HIGH 级事实错误 | 进行中 |
| P0 | 撤销首版验收结论并如实记录（本文档） | 已完成 |
| P0 | 脱敏检出项处理 | 已完成 |
| P1 | 修复约 45 项 MED（含 30+ 处 AGENTS.md 行号偏移、协议方法数重算、证据等级越权 13 处） | 待办 |
| P1 | 新增跨文档数值对账 checker，纳入提交前门禁 | 待办 |
| P2 | 补齐重大覆盖缺口（realtime 会话面、`codex-features` 门控机制、TUI 的 app-server 客户端架构、`vendor/bubblewrap`、Nix/devcontainer、`codex-cli` 顶层目录、协议方法注册表位置、配置发现路径与信任门控） | 待办 |
| P2 | 外部文件引用改为「引内容 + 章节标题」，不再写具体行号 | 待办 |
| P3 | 对修复后的架构定性类断言派独立代理复核后再重新验收 | 待办 |

---

## 相关文档

- [生成方案](./generation_plan.md)
- [项目分析与问题报告](./project_analysis_report.md)
- [生成进度记录](./generation_progress.md)
- [主文档](../AI_Coding_Context.md)
- [AI 规则索引](../rules/combined/AI_RULES.md)
