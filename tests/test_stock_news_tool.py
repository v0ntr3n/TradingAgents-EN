import logging
from datetime import datetime

import pandas as pd


def _patch_a_share_market(monkeypatch):
    from tradingagents.utils import stock_utils as stock_utils_module

    class FakeStockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {
                "is_china": True,
                "is_hk": False,
                "is_us": False,
                "market_name": "China A shares",
            }

    monkeypatch.setattr(stock_utils_module, "StockUtils", FakeStockUtils)


def test_a_share_tool_prefers_akshare_live_when_database_is_empty(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["local", "tushare", "akshare"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["local", "tushare", "akshare"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Ping An Bank")
    tushare_calls = {"count": 0}

    def fake_fetch_tushare(*args, **kwargs):
        tushare_calls["count"] += 1
        return [
            {
                "title": "Ping An Bank releases annual performance report",
                "summary": "Performance and dividend arrangements are disclosed simultaneously.",
                "publish_time": datetime(2026, 4, 12, 9, 30),
                "source": "Sina Finance",
                "category": "company_announcement",
                "sentiment": "positive",
                "importance": "high",
                "keywords": ["performance", "dividend"],
                "data_source": "tushare",
            }
        ]

    monkeypatch.setattr(module, "_fetch_tushare_news_live", fake_fetch_tushare)

    akshare_calls = {"count": 0}

    def fake_fetch_akshare(*args, **kwargs):
        akshare_calls["count"] += 1
        return [
            {
                "title": "Ping An Bank releases annual performance report",
                "summary": "Performance and dividend arrangements are disclosed simultaneously.",
                "publish_time": datetime(2026, 4, 12, 9, 30),
                "source": "Oriental Fortune",
                "category": "company_announcement",
                "sentiment": "positive",
                "importance": "high",
                "keywords": ["performance", "dividend"],
                "data_source": "akshare",
            }
        ]

    monkeypatch.setattr(module, "_fetch_akshare_news_live", fake_fetch_akshare)

    result = module.get_stock_news_unified.invoke({"ticker": "000001", "curr_date": "2026-04-13"})

    assert "## AKShare Oriental Fortune News (real time)" in result
    assert "Ping An Bank releases annual performance report" in result
    assert "Category: company announcement | emotions: Positive side | importance: high" in result
    assert "Tushare Multi-source news (real time)" not in result
    assert akshare_calls["count"] == 1
    assert tushare_calls["count"] == 0


def test_fetch_akshare_news_live_filters_outdated_items(monkeypatch):
    from core.tools.implementations.news import stock_news as module
    from tradingagents.dataflows.providers.china import akshare as akshare_module

    class FakeAKShareProvider:
        def is_available(self):
            return True

        async def get_stock_news(self, symbol=None, limit=10):
            return []

    monkeypatch.setattr(akshare_module, "AKShareProvider", FakeAKShareProvider)
    monkeypatch.setattr(
        module,
        "_run_async_in_thread",
        lambda coroutine_factory, timeout=30.0: [
            {
                "title": "News in the window",
                "summary": "Analyze news within a date window.",
                "publish_time": datetime(2026, 4, 12, 10, 0),
                "source": "Oriental Fortune",
            },
            {
                "title": "Old news outside the window",
                "summary": "Significantly earlier than the analysis date window.",
                "publish_time": datetime(2026, 3, 20, 10, 0),
                "source": "Oriental Fortune",
            },
        ],
    )

    news = module._fetch_akshare_news_live(
        symbol="000001",
        start_date=datetime(2026, 4, 7, 0, 0),
        end_date=datetime(2026, 4, 13, 23, 59, 59),
        limit=20,
    )

    assert [item["title"] for item in news] == ["News in the window"]


def test_fetch_tushare_news_live_matches_company_name_without_symbol(monkeypatch):
    from core.tools.implementations.news import stock_news as module
    from tradingagents.dataflows.providers.china import tushare as tushare_module

    class FakeDataFrame:
        empty = False

    class FakeAPI:
        def news(self, src=None, start_date=None, end_date=None):
            return FakeDataFrame()

    class FakeProvider:
        api = FakeAPI()

        def is_available(self):
            return True

        def _process_tushare_news(self, news_df, source, symbol=None, limit=10):
            return [
                {
                    "title": "Ping An Bank releases annual report",
                    "summary": "Only the company name appears, not the stock code.",
                    "publish_time": datetime(2026, 4, 12, 8, 0),
                    "source": "Sina Finance",
                    "category": "company_announcement",
                    "sentiment": "positive",
                    "importance": "high",
                    "data_source": "tushare",
                },
                {
                    "title": "Unrelated company news",
                    "summary": "It has nothing to do with the target company.",
                    "publish_time": datetime(2026, 4, 12, 9, 0),
                    "source": "Sina Finance",
                    "category": "other",
                    "sentiment": "neutral",
                    "importance": "low",
                    "data_source": "tushare",
                },
            ]

    monkeypatch.setattr(module, "TUSHARE_LIVE_SOURCES", ["sina"])
    monkeypatch.setattr(tushare_module, "get_tushare_provider", lambda: FakeProvider())

    news = module._fetch_tushare_news_live(
        symbol="000001",
        company_name="Ping An Bank",
        start_date=datetime(2026, 4, 7, 0, 0),
        end_date=datetime(2026, 4, 13, 23, 59, 59),
        limit=20,
    )

    assert [item["title"] for item in news] == ["Ping An Bank releases annual report"]


def test_company_aliases_expand_full_width_share_class_suffix():
    from core.tools.implementations.news import stock_news as module

    aliases = module._get_company_aliases("Vanke Ａ")

    assert "Vanke Ａ" in aliases
    assert "Vanke A" in aliases
    assert "Vanke" in aliases


def test_fetch_tushare_news_live_scans_full_feed_for_extended_alias_matches(monkeypatch):
    from core.tools.implementations.news import stock_news as module
    from tradingagents.dataflows.providers.china import tushare as tushare_module

    news_df = pd.DataFrame(
        [
            {
                "datetime": "2026-04-12 09:00:00",
                "title": f"Unrelated market news {index}",
                "content": "It has nothing to do with the target company.",
                "channels": "market",
            }
            for index in range(500)
        ]
        + [
            {
                "datetime": "2026-04-12 18:00:00",
                "title": "Wang Shi issued an article to refute the rumors and was arrested: Everything is fine, the rumormongers will be handed over to the law",
                "content": "4 On March 12, news spread online that Vanke founder Wang Shi had been arrested, sparking heated discussions among netizens. In the evening, Wang Shi issued an article to refute the rumors.",
                "channels": "company",
            }
        ]
    )

    class FakeAPI:
        def news(self, src=None, start_date=None, end_date=None):
            return news_df

    class FakeProvider:
        api = FakeAPI()

        def is_available(self):
            return True

        def _process_tushare_news(self, news_df, source, symbol=None, limit=10):
            processed = []
            for _, row in news_df.head(limit * 2).iterrows():
                processed.append(
                    {
                        "title": str(row.get("title", "")),
                        "summary": str(row.get("content", ""))[:200],
                        "content": str(row.get("content", "")),
                        "publish_time": datetime.fromisoformat(str(row.get("datetime"))),
                        "source": "Wall Street Insights",
                        "category": "other",
                        "importance": "medium",
                        "data_source": "tushare",
                    }
                )
            return processed

    monkeypatch.setattr(module, "TUSHARE_LIVE_SOURCES", ["wallstreetcn"])
    monkeypatch.setattr(tushare_module, "get_tushare_provider", lambda: FakeProvider())

    news = module._fetch_tushare_news_live(
        symbol="000002",
        company_name="Vanke Ａ",
        start_date=datetime(2026, 4, 7, 0, 0),
        end_date=datetime(2026, 4, 13, 23, 59, 59),
        limit=20,
    )

    assert [item["title"] for item in news] == ["Wang Shi issued an article to refute the rumors and was arrested: Everything is fine, the rumormongers will be handed over to the law"]


def test_relevance_ranking_prefers_direct_company_event_over_macro_mention():
    from core.tools.implementations.news import stock_news as module

    ranked_news = module._rank_a_share_news_items(
        [
            {
                "title": "Reminder of important events in the capital market next week: The National Bureau of Statistics will release a series of blockbuster data. CATL, Kweichow Moutai, etc. will release financial reports.",
                "summary": " [Reminder of important events in the capital market next week: The National Bureau of Statistics will release a series of blockbuster data. Ningde Times, Kweichow Moutai, etc. will release financial reports] 1. On April 16, the National Bureau of Statistics will release first-quarter national economic performance data.",
                "publish_time": datetime(2026, 4, 12, 22, 0),
                "source": "Financial Associated Press",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "tushare",
            },
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "More direct company business events.",
                "publish_time": datetime(2026, 4, 8, 16, 30),
                "source": "Red Star Capital Bureau",
                "category": "general",
                "importance": "medium",
                "data_source": "akshare",
            },
        ],
        symbol="600519",
        company_name="Kweichow Moutai",
        limit=20,
    )

    assert ranked_news[0]["title"] == "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped."
    assert ranked_news[0]["relevance_score"] > ranked_news[1]["relevance_score"]


def test_relevance_ranking_keeps_body_only_clarification_news_above_zero():
    from core.tools.implementations.news import stock_news as module

    ranked_news = module._rank_a_share_news_items(
        [
            {
                "title": "Wang Shi issued an article to refute the rumors and was arrested: Everything is fine, the rumormongers will be handed over to the law",
                "summary": "4 On March 12, news spread online that Vanke founder Wang Shi had been arrested, sparking heated discussions among netizens. In the evening, Wang Shi issued an article to refute the rumors.",
                "publish_time": datetime(2026, 4, 12, 18, 0),
                "source": "Wall Street Insights",
                "category": "other",
                "importance": "medium",
                "data_source": "tushare",
            }
        ],
        symbol="000002",
        company_name="Vanke Ａ",
        limit=20,
    )

    assert [item["title"] for item in ranked_news] == ["Wang Shi issued an article to refute the rumors and was arrested: Everything is fine, the rumormongers will be handed over to the law"]
    assert ranked_news[0]["relevance_score"] > 0


def test_relevance_ranking_prefers_title_company_anchor_over_body_only_mention():
    from core.tools.implementations.news import stock_news as module

    ranked_news = module._rank_a_share_news_items(
        [
            {
                "title": "Stock repurchase: strong confidence in two years of trillions, cancellation of hundreds of billions to increase returns",
                "summary": "Industry leaders actively carry out buybacks and cancellations. On April 2, 2026, Kweichow Moutai (600519.SH) disclosed the Announcement on the Implementation Progress of Share Repurchases , which showed that as of",
                "publish_time": datetime(2026, 4, 11, 2, 15),
                "source": "China Business Network",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "akshare",
            },
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "More direct company business events.",
                "publish_time": datetime(2026, 4, 8, 16, 30),
                "source": "Red Star Capital Bureau",
                "category": "general",
                "importance": "medium",
                "data_source": "akshare",
            },
        ],
        symbol="600519",
        company_name="Kweichow Moutai",
        limit=20,
    )

    assert ranked_news[0]["title"] == "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped."
    assert ranked_news[0]["relevance_score"] > ranked_news[1]["relevance_score"]


def test_a_share_tool_uses_akshare_live_even_when_tushare_is_configured(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["tushare", "akshare", "local"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["tushare", "akshare", "local"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Kweichow Moutai")
    tushare_calls = {"count": 0}

    def fake_fetch_tushare(*args, **kwargs):
        tushare_calls["count"] += 1
        return [
            {
                "title": "Reminder of important events in the capital market next week: The National Bureau of Statistics will release a series of blockbuster data. CATL, Kweichow Moutai, etc. will release financial reports.",
                "summary": " [Reminder of important events in the capital market next week: The National Bureau of Statistics will release a series of blockbuster data. Ningde Times, Kweichow Moutai, etc. will release financial reports] 1. On April 16, the National Bureau of Statistics will release first-quarter national economic performance data.",
                "publish_time": datetime(2026, 4, 12, 22, 0),
                "source": "Financial Associated Press",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "tushare",
            }
        ]

    monkeypatch.setattr(module, "_fetch_tushare_news_live", fake_fetch_tushare)
    monkeypatch.setattr(
        module,
        "_fetch_akshare_news_live",
        lambda symbol, start_date, end_date, limit=20: [
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "More direct company business events.",
                "publish_time": datetime(2026, 4, 8, 16, 30),
                "source": "Red Star Capital Bureau",
                "category": "general",
                "importance": "medium",
                "data_source": "akshare",
            }
        ],
    )

    result = module.get_stock_news_unified.invoke({"ticker": "600519", "curr_date": "2026-04-13"})

    assert "## AKShare Oriental Fortune News (real time)" in result
    assert "Moutai s non-standard product sales agency launched" in result
    assert "## Tushare Multi-source news (real time)" not in result
    assert tushare_calls["count"] == 0


def test_a_share_tool_logs_only_akshare_live_selection(monkeypatch, caplog):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["local", "tushare", "akshare"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["local", "tushare", "akshare"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Vanke A")
    tushare_calls = {"count": 0}

    def fake_fetch_tushare(*args, **kwargs):
        tushare_calls["count"] += 1
        return []

    monkeypatch.setattr(module, "_fetch_tushare_news_live", fake_fetch_tushare)
    monkeypatch.setattr(
        module,
        "_fetch_akshare_news_live",
        lambda symbol, start_date, end_date, limit=20: [
            {
                "title": "Vanke A discloses first quarter sales data",
                "summary": "Sales and payment collection updates.",
                "publish_time": datetime(2026, 4, 12, 10, 0),
                "source": "Oriental Fortune",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "akshare",
            }
        ],
    )

    with caplog.at_level(logging.INFO):
        result = module.get_stock_news_unified.invoke({"ticker": "000002", "curr_date": "2026-04-13"})

    assert "Start trying real-time news feeds: akshare" in caplog.text
    assert "## AKShare Oriental Fortune News (real time)" in result
    assert "Start trying real-time news feeds: tushare" not in caplog.text
    assert tushare_calls["count"] == 0


def test_database_news_output_includes_structured_fields(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["local", "tushare", "akshare"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [
                {
                    "title": "Ping An Bank discloses quarterly report",
                    "summary": "Revenue and profit performance were stable.",
                    "publish_time": datetime(2026, 4, 11, 18, 0),
                    "url": "https://example.com/news/1",
                    "source": "Shanghai Stock Exchange Announcement",
                    "category": "company_announcement",
                    "sentiment": "positive",
                    "importance": "high",
                    "keywords": ["quarterly report", "Revenue"],
                    "data_source": "tushare",
                }
            ],
            "enabled_sources": ["local", "tushare", "akshare"],
            "used_sources": ["tushare"],
        },
    )

    result = module.get_stock_news_unified.invoke({"ticker": "000001", "curr_date": "2026-04-13"})

    assert "## Database cache" in result
    assert "**Description**: hit source: Tushare (database cache)" in result
    assert "Summary: Revenue and profit performance were stable." in result
    assert "Category: company announcement | emotions: Positive side | importance: high" in result
    assert "keywords: quarterly report, Revenue" in result
    assert "Current analysis priority: local > akshare" in result
    assert "Tushare The news source is currently only used for synchronous storage and does not participate in real-time news analysis calls." in result


def test_headlines_tool_deduplicates_titles_and_merges_sources(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["tushare", "akshare", "local"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["tushare", "akshare", "local"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Kweichow Moutai")
    monkeypatch.setattr(
        module,
        "_fetch_akshare_news_live",
        lambda symbol, start_date, end_date, limit=20: [
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "Summary of the CFA version.",
                "publish_time": datetime(2026, 4, 8, 16, 32),
                "source": "Financial Associated Press",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "akshare",
            },
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "AKShare Version summary.",
                "publish_time": datetime(2026, 4, 8, 16, 30),
                "source": "Red Star Capital Bureau",
                "category": "general",
                "importance": "medium",
                "data_source": "akshare",
            },
            {
                "title": "Stock repurchase: strong confidence in two years of trillions, cancellation of hundreds of billions to increase returns",
                "summary": "Industry leaders actively carry out buybacks and cancellations.",
                "publish_time": datetime(2026, 4, 11, 2, 15),
                "source": "China Business Network",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "akshare",
            },
        ],
    )

    result = module.get_stock_news_headlines_unified.invoke(
        {"ticker": "600519", "curr_date": "2026-04-13", "limit": 10}
    )

    assert result.count("Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.") == 1
    assert "Source: Financial Associated Press / Red Star Capital Bureau" in result
    assert "Remove duplicates and merge: 2 news items with the same title have been merged" in result
    assert "news_id:" in result
    assert "get_stock_news_details_unified" in result


def test_details_tool_returns_selected_news_by_news_id(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["tushare", "akshare", "local"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["tushare", "akshare", "local"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Kweichow Moutai")
    monkeypatch.setattr(
        module,
        "_fetch_akshare_news_live",
        lambda symbol, start_date, end_date, limit=20: [
            {
                "title": "Moutai s non-standard product sales have been implemented: stores have implemented it, and the first batch of products have been shipped.",
                "summary": "More direct company business events.",
                "content": "3 In May, Kweichow Moutai solicited cooperation intentions from dealers, and the first batch of consignment products have been shipped.",
                "publish_time": datetime(2026, 4, 8, 16, 30),
                "source": "Red Star Capital Bureau",
                "category": "general",
                "importance": "medium",
                "data_source": "akshare",
                "url": "https://example.com/news/maotai-detail",
            }
        ],
    )

    bundle = module._build_stock_news_bundle("600519", "2026-04-13", limit=10)
    news_id = bundle["items"][0]["news_id"]

    result = module.get_stock_news_details_unified.invoke(
        {"ticker": "600519", "curr_date": "2026-04-13", "news_ids": news_id}
    )

    assert f"[news_id: {news_id}]" in result
    assert "Moutai s non-standard product sales agency launched" in result
    assert "Main points of the text: 3 Kweichow Moutai solicits cooperation intentions from dealers in January" in result
    assert "link: https://example.com/news/maotai-detail" in result


def test_headlines_tool_deprioritizes_macro_reminder_detail_recommendation(monkeypatch):
    from core.tools.implementations.news import stock_news as module

    _patch_a_share_market(monkeypatch)

    monkeypatch.setattr(module, "_get_a_share_enabled_sources", lambda: ["tushare", "akshare", "local"])
    monkeypatch.setattr(
        module,
        "_query_news_from_database",
        lambda symbol, start_date, end_date, limit=20: {
            "news": [],
            "enabled_sources": ["tushare", "akshare", "local"],
            "used_sources": [],
        },
    )
    monkeypatch.setattr(module, "_get_company_name", lambda symbol: "Kweichow Moutai")
    monkeypatch.setattr(
        module,
        "_fetch_akshare_news_live",
        lambda symbol, start_date, end_date, limit=20: [
            {
                "title": "Reminder of important events in the capital market next week: The National Bureau of Statistics will release a series of blockbuster data. CATL, Kweichow Moutai, etc. will release financial reports.",
                "summary": "Macro calendar reminders with multiple companies.",
                "publish_time": datetime(2026, 4, 12, 22, 0),
                "source": "Financial Associated Press",
                "category": "company_announcement",
                "importance": "high",
                "data_source": "akshare",
            }
        ],
    )

    result = module.get_stock_news_headlines_unified.invoke(
        {"ticker": "600519", "curr_date": "2026-04-13", "limit": 10}
    )

    assert "Detailed suggestions: Can not be expanded temporarily (more like macro reminder or multi-company enumeration news)" in result