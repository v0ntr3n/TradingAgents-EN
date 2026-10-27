# tradingagents/core/engine/phase_executors/trade_decision.py
"""
Trade decision stage executor

Generate trading signals based on research conclusions:
- Trader (trader) - Generate specific trading signals
"""

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import DataLayer
from .base import PhaseExecutor

logger = get_logger("default")


class TradeDecisionPhase(PhaseExecutor):
    """
    Trade decision stage executor

    Generate specific trading signals based on investment recommendations
    """

    phase_name = "TradeDecisionPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        memory_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize transaction decision phase

        Args:
            llm_provider: LLM provider
            config: stage configuration
            memory_config: Memory Configuration
        """
        super().__init__(llm_provider, config)
        self.memory_config = memory_config or {}
        self._trader = None
    
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execution transaction decision stage
        """
        self.log_start()

        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"💹 [{self.phase_name}] Generate trading signals: {ticker}")

        outputs = {
            "ticker": ticker,
            "trade_signal": None,
            "trader_investment_plan": None
        }

        # Get investment advice
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan")

        if investment_plan is None:
            logger.warning(f"⚠️ [{self.phase_name}] No investment advice found, trading decision skipped")
            self.log_end(outputs)
            return outputs

        # use actual Trader Agent
        trader_result = self._run_trader(context, investment_plan)

        if trader_result:
            trader_plan = trader_result.get("trader_investment_plan", "")

            # Save a trader's investment plan
            context.set(DataLayer.DECISIONS, "trader_investment_plan", trader_plan, source="trader")
            outputs["trader_investment_plan"] = "generated" if trader_plan else None

            # Parse trading signals from trader results
            trade_signal = self._parse_trade_signal(context, trader_plan, investment_plan)
            context.set(DataLayer.DECISIONS, "trade_signal", trade_signal, source="trader")
            outputs["trade_signal"] = trade_signal.get("action")

            logger.info(f"📝 [{self.phase_name}] trading signals: {trade_signal.get('action')}, "
                       f"Confidence: {trade_signal.get('confidence', 0):.2f}")
        else:
            # Fallback to simple parsing
            trade_signal = self._generate_trade_signal(context, investment_plan)
            context.set(DataLayer.DECISIONS, "trade_signal", trade_signal, source="trader")
            outputs["trade_signal"] = trade_signal.get("action")

        self.log_end(outputs)
        return outputs

    def _get_trader(self):
        """Get or create Trader Agent"""
        if self._trader is None:
            try:
                from tradingagents.agents.trader.trader import create_trader
                # Supports two key formats: "trader" or "trader_memory"
                memory = self.memory_config.get("trader") or self.memory_config.get("trader_memory")
                self._trader = create_trader(self.llm_provider, memory)
                logger.debug("💰 [TradeDecision] Create Trader Agent")
            except Exception as e:
                logger.error(f"❌ [TradeDecision] Failed to create Trader: {e}")
        return self._trader

    def _run_trader(self, context: AnalysisContext, investment_plan: Any) -> Optional[Dict[str, Any]]:
        """run Trader Agent"""
        trader = self._get_trader()
        if not trader:
            logger.warning("⚠️ [TradeDecision] Trader Not available, use simple parsing")
            return None

        try:
            # Build state that is compatible with existing agents
            ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
            trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

            state = {
                "company_of_interest": ticker,
                "trade_date": trade_date,
                "investment_plan": investment_plan if isinstance(investment_plan, str) else str(investment_plan),
                # Collect all analysis reports
                "market_report": context.get(DataLayer.REPORTS, "market_report") or "",
                "sentiment_report": context.get(DataLayer.REPORTS, "sentiment_report") or "",
                "news_report": context.get(DataLayer.REPORTS, "news_report") or "",
                "fundamentals_report": context.get(DataLayer.REPORTS, "fundamentals_report") or "",
                "sector_report": context.get(DataLayer.REPORTS, "sector_report") or "",
                "index_report": context.get(DataLayer.REPORTS, "index_report") or "",
            }

            result = trader(state)
            logger.info("💰 [Trader] Transaction decision generation completed")
            return result

        except Exception as e:
            logger.error(f"❌ [Trader] Execution failed: {e}")
            return None

    def _parse_trade_signal(
        self,
        context: AnalysisContext,
        trader_plan: str,
        investment_plan: Any
    ) -> Dict[str, Any]:
        """Parsing trading signals from trader plans"""
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # Merge text for analysis
        combined_text = trader_plan
        if isinstance(investment_plan, str):
            combined_text = f"{investment_plan}\n{trader_plan}"

        recommendation, confidence = self._parse_recommendation_from_text(combined_text)

        action_map = {
            "buy": "BUY",
            "sell": "SELL",
            "hold": "HOLD"
        }
        action = action_map.get(recommendation.lower(), "HOLD")

        if action == "HOLD":
            position_size = 0.0
        else:
            position_size = min(confidence, 1.0)

        return {
            "ticker": ticker,
            "action": action,
            "position_size": position_size,
            "confidence": confidence,
            "rationale": trader_plan[:500] if len(trader_plan) > 500 else trader_plan,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "timestamp": None
        }
    
    def _generate_trade_signal(
        self,
        context: AnalysisContext,
        investment_plan: Any
    ) -> Dict[str, Any]:
        """
        Generate trading signals

        TODO: Integrate actual Trader Agent

        Args:
            context: Analyze context
            investment_plan: investment advice (may be a dictionary or string)

        Returns:
            trading signals
        """
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # Handle different types of investment advice
        if isinstance(investment_plan, dict):
            recommendation = investment_plan.get("recommendation", "hold")
            confidence = investment_plan.get("confidence", 0.5)
            rationale = investment_plan.get("rationale", "")
        elif isinstance(investment_plan, str):
            # Extract suggestions from text
            recommendation, confidence = self._parse_recommendation_from_text(investment_plan)
            rationale = investment_plan[:500] if len(investment_plan) > 500 else investment_plan
        else:
            recommendation = "hold"
            confidence = 0.5
            rationale = ""

        # Generate trading signals based on investment recommendations
        action_map = {
            "buy": "BUY",
            "sell": "SELL",
            "hold": "HOLD"
        }

        action = action_map.get(recommendation.lower(), "HOLD")

        # Calculate positions based on confidence
        if action == "HOLD":
            position_size = 0.0
        else:
            position_size = min(confidence, 1.0)  # maximum 100%

        return {
            "ticker": ticker,
            "action": action,
            "position_size": position_size,
            "confidence": confidence,
            "rationale": rationale,
            "entry_price": None,  # Need real-time quotes
            "stop_loss": None,
            "take_profit": None,
            "timestamp": None
        }

    def _parse_recommendation_from_text(self, text: str) -> tuple:
        """
        Parse investment advice from text

        Args:
            text: investment advice text

        Returns:
            (recommendation, confidence) tuple
        """
        text_lower = text.lower()

        # Simple keyword matching
        buy_keywords = ["buy", "Overweight", "long", "Recommended to buy", "buy", "bullish", "bullish"]
        sell_keywords = ["sell", "Reduce holdings", "bearish", "Recommended to sell", "sell", "bearish", "Bearish"]
        hold_keywords = ["hold", "wait and see", "hold", "neutral", "Neutral"]

        buy_score = sum(1 for kw in buy_keywords if kw in text_lower)
        sell_score = sum(1 for kw in sell_keywords if kw in text_lower)
        hold_score = sum(1 for kw in hold_keywords if kw in text_lower)

        # Confirm recommendations
        if buy_score > sell_score and buy_score > hold_score:
            recommendation = "buy"
            confidence = min(0.5 + buy_score * 0.1, 0.9)
        elif sell_score > buy_score and sell_score > hold_score:
            recommendation = "sell"
            confidence = min(0.5 + sell_score * 0.1, 0.9)
        else:
            recommendation = "hold"
            confidence = 0.5

        return recommendation, confidence

