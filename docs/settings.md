# System Settings (runtime config)

Human-editable live config for MulT Ops Console. Stored in `data/system_runtime.json` — **not** rewritten into `config/settings.py` or `config/symbols.yaml`.

## Surfaces

| UI | API | Section |
|----|-----|---------|
| **Risk Lab** | `GET/POST /api/risk/config` (alias) | `risk` |
| **Settings** tabs | `GET/POST /api/settings` · `GET/POST /api/settings/{section}` | `llm`, `meta`, `sniper`, `calendar`, `execution`, `symbols` |
| LLM probe | `POST /api/settings/llm/test` | — |

## Sections

- **risk** — `%` / fixed `$`, floor/ceiling, streak, cooldown, concurrent, lot, spread %
- **llm** — `lm_studio` or `openai_compatible` (URL, model, key, timeout). GET masks `api_key` as `***`
- **meta** — `min_win_probability`
- **sniper** — cooldown, lookback, min bars, wick ratio
- **calendar** — enabled, blackout before/after, poll interval
- **execution** — MT5 `fixed_lot_size`, max concurrent
- **symbols** — per-pair ATR overlay merged at evaluate time

## Safety

- Research Agent proposals **never** auto-apply into this store.
- First boot migrates legacy `data/risk_runtime.json` into the `risk` section once.
- Consumers hot-read via `load_settings()` (Risk Guard, LLM client, Meta, Sniper, Calendar, MT5 lot).

## Dashboard auth (before live account)

Set env on the FastAPI host:

```bat
set DASHBOARD_PASSWORD=your-strong-password
```

Then restart the dashboard. UI shows an unlock gate; API/WebSocket require `X-MulT-Auth` / `?token=`.

Also served: `robots.txt` Disallow + Next metadata `noindex`.

See also [research-agent.md](research-agent.md).
