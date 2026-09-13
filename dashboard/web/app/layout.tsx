import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'MulT Ops Console | Deep-Sniper AI',
  description: 'Operational dashboard for computer telemetry, trading risk, and MulT decision intelligence.',
  generator: 'v0.app',
  robots: {
    index: false,
    follow: false,
    googleBot: { index: false, follow: false },
  },
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0d1222',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
