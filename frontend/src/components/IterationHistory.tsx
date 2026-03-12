import { useState } from 'react'
import { type HistoryItem, type ReviewIssue } from '../lib/api'

interface Props {
  history: HistoryItem[]
  reviewIssues: ReviewIssue[]
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const cls = `verdict-badge verdict-badge--${verdict}`
  const label =
    verdict === 'human_required' ? 'human required' : verdict
  return <span className={cls}>{label}</span>
}

export default function IterationHistory({ history, reviewIssues }: Props) {
  const [open, setOpen] = useState(false)

  const hasContent = history.length > 0 || reviewIssues.length > 0
  if (!hasContent) return null

  return (
    <div className="collapsible">
      <button
        type="button"
        className="collapsible-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>Iteration History & Issue Detail</span>
        <span className={`collapsible-chevron ${open ? 'collapsible-chevron--open' : ''}`}>
          ▶
        </span>
      </button>

      {open && (
        <div className="collapsible-body">
          {history.length > 0 && (
            <>
              <p className="section-label" style={{ marginBottom: 10 }}>
                Prompt Versions
              </p>
              <table className="history-table">
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>#</th>
                    <th style={{ width: 140 }}>Reviewer Verdict</th>
                    <th>Fail Signature</th>
                    <th>Prompt Preview (first 120 chars)</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.iteration}>
                      <td>{item.iteration}</td>
                      <td>
                        {item.reviewer_verdict ? (
                          <VerdictBadge verdict={item.reviewer_verdict} />
                        ) : (
                          <span style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                            pending
                          </span>
                        )}
                      </td>
                      <td>
                        {item.fail_signature ? (
                          <span className="history-sig">{item.fail_signature}</span>
                        ) : (
                          <span className="history-sig history-sig--empty">—</span>
                        )}
                      </td>
                      <td>
                        <span className="history-preview">
                          {item.prompt_text.slice(0, 120)}
                          {item.prompt_text.length > 120 ? '…' : ''}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {reviewIssues.length > 0 && (
            <div style={{ marginTop: history.length > 0 ? 20 : 0 }}>
              <p className="section-label" style={{ marginBottom: 10 }}>
                Final Review Issues
              </p>
              <ul className="issue-list">
                {reviewIssues.map((issue, i) => (
                  <li key={i} className={`issue-item issue-item--${issue.verdict}`}>
                    <div className="issue-header">
                      <span className="issue-code">{issue.code}</span>
                      <span className="issue-rubric">({issue.rubric_item})</span>
                      <span className={`issue-verdict issue-verdict--${issue.verdict}`}>
                        {issue.verdict}
                      </span>
                    </div>
                    <p className="issue-reason">{issue.reason}</p>
                    {issue.fix_instruction && (
                      <p className="issue-fix">{issue.fix_instruction}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
