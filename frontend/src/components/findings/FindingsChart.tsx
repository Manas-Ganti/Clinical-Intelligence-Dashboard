import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
  type TooltipProps,
} from 'recharts'
import { api } from '../../api/client'
import type { Finding } from '../../types'

// One small-multiple per observation type: same form, same accent, same scaling —
// so the eye compares shapes across metrics instead of decoding four chart styles.
// Each panel is a single series, so none needs a legend; the card title names it.
//
// Axes are dropped by design (these are sparklines, read for trend and outliers,
// not for reading values off a grid). That's only honest because the hover layer
// gives the exact value, date and flag on demand — a chart you can't interrogate
// has no business hiding its numbers.
const ACCENT = '#4C6B8A'

function groupByDisplay(findings: Finding[]): Record<string, Finding[]> {
  const out: Record<string, Finding[]> = {}
  for (const f of findings) {
    if (!out[f.display]) out[f.display] = []
    out[f.display].push(f)
  }
  return out
}

interface Point {
  date: string
  value: number
  unit: string
  flag: string
}

function ChartTip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload as Point
  return (
    <div className="charttip">
      <div className="charttip__val">
        {p.value} {p.unit}
      </div>
      <div className="muted" style={{ fontSize: 12 }}>
        {p.date}
        {p.flag !== 'normal' ? ` · ${p.flag}` : ''}
      </div>
    </div>
  )
}

export function FindingsChart({ patientId }: { patientId: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ['findings', patientId],
    queryFn: () => api.getFindings(patientId),
    staleTime: 30_000,
  })

  if (isPending) return <div className="panel__empty">Loading findings…</div>
  if (error) return <div className="panel__empty">Couldn't load findings.</div>
  if (!data || data.length === 0)
    return <div className="panel__empty">No findings recorded.</div>

  const groups = groupByDisplay(data)

  return (
    <div className="chartgrid">
      {Object.entries(groups).map(([display, findings]) => {
        const points: Point[] = findings.map((f) => ({
          date: f.observed_at.slice(0, 10),
          value: f.value,
          unit: f.unit,
          flag: f.abnormal_flag,
        }))

        return (
          <div className="chartcard" key={display}>
            <div className="chartcard__title">
              {display}{' '}
              <span className="muted" style={{ fontSize: 12 }}>
                ({findings[0].unit})
              </span>
            </div>
            <ResponsiveContainer width="100%" height={100}>
              <AreaChart
                data={points}
                margin={{ top: 6, right: 4, bottom: 0, left: 4 }}
              >
                {/* Sparklines scale to the series, not to zero: a 4 mmol/L swing
                    in potassium is the entire story, and a zero baseline would
                    flatten it into a straight line. */}
                <YAxis hide domain={['dataMin', 'dataMax']} />
                <Tooltip content={<ChartTip />} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={ACCENT}
                  strokeWidth={2}
                  fill={ACCENT}
                  fillOpacity={0.16}
                  dot={{ r: 2.6, fill: '#fff', stroke: ACCENT, strokeWidth: 1.6 }}
                  activeDot={{ r: 4, fill: ACCENT, stroke: '#fff', strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )
      })}
    </div>
  )
}
