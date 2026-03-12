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

export interface OptimizeRequest {
  task_brief: string
  repo_path?: string | null
  target_agent?: string | null
  max_iterations?: number
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

export async function optimizePrompt(
  request: OptimizeRequest,
): Promise<OptimizeResponse> {
  const response = await fetch('/api/optimize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`API error ${response.status}: ${errorText}`)
  }

  return (await response.json()) as OptimizeResponse
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
