# Offline Validation

Offline replay of the Deep-Sniper gate pipeline **without MT5 live orders** and without paid APIs.

## Run

```bash
python -m subsystems.validation.run_backtest --symbol EURUSD --months 6
python -m subsystems.validation.run_backtest --symbol ALL --months 3
```

Reports are written to `data/validation_reports/backtest_<SYMBOL>_<timestamp>.json`.

## Data sources (priority)

1. DuckDB `bars_m1` in `data/sniper_warehouse.duckdb`
2. `data/bars_m1.parquet`
3. Deterministic **synthetic** OHLC (demo-only) unless `--no-synthetic`

## What is simulated

- Sweep/wick-style entry heuristic on M1 bars
- `RiskGuard50` with unified money math + optional ATR(k1) SL (from rolling bars)
- Bar-level SL / TP / BE exits (not tick-level trailing)

## Metrics in report

- Win rate, expectancy, profit factor, max drawdown, average SL USD
- Reject counts (risk / spread / other)
- Calibration bins for predicted `win_prob` vs outcomes (heuristic ECE)

## Deferred (see Phase 1 plan)

Chronos coverage, HMM vs NFP, tick trailing fidelity, Triple-Barrier retrain.
