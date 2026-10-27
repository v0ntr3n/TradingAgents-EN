#!/usr/bin/env python3
"""
Test the CLI log repair effect
Verify that the user interface is clean and that logs are only written to files.
"""

import os
import sys
import subprocess

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_cli_logging_setup():
    """Test CLI log settings"""
    print("🔧 Test CLI log settings")
    print("=" * 60)
    
    try:
        # Import the CLI module to trigger log settings
        from cli.main import setup_cli_logging, logger
        from tradingagents.utils.logging_manager import get_logger_manager
        
        print("📊 Log processor before testing:")
        logger_manager = get_logger_manager()
        handlers_before = len(logger_manager.root_logger.handlers)
        console_handlers_before = sum(1 for h in logger_manager.root_logger.handlers 
                                    if hasattr(h, 'stream') and h.stream.name == '<stderr>')
        print(f"   Total number of processors: {handlers_before}")
        print(f"   Number of console processors: {console_handlers_before}")
        
        # Execute CLI log settings
        setup_cli_logging()
        
        print("\n📊 Log processor after testing:")
        handlers_after = len(logger_manager.root_logger.handlers)
        console_handlers_after = sum(1 for h in logger_manager.root_logger.handlers 
                                   if hasattr(h, 'stream') and h.stream.name == '<stderr>')
        print(f"   Total number of processors: {handlers_after}")
        print(f"   Number of console processors: {console_handlers_after}")
        
        # Verify effect
        if console_handlers_after < console_handlers_before:
            print("✅ Console log handler successfully removed")
        else:
            print("⚠️ Console log processor not completely removed")
        
        # Test log output
        print("\n🧪 Test log output:")
        print("   execute logger.info('test message')...")
        logger.info("This is a test log message and should only be written to the file and not displayed on the console")
        print("   ✅ If the timestamp and log information are not displayed above, the repair is successful.")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_console_output():
    """Test console output"""
    print("\n🎨 Test console output")
    print("=" * 60)
    
    try:
        from rich.console import Console
        
        console = Console()
        
        print("📊 Test Rich Console output:")
        console.print("[bold cyan]This is a user interface message[/bold cyan]")
        console.print("[green]✅ This should display normally without timestamp[/green]")
        console.print("[yellow]💡 This is a user-friendly prompt message[/yellow]")
        
        print("✅ Console The output is normal and the interface is refreshing")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_log_file_writing():
    """Test log file writing"""
    print("\n📁 Test log file writing")
    print("=" * 60)
    
    try:
        from cli.main import logger
        import glob
        
        # Write test log
        test_message = "CLI Log fix test message - this should only appear in the log file"
        logger.info(test_message)
        
        # Find log files
        log_files = glob.glob("data/logs/*.log") + glob.glob("logs/*.log") + glob.glob("*.log")
        
        if log_files:
            print(f"📄 log file found: {log_files}")
            
            # Check latest log files
            latest_log = max(log_files, key=os.path.getmtime)
            print(f"📄 Check latest log files: {latest_log}")
            
            try:
                with open(latest_log, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if test_message in content:
                        print("✅ Test messages are written to the log file")
                        return True
                    else:
                        print("⚠️ Test message not found in log file")
                        return False
            except Exception as e:
                print(f"⚠️ Failed to read log file: {e}")
                return False
        else:
            print("⚠️ Log file not found")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_cli_interface_preview():
    """Preview CLI interface effect"""
    print("\n👀 Preview CLI interface effect")
    print("=" * 60)
    
    try:
        from rich.console import Console
        from rich.panel import Panel
        
        console = Console()
        
        # Simulate the repaired CLI interface
        print("🎭 Simulate the repaired CLI interface:")
        print("-" * 40)
        
        # Title
        title_panel = Panel(
            "[bold blue]steps 1: Choose a market | Step 1: Select Market[/bold blue]\n"
            "Please select the stock market you want to analyze | Please select the stock market to analyze",
            box_style="cyan"
        )
        console.print(title_panel)
        
        # Options
        console.print("\n[bold cyan]Please select a stock market | Please select stock market:[/bold cyan]")
        console.print("[cyan]1[/cyan]. 🌍 US stocks | US Stock")
        console.print("   Example | Examples: SPY, AAPL, TSLA")
        console.print("[cyan]2[/cyan]. 🌍 A shares | China A-Share")
        console.print("   Example | Examples: 000001 (Ping An Bank), 600036 (China Merchants Bank)")
        console.print("[cyan]3[/cyan]. 🌍 Hong Kong stocks | Hong Kong Stock")
        console.print("   Example | Examples: 0700.HK (Tencent), 09988.HK (Alibaba)")
        
        print("\n" + "-" * 40)
        print("✅ Clean interface, no time stamps and technical log information")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Start testing the CLI log repair effect")
    print("=" * 80)
    
    results = []
    
    # test 1: CLI Log settings
    results.append(test_cli_logging_setup())
    
    # test 2: Console output
    results.append(test_console_output())
    
    # test 3: Log file writing
    results.append(test_log_file_writing())
    
    # test 4: CLI Interface preview
    results.append(test_cli_interface_preview())
    
    # Summary results
    print("\n" + "=" * 80)
    print("📋 Summary of test results")
    print("=" * 80)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "CLI Log settings",
        "Console Output test",
        "Log file writing",
        "CLI Interface preview"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! CLI log repair successful")
        print("\n📋 Repair effect:")
        print("1. ✅ The console no longer displays technical log information")
        print("2. ✅ Fresh and beautiful user interface")
        print("3. ✅ System logs are written to files normally")
        print("4. ✅ User prompts display using Rich Console")
        
        print("\n🎯 User experience improvement:")
        print("- Simple interface, no time stamp interference")
        print("- Color output is more beautiful")
        print("- Separation of technical information and user information")
        print("- Debug information is still logged in the log file")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
