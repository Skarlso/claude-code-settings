# Codex CLI Reference

Complete flag and command reference for `codex exec`. See SKILL.md for workflow and sandbox mode selection.

## Model Selection

Codex uses the model configured in `~/.codex/config.toml` by default. Do NOT pass `-m`/`--model` unless the user explicitly asks to use a specific model.

```bash
# Default: uses model from config.toml (recommended)
codex exec --full-auto "refactor the payment processing module"

# Only when user specifies a model explicitly (pass their value through verbatim):
codex exec -m <model-name> --full-auto "implement the user authentication feature"
```

## Sandbox Modes

Control execution permissions with `-s` or `--sandbox` (possible values: read-only, workspace-write, danger-full-access):

### Read-Only Mode

```bash
codex exec "analyze the codebase structure and count lines of code"
codex exec -s read-only "review code quality and suggest improvements"
```

Analyze code without making any modifications.

### Workspace-Write Mode (Recommended for Programming)

```bash
codex exec -s workspace-write "implement the user authentication feature"
codex exec --full-auto "fix the bug in login flow"
```

Read and write files within the workspace. **Must be explicitly enabled (not the default). Use this for most programming tasks.**

### Danger-Full-Access Mode

```bash
codex exec -s danger-full-access "install dependencies and update the API integration"
```

Network access and system-level operations. Use only when necessary.

## Full-Auto Mode (Convenience Alias)

```bash
codex exec --full-auto "implement the user authentication feature"
```

**Convenience alias for**: `-s workspace-write` (enables file editing).
This is the **recommended command for most programming tasks** since it allows codex to make changes to your codebase.

## Config Overrides

Override any `config.toml` value inline with `-c` or `--config`:

```bash
# Override model for a single run (use the exact value the user asked for)
codex exec -c model="<model-name>" --full-auto "implement the feature"

# Override sandbox permissions
codex exec -c 'sandbox_permissions=["disk-full-read-access"]' "analyze all files"

# Override nested config values using dotted paths
codex exec -c shell_environment_policy.inherit=all --full-auto "run build"
```

## Feature Toggles

Enable or disable features with `--enable` and `--disable`:

```bash
codex exec --enable multi_agent --full-auto "implement feature across multiple files"
codex exec --disable plan_tool --full-auto "quick fix for typo"
```

Equivalent to `-c features.<name>=true` or `-c features.<name>=false`.

## Image Attachments

Attach images to the prompt with `-i` or `--image`:

```bash
codex exec -i screenshot.png "implement the UI shown in this screenshot"
codex exec -i mockup.png -i spec.png --full-auto "build this component matching the design"
```

## Code Review

Run code reviews with `codex exec review`:

```bash
# Review uncommitted changes (staged, unstaged, and untracked)
codex exec review --uncommitted

# Review changes against a base branch
codex exec review --base main

# Review a specific commit
codex exec review --commit abc1234

# Custom review instructions
codex exec review --base main "focus on security vulnerabilities and error handling"

# Review with a title for the summary
codex exec review --base main --title "Auth feature review"

# Output review as JSON
codex exec review --uncommitted --json -o review.json
```

## Configuration Profiles

Use saved profiles from `~/.codex/config.toml` with `-p` or `--profile`:

```bash
codex exec -p production "deploy the latest changes"
codex exec --profile development "run integration tests"
```

Profiles can specify default model, sandbox mode, and other options.

## Working Directory

Specify a different working directory with `-C` or `--cd`:

```bash
codex exec -C /path/to/project --full-auto "implement the feature"
codex exec --cd ~/projects/myapp --full-auto "run tests and fix failures"
```

## Additional Writable Directories

Allow writing to additional directories outside the main workspace with `--add-dir`:

```bash
codex exec --full-auto --add-dir /tmp/output --add-dir ~/shared "generate reports in multiple locations"
```

## JSON Output

```bash
codex exec --json "run tests and report results"
codex exec --json -s read-only "analyze security vulnerabilities"
```

Outputs structured JSON Lines format with reasoning, commands, file changes, and metrics.

## Structured Output Schema

Constrain the model's final response to match a JSON schema:

```bash
codex exec --output-schema schema.json "analyze the codebase and report findings"
```

## Save Output to File

```bash
codex exec -o report.txt "generate a security audit report"
codex exec -o results.json --json "run performance benchmarks"
```

Writes the final message to a file instead of stdout.

## Ephemeral Mode

Run without persisting session files to disk:

```bash
codex exec --ephemeral --full-auto "quick one-off fix"
```

## Skip Git Repository Check

```bash
codex exec --skip-git-repo-check "analyze this non-git directory"
```

Bypasses the requirement for the directory to be a git repository.

## Resume Previous Session

```bash
# Resume the most recent session
codex exec resume --last "now implement the next feature"

# Resume a specific session by ID
codex exec resume <session-id> "continue working on the API"

# Show all sessions (not filtered by current directory)
codex exec resume --all
```

Note: `codex exec resume` rejects `-C`, `-s`, and `--full-auto`. `cd` into the repo first, and pass the sandbox via config override when write access is needed: `codex exec resume --last -c 'sandbox_mode="workspace-write"' "<delta>"`.

Behavioral rules for resuming (cold re-exploration burns tokens on every iteration — resume keeps the thread's context):

- On follow-ups to a prior codex run, send **only the new delta instruction** via `codex exec resume --last "<delta>"` — do not re-send context the session already has.
- When the user just says "continue" / "keep going", use: `codex exec resume --last "Continue from the current thread state. Pick the next highest-value step and follow through until the task is resolved."`
- After each run, surface the session id (from the `--json` event stream) and mention `Resume in Codex: codex resume <session-id>` so work can move to the Codex TUI.

## Open-Source / Local Models

Use open-source models via local providers:

```bash
codex exec --oss "analyze this code"
codex exec --oss --local-provider ollama "refactor this function"
codex exec --oss --local-provider lmstudio "implement the feature"
```

## Bypass Approvals and Sandbox

**EXTREMELY DANGEROUS — only use in externally sandboxed environments (containers, VMs)**

```bash
codex exec --dangerously-bypass-approvals-and-sandbox "perform the task"
```

Skips ALL confirmation prompts and executes commands WITHOUT sandboxing.

## Combined Examples

Combine multiple flags for complex scenarios:

```bash
# Workspace write with JSON output
codex exec -s workspace-write --json "implement authentication and output results"

# Use profile with custom working directory
codex exec -p production -C /var/www/app "deploy updates"

# Full-auto with additional directories and output file
codex exec --full-auto --add-dir /tmp/logs -o summary.txt "refactor and log changes"

# Image-driven implementation with full-auto
codex exec -i design.png --full-auto "implement the UI matching this design"

# Config override with ephemeral mode
codex exec -c model_reasoning_effort="high" --ephemeral --full-auto "solve this complex bug"

# Code review with JSON output saved to file
codex exec review --base main --json -o review-report.json
```
