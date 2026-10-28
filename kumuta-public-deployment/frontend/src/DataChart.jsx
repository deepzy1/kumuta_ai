import React, { useState } from 'react';
import { Chart } from './QuickUI';
import { chartBlock, CHART_COLORS } from './dataAnalysis';

function ScatterChart({block}) {
 const [selected,setSelected]=useState('');
 const [x,y]=block.series;
 const xmin=Math.min(...x.values),xmax=Math.max(...x.values),ymin=Math.min(...y.values),ymax=Math.max(...y.values);
 const px=v=>64+(v-xmin)/(xmax-xmin||1)*480,py=v=>262-(v-ymin)/(ymax-ymin||1)*220;
 return <div className="data-scatter"><svg viewBox="0 0 600 320" role="img" aria-label={block.title}>
  <path d="M64 30 V262 H560" fill="none" stroke="#52525B"/>
  <text x="310" y="310" textAnchor="middle">{x.name}</text><text x="12" y="20">{y.name}</text>
  <text x="64" y="285" textAnchor="middle">{Number(xmin.toPrecision(5))}</text><text x="544" y="285" textAnchor="middle">{Number(xmax.toPrecision(5))}</text>
  <text x="56" y="262" textAnchor="end">{Number(ymin.toPrecision(5))}</text><text x="56" y="42" textAnchor="end">{Number(ymax.toPrecision(5))}</text>
  {x.values.map((v,i)=>{const label=`${block.labels[i]}: ${x.name} ${v}, ${y.name} ${y.values[i]}`;return <circle key={i} cx={px(v)} cy={py(y.values[i])} r="5" fill="#c84e00" tabIndex="0" aria-label={label} onFocus={()=>setSelected(label)} onMouseEnter={()=>setSelected(label)}><title>{label}</title></circle>;})}
 </svg><p aria-live="polite">{selected||'Focus a point to inspect its values. Exact values are in the table.'}</p></div>;
}

function CircularChart({block,donut}) {
 const [selected,setSelected]=useState(null),[hidden,setHidden]=useState([]);
 const series=block.series[0],values=series.values.map((v,i)=>hidden.includes(i)?0:v),total=values.reduce((n,v)=>n+v,0);
 let offset=0;
 return <div className="data-circular"><svg viewBox="0 0 260 230" role="img" aria-label={block.title}>
  {values.map((v,i)=>{
   const portion=total?v/total:0,start=offset;offset+=portion;if(v<=0)return null;
   const label=`${block.labels[i]}: ${v}`,props={tabIndex:0,'aria-label':label,onFocus:()=>setSelected(label),onMouseEnter:()=>setSelected(label)};
   if(portion>=1)return <circle key={i} cx="130" cy="112" r={donut?72.5:96} fill={donut?'none':CHART_COLORS[i%CHART_COLORS.length]} stroke={donut?CHART_COLORS[i%CHART_COLORS.length]:'none'} strokeWidth={donut?27:0} {...props}><title>{label}</title></circle>;
   const point=(radius,fraction)=>[130+radius*Math.cos(fraction*2*Math.PI-Math.PI/2),112+radius*Math.sin(fraction*2*Math.PI-Math.PI/2)].join(' ');
   const radius=donut?86:96,large=portion>0.5?1:0;
   const path=donut?`M ${point(radius,start)} A ${radius} ${radius} 0 ${large} 1 ${point(radius,offset)} L ${point(59,offset)} A 59 59 0 ${large} 0 ${point(59,start)} Z`:`M 130 112 L ${point(radius,start)} A ${radius} ${radius} 0 ${large} 1 ${point(radius,offset)} Z`;
   return <path key={i} d={path} fill={CHART_COLORS[i%CHART_COLORS.length]} stroke="white" strokeWidth="1" {...props}><title>{label}</title></path>;
  })}
  {!total&&<text x="130" y="112" textAnchor="middle">Select a category</text>}
  {donut&&total>0&&<text x="130" y="117" textAnchor="middle" fontWeight="700">{Number(total.toPrecision(8))}</text>}
 </svg><div className="data-chart-legend">{block.labels.map((label,i)=><label key={i}><input type="checkbox" checked={!hidden.includes(i)} onChange={()=>setHidden(v=>v.includes(i)?v.filter(n=>n!==i):[...v,i])}/><span style={{background:CHART_COLORS[i%CHART_COLORS.length]}}/>{label} <b>{series.values[i]}</b></label>)}<p aria-live="polite">{selected||'Focus a slice or toggle a category.'}</p></div></div>;
}

export default function DataChart({result,title}) {
 const kind=result.spec.chart,block=chartBlock(result,title);
 if(kind==='table')return null;
 if(kind==='kpi'){
  const names=result.columns.filter(n=>['integer','decimal'].includes(result.column_types[n]));
  if(result.rows.length===1&&names.length)return <div className="data-stats data-kpis">{names.map(n=><div key={n}><span>{n}</span><strong>{result.rows[0][result.columns.indexOf(n)]??'Unavailable'}</strong></div>)}</div>;
  return <p className="data-warning">KPI cards need a single result row with numeric metrics. Use the exact table below.</p>;
 }
 if(!block)return <p className="data-warning">Charts need 1–100 result rows with complete finite numeric metrics up to 10¹⁵. The table retains exact values.</p>;
 if(kind==='scatter')return block.series.length>=2?<ScatterChart block={block}/>:<p className="data-warning">Scatter charts need two numeric result columns. Use the table or another chart.</p>;
 if(['pie','donut'].includes(kind)){
  if(block.series.length!==1||block.labels.length>12||block.series[0].values.some(v=>v<0)||!block.series[0].values.some(v=>v>0))return <p className="data-warning">Pie/donut charts need one nonnegative metric, a positive total and at most 12 categories. Use a bar chart or table for these results.</p>;
  return <CircularChart key={JSON.stringify(block)} block={block} donut={kind==='donut'}/>;
 }
 return <Chart key={JSON.stringify(block)} block={block} colors={CHART_COLORS}/>;
}
