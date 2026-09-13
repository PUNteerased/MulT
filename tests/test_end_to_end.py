"""
End-to-End Pipeline Integration Test.
Simulates the entire Deep-Sniper AI lifecycle from tick to trade execution,
trailing stop ratcheting, DuckDB logging, and weekend evolutionary retraining.
"""
import pytest
import asyncio
import time
import numpy as np
import pandas as pd

from core.bus.events import KillZoneEvent, OrderDirection, TickEvent, BarEvent
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager
from subsystems.m1_sniper.sniper_worker import M1SniperWorker
from subsystems.meta_labeling.lgbm_filter import LightGBMMetaFilter
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.execution.mt5_router import MT5OrderRouter
from subsystems.evolution.weekend_learner import WeekendSelfEvolutionWorker
from subsystems.evolution.performance_audit import PerformanceAuditor

@pytest.mark.asyncio
async def test_full_sniper_e2e_pipeline():
    # 1. Initialize isolated memory and in-memory DuckDB
    DuckDBManager.reset_instance()
    db = DuckDBManager(":memory:")
    cache = MarketMemoryCache()

    # 2. Setup active Kill Zone (EURUSD Buy Zone 1.08450 - 1.08550)
    kz = KillZoneEvent(
        zone_id="KZ_E2E_BUY", symbol="EURUSD", timeframe="M15",
        direction=OrderDirection.BUY, lower_bound=1.08450, upper_bound=1.08550,
        mid_price=1.08500, confidence=0.88, expires_at=time.time() + 3600
    )
    cache.update_kill_zone(kz)

    # 3. Seed historical M1 bars
    for i in range(50):
        b = BarEvent(
            symbol="EURUSD", timeframe="M1", time=1000 + i * 60,
            open=1.0860, high=1.0865, low=1.0855, close=1.0858,
            tick_volume=120, spread=10
        )
        cache.add_bar(b)

    # Trigger bar: Liquidity sweep below zone with huge hammer wick
    sweep_bar = BarEvent(
        symbol="EURUSD", timeframe="M1", time=1000 + 51 * 60,
        open=1.0850, high=1.0854, low=1.0844, close=1.0853,
        tick_volume=350, spread=10
    )
    cache.add_bar(sweep_bar)

    # 4. Trigger Sniper via Live Tick inside Kill Zone
    sniper = M1SniperWorker()
    live_tick = TickEvent(symbol="EURUSD", time_msc=1720000000000, bid=1.08490, ask=1.08500, spread=10)
    alert = await sniper.on_tick(live_tick)
    assert alert is not None
    assert alert.direction == OrderDirection.BUY
    assert alert.wick_sl_price < alert.entry_price

    # 5. Meta-Labeling Filter (LightGBM)
    meta = LightGBMMetaFilter(min_win_prob=0.70)
    feats = alert.features
    is_approved, win_prob = meta.evaluate_features(feats)
    # Ensure gate evaluates
    assert 0.0 <= win_prob <= 1.0

    # 6. $50 Risk Guard ($2.50 hard cap check)
    guard = RiskGuard50()
    ok, reason, ticket = guard.evaluate_trigger(
        alert=alert, current_spread_points=10, active_positions_count=0,
        account_equity=50.0, win_prob=win_prob
    )
    assert ok is True
    assert ticket is not None
    assert ticket.risk_dollars <= 2.50
    assert ticket.lot == 0.01

    # 7. MT5 Order Router Execution (Dry Run)
    router = MT5OrderRouter(dry_run=True)
    order_id = await router.send_order(ticket)
    assert order_id is not None
    assert router.active_position is not None

    # 8. Simulate Price Rally to TP1 (Trigger Break-Even + 2 pips)
    await router.update_active_position_trailing(
        current_bid=ticket.be_trigger_price + 0.00010,
        current_ask=ticket.be_trigger_price + 0.00020
    )
    assert router.active_position["be_applied"] is True
    assert router.active_position["current_sl"] == ticket.be_lock_price

    # 9. Simulate Trade Close
    await router._handle_position_closed(exit_price=ticket.tp_target_price)
    assert router.active_position is None

    # 10. Audit DuckDB Trade Logs
    trades = db.get_trade_logs()
    assert len(trades) == 1
    assert trades.iloc[0]["ticket_id"] == ticket.ticket_id
    assert trades.iloc[0]["pnl"] > 0

    # 11. Run Weekend Evolutionary Retraining
    evolution = WeekendSelfEvolutionWorker(duckdb=db)
    evo_result = evolution.run_evolution_cycle()
    assert evo_result["status"] == "COMPLETED"
    assert evo_result["trades_processed"] == 1

    # 12. Run Performance Auditor
    auditor = PerformanceAuditor(duckdb=db)
    report = auditor.generate_report()
    assert report["total_trades"] == 1
    assert report["win_rate_pct"] == 100.0
    assert report["net_pnl"] > 0

    DuckDBManager.reset_instance()
