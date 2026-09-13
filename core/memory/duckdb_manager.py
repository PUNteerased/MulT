"""
DuckDB analytical storage manager.
Stores historical M1 bars and trade execution logs on NVMe SSD for fast analytics and weekend RL.
"""
import duckdb
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from loguru import logger
from config.settings import DUCKDB_PATH, DATA_DIR
from core.bus.events import BarEvent

class DuckDBManager:
    """Manages persistent columnar time-series storage in DuckDB."""
    _instance = None

    def __new__(cls, db_path: str = DUCKDB_PATH, read_only: bool = False):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db(db_path, read_only=read_only)
        return cls._instance

    def _init_db(self, db_path: str, read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only
        try:
            self.conn = duckdb.connect(self.db_path, read_only=read_only)
            if not read_only:
                self._create_tables()
            logger.info(f"[DuckDB] Connected to {self.db_path} (read_only={read_only})")
        except Exception as e:
            # Fallback to in-memory instance if database file is locked by primary trading engine
            logger.warning(f"[DuckDB] File locked by active engine ({e}). Initializing in-memory reader fallback...")
            self.conn = duckdb.connect(":memory:")
            self._create_tables()
            # Attempt to seed with parquet trade snapshot if available
            parquet_trades = DATA_DIR / "trades.parquet"
            if parquet_trades.exists():
                try:
                    self.conn.execute(f"INSERT INTO trade_logs SELECT * FROM read_parquet('{parquet_trades.as_posix()}');")
                    logger.info("[DuckDB] Seeded in-memory cache from trades.parquet")
                except Exception as ex:
                    logger.debug(f"[DuckDB] Could not load trades.parquet: {ex}")

    def _create_tables(self):
        # M1 bars table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bars_m1 (
                symbol VARCHAR,
                time BIGINT,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                tick_volume BIGINT,
                spread INTEGER,
                PRIMARY KEY (symbol, time)
            );
        """)

        # Trade logs table for weekend evolution
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_logs (
                ticket_id VARCHAR PRIMARY KEY,
                order_id BIGINT,
                symbol VARCHAR,
                direction VARCHAR,
                lot DOUBLE,
                fill_price DOUBLE,
                exit_price DOUBLE,
                initial_sl DOUBLE,
                exit_sl DOUBLE,
                pnl DOUBLE,
                status VARCHAR,
                comment VARCHAR,
                entry_timestamp DOUBLE,
                exit_timestamp DOUBLE,
                features_json VARCHAR
            );
        """)

        # Kill zone history
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kill_zones (
                zone_id VARCHAR PRIMARY KEY,
                symbol VARCHAR,
                timeframe VARCHAR,
                direction VARCHAR,
                lower_bound DOUBLE,
                upper_bound DOUBLE,
                confidence DOUBLE,
                created_at DOUBLE
            );
        """)

    def insert_bar(self, bar: BarEvent):
        """Insert or replace single M1 bar."""
        if bar.timeframe != "M1":
            return
        query = """
            INSERT OR REPLACE INTO bars_m1 
            (symbol, time, open, high, low, close, tick_volume, spread)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(query, [
            bar.symbol, bar.time, bar.open, bar.high, bar.low, bar.close,
            bar.tick_volume, bar.spread
        ])

    def insert_bars_batch(self, bars: List[BarEvent]):
        """Batch insert M1 bars for fast backfill."""
        self._ensure_conn()
        m1_bars = [b for b in bars if b.timeframe == "M1"]
        if not m1_bars:
            return
        data = [
            (b.symbol, b.time, b.open, b.high, b.low, b.close, b.tick_volume, b.spread)
            for b in m1_bars
        ]
        self.conn.executemany("""
            INSERT OR REPLACE INTO bars_m1 
            (symbol, time, open, high, low, close, tick_volume, spread)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, data)

    def log_trade(self, trade_data: Dict[str, Any]):
        """Store completed or updated trade record."""
        self._ensure_conn()
        query = """
            INSERT OR REPLACE INTO trade_logs
            (ticket_id, order_id, symbol, direction, lot, fill_price, exit_price,
             initial_sl, exit_sl, pnl, status, comment, entry_timestamp, exit_timestamp, features_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(query, [
            trade_data.get("ticket_id"),
            trade_data.get("order_id", 0),
            trade_data.get("symbol"),
            trade_data.get("direction"),
            trade_data.get("lot", 0.01),
            trade_data.get("fill_price"),
            trade_data.get("exit_price", 0.0),
            trade_data.get("initial_sl"),
            trade_data.get("exit_sl", 0.0),
            trade_data.get("pnl", 0.0),
            trade_data.get("status"),
            trade_data.get("comment", ""),
            trade_data.get("entry_timestamp"),
            trade_data.get("exit_timestamp", 0.0),
            trade_data.get("features_json", "{}")
        ])

    def _ensure_conn(self):
        """Ensure connection is alive; reconnect to memory fallback if closed or lost."""
        try:
            if hasattr(self, "conn") and self.conn is not None:
                self.conn.execute("SELECT 1;")
                return
        except Exception:
            pass
        self._init_db(getattr(self, "db_path", DUCKDB_PATH), read_only=getattr(self, "read_only", False))

    def get_recent_bars(self, symbol: str, limit: int = 1000) -> pd.DataFrame:
        """Fetch historical bars as pandas DataFrame."""
        self._ensure_conn()
        return self.conn.execute("""
            SELECT * FROM bars_m1 
            WHERE symbol = ? 
            ORDER BY time DESC 
            LIMIT ?;
        """, [symbol, limit]).df().sort_values("time").reset_index(drop=True)

    def get_trade_logs(self) -> pd.DataFrame:
        """Fetch all trade logs for analytics."""
        self._ensure_conn()
        return self.conn.execute("SELECT * FROM trade_logs ORDER BY entry_timestamp DESC;").df()

    def export_to_parquet(self, output_dir: Optional[str] = None):
        """Export DuckDB tables to Parquet files for training."""
        self._ensure_conn()
        target_dir = Path(output_dir or DATA_DIR)
        m1_parquet = target_dir / "bars_m1.parquet"
        trades_parquet = target_dir / "trades.parquet"
        self.conn.execute(f"COPY bars_m1 TO '{m1_parquet.as_posix()}' (FORMAT PARQUET);")
        self.conn.execute(f"COPY trade_logs TO '{trades_parquet.as_posix()}' (FORMAT PARQUET);")
        logger.info(f"[DuckDB] Parquet exported to {target_dir}")

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    @classmethod
    def reset_instance(cls):
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
            cls._instance = None
