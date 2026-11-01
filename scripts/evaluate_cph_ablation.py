#!/usr/bin/env python3
"""
Entrypoint wrapper for Phase 4 CPH multi-regime ablation benchmark on real cached LLM posteriors.
"""
from scripts.run_cph_ablation_benchmark import (  # noqa: F401
    _compute_dm_pvalue,
    _compute_hac_tstat_and_dm_pvalue,
    _compute_paired_bootstrap_pvalue,
    construct_real_cached_panel,
    generate_multi_regime_market_stream,
    plot_cph_ablation_brier_mae,
    run_ablation,
)

main = run_ablation

if __name__ == "__main__":
    main()
