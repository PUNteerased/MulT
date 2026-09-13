# Macro & Sentiment — ข่าวมหภาคและสภาวะตลาด

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
ป้องกันการเปิดไม้ช่วงข่าวแรง และให้ context ว่าตลาดอยู่ในโหมดไหน (trend / range / risk-off)

## 1) Economic Calendar / Red Folder
ไฟล์: `subsystems/macro_sentiment/calendar_crawler.py`

- จัดตารางอีเวนต์ผลกระทบสูง (แนว ForexFactory)
- **Halt window:** ก่อนข่าว **-30 นาที** ถึงหลังข่าว **+15 นาที**
- เมื่อเข้า window → `system_state` / API status เป็น **HALT_TRADING**  
  Risk Guard / Execution ต้องไม่เปิดไม้ใหม่
- Dashboard: แบนเนอร์แดง + `GET /api/calendar`, ฟิลด์ `red_folder` ใน `/api/status`

## 2) FinBERT Sentiment
- โมเดล NLP ประเมินโทนข่าวภาษาอังกฤษ (บวก/ลบ/กลาง)
- ใช้เป็นฟีเจอร์ประกอบ ไม่ใช่สัญญาณเข้าออเดอร์เดี่ยวๆ

## 3) Gaussian HMM (4 states)
- จำแนก regime จากอนุกรมผลตอบแทน/ความผันผวน
- ตัวอย่างสถานะ: quiet range, trending, high-vol shock, transition
- POI / Sniper / Meta อาจลดความมั่นใจใน regime ที่ไม่เอื้อ

## ลำดับในสายงาน
```
Calendar check → (ถ้า Red Folder: HALT → ไม่ส่งออเดอร์)
              → Sentiment + HMM แนบเข้า feature context
              → POI Radar / Sniper ทำงานต่อเมื่อ NORMAL
```

## Output ที่ระบบอื่นใช้
- `check_red_folder_status()` → `(is_halted, title)`
- Publish/สะท้อนผ่าน `system.state` เมื่อมีการเปลี่ยนสถานะระบบ
