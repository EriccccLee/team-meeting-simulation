import { marked } from 'marked'
import DOMPurify from 'dompurify'

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'a',
  'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4',
  'code', 'pre', 'blockquote',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'hr',
]

const ALLOWED_ATTR = ['href', 'target', 'rel']

/**
 * 마크다운 문자열을 안전한 HTML로 변환.
 * DOMPurify 화이트리스트로 XSS를 방지한다.
 */
export function renderMarkdown(content: string): string {
  const raw = marked.parse(content || '')
  const html = typeof raw === 'string' ? raw : ''
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR })
}
