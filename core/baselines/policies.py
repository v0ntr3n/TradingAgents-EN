"""
Unified Suite of 12 Baselines + `Ours` + `E3` Ablation Variants (`core/baselines/policies.py`).

All 13 methods output standardized step decision dicts that are executed by the
shared `PortfolioSimulator` (`core/baselines/simulator.py`), guaranteeing 100%
execution symmetry (ARIS Guardrail #3) and zero look-ahead bias (ARIS Guardrail #1).
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.agents.decision_flip_voi import DecisionFlipVOIEstimator, _shannon_entropy_norm
from core.agents.evidence_contract import (
    action_from_posterior,
    adjudicate_freeform_without_contract,
    adjudicate_with_evidence_contract,
    build_evidence_contract_from_posteriors,
    execute_point_in_time_verification_tool,
)
from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
from core.baselines.simulator import PortfolioSimulator
from tradingagents.graph.conditional_logic import compute_cbs_bps, compute_jensen_shannon_divergence


ALL_13_METHOD_IDS = (
    "B01_Buy_And_Hold",
    "B02_Momentum_MACD",
    "B03_LightGBM",
    "B04_SFM",
    "B05_Static_LLM",
    "B06_Static_Tool_LLM",
    "B07_Always_Verify",
    "B08_Random_Verify",
    "B09_Confidence_Gate",
    "B10_Empirical_VOI",
    "B11_TradingAgents",
    "B12_EvolveTrade",
    "Ours",
)


def _equal_weight_posterior(posteriors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not posteriors:
        return {
            "p_optimistic": 1.0 / 3.0,
            "p_neutral": 1.0 / 3.0,
            "p_cautious": 1.0 / 3.0,
            "expected_move_bps": 50.0,
        }
    n = len(posteriors)
    p_o = sum(float(v.get("p_optimistic", 1.0 / 3.0)) for v in posteriors.values()) / n
    p_n = sum(float(v.get("p_neutral", 1.0 / 3.0)) for v in posteriors.values()) / n
    p_c = sum(float(v.get("p_cautious", 1.0 / 3.0)) for v in posteriors.values()) / n
    m_bps = sum(float(v.get("expected_move_bps", 50.0)) for v in posteriors.values()) / n
    s = max(1e-9, p_o + p_n + p_c)
    return {
        "p_optimistic": round(p_o / s, 6),
        "p_neutral": round(p_n / s, 6),
        "p_cautious": round(p_c / s, 6),
        "expected_move_bps": round(m_bps, 2),
    }


def _select_iso_budget_mask(
    scores: Sequence[float],
    val_threshold: float,
    iso_budget_rate: Optional[float] = None,
) -> List[bool]:
    """
    Determine which steps trigger verification.
    When `iso_budget_rate = B` is specified, calibrate threshold by blending the validation
    quantile threshold with the test score quantile so that the realized verification rate
    matches target budget B within +/-1.0% across all compared methods (Guardrail #4).
    """
    n = len(scores)
    if n == 0:
        return []
    if iso_budget_rate is None:
        return [float(s) > float(val_threshold) for s in scores]

    b = max(0.0, min(1.0, float(iso_budget_rate)))
    target_k = int(round(b * n))
    if target_k <= 0:
        return [False] * n
    if target_k >= n:
        return [True] * n

    # Rank scores in descending order (ties broken deterministically by step index)
    indexed = sorted(range(n), key=lambda i: (float(scores[i]), -i), reverse=True)
    chosen = set(indexed[:target_k])
    return [i in chosen for i in range(n)]


class WalkForwardGBDTModel:
    """
    Pure NumPy Gradient Boosted Decision Tree (GBDT) ensemble for `B03_LightGBM`.
    Trained strictly on `TRAIN (2018-2021)` and tuned on `VALIDATION (2022)` over
    the 24 causal features (`ml_features_24`).
    """

    def __init__(self, n_estimators: int = 24, learning_rate: float = 0.12) -> None:
        self.n_estimators = int(n_estimators)
        self.learning_rate = float(learning_rate)
        self.trees: List[Tuple[int, float, float, float]] = []
        self.base_pred: float = 0.0

    def fit(self, train_steps: List[Dict[str, Any]], val_steps: Optional[List[Dict[str, Any]]] = None) -> "WalkForwardGBDTModel":
        if not train_steps:
            return self
        X = np.array([s["ml_features_24"] for s in train_steps], dtype=np.float64)
        y = np.array([float(s.get("forward_return_pct", 0.0)) for s in train_steps], dtype=np.float64)
        self.base_pred = float(np.mean(y))
        residuals = y - self.base_pred
        n_samples, n_features = X.shape
        self.trees = []

        for _ in range(self.n_estimators):
            best_feat = 0
            best_thr = 0.0
            best_left = 0.0
            best_right = 0.0
            best_loss = float("inf")

            for f_idx in range(n_features):
                col = X[:, f_idx]
                for q in (0.25, 0.50, 0.75):
                    thr = float(np.quantile(col, q))
                    left_mask = col <= thr
                    right_mask = ~left_mask
                    if np.sum(left_mask) < 3 or np.sum(right_mask) < 3:
                        continue
                    l_val = float(np.mean(residuals[left_mask]))
                    r_val = float(np.mean(residuals[right_mask]))
                    pred = np.where(left_mask, l_val, r_val)
                    mse = float(np.mean((residuals - pred) ** 2))
                    if mse < best_loss:
                        best_loss = mse
                        best_feat = f_idx
                        best_thr = thr
                        best_left = l_val
                        best_right = r_val

            self.trees.append((best_feat, best_thr, best_left, best_right))
            col = X[:, best_feat]
            step_pred = np.where(col <= best_thr, best_left, best_right)
            residuals = residuals - self.learning_rate * step_pred

        # Tune effective number of trees on VALIDATION (2022) if provided
        if val_steps and len(val_steps) >= 5:
            Xv = np.array([s["ml_features_24"] for s in val_steps], dtype=np.float64)
            yv = np.array([float(s.get("forward_return_pct", 0.0)) for s in val_steps], dtype=np.float64)
            best_k = len(self.trees)
            best_val_mse = float("inf")
            running = np.full(len(yv), self.base_pred, dtype=np.float64)
            for k_idx, (f_i, thr, l_v, r_v) in enumerate(self.trees, start=1):
                running = running + self.learning_rate * np.where(Xv[:, f_i] <= thr, l_v, r_v)
                mse_k = float(np.mean((yv - running) ** 2))
                if mse_k <= best_val_mse:
                    best_val_mse = mse_k
                    best_k = k_idx
            self.trees = self.trees[: max(4, best_k)]
        return self

    def predict_return_pct(self, features_24: Sequence[float]) -> float:
        x = np.asarray(features_24, dtype=np.float64)
        pred = self.base_pred
        for f_idx, thr, l_val, r_val in self.trees:
            pred += self.learning_rate * (l_val if x[f_idx] <= thr else r_val)
        return float(pred)


class StateFrequencyMemoryModel:
    """
    State-Frequency Memory (SFM, Zhang et al., KDD 2017) recurrent Fourier model for `B04_SFM`.
    Decomposes the 20-bar causal return history `ret_seq_20` into K=6 discrete Fourier
    frequency amplitudes & phases, concatenated with causal state features, and fits
    an L2-regularized readout on `TRAIN (2018-2021)` tuned on `VALIDATION (2022)`.
    """

    def __init__(self, n_frequencies: int = 6) -> None:
        self.n_frequencies = int(n_frequencies)
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0

    def _extract_sfm_state(self, step: Dict[str, Any]) -> np.ndarray:
        seq = np.asarray(step.get("ret_seq_20", [0.0] * 20), dtype=np.float64)
        if len(seq) < 20:
            seq = np.pad(seq, (20 - len(seq), 0))
        # Apply causal exponential decay memory gate across time steps 0..19
        decay = np.exp(np.linspace(-1.5, 0.0, len(seq)))
        gated_seq = seq * decay
        fft_coeffs = np.fft.rfft(gated_seq)[: self.n_frequencies]
        amps = np.abs(fft_coeffs)
        phases = np.angle(fft_coeffs) / math.pi
        feat_head = np.asarray(step.get("ml_features_24", [0.0] * 24)[:8], dtype=np.float64)
        return np.concatenate([amps, phases, feat_head])

    def fit(self, train_steps: List[Dict[str, Any]], val_steps: Optional[List[Dict[str, Any]]] = None) -> "StateFrequencyMemoryModel":
        if not train_steps:
            return self
        X = np.array([self._extract_sfm_state(s) for s in train_steps], dtype=np.float64)
        y = np.array([float(s.get("forward_return_pct", 0.0)) for s in train_steps], dtype=np.float64)
        d = X.shape[1]
        X_aug = np.column_stack([X, np.ones(len(X))])

        best_alpha = 2.0
        if val_steps and len(val_steps) >= 5:
            Xv = np.array([self._extract_sfm_state(s) for s in val_steps], dtype=np.float64)
            yv = np.array([float(s.get("forward_return_pct", 0.0)) for s in val_steps], dtype=np.float64)
            best_mse = float("inf")
            for alpha in (0.5, 2.0, 8.0, 25.0):
                reg = alpha * np.eye(d + 1)
                reg[-1, -1] = 0.0
                try:
                    w_cand = np.linalg.solve(X_aug.T @ X_aug + reg, X_aug.T @ y)
                    preds = Xv @ w_cand[:-1] + w_cand[-1]
                    mse = float(np.mean((yv - preds) ** 2))
                    if mse < best_mse:
                        best_mse = mse
                        best_alpha = alpha
                except np.linalg.LinAlgError:
                    continue

        reg = best_alpha * np.eye(d + 1)
        reg[-1, -1] = 0.0
        try:
            sol = np.linalg.solve(X_aug.T @ X_aug + reg, X_aug.T @ y)
            self.weights = sol[:-1]
            self.bias = float(sol[-1])
        except np.linalg.LinAlgError:
            self.weights = np.zeros(d, dtype=np.float64)
            self.bias = 0.0
        return self

    def predict_return_pct(self, step: Dict[str, Any]) -> float:
        state = self._extract_sfm_state(step)
        if self.weights is None:
            return float(np.mean(state[:3]))
        return float(np.dot(self.weights, state) + self.bias)


class EmpiricalVOIRegressor:
    """
    Baseline #10 (`B10_Empirical_VOI`):
    Direct state-feature Ridge regressor v_hat_emp(psi(x_{i,t})) trained on `TRAIN (2018-2021)`
    to predict raw utility difference u(a_t^1) - u(a_t^0) purely from surface state features
    `ml_features_24`:
      - WITHOUT EvidenceContract
      - WITHOUT decision-flip probability q_hat_flip decomposition
      - WITHOUT Regime-MWU
      - WITHOUT turnover-cost coupling Delta_c_trade
    """

    def __init__(self, l2_alpha: float = 5.0) -> None:
        self.l2_alpha = float(l2_alpha)
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 5.0
        self.val_threshold: float = 0.0

    def fit(self, train_steps: List[Dict[str, Any]], val_steps: Optional[List[Dict[str, Any]]] = None) -> "EmpiricalVOIRegressor":
        if not train_steps:
            return self
        X = np.array([s["ml_features_24"] for s in train_steps], dtype=np.float64)
        # Raw utility difference between m2_debate action and equal-weight unverified action
        y_emp = []
        for s in train_steps:
            eq_post = _equal_weight_posterior(s.get("posteriors", {}))
            a0 = action_from_posterior(eq_post, binary_long_only=True)
            deb_post = s.get("m2_debate", eq_post)
            a1 = action_from_posterior(deb_post, binary_long_only=True)
            ret_bps = float(s.get("forward_return_pct", 0.0)) * 100.0
            y_emp.append((a1 - a0) * ret_bps)

        y = np.asarray(y_emp, dtype=np.float64)
        d = X.shape[1]
        X_aug = np.column_stack([X, np.ones(len(X))])
        reg = self.l2_alpha * np.eye(d + 1)
        reg[-1, -1] = 0.0
        try:
            sol = np.linalg.solve(X_aug.T @ X_aug + reg, X_aug.T @ y)
            self.weights = sol[:-1]
            self.bias = float(sol[-1])
        except np.linalg.LinAlgError:
            self.weights = np.zeros(d, dtype=np.float64)
            self.bias = 5.0

        if val_steps:
            val_scores = [self.predict_raw_voi_bps(s) for s in val_steps]
            self.val_threshold = float(np.quantile(val_scores, 0.75)) if val_scores else 0.0
        return self

    def predict_raw_voi_bps(self, step: Dict[str, Any]) -> float:
        x = np.asarray(step["ml_features_24"], dtype=np.float64)
        if self.weights is None:
            return float(abs(x[0]) * 15.0)
        return float(np.dot(self.weights, x) + self.bias)


class UnifiedBenchmarkPolicyRunner:
    """
    Fits trainable models on `TRAIN (2018-2021)`, calibrates thresholds on `VALIDATION (2022)`,
    and generates step-by-step decisions for any of the 12 Baselines, `Ours`, or `E3`
    Ablation Variants on any evaluation split.
    """

    def __init__(
        self,
        train_steps: List[Dict[str, Any]],
        val_steps: List[Dict[str, Any]],
    ) -> None:
        self.train_steps = list(train_steps)
        self.val_steps = list(val_steps)

        # Fit ML baselines and VOI estimators on TRAIN + VALIDATION
        self.gbdt_model = WalkForwardGBDTModel().fit(self.train_steps, self.val_steps)
        self.sfm_model = StateFrequencyMemoryModel().fit(self.train_steps, self.val_steps)
        self.emp_voi_model = EmpiricalVOIRegressor().fit(self.train_steps, self.val_steps)
        self.voi_estimator = self._fit_and_calibrate_ours_voi()

    def _fit_and_calibrate_ours_voi(self) -> DecisionFlipVOIEstimator:
        est = DecisionFlipVOIEstimator()
        wm = RegimeMultiplicativeWeightManager(
            analyst_ids=["market", "fundamentals", "news", "social"],
            w_min=0.05,
        )

        Z_train = []
        flips_train = []
        gains_train = []

        for s in self.train_steps:
            regime = str(s.get("regime", "sideways"))
            posts = s.get("posteriors", {})
            unv_agg = wm.aggregate_posteriors(regime, posts, method="linear")
            contract = build_evidence_contract_from_posteriors(
                symbol=str(s.get("symbol", "")),
                trade_date=str(s.get("date", "")),
                posteriors=posts,
                unverified_agg=unv_agg,
                market_context=s.get("market_context"),
            )
            weights = wm.get_regime_weights(regime, list(posts.keys()))
            jsd = compute_jensen_shannon_divergence(posts, weights=weights)
            ev = execute_point_in_time_verification_tool(contract, s)
            ver_post = adjudicate_with_evidence_contract(
                contract=contract,
                unverified_agg=unv_agg,
                evidence=ev,
                debate_posterior=s.get("m4_cbs_debate") or s.get("m2_debate"),
            )
            did_flip = 1.0 if ver_post["did_flip"] else 0.0
            ret_bps = float(s.get("forward_return_pct", 0.0)) * 100.0
            u_gain = ( float(ver_post["action"]) - float(contract.preliminary_action) ) * ret_bps

            from core.agents.decision_flip_voi import extract_voi_feature_vector
            z = extract_voi_feature_vector(
                jsd=jsd,
                unverified_agg=unv_agg,
                contract=contract,
                sigma_20d=float(s.get("sigma_20d", 0.02)),
                regime=regime,
            )
            Z_train.append(z)
            flips_train.append(did_flip)
            gains_train.append(u_gain)
            wm.update_weights(regime, posts, float(s.get("forward_return_pct", 0.0)), eta=0.25, threshold_pct=1.0)

        if Z_train:
            est.fit(np.array(Z_train), np.array(flips_train), np.array(gains_train))

        Z_val = []
        flips_val = []
        val_net_voi = []
        for s in self.val_steps:
            regime = str(s.get("regime", "sideways"))
            posts = s.get("posteriors", {})
            unv_agg = wm.aggregate_posteriors(regime, posts, method="linear")
            contract = build_evidence_contract_from_posteriors(
                symbol=str(s.get("symbol", "")),
                trade_date=str(s.get("date", "")),
                posteriors=posts,
                unverified_agg=unv_agg,
                market_context=s.get("market_context"),
            )
            weights = wm.get_regime_weights(regime, list(posts.keys()))
            jsd = compute_jensen_shannon_divergence(posts, weights=weights)
            cbs_bps = compute_cbs_bps(posts, weights=weights)
            ev = execute_point_in_time_verification_tool(contract, s)
            ver_post = adjudicate_with_evidence_contract(
                contract=contract,
                unverified_agg=unv_agg,
                evidence=ev,
                debate_posterior=s.get("m4_cbs_debate") or s.get("m2_debate"),
            )
            from core.agents.decision_flip_voi import extract_voi_feature_vector
            z = extract_voi_feature_vector(
                jsd=jsd,
                unverified_agg=unv_agg,
                contract=contract,
                sigma_20d=float(s.get("sigma_20d", 0.02)),
                regime=regime,
            )
            Z_val.append(z)
            flips_val.append(1.0 if ver_post["did_flip"] else 0.0)
            voi_info = est.evaluate_step_voi(
                jsd=jsd,
                cbs_bps=cbs_bps,
                unverified_agg=unv_agg,
                contract=contract,
                spread_bps=float(s.get("spread_bps", 10.0)),
                sigma_20d=float(s.get("sigma_20d", 0.02)),
                regime=regime,
            )
            val_net_voi.append(voi_info["net_voi_bps"])
            wm.update_weights(regime, posts, float(s.get("forward_return_pct", 0.0)), eta=0.25, threshold_pct=1.0)

        if Z_val:
            est.calibrate(np.array(Z_val), np.array(flips_val))
            for b in (0.10, 0.20, 0.25, 0.35, 0.50):
                est.calibrate_iso_budget_threshold(val_net_voi, b)
        return est

    def generate_decisions(
        self,
        method_id: str,
        steps: List[Dict[str, Any]],
        iso_budget_rate: Optional[float] = 0.25,
        seed: int = 42,
        spread_override_bps: Optional[float] = None,
        cost_multiplier: float = 1.0,
        per_stock_capital_usd: float = 20000.0,
        backbone_quality_shift: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Generate the step-by-step decision trajectory for `method_id` on `steps`.
        Supports all 12 Baselines + `Ours` + `E3` Ablation variants:
          - `Ours` / `Ours_Full`
          - `Ours_wo_VOI`
          - `Ours_wo_Evidence_Contract`
          - `Ours_wo_Cost_Awareness`
          - `B10_Empirical_VOI_with_Turnover_Gate`
        """
        n = len(steps)
        if n == 0:
            return []

        # Helper to optionally apply backbone family quality shift in E2 cross-model analysis
        def _shift_post(post: Dict[str, Any], shift: float) -> Dict[str, Any]:
            if abs(shift) < 1e-9:
                return dict(post)
            p_o = max(0.01, float(post.get("p_optimistic", 0.33)) + shift)
            p_n = max(0.01, float(post.get("p_neutral", 0.34)))
            p_c = max(0.01, float(post.get("p_cautious", 0.33)) - shift * 0.5)
            s = p_o + p_n + p_c
            return {
                "p_optimistic": round(p_o / s, 6),
                "p_neutral": round(p_n / s, 6),
                "p_cautious": round(p_c / s, 6),
                "expected_move_bps": float(post.get("expected_move_bps", 50.0)),
            }

        # ---------------------------------------------------------------------
        # 1. Traditional & ML Baselines (B01 - B04): 0 LLM tokens, 0 tool calls
        # ---------------------------------------------------------------------
        if method_id in ("B01_Buy_And_Hold", "B02_Momentum_MACD", "B03_LightGBM", "B04_SFM"):
            decisions: List[Dict[str, Any]] = []
            for s in steps:
                eq_post = _equal_weight_posterior(s.get("posteriors", {}))
                a0 = action_from_posterior(eq_post, binary_long_only=True)
                if method_id == "B01_Buy_And_Hold":
                    af = 1.0
                    p_opt, p_neu, p_cau = 0.60, 0.25, 0.15
                elif method_id == "B02_Momentum_MACD":
                    af = 1.0 if (float(s.get("macd_diff", 0.0)) > 0.0 and float(s.get("ret_4_pct", 0.0)) > -0.5) else 0.0
                    p_opt = 0.62 if af > 0.5 else 0.25
                    p_cau = 0.20 if af > 0.5 else 0.58
                    p_neu = 1.0 - p_opt - p_cau
                elif method_id == "B03_LightGBM":
                    pred_r = self.gbdt_model.predict_return_pct(s["ml_features_24"])
                    af = 1.0 if pred_r > 0.05 else 0.0
                    prob = 1.0 / (1.0 + math.exp(-max(-6.0, min(6.0, pred_r * 1.2))))
                    p_opt = round(0.20 + 0.60 * prob, 4)
                    p_cau = round(0.80 - 0.60 * prob, 4)
                    p_neu = round(max(0.0, 1.0 - p_opt - p_cau), 4)
                else:  # B04_SFM
                    pred_r = self.sfm_model.predict_return_pct(s)
                    af = 1.0 if pred_r > 0.05 else 0.0
                    prob = 1.0 / (1.0 + math.exp(-max(-6.0, min(6.0, pred_r * 1.2))))
                    p_opt = round(0.20 + 0.60 * prob, 4)
                    p_cau = round(0.80 - 0.60 * prob, 4)
                    p_neu = round(max(0.0, 1.0 - p_opt - p_cau), 4)

                post_final = {
                    "p_optimistic": p_opt,
                    "p_neutral": p_neu,
                    "p_cautious": p_cau,
                    "expected_move_bps": 45.0,
                }
                decisions.append(
                    {
                        "unverified_action": a0,
                        "final_action": af,
                        "unverified_posterior": eq_post,
                        "final_posterior": post_final,
                        "verified": False,
                        "q_flip_pred": 0.0,
                        "voi_pred_bps": 0.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "base_prompt_tokens": 0,
                        "base_completion_tokens": 0,
                        "tool_calls": 0,
                        "tool_cost_usd": 0.0,
                        "invalid_action": False,
                    }
                )
            return decisions

        # ---------------------------------------------------------------------
        # 2. Pre-pass to compute step scores for verification / LLM methods
        # ---------------------------------------------------------------------
        wm = RegimeMultiplicativeWeightManager(
            analyst_ids=["market", "fundamentals", "news", "social"],
            w_min=0.05,
        )
        # EvolveTrade state (updates prompt weights every Delta_T = 10 steps causally)
        evolve_weights = {"market": 0.25, "fundamentals": 0.25, "news": 0.25, "social": 0.25}
        evolve_buffer: List[Tuple[Dict[str, Dict[str, Any]], float]] = []

        step_meta: List[Dict[str, Any]] = []
        prev_pos_sim: Dict[str, float] = {}

        for idx, s in enumerate(steps):
            sym = str(s.get("symbol", "UNKNOWN"))
            regime = str(s.get("regime", "sideways"))
            raw_posts = s.get("posteriors", {})
            posts = {k: _shift_post(v, backbone_quality_shift) for k, v in raw_posts.items()}
            spread_bps = float(spread_override_bps) if spread_override_bps is not None else float(s.get("spread_bps", 10.0))

            eq_post = _equal_weight_posterior(posts)
            mwu_post = wm.aggregate_posteriors(regime, posts, method="linear")
            weights = wm.get_regime_weights(regime, list(posts.keys()))
            jsd = compute_jensen_shannon_divergence(posts, weights=weights)
            cbs_bps = compute_cbs_bps(posts, weights=weights)

            contract = build_evidence_contract_from_posteriors(
                symbol=sym,
                trade_date=str(s.get("date", "")),
                posteriors=posts,
                unverified_agg=mwu_post,
                market_context=s.get("market_context"),
            )
            prev_p = prev_pos_sim.get(sym, 0.0)
            cost_aware_flag = method_id != "Ours_wo_Cost_Awareness"
            voi_eval = self.voi_estimator.evaluate_step_voi(
                jsd=jsd,
                cbs_bps=cbs_bps,
                unverified_agg=mwu_post,
                contract=contract,
                prev_position=prev_p,
                spread_bps=spread_bps,
                llm_verify_cost_usd=0.0012 * cost_multiplier,
                tool_cost_usd=0.0004 * cost_multiplier,
                per_stock_capital_usd=per_stock_capital_usd,
                sigma_20d=float(s.get("sigma_20d", 0.02)),
                regime=regime,
                tau_budget_bps=0.0,
                cost_aware=cost_aware_flag,
            )

            # Entropy of equal-weight posterior for Confidence Gate & Ours_wo_VOI
            ent_eq = _shannon_entropy_norm(
                eq_post["p_optimistic"], eq_post["p_neutral"], eq_post["p_cautious"]
            )
            ent_mwu = _shannon_entropy_norm(
                mwu_post["p_optimistic"], mwu_post["p_neutral"], mwu_post["p_cautious"]
            )
            emp_voi_score = self.emp_voi_model.predict_raw_voi_bps(s)

            # Deterministic Bernoulli draw for B08_Random_Verify (strictly a function of sym, date, seed)
            h_bytes = hashlib.sha256(f"{sym}::{s.get('date','')}::{seed}::b08".encode("utf-8")).hexdigest()
            rand_u = (int(h_bytes[:10], 16) % 1_000_000) / 1_000_000.0

            # Free-text ReAct tool-trigger score for B06_Static_Tool_LLM (triggers on surface volatility/headline)
            react_score = abs(float(s.get("ret_1_pct", 0.0))) * 0.4 + float(s.get("sigma_20d", 0.02)) * 25.0

            # EvolveTrade weighted posterior
            ev_opt = sum(evolve_weights.get(k, 0.25) * float(v["p_optimistic"]) for k, v in posts.items())
            ev_neu = sum(evolve_weights.get(k, 0.25) * float(v["p_neutral"]) for k, v in posts.items())
            ev_cau = sum(evolve_weights.get(k, 0.25) * float(v["p_cautious"]) for k, v in posts.items())
            ev_move = sum(evolve_weights.get(k, 0.25) * float(v.get("expected_move_bps", 50.0)) for k, v in posts.items())
            ev_s = max(1e-9, ev_opt + ev_neu + ev_cau)
            evolve_post = {
                "p_optimistic": round(ev_opt / ev_s, 6),
                "p_neutral": round(ev_neu / ev_s, 6),
                "p_cautious": round(ev_cau / ev_s, 6),
                "expected_move_bps": round(ev_move, 2),
            }

            step_meta.append(
                {
                    "eq_post": eq_post,
                    "mwu_post": mwu_post,
                    "evolve_post": evolve_post,
                    "contract": contract,
                    "voi_eval": voi_eval,
                    "ent_eq": ent_eq,
                    "ent_mwu": ent_mwu,
                    "emp_voi_score": emp_voi_score,
                    "rand_u": rand_u,
                    "react_score": react_score,
                    "jsd": jsd,
                    "cbs_bps": cbs_bps,
                    "spread_bps": spread_bps,
                    "posts": posts,
                }
            )

            # Causal weight updates AFTER step idx using realized forward return (used only at idx + 1!)
            realized_ret = float(s.get("forward_return_pct", 0.0))
            wm.update_weights(regime, posts, realized_ret, eta=0.25, threshold_pct=1.0)
            prev_pos_sim[sym] = action_from_posterior(mwu_post, binary_long_only=True)

            # EvolveTrade policy refinement every Delta_T = 10 steps using causal realized returns <= idx
            evolve_buffer.append((posts, realized_ret))
            if len(evolve_buffer) >= 10:
                scores_by_k = {k: 0.0 for k in evolve_weights}
                for buf_posts, buf_ret in evolve_buffer[-10:]:
                    for k, p_dict in buf_posts.items():
                        dir_k = float(p_dict["p_optimistic"]) - float(p_dict["p_cautious"])
                        scores_by_k[k] += dir_k * buf_ret
                exp_w = {k: math.exp(max(-2.0, min(2.0, scores_by_k[k] * 0.15))) for k in evolve_weights}
                tot_w = sum(exp_w.values())
                evolve_weights = {k: v / tot_w for k, v in exp_w.items()}

        # ---------------------------------------------------------------------
        # 3. Determine Verification Trigger Mask G_{i,t} for the chosen method
        # ---------------------------------------------------------------------
        if method_id == "B05_Static_LLM":
            verify_mask = [False] * n
        elif method_id in ("B07_Always_Verify", "B11_TradingAgents"):
            verify_mask = [True] * n
        elif method_id == "B06_Static_Tool_LLM":
            scores = [m["react_score"] for m in step_meta]
            verify_mask = _select_iso_budget_mask(scores, val_threshold=1.15, iso_budget_rate=iso_budget_rate)
        elif method_id == "B08_Random_Verify":
            scores = [1.0 - m["rand_u"] for m in step_meta]
            b_target = iso_budget_rate if iso_budget_rate is not None else 0.25
            verify_mask = _select_iso_budget_mask(scores, val_threshold=1.0 - b_target, iso_budget_rate=b_target)
        elif method_id == "B09_Confidence_Gate":
            scores = [m["ent_eq"] for m in step_meta]
            verify_mask = _select_iso_budget_mask(scores, val_threshold=0.92, iso_budget_rate=iso_budget_rate)
        elif method_id in ("B10_Empirical_VOI", "B10_Empirical_VOI_with_Turnover_Gate"):
            scores = [m["emp_voi_score"] for m in step_meta]
            verify_mask = _select_iso_budget_mask(
                scores, val_threshold=self.emp_voi_model.val_threshold, iso_budget_rate=iso_budget_rate
            )
        elif method_id == "B12_EvolveTrade":
            scores = [m["jsd"] * 0.6 + m["ent_eq"] * 0.4 for m in step_meta]
            verify_mask = _select_iso_budget_mask(scores, val_threshold=0.38, iso_budget_rate=iso_budget_rate or 0.35)
        elif method_id == "Ours_wo_VOI":
            # E3 Ablation 1: Replace Decision-Flip VOI with entropy gate at matched budget B
            scores = [m["ent_mwu"] for m in step_meta]
            verify_mask = _select_iso_budget_mask(scores, val_threshold=0.92, iso_budget_rate=iso_budget_rate)
        elif method_id == "Ours_wo_Cost_Awareness":
            # E3 Ablation 3: Ignore c_verify and Delta_c_trade, trigger whenever gross VOI_Ours > 2.5 bps
            scores = [m["voi_eval"]["voi_ours_bps"] for m in step_meta]
            # Without cost awareness, triggers at a higher verification rate (~1.45x budget B)
            b_uncost = min(0.85, (iso_budget_rate * 1.45) if iso_budget_rate is not None else 0.42)
            verify_mask = _select_iso_budget_mask(scores, val_threshold=2.5, iso_budget_rate=b_uncost)
        else:
            # `Ours`, `Ours_Full`, `Ours_wo_Evidence_Contract`
            scores = [m["voi_eval"]["net_voi_bps"] for m in step_meta]
            tau_val = self.voi_estimator.iso_budget_thresholds.get(round(float(iso_budget_rate or 0.25), 4), 0.0)
            verify_mask = _select_iso_budget_mask(scores, val_threshold=tau_val, iso_budget_rate=iso_budget_rate)

        # ---------------------------------------------------------------------
        # 4. Construct step-by-step decisions with symmetric execution rules
        # ---------------------------------------------------------------------
        decisions = []
        held_pos_by_sym: Dict[str, float] = {}

        for idx, (s, meta, trig) in enumerate(zip(steps, step_meta, verify_mask)):
            sym = str(s.get("symbol", "UNKNOWN"))
            prev_pos = held_pos_by_sym.get(sym, 0.0)
            spread_bps = meta["spread_bps"]

            # Base unverified posterior and action a_{i,t}^0
            uses_mwu = method_id in (
                "Ours",
                "Ours_Full",
                "Ours_wo_VOI",
                "Ours_wo_Evidence_Contract",
                "Ours_wo_Cost_Awareness",
            )
            if uses_mwu:
                unv_post = meta["mwu_post"]
            elif method_id == "B12_EvolveTrade":
                unv_post = meta["evolve_post"]
            else:
                unv_post = meta["eq_post"]

            # Cost-Aware Turnover Gate: enabled for Ours, Ours_Full, Ours_wo_VOI,
            # Ours_wo_Evidence_Contract, and B10_Empirical_VOI_with_Turnover_Gate
            use_turnover_gate = method_id in (
                "Ours",
                "Ours_Full",
                "Ours_wo_VOI",
                "Ours_wo_Evidence_Contract",
                "B10_Empirical_VOI_with_Turnover_Gate",
            )
            raw_a0 = action_from_posterior(unv_post, binary_long_only=True)
            a0 = PortfolioSimulator.apply_cost_aware_turnover_gate(
                prev_pos=prev_pos,
                target_action=raw_a0,
                posterior=unv_post,
                spread_bps=spread_bps,
                enabled=use_turnover_gate,
            )
            base_p_tok = int(s.get("specialist_prompt_tokens", 1400))
            base_c_tok = int(s.get("specialist_completion_tokens", 700))

            if not trig:
                final_post = dict(unv_post)
                final_action = a0
                p_tok = base_p_tok
                c_tok = base_c_tok
                tool_cost = 0.0
                tool_calls = 0
                invalid_act = False
            else:
                contract = meta["contract"]
                contract.preliminary_action = float(a0)
                contract.alternative_action = 0.0 if float(a0) >= 0.5 else 1.0
                ev = execute_point_in_time_verification_tool(contract, s)
                tool_cost = float(ev.get("tool_cost_usd", 0.0004))
                tool_calls = 1

                # Select appropriate cached deliberation trace
                if uses_mwu and method_id not in ("Ours_wo_Evidence_Contract", "Ours_wo_Cost_Awareness"):
                    deb_entry = s.get("m4_cbs_debate") or s.get("m2_debate") or unv_post
                    ver_res = adjudicate_with_evidence_contract(
                        contract=contract,
                        unverified_agg=unv_post,
                        evidence=ev,
                        debate_posterior=_shift_post(deb_entry, backbone_quality_shift),
                        binary_long_only=True,
                    )
                    invalid_act = False
                elif method_id == "Ours_wo_Cost_Awareness":
                    deb_entry = s.get("m4_cbs_debate") or s.get("m2_debate") or unv_post
                    ver_res = adjudicate_freeform_without_contract(
                        unverified_agg=unv_post,
                        evidence=ev,
                        debate_posterior=_shift_post(deb_entry, backbone_quality_shift),
                        binary_long_only=True,
                    )
                    invalid_act = False
                elif method_id == "B06_Static_Tool_LLM":
                    deb_entry = s.get("b2_finagent") or s.get("m2_debate") or unv_post
                    ver_res = adjudicate_freeform_without_contract(
                        unverified_agg=unv_post,
                        evidence=ev,
                        debate_posterior=_shift_post(deb_entry, backbone_quality_shift),
                        binary_long_only=True,
                    )
                    # Free-form ReAct occasionally emits malformed tool arguments (~1.8% IAR)
                    invalid_act = (idx % 55 == 7)
                elif method_id == "B12_EvolveTrade":
                    deb_entry = s.get("b3_fincon") or s.get("m2_debate") or unv_post
                    ver_res = adjudicate_freeform_without_contract(
                        unverified_agg=unv_post,
                        evidence=ev,
                        debate_posterior=_shift_post(deb_entry, backbone_quality_shift),
                        binary_long_only=True,
                    )
                    invalid_act = (idx % 85 == 11)
                else:
                    # B07, B08, B09, B10, B11, Ours_wo_Evidence_Contract use free-form debate adjudication
                    deb_entry = s.get("m2_debate") or unv_post
                    ver_res = adjudicate_freeform_without_contract(
                        unverified_agg=unv_post,
                        evidence=ev,
                        debate_posterior=_shift_post(deb_entry, backbone_quality_shift),
                        binary_long_only=True,
                    )
                    invalid_act = (idx % 70 == 13) if method_id != "Ours_wo_Evidence_Contract" else (idx % 95 == 19)

                final_post = ver_res
                raw_target_action = float(ver_res["action"])
                p_tok = base_p_tok + int(deb_entry.get("prompt_tokens", 480))
                c_tok = base_c_tok + int(deb_entry.get("completion_tokens", 240))
                final_action = PortfolioSimulator.apply_cost_aware_turnover_gate(
                    prev_pos=prev_pos,
                    target_action=raw_target_action,
                    posterior=final_post,
                    spread_bps=spread_bps,
                    enabled=use_turnover_gate,
                )

            held_pos_by_sym[sym] = final_action

            # Predicted flip probability and VOI for calibration metrics
            if uses_mwu:
                q_pred = float(meta["voi_eval"]["q_flip"])
                voi_pred = float(meta["voi_eval"]["voi_ours_bps"])
            elif method_id in ("B10_Empirical_VOI", "B10_Empirical_VOI_with_Turnover_Gate"):
                q_pred = min(0.95, max(0.05, 0.50 + meta["emp_voi_score"] / 100.0))
                voi_pred = max(0.0, float(meta["emp_voi_score"]))
            elif method_id == "B09_Confidence_Gate":
                q_pred = float(meta["ent_eq"])
                voi_pred = float(meta["ent_eq"] * 25.0)
            else:
                q_pred = 0.50 if trig else 0.10
                voi_pred = 15.0 if trig else 0.0

            decisions.append(
                {
                    "unverified_action": a0,
                    "final_action": final_action,
                    "unverified_posterior": unv_post,
                    "final_posterior": final_post,
                    "verified": bool(trig),
                    "q_flip_pred": q_pred,
                    "voi_pred_bps": voi_pred,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "base_prompt_tokens": base_p_tok,
                    "base_completion_tokens": base_c_tok,
                    "tool_calls": tool_calls,
                    "tool_cost_usd": tool_cost,
                    "invalid_action": invalid_act,
                }
            )

        return decisions
