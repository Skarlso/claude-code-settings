# Codex Usage Scenarios

Worked examples mapping common user requests to `codex exec` commands. See `cli-reference.md` for the full flag reference.

## Code Analysis (Read-Only)

**User**: "Count the lines of code in this project by language"

```bash
codex exec "count the total number of lines of code in this project, broken down by language"
```

## Bug Fixing (Workspace-Write)

**User**: "Fix the authentication bug in the login flow"

```bash
codex exec --full-auto "fix the authentication bug in the login flow"
```

## Feature Implementation (Workspace-Write)

**User**: "Let codex implement dark mode support for the UI"

```bash
codex exec --full-auto "add dark mode support to the UI with theme context and style updates"
```

## Code Review

**User**: "Review my changes before I push"

```bash
codex exec review --uncommitted
```

## Image-Based Implementation

**User**: "Build the UI from this mockup"

```bash
codex exec -i mockup.png --full-auto "implement the UI component matching this design"
```

## Install Dependencies and Integrate API (Danger-Full-Access)

**User**: "Install the new payment SDK and integrate it"

```bash
codex exec -s danger-full-access "install the payment SDK dependencies and integrate the API"
```

## Multi-Project Work (Custom Directory)

**User**: "Implement the API in the backend project"

```bash
codex exec -C ~/projects/backend --full-auto "implement the REST API endpoints for user management"
```

## Non-Git Project Analysis

**User**: "Analyze this legacy codebase that's not in git"

```bash
codex exec --skip-git-repo-check "analyze the architecture and suggest modernization approach"
```

## Adversarial Review (Structured JSON)

**User**: "让 codex 用最挑剔的眼光审查我这次的改动，重点看并发问题"

Read `review-workflows.md` (Adversarial Review) — size the diff with `git diff --shortstat`, assemble the adversarial prompt, then:

```bash
codex exec -s read-only --output-schema <skill-dir>/assets/review-output.schema.json -o /tmp/codex-review.json "<assembled adversarial prompt>"
```

Present findings by severity, then stop and ask which to fix — never auto-apply.

## Plan Review (Before Implementation)

**User**: "实现之前，先让 codex 审一遍 tasks/todo.md 里的计划"

Read `review-workflows.md` (Plan Review) — the prompt must state the plan is not yet implemented:

```bash
codex exec -s read-only "<plan-review prompt referencing tasks/todo.md>"
```

## Iterative Follow-Up (Resume)

**User**: "不错，让 codex 继续把剩下的测试补完"

```bash
codex exec resume --last "add the remaining unit tests for the module you just fixed"
```
