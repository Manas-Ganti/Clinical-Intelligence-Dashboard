import { useQuery } from '@tanstack/react-query'
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from 'recharts'
import { api } from '../../api/client'
import type { Finding } from '../../types'

// One small-multiple per observation type: same form, same accent, same scaling,
// so the eye compares shapes across metrics instead of decoding chart styles.
// Each panel is a single series, so none needs a legend — the card title names it.
//
// Axes are hidden by design (these are sparklines: read for trend and outliers,
// not for reading values off a grid). That is only honest because the hover layer
// gives the exact value, date and flag on demand.
const ACCENT = '#4C6B8A'

// Past this many observations a dot-per-point sparkline stops being a chart and
// becomes a smear: the worst patient here has 228 glucose readings, and 228 marks
// across ~260px is roughly one pixel each. Denser series are aggregated into
// equal-time buckets instead — a median line inside a min–max band, which shows
// the trend AND the spread that the overplotted version was destroying.
const DENSE_THRESHOLD = 48
const BUCKETS = 40

interface Raw {
  t: number // epoch ms — the x scale is real time, not row order
  value: number
  flag: string
}

interface Point {
  t: number
  value: number // the reading, or the bucket median
  band?: [number, number] // min–max within the bucket (aggregated series only)
  n?: number // observations in the bucket
  flag?: string
  lo?: number
  hi?: number
}

// Averaging an even-sized bucket lands on values like 3.3499999999999996. A lab
// result is never displayed like that, so the median is rounded to the precision
// the source actually reported rather than to whatever the float landed on.
function round(x: number, decimals: number): number {
  const f = 10 ** decimals
  return Math.round(x * f) / f
}

function decimalsIn(xs: number[]): number {
  return xs.reduce((max, x) => {
    const dot = String(x).indexOf('.')
    return Math.max(max, dot === -1 ? 0 : String(x).length - dot - 1)
  }, 0)
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length >> 1
  const raw = s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
  return round(raw, decimalsIn(xs))
}

/** Collapse a dense series into equal-time buckets of median + min/max. */
function bucketByTime(raw: Raw[]): Point[] {
  const t0 = raw[0].t
  const tN = raw[raw.length - 1].t
  const span = tN - t0 || 1
  const width = span / BUCKETS

  const buckets = new Map<number, Raw[]>()
  for (const r of raw) {
    // Clamp the final point into the last bucket rather than opening a 41st.
    const i = Math.min(BUCKETS - 1, Math.floor((r.t - t0) / width))
    const b = buckets.get(i)
    if (b) b.push(r)
    else buckets.set(i, [r])
  }

  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([i, rows]) => {
      const values = rows.map((r) => r.value)
      const lo = Math.min(...values)
      const hi = Math.max(...values)
      return {
        // Bucket midpoint, so x stays proportional to real time.
        t: t0 + (i + 0.5) * width,
        value: median(values),
        band: [lo, hi] as [number, number],
        lo,
        hi,
        n: rows.length,
      }
    })
}

function groupByDisplay(findings: Finding[]): Record<string, Finding[]> {
  const out: Record<string, Finding[]> = {}
  for (const f of findings) {
    if (!out[f.display]) out[f.display] = []
    out[f.display].push(f)
  }
  return out
}

const fmtDate = (t: number) => new Date(t).toISOString().slice(0, 10)

function ChartTip({
  active,
  payload,
  unit,
  aggregated,
}: TooltipProps<number, string> & { unit: string; aggregated: boolean }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload as Point

  return (
    <div className="charttip">
      {aggregated ? (
        <>
          <div className="charttip__val">
            median {p.value} {unit}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            range {p.lo}–{p.hi} · {p.n} obs
          </div>
        </>
      ) : (
        <div className="charttip__val">
          {p.value} {unit}
        </div>
      )}
      <div className="muted" style={{ fontSize: 12 }}>
        {fmtDate(p.t)}
        {!aggregated && p.flag && p.flag !== 'normal' ? ` · ${p.flag}` : ''}
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
        const unit = findings[0].unit

        const raw: Raw[] = findings
          .map((f) => ({
            t: Date.parse(f.observed_at),
            value: f.value,
            flag: f.abnormal_flag,
          }))
          .sort((a, b) => a.t - b.t)

        const aggregated = raw.length > DENSE_THRESHOLD
        const points: Point[] = aggregated ? bucketByTime(raw) : raw

        return (
          <div className="chartcard" key={display}>
            <div className="chartcard__title">
              {display}{' '}
              <span className="muted" style={{ fontSize: 12 }}>
                ({unit})
              </span>
            </div>

            {/* Never hide the transform: if the series was aggregated, the card
                says so, with the reading count it was aggregated from. */}
            <div className="chartcard__note">
              {aggregated
                ? `${raw.length} readings · median, min–max band`
                : `${raw.length} reading${raw.length === 1 ? '' : 's'}`}
            </div>

            <ResponsiveContainer width="100%" height={100}>
              <ComposedChart
                data={points}
                margin={{ top: 6, right: 4, bottom: 0, left: 4 }}
              >
                {/* A real time scale, not row order: observations are irregular,
                    and spacing them evenly would draw a decade-long gap the same
                    width as a week. */}
                <XAxis
                  type="number"
                  dataKey="t"
                  domain={['dataMin', 'dataMax']}
                  hide
                />
                {/* Scale to the series, not to zero — a 4 mmol/L swing in
                    potassium is the whole story, and a zero baseline flattens it
                    into a straight line. */}
                <YAxis hide domain={['dataMin', 'dataMax']} />
                <Tooltip
                  content={<ChartTip unit={unit} aggregated={aggregated} />}
                />

                {aggregated ? (
                  <>
                    <Area
                      dataKey="band"
                      stroke="none"
                      fill={ACCENT}
                      fillOpacity={0.18}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke={ACCENT}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{
                        r: 4,
                        fill: ACCENT,
                        stroke: '#fff',
                        strokeWidth: 2,
                      }}
                      isAnimationActive={false}
                    />
                  </>
                ) : (
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
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )
      })}
    </div>
  )
}
