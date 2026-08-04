#!/usr/bin/env bash
# dev_docs 脱敏门禁。每批提交前必跑，退出码非 0 即禁止提交。
#
# 本仓库 fork 为公开仓库，dev_docs/ 全部内容公开可检索，因此这道扫描是硬门禁。
#
# 各条正则的收紧理由：
#   - 凭证：必须是「键 + 分隔符 + 引号包裹的字面量」。只要 `token:` 后跟标识符就报警的
#     宽正则会命中 `cancellation_token: CancellationToken` 这类正常代码引文，
#     报警一多就会被整体忽略，反而失去门禁作用。
#   - 本地路径：/Users/ 后必须跟真实路径段，因而不匹配本脚本自身，
#     也不匹配文档中 /Users/<用户名>/ 这类已脱敏的占位写法。
#   - SSH 组织串：形如 org-<数字>@github.com，会同时泄露作者身份与组织数字 ID，
#     首轮审查曾在 project_analysis_report.md 中实际检出过一处。
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

fail=0
scan() {
  local label="$1" pattern="$2"
  local hits
  hits=$(grep -rnE --binary-files=without-match \
           --exclude-dir=__pycache__ --exclude='*.pyc' \
           "$pattern" dev_docs/ 2>/dev/null | grep -v '_analysis/redact_scan.sh')
  if [ -n "$hits" ]; then
    echo "❌ ${label}"
    echo "$hits" | sed 's/^/    /'
    fail=1
  else
    # 花括号不能省：紧跟其后的全角冒号首字节会被 bash 并入变量名
    echo "✅ ${label}：无命中"
  fi
}

scan "本地绝对路径" '/Users/[A-Za-z0-9._-]+/'
scan "凭证字面量" "(api_key|apikey|access_token|refresh_token|client_secret|password|credential)[\"' ]*[:=][\"' ]*[A-Za-z0-9_/+.-]{12,}"
scan "JWT 形状串" 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.'
scan "私钥块" 'BEGIN [A-Z ]*PRIVATE KEY'
scan "SSH 组织身份串" 'org-[0-9]{6,}@'
scan "内网 IP" '\b(10\.[0-9]{1,3}|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b'
scan "个人邮箱" '[A-Za-z0-9._%+-]+@(gmail|qq|163|outlook|hotmail|foxmail)\.(com|cn)'

if [ "$fail" -ne 0 ]; then
  echo
  echo "脱敏门禁未通过，禁止提交。"
  exit 1
fi
echo
echo "脱敏门禁全部通过。"
