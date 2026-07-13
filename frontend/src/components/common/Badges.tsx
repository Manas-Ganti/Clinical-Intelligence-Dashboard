import type { AbnormalFlag, AlertSeverity } from '../../types'

// Status encodings live here, once. They are reserved: never reused to tell one
// series from another, and always shipped with their word, so a reader who can't
// separate the hues still gets the state.

const FLAG_COLORS: Record<AbnormalFlag, string> = {
  normal: 'var(--status-normal)',
  low: 'var(--status-warning)',
  high: 'var(--status-warning)',
  critical: 'var(--status-critical)',
}

export function FlagBadge({ flag }: { flag: AbnormalFlag }) {
  const color = FLAG_COLORS[flag]
  return (
    <span
      className="badge"
      style={{ color, background: `color-mix(in srgb, ${color} 16%, white)` }}
    >
      {flag.toUpperCase()}
    </span>
  )
}

const SEVERITY_COLORS: Record<AlertSeverity, string> = {
  info: 'var(--accent)',
  warning: 'var(--status-warning)',
  critical: 'var(--status-critical)',
}

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const color = SEVERITY_COLORS[severity]
  return (
    <span
      className="badge"
      style={{ color, background: `color-mix(in srgb, ${color} 16%, white)` }}
    >
      {severity.toUpperCase()}
    </span>
  )
}

// Encounter classes are identity, not status — they get the design's muted tints
// rather than the reserved status hues.
const CLASS_COLORS: Record<string, string> = {
  wellness: '#4C6B4A',
  ambulatory: 'var(--accent)',
  outpatient: 'var(--accent)',
  emergency: '#B23A2E',
  urgent_care: '#946B2D',
  inpatient: '#946B2D',
  virtual: '#6B5B8A',
}

export function ClassTag({ value }: { value: string }) {
  const color = CLASS_COLORS[value] ?? 'var(--muted)'
  return (
    <span
      className="tag"
      style={{ color, background: `color-mix(in srgb, ${color} 14%, white)` }}
    >
      {value.replace('_', ' ')}
    </span>
  )
}
