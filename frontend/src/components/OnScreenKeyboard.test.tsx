import { JSDOM } from 'jsdom'
import { act, useState } from 'react'
import type { Root } from 'react-dom/client'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })
for (const name of ['window', 'document', 'navigator', 'Node', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'KeyboardEvent', 'MouseEvent']) {
  vi.stubGlobal(name, dom.window[name as keyof typeof dom.window])
}
const { createRoot } = await import('react-dom/client')
const { hasNativeKeyboard, isEditable, OnScreenKeyboard } = await import('./OnScreenKeyboard')

afterAll(() => dom.window.close())

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => callback(0))
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

function button(label: string) {
  const found = Array.from(document.querySelectorAll<HTMLButtonElement>('.osk button')).find((item) => item.getAttribute('aria-label') === label)
  if (!found) throw new Error(`Missing keyboard key: ${label}`)
  return found
}

async function press(label: string) {
  await act(async () => button(label).click())
}

function Demo({ multiline = false, enabled = true, onSubmit = () => {}, onSave = () => {} }: {
  multiline?: boolean
  enabled?: boolean
  onSubmit?: (text: string) => void
  onSave?: (text: string) => void
}) {
  const [value, setValue] = useState('hello')
  return <>
    {multiline
      ? <textarea aria-label="Edit" value={value} onChange={(event) => setValue(event.target.value)} onBlur={() => onSave(value)} />
      : <input aria-label="Edit" value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') onSubmit(value) }} onBlur={() => onSave(value)} />}
    <button type="button" aria-label="Outside">Outside</button>
    <OnScreenKeyboard enabled={enabled} />
  </>
}

describe('on-screen keyboard', () => {
  it('updates React-controlled fields at the caret with shift, symbols, space and backspace', async () => {
    await act(async () => root.render(<Demo />))
    const input = host.querySelector('input')!
    await act(async () => input.focus())
    expect(document.querySelector('.osk')).not.toBeNull()
    input.setSelectionRange(1, 4)
    await press('Shift')
    await press('A')
    expect(input.value).toBe('hAo')
    expect(input.selectionStart).toBe(2)
    await press('Space')
    await press('123')
    await press('1')
    expect(input.value).toBe('hA 1o')
    await press('Backspace')
    expect(input.value).toBe('hA o')
    expect(document.activeElement).toBe(input)
  })

  it('invokes input Enter handlers and blur save, then reopens on the same field click', async () => {
    const submit = vi.fn()
    const save = vi.fn()
    await act(async () => root.render(<Demo onSubmit={submit} onSave={save} />))
    const input = host.querySelector('input')!
    await act(async () => input.focus())
    await press('x')
    await press('Enter')
    expect(submit).toHaveBeenCalledWith('hellox')
    expect(save).toHaveBeenCalledWith('hellox')
    expect(document.querySelector('.osk')).toBeNull()
    await act(async () => input.click())
    expect(document.querySelector('.osk')).not.toBeNull()
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    expect(document.querySelector('.osk')).toBeNull()
  })

  it('lets textarea newline insert and Enter close with an onBlur save', async () => {
    const save = vi.fn()
    await act(async () => root.render(<Demo multiline onSave={save} />))
    const textarea = host.querySelector('textarea')!
    await act(async () => textarea.focus())
    textarea.setSelectionRange(textarea.value.length, textarea.value.length)
    await press('New line')
    expect(textarea.value).toBe('hello\n')
    expect(save).not.toHaveBeenCalled()
    await press('Enter')
    expect(save).toHaveBeenCalledWith('hello\n')
    expect(document.querySelector('.osk')).toBeNull()
  })

  it('closes and blurs on outside pointerdown, and excludes nontext and readonly fields', async () => {
    await act(async () => root.render(<Demo />))
    const input = host.querySelector('input')!
    await act(async () => input.focus())
    await act(async () => host.querySelector('button')!.dispatchEvent(new Event('pointerdown', { bubbles: true })))
    expect(document.querySelector('.osk')).toBeNull()
    for (const type of ['checkbox', 'radio', 'date', 'datetime-local', 'file']) {
      const element = document.createElement('input')
      element.type = type
      expect(isEditable(element)).toBe(false)
    }
    input.readOnly = true
    expect(isEditable(input)).toBe(false)
  })

  it('hides immediately when disabled while leaving physical typing and the active field alone', async () => {
    await act(async () => root.render(<Demo />))
    const input = host.querySelector('input')!
    await act(async () => input.focus())
    expect(document.querySelector('.osk')).not.toBeNull()
    await act(async () => root.render(<Demo enabled={false} />))
    expect(document.querySelector('.osk')).toBeNull()
    expect(document.activeElement).toBe(input)
    expect(document.documentElement.style.getPropertyValue('--keyboard-height')).toBe('')
    await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true })))
    expect(document.activeElement).toBe(input)
    await act(async () => input.blur())
    await act(async () => input.focus())
    expect(document.querySelector('.osk')).toBeNull()
    await act(async () => root.render(<Demo enabled />))
    await act(async () => input.click())
    expect(document.querySelector('.osk')).not.toBeNull()
  })

  it('opens for text fields added after mount and skips browser-managed controls', async () => {
    await act(async () => root.render(<Demo />))
    const modal = document.createElement('div')
    modal.innerHTML = '<textarea></textarea><input type="datetime-local"><input type="date">'
    document.body.appendChild(modal)
    try {
      await act(async () => (modal.querySelector('textarea') as HTMLTextAreaElement).focus())
      expect(document.querySelector('.osk')).not.toBeNull()
      await act(async () => (modal.querySelector('input') as HTMLInputElement).focus())
      expect(document.querySelector('.osk')).toBeNull()
    } finally {
      modal.remove()
    }
  })

  it('does not show a second keyboard on native mobile devices', async () => {
    expect(hasNativeKeyboard('Mozilla/5.0 (iPhone)', 'iPhone', 5)).toBe(true)
    expect(hasNativeKeyboard('Mozilla/5.0 (Android)', 'Linux armv8l', 5)).toBe(true)
    expect(hasNativeKeyboard('Mozilla/5.0', 'MacIntel', 5)).toBe(true)
    expect(hasNativeKeyboard('Mozilla/5.0 (X11; Linux armv8l)', 'Linux armv8l', 1)).toBe(false)
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone)')
    await act(async () => root.render(<Demo />))
    await act(async () => host.querySelector('input')!.focus())
    expect(document.querySelector('.osk')).toBeNull()
  })
})
