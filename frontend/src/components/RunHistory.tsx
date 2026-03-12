import { useEffect, useState } from 'react'
import * as Diff from 'diff'
import { listRuns, getRun, type RunSummary, type RunDetailResponse } from '../lib/api'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'completed'
      ? 'status-badge status-badge--completed'
      : status === 'failed'
        ? 'status-badge status-badge--failed'
        : status === 'running'
          ? 'status-badge status-badge--running'
          : 'status-badge status-badge--pending'
  return <span className={cls}>{status}</span>
}

// ---------------------------------------------------------------------------
// Diff panel
// ---------------------------------------------------------------------------

interface DiffPanelProps {
  runA: RunDetailResponse
  runB: RunDetailResponse
  onClose: () => void
}

function DiffPanel({ runA, runB, onClose }: DiffPanelProps) {
  const promptA = runA.final_result?.final_prompt ?? ''
  const promptB = runB.final_result?.final_prompt ?? ''
  const diff = Diff.diffLines(promptA, promptB)

  return (
    <div className="diff-overlay">
      <div className="diff-modal card">
        <div className="diff-modal-header">
          <h2 className="section-label">Prompt Diff</h2>
          <button className="copy-btn" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="diff-meta-row">
          <div className="diff-meta-col">
            <span className="meta-label">Run A</span>
            <span className="meta-value">{runA.run_id.slice(0, 8)}…</span>
            <span className="meta-value meta-value--none">
              {runA.stop_reason ?? '—'} · {runA.cost_summary.total_cost_usd.toFixed(4)} USD ·{' '}
              {runA.prompt_versions.length} iter
            </span>
          </div>
          <div className="diff-meta-col">
            <span className="meta-label">Run B</span>
            <span className="meta-value">{runB.run_id.slice(0, 8)}…</span>
            <span className="meta-value meta-value--none">
              {runB.stop_reason ?? '—'} · {runB.cost_summary.total_cost_usd.toFixed(4)} USD ·{' '}
              {runB.prompt_versions.length} iter
            </span>
          </div>
        </div>

        {promptA === '' && promptB === '' ? (
          <p className="summary-empty">Neither run has a final prompt to diff.</p>
        ) : (
          <pre className="diff-content">
            {diff.map((part, i) => (
              <span
                key={i}
                className={
                  part.added
                    ? 'diff-added'
                    : part.removed
                      ? 'diff-removed'
                      : 'diff-context'
                }
              >
                {part.value}
              </span>
            ))}
          </pre>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run detail drawer
// ---------------------------------------------------------------------------

interface RunDetailDrawerProps {
  detail: RunDetailResponse
  onClose: () => void
}

function RunDetailDrawer({ detail, onClose }: RunDetailDrawerProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="run-detail card">
      <div className="run-detail-header">
        <div>
          <h3 className="section-label">Run Detail</h3>
          <code className="meta-value meta-value--mono">{detail.run_id}</code>
        </div>
        <button className="copy-btn" onClick={onClose}>
          ← Back
        </button>
      </div>

      <div className="result-meta" style={{ marginTop: 12 }}>
        <div className="meta-item">
          <span className="meta-label">Status</span>
          <StatusBadge status={detail.status} />
        </div>
        <div className="meta-item">
          <span className="meta-label">Stop Reason</span>
          <span className="meta-value">{detail.stop_reason ?? '—'}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Iterations</span>
          <span className="meta-value">{detail.prompt_versions.length}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Total Cost</span>
          <span className="meta-value">
            ${detail.cost_summary.total_cost_usd.toFixed(4)}
          </span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Tokens (in / out)</span>
          <span className="meta-value">
            {detail.cost_summary.total_input_tokens.toLocaleString()} /{' '}
            {detail.cost_summary.total_output_tokens.toLocaleString()}
          </span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Target Agent</span>
          <span className="meta-value">
            {(detail.config.target_agent as string) ?? 'Generic'}
          </span>
        </div>
      </div>

      {detail.final_result && (
        <div style={{ marginTop: 16 }}>
          <div className="prompt-header">
            <span className="section-label">Final Prompt</span>
          </div>
          <textarea
            readOnly
            className="prompt-textarea"
            value={detail.final_result.final_prompt}
          />
        </div>
      )}

      {detail.prompt_versions.length > 0 && (
        <div style={{ marginTop: 16 }} className="collapsible">
          <button
            className="collapsible-header"
            onClick={() => setOpen(o => !o)}
          >
            Iteration History ({detail.prompt_versions.length})
            <span
              className={`collapsible-chevron${open ? ' collapsible-chevron--open' : ''}`}
            >
              ▶
            </span>
          </button>
          {open && (
            <div className="collapsible-body">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Verdict</th>
                    <th>Fail Signature</th>
                    <th>Stable</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.prompt_versions.map(v => (
                    <tr key={v.iteration}>
                      <td>{v.iteration}</td>
                      <td>
                        <span
                          className={`verdict-badge verdict-badge--${v.reviewer_verdict || 'unknown'}`}
                        >
                          {v.reviewer_verdict || '—'}
                        </span>
                      </td>
                      <td>
                        {v.fail_signature ? (
                          <span className="history-sig">{v.fail_signature}</span>
                        ) : (
                          <span className="history-sig--empty">—</span>
                        )}
                      </td>
                      <td>{v.is_stable ? '✓' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {detail.cost_summary.by_node.length > 0 && (
        <div style={{ marginTop: 16 }} className="collapsible">
          <button
            className="collapsible-header"
            onClick={() => setOpen(o => !o)}
          >
            Cost Breakdown
            <span className="collapsible-chevron">▶</span>
          </button>
          <div className="collapsible-body">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Calls</th>
                  <th>Input Tokens</th>
                  <th>Output Tokens</th>
                  <th>Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {detail.cost_summary.by_node.map(n => (
                  <tr key={n.node_name}>
                    <td>
                      <code>{n.node_name}</code>
                    </td>
                    <td>{n.call_count}</td>
                    <td>{n.total_input_tokens.toLocaleString()}</td>
                    <td>{n.total_output_tokens.toLocaleString()}</td>
                    <td>${n.total_cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main RunHistory component
// ---------------------------------------------------------------------------

export default function RunHistory() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<RunDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Diff state: up to 2 run IDs selected
  const [diffSelected, setDiffSelected] = useState<string[]>([])
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffRunA, setDiffRunA] = useState<RunDetailResponse | null>(null)
  const [diffRunB, setDiffRunB] = useState<RunDetailResponse | null>(null)

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load runs'))
      .finally(() => setLoading(false))
  }, [])

  async function handleRowClick(runId: string) {
    setDetailLoading(true)
    try {
      const detail = await getRun(runId)
      setSelectedDetail(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run detail')
    } finally {
      setDetailLoading(false)
    }
  }

  function toggleDiffSelect(runId: string) {
    setDiffSelected(prev => {
      if (prev.includes(runId)) return prev.filter(id => id !== runId)
      if (prev.length >= 2) return prev
      return [...prev, runId]
    })
  }

  async function handleCompare() {
    if (diffSelected.length !== 2) return
    setDiffLoading(true)
    try {
      const [a, b] = await Promise.all([
        getRun(diffSelected[0]),
        getRun(diffSelected[1]),
      ])
      setDiffRunA(a)
      setDiffRunB(b)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load runs for diff')
    } finally {
      setDiffLoading(false)
    }
  }

  if (loading) {
    return <div className="run-history-loading">Loading run history…</div>
  }

  if (error) {
    return (
      <div className="banner banner--error">
        <strong>Error:</strong> {error}
      </div>
    )
  }

  if (selectedDetail) {
    return (
      <RunDetailDrawer
        detail={selectedDetail}
        onClose={() => setSelectedDetail(null)}
      />
    )
  }

  if (diffRunA && diffRunB) {
    return (
      <DiffPanel
        runA={diffRunA}
        runB={diffRunB}
        onClose={() => {
          setDiffRunA(null)
          setDiffRunB(null)
          setDiffSelected([])
        }}
      />
    )
  }

  if (runs.length === 0) {
    return (
      <div className="card run-history-empty">
        <p className="summary-empty">No runs yet. Submit a task to get started.</p>
      </div>
    )
  }

  return (
    <div className="card run-history">
      <div className="run-history-header">
        <span className="section-label">Run History</span>
        {diffSelected.length === 2 && (
          <button
            className="submit-btn"
            style={{ width: 'auto', marginTop: 0, padding: '6px 16px' }}
            onClick={handleCompare}
            disabled={diffLoading}
          >
            {diffLoading ? 'Loading…' : 'Compare'}
          </button>
        )}
        {diffSelected.length > 0 && diffSelected.length < 2 && (
          <span className="meta-value meta-value--none" style={{ fontSize: 12 }}>
            Select one more run to compare
          </span>
        )}
      </div>

      <table className="history-table" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th style={{ width: 32 }}></th>
            <th>Task</th>
            <th>Status</th>
            <th>Stop Reason</th>
            <th>Iter</th>
            <th>Cost</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(run => (
            <tr
              key={run.run_id}
              className="run-history-row"
              onClick={() => handleRowClick(run.run_id)}
            >
              <td
                onClick={e => {
                  e.stopPropagation()
                  toggleDiffSelect(run.run_id)
                }}
              >
                <input
                  type="checkbox"
                  checked={diffSelected.includes(run.run_id)}
                  onChange={() => toggleDiffSelect(run.run_id)}
                  disabled={
                    diffSelected.length >= 2 && !diffSelected.includes(run.run_id)
                  }
                  onClick={e => e.stopPropagation()}
                />
              </td>
              <td>
                <span className="history-preview">{run.task_brief_preview}</span>
              </td>
              <td>
                <StatusBadge status={run.status} />
              </td>
              <td>
                <span className="meta-value">{run.stop_reason ?? '—'}</span>
              </td>
              <td>{run.iteration_count}</td>
              <td>${run.total_cost_usd.toFixed(4)}</td>
              <td>
                <span className="meta-value meta-value--none">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {detailLoading && (
        <div className="run-history-loading" style={{ marginTop: 12 }}>
          Loading run…
        </div>
      )}
    </div>
  )
}
