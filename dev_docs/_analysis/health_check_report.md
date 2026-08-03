---
title: Codex CLI 文档体系首版质量验收报告
summary: 记录 openai/codex 仓库 dev_docs 文档体系首版全部 17 篇正式文档加规则索引的最终验收结果，含五项机器检查与两项脱敏门禁的结构化记录、四项事实错误的更正追溯、三项长期挂账 E1 缺口的闭合情况与残留 accepted issues。
keywords: codex | health-check | acceptance | machine-checks | first-release | quality-gate
scope: openai/codex 仓库 dev_docs 文档体系首版质量验收
related_files: dev_docs/AI_Coding_Context.md | dev_docs/crate_map.md | dev_docs/mcp_and_extensions.md | dev_docs/observability.md | dev_docs/rules/combined/AI_RULES.md | AGENTS.md
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-03
---

# 文档体系首版质量验收报告

> **验收范围**: 首版全部产物（17 篇正式文档 + AI 规则索引 + 2 个目录 README）
> **基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`
> **报告性质**: **首版最终验收**（取代此前的第 1 批阶段性验收）

---

## 总体结论

| 字段 | 值 |
| ---- | ---- |
| verdict | PASS_WITH_ACCEPTED_ISSUES |
| scope | 17 篇正式文档 + `rules/combined/AI_RULES.md` + `plans/` 与 `knowledge/` 的 README + `_analysis` 四件套 |
| 产物总行数 | 7,466 |
| blocker_count | 0 |
| accepted_issue_count | 3 |
| 事实错误更正数 | 4 |
| 长期 E1 缺口闭合数 | 3 |

**结论说明**：全部 5 项机器检查与 2 项脱敏门禁通过，两套实现（Python / JS）结果一致。存在 3 项 accepted issue，均为**已显式声明的证据等级限制**，不是被掩盖的缺陷。

> [!IMPORTANT]
> `PASS_WITH_ACCEPTED_ISSUES` 表示**文档体系自身**通过验收。它**不代表**上游代码已被审计，也**不代表**文档覆盖了全部代码——1,270,789 行 Rust 中被文档触及的比例仍然很低，各文档的「本文未覆盖的内容」表列出了具体边界。

---

## 验收对象

| # | 产物 | 行数 |
| ---: | ---- | ---: |
| 1 | `AI_Coding_Context.md`（主文档） | 460 |
| 2 | `crate_map.md` | 408 |
| 3 | `experimental_surfaces.md` | 331 |
| 4 | `development_workflow.md` | 321 |
| 5 | `architecture_overview.md` | 318 |
| 6 | `app_server_protocol.md` | 268 |
| 7 | `mcp_and_extensions.md` | 288 |
| 8 | `testing_guide.md` | 261 |
| 9 | `core_agent_loop.md` | 236 |
| 10 | `build_and_release.md` | 256 |
| 11 | `tools_and_sandbox.md` | 232 |
| 12 | `observability.md` | 233 |
| 13 | `auth_and_providers.md` | 227 |
| 14 | `session_and_persistence.md` | 217 |
| 15 | `config_system.md` | 206 |
| 16 | `sdk_guide.md` | 202 |
| 17 | `tui_guide.md` | 225 |
| 18 | `rules/combined/AI_RULES.md` | 186 |
| 19 | `plans/README.md` | 100 |
| 20 | `knowledge/README.md` | 112 |

---

## machine_checks

| round | tool | implementation | command | exit_code | issue_count | status | disposition |
| ----- | ---- | -------------- | ------- | --------: | ----------: | ------ | ----------- |
| first_release_final | summary_validator | python | `python3 AI-Coding-Context/tools/py/summary_validator.py --dir dev_docs --recursive --strict` | 0 | 0 | PASS | verified |
| first_release_final | doc_health_checker | python | `python3 AI-Coding-Context/tools/py/doc_health_checker.py --full-check --doc-dir dev_docs` | 0 | 0 | PASS | fixed |
| first_release_final | doc_health_checker | js | `node AI-Coding-Context/tools/js/doc_health_checker.js --full-check --doc-dir dev_docs` | 0 | 0 | PASS | fixed |
| first_release_final | semantic_review_checker | python | `python3 AI-Coding-Context/tools/py/semantic_review_checker.py --full-check --doc-dir dev_docs --repo-root .` | 0 | 0 | PASS | fixed |
| first_release_final | semantic_review_checker | js | `node AI-Coding-Context/tools/js/semantic_review_checker.js --full-check --doc-dir dev_docs --repo-root .` | 0 | 0 | PASS | fixed |

### 脱敏门禁

| 扫描项 | 结果 |
| ---- | ---- |
| 本地绝对路径（`grep -rnE "/Users/[A-Za-z0-9._-]+/" dev_docs/`） | 无输出 ✅ |
| 凭证样值（api_key / token / secret / password / credential 后接 12 位以上字面量） | 无输出 ✅ |

### 各批次的修复过程

| 批次 | 首跑问题 | 处置 |
| ---- | ---- | ---- |
| **第 1 批** | 27 个：10 个主文档必需章节缺失（**真实契约违反**）、1 个缺验收报告、16 个锚点极性假阳性 | 按 `main_doc_contract.yaml` 重写主文档结构并补齐四节实质内容；生成验收报告；对齐措辞 |
| **第 2 批** | 4 个锚点极性假阳性（`CODEX_HOME`、`chatwidget.rs`、`config.toml`） | 去除不必要的行内代码标记 |
| **第 3 批** | 3 个锚点极性假阳性 | 同上 |
| **第 4 批** | 5 个：**4 个敏感值策略违规**（`observability.md` 中列出了遥测凭据的常量名与请求头名）+ 1 个锚点假阳性 | **改写为只记录位置与用途，不写常量名与值** |

> [!NOTE]
> 第 4 批的 4 个 blocker 是本轮**唯一的实质性安全类拦截**。checker 正确识别出：即便不写凭据的值，把常量名与自定义请求头名一起列在公开文档中，也构成信息泄露面的扩大。已按其判定修正。

---

## 事实准确性：本轮更正的 4 处错误

| # | 事实 | 原记录 | 更正为 | 发现时机 | 证据 |
| ---: | ---- | ---- | ---- | ---- | ---- |
| 1 | Cargo workspace crate 数 | 130 | **134** | 第 2 轮方案复查 | `cargo metadata --no-deps` 实跑（E4）；`[workspace] members` 显式 128 项 |
| 2 | CLI 子命令数 | 笼统的「23 个」 | **27 个枚举变体**（3 隐藏、1 平台条件编译；Linux 可见 23、macOS/Windows 可见 24） | 第 1 批 | 解析 `cli/src/main.rs:124` 起的枚举 |
| 3 | Linux 沙箱机制 | 仅「Landlock」 | **Landlock + seccomp**（枚举名 `LinuxSeccomp`，两机制同时使用） | 第 2 批 | `linux-sandbox/src/landlock.rs:1,15-26`、`Cargo.toml:28,30` |
| 4 | CI 工作流数 | 29 | **27**（yml 口径） | 第 3 批 | `git ls-files ".github/workflows/*.yml"` |

**四处全部已在所有引用位置同步更正**，未留下不一致。

### 复核通过的量化声明

| 声明 | 值 | 状态 |
| ---- | ---- | ---- |
| Git 跟踪文件（基线 commit 口径） | 5,913 | ✅ |
| Rust 文件 / 行数 | 2,858 / 1,270,789 | ✅ |
| 测试目录 / 测试文件 | 39 / 631 | ✅ |
| `*_tests.rs` | 457 | ✅ |
| insta 快照 | 681 | ✅ |
| v2 TS schema 文件 | 550 | ✅ |
| 协议方法名（去重） | 221 | ✅ |
| `config.toml` 顶层键 | 93 | ✅ |
| `core/tests/suite/` 文件 | 117 | ✅ |
| 依赖热点（`codex-protocol` 被依赖数） | 70 | ✅ |

---

## 长期 E1 缺口的闭合情况

方案阶段标注为「证据等级最薄弱」的三项，本轮闭合了三项中的全部：

| # | 缺口 | 闭合结论 | 位置 |
| ---: | ---- | ---- | ---- |
| 1 | 四条扩展路径的相互关系 | **不是四条平行路径**，而是「一个统一扩展点 + 一个并行机制」——`ext/extension-api` 定义 13 个 Contributor trait，12 个 `ext/*` 全部依赖它；Skills 与 MCP 通过包装 crate 接入；插件不依赖 extension-api，是并行机制 | `mcp_and_extensions.md` §1 |
| 2 | 遥测的默认开关 | 三类导出器默认值**不一致**：metrics 默认 Statsig（开）、trace 与通用默认 None（关）、`log_user_prompt` 默认 false；且 Statsig 在 debug 构建下降级为 None | `observability.md` §1-§2 |
| 3 | `find_codex_home` 是否重复实现 | **不是重复实现**，`core` 侧是一行薄委托，`codex-utils-home-dir` 是唯一事实源 | `config_system.md` §5 |

> [!IMPORTANT]
> 第 1 项的结论**与最初的直觉推断不一致**——这正是当初坚持标为 E1 留白而非凭目录名推断的价值所在。

---

## accepted_issues

| issue_id | tool | implementation | file | issue_type | original_status | accepted_reason | residual_risk | follow_up |
| -------- | ---- | -------------- | ---- | ---------- | --------------- | --------------- | ------------- | --------- |
| AI-003 | manual_review | human | dev_docs/app_server_protocol.md | insufficient_evidence_level | OPEN | app-server 与 exec-server 的跨 OS 传输实现仅有 AGENTS.md 的 E2 声明与 crate 存在性，未做代码级验证；按证据等级规则不得写成 E3 事实 | 中。需要该细节时必须自行读 codex-exec-server-protocol | 后续单独核查，入口为 exec-server-protocol 与 uds crate |
| AI-004 | manual_review | human | dev_docs/testing_guide.md | insufficient_evidence_level | OPEN | insta 快照的更新流程在 justfile 与 AGENTS.md 中均无记载，标准 insta 命令与仓库禁止直跑 cargo 测试的规则存在张力，无法确定既有做法 | 中。更新快照时需先确认做法，不应贸然绕过 just test | 询问维护者或搜索仓库内既有实践 |
| AI-005 | manual_review | human | dev_docs/sdk_guide.md | environment_limitation | OPEN | 分析环境 Python 为 3.9.6，低于 sdk/python 要求的 3.10，无法运行 pytest 取得 E4 验证 | 低。Python SDK 章节已显式标注证据等级上限为 E2/E3 | 用户升级 Python 至 3.10 以上后可补跑并提升证据等级 |

> 三项均**不构成 blocker**：都是被显式声明的边界，且都在对应文档中留有可执行的下一步入口。

---

## 质量维度评估

| 维度 | 评估 | 依据 |
| ---- | ---- | ---- |
| **结构合规** | ✅ | 主文档 10 个框架必需章节齐备；20 个产物 frontmatter 7 字段完整，`related_files` 路径全部存在 |
| **事实准确** | ✅ | 10 项跨文档量化声明实跑复核一致；本轮主动发现并更正 4 处错误 |
| **边界诚实** | ✅ | 每篇文档均有「本文未覆盖的内容」表；E1 级判断一律标注留白而非编造；3 项 accepted issue 显式登记 |
| **规范一致** | ✅ | 未与 `AGENTS.md` 任一条款冲突；产物路径固定 `dev_docs/`，未触碰 `docs/`；`AI_RULES.md` 只做索引不复制条款 |
| **可导航性** | ✅ | 主文档 12 条场景导航；文档间双向交叉引用；每篇有「先读这一节」或速查表 |
| **可维护性** | ✅ | 全部记录基线 commit 与 `verified_at`；主文档列出 5 个高漂移区；数值类事实附可复现命令 |
| **安全合规** | ✅ | 两项脱敏门禁无输出；遥测凭据仅记录源码位置，不记常量名与值 |

---

## 后续建议

| 优先级 | 事项 |
| ---- | ---- |
| P1 | 闭合 AI-003（跨 OS 传输）与 AI-004（快照更新流程）两个缺口 |
| P1 | 拉取上游后对照主文档「高漂移区」表跑一次 diff，走框架路径 C 增量更新 |
| P2 | 升级本机 Python 至 3.10+，补跑 SDK 测试提升证据等级 |
| P2 | 按 `crate_map.md` 建议 1，把 crate 表格的数据来源固化为 `cargo metadata` 命令而非手写 |
| P3 | 各文档「本文未覆盖的内容」表中的 E1 项，按实际需要逐步下钻 |

---

## 相关文档

- [生成方案](./generation_plan.md)
- [项目分析与问题报告](./project_analysis_report.md)
- [生成进度记录](./generation_progress.md)
- [主文档](../AI_Coding_Context.md)
- [AI 规则索引](../rules/combined/AI_RULES.md)
