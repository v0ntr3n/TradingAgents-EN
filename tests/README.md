# TradingAgents-CN Test Directory

This directory contains all test files for the TradingAgents-CN project, used to verify functional correctness, API integrations, and model testing.

## Directory Structure

```
tests/
├── README.md                           # This file
├── __init__.py                         # Python package initialization
├── integration/                        # Integration tests
│   ├── __init__.py
│   └── test_dashscope_integration.py   # Alibaba Bailian (DashScope) integration test
├── test_*.py                           # Functional tests
└── debug_*.py                          # Debugging and diagnostic tools
```

## Test Categories

### 🔧 API and Integration Tests
- `test_all_apis.py` - Test all API keys
- `test_correct_apis.py` - Google and Reddit API tests
- `test_analysis_with_apis.py` - API integration analysis tests
- `test_toolkit_tools.py` - Toolkit tests
- `integration/test_dashscope_integration.py` - Alibaba Bailian (DashScope) integration test

### 📊 Data Source Tests
- `fast_tdx_test.py` - Tushare data interface quick connection test
- `test_tdx_integration.py` - Tushare data interface full integration test

### ⚡ Performance Tests
- `test_redis_performance.py` - Redis performance benchmark test
- `quick_redis_test.py` - Redis quick connection test

### 🤖 AI Model Tests
- `test_chinese_output.py` - Chinese output test
- `test_gemini*.py` - Google Gemini model family tests
- `test_embedding_models.py` - Embedding model tests
- `test_google_memory_fix.py` - Google AI memory feature test

### 🌐 Web Interface Tests
- `test_web_interface.py` - Web interface functional tests

### 🔍 Debugging and Diagnostic Tools
- `debug_imports.py` - Import issue diagnostics
- `diagnose_gemini_25.py` - Gemini 2.5 model diagnostics
- `check_gemini_models.py` - Gemini model availability check

### 🧪 Functional Tests
- `test_analysis.py` - Basic analysis functionality test
- `test_format_fix.py` - Formatting fix test
- `test_progress.py` - Progress tracking test

## Running Tests

### Run All Tests
```bash
# Run from the project root directory
python -m pytest tests/

# Or run a specific test directly
cd tests
python test_chinese_output.py
```

### Run CI Smoke Tests
```bash
python -m pytest tests/config/test_settings.py tests/config/test_logging_config.py tests/middleware/test_trace_id.py
```

Note: The repository's default pytest configuration only collects the `tests/` directory to prevent temporary debugging scripts in the root directory from being inadvertently included in standard regression runs.

### Run Specific Test Categories
```bash
# API tests
python tests/test_all_apis.py

# Gemini model tests
python tests/test_gemini_correct.py

# Web interface tests
python tests/test_web_interface.py

# Alibaba Bailian (DashScope) integration test
python tests/integration/test_dashscope_integration.py

# Tushare data interface tests
python tests/fast_tdx_test.py
python tests/test_tdx_integration.py

# Redis performance tests
python tests/quick_redis_test.py
python tests/test_redis_performance.py
```

### Diagnostic Tools
```bash
# Diagnose Gemini model issues
python tests/diagnose_gemini_25.py

# Check import issues
python tests/debug_imports.py

# Check all available Gemini models
python tests/check_gemini_models.py
```

## Test Environment Requirements

### Required Environment Variables
Before running the tests, make sure the following API keys are configured in your `.env` file:

```env
# Alibaba Bailian / DashScope API (Required)
DASHSCOPE_API_KEY=your_dashscope_key

# Google AI API (Optional, for Gemini tests)
GOOGLE_API_KEY=your_google_key

# Financial Data API (Optional)
FINNHUB_API_KEY=your_finnhub_key

# Reddit API (Optional)
REDDIT_CLIENT_ID=your_reddit_id
REDDIT_CLIENT_SECRET=your_reddit_secret
REDDIT_USER_AGENT=your_user_agent
```

### Python Dependencies
```bash
pip install -r requirements.txt
```

### Interpreting Test Results
- **All tests pass**: Functionality is working properly; all features are ready to use
- **Some tests pass**: Core functionality is working; you may need to check specific configurations
- **Most tests fail**: Issues detected; check your API keys and environment setup

## Contributing Guidelines

When adding new tests, please follow these conventions:

1. **Test file naming**: `test_<feature_name>.py`
2. **Debugging tool naming**: `debug_<issue_description>.py` or `diagnose_<issue_description>.py`
3. **Test function naming**: `test_<specific_feature>()`
4. **Documentation**: Add a clear docstring at the beginning of each function
5. **Categorization**: Place tests in the appropriate category based on functionality

### Test Template

```python
#!/usr/bin/env python3
"""
New feature test
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_new_feature():
    """Test new feature"""
    try:
        print("🧪 Testing new feature")
        print("=" * 50)

        # Test code

        print("✅ Test succeeded")
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 New Feature Test")
    print("=" * 60)

    success = test_new_feature()

    if success:
        print("🎉 All tests passed!")
    else:
        print("❌ Tests failed")

if __name__ == "__main__":
    main()
```

## Recent Updates

- ✅ Added Google Gemini model family tests
- ✅ Added Web interface Google model selection tests
- ✅ Added API integration tests (Google, Reddit)
- ✅ Added Chinese output functionality tests
- ✅ Added memory system and embedding model tests
- ✅ Organized all test files into the `tests` directory
- ✅ Added debugging and diagnostic tools

## Testing Best Practices

1. **Test Isolation**: Each test should run independently
2. **Clear Naming**: Test function names should clearly describe what is being tested
3. **Error Handling**: Tests should gracefully handle various error conditions
4. **Documentation**: Add detailed comments for complex tests
5. **Fast Feedback**: Tests should return results as quickly as possible

## Troubleshooting

### Common Issues
1. **API key issues** - Check your `.env` file configuration
2. **Network connection issues** - Verify network and firewall settings
3. **Dependency package issues** - Ensure all dependencies are installed
4. **Model compatibility** - Check model names and versions

### Debugging Tips
1. Enable verbose output to inspect error messages
2. Run individual test functions to isolate issues
3. Use diagnostic tools to verify configuration
4. Check Web application logs to inspect runtime status

## License

This project is licensed under the Apache 2.0 License.


## Newly Added Test Files

### Integration Tests
- `quick_test.py` - Quick integration test to verify basic functionality
- `test_smart_system.py` - Full smart system test
- `demo_fallback_system.py` - Fallback system demonstration and test

### How to Run
```bash
# Quick test
python tests/quick_test.py

# Smart system test
python tests/test_smart_system.py

# Fallback system demo
python tests/demo_fallback_system.py
```
