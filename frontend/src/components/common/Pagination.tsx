// Pager for the server-paged lists. Deliberately shows the absolute row range
// and total ("101–200 of 1,171") rather than just a page number: with a clinical
// dataset the question is usually "how much am I not looking at", and a bare
// "page 2" doesn't answer it.

interface Props {
  page: number // zero-based
  pageSize: number
  total: number
  onPage: (page: number) => void
  busy?: boolean // a fetch is in flight; keep the current page visible but frozen
}

export function Pagination({ page, pageSize, total, onPage, busy }: Props) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : page * pageSize + 1
  const last = Math.min(total, (page + 1) * pageSize)

  // A single page of results needs no controls.
  if (total <= pageSize) return null

  return (
    <nav className="pager" aria-label="Patient list pages">
      <span className="pager__range">
        <strong>
          {first.toLocaleString()}–{last.toLocaleString()}
        </strong>{' '}
        of {total.toLocaleString()}
      </span>

      <span className="pager__controls">
        <button
          className="pager__btn"
          onClick={() => onPage(0)}
          disabled={page === 0 || busy}
          aria-label="First page"
        >
          ««
        </button>
        <button
          className="pager__btn"
          onClick={() => onPage(page - 1)}
          disabled={page === 0 || busy}
          aria-label="Previous page"
        >
          ‹ Prev
        </button>

        <span className="pager__page" aria-live="polite">
          Page {page + 1} of {pageCount.toLocaleString()}
        </span>

        <button
          className="pager__btn"
          onClick={() => onPage(page + 1)}
          disabled={page >= pageCount - 1 || busy}
          aria-label="Next page"
        >
          Next ›
        </button>
        <button
          className="pager__btn"
          onClick={() => onPage(pageCount - 1)}
          disabled={page >= pageCount - 1 || busy}
          aria-label="Last page"
        >
          »»
        </button>
      </span>
    </nav>
  )
}
