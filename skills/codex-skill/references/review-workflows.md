# Review Workflows

Two specialized review modes built on `codex exec`, plus the shared rules for presenting results.
For an ordinary review, prefer the CLI-native path first: `codex exec review --uncommitted` /
`--base <branch>` / `--commit <sha>` (see cli-reference.md). Use this file when the user asks for
an **adversarial / hostile / second-opinion review**, when a larger workflow needs **structured
JSON findings**, or for a **pre-implementation plan review**.

Both modes run read-only and are safe to invoke programmatically inside larger unattended
workflows — no interactive questions, single synchronous invocation.

## Adversarial Review

### 1. Collect the target

Size the diff first:

```bash
git diff --shortstat                    # uncommitted changes
git diff --shortstat <base>...HEAD      # vs a base branch
```

- **Small scope** (≤ 2 changed files and roughly ≤ 150 changed lines): inline the full diff into
  `<repository_context>` below.
- **Larger scope**: inline only the file list + shortstat, and add this line inside
  `<review_method>`: `Inspect the target diff yourself with read-only git commands before
  finalizing findings.` Codex runs inside the repo, so self-collection works and avoids blowing
  up the prompt.

### 2. Assemble the prompt

Fill in: TARGET (e.g. "uncommitted changes", "diff vs main"), FOCUS (the user's focus area, or
"none — apply your own prioritization"), and the repository context per step 1. Include any task
background the user gave (requirements, linked issues, constraints) inside `<task>`.

```xml
<role>
You are Codex performing an adversarial software review.
Your job is to break confidence in the change, not to validate it.
</role>

<task>
Review the provided repository context as if you are trying to find the strongest reasons this change should not ship yet.
Target: [TARGET]
User focus: [FOCUS]
</task>

<operating_stance>
Default to skepticism.
Assume the change can fail in subtle, high-cost, or user-visible ways until the evidence says otherwise.
Do not give credit for good intent, partial fixes, or likely follow-up work.
If something only works on the happy path, treat that as a real weakness.
</operating_stance>

<attack_surface>
Prioritize the kinds of failures that are expensive, dangerous, or hard to detect:
- auth, permissions, tenant isolation, and trust boundaries
- data loss, corruption, duplication, and irreversible state changes
- rollback safety, retries, partial failure, and idempotency gaps
- race conditions, ordering assumptions, stale state, and re-entrancy
- empty-state, null, timeout, and degraded dependency behavior
- version skew, schema drift, migration hazards, and compatibility regressions
- observability gaps that would hide failure or make recovery harder
</attack_surface>

<review_method>
Actively try to disprove the change.
Look for violated invariants, missing guards, unhandled failure paths, and assumptions that stop being true under stress.
Trace how bad inputs, retries, concurrent actions, or partially completed operations move through the code.
If the user supplied a focus area, weight it heavily, but still report any other material issue you can defend.
</review_method>

<finding_bar>
Report only material findings.
Do not include style feedback, naming feedback, low-value cleanup, or speculative concerns without evidence.
A finding should answer:
1. What can go wrong?
2. Why is this code path vulnerable?
3. What is the likely impact?
4. What concrete change would reduce the risk?
</finding_bar>

<structured_output_contract>
Return only valid JSON matching the provided schema.
Keep the output compact and specific.
Use `needs-attention` if there is any material risk worth blocking on.
Use `approve` only if you cannot support any substantive adversarial finding from the provided context.
Every finding must include:
- the affected file
- `line_start` and `line_end`
- a confidence score from 0 to 1
- a concrete recommendation
Write the summary like a terse ship/no-ship assessment, not a neutral recap.
</structured_output_contract>

<grounding_rules>
Be aggressive, but stay grounded.
Every finding must be defensible from the provided repository context or tool outputs.
Do not invent files, lines, code paths, incidents, attack chains, or runtime behavior you cannot support.
If a conclusion depends on an inference, state that explicitly in the finding body and keep the confidence honest.
</grounding_rules>

<calibration_rules>
Prefer one strong finding over several weak ones.
Do not dilute serious issues with filler.
If the change looks safe, say so directly and return no findings.
</calibration_rules>

<final_check>
Before finalizing, check that each finding is:
- adversarial rather than stylistic
- tied to a concrete code location
- plausible under a real failure scenario
- actionable for an engineer fixing the issue
</final_check>

<repository_context>
[diff or file list per step 1]
</repository_context>
```

### 3. Invoke

Use the schema bundled with this skill (`assets/review-output.schema.json`) — don't regenerate it:

```bash
codex exec -s read-only \
  --output-schema <skill-dir>/assets/review-output.schema.json \
  -o /tmp/codex-review-<slug>.json \
  "<assembled prompt>"
```

### 4. Validate and present

- Check the output parses (`jq empty /tmp/codex-review-<slug>.json`). If it does not, show the
  raw output plus the parse error — never silently reinterpret malformed output into conclusions.
- Present per the shared rules below and SKILL.md "Handling Review Results" (findings first,
  severity order, exact file:line, then STOP and ask which to fix).

## Plan Review

Have codex critique a not-yet-implemented plan against the actual codebase — completeness,
ordering risks, safety, missing edge cases, conflicts with current repository state. The framing
below matters: a post-implementation review prompt pointed at a plan will report "the code doesn't
exist" as a defect.

Pass the plan by file path (codex reads it itself) or inline it if short. Run read-only:

```bash
codex exec -s read-only "<assembled prompt>"
```

```xml
<task>
You are reviewing an implementation PLAN. The code described in it does NOT exist yet.
Do not report missing implementation as a defect.
Read the plan at [PLAN_PATH or inline the plan text here].
Validate the plan against the CURRENT state of this repository: completeness, ordering risks,
safety concerns, missing edge cases, and conflicts with existing code or configuration.
[Add any task background the user gave: goals, constraints, linked issues.]
</task>

<grounding_rules>
Ground every claim in the plan text or the current repository.
Do not present inferences as facts.
If a point is a hypothesis, label it clearly.
</grounding_rules>

<dig_deeper_nudge>
After you find the first plausible issue, check for second-order failures, ordering hazards,
migration/rollback gaps, and steps that silently depend on later steps before you finalize.
</dig_deeper_nudge>

<compact_output_contract>
Keep the final answer compact and structured. Return:
1. blocking risks
2. ordering problems
3. missing steps or edge cases
4. open questions
</compact_output_contract>
```

## Presenting Review Results (both modes)

- Findings first, ordered by severity; keep file paths and line numbers exactly as codex reported.
- Preserve inference/uncertainty labels — don't upgrade a hypothesis into a fact while relaying.
- No findings → say so explicitly, with a one-line residual-risk note.
- If codex made edits during the run, say so and list touched files.
- Then follow SKILL.md "Handling Review Results": stop and ask the user which issues to fix —
  never auto-apply fixes from a review.
