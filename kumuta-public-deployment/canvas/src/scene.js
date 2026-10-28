import { validAnchors } from '../../frontend/src/canvasArtifacts.js';
import { validResourceFrames } from '../../frontend/src/canvasResources.js';
// D7-1 schema v1: persist drawing content, never browser/collaborator state.
export function sceneSnapshot(elements, appState = {}, files = {}, artifacts = [], resources = []) {
  const supported = new Set(['rectangle','diamond','ellipse','frame','magicframe','text','line','arrow','freedraw','image']);
  for (const element of elements) {
    if (!supported.has(element.type) || element.customData != null) {
      throw new Error('This scene contains an unsupported embed or custom element. Download a recovery copy before removing it.');
    }
  }
  if (!validAnchors(artifacts, elements)) throw new Error('Widget anchors must stay ungrouped, outside frames, unrotated and within supported sizes. Undo the last change or download recovery.');
  if (!validResourceFrames(resources,elements,artifacts)) throw new Error('Resource anchors must stay unrotated, ungrouped and within supported sizes. Undo the last change.');
  const ids = new Set(elements.map(e => e.fileId).filter(Boolean));
  const persistent = {};
  for (const key of ['viewBackgroundColor','gridSize','gridStep','gridModeEnabled']) {
    if (appState[key] !== undefined) persistent[key] = appState[key];
  }
  return {
    type: 'excalidraw', version: 2,
    ...(artifacts.length ? {artifacts} : {}),
    resources,
    elements: elements.map(e => Object.fromEntries(Object.entries(e).filter(([k]) => k !== 'customData'))),
    appState: persistent,
    files: Object.fromEntries([...ids].map(id => {
      const f = files[id];
      if (!f) throw new Error('An image is still loading or missing. Wait for it or download a recovery copy.');
      return [id, Object.fromEntries(['id','mimeType','dataURL','created','version'].filter(k => f[k] !== undefined).map(k => [k, f[k]]))];
    })),
  };
}

export function downloadScene(scene, title = 'board-recovery') {
  const blob = new Blob([JSON.stringify(scene, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = `${title.replace(/[^a-z0-9 _-]/gi, '_')}.excalidraw`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
