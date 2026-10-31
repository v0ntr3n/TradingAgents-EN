# TradingAgents/graph/signal_processing.py

import json
import math
import re
from typing import Any, Dict, List, Optional, Union

from langchain_openai import ChatOpenAI

from core.agents.utils.weight_calculator import RegimeAdaptiveWeightCalculator
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_graph_module
logger = get_logger("graph.signal_processing")

__all__ = [
    "SignalProcessor",
    "calculate_bayesian_log_odds_target_price",
    "compute_bayesian_log_odds_details",
    "process_calibrated_signal",
]


def calculate_bayesian_log_odds_target_price(
    current_price: float,
    action: str,
    regime: str,
    analyst_posteriors: Dict[str, Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    is_china: bool = True,
) -> float:
    """
    Bayesian log-odds opinion pooling for calibrated empirical price target estimation:
    1. Prior log-odds L0(regime): Bull=+0.405465, Sideways=0.0, Bear=-0.405465
    2. Analyst log-odds: ell_i = ln(p_opt / p_caut)
    3. Aggregated log-odds: L_agg = L0 + sum(w_i * ell_i)
    4. Calibrated directional probability: P_agg = sigmoid(L_agg)
    5. Weighted expected move: weighted_move_bps = sum(w_i * move_i) / sum(w_i)
    6. Calibrated return: calibrated_return = (2 * P_agg - 1.0) * (|weighted_move_bps| / 10000.0)
    7. Empirical price target:
       - buy: current_price * (1.0 + max(calibrated_return, 0.005))
       - sell: current_price * (1.0 - max(|calibrated_return|, 0.005))
       - hold: current_price
    """
    action = str(action or "hold").lower().strip()
    if action not in ["buy", "sell", "hold"]:
        if "buy" in action:
            action = "buy"
        elif "sell" in action:
            action = "sell"
        else:
            action = "hold"

    if not analyst_posteriors:
        # Fallback to legacy multipliers
        if action == "buy":
            multiplier = 1.15 if is_china else 1.12
            return round(current_price * multiplier, 2)
        elif action == "sell":
            multiplier = 0.95 if is_china else 0.92
            return round(current_price * multiplier, 2)
        return round(current_price, 2)

    regime_str = str(regime or "sideways").lower().strip()
    regime_priors = {
        "bull": math.log(0.60 / 0.40),      # ~ +0.405465
        "sideways": 0.0,
        "bear": math.log(0.40 / 0.60),      # ~ -0.405465
    }
    l0 = regime_priors.get(regime_str, 0.0)

    if weights is None:
        calc = RegimeAdaptiveWeightCalculator()
        weights = calc.get_weights(regime_str, active_analysts=list(analyst_posteriors.keys()))

    l_agg = l0
    moves = []
    w_sum = 0.0
    eps = 1e-4

    for aid, post in analyst_posteriors.items():
        if not isinstance(post, dict):
            continue
        w = float(weights.get(aid, 0.0))
        p_opt = max(eps, float(post.get("p_optimistic", 0.3333)))
        p_caut = max(eps, float(post.get("p_cautious", 0.3333)))
        ell_i = math.log(p_opt / p_caut)
        l_agg += w * ell_i

        move = float(post.get("expected_move_bps", 0.0))
        moves.append(move * w)
        w_sum += w

    l_agg_clipped = max(-10.0, min(10.0, l_agg))
    p_agg = 1.0 / (1.0 + math.exp(-l_agg_clipped))

    weighted_move_bps = (sum(moves) / w_sum) if w_sum > 0 else 50.0
    calibrated_return = (2.0 * p_agg - 1.0) * (abs(weighted_move_bps) / 10000.0)

    if action == "buy":
        target = current_price * (1.0 + max(calibrated_return, 0.005))
    elif action == "sell":
        target = current_price * (1.0 - max(abs(calibrated_return), 0.005))
    else:
        target = current_price

    return round(target, 2)


def compute_bayesian_log_odds_details(
    current_price: float,
    action: str,
    regime: str,
    analyst_posteriors: Dict[str, Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    is_china: bool = True,
) -> Dict[str, Any]:
    """Calculate full Bayesian log-odds aggregation details."""
    action = str(action or "hold").lower().strip()
    if action not in ["buy", "sell", "hold"]:
        if "buy" in action:
            action = "buy"
        elif "sell" in action:
            action = "sell"
        else:
            action = "hold"

    regime_str = str(regime or "sideways").lower().strip()
    regime_priors = {
        "bull": math.log(0.60 / 0.40),
        "sideways": 0.0,
        "bear": math.log(0.40 / 0.60),
    }
    l0 = regime_priors.get(regime_str, 0.0)

    if weights is None:
        calc = RegimeAdaptiveWeightCalculator()
        weights = calc.get_weights(regime_str, active_analysts=list(analyst_posteriors.keys()))

    l_agg = l0
    moves = []
    w_sum = 0.0
    eps = 1e-4

    for aid, post in analyst_posteriors.items():
        if not isinstance(post, dict):
            continue
        w = float(weights.get(aid, 0.0))
        p_opt = max(eps, float(post.get("p_optimistic", 0.3333)))
        p_caut = max(eps, float(post.get("p_cautious", 0.3333)))
        ell_i = math.log(p_opt / p_caut)
        l_agg += w * ell_i

        move = float(post.get("expected_move_bps", 0.0))
        moves.append(move * w)
        w_sum += w

    l_agg_clipped = max(-10.0, min(10.0, l_agg))
    p_agg = 1.0 / (1.0 + math.exp(-l_agg_clipped))

    weighted_move_bps = (sum(moves) / w_sum) if w_sum > 0 else 50.0
    calibrated_return = (2.0 * p_agg - 1.0) * (abs(weighted_move_bps) / 10000.0)

    if action == "buy":
        target = current_price * (1.0 + max(calibrated_return, 0.005))
    elif action == "sell":
        target = current_price * (1.0 - max(abs(calibrated_return), 0.005))
    else:
        target = current_price

    return {
        "target_price": round(target, 2),
        "l_agg": l_agg,
        "p_agg": p_agg,
        "weighted_move_bps": weighted_move_bps,
        "calibrated_return": calibrated_return,
        "regime": regime_str,
        "action": action,
        "weights_used": weights,
    }


def process_calibrated_signal(
    current_price: float,
    action: str,
    regime: str,
    analyst_posteriors: Optional[Dict[str, Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None,
    default_move_bps: float = 50.0,
    is_china: bool = True,
) -> Dict[str, Any]:
    """
    Public API for calibrated signal processing (Milestone 2 / Feature 16).

    Derives empirical target prices via Bayesian log-odds opinion pooling,
    ensemble confidence 2 * |P_agg - 0.5|, risk score 1.0 - confidence,
    and calibrated expected return.

    Gracefully falls back to legacy multipliers (1.15x / 0.95x China; 1.12x / 0.92x US)
    and default 0.70 confidence when analyst_posteriors is absent or empty.

    Args:
        current_price: Current asset price.
        action: Trading action ("buy", "sell", "hold").
        regime: Market regime ("bull", "bear", "sideways").
        analyst_posteriors: Optional dictionary of analyst posterior distributions.
        weights: Optional dictionary of analyst reliability weights.
        default_move_bps: Default move in basis points (default: 50.0).
        is_china: Whether asset trades in China A-share market (affects fallback multipliers).

    Returns:
        Dictionary containing target_price, confidence, risk_score, calibrated_prob,
        p_agg, calibrated_return, weighted_move_bps, aggregated_log_odds, l_agg,
        action, regime, and weights_used.
    """
    action = str(action or "hold").lower().strip()
    if action not in ["buy", "sell", "hold"]:
        if "buy" in action:
            action = "buy"
        elif "sell" in action:
            action = "sell"
        else:
            action = "hold"

    regime_str = str(regime or "sideways").lower().strip()
    if regime_str not in ["bull", "bear", "sideways"]:
        regime_str = "sideways"

    curr_p = float(current_price) if current_price is not None else 0.0

    # Fallback when analyst_posteriors is missing or empty
    if not analyst_posteriors:
        if action == "buy":
            mult = 1.15 if is_china else 1.12
            calibrated_return = 0.15 if is_china else 0.12
        elif action == "sell":
            mult = 0.95 if is_china else 0.92
            calibrated_return = -0.05 if is_china else -0.08
        else:
            mult = 1.0
            calibrated_return = 0.0

        target_price = round(curr_p * mult, 2)
        return {
            "target_price": target_price,
            "confidence": 0.70,
            "risk_score": 0.30,
            "calibrated_prob": 0.50,
            "p_agg": 0.50,
            "calibrated_return": calibrated_return,
            "weighted_move_bps": float(default_move_bps),
            "aggregated_log_odds": 0.0,
            "l_agg": 0.0,
            "action": action,
            "regime": regime_str,
            "weights_used": weights or {},
        }

    details = compute_bayesian_log_odds_details(
        current_price=curr_p,
        action=action,
        regime=regime_str,
        analyst_posteriors=analyst_posteriors,
        weights=weights,
        is_china=is_china,
    )

    p_agg = details["p_agg"]
    confidence = min(1.0, max(0.0, round(2.0 * abs(p_agg - 0.5), 4)))
    risk_score = min(1.0, max(0.0, round(1.0 - confidence, 4)))

    return {
        "target_price": details["target_price"],
        "confidence": confidence,
        "risk_score": risk_score,
        "calibrated_prob": p_agg,
        "p_agg": p_agg,
        "calibrated_return": details["calibrated_return"],
        "weighted_move_bps": details["weighted_move_bps"],
        "aggregated_log_odds": details["l_agg"],
        "l_agg": details["l_agg"],
        "action": action,
        "regime": regime_str,
        "weights_used": details["weights_used"],
    }


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(
        self,
        quick_thinking_llm: Optional[ChatOpenAI] = None,
        weight_calculator: Optional[RegimeAdaptiveWeightCalculator] = None,
    ):
        """Initialize with an LLM for processing and an optional weight calculator."""
        self.quick_thinking_llm = quick_thinking_llm
        self.weight_calculator = (
            weight_calculator if weight_calculator is not None else RegimeAdaptiveWeightCalculator()
        )

    @log_graph_module("signal_processing")
    def process_signal(
        self,
        full_signal: str,
        stock_symbol: Optional[Union[str, dict]] = None,
        state: Optional[dict] = None,
        **kwargs: Any,
    ) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text
            stock_symbol: Stock symbol or state dict to determine currency type
            state: Optional graph state containing analyst_posteriors, market_regime, etc.

        Returns:
            Dictionary containing extracted decision information
        """
        if isinstance(stock_symbol, dict):
            state = stock_symbol
            stock_symbol = state.get("stock_symbol") or state.get("ticker") or state.get("company_of_interest")
        if state is None and "state" in kwargs:
            state = kwargs["state"]

        # Validate input parameters
        if not full_signal or not isinstance(full_signal, str) or len(full_signal.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] The input signal is empty or invalid: {repr(full_signal)}")
            return {
                'action': 'hold',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': 'Input signal is invalid, hold suggestion by default'
            }

        # Clean and validate signal content
        full_signal = full_signal.strip()
        if len(full_signal) == 0:
            logger.error(f"❌ [SignalProcessor] Signal content is empty")
            return {
                'action': 'hold',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': 'The signal content is empty and holds suggestions by default.'
            }

        # Detect stock type and currency
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(stock_symbol)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.info(f"🔍 [SignalProcessor] Process signals: stocks={stock_symbol}, market={market_info['market_name']}, Currency={currency}",
                   extra={'stock_symbol': stock_symbol, 'market': market_info['market_name'], 'currency': currency})

        # If LLM is not provided, use offline rule-based extraction
        if self.quick_thinking_llm is None:
            return self._extract_simple_decision(full_signal, state=state, is_china=is_china)

        messages = [
            (
                "system",
                f"""You are a professional financial analysis assistant responsible for extracting structured investment decision-making information from traders analysis reports.

Please extract the following information from the provided analysis report and return it in JSON format:

{{
    "action": "Buy/Hold/Sell",
    "target_price": numbers({currency}price,**A specific value must be provided and cannot be null**),
    "confidence": numbers(0-1 between, if not explicitly mentioned then 0.7),
    "risk_score": numbers(0-1 between, if not explicitly mentioned then 0.5),
    "reasoning": "Summary of the main reasons for the decision"
}}

Please make sure:
1. action Field must be"buy", "hold"or"sell"One (English buy/hold/sell is absolutely not allowed)
2. target_price Must be a specific number,target_price should be reasonable{currency}price figure (using{currency_symbol}symbol)
3. confidence and risk_score should be between 0-1
4. reasoning Should be a concise Chinese summary
5. All content must be in Chinese, no investment advice in English is allowed

Special attention:
- Stock code {stock_symbol or 'unknown'} Yes{market_info['market_name']}, Use{currency}Pricing
- The target price must be consistent with the currency in which the stock is traded ({currency_symbol}) 

If some information is not explicitly mentioned in the report, use reasonable defaults.""",
            ),
            ("human", full_signal),
        ]

        # Verify message content
        if not messages or len(messages) == 0:
            logger.error(f"❌ [SignalProcessor] messages is empty")
            return self._get_default_decision()

        human_content = messages[1][1] if len(messages) > 1 else ""
        if not human_content or len(human_content.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] human The message content is empty")
            return self._get_default_decision()

        logger.debug(f"🔍 [SignalProcessor] Prepare to call LLM, number of messages: {len(messages)}, Signal length: {len(full_signal)}")

        try:
            response = self.quick_thinking_llm.invoke(messages).content
            logger.debug(f"🔍 [SignalProcessor] LLM response: {response[:200]}...")

            # Extract JSON part
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                logger.debug(f"🔍 [SignalProcessor] extracted JSON: {json_text}")
                decision_data = json.loads(json_text)

                # Validate and standardize data
                action = decision_data.get('action', 'hold')
                if action not in ['buy', 'hold', 'sell']:
                    action_map = {
                        'buy': 'buy', 'hold': 'hold', 'sell': 'sell',
                        'BUY': 'buy', 'HOLD': 'hold', 'SELL': 'sell',
                        'buy': 'buy', 'keep': 'hold', 'for sale': 'sell',
                        'purchase': 'buy', 'keep': 'hold', 'dispose': 'sell'
                    }
                    action = action_map.get(action, 'hold')
                    if action != decision_data.get('action', 'hold'):
                        logger.debug(f"🔍 [SignalProcessor] Investment advice mapping: {decision_data.get('action')} -> {action}")

                # Handle target prices to ensure correct extraction
                target_price = decision_data.get('target_price')
                if target_price is None or target_price == "null" or target_price == "":
                    # If there is no target price in JSON, try to extract from reasoning and full text
                    reasoning = decision_data.get('reasoning', '')
                    full_text = f"{reasoning} {full_signal}"  # Expand search

                    price_patterns = [
                        r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
                        r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # **target price**: 45.50
                        r'目标价[位格]?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                        r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
                        r'reasonable[Price]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)', # Reasonable price: 45.50
                        r'合理[价位]?格?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                        r'Valuation[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # Valuation: 45.50
                        r'估值[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                        r'Suggestions[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # Suggestions: 45.50
                        r'expected[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # expected: 45.50
                        r'look[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',          # see 45.50
                        r'看[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
                        r'rise[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',        # rise to 45.50
                        r'涨[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
                        r'跌[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
                    ]

                    for pattern in price_patterns:
                        price_match = re.search(pattern, full_text, re.IGNORECASE)
                        if price_match:
                            try:
                                target_price = float(price_match.group(1))
                                logger.debug(f"🔍 [SignalProcessor] Extract target price from text: {target_price} (mode: {pattern})")
                                break
                            except (ValueError, IndexError):
                                continue

                    # If price not found, perform smart estimation (with Bayesian aggregation if state has posteriors)
                    if target_price is None or target_price == "null" or target_price == "":
                        target_price = self._smart_price_estimation(full_text, action, is_china, state=state)
                        if target_price:
                            logger.debug(f"🔍 [SignalProcessor] Intelligent calculation of target price: {target_price}")
                        else:
                            target_price = None
                            logger.warning(f"🔍 [SignalProcessor] Failed to extract target price, set to None")
                else:
                    # Make sure the price is a numeric type
                    try:
                        if isinstance(target_price, str):
                            clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').replace('Yuan', '').replace('US dollars', '').strip()
                            target_price = float(clean_price) if clean_price and clean_price.lower() not in ['none', 'null', ''] else None
                        elif isinstance(target_price, (int, float)):
                            target_price = float(target_price)
                        logger.debug(f"🔍 [SignalProcessor] Processed target price: {target_price}")
                    except (ValueError, TypeError):
                        target_price = None
                        logger.warning(f"🔍 [SignalProcessor] Price conversion failed, set to None")

                # If state contains analyst_posteriors, calculate Bayesian details
                bayesian_details = None
                if state and isinstance(state, dict) and state.get("analyst_posteriors"):
                    regime = state.get("market_regime") or "sideways"
                    weights = self.weight_calculator.get_weights(regime)
                    curr_p = target_price or 100.0
                    if state.get("current_price") is not None:
                        try:
                            curr_p = float(state["current_price"])
                        except (ValueError, TypeError):
                            pass
                    bayesian_details = process_calibrated_signal(
                        current_price=curr_p,
                        action=action,
                        regime=regime,
                        analyst_posteriors=state["analyst_posteriors"],
                        weights=weights,
                        is_china=is_china,
                    )
                    if target_price is None or state.get("override_target_price_with_bayesian", False) or (curr_p and abs(target_price - curr_p) < 1e-4):
                        target_price = bayesian_details["target_price"]

                conf = decision_data.get('confidence')
                risk = decision_data.get('risk_score')
                result = {
                    'action': action,
                    'target_price': target_price,
                    'confidence': float(conf) if conf is not None else (bayesian_details['confidence'] if bayesian_details else 0.7),
                    'risk_score': float(risk) if risk is not None else (bayesian_details['risk_score'] if bayesian_details else 0.5),
                    'reasoning': decision_data.get('reasoning', 'Investment advice based on comprehensive analysis')
                }
                if bayesian_details:
                    result['bayesian_target_price'] = bayesian_details['target_price']
                    result['p_agg'] = bayesian_details['p_agg']
                    result['log_odds_agg'] = bayesian_details['l_agg']
                    result['weighted_move_bps'] = bayesian_details['weighted_move_bps']
                    result['calibrated_return'] = bayesian_details['calibrated_return']
                    result['bayesian_confidence'] = bayesian_details['confidence']
                    result['bayesian_risk_score'] = bayesian_details['risk_score']

                logger.info(f"🔍 [SignalProcessor] Processing results: {result}",
                           extra={'action': result['action'], 'target_price': result['target_price'],
                                  'confidence': result['confidence'], 'stock_symbol': stock_symbol})
                return result
            else:
                return self._extract_simple_decision(response, state=state, is_china=is_china)

        except Exception as e:
            logger.error(f"Signal handling error: {e}", exc_info=True, extra={'stock_symbol': stock_symbol})
            return self._extract_simple_decision(full_signal, state=state, is_china=is_china)

    def _smart_price_estimation(
        self,
        text: str,
        action: str,
        is_china: bool = True,
        state: Optional[dict] = None,
        current_price: Optional[float] = None,
    ) -> Optional[float]:
        """
        Intelligent price calculation method:
        - When state and state['analyst_posteriors'] are present:
          performs regime-calibrated Bayesian log-odds aggregation.
        - When state or analyst_posteriors is absent:
          preserves original fallback multipliers (1.15 buy / 0.95 sell for China; 1.12 / 0.92 for US).
        """
        # 1. Extract current price if not explicitly provided
        if current_price is None:
            current_price_patterns = [
                r'current\s*price(?:\s+is|\s+at)?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'stock\s*price(?:\s+is|\s+at)?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'当前价[格位]?(?:为|是)?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                r'现价(?:为|是)?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                r'股价(?:为|是)?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                r'价格(?:为|是)?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
                r'price(?:\s+is|\s+at)?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'current price[grid position]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'Current price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'stock price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
                r'(\d+(?:\.\d+)?)\s*(?:元|yuan|USD|\$|HKD)',
            ]
            for pattern in current_price_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        current_price = float(match.group(1))
                        break
                    except ValueError:
                        continue

        # 2. If still None, search state for price fields
        if current_price is None and state and isinstance(state, dict):
            for price_key in ["current_price", "price", "latest_price", "stock_price"]:
                val = state.get(price_key)
                if val is not None:
                    try:
                        current_price = float(val)
                        break
                    except (ValueError, TypeError):
                        pass

        # If current price cannot be determined, return None
        if current_price is None:
            return None

        # 3. If state contains analyst_posteriors: perform Bayesian log-odds aggregation
        if state and isinstance(state, dict) and state.get("analyst_posteriors"):
            regime = state.get("market_regime") or "sideways"
            weights = self.weight_calculator.get_weights(regime)
            return calculate_bayesian_log_odds_target_price(
                current_price=current_price,
                action=action,
                regime=regime,
                analyst_posteriors=state["analyst_posteriors"],
                weights=weights,
                is_china=is_china,
            )

        # 4. Fallback path: extract percentage change from text if present
        percentage_change = None
        percentage_patterns = [
            r'rise\s*(\d+(?:\.\d+)?)%',
            r'Increase\s*(\d+(?:\.\d+)?)%',
            r'growth\s*(\d+(?:\.\d+)?)%',
            r'(\d+(?:\.\d+)?)%\s*of?rise',
        ]
        for pattern in percentage_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    percentage_change = float(match.group(1)) / 100
                    break
                except ValueError:
                    continue

        if percentage_change:
            if action == 'buy':
                return round(current_price * (1 + percentage_change), 2)
            elif action == 'sell':
                return round(current_price * (1 - percentage_change), 2)

        # 5. Default multiplier fallback for backward compatibility
        if action == 'buy':
            multiplier = 1.15 if is_china else 1.12
            return round(current_price * multiplier, 2)
        elif action == 'sell':
            multiplier = 0.95 if is_china else 0.92
            return round(current_price * multiplier, 2)
        else:  # hold
            return current_price

    def _extract_simple_decision(
        self,
        text: str,
        state: Optional[dict] = None,
        is_china: bool = True,
    ) -> dict:
        """Simple decision extraction method as fallback."""
        action = 'hold'
        if re.search(r'buy|BUY', text, re.IGNORECASE):
            action = 'buy'
        elif re.search(r'sell|SELL', text, re.IGNORECASE):
            action = 'sell'
        elif re.search(r'hold|HOLD', text, re.IGNORECASE):
            action = 'hold'

        target_price = None
        price_patterns = [
            r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
            r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # **target price**: 45.50
            r'目标价[位格]?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
            r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
            r'reasonable[Price]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)', # Reasonable price: 45.50
            r'合理[价位]?格?[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
            r'Valuation[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # Valuation: 45.50
            r'估值[:：\s]*[¥\$]?(\d+(?:\.\d+)?)',
            r'Suggestions[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # Suggestions: 45.50
            r'expected[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # expected: 45.50
            r'look[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',          # see 45.50
            r'看[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'rise[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',        # rise to 45.50
            r'涨[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'跌[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
        ]

        for pattern in price_patterns:
            price_match = re.search(pattern, text, re.IGNORECASE)
            if price_match:
                try:
                    target_price = float(price_match.group(1))
                    break
                except ValueError:
                    continue

        # If price not found, perform smart estimation
        if target_price is None:
            target_price = self._smart_price_estimation(text, action, is_china, state=state)

        result = {
            'action': action,
            'target_price': target_price,
            'confidence': 0.7,
            'risk_score': 0.5,
            'reasoning': 'Investment advice based on comprehensive analysis'
        }

        # If state contains analyst_posteriors, attach Bayesian details
        if state and isinstance(state, dict) and state.get("analyst_posteriors"):
            regime = state.get("market_regime") or "sideways"
            weights = self.weight_calculator.get_weights(regime)
            curr_p = target_price or 100.0
            if state.get("current_price") is not None:
                try:
                    curr_p = float(state["current_price"])
                except (ValueError, TypeError):
                    pass
            details = process_calibrated_signal(
                current_price=curr_p,
                action=action,
                regime=regime,
                analyst_posteriors=state["analyst_posteriors"],
                weights=weights,
                is_china=is_china,
            )
            result['bayesian_target_price'] = details['target_price']
            result['p_agg'] = details['p_agg']
            result['log_odds_agg'] = details['l_agg']
            result['weighted_move_bps'] = details['weighted_move_bps']
            result['calibrated_return'] = details['calibrated_return']
            result['confidence'] = details['confidence']
            result['risk_score'] = details['risk_score']
            result['bayesian_confidence'] = details['confidence']
            result['bayesian_risk_score'] = details['risk_score']
            if target_price is None or (curr_p and abs(target_price - curr_p) < 1e-4):
                result['target_price'] = details['target_price']

        return result

    def _extract_target_price(
        self,
        text: str,
        stock_symbol: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> Optional[float]:
        """Helper to extract target price directly from text."""
        price_patterns = [
            r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'[¥\$](\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)Yuan',
        ]
        for pattern in price_patterns:
            price_match = re.search(pattern, text)
            if price_match:
                try:
                    return float(price_match.group(1))
                except ValueError:
                    continue
        return self._smart_price_estimation(text, "buy", is_china=True)

    def _get_default_decision(self) -> dict:
        """Return to default investment decision"""
        return {
            'action': 'hold',
            'target_price': None,
            'confidence': 0.5,
            'risk_score': 0.5,
            'reasoning': 'Invalid input data, default holds suggestions'
        }
