import test from 'node:test';
import assert from 'node:assert/strict';
import { rasterizeSceneFiles } from './canvasSceneFiles.js';

test('SVG scene images become PNG without changing IDs, geometry or source state', async () => {
  const oldImage = globalThis.Image, oldDocument = globalThis.document;
  globalThis.Image = class {
    naturalWidth = 100; naturalHeight = 50;
    set src(value) { this.onload(); }
  };
  globalThis.document = { createElement: () => ({ getContext: () => ({ drawImage() {} }), toDataURL: () => 'data:image/png;base64,iVBORw0KGgo=' }) };
  try {
    const scene = { elements: [{ id: 'shape', fileId: 'svg', x: 7 }], files: {
      svg: { id: 'svg', mimeType: 'image/svg+xml', dataURL: 'data:image/svg+xml;base64,PHN2Zy8+', created: 1 },
      png: { id: 'png', mimeType: 'image/png', dataURL: 'unchanged' },
    } };
    const converted = await rasterizeSceneFiles(scene);
    assert.equal(converted.files.svg.mimeType, 'image/png');
    assert.equal(converted.files.svg.id, 'svg');
    assert.equal(converted.files.svg.created, 1);
    assert.equal(converted.elements, scene.elements);
    assert.equal(converted.files.png, scene.files.png);
    assert.equal(scene.files.svg.mimeType, 'image/svg+xml');
    await assert.rejects(rasterizeSceneFiles({ files: { bad: { mimeType: 'image/svg+xml', dataURL: 'https://example.com/image.svg' } } }), /inline/);
  } finally { globalThis.Image = oldImage; globalThis.document = oldDocument; }
});
