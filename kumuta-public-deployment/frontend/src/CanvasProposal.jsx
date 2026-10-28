import React, { useEffect, useLayoutEffect, useRef } from 'react';
import StructuredUI from './StructuredUI.jsx';
import { validateManual } from './canvasArtifacts.js';
import { proposalChanges, proposalGeometry, proposalKey } from './canvasProposal.js';
import './canvasGeneration.css';

class ProposalBoundary extends React.Component {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(){this.props.onReady(false);}
  render(){return this.state.failed?<p role="alert">This proposal could not render. Accepted content is preserved.</p>:this.props.children;}
}
function NativePreview({payload,changes}) {
  const nodes=[...payload.nodes,...changes.removed.map(r=>r.item)],byId=new Map(nodes.map(n=>[n.id,n]));
  const x=Math.min(...nodes.map(n=>n.x))-15,y=Math.min(...nodes.map(n=>n.y))-30;
  const w=Math.max(...nodes.map(n=>n.x+n.width))-x+15,h=Math.max(...nodes.map(n=>n.y+n.height))-y+15;
  return <svg className="generation-diagram" role="img" aria-label="Generated diagram preview" viewBox={`${x} ${y} ${w} ${h}`}>
    <defs><marker id="proposal-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#737373" /></marker></defs>
    {[...payload.edges,...changes.removedEdges.map(r=>r.item)].map((e,i)=>{const a=byId.get(e.from),b=byId.get(e.to);const status=changes.edges[i]?.status||'removal';return <g key={i} data-proposal-change={status} opacity={status==='removal'?.4:1}><title>{status}: {e.from} → {e.to}</title><line x1={a.x+a.width/2} y1={a.y+a.height/2} x2={b.x+b.width/2} y2={b.y+b.height/2} stroke="#737373" strokeWidth="2" strokeDasharray={status==='removal'?'5 5':undefined} markerEnd="url(#proposal-arrow)" />{(e.text||status!=='unchanged')&&<text x={(a.x+b.x+a.width/2+b.width/2)/2} y={(a.y+b.y+a.height/2+b.height/2)/2-8} textAnchor="middle" fontSize="12">{e.text||status}</text>}</g>;})}
    {nodes.map(n=>{const change=changes.items.find(c=>c.key===n.id)?.status||'removal';return <g key={n.id} data-proposal-change={change} opacity={change==='removal'?.45:1}><title>{change}: {n.text}</title>{n.type==='ellipse'?<ellipse cx={n.x+n.width/2} cy={n.y+n.height/2} rx={n.width/2} ry={n.height/2} fill="#fff" stroke="#737373" />:n.type==='diamond'?<polygon points={`${n.x+n.width/2},${n.y} ${n.x+n.width},${n.y+n.height/2} ${n.x+n.width/2},${n.y+n.height} ${n.x},${n.y+n.height/2}`} fill="#fff" stroke="#737373" />:<rect x={n.x} y={n.y} width={n.width} height={n.height} rx="8" fill="#fff" stroke="#737373" />}<text x={n.x+6} y={n.y-8} fontSize="11">{change==='unchanged'?'':change}</text><foreignObject x={n.x+6} y={n.y+6} width={n.width-12} height={n.height-12}><div xmlns="http://www.w3.org/1999/xhtml" style={{height:'100%',display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',fontSize:14,overflowWrap:'anywhere',textDecoration:change==='removal'?'line-through':undefined}}>{n.text}</div></foreignObject></g>;})}
  </svg>;
}
function Content({proposal,appearance,onReady}) {
  const {artifact,version}=proposal;
  validateManual(version.content);
  const previous=artifact.versions.find(v=>v.version===artifact.placement?.version);
  const changes=proposalChanges(previous?.content,version.content);
  useEffect(()=>{onReady(true);return()=>onReady(false);},[onReady,version]);
  return <><div className="proposal-caption"><strong>{proposal.partial?'✧ OpenUI streaming preview':'✧ AI proposal'}</strong><span>{proposal.partial?'Partial · generating · acceptance unavailable':'Preview · not saved'}</span></div>
    {version.selection&&<p className="proposal-diff">{version.selection.action==='derive'||version.selection.resources?.length||version.selection.retrieval?'Adds a new artifact; source content is preserved.':<>Replaces {version.selection.element_ids.length} selected elements after acceptance · {version.selection.widgets.length} widgets</>}</p>}
    <p className="proposal-diff">{version.selection&&version.selection.action!=='derive'&&!version.selection.resources?.length&&!version.selection.retrieval?'Complete replacement for the disclosed selection':<>{artifact.placement&&!artifact.placement.removed?'Replace this artifact (compared with accepted definition)':'New artifact'} · {changes.additions} additions · {changes.modifications} modifications · {changes.removals} removals</>}</p>
    <div className="proposal-artwork" inert="">{version.engine==='A'?<NativePreview payload={version.content.payload} changes={changes} />:<StructuredUI spec={version.content.payload} preferences={appearance.widget} chartColors={appearance.charts} blockChanges={changes.items} readOnly />}</div>
    {changes.removals>0&&<p className="proposal-removals">Removed: {[...changes.removed,...changes.removedEdges].map(r=>r.label).join(', ')}</p>}
    {previous&&<small>Acceptance replaces only this artifact and resets its widget state.</small>}
  </>;
}
export default function CanvasProposal({proposal,visual,appearance,onReady,onBounds}) {
  const article=useRef(null);
  const g=!visual?null:proposal?.artifact.placement&&!proposal.artifact.placement.removed?proposalGeometry(proposal.artifact,proposal.version,visual.elements,visual.appState):proposal?.geometry;
  useLayoutEffect(()=>{if(!article.current||!g)return;const report=()=>onBounds({...g,width:article.current.offsetWidth,height:article.current.offsetHeight},proposalKey(proposal));const observer=new ResizeObserver(report);observer.observe(article.current);report();return()=>observer.disconnect();},[proposalKey(proposal),visual?.appState.width,visual?.appState.height,g?.x,g?.y,onBounds]);
  if(!proposal||!visual||!g)return null;
  const z=visual.appState.zoom?.value||1;
  return <div className="canvas-proposal-layer" aria-label="AI proposal layer"><article ref={article} data-proposal-key={proposalKey(proposal)} className="canvas-proposal" aria-label="AI proposal" style={{left:(g.x+visual.appState.scrollX)*z,top:(g.y+visual.appState.scrollY)*z,width:Math.max(300,g.width),minHeight:g.height,transform:`scale(${z})`}}><ProposalBoundary key={proposalKey(proposal)} onReady={onReady}><Content proposal={proposal} appearance={appearance} onReady={onReady} /></ProposalBoundary></article></div>;
}
