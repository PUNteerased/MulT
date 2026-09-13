# Dashboard — MulT Ops Console (v0) + FastAPI

> อัปเดต: 13 กันยายน 2026

## ภาพรวม
หน้าเว็บ **MulT Ops Console** สร้างจาก v0 (Next.js + Tailwind) เชื่อมกับ backend FastAPI บนโน้ตบุ๊กเพื่อแสดง:

1. Command overview — สถานะระบบ, equity, positions  
2. Computer telemetry — RTX 4050 VRAM, CPU, RAM, disk  
3. Portfolio & risk — **ยอดตั้งต้นจริงจาก MT5**, equity curve, closed trades  
4. MulT system engine — Kill Zone / sniper radar ต่อสัญลักษณ์  

เวลาทั้งหมดที่ผู้ใช้เห็นเป็น **Asia/Bangkok (ICT)** ไม่ใช่ UTC

## โครงสร้างไฟล์

| ส่วน | ที่อยู่ |
|------|---------|
| FastAPI + WebSocket hub | `dashboard/app.py` |
| Telemetry + `get_mt5_portfolio_history()` | `dashboard/system_telemetry.py` |
| UI source (v0 Next.js) | `dashboard/web/` |
| Hook ข้อมูลสด | `dashboard/web/hooks/useLiveDashboard.ts` |
| เวลาไทย / API helpers | `dashboard/web/lib/backend.ts` |
| Static export → Vercel | `dashboard/vercel/` (sync จาก `dashboard/web/out`) |
| SPA รุ่นเก่า (สำรอง) | `dashboard/static/` |
| Launcher | `run_dashboard.py` |

## REST / WebSocket

| Endpoint | คำอธิบาย |
|----------|----------|
| `GET /api/status` | สถานะ ONLINE, 7 subsystems, Red Folder, account snapshot |
| `GET /api/telemetry` | hardware + MT5 account + open positions |
| `GET /api/kill-zones` | bounds/zones ต่อ EURUSD, USDJPY, XAUUSD, BTCUSD |
| `GET /api/portfolio?days=180` | **ประวัติพอร์ตจริงจาก MT5** (ดูด้านล่าง) |
| `GET /api/trades?limit=` | trade_logs ใน DuckDB (ของบอท) |
| `GET /api/analytics` | PerformanceAuditor จาก DuckDB + equity ปัจจุบัน |
| `GET /api/symbols` | สเป็กสัญลักษณ์จาก `symbols.yaml` |
| `GET /api/calendar` | Red Folder / ตารางข่าว |
| `WS /ws` | สตรีม telemetry ~1s + อีเวนต์ ZMQ |

### `GET /api/portfolio` (แหล่งความจริงของหน้า Portfolio)

1. เรียก `mt5.history_deals_get(from, to)` (ค่าเริ่มต้น 180 วัน)  
2. **initial_balance** จากดีลฝาก `DEAL_TYPE_BALANCE` (ผลรวมเงินฝากก่อนเริ่มเทรด)  
   - fallback: `current_balance - sum(profit+swap+commission)`  
3. จัดกลุ่มดีลตาม `position_id` → `closed_trades[]`  
4. สร้าง `equity_curve[]` จากยอดตั้งต้นเดินตามเวลาดีล  
5. คำนวณ analytics: win_rate, profit_factor, max_drawdown_usd, net_pnl  
6. ใส่ `"timezone": "Asia/Bangkok"` และสตริงเวลาแบบ `YYYY-MM-DD HH:MM:SS ICT`

ถ้า MT5 อ่านประวัติไม่ได้ → `portfolio_from_duckdb()` + `ACCOUNT_INITIAL_BALANCE`

ตัวอย่างฟิลด์หลัก:

```json
{
  "initial_balance": 1000.0,
  "current_balance": 760.3,
  "current_equity": 760.3,
  "net_pnl": -239.7,
  "net_pnl_pct": -23.97,
  "timezone": "Asia/Bangkok",
  "equity_curve": [1000.0, "..."],
  "closed_trades": [{ "symbol": "XAUUSD", "pnl": -18.39, "exit_time": "... ICT" }],
  "analytics": { "win_rate": 0, "profit_factor": 0, "total_trades": 13 },
  "source": "mt5"
}
```

> หมายเหตุ: ยอดตั้งต้นบน UI **ไม่ใช่** hardcode $50 อีกต่อไป — $50 เป็นแค่โมเดล Risk Guard

## เวลาประเทศไทย

| จุด | พฤติกรรม |
|-----|----------|
| Header clock | `formatClock()` → `HH:mm:ss ICT` |
| Event / console feed | `formatLocalTime()` ใน `Asia/Bangkok` |
| Closed trades table | ใช้ `entry_time` / `exit_time` จาก API (ICT) |

## หน้า UI (แท็บ)

| แท็บ | ข้อมูลหลัก |
|------|------------|
| Command overview | system_state, equity vs initial, open positions, service health |
| Computer telemetry | VRAM (เตือน >2500MB), CPU%, RAM%, disk free |
| Portfolio & risk | Initial → Equity, curve จาก MT5, closed history, Risk Guard $2.50 |
| MulT system engine | Kill Zone ต่อคู่, event stream จาก ZMQ |

ตั้งค่า Backend: ปุ่ม **Backend bridge** / Settings เก็บ URL ใน `localStorage` คีย์ `mulT_backend_url`

## รันท้องถิ่น

```bash
python run_dashboard.py
# http://localhost:8000  และ http://<LAN-IP>:8000

# ถ้าพอร์ต 8000 ถูกจอง (WinError 10048):
# taskkill /F /PID <pid>
# หรือ python run_dashboard.py --port 8001
```

Dev UI แยกจาก FastAPI:

```bash
cd dashboard/web
npm run dev
# เปิด :3000 — บน localhost จะชี้ backend :8000 อัตโนมัติ
```

## Vercel / GitHub

| รายการ | ค่า |
|--------|-----|
| Repo | https://github.com/PUNteerased/MulT |
| Root Directory บน Vercel | `dashboard/vercel` |
| Build | static (`output: 'export'` จาก Next.js) — ไม่ต้องมี Python บน Vercel |

### ใช้งานจากมือถือคนละเน็ต
1. `python main.py`  
2. `python run_dashboard.py --tunnel` (หรือ ngrok / localtunnel ชี้พอร์ต 8000)  
3. เปิดเว็บ Vercel → วาง Tunnel URL ใน Backend bridge  

หน้า Vercel อย่างเดียว **ไม่มี** ข้อมูล MT5 จนกว่าจะต่อ tunnel

## ทดสอบ
`tests/test_dashboard.py` ตรวจ telemetry, REST รวม `/api/portfolio` (`timezone == Asia/Bangkok`), และ WebSocket snapshot
