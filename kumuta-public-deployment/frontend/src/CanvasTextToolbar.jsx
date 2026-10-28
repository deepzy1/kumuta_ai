import React from 'react';

// Only fields the installed native editor supports. Its mutation API owns history.
export default function CanvasTextToolbar({elements,selected,update,readOnly}) {
  const text=elements.filter(e=>!e.isDeleted&&e.type==='text'&&(selected.includes(e.id)||selected.includes(e.containerId)));
  if(!text.length||readOnly)return null;
  const first=text[0],patch=value=>update(text.map(e=>e.id),value);
  return <div className="canvas-text-toolbar" role="toolbar" aria-label="Text typography" onPointerDown={e=>e.stopPropagation()}>
    <label>Font<select aria-label="Text font family" value={first.fontFamily} onChange={e=>patch({fontFamily:Number(e.target.value)})}><option value={2}>Sans serif</option><option value={1}>Handwritten</option><option value={3}>Monospace</option></select></label>
    <label>Size<input aria-label="Text font size" type="number" min={8} max={120} value={first.fontSize} onChange={e=>{const n=Number(e.target.value);if(n>=8&&n<=120)patch({fontSize:n});}} /></label>
    <label>Align<select aria-label="Text alignment" value={first.textAlign} onChange={e=>patch({textAlign:e.target.value})}><option>left</option><option>center</option><option>right</option></select></label>
    <label>Color<input aria-label="Text color" type="color" value={/^#[0-9a-f]{6}$/i.test(first.strokeColor)?first.strokeColor:'#111111'} onChange={e=>patch({strokeColor:e.target.value})} /></label>
    <label>Line height<select aria-label="Text line height" value={first.lineHeight||1.25} onChange={e=>patch({lineHeight:Number(e.target.value)})}>{[1,1.25,1.5,1.75,2].map(n=><option key={n}>{n}</option>)}</select></label>
  </div>;
}
