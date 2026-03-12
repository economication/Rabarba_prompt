/**
 * Typed API client for the Rabarba Prompt backend.
 * All types mirror the OptimizeResponse Pydantic schema exactly.
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

export interface OptimizeRequest {
  task_brief: string
  repo_path?: string | null
  target_agent?: string | null
  max_iterations?: number
}

export interface OptimizeResponse {
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
