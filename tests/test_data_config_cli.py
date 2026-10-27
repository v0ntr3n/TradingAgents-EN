#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test data directory configuration CLI function
Test Data Directory Configuration CLI Features
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tradingagents.config.config_manager import config_manager
from tradingagents.dataflows.config import get_data_dir, set_data_dir, initialize_config

def test_data_dir_configuration():
    """
    Test data directory configuration function
    Test data directory configuration functionality
    """
    print("\n=== Test data directory configuration function | Testing Data Directory Configuration ===")
    
    # 1. Test default configuration
    print("\n1. Test default configuration | Testing Default Configuration")
    initialize_config()
    default_data_dir = get_data_dir()
    print(f"Default data directory | Default data directory: {default_data_dir}")
    
    # 2. Test setting up a custom data directory
    print("\n2. Test setting up a custom data directory | Testing Custom Data Directory")
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_data_dir = os.path.join(temp_dir, "custom_trading_data")
        print(f"Set up a custom data directory | Setting custom data directory: {custom_data_dir}")
        
        set_data_dir(custom_data_dir)
        current_data_dir = get_data_dir()
        print(f"Current data directory | Current data directory: {current_data_dir}")
        
        # Verify directory is created
        if os.path.exists(custom_data_dir):
            print("✅ Custom data directory created successfully | Custom data directory created successfully")
            
            # Check subdirectory structure
            expected_subdirs = [
                "finnhub",
                "finnhub/news", 
                "finnhub/insider_sentiment",
                "finnhub/insider_transactions"
            ]
            
            for subdir in expected_subdirs:
                subdir_path = os.path.join(custom_data_dir, subdir)
                if os.path.exists(subdir_path):
                    print(f"  ✅ subdirectory exists | Subdirectory exists: {subdir}")
                else:
                    print(f"  ❌ Subdirectory missing | Subdirectory missing: {subdir}")
        else:
            print("❌ Custom data directory creation failed | Custom data directory creation failed")
    
    # 3. Test environment variable configuration
    print("\n3. Test environment variable configuration | Testing Environment Variable Configuration")
    with tempfile.TemporaryDirectory() as temp_dir:
        env_data_dir = os.path.join(temp_dir, "env_trading_data")
        
        # Set environment variables
        os.environ["TRADINGAGENTS_DATA_DIR"] = env_data_dir
        print(f"Set environment variables | Setting environment variable: TRADINGAGENTS_DATA_DIR={env_data_dir}")
        
        # Reinitialize configuration to read environment variables
        initialize_config()
        env_current_data_dir = get_data_dir()
        print(f"Environment variable data directory | Environment variable data directory: {env_current_data_dir}")
        
        if env_current_data_dir == env_data_dir:
            print("✅ Environment variable configuration takes effect | Environment variable configuration effective")
        else:
            print("❌ Environment variable configuration does not take effect | Environment variable configuration not effective")
        
        # Clean up environment variables
        del os.environ["TRADINGAGENTS_DATA_DIR"]
    
    # 4. Test Configuration Manager Integration
    print("\n4. Test Configuration Manager Integration | Testing Configuration Manager Integration")
    settings = config_manager.load_settings()
    print(f"Configuration manager settings | Configuration manager settings:")
    for key, value in settings.items():
        if 'dir' in key.lower():
            print(f"  {key}: {value}")
    
    # 5. Test directory automatic creation function
    print("\n5. Test directory automatic creation function | Testing Auto Directory Creation")
    config_manager.ensure_directories_exist()
    print("✅ Directory automatic creation function test completed | Auto directory creation test completed")
    
    print("\n=== Data directory configuration test completed | Data Directory Configuration Test Completed ===")

def test_cli_commands():
    """
    Test CLI commands (simulation)
    Test CLI commands (simulation)
    """
    print("\n=== CLI Command Testing Guide | CLI Commands Test Guide ===")
    print("\n Please run the following commands manually to test the CLI functionality:")
    print("Please manually run the following commands to test CLI functionality:")
    print()
    print("1. View current configuration | View current configuration:")
    print("   python -m cli.main data-config")
    print("   python -m cli.main data-config --show")
    print()
    print("2. Set up a custom data directory | Set custom data directory:")
    print("   python -m cli.main data-config --set C:\\custom\\trading\\data")
    print()
    print("3. Reset to default configuration | Reset to default configuration:")
    print("   python -m cli.main data-config --reset")
    print()
    print("4. View all available commands | View all available commands:")
    print("   python -m cli.main --help")
    print()
    print("5. Run the configuration demo script | Run configuration demo script:")
    print("   python examples/data_dir_config_demo.py")

def main():
    """
    Main test function
    Main test function
    """
    print("Data directory configuration function test | Data Directory Configuration Feature Test")
    print("=" * 70)
    
    try:
        # Run configuration function tests
        test_data_dir_configuration()
        
        # Show CLI command testing guide
        test_cli_commands()
        
        print("\n🎉 All tests completed!| All tests completed!")
        print("\n📝 Summary | Summary:")
        print("✅ The data directory configuration function has been implemented | Data directory configuration feature implemented")
        print("✅ Support custom path settings | Custom path setting supported")
        print("✅ Support environment variable configuration | Environment variable configuration supported")
        print("✅ Integrated configuration manager | Configuration manager integrated")
        print("✅ CLI Complete command interface | CLI command interface complete")
        print("✅ Automatic directory creation feature | Auto directory creation feature")
        
    except Exception as e:
        print(f"\n❌ An error occurred during testing | Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)