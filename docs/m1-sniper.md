# M1 Sniper — จับแพทเทิร์นนาทีบน Kill Zone

## วัตถุประสงค์
เมื่อราคาเข้า Kill Zone ให้ตรวจจับ **liquidity sweep** และจำแนกรูปแบบแท่งเทียน M1 ด้วย deep learning แล้วยิง `trigger_alert` ไปยัง Meta-Labeling

## สถานะการทำงาน
1. **SLEEP** — อยู่นอกโซน  
2. **AWAKE** — ราคาอยู่ใน `[lower, upper]`  
3. **TRIGGER** — ผ่าน sweep + CNN-LSTM → publish alert

## 1) Liquidity Sweep Detector
ไฟล์: `subsystems/m1_sniper/sweep_detector.py`

- หาการแทงทะลุ high/low ระยะสั้นแล้วปิดกลับเข้าโซน ( inducement / stop-run )
- Output เป็นแฟล็ก + เมตาดาต้าทิศทาง

## 2) CNN-LSTM Classifier
ไฟล์: `subsystems/m1_sniper/cnn_lstm_model.py`

- 1D-CNN จับลายท้องถิ่นของลำดับแท่ง  
- LSTM จับลำดับเวลา  
- Output คลาสแพทเทิร์น / ความน่าจะเป็น

## 3) Sniper Worker
ไฟล์: `subsystems/m1_sniper/sniper_worker.py`

- รวมฟีเจอร์จาก Feature Worker + sweep + model score
- Publish `TOPIC_TRIGGER_ALERT`

## Input → Output
| Input | Output |
|-------|--------|
| Kill Zone + M1 bars + features | `TriggerAlert` (symbol, direction, pattern, scores) |

## ข้อจำกัดฮาร์ดแวร์
อินเฟอเรนซ์ควรสั้นและเคลียร์ VRAM หลังจบแบตช์ — แชร์ GPU กับ Chronos
