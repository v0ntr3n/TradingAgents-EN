"""
Weight calculation tool

Automatically calculate the weight of each report based on the analyst selected by the user
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


def calculate_report_weights(
    reports: Dict[str, str],
    trading_style: Optional[str] = None
) -> Dict[str, float]:
    """
    Calculate the weight of each report based on the analyst reports selected by the user
    
    Args:
        reports: Report dictionary, key is the report field name, value is the report content (if it is an empty string or None, it means not selected)
        trading_style: trading style,"short" (short line) or"long" (medium and long term), if it is None, it will be automatically determined
    
    Returns:
        Weight dictionary, key is the report field name, value is the weight (a floating point number between 0-1)
    """
    # Mapping of report field names to analyst types
    REPORT_TO_ANALYST_TYPE = {
        "market_report": "technical",      # Market Analyst (Technical Analysis)
        "news_report": "news",             # news analyst
        "sentiment_report": "social",       # Social Media Analyst (Sentiment Analysis)
        "fundamentals_report": "fundamental",  # fundamental analyst
        "sector_report": "sector",         # Sector Analyst (Industry Analysis)
        "index_report": "index",           # Market Analyst
    }
    
    # Filter out non-empty reports (indicating that the user selected these analysts)
    selected_reports = {
        report_key: report_content
        for report_key, report_content in reports.items()
        if report_content and isinstance(report_content, str) and len(report_content.strip()) > 0
    }
    
    if not selected_reports:
        # If no report is selected, an empty weights dictionary is returned
        return {}
    
    # If no trading style is specified, it will be automatically determined
    if trading_style is None:
        trading_style = _infer_trading_style(selected_reports)
    
    # Set weights based on trading style
    if trading_style == "short":
        # Short-term weight configuration
        weights = _calculate_short_term_weights(selected_reports)
    elif trading_style == "long":
        # Medium and long-term weight allocation
        weights = _calculate_long_term_weights(selected_reports)
    else:
        # Default: average weight
        weights = _calculate_equal_weights(selected_reports)
    
    return weights


def _infer_trading_style(reports: Dict[str, str]) -> str:
    """
    Infer trading style based on selected reports
    
    Args:
        reports: Selected report dictionary
    
    Returns:
        "short" or "long"
    """
    # If you choose a fundamental analyst, it is more likely to be a medium- to long-term analyst.
    if "fundamentals_report" in reports:
        return "long"
    
    # If you choose technology, news, or social media analysts, you are more likely to be short-term
    if "market_report" in reports and "news_report" in reports and "sentiment_report" in reports:
        return "short"
    
    # If you choose a sector analyst, he is more likely to be a medium to long-term analyst.
    if "sector_report" in reports:
        return "long"
    
    # Default returns short line
    return "short"


def _calculate_short_term_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the weight of short-term transactions
    
    Short-term weight configuration:
    - Technical analysis (market_report):40%
    - News analysis (news_report):30%
    - Social media analysis (sentiment_report):30%
    - Other reports: 10% or less
    """
    weights = {}
    total_weight = 0.0
    
    # Core reporting weight
    core_reports = {
        "market_report": 0.40,      # technical analysis 40%
        "news_report": 0.30,        # news analysis 30%
        "sentiment_report": 0.30,   # social media analysis 30%
    }
    
    # Check if the core report exists
    selected_core_reports = {
        k: v for k, v in core_reports.items() if k in reports
    }
    
    if selected_core_reports:
        # If core reports are present, use default weights
        for report_key, weight in selected_core_reports.items():
            weights[report_key] = weight
            total_weight += weight
        
        # Other reports (fundamentals, sectors, market) have lower weights
        other_reports = {
            "fundamentals_report": 0.05,  # Fundamentals 5%
            "sector_report": 0.05,        # plate 5%
            "index_report": 0.10,         # Market 10%
        }
        
        for report_key, weight in other_reports.items():
            if report_key in reports:
                weights[report_key] = weight
                total_weight += weight
        
        # Normalized weights (make sure the sum is 1.0)
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
    else:
        # If core reporting is incomplete, use average weight
        weights = _calculate_equal_weights(reports)
    
    return weights


def _calculate_long_term_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the weight of medium and long-term investments
    
    Medium and long-term weight configuration:
    - Fundamental analysis (fundamentals_report):50%
    - Sector analysis (sector_report):30%
    - Risk analysis (reflected through risk multi-scenario research):20%
    - Other reports: 10% or less
    """
    weights = {}
    total_weight = 0.0
    
    # Core reporting weight
    core_reports = {
        "fundamentals_report": 0.50,  # fundamental analysis 50%
        "sector_report": 0.30,        # Sector analysis 30%
    }
    
    # Check if the core report exists
    selected_core_reports = {
        k: v for k, v in core_reports.items() if k in reports
    }
    
    if selected_core_reports:
        # If core reports are present, use default weights
        for report_key, weight in selected_core_reports.items():
            weights[report_key] = weight
            total_weight += weight
        
        # Other reports have lower weight
        other_reports = {
            "market_report": 0.10,        # Technical analysis 10% (only used to determine whether the technical situation is in a downtrend)
            "news_report": 0.05,          # news analysis 5%
            "sentiment_report": 0.05,     # social media analysis 5%
            "index_report": 0.00,         # Market analysis 0% (not paying much attention to the market in the medium and long term)
        }
        
        for report_key, weight in other_reports.items():
            if report_key in reports:
                weights[report_key] = weight
                total_weight += weight
        
        # Normalized weights (make sure the sum is 1.0)
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
    else:
        # If core reporting is incomplete, use average weight
        weights = _calculate_equal_weights(reports)
    
    return weights


def _calculate_equal_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the average weight (used when the trading style cannot be determined)
    
    Args:
        reports: Selected report dictionary
    
    Returns:
        A dictionary of weights with equal weights for all reports
    """
    if not reports:
        return {}
    
    weight = 1.0 / len(reports)
    return {report_key: weight for report_key in reports.keys()}


def format_weighted_reports_prompt(
    reports: Dict[str, str],
    weights: Dict[str, float],
    report_labels: Optional[Dict[str, str]] = None
) -> str:
    """
    Format weighted report prompt words
    
    Args:
        reports: report dictionary
        weights: weight dictionary
        report_labels: Report label dictionary (optional) to display Chinese names
    
    Returns:
        Formatted prompt text
    """
    if not report_labels:
        report_labels = {
            "market_report": "Market Analysis (Technical Analysis)",
            "news_report": "news analysis",
            "sentiment_report": "Social media analysis (market sentiment)",
            "fundamentals_report": "fundamental analysis",
            "sector_report": "Sector analysis (industry analysis)",
            "index_report": "Market analysis",
        }
    
    # Sort by weight (high to low)
    sorted_reports = sorted(
        weights.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    prompt_parts = []
    
    # High weight report (weight >= 20%) 
    high_weight_reports = [
        (report_key, weight) for report_key, weight in sorted_reports
        if weight >= 0.20 and report_key in reports
    ]
    
    if high_weight_reports:
        prompt_parts.append(" [Important report] (high weight, please pay attention)")
        for report_key, weight in high_weight_reports:
            label = report_labels.get(report_key, report_key)
            weight_pct = int(weight * 100)
            prompt_parts.append(f"- {label} (weight{weight_pct}%) : \n{reports[report_key]}\n")
    
    # Low weight report (weight < 20%) 
    low_weight_reports = [
        (report_key, weight) for report_key, weight in sorted_reports
        if weight < 0.20 and report_key in reports
    ]
    
    if low_weight_reports:
        prompt_parts.append("\n [Secondary report] (low weight, for reference only)")
        for report_key, weight in low_weight_reports:
            label = report_labels.get(report_key, report_key)
            weight_pct = int(weight * 100)
            prompt_parts.append(f"- {label} (weight{weight_pct}%, For reference only):\n{reports[report_key]}\n")
    
    # Add weight description
    if prompt_parts:
        prompt_parts.append(
            "\n**Weight description**: "
            "\n- Please focus on high-weighted reports, which are more important for investment decisions"
            "\n- Low-weighted reports are only for supplementary reference and should not be overly relied upon."
            "\n- When making a comprehensive judgment, please give appropriate attention based on the weight."
        )
    
    return "\n".join(prompt_parts)


# ==============================================================================
# Regime-Adaptive Weight Calculator (CARE-Agents R2)
# ==============================================================================

DEFAULT_ANALYST_IDS: List[str] = [
    "index_analyst_v2",
    "sector_analyst_v2",
    "market_analyst_v2",
    "fundamentals_analyst_v2",
    "news_analyst_v2",
    "social_analyst_v2",
    "chip_distribution_analyst_v2",
]

REGIMES: List[str] = ["bull", "bear", "sideways"]


class RegimeAdaptiveWeightCalculator:
    """
    Regime-Adaptive Weight Calculator using Multiplicative Weights Update
    (Exponentially Weighted Forecaster) based on multiclass Brier loss.

    Maintains separate weight vectors w[regime][analyst_id] across three market regimes:
    'bull', 'bear', and 'sideways'.
    """

    def __init__(
        self,
        analyst_ids: Optional[Sequence[str]] = None,
        initial_weights: Optional[Dict[str, Dict[str, float]]] = None,
        learning_rate: float = 0.2,
        return_threshold: float = 0.005,  # 50 bps deadband
        w_min: float = 0.0,
    ):
        """
        Initialize the regime-adaptive weight calculator.

        Args:
            analyst_ids: List of analyst identifiers. Defaults to the 7 standard v2 analysts.
            initial_weights: Optional dictionary mapping regime -> {analyst_id: weight}.
            learning_rate: Learning rate eta for MWU (default 0.2).
            return_threshold: Deadband threshold in decimal (0.005 = 50 bps) for Brier loss target classification.
            w_min: Weight floor for MWU updates (default 0.0).
        """
        self.analyst_ids = list(analyst_ids) if analyst_ids is not None else list(DEFAULT_ANALYST_IDS)
        self.learning_rate = float(learning_rate)
        self.return_threshold = float(return_threshold)
        self.w_min = float(w_min)
        self.regimes = list(REGIMES)

        if initial_weights is not None:
            self.weights: Dict[str, Dict[str, float]] = {}
            for r in self.regimes:
                if r in initial_weights:
                    user_w = initial_weights[r]
                    sub_w = {aid: float(user_w.get(aid, 0.0)) for aid in self.analyst_ids}
                    tot = sum(sub_w.values())
                    if tot > 0:
                        self.weights[r] = {k: v / tot for k, v in sub_w.items()}
                    else:
                        self.weights[r] = {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}
                else:
                    self.weights[r] = {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}
        else:
            self.weights = {
                r: {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}
                for r in self.regimes
            }

    @staticmethod
    def _normalize_regime(regime: str) -> str:
        """Normalize regime name to 'bull', 'bear', or 'sideways'."""
        if not regime or not isinstance(regime, str):
            return "sideways"
        r = regime.lower().strip()
        return r if r in REGIMES else "sideways"

    def get_weights(
        self,
        regime: str,
        active_analysts: Optional[Sequence[str]] = None,
    ) -> Dict[str, float]:
        """
        Get normalized weights for a given regime across active analysts.

        Args:
            regime: "bull", "bear", or "sideways".
            active_analysts: Optional list of active analyst IDs. If None, uses all registered analysts.

        Returns:
            Dictionary mapping analyst_id to normalized weight (sum == 1.0).
        """
        regime = self._normalize_regime(regime)
        active = list(active_analysts) if active_analysts is not None else list(self.analyst_ids)
        if not active:
            return {}

        current_regime_weights = self.weights.get(regime, {})
        sub = {aid: current_regime_weights.get(aid, 0.0) for aid in active}
        tot = sum(sub.values())
        if tot <= 0:
            return {aid: 1.0 / len(active) for aid in active}
        return {aid: w / tot for aid, w in sub.items()}

    def compute_brier_loss(
        self,
        posterior: Dict[str, Any],
        realized_return: float,
        scaled: bool = False,
    ) -> float:
        """
        Compute multiclass Brier loss for an analyst's 3-class prediction:
        [p_optimistic, p_neutral, p_cautious] vs realized market outcome.

        Target y:
            [1, 0, 0] (optimistic) if realized_return > return_threshold
            [0, 0, 1] (cautious) if realized_return < -return_threshold
            [0, 1, 0] (neutral) otherwise

        BrierLoss = sum_{k=1}^3 (p_k - y_k)^2 in [0, 2].
        If scaled=True, returns Brier / 3.0 in [0, 2/3].
        """
        p_opt = float(posterior.get("p_optimistic", 0.3333))
        p_neu = float(posterior.get("p_neutral", 0.3334))
        p_caut = float(posterior.get("p_cautious", 0.3333))
        tot = p_opt + p_neu + p_caut
        if tot > 0:
            p_opt, p_neu, p_caut = p_opt / tot, p_neu / tot, p_caut / tot
        else:
            p_opt, p_neu, p_caut = 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0

        if realized_return > self.return_threshold:
            y = [1.0, 0.0, 0.0]
        elif realized_return < -self.return_threshold:
            y = [0.0, 0.0, 1.0]
        else:
            y = [0.0, 1.0, 0.0]

        brier = (p_opt - y[0]) ** 2 + (p_neu - y[1]) ** 2 + (p_caut - y[2]) ** 2
        bounded_brier = float(max(0.0, min(2.0, brier)))
        return (bounded_brier / 3.0) if scaled else bounded_brier

    def update_weights(
        self,
        regime: str,
        analyst_posteriors: Dict[str, Dict[str, Any]],
        realized_return: float,
        learning_rate: Optional[float] = None,
        w_min: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Multiplicative Weights Update (MWU) / Exponentially Weighted Forecaster rule:
        w_new[i] = max(w_min, w_old[i] * exp(-learning_rate * brier_loss[i]))
        followed by normalization so sum(w_new) == 1.0.

        Args:
            regime: Current market regime ("bull", "bear", "sideways").
            analyst_posteriors: Dictionary mapping analyst_id -> posterior dictionary.
            realized_return: Realized return over the period.
            learning_rate: Optional learning rate override (eta).
            w_min: Optional weight floor override.

        Returns:
            Updated and normalized weight dictionary for the specified regime.
        """
        regime = self._normalize_regime(regime)
        lr = float(learning_rate) if learning_rate is not None else self.learning_rate
        floor = self.w_min if w_min is None else float(w_min)

        # Expand analyst_ids if new analysts appear in posteriors
        for aid in analyst_posteriors.keys():
            if aid not in self.analyst_ids:
                self.analyst_ids.append(aid)
                for r in self.regimes:
                    if aid not in self.weights[r]:
                        self.weights[r][aid] = 1.0 / len(self.analyst_ids)

        current_w = self.weights[regime]
        updated = {}

        for aid in self.analyst_ids:
            old_w = current_w.get(aid, 1.0 / len(self.analyst_ids))
            if aid in analyst_posteriors and isinstance(analyst_posteriors[aid], dict):
                loss = self.compute_brier_loss(analyst_posteriors[aid], realized_return)
                new_w = old_w * math.exp(-lr * loss)
            else:
                new_w = old_w
            if floor > 0.0:
                new_w = max(floor, new_w)
            updated[aid] = new_w

        tot = sum(updated.values())
        if tot > 0:
            normalized = {aid: w / tot for aid, w in updated.items()}
        else:
            normalized = {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}

        self.weights[regime] = normalized
        return normalized

    def aggregate_posteriors(
        self,
        analyst_posteriors: Dict[str, Dict[str, Any]],
        regime: str = "sideways",
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Aggregate analyst posteriors using logarithmic opinion pooling and current regime weights."""
        if weights is None:
            weights = self.get_weights(regime, active_analysts=list(analyst_posteriors.keys()))
        return aggregate_posteriors(analyst_posteriors, weights=weights)

    def reset(self) -> None:
        """Reset all weights to uniform distribution."""
        self.weights = {
            r: {aid: 1.0 / len(self.analyst_ids) for aid in self.analyst_ids}
            for r in self.regimes
        }


class RegimeMultiplicativeWeightManager(RegimeAdaptiveWeightCalculator):
    """
    Online Regime-Conditioned Multiplicative Weights Manager (MWU).
    Maintains independent analyst reliability weight vectors across market regimes
    ('bull', 'bear', 'sideways') updated online via the Exponentially Weighted Forecaster
    with weight floor w_min=0.03.
    """

    def __init__(
        self,
        analyst_ids: Optional[Sequence[str]] = None,
        initial_weights: Optional[Dict[str, Dict[str, float]]] = None,
        learning_rate: float = 0.2,
        return_threshold: float = 0.005,
        w_min: float = 0.03,
    ):
        super().__init__(
            analyst_ids=analyst_ids,
            initial_weights=initial_weights,
            learning_rate=learning_rate,
            return_threshold=return_threshold,
            w_min=w_min,
        )


def aggregate_posteriors(
    posteriors: Union[Dict[str, Dict[str, Any]], Sequence[Dict[str, Any]]],
    weights: Optional[Dict[str, float]] = None,
    eps: float = 1e-12,
) -> Dict[str, float]:
    """
    Logarithmic opinion pooling (Log-OP) aggregating analyst 3-class posteriors
    into a single calibrated consensus distribution:
        p_{agg, c} ~ exp(sum_i w_i * ln(p_{i, c}))

    Args:
        posteriors: Dict mapping analyst_id -> posterior dict, or sequence of posterior dicts.
        weights: Optional dictionary mapping analyst_id -> weight.
        eps: Epsilon floor for probability clamping before log transform.

    Returns:
        Dict with "p_optimistic", "p_neutral", "p_cautious" summing to 1.0.
    """
    classes = ["p_optimistic", "p_neutral", "p_cautious"]
    if not posteriors:
        return {"p_optimistic": 1.0 / 3.0, "p_neutral": 1.0 / 3.0, "p_cautious": 1.0 / 3.0}

    items = (
        list(posteriors.items())
        if isinstance(posteriors, dict)
        else [(f"analyst_{i}", p) for i, p in enumerate(posteriors)]
    )

    if weights is None:
        w_dict = {aid: 1.0 / len(items) for aid, _ in items}
    else:
        raw_w = {aid: max(0.0, float(weights.get(aid, 0.0))) for aid, _ in items}
        tot_w = sum(raw_w.values())
        w_dict = {aid: v / tot_w for aid, v in raw_w.items()} if tot_w > 0 else {aid: 1.0 / len(items) for aid, _ in items}

    log_agg = {c: 0.0 for c in classes}
    for aid, post in items:
        if not isinstance(post, dict):
            continue
        w = w_dict.get(aid, 0.0)
        raw_probs = [max(eps, float(post.get(c, 1.0 / 3.0))) for c in classes]
        sum_p = sum(raw_probs)
        norm_probs = [p / sum_p for p in raw_probs]
        for idx, c in enumerate(classes):
            log_agg[c] += w * math.log(norm_probs[idx])

    max_log = max(log_agg.values())
    exp_probs = {c: math.exp(log_agg[c] - max_log) for c in classes}
    tot_exp = sum(exp_probs.values())
    if tot_exp <= 0:
        return {"p_optimistic": 1.0 / 3.0, "p_neutral": 1.0 / 3.0, "p_cautious": 1.0 / 3.0}

    return {c: float(exp_probs[c] / tot_exp) for c in classes}


__all__ = [
    "DEFAULT_ANALYST_IDS",
    "REGIMES",
    "RegimeAdaptiveWeightCalculator",
    "RegimeMultiplicativeWeightManager",
    "aggregate_posteriors",
    "calculate_report_weights",
    "format_weighted_reports_prompt",
]


