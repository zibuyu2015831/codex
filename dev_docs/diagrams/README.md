---
title: Codex CLI 架构图目录说明
summary: 说明 dev_docs/diagrams/ 目录的用途、五张架构图各自的内容与适用场景、图中数值的核验口径与来源文档、drawio 源文件与内嵌 XML 图片的分工，以及重新生成与修改图的完整流程。
keywords: codex | diagrams | drawio | architecture-diagram | mermaid | autolayout
scope: dev_docs/diagrams/ 目录使用约定与五张架构图索引
related_files: dev_docs/AI_Coding_Context.md | dev_docs/architecture_overview.md | dev_docs/crate_map.md | dev_docs/core_agent_loop.md | dev_docs/tools_and_sandbox.md
dependencies: dev_docs/AI_Coding_Context.md | dev_docs/architecture_overview.md | dev_docs/crate_map.md
verified_at: 2026-08-05
---

# 架构图目录

面向**初次理解 codex 架构**的可视化材料。文字讲解在各专题文档里，这里放的是配套的图。

> [!IMPORTANT]
> **图是文档的下游产物，不是独立事实源。** 图上的每个数字都来自本体系的专题文档（对应关系见下表「数值来源」）。上游代码变动后，**先修文档、再改图**；反过来会让两者静默分叉。

---

## 五张图

| 图 | 内容 | 什么时候看 | 配套文档 |
| ---- | ---- | ---- | ---- |
| `codex-01-topology` | 全局拓扑：一个二进制 → 五种前端 → `codex-core` → 外部服务 | 第一次接触本项目 | [`architecture_overview.md`](../architecture_overview.md) §2 |
| `codex-02-layers` | 分层总览：L5→L0 六层，134 个 crate 的骨架 | 想知道某个 crate 属于哪一层 | [`crate_map.md`](../crate_map.md) §2 |
| `codex-03-agent-loop` | 三层循环：提交循环 / 任务层 / turn 循环的嵌套 | 想理解「一句话进来之后发生了什么」 | [`core_agent_loop.md`](../core_agent_loop.md) §2 |
| `codex-04-security` | 两道防线：审批策略 + 三平台沙箱的决策流 | 关心 AI 能对本机做什么 | [`tools_and_sandbox.md`](../tools_and_sandbox.md) |
| `codex-05-session-modules` | `core/src/session/` 的真实模块依赖图（16 模块 / 20 边） | 要动 session 子系统的代码 | [`core_agent_loop.md`](../core_agent_loop.md) §3.1 |

前四张是**人工抽象**的概念图，第五张是**从源码自动抽取**的事实图 —— 两者性质不同，见下方「关于第 05 张」。

---

## 每张图的两个文件

| 后缀 | 用途 |
| ---- | ---- |
| `.drawio` | 源文件。用 [draw.io Desktop](https://www.drawio.com/) 或 [app.diagrams.net](https://app.diagrams.net/) 打开编辑，也可用 VS Code 的 Draw.io Integration 扩展 |
| `.drawio.png` | 交付图片。**XML 已内嵌在 PNG 内部**，拖回 draw.io 即可继续编辑，不必另外传源文件 |

改图请改 `.drawio`，然后按下方流程重新导出 `.drawio.png`；不要只改其中一个。

---

## 数值来源

图上出现的每个数字及其来源文档，便于上游变动后逐条回查：

| 断言 | 出现在 | 来源 |
| ---- | ---- | ---- |
| 134 个 crate | 01 / 02 | [`AI_Coding_Context.md`](../AI_Coding_Context.md) 项目概览 |
| 27 个子命令 | 01 / 02 | [`architecture_overview.md`](../architecture_overview.md) §3 |
| `codex-core` 296,963 行 / 依赖 66 个内部 crate | 01 / 02 | [`crate_map.md`](../crate_map.md) §2（66 为**含 dev-dependencies 去重**口径） |
| `codex-tui` 238,439 行 | 02 | [`crate_map.md`](../crate_map.md) §2 |
| `codex-app-server` 128,364 行 | 02 | [`crate_map.md`](../crate_map.md) §2 |
| `codex-mcp-server` 4,128 行 | 02 | [`crate_map.md`](../crate_map.md) §3 |
| `codex-core-plugins` 37,038 行 | 02 | [`crate_map.md`](../crate_map.md) §2 |
| `codex-tools` 6,525 行 | 02 | [`crate_map.md`](../crate_map.md) §2 |
| `codex-protocol` 被 70 个 crate 依赖 | 02 | [`crate_map.md`](../crate_map.md) §4（含 dev 口径） |
| `app-server-protocol` 30,946 行 | 02 | [`crate_map.md`](../crate_map.md) §2 |
| `ext/` 12 个 crate，其中 8 个依赖 extension-api | 02 | [`AI_Coding_Context.md`](../AI_Coding_Context.md) 关键目录速查 |
| `utils/` 23 个 crate；`utils-absolute-path` 被 55 个 crate 依赖 | 02 | [`crate_map.md`](../crate_map.md) §3.11 / §4 |
| `Op` 26 个变体 / `EventMsg` 80 个变体 | 03 | [`core_agent_loop.md`](../core_agent_loop.md) §2.2 |
| 任务层四类：regular / compact / review / user_shell | 03 | [`core_agent_loop.md`](../core_agent_loop.md) §1 |
| macOS 3 份 `.sbpl` 策略 | 04 | [`AI_Coding_Context.md`](../AI_Coding_Context.md) 关键目录速查 |
| Windows 默认无沙箱 | 04 | [`AI_Coding_Context.md`](../AI_Coding_Context.md) 项目概览 |

---

## 一个容易读错的地方

图 01 与图 02 都画了一条红色虚线：**`codex-tui` 不得直连 `codex-core`**。

这条线**只表示「无直接依赖边、无直接 import」**，两图的图例与注记都写明了限定词。它**不**表示 `codex-core` 没有链接进 TUI —— 事实上 core 会经 `codex-app-server-client`、`codex-cloud-config`、`codex-utils-oss` 等中间 crate 传递性地链进去。

本体系在这一句上先后错过三次（详见 [`AI_Coding_Context.md`](../AI_Coding_Context.md) 阅读前必读的 WARNING 与 [`tui_guide.md`](../tui_guide.md) §0.1–§0.2）。看图时请连同注记一起读。

---

## 关于第 05 张

它由 `codex-rs/core/src/session/` 的源码自动抽取，因此**性质与前四张不同**：前四张是人挑选出来的主干，这张是机器抽出来的全部。生成时做了三步收敛，缺一张图就不可读：

1. **滤掉测试模块** —— 原始输出中 27% 的节点是 `*_tests`
2. **切到子系统** —— 整个 `codex-core` 是 411 个模块的平铺命名空间（嵌套模块数为 0），无法折叠，只能按子目录切片
3. **剔除孤立节点** —— 6 个模块在本子系统内没有任何依赖边，留着只会撑宽画布

`dev_docs/diagrams/session-graph.json` 是收敛后的中间数据，改图或换布局方向时从它出发，不必重新抽取。

> 该图上有 20 处边交叉。这是 `session` 与 `turn_context` 的**星型枢纽结构**导致的，不是布局失败 —— 换成 TB 方向交叉能降到 14，但会得到一张 5:1 的扁条图，反而更难读。

---

## 重新生成

依赖：[draw.io Desktop](https://www.drawio.com/)（提供 `drawio` CLI）与 Graphviz（第 05 张的自动布局需要）。

```bash
# macOS
brew install --cask drawio
brew install graphviz
```

**改完 `.drawio` 后重新导出图片**（`-e` 让 XML 内嵌进 PNG）：

```bash
cd dev_docs/diagrams
drawio -x -f png -e -s 2 -o codex-01-topology.drawio.png codex-01-topology.drawio
```

**重新抽取第 05 张的模块图**（上游 `session/` 改动后）：

```bash
python3 <drawio-skill>/scripts/rustimports.py codex-rs/core/src/session -o raw.json
# 按上文三步收敛后写成 dev_docs/diagrams/session-graph.json，再：
python3 <drawio-skill>/scripts/autolayout.py dev_docs/diagrams/session-graph.json -o codex-05-session-modules.drawio
```

上述脚本来自社区 skill [`Agents365-ai/drawio-skill`](https://github.com/Agents365-ai/drawio-skill)（MIT）。draw.io 官方也提供 Claude Code 插件：[`jgraph/drawio-mcp`](https://github.com/jgraph/drawio-mcp)（Apache-2.0）。**两者都不是本仓库的依赖**，只在重新生成图时才需要。

---

## 相关文档

- [`AI_Coding_Context.md`](../AI_Coding_Context.md) — 文档体系主入口
- [`architecture_overview.md`](../architecture_overview.md) — 架构总览
- [`crate_map.md`](../crate_map.md) — 134 个 crate 地图
- [`core_agent_loop.md`](../core_agent_loop.md) — 智能体核心循环
- [`tools_and_sandbox.md`](../tools_and_sandbox.md) — 工具调用与沙箱
