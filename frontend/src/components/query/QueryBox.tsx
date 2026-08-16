import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../../api/client'

// Natural-language query over the clinical data. The backend routes the question
// to whichever model is configured (Claude, or one of the open models VT ARC
// hosts) as function calling; we show the answer, the model that gave it, and
// which tools were invoked.
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
          {/* The server names the credential its configured model needs — which
              differs by provider — so show that rather than guessing at one. */}
          <div className="state__hint">{(ask.error as Error).message}</div>
        </div>
      )}

      {ask.data && (
        <div className="state answer" style={{ textAlign: 'left', marginBottom: 24 }}>
          {/* Models answer in Markdown — tables, **bold**, bullet lists — and
              rendering that as plain text put literal pipes and asterisks on
              screen. remark-gfm is what turns the pipe tables into tables;
              react-markdown escapes raw HTML by default, so model output can't
              inject markup here. */}
          <div className="answer__body">
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Markdown emits a bare <table>, which cannot scroll. Answers
                // about clinical rows carry UUID columns and are routinely wider
                // than the panel, so each table gets its own scroll frame rather
                // than pushing the page sideways.
                table: ({ node: _node, ...props }) => (
                  <div className="answer__tablewrap">
                    <table {...props} />
                  </div>
                ),
              }}
            >
              {ask.data.answer}
            </Markdown>
          </div>
          <div className="state__hint">
            {ask.data.model && <>Model: {ask.data.model}</>}
            {ask.data.model && ask.data.tool_calls.length > 0 && ' · '}
            {ask.data.tool_calls.length > 0 && (
              <>Tools used: {ask.data.tool_calls.map((t) => t.name).join(', ')}</>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
