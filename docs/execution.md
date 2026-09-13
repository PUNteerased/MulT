# Execution — ส่งออเดอร์และ Trailing

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
ส่งคำสั่งเข้า MT5 แบบไม่บล็อก event loop และจัดการไม้เดียวให้กลายเป็น **ความเสี่ยงศูนย์** เมื่อถึงเป้า

## ทำไมไม่ partial close
โบรกส่วนใหญ่ขั้นต่ำ 0.01 lot — ปิดบางส่วนจะเหลือเศษที่เสี่ยงเกิน $2.50  
ดังนั้นใช้กลยุทธ์: **ไม้เดียว + trailing รุนแรง**

## ลำดับชีวิตของออเดอร์
1. `mt5_router` ส่ง market order 0.01 lot พร้อม SL ที่ Risk Guard อนุมัติ  
2. เมื่อราคาวิ่งได้ประมาณ **1:1.5 R:R (TP1)** → เลื่อน SL เป็น **Break-Even + 2 pips**  
3. จากนั้น trail ตาม M1 pivot ตามหลังราคา  
4. ปิดเมื่อชน SL ที่ล็อกแล้ว / trail / หรือสัญญาณออก

## ไฟล์หลัก
- `subsystems/execution/mt5_router.py` — place / modify / close ผ่าน `asyncio.to_thread`
- `subsystems/execution/position_guard.py` — เฝ้าโพซิชัน + equity

## Events (ZeroMQ)
Topic จริง: **`exec.trade`** (`TOPIC_EXECUTION`)

สถานะที่ dashboard รับได้ เช่น:
- `PLACED` — เปิดไม้  
- `MODIFIED_BE` — ล็อก BE+2  
- `CLOSED` — ปิดไม้ (PnL)

## ความสัมพันธ์กับ Portfolio UI
ประวัติปิดไม้บนแท็บ Portfolio มาจาก **MT5 deal history** (`/api/portfolio`)  
ไม่พึ่งเฉพาะ DuckDB `trade_logs` ของบอท — จึงเห็นไม้ที่เทรดในเทอร์มินัลด้วย (รวมไม้ที่ไม่ได้มาจากบอท)
