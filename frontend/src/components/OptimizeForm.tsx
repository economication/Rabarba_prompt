import { type FormEvent, useState } from 'react'
import { type OptimizeRequest } from '../lib/api'

interface Props {
  onSubmit: (request: OptimizeRequest) => void
  loading: boolean
}

export default function OptimizeForm({ onSubmit, loading }: Props) {
  const [taskBrief, setTaskBrief] = useState('')
  const [repoPath, setRepoPath] = useState('')
  const [targetAgent, setTargetAgent] = useState('Generic')
  const [maxIterations, setMaxIterations] = useState(3)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!taskBrief.trim()) return

    onSubmit({
      task_brief: taskBrief,
      repo_path: repoPath.trim() || null,
      target_agent: targetAgent || null,
      max_iterations: maxIterations,
    })
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="task-brief">
          Task Brief<span className="required-mark">*</span>
        </label>
        <textarea
          id="task-brief"
          value={taskBrief}
          onChange={(e) => setTaskBrief(e.target.value)}
          placeholder="Describe the task you want to implement. Be as specific as possible — include language, framework, expected output, constraints, and any relevant background."
          required
          disabled={loading}
        />
        <p className="field-hint">Required. The more context you provide, the better the optimizer performs.</p>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="repo-path">Local Repo Path</label>
          <input
            id="repo-path"
            type="text"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/your/project"
            disabled={loading}
          />
          <p className="field-hint">Optional. Local folder path for repo-aware optimization.</p>
        </div>

        <div className="form-group">
          <label htmlFor="target-agent">Target Agent</label>
          <select
            id="target-agent"
            value={targetAgent}
            onChange={(e) => setTargetAgent(e.target.value)}
            disabled={loading}
          >
            <option value="Generic">Generic</option>
            <option value="Cursor">Cursor</option>
            <option value="Claude Code">Claude Code</option>
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="max-iterations">Max Iterations</label>
          <input
            id="max-iterations"
            type="number"
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            min={1}
            max={5}
            disabled={loading}
          />
        </div>
      </div>

      <button
        type="submit"
        className="submit-btn"
        disabled={loading || !taskBrief.trim()}
      >
        {loading ? 'Optimizing…' : 'Optimize Prompt'}
      </button>
    </form>
  )
}
