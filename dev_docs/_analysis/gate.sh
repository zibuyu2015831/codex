#!/usr/bin/env bash
# dev_docs 提交前门禁总入口。每批提交前跑一次，全绿方可提交。
#
# 注意：全绿是**必要条件，不是充分条件**。本项目实测过一条基准率——每一轮修复都会
# 引入 6~7 个新的 HIGH 级事实错误，而那些错误全部是在门禁全绿的状态下由独立代理
# 发现的。门禁只覆盖结构、引用与已登记数值；断言是否与源码相符，只能靠独立复核。
#
# 用法：bash dev_docs/_analysis/gate.sh [--fast]
#   --fast 跳过需要执行仓库命令的 --verify-repo（cargo metadata 较慢）
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

fast=0
[ "${1:-}" = "--fast" ] && fast=1
rc=0

echo "═══ 1/3 脱敏门禁 ═══"
bash dev_docs/_analysis/redact_scan.sh || rc=1

echo
echo "═══ 2/3 引用可解析性 ═══"
python3 dev_docs/_analysis/ref_checker.py || rc=1

echo
echo "═══ 3/3 跨文档对账与断言账本 ═══"
if [ "$fast" -eq 1 ]; then
  python3 dev_docs/_analysis/cross_doc_consistency_checker.py || rc=1
else
  python3 dev_docs/_analysis/cross_doc_consistency_checker.py --verify-repo || rc=1
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "✅ 门禁全绿。提醒：这只说明结构与已登记数值无误，不代表断言正确。"
else
  echo "❌ 门禁未通过。"
fi
exit "$rc"
