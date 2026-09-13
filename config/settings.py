"""
Global configuration and risk settings for Deep-Sniper AI ($50 Account Architecture).
"""
import os
from pathlib import Path
from typing import Dict, Any
import yaml
from pydantic import BaseModel, Field

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

for folder in [DATA_DIR, MODELS_DIR, LOGS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Risk constants for $50 Account
ACCOUNT_INITIAL_BALANCE = 50.0
MAX_RISK_DOLLARS_PER_TRADE = 2.50  # 5% of $50 hard cap
MAX_CONCURRENT_POSITIONS = 1       # Strictly 1 active trade at any time across account
FIXED_LOT_SIZE = 0.01              # Minimum trade lot allowed by broker
MIN_WIN_PROBABILITY = 0.75         # LightGBM filter gate
MAX_SPREAD_RISK_PCT = 0.20         # Reject if spread USD > 20% of $2.50 risk budget

# Local LM Studio (free) — Research Calculation Auditor
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen/qwen3-8b")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "lm-studio")

# Validation / research artifact dirs
VALIDATION_REPORTS_DIR = DATA_DIR / "validation_reports"
RESEARCH_REPORTS_DIR = DATA_DIR / "research_reports"
for _d in (VALIDATION_REPORTS_DIR, RESEARCH_REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ZeroMQ Endpoints (In-process localhost IPC)
ZMQ_PUB_ENDPOINT = "tcp://127.0.0.1:5555"
ZMQ_SUB_ENDPOINT = "tcp://127.0.0.1:5555"
ZMQ_PULL_ENDPOINT = "tcp://127.0.0.1:5556"
ZMQ_PUSH_ENDPOINT = "tcp://127.0.0.1:5556"

# Topic channels
TOPIC_TICK = "market.tick"
TOPIC_BAR_M1 = "market.bar.m1"
TOPIC_BAR_M15 = "market.bar.m15"
TOPIC_BAR_H1 = "market.bar.h1"
TOPIC_KILL_ZONE = "poi.kill_zone"
TOPIC_TRIGGER_ALERT = "sniper.trigger"
TOPIC_TRADE_TICKET = "risk.ticket"
TOPIC_EXECUTION = "exec.trade"
TOPIC_SYSTEM_STATE = "system.state"

# DuckDB analytical storage
DUCKDB_PATH = str(DATA_DIR / "sniper_warehouse.duckdb")

# Hardware & VRAM Lifecycle Configuration (RTX 4050 6GB)
MAX_GPU_MEMORY_ALLOCATION_MB = 2500  # Dynamic peak upper limit
TORCH_DEVICE = "cuda" if os.environ.get("USE_CPU", "0") != "1" else "cpu"

# Windows Asyncio configuration
import sys
import asyncio
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

class SymbolConfig(BaseModel):
    digits: int
    point: float
    contract_size: float
    pip_value_usd_per_lot: float
    pip_multiplier: float
    min_lot: float = 0.01
    max_lot: float = 0.01
    max_spread_points: int
    max_sl_points: int
    be_trigger_rr: float = 1.5
    be_lock_pips: float = 2.0
    trailing_step_pips: float = 1.5
    atr_k1: float = 1.2
    atr_k2: float = 0.15
    atr_timeframe_sl: str = "M15"
    use_atr_sizing: bool = True

def load_symbols_config() -> Dict[str, SymbolConfig]:
    yaml_path = CONFIG_DIR / "symbols.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    symbols = {}
    for sym, cfg in data.get("symbols", {}).items():
        symbols[sym] = SymbolConfig(**cfg)
    return symbols

SYMBOLS_CONFIG = load_symbols_config()
TARGET_SYMBOLS = list(SYMBOLS_CONFIG.keys())
