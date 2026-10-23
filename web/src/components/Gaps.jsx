import React from 'react'

const KIND = {
  G1: { label: '共鸣缺口', tone: 'g1' },
  G2: { label: '沉默缺口', tone: 'g2' },
  G3: { label: '争议缺口', tone: 'g3' },
  G4: { label: '假设缺口', tone: 'g4' },
  G5: { label: '孤证缺口', tone: 'g5' },
  G6: { label: '异常缺口', tone: 'g6' },
}

const ORDER = ['G1', 'G3', 'G4', 'G2', 'G6', 'G5']

function Papers({ ids }) {
  return (
    <span className="papers">
      {ids.map((id) => (
        <a key={id} href={`#/paper/${encodeURIComponent(id)}`} className="paper-ref">
          #{id}
        </a>
      ))}
    </span>
  )
}

export default function Gaps({ data }) {
  if (!data) return <p className="muted">载入中…</p>
  if (!data.available) {
    return (
      <section>
        <h2>缺口候选</h2>
        <p className="banner warn">{data.reason} — {data.hint}</p>
      </section>
    )
  }

  const counts = {}
  for (const finding of data.findings) {
    counts[finding.kind] = (counts[finding.kind] || 0) + 1
  }
  const sorted = [...data.findings].sort((a, b) => {
    const byKind = ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind)
    return byKind !== 0 ? byKind : String(a.node).localeCompare(String(b.node))
  })

  return (
    <section>
      <h2>
        缺口候选
        <span className="hint">
          共 {data.findings.length} 条 · {data.stats.papers} 篇论文 · {data.stats.edges} 条边 ·{' '}
          {data.stats.nodes_referenced} 个节点 · 待归类 {data.stats.triage}
        </span>
      </h2>

      <div className="counts">
        {ORDER.filter((kind) => counts[kind]).map((kind) => (
          <span key={kind} className={`chip kind-${KIND[kind].tone}`}>
            {kind} {KIND[kind].label} {counts[kind]}
          </span>
        ))}
        {data.stats.category_blanks && data.stats.category_blanks.length ? (
          <span className="chip muted">空类目：{data.stats.category_blanks.join(', ')}</span>
        ) : null}
      </div>

      <p className="muted small">
        缺口是问题，不是点子。表格给的是陈述 + 证据 + 计数，判断权在使用者。
      </p>

      <div className="cards">
        {sorted.map((finding, index) => (
          <article key={`${finding.kind}-${finding.node}-${index}`} className={`gap gap-${KIND[finding.kind].tone}`}>
            <header>
              <span className={`chip kind-${KIND[finding.kind].tone}`}>
                {finding.kind} {KIND[finding.kind].label}
              </span>
              <h3>{finding.statement}</h3>
            </header>
            <div className="gap-meta">
              <span className="mono small">{(finding.nodes || [finding.node]).join(' · ')}</span>
              <Papers ids={finding.papers} />
            </div>
            <ul className="evidence">
              {finding.evidence.map((item) => (
                <li key={item} className="mono small">{item}</li>
              ))}
            </ul>
            <p className="meaning">{finding.meaning}</p>
          </article>
        ))}
      </div>

      {data.triage && data.triage.length ? (
        <>
          <h3>待归类池 <span className="hint">解析不上的短语绝不进图，由人裁决是新建还是别名</span></h3>
          <table className="grid">
            <thead><tr><th>论文</th><th>关系</th><th>短语</th><th>相似候选</th></tr></thead>
            <tbody>
              {data.triage.map((item, index) => (
                <tr key={index}>
                  <td className="mono">{item.paper}</td>
                  <td>{item.relation}</td>
                  <td>{item.phrase}</td>
                  <td className="mono">{item.suggestions.join(', ') || '无'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </section>
  )
}
