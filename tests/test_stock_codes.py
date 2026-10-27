#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to get the stock code and name from Tongdaxin
"""

import pytest
pytest.importorskip("enhanced_stock_list_fetcher")
pytestmark = pytest.mark.integration

from enhanced_stock_list_fetcher import enhanced_fetch_stock_list

def test_get_stock_codes():
    """
    Test to get stock code and name
    """
    print("=" * 60)
    print("📊 Test to get the stock code and name from Tongdaxin")
    print("=" * 60)

    try:
        # Get stock data
        print("\n🔄 Retrieving stock data...")
        stock_data = enhanced_fetch_stock_list(
            type_='stock',  # Get stocks only
            enable_server_failover=True,  # Enable failover
            max_retries=3
        )

        if stock_data is not None and not stock_data.empty:
            print(f"\n✅ Successfully obtained {len(stock_data)} only stocks")

            # Display the symbols and names of the top 20 stocks
            print("\n📋 Top 20 stock codes and names:")
            print("-" * 40)
            print(f"{'Stock code':<10} {'Stock name':<15} {'market'}")
            print("-" * 40)

            for i, (idx, row) in enumerate(stock_data.head(20).iterrows()):
                market = "Shenzhen" if row['sse'] == 'sz' else "Shanghai"
                print(f"{row['code']:<10} {row['name']:<15} {market}")

            # Statistics
            print("\n📊 Statistics:")
            print("-" * 30)
            sz_count = len(stock_data[stock_data['sse'] == 'sz'])
            sh_count = len(stock_data[stock_data['sse'] == 'sh'])
            print(f"Shenzhen market stocks: {sz_count} only")
            print(f"Shanghai market stocks: {sh_count} only")
            print(f"Total number of shares: {len(stock_data)} only")

            # save to file
            output_file = "stock_codes_list.csv"
            stock_codes_df = stock_data[['code', 'name', 'sse']].copy()
            stock_codes_df['market'] = stock_codes_df['sse'].apply(lambda x: 'Shenzhen' if x == 'sz' else 'Shanghai')
            stock_codes_df = stock_codes_df[['code', 'name', 'market']]
            stock_codes_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\n💾 Stock symbol list saved to: {output_file}")

        else:
            print("❌ Unable to obtain stock data")

    except Exception as e:
        print(f"❌ An error occurred while getting stock data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_stock_codes()