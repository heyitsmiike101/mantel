import { JSDOM } from 'jsdom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import type { Root } from 'react-dom/client'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api/client'
import { useSettings } from '../../api/hooks'
import type { AppSettings } from '../../api/types'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })
for (const name of ['window', 'document', 'navigator', 'Node', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'KeyboardEvent', 'MouseEvent']) {
  vi.stubGlobal(name, dom.window[name as keyof typeof dom.window])
}
const { createRoot } = await import('react-dom/client')
const { OnScreenKeyboard } = await import('../../components/OnScreenKeyboard')
const { ScreenTab } = await import('./ScreenTab')

afterAll(() => dom.window.close())

let root: Root
let host: HTMLDivElement
let qc: QueryClient

function View() {
  const { data: settings } = useSettings()
  return <>
    <input aria-label="Meal" />
    <ScreenTab />
    <OnScreenKeyboard enabled={settings?.on_screen_keyboard_enabled ?? true} />
  </>
}

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => callback(0))
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData<AppSettings>(['settings'], {
    on_screen_keyboard_enabled: true,
    screensaver_mode: 'auto',
    screensaver_delay_minutes: 5,
    screensaver_seconds_per_photo: 20,
    screensaver_shuffle: true,
    sleep_enabled: false,
    sleep_start_hour: 23,
    sleep_end_hour: 7,
    burn_in_shift: true,
  } as AppSettings)
  vi.spyOn(api, 'get').mockImplementation(async (url) => url === '/photos' ? [] : qc.getQueryData(['settings']) as AppSettings)
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  qc.clear()
  vi.restoreAllMocks()
})

describe('screen keyboard setting', () => {
  it('hides the keyboard before the save completes and persists a boolean setting', async () => {
    let finishSave: ((settings: AppSettings) => void) | undefined
    const patch = vi.spyOn(api, 'patch').mockImplementation(() => new Promise((resolve) => { finishSave = resolve }))
    await act(async () => root.render(<QueryClientProvider client={qc}><View /></QueryClientProvider>))
    const input = host.querySelector('input[aria-label="Meal"]') as HTMLInputElement
    await act(async () => input.focus())
    expect(document.querySelector('.osk')).not.toBeNull()
    await act(async () => (host.querySelector('button[aria-label="On-screen keyboard"]') as HTMLButtonElement).click())
    expect(patch).toHaveBeenCalledWith('/settings', { on_screen_keyboard_enabled: false })
    expect(qc.getQueryData<AppSettings>(['settings'])?.on_screen_keyboard_enabled).toBe(false)
    expect(document.querySelector('.osk')).toBeNull()
    expect(document.activeElement).toBe(input)
    await act(async () => finishSave?.(qc.getQueryData(['settings']) as AppSettings))
    expect(host.querySelector('button[aria-label="On-screen keyboard"]')?.getAttribute('aria-pressed')).toBe('false')
  })
})
