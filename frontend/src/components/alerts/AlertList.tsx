import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { Alert, AlertSeverity } from '../../types'

const SEVERITY_COLORS: Record<AlertSeverity, string> = {
  info: '#2E75B6',
  warning: '#F59E0B',
  critical: '#EF4444',
}

export function AlertList({ patientId }: { patientId: string }) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['alerts', patientId],
    queryFn: () => api.getAlerts(patientId),
    staleTime: 30_000,
  })

  // Acknowledge writes an audit entry server-side; on success we refetch so the
  // row flips to "acknowledged" with its audit info.
  const ack = useMutation({
    mutationFn: (alertId: string) => api.acknowledgeAlert(alertId, 'demo.user'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts', patientId] }),
  })

  if (isLoading) return <div className="muted">Loading alerts…</div>
  if (error) return <div className="muted">Couldn't load alerts.</div>
  if (!data || data.length === 0) return <div className="muted">No alerts.</div>

  return (
    <ul className="list">
      {data.map((a: Alert) => (
        <li key={a.id} className="list__item">
          <span className="badge" style={{ background: SEVERITY_COLORS[a.severity] }}>
            {a.severity.toUpperCase()}
          </span>
          <span className="list__main">{a.message}</span>
          {a.status === 'active' ? (
            <button
              className="ackbtn"
              onClick={() => ack.mutate(a.id)}
              disabled={ack.isPending}
            >
              Acknowledge
            </button>
          ) : (
            <span
              className="muted"
              title={
                a.audit_trail[0]
                  ? `by ${a.audit_trail[0].acknowledged_by} at ${a.audit_trail[0].acknowledged_at}`
                  : undefined
              }
            >
              ✓ {a.status}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}
