import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../../api/client'
import type { Finding } from '../../types'

// Consistent chart theme per the project conventions.
const CHART_COLORS = { primary: '#2E75B6' }

function groupByDisplay(findings: Finding[]): Record<string, Finding[]> {
  const out: Record<string, Finding[]> = {}
  for (const f of findings) {
    if (!out[f.display]) out[f.display] = []
    out[f.display].push(f)
  }
  return out
}

export function FindingsChart({ patientId }: { patientId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['findings', patientId],
    queryFn: () => api.getFindings(patientId),
    staleTime: 30_000,
  })

  if (isLoading) return <div className="muted">Loading findings…</div>
  if (error) return <div className="muted">Couldn't load findings.</div>
  if (!data || data.length === 0) return <div className="muted">No findings recorded.</div>

  const groups = groupByDisplay(data)
  return (
    <div className="charts">
      {Object.entries(groups).map(([display, findings]) => {
        const chartData = findings.map((f) => ({
          date: f.observed_at.slice(0, 10),
          value: f.value,
        }))
        return (
          <div className="chart" key={display}>
            <div className="chart__title">
              {display} <span className="muted">({findings[0].unit})</span>
            </div>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={CHART_COLORS.primary}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )
      })}
    </div>
  )
}
