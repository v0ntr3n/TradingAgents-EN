import request from './request'

export interface CapabilityIndexState {
  sync_mode?: string
  total_documents?: number
  indexed_documents?: number
  skipped_documents?: number
  vector_backend?: string
  fingerprint?: string
  [key: string]: unknown
}

export interface RebuildResult {
  sync_mode: string
  total_documents: number
  indexed_documents: number
  skipped_documents: number
  vector_backend: string
}

/** Get the current status of the capability index */
export function getCapabilityIndexState() {
  return request.get('/api/capability-index/state')
}

/** Force index rebuild capability */
export function rebuildCapabilityIndex() {
  return request.post('/api/capability-index/rebuild')
}
