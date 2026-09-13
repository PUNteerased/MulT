"""CLI: python -m subsystems.validation.run_backtest --symbol EURUSD --months 6"""
from __future__ import annotations

import argparse
import json
import sys

from loguru import logger

from config.settings import TARGET_SYMBOLS, VALIDATION_REPORTS_DIR
from subsystems.validation.pipeline_backtest import run_pipeline_backtest, write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline Deep-Sniper pipeline backtest")
    parser.add_argument("--symbol", default="EURUSD", choices=TARGET_SYMBOLS + ["ALL"])
    parser.add_argument("--months", type=float, default=6.0)
    parser.add_argument("--max-trades", type=int, default=200)
    parser.add_argument("--no-synthetic", action="store_true", help="Fail if no warehouse bars")
    parser.add_argument("--win-prob", type=float, default=0.80)
    args = parser.parse_args(argv)

    symbols = TARGET_SYMBOLS if args.symbol == "ALL" else [args.symbol]
    paths = []
    for sym in symbols:
        try:
            report = run_pipeline_backtest(
                symbol=sym,
                months=args.months,
                allow_synthetic=not args.no_synthetic,
                win_prob=args.win_prob,
                max_trades=args.max_trades,
            )
            path = write_report(report)
            paths.append(str(path))
            m = report["metrics"]
            print(
                f"{sym}: trades={m['n_trades']} win_rate={m['win_rate']:.1%} "
                f"total_pnl=${m['total_pnl']:.2f} expectancy=${m['expectancy']:.3f} "
                f"-> {path}"
            )
        except Exception as e:
            logger.error(f"[Backtest] {sym} failed: {e}")
            print(f"{sym}: ERROR {e}", file=sys.stderr)
            return 1

    summary = {"reports": paths, "dir": str(VALIDATION_REPORTS_DIR)}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
