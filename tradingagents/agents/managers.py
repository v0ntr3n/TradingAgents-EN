from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['research_manager', 'risk_manager']:
    _sys.modules[f"tradingagents.agents.managers.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === research_manager.py ===
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
            logger.warning("⚠️ [DEBUG] memory If None, skip historical memory retrieval.")
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

        logger.info("📊 [Research Manager] Prompt statistics:")
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

# === risk_manager.py ===
import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import template client
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails, build_research_only_closing


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state.get("company_of_interest", "")

        # Use .get() Secure access to debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        # Use .get() Secure access, supporting the situation where users only select some analysts
        market_research_report = state.get("market_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")
        sentiment_report = state.get("sentiment_report", "")
        trader_plan = state.get("investment_plan", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # Security check: Make sure memory is not None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning("⚠️ [DEBUG] memory If None, skip historical memory retrieval.")
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
                agent_name="risk_manager",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=managers/risk_manager")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="managers",
                agent_name="risk_manager",
                variables=template_variables,
                preference_id="neutral",
                fallback_prompt=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "risk_manager")
            logger.info(f"✅ [risk manager] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [risk manager] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = """As chair of the Risk Management Committee and debate moderator, your goal is to evaluate the debates of three risk analysts and formulate research opinions from a risk governance perspective.

Summarize key arguments, provide detailed reasoning, and adjust trader plans based on analyst insights.

Learn from past mistakes to ensure every decision leads to better results.

Please write all analysis content in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "risk_manager")
            logger.warning(f"⚠️ [risk manager] Use demotion prompts (length: {len(system_prompt)})")

        # Build a complete prompt word
        prompt = f"""{system_prompt}

Trader s original plan:
{trader_plan}

Past reflections and lessons learned:
{past_memory_str}

Analyst Debate History:
{history}

{build_research_only_closing(["Please output the risk summary, main disputes, constraints, information gaps and follow-up observation points based on the above information."])}"""

        # 📊 Statistics prompt size
        prompt_length = len(prompt)
        # Rough estimate of the number of tokens (about 1.5-2 characters/token for Chinese, about 4 characters/token for English)
        estimated_tokens = int(prompt_length / 1.8)  # conservative estimate

        logger.info("📊 [Risk Manager] Prompt statistics:")
        logger.info(f"   - Debate history length: {len(history)} character")
        logger.info(f"   - Trader plan length: {len(trader_plan)} character")
        logger.info(f"   - historical memory length: {len(past_memory_str)} character")
        logger.info(f"   - Total prompt length: {prompt_length} character")
        logger.info(f"   - Estimate input Token: ~{estimated_tokens} tokens")

        # Enhanced LLM calling, including error handling and retry mechanism
        max_retries = 3
        retry_count = 0
        response_content = ""

        while retry_count < max_retries:
            try:
                logger.info(f"🔄 [Risk Manager] Call LLM to generate trading decisions (try {retry_count + 1}/{max_retries})")

                # ⏱️ Recording start time
                start_time = time.time()

                response = llm.invoke(prompt)

                # ⏱️ Record end time
                elapsed_time = time.time() - start_time
                
                if response and hasattr(response, 'content') and response.content:
                    response_content = response.content.strip()

                    # 📊 Statistical response information
                    response_length = len(response_content)
                    estimated_output_tokens = int(response_length / 1.8)

                    # Try to get actual token usage (if LLM returned)
                    usage_info = ""
                    if hasattr(response, 'response_metadata') and response.response_metadata:
                        metadata = response.response_metadata
                        if 'token_usage' in metadata:
                            token_usage = metadata['token_usage']
                            usage_info = f", actual Token: input={token_usage.get('prompt_tokens', 'N/A')} output={token_usage.get('completion_tokens', 'N/A')} total={token_usage.get('total_tokens', 'N/A')}"

                    logger.info(f"⏱️ [Risk Manager] LLM The call takes time: {elapsed_time:.2f}seconds")
                    logger.info(f"📊 [Risk Manager] response statistics: {response_length} character, Estimate~{estimated_output_tokens} tokens{usage_info}")

                    if len(response_content) > 10:  # Make sure responses have substance
                        logger.info("✅ [Risk Manager] LLM Call successful")
                        break
                    else:
                        logger.warning(f"⚠️ [Risk Manager] LLM Response content is too short: {len(response_content)} character")
                        response_content = ""
                else:
                    logger.warning("⚠️ [Risk Manager] LLM Response is empty or invalid")
                    response_content = ""

            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(f"❌ [Risk Manager] LLM call failed (try {retry_count + 1}): {str(e)}")
                logger.error(f"⏱️ [Risk Manager] Time taken before failure: {elapsed_time:.2f}seconds")
                response_content = ""
            
            retry_count += 1
            if retry_count < max_retries and not response_content:
                logger.info("🔄 [Risk Manager] Wait 2 seconds and try again...")
                time.sleep(2)
        
        # If all retries fail, generate a default decision
        if not response_content:
            logger.error("❌ [Risk Manager] All LLM call attempts fail, using default decision")
            response_content = f"""**Risk summary**

Detailed analysis cannot be generated for technical reasons and currently only the {company_name} risk observation.

**main controversy**
1. There is insufficient market information and it is temporarily impossible to confirm the direction of key differences.
2. The available public information is insufficient to support more detailed research conclusions.

**Follow-up observation points**
- Continue to track market dynamics and changes in company fundamentals
- Supplement financial and operating data before reviewing
- Pay attention to major announcements, industry changes and macro-environmental disturbances

Note: This is the system s default research observation and does not constitute any trading advice."""

        new_risk_debate_state = {
            "judge_decision": response_content,
            "history": risk_debate_state.get("history", ""),
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state.get("current_risky_response", ""),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state.get("count", 0),
        }

        logger.info(f"📋 [Risk Manager] Final decision generation is completed, content length: {len(response_content)} character")

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response_content,  # ✅ recovery: output final_trade_decision
        }

    return risk_manager_node
