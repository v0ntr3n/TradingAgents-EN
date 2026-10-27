"""Simple QMT test script"""
import sys
print("Python version:", sys.version)
print("Python path:", sys.executable)

print("\n Check xtquant library...")
try:
    import xtquant
    print("✅ xtquant Installed")
    print("   version:", getattr(xtquant, '__version__', 'unknown'))
except ImportError as e:
    print("❌ xtquant Not installed")
    print("   Error:", e)
    print("\n Installation method:")
    print("   pip install xtquant")
    sys.exit(1)

print("\n Check QMT adapter...")
try:
    from app.services.data_sources.qmt_adapter import QMTAdapter
    print("✅ QMT Adapter module loaded successfully")
    
    adapter = QMTAdapter()
    print("\n Check MiniQMT connection...")
    is_available = adapter.is_available()
    
    if is_available:
        print("✅ QMT Available")
        print("   - xtquant Library installed")
        print("   - MiniQMT Client is connected")
        
        print("\n Test to get the stock list...")
        df = adapter.get_stock_list()
        if df is not None and not df.empty:
            print(f"✅ successfully obtained {len(df)} only stocks")
            print("\n Top 3 stocks:")
            print(df.head(3))
        else:
            print("❌ No stock list obtained")
    else:
        print("❌ QMT Not available")
        print("\n Please check:")
        print("1. MiniQMT Is the client started?")
        print("2. MiniQMT Have you logged in to your brokerage account?")
        print("3. Whether to run on Windows system")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

