import functools
import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import template client
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails, build_research_only_closing


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state.get("company_of_interest", "")
        investment_plan = state.get("investment_plan", "")
        # Use .get() Secure access, supporting the situation where users only select some analysts
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")
        # 🆕 Added new sector and market analysis reports
        sector_report = state.get("sector_report", "")
        index_report = state.get("index_report", "")

        # Use unified stock type detection
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(company_name)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        # Determine currency unit based on stock type
        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.debug("💰 [DEBUG] ===== Trader node starts =====")
        logger.debug(f"💰 [DEBUG] Trader detects stock type: {company_name} -> {market_info['market_name']}, Currency: {currency}")
        logger.debug(f"💰 [DEBUG] currency symbol: {currency_symbol}")
        logger.debug(f"💰 [DEBUG] Market details: China A shares={is_china}, Hong Kong stocks={is_hk}, US stocks={is_us}")
        logger.debug(f"💰 [DEBUG] Fundamental report length: {len(fundamentals_report)}")
        logger.debug(f"💰 [DEBUG] Section report length: {len(sector_report)}, Market report length: {len(index_report)}")

        # 🆕 Integrate all analysis reports (including new sector and market analysis)
        curr_situation_parts = [market_research_report, sentiment_report, news_report, fundamentals_report]
        if index_report:
            curr_situation_parts.insert(0, f" [Macro market analysis]\n{index_report}")
        if sector_report:
            curr_situation_parts.insert(1 if index_report else 0, f" [Industry sector analysis]\n{sector_report}")
        curr_situation = "\n\n".join(curr_situation_parts)

        # Check if memory is available
        if memory is not None:
            logger.warning(f"⚠️ [DEBUG] memory Available, get historical memory")
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            past_memory_str = ""
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            logger.warning(f"⚠️ [DEBUG] memory If None, skip historical memory retrieval.")
            past_memories = []
            past_memory_str = "There is currently no historical memory data for reference."

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": company_name,
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
                agent_type="trader",
                agent_name="trader",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=trader/trader")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="trader",
                agent_name="trader",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "trader")
            logger.info(f"✅ [trader] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [trader] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = f"""You are a research aggregator responsible for integrating market data and forming research summaries.

⚠️ Important reminder: The stock code currently analyzed is {company_name}, Please use the correct currency unit:{currency} ({currency_symbol}) 

Please include the following key information in your analysis:
1. **Research summary**: Key conclusions from current evidence
2. **key signal**: Core variables and changes that affect judgment
3. **Risk warning**: Uncertainties that need to be focused on right now
4. **Watch list**: Data or events that need to be tracked later
5. **detailed reasoning**: Specific reasons to support the study s conclusions

Please write the analysis content in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "trader")
            logger.warning(f"⚠️ [trader] Use demotion prompts (length: {len(system_prompt)})")

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""{system_prompt}

Past Trading Reflections and Lessons Learned:
{past_memory_str}

{build_research_only_closing(["Please output a research summary, key signals, risk tips and watch list based on the above information."])}""",
            },
            context,
        ]

        logger.debug(f"💰 [DEBUG] Prepare to call LLM, the system prompts to include currency: {currency}")
        logger.debug(f"💰 [DEBUG] Key parts of system prompts: target price({currency})")

        result = llm.invoke(messages)

        logger.debug(f"💰 [DEBUG] LLM Call completed")
        logger.debug(f"💰 [DEBUG] Trader reply length: {len(result.content)}")
        logger.debug(f"💰 [DEBUG] Trader s first 500 characters of reply: {result.content[:500]}...")
        logger.debug(f"💰 [DEBUG] ===== Trader node ends =====")

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
