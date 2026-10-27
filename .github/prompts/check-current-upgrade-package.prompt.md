---
description: "Check whether the upgrade package for the current version is safe to release, automatically identifying the version and focusing on packaging manifests, updater replacement lists, upgrade_config, and migrations."
name: "Check Current Upgrade Package Readiness"
argument-hint: "Optionally specify a version range or additional instructions, e.g.: focus on checking upgrade package consistency and rollback risks."
agent: "autoreleases"
---

Check whether the upgrade package for the current version in this repository can be safely released.

Requirements:
1. If I have not explicitly provided a version range, automatically identify the target version and the previous version.
2. Scan the git log and changed files within this version range.
3. Focus on checking `build_update_package.ps1`, `apply_update.ps1`, `start_all.ps1`, `apply_upgrade_config.py`, `manifest`, `upgrade_config`, migrations, and release process documentation.
4. If the repository adopts the `D:/release/<version>/revNNN/` archiving convention, check whether the upgrade package archive exists and whether its byte size and sha256 checksum have been recorded in `RELEASE_UPLOAD_INFO.md`.
5. Focus on outputting upgrade package consistency, updater replacement consistency, release archives and upload artifacts, `upgrade_config` coverage, migration risks, rollback risks, and the final conclusion.
6. Output release blockers first, followed by files requiring modification and the verification checklist.
7. Default to read-only analysis mode; do not modify files directly unless I explicitly ask you to start implementation.
8. Include a "Summary of Improvements (Target Version vs. Previous Version)" in the final output; if a full release has been executed and final artifacts generated, output the path to the corresponding Markdown document.
