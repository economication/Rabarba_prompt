/**
 * Typed API client for the Rabarba Prompt backend.
 * All types mirror the backend Pydantic schemas exactly.
 */

export interface ReviewIssue {
  code: string
  rubric_item: string
  verdict: 'PASS' | 'FAIL' | 'UNCERTAIN'
  reason: string
  fix_instruction: string
}

export interface HistoryItem {
  iteration: number
  prompt_text: string
  fail_signature: string
  reviewer_verdict: string
}

export interface NodeCostSummary {
  node_name: string
  call_count: number
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
}

export interface IntroQuestion {
  id: string
  question: string
  type: 'text' | 'boolean'
}

export interface OptimizeRequest {
  run_id?: string
  task_brief: string
  repo_path?: string | null
  github_url?: string | null
  target_agent?: string | null
  max_iterations?: number
  intro_questions?: IntroQuestion[] | null
  intro_answers?: Record<string, string> | null
}

export interface OptimizeResponse {
  run_id: string
  final_prompt: string
  fail_signature: string
  stop_reason: string
  iteration_count: number
  risk_summary: string
  review_summary: string
  last_error: string | null
  scan_warnings: string[]
  review_issues: ReviewIssue[]
  history: HistoryItem[]
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
  cost_by_node: NodeCostSummary[]
  is_stable: boolean
}

export interface RunSummary {
  run_id: string
  status: string
  stop_reason: string | null
  task_brief_preview: string
  created_at: string
  updated_at: string
  iteration_count: number
  total_cost_usd: number
}

export interface PromptVersionOut {
  run_id: string
  iteration: number
  source: string
  prompt_text: string
  fail_signature: string
  reviewer_verdict: string
  is_stable: boolean
  created_at: string
}

export interface CostSummary {
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
  by_node: NodeCostSummary[]
}

export interface RunDetailResponse {
  run_id: string
  status: string
  stop_reason: string | null
  task_brief: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
  prompt_versions: PromptVersionOut[]
  cost_summary: CostSummary
  final_result: OptimizeResponse | null
}

export interface IntroRequest {
  task_brief: string
  target_agent?: string | null
}

export interface IntroResponse {
  fixed_questions: IntroQuestion[]
  dynamic_questions: IntroQuestion[]
}

export async function introRequest(request: IntroRequest): Promise<IntroResponse> {
  const response = await fetch('/api/intro', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`API error ${response.status}: ${errorText}`)
  }
  return (await response.json()) as IntroResponse
}

export async function optimizeWithStream(
  request: OptimizeRequest,
  onStageStart: (stage: string, iteration: number) => void,
  onStageComplete: (stage: string, iteration: number, durationMs: number) => void,
  onResult: (response: OptimizeResponse) => void,
  onCancelled: (response: OptimizeResponse) => void,
  onError: (message: string) => void,
): Promise<void> {
  const response = await fetch('/api/optimize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const errorText = await response.text()
    onError(`API error ${response.status}: ${errorText}`)
    return
  }

  if (!response.body) {
    onError('No response body from server')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) continue

      let event: Record<string, unknown>
      try {
        event = JSON.parse(jsonStr)
      } catch {
        continue
      }

      const type = event.type as string
      if (type === 'stage_start') {
        onStageStart(event.stage as string, event.iteration as number)
      } else if (type === 'stage_complete') {
        onStageComplete(
          event.stage as string,
          event.iteration as number,
          event.duration_ms as number,
        )
      } else if (type === 'result') {
        onResult(event.data as OptimizeResponse)
        return
      } else if (type === 'cancelled') {
        onCancelled(event.data as OptimizeResponse)
        return
      } else if (type === 'error') {
        onError(event.message as string)
        return
      }
    }
  }
}

export async function cancelRun(runId: string): Promise<void> {
  await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' })
}

/** @deprecated Use optimizeWithStream instead */
export async function optimizePrompt(
  request: OptimizeRequest,
): Promise<OptimizeResponse> {
  return new Promise((resolve, reject) => {
    optimizeWithStream(
      request,
      () => {},
      () => {},
      resolve,
      resolve,
      reject,
    )
  })
}

export async function listRuns(): Promise<RunSummary[]> {
  const response = await fetch('/api/runs')
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`API error ${response.status}: ${errorText}`)
  }
  return (await response.json()) as RunSummary[]
}

export async function getRun(runId: string): Promise<RunDetailResponse> {
  const response = await fetch(`/api/runs/${runId}`)
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`API error ${response.status}: ${errorText}`)
  }
  return (await response.json()) as RunDetailResponse
}
