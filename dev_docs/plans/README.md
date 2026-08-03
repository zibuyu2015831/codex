---
title: Codex CLI 变更计划目录说明
summary: 说明 dev_docs/plans/ 目录的用途、单个计划文件的写法与命名约定，并强调本仓库外部贡献受邀制对计划落地方式的限制。
keywords: codex | plans | change-plan | convention | contributing
scope: dev_docs/plans/ 目录使用约定
related_files: AGENTS.md | docs/contributing.md | dev_docs/AI_Coding_Context.md
dependencies: dev_docs/AI_Coding_Context.md | dev_docs/development_workflow.md
verified_at: 2026-08-03
---

# 变更计划目录

存放**动手改代码之前**写下的实施计划。目的是让改动在落地前就被审视一遍：范围多大、碰哪些 crate、波及谁、怎么验证。

---

## 什么时候写计划

| 建议写 | 不必写 |
| ---- | ---- |
| 预计变更超过 300 行 | 改错别字、调日志文案 |
| 跨 3 个以上 crate | 单文件内的小修 |
| 触及依赖热点（`codex-protocol`、`codex-core`、`codex-config` 等） | 纯注释 |
| 涉及协议或配置类型变更（需要重跑 schema 生成） | — |
| 需要拆成多阶段落地 | — |

> `AGENTS.md:125-131` 规定单次变更不超过 800 行（复杂逻辑 500 行）。**超限时必须拆分**，而拆分方案正是计划文件要回答的问题。

---

## 命名约定

```
YYYY-MM-DD-<简短英文-kebab-case>.md
```

例：`2026-08-03-split-chat-composer.md`

---

## 计划文件模板

```markdown
---
title: <一句话标题>
summary: <这个变更做什么、为什么做、影响哪些 crate>
keywords: <关键词 | 用竖线分隔>
scope: <影响范围>
related_files: <实际读过的文件 | 用竖线分隔>
dependencies: dev_docs/crate_map.md
verified_at: YYYY-MM-DD
---

# <标题>

## 背景
为什么要做这个变更。

## 影响面
| crate | 改动内容 | 被依赖数 |
| ---- | ---- | ---: |
（被依赖数查 crate_map.md §4）

## 方案
具体怎么改。

## 变更规模预估
- 预计行数：
- 是否超过 800 行上限：
- 若超限，拆分阶段：

## 需要补跑的生成命令
- [ ] just write-config-schema（改了 ConfigToml）
- [ ] just write-app-server-schema（改了 app-server API 形状）
- [ ] just bazel-lock-update（改了 Cargo.toml/lock）

## 验证方式
- [ ] just fmt
- [ ] just test -p <crate>
- [ ] 是否需要集成测试（改智能体逻辑则必须）

## 风险与回滚
```

---

## ⚠️ 落地方式的限制

> [!IMPORTANT]
> 本仓库**外部代码贡献受邀制**（`docs/contributing.md:3-17`），未受邀的 PR 会被直接关闭。
>
> 因此这里的计划默认是**在个人 fork 内实施**的。若要向上游提交，请先取得 Codex 团队成员的明确邀请。

---

## 相关文档

- [主文档](../AI_Coding_Context.md)
- [Crate 地图](../crate_map.md) — 查影响面与归属决策
- [开发流程](../development_workflow.md) — 规范、命令与提交前自检
