import type { SourceSystem } from '../../types'

// One color per source so provenance is visible at a glance on every record.
// Rendered as a tinted pill (design system) rather than a solid fill — a table of
// solid badges reads as a row of alarms, and provenance is context, not alarm.
const SOURCE_COLORS: Record<SourceSystem, string> = {
  ehr: 'var(--source-ehr)',
  fhir_api: 'var(--source-fhir)',
  csv_upload: 'var(--source-other)',
  pacs: 'var(--source-other)',
}

const SOURCE_LABELS: Record<SourceSystem, string> = {
  ehr: 'EHR',
  fhir_api: 'FHIR',
  csv_upload: 'CSV',
  pacs: 'PACS',
}

export function SourceBadge({ source }: { source: SourceSystem }) {
  const color = SOURCE_COLORS[source] ?? 'var(--muted)'
  return (
    <span
      className="badge"
      style={{ color, background: `color-mix(in srgb, ${color} 16%, white)` }}
    >
      {SOURCE_LABELS[source] ?? source.toUpperCase()}
    </span>
  )
}
