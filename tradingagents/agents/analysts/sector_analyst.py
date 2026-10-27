"""
Industry/sector analyst - compatible function interface

To be compatible with existing LangGraph workflows, a functional interface is provided

⚠️ Important: Industry reports do not support caching
- Industry reports are analyzed based on specific stocks and include the code and name of the stock.
- If industry reports are cached, the symbols and names of other stocks will be incorrectly used when analyzing other stocks in the same industry.
- Therefore, industry reports must be regenerated for each analysis and caching cannot be used
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, AIMessage

from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

logger = get_logger("default")

# Cache configuration (deprecated)
# ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
SECTOR_REPORT_CACHE_TTL_HOURS = 12  # Sector analysis report cache validity period (hours) - obsolete and no longer used


def _get_cache_manager():
    """Get cache manager (lazy loading to avoid circular imports)"""
    try:
        from tradingagents.dataflows.cache import get_cache
        return get_cache()
    except Exception as e:
        logger.warning(f"⚠️ Unable to get cache manager: {e}")
        return None


def _get_cached_sector_report(ticker: str, trade_date: str) -> Optional[str]:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    
    Args:
        ticker: Stock code
        trade_date: transaction date

    Returns:
        The cached report content, returned if there is no hit None
    """
    cache = _get_cache_manager()
    if not cache:
        return None

    try:
        cache_key = cache.find_cached_analysis_report(
            report_type="sector_report",
            symbol=ticker,
            trade_date=trade_date,
            max_age_hours=SECTOR_REPORT_CACHE_TTL_HOURS
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Sector analysis] hit cache: {ticker} @ {trade_date}")
                return report
    except Exception as e:
        logger.warning(f"⚠️ Failed to read section analysis cache: {e}")

    return None


def _save_sector_report_to_cache(ticker: str, trade_date: str, report: str) -> bool:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    
    Args:
        ticker: Stock code
        trade_date: transaction date
        report: Report content

    Returns:
        Is the save successful?
    """
    cache = _get_cache_manager()
    if not cache:
        return False

    try:
        cache.save_analysis_report(
            report_type="sector_report",
            report_data=report,
            symbol=ticker,
            trade_date=trade_date
        )
        logger.info(f"💾 [Sector analysis] Cached: {ticker} @ {trade_date}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to save section analysis cache: {e}")
        return False


def create_sector_analyst(llm, toolkit):
    """
    Create an industry/sector analyst node

    Args:
        llm: Language model example
        toolkit: Toolkit Example

    Returns:
        Analyst node function
    """

    @log_analyst_module("sector")
    def sector_analyst_node(state):
        """
        Industry/sector analyst node

        Analyze industry trends, sector rotations and peer comparisons

        🔥 Important: This analyst uses"self contained"mode, does not use LangGraph s tool calling mechanism.
        It does all the work in a single call: Get the data + LLM Analysis.
        The returned AIMessage does not contain tool_calls, ensuring that the graph ends immediately.
        """
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")

        # 🔍 Debug log: print current status
        logger.info(f"🔍 [sector_analyst] Node is called")
        logger.info(f"🔍 [sector_analyst] ticker={ticker}, trade_date={trade_date}")
        logger.info(f"🔍 [sector_analyst] Current number of messages: {len(state.get('messages', []))}")
        logger.info(f"🔍 [sector_analyst] Current sector_report length: {len(state.get('sector_report', ''))}")
        logger.info(f"🔍 [sector_analyst] current sector_tool_call_count: {state.get('sector_tool_call_count', 0)}")

        # Print the information of the last message
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            logger.info(f"🔍 [sector_analyst] last message type: {type(last_msg).__name__}")
            if hasattr(last_msg, 'tool_calls'):
                logger.info(f"🔍 [sector_analyst] last message tool_calls: {last_msg.tool_calls}")
            if hasattr(last_msg, 'name'):
                logger.info(f"🔍 [sector_analyst] last message name: {last_msg.name}")

        # 🔥 Prevent infinite loops: check whether a report has been generated
        existing_report = state.get("sector_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🏭 Sector Analyst: Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            # Returns an empty update, leaving the state unchanged
            return {}

        # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
        # Therefore, each analysis must be regenerated and caching cannot be used
        logger.info(f"🏭 Sector Analyst: Skip the cache check (industry reports do not support caching) and directly generate a new report")

        logger.info(f"🏭 Sector analysts begin to analyze: {ticker} @ {trade_date}")

        try:
            # Import and call sector analysis tools
            from core.tools.sector_tools import analyze_sector
            import asyncio
            import concurrent.futures

            # Run asynchronous functions in thread pool to avoid event loop conflicts
            def run_async_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(analyze_sector(ticker, trade_date))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                sector_data = future.result()

            logger.info(f"✅ Sector data acquisition completed: {ticker}")

            # 🆕 Use LLM to analyze and interpret data
            sector_report = _analyze_with_llm(
                llm=llm,
                ticker=ticker,
                trade_date=trade_date,
                sector_data=sector_data,
                state=state
            )

            logger.info(f"✅ Sector analysis report generation completed: {ticker}")

            # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
            # Therefore, it is not saved to cache

            # 🔥 Return AIMessage instead HumanMessage
            # AIMessage There is no tool_calls attribute (or tool_calls is an empty list),
            # In this way, the should_continue function will detect that there is no tool call and end the graph directly.
            final_message = AIMessage(content=sector_report, name="sector_analyst")

            # Only return fields that need to be updated (LangGraph will automatically merge)
            return {
                "sector_report": sector_report,
                "messages": [final_message],
            }

        except Exception as e:
            logger.error(f"❌ Sector analysis failed: {e}")
            import traceback
            logger.error(f"❌ detailed error: {traceback.format_exc()}")
            error_msg = f"Sector analysis encountered an error: {str(e)}"

            # Return error message
            error_message = AIMessage(content=error_msg, name="sector_analyst")

            return {
                "sector_report": error_msg,
                "messages": [error_message],
            }

    return sector_analyst_node


def _analyze_with_llm(llm, ticker: str, trade_date: str, sector_data: str, state: dict) -> str:
    """
    Use LLM to analyze and interpret sector data

    Args:
        llm: Language model example
        ticker: Stock code
        trade_date: transaction date
        sector_data: Sector data report
        state: status dictionary

    Returns:
        LLM Generated analysis report
    """
    try:
        # get AgentContext
        ctx = state.get("agent_context") or {}

        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "trade_date": trade_date,
        }

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_template_client
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="sector_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} agent=analysts/sector_analyst")

            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="sector_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "sector_analyst")
            logger.info(f"✅ [Sector Analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.warning(f"⚠️ [Sector Analyst] Failed to obtain prompt word from template system: {e}, Use default prompt word")
            system_prompt = _get_default_system_prompt(ticker, trade_date)

        # Build a complete analysis request
        analysis_request = f"""{system_prompt}

## 📊 Sector data

The following is sector analysis data obtained through data tools:

{sector_data}

## 🎯 Analysis requirements

Please generate a professional sector analysis report based on the above data. The report must contain:

1. **Sector Performance Summary**
   - The main sector to which the target stock belongs
   - Recent performance evaluation of each sector
   - The strength of the sector relative to the broader market

2. **Sector rotation analysis**
   - Identification of current market hot sectors
   - Determining the trend of capital flow
   - Judgment of plate rotation stage

3. **Comparative evaluation with peers**
   - The position of the target stock in the industry
   - Valuation level evaluation (PE/PB)
   - The gap with industry leaders

4. **Research conclusion**
   - Sector popularity assessment:🔥Popular / ⚡Average / ❄️Unpopular
   - Funding direction:💰inflow / 💸flow out / ⚖️balance
   - Individual stock position:👑faucet / 🥈Second echelon / 🥉follow
    - Follow-up observation points: Signals that need to be followed based on sector trends

Please output in Chinese, the analysis must be well-founded, and the conclusion must be clear, but it must not form investment recommendations or operating instructions."""

        # Call LLM to generate analysis reports
        logger.info(f"📤 [Sector Analyst] Call LLM to generate analysis reports...")
        response = llm.invoke(analysis_request)

        # Extract response content
        if hasattr(response, 'content'):
            report = response.content
        else:
            report = str(response)

        logger.info(f"✅ [Sector Analyst] LLM Analysis report generation completed (length: {len(report)})")
        return report

    except Exception as e:
        logger.error(f"❌ [Sector Analyst] LLM Analysis failed: {e}")
        # If LLM analysis fails, return raw data report
        return sector_data


def _get_default_system_prompt(ticker: str, trade_date: str) -> str:
    """
    Get the default system prompt word

    Args:
        ticker: Stock code
        trade_date: transaction date

    Returns:
        Default system prompt word
    """
    prompt = f"""You are a professional industry/sector analyst, focusing on sector rotation and peer comparison analysis.

📋 **Analysis objects:**
- Stock code:{ticker}
- Analysis date:{trade_date}

🎯 **Your responsibilities:**
1. Analyze the overall performance of the industry to which the target stock belongs
2. Identify sector rotation trends and capital flows
3. Conduct comparative analysis of competitors in the same industry
4. Evaluate the position and valuation level of individual stocks in the industry

📊 **Analysis dimensions:**
- Sector performance: rise and fall, relative strength
- Fund flow direction: the main direction of capital entry and exit
- Valuation comparison: PE/PB relative to industry level
- Industry status: market value ranking, leading position

Please conduct professional analysis based on the data provided and give clear research conclusions, risk tips and follow-up observation points."""
    return apply_compliance_guardrails(prompt, "sector_analyst")
