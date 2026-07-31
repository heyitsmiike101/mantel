import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation, useUsers } from '../../api/hooks'
import type { SharedList } from '../../api/types'

const LIST_KEYS = ['lists']

export function ListsPage() {
  const { data: lists = [] } = useQuery({
    queryKey: LIST_KEYS,
    queryFn: () => api.get<SharedList[]>('/lists'),
    refetchInterval: 30_000,
  })
  const [newName, setNewName] = useState('')

  const createList = useEntityMutation(
    (body: { name: string; icon: string }) => api.post<SharedList>('/lists', body),
    LIST_KEYS,
  )

  const add = () => {
    const name = newName.trim()
    if (!name) return
    createList.mutate({ name, icon: guessIcon(name) })
    setNewName('')
  }

  return (
    <div className="lists">
      <header className="lists__bar">
        <h1 className="lists__title">Lists</h1>
      </header>

      <div className="lists__body">
        {lists.length === 0 && (
          <p className="hint">
            No lists yet. Groceries, chores, packing for a trip — whatever the house needs.
          </p>
        )}

        <div className="lists__grid">
          {lists.map((list) => (
            <ListCard key={list.id} list={list} />
          ))}
        </div>

        <div className="row">
          <input
            className="row__name"
            placeholder="New list (e.g. Groceries)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
          />
          <button className="btn btn--primary" onClick={add}>
            Add list
          </button>
        </div>
      </div>
    </div>
  )
}

function ListCard({ list }: { list: SharedList }) {
  const { data: users = [] } = useUsers()
  const [text, setText] = useState('')
  const [assignee, setAssignee] = useState<number | ''>('')

  const addItem = useEntityMutation(
    (body: { text: string; assigned_user_id: number | null }) =>
      api.post(`/lists/${list.id}/items`, body),
    LIST_KEYS,
  )
  const patchItem = useEntityMutation(
    ({ id, ...patch }: { id: number; checked?: boolean }) =>
      api.patch(`/lists/${list.id}/items/${id}`, patch),
    LIST_KEYS,
  )
  const removeItem = useEntityMutation(
    (id: number) => api.del(`/lists/${list.id}/items/${id}`),
    LIST_KEYS,
  )
  const clearChecked = useEntityMutation(
    () => api.post(`/lists/${list.id}/clear-checked`),
    LIST_KEYS,
  )
  const removeList = useEntityMutation(() => api.del(`/lists/${list.id}`), LIST_KEYS)

  const submit = () => {
    const value = text.trim()
    if (!value) return
    addItem.mutate({ text: value, assigned_user_id: assignee === '' ? null : assignee })
    setText('')
  }

  const checkedCount = list.items.filter((i) => i.checked).length

  return (
    <section className="listcard">
      <div className="listcard__head">
        <h2>
          {list.icon} {list.name}
        </h2>
        <span className="listcard__count">{list.item_count} left</span>
        {/* Grouped so a narrow card wraps both buttons together, rather than
            stranding Delete on a line of its own. */}
        <div className="listcard__actions">
          {checkedCount > 0 && (
            <button className="iconbtn" onClick={() => clearChecked.mutate(undefined as never)}>
              Clear {checkedCount}
            </button>
          )}
          <button className="iconbtn iconbtn--danger" onClick={() => removeList.mutate(undefined as never)}>
            Delete
          </button>
        </div>
      </div>

      <ul className="listcard__items">
        {list.items.map((item) => (
          <li key={item.id} className="listitem" data-checked={item.checked}>
            <button
              className="listitem__check"
              aria-label={item.checked ? `Uncheck ${item.text}` : `Check off ${item.text}`}
              style={item.color && !item.checked ? { borderColor: item.color } : undefined}
              onClick={() => patchItem.mutate({ id: item.id, checked: !item.checked })}
            >
              {item.checked ? '✓' : ''}
            </button>
            <span className="listitem__text">{item.text}</span>
            <button
              className="listitem__remove"
              aria-label={`Remove ${item.text}`}
              onClick={() => removeItem.mutate(item.id)}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      <div className="listcard__add">
        <input
          value={text}
          placeholder="Add an item"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        {users.length > 1 && (
          <select
            value={assignee}
            onChange={(e) => setAssignee(e.target.value ? Number(e.target.value) : '')}
            aria-label="Assign to"
          >
            <option value="">Anyone</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        )}
        <button className="btn btn--primary" onClick={submit}>
          Add
        </button>
      </div>
    </section>
  )
}

/** A small nicety: a new list gets a sensible emoji without anyone picking one. */
function guessIcon(name: string): string {
  const n = name.toLowerCase()
  if (/grocer|food|shop|market|costco|aldi|store/.test(n)) return '🛒'
  if (/chore|clean|task|todo|to-do/.test(n)) return '🧹'
  if (/pack|trip|travel|vacation|holiday/.test(n)) return '🧳'
  if (/hardware|tool|diy|garage/.test(n)) return '🔧'
  if (/gift|present|birthday|christmas/.test(n)) return '🎁'
  if (/school|homework|class/.test(n)) return '🎒'
  return '📝'
}
