"""
Test the news filtering feature
Verify the performance of rule-based filters and enhanced filters
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import time
from datetime import datetime

def test_basic_news_filter():
    """Test basic news filter"""
    print("=== Test basic news filter ===")
    
    try:
        from tradingagents.utils.news_filter import create_news_filter
        
        # Create filter
        filter = create_news_filter('600036')
        print(f"✅ Successfully established China Merchants Bank(600036)news filter")
        
        # Simulated news data
        test_news = pd.DataFrame([
            {
                'News headline': 'China Merchants Bank releases third quarter performance report for 2024',
                'News content': 'China Merchants Bank released its third quarter financial report today. Net profit increased by 8% year-on-year, asset quality continued to improve, and the non-performing loan ratio further declined....'
            },
            {
                'News headline': 'Shanghai Stock Exchange 180ETF Index Fund (530280) has its own barbell strategy',
                'News content': 'Data shows that the top ten heavyweight stocks in the Shanghai Stock Exchange 180 Index are Kweichow Moutai, China Merchants Bank 600036, Wuliangye, etc. This ETF fund adopts a passive investment strategy...'
            },
            {
                'News headline': 'Bank ETF Index(512730)Many constituent stocks rose',
                'News content': 'The banking sector performed strongly today. Many constituent stocks such as China Merchants Bank, Industrial and Commercial Bank of China, and China Construction Bank rose. Bank ETF funds benefited significantly....'
            },
            {
                'News headline': 'China Merchants Bank signed a strategic cooperation agreement with a technology company',
                'News content': 'China Merchants Bank announced that it has reached a strategic cooperation with a well-known technology company, and will cooperate in depth in digital transformation, financial technology innovation and other aspects to promote the upgrading of banking business....'
            },
            {
                'News headline': 'Untitled',
                'News content': 'The index fund tracks the Shanghai 180 Index, which includes 180 large-cap blue-chip stocks. Heavyweight stocks include financial stocks such as China Merchants Bank....'
            }
        ])
        
        print(f"📊 Test number of news: {len(test_news)}Article")
        
        # Perform filtering
        start_time = time.time()
        filtered_news = filter.filter_news(test_news, min_score=30)
        filter_time = time.time() - start_time
        
        print(f"⏱️ Filtration takes time: {filter_time:.3f}seconds")
        print(f"📈 Filter results: {len(test_news)}Article -> {len(filtered_news)}Article")
        
        if not filtered_news.empty:
            print("\n🎯 filtered news:")
            for idx, (_, row) in enumerate(filtered_news.iterrows(), 1):
                print(f"{idx}. {row['News headline']} (Rating: {row['relevance_score']:.1f})")
        
        # Get filter statistics
        stats = filter.get_filter_statistics(test_news, filtered_news)
        print(f"\n📊 Filter statistics:")
        print(f"  - Filtration rate: {stats['filter_rate']:.1f}%")
        print(f"  - average rating: {stats['avg_score']:.1f}")
        print(f"  - highest rating: {stats['max_score']:.1f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic filter test failed: {e}")
        return False


def test_enhanced_news_filter():
    """Test the enhanced news filter"""
    print("\n=== Test the enhanced news filter ===")
    
    try:
        from tradingagents.utils.enhanced_news_filter import create_enhanced_news_filter
        
        # Create enhanced filters (without using external model dependencies)
        enhanced_filter = create_enhanced_news_filter(
            '600036', 
            use_semantic=False,  # Semantic model is not used for the time being
            use_local_model=False  # Do not use local models yet
        )
        print(f"✅ Successfully created enhanced news filter")
        
        # Use the same test data
        test_news = pd.DataFrame([
            {
                'News headline': 'China Merchants Bank releases third quarter performance report for 2024',
                'News content': 'China Merchants Bank released its third quarter financial report today. Net profit increased by 8% year-on-year, asset quality continued to improve, and the non-performing loan ratio further declined....'
            },
            {
                'News headline': 'Shanghai Stock Exchange 180ETF Index Fund (530280) has its own barbell strategy',
                'News content': 'Data shows that the top ten heavyweight stocks in the Shanghai Stock Exchange 180 Index are Kweichow Moutai, China Merchants Bank 600036, Wuliangye, etc. This ETF fund adopts a passive investment strategy...'
            },
            {
                'News headline': 'China Merchants Bank shareholders meeting approved dividend plan',
                'News content': 'China Merchants Bank s shareholders meeting reviewed and approved the 2024 profit distribution plan, distributing a cash dividend of 12 yuan for every 10 shares, with a dividend rate of 30%...'
            },
            {
                'News headline': 'Innovative development of China Merchants Bank s credit card business',
                'News content': 'China Merchants Bank Credit Card Center has launched a number of innovative products, including digital credit cards, consumer installments, etc., significantly improving user experience...'
            }
        ])
        
        print(f"📊 Test number of news: {len(test_news)}Article")
        
        # Perform enhanced filtering
        start_time = time.time()
        enhanced_filtered = enhanced_filter.filter_news_enhanced(test_news, min_score=40)
        filter_time = time.time() - start_time
        
        print(f"⏱️ Enhanced filtering time: {filter_time:.3f}seconds")
        print(f"📈 Enhance filter results: {len(test_news)}Article -> {len(enhanced_filtered)}Article")
        
        if not enhanced_filtered.empty:
            print("\n🎯 Enhanced filtered news:")
            for idx, (_, row) in enumerate(enhanced_filtered.iterrows(), 1):
                print(f"{idx}. {row['News headline']}")
                print(f"   Overall rating: {row['final_score']:.1f} (rules:{row['rule_score']:.1f}, Semantics:{row['semantic_score']:.1f}, Classification:{row['classification_score']:.1f})")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced filter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_real_news_filtering():
    """Test filtering on real news data"""
    print("\n=== Test filtering on real news data ===")
    
    try:
        from tradingagents.dataflows.akshare_utils import get_stock_news_em
        from tradingagents.utils.news_filter import create_news_filter
        
        print("📡 Obtaining real news data of China Merchants Bank...")
        
        # Get real news data
        start_time = time.time()
        real_news = get_stock_news_em('600036')
        fetch_time = time.time() - start_time
        
        if real_news.empty:
            print("❌ No real news data was obtained")
            return False
        
        print(f"✅ Get real news successfully: {len(real_news)}strips, time consuming: {fetch_time:.2f}seconds")
        
        # Show the first 3 news headlines
        print("\n📰 Original news headline example:")
        for idx, (_, row) in enumerate(real_news.head(3).iterrows(), 1):
            title = row.get('News headline', 'Untitled')
            print(f"{idx}. {title}")
        
        # Create filters and filter
        filter = create_news_filter('600036')
        
        start_time = time.time()
        filtered_real_news = filter.filter_news(real_news, min_score=30)
        filter_time = time.time() - start_time
        
        print(f"\n🔍 Filter results:")
        print(f"  - original news: {len(real_news)}Article")
        print(f"  - filtered news: {len(filtered_real_news)}Article")
        print(f"  - Filtration rate: {(len(real_news) - len(filtered_real_news)) / len(real_news) * 100:.1f}%")
        print(f"  - Filtration takes time: {filter_time:.3f}seconds")
        
        if not filtered_real_news.empty:
            avg_score = filtered_real_news['relevance_score'].mean()
            max_score = filtered_real_news['relevance_score'].max()
            print(f"  - average rating: {avg_score:.1f}")
            print(f"  - highest rating: {max_score:.1f}")
            
            print("\n🎯 Filtered high-quality news headlines:")
            for idx, (_, row) in enumerate(filtered_real_news.head(5).iterrows(), 1):
                title = row.get('News headline', 'Untitled')
                score = row.get('relevance_score', 0)
                print(f"{idx}. {title} (Rating: {score:.1f})")
        
        return True
        
    except Exception as e:
        print(f"❌ Real news filter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_news_filter_integration():
    """Test the news filtering integration"""
    print("\n=== Test the news filtering integration ===")
    
    try:
        from tradingagents.utils.news_filter_integration import apply_news_filtering_patches
        
        print("🔧 Applying news filter patch...")
        enhanced_function = apply_news_filtering_patches()
        
        print("✅ News filtering patch applied successfully")
        
        # Test enhanced functions
        print("🧪 Test the enhanced live news function...")
        
        test_result = enhanced_function(
            ticker="600036",
            curr_date=datetime.now().strftime("%Y-%m-%d"),
            enable_filter=True,
            min_score=30
        )
        
        print(f"📊 Enhanced version function returns result length: {len(test_result)} character")
        
        if "Filter news reports" in test_result:
            print("✅ It is detected that the filtering function has taken effect")
        else:
            print("ℹ️ Original news report used")
        
        return True
        
    except Exception as e:
        print(f"❌ News filtering integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("🚀 Start testing the news filtering function")
    print("=" * 50)
    
    test_results = []
    
    # 1. Test basic filters
    test_results.append(("Basic news filter", test_basic_news_filter()))
    
    # 2. Test enhanced filters
    test_results.append(("Enhanced news filter", test_enhanced_news_filter()))
    
    # 3. Test real news filtering
    test_results.append(("Real news data filtering", test_real_news_filtering()))
    
    # 4. Test integration functionality
    test_results.append(("News filtering integration", test_news_filter_integration()))
    
    # Output test summary
    print("\n" + "=" * 50)
    print("📋 Summary of test results:")
    
    passed = 0
    for test_name, result in test_results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"  - {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall results: {passed}/{len(test_results)} tests passed")
    
    if passed == len(test_results):
        print("🎉 All tests passed! News filtering works fine")
    else:
        print("⚠️ Some tests failed, please check related functions")


if __name__ == "__main__":
    main()