// Original local encoders. PDF uses JPEG image XObjects; ZIP uses stored entries.
// No remote renderer, screenshot API, generated code or new runtime dependency.
const utf8 = new TextEncoder();
const bytes = s => utf8.encode(s);
export function concat(parts) {const out=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));let at=0;for(const p of parts){out.set(p,at);at+=p.length;}return out;}
export function filename(title, index=0) {return `${String(index+1).padStart(2,'0')}-${String(title||'component').normalize('NFKC').replace(/[^\p{L}\p{N}_ -]/gu,'').trim().replace(/\s+/g,'-').slice(0,80)||'component'}`;}
export function download(blob, name) {const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function crc32(data) {let crc=0xffffffff;for(const byte of data){crc^=byte;for(let k=0;k<8;k++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function header(size, entries) {const out=new Uint8Array(size),view=new DataView(out.buffer);for(const [at,n,width] of entries)width===2?view.setUint16(at,n,true):view.setUint32(at,n,true);return out;}
export function zipBytes(files) {
  if(!files.length||files.length>120)throw Error('Choose 1–120 files.');
  const local=[],central=[];let offset=0,total=0;
  for(const f of files){const name=bytes(f.name),data=f.data,crc=crc32(data);total+=data.length;if(total>160e6)throw Error('ZIP exceeds 160 MB. Export fewer components.');
    const h=header(30,[[0,0x04034b50,4],[4,20,2],[6,0x800,2],[12,33,2],[14,crc,4],[18,data.length,4],[22,data.length,4],[26,name.length,2]]);
    const c=header(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[8,0x800,2],[14,33,2],[16,crc,4],[20,data.length,4],[24,data.length,4],[28,name.length,2],[42,offset,4]]);
    local.push(h,name,data);central.push(c,name);offset+=h.length+name.length+data.length;
  }
  const directory=concat(central),end=header(22,[[0,0x06054b50,4],[8,files.length,2],[10,files.length,2],[12,directory.length,4],[16,offset,4]]);
  return concat([...local,directory,end]);
}
export function pdfBytes(pages) {
  if(!pages.length||pages.length>500)throw Error('PDF requires 1–500 pages.');
  const objects=[bytes('<< /Type /Catalog /Pages 2 0 R >>'),null,bytes('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')],kids=[];
  for(const p of pages){const pageID=objects.length+1,imageID=pageID+1,contentID=pageID+2;kids.push(`${pageID} 0 R`);
    objects.push(bytes(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${p.pageWidth} ${p.pageHeight}] /Resources << /Font << /F1 3 0 R >> /XObject << /Im ${imageID} 0 R >> >> /Contents ${contentID} 0 R >>`));
    objects.push(concat([bytes(`<< /Type /XObject /Subtype /Image /Width ${p.width} /Height ${p.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.data.length} >>\nstream\n`),p.data,bytes('\nendstream')]));
    const content=bytes(`q ${p.drawWidth} 0 0 ${p.drawHeight} ${p.x} ${p.y} cm /Im Do Q${p.pageNumbers?`\nBT /F1 9 Tf ${p.pageWidth/2-20} 12 Td (Page ${kids.length} of ${pages.length}) Tj ET`:''}`);
    objects.push(concat([bytes(`<< /Length ${content.length} >>\nstream\n`),content,bytes('\nendstream')]));
  }
  objects[1]=bytes(`<< /Type /Pages /Count ${pages.length} /Kids [${kids.join(' ')}] >>`);
  const parts=[bytes('%PDF-1.4\n')],offsets=[0];let position=parts[0].length;
  objects.forEach((object,i)=>{offsets.push(position);const chunk=concat([bytes(`${i+1} 0 obj\n`),object,bytes('\nendobj\n')]);parts.push(chunk);position+=chunk.length;});
  parts.push(bytes(`xref\n0 ${objects.length+1}\n0000000000 65535 f \n${offsets.slice(1).map(n=>`${String(n).padStart(10,'0')} 00000 n \n`).join('')}trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${position}\n%%EOF\n`));
  return concat(parts);
}
// A DOM-local symbol keeps preparations attached to the actual mounted surface
// through development module reloads and independently imported export callers.
const preparation=Symbol.for('kumuta.component.export.prepare');
export function registerExport(node, prepare) {if(node)node[preparation]=prepare;return()=>{if(node?.[preparation]===prepare)delete node[preparation];};}
function styledClone(node, imageSources) {
  if(node.nodeType!==1)return node.cloneNode(true);
  if(node.matches('[data-export-exclude],script,iframe,video,canvas,.artifact-label,.artifact-resize,.resource-frame-header>span,.qui-chart-value,.qui-performance')){
    if(node.matches('iframe,video,canvas'))throw Error('Embedded custom previews, video and canvas surfaces cannot be captured. Export a supported structured component.');
    return document.createTextNode('');
  }
  if(node instanceof HTMLImageElement && !node.src.startsWith('data:')&&!imageSources?.has(node))throw Error('Remote images cannot be embedded. Use an uploaded inline image.');
  const clone=node.cloneNode(false),style=getComputedStyle(node);
  if(node instanceof HTMLImageElement&&imageSources?.has(node))clone.src=imageSources.get(node);
  for(const key of style)clone.style.setProperty(key,style.getPropertyValue(key));
  // Computed layout sizes are used pixels, even when authored as auto. Copying
  // them would freeze a paginated grid's old height over its expanded table.
  if(node instanceof HTMLElement&&!node.matches('img,i,span,small,code,time')&&['block','flex','grid','table','table-row','table-cell','table-row-group','table-header-group','flow-root'].includes(style.display)){
    Object.assign(clone.style,{height:'auto',minHeight:'0',maxHeight:'none'});
    if(style.display==='grid')Object.assign(clone.style,{gridTemplateRows:'none',gridAutoRows:'auto'});
  }
  clone.style.transform='none';clone.style.position=style.position==='absolute'?'static':style.position;clone.style.animation='none';clone.style.transition='none';
  if(node.matches('input,textarea,select')){
    if(node.type==='range')return document.createTextNode('');
    const label=document.createElement('span');label.style.cssText=clone.style.cssText;
    label.textContent=node.type==='checkbox'?(node.checked?'✓':'○'):node.type==='range'?'':node.value;
    if(node.matches('textarea'))Object.assign(label.style,{height:'auto',maxHeight:'none',overflow:'visible',whiteSpace:'pre-wrap',display:'block'});
    return label;
  }
  if(node.matches('button'))return document.createTextNode('');
  for(const child of node.childNodes)clone.appendChild(styledClone(child,imageSources));
  if(node.matches('.canvas-artifact,.artifact-content,.quickui,.qui-panel,.table-scroll,.qui-filtered-table,.canvas-resource-frame,.resource-frame-body,.resource-document,.resource-table')) {
    Object.assign(clone.style,{height:'auto',maxHeight:'none',overflow:'visible',contain:'none',contentVisibility:'visible'});
  }
  if(node.matches('.resource-frame-body,.resource-preview,img'))clone.style.flex='0 0 auto';
  if(node.matches('thead,th'))clone.style.position='static';
  node[preparation]?.(clone);
  return clone;
}
export async function captureComponent(node, scale=2) {
  if(!node?.isConnected)throw Error('The selected component is no longer available.');
  await document.fonts.ready;
  const images=Array.from(node.querySelectorAll('img'));await Promise.all(images.map(i=>i.decode()));
  const imageSources=new Map();
  for(const img of images)if(img.src.startsWith('blob:')){const blob=await(await fetch(img.src)).blob();if(blob.size>8*1024*1024)throw Error('Uploaded image exceeds export limits.');imageSources.set(img,await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);}));}
  if(node.matches('.canvas-resource-frame')&&node.querySelector('[role="alert"],[role="status"]'))throw Error('Wait for this authorized resource preview to load successfully before exporting.');
  const clone=styledClone(node,imageSources),host=document.createElement('div');
  const width=Math.max(240,node.offsetWidth,node.scrollWidth);
  Object.assign(host.style,{position:'fixed',left:'-100000px',top:'0',width:`${width}px`,pointerEvents:'none',zIndex:'-1'});
  Object.assign(clone.style,{position:'static',transform:'none',width:`${width}px`,height:'auto',maxHeight:'none',margin:'0',overflow:'visible',boxSizing:'border-box',outline:'none',boxShadow:'none'});
  // Isolate measurement from application !important rules (for example the
  // live table's 420px scroll cap). The serialized image has only inline styles.
  host.attachShadow({mode:'closed'}).appendChild(clone);document.body.appendChild(host);
  try{
    const w=Math.ceil(Math.max(width,clone.scrollWidth)),h=Math.ceil(Math.max(clone.offsetHeight,clone.scrollHeight));
    if(w*scale>16384||h*scale>16384||w*h*scale*scale>32000000)throw Error('Component exceeds the export memory limit. Choose 1×, filter rows, or export the table as CSV.');
    const serialized=new XMLSerializer().serializeToString(clone);
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml">${serialized}</div></foreignObject></svg>`;
    const img=new Image();img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);await img.decode();
    const canvas=document.createElement('canvas');canvas.width=w*scale;canvas.height=h*scale;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
    const origin=clone.getBoundingClientRect().top;
    canvas.exportBreaks=[...clone.querySelectorAll('tbody tr')].flatMap(row=>{const box=row.getBoundingClientRect();return [Math.round((box.top-origin)*scale),Math.round((box.bottom-origin)*scale)];}).sort((a,b)=>a-b);
    return canvas;
  }finally{host.remove();}
}
export async function imageBlob(canvas, type='png') {const blob=await new Promise(resolve=>canvas.toBlob(resolve,type==='jpeg'?'image/jpeg':'image/png',.95));if(!blob)throw Error('The browser could not encode this component.');return blob;}
export async function pdfPages(canvas, {orientation='landscape',margin=24,pageNumbers=true}={}) {
  const pageWidth=orientation==='landscape'?842:595,pageHeight=orientation==='landscape'?595:842;
  const availableW=pageWidth-2*margin, availableH=pageHeight-2*margin-(pageNumbers?18:0);
  const ratio=canvas.height/canvas.width<=1.7?Math.min(availableW/canvas.width,availableH/canvas.height):availableW/canvas.width;
  // Exceptionally tall components are sliced; never shrink a 1000-row table
  // into an unreadable single page or silently clip the remaining content.
  const sliceHeight=Math.max(1,Math.floor(availableH/ratio)),pages=[];
  for(let offset=0;offset<canvas.height;){
    let end=Math.min(canvas.height,offset+sliceHeight);
    if(end<canvas.height&&canvas.exportBreaks?.length){const candidates=canvas.exportBreaks.filter(y=>y<=end&&y>offset+sliceHeight*.25);if(candidates.length)end=candidates.at(-1);}
    const h=end-offset,slice=document.createElement('canvas');slice.width=canvas.width;slice.height=h;
    slice.getContext('2d').drawImage(canvas,0,offset,canvas.width,h,0,0,canvas.width,h);
    const data=new Uint8Array(await (await imageBlob(slice,'jpeg')).arrayBuffer());
    pages.push({data,width:slice.width,height:h,pageWidth,pageHeight,drawWidth:slice.width*ratio,drawHeight:h*ratio,x:margin,y:pageHeight-margin-h*ratio,pageNumbers});
    slice.width=0;slice.height=0;
    offset=end;
  }
  return pages;
}
export async function exportComponents(items, options={}) {
  const {format='png',scale=2,archive=false}=options;
  if(!items.length||items.length>120)throw Error('Select 1–120 supported components.');
  if(!['png','jpeg','pdf'].includes(format)||![1,2,3].includes(scale))throw Error('Choose a supported format and resolution.');
  const files=[],pages=[],failures=[];let totalBytes=0;
  const budget=size=>{if(totalBytes+size>160e6)throw Error('Export exceeds 160 MB. Choose fewer components.');totalBytes+=size;};
  // Sequential captures bound peak canvas memory and preserve supplied order.
  for(let i=0;i<items.length;i++){
    const item=items[i];let canvas;
    try{
      canvas=item.capture?await item.capture(scale):await captureComponent(item.node,scale);
      if(format==='pdf'){
        const componentPages=await pdfPages(canvas,options);
        budget(componentPages.reduce((n,p)=>n+p.data.length,0));
        if(archive)files.push({name:filename(item.title,i)+'.pdf',data:pdfBytes(componentPages)});else pages.push(...componentPages);
      }else {const data=new Uint8Array(await (await imageBlob(canvas,format)).arrayBuffer());budget(data.length);files.push({name:filename(item.title,i)+'.'+format,data});}
    }catch(e){failures.push(`${item.title||`Component ${i+1}`}: ${e.message}`);}
    finally{if(canvas){canvas.width=0;canvas.height=0;}}
  }
  if(!files.length&&!pages.length)throw Error(failures.join('\n'));
  if(failures.length)files.push({name:'export-failures.txt',data:bytes(failures.join('\n'))});
  if(archive||format!=='pdf'&&files.length>1){download(new Blob([zipBytes(files)],{type:'application/zip'}),'kumuta-components.zip');}
  else if(format==='pdf')download(new Blob([pdfBytes(pages)],{type:'application/pdf'}),'kumuta-components.pdf');
  else download(new Blob([files[0].data],{type:format==='jpeg'?'image/jpeg':'image/png'}),files[0].name);
  return {exported:items.length-failures.length,failures,pages:pages.length};
}
