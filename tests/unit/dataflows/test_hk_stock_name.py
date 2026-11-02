"""
Test whether the real-time price of Hong Kong stocks contains the stock name
"""
import asyncio
from tradingagents.dataflows.providers.hk.hk_stock import get_hk_stock_provider


async def test_hk_stock_name():
    """Test whether the real-time price of Hong Kong stocks contains the stock name"""
    print("=== Test the real-time price of Hong Kong stocks name field ===\n")
    
    provider = get_hk_stock_provider()
    
    # Test stock list
    test_stocks = [
        ("00700", "Tencent Holdings"),
        ("09988", "Alibaba"),
        ("01810", "Xiaomi Group"),
    ]
    
    for code, expected_name in test_stocks:
        print(f"📊 test stocks: {code} (expected name: {expected_name})")
        
        try:
            # Get real-time prices
            quote = provider.get_real_time_price(code)
            
            if quote:
                print(f"✅ get success:")
                print(f"   code: {quote.get('symbol')}")
                print(f"   Name: {quote.get('name', '(no name)')}")
                print(f"   price: {quote.get('price')}")
                print(f"   Currency: {quote.get('currency')}")
                
                # Check if name field is included
                if 'name' in quote:
                    name = quote.get('name')
                    if name and not name.startswith('Hong Kong stocks'):
                        print(f"   ✅ name Fields are correct: {name}")
                    else:
                        print(f"   ⚠️ name Field is default value: {name}")
                else:
                    print(f"   ❌ Missing name field")
            else:
                print(f"❌ Failed to obtain: Return None")
                
        except Exception as e:
            print(f"❌ Abnormal: {e}")
        
        print()


if __name__ == "__main__":
    asyncio.run(test_hk_stock_name())

