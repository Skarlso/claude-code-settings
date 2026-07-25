#!/usr/bin/env bash
# codex-skill 静态检查（设计文档 §5.1）
# 作为升级后版本的验收基线：对未升级的旧版，第 3/5/8 条预期 FAIL（用于验证检查本身有区分度）。
# 用法: evals/static-checks.sh [skill目录]  （默认: 本脚本所在 skill 目录）

set -u
SKILL_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
MIRROR_DIR="/Users/fei/claude-code-settings/plugins/codex-skill/skills/codex-skill"
SKILL_MD="$SKILL_DIR/SKILL.md"
FAIL=0
PASS_N=0
FAIL_N=0

ok()   { echo "PASS  $1"; PASS_N=$((PASS_N+1)); }
bad()  { echo "FAIL  $1"; FAIL=1; FAIL_N=$((FAIL_N+1)); }
warn() { echo "WARN  $1"; }

# 提取 SKILL.md 正文（跳过 frontmatter；description 里的触发词如 "gpt-5" 属用户措辞匹配，不算钉死模型）
body_of_skill_md() {
  awk 'f==2{print} /^---$/{f++}' "$SKILL_MD"
}

# --- 1. frontmatter 含 name 与 description ---
if grep -q '^name:' "$SKILL_MD" && grep -q '^description:' "$SKILL_MD"; then
  ok "1 frontmatter 含 name + description"
else
  bad "1 frontmatter 缺 name 或 description"
fi

# --- 2. SKILL.md 行数预算 ---
LINES=$(wc -l < "$SKILL_MD" | tr -d ' ')
if [ "$LINES" -le 500 ]; then
  ok "2 SKILL.md 行数 $LINES ≤ 500"
  [ "$LINES" -gt 220 ] && warn "2 SKILL.md 行数 $LINES 超过 220 行预算警戒线"
else
  bad "2 SKILL.md 行数 $LINES 超过 500"
fi

# --- 3. 无钉死模型名（正文 + references；见 issue #485 与记忆条目 no-model-pinning-in-skills）---
MODEL_HITS=$( { body_of_skill_md | grep -nE '\bgpt-[0-9]|\bo[0-9]+\b|claude-[a-z0-9]'; \
                grep -rInE '\bgpt-[0-9]|\bo[0-9]+\b|claude-[a-z0-9]' "$SKILL_DIR/references/" 2>/dev/null; } || true)
if [ -z "$MODEL_HITS" ]; then
  ok "3 无钉死模型名"
else
  bad "3 发现具体模型名（应改为 <model-name> 占位符）:"
  echo "$MODEL_HITS" | sed 's/^/        /'
fi

# --- 4. 无 disable-model-invocation（保持模型可编程调用，issue #269/#211）---
if grep -rq 'disable-model-invocation' "$SKILL_DIR" --include='*.md' 2>/dev/null; then
  bad "4 出现 disable-model-invocation"
else
  ok "4 无 disable-model-invocation"
fi

# --- 5. 引用完整性：SKILL.md 提到的文件都存在；references/assets 下每个文件都被提到 ---
REF_OK=1
for f in $(grep -oE '(references|assets)/[A-Za-z0-9._-]+' "$SKILL_MD" | sort -u); do
  if [ ! -f "$SKILL_DIR/$f" ]; then bad "5 SKILL.md 引用了不存在的文件: $f"; REF_OK=0; fi
done
for f in "$SKILL_DIR"/references/* "$SKILL_DIR"/assets/*; do
  [ -e "$f" ] || continue
  rel="${f#"$SKILL_DIR"/}"
  if ! grep -q "$rel" "$SKILL_MD"; then bad "5 文件未被 SKILL.md 提及: $rel"; REF_OK=0; fi
done
[ "$REF_OK" -eq 1 ] && ok "5 引用完整性（双向）"

# --- 6. review schema 合法且 required 字段齐全 ---
SCHEMA="$SKILL_DIR/assets/review-output.schema.json"
if [ -f "$SCHEMA" ]; then
  if jq empty "$SCHEMA" 2>/dev/null && \
     [ "$(jq -r '.required | sort | join(",")' "$SCHEMA")" = "findings,next_steps,summary,verdict" ]; then
    ok "6 review-output.schema.json 合法且 required 齐全"
  else
    bad "6 review-output.schema.json 非法或 required 字段不对"
  fi
else
  bad "6 缺少 assets/review-output.schema.json"
fi

# --- 7. 镜像一致（排除 evals/，设计文档 §3）。镜像为 symlink 时天然一致，跳过 ---
if [ -L "$MIRROR_DIR" ]; then
  warn "7 镜像是 symlink（指向主目录），天然一致，跳过"
elif [ -d "$MIRROR_DIR" ]; then
  if diff -r -x 'evals' "$SKILL_DIR" "$MIRROR_DIR" >/dev/null 2>&1; then
    ok "7 镜像目录一致"
  else
    bad "7 镜像目录不一致"
  fi
else
  warn "7 镜像目录不存在，跳过: $MIRROR_DIR"
fi

# --- 8. 关键护栏语句 ---
if body_of_skill_md | grep -qiE 'auto-applying fixes.*(forbidden|禁止)|strictly forbidden'; then
  ok "8a review 后禁止自动修复的护栏存在"
else
  bad "8a 缺少 review 后禁止自动修复（never-auto-fix）护栏"
fi
if body_of_skill_md | grep -q 'Codex did not run'; then
  ok "8b 失败诚实护栏（'Codex did not run'）存在"
else
  bad "8b 缺少失败诚实护栏语句 'Codex did not run'"
fi
LOGIN_GATE=$( { body_of_skill_md; cat "$SKILL_DIR"/references/*.md 2>/dev/null; } \
  | grep -n 'codex login status' \
  | grep -viE 'not|never|不要|do NOT' || true)
if [ -z "$LOGIN_GATE" ]; then
  ok "8c 未把 codex login status 用作门卫（issue #21/#233）"
else
  bad "8c 出现非否定语境的 codex login status:"
  echo "$LOGIN_GATE" | sed 's/^/        /'
fi

echo
echo "结果: $PASS_N PASS / $FAIL_N FAIL"
exit $FAIL
