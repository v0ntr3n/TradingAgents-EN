#!/usr/bin/env python3
"""
Test the error log configuration of the app directory
Verify that the error log handler in app/core/logging_config.py is configured correctly
"""

import sys
import logging
from pathlib import Path

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging_config import setup_logging


def test_error_logging_toml_config():
    """Test reading error log handler from TOML configuration"""
    print("\n" + "=" * 60)
    print("test 1: TOML Error log handler in configuration")
    print("=" * 60)
    
    # Setup log
    setup_logging(log_level="INFO")
    
    # Get logger
    webapi_logger = logging.getLogger("webapi")
    worker_logger = logging.getLogger("worker")
    
    # Check processor
    print("\n✅ webapi logger handler:")
    for handler in webapi_logger.handlers:
        print(f"  - {handler.__class__.__name__}: {getattr(handler, 'baseFilename', 'N/A')}")
        if hasattr(handler, 'level'):
            print(f"    level: {logging.getLevelName(handler.level)}")
    
    print("\n✅ worker logger handler:")
    for handler in worker_logger.handlers:
        print(f"  - {handler.__class__.__name__}: {getattr(handler, 'baseFilename', 'N/A')}")
        if hasattr(handler, 'level'):
            print(f"    level: {logging.getLevelName(handler.level)}")
    
    # Verify error log handler exists
    error_handlers = [h for h in webapi_logger.handlers 
                     if hasattr(h, 'baseFilename') and 'error.log' in h.baseFilename]
    
    if error_handlers:
        print("\n✅ The error log handler is configured correctly!")
        for handler in error_handlers:
            print(f"  File: {handler.baseFilename}")
            print(f"  level: {logging.getLevelName(handler.level)}")
            print(f"  maximum size: {handler.maxBytes} Bytes")
            print(f"  Number of backups: {handler.backupCount}")
    else:
        print("\n❌ Error log handler not found!")
        return False
    
    return True


def test_error_logging_functionality():
    """Test the actual functionality of the error log"""
    print("\n" + "=" * 60)
    print("test 2: Error log function test")
    print("=" * 60)
    
    # Clear existing logger
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # reset log
    setup_logging(log_level="INFO")
    
    # Get logger
    logger = logging.getLogger("webapi")
    
    # Record different levels of logs
    print("\n📝 Record test log:")
    logger.debug("This is a DEBUG level log (should not appear in error.log)")
    logger.info("This is an INFO level log (should not appear in error.log)")
    logger.warning("This is a WARNING level log (should appear in error.log)")
    logger.error("This is an ERROR level log (should appear in error.log)")
    logger.critical("This is a CRITICAL level log (should appear in error.log)")
    
    print("✅ Log recorded")
    
    # Check the error.log file
    error_log_path = Path("logs/error.log")
    if error_log_path.exists():
        print(f"\n✅ error.log File created: {error_log_path.absolute()}")
        
        # Read file contents
        with open(error_log_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check content
        print(f"\n📄 error.log File content (last 500 characters):")
        print("-" * 60)
        print(content[-500:] if len(content) > 500 else content)
        print("-" * 60)
        
        # Verify content
        if "WARNING" in content or "ERROR" in content or "CRITICAL" in content:
            print("\n✅ error.log Contains expected error level logs!")
            return True
        else:
            print("\n⚠️ error.log File exists but content is not as expected")
            return False
    else:
        print(f"\n❌ error.log File not created: {error_log_path.absolute()}")
        return False


def test_webapi_and_worker_loggers():
    """Both test webapi and worker loggers have error log handlers"""
    print("\n" + "=" * 60)
    print("test 3: webapi Verify with worker logger")
    print("=" * 60)
    
    # Clear existing logger
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # reset log
    setup_logging(log_level="INFO")
    
    loggers_to_check = ["webapi", "worker", "uvicorn", "fastapi"]
    all_ok = True
    
    for logger_name in loggers_to_check:
        logger = logging.getLogger(logger_name)
        error_handlers = [h for h in logger.handlers 
                         if hasattr(h, 'baseFilename') and 'error.log' in h.baseFilename]
        
        if error_handlers:
            print(f"✅ {logger_name:10s} - There is an error log handler")
        else:
            print(f"❌ {logger_name:10s} - Missing error log handler")
            all_ok = False
    
    return all_ok


if __name__ == "__main__":
    print("=" * 60)
    print("app Directory error log configuration test")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("TOML Configuration test", test_error_logging_toml_config()))
    except Exception as e:
        print(f"\n❌ TOML Configuration test failed: {e}")
        results.append(("TOML Configuration test", False))
    
    try:
        results.append(("Error log function test", test_error_logging_functionality()))
    except Exception as e:
        print(f"\n❌ Error log function test failed: {e}")
        results.append(("Error log function test", False))
    
    try:
        results.append(("Logger verification test", test_webapi_and_worker_loggers()))
    except Exception as e:
        print(f"\n❌ Logger verification test failed: {e}")
        results.append(("Logger verification test", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test summary")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:20s} - {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ All tests passed! The error log configuration for the app directory has been correctly fixed.")
    else:
        print("\n❌ Some tests failed, please check the configuration.")
    
    sys.exit(0 if all_passed else 1)

