# Skill Creator

Modified from the [official Anthropic skill-creator plugin](https://github.com/anthropics/skills/tree/main/skills/skill-creator), with added **Codex CLI** and **OpenClaw** platform compatibility.

- Added platform adapters for **Codex CLI** (`scripts/platforms/codex.py`) and **OpenClaw** (`scripts/platforms/openclaw.py`) alongside the default Claude Code adapter
- Skill trigger evaluation and benchmarking now work across all three platforms
