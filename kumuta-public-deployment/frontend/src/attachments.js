export const FILE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "application/pdf",
];
export const MAX_FILE = 8 * 1024 * 1024;
export const MAX_FILES = 5;
export const MAX_TOTAL = 20 * 1024 * 1024;

// Validate the whole batch before changing the draft, regardless of input source.
export function validateFiles(existing, incoming) {
  const files = [...existing, ...incoming];
  if (files.length > MAX_FILES) return "Attach up to 5 files per message.";
  for (const file of incoming) {
    if (!FILE_TYPES.includes(file.type))
      return "Choose a PNG, JPG, WebP image or PDF document.";
    if (!file.size || file.size > MAX_FILE)
      return "Choose a nonempty file up to 8 MB.";
  }
  if (files.reduce((total, file) => total + file.size, 0) > MAX_TOTAL)
    return "Attachments exceed the 20 MB total limit per message.";
  return "";
}

export function clipboardImages(data) {
  return Array.from(data.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
}
