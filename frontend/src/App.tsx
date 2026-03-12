import { useState } from 'react'
import OptimizeForm from './components/OptimizeForm'
import ResultPanel from './components/ResultPanel'
import { type OptimizeRequest, type OptimizeResponse, optimizePrompt } from './lib/api'

export default function App() {
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
        <h1>Rabarba Prompt</h1>
        <p className="app-subtitle">
          LangGraph-powered prompt optimizer for coding agents
        </p>
      </header>

      <main>
        <div className="card optimize-form">
          <OptimizeForm onSubmit={handleSubmit} loading={loading} />
        </div>

        {fetchError && (
          <div className="banner banner--error">
            <strong>Request failed:</strong> {fetchError}
          </div>
        )}

        {result && <ResultPanel result={result} />}
      </main>
    </div>
  )
}
