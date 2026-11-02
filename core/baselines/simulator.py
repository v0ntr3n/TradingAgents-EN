"""
Unified Portfolio Simulator (`core/baselines/simulator.py`).

Enforces ARIS Guardrail #3 (100% Simulator & Execution Symmetry):
All 12 Baselines + `Ours` execute through `PortfolioSimulator` with:
  - `initial_capital = 100000.0`
  - identical fee/slippage bps (`trading_friction_bps`)
  - identical position cap `w_max = 0.20`
  - identical base target mapping and step accounting
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PortfolioSimulator:
    """
    Symmetric step-by-step portfolio & decision utility simulator shared by all 13 methods.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        w_max: float = 0.20,
        default_friction_bps: Optional[float] = None,
        cost_multiplier: float = 1.0,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.w_max = float(w_max)
        self.default_friction_bps = float(default_friction_bps) if default_friction_bps is not None else None
        self.cost_multiplier = float(cost_multiplier)

    @staticmethod
    def apply_cost_aware_turnover_gate(
        prev_pos: float,
        target_action: float,
        posterior: Dict[str, Any],
        spread_bps: float,
        enabled: bool = True,
    ) -> float:
        """
        Symmetric cost-aware turnover gate:
        Only rebalance from `prev_pos` to `target_action` if expected directional edge
        `|p_opt - p_cau|` exceeds the calibrated friction no-trade band.
        """
        if not enabled:
            return float(target_action)
        delta = abs(float(target_action) - float(prev_pos))
        if delta < 1e-9:
            return float(prev_pos)
        p_opt = float(posterior.get("p_optimistic", 1.0 / 3.0))
        p_cau = float(posterior.get("p_cautious", 1.0 / 3.0))
        band = 0.008 + (float(spread_bps) / 2500.0) * delta
        if abs(p_opt - p_cau) <= band:
            return float(prev_pos)
        return float(target_action)

    def simulate_trajectory(
        self,
        steps: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        model_pricing: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Given a chronological list of causal market `steps` and a 1-to-1 list of method
        `decisions`, execute every decision through identical accounting rules.

        Each `decision` dict contains:
          - `unverified_action`: float in {0.0, 1.0} (a_{i,t}^0 before verification)
          - `final_action`: float in {0.0, 1.0} (a_{i,t}^{final} after verification/gate)
          - `unverified_posterior`: dict
          - `final_posterior`: dict
          - `verified`: bool (G_{i,t} in {0, 1})
          - `q_flip_pred`: float
          - `voi_pred_bps`: float
          - `prompt_tokens`: int
          - `completion_tokens`: int
          - `tool_calls`: int
          - `tool_cost_usd`: float
          - `invalid_action`: bool
        """
        if len(steps) != len(decisions):
            raise ValueError(f"Length mismatch: {len(steps)} steps vs {len(decisions)} decisions")

        pricing = model_pricing or {"input_usd_per_1m": 0.27, "output_usd_per_1m": 1.10}
        in_rate = float(pricing.get("input_usd_per_1m", 0.27))
        out_rate = float(pricing.get("output_usd_per_1m", 1.10))

        prev_pos_by_symbol: Dict[str, float] = {}
        prev_u0_pos_by_symbol: Dict[str, float] = {}
        per_stock_capital = self.initial_capital * self.w_max

        records: List[Dict[str, Any]] = []
        for idx, (step, dec) in enumerate(zip(steps, decisions)):
            sym = str(step.get("symbol", "UNKNOWN"))
            prev_pos = prev_pos_by_symbol.get(sym, 0.0)
            prev_u0_pos = prev_u0_pos_by_symbol.get(sym, 0.0)

            a0 = max(0.0, min(1.0, float(dec.get("unverified_action", 0.0))))
            af = max(0.0, min(1.0, float(dec.get("final_action", a0))))
            verified = bool(dec.get("verified", False))

            spread_bps = (
                self.default_friction_bps
                if self.default_friction_bps is not None
                else float(step.get("spread_bps", 10.0))
            )
            ret_pct = float(step.get("forward_return_pct", 0.0))
            ret_bps = ret_pct * 100.0

            # Token & tool cost in USD and bps of per-stock capital
            p_tok = int(dec.get("prompt_tokens", 0))
            c_tok = int(dec.get("completion_tokens", 0))
            base_p_tok = int(dec.get("base_prompt_tokens", p_tok))
            base_c_tok = int(dec.get("base_completion_tokens", c_tok))

            llm_cost_usd = (
                ((p_tok * in_rate) + (c_tok * out_rate)) / 1_000_000.0
            ) * self.cost_multiplier
            base_llm_cost_usd = (
                ((base_p_tok * in_rate) + (base_c_tok * out_rate)) / 1_000_000.0
            ) * self.cost_multiplier
            verify_llm_cost_usd = max(0.0, llm_cost_usd - base_llm_cost_usd)
            tool_cost_usd = float(dec.get("tool_cost_usd", 0.0)) * self.cost_multiplier if verified else 0.0
            c_verify_bps = ((verify_llm_cost_usd + tool_cost_usd) / max(100.0, per_stock_capital)) * 1e4

            # Decision utility u_{i,t}(a) = a * R_{i, t->t+1}^{bps} - c_{fee+slip}^{bps} * |a - pos_{i,t-1}|
            # Note: Both u(a^{final}) and u(a^0) are evaluated relative to the current held position `prev_pos`
            # at step (i, t) for exact Paired Delta Utility comparison!
            u_a0_bps = a0 * ret_bps - spread_bps * abs(a0 - prev_pos)
            u_af_bps = af * ret_bps - spread_bps * abs(af - prev_pos)
            gross_delta_u_bps = u_af_bps - u_a0_bps
            paired_delta_u_bps = gross_delta_u_bps - (c_verify_bps if verified else 0.0)

            # Update positions for next step of this symbol
            prev_pos_by_symbol[sym] = af
            prev_u0_pos_by_symbol[sym] = a0

            final_post = dec.get("final_posterior") or {}
            p_opt = float(final_post.get("p_optimistic", 1.0 / 3.0))
            p_neu = float(final_post.get("p_neutral", 1.0 / 3.0))
            p_cau = float(final_post.get("p_cautious", 1.0 / 3.0))

            records.append(
                {
                    "date": str(step.get("date", "")),
                    "raw_date": str(step.get("raw_date", step.get("date", ""))),
                    "symbol": sym,
                    "market": str(step.get("market", "US")),
                    "regime": str(step.get("regime", "sideways")),
                    "position": af,
                    "prev_position": prev_pos,
                    "unverified_action": a0,
                    "final_action": af,
                    "did_flip": bool(abs(af - a0) > 1e-6),
                    "verified": verified,
                    "debate_skipped": not verified,
                    "asset_return_pct": ret_pct,
                    "spread_bps": spread_bps,
                    "u_a0_bps": round(u_a0_bps, 4),
                    "u_af_bps": round(u_af_bps, 4),
                    "gross_delta_u_bps": round(gross_delta_u_bps, 4),
                    "c_verify_bps": round(c_verify_bps if verified else 0.0, 4),
                    "paired_delta_u_bps": round(paired_delta_u_bps, 4),
                    "q_flip_pred": float(dec.get("q_flip_pred", 0.0)),
                    "voi_pred_bps": float(dec.get("voi_pred_bps", 0.0)),
                    "realized_pos_gain_bps": round(max(0.0, gross_delta_u_bps), 4),
                    "p_optimistic": p_opt,
                    "p_neutral": p_neu,
                    "p_cautious": p_cau,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "llm_cost_usd": round(llm_cost_usd, 8),
                    "tool_cost_usd": round(tool_cost_usd, 8),
                    "tool_calls": int(dec.get("tool_calls", 1 if verified else 0)),
                    "invalid_action": bool(dec.get("invalid_action", False)),
                    "latency_sec": 0.35 if not verified else 1.45,
                }
            )

        return records
