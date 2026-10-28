import IntelligentTable from './IntelligentTable.jsx';
import IntelligentCalculator from './IntelligentCalculator.jsx';
import IntelligentChart from './IntelligentChart.jsx';
import ComponentExport from './ComponentExport.jsx';
import './structuredUI.css';
import React, { memo, useId, useState } from "react";
import { validSpec, DEFAULTS, themeVars } from "./quickui";
import { parseSequence } from "./vendor/answer-me-with-html/sequence";

function PlainText({ text }) { return <div style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{text}</div>; }

function useControlled(value, onValue, initial) {
  const [local, setLocal] = useState(initial);
  const current = value === undefined ? local : value;
  return [current, next => {
    const updated = typeof next === "function" ? next(current) : next;
    if (onValue) onValue(updated); else setLocal(updated);
  }];
}
const safeUrl = (url) => {
  try {
    const p = new URL(url);
    return ["https:", "http:"].includes(p.protocol) &&
      !p.username &&
      !p.password
      ? p.href
      : null;
  } catch {
    return null;
  }
};
function SourceLinks({ refs, sources }) {
  return (
    <span className="qui-source-links">
      {[...new Set(refs || [])].map((n) =>
        sources[n - 1] && safeUrl(sources[n - 1].url) ? (
          <a
            key={n}
            href={safeUrl(sources[n - 1].url)}
            target="_blank"
            rel="noopener noreferrer"
            title={sources[n - 1].title}
          >
            [{n}]
          </a>
        ) : null,
      )}
    </span>
  );
}
function Sequence({ text }) {
  const id = useId().replace(/:/g, "");
  const { participants, steps } = parseSequence(text);
  if (participants.length > 16 || steps.length > 80)
    throw new Error("Diagram exceeds render limit");
  const width = Math.max(360, participants.length * 180),
    height = 90 + steps.length * 60;
  const x = (p) => 90 + participants.indexOf(p) * 180;
  return (
    <div className="qui-sequence">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Sequence diagram"
      >
        <defs>
          <marker
            id={id}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>
        {participants.map((p) => (
          <g key={p}>
            <rect
              x={x(p) - 75}
              y="5"
              width="150"
              height="40"
              rx="8"
              fill="var(--qui-surface)"
              stroke="var(--qui-accent)"
            />
            <text x={x(p)} y="30" textAnchor="middle">
              <title>{p}</title>
              {p.length > 19 ? p.slice(0, 18) + "…" : p}
            </text>
            <line
              x1={x(p)}
              x2={x(p)}
              y1="48"
              y2={height - 15}
              stroke="currentColor"
              opacity=".3"
              strokeDasharray="4 4"
            />
          </g>
        ))}
        {steps.map((s, i) => {
          const y = 85 + i * 60;
          if (s.kind === "msg") {
            const from = x(s.from),
              to = x(s.to);
            return (
              <g key={i}>
                <text x={(from + to) / 2} y={y - 10} textAnchor="middle">
                  <title>{s.label}</title>
                  {s.label.length > 32 ? s.label.slice(0, 31) + "…" : s.label}
                </text>
                {from === to ? (
                  <path
                    d={`M ${from} ${y} h 55 v 22 h -55`}
                    fill="none"
                    stroke="currentColor"
                    markerEnd={`url(#${id})`}
                  />
                ) : (
                  <line
                    x1={from}
                    x2={to}
                    y1={y}
                    y2={y}
                    stroke="currentColor"
                    strokeDasharray={s.dashed ? "5 5" : undefined}
                    markerEnd={`url(#${id})`}
                  />
                )}
              </g>
            );
          }
          return (
            <g key={i}>
              <rect
                x="12"
                y={y - 25}
                width={width - 24}
                height="36"
                rx="6"
                fill="var(--qui-surface)"
                stroke="var(--qui-accent)"
              />
              <text x={width / 2} y={y - 3} textAnchor="middle">
                <title>{s.text}</title>
                {s.text.length > 60 ? s.text.slice(0, 59) + "…" : s.text}
              </text>
            </g>
          );
        })}
      </svg>
      <details>
        <summary>Diagram source</summary>
        <pre>{text}</pre>
      </details>
    </div>
  );
}
export const Chart = IntelligentChart;
function Checklist({ block, value, onValue, interactionScope }) {
  const [checked, setChecked] = useControlled(value, onValue, block.items.map((i) => i.checked));
  return (
    <div className="qui-checklist">
      {block.items.map((item, i) => (
        <label key={i}>
          <input
            type="checkbox"
            checked={checked[i]}
            onChange={() =>
              setChecked((p) => p.map((v, j) => (i === j ? !v : v)))
            }
          />
          <span className={checked[i] ? "done" : ""}>{item.text}</span>
        </label>
      ))}
      <p className="muted">
        {checked.filter(Boolean).length} of {checked.length} complete ·
        {onValue ? `changes save with this ${interactionScope}` : "interactive state lasts while this response is open"}
      </p>
    </div>
  );
}
function FormBlock({block,value,onValue,interactionScope}) {
  const namespace=useId();
  const [current,setCurrent]=useControlled(value,onValue,()=>({values:block.fields.map(f=>f.value),submitted:false}));
  const change=(index,next)=>setCurrent({values:current.values.map((v,i)=>i===index?next:v),submitted:false});
  return <form className="qui-form" onSubmit={event=>{event.preventDefault();setCurrent({...current,submitted:true});}}>
    {block.fields.map((f,i)=>{
      const id=`${namespace}-${i}`,v=current.values[i];
      if(f.kind==='radio')return <fieldset key={i}><legend>{f.label}</legend>{f.options.map((option,j)=><label className="qui-form-toggle" key={option}><input type="radio" name={id} value={option} checked={v===option} onChange={()=>change(i,option)} />{option}</label>)}</fieldset>;
      if(f.kind==='checkbox'||f.kind==='switch')return <label className="qui-form-toggle" key={i}><input type="checkbox" role={f.kind==='switch'?'switch':undefined} checked={v} onChange={e=>change(i,e.target.checked)} />{f.label}</label>;
      return <label key={i} htmlFor={id}>{f.label}{f.kind==='select'?<select id={id} aria-label={f.label} value={v} onChange={e=>change(i,e.target.value)}>{f.options.map(o=><option key={o}>{o}</option>)}</select>:f.kind==='textarea'?<textarea id={id} aria-label={f.label} maxLength={4000} value={v} onChange={e=>change(i,e.target.value)} />:<input id={id} aria-label={f.label} type="text" maxLength={4000} value={v} onChange={e=>change(i,e.target.value)} />}</label>;
    })}
    <button type="submit">{block.submit_label||'Submit'}</button>
    {current.submitted&&<p role="status">Saved locally{onValue?` with this ${interactionScope}`:''}.</p>}
  </form>;
}
function Block({ block, colors, value, onValue, interactionScope, onTableAction, onInsert, MarkdownComponent = PlainText }) {
  switch (block.type) {
    case "form":
      return <FormBlock value={value} onValue={onValue} block={block} interactionScope={interactionScope} />;
    case "markdown":
      return <MarkdownComponent text={block.text} />;
    case "table":
      return <IntelligentTable block={block} value={value} onValue={onValue} onAction={onTableAction} onInsert={onInsert} />;
    case "cards":
      return (
        <div className="qui-cards">
          {block.items.map((c, i) => (
            <article key={i}>
              <span>{c.label}</span>
              <strong>{c.value}</strong>
              <p>{c.detail}</p>
            </article>
          ))}
        </div>
      );
    case "chart":
      return <Chart value={value} onValue={onValue} block={block} colors={colors} />;
    case "timeline":
      return (
        <ol className="qui-timeline">
          {block.items.map((e, i) => (
            <li key={i}>
              <time>{e.when}</time>
              <strong>{e.title}</strong>
              <p>{e.detail}</p>
            </li>
          ))}
        </ol>
      );
    case "diagram":
      return block.syntax === "sequence" ? (
        <Sequence text={block.text} />
      ) : (
        <MarkdownComponent text={"```mermaid\n" + block.text + "\n```"} />
      );
    case "calculator":
      return <IntelligentCalculator value={value} onValue={onValue} block={block} Chart={Chart} />;
    case "checklist":
      return <Checklist value={value} onValue={onValue} block={block} interactionScope={interactionScope} />;
    case "progress":
      return (
        <div className="qui-progress">
          {block.items.map((p, i) => (
            <label key={i}>
              {p.label}
              <span>
                {p.value} / {p.max}
              </span>
              <progress value={Math.min(p.value, p.max)} max={p.max} />
              {p.value > p.max && <small>Above target</small>}
            </label>
          ))}
        </div>
      );
    default:
      throw new Error("Unknown QuickUI block");
  }
}
export const Panels = memo(function Panels({ spec, colors, sources = [], state = {}, onState, MarkdownComponent, blockChanges, interactionScope='board', onTableAction, onInsert }) {
  const exportKey=useId();
  return (
    <>
      <h3 className="qui-title">{spec.title}</h3>
      <div className="qui-grid">
        {spec.blocks.map((b, i) => (
          <section
            key={i}
            data-component-index={i}
            data-export-key={exportKey+'-'+i}
            data-proposal-change={blockChanges?.[i]?.status}
            className={`qui-panel qui-span-${["chart", "table", "diagram"].includes(b.type) ? 2 : b.span || 1}`}
          >
            <div className="qui-panel-title">
              {blockChanges?.[i]?.status && blockChanges[i].status !== "unchanged" && <small className="proposal-change-label">{blockChanges[i].status}</small>}
              {b.title && <h4>{b.title}</h4>}
              <SourceLinks refs={b.sources} sources={sources} />
              <ComponentExport compact items={()=>{const node=Array.from(document.querySelectorAll('[data-component-index]')).find(n=>n.dataset.exportKey===exportKey+'-'+i);return node?[{node,title:b.title||spec.title||b.type}]:[];}} />
            </div>
            <Block MarkdownComponent={MarkdownComponent} block={b} colors={colors} value={state[i]} interactionScope={interactionScope} onInsert={onInsert} onTableAction={onTableAction?context=>onTableAction({...context,blockIndex:i}):undefined} onValue={onState ? value => onState({ ...state, [i]: value }) : undefined} />
          </section>
        ))}
      </div>
    </>
  );
});


export default function StructuredUI({ spec, state = {}, onState, readOnly = false, accent, preferences, chartColors, blockChanges, onTableAction, onInsert }) {
  if (!validSpec(spec)) return <p role="alert">Invalid structured UI specification.</p>;
  const appearance = preferences || (/^#[0-9a-f]{6}$/i.test(accent || '') ? {...DEFAULTS,color:{...DEFAULTS.color,colors:[accent]}} : DEFAULTS);
  return <div className={`quickui qui-light qui-${appearance.density} ${preferences ? "canvas-themed-widget" : ""}`} style={{...themeVars(appearance, false),...((accent||preferences)?{'--qui-text':'#111111','--qui-surface':'#FFFFFF',...(preferences?.appearance==='dark'?{'--qui-border':'#9a9a9a'}:{})}:{})}}>
    <fieldset disabled={readOnly} style={{border:0, padding:0, margin:0, minWidth:0}}>
      <Panels onInsert={onInsert} onTableAction={onTableAction} spec={spec} colors={chartColors || appearance.color.colors} blockChanges={blockChanges} state={state} onState={onState} />
    </fieldset>
  </div>;
}
