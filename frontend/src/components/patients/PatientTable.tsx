import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { Patient } from '../../types'
import { SourceBadge } from '../common/SourceBadge'
import { QualityDot } from '../common/QualityDot'
import { Pagination } from '../common/Pagination'
import { LoadingSkeleton, ErrorCard, EmptyState } from '../common/States'
import { PatientDetail } from './PatientDetail'

const PAGE_SIZE = 25

export function PatientTable() {
  const [page, setPage] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isPending, isFetching, error } = useQuery({
    queryKey: ['patients', page],
    queryFn: () => api.getPatientsPage(PAGE_SIZE, page * PAGE_SIZE),
    staleTime: 30_000,
    // Hold the current page on screen while the next loads, so paging never
    // flashes the skeleton or collapses the table under the cursor.
    placeholderData: keepPreviousData,
  })

  if (isPending) return <LoadingSkeleton />
  if (error) return <ErrorCard message={(error as Error).message} />
  if (!data || data.total === 0) return <EmptyState />

  const toggle = (p: Patient) =>
    setExpandedId((current) => (current === p.id ? null : p.id))

  return (
    <>
      <div className="tablecard">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 36 }} aria-label="data quality" />
              <th>Name</th>
              <th>MRN</th>
              <th style={{ width: 90 }}>Sex</th>
              <th style={{ width: 130 }}>Birth date</th>
              <th style={{ width: 110 }}>Source</th>
            </tr>
          </thead>
          {data.rows.map((p) => {
            const isExpanded = expandedId === p.id
            return (
              <tbody key={p.id}>
                <tr
                  onClick={() => toggle(p)}
                  className={isExpanded ? 'row--expanded' : ''}
                  aria-expanded={isExpanded}
                >
                  <td>
                    <QualityDot score={p.data_quality_score} />
                  </td>
                  <td>
                    <span className="cell-name">
                      {p.given_name} {p.family_name}
                    </span>
                  </td>
                  <td>
                    <span className="cell-mrn" title={p.mrn}>
                      {p.mrn.slice(0, 8)}…
                    </span>
                  </td>
                  <td className="cell-dim" style={{ textTransform: 'capitalize' }}>
                    {p.sex}
                  </td>
                  <td className="cell-dim">{p.birth_date}</td>
                  <td>
                    <SourceBadge source={p.source_system} />
                  </td>
                </tr>

                {/* The clinical detail opens inside the row, so the page you were
                    on stays where it was and the patient stays under the cursor. */}
                {isExpanded && (
                  <tr className="row--inert">
                    <td colSpan={6} style={{ padding: 0 }}>
                      <PatientDetail patient={p} />
                    </td>
                  </tr>
                )}
              </tbody>
            )
          })}
        </table>
      </div>

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={data.total}
        onPage={setPage}
        busy={isFetching}
      />
    </>
  )
}
