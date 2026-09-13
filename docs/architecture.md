# สถาปัตยกรรมระบบ (Architecture)

## เป้าหมาย
ระบบ event-driven สำหรับบัญชีไมโคร ที่วิเคราะห์ตลาดหลายชั้น แล้วคัดกรองจนเหลือเฉพาะเซ็ตอัพคุณภาพสูงก่อนส่งออเดอร์ 0.01 lot

## 4 ชั้นหลัก

1. **Data & Memory** — รับ tick/bar จาก MT5, เก็บใน ring buffer + DuckDB  
2. **Macro & Sentiment** — ข่าวแรง (Red Folder), sentiment, regime  
3. **POI / Sniper / Meta** — Kill Zone → M1 pattern → LightGBM gate  
4. **Risk & Execution** — กันขาดทุน $2.50 แล้วส่งออเดอร์ + trailing

## 7 Subsystems

| # | ชื่อ | หน้าที่สั้นๆ |
|---|------|----------------|
| 1 | Data Ingestion | MT5 poll + feature engineering |
| 2 | Macro & Sentiment | Calendar halt, FinBERT, HMM |
| 3 | POI Radar | KDE zones + Chronos quantiles |
| 4 | M1 Sniper | Sweep + CNN-LSTM ใน Kill Zone |
| 5 | Meta-Labeling | LightGBM `P(win) ≥ 0.75` |
| 6 | Risk Guard | กฎบัญชี $50 fixed-point |
| 7 | Execution | MT5 async + BE trail |

## Event Bus (ZeroMQ)
- PUB ที่ `tcp://127.0.0.1:5555`
- Topics สำคัญ: `market.tick`, `poi.kill_zone`, `sniper.trigger`, `risk.ticket`, `execution`, `system_state`
- Dashboard subscribe topics เดียวกันแล้ว broadcast ผ่าน WebSocket

## Persistence
- **In-memory**: `MarketMemoryCache` (deque) สำหรับ latency ต่ำ  
- **DuckDB**: `data/sniper_warehouse.duckdb` (bars_m1, trade_logs, kill_zones)  
- ถ้าไฟล์ถูกล็อกโดย `main.py` → reader ใช้ in-memory + seed จาก Parquet

## Orchestrator
`main.py` เปิดทุก worker แบบ asyncio ไม่บล็อก event loop ด้วย `asyncio.to_thread()` สำหรับการเรียก MT5 / GPU
