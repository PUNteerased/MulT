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
from typing import Dict, Any, List, Set, Literal, Optional as Opt

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

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
    TOPIC_SYSTEM_STATE,
    RESEARCH_REPORTS_DIR,
    LLM_BASE_URL,
    LLM_MODEL,
    RISK_PCT_PER_TRADE,
    RISK_DOLLARS_FLOOR,
    RISK_DOLLARS_CEILING,
)
from core.bus.zmq_bus import ZMQSubscriber
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager
from subsystems.evolution.performance_audit import PerformanceAuditor
from subsystems.macro_sentiment.calendar_crawler import EconomicCalendarCrawler
from subsystems.research.store import list_reports, get_report, update_status
from subsystems.research.run_all import run_all as research_run_all
from dashboard.system_telemetry import (
    SystemTelemetryCollector,
    get_mt5_portfolio_history,
    portfolio_from_duckdb,
)
from dashboard.health import (
    build_alerts,
    build_subsystem_status,
    derive_system_state,
    resolve_equity,
)
from dashboard.auth import (
    DashboardAuthMiddleware,
    make_token,
    password_configured,
    verify_secret,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
for sub in ["css", "js"]:
    (STATIC_DIR / sub).mkdir(parents=True, exist_ok=True)

# Prefer Next.js static export (MulT Ops Console); fall back to legacy SPA
WEB_OUT_DIR = BASE_DIR / "out"
if not (WEB_OUT_DIR / "index.html").exists():
    alt = BASE_DIR / "dashboard" / "web" / "out"
    if (alt / "index.html").exists():
        WEB_OUT_DIR = alt


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
_last_zmq_ts: float = 0.0
_last_equity: float | None = None


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
        global _last_zmq_ts
        _last_zmq_ts = time.time()
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
    allow_headers=["*", "X-MulT-Auth", "Authorization"],
)
app.add_middleware(DashboardAuthMiddleware)

# Mount static folders (API + WS routes registered below take precedence when matched first)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (WEB_OUT_DIR / "_next").is_dir():
    app.mount("/_next", StaticFiles(directory=str(WEB_OUT_DIR / "_next")), name="next_assets")


@app.get("/")
async def serve_index():
    """Serve MulT Ops Console (Next export) or legacy SPA — same-origin API/WS (no Backend URL)."""
    for index_path in (WEB_OUT_DIR / "index.html", STATIC_DIR / "index.html"):
        if index_path.exists():
            return FileResponse(index_path)
    return JSONResponse({"status": "Dashboard frontend loading..."})


@app.get("/robots.txt")
async def robots_txt():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/api/healthz")
async def healthz():
    return {"ok": True, "auth_required": password_configured()}


@app.get("/api/auth/status")
async def auth_status():
    return {"ok": True, "auth_required": password_configured()}


class AuthLoginBody(BaseModel):
    password: str


@app.post("/api/auth/login")
async def auth_login(body: AuthLoginBody):
    if not password_configured():
        return {"ok": True, "auth_required": False, "token": ""}
    if not verify_secret(body.password):
        raise HTTPException(status_code=401, detail="invalid_password")
    token = make_token(body.password.strip())
    resp = JSONResponse({"ok": True, "auth_required": True, "token": token})
    resp.set_cookie(
        "mult_auth",
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return resp


@app.get("/api/status")
async def get_system_status():
    """System health snapshot and subsystem availability."""
    global _last_equity
    snapshot = await SystemTelemetryCollector.get_full_snapshot_async()
    red_folder, active_news = calendar_crawler.check_red_folder_status()
    account = snapshot.get("account") or {}
    mt5_connected = bool(account.get("connected"))
    equity, equity_stale = resolve_equity(account, _last_equity)
    if mt5_connected and not equity_stale:
        _last_equity = equity

    from subsystems.risk_guard.guard_50 import RiskGuard50
    from subsystems.risk_guard.runtime_config import load_risk_config
    from subsystems.risk_guard.streak import load_streak_state

    streak = await asyncio.to_thread(load_streak_state)
    rcfg = await asyncio.to_thread(load_risk_config)
    cooldown = bool(streak.get("cooldown"))
    streak_mult = float(streak.get("multiplier", 1.0))
    # Display / armed cap never zeros out solely from cooldown (UI must not show $0.00 as "no risk")
    armed_mult = streak_mult if streak_mult > 0 else 1.0
    armed_cap = RiskGuard50.compute_max_risk_dollars(equity, armed_mult)
    # Effective trading cap (0 during cooldown)
    risk_cap = 0.0 if cooldown else RiskGuard50.compute_max_risk_dollars(equity, streak_mult)
    risk_public = rcfg.public_dict(equity, armed_mult)

    zmq_alive = (_last_zmq_ts > 0 and (time.time() - _last_zmq_ts) < 120.0) or mt5_connected
    subsystems = build_subsystem_status(
        mt5_connected=mt5_connected,
        zmq_alive=zmq_alive,
        cooldown=cooldown,
    )
    system_state = derive_system_state(
        red_folder=red_folder,
        subsystems=subsystems,
        mt5_connected=mt5_connected,
    )
    alerts = build_alerts(
        subsystems=subsystems,
        mt5_connected=mt5_connected,
        red_folder=red_folder,
        red_title=active_news,
        cooldown=cooldown,
    )

    return {
        "status": "ok",
        "system_status": "ONLINE" if mt5_connected else "DEGRADED",
        "subsystems": subsystems,
        "system_state": system_state,
        "alerts": alerts,
        "alert_count": len(alerts),
        "red_folder": {
            "is_active": red_folder,
            "title": active_news,
        },
        "symbols": TARGET_SYMBOLS,
        "target_symbols": TARGET_SYMBOLS,
        "account": account,
        "hardware": snapshot["hardware"],
        "risk": {
            **risk_public,
            "pct": rcfg.risk_pct,
            "risk_cap_usd": armed_cap,  # UI live cap — always meaningful $ from equity
            "effective_cap_usd": risk_cap,  # 0 when cooldown blocks entries
            "armed_cap_usd": armed_cap,
            "equity": equity,
            "equity_stale": equity_stale,
            "streak": streak,
            "cooldown": cooldown,
        },
        "timestamp": time.time(),
    }


class RiskConfigBody(BaseModel):
    mode: Opt[Literal["pct", "fixed"]] = None
    risk_pct: Opt[float] = None
    floor: Opt[float] = None
    ceiling: Opt[float] = None
    fixed_dollars: Opt[float] = None
    max_concurrent_positions: Opt[int] = None
    fixed_lot_size: Opt[float] = None
    max_spread_risk_pct: Opt[float] = None
    streak_half_at: Opt[int] = None
    cooldown_at: Opt[int] = None
    cooldown_clear_wins: Opt[int] = None
    cooldown_hours: Opt[float] = None


@app.get("/api/risk/config")
async def get_risk_config():
    from subsystems.risk_guard.runtime_config import load_risk_config

    cfg = await asyncio.to_thread(load_risk_config)
    return {"ok": True, "config": cfg.public_dict()}


@app.post("/api/risk/config")
async def post_risk_config(body: RiskConfigBody):
    from subsystems.risk_guard.runtime_config import save_risk_config

    try:
        cfg = await asyncio.to_thread(save_risk_config, body.model_dump(exclude_none=True))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "config": cfg.public_dict()}


class SettingsBody(BaseModel):
    section: Opt[str] = None
    patch: Opt[Dict[str, Any]] = None


@app.get("/api/settings")
async def get_all_settings():
    from subsystems.config.system_runtime import load_settings

    rt = await asyncio.to_thread(load_settings)
    return {"ok": True, "settings": rt.public_dict(mask_secrets=True)}


@app.post("/api/settings")
async def post_all_settings(body: SettingsBody):
    from subsystems.config.system_runtime import save_settings

    patch = body.patch or {}
    try:
        if body.section:
            rt = await asyncio.to_thread(save_settings, patch, body.section)
        else:
            rt = await asyncio.to_thread(save_settings, patch, None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "settings": rt.public_dict(mask_secrets=True)}


@app.get("/api/settings/{section}")
async def get_settings_section(section: str):
    from subsystems.config.system_runtime import SECTIONS, load_settings

    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
    rt = await asyncio.to_thread(load_settings)
    data = rt.public_dict(mask_secrets=True)
    return {"ok": True, "section": section, "config": data.get(section)}


@app.post("/api/settings/{section}")
async def post_settings_section(section: str, body: Dict[str, Any]):
    from subsystems.config.system_runtime import SECTIONS, save_settings

    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
    try:
        rt = await asyncio.to_thread(save_settings, body, section)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    pub = rt.public_dict(mask_secrets=True)
    return {"ok": True, "section": section, "config": pub.get(section)}


@app.post("/api/settings/llm/test")
async def test_llm_connection():
    from subsystems.research.llm_client import LocalLLMClient

    client = LocalLLMClient.from_runtime()
    ok = await asyncio.to_thread(client.is_reachable)
    return {
        "ok": ok,
        "base_url": client.base_url,
        "model": client.model,
        "provider": getattr(client, "provider", "unknown"),
        "detail": "reachable" if ok else "unreachable",
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


@app.get("/api/research/reports")
async def get_research_reports(limit: int = 30):
    """List Calculation Auditor proposals (read-only; never auto-applied)."""
    rows = await asyncio.to_thread(list_reports, limit)
    return {
        "reports": rows,
        "dir": str(RESEARCH_REPORTS_DIR),
        "llm": {"base_url": LLM_BASE_URL, "model": LLM_MODEL},
        "auto_apply": False,
    }


@app.get("/api/research/reports/{report_id}")
async def get_research_report(report_id: str):
    report = await asyncio.to_thread(get_report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


class ResearchStatusBody(BaseModel):
    status: Literal["approved", "rejected", "proposed", "needs_review", "backtested"]
    note: Opt[str] = None


class ResearchRunBody(BaseModel):
    module: Literal["auditor", "news", "strategy", "all"] = "all"
    force: bool = True
    rules_only: bool = False


@app.post("/api/research/reports/{report_id}/status")
async def post_research_status(report_id: str, body: ResearchStatusBody):
    """Human approve/reject only — never writes live trading config."""
    try:
        report = await asyncio.to_thread(update_status, report_id, body.status, body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"ok": True, "report_id": report_id, "status": report.get("status"), "auto_apply": False}


@app.post("/api/research/run")
async def post_research_run(body: ResearchRunBody):
    """Trigger offline research job (proposals only)."""
    result = await asyncio.to_thread(
        research_run_all,
        force=body.force,
        ignore_gpu=False,
        halt=False,
        use_llm=not body.rules_only,
        modules=[body.module],
    )
    return {**result, "auto_apply": False}


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


@app.get("/{asset_path:path}")
async def serve_web_asset(asset_path: str):
    """Serve Next export public assets (icons, placeholders) from out/."""
    # Never let the SPA catch-all claim /api/* (POST would otherwise become 405).
    if not asset_path or asset_path.startswith(("api/", "ws", "static/", "docs")):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = WEB_OUT_DIR / asset_path
    if candidate.is_file():
        return FileResponse(candidate)
    legacy = STATIC_DIR / asset_path
    if legacy.is_file():
        return FileResponse(legacy)
    raise HTTPException(status_code=404, detail="Not found")


# Explicit unknown-API fallback so missing routes are 404, not catch-all 405.
@app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def unknown_api(full_path: str):
    raise HTTPException(status_code=404, detail=f"Unknown API path: /api/{full_path}")
