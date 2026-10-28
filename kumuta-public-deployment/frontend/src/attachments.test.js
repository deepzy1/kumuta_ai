import test from "node:test";
import assert from "node:assert/strict";
import {
  validateFiles,
  clipboardImages,
  MAX_FILE,
  MAX_TOTAL,
} from "./attachments.js";
const image = { name: "screenshot.png", type: "image/png", size: 100 };
const pdf = { name: "facts.pdf", type: "application/pdf", size: 200 };
test("all upload sources share atomic count, format and size validation", () => {
  assert.equal(validateFiles([image], [pdf]), "");
  assert.match(validateFiles([image], Array(5).fill(pdf)), /5 files/);
  assert.match(validateFiles([], [{ ...image, size: MAX_FILE + 1 }]), /8 MB/);
  assert.match(validateFiles([], [{ ...image, size: 0 }]), /nonempty/);
  assert.match(validateFiles([], [{ ...image, type: "text/plain" }]), /PNG/);
  assert.match(
    validateFiles([], Array(3).fill({ ...pdf, size: MAX_TOTAL / 3 + 1 })),
    /20 MB/,
  );
});
test("clipboard extracts every image while leaving text for normal paste", () => {
  const data = {
    items: [
      { kind: "string", type: "text/plain" },
      { kind: "file", type: "image/png", getAsFile: () => image },
      { kind: "file", type: "image/png", getAsFile: () => null },
      { kind: "file", type: "application/pdf" },
    ],
  };
  assert.deepEqual(clipboardImages(data), [image]);
});
