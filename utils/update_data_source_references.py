#!/usr/bin/env python3
"""
Batch update data source references
will all"Tong Da Xin"Reference updated to"Tushare"or generic description
"""

import os
import re
from pathlib import Path

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('default')


def update_file_content(file_path: Path, replacements: list):
    """Update file content"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        for old_text, new_text in replacements:
            content = content.replace(old_text, new_text)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"✅ update: {file_path}")
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"❌ Update failed {file_path}: {e}")
        return False

def main():
    """main function"""
    logger.info(f"🔧 Batch update data source references")
    logger.info(f"=")
    
    # Project root directory
    project_root = Path(__file__).parent.parent
    
    # File mode that needs to be updated
    file_patterns = [
        "**/*.py",
        "**/*.md",
        "**/*.txt"
    ]
    
    # Excluded directories
    exclude_dirs = {
        ".git", "__pycache__", "env", "venv", ".vscode", 
        "node_modules", ".pytest_cache", "dist", "build"
    }
    
    # Replacement rules
    replacements = [
        # Data source identification
        ("Data source: Tushare Data interface", "Data source: Tushare Data interface"),
        ("Data source: Tushare Data interface (real time data)", "Data source: Tushare Data interface"),
        ("Data source: Tushare Data interface\n", "Data source: Tushare Data interface\n"),
        
        # User interface prompts
        ("Using China Stock Data Sources for Fundamental Analysis", "Using China Stock Data Sources for Fundamental Analysis"),
        ("Using China Stock Data Source", "Using China Stock Data Source"),
        ("Tushare Data interface + fundamental analysis model", "Tushare Data interface + fundamental analysis model"),
        
        # Error message
        ("Due to data interface limitations", "Due to data interface limitations"),
        ("Data interface requires network connection", "Data interface requires network connection"),
        ("data server", "data server"),
        
        # Technical documentation
        ("Tushare + FinnHub API", "Tushare + FinnHub API"),
        ("Tushare Data interface", "Tushare Data interface"),
        
        # CLI Tips
        ("China stock data source will be used", "China stock data source will be used"),
        ("china_stock", "china_stock"),
        
        # Notes and instructions
        ("# China stock data", "# China stock data"),
        ("Data source search function", "Data source search function"),
        
        # variable names and identifiers (Keep the code functional and only update the display text)
        ("'china_stock'", "'china_stock'"),
        ('"china_stock"', '"china_stock"'),
    ]
    
    # Gather all files that need to be updated
    files_to_update = []
    
    for pattern in file_patterns:
        for file_path in project_root.glob(pattern):
            # Check if it is in the excluded directory
            if any(exclude_dir in file_path.parts for exclude_dir in exclude_dirs):
                continue
            
            # Skip binary and special files
            if file_path.suffix in {'.pyc', '.pyo', '.so', '.dll', '.exe'}:
                continue
                
            files_to_update.append(file_path)
    
    logger.info(f"📁 found {len(files_to_update)} files need to be checked")
    
    # update file
    updated_count = 0
    
    for file_path in files_to_update:
        if update_file_content(file_path, replacements):
            updated_count += 1
    
    logger.info(f"\n📊 Update completed:")
    logger.info(f"   Check files: {len(files_to_update)}")
    logger.info(f"   update file: {updated_count}")
    
    if updated_count > 0:
        logger.info(f"\n🎉 successfully updated {updated_count} Data source reference of a file!")
        logger.info(f"\n📋 Main updates:")
        logger.info(f"   ✅ 'Tushare Data interface' → 'Tushare Data interface'")
        logger.info(f"   ✅ 'Tongdaxin data source' → 'China stock data source'")
        logger.error(f"   ✅ Error messages and user interface text")
        logger.info(f"   ✅ Technical documentation and notes")
    else:
        logger.info(f"\n✅ Data source references for all files are up to date")

if __name__ == "__main__":
    main()
