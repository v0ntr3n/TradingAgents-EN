#!/usr/bin/env python3
"""
Test module import
"""

try:
    print("🔄 Test basic module import...")
    
    # Test basic modules
    from webapi.core.config import settings
    print("✅ Configuration module imported successfully")
    
    from webapi.models.user import User
    print("✅ User model imported successfully")
    
    from webapi.services.analysis_service import get_analysis_service
    print("✅ Analysis service imported successfully")
    
    print("🎉 All modules are imported successfully!")
    
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
