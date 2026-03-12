import { type OptimizeResponse } from '../lib/api'
import PromptDisplay from './PromptDisplay'
import RiskSummary from './RiskSummary'
import ReviewSummary from './ReviewSummary'
import IterationHistory from './IterationHistory'

interface Props {
  result: OptimizeResponse
}

export default function ResultPanel({ result }: Props) {
  const failSigDisplay = result.fail_signature || null

  return (
    <div className="result-panel card">
      {/* Top metadata bar */}
      <div className="result-meta">
        <div className="meta-item">
          <span className="meta-label">Stop Reason</span>
          <span className="meta-value">{result.stop_reason || '—'}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Iterations</span>
          <span className="meta-value">{result.iteration_count}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Total Cost</span>
          <span className="meta-value">${result.total_cost_usd.toFixed(4)}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Tokens (in / out)</span>
          <span className="meta-value">
            {result.total_input_tokens.toLocaleString()} /{' '}
            {result.total_output_tokens.toLocaleString()}
          </span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Fail Signature</span>
          {failSigDisplay ? (
            <span className="meta-value meta-value--mono">{failSigDisplay}</span>
          ) : (
            <span className="meta-value meta-value--none">none</span>
          )}
        </div>
      </div>

      {/* Workflow error (not a fetch error — these come from inside the graph) */}
      {result.last_error && (
        <div className="banner banner--error" style={{ marginBottom: 16 }}>
          <strong>Workflow error:</strong> {result.last_error}
        </div>
      )}

      {/* Repo scan warnings */}
      {result.scan_warnings.length > 0 && (
        <div className="banner banner--warning" style={{ marginBottom: 16 }}>
          <strong>Repo scan warnings:</strong>
          <ul>
            {result.scan_warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Final prompt */}
      <PromptDisplay prompt={result.final_prompt} />

      {/* Risk + Review summaries */}
      <div className="summaries-row">
        <RiskSummary summary={result.risk_summary} />
        <ReviewSummary
          summary={result.review_summary}
          issues={result.review_issues}
        />
      </div>

      {/* Collapsible history + issue detail */}
      <IterationHistory
        history={result.history}
        reviewIssues={result.review_issues}
      />
    </div>
  )
}
