import type {
  Alert,
  Encounter,
  Finding,
  ImagingStudy,
  Patient,
  QueryResult,
} from '../types'

// Empty base => same-origin (dev proxy / docker). Override with VITE_API_URL.
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`Request to ${path} failed (HTTP ${res.status})`)
  }
  return (await res.json()) as T
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`POST ${path} failed (HTTP ${res.status})`)
  }
  return (await res.json()) as T
}

export const api = {
  getPatients: () => getJSON<Patient[]>('/patients'),
  getPatient: (id: string) => getJSON<Patient>(`/patients/${id}`),
  getEncounters: (patientId: string) =>
    getJSON<Encounter[]>(`/encounters?patient_id=${patientId}`),
  getFindings: (patientId: string) =>
    getJSON<Finding[]>(`/findings?patient_id=${patientId}`),
  getAlerts: (patientId: string) =>
    getJSON<Alert[]>(`/alerts?patient_id=${patientId}`),
  getImaging: (patientId: string) =>
    getJSON<ImagingStudy[]>(`/imaging?patient_id=${patientId}`),
  acknowledgeAlert: (alertId: string, acknowledgedBy: string, note: string | null = null) =>
    postJSON<Alert>(`/alerts/${alertId}/acknowledge`, {
      acknowledged_by: acknowledgedBy,
      note,
    }),
  query: (question: string) => postJSON<QueryResult>('/query', { question }),
}
