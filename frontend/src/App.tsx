import { useState } from 'react'
import OptimizeForm from './components/OptimizeForm'
import ResultPanel from './components/ResultPanel'
import RunHistory from './components/RunHistory'
import StageProgress, { type StageState } from './components/StageProgress'
import {
  type OptimizeRequest,
  type OptimizeResponse,
  cancelRun,
  optimizeWithStream,
} from './lib/api'

type Tab = 'optimize' | 'history'

export default function App() {
  const [tab, setTab] = useState<Tab>('optimize')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [stages, setStages] = useState<StageState[]>([])
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [wasCancelled, setWasCancelled] = useState(false)

  function resetRunState() {
    setStages([])
    setActiveRunId(null)
    setWasCancelled(false)
    setResult(null)
    setFetchError(null)
  }

  function handleStageStart(stage: string, iteration: number) {
    setStages((prev) => {
      // Mark any previous active stage as complete (fallback)
      const updated = prev.map((s) =>
        s.status === 'active' ? { ...s, status: 'complete' as const } : s,
      )
      return [
        ...updated,
        {
          stage,
          iteration,
          status: 'active' as const,
          startedAt: Date.now(),
        },
      ]
    })
  }

  function handleStageComplete(stage: string, iteration: number, durationMs: number) {
    setStages((prev) =>
      prev.map((s) =>
        s.stage === stage && s.iteration === iteration && s.status === 'active'
          ? { ...s, status: 'complete' as const, durationMs }
          : s,
      ),
    )
  }

  async function handleSubmit(request: OptimizeRequest) {
    resetRunState()
    setLoading(true)

    if (request.run_id) {
      setActiveRunId(request.run_id)
    }

    try {
      await optimizeWithStream(
        request,
        handleStageStart,
        handleStageComplete,
        (response) => {
          setResult(response)
          setLoading(false)
          setActiveRunId(null)
        },
        (response) => {
          setResult(response)
          setWasCancelled(true)
          setLoading(false)
          setActiveRunId(null)
        },
        (message) => {
          setFetchError(message)
          setLoading(false)
          setActiveRunId(null)
        },
      )
    } catch (err) {
      setFetchError(
        err instanceof Error ? err.message : 'An unexpected error occurred.',
      )
      setLoading(false)
      setActiveRunId(null)
    }
  }

  async function handleCancel() {
    if (activeRunId) {
      await cancelRun(activeRunId)
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

            {(loading || stages.length > 0) && (
              <div className="card">
                <StageProgress
                  stages={stages}
                  runId={activeRunId}
                  onCancel={handleCancel}
                  streaming={loading}
                />
              </div>
            )}

            {fetchError && (
              <div className="banner banner--error">
                <strong>Request failed:</strong> {fetchError}
              </div>
            )}

            {wasCancelled && result && (
              <div className="banner banner--warning">
                <strong>Run cancelled.</strong> Showing partial results.
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
