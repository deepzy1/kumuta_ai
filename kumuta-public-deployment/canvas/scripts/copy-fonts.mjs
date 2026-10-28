import { cpSync, mkdirSync } from 'node:fs';

// Serve Excalidraw's fonts locally in development and production.
const publicDirectory = new URL('../public/', import.meta.url);
mkdirSync(publicDirectory, { recursive: true });
cpSync(
  new URL('../node_modules/@excalidraw/excalidraw/dist/prod/fonts', import.meta.url),
  new URL('fonts/', publicDirectory),
  { recursive: true },
);
