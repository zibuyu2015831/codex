---
title: 12 配置系统与特性开关
summary: 展开 02 篇里被简化成四层的配置体系，说明实际是八个具名配置层按显式数值优先级折叠、现代 MDM 层已定义但在生产路径中从未被构造、遗留 MDM 层反而优先级最高这一反直觉倒置、每键来源追溯与层版本指纹的用途、101 个特性开关中有 32 个已是 Removed 阶段、Stage 不参与 apply_map 判定因而不能用它推断开关是否可设，以及自建项目做配置分层与特性开关时的最小方案与三条硬纪律。
keywords: codex | config | config-layer | precedence | profile | mdm | feature-flag | stage | apply-map | toml | origins
scope: codex 的配置层折叠机制与特性开关体系
related_files: codex-rs/config/src/config_layer_source.rs | codex-rs/config/src/loader/README.md | codex-rs/config/src/loader/mod.rs | codex-rs/features/src/lib.rs | codex-rs/core/src/config/mod.rs | codex-rs/config/src/profile_toml.rs
dependencies: 无（本目录文档自包含，不依赖 dev_docs 其余文档）
verified_at: 2026-08-05
---

# 12 配置系统与特性开关

> **前置**：[02 启动](./02-startup.md)

---

## 0. 为什么值得单独一篇

[02](./02-startup.md) §3 用四行讲完了配置："默认值 < config.toml < profile < 命令行"。

**那是一个够用的入门模型，但和实现差得比较远。** 真实情况是**八个具名配置层**，带显式的数值优先级，还有企业管理、项目级配置、每键来源追溯这些东西。

对自建项目来说，这一篇的价值在于：**配置分层是那种"第一天定错、第三年还在还债"的决策**。它很便宜，但改起来极贵——因为所有 crate 的初始化路径都依赖它（这也是 [22](./22-load-bearing-and-cuts.md) §2 把 `codex-config` 列为承重墙的原因）。

---

## 1. ⚠️ 先说取证方式：这一篇不能信注释

仓库规范 `dev_docs/rules/combined/AI_RULES.md` §5.4 的六条取证禁忌里，**第一条 T1 点的就是这个文件**：

> **T1**：读注释 / README / 帮助文本就下结论——`codex-rs/config/src/loader/mod.rs` 的两段紧邻注释对配置层优先级给出**相反**答案，且都与实现不符。

所以本篇的优先级表**全部取自 `precedence()` 的函数体**，不是取自任何注释或 README。你复核时也请这样做：

```bash
sed -n '/fn precedence/,/^    }/p' codex-rs/config/src/config_layer_source.rs
```

> **这条方法论比配置知识本身更值钱。** 配置优先级是**极易腐烂的注释**——每加一层就要改一次描述，但漏改不会报错、不会有测试挂掉。**凡是"顺序/优先级"类的文档，一律去读那个返回数字的函数。**

---

## 2. 八个配置层与它们的真实优先级

```rust
pub fn precedence(&self) -> i16 {
    match self {
        ConfigLayerSource::Mdm { .. }                          => 0,
        ConfigLayerSource::System { .. }                       => 10,
        ConfigLayerSource::EnterpriseManaged { .. }            => 15,
        ConfigLayerSource::User { profile, .. } => {
            if profile.is_some() { 21 } else { 20 }
        }
        ConfigLayerSource::Project { .. }                      => 25,
        ConfigLayerSource::SessionFlags                        => 30,
        ConfigLayerSource::LegacyManagedConfigTomlFromFile {..}=> 40,
        ConfigLayerSource::LegacyManagedConfigTomlFromMdm      => 50,
    }
}
```

**数字大的赢。** 整理成表：

| 优先级 | 层 | 是什么 | 谁控制 |
| ---: | ---- | ---- | ---- |
| **50** | `LegacyManagedConfigTomlFromMdm` | 遗留：MDM 下发的 `managed_config.toml` | 企业 IT |
| **40** | `LegacyManagedConfigTomlFromFile` | 遗留：本机的 `managed_config.toml` | 企业 IT |
| **30** | `SessionFlags` | 命令行 `-c key=value` | 你，本次运行 |
| **25** | `Project` | 项目里的 `.codex/config.toml` | 仓库 |
| **21** | `User` + profile | 用户配置里选中的那个 profile | 你 |
| **20** | `User` | 用户配置 `$CODEX_HOME/config.toml` | 你 |
| **15** | `EnterpriseManaged` | 企业云配置包 | 企业 |
| **10** | `System` | `/etc/codex/config.toml` | 机器管理员 |
| **0** | `Mdm` | 现代 MDM 托管偏好 | — **见 §3** |

### 三个反直觉的地方

**① 项目配置压过用户配置（25 > 20）。**

你在 `~/.codex/config.toml` 里的设置，会被仓库里的 `.codex/config.toml` 覆盖。

> **这是有意的**：仓库能规定"在我这里必须用只读沙箱"，而不是任由每个人的个人偏好生效。但反过来说，**克隆一个不信任的仓库时，它的 `.codex/config.toml` 会改变 codex 在你机器上的行为**。这是个值得注意的安全面。

**② 遗留的 MDM 层优先级最高（50），现代的 MDM 层最低（0）。**

同一个概念的新旧两个实现，一个在天花板一个在地板。这不是笔误——**遗留层要压过所有人，是为了在迁移期保证企业策略不被绕过**；新层的位置则是按"正常的托管配置应该在哪"设计的。

**③ profile 只比 user 高 1（21 vs 20）。**

用 `21` 而不是 `25`，是为了给"user 和 project 之间"留空间。**用离散数字而不是数组下标来表达优先级，就是为了以后能往中间插东西。**

> **这个手法值得抄。** 如果你用 `Vec<Layer>` 的下标当优先级，插一层要动所有代码；用 `i16` 打分，插一层只要选个中间的数。

---

## 3. ⚠️ `Mdm` 这一层：定义了，但没人构造它

`ConfigLayerSource::Mdm { domain, key }` 是 `pub` 的、名字贴切、就排在枚举第一个、优先级函数里有它、诊断和 TUI 里都能显示它。

**但在生产代码里，它从来没有被构造过。**

复现（排除测试文件）：

```bash
grep -rn "ConfigLayerSource::Mdm {" --include=*.rs codex-rs | grep -v "_tests\|/tests/"
```

实测 13 处命中**全部是 `match` 分支**（`Mdm { .. } =>`）或**类型转换**（`Mdm { domain, key } => ApiConfigLayerSource::Mdm { .. }`）——都是"如果拿到这个变体该怎么办"，没有一处是"造一个出来"。唯一真正构造它的地方是 `codex-rs/hooks/src/engine/discovery.rs` 第 1321 行附近，而那是一个 `assert_eq!` 里的测试。

> ⚠️ **仓库规范把这个案例列为 T5 的反例**：*"符号 `pub` + 名字贴切 + 位置显眼 ⇒ 认定它生效"* 是错的。
>
> **判据是"谁构造它"，不是"谁提到它"。** `match` 分支只证明**万一**拿到会怎么处理，不证明**真的**会拿到。
>
> 这和 [11](./11-model-client.md) §1 里那 5 个零引用的 `*_prompt.md` 是同一类错误的两种形态：一个是文件没人读，一个是类型没人造。

**对读代码的实际影响**：你按"MDM 托管配置"这条线去追，会追到一个死胡同，然后怀疑自己漏看了什么。**不是你的问题——它就是没接上。**

---

## 4. 配置栈不只给出"最终值"

`load_config_layers_state(...)` 返回的 `ConfigLayerStack` 提供三样东西：

| 方法 | 给你什么 | 为什么需要 |
| ---- | ---- | ---- |
| `effective_config()` | 折叠后的最终 TOML | 程序真正要用的 |
| `origins()` | **每个键是从哪一层来的** | 回答"为什么这个值是这样" |
| `layers_high_to_low()` | 每一层的原始内容 + 版本指纹 | 冲突检测、UI 展示 |

### `origins()` 是被真实痛苦逼出来的

八层叠加之后，用户会问：**"我明明在 `~/.codex/config.toml` 里设了这个，为什么没生效？"**

没有来源追溯的话，你只能让他一层层自己找。有了 `origins()`，可以直接告诉他"这个键被项目配置覆盖了"。

> **给自建项目**：**只要你的配置超过两层，就要做来源追溯。**
>
> 最简做法：折叠时不要只保留值，保留 `(value, source_name)` 二元组。成本几乎为零，但省掉的支持成本巨大。Python 里就是把 `dict[str, Any]` 换成 `dict[str, tuple[Any, str]]`。

### 层版本指纹用来做乐观并发

每层带一个 `version`（稳定指纹）。用途是：TUI/IDE 里改配置时，先读一次拿到版本，写回时带上版本；如果这期间别人改了同一层，版本对不上，就能检测到冲突而不是静默覆盖。

**还有一个 `disabled_reason` 字段**：被禁用的层**仍然会被列出来给 UI 看**，只是不参与折叠。

> **这个细节很讲究**：如果直接把禁用的层从列表里删掉，用户在界面上会看到"我的企业配置怎么消失了"。留着它 + 一个禁用原因，用户能看到"它在，但因为 XX 没生效"。

---

## 5. 特性开关：101 个，其中 32 个已经是死的<!-- no-count-check -->

`codex-rs/features/src/lib.rs` 里有一张 `FEATURES` 表。实测分布：

```bash
grep -o 'stage: Stage::[A-Za-z]*' codex-rs/features/src/lib.rs | sort | uniq -c
```

| Stage | 数量 | 含义 |
| ---- | ---: | ---- |
| `Stable` | 34 | 已稳定，开关留着以备临时开关 |
| **`Removed`** | **32** | **开关没用了，纯为向后兼容保留** |
| `UnderDevelopment` | 31 | 开发中，不对外 |
| `Deprecated` | 3 | 已废弃 |
| `Experimental` | 1 | 在 `/experimental` 菜单里对用户可见 |
| **合计** | **101** | |

默认值分布：**37 个默认开，63 个默认关**。

> **三分之一的开关是死的。** 这是所有长期项目的宿命——**加开关容易，删开关难**，因为你不知道谁的配置文件里还写着它，删了会让他们的配置报错。
>
> **给自建项目的启示**：**第一天就设计好开关的退休流程。** 至少要有：一个"阶段"字段、一个"读到已退休的开关时打什么日志"的约定。codex 有前者（`Stage`），后者靠 `record_legacy_usage_force` 记录遥测。

### ⚠️ 但 `Stage` 不参与"这个开关能不能设"的判定

这是 AI_RULES §5.4 的 **T3**：*把 `Stage::Removed` 读成「不可用」*。

看 `apply_map`（`codex-rs/features/src/lib.rs:466`）——它是把 TOML 里的开关表应用到运行时状态的函数：

```rust
pub fn apply_map(&mut self, m: &BTreeMap<String, bool>) {
    for (k, v) in m {
        match k.as_str() {
            "web_search_request" => { self.record_legacy_usage_force(...); }
            "tui_app_server" => { continue; }      // ← 手写的忽略名单
            "undo"           => { continue; }
            "js_repl"        => { continue; }
            "remote_control" => { continue; }
            // …
        }
    }
}
```

**它匹配的是字符串键，全程没有读 `feature.stage`。**

真正读 `stage` 的只有 `emit_metrics`（第 447 行），用途是**上报指标时跳过 `Removed` 的**：

```rust
pub fn emit_metrics(&self, otel: &SessionTelemetry) {
    for feature in FEATURES {
        if matches!(feature.stage, Stage::Removed) { continue; }   // ← 只在这里
        // ...
    }
}
```

**所以两件事必须分清：**

| 问题 | 答案 |
| ---- | ---- |
| 一个 `Removed` 的开关还能在 TOML 里被设置吗 | **能**，除非 `apply_map` 里有一条手写的 `continue` 分支 |
| `Removed` 影响什么 | **只影响遥测上报是否跳过它** |

> **这是"元数据没有被强制执行"的典型**：`Stage` 看起来像一个会被系统尊重的声明，实际只是一个供人看和供指标用的标签。忽略名单是**另一份手工维护的清单**，两者可能不同步。
>
> **给自建项目**：**如果你定义了一个"阶段/状态"字段，就让它真的驱动行为。** 否则它迟早会和实际行为对不上，而且没有任何机制会告诉你对不上了。

---

## 6. 给自建项目：最小配置方案

### v0.1 够用的层数

```python
LAYERS = [
    ("default",  10, load_defaults()),          # 代码里的默认值
    ("user",     20, load_toml("~/.yourapp/config.toml")),
    ("project",  25, load_toml("./.yourapp/config.toml")),
    ("cli",      30, parse_cli_overrides(argv)),
]

def effective():
    merged = {}
    origins = {}
    for name, prec, layer in sorted(LAYERS, key=lambda x: x[1]):
        for k, v in flatten(layer).items():
            merged[k] = v
            origins[k] = name          # ← 后写的赢，同时记来源
    return merged, origins
```

**四层起步足够。** 企业管理、云配置那些等你真的有企业客户了再说。

### 三条硬纪律

| 纪律 | 为什么 |
| ---- | ---- |
| **优先级用离散数字，不用列表下标** | 以后要往中间插层。codex 用 `i16`，profile 取 21 就是为了插在 20 和 25 之间 |
| **折叠时同步记录来源** | "为什么这个值是这样"是最高频的支持问题。成本接近零 |
| **配置类型只定义一次，schema 自动生成** | 手写两份（Rust 结构体 + 文档/JSON Schema）第三天就会漂。codex 用 `just write-config-schema` 生成 |

### 特性开关的最小做法

```python
@dataclass(frozen=True)
class FeatureInfo:
    key: str
    default_enabled: bool
    stage: Stage          # ← 但要让它真的驱动行为，见 §5
```

**两个建议：**

1. **默认值倾向关闭。** codex 是 63 关 / 37 开。新功能默认关，出事只影响开了的人。
2. **开关的键名进一个集中的表，不要散在各处 `if config.get("xxx")`。** 否则你永远不知道到底有多少个开关。

### 一个容易漏的点

> **读到不认识的配置键时，是报错还是忽略？**

codex 有一个 `strict_config` 选项来控制这件事（`codex-rs/config/src/strict_config.rs`）。

**两种都对，但必须显式选：**

- **忽略**：老配置文件在新版本上还能用，但用户拼错键名时**静默失效**，他会以为设了
- **报错**：拼错立刻发现，但升级时删掉一个键就会让所有老配置文件启动失败

> **推荐：默认报错，提供一个 `--ignore-unknown-config` 逃生口。** 拼错键名静默失效是极其难排查的一类问题——用户坚信自己设了，你坚信没设。

---

## 本篇小结

| 你现在应该能回答 | 答案 |
| ---- | ---- |
| 配置到底几层？ | **八个具名层**，按 `i16` 数值折叠。[02](./02-startup.md) 的"四层"是简化 |
| 项目配置和用户配置谁大？ | **项目（25）> 用户（20）**。克隆不可信仓库时注意 |
| 优先级最高的是谁？ | **遗留 MDM 层（50）**；现代 `Mdm` 层反而是 0 |
| `Mdm` 层生效吗？ | **不生效**——生产路径里从来没有构造点，只有 `match` 分支 |
| 查配置优先级该读什么？ | **`precedence()` 函数体**。注释在这个文件上翻过车 |
| 配置栈只给最终值吗？ | 不，还给**每键来源**和**每层版本指纹** |
| 有多少特性开关？ | **101 个**，其中 32 个是 `Removed`，37 个默认开 |
| `Stage::Removed` 意味着不能设吗？ | **不是**。`apply_map` 不看 `stage`，忽略名单是另一份手写清单 |
| 自己做几层够？ | **四层**：默认 / 用户 / 项目 / 命令行。但**一定要记来源** |

---

**下一篇**：[13 补丁与执行策略](./13-patch-and-exec-policy.md) —— 模型是怎么安全地改你的代码的。
