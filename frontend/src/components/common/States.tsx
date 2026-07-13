// Loading / error / empty states. The conventions require all three to be
// handled explicitly — an empty table with no explanation is never acceptable.

export function LoadingSkeleton() {
  return <div className="state">Loading patients…</div>
}

export function ErrorCard({ message }: { message: string }) {
  return (
    <div className="state state--error">
      <strong>Couldn't load patients.</strong>
      <div className="state__hint">{message}</div>
      <div className="state__hint">Is the API running and reachable?</div>
    </div>
  )
}

export function EmptyState() {
  return (
    <div className="state">
      <strong>No patients yet.</strong>
      <div className="state__hint">
        The API seeds on boot — run <code>python scripts/fetch_synthea.py</code>{' '}
        for the real dataset, or it falls back to the sample fixtures.
      </div>
    </div>
  )
}
