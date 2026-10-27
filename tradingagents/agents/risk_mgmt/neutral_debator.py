import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import template client
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails, build_research_only_closing


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        # Use .get() Secure access to debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        # Use .get() Secure access, supporting the situation where users only select some analysts
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        trader_decision = state.get("trader_investment_plan", "")

        # 📊 Record the length of all input data for performance analysis
        logger.info(f"📊 [Neutral Analyst] Input data length statistics:")
        logger.info(f"  - market_report: {len(market_research_report):,} character (~{len(market_research_report)//4:,} tokens)")
        logger.info(f"  - sentiment_report: {len(sentiment_report):,} character (~{len(sentiment_report)//4:,} tokens)")
        logger.info(f"  - news_report: {len(news_report):,} character (~{len(news_report)//4:,} tokens)")
        logger.info(f"  - fundamentals_report: {len(fundamentals_report):,} character (~{len(fundamentals_report)//4:,} tokens)")
        logger.info(f"  - trader_decision: {len(trader_decision):,} character (~{len(trader_decision)//4:,} tokens)")
        logger.info(f"  - history: {len(history):,} character (~{len(history)//4:,} tokens)")
        logger.info(f"  - current_risky_response: {len(current_risky_response):,} character (~{len(current_risky_response)//4:,} tokens)")
        logger.info(f"  - current_safe_response: {len(current_safe_response):,} character (~{len(current_safe_response)//4:,} tokens)")

        # Calculate the total prompt length
        total_prompt_length = (len(market_research_report) + len(sentiment_report) +
                              len(news_report) + len(fundamentals_report) +
                              len(trader_decision) + len(history) +
                              len(current_risky_response) + len(current_safe_response))
        logger.info(f"  - 🚨 Total prompt length: {total_prompt_length:,} character (~{total_prompt_length//4:,} tokens)")

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
                agent_name="neutral_debator",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=debators/neutral_debator")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="debators",
                agent_name="neutral_debator",
                variables=template_variables,
                preference_id="neutral",
                fallback_prompt=None
            )

            system_prompt = apply_compliance_guardrails(system_prompt, "neutral_debator")
            logger.info(f"✅ [Neutral Risk Analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [Neutral Risk Analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = """As a neutral risk analyst, your role is to provide a balanced perspective, weighing the potential benefits and risks of a trader s decision or plan.

You prioritize a comprehensive approach, assessing upside and downside risks while taking into account broader market trends.

Your job is to challenge activist and security analysts alike, pointing out where each perspective may be too optimistic or too cautious.

Advocate for a more balanced approach, explaining why a moderate risk strategy may offer the best of both worlds.

Please output in conversational mode in Chinese."""
            system_prompt = apply_compliance_guardrails(system_prompt, "neutral_debator")
            logger.warning(f"⚠️ [Neutral Risk Analyst] Use demotion prompts (length: {len(system_prompt)})")

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
Security Analyst s final response:{current_safe_response}

{build_research_only_closing(["Please present your neutral research perspective, emphasizing scenario differences and constraints, but do not formulate a compromise trading proposal."])}"""

        logger.info(f"⏱️ [Neutral Analyst] Start calling LLM...")
        llm_start_time = time.time()

        response = llm.invoke(prompt)

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"⏱️ [Neutral Analyst] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds")
        logger.info(f"📝 [Neutral Analyst] response length: {len(response.content):,} character")

        argument = f"Neutral Analyst: {response.content}"

        new_count = risk_debate_state["count"] + 1
        logger.info(f"⚖️ [Neutral Risk Analyst] Finished speaking, counting: {risk_debate_state['count']} -> {new_count}")

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": argument,
            "count": new_count,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
