// Scene coordinates are independent of browser zoom and device pixel ratio.
export function scenePoint(clientX,clientY,rect,state){const z=state.zoom?.value||1;return {x:(clientX-rect.left)/z-state.scrollX,y:(clientY-rect.top)/z-state.scrollY};}
export function rectangle(a,b){return {x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(a.x-b.x),height:Math.abs(a.y-b.y)};}
export function selectionBounds(elements){
  const boxes=elements.filter(e=>!e.isDeleted).map(e=>{const c=Math.abs(Math.cos(e.angle||0)),s=Math.abs(Math.sin(e.angle||0)),w=e.width*c+e.height*s,h=e.width*s+e.height*c;return {x:e.x+e.width/2-w/2,y:e.y+e.height/2-h/2,width:w,height:h};});
  if(!boxes.length)return null;const x=Math.min(...boxes.map(b=>b.x)),y=Math.min(...boxes.map(b=>b.y));return {x,y,width:Math.max(...boxes.map(b=>b.x+b.width))-x,height:Math.max(...boxes.map(b=>b.y+b.height))-y};
}
export function capturePlan(source,region,dpr=1){
  if(![source.x,source.y,source.width,source.height,region.x,region.y,region.width,region.height,dpr].every(Number.isFinite)||source.width<0||source.height<0||region.width<=0||region.height<=0)throw Error('Invalid visual region.');
  const scale=Math.min(Math.max(1,dpr),1600/Math.max(source.width,source.height,region.width,region.height,1),Math.sqrt(1900000/Math.max(source.width*source.height,region.width*region.height,1)));
  return {scale,width:Math.max(1,Math.floor(region.width*scale)),height:Math.max(1,Math.floor(region.height*scale)),dx:(source.x-region.x)*scale,dy:(source.y-region.y)*scale};
}
export async function captureSelection(context,drawing,exportToCanvas,getCommonBounds){
  if(context.widgets.some(w=>w.engine==='C'))throw Error('Visual capture of custom HTML previews is unavailable. Select native content or structured widgets.');
  const ids=new Set(context.element_ids),anchors=new Set(context.widgets.map(w=>w.anchor_id));
  const elements=drawing.getSceneElements().filter(e=>ids.has(e.id)&&!anchors.has(e.id)&&!e.isDeleted);
  if(!elements.length)throw Error('This selection already has structured widget context; no native visual capture is needed.');
  const [x,y,x2,y2]=getCommonBounds(elements),source={x,y,width:x2-x,height:y2-y},plan=capturePlan(source,context.bounds,window.devicePixelRatio||1);
  const files={},all=drawing.getFiles();for(const e of elements){if(e.fileId&&all[e.fileId])files[e.fileId]=all[e.fileId];}
  // Export only selected native elements/files. No DOM, sidebar, menus or remote service.
  const image=await exportToCanvas({elements,files,appState:{exportBackground:true,viewBackgroundColor:'#ffffff'},exportPadding:0,getDimensions:(w,h)=>({width:Math.max(1,w),height:Math.max(1,h),scale:plan.scale})});
  const crop=document.createElement('canvas');crop.width=plan.width;crop.height=plan.height;const ctx=crop.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,crop.width,crop.height);ctx.drawImage(image,plan.dx,plan.dy);
  const blob=await new Promise(resolve=>crop.toBlob(resolve,'image/png'));
  if(!blob||blob.size>2*1024*1024)throw Error('Selection image exceeds 2 MiB. Select a smaller region.');
  return new File([blob],'selected-region.png',{type:'image/png'});
}
