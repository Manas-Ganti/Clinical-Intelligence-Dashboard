// Loading / error / empty states. The conventions require all three to be
// handled explicitly — an empty table with no explanation is never acceptable.

export function LoadingSkeleton() {
  return <div className="state">Loading patients…</div>
}

export function ErrorCard({ message }: { message: string }) {
  return (
    <div className="state state--error">
      <strong>Couldn't load patients.</strong>
      <div className="muted">{message}</div>
      <div className="muted">Is the API running and reachable?</div>
    </div>
  )
}

export function EmptyState() {
  return (
    <div className="state">
      <strong>No patients yet.</strong>
      <div className="muted">
        Expected sample patients seeded from{' '}
        <code>ingestion/sample_data/patients.csv</code>. The table fills in once
        the API has ingested them.
      </div>
    </div>
  )
}
