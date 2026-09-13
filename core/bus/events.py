"""
Pydantic event contracts for ZeroMQ IPC event bus.
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time

class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class SystemState(str, Enum):
    NORMAL = "NORMAL"
    RISK_OFF = "RISK_OFF"
    HALT_TRADING = "HALT_TRADING"

class TickEvent(BaseModel):
    symbol: str
    time_msc: int
    bid: float
    ask: float
    spread: float
    volume: float = 0.0

class BarEvent(BaseModel):
    symbol: str
    timeframe: str  # e.g. "M1", "M15", "H1"
    time: int       # Bar open time (unix seconds)
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    is_closed: bool = True

class KillZoneEvent(BaseModel):
    zone_id: str
    symbol: str
    timeframe: str
    direction: OrderDirection
    lower_bound: float
    upper_bound: float
    mid_price: float
    confidence: float
    created_at: float = Field(default_factory=time.time)
    expires_at: float

class TriggerAlertEvent(BaseModel):
    alert_id: str
    symbol: str
    direction: OrderDirection
    entry_price: float
    wick_sl_price: float
    zone_id: Optional[str] = None
    pattern_name: str = "LIQUIDITY_SWEEP_WICK"
    model_confidence: float
    created_at: float = Field(default_factory=time.time)
    features: Dict[str, float] = Field(default_factory=dict)

class TradeTicketEvent(BaseModel):
    ticket_id: str
    symbol: str
    direction: OrderDirection
    lot: float = 0.01
    entry_price: float
    sl_price: float
    be_trigger_price: float
    be_lock_price: float
    tp_target_price: float
    risk_dollars: float
    win_probability: float
    atr_at_entry: float = 0.0
    sl_usd: float = 0.0
    spread_usd: float = 0.0
    atr_k1: float = 1.2
    atr_k2: float = 0.15
    created_at: float = Field(default_factory=time.time)

class ExecutionEvent(BaseModel):
    ticket_id: str
    order_id: int
    symbol: str
    direction: OrderDirection
    lot: float
    fill_price: float
    initial_sl: float
    current_sl: float
    status: str  # "PLACED", "MODIFIED_BE", "TRAILED", "CLOSED_TP", "CLOSED_SL", "REJECTED"
    pnl: float = 0.0
    comment: str = ""
    timestamp: float = Field(default_factory=time.time)

class SystemStateEvent(BaseModel):
    state: SystemState
    reason: str
    source: str
    valid_until: Optional[float] = None
    timestamp: float = Field(default_factory=time.time)
