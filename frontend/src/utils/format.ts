/**
 * ISO 날짜 문자열을 'YYYY.MM.DD HH:MM' 형식으로 변환.
 */
export function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const Y = d.getFullYear()
  const M = String(d.getMonth() + 1).padStart(2, '0')
  const D = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${Y}.${M}.${D} ${h}:${m}`
}
