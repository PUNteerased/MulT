# M1 Sniper — จับแพทเทิร์นนาทีบน Kill Zone

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
เมื่อราคาเข้า Kill Zone ให้ตรวจจับ **liquidity sweep** และจำแนกรูปแบบแท่งเทียน M1 ด้วย deep learning แล้ว publish `sniper.trigger` ไปยัง Meta-Labeling

## สถานะการทำงาน
1. **SLEEP** — อยู่นอกโซน  
2. **AWAKE** — ราคาอยู่ใน `[lower_bound, upper_bound]`  
3. **TRIGGER** — ผ่าน sweep + CNN-LSTM → publish alert

## 1) Liquidity Sweep Detector
ไฟล์: `subsystems/m1_sniper/sweep_detector.py`

- หาการแทงทะลุ high/low ระยะสั้นแล้วปิดกลับเข้าโซน (stop-run / inducement)
- Output เป็นแฟล็ก + เมตาดาต้าทิศทาง

## 2) CNN-LSTM Classifier
ไฟล์: `subsystems/m1_sniper/cnn_lstm_model.py`

- 1D-CNN จับลายท้องถิ่นของลำดับแท่ง  
- LSTM จับลำดับเวลา  
- Output คลาสแพทเทิร์น / ความน่าจะเป็น  
- เคลียร์ VRAM หลังอินเฟอเรนซ์เมื่อใช้ GPU

## 3) Sniper Worker
ไฟล์: `subsystems/m1_sniper/sniper_worker.py`

- รวมฟีเจอร์จาก Feature Worker + sweep + model score
- Publish topic **`sniper.trigger`**

## Input → Output
| Input | Output |
|-------|--------|
| Kill Zone + M1 bars + features | Trigger alert (symbol, direction, pattern, scores) |

## Dashboard
อีเวนต์ `trigger_alert` โผล่ใน console ของแท็บ MulT และ activity feed (เวลา ICT)
