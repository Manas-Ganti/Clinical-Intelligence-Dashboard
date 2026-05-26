// Small colored dot showing a record's data_quality_score — green (clean),
// amber (some coercion), red (lots). Surfaces the ingestion-quality signal that
// rides on every domain object straight into the UI.
export function QualityDot({ score }: { score: number }) {
  const color = score >= 0.9 ? '#10B981' : score >= 0.7 ? '#F59E0B' : '#EF4444'
  return (
    <span
      title={`data quality ${Math.round(score * 100)}%`}
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: 8,
        background: color,
      }}
    />
  )
}
