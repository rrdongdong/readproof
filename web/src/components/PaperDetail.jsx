import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const LABEL = {
  number_with_locator: '具体数字 + 表号 + 页码',
  hyperparameters: '超参 + 章节',
  negative_quote: '负面表述原话',
  body_detail: '正文细节（非结论）',
}

const STATE_LABEL = {
  UNREAD: '未读',
  FETCH_FAILED: '取件失败',
  FETCHED: '已取件',
  READ_PARTIAL: '部分读',
  READ_FULL: '全文读',
  VERIFIED: '已核验',
}

const RELATION_LABEL = {
  solves: '解决',
  leaves_open: '遗留未解',
  assumes: '假设',
  admits: '承认的局限',
  criticizes: '批评的前人方法',
  anomaly: '异常',
}

function gradeOf(entry) {
  return entry && entry.evidence ? entry.evidence : null
}

export default function PaperDetail({ id }) {
  const [paper, setPaper] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setPaper(null)
    setError(null)
    api
      .paper(id)
      .then(setPaper)
      .catch((err) => setError(err.message))
  }, [id])

  if (error) return <p className="banner error">载入失败：{error}</p>
  if (!paper) return <p className="muted">载入中…</p>

  const receipt = paper.receipt

  return (
    <section>
      <a href="#/papers" className="back">← 返回台账</a>
      <h2>
        <span className="mono">#{paper.id}</span> {paper.title}
        <span className={`chip state-${paper.state}`}>{STATE_LABEL[paper.state] || paper.state}</span>
      </h2>
      <div className="meta-grid">
        <div><span className="k">出处</span>{paper.venue || '—'}</div>
        <div><span className="k">arXiv</span>{paper.arxiv || '—'}</div>
        <div><span className="k">DOI</span>{paper.doi || '—'}</div>
        <div><span className="k">取件来源</span>{paper.source || '—'}</div>
        <div><span className="k">可写产物</span>{paper.may_write.join(', ') || '无'}</div>
      </div>

      <h3>读证 <span className="hint">{receipt.present.length}/{receipt.total} 齐</span></h3>
      <table className="grid">
        <thead>
          <tr><th>指纹</th><th>内容</th></tr>
        </thead>
        <tbody>
          {Object.keys(LABEL).map((field) => {
            const value = receipt.values[field]
            const missing = receipt.missing.includes(field)
            return (
              <tr key={field} className={missing ? 'row-missing' : ''}>
                <td>
                  <span className="mono">{field}</span>
                  <div className="sub">{LABEL[field]}</div>
                </td>
                <td>{value ? <span className="quote">{value}</span> : <span className="muted">缺失 → 不能成为「全文读」</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {receipt.extra && Object.keys(receipt.extra).length ? (
        <p className="sub">来源：{JSON.stringify(receipt.extra)}</p>
      ) : null}

      <h3>问题卡</h3>
      {paper.card ? (
        <table className="grid">
          <thead><tr><th>关系</th><th>节点</th><th>位置</th><th>证据</th></tr></thead>
          <tbody>
            {Object.entries(paper.card)
              .filter(([key]) => key !== 'paper')
              .flatMap(([relation, entries]) =>
                (entries || []).map((entry, index) => (
                  <tr key={`${relation}-${index}`}>
                    <td>{RELATION_LABEL[relation] || relation}</td>
                    <td className="mono">{entry.node || '—'}</td>
                    <td className="mono">{entry.loc || '—'}</td>
                    <td>
                      {gradeOf(entry) ? (
                        <span className={`grade grade-${gradeOf(entry)}`}>{gradeOf(entry)}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                )),
              )}
          </tbody>
        </table>
      ) : (
        <p className="muted">这张卡还没录 → 这篇论文不进图谱。</p>
      )}

      <h3>状态历史</h3>
      <ol className="history">
        {(paper.history || []).map((event, index) => (
          <li key={index}>
            <span className="mono">{event.at}</span> {event.from || '—'} → <strong>{event.to}</strong>{' '}
            <span className="sub">({event.via})</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
