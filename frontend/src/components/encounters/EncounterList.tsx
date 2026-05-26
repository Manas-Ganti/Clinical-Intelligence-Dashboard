import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export function EncounterList({ patientId }: { patientId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['encounters', patientId],
    queryFn: () => api.getEncounters(patientId),
    staleTime: 30_000,
  })

  if (isLoading) return <div className="muted">Loading encounters…</div>
  if (error) return <div className="muted">Couldn't load encounters.</div>
  if (!data || data.length === 0) return <div className="muted">No encounters.</div>

  return (
    <ul className="list">
      {data.map((e) => (
        <li key={e.id} className="list__item">
          <span className="tag">{e.encounter_class}</span>
          <span className="list__main">{e.reason ?? '—'}</span>
          <span className="muted">{e.period_start.slice(0, 10)}</span>
        </li>
      ))}
    </ul>
  )
}
