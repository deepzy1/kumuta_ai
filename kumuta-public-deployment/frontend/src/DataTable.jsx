import React from 'react';
export default function DataTable({ columns, rows, caption = 'Dataset preview' }) {
  return <div className="data-table-scroll" tabIndex="0" aria-label={caption}><table><caption>{caption}</caption><thead><tr>{columns.map(c => <th scope="col" key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} title={v===null?'Missing':String(v)}>{v === null ? <span className="muted">Missing</span> : String(v)}</td>)}</tr>)}</tbody></table>{!rows.length && <p>No matching rows.</p>}</div>;
}

