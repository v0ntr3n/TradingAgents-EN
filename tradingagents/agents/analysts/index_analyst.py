"""
Market/Index Analyst - Compatible Function Interface

To be compatible with existing LangGraph workflows, a functional interface is provided

Support caching mechanism:
- The market analysis results of the same day will be cached (not dependent on specific stocks)
- The cache validity period is 12 hours (the data of the day remains unchanged)
- The cache will be checked first during the next analysis, and if there is a hit, it will be returned directly.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, AIMessage

from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

logger = get_logger("default")

# Cache configuration
INDEX_REPORT_CACHE_TTL_HOURS = 12  # Market analysis report cache validity period (hours)


def _get_cache_manager():
    """Get cache manager (lazy loading to avoid circular imports)"""
    try:
        from tradingagents.dataflows.cache import get_cache
        return get_cache()
    except Exception as e:
        logger.warning(f"⚠️ Unable to get cache manager: {e}")
        return None


def _get_cached_index_report(trade_date: str) -> Optional[str]:
    """
    Get market analysis report from cache

    Args:
        trade_date: transaction date

    Returns:
        The cached report content, returned if there is no hit None
    """
    cache = _get_cache_manager()
    if not cache:
        return None

    try:
        # Market analysis does not rely on specific stocks, using "market" as symbol
        cache_key = cache.find_cached_analysis_report(
            report_type="index_report",
            symbol="market",
            trade_date=trade_date,
            max_age_hours=INDEX_REPORT_CACHE_TTL_HOURS
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Market analysis] hit cache: @ {trade_date}")
                return report
    except Exception as e:
        logger.warning(f"⚠️ Failed to read large disk analysis cache: {e}")

    return None


def _save_index_report_to_cache(trade_date: str, report: str) -> bool:
    """
    Save market analysis report to cache

    Args:
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
            report_type="index_report",
            report_data=report,
            symbol="market",
            trade_date=trade_date
        )
        logger.info(f"💾 [Market analysis] Cached: @ {trade_date}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to save disk analysis cache: {e}")
        return False


def create_index_analyst(llm, toolkit):
    """
    Create market/index analyst node

    Args:
        llm: Language model example
        toolkit: Toolkit Example

    Returns:
        Analyst node function
    """

    @log_analyst_module("index")
    def index_analyst_node(state):
        """
        Market/Index Analyst Node

        Analyze major index trends, market environment and systemic risks

        🔥 Important: This analyst uses"self contained"mode, does not use LangGraph s tool calling mechanism.
        It does all the work in a single call: Get the data + LLM Analysis.
        The returned AIMessage does not contain tool_calls, ensuring that the graph ends immediately.
        """
        trade_date = state.get("trade_date", "")

        # 🔥 Prevent infinite loops: check whether a report has been generated
        existing_report = state.get("index_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🌐 Market Analyst: Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            # Returns an empty update, leaving the state unchanged
            return {}

        # 📦 Check cache: If there is a valid cache, return directly
        cached_report = _get_cached_index_report(trade_date)
        if cached_report:
            logger.info(f"🌐 Market Analyst: Use cached reports ({len(cached_report)} character)")
            final_message = AIMessage(content=cached_report, name="index_analyst")
            return {
                "index_report": cached_report,
                "messages": [final_message],
            }

        logger.info(f"🌐 Market analysts begin to analyze @ {trade_date}")

        try:
            # Import and call market analysis tools
            from core.tools.index_tools import analyze_index
            import asyncio
            import concurrent.futures

            # Run asynchronous functions in thread pool to avoid event loop conflicts
            def run_async_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(analyze_index(trade_date))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                index_data = future.result()

            logger.info(f"✅ Obtaining market data is completed")

            # 🆕 Use LLM to analyze and interpret data
            index_report = _analyze_with_llm(
                llm=llm,
                trade_date=trade_date,
                index_data=index_data,
                state=state
            )

            logger.info(f"✅ The market analysis report is generated")

            # 💾 Save to cache
            _save_index_report_to_cache(trade_date, index_report)

            # 🔥 Return AIMessage instead HumanMessage
            # AIMessage There is no tool_calls attribute (or tool_calls is an empty list),
            # In this way, the should_continue function will detect that there is no tool call and end the graph directly.
            final_message = AIMessage(content=index_report, name="index_analyst")

            # Only return fields that need to be updated (LangGraph will automatically merge)
            return {
                "index_report": index_report,
                "messages": [final_message],
            }

        except Exception as e:
            logger.error(f"❌ Market analysis failed: {e}")
            import traceback
            logger.error(f"❌ detailed error: {traceback.format_exc()}")
            error_msg = f"Market analysis encountered an error: {str(e)}"

            # Return error message
            error_message = AIMessage(content=error_msg, name="index_analyst")

            return {
                "index_report": error_msg,
                "messages": [error_message],
            }

    return index_analyst_node


def _analyze_with_llm(llm, trade_date: str, index_data: str, state: dict) -> str:
    """
    Use LLM to analyze and interpret market data

    Args:
        llm: Language model example
        trade_date: transaction date
        index_data: Market data report
        state: status dictionary

    Returns:
        LLM Generated analysis report
    """
    try:
        # get AgentContext
        ctx = state.get("agent_context") or {}

        # Prepare template variables
        template_variables = {
            "trade_date": trade_date,
        }

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_template_client
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="index_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} agent=analysts/index_analyst")

            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="index_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "index_analyst")
            logger.info(f"✅ [Market Analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.warning(f"⚠️ [Market Analyst] Failed to obtain prompt word from template system: {e}, Use default prompt word")
            system_prompt = _get_default_system_prompt(trade_date)

        # Build a complete analysis request
        analysis_request = f"""{system_prompt}

## 📊 Market data

The following is market analysis data obtained through data tools:

{index_data}

## 🎯 Analysis requirements

Please generate a professional market analysis report based on the above data. The report must contain:

1. **Market overview**
   - Today s performance of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
   - Increases and declines and market sentiment
   - Analysis of changes in turnover

2. **Technical analysis**
   - Judgment of technical forms of each index
   - Key support and pressure levels
   - Moving average system analysis

3. **Market Breadth Analysis**
   - Gain/Loss Ratio and Strength Indicator
   - Degree of sector differentiation
   - Market participation assessment

4. **Risk assessment and research conclusions**
   - Market risk level:🟢low risk / 🟡medium risk / 🔴high risk
   - Market trends:📈rise / 📉fall / ➡️shock
    - Follow-up observation points: Signals that need to be followed based on the current market environment

Please output in Chinese, the analysis must be well-founded, and the conclusion must be clear, but it must not form investment advice or position instructions."""

        # Call LLM to generate analysis reports
        logger.info(f"📤 [Market Analyst] Call LLM to generate analysis reports...")
        response = llm.invoke(analysis_request)

        # Extract response content
        if hasattr(response, 'content'):
            report = response.content
        else:
            report = str(response)

        logger.info(f"✅ [Market Analyst] LLM Analysis report generation completed (length: {len(report)})")
        return report

    except Exception as e:
        logger.error(f"❌ [Market Analyst] LLM Analysis failed: {e}")
        # If LLM analysis fails, return raw data report
        return index_data


def _get_default_system_prompt(trade_date: str) -> str:
    """
    Get the default system prompt word

    Args:
        trade_date: transaction date

    Returns:
        Default system prompt word
    """
    prompt = f"""You are a professional market/index analyst focusing on macro market analysis and systemic risk assessment.

📋 **Analysis date:** {trade_date}

🎯 **Your responsibilities:**
1. Analyze the trends of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
2. Assess the overall market environment and sentiment
3. Identify systemic risks and opportunities
4. Provide market-level research conclusions and risk observations

📊 **Analysis dimensions:**
- Index performance: increase or decrease, turnover
- Market breadth: number of winners and losers, strength and weakness distribution
- Technical aspect: support pressure, trend judgment
- Risk Assessment: Systemic Risk Levels

Please conduct professional analysis based on the data provided and give clear research conclusions, risk tips and follow-up observation points."""
    return apply_compliance_guardrails(prompt, "index_analyst")
