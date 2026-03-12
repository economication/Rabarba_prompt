import { useEffect, useState } from 'react'

export interface StageState {
  stage: string
  iteration: number
  status: 'pending' | 'active' | 'complete' | 'error'
  durationMs?: number
  startedAt?: number
}

interface Props {
  stages: StageState[]
  runId: string | null
  onCancel: () => void
  streaming: boolean
}

const STAGE_LABELS: Record<string, string> = {
  repo_scanner:     'Repo Scanner',
  input_analyzer:   'Analyzing Requirements',
  drafter:          'Drafting Prompt',
  risk_assessor:    'Assessing Risks',
  prompt_assembler: 'Assembling Prompt',
  reviewer:         'Reviewing',
  refiner:          'Refining',
}

function stageLabel(stage: string, iteration: number): string {
  const base = STAGE_LABELS[stage] ?? stage
  return iteration > 0 ? `${base} (iteration ${iteration + 1})` : base
}

function formatDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`
}

function LiveTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(Date.now() - startedAt)

  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - startedAt), 100)
    return () => clearInterval(id)
  }, [startedAt])

  return <span className="stage-duration stage-duration--live">{formatDuration(elapsed)}…</span>
}

export default function StageProgress({ stages, runId, onCancel, streaming }: Props) {
  return (
    <div className="stage-progress">
      <div className="stage-progress__header">
        <span className="stage-progress__title">Progress</span>
        {streaming && runId && (
          <button
            type="button"
            className="cancel-btn"
            onClick={onCancel}
          >
            Cancel
          </button>
        )}
      </div>

      <ul className="stage-list">
        {stages.map((s, idx) => (
          <li key={`${s.stage}-${s.iteration}-${idx}`} className={`stage-item stage-item--${s.status}`}>
            <span className="stage-icon">
              {s.status === 'pending'  && '○'}
              {s.status === 'active'   && <span className="spinner">⟳</span>}
              {s.status === 'complete' && '✓'}
              {s.status === 'error'    && '✗'}
            </span>
            <span className="stage-name">{stageLabel(s.stage, s.iteration)}</span>
            <span className="stage-duration">
              {s.status === 'complete' && s.durationMs !== undefined && formatDuration(s.durationMs)}
              {s.status === 'active'   && s.startedAt !== undefined && <LiveTimer startedAt={s.startedAt} />}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
