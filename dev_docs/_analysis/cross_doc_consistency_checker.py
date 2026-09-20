#!/usr/bin/env python3
"""dev_docs 跨文档数值对账检查器。

补上 5 项框架 checker 的结构性盲区。第二轮独立审查查出 15 个 HIGH 级事实错误，
其中至少 4 个属于本脚本能自动拦截的类别，却全部通过了 5 项 checker 的全绿门禁。

本脚本做三件框架 checker 不做的事：

  1. **对账仓库真值**（--verify-repo）：对每个已登记的数值事实执行一条可复现命令，
     用命令输出校验文档里写的数字。这是唯一能防止「数字抄错且各处抄得一样错」的手段。
  2. **跨文档一致性**：同一事实在多篇文档中出现时，取值必须一致。
  3. **标题计数 vs 表格行数**：形如 `## 工具库（20）` 或 `### 12 个内建扩展` 的标题，
     其声明的计数必须与紧随其后的 markdown 表格的实际数据行数相符。
     首版 `crate_map.md` 的「utils 工具库（20）」标题下就列了 23 行。

用法：
    python3 dev_docs/_analysis/cross_doc_consistency_checker.py                # 仅文档内部对账
    python3 dev_docs/_analysis/cross_doc_consistency_checker.py --verify-repo  # 额外核对仓库真值
    python3 dev_docs/_analysis/cross_doc_consistency_checker.py --json

退出码：0 = 无问题；1 = 存在不一致。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "dev_docs"

# --------------------------------------------------------------------------
# 已登记的数值事实
#
# pattern : 必须恰好含一个数字捕获组；在文档正文中逐行匹配。
#           模式要写得足够窄，避免误捕无关数字。
# verify  : 可复现命令，stdout 第一行须为该事实的真值。留空表示只做跨文档一致性。
# --------------------------------------------------------------------------
FACTS: list[dict] = [
    {
        "name": "workspace_crates",
        "desc": "Cargo workspace 内的 crate 总数",
        # 必须带 workspace / 全仓 / Cargo 等限定词，否则「12 个 ext crate」之类会被误捕
        "pattern": (
            r"(?:workspace|Workspace|全仓|仓库(?:内)?共|Cargo\s*workspace)"
            r"[^\n]{0,20}?(\d{2,4})\s*个\s*crate"
            r"|(\d{2,4})\s*个\s*crate[^\n]{0,10}?(?:的\s*)?(?:Cargo\s*)?workspace"
        ),
        # 第 6 轮修复：原命令用裸 cargo 且 2>/dev/null，在 cargo 不在 PATH 的环境下
        # 静默失败，报成「命令执行失败」而非「数值错误」。补 $HOME/.cargo/bin 并加
        # --offline，不再吞 stderr。
        "verify": (
            'PATH="$PATH:$HOME/.cargo/bin" cargo metadata --no-deps --format-version 1 '
            "--offline --manifest-path codex-rs/Cargo.toml "
            "| python3 -c \"import json,sys;print(len(json.load(sys.stdin)['packages']))\""
        ),
    },
    {
        "name": "utils_crates",
        "desc": "codex-rs/utils/ 下的工具 crate 数",
        "pattern": r"(\d{1,3})\s*个(?:通用)?工具\s*crate",
        "verify": "git ls-files 'codex-rs/utils/*/Cargo.toml' | wc -l | tr -d ' '",
    },
    {
        "name": "ci_workflows",
        "desc": ".github/workflows 下的 yml 数",
        "pattern": r"CI\s*工作流(?:数)?[（(]?(\d{1,3})\s*个",
        "verify": "ls .github/workflows/*.yml | wc -l | tr -d ' '",
    },
    {
        "name": "insta_snapshots",
        "desc": "全仓 .snap 快照文件数",
        "pattern": r"(\d{3,5})\s*个(?:\s*insta)?\s*快照",
        "verify": "git ls-files '*.snap' | wc -l | tr -d ' '",
    },
    {
        "name": "tests_rs_files",
        "desc": "*_tests.rs 文件数",
        "pattern": r"(\d{2,5})\s*个\s*`?\*_tests\.rs`?",
        "verify": "git ls-files '*_tests.rs' | wc -l | tr -d ' '",
    },
    {
        "name": "ts_v2_schema_files",
        "desc": "schema/typescript/v2/ 下生成的 TS 文件数",
        "pattern": r"(\d{2,4})\s*个(?:生成的)?\s*(?:TS|ts)\s*(?:类型)?文件",
        "verify": (
            "git ls-files 'codex-rs/app-server-protocol/schema/typescript/v2/*' | wc -l | tr -d ' '"
        ),
    },
    {
        "name": "config_schema_keys",
        "desc": "config.schema.json 顶层键数",
        "pattern": r"(\d{1,3})\s*个(?:配置)?顶层键|顶层键[^\n]{0,6}?(\d{2,3})\s*个",
        "verify": (
            "python3 -c \"import json;"
            "print(len(json.load(open('codex-rs/core/config.schema.json'))['properties']))\""
        ),
    },
    {
        "name": "ext_crates",
        "desc": "codex-rs/ext/ 下的 crate 数",
        "pattern": r"(\d{1,3})\s*个\s*`?ext/\*`?\s*crate",
        "verify": "git ls-files 'codex-rs/ext/*/Cargo.toml' | wc -l | tr -d ' '",
    },
    {
        "name": "ext_with_extension_api",
        "desc": "依赖 codex-extension-api 的 ext/* crate 数",
        "pattern": r"(\d{1,3})\s*(?:个|/)\s*(?:ext/\*\s*)?(?:crate\s*)?依赖\s*`?codex-extension-api`?",
        # 第 6 轮修复：必须限定在 [dependencies] 段内。不限定的版本把
        # [dev-dependencies] 也算进来，正是 HIGH 错误 H3（首版得出 12/12）的成因。
        # 当前两种口径恰好都得 11，属巧合，不能据此保留宽口径写法。
        "verify": (
            "n=0; for f in codex-rs/ext/*/Cargo.toml; do "
            "awk '/^\\[dependencies\\]/{d=1;next}/^\\[/{d=0}d' \"$f\" "
            "| grep -q '^codex-extension-api' && n=$((n+1)); done; echo $n"
        ),
    },
    {
        "name": "cli_subcommand_variants",
        "desc": "CLI Subcommand 枚举变体数",
        "pattern": r"(\d{1,3})\s*个子命令变体",
        "verify": "",  # 需解析 Rust 枚举，代价高于收益，仅做跨文档一致性
    },
    {
        "name": "shipped_aux_binaries",
        "desc": "随正式发布交付的辅助可执行文件数（不含主二进制 codex）",
        "pattern": r"(\d{1,2})\s*个(?:随发布交付的)?辅助可执行文件",
        # 从两个发布工作流的 binaries / WINDOWS_BINARIES 取并集，去掉主二进制
        "verify": (
            "grep -hoE '(WINDOWS_)?[Bb]inaries: \"[^\"]*\"' "
            ".github/workflows/rust-release.yml .github/workflows/rust-release-windows.yml "
            "| sed -E 's/^[^\"]*\"//; s/\"$//' | tr ' ' '\\n' "
            "| grep -v '^codex$' | grep -v '^$' | sort -u | wc -l | tr -d ' '"
        ),
    },
    {
        "name": "agents_md_bytes",
        "desc": "AGENTS.md 字节数",
        "pattern": r"AGENTS\.md[^\n]{0,12}?([\d,]{4,9})\s*字节",
        "verify": "wc -c < AGENTS.md | tr -d ' '",
    },
]

LEDGER_PATH = Path(__file__).resolve().parent / "claim_ledger.jsonl"


def load_ledger() -> list[dict]:
    """读取断言账本。

    账本是本轮引入的：把散落在正文里的数值断言集中登记，每条附一条可复现命令与
    期望值。这样「同一事实在多篇文档里抄成不同数字」和「数字整体抄错」两类问题
    都能被机器拦下——前者靠 pattern 做跨文档对账，后者靠 verify/expected 对仓库真值。
    """
    if not LEDGER_PATH.exists():
        return []
    entries = []
    for lineno, line in enumerate(LEDGER_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"claim_ledger.jsonl:{lineno} 解析失败：{exc}", file=sys.stderr)
            continue
        if obj.get("id", "").startswith("_"):
            continue
        entries.append(obj)
    return entries


def merge_ledger_into_facts(ledger: list[dict]) -> None:
    """账本中带 pattern 的条目并入 FACTS，参与跨文档对账。

    同名条目以账本为准——账本是唯一事实源，脚本内建的 FACTS 只是历史遗留。
    """
    by_name = {f["name"]: f for f in FACTS}
    for e in ledger:
        if not e.get("pattern"):
            continue
        entry = {
            "name": e["id"],
            "desc": e.get("claim", e["id"]),
            "pattern": e["pattern"],
            "verify": e.get("verify", ""),
        }
        if e["id"] in by_name:
            by_name[e["id"]].update(entry)
        else:
            FACTS.append(entry)


def check_ledger_expectations(ledger: list[dict]) -> list[dict]:
    """对账本中每条带 expected 的断言执行其命令，校验期望值仍然成立。"""
    issues = []
    for e in ledger:
        cmd, expected = e.get("verify", ""), e.get("expected", "")
        if not cmd or expected == "":
            continue
        got = run_verify(cmd)
        if got is None:
            issues.append(
                {
                    "type": "ledger_verify_failed",
                    "id": e["id"],
                    "claim": e.get("claim", ""),
                    "command": cmd,
                }
            )
        elif got.replace(",", "") != str(expected).replace(",", ""):
            issues.append(
                {
                    "type": "ledger_expected_stale",
                    "id": e["id"],
                    "claim": e.get("claim", ""),
                    "expected": expected,
                    "actual": got,
                    "command": cmd,
                }
            )
    return issues


def check_ledger_todo(ledger: list[dict]) -> list[dict]:
    """expected 留空 = 本轮尚未复核确认，列为待办而非通过。"""
    return [
        {"type": "ledger_unconfirmed", "id": e["id"], "claim": e.get("claim", "")}
        for e in ledger
        if e.get("expected", "") == ""
    ]

# 标题中声明计数的写法。
#
# 只认「裸数字括号」`（20）`与「N 个 X」两种。若括号内还有别的字（如 `（涉及 19 个 crate）`），
# 视为作者显式说明该计数指的不是表格行数，跳过——这就是本检查的 opt-out 方式，
# 无需额外标记语法。行尾加 `<!-- no-count-check -->` 亦可跳过。
HEADING_COUNT_PATTERNS = [
    re.compile(r"^#{2,4}\s+.*?[（(](\d{1,3})\s*个?[)）]\s*$"),
    re.compile(r"^#{2,4}\s+.*?(\d{1,3})\s*个\s*[^\s（(]+\s*$"),
]

OPT_OUT_MARKER = "no-count-check"


def _norm(raw: str) -> int:
    return int(raw.replace(",", ""))


def iter_docs() -> list[Path]:
    return sorted(p for p in DOC_ROOT.rglob("*.md") if p.is_file())


def strip_code_blocks(text: str) -> str:
    """去掉围栏代码块，避免把示例命令里的数字当成断言。"""
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append("")
            continue
        out.append("" if fence else line)
    return "\n".join(out)


def collect_fact_values(docs: list[Path]) -> dict[str, list[tuple[Path, int, int]]]:
    """返回 {fact_name: [(path, lineno, value), ...]}"""
    found: dict[str, list[tuple[Path, int, int]]] = {f["name"]: [] for f in FACTS}
    compiled = [(f["name"], re.compile(f["pattern"])) for f in FACTS]
    for path in docs:
        body = strip_code_blocks(path.read_text(encoding="utf-8"))
        for lineno, line in enumerate(body.splitlines(), 1):
            for name, rx in compiled:
                for m in rx.finditer(line):
                    raw = next((g for g in m.groups() if g), None)
                    if raw:
                        found[name].append((path, lineno, _norm(raw)))
    return found


def count_table_entities(lines: list[str], start: int) -> tuple[int, int, int] | None:
    """从 start 行起找第一张 markdown 表。

    返回 (实体数, 每行实体数, 表首行号)。

    多数表是「一行一个实体」。但也有并排布局，例如表头为
    `| crate | 行数 | crate | 行数 |`——此时首列名重复 2 次，每行承载 2 个实体。
    据此推断每行实体数，再扣掉空的实体单元格，才能与标题声明的计数正确比对。
    """
    i = start
    limit = min(len(lines), start + 12)
    while i < limit and not (lines[i].lstrip().startswith("|") and lines[i].count("|") >= 2):
        if lines[i].lstrip().startswith("#"):
            return None  # 中途遇到新标题，说明该标题下无紧邻表格
        i += 1
    if i >= limit:
        return None
    header_line = i
    if i + 1 >= len(lines) or not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
        return None

    header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
    per_row = max(1, header.count(header[0])) if header else 1
    # 实体列在每组中的下标（按首列名出现位置）
    entity_cols = [k for k, name in enumerate(header) if name == header[0]] or [0]

    j = i + 2
    entities = 0
    while j < len(lines) and lines[j].lstrip().startswith("|"):
        cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
        if cells and not re.fullmatch(r"[—\-*_\s]*", cells[0]) and "合计" not in cells[0]:
            for col in entity_cols:
                if col < len(cells) and not re.fullmatch(r"[—\-*_\s]*", cells[col]):
                    entities += 1
        j += 1
    return entities, per_row, header_line + 1


def check_heading_counts(docs: list[Path]) -> list[dict]:
    issues = []
    for path in docs:
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if not line.startswith("#"):
                continue
            declared = None
            for rx in HEADING_COUNT_PATTERNS:
                m = rx.match(line.rstrip())
                if m:
                    declared = _norm(m.group(1))
                    break
            if declared is None or OPT_OUT_MARKER in line:
                continue
            res = count_table_entities(lines, idx + 1)
            if res is None:
                continue
            entities, per_row, table_line = res
            if entities != declared:
                issues.append(
                    {
                        "type": "heading_count_vs_table_rows",
                        "file": str(path.relative_to(REPO_ROOT)),
                        "line": idx + 1,
                        "heading": line.strip(),
                        "declared": declared,
                        "actual_rows": entities,
                        "per_row": per_row,
                        "table_at_line": table_line,
                    }
                )
    return issues


# 兼容三种写法：`other.md` §5 — 标题 / [文字](./other.md) §5 — 标题 / other.md §5 — 标题
SECTION_REF = re.compile(
    r"([\w./-]+\.md)[`\)\]]*\s*§\s*(\d+(?:\.\d+)*)\s*(?:—|——|--|－|-)\s*([^\n|，。；]{2,30})"
)
HEADING_NUM = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)*)[\s、.．]\s*(.+?)\s*$")


def build_heading_index() -> dict[str, dict[str, str]]:
    """{文件名: {章节号: 标题文字}}"""
    index: dict[str, dict[str, str]] = {}
    for p in iter_docs():
        table: dict[str, str] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            m = HEADING_NUM.match(line)
            if m:
                table[m.group(1)] = re.sub(r"[（(].*?[)）]", "", m.group(2)).strip()
        index[p.name] = table
    return index


def check_section_refs(docs: list[Path]) -> list[dict]:
    """校验形如 `other.md §5 — 审批与沙箱策略` 的跨文档引用。

    只验章节号存在是不够的——章节号会因插入新章节而整体顺延，此时旧引用
    仍指向一个「存在但内容已换」的章节。引用里带的标题文字正是判据：
    标题对不上就说明引用已漂移。第二轮审查中 core_agent_loop.md 插入
    新的 §2 后，就有 4 处引用变成了指向错误章节。
    """
    index = build_heading_index()
    issues = []
    for path in docs:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in SECTION_REF.finditer(line):
                target, num, label = m.group(1), m.group(2), m.group(3).strip()
                name = Path(target).name
                if name not in index or name == path.name:
                    continue
                headings = index[name]
                if num not in headings:
                    issues.append(
                        {
                            "type": "section_ref_missing",
                            "file": str(path.relative_to(REPO_ROOT)),
                            "line": lineno,
                            "target": name,
                            "num": num,
                            "label": label,
                        }
                    )
                    continue
                actual = headings[num]
                head = re.sub(r"[`*_]", "", label)[:6]
                # 找出标题真正匹配的章节号
                suggest = [k for k, v in headings.items() if (head and head in v) or v[:6] in label]
                # 判据：引用后的文字往往是作者的描述而非原标题，匹配不上很正常。
                # 只有当这段文字明确匹配到了「另一个」章节时，才说明引用漂移了。
                # 引父节而匹配到其子节（如引 §7、标题匹配 §7.2）是合法的精度差异，不算漂移
                suggest = [k for k in suggest if not k.startswith(num + ".")]
                if suggest and num not in suggest:
                    issues.append(
                        {
                            "type": "section_ref_drifted",
                            "file": str(path.relative_to(REPO_ROOT)),
                            "line": lineno,
                            "target": name,
                            "num": num,
                            "label": label,
                            "actual_title": actual,
                            "suggest": suggest,
                        }
                    )
    return issues


def run_verify(cmd: str) -> str | None:
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip().splitlines()
    return out[0].strip() if out else None


def main() -> int:
    ap = argparse.ArgumentParser(description="dev_docs 跨文档数值对账")
    ap.add_argument(
        "--verify-repo",
        action="store_true",
        help="额外执行每个事实的可复现命令，用仓库真值校验文档数字",
    )
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    docs = iter_docs()
    if not docs:
        print(f"未找到文档：{DOC_ROOT}", file=sys.stderr)
        return 1

    ledger = load_ledger()
    merge_ledger_into_facts(ledger)

    issues: list[dict] = []
    values = collect_fact_values(docs)

    truth: dict[str, str] = {}
    if args.verify_repo:
        for fact in FACTS:
            if fact["verify"]:
                got = run_verify(fact["verify"])
                if got is not None:
                    truth[fact["name"]] = got

    for fact in FACTS:
        name = fact["name"]
        hits = values[name]
        if not hits:
            continue
        distinct = sorted({v for _, _, v in hits})

        if len(distinct) > 1:
            issues.append(
                {
                    "type": "cross_doc_value_conflict",
                    "fact": name,
                    "desc": fact["desc"],
                    "values": distinct,
                    "occurrences": [
                        {
                            "file": str(p.relative_to(REPO_ROOT)),
                            "line": ln,
                            "value": v,
                        }
                        for p, ln, v in hits
                    ],
                }
            )

        if name in truth:
            try:
                expected = _norm(truth[name])
            except ValueError:
                expected = None
            if expected is not None:
                wrong = [(p, ln, v) for p, ln, v in hits if v != expected]
                if wrong:
                    issues.append(
                        {
                            "type": "doc_value_contradicts_repo",
                            "fact": name,
                            "desc": fact["desc"],
                            "repo_truth": expected,
                            "command": fact["verify"],
                            "occurrences": [
                                {
                                    "file": str(p.relative_to(REPO_ROOT)),
                                    "line": ln,
                                    "value": v,
                                }
                                for p, ln, v in wrong
                            ],
                        }
                    )

    issues.extend(check_heading_counts(docs))
    issues.extend(check_section_refs(docs))
    issues.extend(check_ledger_todo(ledger))
    if args.verify_repo:
        issues.extend(check_ledger_expectations(ledger))

    if args.json:
        print(
            json.dumps(
                {
                    "docs_scanned": len(docs),
                    "facts_registered": len(FACTS),
                    "repo_truth_resolved": len(truth),
                    "issue_count": len(issues),
                    "issues": issues,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if issues else 0

    print(f"扫描文档 {len(docs)} 篇，账本 {len(ledger)} 条，已登记事实 {len(FACTS)} 项", end="")
    if args.verify_repo:
        print(f"，其中 {len(truth)} 项已取得仓库真值")
    else:
        print("（未开启 --verify-repo，仅做跨文档一致性）")

    if not issues:
        print("\n✅ 无不一致")
        return 0

    print(f"\n❌ 发现 {len(issues)} 个问题\n")
    for it in issues:
        if it["type"] == "cross_doc_value_conflict":
            print(f"[跨文档取值冲突] {it['fact']} — {it['desc']}")
            print(f"  出现的不同取值：{it['values']}")
            for o in it["occurrences"]:
                print(f"    {o['file']}:{o['line']} = {o['value']}")
        elif it["type"] == "doc_value_contradicts_repo":
            print(f"[与仓库真值不符] {it['fact']} — {it['desc']}")
            print(f"  仓库真值 = {it['repo_truth']}")
            print(f"  复现命令 = {it['command']}")
            for o in it["occurrences"]:
                print(f"    {o['file']}:{o['line']} 写的是 {o['value']}")
        elif it["type"] == "ledger_expected_stale":
            print(f"[账本期望值已过期] {it['id']} — {it['claim']}")
            print(f"  期望 {it['expected']}，实测 {it['actual']}")
            print(f"  复现命令 = {it['command']}")
        elif it["type"] == "ledger_verify_failed":
            print(f"[账本命令执行失败] {it['id']} — {it['claim']}")
            print(f"  命令 = {it['command']}")
        elif it["type"] == "ledger_unconfirmed":
            print(f"[账本待复核] {it['id']} — {it['claim']}（expected 留空，尚未确认）")
        elif it["type"] == "section_ref_missing":
            print(f"[跨文档章节引用指向不存在的章节] {it['file']}:{it['line']}")
            print(f"  引用 {it['target']} §{it['num']}（{it['label']}），该章节不存在")
        elif it["type"] == "section_ref_drifted":
            print(f"[跨文档章节引用已漂移] {it['file']}:{it['line']}")
            print(f"  引用写的是 {it['target']} §{it['num']} — {it['label']}")
            print(f"  但该文档 §{it['num']} 实际标题是「{it['actual_title']}」")
            if it["suggest"]:
                print(f"  标题匹配的章节号可能是：§{'、§'.join(it['suggest'])}")
        else:
            print(f"[标题计数与表格实体数不符] {it['file']}:{it['line']}")
            print(f"  标题：{it['heading']}")
            per = it.get("per_row", 1)
            layout = "" if per == 1 else f"（该表并排布局，每行 {per} 个实体）"
            print(f"  声明 {it['declared']} 项，紧随的表格实际 {it['actual_rows']} 项{layout}")
            print("  如该计数本就不指表格实体数，请在标题括号内加以说明，或行尾加 <!-- no-count-check -->")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
