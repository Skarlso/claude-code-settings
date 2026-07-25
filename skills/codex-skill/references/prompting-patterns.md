# Codex Prompting Patterns

How to compose the prompt text passed to `codex exec`. The flags decide *what codex may do*;
the prompt decides *how well it does it*. These patterns are model-agnostic — never pin them
to a specific model version, since guidance rots faster than defaults change.

**Contents**: [Assembly rules](#assembly-rules) · [Prompt blocks](#prompt-blocks) · [Task recipes](#task-recipes) · [Anti-patterns](#anti-patterns)

## Assembly Rules

- Compose prompts from the named XML blocks below. Pick the **smallest** set of blocks that fits
  the task — extra blocks dilute the signal.
- Nearly every prompt contains a `task` block.
- Blocks must not contradict each other (e.g. don't pair `structured_output_contract` with
  `compact_output_contract`).
- Fix-oriented recipes pair with `--full-auto`; diagnosis/review/research recipes pair with the
  default read-only sandbox.

## Prompt Blocks

Wrap each block in the XML tag shown in its heading.

### `task` — core wrapper, use in nearly every prompt

```xml
<task>
Describe the concrete job, the relevant repository or failure context, and the expected end state.
</task>
```

### `structured_output_contract` — when the response shape matters

```xml
<structured_output_contract>
Return exactly the requested output shape and nothing else.
Keep the answer compact.
Put the highest-value findings or decisions first.
</structured_output_contract>
```

### `compact_output_contract` — concise prose instead of a schema

```xml
<compact_output_contract>
Keep the final answer compact and structured.
Do not include long scene-setting or repeated recap.
</compact_output_contract>
```

### `default_follow_through_policy` — act without asking routine questions

```xml
<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going.
Only stop to ask questions when a missing detail changes correctness, safety, or an irreversible action.
</default_follow_through_policy>
```

### `completeness_contract` — multi-step work that should not stop early

```xml
<completeness_contract>
Resolve the task fully before stopping.
Do not stop at the first plausible answer.
Check whether there are follow-on fixes, edge cases, or cleanup needed for a correct result.
</completeness_contract>
```

### `verification_loop` — when correctness matters

```xml
<verification_loop>
Before finalizing, verify the result against the task requirements and the changed files or tool outputs.
If a check fails, revise the answer instead of reporting the first draft.
</verification_loop>
```

### `missing_context_gating` — when codex might otherwise guess

```xml
<missing_context_gating>
Do not guess missing repository facts.
If required context is absent, retrieve it with tools or state exactly what remains unknown.
</missing_context_gating>
```

### `grounding_rules` — review, research, root-cause analysis

```xml
<grounding_rules>
Ground every claim in the provided context or your tool outputs.
Do not present inferences as facts.
If a point is a hypothesis, label it clearly.
</grounding_rules>
```

### `citation_rules` — when external research or quotes matter

```xml
<citation_rules>
Back important claims with citations or explicit references to the source material you inspected.
Prefer primary sources.
</citation_rules>
```

### `action_safety` — write-capable or potentially broad tasks

```xml
<action_safety>
Keep changes tightly scoped to the stated task.
Avoid unrelated refactors, renames, or cleanup unless they are required for correctness.
Call out any risky or irreversible action before taking it.
</action_safety>
```

### `tool_persistence_rules` — long-running tool-heavy tasks

```xml
<tool_persistence_rules>
Keep using tools until you have enough evidence to finish the task confidently.
Do not abandon the workflow after a partial read when another targeted check would change the answer.
</tool_persistence_rules>
```

### `research_mode` — exploration, comparisons, recommendations

```xml
<research_mode>
Separate observed facts, reasoned inferences, and open questions.
Prefer breadth first, then go deeper only where the evidence changes the recommendation.
</research_mode>
```

### `dig_deeper_nudge` — review and adversarial inspection

```xml
<dig_deeper_nudge>
After you find the first plausible issue, check for second-order failures, empty-state behavior, retries, stale state, and rollback paths before you finalize.
</dig_deeper_nudge>
```

### `progress_updates` — when the run may take a while

```xml
<progress_updates>
If you provide progress updates, keep them brief and outcome-based.
Mention only major phase changes or blockers.
</progress_updates>
```

## Task Recipes

Copy the smallest recipe that fits the task, then trim anything you do not need.

### Diagnosis (read-only)

```xml
<task>
Diagnose why the failing test or command is breaking in this repository.
Use the available repository context and tools to identify the most likely root cause.
</task>

<compact_output_contract>
Return a compact diagnosis with:
1. most likely root cause
2. evidence
3. smallest safe next step
</compact_output_contract>

<default_follow_through_policy>
Keep going until you have enough evidence to identify the root cause confidently.
Only stop to ask questions when a missing detail changes correctness materially.
</default_follow_through_policy>

<verification_loop>
Before finalizing, verify that the proposed root cause matches the observed evidence.
</verification_loop>

<missing_context_gating>
Do not guess missing repository facts.
If required context is absent, state exactly what remains unknown.
</missing_context_gating>
```

### Narrow Fix (`--full-auto`)

```xml
<task>
Implement the smallest safe fix for the identified issue in this repository.
Preserve existing behavior outside the failing path.
</task>

<structured_output_contract>
Return:
1. summary of the fix
2. touched files
3. verification performed
4. residual risks or follow-ups
</structured_output_contract>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going.
</default_follow_through_policy>

<completeness_contract>
Resolve the task fully before stopping.
Do not stop after identifying the issue without applying the fix.
</completeness_contract>

<verification_loop>
Before finalizing, verify that the fix matches the task requirements and that the changed code is coherent.
</verification_loop>

<action_safety>
Keep changes tightly scoped to the stated task.
Avoid unrelated refactors or cleanup.
</action_safety>
```

### Root-Cause Review (read-only)

```xml
<task>
Analyze this change for the most likely correctness or regression issues.
Focus on the provided repository context only.
</task>

<structured_output_contract>
Return:
1. findings ordered by severity
2. supporting evidence for each finding
3. brief next steps
</structured_output_contract>

<grounding_rules>
Ground every claim in the repository context or tool outputs.
If a point is an inference, label it clearly.
</grounding_rules>

<dig_deeper_nudge>
Check for second-order failures, empty-state handling, retries, stale state, and rollback paths before finalizing.
</dig_deeper_nudge>

<verification_loop>
Before finalizing, verify that each finding is material and actionable.
</verification_loop>
```

### Research or Recommendation (read-only)

```xml
<task>
Research the available options and recommend the best path for this task.
</task>

<structured_output_contract>
Return:
1. observed facts
2. reasoned recommendation
3. tradeoffs
4. open questions
</structured_output_contract>

<research_mode>
Separate observed facts, reasoned inferences, and open questions.
Prefer breadth first, then go deeper only where the evidence changes the recommendation.
</research_mode>

<citation_rules>
Back important claims with explicit references to the sources you inspected.
Prefer primary sources.
</citation_rules>
```

### Prompt-Patching (improving an underperforming codex prompt)

```xml
<task>
Diagnose why this existing prompt is underperforming and propose the smallest high-leverage changes to improve it.
</task>

<structured_output_contract>
Return:
1. failure modes
2. root causes in the current prompt
3. a revised prompt
4. why the revision should work better
</structured_output_contract>

<grounding_rules>
Base your diagnosis on the prompt text and the failure examples provided.
Do not invent failure modes that are not supported by the examples.
</grounding_rules>

<verification_loop>
Before finalizing, make sure the revised prompt resolves the cited failure modes without adding contradictory instructions.
</verification_loop>
```

## Anti-Patterns

### Vague task framing

Bad: `Take a look at this and let me know what you think.`

Better:

```xml
<task>
Review this change for material correctness and regression risks.
</task>
```

### Missing output contract

Bad: `Investigate and report back.`

Better:

```xml
<structured_output_contract>
Return:
1. root cause
2. evidence
3. smallest safe next step
</structured_output_contract>
```

### No follow-through default

Bad: `Debug this failure.`

Better:

```xml
<default_follow_through_policy>
Keep going until you have enough evidence to identify the root cause confidently.
</default_follow_through_policy>
```

### Asking for more reasoning instead of a better contract

Bad: `Think harder and be very smart.`

Better:

```xml
<verification_loop>
Before finalizing, verify that the answer matches the observed evidence and task requirements.
</verification_loop>
```

### Mixing unrelated jobs into one run

Bad: `Review this diff, fix the bug you find, update the docs, and suggest a roadmap.`

Better:
- Run review first.
- Run a separate fix prompt if needed (`codex exec resume --last` keeps the context).
- Use a third run for docs or roadmap work.

### Unsupported certainty

Bad: `Tell me exactly why production failed.`

Better:

```xml
<grounding_rules>
Ground every claim in the provided context or tool outputs.
If a point is an inference, label it clearly.
</grounding_rules>
```
