import React,{useId,useRef,useState} from 'react';
import {CHART_COLORS,formatCell,seriesColor} from './intelligentUI.js';
import Modal from './Modal.jsx';

export default function IntelligentChart({block,colors,value,onValue,expanded=false}) {
  const [local,setLocal]=useState([]),[selected,setSelected]=useState(''),[full,setFull]=useState(false);
  const container=useRef(null),uid=useId().replaceAll(':',''),hidden=value===undefined?local:value;
  const series=block.series.map((s,i)=>({...s,index:i})).filter(s=>!hidden.includes(s.index)),round=['pie','donut'].includes(block.kind);
  const palette=block.colors?.length?block.colors:colors?.length>1?colors:CHART_COLORS;
  const categories=[...new Set(block.labels)].sort(),assigned=new Map(),used=new Set();
  for(const label of categories){let at=CHART_COLORS.indexOf(seriesColor(label))%palette.length;while(used.has(at)&&used.size<palette.length)at=(at+1)%palette.length;assigned.set(label,palette[at]);used.add(at);}
  // Series are assigned by name, so filtering/reordering keeps identity stable.
  const color=(name,index)=>block.colors?.length||colors?.length>1?palette[index%palette.length]:seriesColor(name);
  const categoryColor=(name,index)=>block.colors?.length?palette[index%palette.length]:assigned.get(name);
  const categorical=round||block.series.length===1&&['bar','stacked'].includes(block.kind);
  const positive=block.kind==='stacked'?block.labels.map((_,k)=>series.reduce((n,s)=>n+Math.max(0,s.values[k]),0)):series.flatMap(s=>s.values);
  const negative=block.kind==='stacked'?block.labels.map((_,k)=>series.reduce((n,s)=>n+Math.min(0,s.values[k]),0)):series.flatMap(s=>s.values);
  const min=Math.min(0,...negative),rawMax=Math.max(0,...positive),max=rawMax===min?min+1:rawMax,span=max-min;
  const W=720,H=320,left=72,right=24,top=20,bottom=65,y=v=>top+(max-v)/span*(H-top-bottom),pitch=(W-left-right)/block.labels.length;
  const xs=block.labels.map(Number),xmin=Math.min(...xs),xmax=Math.max(...xs),x=(k)=>block.kind==='scatter'?left+(xmax===xmin?.5:(xs[k]-xmin)/(xmax-xmin))*(W-left-right):left+pitch*(k+.5);
  const tip=(s,k,v)=>`${s.name} · ${block.labels[k]}: ${formatCell(v,{kind:'number'})} ${block.unit||''}`;
  const events=(s,k,v)=>({tabIndex:0,role:'button','aria-label':tip(s,k,v),onMouseEnter:()=>setSelected(tip(s,k,v)),onFocus:()=>setSelected(tip(s,k,v)),onClick:()=>setSelected(tip(s,k,v)),onKeyDown:e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(tip(s,k,v));}}});
  const toggle=i=>{const next=hidden.includes(i)?hidden.filter(n=>n!==i):[...hidden,i];if(onValue)onValue(next);else setLocal(next);};
  let angle=-Math.PI/2;const sum=series[0]?.values.reduce((a,b)=>a+b,0)||0;
  return <div ref={container} className="qui-chart">
    <div className="qui-legend" data-export-exclude="true">{block.series.map((s,i)=><label key={i}><input type="checkbox" checked={!hidden.includes(i)} onChange={()=>toggle(i)} /><span style={{background:color(s.name,i)}} />{s.name}</label>)}{!expanded&&<button type="button" onClick={()=>setFull(true)}>Inspect chart</button>}</div>
    {!series.length&&<p role="status">All series hidden. Enable a series in the legend.</p>}
    <div className="qui-chart-export-legend">{(categorical?block.labels:series.map(s=>s.name)).map((name,i)=><span key={i}><i style={{background:categorical?categoryColor(name,i):color(name,series[i].index)}} />{name}</span>)}</div>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={block.title||'Interactive chart'}>
      <defs><pattern id={uid} width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 0L8 8" stroke="currentColor" opacity=".15" /></pattern></defs>
      {round?series[0]?.values.map((v,k)=>{const start=angle,sweep=v/sum*2*Math.PI;angle+=sweep;const end=angle,cx=W/2,cy=H/2,r=125,px=a=>cx+r*Math.cos(a),py=a=>cy+r*Math.sin(a);
        return <g key={k} fill={categoryColor(block.labels[k],k)}>{sweep>=Math.PI*2-.000001?<circle cx={cx} cy={cy} r={r} {...events(series[0],k,v)}><title>{tip(series[0],k,v)}</title></circle>:sweep>0?<path d={`M${cx},${cy} L${px(start)},${py(start)} A${r},${r} 0 ${sweep>Math.PI?1:0},1 ${px(end)},${py(end)} Z`} stroke="white" strokeWidth="2" {...events(series[0],k,v)}><title>{tip(series[0],k,v)}</title></path>:null}</g>;}):<>
        {[0,.25,.5,.75,1].map((t,i)=><g key={i}><line x1={left} x2={W-right} y1={y(min+span*t)} y2={y(min+span*t)} stroke="currentColor" opacity=".12" /><text x={left-8} y={y(min+span*t)+4} textAnchor="end">{formatCell(min+span*t,{kind:'number',decimals:1})}</text></g>)}
        {series.map((s,j)=><g key={s.index} fill={color(s.name,s.index)} stroke={color(s.name,s.index)}>
          {['line','area'].includes(block.kind)&&<polyline fill="none" strokeWidth="2.5" points={s.values.map((v,k)=>`${x(k)},${y(v)}`).join(' ')} />}
          {block.kind==='area'&&<polygon stroke="none" opacity=".16" points={`${x(0)},${y(0)} ${s.values.map((v,k)=>`${x(k)},${y(v)}`).join(' ')} ${x(s.values.length-1)},${y(0)}`} />}
          {s.values.map((v,k)=>{if(['line','area','scatter'].includes(block.kind))return <circle key={k} cx={x(k)} cy={y(v)} r={5} {...events(s,k,v)}><title>{tip(s,k,v)}</title></circle>;
            const base=block.kind==='stacked'?series.slice(0,j).reduce((n,prior)=>n+(Math.sign(prior.values[k])===Math.sign(v)?prior.values[k]:0),0):0;
            const single=series.length===1,fill=single?categoryColor(block.labels[k],k):color(s.name,s.index),stack=block.kind==='stacked';
            return <rect key={k} x={left+pitch*k+pitch*.1+(stack?0:j*pitch*.8/series.length)} y={Math.min(y(base+v),y(base))} width={Math.max(1,stack?pitch*.8:pitch*.8/series.length-3)} height={Math.max(.5,Math.abs(y(base+v)-y(base)))} rx={stack?0:3} fill={fill} stroke="none" {...events(s,k,v)}><title>{tip(s,k,v)}</title></rect>;
          })}
        </g>)}
        {block.labels.map((label,k)=>(block.labels.length<=10||k%Math.ceil(block.labels.length/10)===0)&&<text key={k} x={x(k)} y={H-30} textAnchor="middle"><title>{label}</title>{String(label).length>15?String(label).slice(0,14)+'…':label}</text>)}
      </>}
      {block.kind==='donut'&&series.length>0&&<circle cx={W/2} cy={H/2} r={72} fill="var(--qui-surface,#fff)" />}
    </svg>
    <p className="qui-chart-value" role="status" aria-live="polite">{selected||'Focus or hover over a point to explore. Toggle series above.'}</p>
    <details data-export-exclude="true"><summary>Accessible chart data</summary><div className="table-scroll"><table><thead><tr><th>Label</th>{series.map(s=><th key={s.index}>{s.name}</th>)}</tr></thead><tbody>{block.labels.map((l,k)=><tr key={k}><th>{l}</th>{series.map(s=><td key={s.index}>{s.values[k]} {block.unit}</td>)}</tr>)}</tbody></table></div></details>
    {full&&<Modal title="Inspect chart" wide onClose={()=>setFull(false)}><IntelligentChart block={block} colors={colors} value={hidden} onValue={next=>{if(onValue)onValue(next);else setLocal(next);}} expanded /></Modal>}
  </div>;
}
