# Deep-Sniper AI — เอกสารระบบ (อัปเดตล่าสุด)

> อัปเดต: **13 กันยายน 2026**  
> Repo: [github.com/PUNteerased/MulT](https://github.com/PUNteerased/MulT)  
> ฮาร์ดแวร์เป้าหมาย: Acer Nitro V 16 · Ryzen 7 8845HS · RTX 4050 6GB · 32GB RAM · MT5 (FBS-Demo)

ชุดเอกสารนี้อธิบายระบบวิเคราะห์และเทรด **Deep-Sniper AI** แบบ event-driven สำหรับบัญชีไมโคร (กฎเสี่ยง Fixed-Point $50) พร้อม **MulT Ops Console** (เว็บจาก v0) ที่แสดงพอร์ตจริงจาก MT5 และนาฬิกา **Asia/Bangkok (ICT)**

## สารบัญ

| เอกสาร | เนื้อหา |
|--------|---------|
| [architecture.md](architecture.md) | ภาพรวม 4 ชั้น / 7 ซับซิสเต็ม + ชั้นมอนิเตอร์, ZeroMQ, DuckDB |
| [data-ingestion.md](data-ingestion.md) | ดึงข้อมูล MT5, ring buffer, ฟีเจอร์เทคนิค |
| [macro-sentiment.md](macro-sentiment.md) | ปฏิทินข่าว Red Folder, FinBERT, HMM regime |
| [poi-radar.md](poi-radar.md) | KDE Kill Zone, Chronos-Bolt, จัดการ VRAM |
| [m1-sniper.md](m1-sniper.md) | Sweep detector, CNN-LSTM, การตื่นใน Kill Zone |
| [meta-labeling.md](meta-labeling.md) | LightGBM กรองโอกาสชนะ ≥ 0.75 |
| [risk-guard.md](risk-guard.md) | กฎเสี่ยง $2.50 / 0.01 lot / 1 ไม้ vs ยอดบัญชีจริง |
| [execution.md](execution.md) | ส่งออเดอร์ MT5, trailing BE+2 pips |
| [evolution-audit.md](evolution-audit.md) | Weekend learner, Performance Auditor |
| [dashboard.md](dashboard.md) | v0 UI, FastAPI, `/api/portfolio`, Vercel, tunnel |

## สิ่งที่เปลี่ยนล่าสุด (สรุป)

1. **Portfolio จริงจาก MT5** — `GET /api/portfolio` ใช้ `history_deals_get` คำนวณยอดตั้งต้นจากเงินฝาก, equity curve, closed trades, WR/PF  
2. **เวลาไทย (ICT)** — นาฬิกา UI, event feed, เวลาปิดไม้ ใช้ `Asia/Bangkok` ไม่ใช้ UTC  
3. **MulT Ops Console (v0)** — Next.js ที่ `dashboard/web/` export static ไป `dashboard/vercel/`  
4. **GitHub** — โค้ดขึ้น [PUNteerased/MulT](https://github.com/PUNteerased/MulT) แล้ว ผูก Vercel ได้จาก Root Directory `dashboard/vercel`

## วิธีรันแบบย่อ

```bash
# Terminal 1 — เอนจินเทรด
python main.py

# Terminal 2 — API + WebSocket (พอร์ต 8000)
python run_dashboard.py
# remote จากมือถือคนละเน็ต:
python run_dashboard.py --tunnel

# UI พัฒนาท้องถิ่น (Next.js → ชี้ http://127.0.0.1:8000 อัตโนมัติ)
cd dashboard/web
npm install
npm run dev
```

เปิด dashboard ท้องถิ่น: http://localhost:8000 (ถ้าพอร์ตถูกจองแล้ว ให้ `taskkill` โปรเซสเก่า หรือใช้ `--port 8001`)

### Vercel + ข้อมูลสด
1. Deploy โฟลเดอร์ `dashboard/vercel` (หรือผูก repo บน Vercel)  
2. บนคอมรัน `python run_dashboard.py --tunnel`  
3. ในหน้าเว็บกด **Backend bridge** ใส่ URL ทันเนล → Save & Connect  

หน้า Vercel ที่ไม่ต่อ tunnel จะโชว์ Offline / ค่าเริ่มต้น — เป็นเรื่องปกติ

## โครงสร้างโฟลเดอร์สำคัญ

```text
MulT/
├── main.py                 # Orchestrator 7 subsystems
├── run_dashboard.py        # FastAPI launcher (+ --tunnel)
├── config/                 # settings, symbols.yaml
├── core/                   # ZMQ bus, memory, DuckDB
├── subsystems/             # ingestion → … → execution
├── dashboard/
│   ├── app.py              # REST + WebSocket hub
│   ├── system_telemetry.py # VRAM/CPU + MT5 portfolio history
│   ├── web/                # Next.js v0 source (MulT Ops Console)
│   ├── vercel/             # Static export สำหรับ Vercel
│   └── static/             # SPA รุ่นเก่า (สำรอง)
├── docs/                   # เอกสารชุดนี้
└── tests/                  # pytest (รวม test_dashboard.py)
```
