/**
 * Safe Markdown rendering tool
 *
 * Use marked parsing Markdown + DOMPurify Sanitize HTML to prevent XSS attacks.
 * This tool should be used wherever LLM output/user input is rendered via v-html.
 *
 * Security model:
 * - marked Convert Markdown to HTML string
 * - DOMPurify Remove all dangerous labels (<script>, on* event attributes,javascript: agreement, etc.)
 * - Allows regular typography tags (h1-h6, p, a, code, pre, table, ul/ol/li, strong/em, etc.)
 *
 * How to use:
 *   import { renderMarkdown } from '@/utils/markdown'
 *   const html = renderMarkdown(llmOutput)
 *   // In the template: <div v-html="html"></div>
 */

import { marked, type MarkedOptions } from 'marked'
import DOMPurify from 'dompurify'
import type { Config as DOMPurifyConfig } from 'dompurify'

// marked Global configuration: enable GFM and newlines
const markedOptions: MarkedOptions = {
  gfm: true,
  breaks: true,
}

// DOMPurify Configuration: Allow common Markdown formatting tags and prohibit all dangerous content
const purifyConfig: DOMPurifyConfig = {
  // Allowed tag whitelist (covers all regular tags for Markdown output)
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'a', 'img',
    'strong', 'em', 'del', 's', 'u', 'mark', 'small', 'sub', 'sup',
    'code', 'pre', 'kbd', 'samp', 'var',
    'blockquote', 'q', 'cite',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
    'div', 'span',
    'details', 'summary',
    'figure', 'figcaption',
    'abbr', 'address', 'time',
  ],
  // Allowed attribute whitelist
  ALLOWED_ATTR: [
    'href', 'title', 'target', 'rel',
    'src', 'alt', 'width', 'height',
    'class', 'id',
    'colspan', 'rowspan',
    'datetime',
    'open',
    'align',
    'start', 'type', 'value',
  ],
  // Force the rel attribute of the a tag to prevent phishing and tabnabbing
  FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover'],
  // Allow protocol whitelist (forbidden javascript:, data: and other dangerous agreements)
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|ftp|tel):|#|\/)/i,
}

// Configure DOMPurify hook: add for all external links rel="noopener noreferrer" and target="_blank"
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('href')) {
    const href = node.getAttribute('href') || ''
    // Add security attributes to external links (http/https protocol)
    if (/^https?:\/\//i.test(href)) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  }
})

// Initialize marked (configure only once)
marked.setOptions(markedOptions)

/**
 * Safely render Markdown to HTML string
 *
 * @param markdown Markdown Source string (may be from LLM output or user input)
 * @returns The sanitized HTML string can be used directly v-html
 */
export function renderMarkdown(markdown: string): string {
  if (!markdown) {
    return ''
  }
  try {
    // 1. marked parse Markdown → HTML
    const rawHtml = marked.parse(markdown, { async: false }) as string
    // 2. DOMPurify purify HTML → safe HTML
    // Note: DOMPurify.sanitize returns TrustedHTML and needs to be converted to string
    const cleanHtml = String(DOMPurify.sanitize(rawHtml, purifyConfig))
    return cleanHtml
  } catch (err) {
    // Returns escaped plain text when rendering fails to avoid crashes
    console.error('[markdown] Rendering fails, returning escaped text:', err)
    return escapeHtml(String(markdown))
  }
}

/**
 * Escape HTML special characters (for safe display of plain text)
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export default renderMarkdown
