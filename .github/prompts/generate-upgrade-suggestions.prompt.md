---
description: "Generate upgrade_config, migration, manifest, and release fix suggestions based on version diffs, defaulting to read-only analysis."
name: "Generate Upgrade Suggestions"
argument-hint: "Optionally specify a version range or additional instructions, e.g.: from 2.0.0 to 2.0.1, focusing on generating upgrade_config and migration suggestions."
agent: "autoreleases"
---

Generate upgrade suggestions based on the version differences in the current repository.

Requirements:
1. If I have not explicitly provided a version range, automatically identify the target version and the previous version.
2. Scan the git log and changed files within this version range.
3. Determine which changes require updates to `manifest`, `upgrade_config`, migrations, packaging scripts, archiving scripts, or release notes.
4. If the repository adopts the `D:/release/<version>/revNNN/` archiving convention, additionally point out whether a release archive directory, upload info document, or byte size record needs to be added.
5. Organize the output in the following priority order: blockers, files requiring modification, release archives and upload artifacts, `upgrade_config` suggestions, migration suggestions, verification checklist, and final conclusion.
6. For `upgrade_config`, highlight collections recommended for inspection, such as `system_configs`, `prompt_templates`, `agent_configs`, `workflow_definitions`, and `tool_configs`.
7. For migrations, point out whether any are missing, incomplete, or carry idempotency or field-copying risks.
8. Default to read-only analysis mode; do not modify files directly unless I explicitly ask you to start implementation.
9. Additionally, compile a draft "Release Improvements Document (Target Version vs. Previous Version)" for direct reuse in the final release notes; if I request writing final artifacts, output it as a standalone Markdown document.
