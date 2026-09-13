# POI Radar — Kill Zone และพยากรณ์ควอนไทล์

## วัตถุประสงค์
หา **โซนสภาพคล่อง (Point of Interest)** ที่ราคามีโอกาสถูกดึงกลับมาทดสอบ แล้วประกาศเป็น **Kill Zone** ให้ M1 Sniper “ตื่น” เมื่อราคาเข้ากรอบ

## 1) KDE Liquidity Clusters
ไฟล์: `subsystems/poi_radar/kde_zones.py`

- ใช้ SciPy Kernel Density Estimation บนราคา (เช่น highs/lows / volume nodes)
- จุดหนาแน่นสูง = โซนที่มีออเดอร์รอ / liquidity pool
- สร้างขอบเขต `lower_bound` / `upper_bound` + `confidence`

## 2) Chronos-Bolt Quantile Forecast
ไฟล์: `subsystems/poi_radar/chronos_engine.py`

- พยากรณ์ควอนไทล์ **10% / 50% / 90%** ของราคาข้างหน้า
- ใช้ช่วยยืนยันทิศทางหรือความกว้างของโซน
- รันบน GPU (RTX 4050) แบบ FP16 แล้ว **ปล่อย VRAM ทันที**  
  (`torch.cuda.empty_cache()` + `gc.collect()`) เพื่อไม่ให้เกินเกณฑ์ปลอดภัย ~2.5GB

## 3) Kill Zone Manager
ไฟล์: `subsystems/poi_radar/kill_zone_manager.py`

- รวมผล KDE + Chronos เป็น `KillZoneEvent`
- Publish บน topic `poi.kill_zone`
- มี `expires_at` — โซนหมดอายุแล้ว sniper ไม่ใช้

## Input → Output
| Input | Output |
|-------|--------|
| อนุกรมราคา M15/H1 | clusters + quantile bands |
| รวมผล | `KillZoneEvent` (direction, bounds, confidence) |

## ความสัมพันธ์กับ Sniper
Sniper **นอน** จนกว่า `check_kill_zone_penetration(symbol, price)` จะเป็นจริง
