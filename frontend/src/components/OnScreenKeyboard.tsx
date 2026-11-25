import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { keyboardIsUp } from '../hooks/useViewportFit'

type Editable = HTMLInputElement | HTMLTextAreaElement

const letters = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
const symbols = ['1234567890', '@#$%&*()/', '-_+=:;!?']
const inputTypes = new Set(['text', 'search', 'email', 'tel', 'url', 'password', 'number'])

export function isEditable(target: EventTarget | null): target is Editable {
  if (target instanceof HTMLTextAreaElement) return !target.disabled && !target.readOnly
  return target instanceof HTMLInputElement && !target.disabled && !target.readOnly && inputTypes.has(target.type)
}

export function hasNativeKeyboard(userAgent: string, platform: string, touchPoints: number): boolean {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(userAgent) || (platform === 'MacIntel' && touchPoints > 1)
}

export function insertKeyboardText(field: Editable, text: string, backward = false): void {
  let start = field.value.length
  let end = start
  try {
    start = field.selectionStart ?? start
    end = field.selectionEnd ?? start
  } catch {
    start = field.value.length
  }
  const from = backward && start === end ? Math.max(0, start - 1) : start
  if (backward && from === end) return
  const next = field.value.slice(0, from) + text + field.value.slice(end)
  const setter = field instanceof HTMLTextAreaElement
    ? Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
    : Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(field, next)
  field.dispatchEvent(new Event('input', { bubbles: true }))
  const caret = from + text.length
  try {
    field.setSelectionRange(caret, caret)
    requestAnimationFrame(() => {
      if (field.isConnected) field.setSelectionRange(caret, caret)
    })
  } catch {
    return
  }
}

export function OnScreenKeyboard({ enabled = true }: { enabled?: boolean }) {
  const [field, setField] = useState<Editable | null>(null)
  const [shift, setShift] = useState(false)
  const [numeric, setNumeric] = useState(false)
  const [native, setNative] = useState(() => hasNativeKeyboard(navigator.userAgent, navigator.platform, navigator.maxTouchPoints))
  const fieldRef = useRef<Editable | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!enabled) {
      fieldRef.current = null
      setField(null)
      return
    }
    const onFocus = (event: FocusEvent) => {
      if (isEditable(event.target) && !native) {
        fieldRef.current = event.target
        setField(event.target)
      } else if (!panelRef.current?.contains(event.target as Node)) {
        fieldRef.current = null
        setField(null)
      }
    }
    const onClick = (event: MouseEvent) => {
      if (isEditable(event.target) && !native) {
        fieldRef.current = event.target
        setField(event.target)
      }
    }
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!panelRef.current?.contains(target) && !isEditable(target)) {
        fieldRef.current?.blur()
        fieldRef.current = null
        setField(null)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && fieldRef.current && !native) {
        event.preventDefault()
        event.stopImmediatePropagation()
        fieldRef.current.blur()
        fieldRef.current = null
        setField(null)
      }
    }
    const onViewport = () => {
      const mobile = hasNativeKeyboard(navigator.userAgent, navigator.platform, navigator.maxTouchPoints)
      const next = mobile || keyboardIsUp(window.innerHeight, window.visualViewport?.height ?? window.innerHeight)
      setNative(next)
      if (next) {
        fieldRef.current = null
        setField(null)
      }
    }
    document.addEventListener('focusin', onFocus)
    document.addEventListener('click', onClick)
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeyDown, true)
    window.visualViewport?.addEventListener('resize', onViewport)
    onViewport()
    return () => {
      document.removeEventListener('focusin', onFocus)
      document.removeEventListener('click', onClick)
      document.removeEventListener('pointerdown', onPointerDown, true)
      document.removeEventListener('keydown', onKeyDown, true)
      window.visualViewport?.removeEventListener('resize', onViewport)
      document.documentElement.style.removeProperty('--keyboard-height')
    }
  }, [enabled, native])

  useEffect(() => {
    if (!enabled || !field || native) {
      document.documentElement.style.removeProperty('--keyboard-height')
      return
    }
    const panel = panelRef.current
    if (!panel) return
    const update = () => {
      document.documentElement.style.setProperty('--keyboard-height', `${panel.offsetHeight}px`)
      field.scrollIntoView?.({ block: 'nearest' })
    }
    const observer = new ResizeObserver(update)
    observer.observe(panel)
    update()
    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty('--keyboard-height')
    }
  }, [enabled, field, native])

  if (!enabled || !field || native) return null

  const write = (value: string, backward = false) => {
    const target = fieldRef.current
    if (!target?.isConnected) {
      setField(null)
      return
    }
    target.focus()
    insertKeyboardText(target, value, backward)
    if (shift && !numeric) setShift(false)
  }
  const enter = () => {
    const target = fieldRef.current
    if (!target?.isConnected) return setField(null)
    if (target instanceof HTMLInputElement) {
      target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
    }
    target.blur()
    fieldRef.current = null
    setField(null)
  }
  const key = (label: string, action: () => void, extra = '') => (
    <button type="button" className={`osk__key ${extra}`} aria-label={label} onPointerDown={(event) => event.preventDefault()} onClick={action} key={label}>
      {label}
    </button>
  )

  return createPortal(
    <div ref={panelRef} className="osk" role="group" aria-label="On-screen keyboard">
      <div className="osk__toolbar">
        <span>Keyboard</span>
        {key('Close keyboard', () => {
          fieldRef.current?.blur()
          fieldRef.current = null
          setField(null)
        })}
      </div>
      {(numeric ? symbols : letters).map((row) => (
        <div className="osk__row" key={row}>
          {Array.from(row).map((character) => key(numeric || shift ? character.toUpperCase() : character, () => write(numeric || shift ? character.toUpperCase() : character)))}
        </div>
      ))}
      <div className="osk__row">
        {key(numeric ? 'ABC' : '123', () => setNumeric(!numeric), 'osk__key--wide')}
        {key('Shift', () => setShift(!shift), `osk__key--wide ${shift ? 'osk__key--active' : ''}`)}
        {key(',', () => write(','))}
        {key('Space', () => write(' '), 'osk__key--space')}
        {key('.', () => write('.'))}
        {key('Backspace', () => write('', true), 'osk__key--wide')}
        {field instanceof HTMLTextAreaElement && key('New line', () => write('\n'), 'osk__key--wide')}
        {key('Enter', enter, 'osk__key--enter')}
      </div>
    </div>,
    document.body,
  )
}
