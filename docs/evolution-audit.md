# Evolution & Performance Audit — Self-Learning Survivability

> อัปเดต: 13 กันยายน 2026

## หลักคิด
Optimize **expectancy** (ไม่ใช่ win rate) ภายใต้ constraint ความเสี่ยง  
Champion ไม่ถูกทับจนกว่าจะผ่าน shadow + expectancy gate + human approve

## วงจร

1. **Shadow logging** — `shadow_signals` ใน DuckDB: ทุก gate reject/pass (`meta`, `risk`, `passed`, …)
2. **Feature persistence** — `trade_logs.features_json` จาก alert features ตอนปิดไม้
3. **Weekend learner** — เทรน **challenger** ด้วย purged walk-forward + embargo (debounce 1 ครั้ง/weekend)
4. **Model registry** — `models/registry/lgbm/<version>/` + `champion_pointer.json`
5. **Champion–challenger shadow** — live ใช้ champion; challenger คะแนนคู่ขนานลง shadow
6. **Expectancy gate** — calibration (ECE) + expectancy CI + max DD + Research approve → promote
7. **PSI drift** — เทียบ feature snapshot ตอนเทรน; breach → research `needs_review`
8. **Survivability** — fractional Kelly เป็นเพดาน; peak-DD circuit breaker + `POST /api/halt/reset` (human only)

## API
- `GET /api/halt/status` / `POST /api/halt/reset`
- Research approve บนรายงาน `kind=model_challenger` จะรัน promote hook อัตโนมัติ

## Runtime knobs (`system_runtime`)
- `risk.kelly_fraction`, `risk.max_peak_dd_pct`, `risk.halt_requires_human_reset`
- `evolution.shadow_min_days`, `shadow_min_signals`, `psi_threshold`, `max_dd_worsen_pct`, `once_per_weekend`

## ไฟล์
- `data/shadow_signals` (ใน DuckDB) + `data/shadow_signals.parquet`
- `data/halt_state.json`, `data/last_weekend_evolution.json`
- `models/registry/`, `models/active/`, `models/champion_pointer.json`

## CNN fine-tune
ข้ามจนกว่าจะมี M1 sequence store (`SKIPPED_NO_SEQUENCE_STORE`)

## สองแหล่งสถิติบน Dashboard
| แหล่ง | ความหมาย |
|-------|----------|
| MT5 deals (`/api/portfolio`) | ความจริงบัญชีโบรกเกอร์ |
| DuckDB bot log | ออเดอร์ที่เอนจินบันทึก + shadow สำหรับเรียน |
