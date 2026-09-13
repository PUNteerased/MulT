/** Shared types for Deep-Sniper live dashboard */

export type Tone = 'cyan' | 'green' | 'violet' | 'amber' | 'rose'

export interface AccountSnapshot {
  balance: number
  equity: number
  margin_free: number
  floating_pnl: number
  currency: string
  login: number | string
  server: string
  connected: boolean
  active_positions: PositionLive[]
  active_positions_count: number
}

export interface PositionLive {
  ticket: number
  symbol: string
  type: 'BUY' | 'SELL' | string
  volume: number
  price_open: number
  price_current: number
  sl: number
  tp: number
  profit: number
  magic?: number
  comment?: string
}

export interface HardwareSnapshot {
  vram_used_mb: number
  vram_total_mb: number
  vram_free_mb: number
  vram_percent: number
  vram_warning: boolean
  cpu_percent: number
  ram_percent: number
  disk_free_gb: number
  gpu?: {
    name: string
    available: boolean
    vram_used_mb: number
    vram_total_mb: number
    vram_percent: number
    vram_warning: boolean
    threshold_mb: number
  }
  cpu?: { percent: number; logical_cores: number; model: string }
  ram?: { used_gb: number; total_gb: number; percent: number }
  disk?: { free_gb: number; total_gb: number; percent: number }
}

export interface KillZoneBounds {
  lower: number
  upper: number
  direction: string
}

export interface KillZoneSymbol {
  current_price: number | null
  current_spread: number | null
  bounds: KillZoneBounds[]
  zones: Array<{
    zone_id: string
    direction: string
    lower_bound: number
    upper_bound: number
    mid_price: number
    confidence: number
    timeframe?: string
    expires_at?: number
  }>
}

export interface AnalyticsReport {
  total_trades: number
  win_rate: number
  win_rate_pct?: number
  profit_factor: number
  net_pnl?: number
  max_drawdown_usd?: number
  expectancy_usd?: number
  current_equity?: number
  current_balance?: number
}

export interface TradeLog {
  ticket_id?: number
  symbol?: string
  direction?: string
  lot?: number
  fill_price?: number
  exit_price?: number
  pnl?: number
  status?: string
  entry_timestamp?: number
  exit_timestamp?: number
  comment?: string
}

export interface StatusResponse {
  status: string
  system_status?: string
  subsystems?: Record<string, string>
  system_state: string
  red_folder?: { is_active: boolean; title?: string }
  symbols?: string[]
  account?: AccountSnapshot
  hardware?: HardwareSnapshot
  timestamp?: number
}

export interface LiveEvent {
  id: string
  time: string
  level: 'INFO' | 'WARN' | 'OK' | 'ERR'
  message: string
}

export interface PortfolioClosedTrade {
  ticket: number | string
  position_id?: number
  symbol: string
  direction: string
  lot: number
  fill_price: number
  exit_price: number
  pnl: number
  entry_time: string
  exit_time: string
  comment?: string
}

export interface PortfolioSnapshot {
  initial_balance: number
  current_balance: number
  current_equity: number
  net_pnl: number
  net_pnl_pct: number
  timezone: string
  equity_curve: number[]
  closed_trades: PortfolioClosedTrade[]
  analytics: AnalyticsReport & { max_drawdown_usd?: number; net_pnl?: number }
  source: string
  server?: string
  login?: number | string
}

export interface ResearchReportRow {
  report_id: string
  status: string
  mode?: string
  created_at?: number
  title?: string
  summary?: string
  path?: string
}

export interface DashboardState {
  connected: boolean
  backendUrl: string
  clock: string
  status: StatusResponse | null
  hardware: HardwareSnapshot | null
  account: AccountSnapshot | null
  killZones: Record<string, KillZoneSymbol>
  analytics: AnalyticsReport | null
  trades: TradeLog[]
  portfolio: PortfolioSnapshot | null
  researchReports: ResearchReportRow[]
  events: LiveEvent[]
  prices: Record<string, number>
  lastHeartbeatMs: number
}
