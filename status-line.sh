#!/bin/bash
#
# Claude Code Status Line
# A clean, informative status bar for Claude Code CLI
#
# ─────────────────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────────────────
#
#   Required:
#     jq        JSON parser for reading Claude's input
#               Install: brew install jq (macOS) | apt install jq (Linux)
#
#   Optional:
#     git       For branch/dirty status (skip if not in a repo)
#
# ─────────────────────────────────────────────────────────────────────────────
# Data source
# ─────────────────────────────────────────────────────────────────────────────
#
# Everything is read from the stdin JSON that Claude Code passes to statusline
# commands (requires Claude Code >= 2.1.132 for correct context_window
# semantics):
#
#   context_window.context_window_size   200000, or 1000000 for 1M models
#                                         (works on 1P/Vertex/Bedrock/proxies —
#                                         resolved client-side by Claude Code)
#   context_window.total_input_tokens    current context usage: input tokens
#                                         incl. cache reads + writes (official
#                                         used_percentage uses the same
#                                         input-only formula)
#   context_window.total_output_tokens   output tokens of most recent response
#   cost.total_cost_usd                  session cost estimated by Claude Code
#                                         (provider-aware; replaces any
#                                         hardcoded price table)
#   cost.total_duration_ms               wall-clock session duration
#
# No transcript parsing: the old grep-the-JSONL approach scanned an
# uncontracted internal format on every refresh and broke on streaming/partial
# usage entries.

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BAR_WIDTH=10
CONTEXT_WARN_PCT=70
CONTEXT_CRIT_PCT=90

# Colors (using $'...' for proper escape sequence interpretation)
C_RESET=$'\033[0m'
C_BOLD_GREEN=$'\033[1;32m'
C_CYAN=$'\033[0;36m'
C_BLUE=$'\033[1;34m'
C_RED=$'\033[0;31m'
C_YELLOW=$'\033[0;33m'
C_GREEN=$'\033[0;32m'
C_DIM=$'\033[2m'

# ─────────────────────────────────────────────────────────────────────────────
# Input Parsing (single jq pass)
# ─────────────────────────────────────────────────────────────────────────────

IFS=$'\t' read -r MODEL CWD CTX_USED CTX_OUT CTX_LIMIT COST DURATION_MS < <(
    jq -r '[
        (.model.display_name // "unknown"),
        (.workspace.current_dir // "."),
        (.context_window.total_input_tokens // 0),
        (.context_window.total_output_tokens // 0),
        (.context_window.context_window_size // 200000),
        (.cost.total_cost_usd // 0),
        (.cost.total_duration_ms // 0)
    ] | @tsv'
)

# Defaults in case jq fails (empty/invalid stdin)
MODEL=${MODEL:-unknown}
CWD=${CWD:-.}
CTX_USED=${CTX_USED:-0}
CTX_OUT=${CTX_OUT:-0}
CTX_LIMIT=${CTX_LIMIT:-200000}
COST=${COST:-0}
DURATION_MS=${DURATION_MS:-0}

DIR=$(basename "$CWD")

# ─────────────────────────────────────────────────────────────────────────────
# Git Status
# ─────────────────────────────────────────────────────────────────────────────

get_git_info() {
    git -C "$CWD" rev-parse --git-dir >/dev/null 2>&1 || return 0

    local branch dirty=""
    branch=$(git -C "$CWD" --no-optional-locks branch --show-current 2>/dev/null)
    [[ -z "$branch" ]] && branch="detached"

    # Check for uncommitted changes
    if ! git -C "$CWD" --no-optional-locks diff --quiet 2>/dev/null ||
       ! git -C "$CWD" --no-optional-locks diff --cached --quiet 2>/dev/null ||
       [[ -n $(git -C "$CWD" --no-optional-locks ls-files --others --exclude-standard 2>/dev/null) ]]; then
        dirty=" ${C_YELLOW}✗"
    fi

    printf " ${C_BLUE}git:(${C_RED}%s${C_BLUE})%s${C_RESET}" "$branch" "$dirty"
}

# ─────────────────────────────────────────────────────────────────────────────
# Session Duration
# ─────────────────────────────────────────────────────────────────────────────

format_duration() {
    local ms=$1 mins hours
    mins=$((ms / 60000))
    hours=$((mins / 60))
    mins=$((mins % 60))

    if [[ $hours -gt 0 ]]; then
        echo "${hours}h${mins}m"
    else
        echo "${mins}m"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Context Progress Bar
# ─────────────────────────────────────────────────────────────────────────────

build_progress_bar() {
    local pct=$1
    local pct_int filled empty bar="" color

    pct_int=${pct%.*}
    pct_int=${pct_int:-0}

    filled=$(awk "BEGIN {printf \"%.0f\", ($pct / 100) * $BAR_WIDTH}")
    filled=${filled:-0}
    [[ $filled -gt $BAR_WIDTH ]] && filled=$BAR_WIDTH
    [[ $filled -lt 0 ]] && filled=0
    empty=$((BAR_WIDTH - filled))

    # Color based on usage level
    if [[ $pct_int -ge $CONTEXT_CRIT_PCT ]]; then
        color=$C_RED
    elif [[ $pct_int -ge $CONTEXT_WARN_PCT ]]; then
        color=$C_YELLOW
    else
        color=$C_GREEN
    fi

    for ((i = 0; i < filled; i++)); do bar+="█"; done
    for ((i = 0; i < empty; i++)); do bar+="░"; done

    printf "%b[%s %s%%]%b" "$color" "$bar" "$pct" "$C_RESET"
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

main() {
    local ctx_pct duration cost_fmt git_info limit_tag=""

    ctx_pct=$(awk "BEGIN {
        limit = $CTX_LIMIT; if (limit <= 0) limit = 200000
        printf \"%.1f\", ($CTX_USED / limit) * 100
    }")
    duration=$(format_duration "$DURATION_MS")
    cost_fmt=$(awk "BEGIN {printf \"%.2f\", $COST}")
    git_info=$(get_git_info)
    [[ "$CTX_LIMIT" -ge 1000000 ]] && limit_tag=" 1M"

    # Output: ctx = current context tokens (input+cache), out = last response
    printf "%b➜%b  %b%s%b%s %b[%s%s]%b %b[ctx %dk/out %dk \$%s]%b %s %b⏱ %s%b" \
        "$C_BOLD_GREEN" "$C_RESET" \
        "$C_CYAN" "$DIR" "$C_RESET" \
        "$git_info" \
        "$C_DIM" "$MODEL" "$limit_tag" "$C_RESET" \
        "$C_DIM" "$((CTX_USED / 1000))" "$((CTX_OUT / 1000))" "$cost_fmt" "$C_RESET" \
        "$(build_progress_bar "$ctx_pct")" \
        "$C_CYAN" "$duration" "$C_RESET"
}

main
