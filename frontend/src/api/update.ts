/**
 * System update API
 */
import request from '@/api/request'

/** Build information */
export interface BuildInfo {
  build_type?: string
  version?: string
  build_date?: string
  git_commit?: string
  full_version?: string
}

/** Version information */
export interface VersionInfo {
  current_version: string
  build_info: BuildInfo
  update_channel?: string
  /** Docker environment */
  is_docker?: boolean
  /** Whether to support in-app updates (Windows portable version/installation version) */
  supports_in_app_update?: boolean
}

/** Update information */
export interface UpdateInfo {
  has_update: boolean
  latest_version: string
  package_type?: 'installer' | 'update'
  download_url: string
  file_size: number
  sha256: string
  release_notes: string
  release_date: string
  is_mandatory: boolean
  min_version: string
  /** The check failed (for example, the server cannot be connected) */
  check_failed?: boolean
  /** Error message */
  error_message?: string
}

/** Download progress */
export interface DownloadProgress {
  status: string       // idle | downloading | completed | failed | verify_failed
  version?: string
  total?: number
  downloaded?: number
  percent?: number
}

/** Get current version information */
export function getVersionInfo() {
  return request<VersionInfo>({
    url: '/api/system/update/info',
    method: 'get'
  })
}

/** Check for updates */
export function checkUpdate() {
  return request<UpdateInfo>({
    url: '/api/system/update/check',
    method: 'get'
  })
}

/** Get download progress */
export function getDownloadProgress() {
  return request<DownloadProgress>({
    url: '/api/system/update/progress',
    method: 'get'
  })
}

/** Start downloading update package */
export function downloadUpdate() {
  return request({
    url: '/api/system/update/download',
    method: 'post'
  })
}

/** Apply updates (service will restart) */
export function applyUpdate() {
  return request({
    url: '/api/system/update/apply',
    method: 'post'
  })
}

