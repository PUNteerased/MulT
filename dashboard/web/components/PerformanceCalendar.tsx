'use client'

import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { formatUsd } from '@/lib/backend'

export type CalendarTrade = {
  time?: string
  exit_time?: string
  closed_at?: string
  entry_time?: string
  exit_timestamp?: number
  pnl?: number
  profit?: number
  symbol?: string
  direction?: string
  side?: string
}

type DayAgg = {
  key: string
  pnl: number
  trades: number
  wins: number
  losses: number
}

const WEEKDAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'] as const
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function dayKey(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}

/** Parse trade close time → YYYY-MM-DD. */
export function tradeDayKey(t: CalendarTrade): string | null {
  const raw =
    t.exit_time ||
    t.closed_at ||
    t.time ||
    t.entry_time ||
    (t.exit_timestamp
      ? new Date(Number(t.exit_timestamp) * (Number(t.exit_timestamp) > 1e12 ? 1 : 1000)).toISOString()
      : '')
  if (!raw) return null
  const s = String(raw)
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})/)
  if (m) return `${m[1]}-${m[2]}-${m[3]}`
  const d = new Date(s)
  if (!Number.isNaN(d.getTime())) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  }
  return null
}

function tradePnl(t: CalendarTrade): number {
  return Number(t.pnl ?? t.profit ?? 0)
}

function aggregateByDay(trades: CalendarTrade[]): Map<string, DayAgg> {
  const map = new Map<string, DayAgg>()
  for (const t of trades) {
    const key = tradeDayKey(t)
    if (!key) continue
    const pnl = tradePnl(t)
    const cur = map.get(key) || { key, pnl: 0, trades: 0, wins: 0, losses: 0 }
    cur.pnl += pnl
    cur.trades += 1
    if (pnl > 0) cur.wins += 1
    else if (pnl < 0) cur.losses += 1
    map.set(key, cur)
  }
  return map
}

function monthMetrics(trades: CalendarTrade[], monthPrefix: string, initialBalance: number) {
  const monthTrades = trades.filter((t) => {
    const k = tradeDayKey(t)
    return k?.startsWith(monthPrefix)
  })
  const pnls = monthTrades.map(tradePnl)
  const pnl = pnls.reduce((s, v) => s + v, 0)
  const wins = pnls.filter((v) => v > 0)
  const losses = pnls.filter((v) => v < 0)
  const be = pnls.filter((v) => v === 0).length
  const grossWin = wins.reduce((s, v) => s + v, 0)
  const grossLoss = Math.abs(losses.reduce((s, v) => s + v, 0))
  const pf = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99 : 0
  const avgWin = wins.length ? grossWin / wins.length : 0
  const avgLoss = losses.length ? losses.reduce((s, v) => s + v, 0) / losses.length : 0

  const byDay = aggregateByDay(monthTrades)
  const dayList = [...byDay.values()].sort((a, b) => a.key.localeCompare(b.key))
  let peak = 0
  let eq = 0
  let maxDd = 0
  for (const d of dayList) {
    eq += d.pnl
    peak = Math.max(peak, eq)
    maxDd = Math.min(maxDd, eq - peak)
  }
  const pct = (pnl / (initialBalance + 1e-9)) * 100
  const ddPct = (maxDd / (initialBalance + 1e-9)) * 100
  return {
    pnl,
    pct,
    trades: monthTrades.length,
    wins: wins.length,
    losses: losses.length,
    be,
    pf,
    avgWin,
    avgLoss,
    best: pnls.length ? Math.max(...pnls) : 0,
    worst: pnls.length ? Math.min(...pnls) : 0,
    maxDd,
    ddPct,
  }
}

type Cell = {
  inMonth: boolean
  day: number
  key: string
  agg?: DayAgg
}

type Props = {
  trades: CalendarTrade[]
  initialBalance?: number
  onSelectDay?: (dayKey: string | null) => void
  selectedDay?: string | null
}

export function PerformanceCalendar({
  trades,
  initialBalance = 50,
  onSelectDay,
  selectedDay,
}: Props) {
  const now = new Date()
  const [cursor, setCursor] = useState({ y: now.getFullYear(), m: now.getMonth() })
  const [showWeekend, setShowWeekend] = useState(true)
  const [view, setView] = useState<'daily' | 'weekly'>('daily')

  const byDay = useMemo(() => aggregateByDay(trades), [trades])
  const monthPrefix = `${cursor.y}-${pad(cursor.m + 1)}`

  const weeks = useMemo(() => {
    const { y, m } = cursor
    const firstDow = new Date(y, m, 1).getDay()
    const daysInMonth = new Date(y, m + 1, 0).getDate()
    const grid: Cell[] = []

    for (let i = 0; i < firstDow; i++) {
      const d = new Date(y, m, -firstDow + i + 1)
      const key = dayKey(d.getFullYear(), d.getMonth(), d.getDate())
      grid.push({ inMonth: false, day: d.getDate(), key, agg: byDay.get(key) })
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const key = dayKey(y, m, d)
      grid.push({ inMonth: true, day: d, key, agg: byDay.get(key) })
    }
    let next = 1
    while (grid.length % 7 !== 0) {
      const d = new Date(y, m + 1, next++)
      const key = dayKey(d.getFullYear(), d.getMonth(), d.getDate())
      grid.push({ inMonth: false, day: d.getDate(), key, agg: byDay.get(key) })
    }

    const rows: Cell[][] = []
    for (let i = 0; i < grid.length; i += 7) rows.push(grid.slice(i, i + 7))
    return rows
  }, [cursor, byDay])

  const metrics = useMemo(
    () => monthMetrics(trades, monthPrefix, initialBalance),
    [trades, monthPrefix, initialBalance],
  )

  function shiftMonth(delta: number) {
    setCursor((c) => {
      const d = new Date(c.y, c.m + delta, 1)
      return { y: d.getFullYear(), m: d.getMonth() }
    })
  }

  function goToday() {
    const t = new Date()
    setCursor({ y: t.getFullYear(), m: t.getMonth() })
    onSelectDay?.(dayKey(t.getFullYear(), t.getMonth(), t.getDate()))
  }

  const todayKey = dayKey(now.getFullYear(), now.getMonth(), now.getDate())
  const headDays = showWeekend ? [...WEEKDAYS] : ['MON', 'TUE', 'WED', 'THU', 'FRI']

  return (
    <div className="perf-layout">
      <section className="panel perf-calendar">
        <div className="panel-title perf-cal-title">
          <div>
            <p className="eyebrow">PERFORMANCE CALENDAR</p>
            <h2>Daily trade results</h2>
            <p className="muted" style={{ margin: '4px 0 0', fontSize: 11 }}>
              Click a day to filter the journal below.
            </p>
          </div>
          <div className="perf-cal-controls">
            <button type="button" className="icon-button" aria-label="Previous month" onClick={() => shiftMonth(-1)}>
              <ChevronLeft />
            </button>
            <strong className="mono" style={{ minWidth: 140, textAlign: 'center', fontSize: 13 }}>
              {MONTHS[cursor.m]} {cursor.y}
            </strong>
            <button type="button" className="icon-button" aria-label="Next month" onClick={() => shiftMonth(1)}>
              <ChevronRight />
            </button>
            <button type="button" className="subtle-button" style={{ padding: '7px 10px' }} onClick={goToday}>
              Today
            </button>
            <label className="weekend-toggle">
              Weekend
              <button
                type="button"
                className={`toggle-pill ${showWeekend ? 'on' : ''}`}
                onClick={() => setShowWeekend((v) => !v)}
                aria-pressed={showWeekend}
              >
                <i />
                <span>{showWeekend ? 'On' : 'Off'}</span>
              </button>
            </label>
          </div>
        </div>

        <div className={`perf-table ${showWeekend ? 'with-weekend' : 'no-weekend'}`}>
          <div className="perf-row head">
            {headDays.map((d) => (
              <div key={d} className="perf-head">
                {d}
              </div>
            ))}
            <div className="perf-head weekly">WEEKLY</div>
          </div>

          {weeks.map((row, wi) => {
            const visible = showWeekend ? row : row.filter((_, i) => i >= 1 && i <= 5)
            const weekPnl = visible.reduce((s, c) => s + (c.agg?.pnl || 0), 0)
            const weekDays = visible.filter((c) => (c.agg?.trades || 0) > 0).length
            const weekTrades = visible.reduce((s, c) => s + (c.agg?.trades || 0), 0)

            return (
              <div key={`w-${wi}`} className="perf-row">
                {visible.map((c) => {
                  const pnl = c.agg?.pnl ?? 0
                  const n = c.agg?.trades ?? 0
                  const active = selectedDay === c.key
                  if (view === 'weekly') {
                    return (
                      <div
                        key={c.key}
                        className={`perf-cell muted-cell ${c.inMonth ? '' : 'out'} ${c.key === todayKey ? 'today' : ''}`}
                      >
                        <span className="perf-day-num">{c.day}</span>
                      </div>
                    )
                  }
                  return (
                    <button
                      key={c.key}
                      type="button"
                      className={`perf-cell ${c.inMonth ? '' : 'out'} ${n ? (pnl >= 0 ? 'win' : 'loss') : ''} ${
                        c.key === todayKey ? 'today' : ''
                      } ${active ? 'selected' : ''}`}
                      onClick={() => onSelectDay?.(active ? null : c.key)}
                    >
                      <span className="perf-day-num">{c.day}</span>
                      {n > 0 ? (
                        <>
                          <strong className={pnl >= 0 ? 'text-green' : 'text-rose'}>
                            {pnl >= 0 ? '+' : ''}
                            {formatUsd(pnl)}
                          </strong>
                          <small>
                            {n} trade{n === 1 ? '' : 's'}
                          </small>
                        </>
                      ) : (
                        <span className="perf-empty">—</span>
                      )}
                    </button>
                  )
                })}
                <div className={`perf-cell weekly-cell ${weekTrades ? (weekPnl >= 0 ? 'win' : 'loss') : ''}`}>
                  <strong className={weekPnl >= 0 ? 'text-green' : 'text-rose'}>
                    {weekPnl >= 0 ? '+' : ''}
                    {formatUsd(weekPnl)}
                  </strong>
                  <small>
                    {weekDays}d · {weekTrades}t
                  </small>
                </div>
              </div>
            )
          })}
        </div>

        <div className="perf-view-toggle">
          <button type="button" className={view === 'daily' ? 'active' : ''} onClick={() => setView('daily')}>
            Daily View
          </button>
          <button type="button" className={view === 'weekly' ? 'active' : ''} onClick={() => setView('weekly')}>
            Weekly View
          </button>
        </div>
      </section>

      <aside className="perf-metrics">
        <div className="perf-metric-card">
          <span>NET RETURN</span>
          <strong className={metrics.pnl >= 0 ? 'text-green' : 'text-rose'}>
            {metrics.pnl >= 0 ? '+' : ''}
            {formatUsd(metrics.pnl)}
          </strong>
          <small className={metrics.pct >= 0 ? 'text-green' : 'text-rose'}>
            {metrics.pct >= 0 ? '+' : ''}
            {metrics.pct.toFixed(2)}% this month
          </small>
        </div>
        <div className="perf-metric-card">
          <span>W / L / BE</span>
          <strong>
            {metrics.wins} / {metrics.losses} / {metrics.be}
          </strong>
          <div className="perf-wl-bar">
            <i className="win" style={{ width: `${metrics.trades ? (metrics.wins / metrics.trades) * 100 : 0}%` }} />
            <i className="loss" style={{ width: `${metrics.trades ? (metrics.losses / metrics.trades) * 100 : 0}%` }} />
          </div>
          <small>{metrics.trades} trades in month</small>
        </div>
        <div className="perf-metric-card">
          <span>PROFIT FACTOR</span>
          <strong>{metrics.pf >= 99 ? '∞' : metrics.pf.toFixed(2)}</strong>
          <small className={metrics.pf >= 1 ? 'text-green' : 'text-rose'}>
            {metrics.pf >= 1 ? 'Positive edge' : 'Negative edge'}
          </small>
        </div>
        <div className="perf-metric-card">
          <span>AVG WIN</span>
          <strong className="text-green">{formatUsd(metrics.avgWin)}</strong>
          <small>Best {formatUsd(metrics.best)}</small>
        </div>
        <div className="perf-metric-card">
          <span>AVG LOSS</span>
          <strong className="text-rose">{formatUsd(metrics.avgLoss)}</strong>
          <small>Worst {formatUsd(metrics.worst)}</small>
        </div>
        <div className="perf-metric-card">
          <span>MAX DD</span>
          <strong>
            {metrics.ddPct.toFixed(1)}% · {formatUsd(metrics.maxDd)}
          </strong>
          <small className={Math.abs(metrics.ddPct) < 20 ? 'text-green' : 'text-amber'}>
            {Math.abs(metrics.ddPct) < 20 ? 'Safe' : 'Watch'}
          </small>
        </div>
      </aside>
    </div>
  )
}
