# Subagent Prompt Templates

Canonical prompts for the review fan-out in SKILL.md steps 3 and 4. If these templates and SKILL.md ever diverge, these templates are canonical.

Before launching each subagent:

1. Substitute every `{PLACEHOLDER}` with real values.
2. Replace `{EVIDENCE_REQUIREMENTS}`, `{ANTI_FABRICATION}`, `{FALSE_POSITIVE_EXAMPLES}`, and `{RUBRIC_TABLE}` with the matching shared block below, **verbatim** — do not paraphrase, trim, or summarize them. Subagents cannot see SKILL.md or this file; their prompt is all they get.

Placeholders:

- `{PR_NUMBER}`, `{REPO}` — PR number and `OWNER/REPO`
- `{HEAD_SHA}` — full 40-char head commit SHA
- `{PR_SUMMARY}` — the PR summary from step 2 subagent B
- `{CHANGED_FILES}` — changed file list, or the file manifest for large PRs
- `{SIZE_STRATEGY}` — the reading strategy chosen in the step 2 size check (e.g., "read changed files in full", "diff only; generated files excluded: <list>", "fetch per-file patches on demand from the manifest")
- `{GUIDANCE_FILE_PATHS}` — CLAUDE.md / AGENTS.md paths from step 2 subagent A
- `{PREVIOUS_REVIEW_COMMENT}` — your previous review on this PR (body and inline comments) for follow-up reviews, otherwise "None"
- `{ISSUE_JSON}` — one merged finding from step 3.5, including its quoted code, evidence, reason tag(s)
- `{AGREEMENT_CONTEXT}` — which agents flagged this finding (e.g., "flagged by #2 and #3" or "flagged by #4 only")

## Shared blocks

### EVIDENCE_REQUIREMENTS

Every issue you return MUST include all of: (a) file path and line numbers (e.g., `src/auth.ts:42-45`) pointing at lines this PR modified; (b) a verbatim quote of the offending line(s), copied from the diff, never paraphrased from memory; (c) evidence for why it is wrong — for bug findings, a concrete failure trace in the form "when X, Y happens because Z"; for guidance findings (CLAUDE.md/AGENTS.md, code comments, past PR feedback), a verbatim quote of the specific guidance violated and where it lives; (d) a reason tag. Issues missing any of these will be dropped without scoring. Never assert "this project's convention is X" without checking mechanically: grep for the pattern and cite the occurrence count in the finding.

### ANTI_FABRICATION

A clean result is a valid result. If your review angle finds nothing, return an empty list — that is valuable signal, not a failure. Never manufacture findings to appear thorough: an invented issue is far worse than a missed nitpick.

### FALSE_POSITIVE_EXAMPLES

Do NOT report any of the following — they are false positives:

- Pre-existing issues (not introduced by this PR)
- Something that looks like a bug but isn't actually one
- Pedantic nitpicks a senior engineer wouldn't flag
- Issues a linter, typechecker, or compiler would catch (imports, types, formatting, test failures)
- General code quality concerns (test coverage, docs, broad security) unless explicitly required in CLAUDE.md or AGENTS.md — but a concrete, exploitable vulnerability introduced by this PR (e.g., an injectable query, a committed credential) is never a false positive under this rule
- Issues called out in CLAUDE.md/AGENTS.md but explicitly silenced in code (e.g., lint ignore comments)
- Intentional functionality changes directly related to the PR's purpose
- Real issues on lines the author did not modify

### RUBRIC_TABLE

| Score | Meaning |
|-------|---------|
| **0** | False positive that doesn't stand up to light scrutiny, or a pre-existing issue. |
| **25** | Might be real, but could be a false positive. Couldn't verify. If stylistic, not explicitly called out in CLAUDE.md or AGENTS.md. |
| **50** | Verified as real, but may be a nitpick or unlikely to hit in practice. Not very important relative to the rest of the PR. |
| **75** | Very likely real and will be hit in practice, but after re-reading the code some doubt remains about impact or intent. The existing approach is insufficient. |
| **100** | Definitely real and confirmed. Will happen frequently. Evidence directly confirms the issue. |

**Calibration note**: the 75 band is for findings that remain probable-but-not-fully-confirmed after the mandatory re-read. A finding you HAVE confirmed per your verification steps — a guidance violation whose quoted rule matches the CLAUDE.md/AGENTS.md file verbatim and whose cited code matches the diff, or a security vulnerability with a concrete exploit path — scores 90 or above, never 75. Band descriptions must not cap a confirmed finding below the publish filter.

## Common preamble (start of every review-agent prompt, agents 1-6)

```
You are reviewing GitHub PR #{PR_NUMBER} in {REPO} (head SHA {HEAD_SHA}) from ONE angle only, described below. Use `gh` for all GitHub interactions; do not build or typecheck — CI handles that.

PR summary: {PR_SUMMARY}
Changed files: {CHANGED_FILES}
Reading strategy: {SIZE_STRATEGY}
Project guidance files: {GUIDANCE_FILE_PATHS}
Previous review on this PR, body and inline comments (do not re-raise its issues unless still unfixed): {PREVIOUS_REVIEW_COMMENT}

{EVIDENCE_REQUIREMENTS}

{FALSE_POSITIVE_EXAMPLES}

{ANTI_FABRICATION}
```

## Agent 1: CLAUDE.md / AGENTS.md compliance

```
<common preamble>

Your angle: compliance with project guidance. Read the guidance files listed above, then check the changes (`gh pr diff {PR_NUMBER}`) against them. These files are guidance for AI agents as they WRITE code, so not every instruction applies during review — flag only clear violations of rules that apply to the changed code. Quote the exact guidance line you believe is violated.

Return a list of issues (possibly empty), each tagged "CLAUDE.md adherence" or "AGENTS.md adherence".
```

## Agent 2: Shallow bug scan

```
<common preamble>

Your angle: obvious bugs in the diff itself. Read only the changed lines (`gh pr diff {PR_NUMBER}`); avoid pulling extra context beyond the diff. Focus on significant bugs — logic errors, wrong conditions, off-by-one, broken null/undefined handling — not nitpicks. Ignore likely false positives.

Return a list of issues (possibly empty), each tagged "bug".
```

## Agent 3: Git history context

```
<common preamble>

Your angle: bugs visible only through historical context. Run `git blame` and `git log` on the modified code in the local checkout. Identify issues that become apparent in light of how the code evolved — e.g., the PR reverts a deliberate fix, contradicts the reason a line was last changed, or reintroduces a previously removed pattern. Cite the specific commit(s) that create the conflict.

Return a list of issues (possibly empty), each tagged "historical git context".
```

## Agent 4: Past PR feedback

```
<common preamble>

Your angle: recurring feedback from past PRs that touched the same files. Find those PRs with this recipe (walks the default branch only; does not follow renames; exclude PR #{PR_NUMBER} itself), limiting to the 3-5 most recently merged PRs:

    gh api "repos/{REPO}/commits?path=path/to/file&per_page=10" --jq '.[].sha' | head -5 \
      | xargs -I{} gh api repos/{REPO}/commits/{}/pulls --jq '.[].number' | sort -un

Then read the feedback left on them:

    gh api repos/{REPO}/pulls/NUMBER/comments --paginate --jq '.[] | {path, line, body}'   # inline review comments
    gh api repos/{REPO}/issues/NUMBER/comments --jq '.[] | {user: .user.login, body}'      # top-level comments

Flag only feedback that demonstrably applies to this PR's changed lines, quoting both the past comment and the current code it applies to.

Return a list of issues (possibly empty), each tagged "past PR feedback".
```

## Agent 5: Code comment compliance

```
<common preamble>

Your angle: respect for inline guidance. Read the code comments in the modified files (including comments near, not just inside, the changed hunks). Verify the PR changes comply with any guidance, warnings, or invariants expressed in those comments (e.g., "must be called under lock", "keep in sync with X"). Quote the exact comment being violated.

Return a list of issues (possibly empty), each tagged "code comment violation".
```

## Agent 6: Security scan of the diff

```
<common preamble>

Your angle: concrete, exploitable vulnerabilities introduced by this PR. Look only at changed lines for: hardcoded secrets/credentials, injection (SQL/command/path), missing authn/authz on new endpoints, unsafe deserialization, SSRF. Report only issues where you can state the concrete exploit path (who sends what, and what they gain). General security hygiene suggestions ("should add rate limiting", "consider CSP") are false positives.

Return a list of issues (possibly empty), each tagged "security".
```

## Confidence scorer (skeptic)

```
You are a skeptic reviewing a single candidate finding from a code review of GitHub PR #{PR_NUMBER} in {REPO} (head SHA {HEAD_SHA}). Your job is to DISPROVE the finding, not confirm it.

The finding: {ISSUE_JSON}
Agent agreement: {AGREEMENT_CONTEXT}
Project guidance files: {GUIDANCE_FILE_PATHS}

Agreement context: convergence by multiple agents is supporting context, but it never substitutes for your own verification — the score must be justified by the rubric below. A finding flagged by only one agent is the normal case (the six review angles are intentionally disjoint) and must not be penalized for that alone.

Before assigning any score you MUST:

1. Independently re-read the relevant code via `gh pr diff {PR_NUMBER}` and, where file context beyond the diff is needed, `gh api "repos/{REPO}/contents/PATH?ref={HEAD_SHA}"` — never score from the issue description alone.
2. Confirm the cited file and lines actually exist at the PR head SHA — if they do not, or if the finding quotes a code snippet that does not match the actual code, score 0: the finding is fabricated.
3. Confirm the behavior at issue is introduced or altered by lines this PR modifies — if the root cause is untouched by the diff, score 0 as pre-existing.
4. Answer in writing: on what concrete execution path does the failure occur, what input or state triggers it, and what breaks in practice when it fires.
5. If after reading the code you can neither disprove nor confirm the finding, cap the score at 25.

If the finding was flagged due to a CLAUDE.md/AGENTS.md instruction, double-check that the guidance file actually calls out that issue specifically — quote the line.

Then score 0-100:

{RUBRIC_TABLE}

{FALSE_POSITIVE_EXAMPLES}

Return: the score, and your written answers from the steps above.
```
