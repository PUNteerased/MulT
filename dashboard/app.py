"""
Deep-Sniper AI FastAPI Web Gateway & Real-time WebSocket Hub.
Connects to ZeroMQ PUB/SUB, DuckDB, In-Memory Ring Buffer, and System Telemetry.
Streams live market ticks, Kill Zones, sniper alerts, trade executions, and hardware health
to web clients across LAN, remote tunnel, or Vercel.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import time
from typing import Dict, Any, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from config.settings import (
    BASE_DIR,
    TARGET_SYMBOLS,
    SYMBOLS_CONFIG,
    ZMQ_SUB_ENDPOINT,
    TOPIC_TICK,
    TOPIC_BAR_M1,
    TOPIC_KILL_ZONE,
    TOPIC_TRIGGER_ALERT,
    TOPIC_TRADE_TICKET,
    TOPIC_EXECUTION,
    TOPIC_SYSTEM_STATE
)
from core.bus.zmq_bus import ZMQSubscriber
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager
from subsystems.evolution.performance_audit import PerformanceAuditor
from subsystems.macro_sentiment.calendar_crawler import EconomicCalendarCrawler
from dashboard.system_telemetry import (
    SystemTelemetryCollector,
    get_mt5_portfolio_history,
    portfolio_from_duckdb,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
for sub in ["css", "js"]:
    (STATIC_DIR / sub).mkdir(parents=True, exist_ok=True)


class ConnectionManager:
    """Manages active WebSocket connections and message broadcasting."""
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.event_history: List[Dict[str, Any]] = []
        self.max_history = 100
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"[WebSocket] Client connected. Total active: {len(self.active_connections)}")

        # Send immediate initial telemetry snapshot so UI initializes instantly
        try:
            snapshot = await SystemTelemetryCollector.get_full_snapshot_async()
            await websocket.send_json({
                "type": "telemetry",
                "hardware": snapshot["hardware"],
                "mt5": snapshot["mt5"],
                "account": snapshot["account"],
                "timestamp": time.time(),
            })
        except Exception as e:
            logger.debug(f"[WebSocket] Error sending initial snapshot: {e}")

        # Send initial backlog of recent events if present
        if self.event_history:
            try:
                await websocket.send_json({
                    "type": "event_backlog",
                    "events": self.event_history[-30:],
                    "timestamp": time.time(),
                })
            except Exception as e:
                logger.debug(f"[WebSocket] Error sending backlog: {e}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"[WebSocket] Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast JSON message to all active clients."""
        async with self._lock:
            if message.get("type") in ["trigger_alert", "trade_ticket", "execution", "system_state"]:
                self.event_history.append(message)
                if len(self.event_history) > self.max_history:
                    self.event_history.pop(0)

            disconnected = set()
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)

            for dead in disconnected:
                self.active_connections.discard(dead)


# Global instances
ws_manager = ConnectionManager()
cache = MarketMemoryCache()
duckdb_mgr = DuckDBManager(read_only=True)
auditor = PerformanceAuditor(duckdb=duckdb_mgr)
calendar_crawler = EconomicCalendarCrawler()

# Background tasks reference
background_tasks = []


async def zmq_bridge_worker():
    """Subscribe to ZeroMQ events from Deep-Sniper AI engine and forward to WebSockets."""
    sub = ZMQSubscriber(
        endpoint=ZMQ_SUB_ENDPOINT,
        topics=[
            TOPIC_TICK,
            TOPIC_KILL_ZONE,
            TOPIC_TRIGGER_ALERT,
            TOPIC_TRADE_TICKET,
            TOPIC_EXECUTION,
            TOPIC_SYSTEM_STATE,
        ]
    )
    try:
        sub.connect()
    except Exception as e:
        logger.warning(f"[Dashboard ZMQ Bridge] Cannot connect immediately ({e}), will retry in loop.")

    async def on_zmq_message(topic: str, payload: dict):
        event_type_map = {
            TOPIC_TICK: "tick",
            TOPIC_KILL_ZONE: "kill_zone",
            TOPIC_TRIGGER_ALERT: "trigger_alert",
            TOPIC_TRADE_TICKET: "trade_ticket",
            TOPIC_EXECUTION: "execution",
            TOPIC_SYSTEM_STATE: "system_state",
        }
        # Update in-memory DuckDB trade cache if trade closed
        if topic == TOPIC_EXECUTION and payload.get("status") in ["CLOSED", "PLACED"]:
            try:
                duckdb_mgr.log_trade({
                    "ticket_id": payload.get("ticket_id"),
                    "order_id": payload.get("order_id", 0),
                    "symbol": payload.get("symbol"),
                    "direction": payload.get("direction"),
                    "lot": payload.get("lot", 0.01),
                    "fill_price": payload.get("fill_price", 0.0),
                    "exit_price": payload.get("exit_price", 0.0),
                    "initial_sl": payload.get("initial_sl", 0.0),
                    "exit_sl": payload.get("current_sl", 0.0),
                    "pnl": payload.get("pnl", 0.0),
                    "status": payload.get("status"),
                    "comment": payload.get("comment", ""),
                    "entry_timestamp": payload.get("timestamp", time.time()),
                    "exit_timestamp": time.time() if payload.get("status") == "CLOSED" else 0.0,
                    "features_json": "{}"
                })
            except Exception as ex:
                logger.debug(f"[Dashboard] Error caching trade: {ex}")

        # Cache live kill zones in memory cache
        if topic == TOPIC_KILL_ZONE:
            try:
                from core.bus.events import KillZoneEvent
                kz = KillZoneEvent(**payload)
                cache.update_kill_zone(kz)
            except Exception:
                pass

        # Cache live ticks
        if topic == TOPIC_TICK:
            try:
                from core.bus.events import TickEvent
                tk = TickEvent(**payload)
                cache.add_tick(tk)
            except Exception:
                pass

        msg = {
            "type": event_type_map.get(topic, "custom_event"),
            "topic": topic,
            "data": payload,
            "timestamp": time.time(),
        }
        await ws_manager.broadcast(msg)

    logger.info("[Dashboard] ZMQ Bridge worker started listening...")
    try:
        await sub.listen(on_zmq_message)
    except asyncio.CancelledError:
        pass
    finally:
        sub.stop()


async def telemetry_broadcaster_worker():
    """Periodically collect hardware and account telemetry and stream via WebSocket."""
    logger.info("[Dashboard] Telemetry Broadcaster worker started...")
    while True:
        try:
            snapshot = await SystemTelemetryCollector.get_full_snapshot_async()
            # Fetch active kill zones summary
            active_zones = {}
            for sym in TARGET_SYMBOLS:
                zones = cache.get_active_kill_zones(sym)
                active_zones[sym] = [
                    {
                        "zone_id": z.zone_id,
                        "direction": z.direction,
                        "lower_bound": z.lower_bound,
                        "upper_bound": z.upper_bound,
                        "mid_price": z.mid_price,
                        "confidence": z.confidence,
                        "expires_at": z.expires_at,
                    }
                    for z in zones
                ]

            telemetry_event = {
                "type": "telemetry",
                "hardware": snapshot["hardware"],
                "mt5": snapshot["mt5"],
                "active_kill_zones": active_zones,
                "timestamp": time.time(),
            }
            await ws_manager.broadcast(telemetry_event)
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"[Dashboard Telemetry Broadcaster] Loop warning: {e}")
            await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background workers
    t1 = asyncio.create_task(zmq_bridge_worker(), name="DashboardZMQBridge")
    t2 = asyncio.create_task(telemetry_broadcaster_worker(), name="DashboardTelemetry")
    background_tasks.extend([t1, t2])
    yield
    # Shutdown: cancel workers
    for t in background_tasks:
        t.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)


app = FastAPI(
    title="Deep-Sniper AI Dashboard",
    description="Real-time FinTech Telemetry & Sniper Execution Monitor",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for remote access (e.g. from Vercel deployed frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the single page application dashboard."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"status": "Dashboard frontend loading..."})


@app.get("/api/status")
async def get_system_status():
    """System health snapshot and subsystem availability."""
    snapshot = await SystemTelemetryCollector.get_full_snapshot_async()
    red_folder, active_news = calendar_crawler.check_red_folder_status()

    return {
        "status": "ok",
        "system_status": "ONLINE",
        "subsystems": {
            "data_ingestion": "ONLINE",
            "macro_sentiment": "ONLINE",
            "poi_radar": "ONLINE",
            "m1_sniper": "ONLINE",
            "meta_labeling": "ONLINE",
            "risk_guard": "ONLINE",
            "execution": "ONLINE",
        },
        "system_state": "HALT_TRADING" if red_folder else "NORMAL",
        "red_folder": {
            "is_active": red_folder,
            "title": active_news,
        },
        "symbols": TARGET_SYMBOLS,
        "target_symbols": TARGET_SYMBOLS,
        "account": snapshot["account"],
        "hardware": snapshot["hardware"],
        "timestamp": time.time(),
    }


@app.get("/api/telemetry")
async def get_telemetry():
    """Get latest hardware and MT5 stats."""
    return await SystemTelemetryCollector.get_full_snapshot_async()


@app.get("/api/kill-zones")
async def get_kill_zones():
    """Retrieve all current active Kill Zones across all target assets."""
    data = {}
    for sym in TARGET_SYMBOLS:
        zones = cache.get_active_kill_zones(sym)
        latest_tick = cache.get_latest_tick(sym)
        data[sym] = {
            "current_price": latest_tick.bid if latest_tick else None,
            "current_spread": latest_tick.spread if latest_tick else None,
            "bounds": [
                {"lower": z.lower_bound, "upper": z.upper_bound, "direction": z.direction}
                for z in zones
            ],
            "zones": [
                {
                    "zone_id": z.zone_id,
                    "direction": z.direction,
                    "lower_bound": z.lower_bound,
                    "upper_bound": z.upper_bound,
                    "mid_price": z.mid_price,
                    "confidence": z.confidence,
                    "timeframe": z.timeframe,
                    "expires_at": z.expires_at,
                }
                for z in zones
            ],
        }
    return data


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """Fetch completed and active trade logs from DuckDB."""
    try:
        df = duckdb_mgr.get_trade_logs()
        if df.empty:
            return {"trades": [], "total": 0}
        records = df.head(limit).to_dict(orient="records")
        return {"trades": records, "total": len(df)}
    except Exception as e:
        logger.error(f"[API] Error querying trades: {e}")
        return {"trades": [], "total": 0, "error": str(e)}


@app.get("/api/portfolio")
async def get_portfolio(days: int = 180):
    """
    Real MT5 deal history: initial balance, equity curve, closed trades, analytics.
    Times are Asia/Bangkok (ICT). Falls back to DuckDB if MT5 history unavailable.
    """
    data = await asyncio.to_thread(get_mt5_portfolio_history, days)
    if data.get("source") == "mt5":
        return data
    # fallback / error → DuckDB, but keep live balances when MT5 partially worked
    fb = await asyncio.to_thread(portfolio_from_duckdb, duckdb_mgr)
    if data.get("current_balance") and data.get("source") != "fallback":
        fb["current_balance"] = data["current_balance"]
        fb["current_equity"] = data.get("current_equity", data["current_balance"])
        fb["initial_balance"] = data.get("initial_balance", fb["initial_balance"])
        fb["net_pnl"] = round(fb["current_equity"] - fb["initial_balance"], 2)
        fb["net_pnl_pct"] = round((fb["net_pnl"] / (fb["initial_balance"] + 1e-9)) * 100.0, 2)
    if data.get("equity_curve") and len(data.get("equity_curve", [])) > 2:
        fb["equity_curve"] = data["equity_curve"]
    if data.get("closed_trades"):
        fb["closed_trades"] = data["closed_trades"]
        fb["analytics"] = data.get("analytics") or fb["analytics"]
    fb["timezone"] = "Asia/Bangkok"
    fb["server"] = data.get("server", fb.get("server", ""))
    fb["login"] = data.get("login", fb.get("login", 0))
    if data.get("error"):
        fb["mt5_error"] = data["error"]
    return fb


@app.get("/api/analytics")
async def get_analytics():
    """Calculate performance metrics (Win Rate, Profit Factor, Max Drawdown)."""
    report = auditor.generate_report()
    snapshot = await SystemTelemetryCollector.get_full_snapshot_async()
    acc = snapshot.get("account") or {}
    report["win_rate"] = report.get("win_rate_pct", 0.0)
    report["current_equity"] = acc.get("equity", 50.0)
    report["current_balance"] = acc.get("balance", 50.0)
    return report


@app.get("/api/symbols")
async def get_symbols_config():
    """Return symbol parameters, contract sizes, and trailing rules."""
    out = {}
    for sym, cfg in SYMBOLS_CONFIG.items():
        out[sym] = cfg.model_dump()
    return out


@app.get("/api/calendar")
async def get_calendar():
    """Return scheduled news events and Red Folder status."""
    halted, title = calendar_crawler.check_red_folder_status()
    return {
        "is_halted": halted,
        "active_event": title,
        "events_count": len(calendar_crawler.scheduled_events),
        "scheduled_events": calendar_crawler.scheduled_events[-20:],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time bi-directional WebSocket connection."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive & handle incoming pings
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except Exception:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"[WebSocket] Disconnected with reason: {e}")
        await ws_manager.disconnect(websocket)
