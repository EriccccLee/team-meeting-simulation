/**
 * ISO 날짜 문자열을 'YYYY.MM.DD HH:MM' 형식으로 변환.
 * @param {string} iso
 * @returns {string}
 */
export function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
