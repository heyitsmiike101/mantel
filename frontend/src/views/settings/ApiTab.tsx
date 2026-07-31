import { useQuery } from '@tanstack/react-query'
import { Markdown } from '../../components/Markdown'

/** Renders the same markdown that /api/ai-guide serves, so what a person reads here and
 *  what an agent fetches can never drift apart. */
export function ApiTab() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['ai-guide'],
    queryFn: async () => {
      const res = await fetch('/api/ai-guide')
      if (!res.ok) throw new Error(`ai-guide ${res.status}`)
      return res.text()
    },
    // The guide ships inside the image; it only changes when the app is redeployed.
    refetchInterval: false,
    staleTime: Infinity,
  })

  return (
    <section className="panel">
      <h2>API</h2>
      <p className="hint">
        Everything this app can do is available over HTTP, with no authentication — it is meant
        for a trusted home network. Point another tool, a script, or an AI agent at the guide
        below.
      </p>

      <div className="row">
        <a className="btn" href="/api/docs" target="_blank" rel="noreferrer">
          Interactive docs
        </a>
        <a className="btn" href="/api/redoc" target="_blank" rel="noreferrer">
          Reference
        </a>
        <a className="btn" href="/api/openapi.json" target="_blank" rel="noreferrer">
          OpenAPI schema
        </a>
        <a className="btn" href="/api/ai-guide" target="_blank" rel="noreferrer">
          Guide as markdown
        </a>
      </div>

      <div className="docs__body">
        {isLoading && <p className="hint">Loading the guide…</p>}
        {isError && (
          <p className="hint">
            Couldn't load the guide. It is also at <code>/api/ai-guide</code>.
          </p>
        )}
        {data && <Markdown source={data} />}
      </div>
    </section>
  )
}
