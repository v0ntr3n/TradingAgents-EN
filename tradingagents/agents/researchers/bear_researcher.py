from langchain_core.messages import AIMessage
import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import template client
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails, build_research_only_closing


def _get_extension_reports(state: dict) -> dict:
    """
    Dynamically obtain extended analysis reports (sectors, market, etc.)

    Use ReportAggregator to get all extended reports from the registry,
    Returns an empty dictionary if the core module is not available
    """
    try:
        from core.utils.report_aggregator import get_all_reports
        reports = get_all_reports(state)
        return reports.to_dict()
    except ImportError:
        # core Module not available, returns hardcoded extended report
        return {
            "sector_report": state.get("sector_report", ""),
            "index_report": state.get("index_report", ""),
        }


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        # Use .get() Secure access to debate status
        investment_debate_state = state.get("investment_debate_state", {})
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")

        # Get core analysis report
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        # Dynamically obtain extended analysis reports (sectors, market, etc.)
        extension_reports = _get_extension_reports(state)

        # Use unified stock type detection
        ticker = state.get('company_of_interest', 'Unknown')
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']

        # Get company name
        def _get_company_name(ticker_code: str, market_info_dict: dict) -> str:
            """Get company name based on stock code"""
            try:
                if market_info_dict['is_china']:
                    from tradingagents.dataflows.interface import get_china_stock_info_unified
                    stock_info = get_china_stock_info_unified(ticker_code)
                    if stock_info and "Stock name:" in stock_info:
                        name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                        logger.info(f"✅ [short researcher] Successfully obtained Chinese stock names: {ticker_code} -> {name}")
                        return name
                    else:
                        # Downgrade plan
                        try:
                            from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                            info_dict = get_info_dict(ticker_code)
                            if info_dict and info_dict.get('name'):
                                name = info_dict['name']
                                logger.info(f"✅ [short researcher] The downgrade plan successfully obtained the stock name: {ticker_code} -> {name}")
                                return name
                        except Exception as e:
                            logger.error(f"❌ [short researcher] Downgrade plan also failed: {e}")
                elif market_info_dict['is_hk']:
                    try:
                        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                        name = get_hk_company_name_improved(ticker_code)
                        return name
                    except Exception:
                        clean_ticker = ticker_code.replace('.HK', '').replace('.hk', '')
                        return f"Hong Kong stocks{clean_ticker}"
                elif market_info_dict['is_us']:
                    us_stock_names = {
                        'AAPL': 'apple inc.', 'TSLA': 'Tesla', 'NVDA': 'NVIDIA',
                        'MSFT': 'Microsoft', 'GOOGL': 'Google', 'AMZN': 'Amazon',
                        'META': 'Meta', 'NFLX': 'Netflix'
                    }
                    return us_stock_names.get(ticker_code.upper(), f"US stocks{ticker_code}")
            except Exception as e:
                logger.error(f"❌ [short researcher] Failed to get company name: {e}")
            return f"Stock code{ticker_code}"

        company_name = _get_company_name(ticker, market_info)
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        # Integrate all analytical reports (core reports + Extended reporting)
        curr_situation_parts = []

        # First add extended reports (market, sector, etc., sorted by priority)
        index_report = extension_reports.get("index_report", "")
        sector_report = extension_reports.get("sector_report", "")
        if index_report:
            curr_situation_parts.append(f" [Macro market analysis]\n{index_report}")
        if sector_report:
            curr_situation_parts.append(f" [Industry sector analysis]\n{sector_report}")

        # Add core reports
        curr_situation_parts.extend([market_research_report, sentiment_report, news_report, fundamentals_report])
        curr_situation = "\n\n".join([p for p in curr_situation_parts if p])

        # Security check: Make sure memory is not None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory If None, skip historical memory retrieval.")
            past_memories = []

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": ticker,
                "company_name": company_name,
                "market_name": market_info['market_name'],
                "current_date": state.get("trade_date", ""),
                "start_date": state.get("trade_date", ""),
                "currency_name": currency,
                "currency_symbol": currency_symbol,
                "tool_names": ""
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            tpl_info = get_template_client().get_effective_template(
                agent_type="researchers",
                agent_name="bear_researcher",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=researchers/bear_researcher")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="researchers",
                agent_name="bear_researcher",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "bear_researcher")
            logger.info(f"✅ [short researcher] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [short researcher] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = f"""You are a bearish researcher responsible for analyzing stocks {company_name} (Stock code:{ticker}) Existing risks and disadvantages.

⚠️ Important reminder: The current analysis is {market_info['market_name']}, For all prices and estimates please use {currency} ({currency_symbol}) as a unit.
⚠️ In your analysis, always use the company name"{company_name}"instead of stock code"{ticker}"Come call this company.

Your goal is to present a sound argument for your research, highlighting risks, challenges, and negative indicators.

Please answer in Chinese, focusing on the following aspects:
- Risks and Challenges: Highlight factors such as market saturation, financial instability, or macroeconomic threats that could hinder stock performance
- Competitive Weaknesses: Highlights vulnerabilities such as weaker market position, reduced innovation, or threats from competitors
- Negative Indicators: Use financial data, market trends, or evidence of recent bad news to support your position
- Countering Bullish Arguments: Critically Analyze Bullish Arguments Using Concrete Data and Sound Reasoning

Please make sure all answers are in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "bear_researcher")
            logger.warning(f"⚠️ [short researcher] Use demotion prompts (length: {len(system_prompt)})")

        # Build a complete prompt word
        prompt = f"""{system_prompt}

Available resources:
Market research report:{market_research_report}
Social Media Sentiment Report:{sentiment_report}
Latest world affairs news:{news_report}
Company fundamentals report:{fundamentals_report}
Debate dialogue history:{history}
Final bullish thesis:{current_response}
Reflections and lessons learned from similar situations:{past_memory_str}

{build_research_only_closing(["Please use this information to provide bearish research arguments, counter bullish claims, and participate in dynamic debates."])}"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_count = investment_debate_state["count"] + 1
        logger.info(f"🐻 [short researcher] Finished speaking, counting: {investment_debate_state['count']} -> {new_count}")

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": new_count,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
