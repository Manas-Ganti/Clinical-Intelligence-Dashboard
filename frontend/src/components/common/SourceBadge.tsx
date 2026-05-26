import type { SourceSystem } from '../../types'

// One color per source so provenance is visible at a glance on every record.
const SOURCE_COLORS: Record<SourceSystem, string> = {
  ehr: '#2E75B6',
  fhir_api: '#10B981',
  csv_upload: '#F59E0B',
  pacs: '#7C3AED',
}

export function SourceBadge({ source }: { source: SourceSystem }) {
  return (
    <span className="badge" style={{ background: SOURCE_COLORS[source] ?? '#888' }}>
      {source.toUpperCase()}
    </span>
  )
}
