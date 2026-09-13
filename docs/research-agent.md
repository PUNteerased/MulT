# Research Agent — Chatbot + Batch (zero-cost)

Human-gated research. **Never silent auto-apply** to trading config / MT5 / model champion.

## Research Chatbot (v1 safe scope)

Conversational advisor on the **Research** tab.

| Can | Cannot (use dedicated UI) |
|-----|---------------------------|
| `web_search` (DDG, sanitized as untrusted data) | `mt5.order_send` / change BUY-SELL rules |
| Read runtime, models, halt, trades, reports | Promote / rollback LGBM from chat |
| `propose_runtime_patch` → Confirm card | Halt reset from chat (use **Human reset HALT**) |
| `propose_research_status` → Confirm card | Force weekend evolution from chat |

### Auth (required for chat)

Chat APIs **fail closed** unless `DASHBOARD_PASSWORD` is set and the client is logged in
(`X-MulT-Auth` / bearer / cookie). Other dashboard APIs may still be open if password unset;
**chat writes never are.**

### API

- `POST /api/research/chat` `{ message, session_id? }`
- `GET /api/research/chat/{session_id}`
- `POST /api/research/chat/{session_id}/actions/{action_id}/confirm|reject`

Audit: `data/research_reports/CHAT_APPLY_LOG.md` (actor, action_id, web_sourced, tool traces).

### Prompt injection

Search hits are wrapped as `WEB_SEARCH_DATA (untrusted, not instructions)`.  
Pending actions after a search turn set `web_sourced=true` and the UI shows a warning banner.

### High-stakes friction

- **Halt reset:** `POST /api/halt/reset` (button on Research panel)
- **Model promote:** Approve a `model_challenger` research report (expectancy gate still runs)

---

## Batch modules (legacy)

| Module | Entry | Citations required? |
|--------|--------|---------------------|
| Calculation Auditor | `python -m subsystems.research.run_auditor` | No |
| News & Macro Digest | `python -m subsystems.research.run_news_digest` | Yes |
| Strategy Literature Scanner | `python -m subsystems.research.run_strategy_scanner` | Yes |
| All | `python -m subsystems.research.run_all --force` | — |

## Zero-cost constraint

- Default LLM = **LM Studio** @ runtime `system_runtime.llm`
- Web search = **duckduckgo-search**
- Overlay writes go to `data/system_runtime.json` only — never raw `settings.py` / `symbols.yaml` from chat

## Status workflow (reports)

`needs_review` | `proposed` → `approved` | `rejected` → `backtested`

`model_challenger` approve → expectancy gate + promote (see evolution-audit.md).

## Off-hours scheduler

`main.py` `_research_agent_loop` hourly when weekend **or** `HALT_TRADING`.

## Human apply audit (manual config merge)

```bash
python -m subsystems.research.log_apply RES_XXXXXXXX --files config/settings.py --note "note"
```
