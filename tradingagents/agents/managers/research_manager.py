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
    """
    try:
        from core.utils.report_aggregator import get_all_reports
        reports = get_all_reports(state)
        return reports.to_dict()
    except ImportError:
        return {
            "sector_report": state.get("sector_report", ""),
            "index_report": state.get("index_report", ""),
        }


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        # Use .get() Secure access to debate status
        investment_debate_state = state.get("investment_debate_state", {})
        history = investment_debate_state.get("history", "")

        # Get core analysis report
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        # Dynamically obtain extended analysis reports
        extension_reports = _get_extension_reports(state)
        index_report = extension_reports.get("index_report", "")
        sector_report = extension_reports.get("sector_report", "")

        investment_debate_state = state["investment_debate_state"]

        # Integrate all analytical reports (core reports + Extended reporting)
        curr_situation_parts = []
        if index_report:
            curr_situation_parts.append(f" [Macro market analysis]\n{index_report}")
        if sector_report:
            curr_situation_parts.append(f" [Industry sector analysis]\n{sector_report}")
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
                "ticker": state.get("company_of_interest", ""),
                "company_name": state.get("company_of_interest", ""),
                "market_name": "",
                "current_date": state.get("trade_date", ""),
                "start_date": state.get("trade_date", ""),
                "currency_name": "",
                "currency_symbol": "",
                "tool_names": ""
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            tpl_info = get_template_client().get_effective_template(
                agent_type="managers",
                agent_name="research_manager",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=managers/research_manager")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="managers",
                agent_name="research_manager",
                variables=template_variables,
                preference_id="neutral",
                fallback_prompt=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "research_manager")
            logger.info(f"✅ [research manager] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [research manager] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = """As the research manager and debate moderator, your role is to critically evaluate the debate and formulate research conclusions.

Concisely summarize the key arguments from both sides, focusing on the most convincing evidence or reasoning.

Please write all analysis content in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "research_manager")
            logger.warning(f"⚠️ [research manager] Use demotion prompts (length: {len(system_prompt)})")

        # 🆕 Build a macro analysis section
        macro_section = ""
        if index_report:
            macro_section += f"\n [Macro market analysis]\n{index_report}\n"
        if sector_report:
            macro_section += f"\n [Industry sector analysis]\n{sector_report}\n"

        # Build a complete prompt word
        prompt = f"""{system_prompt}

Past reflections and lessons learned:
{past_memory_str}

Comprehensive analysis report:
{macro_section}
Market research:{market_research_report}
Sentiment analysis:{sentiment_report}
News analysis:{news_report}
Fundamental analysis:{fundamentals_report}

Debate history:
{history}

⚠️ When making investment decisions, please consider:
1. Is the market environment favorable (bull market/bear market/concussive)?
2. Is the sector to which it belongs in a rotation hotspot?
3. Fundamental and technical signals for individual stocks

{build_research_only_closing(["Please formulate research conclusions, core differences, main risks and follow-up observation points based on the above information."])}"""

        # 📊 Statistics prompt size
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt statistics:")
        logger.info(f"   - Debate history length: {len(history)} character")
        logger.info(f"   - Total prompt length: {prompt_length} character")
        logger.info(f"   - Estimate input Token: ~{estimated_tokens} tokens")

        # ⏱️ Recording start time
        start_time = time.time()

        response = llm.invoke(prompt)

        # ⏱️ Record end time
        elapsed_time = time.time() - start_time

        # 📊 Statistical response information
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM The call takes time: {elapsed_time:.2f}seconds")
        logger.info(f"📊 [Research Manager] response statistics: {response_length} character, Estimate~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
