import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export function ImagingList({ patientId }: { patientId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['imaging', patientId],
    queryFn: () => api.getImaging(patientId),
    staleTime: 30_000,
  })

  if (isLoading) return <div className="muted">Loading imaging…</div>
  if (error) return <div className="muted">Couldn't load imaging.</div>
  if (!data || data.length === 0) return <div className="muted">No imaging studies.</div>

  return (
    <ul className="list">
      {data.map((s) => (
        <li key={s.id} className="list__item">
          <span className="tag">{s.modality}</span>
          <span className="list__main">{s.body_part ?? '—'}</span>
          <span className="badge" style={{ background: '#7C3AED' }}>
            {s.source_format.toUpperCase()}
          </span>
          <span className="muted">{s.study_date.slice(0, 10)}</span>
        </li>
      ))}
    </ul>
  )
}
