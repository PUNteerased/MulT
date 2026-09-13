'use client'

import { useEffect, useState } from 'react'
import { LockKeyhole } from 'lucide-react'
import { apiGet, apiPost, getAuthToken, resolveBackendUrl, setAuthToken } from '@/lib/backend'

/**
 * Password gate when backend has DASHBOARD_PASSWORD set.
 * If auth not required, children render immediately.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)
  const [needed, setNeeded] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function check() {
      const base = resolveBackendUrl()
      if (!base) {
        // Vercel without backend yet — still allow UI, banner handles tunnel
        if (!cancelled) {
          setNeeded(false)
          setReady(true)
        }
        return
      }
      const status = await apiGet<{ auth_required?: boolean }>(base, '/api/auth/status')
      if (cancelled) return
      if (!status?.auth_required) {
        setNeeded(false)
        setReady(true)
        return
      }
      if (getAuthToken()) {
        // probe a protected endpoint
        const probe = await apiGet<{ status?: string; auth_required?: boolean }>(base, '/api/status')
        if (probe?.status === 'ok') {
          setNeeded(false)
          setReady(true)
          return
        }
      }
      setNeeded(true)
      setReady(true)
    }
    void check()
    return () => {
      cancelled = true
    }
  }, [])

  async function login() {
    const base = resolveBackendUrl()
    if (!base) {
      setError('Set backend / tunnel URL first')
      return
    }
    setBusy(true)
    setError('')
    const res = await apiPost<{ ok?: boolean; token?: string; reason?: string }>(base, '/api/auth/login', {
      password,
    })
    setBusy(false)
    if (res?.ok && res.token) {
      setAuthToken(res.token)
      setNeeded(false)
      window.location.reload()
      return
    }
    // login endpoint is public — if password wrong
    if (res && (res as { ok?: boolean }).ok === false) {
      setError((res as { reason?: string }).reason || 'Invalid password')
      return
    }
    // Try using raw password as token (middleware accepts either)
    setAuthToken(password)
    const probe = await apiGet<{ status?: string }>(base, '/api/status')
    if (probe?.status === 'ok') {
      setNeeded(false)
      window.location.reload()
      return
    }
    setAuthToken('')
    setError('Invalid password')
  }

  if (!ready) {
    return (
      <div className="auth-gate">
        <p className="muted">Checking access…</p>
      </div>
    )
  }

  if (!needed) return <>{children}</>

  return (
    <div className="auth-gate">
      <div className="auth-card">
        <LockKeyhole />
        <h1>MulT Ops Console</h1>
        <p className="muted">This dashboard is password-protected. Enter the ops password to continue.</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void login()}
          placeholder="Dashboard password"
          autoFocus
        />
        <button type="button" className="primary-button" disabled={busy || !password} onClick={() => void login()}>
          {busy ? 'Unlocking…' : 'Unlock'}
        </button>
        {error ? <p className="text-rose" style={{ fontSize: 12 }}>{error}</p> : null}
      </div>
    </div>
  )
}
