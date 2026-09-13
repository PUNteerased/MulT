# Research Agent — LM Studio + DuckDuckGo (zero-cost)

Human-gated research subsystem. **Never auto-writes** `settings` / `symbols.yaml` / model weights.

## Modules

| Module | Entry | Citations required? |
|--------|--------|---------------------|
| Calculation Auditor | `python -m subsystems.research.run_auditor` | No — rules are source of truth |
| News & Macro Digest | `python -m subsystems.research.run_news_digest` | Yes → else `needs_review` |
| Strategy Literature Scanner | `python -m subsystems.research.run_strategy_scanner` | Yes → else `needs_review` |
| All (prune + 3 modules) | `python -m subsystems.research.run_all --force` | — |

## Zero-cost constraint

- Default LLM = **LM Studio** `qwen/qwen3-8b` @ `http://127.0.0.1:1234/v1`
- Dashboard **Settings → Research LLM** can switch to any OpenAI-compatible endpoint (runtime only — see [settings.md](settings.md))
- Web search = **duckduckgo-search** (retry/backoff; fail → empty report, never recycle stale news)
- Research Agent **never** auto-writes system settings

## Quality gate

```text
check_quality(..., require_citations=True|False)
```

- News / Strategy: `require_citations=True` — 0 citations or empty findings → `needs_review`
- Auditor: `require_citations=False` — status from rule checklist (failed rules → `needs_review`)

## Status workflow

`needs_review` | `proposed` → `approved` | `rejected` → (manual backtest) `backtested`

Dashboard: **Research** tab → Approve / Reject.  
API: `POST /api/research/reports/{id}/status` — store only, no config write.

## Off-hours scheduler

`main.py` `_research_agent_loop` hourly when weekend **or** `HALT_TRADING`.

GPU / enable gate:

1. `RESEARCH_AGENT_ENABLED=0` → skip entirely
2. `nvidia-smi` util ≥ `RESEARCH_GPU_SKIP_PCT` (default **40**) → skip
3. No nvidia-smi → skip GPU check only (still honor kill-switch)

## Retention

`prune_reports(max_age_days=90, reject_max_age_days=30)` archives to `data/research_reports/archive/`.

## Human apply audit

After approve + backtest, when you manually copy values into config:

```bash
python -m subsystems.research.log_apply RES_XXXXXXXX --files config/settings.py --note "atr k1 tweak"
# or mark backtested:
python -m subsystems.research.log_apply RES_XXXXXXXX --backtest data/validation_reports/backtest_....json
```

Git commit message **must** include: `research_report_id=RES_XXXXXXXX`  
Or a comment in config: `# applied from RES_XXXXXXXX`

## LM Studio setup

| Setting | Value |
|---------|--------|
| Model | `qwen/qwen3-8b` |
| Server | `http://127.0.0.1:1234` |

Unload Chronos / CNN before heavy research runs if VRAM is tight.
