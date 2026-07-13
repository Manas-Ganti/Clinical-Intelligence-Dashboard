import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export function ImagingList({ patientId }: { patientId: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ['imaging', patientId],
    queryFn: () => api.getImaging(patientId),
    staleTime: 30_000,
  })

  if (isPending) return <div className="panel__empty">Loading imaging…</div>
  if (error) return <div className="panel__empty">Couldn't load imaging.</div>
  if (!data || data.length === 0)
    return <div className="panel__empty">No imaging studies.</div>

  return (
    <div className="panel">
      {data.map((s) => (
        <div className="panel__row" key={s.id}>
          <span
            className="tag"
            style={{
              color: 'var(--accent)',
              background: 'color-mix(in srgb, var(--accent) 14%, white)',
            }}
          >
            {s.modality}
          </span>
          <span className="panel__main">{s.body_part ?? '—'}</span>
          {/* Synthea ships study metadata but no pixels; saying so beats a fake
              thumbnail. The blob location it would occupy is in the title. */}
          <span className="panel__meta" title={s.image_uri}>
            no pixels
          </span>
          <span className="panel__meta">{s.study_date.slice(0, 10)}</span>
        </div>
      ))}
    </div>
  )
}
