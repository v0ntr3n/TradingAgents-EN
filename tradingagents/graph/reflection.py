# TradingAgents/graph/reflection.py

from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
)


class Reflector:
    """Handles reflection on decisions and updating memory."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        """Get the system prompt for reflection."""
        return """
You are an expert financial analyst tasked with reviewing trading decisions/analysis and providing a comprehensive, step-by-step analysis. 
Your goal is to deliver detailed insights into investment decisions and highlight opportunities for improvement, adhering strictly to the following guidelines:

1. Reasoning:
   - For each trading decision, determine whether it was correct or incorrect. A correct decision results in an increase in returns, while an incorrect decision does the opposite.
   - Analyze the contributing factors to each success or mistake. Consider:
     - Market intelligence.
     - Technical indicators.
     - Technical signals.
     - Price movement analysis.
     - Overall market data analysis 
     - News analysis.
     - Social media and sentiment analysis.
     - Fundamental data analysis.
     - Weight the importance of each factor in the decision-making process.

2. Improvement:
   - For any incorrect decisions, propose revisions to maximize returns.
   - Provide a detailed list of corrective actions or improvements, including specific recommendations (e.g., changing a decision from HOLD to BUY on a particular date).

3. Summary:
   - Summarize the lessons learned from the successes and mistakes.
   - Highlight how these lessons can be adapted for future trading scenarios and draw connections between similar situations to apply the knowledge gained.

4. Query:
   - Extract key insights from the summary into a concise sentence of no more than 1000 tokens.
   - Ensure the condensed sentence captures the essence of the lessons and reasoning for easy reference.

Adhere strictly to these instructions, and ensure your output is detailed, accurate, and actionable. You will also be given objective descriptions of the market from a price movements, technical indicator, news, and sentiment perspective to provide more context for your analysis.
"""

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """Extract the current market situation from the state."""
        # Use .get() Secure access, supporting the situation where users only select some analysts
        curr_market_report = current_state.get("market_report", "")
        curr_sentiment_report = current_state.get("sentiment_report", "")
        curr_news_report = current_state.get("news_report", "")
        curr_fundamentals_report = current_state.get("fundamentals_report", "")

        return f"{curr_market_report}\n\n{curr_sentiment_report}\n\n{curr_news_report}\n\n{curr_fundamentals_report}"

    def _extract_manager_action(self, current_state: Dict[str, Any]) -> str:
        """Extract executed manager action ('buy', 'sell', 'hold') from state."""
        for key in ("final_trade_decision", "trader_investment_plan", "action"):
            val = current_state.get(key)
            if isinstance(val, dict):
                act = str(val.get("action") or "").lower().strip()
                if act in ("buy", "sell", "hold"):
                    return act
            elif isinstance(val, str) and val:
                low = val.lower()
                if "buy" in low or "long" in low:
                    return "buy"
                elif "sell" in low or "short" in low:
                    return "sell"
                elif "hold" in low:
                    return "hold"

        risk_debate = current_state.get("risk_debate_state")
        if isinstance(risk_debate, dict):
            judge = str(risk_debate.get("judge_decision") or "").lower()
            if "buy" in judge or "long" in judge:
                return "buy"
            elif "sell" in judge or "short" in judge:
                return "sell"
            elif "hold" in judge:
                return "hold"

        invest_debate = current_state.get("investment_debate_state")
        if isinstance(invest_debate, dict):
            judge = str(invest_debate.get("judge_decision") or "").lower()
            if "buy" in judge or "long" in judge:
                return "buy"
            elif "sell" in judge or "short" in judge:
                return "sell"
            elif "hold" in judge:
                return "hold"

        return "hold"

    def _reflect_on_component(
        self,
        component_type: str,
        report: str,
        situation: str,
        returns_losses,
        attribution_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate reflection for a component with counterfactual credit assignment."""
        try:
            ret_val = float(returns_losses)
        except (ValueError, TypeError):
            ret_val = 0.0

        if attribution_context:
            quadrant = attribution_context.get("quadrant", "Q1_Vindicated_Followed")
            score = float(attribution_context.get("attribution_score", ret_val))
            directive = attribution_context.get("directive", "")
            stance_val = attribution_context.get("agent_stance", 0.0)
            stance_desc = "BULL/BUY" if stance_val > 0 else ("BEAR/SELL" if stance_val < 0 else "NEUTRAL/HOLD")
            mgr_act = attribution_context.get("manager_action", "hold")

            human_prompt = (
                f"=== Counterfactual Credit Assignment ===\n"
                f"- Component: {component_type} (Stance: {stance_desc})\n"
                f"- Realized Trade Return: {ret_val:+.2%}\n"
                f"- Manager Action: {mgr_act}\n"
                f"- Status: {quadrant}\n"
                f"- Attribution Score: {score:+.3f}\n"
                f"- Directive: {directive}\n\n"
                f"=== Analysis/Decision under Review ===\n{report}\n\n"
                f"=== Objective Market Reports for Reference ===\n{situation}"
            )
        else:
            human_prompt = (
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}"
            )

        messages = [
            ("system", self.reflection_system_prompt),
            ("human", human_prompt),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        return result

    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory):
        """Reflect on bull researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state.get("investment_debate_state", {}).get("bull_history", "")
        mgr_action = self._extract_manager_action(current_state)

        conf = 0.8
        posteriors = current_state.get("analyst_posteriors") or {}
        if "bull_researcher_v2" in posteriors and isinstance(posteriors["bull_researcher_v2"], dict):
            conf = float(posteriors["bull_researcher_v2"].get("confidence", 0.8))

        attr = calculate_counterfactual_attribution(
            agent_stance=+1.0,
            realized_return=float(returns_losses),
            manager_action=mgr_action,
            agent_confidence=conf,
        )

        result = self._reflect_on_component(
            "BULL", bull_debate_history, situation, returns_losses, attribution_context=attr
        )
        bull_memory.add_situations([(situation, result)])
        return result

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory):
        """Reflect on bear researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state.get("investment_debate_state", {}).get("bear_history", "")
        mgr_action = self._extract_manager_action(current_state)

        conf = 0.8
        posteriors = current_state.get("analyst_posteriors") or {}
        if "bear_researcher_v2" in posteriors and isinstance(posteriors["bear_researcher_v2"], dict):
            conf = float(posteriors["bear_researcher_v2"].get("confidence", 0.8))

        attr = calculate_counterfactual_attribution(
            agent_stance=-1.0,
            realized_return=float(returns_losses),
            manager_action=mgr_action,
            agent_confidence=conf,
        )

        result = self._reflect_on_component(
            "BEAR", bear_debate_history, situation, returns_losses, attribution_context=attr
        )
        bear_memory.add_situations([(situation, result)])
        return result

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state.get("trader_investment_plan", "")
        mgr_action = self._extract_manager_action(current_state)

        low = trader_decision.lower() if isinstance(trader_decision, str) else ""
        if "buy" in low or "long" in low:
            stance = +1.0
        elif "sell" in low or "short" in low:
            stance = -1.0
        else:
            stance = 0.0

        attr = calculate_counterfactual_attribution(
            agent_stance=stance,
            realized_return=float(returns_losses),
            manager_action=mgr_action,
            agent_confidence=0.8,
        )

        result = self._reflect_on_component(
            "TRADER", trader_decision, situation, returns_losses, attribution_context=attr
        )
        trader_memory.add_situations([(situation, result)])
        return result

    def reflect_invest_judge(self, current_state, returns_losses, invest_judge_memory):
        """Reflect on investment judge's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state.get("investment_debate_state", {}).get("judge_decision", "")
        mgr_action = self._extract_manager_action(current_state)

        low = judge_decision.lower() if isinstance(judge_decision, str) else ""
        if "buy" in low or "long" in low:
            stance = +1.0
        elif "sell" in low or "short" in low:
            stance = -1.0
        else:
            stance = 0.0

        attr = calculate_counterfactual_attribution(
            agent_stance=stance,
            realized_return=float(returns_losses),
            manager_action=mgr_action,
            agent_confidence=0.85,
        )

        result = self._reflect_on_component(
            "INVEST JUDGE", judge_decision, situation, returns_losses, attribution_context=attr
        )
        invest_judge_memory.add_situations([(situation, result)])
        return result

    def reflect_risk_manager(self, current_state, returns_losses, risk_manager_memory):
        """Reflect on risk manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state.get("risk_debate_state", {}).get("judge_decision", "")
        mgr_action = self._extract_manager_action(current_state)

        low = judge_decision.lower() if isinstance(judge_decision, str) else ""
        if "buy" in low or "long" in low:
            stance = +1.0
        elif "sell" in low or "short" in low:
            stance = -1.0
        else:
            stance = 0.0

        attr = calculate_counterfactual_attribution(
            agent_stance=stance,
            realized_return=float(returns_losses),
            manager_action=mgr_action,
            agent_confidence=0.85,
        )

        result = self._reflect_on_component(
            "RISK JUDGE", judge_decision, situation, returns_losses, attribution_context=attr
        )
        risk_manager_memory.add_situations([(situation, result)])
        return result
