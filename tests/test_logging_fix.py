#!/usr/bin/env python3
"""
Script to test log repair effect
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_logging_fix():
    """Test log repair effect"""
    print("🔍 Test log repair effect")
    print("=" * 60)
    
    try:
        # Initialize TradingAgents log system
        from tradingagents.utils.logging_init import init_logging, get_logger
        init_logging()
        
        # Get logger
        logger = get_logger('test')
        logger.info("🧪 Test log system initialization successful")
        
        # import TradingAgents
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = False  # Use offline mode to avoid API calls
        config["llm_provider"] = "dashscope"
        config["debug"] = True  # Enable debug mode
        
        logger.info(f"✅ Configuration created successfully")
        logger.info(f"   LLM provider: {config['llm_provider']}")
        logger.info(f"   Online tools: {config['online_tools']}")
        logger.info(f"   debug mode: {config['debug']}")
        
        # Create an analysis chart
        graph = TradingAgentsGraph(
            selected_analysts=["market"],  # Use only market analysts for quick testing
            debug=True,
            config=config
        )
        
        logger.info(f"✅ TradingAgentsGraph Created successfully")
        
        # Test whether market analysts can record logs correctly
        print(f"\n🚀 Start testing the Market Analyst Diary...")
        
        # Check log files
        log_file = Path("logs/tradingagents.log")
        if log_file.exists():
            print(f"✅ Log file exists: {log_file}")
            
            # Read the last few lines of the log
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) > 0:
                    print(f"📊 The last 5 lines of the log file:")
                    for line in lines[-5:]:
                        print(f"   {line.strip()}")
                else:
                    print(f"⚠️ Log file is empty")
        else:
            print(f"❌ Log file does not exist: {log_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_logging_fix()
