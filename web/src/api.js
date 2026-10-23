const API = ''

export async function get(path) {
  const response = await fetch(API + path, { headers: { accept: 'application/json' } })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.error || detail
    } catch (_) {
      /* keep statusText */
    }
    throw new Error(`${response.status} ${detail}`)
  }
  return response.json()
}

export const api = {
  papers: () => get('/api/papers'),
  paper: (id) => get(`/api/papers/${encodeURIComponent(id)}`),
  gaps: () => get('/api/gaps'),
  meta: () => get('/api/meta'),
}

/** Hash router: '#/papers', '#/paper/07', '#/gaps', '#/meta'. */
export function parseRoute(hash) {
  const raw = (hash || '').replace(/^#\/?/, '')
  const [head, tail] = raw.split('/')
  if (head === 'paper' && tail) return { view: 'paper', id: decodeURIComponent(tail) }
  if (head === 'gaps') return { view: 'gaps' }
  if (head === 'meta') return { view: 'meta' }
  return { view: 'papers' }
}
