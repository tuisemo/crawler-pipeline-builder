export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // fallback path
    }
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    document.execCommand('copy')
    return true
  } finally {
    document.body.removeChild(textarea)
  }
}

export function formatSavedAt(savedAt?: number) {
  if (!savedAt) return '未保存'
  return new Date(savedAt).toLocaleString('zh-CN', { hour12: false })
}
