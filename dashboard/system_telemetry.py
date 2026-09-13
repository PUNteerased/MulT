"""
System Hardware & MT5 Account Telemetry Collector.
Captures real-time metrics for RTX 4050 Laptop GPU (VRAM), Ryzen 7 8845HS CPU,
32GB DDR5 RAM, NVMe SSD storage, and MetaTrader 5 account status.
"""
import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
import psutil
from loguru import logger

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

BANGKOK = ZoneInfo("Asia/Bangkok")
TZ_NAME = "Asia/Bangkok"

class SystemTelemetryCollector:
    """Collects system resource utilization and MT5 account health."""

    VRAM_WARNING_THRESHOLD_MB = 2500.0  # Safe ceiling on RTX 4050 6GB

    @classmethod
    def get_hardware_telemetry(cls) -> Dict[str, Any]:
        """Collect GPU, CPU, RAM, and Disk metrics."""
        # 1. GPU VRAM Telemetry
        vram_total_mb = 6144.0  # RTX 4050 6GB nominal
        vram_used_mb = 0.0
        vram_free_mb = 6144.0
        gpu_name = "NVIDIA GeForce RTX 4050 Laptop GPU"
        is_gpu_available = False

        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info()
                vram_total_mb = round(total_bytes / (1024 * 1024), 1)
                vram_free_mb = round(free_bytes / (1024 * 1024), 1)
                vram_used_mb = round((total_bytes - free_bytes) / (1024 * 1024), 1)
                gpu_name = torch.cuda.get_device_name(0)
                is_gpu_available = True
            except Exception as e:
                logger.debug(f"[Telemetry] GPU query warning: {e}")

        vram_usage_percent = round((vram_used_mb / (vram_total_mb + 1e-9)) * 100.0, 1)
        vram_warning = vram_used_mb >= cls.VRAM_WARNING_THRESHOLD_MB

        # 2. CPU & Host RAM
        cpu_percent = psutil.cpu_percent(interval=None)
        cpu_count = psutil.cpu_count(logical=True)
        ram = psutil.virtual_memory()
        ram_total_gb = round(ram.total / (1024 ** 3), 1)
        ram_used_gb = round(ram.used / (1024 ** 3), 1)
        ram_percent = ram.percent

        # 3. NVMe Disk Storage
        try:
            cwd_drive = os.path.splitdrive(os.getcwd())[0] or "C:"
            disk = psutil.disk_usage(cwd_drive)
            disk_free_gb = round(disk.free / (1024 ** 3), 1)
            disk_total_gb = round(disk.total / (1024 ** 3), 1)
            disk_percent = disk.percent
        except Exception:
            disk_free_gb = 0.0
            disk_total_gb = 0.0
            disk_percent = 0.0

        telemetry_dict = {
            "vram_used_mb": vram_used_mb,
            "vram_total_mb": vram_total_mb,
            "vram_free_mb": vram_free_mb,
            "vram_percent": vram_usage_percent,
            "vram_warning": vram_warning,
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "disk_free_gb": disk_free_gb,
            "gpu": {
                "name": gpu_name,
                "available": is_gpu_available,
                "vram_used_mb": vram_used_mb,
                "vram_free_mb": vram_free_mb,
                "vram_total_mb": vram_total_mb,
                "vram_percent": vram_usage_percent,
                "vram_warning": vram_warning,
                "threshold_mb": cls.VRAM_WARNING_THRESHOLD_MB,
            },
            "cpu": {
                "percent": cpu_percent,
                "logical_cores": cpu_count,
                "model": "AMD Ryzen 7 8845HS with Radeon 780M Graphics",
            },
            "ram": {
                "used_gb": ram_used_gb,
                "total_gb": ram_total_gb,
                "percent": ram_percent,
            },
            "disk": {
                "free_gb": disk_free_gb,
                "total_gb": disk_total_gb,
                "percent": disk_percent,
            },
            "timestamp": time.time(),
        }
        return telemetry_dict

    @classmethod
    def get_mt5_telemetry(cls) -> Dict[str, Any]:
        """Fetch MT5 live terminal and account statistics."""
        if not MT5_AVAILABLE:
            return {"connected": False, "reason": "MT5 module unavailable"}

        try:
            term = mt5.terminal_info()
            if not term or not term.connected:
                # Attempt init if not initialized
                mt5.initialize()
                term = mt5.terminal_info()

            if not term:
                return {
                    "connected": False,
                    "trade_allowed": False,
                    "account": None,
                    "open_positions": [],
                }

            acc = mt5.account_info()
            positions = mt5.positions_get() or []

            pos_list = []
            for p in positions:
                pos_list.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": round(p.profit, 2),
                    "magic": p.magic,
                    "comment": p.comment,
                })

            acc_dict = None
            if acc:
                acc_dict = {
                    "login": acc.login,
                    "server": acc.server,
                    "currency": acc.currency,
                    "balance": round(acc.balance, 2),
                    "equity": round(acc.equity, 2),
                    "profit": round(acc.profit, 2),
                    "margin": round(acc.margin, 2),
                    "margin_free": round(acc.margin_free, 2),
                    "margin_level": round(acc.margin_level, 2) if acc.margin > 0 else 0.0,
                    "leverage": acc.leverage,
                }

            return {
                "connected": bool(term.connected),
                "trade_allowed": bool(term.trade_allowed),
                "ping_ms": round(term.ping_last / 1000.0, 1) if hasattr(term, "ping_last") else 0.0,
                "account": acc_dict,
                "open_positions_count": len(pos_list),
                "open_positions": pos_list,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.debug(f"[Telemetry] MT5 query error: {e}")
            return {
                "connected": False,
                "error": str(e),
                "open_positions": [],
            }

    @classmethod
    async def get_full_snapshot_async(cls) -> Dict[str, Any]:
        """Asynchronously gather hardware and MT5 telemetry without blocking."""
        hw = await asyncio.to_thread(cls.get_hardware_telemetry)
        mt5_stats = await asyncio.to_thread(cls.get_mt5_telemetry)
        raw_acc = mt5_stats.get("account") or {}
        
        account_summary = {
            "balance": raw_acc.get("balance", 50.0),
            "equity": raw_acc.get("equity", 50.0),
            "margin_free": raw_acc.get("margin_free", 50.0),
            "floating_pnl": raw_acc.get("profit", 0.0),
            "currency": raw_acc.get("currency", "USD"),
            "login": raw_acc.get("login", 0),
            "server": raw_acc.get("server", ""),
            "connected": mt5_stats.get("connected", False),
            "active_positions": mt5_stats.get("open_positions", []),
            "active_positions_count": mt5_stats.get("open_positions_count", 0),
        }
        return {
            "hardware": hw,
            "mt5": mt5_stats,
            "account": account_summary,
            "timestamp": time.time(),
        }

def get_system_telemetry() -> Dict[str, Any]:
    """Helper function returning unified hardware and MT5 telemetry dictionary."""
    hw = SystemTelemetryCollector.get_hardware_telemetry()
    mt5_stats = SystemTelemetryCollector.get_mt5_telemetry()
    raw_acc = mt5_stats.get("account") or {}

    account_summary = {
        "balance": raw_acc.get("balance", 50.0),
        "equity": raw_acc.get("equity", 50.0),
        "margin_free": raw_acc.get("margin_free", 50.0),
        "floating_pnl": raw_acc.get("profit", 0.0),
        "currency": raw_acc.get("currency", "USD"),
        "login": raw_acc.get("login", 0),
        "server": raw_acc.get("server", ""),
        "connected": mt5_stats.get("connected", False),
        "active_positions": mt5_stats.get("open_positions", []),
        "active_positions_count": mt5_stats.get("open_positions_count", 0),
    }

    result = dict(hw)
    result["account"] = account_summary
    result["mt5"] = mt5_stats
    return result


# --- Portfolio history (MT5 deals → initial balance, curve, analytics) ---


def _to_ict_str(epoch_sec: float) -> str:
    """Format unix epoch as Thailand local time string."""
    try:
        dt = datetime.fromtimestamp(float(epoch_sec), tz=timezone.utc).astimezone(BANGKOK)
        return dt.strftime("%Y-%m-%d %H:%M:%S ICT")
    except Exception:
        return "—"


def _analytics_from_pnls(pnls: list) -> Dict[str, Any]:
    if not pnls:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "net_pnl": 0.0,
            "max_drawdown_usd": 0.0,
        }
    total = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / total) * 100.0
    gross_profit = float(sum(wins)) if wins else 0.0
    gross_loss = float(abs(sum(losses))) if losses else 0.0
    profit_factor = round(gross_profit / (gross_loss + 1e-9), 2)
    net_pnl = round(float(sum(pnls)), 2)
    cumulative = []
    run = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        run += p
        cumulative.append(run)
        peak = max(peak, run)
        max_dd = max(max_dd, peak - run)
    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": profit_factor,
        "total_trades": total,
        "net_pnl": net_pnl,
        "max_drawdown_usd": round(max_dd, 2),
    }


def get_mt5_portfolio_history(days: int = 180) -> Dict[str, Any]:
    """
    Reconstruct portfolio history from MT5 deals.
    Returns initial_balance, equity_curve, closed_trades, analytics (ICT timestamps).
    Each closed trade is tagged source='ai' | 'legacy' via magic / comment.
    """
    from config.settings import ACCOUNT_INITIAL_BALANCE, MT5_MAGIC_NUMBER

    empty = {
        "initial_balance": float(ACCOUNT_INITIAL_BALANCE),
        "current_balance": float(ACCOUNT_INITIAL_BALANCE),
        "current_equity": float(ACCOUNT_INITIAL_BALANCE),
        "net_pnl": 0.0,
        "net_pnl_pct": 0.0,
        "timezone": TZ_NAME,
        "equity_curve": [float(ACCOUNT_INITIAL_BALANCE), float(ACCOUNT_INITIAL_BALANCE)],
        "closed_trades": [],
        "analytics": _analytics_from_pnls([]),
        "source": "fallback",
        "trade_counts": {"all": 0, "ai": 0, "legacy": 0},
    }

    if not MT5_AVAILABLE:
        return empty

    try:
        term = mt5.terminal_info()
        if not term or not term.connected:
            mt5.initialize()
            term = mt5.terminal_info()
        if not term:
            return empty

        acc = mt5.account_info()
        current_balance = float(acc.balance) if acc else float(ACCOUNT_INITIAL_BALANCE)
        current_equity = float(acc.equity) if acc else current_balance

        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=max(1, int(days)))
        deals = mt5.history_deals_get(from_dt, to_dt)
        if deals is None:
            deals = []
        deals = list(deals)

        # --- Initial balance from DEAL_TYPE_BALANCE deposits ---
        DEAL_BALANCE = getattr(mt5, "DEAL_TYPE_BALANCE", 2)
        DEAL_BUY = getattr(mt5, "DEAL_TYPE_BUY", 0)
        DEAL_SELL = getattr(mt5, "DEAL_TYPE_SELL", 1)

        sorted_deals = sorted(deals, key=lambda d: d.time)
        balance_deals = [d for d in sorted_deals if int(d.type) == DEAL_BALANCE]
        trading_started = False
        deposit_sum = 0.0
        for d in sorted_deals:
            if int(d.type) in (DEAL_BUY, DEAL_SELL) and getattr(d, "position_id", 0):
                trading_started = True
            if int(d.type) == DEAL_BALANCE and float(d.profit) > 0 and not trading_started:
                deposit_sum += float(d.profit)

        if deposit_sum > 0:
            initial_balance = round(deposit_sum, 2)
        elif balance_deals:
            first = min(balance_deals, key=lambda d: d.time)
            initial_balance = round(abs(float(first.profit)), 2) if first.profit else float(ACCOUNT_INITIAL_BALANCE)
        else:
            net_all = sum(float(d.profit) + float(getattr(d, "swap", 0) or 0) + float(getattr(d, "commission", 0) or 0) for d in deals)
            initial_balance = round(current_balance - net_all, 2)
            if initial_balance <= 0:
                initial_balance = float(ACCOUNT_INITIAL_BALANCE)

        # --- Group closed positions by position_id ---
        by_pos: Dict[int, list] = defaultdict(list)
        for d in sorted_deals:
            pid = int(getattr(d, "position_id", 0) or 0)
            if pid <= 0:
                continue
            if int(d.type) not in (DEAL_BUY, DEAL_SELL):
                continue
            by_pos[pid].append(d)

        closed_trades = []
        for pid, group in by_pos.items():
            group = sorted(group, key=lambda x: x.time)
            if len(group) < 1:
                continue
            entry = group[0]
            exit_d = group[-1]
            # Need both in and out (entry deal usually has entry=0/1, exit has profit)
            total_pnl = sum(
                float(d.profit) + float(getattr(d, "swap", 0) or 0) + float(getattr(d, "commission", 0) or 0)
                for d in group
            )
            # Only treat as closed if last deal realizes PnL or volume closed (entry != exit time with multiple deals)
            if len(group) == 1 and abs(total_pnl) < 1e-9 and float(getattr(entry, "volume", 0) or 0) > 0:
                # Likely still open / entry-only
                continue
            if len(group) == 1:
                continue

            direction = "BUY" if int(entry.type) == DEAL_BUY else "SELL"
            # If first deal is closing opposite, flip
            entry_price = float(entry.price)
            exit_price = float(exit_d.price)
            volume = float(getattr(entry, "volume", 0) or 0)
            magic = int(getattr(exit_d, "magic", 0) or getattr(entry, "magic", 0) or 0)
            comment = str(getattr(exit_d, "comment", "") or getattr(entry, "comment", "") or "")
            is_ai = magic == int(MT5_MAGIC_NUMBER) or comment.startswith("DS_")
            closed_trades.append({
                "ticket": int(exit_d.ticket),
                "position_id": pid,
                "symbol": str(entry.symbol),
                "direction": direction,
                "lot": round(volume, 4),
                "fill_price": entry_price,
                "exit_price": exit_price,
                "pnl": round(total_pnl, 2),
                "entry_time": _to_ict_str(entry.time),
                "exit_time": _to_ict_str(exit_d.time),
                "entry_timestamp": float(entry.time),
                "exit_timestamp": float(exit_d.time),
                "comment": comment,
                "magic": magic,
                "source": "ai" if is_ai else "legacy",
            })

        closed_trades.sort(key=lambda t: t["exit_timestamp"], reverse=True)

        # --- Equity curve: start at initial, apply chronological deal nets ---
        curve = [float(initial_balance)]
        running = float(initial_balance)
        for d in sorted_deals:
            delta = float(d.profit) + float(getattr(d, "swap", 0) or 0) + float(getattr(d, "commission", 0) or 0)
            if abs(delta) < 1e-12:
                continue
            running += delta
            curve.append(round(running, 4))
        if len(curve) == 1:
            curve.append(round(current_balance, 4))
        # Cap curve length for JSON payload
        if len(curve) > 500:
            step = len(curve) / 500.0
            curve = [curve[int(i * step)] for i in range(500)]
            curve[-1] = round(current_balance, 4)

        pnls = [t["pnl"] for t in closed_trades]
        analytics = _analytics_from_pnls(list(reversed(pnls)))  # chronological for DD
        # Recompute DD chronologically
        chrono_pnls = [t["pnl"] for t in sorted(closed_trades, key=lambda x: x["exit_timestamp"])]
        analytics = _analytics_from_pnls(chrono_pnls)

        net_pnl = round(current_equity - initial_balance, 2)
        net_pnl_pct = round((net_pnl / (initial_balance + 1e-9)) * 100.0, 2)
        ai_n = sum(1 for t in closed_trades if t.get("source") == "ai")
        legacy_n = sum(1 for t in closed_trades if t.get("source") == "legacy")

        return {
            "initial_balance": float(initial_balance),
            "current_balance": round(current_balance, 2),
            "current_equity": round(current_equity, 2),
            "net_pnl": net_pnl,
            "net_pnl_pct": net_pnl_pct,
            "timezone": TZ_NAME,
            "equity_curve": curve,
            "closed_trades": closed_trades[:100],
            "analytics": analytics,
            "source": "mt5",
            "server": acc.server if acc else "",
            "login": acc.login if acc else 0,
            "trade_counts": {
                "all": len(closed_trades),
                "ai": ai_n,
                "legacy": legacy_n,
            },
            "ai_magic": int(MT5_MAGIC_NUMBER),
        }
    except Exception as e:
        logger.warning(f"[Portfolio] MT5 history error: {e}")
        empty["error"] = str(e)
        return empty


def portfolio_from_duckdb(duckdb_mgr) -> Dict[str, Any]:
    """Fallback portfolio reconstruction from DuckDB trade_logs."""
    from config.settings import ACCOUNT_INITIAL_BALANCE

    initial = float(ACCOUNT_INITIAL_BALANCE)
    try:
        df = duckdb_mgr.get_trade_logs()
    except Exception:
        df = None

    if df is None or getattr(df, "empty", True):
        return {
            "initial_balance": initial,
            "current_balance": initial,
            "current_equity": initial,
            "net_pnl": 0.0,
            "net_pnl_pct": 0.0,
            "timezone": TZ_NAME,
            "equity_curve": [initial, initial],
            "closed_trades": [],
            "analytics": _analytics_from_pnls([]),
            "source": "duckdb",
        }

    rows = df.to_dict(orient="records")
    closed = []
    for r in rows:
        if str(r.get("status", "")).upper() not in ("CLOSED", "DONE", "FILLED", ""):
            # still include if pnl present
            pass
        pnl = float(r.get("pnl") or 0.0)
        entry_ts = float(r.get("entry_timestamp") or 0.0)
        exit_ts = float(r.get("exit_timestamp") or entry_ts)
        closed.append({
            "ticket": r.get("ticket_id") or r.get("order_id") or 0,
            "position_id": r.get("order_id") or 0,
            "symbol": r.get("symbol") or "",
            "direction": r.get("direction") or "",
            "lot": float(r.get("lot") or 0.01),
            "fill_price": float(r.get("fill_price") or 0.0),
            "exit_price": float(r.get("exit_price") or 0.0),
            "pnl": round(pnl, 2),
            "entry_time": _to_ict_str(entry_ts) if entry_ts else "—",
            "exit_time": _to_ict_str(exit_ts) if exit_ts else "—",
            "entry_timestamp": entry_ts,
            "exit_timestamp": exit_ts,
            "comment": str(r.get("comment") or ""),
            "magic": 0,
            "source": "ai",
        })

    chrono = sorted(closed, key=lambda t: t["exit_timestamp"] or t["entry_timestamp"])
    curve = [initial]
    run = initial
    for t in chrono:
        run += t["pnl"]
        curve.append(round(run, 4))
    if len(curve) == 1:
        curve.append(initial)

    analytics = _analytics_from_pnls([t["pnl"] for t in chrono])
    current = round(run, 2)
    net = round(current - initial, 2)
    return {
        "initial_balance": initial,
        "current_balance": current,
        "current_equity": current,
        "net_pnl": net,
        "net_pnl_pct": round((net / (initial + 1e-9)) * 100.0, 2),
        "timezone": TZ_NAME,
        "equity_curve": curve,
        "closed_trades": list(reversed(chrono))[:100],
        "analytics": analytics,
        "source": "duckdb",
    }


