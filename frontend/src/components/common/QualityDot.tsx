// Small colored dot showing a record's data_quality_score — clean, some coercion,
// or heavily coerced. Surfaces the ingestion-quality signal that rides on every
// domain object straight into the UI.
//
// The dot is never the only carrier of that meaning: the title gives the actual
// percentage, so the score is available to anyone the color doesn't reach.
export function QualityDot({ score }: { score: number }) {
  const color =
    score >= 0.9
      ? 'var(--status-normal)'
      : score >= 0.7
        ? 'var(--status-warning)'
        : 'var(--status-critical)'

  return (
    <span
      className="qualitydot"
      title={`data quality ${Math.round(score * 100)}%`}
      style={{ background: color }}
    />
  )
}
