# Deep-Sniper AI — เอกสารระบบ

ชุดเอกสารนี้อธิบายระบบวิเคราะห์และเทรด **Deep-Sniper AI** บนบัญชีไมโคร (สถาปัตยกรรม Fixed-Point $50) รันบน Acer Nitro V 16 (Ryzen 7 8845HS + RTX 4050 6GB) ผ่าน MetaTrader 5

## สารบัญ

| เอกสาร | เนื้อหา |
|--------|---------|
| [architecture.md](architecture.md) | ภาพรวม 4 ชั้น / 7 ซับซิสเต็ม, ZeroMQ, DuckDB |
| [data-ingestion.md](data-ingestion.md) | ดึงข้อมูล MT5, ring buffer, ฟีเจอร์เทคนิค |
| [macro-sentiment.md](macro-sentiment.md) | ปฏิทินข่าว Red Folder, FinBERT, HMM regime |
| [poi-radar.md](poi-radar.md) | KDE Kill Zone, Chronos-Bolt, จัดการ VRAM |
| [m1-sniper.md](m1-sniper.md) | Sweep detector, CNN-LSTM, การตื่นใน Kill Zone |
| [meta-labeling.md](meta-labeling.md) | LightGBM กรองโอกาสชนะ ≥ 0.75 |
| [risk-guard.md](risk-guard.md) | กฎเสี่ยง $2.50 / 0.01 lot / 1 ไม้ |
| [execution.md](execution.md) | ส่งออเดอร์ MT5, trailing BE+2 pips |
| [evolution-audit.md](evolution-audit.md) | Weekend learner, Performance Auditor |
| [dashboard.md](dashboard.md) | Web dashboard, `/api/portfolio`, เวลาไทย |

## วิธีรันแบบย่อ

```bash
# Terminal 1 — เอนจินเทรด
python main.py

# Terminal 2 — API + WebSocket (พอร์ต 8000)
python run_dashboard.py
# หรือ remote: python run_dashboard.py --tunnel

# UI (dev)
cd dashboard/web && npm run dev
```

เวลาที่แสดงบน dashboard เป็น **Asia/Bangkok (ICT)**  
ประวัติพอร์ตโฟลิโอจริงมาจาก **MT5 `history_deals_get`** ผ่าน `GET /api/portfolio`
