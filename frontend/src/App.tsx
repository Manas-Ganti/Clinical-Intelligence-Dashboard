import { LeftSidebar } from './components/layout/LeftSidebar'
import { PatientTable } from './components/patients/PatientTable'
import { QueryBox } from './components/query/QueryBox'

// One section. Everything clinical hangs off a patient — encounters, findings,
// alerts and imaging all live in the expanded row — so a cross-patient section
// per domain object was a second way to reach data the patient list already
// reaches, and a second thing to keep in sync.
export default function App() {
  return (
    <div className="app">
      <LeftSidebar />
      <main className="main">
        <header className="main__header">
          <h1>Patients</h1>
          <p className="muted">
            Multi-source ingestion · normalized into the typed domain model ·
            select a row for clinical detail
          </p>
        </header>
        <QueryBox />
        <PatientTable />
      </main>
    </div>
  )
}
