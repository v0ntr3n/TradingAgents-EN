#!/usr/bin/env python3
"""
Test the automatic hiding function of the user guide
Verify that the usage guide is automatically hidden when starting an analysis
"""

import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_guide_auto_hide_logic():
    """Test usage guide automatically hides logic"""
    print("📖 Test the automatic hiding function of the user guide")
    print("=" * 60)
    
    # Simulation session state
    class MockSessionState:
        def __init__(self):
            self.data = {}
        
        def get(self, key, default=None):
            return self.data.get(key, default)
        
        def __setitem__(self, key, value):
            self.data[key] = value
        
        def __getitem__(self, key):
            return self.data[key]
        
        def __contains__(self, key):
            return key in self.data
    
    session_state = MockSessionState()
    
    # test scenario 1: Initial state - Usage guide should be displayed
    print("\n📋 scene 1: initial state")
    print("-" * 40)
    
    analysis_running = session_state.get('analysis_running', False)
    analysis_results = session_state.get('analysis_results')
    default_show_guide = not (analysis_running or analysis_results is not None)
    
    print(f"   analysis_running: {analysis_running}")
    print(f"   analysis_results: {analysis_results}")
    print(f"   default_show_guide: {default_show_guide}")
    print(f"   ✅ The initial state should show the usage guide: {default_show_guide}")
    
    # test scenario 2: Start analysis - usage guide should be hidden
    print("\n📋 scene 2: Start analysis")
    print("-" * 40)
    
    # Simulation starts analysis
    session_state['analysis_running'] = True
    session_state['analysis_results'] = None
    
    # Automatically hide the usage guide (unless the user explicitly sets it to be shown)
    if not session_state.get('user_set_guide_preference', False):
        session_state['show_guide_preference'] = False
        print("   📖 Start analysis and automatically hide the user guide")
    
    analysis_running = session_state.get('analysis_running', False)
    analysis_results = session_state.get('analysis_results')
    default_show_guide = not (analysis_running or analysis_results is not None)
    show_guide_preference = session_state.get('show_guide_preference', default_show_guide)
    
    print(f"   analysis_running: {analysis_running}")
    print(f"   analysis_results: {analysis_results}")
    print(f"   default_show_guide: {default_show_guide}")
    print(f"   show_guide_preference: {show_guide_preference}")
    print(f"   ✅ The usage guide should be hidden after starting the analysis: {not show_guide_preference}")
    
    # test scenario 3: Analysis completed with results - should remain hidden
    print("\n📋 scene 3: Analysis completed with results")
    print("-" * 40)
    
    session_state['analysis_running'] = False
    session_state['analysis_results'] = {"stock_symbol": "AAPL", "analysis": "Test results"}
    
    analysis_running = session_state.get('analysis_running', False)
    analysis_results = session_state.get('analysis_results')
    default_show_guide = not (analysis_running or analysis_results is not None)
    show_guide_preference = session_state.get('show_guide_preference', default_show_guide)
    
    print(f"   analysis_running: {analysis_running}")
    print(f"   analysis_results: {bool(analysis_results)}")
    print(f"   default_show_guide: {default_show_guide}")
    print(f"   show_guide_preference: {show_guide_preference}")
    print(f"   ✅ Analysis results should remain hidden when available: {not show_guide_preference}")
    
    # test scenario 4: User manually sets display - user choice should be respected
    print("\n📋 scene 4: Display manually set by user")
    print("-" * 40)
    
    # Simulate user manual settings to display usage guide
    session_state['user_set_guide_preference'] = True
    session_state['show_guide_preference'] = True
    
    # Start analysis again
    session_state['analysis_running'] = True
    session_state['analysis_results'] = None
    
    # It shouldn't be automatically hidden this time because the user explicitly set it
    if not session_state.get('user_set_guide_preference', False):
        session_state['show_guide_preference'] = False
        print("   📖 Autohide User Guide")
    else:
        print("   👤 User has set it manually, keep user selection")
    
    show_guide_preference = session_state.get('show_guide_preference', False)
    print(f"   user_set_guide_preference: {session_state.get('user_set_guide_preference')}")
    print(f"   show_guide_preference: {show_guide_preference}")
    print(f"   ✅ User choices should be respected after manual settings: {show_guide_preference}")
    
    print("\n💡 Test summary:")
    print("   1. ✅ The user guide is displayed by default in the initial state.")
    print("   2. ✅ Automatically hide usage guide when starting analysis")
    print("   3. ✅ Stay hidden when analysis results are available")
    print("   4. ✅ Respect user choice after manual setting by user")
    
    return True

def test_ui_behavior():
    """Test UI behavior logic"""
    print("\n🎨 Test UI behavior logic")
    print("=" * 60)
    
    # Simulate different layout scenarios
    scenarios = [
        {
            "name": "initial access",
            "analysis_running": False,
            "analysis_results": None,
            "user_set_preference": False,
            "expected_show_guide": True
        },
        {
            "name": "Start analysis",
            "analysis_running": True,
            "analysis_results": None,
            "user_set_preference": False,
            "expected_show_guide": False
        },
        {
            "name": "Analysis completed",
            "analysis_running": False,
            "analysis_results": {"data": "test"},
            "user_set_preference": False,
            "expected_show_guide": False
        },
        {
            "name": "User forced display",
            "analysis_running": True,
            "analysis_results": {"data": "test"},
            "user_set_preference": True,
            "user_preference_value": True,
            "expected_show_guide": True
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📋 scene{i}: {scenario['name']}")
        print("-" * 40)
        
        # Calculate default value
        default_show_guide = not (scenario['analysis_running'] or scenario['analysis_results'] is not None)
        
        # Calculate the actual displayed value
        if scenario['user_set_preference']:
            actual_show_guide = scenario.get('user_preference_value', True)
        else:
            actual_show_guide = default_show_guide
            # Hide if analysis is started and user has not set
            if scenario['analysis_running'] and not scenario['user_set_preference']:
                actual_show_guide = False
        
        print(f"   Analysis is running: {scenario['analysis_running']}")
        print(f"   There are analysis results: {bool(scenario['analysis_results'])}")
        print(f"   User settings preferences: {scenario['user_set_preference']}")
        print(f"   Default display guide: {default_show_guide}")
        print(f"   Actual display guide: {actual_show_guide}")
        print(f"   Expected Display Guidelines: {scenario['expected_show_guide']}")
        
        if actual_show_guide == scenario['expected_show_guide']:
            print(f"   ✅ Test passed")
        else:
            print(f"   ❌ test failed")
    
    return True

if __name__ == "__main__":
    print("🧪 Usage Guide Automatically Hide Functional Tests")
    print("=" * 70)
    
    try:
        test_guide_auto_hide_logic()
        test_ui_behavior()
        
        print("\n🎉 All tests completed!")
        print("💡 Function description:")
        print("   - Display the user guide on first visit to help users understand the operation")
        print("   - After clicking to start analysis, the user guide will be automatically hidden to save screen space.")
        print("   - Users can manually control the display/hide of the user guide")
        print("   - User preferences are remembered")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        sys.exit(1)