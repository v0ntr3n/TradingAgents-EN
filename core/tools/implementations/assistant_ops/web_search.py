"""Web Search Tool - Based on SearXNG meta-search engine, supporting Baidu/Bing crawler alternatives."""

import logging
import os
import random
import re
import time
from typing import Annotated, Optional
from urllib.parse import quote, unquote, urlencode, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # SearXNG takes longer

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# SearXNG Engine rotation order (quality first).
# Note: don't let go bing——Bing The Chinese version will downgrade long Chinese queries to single-word matching.
# Return"race"Dictionary pages and other irrelevant results, filtering them will waste context tokens.
SEARXNG_ENGINE_ORDER = ["baidu", "sogou", "360so"]

# Engine fuse status: engine name -> Cooldown expiration timestamp.
# If the engine is continuously queried, it will trigger the anti-crawling CAPTCHA and be suspended by SearXNG (actual measurement of LLM round of dialogue)
# Triggered after 8 searches), the engine returns 0 results after suspending. Here is the circuit breaker on the client side:
# After an engine has no valid results, it will no longer be preferred within 5 minutes and will be automatically rotated to the next engine.
_engine_cooldown: dict = {}

# Minimum interval (seconds) between two SearXNG requests to reduce the probability of triggering anti-crawling
_SEARXNG_MIN_INTERVAL = 1.2
_last_searxng_ts = 0.0

# Financial website domain name priority (the higher the score, the priority)
FINANCE_DOMAINS = {
    # Official website (highest priority)
    "seres.cn": 100,
    "byd.com": 100,
    # Juchao Information (Official Announcement Platform)
    "cninfo.com.cn": 95,
    # Mainstream financial media
    "eastmoney.com": 90,
    "finance.sina.com.cn": 85,
    "10jqka.com.cn": 85,
    "stcn.com": 80,
    "cs.com.cn": 80,
    "cnstock.com": 80,
    "money.163.com": 75,
    "163.com": 70,
    "finance.qq.com": 75,
    "finance.ifeng.com": 75,
    "hexun.com": 70,
    "finance.people.com.cn": 70,
    # Passenger Car Association/Automobile Industry Association (authoritative source of sales data)
    "cpcaauto.com": 95,
    "caam.org.cn": 95,
}

# overall situation Session
_baidu_session: Optional[requests.Session] = None


def _get_domain_score(url: str) -> int:
    """Returns a financial priority score based on the URL domain."""
    try:
        domain = urlparse(url).netloc.lower()
        for fin_domain, score in FINANCE_DOMAINS.items():
            if fin_domain in domain:
                return score
    except Exception:
        pass
    return 0


def _sort_by_finance_priority(results: list[dict]) -> list[dict]:
    """Sort search results by financial website priority."""
    return sorted(results, key=lambda r: _get_domain_score(r.get("url", "")), reverse=True)


def _query_key_terms(query: str) -> list:
    """Extract the core words in the query (remove the year/number/quantifier/word for relevance filtering).

    Example:"Thalys June 2026 Production and Sales Report Sales Volume Units" -> ["Thalys", "Production and Sales Express", "Sales volume"]
    """
    tokens = re.split(r"[\s,，、/·\"']+", query.strip())
    terms = []
    for tok in tokens:
        # Remove pure numbers, year and month, percentages, and common quantifiers
        cleaned = re.sub(r"^\d{4}year?\d{0,2}month?\d{0,2}day?$|^\d+%?$|^\d+$", "", tok)
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms


def _filter_irrelevant_results(query: str, results: list) -> list:
    """Filter junk results that have zero relevance to the query.

    Background: Bing China version will downgrade long Chinese queries to single word matching and return"race"word dictionary,
    Irrelevant pages such as Chinese dictionary pollute the LLM context. Filtering rules: Result title (including decoded URL)
    Contain at least one core word, otherwise discard.
    """
    terms = _query_key_terms(query)
    if not terms:
        return results  # Unable to extract core words (such as pure code query), no filtering

    kept = []
    for r in results:
        text = (r.get("title", "") or "") + " " + unquote(r.get("url", "") or "")
        if any(t in text for t in terms):
            kept.append(r)
    dropped = len(results) - len(kept)
    if dropped:
        logger.info("Spam result filtering: Discarding %d results with zero relevance to the query", dropped)
    return kept


def _search_searxng(
    instance_url: str, query: str, language: str, max_results: int
) -> list:
    """Search by SearXNG instance (engine rotation + fuse + relevance filtering).

    No longer run all engines concurrently (which will trigger the anti-crawling CAPTCHA of multiple engines at the same time),
    Instead, they are tried one by one in order of quality: an engine stops when it returns a valid result;
    Engines with no valid results will enter a 5-minute cooling period, and subsequent searches will be automatically rotated.
    """
    global _last_searxng_ts

    # Global throttling: two SearXNG requests are separated by at least _SEARXNG_MIN_INTERVAL seconds
    wait = _SEARXNG_MIN_INTERVAL - (time.time() - _last_searxng_ts)
    if wait > 0:
        time.sleep(wait)
    _last_searxng_ts = time.time()

    now = time.time()
    # Available engines are placed first (after cooling), maintaining quality order with the same priority.
    engines = sorted(
        SEARXNG_ENGINE_ORDER,
        key=lambda e: (_engine_cooldown.get(e, 0) > now, SEARXNG_ENGINE_ORDER.index(e)),
    )
    logger.info("SearXNG Engine order: %s (cooling: %s) ", engines, {
        e: f"{_engine_cooldown[e] - now:.0f}s" for e in _engine_cooldown if _engine_cooldown[e] > now
    } or "无")

    for engine in engines:
        params = {
            "q": query,
            "format": "json",
            "language": language,
            "safesearch": 0,
            "categories": "general",
            "engines": engine,
            "timeout": 6,
        }
        full_url = f"{instance_url.rstrip('/')}/search?{urlencode(params)}"
        try:
            resp = requests.get(
                full_url,
                headers={
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("SearXNG Engine %s query failed: %s", engine, exc)
            _engine_cooldown[engine] = time.time() + 300
            continue

        raw = data.get("results") or []
        unresponsive = [u[0] for u in (data.get("unresponsive_engines") or [])]
        if engine in unresponsive:
            logger.warning("SearXNG Engine %s has been suspended (anti-climb/timeout), cool down for 5 minutes", engine)
            _engine_cooldown[engine] = time.time() + 300
            continue

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "engine": item.get("engine", engine),
                "published_date": item.get("publishedDate", ""),
            }
            for item in raw[: max_results * 2]
        ]
        results = _filter_irrelevant_results(query, results)
        if not results:
            logger.warning(
                "SearXNG Engine %s has no valid results (original %d bars), cool down for 5 minutes", engine, len(raw)
            )
            _engine_cooldown[engine] = time.time() + 300
            continue

        results = _sort_by_finance_priority(results)
        logger.info("SearXNG Hit engine %s: %d valid results", engine, len(results))
        return results[:max_results]

    return []


def _get_baidu_session() -> requests.Session:
    """Get Baidu Search Session."""
    global _baidu_session
    if _baidu_session is None or not _baidu_session.cookies:
        _baidu_session = requests.Session()
        _baidu_session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.baidu.com/",
            }
        )
        try:
            _baidu_session.get("https://www.baidu.com/", timeout=DEFAULT_TIMEOUT)
        except Exception:
            pass
    return _baidu_session


def _search_baidu(query: str, max_results: int) -> list[dict]:
    """Crawling results through Baidu search."""
    session = _get_baidu_session()
    resp = session.get(
        "https://www.baidu.com/s",
        params={"wd": query, "rn": max_results, "ie": "utf-8"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "baidu.com/link" not in href and "baidu.php" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        snippet = ""
        h3 = a.find_parent("h3")
        container = h3.parent.parent if h3 and h3.parent else a.parent
        if container:
            for el in container.find_all(["span", "div", "p"]):
                text = el.get_text(strip=True)
                if len(text) > 30 and text != title and title not in text:
                    snippet = text[:300]
                    break
        results.append({"title": title, "url": href, "content": snippet, "engine": "baidu"})
        if len(results) >= max_results:
            break
    return results


def _format_results(query: str, results: list[dict], engine_used: str) -> str:
    """Format search results into LLM-friendly text."""
    if not results:
        return f"未找到与「{query}」相关的搜索结果。"

    lines = [
        f"Web Search results:{query}",
        f"Search engine:{engine_used}",
        f"共 {len(results)} 条结果\n",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"--- 结果 {i} ---")
        lines.append(f"Title:{r['title']}")
        if r.get("published_date"):
            lines.append(f"Release date:{r['published_date']}")
        lines.append(f"Links:{r['url']}")
        if r["content"]:
            lines.append(f"Summary:{r['content'][:300]}")
        lines.append("")
    return "\n".join(lines)


def run_web_search(
    query: str,
    language: str = "zh",
    max_results: int = 10,
) -> str:
    """Perform a web search."""
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide search keywords."

    errors = []

    # 1) SearXNG (Priority, only use domestic engines)
    searxng_instances = os.getenv("SEARXNG_INSTANCES", "").strip()
    if searxng_instances:
        for instance_url in searxng_instances.split(","):
            instance_url = instance_url.strip()
            if not instance_url:
                continue
            try:
                logger.info("SearXNG Search: %s | query=%s", instance_url, query_clean)
                results = _search_searxng(instance_url, query_clean, language, max_results)
                if results:
                    return _format_results(query_clean, results, f"SearXNG({instance_url})")
            except Exception as exc:
                logger.warning("SearXNG %s failed: %s", instance_url, exc)
                errors.append(f"searxng: {exc}")

    # 2) Baidu search (optional)
    try:
        logger.info("Baidu search: query=%s", query_clean)
        results = _search_baidu(query_clean, max_results)
        if results:
            return _format_results(query_clean, results, "百度")
    except Exception as exc:
        logger.warning("百度搜索失败: %s", exc)
        errors.append(f"baidu: {exc}")

    return f"Web Search failed, all search engines are unavailable. Error details:{'; '.join(errors)}"


@tool
@register_tool(
    tool_id="web_search",
    name="Web 搜索",
    description="Search Internet information through SearXNG meta-search engine (Baidu/360/Sogou/Bing China version engine aggregation). Automatically prioritize results from financial websites (Oriental Fortune, Sina Finance, Juchao Information, etc.). Suitable for obtaining real-time data that is not included in financial reports, such as monthly sales, latest announcements, industry news, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=[
        "web_search", "internet_search", "online_search", "information_search",
        "real_time_info", "current_events", "news_query", "fact_check",
        "market_information", "search_engine", "finance_data",
    ],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=[
        "搜索互联网实时信息",
        "Obtain operating data outside of financial reports (such as monthly sales)",
        "查询最新新闻和公告",
        "事实核查和背景调研",
    ],
    when_to_use="Use it when you need to search the Internet to obtain the latest information, especially real-time data not covered in financial reports (monthly sales, industry trends, latest news, etc.).",
    returns="Return structured search results, including titles, links, and abstracts. Automatically prioritize financial websites and aggregate Baidu/360/Sogou/Bing China version engine results.",
)
def web_search(
    query: Annotated[str, "Search keywords, for example: Cyrus July 2025 sales, or BYD latest monthly sales"],
    max_results: Annotated[int, "Maximum number of results returned, default 10"] = 10,
) -> str:
    """Search Internet information and aggregate the results of multiple search engines, giving priority to financial websites."""
    return run_web_search(query=query, max_results=max_results)
