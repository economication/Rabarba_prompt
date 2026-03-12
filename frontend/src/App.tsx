import { useState } from 'react'
import OptimizeForm from './components/OptimizeForm'
import ResultPanel from './components/ResultPanel'
import RunHistory from './components/RunHistory'
import { type OptimizeRequest, type OptimizeResponse, optimizePrompt } from './lib/api'

type Tab = 'optimize' | 'history'

export default function App() {
  const [tab, setTab] = useState<Tab>('optimize')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)

  async function handleSubmit(request: OptimizeRequest) {
    setLoading(true)
    setFetchError(null)
    setResult(null)

    try {
      const response = await optimizePrompt(request)
      setResult(response)
    } catch (err) {
      setFetchError(
        err instanceof Error ? err.message : 'An unexpected error occurred.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-top">
          <div>
            <h1>Rabarba Prompt</h1>
            <p className="app-subtitle">
              LangGraph-powered prompt optimizer for coding agents
            </p>
          </div>
          <nav className="app-tabs">
            <button
              className={`tab-btn${tab === 'optimize' ? ' tab-btn--active' : ''}`}
              onClick={() => setTab('optimize')}
            >
              Optimize
            </button>
            <button
              className={`tab-btn${tab === 'history' ? ' tab-btn--active' : ''}`}
              onClick={() => setTab('history')}
            >
              History
            </button>
          </nav>
        </div>
      </header>

      <main>
        {tab === 'optimize' && (
          <>
            <div className="card optimize-form">
              <OptimizeForm onSubmit={handleSubmit} loading={loading} />
            </div>

            {fetchError && (
              <div className="banner banner--error">
                <strong>Request failed:</strong> {fetchError}
              </div>
            )}

            {result && <ResultPanel result={result} />}
          </>
        )}

        {tab === 'history' && <RunHistory />}
      </main>
    </div>
  )
}
