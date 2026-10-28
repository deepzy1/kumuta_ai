export const CHART_COLORS = ['#ed6416', '#e4a13c', '#497fa6', '#5c967e', '#986cb0'];
export const defaultSpec = () => ({sheet:null,operation:'aggregate',columns:[],filters:[],group_by:[],metrics:[{op:'count',column:null,alias:'Count'}],derived:[],sort:[],limit:100,offset:0,chart:'bar'});
export function chartBlock(result, title='Analysis chart') {
  const names=result.columns, types=result.column_types;
  const groups=result.spec.group_by?.map(g=>g.column)||[];
 const metricIndexes=names.map((n,i)=>!groups.includes(n)&&['decimal','integer'].includes(types[n])?i:-1).filter(i=>i>=0);
  const labelIndex=groups.length?names.indexOf(groups[0]):names.findIndex(n=>!['decimal','integer'].includes(types[n]));
  // No coercion of missing or huge values into zero / approximate identifiers.
  if (!result.rows.length || !metricIndexes.length || result.rows.length>100) return null;
  if (result.rows.some(r=>metricIndexes.some(i=>r[i]===null || !Number.isFinite(Number(r[i])) || Math.abs(Number(r[i]))>1e15))) return null;
  return {title,kind:['line','area'].includes(result.spec.chart)?result.spec.chart:'bar',labels:result.rows.map((r,i)=>labelIndex>=0?String(r[labelIndex]??'(missing)'):String(i+1)),series:metricIndexes.map(i=>({name:names[i],values:result.rows.map(r=>Number(r[i]))}))};
}
export function moveWidget(widgets,index,direction){const next=[...widgets],target=index+direction;if(target<0||target>=next.length)return next;[next[index],next[target]]=[next[target],next[index]];return next;}
// Check renderable draft shapes; the backend remains authoritative for semantics.
export function parseSpecDraft(raw) {
 const parsed=JSON.parse(raw);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('Specification must be an object.');
 const d={...defaultSpec(),...parsed},record=v=>v&&typeof v==='object'&&!Array.isArray(v),str=v=>typeof v==='string',nullable=v=>v===null||str(v);
 if(!['rows','aggregate','missing','describe'].includes(d.operation)||!['table','bar','line','area','pie','donut','kpi','scatter'].includes(d.chart)||!nullable(d.sheet)||!Number.isInteger(d.limit)||d.limit<1||d.limit>500||!Number.isInteger(d.offset)||d.offset<0)throw Error('Invalid operation, chart, worksheet or result bounds.');
 for(const k of ['columns','filters','group_by','metrics','derived','sort'])if(!Array.isArray(d[k]))throw Error(`${k} must be an array.`);
 if(!d.columns.every(str)||!d.metrics.every(v=>record(v)&&str(v.op)&&str(v.alias)&&(v.column===undefined||nullable(v.column)))||!d.group_by.every(v=>record(v)&&str(v.column)&&(v.period===undefined||nullable(v.period)))||!d.filters.every(v=>record(v)&&str(v.column)&&str(v.op)&&(v.value===undefined||v.value===null||['string','number','boolean'].includes(typeof v.value)||Array.isArray(v.value)&&v.value.every(x=>['string','number','boolean'].includes(typeof x))))||!d.sort.every(v=>record(v)&&str(v.column)&&(v.descending===undefined||typeof v.descending==='boolean'))||!d.derived.every(v=>record(v)&&str(v.op)&&str(v.numerator)&&str(v.denominator)&&str(v.alias)))throw Error('Use named columns and correctly typed metric, filter, group and sort objects.');
 return d;
}

export function supportedCharts(result) {
 const block=chartBlock(result), kinds=['table'];
 if(!block)return kinds;
 kinds.push('bar','line','area');
 if(block.series.length>=2)kinds.push('scatter');
 if(block.series.length===1&&block.labels.length<=12&&block.series[0].values.every(v=>v>=0)&&block.series[0].values.some(v=>v>0))kinds.push('pie','donut');
 if(result.rows.length===1)kinds.push('kpi');
 return kinds;
}
