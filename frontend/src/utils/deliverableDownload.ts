/**
 * Deliverable file download interceptor (global)
 *
 * Background: Download link in smart assistant reply (/api/assistant/deliverables/*.xlsx) Yes
 * <a> tag, the browser navigates directly without the Authorization header (JWT is stored in localStorage, only
 * XHR/fetch will be carried), the link in the historical message will be clicked 401"Not logged in or your login has expired". 
 *
 * Solution: Document capture phase global delegation, intercept the click of this type of link, use fetch
 *  (Trigger browser download as blob after request (with JWT header).
 *   - Old links in historical messages (without signature)→ fetch bring JWT → Downloadable
 *   - New signature link (?exp=&sig=) → Follow this path and behave the same way
 *   - Not logged in/expired → Prompt user to log in again
 *
 * Global one-time binding, covering smart assistant homepage, floating assistant, stock details page, etc.
 * The position where markdown messages are rendered, and subsequent new entries do not need to be rewired.
 */

// Match the intelligent assistant deliverable download link (either relative path or absolute path)
const DELIVERABLE_HREF_PATTERN = /\/api\/assistant\/deliverables\//

/** Extract filename from Content-Disposition (supports RFC 5987 filename* with ordinary filename) */
function extractFilename(
  contentDisposition: string | null,
  fallbackHref: string
): string {
  if (contentDisposition) {
    // filename*=UTF-8''%E8%B5%9B... Priority (FastAPI uses this format for Chinese file names)
    const starMatch = contentDisposition.match(/filename\*=(?:UTF-8''|utf-8'')([^;]+)/i)
    if (starMatch) {
      try {
        return decodeURIComponent(starMatch[1].replace(/["']/g, '').trim())
      } catch {
        /* fallthrough */
      }
    }
    const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
    if (plainMatch) {
      try {
        return decodeURIComponent(plainMatch[1].trim())
      } catch {
        return plainMatch[1].trim()
      }
    }
  }
  // fallback: URL path final section
  try {
    const path = fallbackHref.split('?')[0]
    return decodeURIComponent(path.substring(path.lastIndexOf('/') + 1)) || 'download.xlsx'
  } catch {
    return 'download.xlsx'
  }
}

async function downloadDeliverable(href: string): Promise<void> {
  // Dynamic introduction avoids the hard dependence of the utils layer on pinia (the request.ts system is responsible for token expiration refresh,
  // Here, localStorage is read directly, keeping the same value chain as request.ts)
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()
  const token = authStore.token || localStorage.getItem('auth-token')

  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  try {
    const resp = await fetch(href, { headers, credentials: 'include' })

    if (resp.status === 401) {
      const { ElMessage } = await import('element-plus')
      ElMessage.error('Login has expired, please log in again and click download again')
      return
    }
    if (!resp.ok) {
      const { ElMessage } = await import('element-plus')
      ElMessage.error(`Download failed (HTTP ${resp.status}) , Please re-export and try again`)
      return
    }

    const blob = await resp.blob()
    const filename = extractFilename(resp.headers.get('content-disposition'), href)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('[deliverableDownload] Download failed:', err)
    const { ElMessage } = await import('element-plus')
    ElMessage.error('Download failed, please check the network and try again')
  }
}

let installed = false

/** Install global deliverable download interception (idempotent, called once at the application entry) */
export function setupDeliverableDownloadInterceptor(): void {
  if (installed) return
  installed = true

  document.addEventListener(
    'click',
    (event) => {
      // Interception during the capture phase, before browser navigation
      const target = event.target as HTMLElement | null
      const anchor = target?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!anchor) return

      const href = anchor.getAttribute('href') || ''
      if (!DELIVERABLE_HREF_PATTERN.test(href)) return

      event.preventDefault()
      event.stopPropagation()
      void downloadDeliverable(href)
    },
    true
  )
}
