# Evolution & Performance Audit — เรียนรู้ช่วงสุดสัปดาห์

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
นอกตลาด (สุดสัปดาห์) ระบบทบทวนประสบการณ์ แล้วปรับโมเดลโดยไม่รบกวนเซสชันสด

## Weekend Learner (`subsystems/evolution/weekend_learner.py`)
- อ่าน trade logs / ฟีเจอร์ที่บันทึกไว้
- Experience replay
- Retrain LightGBM และ/หรือ fine-tune CNN-LSTM ตามตาราง
- Export Parquet จาก DuckDB เพื่อเทรนออฟไลน์

## Performance Auditor (`subsystems/evolution/performance_audit.py`)
คำนวณจาก DuckDB `trade_logs` (เฉพาะที่บอทบันทึก):
- Win rate (%)
- Profit factor
- Net PnL
- Max drawdown (USD)
- Expectancy

ใช้ผ่าน `GET /api/analytics`

## สองแหล่งสถิติบน Dashboard (อย่าสับสน)

| แหล่ง | Endpoint / ฟังก์ชัน | ความหมาย |
|-------|---------------------|----------|
| **MT5 deals** | `GET /api/portfolio` | ความจริงของบัญชีโบรกเกอร์ (แนะนำสำหรับหน้า Portfolio) |
| **DuckDB bot log** | `GET /api/analytics`, `GET /api/trades` | เฉพาะออเดอร์ที่เอนจิน Deep-Sniper บันทึก |

ถ้า DuckDB ว่าง แต่เคยเทรดใน MT5 → หน้า Portfolio ยังมี curve/history จาก MT5 ได้

## ไฟล์ข้อมูล
- `data/sniper_warehouse.duckdb` (ถูกล็อกตอน `main.py` รัน)
- `data/trades.parquet`, `data/bars_m1.parquet`
- `models/lgbm_meta_filter.txt`
