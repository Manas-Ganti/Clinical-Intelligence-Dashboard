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

// A path the dev proxy doesn't know about falls through to Vite's SPA fallback,
// which returns 200 with index.html — so res.ok is true and the failure only
// shows up as an unhelpful JSON parse error. Check the content type and say what
// actually went wrong.
async function parseJSON<T>(res: Response, path: string): Promise<T> {
  const contentType = res.headers.get('Content-Type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new Error(
      `Expected JSON from ${path} but got "${contentType}" — is the API running ` +
        `and is this path proxied in vite.config.ts?`,
    )
  }
  return (await res.json()) as T
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`Request to ${path} failed (HTTP ${res.status})`)
  }
  return parseJSON<T>(res, path)
}

// The list endpoints are paged (see backend/pagination.py) — a real Synthea load
// is ~150k findings, so the API caps any single response. That cap must never
// become silent data loss: 29% of patients have more than one page of findings,
// and a chart quietly missing half a patient's labs is worse than no chart. So
// collection reads walk every page, using the X-Total-Count header to know when
// to stop. Per-patient volumes are bounded (a few thousand rows at most), so
// this is one or two extra requests, not an unbounded crawl.
const PAGE_SIZE = 1000 // backend MAX_LIMIT

export interface Page<T> {
  rows: T[]
  total: number // the unpaged total, from X-Total-Count
}

// One page, for lists the user pages through by hand (the patient table). The
// counterpart to getAllPages: use this when the UI shows a slice, and that one
// when a component needs the whole series (a chart cannot plot page 1 of 3).
async function getPage<T>(
  path: string,
  limit: number,
  offset: number,
): Promise<Page<T>> {
  const sep = path.includes('?') ? '&' : '?'
  const res = await fetch(`${BASE}${path}${sep}limit=${limit}&offset=${offset}`)
  if (!res.ok) {
    throw new Error(`Request to ${path} failed (HTTP ${res.status})`)
  }
  const rows = await parseJSON<T[]>(res, path)
  const header = res.headers.get('X-Total-Count')
  return { rows, total: header === null ? rows.length : Number(header) }
}

async function getAllPages<T>(path: string): Promise<T[]> {
  const sep = path.includes('?') ? '&' : '?'
  const rows: T[] = []
  let offset = 0
  let total = Infinity

  while (offset < total) {
    const res = await fetch(`${BASE}${path}${sep}limit=${PAGE_SIZE}&offset=${offset}`)
    if (!res.ok) {
      throw new Error(`Request to ${path} failed (HTTP ${res.status})`)
    }
    const page = await parseJSON<T[]>(res, path)
    rows.push(...page)

    const header = res.headers.get('X-Total-Count')
    total = header === null ? rows.length : Number(header)
    // Defensive: a short page means the server has nothing more to give, and
    // trusting the header alone here would spin forever if it ever disagreed.
    if (page.length === 0) break
    offset += page.length
  }
  return rows
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
  // The patient list is paged in the UI — at 1,171 patients (and growing with the
  // dataset) rendering every row at once is a wall, not a table.
  getPatientsPage: (limit: number, offset: number) =>
    getPage<Patient>('/patients', limit, offset),
  getPatient: (id: string) => getJSON<Patient>(`/patients/${id}`),

  // Everything below is read for one patient, to fill their expanded row.
  getEncounters: (patientId: string) =>
    getAllPages<Encounter>(`/encounters?patient_id=${patientId}`),
  getFindings: (patientId: string) =>
    getAllPages<Finding>(`/findings?patient_id=${patientId}`),
  getAlerts: (patientId: string) =>
    getAllPages<Alert>(`/alerts?patient_id=${patientId}`),
  getImaging: (patientId: string) =>
    getAllPages<ImagingStudy>(`/imaging?patient_id=${patientId}`),
  acknowledgeAlert: (alertId: string, acknowledgedBy: string, note: string | null = null) =>
    postJSON<Alert>(`/alerts/${alertId}/acknowledge`, {
      acknowledged_by: acknowledgedBy,
      note,
    }),
  query: (question: string) => postJSON<QueryResult>('/query', { question }),
}
