#!/usr/bin/env python3
"""
Entrypoint wrapper for Phase 5 real-market cached LLM posterior evaluation.
"""
from scripts.run_phase5_real_market_benchmark import (  # noqa: F401
    LiveDeepSeekBenchmarkClient,
    ThreadSafeLLMCache,
    detect_causal_regime,
    diebold_mariano_pvalue,
    evaluate_cohort_and_collect_rows,
    evaluate_portfolio_records,
    generate_agent_signals,
    load_real_2025_2026_dataset,
    main,
    newey_west_hac_tstat,
    paired_block_bootstrap_sharpe_test,
    paired_brier_z_pvalue,
    query_specialist_posteriors,
    run_market_universe_chronologically,
)

if __name__ == "__main__":
    main()
