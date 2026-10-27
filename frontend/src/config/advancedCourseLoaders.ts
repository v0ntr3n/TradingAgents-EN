/**
 * Advanced Course Legacy Loader Compatibility Layer
 *
 * Historically, the text of advanced courses has been packaged directly into the front end. To avoid exposure of advanced content again,
 * The old synchronous loading method retains an empty implementation and no longer provides text content.
 */

/**
 * Course file mapping table
 *
 * The old version of synchronization body mapping has been offline, and empty objects are retained only for compatibility with historical import.
 */
export const courseFileMap: Record<string, string> = {}

/**
 * Get course content based on file name
 */
export function getCourseContent(fileName: string): string | null {
  void fileName
  return null
}

