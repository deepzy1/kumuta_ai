// Shared, deterministic view operations. Row IDs always refer to source order.
export const CHART_COLORS = ['#2563eb','#ea580c','#059669','#7c3aed','#db2777','#0891b2','#b45309','#475569'];
export function seriesColor(name, overrides = []) {
  const explicit = overrides.find?.(c => c.name === name)?.color;
  if (explicit) return explicit;
  let hash = 2166136261;
  for (const c of String(name)) hash = Math.imul(hash ^ c.codePointAt(0), 16777619);
  return CHART_COLORS[(hash >>> 0) % CHART_COLORS.length];
}
export function tableState(value) {
  return {query: '', filters: {}, sort: null, page: 0, pageSize: 25, hidden: [], selected: [], widths: {},
    ...(typeof value === 'string' ? {query: value} : value || {})};
}
export function tableRows(block, value) {
  const state = tableState(value), query = state.query.toLowerCase();
  const rows = block.rows.map((cells, id) => ({id, cells})).filter(({cells}) =>
    cells.some(c => String(c).toLowerCase().includes(query)) && Object.entries(state.filters).every(([col, q]) =>
      String(cells[Number(col)]).toLowerCase().includes(q.toLowerCase())));
  if (state.sort) {
    const {column, direction} = state.sort;
    rows.sort((a,b) => {
      const x = a.cells[column], y = b.cells[column];
      const nx = numericCell(x), ny = numericCell(y);
      const comparison = nx !== null && ny !== null ? nx - ny : nx!==null?-1:ny!==null?1:naturalCompare(x,y);
      return (direction === 'desc' ? -comparison : comparison) || a.id - b.id;
    });
  }
  return rows;
}
function naturalCompare(x,y){const a=String(x).toLowerCase().match(/\d+|\D+/g)||[],b=String(y).toLowerCase().match(/\d+|\D+/g)||[];for(let i=0;i<Math.min(a.length,b.length);i++){const an=/^\d+$/.test(a[i]),bn=/^\d+$/.test(b[i]);const result=an&&bn?Number(a[i])-Number(b[i]):an?-1:bn?1:a[i]<b[i]?-1:a[i]>b[i]?1:0;if(result)return result;}return a.length-b.length;}
export function scopedRows(block, value, scope = 'filtered') {
  const state = tableState(value), rows = tableRows(block, state);
  if (scope === 'selected') return rows.filter(r => state.selected.includes(r.id));
  if (scope === 'visible') {const page = Math.min(state.page, Math.max(0, Math.ceil(rows.length/state.pageSize)-1));return rows.slice(page*state.pageSize,(page+1)*state.pageSize);}
  return rows;
}
export function numericCell(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim())) return null;
  const n = Number(value); return Number.isFinite(n) ? n : null;
}
export function aggregates(block, rows) {
  return block.columns.flatMap((name, column) => {
    const values = rows.map(r => numericCell(r.cells[column]));
    if (!values.length || values.some(v => v === null)) return [];
    const sum = values.reduce((a,b)=>a+b,0);
    return [{name, column, count: values.length, sum, average: sum / values.length, min: Math.min(...values), max: Math.max(...values)}];
  });
}
export function formatCell(value, format) {
  const n = numericCell(value);
  if (format?.kind === 'date') {
    // ISO-only dates avoid locale-dependent parsing and invented dates.
    if (/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(String(value)) && Number.isFinite(Date.parse(value))) return new Intl.DateTimeFormat(undefined,{timeZone:'UTC'}).format(new Date(value));
  }
  if (n === null || !format || format.kind === 'text' || format.kind === 'status') return String(value);
  const options = {maximumFractionDigits: format.decimals ?? 2};
  if (format.kind === 'currency') Object.assign(options,{style:'currency',currency:format.currency || 'USD'});
  // Percentage values are percentage points: 20 is displayed as 20%, not 2000%.
  return new Intl.NumberFormat(undefined, options).format(n) + (format.kind === 'percent' ? '%' : '');
}
export function csvData(columns, rows) {
  const cell = v => {let s=String(v);if (/^[=+\-@\t\r]/.test(s)) s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  return '\ufeff'+[columns,...rows].map(row=>row.map(cell).join(',')).join('\r\n');
}
// A bounded arithmetic grammar, not JavaScript. Only x1..x6 and preceding rN
// references are available. No functions, strings, properties or assignments.
export function formulaValue(expression, values, results = [], syntaxOnly = false) {
  if (typeof expression !== 'string' || expression.length > 240) throw Error('Formula exceeds 240 characters.');
  const tokens = expression.match(/(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[xr][1-9]\d*|[()+\-*/^]|\s+/g) || [];
  if (tokens.join('') !== expression) throw Error('Use numbers, x1…x6, earlier r1…r12, parentheses and + − * / ^.');
  const ts=tokens.filter(t=>t.trim());if(ts.length>100)throw Error('Formula is too complex.');let at=0;
  const checked = v => {if(syntaxOnly)return 0;if(!Number.isFinite(v)||Math.abs(v)>1e15)throw Error('Result is outside the calculation range.');return v;};
  function atom(depth) {
    if(depth>20)throw Error('Formula is too deeply nested.');
    const t=ts[at++];
    if(t==='+'||t==='-')return (t==='-'?-1:1)*power(depth+1);
    if(t==='('){const v=add(depth+1);if(ts[at++]!==')')throw Error('Close the formula parentheses.');return v;}
    if(/^[xr]/.test(t||'')){const source=t[0]==='x'?values:results,index=Number(t.slice(1))-1;if(index>=source.length||!Number.isFinite(source[index]))throw Error('Unknown or unavailable reference: '+t);return source[index];}
    if(t===undefined||!/^\d|^\.\d/.test(t))throw Error('A number or reference is missing.');const n=Number(t);if(/^0\d/.test(t)||!Number.isFinite(n)||Math.abs(n)>1e15)throw Error('Invalid formula number.');return checked(n);
  }
  function power(depth){const v=atom(depth);return ts[at]==='^'?(at++,checked(v**power(depth+1))):v;}
  function mul(depth){let v=power(depth);while(['*','/'].includes(ts[at])){const op=ts[at++],b=power(depth);if(op==='/'&&b===0&&!syntaxOnly)throw Error('Cannot divide by zero.');v=checked(op==='*'?v*b:v/b);}return v;}
  function add(depth){let v=mul(depth);while(['+','-'].includes(ts[at])){const op=ts[at++],b=mul(depth);v=checked(op==='+'?v+b:v-b);}return v;}
  const answer=add(0);if(at!==ts.length)throw Error('Unexpected formula token.');return checked(answer);
}
export function validFormulas(expressions, inputs) {try {return Array.isArray(expressions)&&expressions.length<=12&&expressions.every((f,i)=>{formulaValue(f,Array(inputs).fill(1),Array(i).fill(1),true);return true;});} catch {return false;}}
export function validTableState(block, value) {
  if(typeof value==='string')return value.length<=120;
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!['query','filters','sort','page','pageSize','hidden','selected','widths'].includes(k)))return false;
  const s=tableState(value),indexes=(xs,n)=>Array.isArray(xs)&&new Set(xs).size===xs.length&&xs.every(i=>Number.isInteger(i)&&i>=0&&i<n);
  return typeof s.query==='string'&&s.query.length<=120&&Number.isInteger(s.page)&&s.page>=0&&s.page<=1000&&[10,25,50,100].includes(s.pageSize)&&indexes(s.hidden,block.columns.length)&&s.hidden.length<block.columns.length&&indexes(s.selected,block.rows.length)&&
    (s.sort===null||s.sort&&Object.keys(s.sort).length===2&&Number.isInteger(s.sort.column)&&s.sort.column>=0&&s.sort.column<block.columns.length&&['asc','desc'].includes(s.sort.direction))&&
    ['filters','widths'].every(key=>s[key]&&typeof s[key]==='object'&&!Array.isArray(s[key])&&Object.entries(s[key]).every(([col,v])=>/^(0|[1-9]\d*)$/.test(col)&&Number(col)<block.columns.length&&(key==='filters'?typeof v==='string'&&v.length<=120:Number.isFinite(v)&&v>=64&&v<=600)));
}
export function calculatorValues(block, state) {return Array.isArray(state)?state:state?.values || block.inputs.map(i=>i.value);}
export function calculatorResults(block, state) {
  const values=calculatorValues(block,state), expressions=state?.expressions || block.formulas?.map(f=>f.expression) || [];
  const results=[];
  return (block.formulas||[]).map((f,i)=>{try{const value=formulaValue(expressions[i],values,results);results.push(value);return {...f,value,expression:expressions[i]};}catch(e){results.push(null);return {...f,value:null,error:e.message,expression:expressions[i]};}});
}
export function componentSize(spec) {
  if(!spec?.blocks)return {width:540,height:380};
  const wide=spec.blocks.some(b=>['chart','table','calculator'].includes(b.type));
  return {width:wide?720:480,height:Math.min(1000,Math.max(260,100+spec.blocks.reduce((h,b)=>h+({table:340,chart:320,calculator:400,cards:170}[b.type]||180),0)))};
}
