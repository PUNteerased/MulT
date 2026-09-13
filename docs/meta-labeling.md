# Meta-Labeling — ประตูคัดกรองด้วย LightGBM

## วัตถุประสงค์
แม้ sniper จะเจอแพทเทิร์นแล้ว ก็ยังไม่เปิดไม้ทันที ต้องผ่าน **binary meta-labeler** ที่ประมาณ `win_probability`

## โมเดล
ไฟล์: `subsystems/meta_labeling/lgbm_filter.py`

- LightGBM classifier (CPU — ประหยัด VRAM)
- ฟีเจอร์รวม: เทคนิค M1, บริบท Kill Zone, regime/sentiment (ถ้ามี), คะแนน sniper
- **เกณฑ์ผ่าน:** `win_probability >= 0.75` (`MIN_WIN_PROBABILITY` ใน `config/settings.py`)

## ทำไมต้องมีชั้นนี้
- ลด false positive จากแพทเทิร์นที่ “สวยแต่แพ้บ่อย”
- แยกหน้าที่: sniper หา candidate → meta ตัดสินว่า “ควรเสี่ยงเงินจริงไหม”

## Input → Output
| Input | Output |
|-------|--------|
| Trigger + feature vector | `TradeTicket` (ผ่าน) หรือ reject |

ตั๋วที่ผ่านไปต่อที่ **Risk Guard** เท่านั้น
