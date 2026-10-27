# Prompt Governance Checklist

## Runtime Template Checks

- Did you check `prompt_templates` in the database first rather than only inspecting repository files?
- Did you verify `agent_type`, `agent_name`, `preference_type`, and `status=active`?
- Did you check both `with_cache` and `without_cache` branches separately?
- Did you read back the DB record immediately after modifying it?

## Code Assembly Checks

- Did you inspect `_build_system_prompt` and `_build_user_prompt`?
- Did you inspect the cache-miss (`without_cache`) fallback branch?
- Did you check whether the adapter passes raw upstream text through directly?
- Did you check whether the service layer is still extracting legacy `action` / `price_targets` / `recommendation` fields?

## Data and Parameter Checks

- Did you check the actual runtime value of `analysis_date` in the logs?
- Did you check `start_date` / `end_date` / `ticker` in the tool arguments?
- Did you verify whether `current_price`, technical `latest_price`, and `effective_data_date` come from the same data source and date basis?
- Did you distinguish between "date drift", "price basis drift", and "prompt contamination"?

## Compliance and Output Checks

- Did you only strip surface-level recommendation words without addressing implicit trigger phrases?
- Did you inspect upstream analysts, risk assessors, and advisors in addition to the final manager?
- Did you verify that `user_view` and the detailed research body do not duplicate content?
- Did you verify that the final sanitizer does not reintroduce legacy compatibility fields?

## Verification Checks

- Did you run the narrowest regression test slice first?
- Did you fix any failures within the same slice and re-run?
- Did you run the governance validation suite afterward?
- If DB templates were modified, did you perform an independent read-back verification?
- If runtime behavior was changed, did you recommend or execute a re-run of the target workflow and inspect the logs?

## Common Root Causes in TradingAgentsCN

- The DB template is outdated, so the repository fallback never actually took effect.
- The adapter injects raw upstream reports directly into downstream prompts, causing compliance trigger phrases to propagate.
- The cache-miss path does not pin tool parameters to `analysis_date`, causing the LLM to guess historical dates on its own.
- The service layer still parses legacy `action` / `price_targets` from neutral JSON outputs.
- `current_price` and the price series used in technical analysis do not share the same date or data source.
