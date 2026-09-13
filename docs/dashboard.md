# Dashboard — มอนิเตอร์เว็บและพอร์ตโฟลิโอจริง

## องค์ประกอบ
| ส่วน | ที่อยู่ |
|------|---------|
| FastAPI + WebSocket | `dashboard/app.py` |
| Telemetry / MT5 history | `dashboard/system_telemetry.py` |
| UI (v0 Next.js) | `dashboard/web/` |
| Static สำหรับ Vercel | `dashboard/web/out` → `dashboard/vercel/` |
| Launcher | `run_dashboard.py` |

## REST ที่สำคัญ
- `GET /api/status` — สถานะระบบ + Red Folder  
- `GET /api/telemetry` — VRAM / CPU / RAM / บัญชี  
- `GET /api/kill-zones` — โซน POI ต่อสัญลักษณ์  
- `GET /api/portfolio?days=180` — **ประวัติจริงจาก MT5**  
- `GET /api/trades` — log ใน DuckDB (ของบอท)  
- `WS /ws` — สตรีม telemetry + อีเวนต์

## `/api/portfolio` คำนวณอะไร
1. `history_deals_get` ย้อนหลัง (ค่าเริ่มต้น 180 วัน)  
2. **Initial balance** จากดีลฝากเงิน (`DEAL_TYPE_BALANCE`) หรือถอดย้อนจากผลรวมดีล  
3. จัดกลุ่มดีลตาม `position_id` → closed trades  
4. Equity curve จาก running balance  
5. Win rate / profit factor / max DD  
6. เวลาทั้งหมดเป็น **Asia/Bangkok (ICT)**

ถ้า MT5 อ่านประวัติไม่ได้ → fallback DuckDB + `ACCOUNT_INITIAL_BALANCE`

## เวลาประเทศไทย
- Frontend: `formatClock` / `formatLocalTime` ใช้ `timeZone: 'Asia/Bangkok'` ต่อท้าย `ICT`  
- Backend: ฟิลด์ `entry_time` / `exit_time` เป็นสตริง ICT  

## Remote / Vercel
1. `python run_dashboard.py --tunnel`  
2. เปิดหน้า Vercel → ใส่ Tunnel URL ใน Backend bridge  
3. UI อยู่บนคลาวด์ ข้อมูลสดมาจากโน้ตบุ๊ก
