"""
Weight calculation tool

Automatically calculate the weight of each report based on the analyst selected by the user
"""

from typing import Any, Dict, List, Optional, Tuple


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





import math

DEFAULT_V2_ANALYSTS = (
    "index_analyst_v2",
    "sector_analyst_v2",
    "market_analyst_v2",
    "fundamentals_analyst_v2",
    "news_analyst_v2",
    "social_analyst_v2",
    "chip_distribution_analyst_v2",
)


class RegimeMultiplicativeWeightManager:
    """
    Online Exponentially Weighted Forecaster (Multiplicative Weights Update)
    partitioned across market regimes ('bull', 'bear', 'sideways') using
    multiclass Brier loss calibration.
    """

    REGIMES = ("bull", "bear", "sideways")

    def __init__(
        self,
        analyst_ids: Optional[List[str]] = None,
        w_min: float = 0.03,
    ):
        self.analyst_ids = list(analyst_ids or DEFAULT_V2_ANALYSTS)
        self.w_min = float(w_min)
        n = len(self.analyst_ids)
        uniform = 1.0 / n if n > 0 else 1.0
        self.weights: Dict[str, Dict[str, float]] = {
            r: {a: uniform for a in self.analyst_ids}
            for r in self.REGIMES
        }
        self.history: List[Dict[str, Any]] = []

    @staticmethod
    def compute_brier_loss(
        posterior: Dict[str, Any],
        realized_return_pct: float,
        threshold_pct: float = 1.0,
    ) -> float:
        """
        Compute multiclass Brier score in [0, 2/3] between (p_optimistic, p_neutral, p_cautious)
        and the realized return outcome vector.
        """
        p_opt = float(posterior.get("p_optimistic", 1.0 / 3.0))
        p_neu = float(posterior.get("p_neutral", 1.0 / 3.0))
        p_cau = float(posterior.get("p_cautious", 1.0 / 3.0))
        s = p_opt + p_neu + p_cau
        if s > 0:
            p_opt, p_neu, p_cau = p_opt / s, p_neu / s, p_cau / s
        else:
            p_opt = p_neu = p_cau = 1.0 / 3.0

        if realized_return_pct > threshold_pct:
            y = (1.0, 0.0, 0.0)
        elif realized_return_pct < -threshold_pct:
            y = (0.0, 0.0, 1.0)
        else:
            y = (0.0, 1.0, 0.0)

        mse = ((p_opt - y[0]) ** 2 + (p_neu - y[1]) ** 2 + (p_cau - y[2]) ** 2) / 3.0
        return round(mse, 6)

    def get_regime_weights(
        self,
        regime: str,
        active_analysts: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        r = regime.lower() if regime and regime.lower() in self.REGIMES else "sideways"
        base = self.weights[r]
        keys = [k for k in (active_analysts or list(base.keys())) if k in base or active_analysts]
        if not keys:
            return {}
        raw = {k: base.get(k, 1.0 / len(keys)) for k in keys}
        total = sum(raw.values())
        if total <= 0:
            return {k: 1.0 / len(keys) for k in keys}
        return {k: v / total for k, v in raw.items()}

    def update_weights(
        self,
        regime: str,
        posteriors: Dict[str, Dict[str, Any]],
        realized_return_pct: float,
        eta: float = 0.25,
        threshold_pct: float = 1.0,
    ) -> Dict[str, float]:
        r = regime.lower() if regime and regime.lower() in self.REGIMES else "sideways"
        regime_table = self.weights[r]

        for agent_id in posteriors.keys():
            if agent_id not in regime_table:
                regime_table[agent_id] = 1.0 / max(1, len(regime_table) + 1)

        losses = {}
        unnormalized = {}
        for agent_id, w_old in regime_table.items():
            if agent_id in posteriors:
                loss = self.compute_brier_loss(posteriors[agent_id], realized_return_pct, threshold_pct=threshold_pct)
                losses[agent_id] = loss
                w_cand = w_old * math.exp(-float(eta) * loss)
            else:
                w_cand = w_old
            unnormalized[agent_id] = max(self.w_min, w_cand)

        total = sum(unnormalized.values())
        self.weights[r] = {k: v / total for k, v in unnormalized.items()}
        self.history.append({
            "regime": r,
            "realized_return_pct": realized_return_pct,
            "losses": losses,
            "updated_weights": dict(self.weights[r]),
        })
        return dict(self.weights[r])

    def aggregate_posteriors(
        self,
        regime: str,
        posteriors: Dict[str, Dict[str, Any]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        Combine analyst probability vectors using a Regime-Weighted Linear Opinion Pool
        (default `method="linear"`, matching Theorem 1) or Logarithmic Opinion Pool (`method="logarithmic"`).
        """
        if not posteriors:
            return {
                "p_optimistic": 1.0 / 3.0,
                "p_neutral": 1.0 / 3.0,
                "p_cautious": 1.0 / 3.0,
                "expected_move_bps": 0.0,
                "confidence": 0.5,
                "risk_score": 0.5,
                "recommended_action": "hold",
            }

        active_weights = self.get_regime_weights(regime, list(posteriors.keys()))
        eps = 1e-6
        expected_move_bps = 0.0

        if method == "logarithmic":
            log_opt = 0.0
            log_neu = 0.0
            log_cau = 0.0
            for agent_id, post in posteriors.items():
                w = active_weights.get(agent_id, 1.0 / len(posteriors))
                p_o = max(eps, float(post.get("p_optimistic", 1.0 / 3.0)))
                p_n = max(eps, float(post.get("p_neutral", 1.0 / 3.0)))
                p_c = max(eps, float(post.get("p_cautious", 1.0 / 3.0)))
                s = p_o + p_n + p_c
                p_o, p_n, p_c = p_o / s, p_n / s, p_c / s

                log_opt += w * math.log(p_o)
                log_neu += w * math.log(p_n)
                log_cau += w * math.log(p_c)
                expected_move_bps += w * float(post.get("expected_move_bps", 50.0))

            max_log = max(log_opt, log_neu, log_cau)
            u_opt = math.exp(log_opt - max_log)
            u_neu = math.exp(log_neu - max_log)
            u_cau = math.exp(log_cau - max_log)
            Z = u_opt + u_neu + u_cau

            P_opt = u_opt / Z
            P_neu = u_neu / Z
            P_cau = u_cau / Z
        else:
            lin_opt = 0.0
            lin_neu = 0.0
            lin_cau = 0.0
            for agent_id, post in posteriors.items():
                w = active_weights.get(agent_id, 1.0 / len(posteriors))
                p_o = max(0.0, float(post.get("p_optimistic", 1.0 / 3.0)))
                p_n = max(0.0, float(post.get("p_neutral", 1.0 / 3.0)))
                p_c = max(0.0, float(post.get("p_cautious", 1.0 / 3.0)))
                s = max(eps, p_o + p_n + p_c)
                p_o, p_n, p_c = p_o / s, p_n / s, p_c / s

                lin_opt += w * p_o
                lin_neu += w * p_n
                lin_cau += w * p_c
                expected_move_bps += w * float(post.get("expected_move_bps", 50.0))

            Z = max(eps, lin_opt + lin_neu + lin_cau)
            P_opt = lin_opt / Z
            P_neu = lin_neu / Z
            P_cau = lin_cau / Z

        entropy = 0.0
        for p in (P_opt, P_neu, P_cau):
            if p > 1e-12:
                entropy -= p * math.log2(p)
        norm_entropy = entropy / math.log2(3.0)
        confidence = max(0.0, min(1.0, 1.0 - norm_entropy))
        risk_score = max(0.0, min(1.0, 0.5 * norm_entropy + 0.5 * P_cau))

        if P_opt > P_cau and P_opt > P_neu:
            action = "buy"
        elif P_cau > P_opt and P_cau > P_neu:
            action = "sell"
        else:
            action = "hold"

        return {
            "p_optimistic": round(P_opt, 6),
            "p_neutral": round(P_neu, 6),
            "p_cautious": round(P_cau, 6),
            "expected_move_bps": round(expected_move_bps, 2),
            "confidence": round(confidence, 4),
            "risk_score": round(risk_score, 4),
            "recommended_action": action,
            "weights_used": active_weights,
        }


RegimeAdaptiveWeightCalculator = RegimeMultiplicativeWeightManager
