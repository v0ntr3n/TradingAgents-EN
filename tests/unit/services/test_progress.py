#!/usr/bin/env python3
"""
Test progress display function
"""

import time
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_progress_callback():
    """Test progress callback function"""
    
    def mock_progress_callback(message, step=None, total_steps=None):
        """Simulation progress callback"""
        print(f"[Progress] {message}")
        if step is not None and total_steps is not None:
            percentage = (step / total_steps) * 100
            print(f"  steps: {step}/{total_steps} ({percentage:.1f}%)")
        print()
    
    # Simulation analysis process
    steps = [
        "Start stock analysis...",
        "Check environment variable configuration...",
        "Environment variable verification passed",
        "Configure analysis parameters...",
        "Create necessary directories...",
        "Initialize the analysis engine...",
        "Start analyzing AAPL stock, this may take a few minutes...",
        "Analysis completed, results are being compiled...",
        "✅ Analysis completed successfully!"
    ]
    
    print("🧪 Test progress callback function")
    print("=" * 50)
    
    for i, step in enumerate(steps):
        mock_progress_callback(step, i, len(steps))
        time.sleep(0.5)  # Simulation processing time
    
    print("✅ Progress callback testing completed!")

def test_progress_tracker():
    """Test progress tracker"""
    try:
        from web.utils.progress_tracker import AnalysisProgressTracker
        
        print("🧪 Test progress tracker")
        print("=" * 50)
        
        def mock_callback(message, current_step, total_steps, progress, elapsed_time):
            print(f"[tracker] {message}")
            print(f"  steps: {current_step + 1}/{total_steps}")
            print(f"  Progress: {progress:.1%}")
            print(f"  time: {elapsed_time:.1f}seconds")
            print()
        
        tracker = AnalysisProgressTracker(callback=mock_callback)
        
        # Simulation analysis steps
        steps = [
            "Start stock analysis...",
            "Check environment variable configuration...",
            "Configure analysis parameters...",
            "Create necessary directories...",
            "Initialize the analysis engine...",
            "Get stock data...",
            "Perform technical analysis...",
            "Analysis completed, results are being compiled...",
            "✅ Analysis completed successfully!"
        ]
        
        for step in steps:
            tracker.update(step)
            time.sleep(0.3)
        
        print("✅ Progress Tracker Testing Complete!")
        return True
        
    except Exception as e:
        print(f"❌ Progress tracker test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Progress display function test")
    print("=" * 60)
    
    # Test basic progress callback
    test_progress_callback()
    print()
    
    # Test progress tracker
    test_progress_tracker()
    
    print("\n🎉 All tests completed!")

if __name__ == "__main__":
    main()
