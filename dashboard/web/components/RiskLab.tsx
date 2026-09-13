'use client'

import { useEffect, useState, type CSSProperties } from 'react'
import { FlaskConical } from 'lucide-react'
import type { LiveDashboardApi } from '@/hooks/useLiveDashboard'
import { apiPost, formatUsd } from '@/lib/backend'

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid rgba(148,163,184,.35)',
  background: '#0b1220',
  color: '#e2e8f0',
  fontSize: 13,
}

type RiskFields = {
  mode: 'pct' | 'fixed'
  risk_pct: string
  fixed_dollars: string
  floor: string
  ceiling: string
  max_concurrent_positions: string
  fixed_lot_size: string
  max_spread_risk_pct: string
  streak_half_at: string
  cooldown_at: string
  cooldown_clear_wins: string
  cooldown_hours: string
}

function fromLive(r: Record<string, unknown> | null | undefined): RiskFields {
  const risk = r || {}
  const pct = Number(risk.risk_pct ?? risk.pct ?? 0.005)
  return {
    mode: (risk.mode as 'pct' | 'fixed') || 'pct',
    risk_pct: String((pct * 100).toFixed(2)),
    fixed_dollars: String(risk.fixed_dollars ?? 2.5),
    floor: String(risk.floor ?? 1),
    ceiling: String(risk.ceiling ?? 5),
    max_concurrent_positions: String(risk.max_concurrent_positions ?? 1),
    fixed_lot_size: String(risk.fixed_lot_size ?? 0.01),
    max_spread_risk_pct: String((Number(risk.max_spread_risk_pct ?? 0.2) * 100).toFixed(0)),
    streak_half_at: String(risk.streak_half_at ?? 2),
    cooldown_at: String(risk.cooldown_at ?? 3),
    cooldown_clear_wins: String(risk.cooldown_clear_wins ?? 2),
    cooldown_hours: String(risk.cooldown_hours ?? 4),
  }
}

export function RiskLab({ live }: { live: LiveDashboardApi }) {
  const r = live.status?.risk
  const [f, setF] = useState<RiskFields>(() => fromLive(r as Record<string, unknown> | undefined))
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!r) return
    setF(fromLive(r as Record<string, unknown>))
  }, [r])

  function set<K extends keyof RiskFields>(key: K, value: RiskFields[K]) {
    setF((prev) => ({ ...prev, [key]: value }))
  }

  async function save() {
    if (!live.backendUrl) {
      setMsg('No backend URL')
      return
    }
    setBusy(true)
    const body = {
      mode: f.mode,
      risk_pct: Number(f.risk_pct),
      fixed_dollars: Number(f.fixed_dollars),
      floor: Number(f.floor),
      ceiling: Number(f.ceiling),
      max_concurrent_positions: Number(f.max_concurrent_positions),
      fixed_lot_size: Number(f.fixed_lot_size),
      max_spread_risk_pct: Number(f.max_spread_risk_pct) / 100,
      streak_half_at: Number(f.streak_half_at),
      cooldown_at: Number(f.cooldown_at),
      cooldown_clear_wins: Number(f.cooldown_clear_wins),
      cooldown_hours: Number(f.cooldown_hours),
    }
    const res = await apiPost<{ ok?: boolean; reason?: string; config?: { label?: string; risk_cap_usd?: number } }>(
      live.backendUrl,
      '/api/risk/config',
      body,
    )
    setBusy(false)
    if (res?.ok) {
      setMsg(`Saved · live cap ${formatUsd(res.config?.risk_cap_usd)} (${res.config?.label || f.mode})`)
      await live.refresh()
    } else {
      setMsg(`Save failed: ${res?.reason || 'error'}`)
    }
  }

  const equity = live.account?.equity ?? live.portfolio?.current_equity ?? 50
  const previewPct =
    f.mode === 'fixed'
      ? Number(f.fixed_dollars)
      : Math.min(Number(f.ceiling), Math.max(Number(f.floor), equity * (Number(f.risk_pct) / 100)))

  return (
    <>
      <header className="topbar">
        <div>
          <p className="eyebrow">PROCESS · RISK LAB</p>
          <h1>Risk Lab</h1>
        </div>
        <div className="top-actions">
          <span className="live">
            <i /> {live.connected ? 'LIVE SYNC' : 'OFFLINE'}
          </span>
          <span className="muted mono">{live.clock}</span>
          <span className="badge amber">{r?.label || '0.5% eq'}</span>
        </div>
      </header>

      <section className="mult-summary">
        <div>
          <p className="eyebrow">PRIMARY RISK SURFACE</p>
          <h2>% of equity or fixed $ · streak · concurrency · lot</h2>
          <p className="muted">Changes apply hot via system runtime — no restart required for Risk Guard.</p>
        </div>
        <span className="badge cyan">
          <FlaskConical style={{ width: 12, height: 12, display: 'inline' }} /> Cap preview {formatUsd(previewPct)}
        </span>
      </section>

      <section className="panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">SIZING MODE</p>
            <h2>Risk dollars per trade</h2>
          </div>
          <span className="mono muted">Equity {formatUsd(equity)}</span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, padding: '8px 4px' }}>
          <button
            className="primary-button"
            style={{ padding: '8px 14px', fontSize: 12, width: 'auto', marginTop: 0, opacity: f.mode === 'pct' ? 1 : 0.55 }}
            onClick={() => set('mode', 'pct')}
            type="button"
          >
            % of equity
          </button>
          <button
            className="primary-button"
            style={{ padding: '8px 14px', fontSize: 12, width: 'auto', marginTop: 0, opacity: f.mode === 'fixed' ? 1 : 0.55 }}
            onClick={() => set('mode', 'fixed')}
            type="button"
          >
            Fixed $
          </button>
        </div>

        {f.mode === 'pct' ? (
          <div className="settings-grid">
            <label>
              Risk % per trade
              <input className="mono" style={inputStyle} value={f.risk_pct} onChange={(e) => set('risk_pct', e.target.value)} />
            </label>
            <label>
              Floor $
              <input className="mono" style={inputStyle} value={f.floor} onChange={(e) => set('floor', e.target.value)} />
            </label>
            <label>
              Ceiling $
              <input className="mono" style={inputStyle} value={f.ceiling} onChange={(e) => set('ceiling', e.target.value)} />
            </label>
          </div>
        ) : (
          <div className="settings-grid" style={{ maxWidth: 280 }}>
            <label>
              Fixed $ per trade
              <input className="mono" style={inputStyle} value={f.fixed_dollars} onChange={(e) => set('fixed_dollars', e.target.value)} />
            </label>
          </div>
        )}
      </section>

      <section className="panel" style={{ marginTop: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">GUARDS</p>
            <h2>Concurrency · lot · spread · streak</h2>
          </div>
        </div>
        <div className="settings-grid">
          <label>
            Max concurrent
            <input className="mono" style={inputStyle} value={f.max_concurrent_positions} onChange={(e) => set('max_concurrent_positions', e.target.value)} />
          </label>
          <label>
            Fixed lot size
            <input className="mono" style={inputStyle} value={f.fixed_lot_size} onChange={(e) => set('fixed_lot_size', e.target.value)} />
          </label>
          <label>
            Max spread % of risk
            <input className="mono" style={inputStyle} value={f.max_spread_risk_pct} onChange={(e) => set('max_spread_risk_pct', e.target.value)} />
          </label>
          <label>
            Half size after N losses
            <input className="mono" style={inputStyle} value={f.streak_half_at} onChange={(e) => set('streak_half_at', e.target.value)} />
          </label>
          <label>
            Cooldown after N losses
            <input className="mono" style={inputStyle} value={f.cooldown_at} onChange={(e) => set('cooldown_at', e.target.value)} />
          </label>
          <label>
            Wins to clear cooldown
            <input className="mono" style={inputStyle} value={f.cooldown_clear_wins} onChange={(e) => set('cooldown_clear_wins', e.target.value)} />
          </label>
          <label>
            Cooldown hours
            <input className="mono" style={inputStyle} value={f.cooldown_hours} onChange={(e) => set('cooldown_hours', e.target.value)} />
          </label>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '12px 4px 4px', flexWrap: 'wrap' }}>
          <button
            className="primary-button"
            style={{ padding: '10px 18px', fontSize: 12, width: 'auto', marginTop: 0 }}
            disabled={busy || !live.backendUrl}
            onClick={() => void save()}
            type="button"
          >
            {busy ? 'Saving…' : 'Save Risk Lab'}
          </button>
          <span className="mono" style={{ fontSize: 12 }}>
            Live cap: {formatUsd(r?.risk_cap_usd)}
            {r?.cooldown ? ' · COOLDOWN' : ''}
          </span>
        </div>
        {msg ? <p className="muted" style={{ fontSize: 12, padding: '4px' }}>{msg}</p> : null}
      </section>
    </>
  )
}
