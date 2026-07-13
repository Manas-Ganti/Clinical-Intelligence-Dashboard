import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { SeverityBadge } from '../common/Badges'

export function AlertList({ patientId }: { patientId: string }) {
  const qc = useQueryClient()
  const { data, isPending, error } = useQuery({
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

  if (isPending) return <div className="panel__empty">Loading alerts…</div>
  if (error) return <div className="panel__empty">Couldn't load alerts.</div>
  if (!data || data.length === 0)
    return <div className="panel__empty">No alerts.</div>

  return (
    <div className="panel">
      {data.map((a) => (
        <div className="panel__row" key={a.id}>
          <SeverityBadge severity={a.severity} />
          <span className="panel__main">{a.message}</span>
          {a.status === 'active' ? (
            <button
              className="ackbtn"
              onClick={(ev) => {
                ev.stopPropagation() // the row behind this opens/closes the patient
                ack.mutate(a.id)
              }}
              disabled={ack.isPending}
            >
              Acknowledge
            </button>
          ) : (
            <span
              className="panel__meta"
              title={
                a.audit_trail[0]
                  ? `by ${a.audit_trail[0].acknowledged_by} at ${a.audit_trail[0].acknowledged_at}`
                  : undefined
              }
            >
              ✓ {a.status}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
