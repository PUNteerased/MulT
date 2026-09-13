"""
Account Performance Audit and Metrics Calculator.
Analyzes DuckDB trade logs to ensure the $50 account stays strictly within survival metrics.
"""
from typing import Dict, Any
import numpy as np
import pandas as pd
from loguru import logger
from core.memory.duckdb_manager import DuckDBManager

class PerformanceAuditor:
    """Computes critical financial metrics for the $50 trading account."""
    def __init__(self, duckdb: DuckDBManager = None):
        self.duckdb = duckdb or DuckDBManager()

    def generate_report(self) -> Dict[str, Any]:
        """Calculate complete statistics."""
        df = self.duckdb.get_trade_logs()
        if df.empty:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "net_pnl": 0.0,
                "max_drawdown_usd": 0.0,
                "expectancy_usd": 0.0
            }

        pnls = df["pnl"].values
        total_trades = len(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0

        gross_profit = float(np.sum(wins)) if win_count > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if loss_count > 0 else 0.0

        profit_factor = round(gross_profit / (gross_loss + 1e-9), 2)
        net_pnl = round(float(np.sum(pnls)), 2)

        # Max Drawdown calculation
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Expectancy
        avg_win = float(np.mean(wins)) if win_count > 0 else 0.0
        avg_loss = float(abs(np.mean(losses))) if loss_count > 0 else 0.0
        expectancy = ((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss)

        report = {
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": profit_factor,
            "net_pnl": net_pnl,
            "max_drawdown_usd": round(max_drawdown, 2),
            "expectancy_usd": round(expectancy, 2)
        }

        logger.info(
            f"[PerformanceAuditor] Report: Trades={total_trades} | WinRate={win_rate:.1f}% | "
            f"PF={profit_factor} | NetPnL=${net_pnl:.2f} | MaxDD=${max_drawdown:.2f}"
        )
        return report
