import { describe, expect, it } from 'vitest'
import { contentSecurityPolicy, isNoindexHost, isProxied, makeNonce, shellFor } from './index'
import { idFromPath } from '../lib/routeId'

describe('tool Worker', () => {
  it('builds the CSP the middleware sent, with the nonce and the shim API origins', () => {
    const csp = contentSecurityPolicy('abc')
    expect(csp.startsWith("default-src 'self'; script-src 'self' 'nonce-abc' 'strict-dynamic'; ")).toBe(true)
    expect(csp).toContain('connect-src \'self\' https://*.domelayer.com https://*.up.railway.app')
    expect(csp).not.toContain('localhost')
    expect(csp).not.toContain('{NONCE}')
  })

  it('makes a fresh 128-bit nonce each time', () => {
    const a = makeNonce()
    expect(atob(a)).toHaveLength(16)
    expect(makeNonce()).not.toBe(a)
  })

  it('serves runs from the prebuilt shell, payloads included', () => {
    expect(shellFor('/runs/wf-2026-0042')).toBe('/runs/_')
    expect(shellFor('/runs/wf-2026-0042.txt')).toBe('/runs/_.txt')
    expect(shellFor('/runs/wf-2026-0042/__next._tree.txt')).toBe('/runs/_/__next._tree.txt')
    expect(shellFor('/runs')).toBeUndefined()
    expect(shellFor('/')).toBeUndefined()
    expect(isProxied('/api/v1/runs')).toBe(false)
  })

  it('reads the id from the URL, and none from the bare shell', () => {
    expect(idFromPath('/runs/wf-2026-0042')).toBe('wf-2026-0042')
    expect(idFromPath('/runs/run%2042')).toBe('run 42')
    expect(idFromPath('/runs/_')).toBe('')
  })

  it('marks every host noindex', () => {
    expect(isNoindexHost('agent-flow.staging.domelayer.com', { DOME_NOINDEX: 'true' } as never)).toBe(true)
    expect(isNoindexHost('dome-agent-flow-staging.x.workers.dev', {} as never)).toBe(true)
  })
})
