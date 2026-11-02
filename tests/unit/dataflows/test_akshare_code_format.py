"""
Test the stock code format returned by AKShare s two real-time market interfaces
"""
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_akshare_interfaces():
    """Test two real-time market interfaces of AKShare"""
    print("\n" + "="*60)
    print("🧪 Test the stock code format of AKShare real-time market interface")
    print("="*60)
    
    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        print("❌ AKShare Not installed, skip testing")
        return
    
    # test 1: Sina Finance Interface
    print("\n" + "-"*60)
    print("test 1: stock_zh_a_spot() - Sina Finance Interface")
    print("-"*60)
    
    try:
        print("📡 Getting data...")
        df_sina = ak.stock_zh_a_spot()
        
        if df_sina is None or df_sina.empty:
            print("⚠️ Sina interface returns empty data")
        else:
            print(f"✅ Get {len(df_sina)} piece of data")
            print(f"\n📋 List: {list(df_sina.columns)}")
            
            # Find code column
            code_col = None
            for col in ["code", "code", "symbol", "Stock code"]:
                if col in df_sina.columns:
                    code_col = col
                    break
            
            if code_col:
                print(f"\n🔍 code column name: '{code_col}'")
                print(f"\n📊 Top 10 stock symbol samples:")
                
                for i, code in enumerate(df_sina[code_col].head(10), 1):
                    code_str = str(code)
                    code_len = len(code_str)
                    has_prefix = not code_str.isdigit()
                    
                    status = "⚠️" if has_prefix or code_len != 6 else "✅"
                    print(f"   {status} {i:2d}. {code_str:12s} | length: {code_len} | pure numbers: {not has_prefix}")
                
                # Statistical exception code
                abnormal_codes = []
                for code in df_sina[code_col]:
                    code_str = str(code)
                    if len(code_str) != 6 or not code_str.isdigit():
                        abnormal_codes.append(code_str)
                
                if abnormal_codes:
                    print(f"\n   ⚠️ discover {len(abnormal_codes)} exception codes (top 5):")
                    for code in abnormal_codes[:5]:
                        print(f"      - {code}")
                else:
                    print(f"\n   ✅ All codes are in standard 6-digit format")
            else:
                print("❌ Code column not found")
                
    except Exception as e:
        print(f"❌ Sina interface test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # test 2: Oriental Wealth Interface
    print("\n" + "-"*60)
    print("test 2: stock_zh_a_spot_em() - Oriental Wealth Interface")
    print("-"*60)
    
    try:
        print("📡 Getting data...")
        df_em = ak.stock_zh_a_spot_em()
        
        if df_em is None or df_em.empty:
            print("⚠️ Oriental Fortune interface returns empty data")
        else:
            print(f"✅ Get {len(df_em)} piece of data")
            print(f"\n📋 List: {list(df_em.columns)}")
            
            # Find code column
            code_col = None
            for col in ["code", "code", "symbol", "Stock code"]:
                if col in df_em.columns:
                    code_col = col
                    break
            
            if code_col:
                print(f"\n🔍 code column name: '{code_col}'")
                print(f"\n📊 Top 10 stock symbol samples:")
                
                for i, code in enumerate(df_em[code_col].head(10), 1):
                    code_str = str(code)
                    code_len = len(code_str)
                    has_prefix = not code_str.isdigit()
                    
                    status = "⚠️" if has_prefix or code_len != 6 else "✅"
                    print(f"   {status} {i:2d}. {code_str:12s} | length: {code_len} | pure numbers: {not has_prefix}")
                
                # Statistical exception code
                abnormal_codes = []
                for code in df_em[code_col]:
                    code_str = str(code)
                    if len(code_str) != 6 or not code_str.isdigit():
                        abnormal_codes.append(code_str)
                
                if abnormal_codes:
                    print(f"\n   ⚠️ discover {len(abnormal_codes)} exception codes (top 5):")
                    for code in abnormal_codes[:5]:
                        print(f"      - {code}")
                else:
                    print(f"\n   ✅ All codes are in standard 6-digit format")
            else:
                print("❌ Code column not found")
                
    except Exception as e:
        print(f"❌ Oriental Fortune interface test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Comparison summary
    print("\n" + "="*60)
    print("📊 Test summary")
    print("="*60)
    print("✅ Sina interface (stock_zh_a_spot): The ticker may have an exchange prefix (e.g. sz000001)")
    print("✅ Oriental Wealth Interface (stock_zh_a_spot_em): Need to verify code format")
    print("\n💡 Suggestions: Both interfaces should use unified code standardization logic")


if __name__ == "__main__":
    test_akshare_interfaces()

