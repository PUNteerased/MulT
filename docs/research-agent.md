# Research Agent — Calculation Auditor (free / local only)

Human-gated auditor for money math and ATR config. **Never auto-writes** `settings` or `symbols.yaml`.

## Zero-cost constraint

- No Anthropic / OpenAI cloud billing
- LLM = **LM Studio** on this laptop only
- If LM Studio is offline → **rule-based checklist still runs**

## LM Studio setup (locked)

| Setting | Value |
|---------|--------|
| Model | `qwen/qwen3-8b` |
| Server | `http://127.0.0.1:1234` |
| Client base URL | `http://127.0.0.1:1234/v1` |
| Approx VRAM | ~4.94GB |

Unload Chronos / CNN before running the auditor so the 6GB laptop GPU has headroom.

Env overrides (optional):

```text
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=qwen/qwen3-8b
LLM_API_KEY=lm-studio
```

## Run

```bash
# Weekend / halt only — not on the tick path
python -m subsystems.research.run_auditor

# Force rules-only (no LLM call)
python -m subsystems.research.run_auditor --rules-only
```

Reports land in `data/research_reports/RES_*.json` with `"status": "proposed"`.

## Dashboard

`GET /api/research/reports` lists proposals (status + summary only).  
No apply / write endpoints — human reviews JSON offline.

## Deferred

News Digest, Strategy Scanner, paid search APIs.
