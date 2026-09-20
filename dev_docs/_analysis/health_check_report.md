---
title: Codex CLI 文档体系质量验收报告
summary: 记录 openai/codex 仓库 dev_docs 文档体系第 5 轮双轨交叉审查的验收结果，判定 PASS_WITH_ACCEPTED_ISSUES；含双轨方法（核验轨 + 禁读文档的重推导轨）必要性的三个实证、修订代理拒改与纠正主控裁定的完整记录、按文档汇总的事实错误修正清单、5 项门禁的实跑结果、引用可解析性由 25.1% 提升到 84.6% 的量化改进，以及 AI-005 原因改写、AI-006 闭合与 AI-007 新增的 accepted issue 重判。
keywords: codex | health-check | acceptance | dual-track-review | machine-checks | claim-ledger | reference-resolvability
scope: openai/codex 仓库 dev_docs 文档体系质量验收
related_files: dev_docs/AI_Coding_Context.md | dev_docs/crate_map.md | dev_docs/mcp_and_extensions.md | dev_docs/observability.md | dev_docs/rules/combined/AI_RULES.md | dev_docs/_analysis/claim_ledger.jsonl | dev_docs/_analysis/ref_checker.py | dev_docs/_analysis/cross_doc_consistency_checker.py | dev_docs/_analysis/redact_scan.sh | AGENTS.md
dependencies: dev_docs/_analysis/generation_plan.md | dev_docs/_analysis/generation_progress.md
verified_at: 2026-08-05
---

# 文档体系质量验收报告

> **验收范围**: 全部产物（17 篇正式文档 + AI 规则索引 + 2 个目录 README + `_analysis` 四件套）
> **代码基线 commit**: `bb5054fe47abe73ecbbd454751066a28c89f4bb9`（本轮**不同步上游**，工作树代码即该基线）
> **报告性质**: **第 5 轮双轨交叉审查后的重新验收**，兑现第 4 轮遗留的 accepted issue AI-006

---

## 总体结论

| 字段 | 值 |
| ---- | ---- |
| verdict | PASS_WITH_ACCEPTED_ISSUES |
| scope | 17 篇正式文档 + `dev_docs/rules/combined/AI_RULES.md` + `dev_docs/plans/README.md` + `dev_docs/knowledge/README.md` + `_analysis` 四件套 |
| 审查方法 | **双轨交叉**（核验轨 + 禁读 `dev_docs/` 的重推导轨）+ **修订代理独立复核** |
| 产物总行数 | **11,463**（20 个交付产物，`wc -l` 实测）；`_analysis` 四件套另计约 **2,660** 行 |
| blocker_count | 0 |
| accepted_issue_count | 2（AI-005 改写后保留、AI-007 本轮新增） |
| 本轮修正的事实错误 | **117 条**（13 篇文档，按提交信息逐条汇总） |
| 累计修正的 HIGH 级错误 | 28（首版 15 + 第二轮修复引入 6 + 第三轮修复引入 7）+ 本轮 7 条显式标注 HIGH |
| 校验项 | 5 项框架 checker + 5 项本轮门禁（脱敏、引用可解析性、跨文档对账、frontmatter/related_files、修后复核） |
| 断言账本 | `dev_docs/_analysis/claim_ledger.jsonl` 26 条可复验事实，**全部通过** |

> 行数复现命令：
>
> ```bash
> wc -l dev_docs/*.md dev_docs/rules/combined/AI_RULES.md dev_docs/plans/README.md dev_docs/knowledge/README.md
> wc -l dev_docs/_analysis/*.md
> ```
>
> 此前版本记录的「合计 5,182」是**首版行数**，早已过期；本表为第 5 轮 `wc -l` 实测重建。

---

## 验收对象

| # | 产物 | 行数 |
| ---: | ---- | ---: |
| 1 | `dev_docs/AI_Coding_Context.md`（主文档） | 598 |
| 2 | `dev_docs/architecture_overview.md` | 505 |
| 3 | `dev_docs/crate_map.md` | 597 |
| 4 | `dev_docs/development_workflow.md` | 610 |
| 5 | `dev_docs/core_agent_loop.md` | 838 |
| 6 | `dev_docs/tools_and_sandbox.md` | 664 |
| 7 | `dev_docs/app_server_protocol.md` | 637 |
| 8 | `dev_docs/config_system.md` | 578 |
| 9 | `dev_docs/tui_guide.md` | 464 |
| 10 | `dev_docs/testing_guide.md` | 751 |
| 11 | `dev_docs/mcp_and_extensions.md` | 567 |
| 12 | `dev_docs/auth_and_providers.md` | 941 |
| 13 | `dev_docs/build_and_release.md` | 723 |
| 14 | `dev_docs/session_and_persistence.md` | 516 |
| 15 | `dev_docs/experimental_surfaces.md` | 804 |
| 16 | `dev_docs/observability.md` | 632 |
| 17 | `dev_docs/sdk_guide.md` | 521 |
| 18 | `dev_docs/rules/combined/AI_RULES.md` | 305 |
| 19 | `dev_docs/plans/README.md` | 100 |
| 20 | `dev_docs/knowledge/README.md` | 112 |
| — | **合计** | **11,463** |

`_analysis` 四件套（`wc -l dev_docs/_analysis/*.md`）：`generation_plan.md` 1,207 + `generation_progress.md` 465 + `project_analysis_report.md` 658 + 本文件（约 330）≈ **2,660**。本文件自身的行数在落笔过程中仍在变，故只给约数——真值以命令输出为准。

> 行数是快照，不是不变量。本轮修订期间多篇文档仍在增写（例如 `auth_and_providers.md` 由 420 增至 941 行），任何时候都以上面两条 `wc -l` 命令的输出为准。

---

## 为什么必须双轨：三个实证

前四轮的审查全部是单轨的——派代理读文档、逐条断言回源取证。这种方法有一个结构性上限：**它只能判断「写下来的话对不对」，判断不了「该写的话有没有写」，更判断不了「整篇的叙事骨架是不是从一开始就选错了」。** 当骨架错了，逐条核验每一条断言都能通过，因为每一条单独看都没错。

第 5 轮起，每篇文档同时派两类代理：**核验轨**（读文档 + 源码，逐条断言回源取证）与**重推导轨**（**明令禁读 `dev_docs/`**，仅凭源码从零推导该主题事实，写成独立结论后再与文档差分）。以下三个实例经主控亲自复核，是双轨必要性的直接证据。

### 实证一：`Op` 枚举变体数——核验轨数出 16，重推导轨数出 26

核验轨用一个按括号深度计数的脚本数 `Op` 枚举，得 **16**；重推导轨不用脚本，直接把变体名一个个列出来，得 **26**。主控复核确认 **26 正确**。

脚本错在哪：它在**更新括号深度之后**才判定当前行是不是一个变体，于是带结构体字段的变体（形如 `UserInput { .. }`）在进入判定前深度已经加 1，被整体跳过。交叉印证来自另一侧——`codex-rs/core/src/session/handlers.rs` 中 `Op::` 的去重命中数恰好也是 **26**。

```bash
# 交叉验证命令（两者应相等）
grep -o "Op::[A-Za-z0-9_]*" codex-rs/core/src/session/handlers.rs | sort -u | wc -l
```

> **这条最值得记住的地方不是脚本错了，而是主控自己最初写的计数脚本犯了同一个错。** 同一个思维定式会在不同代理身上重复出现，因此「换一个代理再数一遍」并不能排除它——只有「换一种数法」才能。这类错误**任何 checker 都拦不住**：脚本输出 16，看起来干净、可复现、有据可查。

对应账本条目 `op_variants = 26`，口径陷阱已写进 `dev_docs/_analysis/claim_ledger.jsonl` 的 note 字段。

### 实证二：rollout 文件名的时区不一致——核验轨 121 条全过，重推导轨查出

`session_and_persistence` 的核验轨拆出 **121 条断言**并逐条取证，**没有发现**这个问题：rollout 文件名的**写入**用 `OffsetDateTime::now_local()`（本地时区），而**反向解析**用 `assume_utc()`（当作 UTC）。

核验轨查不出来是必然的——文档里根本没写这件事，没有断言可核。而它不是无关紧要的细节：该文件名同时是排序键、分页游标的组成部分，以及反归档时重建路径的依据，**三处耦合**。这正是重推导轨的价值：它不受文档议程约束，从源码出发就会撞上这条链路。

### 实证三：上游注释自身错误且自相矛盾——「读注释确认」在此处必然得到错误答案

`codex-rs/config/src/loader/mod.rs` 中 `load_config_layers_state` 的文档注释，紧邻的两段把 admin 层排在了**相反**的位置：

- 前一段（requirements 层）明写 "collected in **ascending** precedence order"，并把 `admin: managed preferences` 列在**最后**——即 admin **最高**。
- 后一段（config 层）写 "Configuration is built up from multiple layers in the following order"，把 `admin: managed preferences` 列在**最前**——按同样的升序读法，admin **最低**。

而实现把 MDM 放在**最高**（`codex-rs/config/src/loader/README.md` 的 "Precedence is top overrides bottom" 清单里 `LegacyManagedConfigTomlFromMdm` 排第一；`codex-rs/config/src/loader/mod.rs` 中 `requirements_layers_from_legacy_scheme` 的行内注释也明写 "MDM has higher precedence than the legacy managed_config.toml file"）。

> **结论**：在这个位置上，「读注释确认一下」这种复核方式**必然得到错误答案**。同一文件里还有一处同类问题——注释把 cwd 层的路径写成 `${PWD}/config.toml`，实际是 `${PWD}/.codex/config.toml`；本文档体系首版正是照抄了这条注释而未验证。这是把「上游文字」当成 E3 证据的典型代价：**注释不是实现**。

---

## 修订代理拒改 / 纠正主控裁定的记录

这是「修后复核」有效性的直接证据，单列一节。本轮在双轨之外新增了第三类代理：**修订轨**——把两轨的裁定交给它落笔，并明确要求「**若裁定与源码不符，拒改并回报反证**」。它确实抓到了主控自己的错误。

| 文档 | 主控/上游轨的裁定 | 修订代理的处置 | 实测反证 |
| ---- | ---- | ---- | ---- |
| `dev_docs/core_agent_loop.md` | 重推导轨称 `symphonia` 与 `tokio-tungstenite`「专为 realtime 子系统而在」 | **拒改** | 该文件的 `use` 列表中两者**都没有**；真实使用者分别是 `codex-rs/core/src/audio_preparation.rs`<!-- ref-exempt: 历史记录——第 5 轮当时的路径，该文件第 6 轮已迁至 codex-rs/utils/audio/ -->（`symphonia`）与 `codex-rs/core/src/client.rs`（`tokio-tungstenite`）。已改写为反例说明 |
| `dev_docs/app_server_protocol.md` | 主控称四个宏「同时生成 enum + `method_name()` + `TryFrom` + `export_*`」 | **拒改** | 四者**不对称**，不是每个宏都生成全部四项。已改为逐宏列明的表格 |
| `dev_docs/config_system.md` | 主控给出的 7 处行号与 1 处字段计数 | **纠正 8 处** | 7 处行号偏移；`ConfigRequirementsToml` 是 **31** 个字段而非 32（`codex-rs/config/src/config_requirements.rs`） |
| `dev_docs/auth_and_providers.md` | 主控的 3 条裁定 | **纠正 3 处** | 最重要一条：主控把 `ConfigLayerSource::Mdm`（优先级 **0**）与 `LegacyManagedConfigTomlFromMdm`（**50**）混为一谈——两者是不同的层，优先级恰好一低一高；另确认 `CODEX_REMOTE_AUTH_TOKEN` 实为**测试专用**，真实机制是 `--remote-auth-token-env` |
| `dev_docs/tui_guide.md` | 主控给出的 4 个数字 | **纠正 4 处** | sqlx 禁用项 **13** 条（非 11，`codex-rs/clippy.toml:15-27`，第 14 行是注释）；TUI 集成测试 **9** 个 `.rs`（非 10）；`allow(clippy::disallowed_methods)` **18** 处（非「20+」）；`prefix_lines` 是 `pub fn` 而非 `pub(crate)`（`codex-rs/tui/src/render/line_utils.rs:57`） |
| `dev_docs/build_and_release.md` | 主控称 `register_toolchains("@llvm//toolchain:all")` 在 `MODULE.bazel:37` | **纠正 1 处** | 实际在 `MODULE.bazel:29` |
| `dev_docs/mcp_and_extensions.md` | 主控给出的 `SkillScope` 各根行号 | **纠正若干处** | 逐根实测校正 |
| `dev_docs/tools_and_sandbox.md` | 主控给出的「25 处规则写入」 | **改口径** | 按实测改为更准确的口径表述，而非沿用主控的粗略计数 |

复现命令（逐条可验）：

```bash
grep -n "register_toolchains" MODULE.bazel                              # → :29
grep -n "sqlx" codex-rs/clippy.toml                                     # → 14 行命中，其中 :14 是注释，禁用项 13 条
git ls-files "codex-rs/tui/tests/*.rs" | wc -l                          # → 9
grep -rn "allow(clippy::disallowed_methods)" codex-rs/tui/ | wc -l      # → 18
grep -rn "fn prefix_lines" codex-rs/tui/src/                            # → pub fn
```

> **这一节的意义**：本项目此前三轮的经验是「每一轮修复都会引入新的 HIGH 级错误」（第二轮 6 个、第三轮 7 个）。根因之一就是**没有任何环节复核「修复动作」本身**——主控把两轨结论汇总成裁定，裁定直接落笔。修订轨补上了这一环，并且**当场证明了它的必要性**：上表的每一行都是一个「如果没有这一步就会被写进文档的新错误」。

---

## 本轮修正的事实错误清单

数据来源：`git log --oneline 73f3fce005..HEAD` 的 7 次提交，每次提交信息里逐条列了修正项。下表按文档汇总。

| 文档 | 修正条数 | 显式标注 HIGH | 最严重的一条 |
| ---- | ---: | ---: | ---- |
| `dev_docs/architecture_overview.md` | 13 | 未分级 | 「TUI 抵达业务能力的唯一通路是 app-server-client」越权——TUI 有三条绕过它的生产路径，CI 门禁只禁 `codex-core` 这一个包名 |
| `dev_docs/tools_and_sandbox.md` | 13 | 未分级 | seccomp 与 `no_new_privs` 被标为无条件「默认」，实际两者都受网络策略门控；网络放开且无受管代理时 seccomp 完全不装 |
| `dev_docs/config_system.md` | 13 | 未分级 | §2 遗漏项目层的**键黑名单**：11 项顶层配置键被无条件剥离，与信任门控**正交**——即使目录受信任，项目配置也无法设置 base URL / model provider |
| `dev_docs/auth_and_providers.md` | 13 | 未分级 | 认证加载是四级优先级且第一级是 `CODEX_API_KEY`；**`OPENAI_API_KEY` 根本不在 `load_auth()` 里**，原文的优先级描述整体错位 |
| `dev_docs/core_agent_loop.md` | 12 | 未分级 | `codex-rs/core/src/safety.rs` 被描述为「命令安全性判定的 core 侧入口」，实际其唯一 `pub fn` 判的是**补丁写入路径**；命令安全判定的入口是 `codex-rs/core/src/exec_policy.rs` |
| `dev_docs/session_and_persistence.md` | 11 | 未分级 | 「thread-store 操作面与 `thread/*` 方法严格对应」三重不成立；且 rollout 文件名写入用本地时区、解析当 UTC（见上文实证二） |
| `dev_docs/crate_map.md` | 11 | 未分级 | §1 的两个 128（`members` 条目数 / `workspace.dependencies` path 条目数）数值相同但**集合不同**，互差各 6 项——最易被误读处 |
| `dev_docs/app_server_protocol.md` | 10 | 3 | `ClientNotification::Initialized` 被说成「无 wire 名」，实际由 `serde rename_all` 派生为 `"initialized"` 并已固化进 JSON Schema，收发两端均有生产代码——**会误导第三方客户端作者的可执行层面错误** |
| `dev_docs/mcp_and_extensions.md` | 9 | 2 | 「只有扩展体系有生命周期钩子」错：`codex-hooks` 提供 10 种用户可配置的生命周期事件，且是 `codex-core` 的**生产依赖** |
| `dev_docs/observability.md` | 6 | 2 | `[otel] exporter` 被标为「通用导出器」，实为**日志导出器**——而它恰是唯一携带 `user.email` / `user.account_id` 与用户提示词原文的通道。**把隐私敏感度最高的一类描述成了最模糊的一类** |
| `dev_docs/sdk_guide.md` | 4 | 未分级 | `schema/typescript/v2/` 路径不存在（缺 `codex-rs/app-server-protocol/` 前缀）；AI-005 的阻塞原因已过期需改写 |
| `dev_docs/AI_Coding_Context.md` | 1 | 未分级 | 首版写「`main.rs:1016` 起的 match」<!-- ref-exempt: 引述首版的错误写法，裸文件名正是被更正的对象 -->，实际 match 起于 `codex-rs/cli/src/main.rs:1001`，`:1016` 只是其中一个 arm |
| `dev_docs/rules/combined/AI_RULES.md` | 1 | 未分级 | MCP 规则行指向的 `mcp_connection_manager.rs` 不存在 <!-- ref-exempt: 反例，正文正在说明该路径不存在 -->，实际文件是 `codex-rs/codex-mcp/src/connection_manager.rs` |
| **合计** | **117** | **7** | — |

> [!IMPORTANT]
> **「显式标注 HIGH」列的口径必须说清楚**：只有 `observability`、`app_server_protocol`、`mcp_and_extensions` 三篇的提交信息按 HIGH/MED 逐条分级（合计 7 条 HIGH）。其余各批次的提交信息只列「事实错误 N 项」而未分级。**本报告不追认分级**——把未分级的条目按事后印象补标 HIGH，正是本项目前几轮反复犯的「拿 E2 证据下 E3 结论」。「最严重的一条」一列是本报告的判断，读者可按该列自行评估量级。

另有大量**覆盖缺口补写**（不计入上表的 117 条，因为它们是「原本没写」而非「原本写错」），其中体量较大的有：`core_agent_loop` 新增实时会话子系统整节、`tools_and_sandbox` 补入 `vendor/bubblewrap` 的完整来源链与 Windows 默认无沙箱一节、`mcp_and_extensions` 新增 `codex-hooks` 作为第五条扩展路径、`observability` 新增 Sentry 通路与「无 opt-out 环境变量」这一反面事实、`auth_and_providers` 由 420 行增至 941 行。

---

## machine_checks

本轮的 5 项门禁。前 3 项可直接复跑，后 2 项是流程性门禁。

| # | 门禁 | 实现 | 命令 | exit_code | 结果 | disposition |
| ---: | ---- | ---- | ---- | ---: | ---- | ---- |
| 1 | 脱敏扫描 | shell | `bash dev_docs/_analysis/redact_scan.sh` | 0 | **7 项全绿** | verified |
| 2 | 引用可解析性 | python | `python3 dev_docs/_analysis/ref_checker.py` | 0 | **ERROR 0 / WARN 41** | partially_open |
| 3 | 跨文档对账 | python | `python3 dev_docs/_analysis/cross_doc_consistency_checker.py --verify-repo` | 0 | **0 问题**（24 篇文档、账本 26 条、12 项已登记事实全部取得仓库真值并吻合） | verified |
| 4 | frontmatter / `related_files` | python | 同 #2（`dev_docs/_analysis/ref_checker.py` 内置该检查） | 0 | **0 问题**：24 篇文档的 7 个必需字段齐备，`related_files` 中每条路径均可解析 | verified |
| 5 | 修后复核 | 修订代理 | 每篇文档的第三类代理，要求「与源码不符则拒改并回报」 | — | **触发多次拒改与纠正**，逐条见上文 | verified |

### 门禁 #1 明细：脱敏 7 项

| 扫描项 | 结果 |
| ---- | ---- |
| 本地绝对路径 | 无命中 ✅ |
| 凭证字面量 | 无命中 ✅ |
| JWT 形状串 | 无命中 ✅ |
| 私钥块 | 无命中 ✅ |
| SSH 组织身份串 | 无命中 ✅ |
| 内网 IP | 无命中 ✅ |
| 个人邮箱 | 无命中 ✅ |

### 门禁 #2 明细：`ref_checker` 仍未闭合的部分

**不粉饰**：这一项没有全绿。

本轮**开始**时，`ref_checker` 在全仓报 **70 条 ERROR**，集中在三个文件：`dev_docs/_analysis/generation_plan.md` 44 条、`dev_docs/experimental_surfaces.md` 15 条、`dev_docs/_analysis/project_analysis_report.md` 11 条。到本报告落笔时，这 70 条已全部处理完（补全路径或加 `<!-- ref-exempt: 理由 -->` 行级豁免），**ERROR 归零**。

剩下的 WARN 未清零。本报告落笔时实测为 **41 条**（`python3 dev_docs/_analysis/ref_checker.py`），但该数字是**移动靶**——同一时段仍有文档在被修订，复跑可能得到 ±数条的差异，请以命令输出为准。分布与性质如下：

| 文档 | WARN | 性质 |
| ---- | ---: | ---- |
| `dev_docs/auth_and_providers.md` | 18（本篇仍在增写，复跑时该值最易变动） | `symbol_far_from_cited_line` 与 `symbol_not_in_file` 为主。本篇在批次 3 大幅扩写（420 → 941 行），行号引用密度最高，符号邻近性检查的假阳性也最多——例如同一行同时出现 `codex-rs/login/src/auth/storage.rs` 与 `chmod`（那是对系统调用的描述，不是该文件里的符号） |
| `dev_docs/session_and_persistence.md` | 11 | 同上。多为「同一行的路径与符号分属不同文件」，如引 `codex-rs/protocol/src/protocol.rs` 而同行提到 `LocalThreadStore` |
| `dev_docs/config_system.md` | 7 | 同上 |
| `dev_docs/tui_guide.md` | 4 | 3 条 `ref_not_root_relative` + 1 条 `symbol_not_in_file`：`codex-rs/tui/src/chatwidget.rs`、`codex-rs/clippy.toml` 等裸文件名，全仓唯一匹配，可机械补全 <!-- ref-exempt: 举例说明何为裸文件名写法，这些正是待归一化的对象 --> |
| `dev_docs/architecture_overview.md` | 1 | `symbol_far_from_cited_line` |

**性质判定**：这 41 条**没有一条是断链**（断链会报 ERROR）。`symbol_*` 两类是本检查器最弱的一项启发式——它假设「同一行里的符号应当出现在同一行里的路径所指的文件中」，而这个假设在「引 A 文件、同时提到 B 文件里的类型」这种正常写法下必然误报。`ref_not_root_relative` 那 3 条是真问题，只是危害等级低于 ERROR（读者仍能靠唯一性定位）。

**为什么不清零**：清 `symbol_*` 假阳性的唯一办法是逐行加豁免注释，那会把豁免标记从「有意义的例外声明」稀释成噪声，反而降低这项检查未来的信噪比。此项已登记为 accepted issue（见 AI-007 的 follow_up）。

---

## 引用可解析性的量化改进

这是本轮最大的**机制性**成果，也是对上一版「行号引用方式本身不可维护」这条批评的正面回应。

本体系的运行机制是「会话中携带入口文档 + 按需阅读」——子代理拿到一条引用后，必须能**直接定位到文件**。因此**一条无法从仓库根解析的引用，等价于一条断掉的链接**，危害不亚于事实错误。

首次扫描（批次 0 归一化之前）：

| 指标 | 值 |
| ---- | ---- |
| 仓库路径引用总数 | 2,510 |
| 可从仓库根直接解析 | **629（25.1%）** |
| 其余 | crate 内相对写法（`codex-rs/config/src/loader/mod.rs`）与裸文件名（`main.rs`、`manager.rs`）——**人能看懂，机器定位不了** <!-- ref-exempt: 举例说明何为不可解析的写法，这些正是被归一化的对象 --> |

本轮归一化后（`python3 dev_docs/_analysis/ref_checker.py` 实测）：

| 指标 | 值 |
| ---- | ---- |
| 仓库路径引用总数 | 3,436 |
| 可从仓库根直接解析 | **2,907（84.6%）** |
| 已标注豁免（泛指 / 反例） | 224 |
| 本体系文档名（免于前缀要求） | 442 |
| 运行时产物（`config.toml`、`auth.json` 等，不参与解析） <!-- ref-exempt: 指用户机器上生成的运行时文件，仓库内不存在 --> | 84 |
| 仓库中不存在（断链） | **0** |

> 三类计数（豁免 / 本体系文档名 / 运行时产物）都不是「未解析」——它们是**被显式判定为不需要解析**的引用。把这三类算进去，剩余真正待归一化的只有个位数条。

> [!NOTE]
> `dev_docs/_analysis/ref_checker.py` 的文件头注释里记录的是一个**更早**的快照（2,475 条中 616 条可解析，约 25%），与上表的 2,510 / 629 略有出入。两者都是归一化前的口径，差额来自扫描时点不同（其间有文档在增写）。此处保留两个数字而不统一，是为了不制造「同一个数在不同地方对不上」的新问题。

---

## accepted_issues

| issue_id | tool | implementation | file | issue_type | original_status | accepted_reason | residual_risk | follow_up |
| -------- | ---- | -------------- | ---- | ---------- | --------------- | --------------- | ------------- | --------- |
| AI-005 | manual_review | human | dev_docs/sdk_guide.md | environment_limitation | OPEN（原因已改写） | **原记「本机 Python 3.9.6 低于 `requires-python >=3.10`」已过期**——实测本机为 **3.14.6**。新原因有二：①缺 `pytest` / `pydantic` / `openai-codex-cli-bin`，且核验期禁止联网安装；②即便跨过第 ①，`sdk/python/tests/test_contract_generation.py:43` 仍硬断言 `openai-codex-cli-bin == "0.144.4"`，而该包是**只发 PyPI 的平台专属 wheel**（`sdk/python-runtime/hatch_build.py:17-20` 对 sdist 构建直接 `raise`），仓库内无法本地构建替代品——这是**不可绕过的硬墙** | 低。Python SDK 章节已显式标注证据等级上限为 E2/E3，且已写明「未在本机运行验证」 | 消解条件改为**允许联网**后执行 `uv sync --group dev --frozen`（官方 CI 的第一步也正是这条），再补跑 pytest 将证据提升至 E4。**不是**「升级 Python」 |
| ~~AI-006~~ | manual_review | human | dev_docs/（全体） | unverified_fix_round | **CLOSED** | 原记「第四轮修复未经独立复核」。**第 5 轮双轨交叉审查即为对该项的兑现**，已闭合 | — | 残留风险另立 AI-007 |
| AI-007 | manual_review | human | dev_docs/（全体） | residual_fix_risk + open_warnings | OPEN | 本轮同样存在「修复引入新错」的可能。**缓解措施有二且均已证明有效**：①修订代理的拒改机制（本轮触发多次，逐条见上文）；②断言账本 26 条可复验事实全部通过、跨文档对账 0 问题。**但这仍不等于零错误**——本轮 117 条修正中有 110 条未按 HIGH/MED 分级，其严重度分布未经独立评估；同时 `ref_checker` 尚有 41 条 WARN 未闭合 | **中低**。低于 AI-006 时期（那时是「完全未复核」，现在是「已复核但复核本身可能有盲区」）。风险集中在两处：本轮**新增**的章节（它们只经过一轮双轨，没有历史审查的沉淀），以及未分级的 110 条修正 | 见下方「下一轮的建议动作」 |

### 已撤销的 accepted issue（沿用前轮判定）

| issue_id | 原因 |
| -------- | ---- |
| AI-003 | 原记「app-server 与 exec-server 跨 OS 传输仅有 E2 证据」。第二轮独立审查已定位到可读的实现入口，不再构成证据等级限制，转为待补齐的覆盖缺口 |
| AI-004 | **原记「insta 快照流程无任何记载」——该前提为假**。AGENTS.md 的 `### Snapshot tests` 一节有完整专章。此条不是「未知」，是漏读，不应被登记为 accepted issue |

### 下一轮的建议动作

1. **对本轮新增章节做抽样双轨复核**（优先级最高）。本轮新增的整节内容——`core_agent_loop` 的实时会话子系统、`tools_and_sandbox` 的 `vendor/bubblewrap` 来源链与 Windows 一节、`mcp_and_extensions` 的 `codex-hooks` 路径、`observability` 的 Sentry 通路、`auth_and_providers` 扩写的 500 余行——**只经过一轮审查**，没有历史沉淀。按本项目的经验，新写的内容出错率高于修订过的内容。
2. **给 117 条修正补分级**，或至少对其中的架构定性类断言（「唯一 / 全部 / 从不 / 必然」类量词所在句）做一次穷举取证。本报告拒绝事后追认分级，但下一轮可以重新逐条判定。
3. **决定 `ref_checker` 的 41 条 WARN 怎么办**。两条路：要么把 `symbol_*` 两类检查改成「只在引用与符号距离超过阈值且该符号在被引文件中完全不存在时才报」以降低假阳性，要么把这两类降级为 INFO。当前形态下它们既清不掉也不该被无脑豁免。
4. **把断言账本继续扩容**。当前 26 条覆盖的主要是结构性计数（crate 数、文件数、变体数）。行为性事实（默认走哪条路径、哪个开关控制什么）目前仍无机器校验手段，只能靠双轨。

---

## 质量维度评估

沿用上一版的 7 个维度。

| 维度 | 上一版评级 | 本轮评级 | 依据 |
| ---- | ---- | ---- | ---- |
| **结构合规** | ✅ | ✅ | 5 项框架 checker 全绿；24 篇文档 frontmatter 7 字段完整、`related_files` 路径全部可解析（`ref_checker` 内置检查，0 问题）；主文档 10 个契约必需章节齐备 |
| **事实准确** | ❌ | ⚠️ | 本轮修正 117 条事实错误，双轨交叉是迄今最强的检出手段。评级不给 ✅ 的理由写在 AI-007 里：**已知问题全部修正且经复核，不等于零错误**；且 110 条未分级，严重度分布未经独立评估 |
| **边界诚实** | ⚠️ | ✅ | 本轮多篇文档新增了**反面事实**：`observability` 写明 `sentry::init` 全树零命中（⇒ 崩溃不会自动上报）与「无 `DO_NOT_TRACK`、无 `*_DISABLE_TELEMETRY`」；`app_server_protocol` 指出 `codex-rs/app-server-protocol/src/protocol/mappers.rs` 是 24 行死代码 <!-- ref-exempt: 该路径在正式文档中已写全，此处为转述 -->；`config_system` 点出第二个死类型 `ConfigProfile`。写清「什么不存在」比写清「什么存在」更难，也更能防止读者做出错误推断。本报告本身也如实记录了未闭合的 41 条 WARN |
| **规范一致** | ❌ | ✅ | `cross_doc_consistency_checker --verify-repo` **0 问题**：账本 26 条可复验事实全部通过，「标题声明的计数 vs 紧随表格的行数」检查全绿。上一版的 X1–X4 四项跨文档矛盾已全部闭合，其中 X4（CLI 子命令 23 vs 27）由本轮实测确认为「27 个变体 / Linux 可见 23 / macOS·Windows 24」并写入账本 |
| **可导航性** | ✅ | ✅ | 引用可从仓库根解析率由 **25.1% 提升至 84.6%**，断链 **0**；跨文档 `§N` 引用由 `cross_doc_consistency_checker` 的章节漂移检查覆盖，0 问题 |
| **可维护性** | ⚠️ | ✅ | **本轮的主要改进项，详见下方专段** |
| **安全合规** | ⚠️ | ✅ | 脱敏 7 项全绿。此外 `observability` 修正的两项 HIGH 都直接关系到读者能否正确判断「打开哪个配置键会导致邮箱与提示词外发」——这是安全合规维度上的实质提升，不只是扫描通过 |

### 关于「可维护性」的专门说明

上一版给出的批评是：**「30+ 处 AGENTS.md 行号引用已偏移，行号引用方式本身不可维护」**。本轮对此的回应是把两类此前纯靠人工的检查**变成了机器检查**：

| 此前 | 现在 | 工具 |
| ---- | ---- | ---- |
| 跨文档数值一致性靠人记、靠人对 | 数值断言进 `dev_docs/_analysis/claim_ledger.jsonl`，每条附**可复现命令**与期望值；checker 逐条重跑命令并与仓库真值比对 | `dev_docs/_analysis/cross_doc_consistency_checker.py --verify-repo` |
| 引用能否被定位无人校验 | 每条 `` `path` `` / `` `path:123` `` 引用逐条解析，含行号越界与符号邻近性 | `dev_docs/_analysis/ref_checker.py` |
| 「标题说 20 个、表格列了 23 行」这类自相矛盾靠肉眼 | 自动比对标题声明的计数与紧随其后的表格实体数 | `dev_docs/_analysis/cross_doc_consistency_checker.py` |
| 脱敏靠提交前记得跑 | 固化为脚本，7 项一次跑完 | `dev_docs/_analysis/redact_scan.sh` |

引用格式本身也按用户决策改为**符号名为主、行号为辅**：优先写「`codex-rs/config/src/loader/mod.rs` 的 `load_config_layers_state`」<!-- ref-exempt: 引用写法示例，符号与路径的搭配本身就是被示范的对象 -->，行号只作定位辅助。符号名在上游重构中比行号稳定得多，而 `ref_checker` 的符号邻近性检查恰好能校验这类引用——这是「可维护」与「可校验」第一次对齐。

> **诚实地说清边界**：这些工具解决的是「引用可定位」与「数值一致」，**不解决「断言与源码是否相符」**。那一层至今没有机器手段，只能靠双轨交叉。这也正是 AI-007 存在的原因。

---

## 三个错误模式（累积的根因分析）

| # | 模式 | 本轮的新实例 | 教训 |
| ---: | ---- | ---- | ---- |
| 1 | **读定义不读使用方** | 两例：`codex-rs/core/src/safety.rs` 被当成命令安全判定入口，实际判的是补丁写入路径 <!-- ref-exempt: 同行另一例的符号属于 codex-rs/login，与本路径无关 -->；`AuthMode::Headers` 在本仓库生产代码中零构造 | 类型存在 ≠ 类型生效。必须找到构造点与调用方 |
| 2 | **拿 E2 证据下 E3 结论** <!-- ref-exempt: Cargo.toml 在此为泛指，指任意 crate 的清单文件 --> | 批次 1 的系统性问题：把「读 `Cargo.toml` 得出的依赖结论」标成 E3——按本体系约定应为 E2 | 依赖出现在 `Cargo.toml` ≠ 依赖生效。须区分 `[dependencies]` / `[dev-dependencies]` / `[target.*]` 并用 `cargo metadata` |
| 3 | **把上游文字当权威** | `config_system` 照抄上游 doc comment 的 `${PWD}/config.toml`（实为 `${PWD}/.codex/config.toml`）；`app_server_protocol` 把 `just write-app-server-schema` 当强制流程照抄而未验证可执行性 | **上游注释与文档也会错，而且会自相矛盾**（见实证三）。注释不是实现 |

> [!WARNING]
> 模式 1 与模式 2 正是本体系自己在 `dev_docs/rules/combined/AI_RULES.md` §5.3 与主文档「禁忌」章节中明令警告过的错误，**本轮仍然出现**。写下规则不等于遵守规则——因此本轮把这三条从「规则」升级为「审查流程中的强制取证要求」，并写入 `dev_docs/_analysis/generation_plan.md` 的「审查方法」一节。

---

## 相关文档

- [生成方案](./generation_plan.md)
- [项目分析与问题报告](./project_analysis_report.md)
- [生成进度记录](./generation_progress.md)
- [主文档](../AI_Coding_Context.md)
- [AI 规则索引](../rules/combined/AI_RULES.md)
