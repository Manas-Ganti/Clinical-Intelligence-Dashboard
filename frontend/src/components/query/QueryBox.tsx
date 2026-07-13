import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../api/client'

// Natural-language query over the clinical data. The backend routes the question
// to Claude function-calling; we show the answer plus which tools were invoked.
export function QueryBox() {
  const [question, setQuestion] = useState('')
  const ask = useMutation({ mutationFn: (q: string) => api.query(q) })

  return (
    <div style={{ marginBottom: 24 }}>
      <form
        className="querybox"
        onSubmit={(e) => {
          e.preventDefault()
          const q = question.trim()
          if (q) ask.mutate(q)
        }}
      >
        <input
          className="querybox__input"
          placeholder="Ask in plain English — e.g. “Which patients came from FHIR?”"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="btn" type="submit" disabled={ask.isPending}>
          {ask.isPending ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {ask.isError && (
        <div className="state state--error" style={{ marginBottom: 24 }}>
          <strong>Couldn't run the query.</strong>
          <div className="state__hint">
            The natural-language layer needs <code>ANTHROPIC_API_KEY</code> set on
            the server.
          </div>
        </div>
      )}

      {ask.data && (
        <div className="state" style={{ textAlign: 'left', marginBottom: 24 }}>
          <p style={{ margin: 0, color: 'var(--ink)' }}>{ask.data.answer}</p>
          {ask.data.tool_calls.length > 0 && (
            <div className="state__hint">
              Tools used: {ask.data.tool_calls.map((t) => t.name).join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
