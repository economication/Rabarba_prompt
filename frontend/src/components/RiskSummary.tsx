interface Props {
  summary: string
}

export default function RiskSummary({ summary }: Props) {
  return (
    <div className="summary-card">
      <h3>Risk Summary</h3>
      {summary ? (
        <p className="summary-text">{summary}</p>
      ) : (
        <p className="summary-empty">No risk summary available.</p>
      )}
    </div>
  )
}
