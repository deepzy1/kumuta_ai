// Native Excalidraw accepts SVG images; persisted board scenes accept raster images.
// Convert only inline SVGs, preserving file IDs and native image geometry.
export async function rasterizeSceneFiles(scene) {
  if (!scene?.files) return scene;
  const files = { ...scene.files };
  for (const [id, file] of Object.entries(files)) {
    if (file.mimeType !== 'image/svg+xml') continue;
    if (!/^data:image\/svg\+xml(?:;base64,|;charset=[^,]+,|,)/i.test(file.dataURL || '')) {
      throw new Error('Canvas SVG images must contain inline image data.');
    }
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('Cannot convert this SVG image. Remove it or replace it with a PNG.'));
      image.src = file.dataURL;
    });
    const width = image.naturalWidth, height = image.naturalHeight;
    if (!width || !height || width > 8192 || height > 8192 || width * height > 16777216) {
      throw new Error('Canvas SVG image is too large. Replace it with a smaller PNG.');
    }
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Cannot convert Canvas image in this browser.');
    context.drawImage(image, 0, 0);
    const dataURL = canvas.toDataURL('image/png');
    if (!dataURL.startsWith('data:image/png;base64,') || dataURL.length > 6990530) {
      throw new Error('Converted Canvas image exceeds 5 MiB. Use a smaller PNG.');
    }
    files[id] = { ...file, mimeType: 'image/png', dataURL };
  }
  return { ...scene, files };
}
