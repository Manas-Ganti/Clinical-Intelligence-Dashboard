import type { Patient } from '../../types'
import { SourceBadge } from '../common/SourceBadge'
import { EncounterList } from '../encounters/EncounterList'
import { FindingsChart } from '../findings/FindingsChart'
import { AlertList } from '../alerts/AlertList'
import { ImagingList } from '../imaging/ImagingList'

// Shown in the main area when a patient is selected. Renders the related clinical
// objects, each fetched by patient id — exercising the relationships end to end.
export function PatientDetail({ patient }: { patient: Patient }) {
  return (
    <section className="detailpanel">
      <header className="detailpanel__head">
        <h2>
          {patient.given_name} {patient.family_name}
        </h2>
        <span className="muted">
          MRN {patient.mrn} · {patient.sex} · born {patient.birth_date}
        </span>
        <SourceBadge source={patient.source_system} />
      </header>
      <div className="detailgrid">
        <div className="card">
          <h3>Findings</h3>
          <FindingsChart patientId={patient.id} />
        </div>
        <div className="card">
          <h3>Encounters</h3>
          <EncounterList patientId={patient.id} />
        </div>
        <div className="card">
          <h3>Alerts</h3>
          <AlertList patientId={patient.id} />
        </div>
        <div className="card">
          <h3>Imaging</h3>
          <ImagingList patientId={patient.id} />
        </div>
      </div>
    </section>
  )
}
