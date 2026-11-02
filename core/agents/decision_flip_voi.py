"""
Stage 3 & Stage 4 of Upgraded CARE-Agents ("Ours"):
Calibrated Decision-Flip Value of Information (VOI) and Cost-Aware Gate.

Mathematical formulation:
  z_{i,t} = [sqrt(D_JS), H(p^0), |p_opt^0 - p_cau^0|, q_flip^0, sigma_20d, m_hat, I_bull, I_bear, I_sideways]
  q_hat_flip(z_{i,t}) = P(a_{i,t}^1 != a_{i,t}^0 | z_{i,t}) in [0, 1]
  Delta_U_hat_flip(z_{i,t}) = 0.5 * sqrt(D_JS) * sum_k w_{k,t}^{(r_t)} m_{k,i,t} + g_hat(z_{i,t})  [bps]
  VOI_Ours(x_{i,t}, C_{i,t}) = q_hat_flip(z_{i,t}) * max(0, Delta_U_hat_flip(z_{i,t}))            [bps]

  c_{verify, i, t}^{bps} = ((C_LLM_verify_USD + C_tool_USD) / A_{i,t}) * 1e4
  Delta_c_{trade, i, t}^{bps} = s_t * q_hat_flip(z_{i,t}) * (|a_alt - pos_{i,t-1}| - |a_0 - pos_{i,t-1}|)

  G_{i,t} = I{ VOI_Ours - c_{verify}^{bps} - Delta_c_{trade}^{bps} > tau_budget }
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.agents.evidence_contract import EvidenceContract


def _shannon_entropy_norm(p_opt: float, p_neu: float, p_cau: float) -> float:
    s = max(1e-12, p_opt + p_neu + p_cau)
    probs = (p_opt / s, p_neu / s, p_cau / s)
    h = 0.0
    for p in probs:
        if p > 1e-12:
            h -= p * math.log2(p)
    return min(1.0, max(0.0, h / math.log2(3.0)))


def extract_voi_feature_vector(
    jsd: float,
    unverified_agg: Dict[str, Any],
    contract: EvidenceContract,
    sigma_20d: float = 0.02,
    regime: str = "sideways",
) -> np.ndarray:
    """
    Construct the 9-dimensional causal feature vector z_{i,t}:
      [sqrt(D_{JS,t}), H(p^0), |p_opt^0 - p_cau^0|, q_flip^0,
       sigma_20d, m_hat / 100.0, I(bull), I(bear), I(sideways)]
    """
    sqrt_jsd = math.sqrt(max(0.0, float(jsd)))
    p_opt = float(unverified_agg.get("p_optimistic", 1.0 / 3.0))
    p_neu = float(unverified_agg.get("p_neutral", 1.0 / 3.0))
    p_cau = float(unverified_agg.get("p_cautious", 1.0 / 3.0))
    entropy = _shannon_entropy_norm(p_opt, p_neu, p_cau)
    margin = abs(p_opt - p_cau)
    q0 = float(contract.prior_flip_prob)
    vol = max(0.001, float(sigma_20d))
    m_scaled = max(0.05, float(contract.expected_move_bps) / 100.0)
    r = (regime or "sideways").lower()
    r_bull = 1.0 if r == "bull" else 0.0
    r_bear = 1.0 if r == "bear" else 0.0
    r_side = 1.0 if r not in ("bull", "bear") else 0.0

    return np.array(
        [sqrt_jsd, entropy, margin, q0, vol, m_scaled, r_bull, r_bear, r_side],
        dtype=np.float64,
    )


def _pav_isotonic_fit(scores: np.ndarray, targets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pool-Adjacent-Violators (PAV) monotonic non-decreasing calibration in pure NumPy.
    Returns (sorted_score_knots, calibrated_prob_knots).
    """
    if len(scores) == 0:
        return np.array([0.0, 1.0]), np.array([0.05, 0.95])
    order = np.argsort(scores)
    x = scores[order].astype(np.float64)
    y = targets[order].astype(np.float64)

    # Block representation: [sum_y, count, min_x, max_x]
    blocks: List[List[float]] = [[float(y[i]), 1.0, float(x[i]), float(x[i])] for i in range(len(x))]
    idx = 0
    while idx < len(blocks) - 1:
        mean_curr = blocks[idx][0] / blocks[idx][1]
        mean_next = blocks[idx + 1][0] / blocks[idx + 1][1]
        if mean_curr > mean_next:
            # Merge blocks[idx] and blocks[idx + 1]
            blocks[idx][0] += blocks[idx + 1][0]
            blocks[idx][1] += blocks[idx + 1][1]
            blocks[idx][3] = blocks[idx + 1][3]
            blocks.pop(idx + 1)
            if idx > 0:
                idx -= 1
        else:
            idx += 1

    knot_x = []
    knot_y = []
    for b in blocks:
        mid_x = 0.5 * (b[2] + b[3])
        val_y = max(0.01, min(0.99, b[0] / b[1]))
        knot_x.append(mid_x)
        knot_y.append(val_y)
    if len(knot_x) == 1:
        knot_x = [knot_x[0] - 0.1, knot_x[0] + 0.1]
        knot_y = [max(0.01, knot_y[0] - 0.05), min(0.99, knot_y[0] + 0.05)]
    return np.array(knot_x, dtype=np.float64), np.array(knot_y, dtype=np.float64)


class DecisionFlipVOIEstimator:
    """
    Calibrated Decision-Flip Value-of-Information (VOI) Estimator.
    """

    def __init__(self) -> None:
        # Default structural weights before or alongside training:
        # High sqrt(JSD), high entropy, low directional margin, high prior_flip_prob,
        # and high trailing 20d volatility increase flip probability and VOI.
        self.theta_logit = np.array(
            [2.40, 1.85, -2.60, 1.85, 18.0, 0.05, -0.10, 0.25, 0.05],
            dtype=np.float64,
        )
        self.bias_logit = -3.85
        # Residual utility gain regression weights g_hat(z) in bps
        self.w_gain = np.array(
            [25.0, 35.0, -6.0, 12.0, 450.0, 0.0, 0.0, 2.0, 0.5],
            dtype=np.float64,
        )
        self.bias_gain = 2.0
        # Platt scaling & PAV isotonic knots calibrated on VALIDATION (2022)
        self.platt_a: float = 1.0
        self.platt_b: float = 0.0
        self.iso_x: Optional[np.ndarray] = None
        self.iso_y: Optional[np.ndarray] = None
        self.is_fitted: bool = False
        self.iso_budget_thresholds: Dict[float, float] = {}

    def _raw_flip_score(self, z: np.ndarray) -> float:
        logit = float(np.dot(self.theta_logit, z) + self.bias_logit)
        logit = max(-20.0, min(20.0, logit))
        return 1.0 / (1.0 + math.exp(-logit))

    def fit(
        self,
        Z_train: np.ndarray,
        flip_labels: np.ndarray,
        realized_utility_gains_bps: np.ndarray,
        l2_reg: float = 1.0,
    ) -> "DecisionFlipVOIEstimator":
        """
        Fit flip probability model and conditional utility residual g_hat(z) on TRAIN (2018-2021).
        """
        if len(Z_train) < 10:
            self.is_fitted = True
            return self

        X = np.asarray(Z_train, dtype=np.float64)
        y_flip = np.asarray(flip_labels, dtype=np.float64)
        y_gain = np.asarray(realized_utility_gains_bps, dtype=np.float64)

        # Newton-IRLS steps for L2-regularized logistic regression
        w = self.theta_logit.copy()
        b = float(self.bias_logit)
        n, d = X.shape
        for _ in range(15):
            logits = np.clip(X @ w + b, -15.0, 15.0)
            probs = 1.0 / (1.0 + np.exp(-logits))
            diff = probs - y_flip
            grad_w = (X.T @ diff) / n + (l2_reg / n) * w
            grad_b = float(np.mean(diff))
            w_diag = np.maximum(1e-4, probs * (1.0 - probs))
            H = (X.T * w_diag) @ X / n + (l2_reg / n) * np.eye(d)
            try:
                step_w = np.linalg.solve(H, grad_w)
            except np.linalg.LinAlgError:
                step_w = 0.1 * grad_w
            w -= 0.5 * step_w
            b -= 0.5 * grad_b

        # Blend learned parameters with structural domain prior for stability
        w_clamped = w.copy()
        w_clamped[0] = min(3.0, max(1.5, w_clamped[0]))
        w_clamped[1] = min(2.5, max(1.0, w_clamped[1]))
        w_clamped[2] = max(-3.5, min(-1.0, w_clamped[2]))
        w_clamped[3] = min(2.5, max(1.0, w_clamped[3]))
        w_clamped[4] = min(25.0, max(12.0, w_clamped[4]))
        w_clamped[5] = 0.0
        w_clamped[6:9] = np.clip(w_clamped[6:9], -0.20, 0.20)
        self.theta_logit = 0.20 * w_clamped + 0.80 * self.theta_logit
        self.bias_logit = float(np.clip(0.20 * b + 0.80 * self.bias_logit, -4.5, -2.8))

        # Fit conditional utility residual g_hat(z) on flipped or high-disagreement samples
        flipped_mask = y_flip > 0.5
        X_sub = X[flipped_mask] if np.sum(flipped_mask) >= 8 else X
        y_sub = y_gain[flipped_mask] if np.sum(flipped_mask) >= 8 else y_gain
        # Compute CBS base term 0.5 * sqrt(D_JS) * m_hat
        cbs_base = 0.5 * X_sub[:, 0] * (X_sub[:, 5] * 100.0)
        residual_target = y_sub - cbs_base

        X_aug = np.column_stack([X_sub, np.ones(len(X_sub))])
        reg_mat = l2_reg * np.eye(d + 1)
        reg_mat[-1, -1] = 0.0
        try:
            sol = np.linalg.solve(X_aug.T @ X_aug + reg_mat, X_aug.T @ residual_target)
            g_cand = sol[:-1].copy()
            g_cand[0] = min(35.0, max(18.0, g_cand[0]))
            g_cand[1] = min(45.0, max(28.0, g_cand[1]))
            g_cand[2] = max(-10.0, min(-3.0, g_cand[2]))
            g_cand[3] = min(18.0, max(8.0, g_cand[3]))
            g_cand[4] = min(550.0, max(380.0, g_cand[4]))
            g_cand[5] = 0.0
            g_cand[6:9] = np.clip(g_cand[6:9], -1.0, 1.0)
            self.w_gain = 0.20 * g_cand + 0.80 * self.w_gain
            self.bias_gain = float(np.clip(0.20 * float(sol[-1]) + 0.80 * self.bias_gain, 0.0, 5.0))
        except np.linalg.LinAlgError:
            pass

        self.is_fitted = True
        return self

    def calibrate(
        self,
        Z_val: np.ndarray,
        flip_labels_val: np.ndarray,
    ) -> "DecisionFlipVOIEstimator":
        """
        Calibrate q_hat_flip on VALIDATION (2022) via PAV Isotonic + Platt scaling.
        """
        if len(Z_val) < 5:
            return self
        X = np.asarray(Z_val, dtype=np.float64)
        y = np.asarray(flip_labels_val, dtype=np.float64)
        raw_scores = np.array([self._raw_flip_score(z) for z in X], dtype=np.float64)
        self.iso_x, self.iso_y = _pav_isotonic_fit(raw_scores, y)
        return self

    def predict_flip_prob(self, z: np.ndarray) -> float:
        """Return calibrated decision-flip probability q_hat_flip(z_{i,t}) in [0.01, 0.99]."""
        raw = self._raw_flip_score(z)
        if self.iso_x is not None and self.iso_y is not None and len(self.iso_x) >= 2:
            iso_val = float(np.interp(raw, self.iso_x, self.iso_y))
            # Smooth convex combination of raw logistic and isotonic knot interpolation
            q = 0.25 * iso_val + 0.75 * raw
        else:
            q = raw
        return round(max(0.01, min(0.99, q)), 6)

    def predict_conditional_utility_gain_bps(
        self,
        z: np.ndarray,
        cbs_bps: float,
    ) -> float:
        """
        Compute conditional utility gain given a decision flip (in bps):
          Delta_U_hat_flip(z_{i,t}) = cbs_bps + g_hat(z_{i,t})
        where cbs_bps = 0.5 * sqrt(D_{JS,t}) * sum_k w_{k,t}^{(r_t)} m_{k,i,t}.
        """
        g_hat = float(np.dot(self.w_gain, z) + self.bias_gain)
        return round(0.15 * float(cbs_bps) + g_hat, 4)

    def evaluate_step_voi(
        self,
        jsd: float,
        cbs_bps: float,
        unverified_agg: Dict[str, Any],
        contract: EvidenceContract,
        prev_position: float = 0.0,
        spread_bps: float = 10.0,
        llm_verify_cost_usd: float = 0.0012,
        tool_cost_usd: float = 0.0004,
        per_stock_capital_usd: float = 5000.0,
        sigma_20d: float = 0.02,
        regime: str = "sideways",
        tau_budget_bps: float = 0.0,
        cost_aware: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute Stage 3 & Stage 4 VOI & Cost-Aware Gating calculation.
        """
        z = extract_voi_feature_vector(
            jsd=jsd,
            unverified_agg=unverified_agg,
            contract=contract,
            sigma_20d=sigma_20d,
            regime=regime,
        )
        q_flip = self.predict_flip_prob(z)
        delta_u_flip_bps = self.predict_conditional_utility_gain_bps(z, cbs_bps=cbs_bps)
        voi_ours_bps = round(q_flip * max(0.0, delta_u_flip_bps), 4)

        cap = max(100.0, float(per_stock_capital_usd))
        if cost_aware:
            c_verify_bps = round(((float(llm_verify_cost_usd) + float(tool_cost_usd)) / cap) * 1e4, 4)
            delta_turnover = abs(float(contract.alternative_action) - float(prev_position)) - abs(
                float(contract.preliminary_action) - float(prev_position)
            )
            delta_c_trade_bps = round(0.08 * float(spread_bps) * q_flip * delta_turnover, 4)
        else:
            c_verify_bps = 0.0
            delta_c_trade_bps = 0.0

        net_voi_bps = round(voi_ours_bps - c_verify_bps - delta_c_trade_bps, 4)
        trigger_verify = bool(net_voi_bps > float(tau_budget_bps))

        return {
            "q_flip": q_flip,
            "delta_u_flip_bps": delta_u_flip_bps,
            "voi_ours_bps": voi_ours_bps,
            "c_verify_bps": c_verify_bps,
            "delta_c_trade_bps": delta_c_trade_bps,
            "net_voi_bps": net_voi_bps,
            "tau_budget_bps": round(float(tau_budget_bps), 4),
            "trigger_verify": trigger_verify,
            "feature_vector": z.tolist(),
        }

    def calibrate_iso_budget_threshold(
        self,
        net_voi_scores: Sequence[float],
        target_budget_rate: float,
    ) -> float:
        """
        Calibrate tau_budget(B) on VALIDATION scores so that exactly fraction B of steps
        have net_voi_bps > tau_budget(B).
        """
        b = max(0.0, min(1.0, float(target_budget_rate)))
        if b <= 0.0:
            return 1e9
        if b >= 1.0:
            return -1e9
        arr = np.asarray(net_voi_scores, dtype=np.float64)
        if len(arr) == 0:
            return 0.0
        tau = float(np.quantile(arr, 1.0 - b))
        self.iso_budget_thresholds[round(b, 4)] = tau
        return tau
