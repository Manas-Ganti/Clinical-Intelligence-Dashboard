import type { Patient } from '../../types'
import { SourceBadge } from '../common/SourceBadge'
import { EncounterList } from '../encounters/EncounterList'
import { FindingsChart } from '../findings/FindingsChart'
import { AlertList } from '../alerts/AlertList'
import { ImagingList } from '../imaging/ImagingList'

// The clinical detail for one patient, rendered *inside* their table row rather
// than in a panel below the table. That's the point of the accordion: the row
// stays where it is, the page you were on stays where it was, and the patient you
// opened is still under the cursor that opened them.
//
// The design's expanded row carries FINDINGS + ENCOUNTERS. Alerts and Imaging are
// kept in the side column too — dropping them would quietly delete the audited
// acknowledge workflow, which is a feature, not decoration.
export function PatientDetail({ patient }: { patient: Patient }) {
  return (
    <div className="expando">
      {/* The table truncates the MRN to keep a UUID from crowding out the
          clinical columns, so opening the patient is where the full identifier
          has to appear — it's the value you'd paste into another system. */}
      <header className="expando__head">
        <span className="expando__name">
          {patient.given_name} {patient.family_name}
        </span>
        <span className="expando__meta">
          MRN <span className="expando__mrn">{patient.mrn}</span>
        </span>
        <span className="expando__meta">
          <span className="cap">{patient.sex}</span> · born {patient.birth_date}
          {patient.deceased ? ' · deceased' : ''}
        </span>
        <SourceBadge source={patient.source_system} />
      </header>

      <div className="expando__body">
        <div className="expando__main">
          <div className="sectionlabel">FINDINGS</div>
          <FindingsChart patientId={patient.id} />
        </div>

        <div className="expando__side">
          <div>
            <div className="sectionlabel">ENCOUNTERS</div>
            <EncounterList patientId={patient.id} />
          </div>
          <div>
            <div className="sectionlabel">ALERTS</div>
            <AlertList patientId={patient.id} />
          </div>
          <div>
            <div className="sectionlabel">IMAGING</div>
            <ImagingList patientId={patient.id} />
          </div>
        </div>
      </div>
    </div>
  )
}
