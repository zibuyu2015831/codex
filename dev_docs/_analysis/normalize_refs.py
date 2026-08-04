#!/usr/bin/env python3
"""把 dev_docs 中的仓库路径引用归一化为「仓库根相对路径」。

背景：本体系的机制是「入口文档 + 按需阅读」，子代理拿到引用后要能直接定位文件。
首次扫描时 2,510 条引用里只有 629 条（25%）可从仓库根解析，其余是 crate 内相对
写法（`loader/mod.rs`）或裸文件名（`main.rs`）——人能看懂，机器定位不了。

本脚本只改**全仓唯一匹配**的引用（`ref_checker.py` 判为 unique 的那类），
这类改写是无歧义的机械操作。多个同名文件的歧义引用（`main.rs` 有 17 个）
必须由了解上下文的人/代理逐条决定，本脚本一律不碰，只列出待办。

围栏代码块内的路径不改——那些是带 cwd 的命令，改成根相对反而会错。

用法：
    python3 dev_docs/_analysis/normalize_refs.py --dry-run     # 只看会改什么
    python3 dev_docs/_analysis/normalize_refs.py --apply
    python3 dev_docs/_analysis/normalize_refs.py --apply --only crate_map
    python3 dev_docs/_analysis/normalize_refs.py --list-ambiguous
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ref_checker import DOC_ROOT, REF, REPO_ROOT, resolve  # noqa: E402


def rewrite_line(line: str, changes: list[tuple[str, str]]) -> str:
    def sub(m: re.Match[str]) -> str:
        ref, spec = m.group(1), m.group(2)
        if ref.startswith("dev_docs/"):
            return m.group(0)
        state, resolved, _ = resolve(ref)
        if state != "unique" or not resolved:
            return m.group(0)
        changes.append((ref, resolved))
        return f"`{resolved}{spec}`"

    return REF.sub(sub, line)


def rewrite_related_files(line: str, changes: list[tuple[str, str]]) -> str:
    """frontmatter 的 related_files 是 `|` 分隔的裸路径，不带反引号，单独处理。"""
    prefix, _, rest = line.partition(":")
    items = []
    for raw in rest.split("|"):
        item = raw.strip()
        if not item:
            continue
        state, resolved, _ = resolve(item)
        if state == "unique" and resolved:
            changes.append((item, resolved))
            items.append(resolved)
        else:
            items.append(item)
    return f"{prefix}: {' | '.join(items)}"


def process(path: Path, apply: bool) -> tuple[int, list[tuple[str, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changes: list[tuple[str, str]] = []
    out: list[str] = []
    fence = False
    in_fm = False
    for idx, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if idx == 0 and stripped == "---":
            in_fm = True
            out.append(line)
            continue
        if in_fm:
            if stripped == "---":
                in_fm = False
                out.append(line)
                continue
            if stripped.startswith("related_files:"):
                new = rewrite_related_files(stripped, changes)
                out.append(new + "\n")
                continue
            out.append(line)
            continue
        if stripped.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        out.append(rewrite_line(stripped, changes) + ("\n" if line.endswith("\n") else ""))

    if apply and changes:
        path.write_text("".join(out), encoding="utf-8")
    return len(changes), changes


def list_ambiguous(docs: list[Path]) -> None:
    buckets: dict[str, list[str]] = defaultdict(list)
    fence_state: dict[Path, bool] = {}
    for path in docs:
        fence = False
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if raw.lstrip().startswith("```"):
                fence = not fence
                continue
            if fence:
                continue
            for m in REF.finditer(raw):
                ref = m.group(1)
                if ref.startswith("dev_docs/"):
                    continue
                state, _, cands = resolve(ref)
                if state == "ambiguous":
                    ctx = raw.strip()
                    buckets[ref].append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}  {ctx[:150]}"
                    )
        fence_state[path] = fence

    print(f"歧义引用 {len(buckets)} 种，共 {sum(len(v) for v in buckets.values())} 处")
    print("（这些必须结合上下文逐条判定，脚本不自动改）\n")
    for ref, occ in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        _, _, cands = resolve(ref)
        print(f"### `{ref}`  ×{len(occ)}  仓库中 {len(cands)} 个同名")
        for line in occ:
            print(f"    {line}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="只处理文件名含该子串的文档")
    ap.add_argument("--list-ambiguous", action="store_true")
    args = ap.parse_args()

    docs = sorted(p for p in DOC_ROOT.rglob("*.md") if p.is_file())
    if args.only:
        docs = [p for p in docs if args.only in p.name]

    if args.list_ambiguous:
        list_ambiguous(docs)
        return 0

    if not (args.apply or args.dry_run):
        ap.error("需指定 --apply 或 --dry-run")

    total = 0
    for path in docs:
        n, changes = process(path, apply=args.apply)
        if not n:
            continue
        total += n
        uniq = sorted({c for c in changes})
        print(f"{path.relative_to(REPO_ROOT)}: {n} 处（{len(uniq)} 种）")
        for old, new in uniq[:6]:
            print(f"    {old}  →  {new}")
        if len(uniq) > 6:
            print(f"    … 另 {len(uniq) - 6} 种")
    verb = "已改写" if args.apply else "将改写"
    print(f"\n{verb} {total} 处引用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
