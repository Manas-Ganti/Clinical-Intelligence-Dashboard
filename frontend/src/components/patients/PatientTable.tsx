import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { Patient } from '../../types'
import { SourceBadge } from '../common/SourceBadge'
import { QualityDot } from '../common/QualityDot'
import { LoadingSkeleton, ErrorCard, EmptyState } from '../common/States'

interface Props {
  onSelect: (p: Patient) => void
  selectedId: string | null
}

export function PatientTable({ onSelect, selectedId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['patients'],
    queryFn: api.getPatients,
    staleTime: 30_000,
  })

  if (isLoading) return <LoadingSkeleton />
  if (error) return <ErrorCard message={(error as Error).message} />
  if (!data || data.length === 0) return <EmptyState />

  return (
    <table className="table">
      <thead>
        <tr>
          <th aria-label="data quality" />
          <th>MRN</th>
          <th>Name</th>
          <th>Sex</th>
          <th>Birth date</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {data.map((p) => (
          <tr
            key={p.id}
            className={selectedId === p.id ? 'row--selected' : ''}
            onClick={() => onSelect(p)}
          >
            <td>
              <QualityDot score={p.data_quality_score} />
            </td>
            <td>{p.mrn}</td>
            <td>
              {p.given_name} {p.family_name}
            </td>
            <td>{p.sex}</td>
            <td>{p.birth_date}</td>
            <td>
              <SourceBadge source={p.source_system} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
