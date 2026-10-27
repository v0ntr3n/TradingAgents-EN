---
description: "Prepare the current version release for the repository, automatically identify the previous version, and output release blockers, required file modifications, and a verification checklist."
name: "Prepare Current Version Release"
argument-hint: "Optionally specify a version range or additional instructions, e.g.: from 2.0.0 to 2.0.1, focusing on checking the upgrade package and migrations."
agent: "autoreleases"
---

Prepare the current version release for the repository.

Requirements:
1. If I have not explicitly provided a version range, automatically identify the target version and the previous version.
2. Scan the git log and changed files within this version range.
3. Check `VERSION`, `BUILD_INFO`, `releases/<target_version>/manifest.json`, `releases/<target_version>/upgrade_config.json`, migrations, packaging scripts, updater scripts, startup scripts, and release process documentation.
4. If the repository adopts the `D:/release/<version>/revNNN/` archiving convention, check whether the archive directory is complete, whether the revision number is incremented, and whether `RELEASE_UPLOAD_INFO.md` records the byte sizes of the installer and upgrade packages.
5. Output release blockers first, followed by files requiring modification, upgrade package consistency, release archives and upload artifacts, `upgrade_config` coverage, migration review, verification checklist, and final conclusion.
6. Default to read-only analysis mode; do not modify files directly unless I explicitly ask you to start implementation.
7. Additionally, generate a draft "Release Improvements Document (Target Version vs. Previous Version)"; if I explicitly request executing a full release or writing final artifacts, output it as a standalone Markdown document and state its path in the results.
