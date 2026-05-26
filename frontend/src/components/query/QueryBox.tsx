import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../api/client'

// Natural-language query over the clinical data. The backend routes the question
// to Claude function-calling; we show the answer plus which tools were invoked.
export function QueryBox() {
  const [question, setQuestion] = useState('')
  const ask = useMutation({ mutationFn: (q: string) => api.query(q) })

  return (
    <div className="querybox">
      <form
        className="querybox__form"
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
        <button className="querybox__btn" type="submit" disabled={ask.isPending}>
          {ask.isPending ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {ask.isError && (
        <div className="querybox__note muted">
          Couldn't run the query — the natural-language layer needs{' '}
          <code>ANTHROPIC_API_KEY</code> set on the server.
        </div>
      )}

      {ask.data && (
        <div className="querybox__answer">
          <p>{ask.data.answer}</p>
          {ask.data.tool_calls.length > 0 && (
            <div className="querybox__tools muted">
              Tools used: {ask.data.tool_calls.map((t) => t.name).join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
