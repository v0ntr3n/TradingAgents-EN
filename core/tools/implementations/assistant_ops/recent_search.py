"""Recent information search tool."""

import logging
import os
from datetime import datetime
from typing import Annotated, Any, Optional

from langchain_core.tools import tool
from openai import OpenAI

from core.tools.base import register_tool
from tradingagents.agents.utils.agent_utils import Toolkit

logger = logging.getLogger(__name__)

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_SEARCH_MODEL = os.getenv("DASHSCOPE_SEARCH_MODEL", "qwen3.5-plus")


def _invoke_legacy_tool(tool_func, **kwargs):
    try:
        if hasattr(tool_func, "invoke"):
            return tool_func.invoke(kwargs)
        return tool_func(**kwargs)
    except Exception as exc:
        logger.error("Failed to call recent search underlying tool %s: %s", tool_func, exc)
        return f"近期信息搜索失败: {str(exc)}"


def _resolve_dashscope_runtime_config() -> tuple[Optional[str], str, str]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_DASHSCOPE_BASE_URL)
    model = DEFAULT_SEARCH_MODEL

    if api_key:
        return api_key, base_url, model

    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        provider_doc = db.llm_providers.find_one({"name": "dashscope"}) or {}
        client.close()

        api_key = provider_doc.get("api_key") or api_key
        base_url = provider_doc.get("default_base_url") or base_url
    except Exception as exc:
        logger.warning("Failed to read DashScope configuration, fallback environment variables: %s", exc)

    return api_key, base_url, model


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    pieces: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                pieces.append(str(text).strip())
    return "\n\n".join(piece for piece in pieces if piece).strip()


def _search_with_qwen(query: str, curr_date: str) -> str:
    api_key, base_url, model = _resolve_dashscope_runtime_config()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured and not found in llm_providers DashScope API Key")

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = (
        f"Please search online and confirm recent public information on the following issues:{query}. "
        f"The current date is {curr_date}. "
        "Priority will be given to using the information of the last 30 days; if not, it will fall back to the last 90 days."
        "Please give priority to citing exchange announcements, company announcements, and authoritative financial media."
        "Do not rely on common sense to add historical context and do not infer conclusions that are not directly supported by recent sources."
        "Don t use very likely  High probability This type of vague wording pretends to be a definite conclusion."
        "If the evidence is insufficient to fully confirm, don t just answer Unable to confirm It ends; you should continue to list recent media reports or market information that you can refer to, and indicate that they are not final confirmation."
        "Do not output a timeline table unless there is a recent, verifiable source for each time point."
        "Please output strictly in the following format:"
        " [The latest conclusion] First give the most reliable conclusion that can be confirmed at present. If you are not completely sure, please write clearly Unable to fully confirm at present , However, reference information still needs to be added."
        " [Corroborating basis] List 2-4 corroborating sources, each containing: Date | Source | Title | Information that can be directly confirmed. If not, just write No direct source of confirmation . "
        " [Reference reports] List 2-5 reference sources, such as Caixin, Securities Times, Reuters, Bloomberg, and mainstream financial media reports; each item includes: date | Source | Title | Reporting caliber. and clearly state at the beginning of this paragraph The following is a reference report and may not necessarily be equivalent to final official confirmation. . "
        " [Uncertain points] Clearly write down what evidence is missing, for example Lacking the latest equity disclosure from the Hong Kong Stock Exchange . If not, write None . "
        "If the media clearly reports Cleared  Has dropped below 5%  no longer disclosed , These contents should be entered into [Reference Reports] or [Latest Conclusions], but it must be distinguished whether they are media reports or official confirmations."
    )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "medium",
            }
        ],
        temperature=0.2,
        max_output_tokens=2048,
        top_p=0.9,
        store=False,
    )

    text = _extract_response_text(response)
    if not text:
        raise RuntimeError("百炼搜索返回为空")
    return text


def run_recent_information_search(query: str) -> str:
    """Search recent public information, giving priority to fact-confirmation questions.

    Search source priority:
    1. SearXNG Local instance (fast, about 1-2 seconds; enabled when SEARXNG_INSTANCES is configured)
    2. DashScope Internet search (qwen + web_search_preview, Slower, may timeout)
    3. Google News (full details)
    """
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide the keywords to be searched, for example: BYD, Berkshire, shareholding reduction, shareholding ratio."

    curr_date = datetime.now().strftime("%Y-%m-%d")

    # 1) SearXNG Local search (priority, return within seconds)
    try:
        from core.tools.implementations.assistant_ops.web_search import run_web_search

        searx_result = run_web_search(query_clean, max_results=10)
        if searx_result and not searx_result.startswith("Web 搜索失败"):
            return (
                f"以下是“{query_clean}”的近期联网搜索结果（搜索引擎聚合，按相关性排序）。"
                "Please give priority to answers based on entries with the latest release date and more authoritative sources, and be sure to check the release date.\n\n"
                f"{searx_result}"
            )
        logger.warning("SearXNG No results found in search, return DashScope: %s", query_clean)
    except Exception as exc:
        logger.warning("SearXNG Search failed, fallback DashScope: %s", exc)

    # 2) DashScope Internet search (optional)
    try:
        result = _search_with_qwen(query_clean, curr_date)
        return (
            f"以下是“{query_clean}”的近期联网搜索结果。请优先依据发布时间最新、来源更权威的条目回答。\n\n"
            f"{result}"
        )
    except Exception as exc:
        logger.warning("Bailian s recent search failed and returned Google News: %s", exc)

    # 3) Google News (full details)
    result = _invoke_legacy_tool(Toolkit.get_google_news, query=query_clean, curr_date=curr_date)
    if not result or str(result).startswith("近期信息搜索失败"):
        return f"Recent information search failed:{result}"

    return (
        f"Bailian search is temporarily unavailable, and the following will fall back to recent Google News search results. Please give priority to answers based on items with the latest release date and more authoritative sources.\n\n"
        f"{result}"
    )


@tool
@register_tool(
    tool_id="search_recent_information",
    name="近期信息搜索",
    description="Search public news and recent information within the last 7 days. suitable answer Up to now  Latest  Are there any recent changes?  Need to confirm the latest shareholding ratio/announcement/news These kind of questions. The input should contain a company name, event keyword, or stock symbol.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=["information_search", "recent_news", "web_search", "assistant_ops", "fact_check", "news_query", "current_events", "online_search", "market_information", "real_time_info"],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=["搜索近期公开新闻", "确认最新事实信息", "查询近期公告或事件", "核实最新持股或市场动态"],
    when_to_use="When users ask Up to now  Latest  Are there any recent changes? Or use it when you need to confirm the latest shareholding ratio, announcements, market news, etc.",
    when_not_to_use="It is not suitable for checking the stock price trend of individual stocks, the rise and fall of the market, whether it rebounds/callbacks/breakthroughs and other price trend judgments.——For this type of problem, you must call market data tools (get_stock_market_data_unified / get_technical_indicators / real-time market conditions) to obtain real K-line data. Web search results cannot provide stock price trends; they are not suitable for querying historical price data.",
    returns="Returns search results in text format, including the latest conclusions, corroborating evidence, reference reports and uncertainties.",
)
def search_recent_information(
    query: Annotated[str, "Search keywords, for example: BYD, Berkshire, shareholding reduction, or CATL s latest announcement"],
) -> str:
    """Search recent public information for the latest fact-confirming questions."""
    return run_recent_information_search(query)