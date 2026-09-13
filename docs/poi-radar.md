# POI Radar — Kill Zone และพยากรณ์ควอนไทล์

> อัปเดต: 13 กันยายน 2026

## วัตถุประสงค์
หา **โซนสภาพคล่อง (Point of Interest)** ที่ราคามีโอกาสถูกดึงกลับมาทดสอบ แล้วประกาศเป็น **Kill Zone** ให้ M1 Sniper “ตื่น” เมื่อราคาเข้ากรอบ

## 1) KDE Liquidity Clusters
ไฟล์: `subsystems/poi_radar/kde_zones.py`

- SciPy Kernel Density Estimation บนราคา (highs/lows / volume nodes)
- จุดหนาแน่นสูง = liquidity pool
- สร้าง `lower_bound` / `upper_bound` + `confidence`

## 2) Chronos-Bolt Quantile Forecast
ไฟล์: `subsystems/poi_radar/chronos_engine.py`

- พยากรณ์ควอนไทล์ **10% / 50% / 90%**
- รันบน GPU (RTX 4050) แบบ FP16 แล้ว **ปล่อย VRAM ทันที**  
  (`torch.cuda.empty_cache()` + `gc.collect()`)
- เกณฑ์เตือนบน dashboard: VRAM ≥ **2500 MB**

## 3) Kill Zone Manager
ไฟล์: `subsystems/poi_radar/kill_zone_manager.py`

- รวมผล KDE + Chronos เป็น `KillZoneEvent`
- Publish topic **`poi.kill_zone`**
- มี `expires_at` — หมดอายุแล้ว sniper ไม่ใช้

## Input → Output
| Input | Output |
|-------|--------|
| อนุกรมราคา M15/H1 | clusters + quantile bands |
| รวมผล | `KillZoneEvent` → ZMQ + cache |

## Dashboard
- `GET /api/kill-zones` และสตรีม `kill_zone` / telemetry `active_kill_zones`
- แท็บ **MulT system engine** แสดง confidence / bounds ต่อคู่เงิน
