---
title: Codex CLI 知识沉淀目录说明
summary: 说明 dev_docs/knowledge/ 目录的用途、适合沉淀的内容类型、笔记模板与证据等级要求，并划清它与批次文档、变更计划的边界。
keywords: codex | knowledge | notes | evidence-level | convention
scope: dev_docs/knowledge/ 目录使用约定
related_files: AGENTS.md | dev_docs/AI_Coding_Context.md | dev_docs/crate_map.md
dependencies: dev_docs/AI_Coding_Context.md
verified_at: 2026-08-03
---

# 知识沉淀目录

存放**读代码过程中挖出来的、值得记住的事实**——尤其是那些"当时查了半天，下次还会再查一遍"的东西。

---

## 和其他目录的分工

| 目录 | 放什么 | 时态 |
| ---- | ---- | ---- |
| `dev_docs/*.md`（批次文档） | 体系化的主题说明，有固定结构 | 稳定 |
| `dev_docs/plans/` | 动手**之前**的实施计划 | 未来 |
| **`dev_docs/knowledge/`** | **读代码过程中的零散发现** | 过去 |

一条经验：如果某个知识点开始反复被引用，就应该从这里**提升**进对应的批次文档。

---

## 适合沉淀的内容

| 类型 | 例子 |
| ---- | ---- |
| 反直觉的实现 | `codex-core` 的 `find_codex_home` 是薄委托，真正实现在 `codex-utils-home-dir` |
| 踩坑记录 | Cargo 通过但 Bazel 失败——因为 `include_str!` 没在 `BUILD.bazel` 补 `compile_data` |
| 调用链追踪结果 | 某个事件从 TUI 到 core 的完整路径与行号 |
| 命名与实际不符 | 目录名或 crate 名容易引起误解的地方 |
| 一次性排查的结论 | 某个数值是怎么算出来的、口径是什么 |

**不适合放这里**：能直接从 `AGENTS.md` 或代码注释读到的内容（会产生第二份可能漂移的事实源）。

---

## 命名约定

```
<主题-kebab-case>.md
```

例：`codex-home-resolution.md`、`bazel-compile-data-pitfall.md` <!-- ref-exempt: 命名规范示例，这两个文件尚未创建 -->

---

## 笔记模板

```markdown
---
title: <一句话标题>
summary: <结论是什么>
keywords: <关键词 | 用竖线分隔>
scope: <适用范围>
related_files: <实际读过的文件 | 用竖线分隔>
dependencies: dev_docs/AI_Coding_Context.md
verified_at: YYYY-MM-DD
---

# <标题>

## 结论
一句话说清楚。

## 证据
| 事实 | 证据等级 | 位置 |
| ---- | ---- | ---- |
| … | E3 | `codex-rs/xxx/src/yyy.rs:123` |

## 为什么容易搞错
（这一节是这份笔记存在的理由）

## 基线
- commit：
- 复核日期：
```

---

## 证据等级要求

沉淀的是"事实"，所以必须标等级，规则与主文档一致：

| 等级 | 来源 | 允许的措辞 |
| ---- | ---- | ---- |
| E1 | 目录结构、文件名、数量 | 只能写"疑似""待验证" |
| E2 | 配置、锁文件、README | 可写"已从配置确认" |
| E3 | 源码片段、调用链 | 可写"代码显示" |
| E4 | 实跑构建/测试/工具 | 可写"已验证" |

> [!WARNING]
> 最容易犯的错是**把 E1 的目录名推断写成 E3 的事实**。例如看到 `ext/`、`core-plugins/`、`skills/` 三个目录就断言它们的层次关系——这需要读代码才能确认。

---

## 时效性

上游迭代频繁。每条笔记都要记 `verified_at` 与基线 commit；引用行号时，**行号会随上游变动而失效**，同时记下函数名或代码片段特征，便于重新定位。

---

## 相关文档

- [主文档](../AI_Coding_Context.md) — 证据等级与未覆盖范围
- [Crate 地图](../crate_map.md)
- [架构总览](../architecture_overview.md)
