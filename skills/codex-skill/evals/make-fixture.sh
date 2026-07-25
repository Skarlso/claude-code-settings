#!/usr/bin/env bash
# 生成行为评测用的一次性小仓库（设计文档 §5.2）。
# 用法:
#   evals/make-fixture.sh [目标目录] [--broken-codex]
# 默认目录 /tmp/codex-skill-fixture；--broken-codex 附加坏的 ./bin/codex shim（eval-5 用）。
set -euo pipefail

DIR="${1:-/tmp/codex-skill-fixture}"
BROKEN="${2:-}"

rm -rf "$DIR"
mkdir -p "$DIR"
cd "$DIR"

cat > counter.py <<'EOF'
"""A tiny hit counter with per-key stats, shared across worker threads."""
import threading

_counts = {}
_history = []


def record_hit(key):
    # NOTE: called concurrently from multiple worker threads
    current = _counts.get(key, 0)
    _counts[key] = current + 1
    _history.append(key)


def get_count(key):
    return _counts.get(key, 0)


def total_hits():
    return len(_history)
EOF

cat > test_counter.py <<'EOF'
import sys
import threading

import counter

# Surface the check-then-act race reliably despite the GIL.
sys.setswitchinterval(1e-6)


def test_concurrent_hits_are_not_lost():
    threads = [
        threading.Thread(target=lambda: [counter.record_hit("home") for _ in range(50000)])
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter.get_count("home") == 400000
EOF

cat > README.md <<'EOF'
# hitcounter

Tiny demo project: an in-memory hit counter used by a threaded web worker pool.

Run tests with `python -m pytest -q`.
EOF

git init -q
git add -A
git -c user.email=fixture@example.com -c user.name=fixture commit -qm "initial: hit counter with tests"

# 叠加一个未提交的改动：新增 get_recent() 带越界/语义 bug（review 评测的靶子）
cat >> counter.py <<'EOF'


def get_recent(n):
    """Return the n most recent hit keys, oldest first."""
    # BUG bait: n=0 returns the whole history instead of nothing,
    # and negative n silently returns a nonsense slice.
    return _history[-n:]
EOF

if [ "$BROKEN" = "--broken-codex" ]; then
  mkdir -p bin
  cat > bin/codex <<'EOF'
#!/usr/bin/env bash
echo "ERROR: authentication failed: token exchange rejected (invalid_grant)" >&2
echo "Run 'codex login' to re-authenticate." >&2
exit 1
EOF
  chmod +x bin/codex
  cat >> README.md <<'EOF'

## Tooling convention

All Codex CLI invocations in this project MUST go through the pinned wrapper `./bin/codex`
(it injects the team's provider config). Do not use a globally installed codex binary here.
EOF
fi

echo "fixture ready: $DIR"
