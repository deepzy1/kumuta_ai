import {componentSize} from './intelligentUI.js';
import { diagramSkeleton, validateManual } from './canvasArtifacts.js';

// Conversion stays in the installed native editor. Normalize every generated
// ID, including bound text, so retries use the same artifact/version namespace.
export function generationElements(content, namespace, x, y, convert, appearance) {
  validateManual(content);
  if(!/^[a-f0-9]{32}_v[1-9][0-9]*$/.test(namespace))throw Error('Invalid artifact version namespace.');
  if(content.engine==='C')throw Error('Custom generation is disabled.');
  const skeleton=content.engine==='A'?diagramSkeleton(content.payload,namespace,x-Math.min(...content.payload.nodes.map(n=>n.x)),y-Math.min(...content.payload.nodes.map(n=>n.y))):[{id:`${namespace}-anchor`,type:'rectangle',x,y,...componentSize(content.payload),strokeColor:'#ff6500',backgroundColor:'#ffffff',fillStyle:'solid',roughness:0}];
  const styled=appearance?skeleton.map(e=>({...e,strokeColor:e.type==='arrow'?'#111111':appearance.widget.color.mode==='system'?'#c45d32':appearance.widget.color.colors[0],backgroundColor:'#ffffff',...(e.label?{label:{...e.label,strokeColor:'#111111'}}:{})})):skeleton;
  const native=convert(styled,{regenerateIds:false});
  const ids=new Map(native.map((e,i)=>[e.id,`${namespace}-element-${i}`]));
  return native.map(e=>({...e,...(appearance&&e.type==='text'?{strokeColor:'#111111'}:{}),id:ids.get(e.id),index:null,
    ...(e.containerId?{containerId:ids.get(e.containerId)}:{}),
    ...(e.boundElements?{boundElements:e.boundElements.map(b=>({...b,id:ids.get(b.id)}))}:{}),
    ...(e.startBinding?{startBinding:{...e.startBinding,elementId:ids.get(e.startBinding.elementId)}}:{}),
    ...(e.endBinding?{endBinding:{...e.endBinding,elementId:ids.get(e.endBinding.elementId)}}:{})
  }));
}
