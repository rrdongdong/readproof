import React from 'react'

const STATE_LABEL = {
  UNREAD: '未读',
  FETCH_FAILED: '取件失败',
  FETCHED: '已取件',
  READ_PARTIAL: '部分读',
  READ_FULL: '全文读',
  VERIFIED: '已核验',
}

function ReceiptDots({ receipt }) {
  const fields = ['number_with_locator', 'hyperparameters', 'negative_quote', 'body_detail']
  return (
    <span className="dots" title={receipt.complete ? '读证完整 4/4' : `缺：${receipt.missing.join(', ')}`}>
      {fields.map((field) => (
        <i key={field} className={receipt.present.includes(field) ? 'dot on' : 'dot off'} />
      ))}
      <span className="dots-count">
        {receipt.present.length}/{receipt.total}
      </span>
    </span>
  )
}

export default function Papers({ data, gaps }) {
  if (!data) return <p className="muted">载入中…</p>
  const gapCount = {}
  if (gaps && gaps.available) {
    for (const finding of gaps.findings) {
      for (const paper of finding.papers) {
        gapCount[paper] = (gapCount[paper] || 0) + 1
      }
    }
  }

  return (
    <section>
      <h2>论文台账<span className="hint">状态是权限，不是标签：只有 <code>全文读</code> 能写 8 问，只有 <code>已核验</code> 能进缺口表。</span></h2>
      <div className="counts">
        {Object.entries(data.counts).map(([state, count]) => (
          <span key={state} className={`chip state-${state}`}>
            {STATE_LABEL[state] || state} {count}
          </span>
        ))}
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>#</th>
            <th>状态</th>
            <th>标题</th>
            <th>读证</th>
            <th>问题卡</th>
            <th>关联缺口</th>
          </tr>
        </thead>
        <tbody>
          {data.papers.map((paper) => (
            <tr key={paper.id}>
              <td className="mono">{paper.id}</td>
              <td>
                <span className={`chip state-${paper.state}`}>{STATE_LABEL[paper.state] || paper.state}</span>
              </td>
              <td>
                <a href={`#/paper/${encodeURIComponent(paper.id)}`} className="title-link">
                  {paper.title}
                </a>
                <div className="sub">{paper.venue || paper.arxiv || '—'}</div>
              </td>
              <td><ReceiptDots receipt={paper.receipt} /></td>
              <td>{paper.has_card ? <span className="chip ok">有</span> : <span className="chip muted">无</span>}</td>
              <td className="mono">{gapCount[paper.id] || 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
