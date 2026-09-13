# Evolution & Performance Audit — เรียนรู้ช่วงสุดสัปดาห์

## วัตถุประสงค์
นอกตลาด (สุดสัปดาห์) ระบบทบทวนประสบการณ์ แล้วปรับโมเดลโดยไม่รบกวนเซสชันสด

## Weekend Learner (`subsystems/evolution/weekend_learner.py`)
- อ่าน trade logs / ฟีเจอร์ที่บันทึกไว้
- Experience replay
- Retrain LightGBM และ/หรือ fine-tune CNN-LSTM ตามตาราง
- Export Parquet จาก DuckDB เพื่อเทรนออฟไลน์

## Performance Auditor (`subsystems/evolution/performance_audit.py`)
คำนวณจาก `trade_logs`:
- Win rate (%)
- Profit factor
- Net PnL
- Max drawdown (USD)
- Expectancy

หมายเหตุ: หน้า Portfolio บน dashboard ใช้สถิติจาก **MT5 deals** เป็นหลัก (`/api/portfolio`) ส่วน auditor ยังใช้ DuckDB ของบอท

## ไฟล์ข้อมูล
- `data/sniper_warehouse.duckdb`
- `data/trades.parquet`, `data/bars_m1.parquet`
