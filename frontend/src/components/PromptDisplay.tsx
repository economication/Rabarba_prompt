import { useState } from 'react'

interface Props {
  prompt: string
}

export default function PromptDisplay({ prompt }: Props) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(prompt)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback for environments without clipboard API
      const el = document.createElement('textarea')
      el.value = prompt
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="prompt-display">
      <div className="prompt-header">
        <span className="section-label">Final Prompt</span>
        <button
          type="button"
          className={`copy-btn ${copied ? 'copy-btn--copied' : ''}`}
          onClick={handleCopy}
          disabled={!prompt}
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <textarea
        className="prompt-textarea"
        readOnly
        value={prompt || '(no prompt generated)'}
        aria-label="Final optimized prompt"
      />
    </div>
  )
}
