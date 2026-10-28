export function selectionActions(artifacts, resources, count) {
  const base=[['ask','Ask AI',''],['explain','Explain','Explain the selected content.'],['summarize','Summarize','Summarize the selected content.']];
  if(count>1&&(artifacts.length||resources.length))return [...base,['explain','Compare selected','Compare only the selected components and explain their relationships.'],['derive','Create combined dashboard','Create a coordinated dashboard from the selected components. Preserve their sources and original components.'],['derive','Merge into report','Create a report from the selected components with source attribution and data limitations. Preserve originals.']];
  const types=new Set(artifacts.flatMap(a=>a.engine==='B'?a.payload.blocks.map(b=>b.type):[]));
  if(types.has('chart'))return [...base,['explain','Summarize trends','Summarize trends and compare categories using the supplied chart data.'],['suggest','Suggest improvements','Suggest improvements to this chart.'],['derive','Change visualization','Propose a more suitable visualization of the same supplied data. Preserve the original chart.']];
  if(types.has('table'))return [...base,['explain','Analyze selected rows','Analyze only the scoped table rows; state selected/filtered scope and limitations.'],['derive','Create comparison','Create a comparison from the scoped table rows. Preserve the source table.']];
  if(resources.some(r=>r.reference.kind==='document'))return [...base,['explain','Extract information','Extract structured information from the selected document evidence.'],['derive','Generate questions','Generate questions from the selected document evidence. Preserve the original.']];
  return [...base,['suggest','Suggest improvements','Suggest improvements to the selected content.'],['modify','Modify selected content','Improve the selected content.']];
}
export function canvasExportItems({elements,artifacts=[],resources=[],selected,nativeRef,exportToCanvas}) {
  const chosen=new Set(selected),anchors=new Set([...artifacts,...resources].map(a=>a.anchor_id));
  return elements.filter(e=>chosen.has(e.id)&&!e.isDeleted&&!e.containerId).map(e=>{
    const widget=artifacts.find(a=>a.anchor_id===e.id),resource=resources.find(a=>a.anchor_id===e.id);
    if(widget){const node=Array.from(document.querySelectorAll('[data-artifact-id]')).find(n=>n.dataset.artifactId===widget.id)?.querySelector('.artifact-content');return {node,title:widget.payload.title||'Widget'};}
    if(resource){const node=Array.from(document.querySelectorAll('[data-resource-id]')).find(n=>n.dataset.resourceId===resource.id);return {node,title:node?.getAttribute('aria-label')||'Document component'};}
    const parts=elements.filter(p=>!p.isDeleted&&!anchors.has(p.id)&&(p.id===e.id||p.containerId===e.id));
    return {title:e.text?.slice(0,60)||`${e.type} component`,capture:async scale=>{
      const all=nativeRef.current.getFiles(),files={};for(const p of parts)if(p.fileId&&all[p.fileId])files[p.fileId]=all[p.fileId];
      return exportToCanvas({elements:parts,files,appState:{exportBackground:true,viewBackgroundColor:'#ffffff'},exportPadding:16,getDimensions:(width,height)=>{if(width*height*scale*scale>32000000||width*scale>16384||height*scale>16384)throw Error('Native component exceeds export limits.');return {width:width*scale,height:height*scale,scale};}});
    }};
  });
}
