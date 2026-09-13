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

export type DateRange = { start: string; end: string; label: string }

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
const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function dayKey(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}

function parseKey(key: string): Date {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function formatRangeLabel(startKey: string, endKey: string): string {
  const a = parseKey(startKey)
  const b = parseKey(endKey)
  return `${SHORT_MONTHS[a.getMonth()]} ${a.getDate()} - ${SHORT_MONTHS[b.getMonth()]} ${b.getDate()}`
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

export function tradeInRange(t: CalendarTrade, range: DateRange | null | undefined): boolean {
  if (!range) return true
  const k = tradeDayKey(t)
  if (!k) return false
  return k >= range.start && k <= range.end
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

function periodMetrics(trades: CalendarTrade[], prefixOrYear: string, initialBalance: number) {
  const filtered = trades.filter((t) => {
    const k = tradeDayKey(t)
    return k?.startsWith(prefixOrYear)
  })
  const pnls = filtered.map(tradePnl)
  const pnl = pnls.reduce((s, v) => s + v, 0)
  const wins = pnls.filter((v) => v > 0)
  const losses = pnls.filter((v) => v < 0)
  const be = pnls.filter((v) => v === 0).length
  const grossWin = wins.reduce((s, v) => s + v, 0)
  const grossLoss = Math.abs(losses.reduce((s, v) => s + v, 0))
  const pf = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99 : 0
  const avgWin = wins.length ? grossWin / wins.length : 0
  const avgLoss = losses.length ? losses.reduce((s, v) => s + v, 0) / losses.length : 0

  const byDay = aggregateByDay(filtered)
  const dayList = [...byDay.values()].sort((a, b) => a.key.localeCompare(b.key))
  let peak = 0
  let eq = 0
  let maxDd = 0
  for (const d of dayList) {
    eq += d.pnl
    peak = Math.max(peak, eq)
    maxDd = Math.min(maxDd, eq - peak)
  }
  return {
    pnl,
    pct: (pnl / (initialBalance + 1e-9)) * 100,
    trades: filtered.length,
    wins: wins.length,
    losses: losses.length,
    be,
    pf,
    avgWin,
    avgLoss,
    best: pnls.length ? Math.max(...pnls) : 0,
    worst: pnls.length ? Math.min(...pnls) : 0,
    maxDd,
    ddPct: (maxDd / (initialBalance + 1e-9)) * 100,
  }
}

/** Sunday–Saturday week cards for a year (WEEK 1 … WEEK 52/53). */
function buildYearWeeks(year: number) {
  const jan1 = new Date(year, 0, 1)
  const start = new Date(year, 0, 1 - jan1.getDay())
  const weeks: Array<{ week: number; start: string; end: string; days: string[] }> = []
  const cursor = new Date(start)
  let week = 1

  while (week <= 54) {
    const days: string[] = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + i)
      days.push(dayKey(d.getFullYear(), d.getMonth(), d.getDate()))
    }
    if (days.some((k) => k.startsWith(String(year)))) {
      weeks.push({ week, start: days[0], end: days[6], days })
      week += 1
    }
    cursor.setDate(cursor.getDate() + 7)
    if (cursor.getFullYear() > year) break
  }
  return weeks
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
  onSelectRange?: (range: DateRange | null) => void
  selectedRange?: DateRange | null
}

export function PerformanceCalendar({
  trades,
  initialBalance = 50,
  onSelectDay,
  selectedDay,
  onSelectRange,
  selectedRange,
}: Props) {
  const now = new Date()
  const [cursor, setCursor] = useState({ y: now.getFullYear(), m: now.getMonth() })
  const [showWeekend, setShowWeekend] = useState(true)
  const [view, setView] = useState<'daily' | 'weekly'>('daily')

  const byDay = useMemo(() => aggregateByDay(trades), [trades])
  const monthPrefix = `${cursor.y}-${pad(cursor.m + 1)}`
  const yearPrefix = String(cursor.y)

  const monthWeeks = useMemo(() => {
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

  const yearWeeks = useMemo(() => {
    return buildYearWeeks(cursor.y).map((w) => {
      const dayKeys = showWeekend ? w.days : w.days.slice(1, 6)
      let pnl = 0
      let tradesN = 0
      let tradeDays = 0
      for (const k of dayKeys) {
        const agg = byDay.get(k)
        if (!agg) continue
        pnl += agg.pnl
        tradesN += agg.trades
        if (agg.trades > 0) tradeDays += 1
      }
      return { ...w, pnl, trades: tradesN, tradeDays, label: formatRangeLabel(w.start, w.end) }
    })
  }, [cursor.y, byDay, showWeekend])

  const metrics = useMemo(
    () => periodMetrics(trades, view === 'weekly' ? yearPrefix : monthPrefix, initialBalance),
    [trades, view, yearPrefix, monthPrefix, initialBalance],
  )

  const yearPnl = useMemo(() => periodMetrics(trades, yearPrefix, initialBalance).pnl, [trades, yearPrefix, initialBalance])

  function shift(delta: number) {
    if (view === 'weekly') {
      setCursor((c) => ({ y: c.y + delta, m: c.m }))
      return
    }
    setCursor((c) => {
      const d = new Date(c.y, c.m + delta, 1)
      return { y: d.getFullYear(), m: d.getMonth() }
    })
  }

  function goToday() {
    const t = new Date()
    setCursor({ y: t.getFullYear(), m: t.getMonth() })
    if (view === 'daily') {
      onSelectRange?.(null)
      onSelectDay?.(dayKey(t.getFullYear(), t.getMonth(), t.getDate()))
    } else {
      onSelectDay?.(null)
      const weeks = buildYearWeeks(t.getFullYear())
      const today = dayKey(t.getFullYear(), t.getMonth(), t.getDate())
      const hit = weeks.find((w) => today >= w.start && today <= w.end)
      if (hit) {
        onSelectRange?.({ start: hit.start, end: hit.end, label: `WEEK ${hit.week}` })
      }
    }
  }

  function switchView(next: 'daily' | 'weekly') {
    setView(next)
    onSelectDay?.(null)
    onSelectRange?.(null)
  }

  const todayKey = dayKey(now.getFullYear(), now.getMonth(), now.getDate())
  const headDays = showWeekend ? [...WEEKDAYS] : ['MON', 'TUE', 'WED', 'THU', 'FRI']

  return (
    <div className="perf-layout">
      <section className="panel perf-calendar">
        <div className="panel-title perf-cal-title">
          <div>
            <p className="eyebrow">PERFORMANCE CALENDAR</p>
            <h2>{view === 'weekly' ? 'Weekly trade results' : 'Daily trade results'}</h2>
            <p className="muted" style={{ margin: '4px 0 0', fontSize: 11 }}>
              {view === 'weekly' ? 'Click a week to filter the journal below.' : 'Click a day to filter the journal below.'}
            </p>
          </div>
          <div className="perf-cal-controls">
            <button type="button" className="icon-button" aria-label="Previous" onClick={() => shift(-1)}>
              <ChevronLeft />
            </button>
            <strong className="mono" style={{ minWidth: view === 'weekly' ? 150 : 140, textAlign: 'center', fontSize: 13 }}>
              {view === 'weekly'
                ? `${cursor.y} (${yearPnl >= 0 ? '+' : ''}${formatUsd(yearPnl)})`
                : `${MONTHS[cursor.m]} ${cursor.y}`}
            </strong>
            <button type="button" className="icon-button" aria-label="Next" onClick={() => shift(1)}>
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

        {view === 'daily' ? (
          <div className={`perf-table ${showWeekend ? 'with-weekend' : 'no-weekend'}`}>
            <div className="perf-row head">
              {headDays.map((d) => (
                <div key={d} className="perf-head">
                  {d}
                </div>
              ))}
              <div className="perf-head weekly">WEEKLY</div>
            </div>

            {monthWeeks.map((row, wi) => {
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
                    return (
                      <button
                        key={c.key}
                        type="button"
                        className={`perf-cell ${c.inMonth ? '' : 'out'} ${n ? (pnl >= 0 ? 'win' : 'loss') : ''} ${
                          c.key === todayKey ? 'today' : ''
                        } ${active ? 'selected' : ''}`}
                        onClick={() => {
                          onSelectRange?.(null)
                          onSelectDay?.(active ? null : c.key)
                        }}
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
        ) : (
          <div className="perf-week-grid">
            {yearWeeks.map((w) => {
              const active = selectedRange?.start === w.start && selectedRange?.end === w.end
              const has = w.trades > 0
              const current =
                todayKey >= w.start && todayKey <= w.end && now.getFullYear() === cursor.y
              return (
                <button
                  key={`${w.week}-${w.start}`}
                  type="button"
                  className={`perf-week-card ${has ? (w.pnl >= 0 ? 'win' : 'loss') : ''} ${active ? 'selected' : ''} ${
                    current ? 'today' : ''
                  }`}
                  onClick={() => {
                    onSelectDay?.(null)
                    onSelectRange?.(
                      active
                        ? null
                        : { start: w.start, end: w.end, label: `WEEK ${w.week}` },
                    )
                  }}
                >
                  <span className="perf-week-title">WEEK {w.week}</span>
                  <span className="perf-week-range">{w.label}</span>
                  {has ? (
                    <>
                      <strong className={w.pnl >= 0 ? 'text-green' : 'text-rose'}>
                        {w.pnl >= 0 ? '+' : ''}
                        {formatUsd(w.pnl)}
                      </strong>
                      <small>
                        {w.tradeDays}d · {w.trades} trade{w.trades === 1 ? '' : 's'}
                      </small>
                    </>
                  ) : (
                    <span className="perf-week-empty">No trades</span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        <div className="perf-view-toggle">
          <button type="button" className={view === 'daily' ? 'active' : ''} onClick={() => switchView('daily')}>
            Daily View
          </button>
          <button type="button" className={view === 'weekly' ? 'active' : ''} onClick={() => switchView('weekly')}>
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
            {metrics.pct.toFixed(2)}% this {view === 'weekly' ? 'year' : 'month'}
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
          <small>
            {metrics.trades} trades in {view === 'weekly' ? 'year' : 'month'}
          </small>
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
