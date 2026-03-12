import { useEffect, useRef, useState } from 'react'
import {
  type IntroQuestion,
  type OptimizeRequest,
  introRequest,
} from '../lib/api'

type RepoSource = 'none' | 'local' | 'github'

interface Props {
  onSubmit: (request: OptimizeRequest) => void
  loading: boolean
}

const GITHUB_OWNER_REPO_RE = /^(https?:\/\/github\.com\/[\w.-]+\/[\w.-]+|[\w.-]+\/[\w.-]+)$/

export default function OptimizeForm({ onSubmit, loading }: Props) {
  const runIdRef = useRef<string>(crypto.randomUUID())

  // Step 1 state
  const [step, setStep] = useState<1 | 2>(1)
  const [taskBrief, setTaskBrief] = useState('')
  const [targetAgent, setTargetAgent] = useState('Generic')
  const [maxIterations, setMaxIterations] = useState(3)
  const [repoSource, setRepoSource] = useState<RepoSource>('none')
  const [localPath, setLocalPath] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [githubUrlError, setGithubUrlError] = useState('')

  // Step 2 state
  const [introLoading, setIntroLoading] = useState(false)
  const [introError, setIntroError] = useState('')
  const [introQuestions, setIntroQuestions] = useState<IntroQuestion[]>([])
  const [introAnswers, setIntroAnswers] = useState<Record<string, string>>({})

  // Reset run_id on every fresh form mount to avoid stale IDs after a completed run
  useEffect(() => {
    runIdRef.current = crypto.randomUUID()
  }, [])

  function getRepoFields(): { repo_path: string | null; github_url: string | null } {
    if (repoSource === 'local') return { repo_path: localPath.trim() || null, github_url: null }
    if (repoSource === 'github') return { repo_path: null, github_url: githubUrl.trim() || null }
    return { repo_path: null, github_url: null }
  }

  function buildRequest(withIntro: boolean): OptimizeRequest {
    const { repo_path, github_url } = getRepoFields()
    return {
      run_id: runIdRef.current,
      task_brief: taskBrief,
      repo_path,
      github_url,
      target_agent: targetAgent || null,
      max_iterations: maxIterations,
      intro_questions: withIntro && introQuestions.length > 0 ? introQuestions : null,
      intro_answers: withIntro && Object.keys(introAnswers).length > 0 ? introAnswers : null,
    }
  }

  function validateGitHubUrl(val: string): boolean {
    if (!val.trim()) return true
    return GITHUB_OWNER_REPO_RE.test(val.trim())
  }

  async function handleContinue() {
    setIntroError('')
    setIntroLoading(true)
    try {
      const resp = await introRequest({ task_brief: taskBrief, target_agent: targetAgent || null })
      const allQuestions = [...resp.fixed_questions, ...resp.dynamic_questions]
      setIntroQuestions(allQuestions)
      setIntroAnswers({})
      setStep(2)
    } catch (err) {
      setIntroError(err instanceof Error ? err.message : 'Failed to load questions.')
    } finally {
      setIntroLoading(false)
    }
  }

  function handleSkip() {
    onSubmit(buildRequest(false))
  }

  function handleOptimize() {
    onSubmit(buildRequest(true))
  }

  function handleBack() {
    setStep(1)
  }

  function setAnswer(id: string, value: string) {
    setIntroAnswers((prev) => ({ ...prev, [id]: value }))
  }

  const fixedIds = new Set(['language', 'output_format', 'constraints', 'test_required'])
  const fixedQuestions = introQuestions.filter((q) => fixedIds.has(q.id))
  const allFixedAnswered = fixedQuestions.every((q) => {
    const ans = introAnswers[q.id]?.trim()
    return ans && ans.length > 0
  })

  const canContinue = taskBrief.trim().length > 0 && !loading && !introLoading
  const canOptimize = allFixedAnswered && !loading

  // -------------------------------------------------------------------------
  // Step 1
  // -------------------------------------------------------------------------

  if (step === 1) {
    return (
      <div>
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

        <div className="form-group">
          <label>Repository (optional)</label>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="repo-source"
                value="none"
                checked={repoSource === 'none'}
                onChange={() => setRepoSource('none')}
                disabled={loading}
              />
              None
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="repo-source"
                value="local"
                checked={repoSource === 'local'}
                onChange={() => setRepoSource('local')}
                disabled={loading}
              />
              Local Path
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="repo-source"
                value="github"
                checked={repoSource === 'github'}
                onChange={() => setRepoSource('github')}
                disabled={loading}
              />
              GitHub URL
            </label>
          </div>

          {repoSource === 'local' && (
            <input
              type="text"
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
              placeholder="/path/to/your/project"
              disabled={loading}
              style={{ marginTop: '0.5rem' }}
            />
          )}

          {repoSource === 'github' && (
            <div style={{ marginTop: '0.5rem' }}>
              <input
                type="text"
                value={githubUrl}
                onChange={(e) => {
                  setGithubUrl(e.target.value)
                  setGithubUrlError(
                    e.target.value && !validateGitHubUrl(e.target.value)
                      ? 'Enter a valid GitHub URL or owner/repo'
                      : '',
                  )
                }}
                placeholder="https://github.com/owner/repo"
                disabled={loading}
              />
              {githubUrlError && <p className="field-error">{githubUrlError}</p>}
              <p className="field-hint">
                Public repositories only. For private repos, configure GITHUB_TOKEN.
              </p>
            </div>
          )}
        </div>

        {introError && (
          <div className="banner banner--error" style={{ marginBottom: '0.75rem' }}>
            {introError}
          </div>
        )}

        <div className="form-actions">
          <button
            type="button"
            className="submit-btn"
            onClick={handleContinue}
            disabled={!canContinue || !!githubUrlError}
          >
            {introLoading ? 'Loading questions…' : 'Continue'}
          </button>
          <button
            type="button"
            className="submit-btn submit-btn--secondary"
            onClick={handleSkip}
            disabled={!taskBrief.trim() || loading}
          >
            Skip and Optimize
          </button>
        </div>
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Step 2 — Clarification
  // -------------------------------------------------------------------------

  return (
    <div>
      <div className="step-header">
        <h3 className="step-title">Clarification</h3>
        <p className="step-subtitle">Answer the questions below to improve prompt quality. Dynamic questions are optional.</p>
      </div>

      <div className="intro-questions">
        {introQuestions.map((q) => (
          <div key={q.id} className="form-group">
            <label>
              {q.question}
              {fixedIds.has(q.id) && <span className="required-mark">*</span>}
            </label>

            {q.type === 'boolean' ? (
              <div className="radio-group">
                {['Evet', 'Hayır'].map((opt) => (
                  <label key={opt} className="radio-label">
                    <input
                      type="radio"
                      name={`intro-${q.id}`}
                      value={opt}
                      checked={introAnswers[q.id] === opt}
                      onChange={() => setAnswer(q.id, opt)}
                      disabled={loading}
                    />
                    {opt}
                  </label>
                ))}
              </div>
            ) : (
              <input
                type="text"
                value={introAnswers[q.id] ?? ''}
                onChange={(e) => setAnswer(q.id, e.target.value)}
                disabled={loading}
              />
            )}
          </div>
        ))}
      </div>

      <div className="form-actions">
        <button
          type="button"
          className="submit-btn"
          onClick={handleOptimize}
          disabled={!canOptimize}
        >
          Optimize
        </button>
        <button
          type="button"
          className="submit-btn submit-btn--secondary"
          onClick={() => onSubmit(buildRequest(false))}
          disabled={loading}
        >
          Skip
        </button>
        <button
          type="button"
          className="submit-btn submit-btn--ghost"
          onClick={handleBack}
          disabled={loading}
        >
          Back
        </button>
      </div>
    </div>
  )
}
