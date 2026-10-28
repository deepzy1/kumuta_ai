import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
const canvas = process.env.KUMUTA_CANVAS_ROOT || fileURLToPath(new URL('../canvas/', import.meta.url));
const shared = fileURLToPath(new URL('./src/', import.meta.url));
export default defineConfig(({mode}) => {
  const env=loadEnv(mode, process.cwd(), '');
  return {
    plugins:[react(), {name:'kumuta-icon',generateBundle(){this.emitFile({type:'asset',fileName:'kumuta.svg',source:readFileSync(new URL('./public/kumuta.svg',import.meta.url))});},configureServer(server){server.middlewares.use('/kumuta.svg',(_req,res)=>{res.setHeader('Content-Type','image/svg+xml');res.end(readFileSync(new URL('./public/kumuta.svg',import.meta.url)));});}}],
    publicDir:`${canvas}/public`,
    resolve:{alias:{'@canvas':`${canvas}/src`,'@kumuta':shared,'@excalidraw/excalidraw/index.css':`${canvas}/node_modules/@excalidraw/excalidraw/dist/prod/index.css`,'@excalidraw/excalidraw':`${canvas}/node_modules/@excalidraw/excalidraw`},dedupe:['react','react-dom']},
    server:{port:5173,fs:{allow:[shared,canvas,fileURLToPath(new URL('.',import.meta.url))]},proxy:{'/api':{target:env.KUMUTA_API_PROXY_TARGET||'http://127.0.0.1:8000',changeOrigin:false,rewrite:path=>path.replace(/^\/api/,'')}}},
    build:{rollupOptions:{input:{main:fileURLToPath(new URL('./index.html',import.meta.url)),canvas:fileURLToPath(new URL('./canvas.html',import.meta.url))}}},
  };
});
