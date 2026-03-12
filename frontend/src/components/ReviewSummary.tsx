import { type ReviewIssue } from '../lib/api'

interface Props {
  summary: string
  issues: ReviewIssue[]
}

export default function ReviewSummary({ summary, issues }: Props) {
  return (
    <div className="summary-card">
      <h3>Review Summary</h3>
      {summary ? (
        <p className="summary-text">{summary}</p>
      ) : (
        <p className="summary-empty">No review summary available.</p>
      )}

      {issues.length > 0 && (
        <div className="review-issues">
          <ul className="issue-list">
            {issues.map((issue, i) => (
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
  )
}
