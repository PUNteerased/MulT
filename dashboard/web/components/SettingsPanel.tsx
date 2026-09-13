'use client'

import { useEffect, useState, type CSSProperties } from 'react'
import { Settings2 } from 'lucide-react'
import type { LiveDashboardApi } from '@/hooks/useLiveDashboard'
import { apiGet, apiPost } from '@/lib/backend'

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid rgba(148,163,184,.35)',
  background: '#0b1220',
  color: '#e2e8f0',
  fontSize: 13,
}

type SettingsTab = 'llm' | 'meta' | 'sniper' | 'calendar' | 'execution' | 'symbols'

type SystemSettings = {
  llm?: Record<string, unknown>
  meta?: Record<string, unknown>
  sniper?: Record<string, unknown>
  calendar?: Record<string, unknown>
  execution?: Record<string, unknown>
  symbols?: Record<string, Record<string, unknown>>
  updated_at?: number
}

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'llm', label: 'Research LLM' },
  { id: 'meta', label: 'Meta' },
  { id: 'sniper', label: 'Sniper' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'execution', label: 'Execution' },
  { id: 'symbols', label: 'Symbols' },
]

export function SettingsPanel({ live }: { live: LiveDashboardApi }) {
  const [tab, setTab] = useState<SettingsTab>('llm')
  const [data, setData] = useState<SystemSettings | null>(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [apiKeyEdit, setApiKeyEdit] = useState('')

  async function load() {
    if (!live.backendUrl) return
    const res = await apiGet<{ ok?: boolean; settings?: SystemSettings }>(live.backendUrl, '/api/settings')
    if (res?.settings) {
      setData(res.settings)
      setApiKeyEdit('')
    }
  }

  useEffect(() => {
    void load()
  }, [live.backendUrl, live.connected])

  function patchLocal(section: SettingsTab, key: string, value: unknown) {
    setData((prev) => {
      const base = prev || {}
      const sec = { ...((base[section] as Record<string, unknown>) || {}), [key]: value }
      return { ...base, [section]: sec }
    })
  }

  async function saveSection(section: SettingsTab) {
    if (!live.backendUrl || !data?.[section]) {
      setMsg('No backend / section')
      return
    }
    setBusy(true)
    let patch = { ...(data[section] as Record<string, unknown>) }
    if (section === 'llm') {
      if (apiKeyEdit && apiKeyEdit !== '***') patch.api_key = apiKeyEdit
      else delete patch.api_key
    }
    const res = await apiPost<{ ok?: boolean; reason?: string }>(live.backendUrl, `/api/settings/${section}`, patch)
    setBusy(false)
    if (res?.ok) {
      setMsg(`Saved ${section}`)
      await load()
      await live.refresh()
    } else {
      setMsg(`Save failed: ${(res as { reason?: string })?.reason || 'error'}`)
    }
  }

  async function testLlm() {
    if (!live.backendUrl) return
    setBusy(true)
    const res = await apiPost<{ ok?: boolean; reason?: string; detail?: string; models?: string[]; base_url?: string; model?: string }>(
      live.backendUrl,
      '/api/settings/llm/test',
      {},
    )
    setBusy(false)
    if (res?.ok) {
      setMsg(`LLM OK · ${res.detail || res.model || 'reachable'} @ ${res.base_url || ''}`)
    } else {
      setMsg(`LLM test failed: ${res?.detail || res?.reason || 'unreachable'}`)
    }
  }

  const llm = (data?.llm || {}) as Record<string, unknown>
  const meta = (data?.meta || {}) as Record<string, unknown>
  const sniper = (data?.sniper || {}) as Record<string, unknown>
  const calendar = (data?.calendar || {}) as Record<string, unknown>
  const execution = (data?.execution || {}) as Record<string, unknown>
  const symbols = data?.symbols || {}

  return (
    <>
      <header className="topbar">
        <div>
          <p className="eyebrow">SYSTEM · SETTINGS</p>
          <h1>Settings</h1>
        </div>
        <div className="top-actions">
          <span className="live">
            <i /> {live.connected ? 'LIVE SYNC' : 'OFFLINE'}
          </span>
          <span className="muted mono">{live.clock}</span>
          <span className="badge cyan">
            <Settings2 style={{ width: 12, height: 12, display: 'inline' }} /> Runtime
          </span>
        </div>
      </header>

      <section className="mult-summary">
        <div>
          <p className="eyebrow">HUMAN CONFIG ONLY</p>
          <h2>LLM · Meta · Sniper · Calendar · Execution · Symbols</h2>
          <p className="muted">
            Research Agent never auto-writes these. Risk Lab edits risk separately —{' '}
            <button type="button" className="subtle-button" style={{ padding: '2px 8px' }} onClick={() => live.refresh()}>
              refresh status
            </button>
          </p>
        </div>
      </section>

      <div className="settings-tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      <section className="panel">
        {tab === 'llm' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">RESEARCH LLM</p>
                <h2>LM Studio or OpenAI-compatible</h2>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
              {(['lm_studio', 'openai_compatible'] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  className="primary-button"
                  style={{
                    width: 'auto',
                    marginTop: 0,
                    padding: '8px 14px',
                    fontSize: 12,
                    opacity: llm.provider === p ? 1 : 0.55,
                  }}
                  onClick={() => {
                    patchLocal('llm', 'provider', p)
                    if (p === 'lm_studio') {
                      patchLocal('llm', 'base_url', 'http://127.0.0.1:1234/v1')
                      if (!apiKeyEdit) setApiKeyEdit('lm-studio')
                    }
                  }}
                >
                  {p === 'lm_studio' ? 'LM Studio' : 'OpenAI-compatible'}
                </button>
              ))}
            </div>
            <div className="settings-grid">
              <label>
                Base URL
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(llm.base_url ?? '')}
                  onChange={(e) => patchLocal('llm', 'base_url', e.target.value)}
                />
              </label>
              <label>
                Model
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(llm.model ?? '')}
                  onChange={(e) => patchLocal('llm', 'model', e.target.value)}
                />
              </label>
              <label>
                API key {String(llm.api_key) === '***' ? '(masked — leave blank to keep)' : ''}
                <input
                  className="mono"
                  style={inputStyle}
                  value={apiKeyEdit}
                  placeholder={String(llm.api_key ?? '')}
                  onChange={(e) => setApiKeyEdit(e.target.value)}
                />
              </label>
              <label>
                Timeout (s)
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(llm.timeout_s ?? 90)}
                  onChange={(e) => patchLocal('llm', 'timeout_s', Number(e.target.value))}
                />
              </label>
              <label>
                Temperature
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(llm.temperature ?? 0.2)}
                  onChange={(e) => patchLocal('llm', 'temperature', Number(e.target.value))}
                />
              </label>
              <label>
                Max tokens
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(llm.max_tokens ?? 1200)}
                  onChange={(e) => patchLocal('llm', 'max_tokens', Number(e.target.value))}
                />
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={Boolean(llm.enabled ?? true)}
                  onChange={(e) => patchLocal('llm', 'enabled', e.target.checked)}
                />
                Enabled
              </label>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="primary-button"
                style={{ width: 'auto', marginTop: 0, padding: '10px 16px', fontSize: 12 }}
                disabled={busy || !live.backendUrl}
                onClick={() => void saveSection('llm')}
              >
                Save LLM
              </button>
              <button
                type="button"
                className="subtle-button"
                style={{ padding: '10px 16px', fontSize: 12 }}
                disabled={busy || !live.backendUrl}
                onClick={() => void testLlm()}
              >
                Test connection
              </button>
            </div>
          </>
        )}

        {tab === 'meta' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">META LABELING</p>
                <h2>LightGBM win probability gate</h2>
              </div>
            </div>
            <div className="settings-grid" style={{ maxWidth: 280 }}>
              <label>
                Min win probability
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(meta.min_win_probability ?? 0.75)}
                  onChange={(e) => patchLocal('meta', 'min_win_probability', Number(e.target.value))}
                />
              </label>
            </div>
            <button
              type="button"
              className="primary-button"
              style={{ width: 'auto', marginTop: 14, padding: '10px 16px', fontSize: 12 }}
              disabled={busy || !live.backendUrl}
              onClick={() => void saveSection('meta')}
            >
              Save Meta
            </button>
          </>
        )}

        {tab === 'sniper' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">M1 SNIPER</p>
                <h2>Cooldown · lookback · wick ratio</h2>
              </div>
            </div>
            <div className="settings-grid">
              <label>
                Alert cooldown (s)
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(sniper.alert_cooldown_s ?? 45)}
                  onChange={(e) => patchLocal('sniper', 'alert_cooldown_s', Number(e.target.value))}
                />
              </label>
              <label>
                M1 lookback
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(sniper.m1_lookback ?? 60)}
                  onChange={(e) => patchLocal('sniper', 'm1_lookback', Number(e.target.value))}
                />
              </label>
              <label>
                Min bars
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(sniper.min_bars ?? 40)}
                  onChange={(e) => patchLocal('sniper', 'min_bars', Number(e.target.value))}
                />
              </label>
              <label>
                Wick ratio min
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(sniper.wick_ratio_min ?? 0.35)}
                  onChange={(e) => patchLocal('sniper', 'wick_ratio_min', Number(e.target.value))}
                />
              </label>
            </div>
            <button
              type="button"
              className="primary-button"
              style={{ width: 'auto', marginTop: 14, padding: '10px 16px', fontSize: 12 }}
              disabled={busy || !live.backendUrl}
              onClick={() => void saveSection('sniper')}
            >
              Save Sniper
            </button>
          </>
        )}

        {tab === 'calendar' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">MACRO CALENDAR</p>
                <h2>Red-folder blackout windows</h2>
              </div>
            </div>
            <div className="settings-grid">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={Boolean(calendar.enabled ?? true)}
                  onChange={(e) => patchLocal('calendar', 'enabled', e.target.checked)}
                />
                Enabled
              </label>
              <label>
                Blackout before (min)
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(calendar.blackout_before_min ?? 30)}
                  onChange={(e) => patchLocal('calendar', 'blackout_before_min', Number(e.target.value))}
                />
              </label>
              <label>
                Blackout after (min)
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(calendar.blackout_after_min ?? 15)}
                  onChange={(e) => patchLocal('calendar', 'blackout_after_min', Number(e.target.value))}
                />
              </label>
              <label>
                Poll interval (s)
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(calendar.poll_interval_sec ?? 30)}
                  onChange={(e) => patchLocal('calendar', 'poll_interval_sec', Number(e.target.value))}
                />
              </label>
            </div>
            <button
              type="button"
              className="primary-button"
              style={{ width: 'auto', marginTop: 14, padding: '10px 16px', fontSize: 12 }}
              disabled={busy || !live.backendUrl}
              onClick={() => void saveSection('calendar')}
            >
              Save Calendar
            </button>
          </>
        )}

        {tab === 'execution' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">EXECUTION</p>
                <h2>MT5 lot · concurrency</h2>
              </div>
            </div>
            <div className="settings-grid">
              <label>
                Fixed lot size
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(execution.fixed_lot_size ?? 0.01)}
                  onChange={(e) => patchLocal('execution', 'fixed_lot_size', Number(e.target.value))}
                />
              </label>
              <label>
                Max concurrent positions
                <input
                  className="mono"
                  style={inputStyle}
                  value={String(execution.max_concurrent_positions ?? 1)}
                  onChange={(e) => patchLocal('execution', 'max_concurrent_positions', Number(e.target.value))}
                />
              </label>
            </div>
            <button
              type="button"
              className="primary-button"
              style={{ width: 'auto', marginTop: 14, padding: '10px 16px', fontSize: 12 }}
              disabled={busy || !live.backendUrl}
              onClick={() => void saveSection('execution')}
            >
              Save Execution
            </button>
          </>
        )}

        {tab === 'symbols' && (
          <>
            <div className="panel-title">
              <div>
                <p className="eyebrow">SYMBOL OVERLAY</p>
                <h2>ATR knobs (runtime only — not symbols.yaml)</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>ATR k1</th>
                    <th>ATR k2</th>
                    <th>Max spread pts</th>
                    <th>ATR sizing</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(symbols).map(([sym, cfg]) => (
                    <tr key={sym}>
                      <td className="mono">{sym}</td>
                      <td>
                        <input
                          className="mono"
                          style={{ ...inputStyle, minWidth: 70 }}
                          value={String(cfg.atr_k1 ?? '')}
                          onChange={(e) => {
                            setData((prev) => ({
                              ...prev,
                              symbols: {
                                ...(prev?.symbols || {}),
                                [sym]: { ...cfg, atr_k1: Number(e.target.value) },
                              },
                            }))
                          }}
                        />
                      </td>
                      <td>
                        <input
                          className="mono"
                          style={{ ...inputStyle, minWidth: 70 }}
                          value={String(cfg.atr_k2 ?? '')}
                          onChange={(e) => {
                            setData((prev) => ({
                              ...prev,
                              symbols: {
                                ...(prev?.symbols || {}),
                                [sym]: { ...cfg, atr_k2: Number(e.target.value) },
                              },
                            }))
                          }}
                        />
                      </td>
                      <td>
                        <input
                          className="mono"
                          style={{ ...inputStyle, minWidth: 80 }}
                          value={String(cfg.max_spread_points ?? '')}
                          onChange={(e) => {
                            setData((prev) => ({
                              ...prev,
                              symbols: {
                                ...(prev?.symbols || {}),
                                [sym]: { ...cfg, max_spread_points: Number(e.target.value) },
                              },
                            }))
                          }}
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={Boolean(cfg.use_atr_sizing ?? true)}
                          onChange={(e) => {
                            setData((prev) => ({
                              ...prev,
                              symbols: {
                                ...(prev?.symbols || {}),
                                [sym]: { ...cfg, use_atr_sizing: e.target.checked },
                              },
                            }))
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              type="button"
              className="primary-button"
              style={{ width: 'auto', marginTop: 14, padding: '10px 16px', fontSize: 12 }}
              disabled={busy || !live.backendUrl}
              onClick={async () => {
                if (!live.backendUrl || !data?.symbols) return
                setBusy(true)
                const res = await apiPost<{ ok?: boolean; reason?: string }>(live.backendUrl, '/api/settings/symbols', data.symbols)
                setBusy(false)
                setMsg(res?.ok ? 'Saved symbols' : `Save failed: ${res?.reason || 'error'}`)
                if (res?.ok) await load()
              }}
            >
              Save Symbols
            </button>
          </>
        )}

        {msg ? <p className="muted mono" style={{ fontSize: 12, marginTop: 12 }}>{msg}</p> : null}
      </section>
    </>
  )
}
