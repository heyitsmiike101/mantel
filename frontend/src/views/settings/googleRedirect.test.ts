import { describe, expect, it } from 'vitest'
import { googleRedirectProblem, localhostAlternative } from './googleRedirect'

describe('googleRedirectProblem', () => {
  it('accepts loopback over plain http, which is the documented exemption', () => {
    expect(googleRedirectProblem('http://localhost:8080')).toBeNull()
    expect(googleRedirectProblem('http://localhost:8099')).toBeNull()
    expect(googleRedirectProblem('http://127.0.0.1:8080')).toBeNull()
  })

  it('accepts a real domain over https', () => {
    expect(googleRedirectProblem('https://calendar.example.com')).toBeNull()
    expect(googleRedirectProblem('https://pi.tail1234.ts.net')).toBeNull()
  })

  it('rejects a bare LAN hostname — the case that sent people to Google to be refused', () => {
    const problem = googleRedirectProblem('http://debian-docker:8099')
    expect(problem).toContain('public domain')
    expect(problem).toContain('debian-docker')
  })

  it('rejects a LAN IP, which the old docs recommended', () => {
    expect(googleRedirectProblem('http://192.168.1.50:8080')).toContain('IP addresses')
  })

  it('rejects .local and .localhost, which look allowed but are not', () => {
    expect(googleRedirectProblem('http://calendar.local:8080')).toContain('public domain')
    expect(googleRedirectProblem('http://app.localhost:8080')).toContain('public domain')
  })

  it('rejects plain http on a real domain', () => {
    expect(googleRedirectProblem('http://calendar.example.com')).toContain('https://')
  })

  it('explains itself when the value is not a URL at all', () => {
    expect(googleRedirectProblem('debian-docker:8099')).toContain('URL')
    expect(googleRedirectProblem('')).toContain('URL')
  })
})

describe('localhostAlternative', () => {
  it('keeps the port so the suggestion is copy-pasteable', () => {
    expect(localhostAlternative('http://debian-docker:8099')).toBe('http://localhost:8099')
    expect(localhostAlternative('http://192.168.1.50:8080')).toBe('http://localhost:8080')
  })

  it('drops a default port rather than inventing one', () => {
    expect(localhostAlternative('https://calendar.example.com')).toBe('http://localhost')
  })
})
