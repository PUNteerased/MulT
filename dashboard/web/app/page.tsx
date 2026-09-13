'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  Cpu,
  Database,
  FileSearch,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  LockKeyhole,
  MemoryStick,
  Network,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Terminal,
  Wallet,
  Wifi,
  Zap,
} from 'lucide-react'
import { useLiveDashboard, type LiveDashboardApi } from '@/hooks/useLiveDashboard'
import {
  apiGet,
  apiPost,
  cumulativeEquity,
  displayRiskCap,
  equityPath,
  formatPrice,
  formatUsd,
  isVercelHost,
} from '@/lib/backend'
import type { PositionLive, Tone } from '@/lib/types'
import { RiskLab } from '@/components/RiskLab'
import { SettingsPanel } from '@/components/SettingsPanel'
import { PerformanceCalendar, tradeDayKey, tradeInRange, type CalendarTrade, type DateRange } from '@/components/PerformanceCalendar'
import { AuthGate } from '@/components/AuthGate'

function VercelTunnelBanner({
  connected,
  backendUrl,
  onSave,
}: {
  connected: boolean
  backendUrl: string
  onSave: (url: string) => void
}) {
  const [value, setValue] = useState(backendUrl)
  const [show, setShow] = useState(false)

  useEffect(() => {
    setShow(isVercelHost() && !connected)
    setValue(backendUrl)
  }, [connected, backendUrl])

  if (!show) return null

  return (
    <div
      style={{
        gridColumn: '1 / -1',
        padding: '10px 14px',
        background: 'rgba(245, 158, 11, 0.12)',
        borderBottom: '1px solid rgba(245, 158, 11, 0.35)',
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        alignItems: 'center',
      }}
    >
      <span style={{ fontSize: 12, color: '#fbbf24', flex: '1 1 220px' }}>
        หน้า Vercel ไม่มี backend — วาง Tunnel URL จากโน้ตบุ๊ก (ngrok) ครั้งเดียว แล้วจำไว้
      </span>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="https://beula-nonintersecting-frigidly.ngrok-free.dev"
        className="mono"
        style={{
          flex: '1 1 240px',
          minWidth: 200,
          padding: '8px 10px',
          borderRadius: 6,
          border: '1px solid rgba(251,191,36,.4)',
          background: '#0b1220',
          color: '#e2e8f0',
          fontSize: 12,
        }}
      />
      <button
        className="primary-button"
        style={{ padding: '8px 14px', fontSize: 12 }}
        onClick={() => onSave(value.trim())}
      >
        Connect
      </button>
    </div>
  )
}

const navGroups = [
  {
    label: 'Overview',
    items: [
      { id: 'overview', label: 'Command', icon: LayoutDashboard },
      { id: 'hardware', label: 'Hardware', icon: Cpu },
    ],
  },
  {
    label: 'Trading',
    items: [
      { id: 'portfolio', label: 'Portfolio', icon: Wallet },
      { id: 'trades', label: 'Trades', icon: Activity },
      { id: 'mult', label: 'Engine', icon: Network },
    ],
  },
  {
    label: 'Process',
    items: [
      { id: 'risklab', label: 'Risk Lab', icon: FlaskConical },
      { id: 'research', label: 'Research', icon: FileSearch },
    ],
  },
  {
    label: 'System',
    items: [{ id: 'settings', label: 'Settings', icon: Settings2 }],
  },
]


function Sparkline({ tone = 'cyan' }: { tone?: string }) {
  const stroke = tone === 'green' ? '#4ade80' : tone === 'rose' ? '#fb7185' : '#67e8f9'
  return (
    <svg className="sparkline" viewBox="0 0 160 42" role="img" aria-label="trend chart">
      <path d="M2 34 C 20 29, 20 31, 35 25 S 54 29, 65 20 S 82 23, 92 14 S 112 20, 122 10 S 145 16, 158 4" fill="none" stroke={stroke} strokeWidth="2" />
      <path d="M2 34 C 20 29, 20 31, 35 25 S 54 29, 65 20 S 82 23, 92 14 S 112 20, 122 10 S 145 16, 158 4 V42 H2Z" fill={stroke} opacity=".08" />
    </svg>
  )
}

function Header({
  title,
  clock,
  connected,
}: {
  title: string
  clock: string
  connected: boolean
}) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">MUL-T / OPERATIONS CONSOLE</p>
        <h1>{title}</h1>
      </div>
      <div className="top-actions">
        <span className="live">
          <i /> {connected ? 'LIVE SYNC' : 'OFFLINE'}
        </span>
        <span className="muted mono">{clock}</span>
        <button className="icon-button" aria-label="Notifications">
          <Bell />
        </button>
        <div className="avatar">DS</div>
      </div>
    </header>
  )
}

function niceAxisTicks(values: number[], count = 4): number[] {
  if (!values.length) return [50, 25, 0]
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [50, 25, 0]
  if (Math.abs(hi - lo) < 1e-9) {
    const pad = Math.max(Math.abs(hi) * 0.05, 1)
    lo -= pad
    hi += pad
  }
  const span = hi - lo
  const raw = span / Math.max(count - 1, 1)
  const pow = Math.pow(10, Math.floor(Math.log10(raw)))
  let step = pow
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * pow >= raw) {
      step = m * pow
      break
    }
  }
  const niceMin = Math.floor(lo / step) * step
  const ticks: number[] = []
  for (let v = niceMin; v <= hi + step * 0.01; v += step) {
    ticks.push(Number(v.toFixed(6)))
    if (ticks.length > 8) break
  }
  return ticks.length ? [...ticks].reverse() : [hi, lo]
}

function EquityChart({
  values,
  stroke = '#67e8f9',
  empty,
}: {
  values: number[]
  stroke?: string
  empty?: boolean
}) {
  if (empty) {
    return (
      <div className="chart-empty">
        <p>ยังไม่มีประวัติ equity ที่มีความหมาย</p>
        <small className="muted">กราฟจะเริ่มหลังเทรดไม้แรก (หรือเมื่อ equity ขยับจาก baseline)</small>
      </div>
    )
  }
  const line = equityPath(values, 720, 260)
  const area = `${line} V260 H0Z`
  const ticks = niceAxisTicks(values, 4)
  return (
    <>
      <div className="chart-wrap">
        <div className="chart-y">
          {ticks.map((t) => (
            <span key={t}>{Number.isInteger(t) ? String(t) : t.toFixed(1)}</span>
          ))}
        </div>
        <svg className="area-chart" viewBox="0 0 720 260" preserveAspectRatio="none" aria-label="Equity curve">
          <defs>
            <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={stroke} stopOpacity=".25" />
              <stop offset="1" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill="url(#fill)" />
          <path d={line} fill="none" stroke={stroke} strokeWidth="3" />
        </svg>
      </div>
      <div className="chart-labels">
        <span>SESSION</span>
        <span>LIVE</span>
      </div>
    </>
  )
}

function meaningfulEquityCurve(values: number[], tradeCount: number): boolean {
  if (!values.length) return false
  if (tradeCount < 1 && values.length <= 3) return false
  const min = Math.min(...values)
  const max = Math.max(...values)
  return max - min >= 0.5
}

function PositionTable({ positions }: { positions: PositionLive[] }) {
  if (!positions.length) {
    return (
      <div className="muted" style={{ padding: '18px 10px', fontSize: 12 }}>
        No open MT5 positions — Risk Guard allows max 1 × 0.01 lot.
      </div>
    )
  }
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Size</th>
            <th>Entry</th>
            <th>Mark</th>
            <th>SL</th>
            <th>Unrealized P/L</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const tone: Tone = p.profit >= 0 ? 'green' : 'rose'
            const side = p.type === 'BUY' || p.type === 0 ? 'LONG' : 'SHORT'
            return (
              <tr key={p.ticket}>
                <td>
                  <strong>{p.symbol}</strong>
                  <small>#{p.ticket}</small>
                </td>
                <td>
                  <span className={`badge ${side === 'LONG' ? 'green' : 'rose'}`}>{side}</span>
                </td>
                <td className="mono">{Number(p.volume).toFixed(2)}</td>
                <td className="mono">{formatPrice(p.symbol, p.price_open)}</td>
                <td className="mono">{formatPrice(p.symbol, p.price_current)}</td>
                <td className="mono">{formatPrice(p.symbol, p.sl)}</td>
                <td className={`mono text-${tone}`}>
                  {p.profit >= 0 ? '+' : ''}
                  {formatUsd(p.profit)}
                </td>
                <td>
                  <span className="status-pill">
                    <i className="dot green" /> Open
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Overview({ live, onOpenRiskLab }: { live: LiveDashboardApi; onOpenRiskLab?: () => void }) {
  const pf = live.portfolio
  const equity = pf?.current_equity ?? live.account?.equity ?? live.status?.risk?.equity ?? 50
  const balance = pf?.current_balance ?? live.account?.balance ?? 50
  const initial = pf?.initial_balance ?? 50
  const pnl = pf?.net_pnl ?? equity - initial
  const pnlPct = pf?.net_pnl_pct ?? (pnl / (initial + 1e-9)) * 100
  const positions = live.account?.active_positions || []
  const tradeCount = live.trades.length || pf?.closed_trades?.length || 0
  const curve = useMemo(
    () => (pf?.equity_curve?.length ? pf.equity_curve : cumulativeEquity(live.trades, initial)),
    [pf, live.trades, initial],
  )
  const showCurve = meaningfulEquityCurve(curve, tradeCount)
  const riskCap = displayRiskCap({ risk: live.status?.risk, equity })

  const rawState = live.status?.system_state
  const state = !live.connected
    ? 'OFFLINE'
    : rawState && rawState !== 'NORMAL'
      ? rawState
      : live.account?.connected === false
        ? 'DEGRADED'
        : rawState || 'NORMAL'
  const subsystems = live.status?.subsystems || {
    data_ingestion: live.connected && live.account?.connected ? 'ONLINE' : 'OFFLINE',
    poi_radar: live.connected && live.account?.connected ? 'ONLINE' : 'OFFLINE',
    risk_guard: live.status?.risk?.cooldown ? 'COOLDOWN' : 'ONLINE',
    execution: live.account?.connected ? 'ONLINE' : 'OFFLINE',
  }

  const cards = [
    {
      label: 'System state',
      value: state,
      note: !live.connected
        ? 'Backend / tunnel offline'
        : state === 'DEGRADED'
          ? 'Core services degraded'
          : state === 'OFFLINE'
            ? 'MT5 / pipeline offline'
            : live.connected
              ? 'Gateway linked'
              : 'Waiting for tunnel',
      icon: Server,
      tone: state === 'HALT_TRADING' || state === 'OFFLINE' ? 'rose' : state === 'DEGRADED' ? 'amber' : 'cyan',
    },
    {
      label: 'Portfolio equity',
      value: formatUsd(equity),
      note: `${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}% vs initial ${formatUsd(initial)}`,
      icon: Wallet,
      tone: pnl >= 0 ? 'green' : 'rose',
    },
    {
      label: 'Active positions',
      value: String(positions.length).padStart(2, '0'),
      note: `Balance ${formatUsd(balance)}`,
      icon: Activity,
      tone: 'violet',
    },
    {
      label: 'Risk guard',
      value: live.status?.risk?.cooldown ? 'COOLDOWN' : 'ARMED',
      note: live.status?.risk?.cooldown
        ? `Armed ${formatUsd(riskCap)} · entries blocked`
        : `Max ${formatUsd(riskCap)} · ${live.status?.risk?.label || `${(((live.status?.risk?.risk_pct ?? live.status?.risk?.pct ?? 0.005) * 100)).toFixed(2)}% eq`} · floor ${formatUsd(live.status?.risk?.floor ?? 1)}–${formatUsd(live.status?.risk?.ceiling ?? 5)}`,
      icon: ShieldCheck,
      tone: live.status?.risk?.cooldown ? 'rose' : 'amber',
    },
  ] as const

  return (
    <>
      <Header title="Command overview" clock={live.clock} connected={live.connected} />
      {live.status?.red_folder?.is_active && (
        <div className="panel" style={{ borderColor: 'rgba(251,113,133,.45)', marginBottom: 15, color: '#fda4af' }}>
          RED FOLDER HALT — {live.status.red_folder.title || 'High-impact news window'}
        </div>
      )}
      <section className="metric-grid">
        {cards.map((item) => {
          const Icon = item.icon
          return (
            <article className={`metric-card ${item.tone}`} key={item.label}>
              <div className="metric-head">
                <span>{item.label}</span>
                <Icon />
              </div>
              <strong>{item.value}</strong>
              <div className="metric-note">{item.note}</div>
              <Sparkline tone={item.tone === 'green' ? 'green' : item.tone === 'rose' ? 'rose' : 'cyan'} />
            </article>
          )
        })}
      </section>
      <div className="content-grid overview-grid">
        <section className="panel large-panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">REAL-TIME EQUITY</p>
              <h2>Account performance</h2>
            </div>
            <span className={`badge ${pnl >= 0 ? 'green' : 'rose'}`}>
              {pnl >= 0 ? '+' : ''}
              {pnlPct.toFixed(2)}%
            </span>
          </div>
          <EquityChart values={curve} stroke={pnl >= 0 ? '#4ade80' : '#fb7185'} empty={!showCurve} />
        </section>
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">SERVICE HEALTH</p>
              <h2>Runtime status</h2>
            </div>
            <RefreshCw className="spin-soft" />
          </div>
          <div className="service-list">
            {[
              ['MT5 account feed', live.account?.connected ? 'Connected' : 'Offline', live.account?.connected ? 'green' : 'rose', Wifi],
              ['MulT orchestrator', live.connected ? 'Streaming' : 'Disconnected', live.connected ? 'cyan' : 'rose', Zap],
              ['DuckDB AI journal', `${live.trades.length} AI trades`, 'green', Database],
              ['ZeroMQ bridge', live.connected ? 'Subscribed' : 'Idle', live.connected ? 'violet' : 'amber', Network],
              ['Risk guard', live.status?.risk?.cooldown ? 'COOLDOWN' : `Armed ${formatUsd(riskCap)}`, live.status?.risk?.cooldown ? 'rose' : 'amber', LockKeyhole],
            ].map(([name, status, tone, Icon]) => (
              <div className="service-row" key={name as string}>
                <Icon />
                <span>{name as string}</span>
                <strong className={`text-${tone}`}>{status as string}</strong>
                <i className={`dot ${tone}`} />
              </div>
            ))}
          </div>
          <div className="detail-grid" style={{ marginTop: 14 }}>
            {Object.entries(subsystems)
              .slice(0, 4)
              .map(([k, v]) => (
                <div key={k}>
                  <span>{k}</span>
                  <strong>{v}</strong>
                </div>
              ))}
          </div>
        </section>
      </div>
      <section className="panel" style={{ marginTop: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">RISK GUARD</p>
            <h2>Live sizing summary</h2>
          </div>
          <span className="badge amber">{live.status?.risk?.label || '0.5% eq'}</span>
        </div>
        <div className="detail-grid">
          <div>
            <span>Live cap</span>
            <strong>{formatUsd(riskCap)}</strong>
          </div>
          <div>
            <span>Mode</span>
            <strong className="mono">{live.status?.risk?.mode || 'pct'}</strong>
          </div>
          <div>
            <span>Cooldown</span>
            <strong>{live.status?.risk?.cooldown ? 'ACTIVE' : 'Clear'}</strong>
          </div>
          <div>
            <span>Editor</span>
            <strong>
              <button
                type="button"
                className="subtle-button"
                style={{ padding: '4px 8px' }}
                onClick={() => onOpenRiskLab?.()}
              >
                Open Risk Lab →
              </button>
            </strong>
          </div>
        </div>
      </section>
      <section className="panel table-panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">OPEN EXPOSURE</p>
            <h2>Active positions</h2>
          </div>
        </div>
        <PositionTable positions={positions} />
      </section>
    </>
  )
}

function Hardware({ live }: { live: LiveDashboardApi }) {
  const hw = live.hardware
  const cpu = hw?.cpu_percent ?? hw?.cpu?.percent ?? 0
  const ramPct = hw?.ram_percent ?? hw?.ram?.percent ?? 0
  const ramUsed = hw?.ram?.used_gb ?? 0
  const ramTotal = hw?.ram?.total_gb ?? 32
  const vramUsed = hw?.vram_used_mb ?? hw?.gpu?.vram_used_mb ?? 0
  const vramTotal = hw?.vram_total_mb ?? hw?.gpu?.vram_total_mb ?? 6144
  const vramPct = hw?.vram_percent ?? hw?.gpu?.vram_percent ?? 0
  const diskFree = hw?.disk_free_gb ?? hw?.disk?.free_gb ?? 0
  const hb = live.lastHeartbeatMs ? ((Date.now() - live.lastHeartbeatMs) / 1000).toFixed(1) : '—'

  return (
    <>
      <Header title="Computer telemetry" clock={live.clock} connected={live.connected} />
      <div className="hardware-head">
        <div>
          <p className="subheading">
            <i className={`dot ${live.connected ? 'green' : 'rose'}`} /> ACER NITRO V 16 · {live.connected ? 'ONLINE' : 'OFFLINE'}
          </p>
          <p className="muted">
            {hw?.cpu?.model || 'AMD Ryzen 7 8845HS'} · Last heartbeat {hb}s ago
          </p>
        </div>
        <span className={`badge ${hw?.vram_warning || hw?.gpu?.vram_warning ? 'amber' : 'cyan'}`}>
          {hw?.vram_warning || hw?.gpu?.vram_warning ? 'VRAM WARNING >2.5GB' : 'MONITORING LIVE METRICS'}
        </span>
      </div>
      <section className="metric-grid hardware-metrics">
        {[
          ['CPU load', `${cpu.toFixed(1)}%`, hw?.cpu?.model || 'AMD Ryzen 7 8845HS', `${Math.min(cpu, 100).toFixed(0)}%`, Cpu, 'cyan'],
          [
            'Memory usage',
            `${ramUsed.toFixed(1)} / ${ramTotal.toFixed(1)} GB`,
            `${ramPct.toFixed(1)}% allocated`,
            `${Math.min(ramPct, 100).toFixed(0)}%`,
            MemoryStick,
            ramPct > 90 ? 'rose' : 'green',
          ],
          [
            'GPU device',
            hw?.gpu?.available ? 'ACTIVE' : 'N/A',
            hw?.gpu?.name || 'RTX 4050 Laptop GPU',
            `${Math.min(vramPct, 100).toFixed(0)}%`,
            Gauge,
            'violet',
          ],
          [
            'VRAM allocation',
            `${vramUsed.toFixed(0)} / ${vramTotal.toFixed(0)} MB`,
            `${vramPct.toFixed(1)}% · threshold 2500 MB`,
            `${Math.min(vramPct, 100).toFixed(0)}%`,
            Zap,
            vramUsed >= 2500 ? 'amber' : 'cyan',
          ],
        ].map(([label, value, note, progress, Icon, tone]) => (
          <article className={`panel telemetry-card ${tone}`} key={label as string}>
            <div className="metric-head">
              <span>{label as string}</span>
              <Icon />
            </div>
            <strong>{value as string}</strong>
            <p className="muted">{note as string}</p>
            <div className="progress">
              <i style={{ width: progress as string }} />
            </div>
            <small>{progress as string} of capacity</small>
          </article>
        ))}
      </section>
      <div className="content-grid hardware-grid">
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">PIPELINE TELEMETRY</p>
              <h2>Data movement</h2>
            </div>
            <Activity className="text-cyan" />
          </div>
          <div className="data-bars">
            {[
              ['WebSocket link', live.connected ? 'OPEN' : 'CLOSED', live.connected ? '90%' : '5%'],
              ['Kill zones cached', `${Object.keys(live.killZones).length} symbols`, '40%'],
              ['Disk free (NVMe)', `${diskFree.toFixed(1)} GB`, `${Math.min(100, diskFree / 5).toFixed(0)}%`],
              ['Event feed', `${live.events.length} events`, `${Math.min(live.events.length * 5, 100)}%`],
            ].map(([name, value, width]) => (
              <div className="data-bar" key={name}>
                <div>
                  <span>{name}</span>
                  <strong className="mono">{value}</strong>
                </div>
                <div className="progress">
                  <i style={{ width }} />
                </div>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">CORE DETAILS</p>
              <h2>Runtime envelope</h2>
            </div>
            <Terminal />
          </div>
          <div className="detail-grid">
            {[
              ['OS', 'Windows 11'],
              ['GPU', hw?.gpu?.name || 'RTX 4050 6GB'],
              ['CPU cores', String(hw?.cpu?.logical_cores ?? 16)],
              ['MT5 server', String(live.account?.server || '—')],
              ['Account', String(live.account?.login || '—')],
              ['Backend', live.backendUrl || 'not set'],
            ].map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}

function tradeSource(t: CalendarTrade): 'ai' | 'legacy' {
  if (t.source === 'ai' || t.source === 'legacy') return t.source
  if (Number(t.magic) === 20250913 || String(t.comment || '').startsWith('DS_')) return 'ai'
  return 'legacy'
}

function TradesPanel({ live }: { live: LiveDashboardApi }) {
  const closed = (live.portfolio?.closed_trades || live.trades || []) as CalendarTrade[]
  const open = live.account?.active_positions || []
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const [selectedRange, setSelectedRange] = useState<DateRange | null>(null)
  const [sourceFilter, setSourceFilter] = useState<'all' | 'ai' | 'legacy'>('all')
  const initial = live.portfolio?.initial_balance ?? 50
  const counts = live.portfolio?.trade_counts || {
    all: closed.length,
    ai: closed.filter((t) => tradeSource(t) === 'ai').length,
    legacy: closed.filter((t) => tradeSource(t) === 'legacy').length,
  }

  const bySource =
    sourceFilter === 'all' ? closed : closed.filter((t) => tradeSource(t) === sourceFilter)

  const filtered = selectedDay
    ? bySource.filter((t) => tradeDayKey(t) === selectedDay)
    : selectedRange
      ? bySource.filter((t) => tradeInRange(t, selectedRange))
      : bySource

  const journalTitle = selectedDay
    ? `Trades on ${selectedDay}`
    : selectedRange
      ? `${selectedRange.label} · ${selectedRange.start} → ${selectedRange.end}`
      : sourceFilter === 'ai'
        ? 'AI system trades'
        : sourceFilter === 'legacy'
          ? 'Legacy (manual) MT5 trades'
          : 'Closed / logged trades'

  return (
    <>
      <Header title="Trades" clock={live.clock} connected={live.connected} />
      <section className="panel" style={{ marginBottom: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">DATA SOURCE</p>
            <h2>Separate AI journal from broker history</h2>
            <p className="muted" style={{ margin: '4px 0 0', fontSize: 11 }}>
              DuckDB AI journal: {live.trades.length} · MT5 closed: {counts.all ?? closed.length} (
              {counts.ai ?? 0} AI / {counts.legacy ?? 0} legacy)
            </p>
          </div>
        </div>
        <div className="settings-tabs" style={{ marginBottom: 0 }}>
          {(
            [
              ['all', `All MT5 (${counts.all ?? closed.length})`],
              ['ai', `AI system (${counts.ai ?? 0})`],
              ['legacy', `Legacy manual (${counts.legacy ?? 0})`],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" className={sourceFilter === id ? 'active' : ''} onClick={() => setSourceFilter(id)}>
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="panel table-panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">OPEN</p>
            <h2>Active positions</h2>
          </div>
          <span className="badge cyan">{open.length}</span>
        </div>
        <PositionTable positions={open} />
      </section>

      <div style={{ marginTop: 15 }}>
        <PerformanceCalendar
          trades={bySource}
          initialBalance={initial}
          selectedDay={selectedDay}
          onSelectDay={setSelectedDay}
          selectedRange={selectedRange}
          onSelectRange={setSelectedRange}
        />
      </div>

      <section className="panel table-panel" style={{ marginTop: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">JOURNAL</p>
            <h2>{journalTitle}</h2>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {selectedDay || selectedRange ? (
              <button
                type="button"
                className="subtle-button"
                style={{ padding: '6px 10px' }}
                onClick={() => {
                  setSelectedDay(null)
                  setSelectedRange(null)
                }}
              >
                Clear filter
              </button>
            ) : null}
            <span className="badge green">{filtered.length}</span>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Source</th>
                <th>PnL</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {(filtered.length
                ? filtered.slice(0, 80)
                : [
                    {
                      time: '—',
                      symbol: '—',
                      direction: '—',
                      pnl: 0,
                      comment: selectedDay || selectedRange ? 'No trades in this period' : 'No trades yet',
                      source: 'legacy',
                    },
                  ]
              ).map((t, i) => {
                const src = tradeSource(t as CalendarTrade)
                return (
                  <tr key={String((t as CalendarTrade & { ticket?: string; id?: string }).id || (t as { ticket?: string }).ticket || i)}>
                    <td className="mono">{String(t.time || t.closed_at || t.exit_time || '—')}</td>
                    <td className="mono">{String(t.symbol || '—')}</td>
                    <td>{String(t.direction || t.side || '—')}</td>
                    <td>
                      <span className={`badge ${src === 'ai' ? 'cyan' : 'amber'}`}>
                        {src === 'ai' ? 'AI system' : 'Legacy'}
                      </span>
                    </td>
                    <td className={Number(t.pnl ?? t.profit ?? 0) >= 0 ? 'text-green' : 'text-rose'}>
                      {formatUsd(Number(t.pnl ?? t.profit ?? 0))}
                    </td>
                    <td className="muted">{String(t.comment || '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function Portfolio({ live }: { live: LiveDashboardApi }) {
  const pf = live.portfolio
  const equity = pf?.current_equity ?? live.account?.equity ?? live.status?.risk?.equity ?? 50
  const balance = pf?.current_balance ?? live.account?.balance ?? 50
  const initial = pf?.initial_balance ?? 50
  const pnl = pf?.net_pnl ?? equity - initial
  const pnlPct = pf?.net_pnl_pct ?? (pnl / (initial + 1e-9)) * 100
  const positions = live.account?.active_positions || []
  const tradeCount = live.trades.length || pf?.closed_trades?.length || 0
  const curve = useMemo(
    () => (pf?.equity_curve?.length ? pf.equity_curve : cumulativeEquity(live.trades, initial)),
    [pf, live.trades, initial],
  )
  const showCurve = meaningfulEquityCurve(curve, tradeCount)
  const riskCap = displayRiskCap({ risk: live.status?.risk, equity })
  const wr = pf?.analytics?.win_rate ?? live.analytics?.win_rate ?? live.analytics?.win_rate_pct ?? 0
  const pfFactor = pf?.analytics?.profit_factor ?? live.analytics?.profit_factor ?? 0
  const floating = positions.reduce((s, p) => s + Number(p.profit || 0), 0)
  const closed = pf?.closed_trades || []
  const server = pf?.server || live.account?.server || 'FBS-Demo'
  const login = pf?.login || live.account?.login || '—'

  return (
    <>
      <Header title="Portfolio & risk" clock={live.clock} connected={live.connected} />
      <section className="portfolio-hero">
        <div>
          <p className="eyebrow">
            {server} / LOGIN {login} · INITIAL {formatUsd(initial)} → NOW
          </p>
          <strong>{formatUsd(equity)}</strong>
          <span className={pnl >= 0 ? 'text-green' : 'text-rose'}>
            {pnl >= 0 ? <ArrowUpRight /> : <ArrowDownRight />} {pnl >= 0 ? '+' : ''}
            {formatUsd(pnl)} ({pnlPct >= 0 ? '+' : ''}
            {pnlPct.toFixed(2)}%)
          </span>
        </div>
        <div className="risk-lock">
          <LockKeyhole />
          <div>
            <span>Risk guard</span>
            <strong>
              {live.status?.risk?.cooldown
                ? 'COOLDOWN'
                : live.status?.risk
                  ? `ARMED · ${formatUsd(riskCap)} (${live.status.risk.label || `${((live.status.risk.pct || 0) * 100).toFixed(2)}% EQ`})`
                  : `ARMED · ${formatUsd(riskCap)}`}
            </strong>
          </div>
        </div>
      </section>
      <div className="content-grid portfolio-grid">
        <section className="panel large-panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">EQUITY CURVE</p>
              <h2>From MT5 deal history</h2>
            </div>
            <span className="muted mono">
              WR {Number(wr).toFixed(1)}% · PF {Number(pfFactor).toFixed(2)} · {pf?.timezone || 'Asia/Bangkok'}
            </span>
          </div>
          <EquityChart values={curve} stroke="#4ade80" empty={!showCurve} />
        </section>
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">GUARDRAILS</p>
              <h2>Risk controls</h2>
            </div>
            <ShieldCheck className="text-green" />
          </div>
          <div className="risk-list">
            {[
              ['Initial balance', formatUsd(initial), pf?.source || 'mt5', 'cyan'],
              ['Max risk / trade', `${formatUsd(riskCap)} · ${live.status?.risk?.label || '—'}`, live.status?.risk?.mode === 'fixed' ? 'Fixed dollar mode' : `Floor ${formatUsd(live.status?.risk?.floor ?? 1)} · ceiling ${formatUsd(live.status?.risk?.ceiling ?? 5)}`, 'green'],
              ['Max position size', '0.01 lots', 'Broker minimum', 'cyan'],
              ['Balance', formatUsd(balance), live.account?.currency || 'USD', 'green'],
              ['Floating P/L', formatUsd(floating), `${positions.length} open`, floating >= 0 ? 'green' : 'rose'],
            ].map(([a, b, c, t]) => (
              <div className="risk-item" key={a}>
                <div>
                  <span>{a}</span>
                  <strong className={`text-${t}`}>{b}</strong>
                </div>
                <small>{c}</small>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="panel table-panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">BROKER POSITIONS</p>
            <h2>Exposure ledger</h2>
          </div>
          <span className="badge amber">{formatUsd(Math.abs(floating))} OPEN RISK</span>
        </div>
        <PositionTable positions={positions} />
      </section>
      <section className="panel table-panel" style={{ marginTop: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">CLOSED TRADE HISTORY · ICT</p>
            <h2>MT5 deals ({closed.length})</h2>
          </div>
          <span className="badge cyan">{pf?.source || '—'}</span>
        </div>
        {!closed.length ? (
          <div className="muted" style={{ padding: '18px 10px', fontSize: 12 }}>
            No closed deals in the selected history window.
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Exit (ICT)</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Lots</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {closed.slice(0, 40).map((t) => {
                  const tone = t.pnl >= 0 ? 'green' : 'rose'
                  return (
                    <tr key={`${t.ticket}-${t.exit_time}`}>
                      <td className="mono">{t.exit_time}</td>
                      <td>
                        <strong>{t.symbol}</strong>
                        <small>#{t.ticket}</small>
                      </td>
                      <td>
                        <span className={`badge ${String(t.direction).toUpperCase().includes('BUY') || t.direction === 'LONG' ? 'green' : 'rose'}`}>
                          {t.direction}
                        </span>
                      </td>
                      <td className="mono">{Number(t.lot).toFixed(2)}</td>
                      <td className="mono">{formatPrice(t.symbol, t.fill_price)}</td>
                      <td className="mono">{formatPrice(t.symbol, t.exit_price)}</td>
                      <td className={`mono text-${tone}`}>
                        {t.pnl >= 0 ? '+' : ''}
                        {formatUsd(t.pnl)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

function ResearchPanel({ live }: { live: LiveDashboardApi }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [detail, setDetail] = useState<string>('')
  const [llmLabel, setLlmLabel] = useState('Research LLM')
  const [legacyOpen, setLegacyOpen] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [messages, setMessages] = useState<
    Array<{ role: string; content: string; citations?: Array<{ title?: string; url?: string }> }>
  >([])
  const [pending, setPending] = useState<
    Array<{
      id: string
      type: string
      preview: string
      web_sourced?: boolean
      status?: string
    }>
  >([])
  const [chatError, setChatError] = useState('')
  const [haltBusy, setHaltBusy] = useState(false)

  useEffect(() => {
    if (!live.backendUrl) return
    void apiGet<{ settings?: { llm?: { provider?: string; model?: string; enabled?: boolean } } }>(
      live.backendUrl,
      '/api/settings',
    ).then((s) => {
      const llm = s?.settings?.llm
      if (!llm) return
      const p = llm.provider === 'lm_studio' ? 'LM Studio' : 'OpenAI-compatible'
      setLlmLabel(`${llm.enabled === false ? 'OFF · ' : ''}${p} · ${llm.model || 'model'}`)
    })
  }, [live.backendUrl, live.connected])

  async function setStatus(reportId: string, status: 'approved' | 'rejected') {
    if (!live.backendUrl) return
    setBusy(reportId + status)
    const res = await apiPost<{ ok?: boolean }>(live.backendUrl, `/api/research/reports/${reportId}/status`, {
      status,
      note: `dashboard_${status}`,
    })
    setBusy(null)
    if (res?.ok) {
      setDetail(`${reportId} → ${status}`)
      await live.refresh()
    } else {
      setDetail(`Failed to set ${status} on ${reportId}`)
    }
  }

  async function runModule(module: 'auditor' | 'news' | 'strategy' | 'all') {
    if (!live.backendUrl) return
    setBusy(`run-${module}`)
    const res = await apiPost<{ ok?: boolean; reason?: string }>(live.backendUrl, '/api/research/run', {
      module,
      force: true,
      rules_only: false,
    })
    setBusy(null)
    setDetail(res?.ok ? `Run ${module} ok` : `Run skipped: ${res?.reason || 'error'}`)
    await live.refresh()
  }

  async function sendChat() {
    if (!live.backendUrl || !chatInput.trim() || chatBusy) return
    const text = chatInput.trim()
    setChatInput('')
    setChatBusy(true)
    setChatError('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    const res = await apiPost<{
      ok?: boolean
      reply?: string
      citations?: Array<{ title?: string; url?: string }>
      pending_actions?: Array<{ id: string; type: string; preview: string; web_sourced?: boolean }>
      session_id?: string
      reason?: string
      detail?: { reason?: string }
    }>(live.backendUrl, '/api/research/chat', {
      message: text,
      session_id: sessionId,
    })
    setChatBusy(false)
    if (!res || res.ok === false) {
      const reason =
        (typeof res?.detail === 'object' && res.detail?.reason) ||
        res?.reason ||
        'Chat failed — set DASHBOARD_PASSWORD and login if needed'
      setChatError(String(reason))
      setMessages((m) => [...m, { role: 'assistant', content: `Error: ${reason}` }])
      return
    }
    if (res.session_id) setSessionId(res.session_id)
    setMessages((m) => [
      ...m,
      { role: 'assistant', content: res.reply || '(empty)', citations: res.citations || [] },
    ])
    setPending(res.pending_actions || [])
  }

  async function actOnPending(actionId: string, decision: 'confirm' | 'reject') {
    if (!live.backendUrl || !sessionId) return
    setChatBusy(true)
    const path = `/api/research/chat/${sessionId}/actions/${actionId}/${decision}`
    const res = await apiPost<{
      ok?: boolean
      reason?: string
      session?: { pending_actions?: typeof pending }
      result?: { promotion_result?: unknown }
    }>(live.backendUrl, path, {})
    setChatBusy(false)
    if (!res?.ok) {
      setChatError(res?.reason || `${decision} failed`)
      return
    }
    setPending(res.session?.pending_actions || [])
    setMessages((m) => [
      ...m,
      {
        role: 'system',
        content: decision === 'confirm' ? `Confirmed ${actionId}` : `Rejected ${actionId}`,
      },
    ])
    if (decision === 'confirm') await live.refresh()
  }

  async function resetHalt() {
    if (!live.backendUrl) return
    setHaltBusy(true)
    const res = await apiPost<{ ok?: boolean }>(live.backendUrl, '/api/halt/reset', {
      note: 'dashboard_research_panel',
    })
    setHaltBusy(false)
    setDetail(res?.ok ? 'Halt reset OK' : 'Halt reset failed')
  }

  return (
    <>
      <Header title="Research Chatbot" clock={live.clock} connected={live.connected} />
      <section className="mult-summary">
        <div>
          <p className="eyebrow">CONFIRM CARD · NO AUTO-APPLY · AUTH REQUIRED</p>
          <h2>Advisor chat · web search · runtime proposals</h2>
          <p className="muted">
            Promote / halt reset / evolution stay on dedicated controls — not in chat. High-stakes model
            promote: Approve a <span className="mono">model_challenger</span> report below.
          </p>
        </div>
        <span className="badge amber">
          <FileSearch style={{ width: 12, height: 12, display: 'inline' }} /> {llmLabel}
        </span>
      </section>

      <section className="panel" style={{ marginBottom: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">CHAT</p>
            <h2>Research console</h2>
          </div>
          <span className="badge cyan mono" style={{ fontSize: 9 }}>
            {sessionId || 'new session'}
          </span>
        </div>
        <div className="research-chat-log">
          {!messages.length ? (
            <p className="muted" style={{ fontSize: 12, padding: 12 }}>
              Ask about markets, runtime knobs, or model status. Patches appear as Confirm cards.
            </p>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className={`research-chat-bubble ${msg.role}`}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>
                  {msg.role.toUpperCase()}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.45 }}>{msg.content}</div>
                {msg.citations?.length ? (
                  <ul className="research-chat-cites">
                    {msg.citations.map((c, j) => (
                      <li key={j}>
                        <a href={c.url} target="_blank" rel="noreferrer">
                          {c.title || c.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))
          )}
        </div>
        {pending.map((a) => (
          <div key={a.id} className="research-action-card">
            {a.web_sourced ? (
              <p className="badge amber" style={{ marginBottom: 8 }}>
                ข้อเสนอนี้อ้างอิงข้อมูลจากเว็บ — ตรวจก่อน Confirm
              </p>
            ) : null}
            <p className="eyebrow">{a.type}</p>
            <pre className="mono" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: '6px 0 10px' }}>
              {a.preview}
            </pre>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="primary-button"
                style={{ padding: '6px 12px', fontSize: 12 }}
                disabled={chatBusy}
                onClick={() => actOnPending(a.id, 'confirm')}
              >
                Confirm
              </button>
              <button
                style={{ padding: '6px 12px', fontSize: 12 }}
                disabled={chatBusy}
                onClick={() => actOnPending(a.id, 'reject')}
              >
                Reject
              </button>
            </div>
          </div>
        ))}
        <div className="research-chat-compose">
          <textarea
            className="research-chat-input"
            value={chatInput}
            disabled={chatBusy || !live.backendUrl}
            placeholder="พิมพ์ข้อความ… (Enter ส่ง · Shift+Enter ขึ้นบรรทัดใหม่) — ใช้ Research LLM / LM Studio จาก Settings"
            rows={4}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void sendChat()
              }
            }}
          />
          <div className="research-chat-compose-bar">
            <span className="muted mono" style={{ fontSize: 11 }}>
              LLM: {llmLabel} · same as Settings → Research LLM / LM Studio
            </span>
            <button
              className="primary-button"
              type="button"
              disabled={chatBusy || !chatInput.trim() || !live.backendUrl}
              onClick={() => void sendChat()}
            >
              {chatBusy ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </div>
        {chatError ? (
          <p className="text-rose mono" style={{ fontSize: 11, marginTop: 8 }}>
            {chatError.includes('404')
              ? `${chatError} — รีสตาร์ท dashboard backend (run_dashboard) แล้วรีเฟรชหน้า`
              : chatError}
          </p>
        ) : null}
      </section>

      <section className="panel" style={{ marginBottom: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">HIGH-STAKES (NOT IN CHAT)</p>
            <h2>Dedicated controls</h2>
          </div>
        </div>
        <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Halt reset and model promote keep higher friction outside the chat flow.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <button
            className="primary-button"
            style={{ padding: '8px 12px', fontSize: 12 }}
            disabled={haltBusy || !live.backendUrl}
            onClick={() => void resetHalt()}
          >
            {haltBusy ? 'Resetting…' : 'Human reset HALT'}
          </button>
          <span className="muted" style={{ fontSize: 11, alignSelf: 'center' }}>
            Model promote: Approve a model_challenger report in the table below (expectancy gate still applies).
          </span>
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 15 }}>
        <div className="panel-title">
          <div>
            <p className="eyebrow">LEGACY BATCH</p>
            <h2>Offline research jobs</h2>
          </div>
          <button
            style={{ padding: '4px 10px', fontSize: 11 }}
            onClick={() => setLegacyOpen((v) => !v)}
          >
            {legacyOpen ? 'Hide' : 'Show'}
          </button>
        </div>
        {legacyOpen ? (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '8px 4px 12px' }}>
              {(['auditor', 'news', 'strategy', 'all'] as const).map((m) => (
                <button
                  key={m}
                  className="primary-button"
                  style={{ padding: '8px 12px', fontSize: 12 }}
                  disabled={!!busy || !live.backendUrl}
                  onClick={() => runModule(m)}
                >
                  {busy === `run-${m}` ? 'Running…' : `Run ${m}`}
                </button>
              ))}
            </div>
            {detail ? (
              <p className="muted mono" style={{ fontSize: 12, padding: '0 4px 8px' }}>
                {detail}
              </p>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="panel table-panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">REPORTS</p>
            <h2>Human gate</h2>
          </div>
          <span className="badge amber">auto_apply=false</span>
        </div>
        {!live.researchReports?.length ? (
          <div className="muted" style={{ padding: '18px 10px', fontSize: 12 }}>
            No reports yet. Expand Legacy batch or{' '}
            <span className="mono text-cyan">python -m subsystems.research.run_all --force</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Module</th>
                  <th>Status</th>
                  <th>Summary</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {live.researchReports.slice(0, 40).map((r) => (
                  <tr key={r.report_id}>
                    <td className="mono">{r.report_id}</td>
                    <td className="mono muted">{(r as { module?: string }).module || r.mode || '—'}</td>
                    <td>
                      <span className="badge amber">{r.status || 'proposed'}</span>
                    </td>
                    <td style={{ fontSize: 12, color: '#e2e8f0' }}>
                      {(r.summary || '').slice(0, 120) || '—'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button
                        className="primary-button"
                        style={{ padding: '4px 8px', fontSize: 11, marginRight: 4 }}
                        disabled={!!busy || r.status === 'approved'}
                        onClick={() => setStatus(r.report_id, 'approved')}
                      >
                        Approve
                      </button>
                      <button
                        style={{ padding: '4px 8px', fontSize: 11 }}
                        disabled={!!busy || r.status === 'rejected'}
                        onClick={() => setStatus(r.report_id, 'rejected')}
                      >
                        Reject
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

function Mult({ live }: { live: LiveDashboardApi }) {
  const [selected, setSelected] = useState('EURUSD')
  const symbols = live.symbols

  const cards = symbols.map((symbol) => {
    const kz = live.killZones[symbol]
    const price = live.prices[symbol] ?? kz?.current_price ?? null
    const zone = kz?.zones?.[0]
    const conf = zone ? Math.round((zone.confidence || 0) * 100) : 0
    const bias = zone ? `${zone.direction} BIAS` : 'WAIT'
    const tone: Tone = !zone ? 'amber' : zone.direction === 'BUY' ? 'green' : zone.direction === 'SELL' ? 'rose' : 'cyan'
    return { symbol, price, conf, bias, tone, zone, kz }
  })

  const pair = cards.find((c) => c.symbol === selected) ?? cards[0]
  const entry =
    pair.zone != null
      ? `${formatPrice(pair.symbol, pair.zone.lower_bound)} — ${formatPrice(pair.symbol, pair.zone.upper_bound)}`
      : 'No active Kill Zone'

  return (
    <>
      <Header title="MulT system engine" clock={live.clock} connected={live.connected} />
      <section className="mult-summary">
        <div>
          <p className="eyebrow">DECISION ENGINE</p>
          <h2>POI Radar · Kill Zones · M1 Sniper</h2>
          <p className="muted">
            Live symbols {symbols.join(' · ')} · state {live.status?.system_state || '—'}
          </p>
        </div>
        <span className={`badge ${live.connected ? 'green' : 'rose'}`}>
          <i className={`dot ${live.connected ? 'green' : 'rose'}`} /> {live.connected ? 'ENGINE LINKED' : 'BACKEND OFFLINE'}
        </span>
      </section>

      <div className="panel pair-analytics">
        <div className="panel-title">
          <div>
            <p className="eyebrow">PAIR-BY-PAIR ANALYSIS</p>
            <h2>Kill Zone intelligence</h2>
          </div>
          <span className="muted mono">LIVE</span>
        </div>
        <div className="pair-tabs" role="tablist">
          {cards.map((item) => (
            <button
              key={item.symbol}
              className={selected === item.symbol ? 'active' : ''}
              onClick={() => setSelected(item.symbol)}
              role="tab"
              aria-selected={selected === item.symbol}
            >
              <strong>{item.symbol}</strong>
              <span className={`text-${item.tone}`}>{item.conf}%</span>
            </button>
          ))}
        </div>
        <div className="pair-analysis-grid">
          <div className="pair-chart-card">
            <div className="pair-chart-head">
              <div>
                <span className="eyebrow">{pair.symbol} / LIVE PRICE</span>
                <strong className="mono">{formatPrice(pair.symbol, pair.price)}</strong>
              </div>
              <span className={`badge ${pair.tone}`}>{pair.bias}</span>
            </div>
            <div className="pair-stat-grid">
              <div>
                <span>POI confidence</span>
                <strong className={`text-${pair.tone}`}>{pair.conf}%</strong>
              </div>
              <div>
                <span>Zones active</span>
                <strong>{pair.kz?.zones?.length || 0}</strong>
              </div>
              <div>
                <span>Entry / Kill Zone</span>
                <strong className="mono">{entry}</strong>
              </div>
              <div>
                <span>Spread</span>
                <strong className="mono">{pair.kz?.current_spread ?? '—'}</strong>
              </div>
              <div>
                <span>Mid price</span>
                <strong className="mono">{pair.zone ? formatPrice(pair.symbol, pair.zone.mid_price) : '—'}</strong>
              </div>
              <div>
                <span>Win gate</span>
                <strong className="text-green">≥ 0.75</strong>
              </div>
            </div>
          </div>
          <div className="pair-reasoning">
            <p className="eyebrow">WHY THIS PAIR</p>
            <h3>{pair.symbol}</h3>
            <p>
              {pair.zone
                ? `Active Kill Zone ${pair.zone.direction} between ${formatPrice(pair.symbol, pair.zone.lower_bound)} and ${formatPrice(pair.symbol, pair.zone.upper_bound)} (confidence ${(pair.zone.confidence || 0).toFixed(2)}). M1 Sniper wakes only inside this band; LightGBM meta-label requires win_probability ≥ 0.75.`
                : 'No active Kill Zone from KDE/Chronos yet. Sniper remains asleep until POI Radar publishes a zone on ZeroMQ.'}
            </p>
            <div className="pair-plan">
              <span>PLAN STATUS</span>
              <strong>{pair.zone ? 'ZONE ARMED · WAITING M1 TRIGGER' : 'SCANNING'}</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="poi-grid">
        {cards.map((c) => (
          <article className="panel poi-card" key={c.symbol}>
            <div>
              <strong>{c.symbol}</strong>
              <span className={`badge ${c.tone}`}>{c.bias}</span>
            </div>
            <strong className="poi-price mono">{formatPrice(c.symbol, c.price)}</strong>
            <div className="poi-score">
              <span>POI confidence</span>
              <strong className={`text-${c.tone}`}>{c.conf}%</strong>
            </div>
            <div className="progress">
              <i className={c.tone} style={{ width: `${c.conf}%` }} />
            </div>
          </article>
        ))}
      </div>

      <div className="content-grid mult-grid">
        <section className="panel trade-plan">
          <div className="panel-title">
            <div>
              <p className="eyebrow">SELECTED / {pair.symbol}</p>
              <h2>Live sniper plan</h2>
            </div>
            <span className={`badge ${pair.zone ? 'green' : 'amber'}`}>{pair.zone ? 'ARMED' : 'IDLE'}</span>
          </div>
          <div className="plan-direction">
            <div>
              <span className={`arrow-circle ${pair.tone === 'rose' ? 'rose' : 'green'}`}>
                {pair.tone === 'rose' ? <ArrowDownRight /> : <ArrowUpRight />}
              </span>
              <div>
                <strong>{pair.zone?.direction || 'FLAT'}</strong>
                <span>Kill Zone driven</span>
              </div>
            </div>
            <strong className="mono">0.01 lots</strong>
          </div>
          <div className="plan-grid">
            {[
              ['Entry zone', entry],
              ['Risk cap', live.status?.risk ? formatUsd(live.status.risk.risk_cap_usd) : '0.5% eq'],
              ['Lot size', '0.01'],
              ['BE trail', '+2 pips @ 1:1.5R'],
              ['Meta gate', 'LGBM ≥ 0.75'],
              ['Trades logged', String(live.analytics?.total_trades ?? live.trades.length)],
            ].map(([a, b]) => (
              <div key={a}>
                <span>{a}</span>
                <strong className="mono">{b}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">SUBSYSTEMS</p>
              <h2>Agent statuses</h2>
            </div>
            <Network />
          </div>
          <div className="agent-list">
            {[
              ['Data ingestion', live.connected ? 'Streaming' : 'Offline', live.connected ? 'green' : 'rose'],
              ['POI Radar / Chronos', Object.values(live.killZones).some((z) => z.zones?.length) ? 'Zones live' : 'Scanning', 'cyan'],
              ['M1 Sniper', 'Armed', 'green'],
              ['Meta-label LightGBM', 'Gate 0.75', 'amber'],
              ['Risk Guard $50', 'Armed', 'violet'],
            ].map(([a, b, t]) => (
              <div className="agent-row" key={a}>
                <span className={`agent-icon ${t}`}>
                  <Activity />
                </span>
                <div>
                  <strong>{a}</strong>
                  <small className={`text-${t}`}>{b}</small>
                </div>
                <i className={`dot ${t}`} />
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel console">
        <div className="panel-title">
          <div>
            <p className="eyebrow">EVENT STREAM</p>
            <h2>MulT console</h2>
          </div>
          <span className="mono muted">LIVE / {live.events.length} EVENTS</span>
        </div>
        <div className="console-body">
          {(live.events.length
            ? live.events
            : [{ id: '0', time: live.clock.slice(0, 8), level: 'INFO' as const, message: 'Waiting for ZeroMQ / telemetry events…' }]
          ).map((ev) => (
            <div className="log-row" key={ev.id}>
              <span className="mono muted">{ev.time}</span>
              <span className={`log-level ${ev.level === 'WARN' || ev.level === 'ERR' ? 'warn' : 'ok'}`}>{ev.level}</span>
              <p>{ev.message}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

export default function Page() {
  const live = useLiveDashboard()
  const [active, setActive] = useState('overview')
  const view =
    active === 'hardware' ? (
      <Hardware live={live} />
    ) : active === 'portfolio' ? (
      <Portfolio live={live} />
    ) : active === 'trades' ? (
      <TradesPanel live={live} />
    ) : active === 'risklab' ? (
      <RiskLab live={live} />
    ) : active === 'research' ? (
      <ResearchPanel live={live} />
    ) : active === 'settings' ? (
      <SettingsPanel live={live} />
    ) : active === 'mult' ? (
      <Mult live={live} />
    ) : (
      <Overview live={live} onOpenRiskLab={() => setActive('risklab')} />
    )

  const zoneCount = Object.values(live.killZones).reduce((n, z) => n + (z.zones?.length || 0), 0)
  const alertCount =
    live.status?.alert_count ??
    live.status?.alerts?.length ??
    (live.status?.red_folder?.is_active ? 1 : 0) +
      (!live.connected || live.account?.connected === false ? 1 : 0)
  const backendHost = (() => {
    try {
      if (!live.backendUrl) return 'no backend'
      const u = new URL(live.backendUrl)
      if (u.hostname.includes('ngrok')) return 'ngrok'
      if (u.hostname === '127.0.0.1' || u.hostname === 'localhost') return 'local'
      return u.hostname
    } catch {
      return 'backend'
    }
  })()

  return (
    <AuthGate>
    <main className="app-shell">
      <VercelTunnelBanner
        connected={live.connected}
        backendUrl={live.backendUrl}
        onSave={(url) => live.setBackendUrl(url)}
      />
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <strong>
              MUL<span>T</span>
            </strong>
            <small>OPS CONSOLE</small>
          </div>
        </div>
        <div className="workspace">
          <span className="status-dot" />
          <div>
            <small>Workspace</small>
            <strong>Deep-Sniper AI</strong>
          </div>
          <ArrowDownRight />
        </div>
        <nav>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-group-label">{group.label}</p>
              {group.items.map(({ id, label, icon: Icon }) => (
                <button key={id} className={active === id ? 'active' : ''} onClick={() => setActive(id)}>
                  <Icon />
                  <span>{label}</span>
                  {id === 'mult' && zoneCount > 0 ? (
                    <b title={`${zoneCount} active kill zone${zoneCount === 1 ? '' : 's'}`}>{zoneCount}</b>
                  ) : null}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="connection">
            <span className="live">
              <i /> {live.connected ? 'Connected' : 'Offline'}
            </span>
            <small>{backendHost}</small>
          </div>
          <button className="sidebar-link" type="button" onClick={() => setActive('settings')} title={(live.status?.alerts || []).map((a) => a.message).join(' · ') || 'No alerts'}>
            <AlertTriangle /> System alerts <b>{alertCount}</b>
          </button>
        </div>
      </aside>
      <div className="main-content">
        {view}
      </div>
    </main>
    </AuthGate>
  )
}
