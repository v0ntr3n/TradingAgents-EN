# tradingagents/core/engine/phase_executors/risk_assessment.py
"""
Risk assessment stage executor

Perform a multi-dimensional risk assessment:
1. RiskyRisk (Radical risk control) - High risk tolerance
2. SafeRisk (Robust risk control) - Low risk tolerance
3. NeutralRisk (Neutral risk control) - Balance risk and reward
4. RiskManager (Risk Control Manager) - Comprehensive evaluation to form final decision
"""

from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import DataLayer
from .base import PhaseExecutor

logger = get_logger("default")


class RiskAssessmentPhase(PhaseExecutor):
    """
    Risk assessment stage executor

    Perform multi-dimensional risk assessments to form final analysis results
    """

    phase_name = "RiskAssessmentPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        risk_profiles: Optional[List[str]] = None,
        debate_rounds: int = 1,
        memory_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initial risk assessment phase

        Args:
            llm_provider: LLM provider
            config: stage configuration
            risk_profiles: Risk control type list, default all
            debate_rounds: Debate rounds
            memory_config: Memory Configuration
        """
        super().__init__(llm_provider, config)
        self.risk_profiles = risk_profiles or ["risky", "safe", "neutral"]
        self.debate_rounds = debate_rounds
        self.memory_config = memory_config or {}

        # Agent cache
        self._risky_analyst = None
        self._safe_analyst = None
        self._neutral_analyst = None
        self._risk_manager = None
    
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Perform risk assessment phase
        """
        self.log_start()

        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"⚖️ [{self.phase_name}] risk assessment: {ticker}")

        outputs = {
            "ticker": ticker,
            "risk_reports": [],
            "final_decision": None
        }

        # Get trading signals and trader plans
        trade_signal = context.get(DataLayer.DECISIONS, "trade_signal")
        trader_plan = context.get(DataLayer.DECISIONS, "trader_investment_plan")
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan")

        if trade_signal is None and trader_plan is None:
            logger.warning(f"⚠️ [{self.phase_name}] No trading signal found, risk assessment skipped")
            self.log_end(outputs)
            return outputs

        # Build initial state
        state = self._build_initial_state(context, trader_plan or str(investment_plan))

        # Conduct multiple rounds of risk control debates
        for round_num in range(self.debate_rounds):
            logger.info(f"💬 [{self.phase_name}] Risk Control Debate No. {round_num + 1}/{self.debate_rounds} wheel")

            # Radical risk control speech
            if "risky" in self.risk_profiles:
                state = self._run_risky_analyst(state)
                outputs["risk_reports"].append("risky")

            # Speech on Steady Risk Control
            if "safe" in self.risk_profiles:
                state = self._run_safe_analyst(state)
                outputs["risk_reports"].append("safe")

            # Neutral risk control speech
            if "neutral" in self.risk_profiles:
                state = self._run_neutral_analyst(state)
                outputs["risk_reports"].append("neutral")

        # Risk control manager summary
        state = self._run_risk_manager(state)

        # Save results
        risk_debate_state = state.get("risk_debate_state", {})

        # 🔥 Modification: Generate final_trade_decision (comprehensive investment advice, trading plan, risk assessment)
        final_trade_decision = self._generate_final_trade_decision(context)
        state["final_trade_decision"] = final_trade_decision

        context.set(DataLayer.DECISIONS, "risk_debate_state", risk_debate_state, source="risk_assessment")
        context.set(DataLayer.DECISIONS, "final_trade_decision", final_trade_decision, source="risk_assessment")

        # Generate final decision
        final_decision = self._form_final_decision_from_text(context, trade_signal, final_trade_decision)
        context.set(DataLayer.DECISIONS, "final_decision", final_decision, source="risk_manager")
        outputs["final_decision"] = final_decision.get("action")

        logger.info(f"📝 [{self.phase_name}] final decision: {final_decision.get('action')}")

        self.log_end(outputs)
        return outputs

    def _build_initial_state(self, context: AnalysisContext, trader_plan: str) -> Dict[str, Any]:
        """Build initial state"""
        ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
        trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

        return {
            "company_of_interest": ticker,
            "trade_date": trade_date,
            "trader_investment_plan": trader_plan,
            "investment_plan": context.get(DataLayer.DECISIONS, "investment_plan") or "",
            "market_report": context.get(DataLayer.REPORTS, "market_report") or "",
            "sentiment_report": context.get(DataLayer.REPORTS, "sentiment_report") or "",
            "news_report": context.get(DataLayer.REPORTS, "news_report") or "",
            "fundamentals_report": context.get(DataLayer.REPORTS, "fundamentals_report") or "",
            "risk_debate_state": {
                "history": "",
                "risky_history": "",
                "safe_history": "",
                "neutral_history": "",
                "current_risky_response": "",
                "current_safe_response": "",
                "current_neutral_response": "",
                "count": 0,
                "judge_decision": ""
            }
        }

    def _get_risky_analyst(self):
        """Obtain or create aggressive risk controls"""
        if self._risky_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator
                self._risky_analyst = create_risky_debator(self.llm_provider)
                logger.debug("🔥 [RiskAssessment] Create RiskyAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating RiskyAnalyst failed: {e}")
        return self._risky_analyst

    def _get_safe_analyst(self):
        """Obtain or create robust risk controls"""
        if self._safe_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator
                self._safe_analyst = create_safe_debator(self.llm_provider)
                logger.debug("🛡️ [RiskAssessment] Create SafeAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating SafeAnalyst failed: {e}")
        return self._safe_analyst

    def _get_neutral_analyst(self):
        """Obtain or create neutral risk controls"""
        if self._neutral_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
                self._neutral_analyst = create_neutral_debator(self.llm_provider)
                logger.debug("⚖️ [RiskAssessment] Create NeutralAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Failed to create NeutralAnalyst: {e}")
        return self._neutral_analyst

    def _get_risk_manager(self):
        """Get or create a risk control manager"""
        if self._risk_manager is None:
            try:
                from tradingagents.agents.managers.risk_manager import create_risk_manager
                memory = self.memory_config.get("risk_memory")
                self._risk_manager = create_risk_manager(self.llm_provider, memory)
                logger.debug("👔 [RiskAssessment] Create RiskManager")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating RiskManager failed: {e}")
        return self._risk_manager

    def _run_risky_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement aggressive risk control"""
        agent = self._get_risky_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("🔥 [Radical risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Radical risk control] Execution failed: {e}")
        return state

    def _run_safe_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement robust risk control"""
        agent = self._get_safe_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("🛡️ [Robust risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Robust risk control] Execution failed: {e}")
        return state

    def _run_neutral_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement neutral risk control"""
        agent = self._get_neutral_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("⚖️ [Neutral risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Neutral risk control] Execution failed: {e}")
        return state

    def _run_risk_manager(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Executive risk control manager summary"""
        agent = self._get_risk_manager()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                if "final_trade_decision" in result:
                    state["final_trade_decision"] = result["final_trade_decision"]
                logger.info("👔 [Risk Control Manager] The final decision is generated")
            except Exception as e:
                logger.error(f"❌ [Risk Control Manager] Execution failed: {e}")
                state["final_trade_decision"] = "[Error] Risk control decision generation failed"
        return state

    def _form_final_decision_from_text(
        self,
        context: AnalysisContext,
        trade_signal: Optional[Dict[str, Any]],
        final_text: str
    ) -> Dict[str, Any]:
        """Generate final decision from risk text (using SignalProcessor to maintain consistency with legacy)"""
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # 🔥 Use SignalProcessor to process final_trade_decision text
        # This can extract target_price and reasoning, consistent with the old version
        try:
            from tradingagents.graph.signal_processing import SignalProcessor
            signal_processor = SignalProcessor()
            decision = signal_processor.process_signal(final_text, ticker)
            logger.info(f"✅ [RiskAssessment] Use SignalProcessor to handle decisions: {decision}")

            # Map reasoning to rationale to maintain compatibility
            if "reasoning" in decision and "rationale" not in decision:
                decision["rationale"] = decision["reasoning"]

            # Add risk_level field
            if "risk_level" not in decision:
                decision["risk_level"] = self._determine_risk_level_from_text(final_text)

            # Add ticker field
            decision["ticker"] = ticker

            # If there is a raw trading signal, add original_rationale
            if trade_signal and isinstance(trade_signal, dict):
                original_rationale = trade_signal.get("rationale", "")
                decision["original_rationale"] = original_rationale[:200] if original_rationale else ""

            return decision

        except Exception as e:
            logger.warning(f"⚠️ [RiskAssessment] SignalProcessor Handling failed, use simple parsing: {e}")

            # Downgrade to simple parsing
            action, confidence = self._parse_action_from_text(final_text)

            # If there are original trading signals, merge the information
            if trade_signal and isinstance(trade_signal, dict):
                original_position = trade_signal.get("position_size", 0.0)
                original_rationale = trade_signal.get("rationale", "")
            else:
                original_position = 0.5
                original_rationale = ""

            # Adjust positions according to risk control recommendations
            if action == "HOLD":
                position_size = 0.0
            else:
                position_size = min(confidence, 1.0) * original_position if original_position > 0 else confidence * 0.5

            return {
                "ticker": ticker,
                "action": action,
                "position_size": position_size,
                "confidence": confidence,
                "risk_level": self._determine_risk_level_from_text(final_text),
                "rationale": final_text[:500] if len(final_text) > 500 else final_text,
                "reasoning": final_text[:500] if len(final_text) > 500 else final_text,  # Add reasoning field
                "original_rationale": original_rationale[:200] if original_rationale else "",
                "target_price": None,  # Add target_price field
                "risk_score": 0.5,  # Add risk_score field
            }

    def _parse_action_from_text(self, text: str) -> tuple:
        """Parse transaction actions from text"""
        text_lower = text.lower()

        buy_keywords = ["buy", "Overweight", "long", "Recommended to buy", "buy", "bullish"]
        sell_keywords = ["sell", "Reduce holdings", "bearish", "Recommended to sell", "sell", "bearish"]
        hold_keywords = ["hold", "wait and see", "hold", "neutral", "Neutral"]

        buy_score = sum(1 for kw in buy_keywords if kw in text_lower)
        sell_score = sum(1 for kw in sell_keywords if kw in text_lower)
        hold_score = sum(1 for kw in hold_keywords if kw in text_lower)

        if buy_score > sell_score and buy_score > hold_score:
            return "BUY", min(0.5 + buy_score * 0.1, 0.9)
        elif sell_score > buy_score and sell_score > hold_score:
            return "SELL", min(0.5 + sell_score * 0.1, 0.9)
        else:
            return "HOLD", 0.5

    def _determine_risk_level_from_text(self, text: str) -> str:
        """Determine risk level from text"""
        text_lower = text.lower()

        high_risk_keywords = ["high risk", "Riskier", "cautious", "danger", "high risk"]
        low_risk_keywords = ["low risk", "safe", "Robust", "low risk"]

        high_score = sum(1 for kw in high_risk_keywords if kw in text_lower)
        low_score = sum(1 for kw in low_risk_keywords if kw in text_lower)

        if high_score > low_score:
            return "high"
        elif low_score > high_score:
            return "low"
        else:
            return "medium"

    def _generate_final_trade_decision(self, context: "AnalysisContext") -> str:
        """
        Generate final analysis results

        Taking into account the following:
        1. investment_plan (Research Manager s Investment Advice)
        2. trader_investment_plan (Trader s Trading Plan)
        3. risk_debate_state.judge_decision (Risk assessment for risk managers)

        Args:
            context: Analyze context

        Returns:
            Final analysis result text (Markdown format)
        """
        from tradingagents.core.engine.data_layer import DataLayer

        # Extract individual reports
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan") or ""
        trader_plan = context.get(DataLayer.DECISIONS, "trader_investment_plan") or ""
        risk_debate_state = context.get(DataLayer.DECISIONS, "risk_debate_state") or {}
        risk_assessment = risk_debate_state.get("judge_decision", "") if isinstance(risk_debate_state, dict) else ""

        # If all three are empty, return an empty string
        if not any([investment_plan, trader_plan, risk_assessment]):
            logger.warning("⚠️ [RiskAssessment] Unable to generate final_trade_decision: all input reports are empty")
            return ""

        # Build the final decision (Markdown format)
        sections = []

        if investment_plan:
            sections.append(f"## 📋 investment advice\n\n{investment_plan}")

        if trader_plan:
            sections.append(f"## 💼 trading plan\n\n{trader_plan}")

        if risk_assessment:
            sections.append(f"## ⚠️ risk assessment\n\n{risk_assessment}")

        final_decision = "\n\n".join(sections)
        logger.info(f"✅ [RiskAssessment] Generate final_trade_decision, containing {len(sections)} parts")

        return final_decision

