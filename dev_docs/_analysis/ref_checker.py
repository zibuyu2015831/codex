#!/usr/bin/env python3
"""dev_docs 引用可解析性检查器。

本体系的运行机制是「会话中携带入口文档，按需阅读」——子代理拿到一条引用后
必须能**直接定位到文件**。因此一条无法从仓库根解析的引用，等价于一条断掉的链接，
危害不亚于事实错误。

首次扫描的基线（修订前）：2,475 条仓库路径引用中，仅 616 条（25%）可从仓库根
直接解析；414 条是 crate 内相对写法（`loader/mod.rs`），1,445 条是裸文件名
（`main.rs`、`manager.rs`）——后两类人能看懂，机器定位不了。

本脚本检查五件事：

  1. **路径可解析性**：每条 `` `path` `` 引用能否从仓库根直接定位。
     不能直接定位但加 `codex-rs/` 前缀可解析、或全仓唯一同名文件，均给出修复建议。
  2. **行号越界**：`` `path:123` `` 中的行号不得超过文件实际行数。
  3. **符号邻近性**：同一行若同时出现路径引用与符号名（`fn_name()`/`TypeName`），
     校验该符号确实出现在被引文件中；若引用带行号，还校验符号出现在该行附近。
     这是唯一能自动发现「引用指向了错误文件」的检查。
  4. **文档内部链接**：`[文字](./other.md)` 的目标文件存在。
  5. **frontmatter**：7 个必需字段齐备，且 `related_files` 中每条路径可解析。

用法：
    python3 dev_docs/_analysis/ref_checker.py
    python3 dev_docs/_analysis/ref_checker.py --json
    python3 dev_docs/_analysis/ref_checker.py --strict   # 把 WARN 也算作失败

退出码：0 = 无 ERROR；1 = 存在 ERROR（--strict 下 WARN 亦致失败）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "dev_docs"

# 引用形如 `path/to/file.rs` 或 `path/to/file.rs:120` 或 `file.rs:120-140`
REF = re.compile(
    r"`([~/]?[A-Za-z0-9_.@/-]+\.(?:rs|py|toml|md|json|jsonl|ts|tsx|js|yml|yaml|sh|bzl|bazel"
    r"|nix|lock|sbpl|snap|txt|proto|sql))((?::\d+(?:-\d+)?)*)`"
)

# 同一行中的符号名候选：`foo()`、`foo_bar()`、`TypeName`、`CONST_NAME`、`mod::path`
SYMBOL = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*)(\(\))?`")

# 运行时产物：这些名字指的是用户机器上生成的文件，不是仓库内文件，不参与解析
RUNTIME_BASENAMES = {
    "config.toml",
    "auth.json",
    "requirements.toml",
    "managed_config.toml",
    "history.jsonl",
    "session_index.jsonl",
    "rollout-compression.lock",
    ".coordination.lock",
    "version.json",
    "settings.json",
    "package-lock.json",
    "keybindings.json",
}

# 不当作符号名的常见词（避免把散文里的普通标记误判为符号）
SYMBOL_STOPWORDS = {
    "true",
    "false",
    "None",
    "Some",
    "Ok",
    "Err",
    "String",
    "Vec",
    "Option",
    "Result",
    "bool",
    "u8",
    "u32",
    "u64",
    "usize",
    "i32",
    "i64",
    "str",
    "self",
    "Self",
    "main",
    "src",
    "dev_docs",
    "codex",
    "cargo",
    "bazel",
    "just",
    "git",
    "npm",
    "pnpm",
    "python3",
    "justfile",
    "Cargo",
    "AGENTS",
    "README",
    "BUILD",
    "MODULE",
}

# AI-Coding-Context 框架自带的模板文件名。它们属于框架而非本仓库，
# 在 generation_plan.md 中被引用是正常的，不应判为断链。
FRAMEWORK_REFS = {
    "cli_usage.md",
    "installation.md",
    "plugin_system.md",
    "core/project_types/cli_tool.md",
    "core/project_types/library.md",
    "core/project_types/web_app.md",
    "AI_Coding_Context.md.template",
    "config/user_config.md",
    "path_a_first_generation.md",
    "main_doc_contract.yaml",
    "project_scanner.py",
    "configuration.md",
    "cli_tool.md",
    "templates/plans_README_TEMPLATE.md",
    "templates/knowledge_README_TEMPLATE.md",
    "templates/AI_RULES_TEMPLATE.md",
}

# 环境变量展开后的运行时路径前缀
RUNTIME_PREFIXES = ("CODEX_HOME/", "$CODEX_HOME/", "%CODEX_HOME%/", "XDG_CONFIG_HOME/")

FRONTMATTER_FIELDS = [
    "title",
    "summary",
    "keywords",
    "scope",
    "related_files",
    "dependencies",
    "verified_at",
]

SYMBOL_NEAR_WINDOW = 40  # 带行号的引用，符号应出现在该行 ±40 行内

# 行级豁免标记。用于两种正当情形：
#   1. 泛指——「以 `Cargo.toml` 的 name 为准」说的是任意 crate 的清单，不指某一个文件；
#   2. 反例——正文正在说明「`AGENTS.md` 给的这个路径不存在」，引用不可解析恰是要表达的事实。
# 没有豁免机制的检查器最终会被整个关掉，所以这个口子必须留，但要求写明理由。
EXEMPT_MARKER = re.compile(r"<!--\s*ref-exempt(?::\s*(?P<why>[^>]*?))?\s*-->")


@lru_cache(maxsize=1)
def tracked_files() -> tuple[str, ...]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return tuple(line for line in out.splitlines() if line)


@lru_cache(maxsize=1)
def doc_stems() -> frozenset[str]:
    """本体系自身的文档名（去扩展名）。表格里出现 `observability` 指的是文档，
    不是源码符号，不能拿去源文件里找。"""
    return frozenset(p.stem for p in DOC_ROOT.rglob("*.md"))


@lru_cache(maxsize=1)
def basename_index() -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for p in tracked_files():
        idx[p.rsplit("/", 1)[-1]].append(p)
    return dict(idx)


@lru_cache(maxsize=1)
def suffix_index() -> dict[str, list[str]]:
    """后缀索引：把每个跟踪文件的所有路径后缀（按 / 切分）都登记一遍。

    用于把 `loader/mod.rs` 这类 crate 内相对写法映射回完整路径。
    """
    idx: dict[str, list[str]] = defaultdict(list)
    for p in tracked_files():
        parts = p.split("/")
        for i in range(len(parts)):
            idx["/".join(parts[i:])].append(p)
    return dict(idx)


@lru_cache(maxsize=4096)
def file_lines(rel: str) -> int:
    fp = REPO_ROOT / rel
    try:
        with fp.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


@lru_cache(maxsize=4096)
def file_text(rel: str) -> str:
    try:
        return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def resolve(ref: str) -> tuple[str, str | None, list[str]]:
    """返回 (状态, 解析到的路径, 候选列表)。

    状态取值：
      ok        —— 从仓库根直接解析成功
      prefix    —— 加 codex-rs/ 等前缀后唯一解析成功（应归一化）
      unique    —— 后缀/文件名全仓唯一匹配（应归一化）
      ambiguous —— 匹配到多个文件，机器无法定位
      runtime   —— 运行时产物，不参与解析
      broken    —— 仓库中找不到任何匹配
    """
    if ref.startswith(("/", "~")) or ref.startswith(RUNTIME_PREFIXES):
        return "runtime", None, []
    if ref in FRAMEWORK_REFS:
        return "runtime", None, []
    # 本体系自身的文档名（`tui_guide.md`）在导航表里裸写是可读且无歧义的，不要求带 dev_docs/ 前缀
    if ref.endswith(".md") and "/" not in ref and ref[:-3] in doc_stems():
        return "internal_doc", None, []

    if (REPO_ROOT / ref).exists():
        return "ok", ref, []

    cands = suffix_index().get(ref)
    if cands:
        return ("unique", cands[0], []) if len(cands) == 1 else ("ambiguous", None, cands)

    base = ref.rsplit("/", 1)[-1]
    if base in RUNTIME_BASENAMES:
        return "runtime", None, []

    if "/" not in ref:
        hits = basename_index().get(ref, [])
        if len(hits) == 1:
            return "unique", hits[0], []
        if len(hits) > 1:
            return "ambiguous", None, hits

    return "broken", None, []


def strip_fences(text: str) -> list[str]:
    """把围栏代码块内的行置空，保留行号对齐。"""
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append("")
            continue
        out.append("" if fence else line)
    return out


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def check_doc(path: Path, issues: list[dict]) -> dict[str, int]:
    rel_doc = str(path.relative_to(REPO_ROOT))
    raw = path.read_text(encoding="utf-8")
    lines = strip_fences(raw)
    stats = defaultdict(int)

    # ---- frontmatter ----
    fm = parse_frontmatter(raw)
    if not fm:
        issues.append({"sev": "ERROR", "type": "frontmatter_missing", "file": rel_doc, "line": 1})
    else:
        for field in FRONTMATTER_FIELDS:
            if not fm.get(field):
                issues.append(
                    {
                        "sev": "ERROR",
                        "type": "frontmatter_field_missing",
                        "file": rel_doc,
                        "line": 1,
                        "field": field,
                    }
                )
        for item in (fm.get("related_files") or "").split("|"):
            item = item.strip()
            if not item:
                continue
            state, _, cands = resolve(item)
            if state in ("broken", "ambiguous"):
                issues.append(
                    {
                        "sev": "ERROR",
                        "type": "related_file_unresolvable",
                        "file": rel_doc,
                        "line": 1,
                        "ref": item,
                        "state": state,
                        "candidates": cands[:5],
                    }
                )
            elif state in ("prefix", "unique"):
                issues.append(
                    {
                        "sev": "WARN",
                        "type": "related_file_not_root_relative",
                        "file": rel_doc,
                        "line": 1,
                        "ref": item,
                        "suggest": _,
                    }
                )

    # ---- 正文引用 ----
    for lineno, line in enumerate(lines, 1):
        # 文档内部相对链接
        for m in re.finditer(r"\]\((\./[^)]+\.md)(#[^)]*)?\)", line):
            target = (path.parent / m.group(1)).resolve()
            if not target.exists():
                issues.append(
                    {
                        "sev": "ERROR",
                        "type": "internal_link_broken",
                        "file": rel_doc,
                        "line": lineno,
                        "ref": m.group(1),
                    }
                )

        refs = list(REF.finditer(line))
        if not refs:
            continue
        if EXEMPT_MARKER.search(line):
            stats["exempt"] += len(refs)
            continue

        symbols = [
            (s.group(1), bool(s.group(2)))
            for s in SYMBOL.finditer(line)
            if s.group(1) not in SYMBOL_STOPWORDS and s.group(1) not in doc_stems()
        ]

        for m in refs:
            ref, linespec = m.group(1), m.group(2)
            if ref.startswith("dev_docs/"):
                continue
            stats["refs"] += 1
            state, resolved, cands = resolve(ref)
            stats[state] += 1

            if state == "broken":
                issues.append(
                    {
                        "sev": "ERROR",
                        "type": "ref_broken",
                        "file": rel_doc,
                        "line": lineno,
                        "ref": ref,
                    }
                )
                continue
            if state == "ambiguous":
                issues.append(
                    {
                        "sev": "ERROR",
                        "type": "ref_ambiguous",
                        "file": rel_doc,
                        "line": lineno,
                        "ref": ref,
                        "candidates": cands[:6],
                        "match_count": len(cands),
                    }
                )
                continue
            if state in ("runtime", "internal_doc"):
                continue
            if state in ("prefix", "unique"):
                issues.append(
                    {
                        "sev": "WARN",
                        "type": "ref_not_root_relative",
                        "file": rel_doc,
                        "line": lineno,
                        "ref": ref,
                        "suggest": resolved,
                    }
                )

            assert resolved is not None
            nlines = file_lines(resolved)

            cited: list[int] = []
            for num in re.findall(r":(\d+)", linespec or ""):
                n = int(num)
                cited.append(n)
                if nlines and n > nlines:
                    issues.append(
                        {
                            "sev": "ERROR",
                            "type": "line_out_of_range",
                            "file": rel_doc,
                            "line": lineno,
                            "ref": f"{ref}:{n}",
                            "resolved": resolved,
                            "file_lines": nlines,
                        }
                    )

            # 符号邻近性：仅当本行恰有一条路径引用时才做，多引用行归属不明
            if len(refs) == 1 and symbols and resolved.endswith((".rs", ".py", ".ts", ".tsx")):
                text = file_text(resolved)
                body = text.splitlines()
                for sym, is_call in symbols:
                    leaf = sym.split("::")[-1]
                    if len(leaf) < 4:
                        continue
                    if leaf not in text:
                        issues.append(
                            {
                                "sev": "WARN",
                                "type": "symbol_not_in_file",
                                "file": rel_doc,
                                "line": lineno,
                                "ref": ref,
                                "resolved": resolved,
                                "symbol": leaf + ("()" if is_call else ""),
                            }
                        )
                    elif cited:
                        hits = [i for i, ln in enumerate(body, 1) if leaf in ln]
                        near = [h for h in hits if any(abs(h - c) <= SYMBOL_NEAR_WINDOW for c in cited)]
                        if hits and not near:
                            issues.append(
                                {
                                    "sev": "WARN",
                                    "type": "symbol_far_from_cited_line",
                                    "file": rel_doc,
                                    "line": lineno,
                                    "ref": f"{ref}:{cited[0]}",
                                    "resolved": resolved,
                                    "symbol": leaf,
                                    "actual_lines": hits[:6],
                                }
                            )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="dev_docs 引用可解析性检查")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="WARN 也算失败")
    ap.add_argument("--only", help="只检查文件名匹配该子串的文档")
    args = ap.parse_args()

    docs = sorted(p for p in DOC_ROOT.rglob("*.md") if p.is_file())
    if args.only:
        docs = [p for p in docs if args.only in p.name]
    if not docs:
        print(f"未找到文档：{DOC_ROOT}", file=sys.stderr)
        return 1

    issues: list[dict] = []
    totals: dict[str, int] = defaultdict(int)
    for doc in docs:
        for k, v in check_doc(doc, issues).items():
            totals[k] += v

    errors = [i for i in issues if i["sev"] == "ERROR"]
    warns = [i for i in issues if i["sev"] == "WARN"]

    if args.json:
        print(
            json.dumps(
                {
                    "docs_scanned": len(docs),
                    "totals": dict(totals),
                    "error_count": len(errors),
                    "warn_count": len(warns),
                    "issues": issues,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if errors or (args.strict and warns) else 0

    root_ok = totals.get("ok", 0)
    total = totals.get("refs", 0)
    pct = (100 * root_ok / total) if total else 100.0
    print(f"扫描文档 {len(docs)} 篇，仓库路径引用 {total} 条")
    print(f"  可从仓库根直接解析：{root_ok}（{pct:.1f}%）")
    for state, label in (
        ("unique", "需归一化（全仓唯一匹配）"),
        ("ambiguous", "无法定位（多个同名文件）"),
        ("exempt", "已标注豁免（泛指或反例）"),
        ("internal_doc", "本体系文档名（免于前缀要求）"),
        ("runtime", "运行时产物（不参与解析）"),
        ("broken", "仓库中不存在"),
    ):
        if totals.get(state):
            print(f"  {label}：{totals[state]}")

    by_type: dict[str, int] = defaultdict(int)
    for i in issues:
        by_type[i["type"]] += 1
    if by_type:
        print("\n问题分布：")
        for t, c in sorted(by_type.items(), key=lambda kv: -kv[1]):
            sev = next(i["sev"] for i in issues if i["type"] == t)
            print(f"  [{sev:5}] {t}: {c}")

    if not errors and not warns:
        print("\n✅ 引用全部可解析")
        return 0

    print(f"\n{'❌' if errors else '⚠️'} ERROR {len(errors)} 条，WARN {len(warns)} 条\n")
    shown: dict[str, int] = defaultdict(int)
    for i in errors + warns:
        shown[i["type"]] += 1
        if shown[i["type"]] > 12:
            continue
        extra = ""
        if i["type"] == "ref_ambiguous":
            extra = f" → {i['match_count']} 个同名：{', '.join(i['candidates'][:3])} …"
        elif i["type"] in ("ref_not_root_relative", "related_file_not_root_relative"):
            extra = f" → 应写 {i['suggest']}"
        elif i["type"] == "line_out_of_range":
            extra = f" → {i['resolved']} 仅 {i['file_lines']} 行"
        elif i["type"] == "symbol_not_in_file":
            extra = f" → {i['resolved']} 中找不到符号 {i['symbol']}"
        elif i["type"] == "symbol_far_from_cited_line":
            extra = f" → 符号 {i['symbol']} 实际在 {i['actual_lines']} 行"
        elif i["type"] == "frontmatter_field_missing":
            extra = f" → 缺字段 {i['field']}"
        elif i["type"] == "related_file_unresolvable":
            extra = f" → {i['state']}"
        print(f"  [{i['sev']:5}] {i['file']}:{i['line']} {i.get('ref', '')}{extra}")
    for t, c in shown.items():
        if c > 12:
            print(f"  … {t} 另有 {c - 12} 条未显示（用 --json 查看全部）")

    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
