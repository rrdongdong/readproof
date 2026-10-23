import React, { useEffect, useState } from 'react'
import { api, parseRoute } from './api.js'
import Papers from './components/Papers.jsx'
import PaperDetail from './components/PaperDetail.jsx'
import Gaps from './components/Gaps.jsx'
import Meta from './components/Meta.jsx'

export default function App() {
  const [route, setRoute] = useState(parseRoute(window.location.hash))
  const [papers, setPapers] = useState(null)
  const [gaps, setGaps] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    api
      .papers()
      .then(setPapers)
      .catch((err) => setError(err.message))
    api
      .gaps()
      .then(setGaps)
      .catch((err) => setError(err.message))
  }, [])

  const nav = [
    ['papers', '论文', '#/papers'],
    ['gaps', '缺口', '#/gaps'],
    ['meta', '状态机', '#/meta'],
  ]

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">readproof</span>
          <span className="brand-cn">读证</span>
          <span className="tagline">每篇论文都留一张读证；拿不到全文，就写不出结论。</span>
        </div>
        <nav className="tabs">
          {nav.map(([key, label, href]) => (
            <a key={key} href={href} className={route.view === key ? 'tab active' : 'tab'}>
              {label}
              {key === 'papers' && papers ? <span className="tab-count">{papers.count}</span> : null}
              {key === 'gaps' && gaps && gaps.available ? (
                <span className="tab-count">{gaps.findings.length}</span>
              ) : null}
            </a>
          ))}
        </nav>
      </header>

      {error ? <div className="banner error">API 错误：{error}</div> : null}
      {gaps && gaps.available && gaps.health && !gaps.health.ok ? (
        <div className="banner warn">
          <strong>图谱健康度不合格（exit 4）</strong>
          <ul>
            {gaps.health.failures.map((failure) => (
              <li key={failure}>{failure}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <main>
        {route.view === 'papers' ? <Papers data={papers} gaps={gaps} /> : null}
        {route.view === 'paper' ? <PaperDetail id={route.id} gaps={gaps} /> : null}
        {route.view === 'gaps' ? <Gaps data={gaps} /> : null}
        {route.view === 'meta' ? <Meta /> : null}
      </main>

      <footer className="footer">
        只读界面：所有写入仍走 CLI，每个闸门都有退出码。 引擎无第三方依赖。
      </footer>
    </div>
  )
}
