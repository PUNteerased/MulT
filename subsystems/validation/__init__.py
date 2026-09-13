"""Offline pipeline validation: replay, backtest, metrics, calibration."""
from subsystems.validation.metrics import summarize_trades
from subsystems.validation.pipeline_backtest import run_pipeline_backtest

__all__ = ["run_pipeline_backtest", "summarize_trades"]
