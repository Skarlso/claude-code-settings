---
name: github-review-pr
description: Review GitHub pull requests with detailed, multi-perspective code analysis using parallel subagents. Use this skill whenever the user wants to review a PR, asks for code review on a pull request, mentions "review PR", "check this PR", "look at pull request", or references a PR number or GitHub PR URL. Do NOT use for local uncommitted changes — this skill only reviews pull requests on GitHub.
argument-hint: "[pr-number | pr-url]"
allowed-tools: Bash(gh pr list:*), Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh pr comment:*), Bash(gh pr review:*), Bash(gh repo view:*), Bash(gh api repos/*), Bash(gh api user:*), Bash(gh search:*)
---

# Review GitHub Pull Request

A structured, multi-agent workflow for thorough code reviews on GitHub PRs. The approach uses parallel specialized reviewers, adversarial verification with confidence scoring, and false positive filtering to produce high-signal, actionable feedback.

Use `gh` for all GitHub interactions. Do not use web fetch or attempt to build/typecheck the app — CI handles that separately.

## Workflow

Before starting, create a todo list with one item per step below (1. Eligibility check, 2. Gather context, 3. Parallel code review, 3.5 Deduplicate, 4. Adversarial verification & scoring, 5. Filter, 6. Re-check eligibility, 7. Post review or approve) and mark each item complete as it finishes. Never post the review or approval (step 7) unless the eligibility re-check (step 6) passed during this same run.

### 1. Eligibility Check

Use a subagent to verify the PR is eligible for review. Skip the review if any of these are true:

- The PR is closed or merged
- The PR is a draft
- The PR doesn't need review (e.g., automated/bot PR, or trivially simple)
- You've already reviewed it (posted a review, an approval, or a "### Code review" comment) AND there are no new commits since then. To check: get your login (`gh api user --jq '.login'`), find the timestamp of your most recent review — submittedAt under reviews (including a bare LGTM approval), or createdAt of a "### Code review" comment from older runs (`gh pr view 78 --json comments,reviews`) — and get the latest commit time (`gh pr view 78 --json commits --jq '.commits[-1].committedDate'`). If commits landed after your last review, proceed as a follow-up review: review the full current diff as usual (do not attempt to diff only "new" commits — the last-reviewed SHA may be unknown or force-pushed away), pass your previous review to the review and scoring agents so they do not re-raise previously reported issues unless still unfixed, and use the heading `### Code review (follow-up)` in the review body.

**Exception**: if the user explicitly pointed at this PR (gave its number or URL), only closed/merged remains a hard stop. For draft, bot, or trivially-simple PRs, tell the user the status and proceed with the review (for drafts, note in the posted review that the PR was a draft at review time). If you already reviewed it, say so and proceed only if the PR has new commits since that review or the user confirms they want a re-review.

If no PR number is provided, run `gh pr list` to show open PRs and ask which one to review.

### 2. Gather Context (parallel)

**Size check.** Probe the PR before launching subagents: `gh pr view 78 --json changedFiles,additions,deletions`.

- Fewer than 20 changed files: proceed normally; reviewers may read changed files in full.
- 20-100 files: exclude generated/vendored files (lockfiles, `*.min.js`, snapshots, `dist/`, codegen output) from review and note them as "not reviewed" in the summary; reviewers work from the diff, deep-reading only high-risk files (auth, payments, config, migrations, shared utilities).
- More than 100 files or ~10,000 changed lines: `gh pr diff` may fail or truncate. Instead, build a file manifest with `gh api repos/OWNER/REPO/pulls/78/files --paginate --jq '.[] | {filename, additions, deletions}'` and give each of the 6 reviewers the manifest — keeping all 6 angles over the whole PR, NOT partitioning files across angles — instructing each to fetch individual patches on demand for the files relevant to its angle (`gh api repos/OWNER/REPO/pulls/78/files --paginate --jq '.[] | select(.filename == "PATH") | .patch'`; note GitHub omits `patch` for very large files and lists at most 3000 files). If one angle's relevant file set is still too large for a single agent, split that angle across multiple instances of the same agent, each taking a slice of the manifest. If the PR remains unmanageable, tell the user it is too large for a high-signal review and ask them to scope it (e.g., to a monorepo path via `--jq '.[] | select(.filename | startswith("packages/api/"))'`).

Launch two subagents in parallel:

**Subagent A — Project guidance discovery**: Find all relevant CLAUDE.md and AGENTS.md files — check the repo root and any directories whose files the PR modified. Return a list of file paths (not contents).

**Subagent B — PR summary**: View the PR with `gh pr view` and `gh pr diff`, then return a concise summary of what changed.

### 3. Parallel Code Review (6 specialized agents)

Read [references/subagent-prompts.md](references/subagent-prompts.md) and launch 6 parallel subagents using those templates, substituting the placeholders and keeping the embedded shared blocks intact. Subagents cannot see this skill file — everything they need must be in their prompt. Each agent returns a list of issues found, with a reason tag for why it was flagged (e.g., "CLAUDE.md adherence", "bug", "historical git context", "past PR feedback", "code comment violation", "security").

Every issue returned by a review agent MUST include all of: (a) file path and line numbers (e.g., `src/auth.ts:42-45`) pointing at lines this PR modified; (b) a verbatim quote of the offending line(s), copied from the diff, never paraphrased from memory; (c) evidence for why it is wrong — for bug findings, a concrete failure trace in the form "when X, Y happens because Z"; for guidance findings (CLAUDE.md/AGENTS.md, code comments, past PR feedback), a verbatim quote of the specific guidance violated and where it lives; (d) the reason tag. Findings missing any of these are dropped before step 4 — do not score them. Never assert "this project's convention is X" without checking mechanically: grep for the pattern and cite the occurrence count in the finding.

Summary of the six angles for the orchestrator (if this table and the templates ever diverge, the templates are canonical):

| Agent | Focus | Approach |
|-------|-------|----------|
| **#1 CLAUDE.md / AGENTS.md compliance** | Check changes against project guidance | Read the CLAUDE.md and AGENTS.md files from step 2. Note that these files are guidance for AI agents as they write code, so not all instructions apply during code review. |
| **#2 Shallow bug scan** | Obvious bugs in the diff | Read only the changed lines (avoid extra context beyond the diff). Focus on significant bugs, not nitpicks. Ignore likely false positives. |
| **#3 Git history context** | Bugs visible through historical context | Read `git blame` and history of modified code. Identify issues that become apparent in light of how the code evolved. |
| **#4 Past PR feedback** | Recurring issues | Find previous PRs that touched these files. Check their comments for feedback that may also apply here. Use the "PRs that previously touched a file" recipe in the command reference; limit to the 3-5 most recently merged PRs. |
| **#5 Code comment compliance** | Respect inline guidance | Read code comments in modified files. Verify the PR changes comply with any guidance expressed in those comments. |
| **#6 Security scan of the diff** | Concrete, exploitable vulnerabilities introduced by this PR | Look only at changed lines for: hardcoded secrets/credentials, injection (SQL/command/path), missing authn/authz on new endpoints, unsafe deserialization, SSRF. Report only issues where you can state the concrete exploit path; general security hygiene suggestions ("should add rate limiting", "consider CSP") are false positives. |

### 3.5 Deduplicate (merge only — no judging)

Before scoring, merge findings from the 6 agents that describe the same defect — same file, overlapping lines, same described problem. Record which agents flagged each merged issue (e.g., "flagged by #2 and #3") and preserve each agent's reason tag. Do NOT read the code, evaluate validity, or drop any finding at this stage: verification belongs to step 4, and pre-judging here turns the orchestrator into a seventh reviewer with a veto. Merge only on what the findings themselves say, not on your own opinion of the code.

### 4. Adversarial Verification & Confidence Scoring

For each issue from step 3.5, launch a parallel subagent acting as a skeptic whose job is to disprove the finding, not confirm it. Give it the issue as reported (including its quoted code and evidence), the PR number, and the CLAUDE.md/AGENTS.md file list. Include the agreement count from step 3.5 in the skeptic's context, with this framing: convergence by multiple agents is supporting context, but it never substitutes for the skeptic's own verification — the score must still be justified by the rubric below. A finding flagged by only one agent is the normal case (the six angles are intentionally disjoint — e.g., only agent #4 sees past PR feedback) and must not be penalized for that alone.

Before assigning any score the skeptic MUST:

1. Independently re-read the relevant code via `gh pr diff` and, where file context beyond the diff is needed, `gh api repos/OWNER/REPO/contents/PATH?ref=HEAD_SHA` — never score from the issue description alone.
2. Confirm the cited file and lines actually exist at the PR head SHA — if they do not, or if the issue quotes a code snippet that does not match the actual code, score 0: the finding is fabricated.
3. Confirm the behavior at issue is introduced or altered by lines this PR modifies — if the root cause is untouched by the diff, score 0 as pre-existing.
4. Answer in writing: on what concrete execution path does the failure occur, what input or state triggers it, and what breaks in practice when it fires.
5. If after reading the code the skeptic can neither disprove nor confirm the finding, cap the score at 25.

Then score 0-100:

| Score | Meaning |
|-------|---------|
| **0** | False positive that doesn't stand up to light scrutiny, or a pre-existing issue. |
| **25** | Might be real, but could be a false positive. Couldn't verify. If stylistic, not explicitly called out in CLAUDE.md or AGENTS.md. |
| **50** | Verified as real, but may be a nitpick or unlikely to hit in practice. Not very important relative to the rest of the PR. |
| **75** | Very likely real and will be hit in practice, but after re-reading the code some doubt remains about impact or intent. The existing approach is insufficient. |
| **100** | Definitely real and confirmed. Will happen frequently. Evidence directly confirms the issue. |

**Calibration note**: the 75 band is for findings that remain probable-but-not-fully-confirmed after the mandatory re-read. A finding the skeptic HAS confirmed per the steps above — a guidance violation whose quoted rule matches the CLAUDE.md/AGENTS.md file verbatim and whose cited code matches the diff, or a security vulnerability with a concrete exploit path — scores 90 or above, never 75. Band descriptions must not cap a confirmed finding below the step 5 publish filter.

For issues flagged due to CLAUDE.md/AGENTS.md instructions, the scoring agent should double-check that the relevant file actually calls out that issue specifically.

This rubric table and the False Positive Examples section must appear verbatim in every scoring subagent's prompt — do not paraphrase either. The canonical scorer prompt is in [references/subagent-prompts.md](references/subagent-prompts.md).

### 5. Filter

Discard any issues scoring below **80**. If no issues meet this threshold, skip to step 7's no-issues path (approve with LGTM).

### 6. Re-check Eligibility

Before posting, use a subagent to repeat the eligibility check from step 1. PRs can be closed or updated while the review runs. Apply the same explicit-request exception from step 1. Also re-fetch the head SHA (`gh api repos/OWNER/REPO/pulls/78 --jq '.head.sha'`); if it differs from the SHA you reviewed, verify each surviving issue still applies to the new head before posting, and use the new SHA in links.

### 7. Post Review or Approve

**No issues passed the filter** — do not post a findings comment; approve instead:

```sh
gh pr review 78 --approve --body "LGTM"
```

If approval fails (GitHub forbids approving your own PR), fall back to `gh pr comment 78 --body "LGTM"`.

**Issues found** — post ONE batched review via the reviews API (see command reference), splitting findings by whether they anchor to a changed line:

- **Code-level issues** (the cited lines are part of the PR diff): post as inline comments in the `comments[]` array, anchored to the offending lines. Each anchored line must be part of the PR diff or the API returns 422 — verify anchors against the `gh pr diff` hunks first; anything that doesn't anchor goes in the body.
- **Design-level and other non-line-anchored issues** (architectural concerns, cross-file problems, findings whose lines fall outside the diff): list them in the review `body`.

Rules:

- Every finding that passed the filter must be posted — inline if anchorable, in the body otherwise; never omit one
- Keep output brief; no emojis
- Inline comments are already anchored to the code, so cite only the justification (e.g., the CLAUDE.md quote or the failure trace); body issues must link the code they refer to
- You must provide the **full git SHA** in body links (not `$(git rev-parse HEAD)` — the comment renders as Markdown)
- Provide at least 1 line of context before and after the issue line in link ranges
- If the body would list more than 5 issues, keep each to a single line (description + link)

#### Review body format

For a follow-up review of new commits, use the heading `### Code review (follow-up)` instead.

```markdown
### Code review

Found 3 issues (2 inline).

1. <design-level or non-anchored issue> (AGENTS.md says "<quote>")

https://github.com/OWNER/REPO/blob/FULL_SHA/path/to/file.ts#L30-L35

<sub>- If this code review was useful, please react with a thumbs up. Otherwise, react with a thumbs down.</sub>
```

#### Inline comment format

```markdown
<brief description> (CLAUDE.md says "<quote>" | bug: when X, Y happens because Z)
```

#### Link format

Links must follow this exact format for Markdown rendering to work:

```
https://github.com/OWNER/REPO/blob/FULL_SHA/path/to/file.ext#L[start]-L[end]
```

- Full 40-character git SHA (no shell expansion)
- Repo name must match the repo being reviewed
- `#` after the file name
- Line range as `L[start]-L[end]`
- Include at least 1 line of context before/after (e.g., commenting on lines 5-6 should link `L4-L7`)

## False Positive Examples

These should be filtered out during steps 3-5. Share this context with the review and scoring agents:

- Pre-existing issues (not introduced by this PR)
- Something that looks like a bug but isn't actually one
- Pedantic nitpicks a senior engineer wouldn't flag
- Issues a linter, typechecker, or compiler would catch (imports, types, formatting, test failures)
- General code quality concerns (test coverage, docs, broad security) unless explicitly required in CLAUDE.md or AGENTS.md — but a concrete, exploitable vulnerability introduced by this PR (e.g., an injectable query, a committed credential) is never a false positive under this rule
- Issues called out in CLAUDE.md/AGENTS.md but explicitly silenced in code (e.g., lint ignore comments)
- Intentional functionality changes directly related to the PR's purpose
- Real issues on lines the author did not modify

## gh Command Reference

```sh
# List open PRs
gh pr list

# View PR description and metadata
gh pr view 78

# View PR code changes
gh pr diff 78

# Get repo owner/name
gh repo view --json nameWithOwner --jq '.nameWithOwner'

# Get PR head commit SHA (full 40-char)
gh api repos/OWNER/REPO/pulls/78 --jq '.head.sha'

# Your login (for the "already reviewed" check in steps 1 and 6)
gh api user --jq '.login'

# Existing top-level comments and reviews on this PR
gh pr view 78 --json comments,reviews

# PRs that previously touched a file (agent #4).
# Note: walks the default branch only; does not follow renames. Exclude the current PR number.
gh api "repos/OWNER/REPO/commits?path=path/to/file&per_page=10" --jq '.[].sha' | head -5 \
  | xargs -I{} gh api repos/OWNER/REPO/commits/{}/pulls --jq '.[].number' | sort -un

# Feedback left on a past PR
gh api repos/OWNER/REPO/pulls/72/comments --paginate --jq '.[] | {path, line, body}'   # inline review comments
gh api repos/OWNER/REPO/issues/72/comments --jq '.[] | {user: .user.login, body}'      # top-level comments

# Approve when no issues found (fallback if approving your own PR fails: gh pr comment 78 --body "LGTM")
gh pr review 78 --approve --body "LGTM"

# Post the review when issues found — ONE batched review per run (one notification):
# code-level findings as inline comments anchored to diff lines, design-level /
# non-anchored findings in the body. commit_id is the full head SHA from the command above.
cat > /tmp/review.json <<'EOF'
{
  "commit_id": "FULL_HEAD_SHA",
  "event": "COMMENT",
  "body": "### Code review\n\nFound 3 issues (2 inline).\n\n1. <design-level issue> (AGENTS.md says \"<quote>\")\n\nhttps://github.com/OWNER/REPO/blob/FULL_SHA/path/to/file.ts#L30-L35",
  "comments": [
    {"path": "src/a.ts", "line": 42, "side": "RIGHT", "body": "<finding 1>"},
    {"path": "src/b.ts", "start_line": 10, "start_side": "RIGHT", "line": 14, "side": "RIGHT", "body": "<finding 2>"}
  ]
}
EOF
gh api repos/OWNER/REPO/pulls/78/reviews --method POST --input /tmp/review.json
```
