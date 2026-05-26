import { useState } from 'react'
import { LeftSidebar } from './components/layout/LeftSidebar'
import { PatientTable } from './components/patients/PatientTable'
import { PatientDetail } from './components/patients/PatientDetail'
import { QueryBox } from './components/query/QueryBox'
import type { Patient } from './types'

export default function App() {
  const [selected, setSelected] = useState<Patient | null>(null)

  return (
    <div className="app">
      <LeftSidebar />
      <main className="main">
        <header className="main__header">
          <h1>Patients</h1>
          <p className="muted">
            Ingested from CSV · normalized into the typed domain model · select a
            row for clinical detail
          </p>
        </header>
        <QueryBox />
        <PatientTable onSelect={setSelected} selectedId={selected?.id ?? null} />
        {selected && <PatientDetail patient={selected} />}
      </main>
    </div>
  )
}
