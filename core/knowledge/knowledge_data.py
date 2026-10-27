"""
Financial knowledge base initial data

contains ~55 Structured knowledge documents are divided into 4 categories:
- concept: Financial concepts (core knowledge of A-share market)~16 Article
- tool_guide: Tool Usage Guide (Best Practices for System Tools)~14 Article
- methodology: Analysis methodology (standard analysis process)~7 Article
- pattern: Problem Pattern Mapping (FAQ → tool mapping)~15 Article
"""

from typing import List, Dict, Any

# ============================================================
# Financial concepts (concept) — ~16 Article
# ============================================================

CONCEPT_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "id": "concept_sector_system",
        "category": "concept",
        "title": "A stock sector system",
        "content": (
            "A There are three sector types of stocks (flush classification):"
            "Industry sector(N)Contains industry classifications and theme concept sections, such as liquor, semiconductors, photovoltaic equipment, Huawei concepts, Xiaomi cars, ChatGPT concepts, etc."
            "A stock can belong to multiple industries/concepts at the same time.400+section;"
            "Concept section(S)It is a statistical section, such as yesterday s daily limit, sub-new stocks, QFII heavy positions and other quantitative screening sections, a total of 126;"
            "Geographical sector(R)Classified by the place of registration of listed companies, such as Zhejiang plate and Shenzhen plate, there are 33 in total."
            "Important: When querying concept stocks (such as Xiaomi Auto, Huawei Concept), you should search the industry sector(N), Not a concept section(S). "
            "The source of sector data is Flush/Tushare."
        ),
        "tags": ["plate", "Industry", "concept", "Region", "Flush"],
        "priority": 1,
    },
    {
        "id": "concept_stock",
        "category": "concept",
        "title": "concept stocks",
        "content": (
            "Concept stocks refer to industry sectors that belong to Flush(N Type)The constituent stocks of the theme concept classification."
            "For example'Photovoltaic concept stocks'It s a straight flush'photovoltaic concept(885531.TI)'All A-share companies under the sector;"
            "'Xiaomi Auto Concept Stock'It s a straight flush'Xiaomi car(886064.TI)'A-share listed companies supporting Xiaomi Motors under the sector."
            "To query concept stocks, you need to use the sector tool to search for the corresponding sector name (type N), and then obtain the list of constituent stocks."
            "Note: The name of the concept section may not be exactly the same as the user description, and you need to search for matches with keywords."
            "Examples of common concept sections: Xiaomi concept, Xiaomi car, Huawei concept, Tesla concept, artificial intelligence, AIGC concept, robot concept, chip concept, new energy vehicle, liquor concept, etc."
        ),
        "tags": ["concept stocks", "plate", "Constituent stocks"],
        "priority": 1,
    },
    {
        "id": "concept_leading_stock",
        "category": "concept",
        "title": "leading stocks",
        "content": (
            "Leading stocks are representative stocks with the largest market value or leading gains in the sector, and usually have a strong driving effect."
            "How to identify leading stocks: Check the list of sector constituent stocks, and choose the top ones in order of total market capitalization or circulating market capitalization;"
            "Or sorted by recent gains, the short-term leader is the leader in gains."
            "Leading stocks change frequently, and it is necessary to query sector constituent stock data in real time."
        ),
        "tags": ["leading stocks", "plate", "Market value"],
        "priority": 2,
    },
    {
        "id": "concept_north_flow",
        "category": "concept",
        "title": "Northbound funds",
        "content": (
            "Northbound funds refer to overseas funds flowing into A-shares from Hong Kong through the Shanghai-Shenzhen-Hong Kong Stock Connect."
            "Shanghai Stock Connect buys Shanghai market stocks, and Shenzhen Stock Connect buys Shenzhen market stocks."
            "Northbound funds are often referred to as'smart money', Its inflows and outflows are considered important market signals."
            "An increase in net buying of northbound funds is usually regarded as a bullish signal, and an increase in net selling is regarded as a bearish signal."
            "You can pay attention to the daily net inflow amount of northbound funds, cumulative net inflows, and changes in heavily held stocks."
        ),
        "tags": ["Northbound funds", "foreign capital", "Shanghai-Shenzhen-Hong Kong Stock Connect", "smart money"],
        "priority": 2,
    },
    {
        "id": "concept_margin_trading",
        "category": "concept",
        "title": "Financing (margin and securities lending)",
        "content": (
            "Financing refers to margin trading and securities lending transactions. Financing means investors borrow money to buy stocks (long view), while securities lending means borrowing money to sell stocks (short view)."
            "An increase in the financing balance indicates bullish leverage, while a decrease indicates deleveraging."
            "The two financial data reflect market risk preferences and leveraged capital trends, and are important market sentiment indicators."
            "Note: The absolute value of the balance of financing and financing has limited meaning, focusing on marginal changes (increase and decrease trends)."
        ),
        "tags": ["Integration of both", "Margin margin trading", "Leverage", "market sentiment"],
        "priority": 3,
    },
    {
        "id": "concept_limit_up_down",
        "category": "concept",
        "title": "price limit system",
        "content": (
            "A The price limit for the main stock market is 10% (5% for ST shares), 20% for the Science and Technology Innovation Board and GEM, and 30% for the Beijing Stock Exchange."
            "The upper limit indicates strong buying and the stock price has reached its maximum increase of the day, and the lower limit indicates that strong selling has reached its maximum decrease."
            "The ratio of the number of companies at the daily limit to the number of companies at the low limit is an important indicator of market sentiment: the number of companies at the daily limit is far more than the number of companies at the low limit, indicating a bullish market sentiment."
            "Continuous daily limit is called'Even board', The height of the connecting board reflects the heat of market speculation."
        ),
        "tags": ["price limit", "daily limit", "Limit down", "market sentiment"],
        "priority": 3,
    },
    {
        "id": "concept_a_share_lot_size",
        "category": "concept",
        "title": "A Whole lot trading and odd lot rules",
        "content": (
            "A Ordinary stock transactions are usually based on 100 shares per lot, and normal purchases and sales should be declared in multiples of 100 shares."
            "Therefore, when deriving execution recommendations based on position ratios, we cannot directly give the quantities that cannot be completed in ordinary transactions such as 30 shares, 60 shares, and 80 shares."
            "Only odd shares formed due to historical reasons such as rights issue, transfer, split, etc., may be sold with less than 100 shares, but this is not the default premise of regular trading advice."
            "If you need to convert the proportional rule into the number of shares, you should first round the current position to the nearest multiple of 100 shares, and then explain how to handle the remaining fractions."
        ),
        "tags": ["A shares", "Handle", "100 shares", "Odd shares", "trading rules"],
        "priority": 1,
    },
    {
        "id": "concept_pe_pb_roe",
        "category": "concept",
        "title": "Core Valuation Metrics PE/PB/ROE",
        "content": (
            "PE(P/E ratio)=Stock price/earnings per share reflects the price investors are willing to pay for each unit of earnings. The lower the PE, the cheaper the valuation (but it must be combined with the industry)."
            "PB(price to book ratio)=Stock price/net assets per share, suitable for valuation of heavy asset industries.PB<1 called'Break the net'. "
            "ROE(ROE)=Net profit/net assets, a measure of a company s profitability,ROE>15%Generally considered better."
            "The reasonable PE/PB ranges of different industries vary greatly: the PE of technology stocks is usually higher than that of bank stocks."
        ),
        "tags": ["PE", "PB", "ROE", "Valuation", "Fundamentals"],
        "priority": 2,
    },
    {
        "id": "concept_technical_indicators",
        "category": "concept",
        "title": "Commonly used technical indicators",
        "content": (
            "MACD(Exponential Smoothing Convergence and Divergence Moving Average): To determine the direction and strength of the trend, golden crosses are bullish and dead crosses are bearish."
            "RSI(relative strength indicator): Measures overbought and oversold,RSI>70 overbought,RSI<30 Oversold."
            "KDJ(Stochastic): To judge overbought, oversold and short-term turning points, the K line crossing the D line is a golden cross."
            "BOLL(Bollinger Bands): Determine the price fluctuation range and support pressure level. If the price hits the upper track, it may pull back, and if it hits the lower track, it may rebound."
            "Technical indicators need to be used in combination, and a single indicator can easily lead to misjudgment."
        ),
        "tags": ["MACD", "RSI", "KDJ", "BOLL", "technical analysis"],
        "priority": 2,
    },
    {
        "id": "concept_fund_flow",
        "category": "concept",
        "title": "Fund flow",
        "content": (
            "Fund flow direction refers to the direction of inflow and outflow of funds in the market, and is an important basis for judging market hot spots and sentiment."
            "The inflow of main funds means that big funds are optimistic, and the outflow means that big funds are leaving the market."
            "The fund flow of sectors can identify the current hot market sectors; the fund flow of individual stocks can determine the main trends."
            "Northbound capital flows and changes in the balance of financing and financing are also important funding indicators."
        ),
        "tags": ["Fund flow", "main funds", "Hotspot"],
        "priority": 3,
    },
    {
        "id": "concept_market_breadth",
        "category": "concept",
        "title": "market breadth",
        "content": (
            "Market breadth refers to the ratio of advancing to declining stocks and is a measure of the overall health of the market."
            "When the index rises but the number of advancing stocks decreases (the market width narrows), it may indicate a lack of upward momentum."
            "The ratio of the number of traders rising and falling, the ratio of the number of traders rising and falling, and the distribution of volume and energy are all indicators of market width."
            "Healthy gains should be accompanied by broad individual stock participation (widening market breadth)."
        ),
        "tags": ["market breadth", "rise/fall ratio", "Market"],
        "priority": 3,
    },
    {
        "id": "concept_industry_chain",
        "category": "concept",
        "title": "Industrial chain and supply chain",
        "content": (
            "The industrial chain refers to the complete chain of an industry from raw materials to end products."
            "For example, the new energy vehicle industry chain includes: upstream (lithium mine, cobalt mine)→ Midstream (battery, motor)→ Downstream (complete vehicle, charging pile)."
            "Industry chain analysis helps to understand the upstream and downstream relationships and profit distribution of the industry."
            "In A-shares, companies related to the industry chain are usually classified into the same concept section, and industry chain companies can be obtained by searching the concept section."
        ),
        "tags": ["Industrial chain", "supply chain", "Upstream and downstream"],
        "priority": 3,
    },
    {
        "id": "concept_sector_rotation",
        "category": "concept",
        "title": "sector rotation",
        "content": (
            "Sector rotation refers to the phenomenon of market hot spots switching between different sectors."
            "Typical rotation pattern: looking at financial and real estate during the economic recovery period → Looking at consumer technology during the expansion period → Look at cyclical resources during overheating period → Look at defensive sectors during recession."
            "Observing sector rotation can be judged by the ranking of capital flow and the ranking of sector gains and losses."
            "Short-term rotation (intraday/weekly level) is more driven by funds and sentiment, while long-term rotation is related to the economic cycle."
        ),
        "tags": ["sector rotation", "Hotspot", "business cycle"],
        "priority": 3,
    },
    {
        "id": "concept_financial_reports",
        "category": "concept",
        "title": "A financial report disclosure",
        "content": (
            "A Listed companies are required to regularly disclose financial reports: annual report(1-4 end of month), First quarter report(4 before the end of the month), semi-annual report(8 before the end of the month), third quarter report(10 before the end of the month). "
            "The financial report includes the income statement (revenue, net profit), balance sheet (assets, liabilities), and cash flow statement (operating/investing/financing cash flow)."
            "The earnings season is usually accompanied by large stock price fluctuations. Performance that exceeds expectations may lead to a rise, while performance that falls short of expectations may lead to a fall."
            "Analyzing financial reports focuses on: revenue growth rate, net profit growth rate, changes in gross profit margin, and cash flow quality."
        ),
        "tags": ["financial report", "annual report", "quarterly report", "financial analysis"],
        "priority": 2,
    },
    {
        "id": "concept_index",
        "category": "concept",
        "title": "A major stock indexes",
        "content": (
            "Shanghai Composite Index(000001): The weighted index of all A-shares on the Shanghai Stock Exchange reflects the overall trend of the Shanghai stock market."
            "Shenzhen Component Index(399001): Shenzhen Stock Exchange constituent index."
            "GEM Index(399006): The GEM representative index is biased towards growth style."
            "Shanghai and Shenzhen 300(000300): The 300 largest stocks on the Shanghai and Shenzhen stock exchanges represent the blue chips of the market."
            "CSI 500(000905): Mid-cap stocks represented. CSI 1000(000852): Small cap stocks represented."
            "Science and Technology 50(000688): Representative of the Science and Technology Innovation Board."
        ),
        "tags": ["Index", "Shanghai Stock Exchange", "Shenzhen Certificate", "Shanghai and Shenzhen 300", "GEM"],
        "priority": 2,
    },
    {
        "id": "concept_financial_statements",
        "category": "concept",
        "title": "Three major financial statements",
        "content": (
            "The three core financial statements of listed companies: income statement, balance sheet, and cash flow statement."
            "The income statement reflects the company s operating results over a period of time. The core indicators are: operating income, net profit, gross profit margin, net profit rate, and expense ratio."
            "The balance sheet reflects the company s financial status at a certain point in time. The core indicators are: total assets, total liabilities, asset-liability ratio, current ratio, and quick ratio."
            "The cash flow statement reflects the source and destination of the company s cash and is divided into three parts: cash flow from operating activities (core hematopoietic capacity),"
            "Cash flows from investing activities (capital expenditures and investments), cash flows from financing activities (financing and dividends)."
            "Analyzing financial statements requires the linkage of three tables: the income statement looks at profitability, the balance sheet looks at financial security, and the cash flow statement verifies the quality of profits."
            "free cash flow = operating cash flow + Investment cash flow is a key indicator of a company s true hematopoietic capabilities."
            "The system provides 5 special financial tools: get_income_analysis (income statement), get_balance_sheet_analysis (balance sheet),"
            "get_cashflow_analysis (Cash flow), get_dividend_data (dividend), get_main_business (main business composition),"
            "A certain type of financial data can be accurately obtained on demand."
        ),
        "tags": ["financial statements", "income statement", "balance sheet", "cash flow statement", "financial analysis"],
        "priority": 1,
    },
    {
        "id": "concept_dividend_strategy",
        "category": "concept",
        "title": "Dividend investment strategy and entry timing",
        "content": (
            "Core knowledge of high dividend stock investment strategies:"
            "1. Key time point for dividend distribution: annual report release (March-April)→ Announcement of dividend plan → Passed by shareholders meeting → Equity registration date → ex-rights ex-dividend date → Dividend payment date."
            "2. Analysis of entry timing:"
            "1) The best deployment period: after the annual report preview/express is released (January-March), confirm performance and dividend capabilities. At this time, the market has not yet fully reflected dividend expectations, so deploy 2-3 months in advance;"
            "2) 1-2 weeks before the announcement of the dividend plan: retail investors and short-term funds begin to grab power and push up the stock price, while institutional investors usually make arrangements earlier;"
            "3) Around ex-rights and ex-dividend dates: The stock price will automatically drop on the ex-dividend date (minus the amount of dividends). In the short term, it seems'Loss', But in the long run, high-quality, high-dividend stocks will'Fill in the right' (The stock price rebounds to pre-ex-dividend levels);"
            "4) It is not recommended to chase high prices and buy a few days before the ex-rights and ex-dividend dates. It is easy to buy at'Power grab market'of high points."
            "3. Right to fill in and paste:"
            "Fill-in right means that the stock price gradually returns to the pre-ex-dividend level after ex-dividend, indicating that the company s fundamentals are good and the market recognizes it;"
            "Discounting means that the stock price continues to fall after ex-dividend, indicating that the market is not optimistic about the company s prospects. High-quality, high-dividend stocks are easier to fill in."
            "4. Dividend tax rules (A shares):"
            "If you hold shares for more than 1 year: you are exempt from dividend tax; if you hold shares for 1 month to 1 year: you are taxed at 10%; if you hold shares for less than 1 month: you are taxed at 20%."
            "Therefore, the tax cost of holding high-dividend stocks for a long time is the lowest, and short-term entry and exit are not cost-effective."
            "5. Stock selection criteria:"
            "1) Stable dividends for more than 3 consecutive years;2) dividend yield > 3% (Excellent > 5%) ; "
            "3) A dividend ratio of 30%-70% is appropriate (too high may be unsustainable);4) Sufficient operating cash flow (dividends come from real profits);"
            "5) The industry you work in is mature and stable (such as banking, public utilities, consumption, etc.)."
            "6. Suggestions for prudent investors: Screen for stocks with continuous high dividends during the annual reporting season (March-April), and gradually build positions after confirming the dividend plan."
            "Hold for more than 1 year to enjoy tax-free dividends, pass'Dividends reinvested'Achieve compound interest growth."
        ),
        "tags": ["dividend", "dividends", "investment strategy", "Entry time", "ex-rights and ex-dividends", "Fill in the right", "High dividends"],
        "priority": 1,
    },
]


# ============================================================
# Tool usage guide (tool_guide) — ~14 Article
# ============================================================

TOOL_GUIDE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "id": "tool_analyze_sector_by_name",
        "category": "tool_guide",
        "title": "analyze_sector_by_name Tool Guide",
        "content": (
            "analyze_sector_by_name It is a one-stop comprehensive sector analysis tool, just pass in sector_name (sector name keyword)."
            "Applicable scenarios:'XX Sector prospects', 'XX Concept stock analysis', 'XX Industry investment opportunities', 'XX Sector leader'. "
            "This tool will automatically search for matching sectors and obtain comprehensive information such as sector trends, constituent stocks, and capital flows."
            "The parameter sector_name should be passed in the sector/industry/concept keyword mentioned by the user, and there is no need to pass in the stock code."
            "If the user asks'XX What are concept stocks?', You can also use this tool, which returns a list of constituent stocks."
        ),
        "tags": ["plate", "Tools", "analyze_sector_by_name"],
        "priority": 1,
    },
    {
        "id": "tool_get_sector_constituents",
        "category": "tool_guide",
        "title": "get_sector_constituents Tool Guide",
        "content": (
            "get_sector_constituents Get the list of sector constituent stocks, and pass in the sector name keyword as the parameter sector_name."
            "Applicable scenarios:'XX What are concept stocks?', 'XX What stocks are in the sector?', 'XX Who is the sector leader?'. "
            "The returned results include information such as component stock code, name, market value, etc. You can sort by market value to find the leader."
            "Note: If no exact matching section is found, the closest matching result will be returned."
        ),
        "tags": ["plate", "Constituent stocks", "Tools", "get_sector_constituents"],
        "priority": 1,
    },
    {
        "id": "tool_search_sector",
        "category": "tool_guide",
        "title": "search_sector Tool Guide",
        "content": (
            "search_sector Search the matching sector list based on keywords, and pass in the search keywords as the parameter sector_name."
            "Applicable scenarios: Search first when you are not sure about the specific section name, or view all sections related to a certain keyword."
            "Returns a list of matching sections (including section code, name, type), based on which specific sections can be selected for further analysis."
            "The more precise the search keyword matches, the better, such as searching'photovoltaic'Than'new energy'More precise."
        ),
        "tags": ["plate", "Search", "Tools", "search_sector"],
        "priority": 2,
    },
    {
        "id": "tool_stock_fundamentals",
        "category": "tool_guide",
        "title": "get_stock_fundamentals_unified Tool Guide",
        "content": (
            "get_stock_fundamentals_unified Get the fundamental data of individual stocks, and pass in the 6-digit stock code as parameter ticker."
            "The returned data includes: valuation indicators such as PE/PB/ROE, financial data such as revenue/net profit, industry comparisons, etc."
            "Applicable scenarios: Analyze whether the valuation of a certain stock is reasonable and whether the financial situation is healthy."
            "Note: The ticker must be a 6-digit code (such as 601012), and the stock name cannot be passed in."
        ),
        "tags": ["Fundamentals", "individual stocks", "Tools", "get_stock_fundamentals_unified"],
        "priority": 1,
    },
    {
        "id": "tool_technical_indicators",
        "category": "tool_guide",
        "title": "get_technical_indicators Tool Guide",
        "content": (
            "get_technical_indicators Get the technical indicators of individual stocks, and pass in the stock code as parameter ticker."
            "Returns data of commonly used technical indicators such as MACD, RSI, KDJ, BOLL, etc."
            "Applicable scenarios: Determine the technical trend, overbought and oversold status, and support and pressure levels of a certain stock."
            "Advice and market data(get_stock_market_data_unified)Use it together to comprehensively analyze the technical aspects."
        ),
        "tags": ["Technical indicators", "individual stocks", "Tools", "get_technical_indicators"],
        "priority": 2,
    },
    {
        "id": "tool_china_market_overview",
        "category": "tool_guide",
        "title": "get_china_market_overview Tool Guide",
        "content": (
            "get_china_market_overview Get an overall overview of the A-share market without entering the stock code."
            "Returns market macro data such as the rise and fall of major indexes, the number of gainers and losers, and transaction volume."
            "Applicable scenarios: User questions'How is the market?', 'Today s market conditions', 'overall market environment'. "
            "This tool provides a complete snapshot of the market and is suitable as a starting point for analysis."
        ),
        "tags": ["Market", "market", "Tools", "get_china_market_overview"],
        "priority": 1,
    },
    {
        "id": "tool_north_flow",
        "category": "tool_guide",
        "title": "get_north_flow Tool Guide",
        "content": (
            "get_north_flow Obtain data on the inflow and outflow of northbound funds (Shanghai-Shenzhen-Hong Kong Stock Connect)."
            "Returns the data on the daily net inflow/outflow of northbound funds, Shanghai-Hong Kong Stock Connect and Shenzhen-Hong Kong Stock Connect."
            "Applicable scenarios: User questions'Northbound funds', 'Foreign investment trends', 'Shanghai-Shenzhen-Hong Kong Stock Connect Funds'. "
            "Large northbound inflows are generally seen as a positive sign."
        ),
        "tags": ["Northbound funds", "foreign capital", "Tools", "get_north_flow"],
        "priority": 2,
    },
    {
        "id": "tool_fund_flow_data",
        "category": "tool_guide",
        "title": "get_fund_flow_data Tool Guide",
        "content": (
            "get_fund_flow_data Obtain fund flow data for sectors or individual stocks."
            "Applicable scenarios:'Ranking of sector capital flows', 'Main capital inflow and outflow', 'Market hot sectors'. "
            "Through the flow of funds, you can discover the sectors and individual stocks that are attracting the most attention in the current market."
            "Sectors/stocks with the highest net inflows of major funds are usually hot spots in the near future."
        ),
        "tags": ["Fund flow", "main force", "Tools", "get_fund_flow_data"],
        "priority": 2,
    },
    {
        "id": "tool_peer_comparison",
        "category": "tool_guide",
        "title": "get_peer_comparison Tool Guide",
        "content": (
            "get_peer_comparison To conduct comparative analysis in the same industry, the parameter ticker is passed in the stock code."
            "Returns the valuation comparison (PE/PB), profit comparison (ROE/gross profit margin), and growth comparison (revenue/profit growth rate) of companies in the same industry."
            "Applicable scenarios:'XX Which one is better with YY?', 'XX Rank in the industry', 'Comparison with the same industry'. "
            "Comparative analysis helps determine the relative position of individual stocks in the industry."
        ),
        "tags": ["Contrast", "Peers", "Tools", "get_peer_comparison"],
        "priority": 2,
    },
    {
        "id": "tool_get_income_analysis",
        "category": "tool_guide",
        "title": "get_income_analysis Income Statement Analysis Tools Guide",
        "content": (
            "get_income_analysis To analyze the core indicators of the stock s income statement, the parameter ticker is passed in the 6-digit stock code (such as 600519)."
            "The returned data includes: operating income, net profit, gross profit margin, net profit rate, expense ratio (sales/management/R&D/financial expense ratio), etc.,"
            "Supports multi-period trend display for the last N quarters. The parameter periods controls the number of analysis periods, the default is 8 quarters."
            "Applicable scenarios:'How is Moutai s revenue and profit growth?', 'Profit trends in recent years', 'What is the gross profit margin and net profit margin?', 'Profitability analysis'. "
            "Differences from get_stock_fundamentals_unified: This tool focuses on the details of the income statement and provides more detailed analysis of multi-period trends and expense structures."
            "The data source is Tushare income statement(income)and financial indicators(fina_indicator), Read from MongoDB cache first."
        ),
        "tags": ["income statement", "financial analysis", "Tools", "get_income_analysis", "Revenue", "net profit", "Gross profit margin"],
        "priority": 1,
    },
    {
        "id": "tool_get_balance_sheet_analysis",
        "category": "tool_guide",
        "title": "get_balance_sheet_analysis A Guide to Balance Sheet Analysis Tools",
        "content": (
            "get_balance_sheet_analysis To analyze the balance sheet of a stock, the parameter ticker is passed in the 6-digit stock code."
            "The returned data includes: total assets, total liabilities, net assets, asset-liability ratio, current ratio, quick ratio,"
            "Asset structure (proportion of monetary funds, accounts receivable, inventory, fixed assets, etc.). Supports multi-period trend display."
            "Applicable scenarios:'Is the asset-liability ratio high?', 'Are cash reserves sufficient?', 'Is your finances healthy?', 'Solvency Analysis'. "
            "The parameter periods controls the number of analysis periods, the default is 8 quarters."
            "Focus on: Whether the asset-liability ratio exceeds the industry average and whether the current ratio > 1, Whether monetary funds can cover short-term liabilities."
        ),
        "tags": ["balance sheet", "financial analysis", "Tools", "get_balance_sheet_analysis", "Debt ratio", "Solvency"],
        "priority": 1,
    },
    {
        "id": "tool_get_cashflow_analysis",
        "category": "tool_guide",
        "title": "get_cashflow_analysis A Guide to Cash Flow Statement Analysis Tools",
        "content": (
            "get_cashflow_analysis To analyze the cash flow statement of a stock, the parameter ticker is passed in the 6-digit stock code."
            "Returned data includes: cash flow from operating activities(OCF), cash flow from investing activities(ICF), cash flow from financing activities(FCF), "
            "free cash flow(OCF+ICF), Cash flow quality (operating cash flow/net profit ratio). Supports multi-period trend display."
            "Applicable scenarios:'Is the operating cash flow good?', 'Is Free Cash Flow Generous?', 'What is the quality of cash flow?', 'The company s hematopoietic ability'. "
            "The parameter periods controls the number of analysis periods, the default is 8 quarters."
            "Characteristics of high-quality companies: continuous positive operating cash flow, ample free cash flow, OCF/net profit > 1 (high quality of earnings)."
        ),
        "tags": ["cash flow", "financial analysis", "Tools", "get_cashflow_analysis", "free cash flow", "operating cash flow"],
        "priority": 1,
    },
    {
        "id": "tool_get_dividend_data",
        "category": "tool_guide",
        "title": "get_dividend_data Dividend bonus data tool guide",
        "content": (
            "get_dividend_data Get the historical dividend and share data of the stock. The parameter ticker is passed in the 6-digit stock code."
            "The returned data includes: annual cash dividends (dividends per share), bonus share ratio, capitalization ratio, equity registration date, ex-rights and ex-dividend date, and dividend payment date."
            "The parameter years controls the number of years to query, the default is 5 years."
            "Applicable scenarios:'Dividend distribution in recent years', 'What is the dividend rate?', 'Dividend ratio', 'History of dividends and shares', 'high dividend stocks'. "
            "The data source is the Tushare dividend interface (requires permission of 2000 points or more)."
            "When analyzing dividend data, pay attention to: the number of consecutive dividend years, the stability of the dividend rate, and whether the dividend ratio is reasonable (30%-70% is appropriate)."
            "Use get_income_analysis and get_cashflow_analysis to determine the sustainability of dividends."
        ),
        "tags": ["dividend", "dividends", "Tools", "get_dividend_data", "Bonus shares", "dividend"],
        "priority": 1,
    },
    {
        "id": "tool_get_main_business",
        "category": "tool_guide",
        "title": "get_main_business Main business composition tool guide",
        "content": (
            "get_main_business Get the main business income composition of the stock, and pass in the 6-digit stock code as the parameter ticker."
            "The returned data includes: revenue amount, revenue proportion, and gross profit margin by product/business classification; revenue distribution by region."
            "The parameter periods controls the number of analysis periods, the default is 4 periods."
            "Applicable scenarios:'Main business composition', 'Income source structure', 'Proportion of each business', 'Business with the highest gross profit margin'. "
            "The data source is the Tushare fina_mainbz interface."
            "Analyzing the main business can understand the company s core competitiveness and revenue diversification."
        ),
        "tags": ["Main business", "Income composition", "Tools", "get_main_business", "business structure"],
        "priority": 1,
    },
]



# ============================================================
# Analytical Methodology (methodology) — ~7 Article
# ============================================================

METHODOLOGY_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "id": "method_sector_analysis",
        "category": "methodology",
        "title": "Standard process for sector analysis",
        "content": (
            "Standard process for sector analysis:1) Use analyze_sector_by_name to obtain the overall overview of the sector (trend, increase or decrease, turnover);"
            "2) Use get_sector_constituents to view sector constituent stocks and find the leading stocks sorted by market value;"
            "3) Use get_sector_daily to check the recent trend and trend direction of the sector;"
            "4) Use get_stock_fundamentals_unified to conduct in-depth fundamental analysis of key leading stocks;"
            "5) Use get_fund_flow_data to check the fund flow of the sector and determine the degree of fund attention."
        ),
        "tags": ["Sector analysis", "methodology", "process"],
        "priority": 1,
    },
    {
        "id": "method_stock_analysis",
        "category": "methodology",
        "title": "Standard process for comprehensive analysis of individual stocks",
        "content": (
            "Comprehensive analysis process of individual stocks:1) Fundamentals overview: Use get_stock_fundamentals_unified to obtain quick judgments on valuation indicators such as PE/PB/ROE;"
            "2) Financial depth (optional): For in-depth analysis, use get_income_analysis to see profit trends, get_balance_sheet_analysis to see debt levels,"
            "get_cashflow_analysis Look at cash flow quality, get_dividend_data to look at dividend history, get_main_business to look at business structure;"
            "3) Technical aspect: Use get_technical_indicators to obtain MACD/RSI/KDJ/BOLL to determine the trend and overbought and oversold;"
            "4) Market side: Use get_stock_market_data_unified to obtain the price trend and trading volume, and observe the coordination between volume and price;"
            "5) News side: Use get_stock_news_unified to get relevant news and understand recent events and sentiment;"
            "6) Comprehensive judgment: combined with fundamental valuation+Technical trends+The news is catalyzed and a comprehensive analysis is given."
            "It is recommended to fetch data in parallel to improve efficiency. It is not necessary to call on all financial segmentation tools when the fundamental overview is sufficient."
        ),
        "tags": ["individual stock analysis", "methodology", "process"],
        "priority": 1,
    },
    {
        "id": "method_market_analysis",
        "category": "methodology",
        "title": "Broad/Market Analysis Standard Process",
        "content": (
            "Market analysis process:1) Use get_china_market_overview to obtain the market panorama (index rise and fall, number of risers and fallers, transaction volume);"
            "2) Use get_limit_stats to check the upper and lower limits and judge market sentiment;"
            "3) Use get_fund_flow_data to check the sector fund flow rankings and discover the hot spots of the day;"
            "4) Use get_north_flow to check the movement of northbound funds and determine the attitude of foreign investment;"
            "5) Based on the above data, the overall market judgment is given: trends, emotions, hot spots, and financial aspects."
        ),
        "tags": ["Market", "market analysis", "methodology"],
        "priority": 1,
    },
    {
        "id": "method_comparison",
        "category": "methodology",
        "title": "Individual stock comparative analysis process",
        "content": (
            "Comparative analysis process:1) Use get_peer_comparison to obtain peer industry comparison data;"
            "2) Comparison dimensions: valuation (which one is cheaper, PE/PB), profit (which one is better, ROE/gross profit margin),"
            "Growth potential (whose revenue/profit growth rate is faster), market value size;"
            "3) Use get_stock_fundamentals_unified to obtain detailed fundamentals for in-depth comparison;"
            "4) Summarizes the advantages and disadvantages of each company, does not make buying and selling recommendations, and only presents objective data comparisons."
        ),
        "tags": ["Comparative analysis", "methodology", "Peers"],
        "priority": 2,
    },
    {
        "id": "method_concept_stock_query",
        "category": "methodology",
        "title": "Concept stock inquiry process",
        "content": (
            "Concept stock inquiry process:1) Use analyze_sector_by_name or get_sector_constituents to pass in concept keywords;"
            "2) The system will automatically search the Flush industry sector(N Type, including all concept sections)and return matching results;"
            "3) If you need to learn more about a certain concept stock, use individual stock analysis tools for in-depth analysis;"
            "4) Note: The name of the concept section may be different from the user s statement. For example, the user said'Xiaomi concept'The corresponding section name may be'Xiaomi car'. "
            "If the keyword cannot be matched, try shortening the keyword and search again."
        ),
        "tags": ["concept stocks", "Query", "methodology"],
        "priority": 1,
    },
    {
        "id": "method_financial_deep_analysis",
        "category": "methodology",
        "title": "Financial in-depth analysis process",
        "content": (
            "In-depth financial analysis process (applicable to scenarios that require a detailed understanding of the company s financial status):"
            "1) Profitability: Use get_income_analysis to view revenue and profit trends, gross profit margin/net profit margin changes, and expense structure;"
            "2) Financial security: Use get_balance_sheet_analysis to view the asset-liability ratio, current ratio, asset structure, and determine solvency;"
            "3) Cash quality: Use get_cashflow_analysis to view operating/investing/financing cash flow, calculate free cash flow and OCF/net profit ratio;"
            "4) Business structure: Use get_main_business to view the composition of revenue sources and gross profit margin of each business to understand core competitiveness;"
            "5) Dividend paying ability: Use get_dividend_data to check the historical dividend situation and judge the company s willingness and ability to return shareholders;"
            "6) Comprehensive judgment: Profit continues to grow + Debt ratio is reasonable + Abundant cash flow + The main business is clear + Stable dividends = Financially high quality company."
            "If you just want a quick overview, use get_stock_fundamentals_unified instead of calling each of the 5 segmentation tools."
        ),
        "tags": ["financial analysis", "methodology", "In-depth analysis", "process"],
        "priority": 1,
    },
    {
        "id": "method_dividend_analysis",
        "category": "methodology",
        "title": "Dividend investment analysis process",
        "content": (
            "Dividend investment analysis process (applicable to'How to choose high dividend stocks', 'When to buy dividend stocks'etc.):"
            "1) Use get_dividend_data to obtain the dividend records of the target stock in the past five years, and confirm whether there are continuous dividends and the dividend rate level;"
            "2) Use get_income_analysis to confirm whether profits are growing steadily (the basis for dividends is sustained profitability);"
            "3) Use get_cashflow_analysis to confirm that operating cash flow is sufficient (make sure that dividends come from real profits rather than debt dividends);"
            "4) Use get_balance_sheet_analysis to confirm that the debt ratio is reasonable (dividends from companies with high debt levels are unsustainable);"
            "5) Evaluate the timing of entry: The best deployment period is after the annual report season (March-April) confirms the dividend plan and gradually builds a position 2-3 months before the ex-dividend date;"
            "Avoid chasing prices a few days before the ex-dividend date (the market grab for power is risky)."
            "6) Holding suggestion: Dividend tax is exempted if you hold shares for more than 1 year, and you can achieve compound interest by reinvesting the dividends."
        ),
        "tags": ["dividend", "investment analysis", "methodology", "High dividends", "Entry time"],
        "priority": 1,
    },
]


# ============================================================
# Problem pattern mapping class (pattern) — ~15 Article
# ============================================================

PATTERN_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "id": "pattern_concept_stock",
        "category": "pattern",
        "title": "Concept stock query mode",
        "content": (
            "User asked'XX What are concept stocks?', 'XX concept stocks', 'XX Related stocks'When, it is a concept stock inquiry."
            "Core tools:get_sector_constituents(sector_name=XX) or analyze_sector_by_name(sector_name=XX). "
            "No ticker parameter is required, search directly using concept keywords."
            "Example:'Xiaomi Auto Concept Stock' → sector_name='Xiaomi car'; 'Photovoltaic concept stocks' → sector_name='photovoltaic'. "
        ),
        "tags": ["concept stocks", "mode", "plate"],
        "priority": 1,
    },
    {
        "id": "pattern_sector_analysis",
        "category": "pattern",
        "title": "Sector analysis mode",
        "content": (
            "User asked'XX How about the sector?', 'XX Industry prospects', 'XX Sector investment opportunities'When, it belongs to sector analysis."
            "Core tools:analyze_sector_by_name(sector_name=XX keywords). "
            "This tool will comprehensively return information such as sector trends, constituent stocks, and capital flows."
            "For more in-depth analysis, append get_sector_daily and get_fund_flow_data."
        ),
        "tags": ["Sector analysis", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_market_overview",
        "category": "pattern",
        "title": "Broad/Market Overview Mode",
        "content": (
            "User asked'How is the market?', 'Today s market conditions', 'overall market', 'A stock trend'time, it is a market overview."
            "Core tool: get_china_market_overview (market overview)."
            "Supplementary tools: get_limit_stats (price limit statistics), get_fund_flow_data (fund flow direction)."
            "If the user is concerned about foreign investment, add get_north_flow."
        ),
        "tags": ["Market", "market", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_stock_analysis",
        "category": "pattern",
        "title": "individual stock analysis model",
        "content": (
            "User asked'XX How is the stock?', 'Help me analyze XX', 'XX Is it worth buying?'When, it belongs to individual stock analysis."
            "A ticker (stock code) is required. If the user only gives a name, the code needs to be looked up first."
            "Recommended parallel calls:get_stock_fundamentals_unified + get_stock_market_data_unified + "
            "get_technical_indicators + get_stock_news_unified。"
        ),
        "tags": ["individual stocks", "analysis", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_comparison",
        "category": "pattern",
        "title": "individual stock comparison model",
        "content": (
            "User asked'XX Which one is better with YY?', 'XX Contrast YY', 'Comparison with the same industry'When, it is a comparative analysis."
            "Core tools:get_peer_comparison(ticker=XX code). "
            "Supplement: get_stock_fundamentals_unified obtains the fundamentals of each company separately."
        ),
        "tags": ["Contrast", "mode"],
        "priority": 2,
    },
    {
        "id": "pattern_north_flow",
        "category": "pattern",
        "title": "Northbound fund inquiry mode",
        "content": (
            "User asked'Northbound funds', 'Foreign investment trends', 'Shanghai-Shenzhen-Hong Kong Stock Connect', 'What are foreign investors buying?'At this time, it is a northbound fund inquiry."
            "Core tool: get_north_flow."
            "You can cooperate with get_china_market_overview to understand the market background."
        ),
        "tags": ["Northbound funds", "foreign capital", "mode"],
        "priority": 2,
    },
    {
        "id": "pattern_technical_analysis",
        "category": "pattern",
        "title": "technical analysis patterns",
        "content": (
            "User asked'XX technical aspect', 'XX support level pressure level', 'XX MACD/KDJ'When, it belongs to technical analysis."
            "Core tools:get_technical_indicators(ticker=XX code). "
            "Supplement: get_stock_market_data_unified Get K-line trend analysis."
        ),
        "tags": ["technical analysis", "mode"],
        "priority": 2,
    },
    {
        "id": "pattern_hot_sector",
        "category": "pattern",
        "title": "Hot section query mode",
        "content": (
            "User asked'What sector is hot today?', 'Hot sectors', 'Where are the funds flowing?', 'sector rotation'When, it belongs to the hot section query."
            "Core tool: get_fund_flow_data (sector fund flow ranking)."
            "Supplement: get_china_market_overview understands the overall market background, get_limit_stats bullishly limits the concentrated sectors."
        ),
        "tags": ["Hotspot", "plate", "funds", "mode"],
        "priority": 2,
    },
    {
        "id": "pattern_margin_trading",
        "category": "pattern",
        "title": "Two-in-one query mode",
        "content": (
            "User asked'Financing balance', 'Two integrated data', 'Leveraged funds'When, it is a two-in-one query."
            "Core tool: get_margin_trading."
            "The two financing data reflect the trend of leveraged funds, and the increase in financing balance indicates an increase in bullish sentiment."
        ),
        "tags": ["Integration of both", "Margin margin trading", "mode"],
        "priority": 3,
    },
    {
        "id": "pattern_limit_stats",
        "category": "pattern",
        "title": "Price limit statistical mode",
        "content": (
            "User asked'How many companies have reached their daily limit today?', 'Limit down situation', 'Connecting plate height', 'market sentiment'When, it belongs to the price limit statistics."
            "Core tool: get_limit_stats."
            "The ratio of the number of companies at the daily limit vs the number of companies at the daily limit is an important market sentiment indicator. The height of the link reflects the heat of speculation."
        ),
        "tags": ["price limit", "market sentiment", "mode"],
        "priority": 3,
    },
    {
        "id": "pattern_income_profit",
        "category": "pattern",
        "title": "Profit/revenue analysis model",
        "content": (
            "User asked'How is revenue and profit growth?', 'profit trend', 'What is the gross profit margin?', 'net profit margin', 'Profitability', "
            "'expense ratio', 'revenue growth'When, it belongs to income statement analysis."
            "Core tools:get_income_analysis(ticker=Stock code, periods=8). "
            "This tool returns detailed multi-period trends of the income statement, including gross profit margin, net profit margin, expense structure, etc."
            "If you just want a quick overview, get_stock_fundamentals_unified also contains fundamental profitability indicators."
        ),
        "tags": ["profit", "Revenue", "Gross profit margin", "net profit margin", "Profit", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_financial_health",
        "category": "pattern",
        "title": "Financial health/asset and liability analysis model",
        "content": (
            "User asked'Is the asset-liability ratio high?', 'Is your finances healthy?', 'Liabilities', 'cash reserves', "
            "'Solvency', 'current ratio'When, it belongs to balance sheet analysis."
            "Core tools:get_balance_sheet_analysis(ticker=Stock code). "
            "Return to asset-liability ratio, current ratio, quick ratio, asset structure and other multi-dimensional analysis."
            "If you are also concerned about cash flow, use it with get_cashflow_analysis."
        ),
        "tags": ["Debt ratio", "financial health", "Assets and liabilities", "debt repayment", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_cashflow_query",
        "category": "pattern",
        "title": "cash flow analysis model",
        "content": (
            "User asked'Is the cash flow good?', 'free cash flow', 'operating cash flow', 'Hematopoietic ability', "
            "'cash flow quality'When, it belongs to cash flow statement analysis."
            "Core tools:get_cashflow_analysis(ticker=Stock code). "
            "Return to the three major cash flows of operating/investing/financing, free cash flow, OCF/net profit ratio, etc."
            "Cash flow is a key indicator of earnings quality: profits but no cash inflow may be problematic."
        ),
        "tags": ["cash flow", "free cash flow", "operating cash flow", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_dividend_query",
        "category": "pattern",
        "title": "Dividend/dividend inquiry mode",
        "content": (
            "User asked'Dividend status', 'dividend yield', 'Dividend ratio', 'Bonus shares converted into additional shares', 'high dividend stocks', "
            "'When does the dividend come in?', 'ex-rights and ex-dividends'When, it belongs to dividend analysis."
            "Core tools:get_dividend_data(ticker=Stock code, years=5). "
            "If a user asks about investment strategies (e.g.'When to buy high dividend stocks') , The answer needs to be combined with the knowledge of dividend investment strategies."
            "Including: the best layout period (annual reporting season March-April), avoiding chasing prices before ex-dividends, exempting dividend tax from holding shares for more than one year, etc."
            "Use get_income_analysis and get_cashflow_analysis to determine the sustainability of dividends."
        ),
        "tags": ["dividend", "dividends", "ex-rights and ex-dividends", "High dividends", "mode"],
        "priority": 1,
    },
    {
        "id": "pattern_main_business",
        "category": "pattern",
        "title": "Main business query mode",
        "content": (
            "User asked'What is the main business', 'source of income', 'Business composition', 'Proportion of each product', "
            "'What to make money from'At this time, it belongs to the main business analysis."
            "Core tools:get_main_business(ticker=Stock code). "
            "Returns the revenue structure classified by product and region and the gross profit margin of each business."
            "Understanding the company s main business can help determine its core competitiveness and future growth potential."
        ),
        "tags": ["Main business", "Income composition", "business structure", "mode"],
        "priority": 1,
    },
]


# ============================================================
# Summarize all knowledge documents
# ============================================================

def get_all_knowledge_documents() -> List[Dict[str, Any]]:
    """Returns a list of all knowledge documents"""
    return (
        CONCEPT_DOCUMENTS
        + TOOL_GUIDE_DOCUMENTS
        + METHODOLOGY_DOCUMENTS
        + PATTERN_DOCUMENTS
    )
