const STORAGE_KEY = 'mulT_backend_url'
const VERCEL_HOST_RE = /vercel\.app$/i

export function getStoredBackendUrl(): string {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setStoredBackendUrl(url: string) {
  if (typeof window === 'undefined') return
  if (!url) {
    localStorage.removeItem(STORAGE_KEY)
    return
  }
  localStorage.setItem(STORAGE_KEY, url.replace(/\/$/, ''))
}

export function isVercelHost(hostname?: string): boolean {
  if (typeof window === 'undefined' && !hostname) return false
  const host = hostname ?? window.location.hostname
  return VERCEL_HOST_RE.test(host)
}

function isBrowserLocalHost(host: string): boolean {
  return host === 'localhost' || host === '127.0.0.1' || host === '[::1]'
}

function cleanUrl(url: string): string {
  return url.trim().replace(/\/$/, '')
}

function backendFromQuery(): string {
  if (typeof window === 'undefined') return ''
  try {
    const q = new URLSearchParams(window.location.search).get('backend')
    return q ? cleanUrl(q) : ''
  } catch {
    return ''
  }
}

/**
 * Resolve API base URL.
 * - Local / ngrok / LAN (UI served by FastAPI): same origin
 * - Vercel static UI: ?backend= → localStorage → NEXT_PUBLIC_BACKEND_URL
 */
export function resolveBackendUrl(explicit?: string): string {
  if (explicit) return cleanUrl(explicit)

  if (typeof window !== 'undefined') {
    const { hostname, origin, port } = window.location

    // Vercel page has no Python API — must use laptop tunnel URL
    if (isVercelHost(hostname)) {
      const fromQuery = backendFromQuery()
      if (fromQuery) {
        setStoredBackendUrl(fromQuery)
        return fromQuery
      }
      const stored = getStoredBackendUrl()
      if (stored) {
        try {
          if (!VERCEL_HOST_RE.test(new URL(stored).hostname)) return stored
        } catch {
          /* ignore bad stored */
        }
      }
      const envUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, '') || ''
      if (envUrl) return envUrl
      return ''
    }

    // Next.js dev on :3000 → API on :8000
    if (isBrowserLocalHost(hostname) && (port === '3000' || port === '3001')) {
      return 'http://127.0.0.1:8000'
    }

    // FastAPI / ngrok / LAN serving this UI
    return origin.replace(/\/$/, '')
  }

  return process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, '') || ''
}

export function toWsUrl(backendUrl: string): string {
  const base =
    backendUrl ||
    (typeof window !== 'undefined' && !isVercelHost()
      ? window.location.origin
      : 'http://127.0.0.1:8000')
  const proto = base.startsWith('https') ? 'wss:' : 'ws:'
  const host = base.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return `${proto}//${host}/ws`
}

export async function apiGet<T>(backendUrl: string, path: string): Promise<T | null> {
  const base = backendUrl || resolveBackendUrl()
  if (!base) return null
  try {
    const res = await fetch(`${base}${path}`, {
      cache: 'no-store',
      headers: {
        // ngrok free interstitial bypass
        'ngrok-skip-browser-warning': 'true',
      },
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

export function formatUsd(n: number | null | undefined, digits = 2): string {
  const v = Number(n ?? 0)
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

export function formatPrice(symbol: string, price: number | null | undefined): string {
  if (price == null || Number.isNaN(price)) return '—'
  if (symbol.includes('JPY')) return price.toFixed(3)
  if (symbol.startsWith('XAU') || symbol.startsWith('BTC')) {
    return price.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  return price.toFixed(5)
}

export function formatPct(n: number | null | undefined, digits = 1): string {
  return `${Number(n ?? 0).toFixed(digits)}%`
}

export function formatClock(ts = Date.now()): string {
  return (
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Bangkok',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(ts)) + ' ICT'
  )
}

export function formatLocalTime(ts = Date.now()): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(ts))
}

/** Build SVG path from equity points (0..1 normalized). */
export function equityPath(values: number[], width = 720, height = 260): string {
  if (!values.length) {
    return `M0 ${height * 0.7} L${width} ${height * 0.7}`
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1e-6)
  const pts = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * width
    const y = height - ((v - min) / span) * (height * 0.75) - height * 0.08
    return `${x.toFixed(1)} ${y.toFixed(1)}`
  })
  return `M${pts.join(' L')}`
}

export function cumulativeEquity(trades: { pnl?: number }[], start = 50): number[] {
  const out = [start]
  let eq = start
  for (const t of [...trades].reverse()) {
    eq += Number(t.pnl ?? 0)
    out.push(Number(eq.toFixed(4)))
  }
  return out.length > 1 ? out : [start, start]
}
