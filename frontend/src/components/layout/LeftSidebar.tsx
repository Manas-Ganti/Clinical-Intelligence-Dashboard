// Fixed 240px nav. Patients is the only section: every other domain object is
// reached through the patient it belongs to, in the expanded row.
export function LeftSidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        Clinical
        <br />
        Intelligence
      </div>
      <nav className="sidebar__nav">
        <span
          className="sidebar__link sidebar__link--active"
          aria-current="page"
        >
          <span className="sidebar__dot" />
          <span>Patients</span>
        </span>
      </nav>
      <div className="sidebar__foot">Synthea · 1,171 patients</div>
    </aside>
  )
}
