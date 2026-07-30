import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation } from '../../api/hooks'
import type { CalendarEvent } from '../../api/types'
import { EventModal } from '../../components/EventModal'
import { WIDGETS } from './widgets'

interface Widget {
  id: number
  widget_type: string
  size: 'small' | 'medium' | 'large'
  position: number
  config: Record<string, unknown>
}

interface WidgetType {
  type: string
  name: string
  description: string
  default_size: string
}

const SIZES: Widget['size'][] = ['small', 'medium', 'large']

export function DashboardPage() {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [openEvent, setOpenEvent] = useState<CalendarEvent | null>(null)
  const [newEventAt, setNewEventAt] = useState<Date | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const { data: widgets = [] } = useQuery({
    queryKey: ['widgets'],
    queryFn: () => api.get<Widget[]>('/dashboard/widgets'),
  })
  const { data: types = [] } = useQuery({
    queryKey: ['widget-types'],
    queryFn: () => api.get<WidgetType[]>('/dashboard/widget-types'),
  })

  const addWidget = useEntityMutation(
    (body: { widget_type: string; size: string }) => api.post<Widget>('/dashboard/widgets', body),
    ['widgets'],
  )
  const patchWidget = useEntityMutation(
    ({ id, ...patch }: { id: number } & Partial<Widget>) =>
      api.patch<Widget>(`/dashboard/widgets/${id}`, patch),
    ['widgets'],
  )
  const removeWidget = useEntityMutation(
    (id: number) => api.del<void>(`/dashboard/widgets/${id}`),
    ['widgets'],
  )

  const move = (index: number, direction: -1 | 1) => {
    const target = widgets[index + direction]
    const current = widgets[index]
    if (!target) return
    patchWidget.mutate({ id: current.id, position: target.position })
    patchWidget.mutate({ id: target.id, position: current.position })
  }

  const cycleSize = (w: Widget) =>
    patchWidget.mutate({ id: w.id, size: SIZES[(SIZES.indexOf(w.size) + 1) % SIZES.length] })

  const showEvent = (e: CalendarEvent) => {
    setOpenEvent(e)
    setNewEventAt(null)
    setModalOpen(true)
  }
  const createAt = (start: Date) => {
    setOpenEvent(null)
    setNewEventAt(start)
    setModalOpen(true)
  }

  return (
    <div className="dash">
      <header className="dash__bar">
        <h1 className="dash__title">Dashboard</h1>
        <button className="iconbtn" onClick={() => setAdding(true)}>
          + Widget
        </button>
        <button
          className="iconbtn"
          aria-current={editing ? 'page' : undefined}
          onClick={() => setEditing(!editing)}
        >
          {editing ? 'Done' : 'Arrange'}
        </button>
      </header>

      {widgets.length === 0 && (
        <div className="placeholder">
          <div style={{ fontSize: 'var(--font-lg)' }}>Your dashboard is empty</div>
          <div style={{ fontSize: 'var(--font-sm)' }}>
            Tap “+ Widget” to build the wall however you like.
          </div>
        </div>
      )}

      <div className="dash__grid">
        {widgets.map((w, i) => {
          const def = WIDGETS[w.widget_type]
          return (
            <section key={w.id} className="widget" data-size={w.size}>
              {editing && (
                <div className="widget__edit">
                  <button className="iconbtn" onClick={() => move(i, -1)} disabled={i === 0}>
                    ↑
                  </button>
                  <button
                    className="iconbtn"
                    onClick={() => move(i, 1)}
                    disabled={i === widgets.length - 1}
                  >
                    ↓
                  </button>
                  <button className="iconbtn" onClick={() => cycleSize(w)}>
                    {w.size}
                  </button>
                  <button className="iconbtn iconbtn--danger" onClick={() => removeWidget.mutate(w.id)}>
                    Remove
                  </button>
                </div>
              )}
              {def ? (
                <def.component
                  config={w.config}
                  onConfigChange={(config) => patchWidget.mutate({ id: w.id, config })}
                  onOpenEvent={showEvent}
                  onNewEvent={createAt}
                />
              ) : (
                <p className="widget__empty">Unknown widget “{w.widget_type}”.</p>
              )}
            </section>
          )
        })}
      </div>

      {adding && (
        <div className="modal" onClick={() => setAdding(false)} role="dialog">
          <div className="modal__card" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal__title">Add a widget</h2>
            {types.map((t) => (
              <button
                key={t.type}
                className="picker"
                onClick={() => {
                  addWidget.mutate({ widget_type: t.type, size: t.default_size })
                  setAdding(false)
                }}
              >
                <span className="picker__name">{t.name}</span>
                <span className="picker__desc">{t.description}</span>
              </button>
            ))}
            <div className="modal__actions">
              <div className="modal__spacer" />
              <button className="btn" onClick={() => setAdding(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {modalOpen && (
        <EventModal
          event={openEvent}
          defaultStart={newEventAt}
          onClose={() => {
            setModalOpen(false)
            setOpenEvent(null)
            setNewEventAt(null)
          }}
        />
      )}
    </div>
  )
}
