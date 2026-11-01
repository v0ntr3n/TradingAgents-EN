# TradingAgents/graph/reflection.py

from typing import Dict, Any
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = object

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")



def compute_counterfactual_attribution(
    state: Dict[str, Any],
    realized_return_pct: float,
    threshold_pct: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute counterfactual credit assignment for each agent based on its directional
    prediction/stance, the system's final decision, and the realized return.
    Labels:
      - "correct_driver": Agent predicted true direction AND final decision followed agent.
      - "overridden_correct": Agent predicted true direction BUT final decision ignored agent.
      - "false_driver": Agent predicted wrong direction AND final decision followed agent.
      - "correct_dissent_ignored": Risk/Bear agent warned of downside, downside occurred, warning ignored.
      - "neutral": Neutral stance or flat market return.
    """
    if realized_return_pct > threshold_pct:
        true_dir = "buy"
    elif realized_return_pct < -threshold_pct:
        true_dir = "sell"
    else:
        true_dir = "hold"

    final_action = str(state.get("final_action") or state.get("final_trade_decision") or "hold").lower()
    if "buy" in final_action or "optimistic" in final_action:
        sys_dir = "buy"
    elif "sell" in final_action or "cautious" in final_action:
        sys_dir = "sell"
    else:
        sys_dir = "hold"

    attributions: Dict[str, Dict[str, Any]] = {}
    posteriors = state.get("analyst_posteriors") or {}

    for agent_id, post in posteriors.items():
        p_o = float(post.get("p_optimistic", 1.0 / 3.0))
        p_c = float(post.get("p_cautious", 1.0 / 3.0))
        if p_o > p_c + 0.05:
            agent_dir = "buy"
        elif p_c > p_o + 0.05:
            agent_dir = "sell"
        else:
            agent_dir = "hold"

        if true_dir == "hold" or agent_dir == "hold":
            role = "neutral"
            score = 0.0
        elif agent_dir == true_dir and sys_dir == agent_dir:
            role = "correct_driver"
            score = 1.0
        elif agent_dir == true_dir and sys_dir != agent_dir:
            role = "overridden_correct"
            score = 0.75
        elif agent_dir != true_dir and sys_dir == agent_dir:
            role = "false_driver"
            score = -1.0
        else:
            role = "neutral"
            score = -0.25

        attributions[agent_id] = {
            "agent_direction": agent_dir,
            "system_direction": sys_dir,
            "true_direction": true_dir,
            "attribution_role": role,
            "marginal_score": score,
        }

    # Explicit role attribution for Bull, Bear, and Risk Manager
    attributions["BULL"] = {
        "agent_direction": "buy",
        "system_direction": sys_dir,
        "true_direction": true_dir,
        "attribution_role": (
            "correct_driver" if (true_dir == "buy" and sys_dir == "buy")
            else "overridden_correct" if (true_dir == "buy" and sys_dir != "buy")
            else "false_driver" if (true_dir == "sell" and sys_dir == "buy")
            else "neutral"
        ),
        "marginal_score": 1.0 if true_dir == "buy" else (-1.0 if (true_dir == "sell" and sys_dir == "buy") else 0.0),
    }
    attributions["BEAR"] = {
        "agent_direction": "sell",
        "system_direction": sys_dir,
        "true_direction": true_dir,
        "attribution_role": (
            "correct_dissent_ignored" if (true_dir == "sell" and sys_dir == "buy")
            else "correct_driver" if (true_dir == "sell" and sys_dir == "sell")
            else "false_driver" if (true_dir == "buy" and sys_dir == "sell")
            else "neutral"
        ),
        "marginal_score": 1.0 if (true_dir == "sell" and sys_dir == "buy") else (0.8 if true_dir == "sell" else -0.5),
    }
    attributions["RISK JUDGE"] = attributions["BEAR"]
    return attributions


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

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses, attribution: Dict[str, Any] = None
    ) -> str:
        """Generate reflection for a component."""
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\nCounterfactual Attribution: {attribution or {}}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        return result

    def _store_with_attribution(self, memory, situation: str, result: str, current_state: Dict[str, Any], role_meta: Dict[str, Any]):
        """Store reflection into memory along with regime and counterfactual attribution metadata."""
        meta = {
            "market_regime": current_state.get("market_regime", "unknown"),
            "attribution_role": role_meta.get("attribution_role", "neutral"),
            "marginal_score": role_meta.get("marginal_score", 0.0),
        }
        try:
            memory.add_situations([(situation, result)], metadata=meta)
        except TypeError:
            memory.add_situations([(situation, result)])

    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory):
        """Reflect on bull researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state["investment_debate_state"]["bull_history"]
        attrib = compute_counterfactual_attribution(current_state, float(returns_losses))
        bull_attrib = attrib.get("BULL", attrib)

        result = self._reflect_on_component(
            "BULL", bull_debate_history, situation, returns_losses, attribution=bull_attrib
        )
        self._store_with_attribution(bull_memory, situation, result, current_state, bull_attrib)

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory):
        """Reflect on bear researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state["investment_debate_state"]["bear_history"]
        attrib = compute_counterfactual_attribution(current_state, float(returns_losses))
        bear_attrib = attrib.get("BEAR", attrib)

        result = self._reflect_on_component(
            "BEAR", bear_debate_history, situation, returns_losses, attribution=bear_attrib
        )
        self._store_with_attribution(bear_memory, situation, result, current_state, bear_attrib)

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_investment_plan"]
        attrib = compute_counterfactual_attribution(current_state, float(returns_losses))

        result = self._reflect_on_component(
            "TRADER", trader_decision, situation, returns_losses, attribution=attrib
        )
        self._store_with_attribution(trader_memory, situation, result, current_state, attrib.get("BULL", {}))

    def reflect_invest_judge(self, current_state, returns_losses, invest_judge_memory):
        """Reflect on investment judge's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["investment_debate_state"]["judge_decision"]
        attrib = compute_counterfactual_attribution(current_state, float(returns_losses))

        result = self._reflect_on_component(
            "INVEST JUDGE", judge_decision, situation, returns_losses, attribution=attrib
        )
        self._store_with_attribution(invest_judge_memory, situation, result, current_state, attrib.get("BULL", {}))

    def reflect_risk_manager(self, current_state, returns_losses, risk_manager_memory):
        """Reflect on risk manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]
        attrib = compute_counterfactual_attribution(current_state, float(returns_losses))
        risk_attrib = attrib.get("RISK JUDGE", attrib)

        result = self._reflect_on_component(
            "RISK JUDGE", judge_decision, situation, returns_losses, attribution=risk_attrib
        )
        self._store_with_attribution(risk_manager_memory, situation, result, current_state, risk_attrib)
