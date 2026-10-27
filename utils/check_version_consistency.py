#!/usr/bin/env python3
"""
Version number consistency checking tool
Ensure that all version number references in the project are consistent
"""

import os
import re
from pathlib import Path

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('default')


def get_target_version():
    """Get target version number from VERSION file"""
    version_file = Path("VERSION")
    if version_file.exists():
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

# Low-noise version specification helper functions and dedicated checks

def normalize_version(v: str) -> str:
    """Standardized version string for comparison (prefixes and modifications removed)"""
    return (
        v.lower()
         .replace('version-', '')
         .replace('version', '')
         .lstrip('v')
         .strip()
    )


def check_special_files(file_path: Path, content: str, target_version: str):
    """Perform precise verification on specific files to reduce false positives"""
    issues = []
    target_norm = normalize_version(target_version)
    target_numeric = target_norm.replace('cn-', '')  # pyproject.toml Use a digital-only version

    # 1) pyproject.toml: version Fields should be consistent with the target digital version
    if file_path.name == 'pyproject.toml':
        m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', content)
        if m:
            found = m.group(1).strip()
            if found != target_numeric:
                issues.append({
                    'line': content[:m.start()].count('\n') + 1,
                    'found': found,
                    'expected': target_numeric,
                    'context': content[max(0, m.start()-20):m.end()+20]
                })
        else:
            issues.append({'line': 1, 'found': '(missing version)', 'expected': target_numeric, 'context': ''})
        return issues

    # 2) README.md: badge with"latest version"Tips
    if file_path.name == 'README.md':
        # shields The badge will display a single - as --
        badge_text = normalize_version(target_version).replace('cn-', 'cn-').replace('-', '--')
        if badge_text not in content:
            issues.append({'line': 1, 'found': '(missing/old badge)', 'expected': badge_text, 'context': 'badge'})
        if target_version not in content:
            issues.append({'line': 1, 'found': '(missing latest tip)', 'expected': target_version, 'context': 'latest-tip'})
        return issues

    # 3) CHANGELOG: Allow historical versions to exist without verification
    if file_path.name.upper() == 'CHANGELOG.MD':
        return []

    return []


def check_file_versions(file_path: Path, target_version: str):
    """Check version number in file (low noise strategy)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Perform precise checks on specific files
        special_issues = check_special_files(file_path, content, target_version)
        if special_issues:
            return special_issues

        # CHANGELOG and other documents are ignored by default (allow historical versions and dependent versions to exist)
        if file_path.name.upper() == 'CHANGELOG.MD':
            return []

        return []  # The remaining files will not be scanned in a generalized manner to avoid false positives.

    except Exception as e:
        return [{'error': str(e)}]

def main():
    """main check function"""
    logger.debug(f"🔍 Version number consistency check")
    logger.info(f"=")

    # Get target version number
    target_version = get_target_version()
    if not target_version:
        logger.error(f"❌ Unable to read VERSION file")
        return

    logger.info(f"🎯 target version: {target_version}")

    # Documents to be checked
    files_to_check = [
        "README.md",
        "pyproject.toml",
        "docs/releases/CHANGELOG.md",  # Only used for existence verification, checks are ignored internally
    ]

    total_issues = 0

    for file_path in files_to_check:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"⚠️ File does not exist: {file_path}")
            continue

        logger.info(f"\n📄 Check files: {file_path}")
        issues = check_file_versions(path, target_version)

        if not issues:
            logger.info(f"   ✅ The version number is consistent")
        else:
            for issue in issues:
                if 'error' in issue:
                    logger.error(f"   ❌ Check for errors: {issue['error']}")
                else:
                    logger.error(f"   ❌ No.{issue['line']}OK: discover '{issue['found']}', Expectation '{issue['expected']}'")
                    logger.info(f"      context: ...{issue['context']}...")
                total_issues += len(issues)

    # Summary
    logger.info(f"\n📊 Inspection summary")
    logger.info(f"=")

    if total_issues == 0:
        logger.info(f"🎉 All version numbers are consistent!")
        logger.info(f"✅ Current version: {target_version}")
    else:
        logger.warning(f"⚠️ discover {total_issues} Version number inconsistency issue")
        logger.info(f"Please fix the above issue manually")

    # Version number specification reminder
    logger.info(f"\n💡 Version number specification:")
    logger.info(f"   - master version file: VERSION")
    logger.info(f"   - Current version: {target_version}")
    logger.info(f"   - Format requirements: v0.1.x")
    logger.info(f"   - Historical version: Can be retained in CHANGELOG")

if __name__ == "__main__":
    main()
