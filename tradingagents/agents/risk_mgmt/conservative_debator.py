from langchain_core.messages import AIMessage
import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import template client
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails, build_research_only_closing


def create_safe_debator(llm):
    def safe_node(state) -> dict:
        # Use .get() Secure access to debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        # Use .get() Secure access, supporting the situation where users only select some analysts
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        trader_decision = state.get("trader_investment_plan", "")

        # 📊 Record input data length
        logger.info(f"📊 [Safe Analyst] Input data length statistics:")
        logger.info(f"  - market_report: {len(market_research_report):,} character")
        logger.info(f"  - sentiment_report: {len(sentiment_report):,} character")
        logger.info(f"  - news_report: {len(news_report):,} character")
        logger.info(f"  - fundamentals_report: {len(fundamentals_report):,} character")
        logger.info(f"  - trader_decision: {len(trader_decision):,} character")
        logger.info(f"  - history: {len(history):,} character")
        total_length = (len(market_research_report) + len(sentiment_report) +
                       len(news_report) + len(fundamentals_report) +
                       len(trader_decision) + len(history) +
                       len(current_risky_response) + len(current_neutral_response))
        logger.info(f"  - Total prompt length: {total_length:,} character (~{total_length//4:,} tokens)")

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
                agent_type="debators",
                agent_name="conservative_debator",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "conservative",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=debators/conservative_debator")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="debators",
                agent_name="conservative_debator",
                variables=template_variables,
                preference_id="conservative",
                fallback_prompt=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "conservative_debator")
            logger.info(f"✅ [conservative risk analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [conservative risk analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = """As a Safe/Conservative Risk Analyst, your primary goals are to protect assets, minimize volatility, and ensure stable, reliable growth.

You prioritize stability, security and risk mitigation, carefully assessing potential losses, economic downturns and market fluctuations.

When evaluating a trader s decisions or plans, critically review high-risk elements, noting where decisions may expose the company to undue risk.

Your task is to actively counter the arguments of both activist and neutral analysts, highlighting potential threats that their perspectives may overlook.

Please output in conversational mode in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "conservative_debator")
            logger.warning(f"⚠️ [conservative risk analyst] Use demotion prompts (length: {len(system_prompt)})")

        # Build a complete prompt word
        prompt = f"""{system_prompt}

Here are the traders decisions:
{trader_decision}

Incorporate insights from the following sources into your argument:
Market research report:{market_research_report}
Social Media Sentiment Report:{sentiment_report}
Latest World Affairs Report:{news_report}
Company fundamentals report:{fundamentals_report}

Current conversation history:{history}
Final response from activist analysts:{current_risky_response}
Final response from the neutral analyst:{current_neutral_response}

{build_research_only_closing(["Please present your conservative research perspective, emphasizing vulnerabilities and sources of risk, but do not formulate stop-loss, position reduction, or exit plans."])}"""

        logger.info(f"⏱️ [Safe Analyst] Start calling LLM...")
        llm_start_time = time.time()

        response = llm.invoke(prompt)

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"⏱️ [Safe Analyst] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds")

        argument = f"Safe Analyst: {response.content}"

        new_count = risk_debate_state["count"] + 1
        logger.info(f"🛡️ [conservative risk analyst] Finished speaking, counting: {risk_debate_state['count']} -> {new_count}")

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": new_count,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return safe_node
