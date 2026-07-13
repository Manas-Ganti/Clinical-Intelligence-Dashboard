import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { ClassTag } from '../common/Badges'

export function EncounterList({ patientId }: { patientId: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ['encounters', patientId],
    queryFn: () => api.getEncounters(patientId),
    staleTime: 30_000,
  })

  if (isPending) return <div className="panel__empty">Loading encounters…</div>
  if (error) return <div className="panel__empty">Couldn't load encounters.</div>
  if (!data || data.length === 0)
    return <div className="panel__empty">No encounters.</div>

  return (
    <div className="panel">
      {data.map((e) => (
        <div className="panel__row" key={e.id}>
          <ClassTag value={e.encounter_class} />
          <span className="panel__main">{e.reason ?? '—'}</span>
          <span className="panel__meta">{e.period_start.slice(0, 10)}</span>
        </div>
      ))}
    </div>
  )
}
