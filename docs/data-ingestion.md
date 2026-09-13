# Data Ingestion — การรับข้อมูลและการสร้างฟีเจอร์

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
แปลงสตรีมราคาดิบจาก MetaTrader 5 ให้เป็นสถานะตลาดที่โมดูลอื่นใช้ได้ทันที (tick, M1/M15 bars, ฟีเจอร์ตัวเลข)

## องค์ประกอบ

### MT5 Async Streamer (`subsystems/data_ingestion/mt5_streamer.py`)
- Initialize เทอร์มินัล + บัญชี
- Backfill bars ย้อนหลังลง cache / DuckDB
- Poll ticks แบบไม่บล็อก (`asyncio.to_thread`)
- Publish `TickEvent` / `BarEvent` เข้า ZeroMQ ที่ `tcp://127.0.0.1:5555`
- รองรับ `zmq_endpoint=` แยกสำหรับ unit test เพื่อไม่ชนกับ `main.py`

**สัญลักษณ์เป้าหมาย:** EURUSD, USDJPY, XAUUSD, BTCUSD (`config/symbols.yaml` / `TARGET_SYMBOLS`)

### In-Memory Ring Buffer (`core/memory/in_memory_cache.py`)
- `deque` จำกัดความยาว → O(1) append
- เก็บ tick ล่าสุด, M1/M15 bars, Kill Zone ที่ยังไม่หมดอายุ
- API เช่น `get_latest_tick`, `get_m1_dataframe`, `check_kill_zone_penetration`, `update_kill_zone`

### Feature Worker (`subsystems/data_ingestion/feature_worker.py`)
คำนวณบน CPU (ไม่กิน VRAM):
- **ATR** — ความผันผวนสำหรับระยะ SL/TP
- **RSI** — โมเมนตัม
- **Z-score** ของราคา/รีเทิร์น — หา extreme
- **Wick ratios** — สัดส่วนไส้เทียน (สัญญาณ sweep / rejection)
- **Relative volume** — ปริมาตรเทียบค่าเฉลี่ย

### DuckDB (`core/memory/duckdb_manager.py`)
- เขียน bars / trade_logs จากเอนจิน
- Dashboard เปิด `read_only=True`; ถูกล็อกแล้ว fallback in-memory + seed จาก Parquet

## Input → Output
| Input | Output |
|-------|--------|
| MT5 ticks/bars | `market.tick` / `market.bar.*` บน ZMQ |
| หน้าต่าง M1 | dict ฟีเจอร์สำหรับ sniper / meta |

## ความสัมพันธ์กับ Dashboard
Telemetry บัญชี (balance/equity/positions) มาจาก `SystemTelemetryCollector.get_mt5_telemetry()`  
ประวัติปิดไม้มาจาก `get_mt5_portfolio_history()` — คนละเส้นทางกับ ring buffer สด
