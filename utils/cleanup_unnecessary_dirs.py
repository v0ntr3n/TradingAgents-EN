#!/usr/bin/env python3
"""
Clean unnecessary directories and files
Remove automatically generated files and temporary output
"""

import os
import shutil
from pathlib import Path

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('default')


def cleanup_directories():
    """Clean unnecessary directories"""
    logger.info(f"🧹 Clean unnecessary directories and files")
    logger.info(f"=")
    
    # Project root directory
    project_root = Path(".")
    
    # Directories that need to be cleaned
    cleanup_dirs = [
        "tradingagents.egg-info",
        "enhanced_analysis_reports",
        "__pycache__",
        ".pytest_cache",
    ]
    
    # File patterns that need to be cleaned
    cleanup_patterns = [
        "*.pyc",
        "*.pyo", 
        "*.pyd",
        ".DS_Store",
        "Thumbs.db"
    ]
    
    cleaned_count = 0
    
    # Clean directory
    for dir_name in cleanup_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                logger.info(f"✅ delete directory: {dir_name}")
                cleaned_count += 1
            except Exception as e:
                logger.error(f"❌ Delete failed {dir_name}: {e}")
    
    # Clean files recursively
    for pattern in cleanup_patterns:
        for file_path in project_root.rglob(pattern):
            try:
                file_path.unlink()
                logger.info(f"✅ Delete files: {file_path}")
                cleaned_count += 1
            except Exception as e:
                logger.error(f"❌ Delete failed {file_path}: {e}")
    
    return cleaned_count

def update_gitignore():
    """Update .gitignore file"""
    logger.info(f"\n📝 Update .gitignore file")
    logger.info(f"=")
    
    gitignore_path = Path(".gitignore")
    
    # Ignore rules that need to be added
    ignore_rules = [
        "# Python package metadata",
        "*.egg-info/",
        "tradingagents.egg-info/",
        "",
        "# Temporary output file", 
        "enhanced_analysis_reports/",
        "analysis_reports/",
        "",
        "# Python cache",
        "__pycache__/",
        "*.py[cod]",
        "*$py.class",
        ".pytest_cache/",
        "",
        "# System files",
        ".DS_Store",
        "Thumbs.db",
        "",
        "# IDE File",
        ".vscode/settings.json",
        ".idea/",
        "",
        "# log file",
        "*.log",
        "logs/",
    ]
    
    try:
        # Read existing content
        existing_content = ""
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # Check which rules need to be added
        new_rules = []
        for rule in ignore_rules:
            if rule.strip() and rule not in existing_content:
                new_rules.append(rule)
        
        if new_rules:
            # Add new rule
            with open(gitignore_path, 'a', encoding='utf-8') as f:
                f.write("\n# Rules added by automatic cleaning script\n")
                for rule in new_rules:
                    f.write(f"{rule}\n")
            
            logger.info(f"✅ added {len(new_rules)} new ignore rules")
        else:
            logger.info(f"✅ .gitignore Already the latest")
            
    except Exception as e:
        logger.error(f"❌ Update .gitignore failed: {e}")

def analyze_upstream_contribution():
    """Analyze the upstream_contribution directory"""
    logger.debug(f"\n🔍 Analyze the upstream_contribution directory")
    logger.info(f"=")
    
    upstream_dir = Path("upstream_contribution")
    
    if not upstream_dir.exists():
        logger.info(f"✅ upstream_contribution Directory does not exist")
        return
    
    # Statistical content
    batch_dirs = list(upstream_dir.glob("batch*"))
    json_files = list(upstream_dir.glob("*.json"))
    
    logger.info(f"📊 Discover content:")
    logger.info(f"   - Batch Directory: {len(batch_dirs)}a")
    logger.info(f"   - JSON File: {len(json_files)}a")
    
    for batch_dir in batch_dirs:
        logger.info(f"   - {batch_dir.name}: {len(list(batch_dir.rglob('*')))}files")
    
    # Ask whether to delete
    logger.info(f"\n💡 upstream_contribution Directory purpose:")
    logger.info(f"   - Prepare for upstream projects(TauricResearch/TradingAgents)Contribute code")
    logger.info(f"   - Contains version with Chinese content removed")
    logger.info(f"   - If you do not plan to contribute to upstream, you can delete it")
    
    return len(batch_dirs) + len(json_files)

def main():
    """main function"""
    logger.info(f"🧹 TradingAgents Directory cleaning tool")
    logger.info(f"=")
    logger.info(f"💡 target: Clean automatically generated files and unnecessary directories")
    logger.info(f"=")
    
    # Clean directories and files
    cleaned_count = cleanup_directories()
    
    # update gitignore
    update_gitignore()
    
    # analysis upstream_contribution
    upstream_count = analyze_upstream_contribution()
    
    # Summary
    logger.info(f"\n📊 Cleanup summary")
    logger.info(f"=")
    logger.info(f"✅ Cleaned up {cleaned_count} files/directories")
    logger.info(f"📝 Updated .gitignore file")
    
    if upstream_count > 0:
        logger.warning(f"⚠️ upstream_contribution Directory contains {upstream_count} items")
        logger.info(f"   If you do not need to contribute to upstream, you can delete it manually:")
        logger.info(f"   rm -rf upstream_contribution/")
    
    logger.info(f"\n🎉 Cleanup completed! The project directory is cleaner")
    logger.info(f"\n💡 Suggestions:")
    logger.info(f"   1. Check git status: git status")
    logger.info(f"   2. Commit cleanup changes: git add . && git commit -m 'Clean unnecessary directories and files'")
    logger.info(f"   3. If upstream_contribution is not needed, it can be deleted manually")

if __name__ == "__main__":
    main()
