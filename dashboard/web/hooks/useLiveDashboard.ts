'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  apiGet,
  formatLocalTime,
  formatClock,
  getStoredBackendUrl,
  resolveBackendUrl,
  setStoredBackendUrl,
  toWsUrl,
} from '@/lib/backend'
import type {
  AccountSnapshot,
  AnalyticsReport,
  DashboardState,
  HardwareSnapshot,
  KillZoneSymbol,
  LiveEvent,
  PortfolioSnapshot,
  ResearchReportRow,
  StatusResponse,
  TradeLog,
} from '@/lib/types'

const TARGET_SYMBOLS = ['EURUSD', 'USDJPY', 'XAUUSD', 'BTCUSD']

function pushEvent(prev: LiveEvent[], message: string, level: LiveEvent['level'] = 'INFO'): LiveEvent[] {
  const next: LiveEvent = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    time: formatLocalTime(),
    level,
    message,
  }
  return [next, ...prev].slice(0, 40)
}

export function useLiveDashboard() {
  const [backendUrl, setBackendUrlState] = useState('')
  const [connected, setConnected] = useState(false)
  const [clock, setClock] = useState(formatClock())
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [hardware, setHardware] = useState<HardwareSnapshot | null>(null)
  const [account, setAccount] = useState<AccountSnapshot | null>(null)
  const [killZones, setKillZones] = useState<Record<string, KillZoneSymbol>>({})
  const [analytics, setAnalytics] = useState<AnalyticsReport | null>(null)
  const [trades, setTrades] = useState<TradeLog[]>([])
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null)
  const [researchReports, setResearchReports] = useState<ResearchReportRow[]>([])
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [lastHeartbeatMs, setLastHeartbeatMs] = useState(0)
  const [configOpen, setConfigOpen] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const setBackendUrl = useCallback((url: string) => {
    const clean = url.trim().replace(/\/$/, '')
    setStoredBackendUrl(clean)
    setBackendUrlState(clean)
  }, [])

  const refreshRest = useCallback(async (base: string) => {
    if (!base) return
    const [st, kz, tr, an, tel, pf, research] = await Promise.all([
      apiGet<StatusResponse>(base, '/api/status'),
      apiGet<Record<string, KillZoneSymbol>>(base, '/api/kill-zones'),
      apiGet<{ trades: TradeLog[] } | TradeLog[]>(base, '/api/trades?limit=50'),
      apiGet<AnalyticsReport>(base, '/api/analytics'),
      apiGet<{ hardware: HardwareSnapshot; account: AccountSnapshot; mt5?: unknown }>(base, '/api/telemetry'),
      apiGet<PortfolioSnapshot>(base, '/api/portfolio?days=180'),
      apiGet<{ reports: ResearchReportRow[] }>(base, '/api/research/reports?limit=20'),
    ])

    if (st) {
      setStatus(st)
      if (st.account) setAccount(st.account)
      if (st.hardware) setHardware(st.hardware)
    }
    if (kz) {
      setKillZones(kz)
      const nextPrices: Record<string, number> = {}
      for (const [sym, row] of Object.entries(kz)) {
        if (row.current_price != null) nextPrices[sym] = row.current_price
      }
      if (Object.keys(nextPrices).length) setPrices((p) => ({ ...p, ...nextPrices }))
    }
    if (tr) {
      const list = Array.isArray(tr) ? tr : tr.trades || []
      setTrades(list)
    }
    if (an) setAnalytics(an)
    if (tel) {
      if (tel.hardware) setHardware(tel.hardware)
      if (tel.account) setAccount(tel.account)
    }
    if (pf) setPortfolio(pf)
    if (research?.reports) setResearchReports(research.reports)
    else setResearchReports([])
  }, [])

  const connectWs = useCallback(
    (base: string) => {
      if (!base) {
        setConfigOpen(true)
        return
      }
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {
          /* ignore */
        }
      }

      const wsUrl = toWsUrl(base)
      let ws: WebSocket
      try {
        ws = new WebSocket(wsUrl)
      } catch {
        setConnected(false)
        setConfigOpen(true)
        return
      }
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectRef.current = 0
        setLastHeartbeatMs(Date.now())
        setEvents((e) => pushEvent(e, `WebSocket connected → ${base}`, 'OK'))
        void refreshRest(base)
      }

      ws.onclose = () => {
        setConnected(false)
        const delay = Math.min(10000, 1000 * 2 ** reconnectRef.current)
        reconnectRef.current += 1
        if (timerRef.current) clearTimeout(timerRef.current)
        timerRef.current = setTimeout(() => connectWs(base), delay)
      }

      ws.onerror = () => {
        setConnected(false)
      }

      ws.onmessage = (ev) => {
        setLastHeartbeatMs(Date.now())
        try {
          const msg = JSON.parse(ev.data)
          const type = msg.type as string

          if (type === 'telemetry') {
            if (msg.hardware) setHardware(msg.hardware)
            if (msg.account) setAccount(msg.account)
            else if (msg.mt5?.account) {
              const raw = msg.mt5.account
              setAccount({
                balance: raw.balance ?? 0,
                equity: raw.equity ?? 0,
                margin_free: raw.margin_free ?? 0,
                floating_pnl: raw.profit ?? 0,
                currency: raw.currency ?? 'USD',
                login: raw.login ?? 0,
                server: raw.server ?? '',
                connected: !!msg.mt5.connected,
                active_positions: msg.mt5.open_positions || [],
                active_positions_count: msg.mt5.open_positions_count || 0,
              })
            }
            if (msg.active_kill_zones) {
              setKillZones((prev) => {
                const next = { ...prev }
                for (const [sym, zones] of Object.entries(msg.active_kill_zones as Record<string, unknown[]>)) {
                  const existing = next[sym] || { current_price: null, current_spread: null, bounds: [], zones: [] }
                  next[sym] = {
                    ...existing,
                    zones: zones as KillZoneSymbol['zones'],
                    bounds: (zones as KillZoneSymbol['zones']).map((z) => ({
                      lower: z.lower_bound,
                      upper: z.upper_bound,
                      direction: z.direction,
                    })),
                  }
                }
                return next
              })
            }
          } else if (type === 'tick' && msg.data) {
            const d = msg.data
            if (d.symbol && d.bid != null) {
              setPrices((p) => ({ ...p, [d.symbol]: d.bid }))
            }
          } else if (type === 'kill_zone' && msg.data) {
            const d = msg.data
            setEvents((e) =>
              pushEvent(e, `Kill Zone ${d.symbol} ${d.direction} conf=${Number(d.confidence || 0).toFixed(2)}`, 'INFO'),
            )
            void refreshRest(base)
          } else if (type === 'trigger_alert' && msg.data) {
            const d = msg.data
            setEvents((e) => pushEvent(e, `Sniper trigger ${d.symbol}: ${d.pattern || d.reason || 'setup'}`, 'WARN'))
          } else if (type === 'trade_ticket' && msg.data) {
            const d = msg.data
            setEvents((e) => pushEvent(e, `Trade ticket ${d.symbol} ${d.direction} lot=${d.lot ?? 0.01}`, 'OK'))
          } else if (type === 'execution' && msg.data) {
            const d = msg.data
            setEvents((e) =>
              pushEvent(
                e,
                `Execution ${d.symbol} [${d.status}] PnL=${Number(d.pnl || 0).toFixed(2)}`,
                d.status === 'CLOSED' ? 'OK' : 'INFO',
              ),
            )
            void refreshRest(base)
          } else if (type === 'system_state' && msg.data) {
            setStatus((s) => ({
              ...(s || { status: 'ok', system_state: 'NORMAL' }),
              system_state: msg.data.state || msg.data.system_state || s?.system_state || 'NORMAL',
            }))
            setEvents((e) => pushEvent(e, `System state → ${msg.data.state || JSON.stringify(msg.data)}`, 'WARN'))
          }
        } catch {
          /* ignore malformed */
        }
      }
    },
    [refreshRest],
  )

  useEffect(() => {
    const initial = resolveBackendUrl()
    setBackendUrlState(initial || getStoredBackendUrl())
    if (!initial) setConfigOpen(true)
    const clockTimer = setInterval(() => setClock(formatClock()), 1000)
    return () => clearInterval(clockTimer)
  }, [])

  useEffect(() => {
    if (!backendUrl) return
    connectWs(backendUrl)
    const poll = setInterval(() => void refreshRest(backendUrl), 15000)
    return () => {
      clearInterval(poll)
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [backendUrl, connectWs, refreshRest])

  // Keepalive ping
  useEffect(() => {
    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'ping' }))
      }
    }, 15000)
    return () => clearInterval(ping)
  }, [])

  const state: DashboardState = useMemo(
    () => ({
      connected,
      backendUrl,
      clock,
      status,
      hardware,
      account,
      killZones,
      analytics,
      trades,
      portfolio,
      researchReports,
      events,
      prices,
      lastHeartbeatMs,
    }),
    [
      connected,
      backendUrl,
      clock,
      status,
      hardware,
      account,
      killZones,
      analytics,
      trades,
      portfolio,
      researchReports,
      events,
      prices,
      lastHeartbeatMs,
    ],
  )

  return {
    ...state,
    symbols: TARGET_SYMBOLS,
    configOpen,
    setConfigOpen,
    setBackendUrl,
    refresh: () => (backendUrl ? refreshRest(backendUrl) : Promise.resolve()),
  }
}

export type LiveDashboardApi = ReturnType<typeof useLiveDashboard>
