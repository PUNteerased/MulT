# Data Ingestion — การรับข้อมูลและการสร้างฟีเจอร์

## วัตถุประสงค์
แปลงสตรีมราคาดิบจาก MetaTrader 5 ให้เป็นสถานะตลาดที่โมดูลอื่นใช้ได้ทันที (tick, M1/M15 bars, ฟีเจอร์ตัวเลข)

## องค์ประกอบ

### MT5 Async Streamer (`subsystems/data_ingestion/mt5_streamer.py`)
- Initialize เทอร์มินัล + บัญชี
- Backfill bars ย้อนหลังลง cache / DuckDB
- Poll ticks แบบไม่บล็อก (`asyncio.to_thread`)
- Publish `TickEvent` / `BarEvent` เข้า ZeroMQ

**สัญลักษณ์เป้าหมาย:** EURUSD, USDJPY, XAUUSD, BTCUSD (จาก `config/symbols.yaml`)

### In-Memory Ring Buffer (`core/memory/in_memory_cache.py`)
- `deque` จำกัดความยาว → O(1) append
- เก็บ tick ล่าสุด, M1/M15 bars, Kill Zone ที่ยังไม่หมดอายุ
- API เช่น `get_latest_tick`, `get_m1_dataframe`, `check_kill_zone_penetration`

### Feature Worker (`subsystems/data_ingestion/feature_worker.py`)
คำนวณบน CPU (ไม่กิน VRAM):
- **ATR** — ความผันผวนสำหรับระยะ SL/TP
- **RSI** — โมเมนตัม
- **Z-score** ของราคา/รีเทิร์น — หา extreme
- **Wick ratios** — สัดส่วนไส้เทียน (สัญญาณ sweep / rejection)
- **Relative volume** — ปริมาตรเทียบค่าเฉลี่ย

## Input → Output
| Input | Output |
|-------|--------|
| MT5 ticks/bars | `TickEvent`, `BarEvent` บน ZMQ |
| หน้าต่าง M1 | dict ฟีเจอร์สำหรับ sniper / meta |

## ข้อควรรู้
Streamer ต้องไม่ bind พอร์ต ZMQ ซ้ำกับ `main.py` เวลาเทส — ใช้ endpoint แยกใน unit test
