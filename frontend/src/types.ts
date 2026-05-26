// Mirrors the Pydantic domain models served by the API. Keeping these in sync is
// the frontend half of the typed contract — change a field in domain/models and
// it should change here too.
export type SourceSystem = 'ehr' | 'fhir_api' | 'csv_upload' | 'pacs'
export type Sex = 'male' | 'female' | 'other' | 'unknown'

interface Envelope {
  id: string
  created_at: string
  updated_at: string
  source_system: SourceSystem
  source_record_id: string
  data_quality_score: number
}

export interface Patient extends Envelope {
  mrn: string
  given_name: string
  family_name: string
  birth_date: string
  sex: Sex
  deceased: boolean
}

export interface Encounter extends Envelope {
  patient_id: string
  encounter_class: string
  status: string
  period_start: string
  period_end: string | null
  reason: string | null
}

export type AbnormalFlag = 'normal' | 'high' | 'low' | 'critical'

export interface Finding extends Envelope {
  patient_id: string
  encounter_id: string | null
  code: string
  display: string
  value: number
  unit: string
  abnormal_flag: AbnormalFlag
  reference_range_low: number | null
  reference_range_high: number | null
  observed_at: string
  raw_value: string | null
  raw_unit: string | null
}

export type AlertSeverity = 'info' | 'warning' | 'critical'
export type AlertStatus = 'active' | 'acknowledged' | 'resolved'

export interface AuditEntry {
  acknowledged_by: string
  acknowledged_at: string
  prior_status: AlertStatus
  new_status: AlertStatus
  note: string | null
}

export interface Alert extends Envelope {
  patient_id: string
  severity: AlertSeverity
  status: AlertStatus
  message: string
  triggered_at: string
  finding_id: string | null
  audit_trail: AuditEntry[]
}

export type Modality = 'CT' | 'MR' | 'US' | 'XR' | 'PET' | 'NM' | 'OTHER'
export type ImageFormat = 'dicom' | 'nifti'

export interface ImagingStudy extends Envelope {
  patient_id: string
  encounter_id: string | null
  modality: Modality
  body_part: string | null
  study_date: string
  series_count: number
  image_uri: string
  source_format: ImageFormat
}

export interface QueryToolCall {
  name: string
  input: Record<string, unknown>
  result: Record<string, unknown>
}

export interface QueryResult {
  answer: string
  tool_calls: QueryToolCall[]
}
