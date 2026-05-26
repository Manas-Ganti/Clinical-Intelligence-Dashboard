// Fixed 220px nav. Only Patients is active in Phase 2; the rest are placeholders
// for the domain objects that arrive in Phase 3.
const SECTIONS = ['Patients', 'Encounters', 'Findings', 'Imaging', 'Alerts']

export function LeftSidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        Clinical
        <br />
        Intelligence
      </div>
      <nav className="sidebar__nav">
        {SECTIONS.map((s) => (
          <span
            key={s}
            className={`sidebar__link ${
              s === 'Patients' ? 'sidebar__link--active' : 'sidebar__link--disabled'
            }`}
          >
            {s}
          </span>
        ))}
      </nav>
      <div className="sidebar__foot muted">Phase 2 · vertical slice</div>
    </aside>
  )
}
