export function sea_query_all(selector: string, maxSamples = 20) {
  try {
    const elements = [...document.querySelectorAll(selector)]
    return {
      count: elements.length,
      elements: elements.slice(0, maxSamples).map((el) => ({
        text: (el.textContent || '').trim().slice(0, 200),
        html: el.outerHTML.slice(0, 600),
        children: el.querySelectorAll('*').length,
        has_image: el.querySelectorAll('img').length > 0,
        has_link: el.querySelectorAll('a[href]').length > 0,
      })),
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'query failed', count: 0, elements: [] }
  }
}

export function sea_extract_fields(
  itemSelector: string,
  fields: Array<{ name: string; selector: string; type: string }>
) {
  try {
    const items = [...document.querySelectorAll(itemSelector)]
    const pageUrl = location.href
    const records = items.map((item, index) => {
      const record: Record<string, any> = { _index: index }
      for (const field of fields) {
        try {
          const selector = field.selector || ''
          const extType = field.type === 'all(text)' ? 'all_text' : field.type
          const matchedSelf = selector ? item.matches(selector) : false
          const subElements = matchedSelf ? [item] : [...item.querySelectorAll(selector)]
          if (subElements.length === 0) {
            record[field.name] = null
            continue
          }
          const first = subElements[0]
          if (extType === 'text') {
            record[field.name] = (first.textContent || '').trim() || null
          } else if (extType === 'html' || extType === 'inner') {
            record[field.name] = first.innerHTML
          } else if (extType === 'all_text') {
            record[field.name] = subElements.map((el) => (el.textContent || '').trim()).filter(Boolean)
          } else if (extType.startsWith('all(@') && extType.endsWith(')')) {
            const attrName = extType.slice(5, -1)
            record[field.name] = subElements.map((el) => el.getAttribute(attrName)).filter(Boolean)
          } else if (extType.startsWith('attr:')) {
            const [, attrName, ...rest] = extType.split(':')
            let value = first.getAttribute(attrName) || null
            if (value && rest.includes('abs')) {
              try {
                value = new URL(value, pageUrl).href
              } catch {}
            }
            record[field.name] = value
          } else {
            record[field.name] = null
          }
        } catch {
          record[field.name] = null
        }
      }
      return record
    })
    return { records }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'extract failed', records: [] }
  }
}

export function sea_click_and_observe(selector: string, timeoutMs = 5000) {
  return new Promise<{ clicked: boolean; domChanged: boolean; error?: string }>((resolve) => {
    try {
      const el = document.querySelector(selector) as HTMLElement | null
      if (!el) return resolve({ clicked: false, domChanged: false, error: 'Element not found' })
      let changed = false
      const observer = new MutationObserver(() => {
        changed = true
        observer.disconnect()
      })
      observer.observe(document.body, { childList: true, subtree: true })
      el.click()
      setTimeout(() => {
        observer.disconnect()
        resolve({ clicked: true, domChanged: changed })
      }, timeoutMs)
    } catch (error) {
      resolve({ clicked: false, domChanged: false, error: error instanceof Error ? error.message : 'click failed' })
    }
  })
}

export function sea_scroll_bottom() {
  window.scrollTo(0, document.body.scrollHeight)
  return { scrolled: true }
}

export function __eval__(js: string) {
  // eslint-disable-next-line no-eval
  const value = eval(js)
  return { value }
}
