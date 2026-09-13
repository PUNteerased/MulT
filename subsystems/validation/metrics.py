"""Trade / backtest summary metrics."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence


def summarize_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "expectancy": 0.0,
            "avg_risk_usd": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
        }

    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    n = len(pnls)
    win_rate = len(wins) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    expectancy = win_rate * avg_win - (1.0 - win_rate) * avg_loss
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 1e-9 else (999.0 if gross_win > 0 else 0.0)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    risks = [float(t.get("sl_usd", t.get("risk_dollars", 0.0))) for t in trades]
    return {
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "avg_pnl": round(total / n, 4),
        "total_pnl": round(total, 4),
        "expectancy": round(expectancy, 4),
        "avg_risk_usd": round(sum(risks) / n if risks else 0.0, 4),
        "max_drawdown": round(max_dd, 4),
        "profit_factor": round(pf, 4),
    }
