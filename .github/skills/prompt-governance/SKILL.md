---
name: prompt-governance
description: "Audit, fix, and verify agent and prompt workflows in TradingAgentsCN. Use for portfolio analysis, workflow prompts, MongoDB prompt_templates, adapter prompt assembly, compliance fixes, and synchronizing runtime templates with code. Triggers: modify agent prompt, prompt governance, DB template sync, workflow prompt fix, portfolio analysis prompt troubleshooting, prompt compliance, runtime prompt audit."
argument-hint: "Describe the workflow, agent name, target issue, and whether direct modifications are allowed. E.g.: Fix date drift in the pa_technical_v2 prompt of position_analysis_v2, and synchronize runtime templates with code."
user-invocable: true
---

# Prompt Governance

This skill handles scenarios where "agent behavior is wrong, and the root cause could be in the prompt itself, code assembly, runtime database templates, or legacy compatibility parsing paths."

It is not a simple copywriting workflow, but a runtime-first governance workflow: first identify the prompt and code paths that actually control runtime behavior, then apply minimal fixes and complete verification.

## When to Use

- A user asks to modify the prompt of a workflow or agent, but runtime results remain unchanged after editing repository files.
- You need to simultaneously inspect repository fallback prompts, `prompt_templates` in MongoDB, `_build_system_prompt` / `_build_user_prompt` in the adapter, and parsing logic in the service layer.
- You are working on portfolio analysis, research pipelines, compliance rewrites, user view streamlining, trigger phrase removal, or DB template synchronization.
- Runtime generated content in the logs diverges from what is expected based on repository templates/code.

## When Not to Use

- Editing a small piece of static UI copy that is guaranteed not to use database templates at runtime.
- Merely explaining what an agent does without fixing behavior.
- Ordinary backend bugs that do not involve prompts, workflows, adapters, or DB templates at all.

## Core Principles

1. Inspect the actual runtime control plane before modifying repository files.
2. Formulate a minimal falsifiable hypothesis first, then apply a minimal fix rather than rewriting entire templates upfront.
3. DB templates and code assembly may jointly control behavior; never assume changing only one place is sufficient.
4. Always run narrow verification after any change, followed by governance validation.

## Standard Workflow

### 1. Pinpoint the Control Path

- Locate `workflow_id`, `agent_name`, trigger logs, failing outputs, and related tests first.
- Prioritize finding where behavior is actually computed or assembled, rather than only looking at registration layers.
- For prompt-related issues, distinguish between:
  - Runtime DB templates
  - Repository fallback templates
  - Prompt fragments appended or rewritten by the adapter
  - Secondary output parsing or sanitization in the service layer

### 2. Audit Runtime Templates First

- Query the MongoDB `prompt_templates` collection first; do not assume repository templates are active.
- Read the template matching the target `agent_type` + `agent_name` + `preference_type` + `status=active`.
- If there are dual `without_cache` / `with_cache` branches, verify both separately.
- When modifying a DB template, only update the target active document and immediately read it back to confirm.

### 3. Audit the Code Assembly Layer Next

- In the adapter, focus on checking:
  - `_build_system_prompt`
  - `_build_user_prompt`
  - Cache-miss (`without_cache`) fallback branches
  - Summarization and sanitization logic for upstream reports
- In the service / workflow layer, focus on checking:
  - Sources of `analysis_date`, `current_price`, and `effective_data_date`
  - Legacy `action` / `price_targets` / `recommendation` extraction logic
  - Whether output sanitization reintroduces legacy semantics

### 4. Determine the Fix Scope

- **DB only**: Runtime template is wrong, while code assembly is correct.
- **Code only**: Runtime template is correct, but the adapter / service is appending, contaminating, or misparsing.
- **Both**: Both runtime templates and code assembly need synchronization to prevent future drift.

### 5. Implement the Fix

- Keep code changes minimal; avoid rewriting entire prompts.
- For cache-miss scenarios, prioritize adding explicit parameter constraints so the LLM does not guess dates, tickers, or price bases.
- For upstream contamination, prioritize summarization and sanitization rather than passing raw long-form text downstream.
- For legacy compatibility exits, prioritize removing automatic extraction of legacy fields rather than hard-scrubbing at the final copy layer.

### 6. Verify

- Add or update the narrowest regression test first.
- Run only the affected test slice in the first verification round.
- Run the governance validation task next.
- If DB templates were modified, perform a read-back check; if runtime behavior changed, re-run the target workflow and inspect the logs.

### 7. Report Results

Your final conclusion must include at least:

- Whether the root cause was in DB templates, code assembly, service parsing, or data basis.
- Which control planes were actually modified.
- Which verifications were performed and which passed.
- Whether any residual risks or follow-up observation points remain.

## Execution Checklist

Follow these steps in order without skipping:

1. Check actual `workflow` / `agent` / `tool args` in the logs.
2. Check the active document in MongoDB `prompt_templates`.
3. Check the actual assembly path in the adapter / service.
4. Select and implement the minimal fix scope.
5. Run narrow tests.
6. Run governance validation.
7. Read back from the DB to confirm if DB changes were made.

## Common Pitfalls

- Modifying only repository prompts without updating runtime DB templates.
- Modifying only the manager prompt without addressing contamination from raw upstream analyst text.
- Scrubbing only the final output without removing legacy compatibility extraction in the service layer.
- Looking only at the `analysis_date` variable without checking what arguments the LLM actually passed during tool calls.
- Misdiagnosing a `current_price` basis mismatch as a prompt issue without inspecting logs and data sources.

See the [Prompt Governance Checklist](./references/checklist.md) for detailed checkpoints.
