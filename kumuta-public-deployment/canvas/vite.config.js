import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
const shared = process.env.KUMUTA_MAIN_FRONTEND || fileURLToPath(new URL('../frontend/src/', import.meta.url));
export default defineConfig(({mode}) => {
const env=loadEnv(mode, process.cwd(), '');
return {
  plugins: [react()],
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify(env.VITE_API_URL || '/api') },
  resolve: { alias: { '@kumuta': shared }, dedupe: ['react', 'react-dom'] },
  server: { host: '0.0.0.0', port: 5174, strictPort: true, proxy: { '/api': { target: env.CANVAS_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin:false, rewrite:path=>path.replace(/^\/api/, '') } }, fs: { allow: [shared, fileURLToPath(new URL('.', import.meta.url))] } },
  preview: { port: 5174, strictPort: true },
};});
