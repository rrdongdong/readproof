import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Meta() {
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.meta().then(setMeta).catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="banner error">载入失败：{error}</p>
  if (!meta) return <p className="muted">载入中…</p>

  return (
    <section>
      <h2>状态机 <span className="hint">状态是权限，不是标签</span></h2>
      <table className="grid">
        <thead><tr><th>状态</th><th>可转移</th><th>可写产物</th></tr></thead>
        <tbody>
          {meta.state_machine.map((row) => (
            <tr key={row.state}>
              <td><span className={`chip state-${row.state}`}>{row.state}</span></td>
              <td className="mono small">{row.next.join(', ') || '（终态）'}</td>
              <td className="mono small">{row.may_write.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="sub">手动上传最多只能到 <code>{meta.manual_upload_target}</code>——它放宽的是「怎么拿到文件」，从不放宽「什么算证据」。</p>

      <h3>读证四项</h3>
      <ul className="plain mono">{meta.receipt_fields.map((field) => <li key={field}>{field}</li>)}</ul>

      <h3>退出码就是契约</h3>
      <table className="grid">
        <thead><tr><th>码</th><th>含义</th></tr></thead>
        <tbody>
          {Object.entries(meta.exit_codes).map(([code, meaning]) => (
            <tr key={code}><td className="mono">{code}</td><td>{meaning}</td></tr>
          ))}
        </tbody>
      </table>

      <h3>六类缺口</h3>
      <table className="grid">
        <thead><tr><th>类型</th><th>含义</th></tr></thead>
        <tbody>
          {Object.entries(meta.gap_types).map(([kind, meaning]) => (
            <tr key={kind}><td className="mono">{kind}</td><td>{meaning}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
