"""
Step 1.3.8 Integration testing - verify assistant_ops tool module
"""
import asyncio
import sys
import os

# Make sure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_1_context_module():
    """Test contextvars user context delivery"""
    print("=== 1. Test context module ===")
    from core.tools.context import set_current_user_id, get_current_user_id, require_current_user_id

    set_current_user_id("test_user_123")
    assert get_current_user_id() == "test_user_123", "context Not set correctly"
    assert require_current_user_id() == "test_user_123", "require Correct value not returned"

    # require throws exception when test is not set
    set_current_user_id(None)
    try:
        require_current_user_id()
        assert False, "should throw RuntimeError"
    except RuntimeError:
        pass

    print("  ✅ context Module is normal")


def test_2_module_imports():
    """Test that all 4 submodules can be imported"""
    print("\n=== 2. Test assistant_ops tool import ===")
    from core.tools.implementations.assistant_ops import analysis_trigger  # noqa
    from core.tools.implementations.assistant_ops import report_query  # noqa
    from core.tools.implementations.assistant_ops import schedule_manager  # noqa
    from core.tools.implementations.assistant_ops import watchlist_manager  # noqa
    print("  ✅ 4 All submodules were imported successfully")


def test_3_tool_registration():
    """12 assistant_ops tools are registered in the test ToolRegistry"""
    print("\n=== 3. Test ToolRegistry registration ===")
    from core.tools import get_tool_registry

    registry = get_tool_registry()
    all_tools = registry.get_all_tools()
    ops_tools = [t for t in all_tools if t.category == "assistant_ops"]
    print(f"  Number of registered assistant_ops tools: {len(ops_tools)}")
    for t in ops_tools:
        desc = t.description[:60] if t.description else "(No description)"
        print(f"    - {t.id} ({t.name}): {desc}...")

    expected_ids = {
        "trigger_stock_analysis",
        "trigger_batch_analysis",
        "get_analysis_status",
        "search_reports",
        "get_report_detail",
        "get_latest_report",
        "list_scheduled_configs",
        "create_scheduled_analysis",
        "toggle_scheduled_config",
        "list_watchlist_groups",
        "add_stock_to_watchlist",
        "remove_stock_from_watchlist",
    }
    actual_ids = {t.id for t in ops_tools}
    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids

    if missing:
        print(f"  ❌ Missing tools: {missing}")
    if extra:
        print(f"  ⚠️ Extra tools: {extra}")

    assert len(missing) == 0, f"Missing tools: {missing}"
    print("  ✅ 12 All assistant_ops tools are registered")


def test_4_fc_conversion():
    """Test OpenAI function calling format conversion"""
    print("\n=== 4. Test FC conversion (OpenAI function calling Format) ===")
    from core.tools import get_tool_registry, tool_metadata_list_to_openai

    registry = get_tool_registry()
    all_tools = registry.get_all_tools()
    ops_tools = [t for t in all_tools if t.category == "assistant_ops"]

    fc_list = tool_metadata_list_to_openai(ops_tools)
    print(f"  Number of functions after conversion: {len(fc_list)}")
    for fc in fc_list:
        fn = fc.get("function", {})
        params = list(fn.get("parameters", {}).get("properties", {}).keys())
        print(f"    - {fn.get('name')}: params={params}")

    assert len(fc_list) == 12, f"Expected 12 FC, Actual {len(fc_list)}"
    print("  ✅ FC Conversion is OK")


def test_5_system_prompt():
    """The test system prompt word contains the operator role"""
    print("\n=== 5. Test system prompt words ===")
    # Directly import internal functions
    from app.services.intelligent_assistant_service import _get_system_prompt

    prompt = _get_system_prompt()
    assert "operator" in prompt or "Operation ability" in prompt or "Trigger analysis" in prompt, "Prompt word missing operator role"
    assert "trigger_stock_analysis" in prompt, "Prompt word is missing tool name reference"
    assert "Stock Watchlist" in prompt, "The prompt word is missing stock watch list management instructions"
    print(f"  Prompt word length: {len(prompt)} character")
    print("  ✅ System prompt words include operator role and tool description")


def test_6_tool_callable():
    """Test harness functions can be called (dry-run level)"""
    print("\n=== 6. Test utility function callability ===")
    from core.tools import get_tool_registry

    registry = get_tool_registry()
    all_tools = registry.get_all_tools()
    ops_tools = [t for t in all_tools if t.category == "assistant_ops"]

    for t in ops_tools:
        func = registry.get_function(t.id)
        assert func is not None, f"Tools {t.id} Unable to get function"
        assert callable(func), f"Tools {t.id} Not callable"
        print(f"    ✅ {t.id} ({t.name}) — callable")

    print("  ✅ All tool functions are available and callable")


if __name__ == "__main__":
    tests = [
        test_1_context_module,
        test_2_module_imports,
        test_3_tool_registration,
        test_4_fc_conversion,
        test_5_system_prompt,
        test_6_tool_callable,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"result: {passed} Pass, {failed} failed")
    sys.exit(1 if failed > 0 else 0)

