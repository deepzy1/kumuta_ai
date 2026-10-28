export function resourceReference(resource) {
  return {schema_version:1,kind:resource.kind,source_id:resource.source_id,fingerprint:resource.fingerprint,...(resource.format==='pdf'?{page:1}:{})};
}
export function resourceKey(resource) {return `${resource.kind}:${resource.source_id}`;}
export function validResourceFrames(frames,elements,artifacts=[]) {
  const ids=new Set(),anchors=new Set(artifacts.map(a=>a.anchor_id));
  return frames.length<=100&&frames.every(f=>{
    const e=elements.find(e=>e.id===f.anchor_id),r=f.reference;
    if(ids.has(f.id)||anchors.has(f.anchor_id)||!e||e.type!=='rectangle'||e.angle||e.groupIds?.length||e.frameId||e.width<240||e.width>2400||e.height<160||e.height>2400||f.schema_version!==1||!['document','dataset','image'].includes(r?.kind)||!Number.isSafeInteger(r.source_id)||r.source_id<1||!/^[a-f0-9]{64}$/.test(r.fingerprint))return false;
    ids.add(f.id);anchors.add(f.anchor_id);return true;
  });
}
