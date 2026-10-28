import { resourceKey, resourceReference } from './canvasResources.js';

export const DEFAULT_INTELLIGENCE = {scope:'selection',operation:'ask',automatic:true,keys:[],fullDocument:false,confirmFull:false};
export function intelligenceReferences(value, resources, selection) {
  const ready=resources.filter(r=>r.status==='ready'&&['document','dataset'].includes(r.kind));
  const selected=value.scope==='board'?ready:ready.filter(r=>value.keys.includes(resourceKey(r)));
  return selected.flatMap(r=>{
    const existing=selection?.request?.resources?.find(x=>resourceKey(x)===resourceKey(r));
    const configured=value.sheets?.[resourceKey(r)];
    const sheets=Array.isArray(configured)&&value.scope!=='selected'?configured[0]:configured;
    if(r.kind==='dataset'&&Array.isArray(sheets))return sheets.map(sheet=>({...resourceReference(r),sheet}));
    return [{...resourceReference(r),...(r.kind==='dataset'&&existing?.sheet?{sheet:existing.sheet}:{}),...(typeof sheets==='string'&&sheets?{sheet:sheets}:{})}];
  });
}
export function intelligenceSelection(value, resources, selection, revision, prompt) {
  if(value.scope==='selection')return selection?.request||null;
  return {expected_revision:revision,resources:intelligenceReferences(value,resources,selection),
    action:value.operation==='visualize'?'modify':'ask',
    intelligence:{scope:value.scope,operation:value.operation,query:prompt,full_document:!!value.fullDocument,
      confirm_full:!!value.confirmFull,...(value.analyses?{analyses:value.analyses}:{})}};
}
export function applicableActions(resources) {
  const docs=resources.some(r=>r.kind==='document'),data=resources.some(r=>r.kind==='dataset');
  return ['ask',...(docs?['search','summarize']:[]),...(resources.length>1?['compare']:[]),...(data?['analyze','visualize']:[]),...(docs||data?['report']:[])];
}

export const SOURCE_ACTION_LABELS={ask:'Ask',search:'Search',summarize:'Summarize',compare:'Compare',analyze:'Analyze',visualize:'Visualize',report:'Create report'};
export function automaticSourceAction(value){return value.automatic??value.operation==='ask';}
export function resolveSourceAction(value,resources,selection,mode,prompt){
  if(value.scope==='selection'||!automaticSourceAction(value))return value;
  const refs=intelligenceReferences(value,resources,selection);
  const dataset=refs.some(r=>r.kind==='dataset');
  let operation='ask';
  if(dataset&&mode!=='diagram'){
    const text=prompt.trim().toLowerCase();
    const visual=/\b(chart|graph|plot|dashboard|histogram|visuali[sz](?:e|ation))\b/.test(text);
    const create=/\b(create|build|draw|generate|design|make|plot|convert|show|interactive)\b/.test(text);
    const explanation=/^(explain|what\b|why\b|how\b|describe|tell me)\b/.test(text);
    if(mode==='ui'||mode==='auto'&&visual&&create&&!explanation)operation='visualize';
    else if(/\b(calculate|compute|sum|total|average|minimum|maximum|count|analy[sz]e)\b/.test(text))operation='analyze';
  }
  return {...value,operation,automatic:true};
}
export function sourceSummary(value,resources,selection){
  if(value.scope==='selection'){
    const names=selection?.context.resources?.map(r=>r.label||r.filename)||[];
    return names.length?names.join(' · '):selection?`Selection · ${selection.context.element_ids.length} elements`:'';
  }
  const refs=intelligenceReferences(value,resources,selection);
  return refs.map(ref=>{
    const resource=resources.find(r=>resourceKey(r)===resourceKey(ref));
    const sheet=ref.kind==='dataset'?(ref.sheet||resource?.sheets?.[0]?.name):null;
    return `${resource?.filename||'Unavailable source'}${sheet?` · ${sheet}`:''}`;
  }).join(' · ');
}
