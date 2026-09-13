# Macro & Sentiment — ข่าวมหภาคและสภาวะตลาด

## วัตถุประสงค์
ป้องกันการเปิดไม้ช่วงข่าวแรง และให้ context ว่าตลาดอยู่ในโหมดไหน (trend / range / risk-off)

## 1) Economic Calendar / Red Folder
ไฟล์: `subsystems/macro_sentiment/calendar_crawler.py`

- ดึง/จัดตารางอีเวนต์ผลกระทบสูง (แนว ForexFactory)
- **Halt window:** ก่อนข่าว **-30 นาที** ถึงหลังข่าว **+15 นาที**
- เมื่อเข้า window → `system_state = HALT_TRADING`  
  Risk Guard / Execution ต้องไม่เปิดไม้ใหม่

## 2) FinBERT Sentiment
- โมเดล NLP ประเมินโทนข่าวภาษาอังกฤษ (บวก/ลบ/กลาง)
- ใช้เป็นฟีเจอร์ประกอบ ไม่ใช่สัญญาณเข้าออเดอร์เดี่ยวๆ

## 3) Gaussian HMM (4 states)
- จำแนก regime จากอนุกรมผลตอบแทน/ความผันผวน
- ตัวอย่างสถานะ: quiet range, trending, high-vol shock, transition
- POI / Sniper อาจลดความมั่นใจใน regime ที่ไม่เอื้อ

## ลำดับในสายงาน
```
Calendar check → (ถ้า Red Folder: HALT)
              → Sentiment + HMM แนบเข้า feature context
              → POI Radar / Sniper ทำงานต่อเมื่อ NORMAL
```

## Output ที่ระบบอื่นใช้
- `check_red_folder_status()` → `(is_halted, title)`
- Dashboard แสดงแบนเนอร์แดงเมื่อ halt
