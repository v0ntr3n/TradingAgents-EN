/**
 * Date and time utility functions
 * Unified processing of time conversion and display
 *
 * Processing logic:
 * 1. If the time string contains time zone information (+08:00 or Z), use directly
 * 2. 🔥 If the time string has no time zone information, it is assumed to be UTC+8 time (the backend has been stored as UTC+8) 
 * 3. The final unified display is China time zone (Asia/Shanghai)
 *
 * Note: The backend requires that all warehousing data be UTC+8 time, but may not have a time zone flag
 */

/**
 * Format time string and automatically handle time zone conversion
 * @param dateStr - time string or timestamp
 * @param options - Format options
 * @returns Formatted time string
 */
export function formatDateTime(
  dateStr: string | number | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!dateStr) return '-'

  try {
    let timeStr: string

    // Process timestamp (seconds or milliseconds)
    if (typeof dateStr === 'number') {
      // If it is a second-level timestamp (less than 10000000000), convert it to milliseconds
      const timestamp = dateStr < 10000000000 ? dateStr * 1000 : dateStr
      timeStr = new Date(timestamp).toISOString()
    } else {
      timeStr = String(dateStr).trim()
    }

    // Check if a time string contains time zone information
    const hasTimezone = timeStr.endsWith('Z') ||
                       timeStr.includes('+') ||
                       timeStr.includes('-', 10) // The - after the date is the time zone identifier

    // 🔥 If there is no time zone identifier, it is assumed to be UTC+8 time (the backend has been stored as UTC+8) , add +08:00 suffix
    // Note: If the backend has returned the time with time zone (such as +08:00 or Z), will not be modified here
    if (timeStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && !hasTimezone) {
      console.debug('[time processing] Time string without time zone detected, add +08:00:', timeStr)
      timeStr += '+08:00'
      console.debug('[time processing] After conversion:', timeStr)
    } else {
      console.debug('[time processing] The time string already has a time zone or format mismatch:', timeStr, 'hasTimezone:', hasTimezone)
    }

    // Parse time string
    const date = new Date(timeStr)

    if (isNaN(date.getTime())) {
      console.warn('Invalid time format:', dateStr)
      return String(dateStr)
    }

    // Default formatting options
    const defaultOptions: Intl.DateTimeFormatOptions = {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }

    // Merge user-provided options
    const finalOptions = { ...defaultOptions, ...options }

    // Formatted to Chinese local time (UTC+8) 
    return date.toLocaleString('zh-CN', finalOptions)
  } catch (e) {
    console.error('Time formatting error:', e, dateStr)
    return String(dateStr)
  }
}

/**
 * Format time and add relative time description
 * @param dateStr - time string or timestamp
 * @returns Formatted time string + relative time
 */
export function formatDateTimeWithRelative(dateStr: string | number | null | undefined): string {
  if (!dateStr) return '-'
  
  try {
    let timeStr: string
    
    // Processing timestamps
    if (typeof dateStr === 'number') {
      const timestamp = dateStr < 10000000000 ? dateStr * 1000 : dateStr
      timeStr = new Date(timestamp).toISOString()
    } else {
      timeStr = String(dateStr).trim()
    }
    
    // 🔥 If the time string has no time zone identifier, it is assumed to be UTC+8 time (the backend has been stored as UTC+8) , add +08:00 suffix
    if (timeStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && !timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
      timeStr += '+08:00'
    }
    
    const utcDate = new Date(timeStr)
    
    if (isNaN(utcDate.getTime())) {
      console.warn('Invalid time format:', dateStr)
      return String(dateStr)
    }
    
    // Get current time
    const now = new Date()
    
    // Calculate time difference
    const diff = now.getTime() - utcDate.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const minutes = Math.floor(diff / (1000 * 60))
    
    // Format to Chinese local time
    const formatted = utcDate.toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
    
    // Add relative time
    let relative = ''
    if (days > 0) {
      relative = ` (${days}days ago)`
    } else if (hours > 0) {
      relative = ` (${hours}hours ago)`
    } else if (minutes > 0) {
      relative = ` (${minutes}minutes ago)`
    } else {
      relative = ' (just now)'
    }
    
    return formatted + ' ' + relative
  } catch (e) {
    console.error('Time formatting error:', e, dateStr)
    return String(dateStr)
  }
}

/**
 * Format only the date part (without time)
 * @param dateStr - time string or timestamp
 * @returns Formatted date string
 */
export function formatDate(dateStr: string | number | null | undefined): string {
  return formatDateTime(dateStr, {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

/**
 * Format a Date object or date string to the local time zone "YYYY-MM-DD" string
 *
 * ⚠️ substitute `new Date(d).toISOString().split('T')[0]`: 
 * The latter will convert local time to UTC, and users in the East Eighth District chose May 12 00:00 would be incorrectly formatted as "2026-05-11". 
 * This function uses the local time zone field value to ensure that the date is consistent with the user selection.
 *
 * @param date - Date Object, date string, or timestamp
 * @returns "YYYY-MM-DD" Format string, returns an empty string when the input is invalid
 */
export function formatLocalDate(date: Date | string | number | null | undefined): string {
  if (!date) return ''
  const d = date instanceof Date ? date : new Date(date)
  if (isNaN(d.getTime())) return ''
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

/**
 * Format only the time part (without date)
 * @param dateStr - time string or timestamp
 * @returns Formatted time string
 */
export function formatTime(dateStr: string | number | null | undefined): string {
  return formatDateTime(dateStr, {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

/**
 * Format relative time (how long since now)
 * @param dateStr - time string or timestamp
 * @returns Relative time description
 */
export function formatRelativeTime(dateStr: string | number | null | undefined): string {
  if (!dateStr) return '-'

  try {
    let timeStr: string

    // Processing timestamps
    if (typeof dateStr === 'number') {
      const timestamp = dateStr < 10000000000 ? dateStr * 1000 : dateStr
      timeStr = new Date(timestamp).toISOString()
    } else {
      timeStr = String(dateStr).trim()
    }

    // 🔥 If the time string has no time zone identifier, it is assumed to be UTC+8 time (the backend has been stored as UTC+8) , add +08:00 suffix
    if (timeStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/) && !timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
      timeStr += '+08:00'
    }

    const targetDate = new Date(timeStr)

    if (isNaN(targetDate.getTime())) {
      console.warn('Invalid time format:', dateStr)
      return String(dateStr)
    }

    // Get current time
    const now = new Date()

    // Calculation time difference (milliseconds)
    const diff = targetDate.getTime() - now.getTime()
    const absDiff = Math.abs(diff)

    // Convert to various time units
    const seconds = Math.floor(absDiff / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    // Determine whether it is the past or the future
    const isPast = diff < 0

    // Format relative time
    if (days > 0) {
      return isPast ? `${days}days ago` : `${days}queen of heaven`
    } else if (hours > 0) {
      return isPast ? `${hours}hours ago` : `${hours}hours later`
    } else if (minutes > 0) {
      return isPast ? `${minutes}minutes ago` : `${minutes}minutes later`
    } else if (seconds > 10) {
      return isPast ? `${seconds}seconds ago` : `${seconds}seconds later`
    } else {
      return isPast ? 'just now' : 'About to be executed'
    }
  } catch (e) {
    console.error('Relative time formatting error:', e, dateStr)
    return String(dateStr)
  }
}
